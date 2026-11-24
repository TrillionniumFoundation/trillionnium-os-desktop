//! Held ordinary input bytes and create-only output files for the fixed activation producer.
//! An input digest is content custody, never permission to install or retire an owner.
use super::Result;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    ffi::CString,
    fs::{self, File, Metadata},
    io::{Seek, SeekFrom, Write},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{
            ffi::OsStrExt,
            fs::{FileExt, MetadataExt, PermissionsExt},
        },
    },
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct FilePin {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct FileIdentity {
    pub device: u64,
    pub inode: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
    pub links: u64,
    pub bytes: u64,
    pub modified_sec: i64,
    pub modified_nsec: i64,
    pub changed_sec: i64,
    pub changed_nsec: i64,
}
impl FileIdentity {
    pub(super) fn read(m: Metadata) -> Result<Self> {
        if !m.is_file() || m.nlink() != 1 || m.mode() & 0o7022 != 0 {
            return Err("activation input is not a single protected ordinary file".into());
        }
        Ok(Self {
            device: m.dev(),
            inode: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.len(),
            modified_sec: m.mtime(),
            modified_nsec: m.mtime_nsec(),
            changed_sec: m.ctime(),
            changed_nsec: m.ctime_nsec(),
        })
    }
}

pub(super) fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
pub(super) fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn components(path: &Path) -> Result<Vec<CString>> {
    let raw = path.as_os_str().as_bytes();
    if !raw.starts_with(b"/") || raw.contains(&0) {
        return Err("activation path must be absolute and contain no NUL".into());
    }
    let mut out = Vec::new();
    for part in raw[1..].split(|b| *b == b'/') {
        if part.is_empty() || part == b"." || part == b".." {
            return Err("activation path has an empty, dot or parent component".into());
        }
        out.push(CString::new(part)?);
    }
    Ok(out)
}
fn open_at(parent: &File, name: &std::ffi::CStr, flags: i32, mode: u32) -> Result<File> {
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            mode,
        )
    };
    if fd < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
pub(super) fn parent(path: &Path) -> Result<(File, CString)> {
    let mut names = components(path)?;
    let leaf = names.pop().ok_or("activation path has no leaf")?;
    let mut dir = File::open("/")?;
    for name in names {
        dir = open_at(
            &dir,
            &name,
            libc::O_PATH | libc::O_DIRECTORY | libc::O_NONBLOCK,
            0,
        )?;
    }
    Ok((dir, leaf))
}
pub(super) fn open_regular(path: &Path) -> Result<File> {
    let (dir, name) = parent(path)?;
    let file = open_at(&dir, &name, libc::O_RDONLY | libc::O_NONBLOCK, 0)?;
    FileIdentity::read(file.metadata()?)?;
    Ok(file)
}
pub(super) fn hash_file(file: &File, bytes: u64) -> Result<String> {
    let mut hash = Sha256::new();
    let mut buffer = vec![0; 1024 * 1024];
    let mut offset = 0u64;
    while offset < bytes {
        let size = usize::try_from((bytes - offset).min(buffer.len() as u64))?;
        let count = file.read_at(&mut buffer[..size], offset)?;
        if count == 0 {
            return Err("activation input truncated during read".into());
        }
        hash.update(&buffer[..count]);
        offset += count as u64;
    }
    let mut extra = [0];
    if file.read_at(&mut extra, bytes)? != 0 {
        return Err("activation input grew during read".into());
    }
    Ok(format!("{:x}", hash.finalize()))
}
pub(super) struct HeldFile {
    pin: FilePin,
    file: File,
    identity: FileIdentity,
}
impl HeldFile {
    pub(super) fn open(pin: &FilePin, max: u64) -> Result<Self> {
        if !valid_digest(&pin.sha256) || pin.bytes > max {
            return Err("activation input exceeds its bound or has an invalid digest".into());
        }
        let file = open_regular(&pin.path)?;
        let identity = FileIdentity::read(file.metadata()?)?;
        if identity.bytes != pin.bytes || hash_file(&file, pin.bytes)? != pin.sha256 {
            return Err("activation input content differs from the pinned normal product".into());
        }
        let held = Self {
            pin: pin.clone(),
            file,
            identity,
        };
        held.revalidate()?;
        Ok(held)
    }
    pub(super) fn pin(&self) -> &FilePin {
        &self.pin
    }
    pub(super) fn file(&self) -> &File {
        &self.file
    }
    pub(super) fn identity(&self) -> &FileIdentity {
        &self.identity
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        if FileIdentity::read(self.file.metadata()?)? != self.identity
            || FileIdentity::read(open_regular(&self.pin.path)?.metadata()?)? != self.identity
        {
            return Err("original activation input was changed, renamed or replaced".into());
        }
        Ok(())
    }
    pub(super) fn read_all(&self, max: u64) -> Result<Vec<u8>> {
        self.revalidate()?;
        if self.pin.bytes > max {
            return Err("activation read exceeds this member's bound".into());
        }
        let mut bytes = vec![0; usize::try_from(self.pin.bytes)?];
        self.file.read_exact_at(&mut bytes, 0)?;
        if digest(&bytes) != self.pin.sha256 {
            return Err("activation input changed while read".into());
        }
        self.revalidate()?;
        Ok(bytes)
    }
    pub(super) fn copy_new(&self, path: &Path, mode: u32) -> Result<FilePin> {
        self.revalidate()?;
        let mut out = new_file(path, mode)?;
        let mut hash = Sha256::new();
        let mut buffer = vec![0; 1024 * 1024];
        let mut count = 0u64;
        while count < self.pin.bytes {
            let size = usize::try_from((self.pin.bytes - count).min(buffer.len() as u64))?;
            self.file.read_exact_at(&mut buffer[..size], count)?;
            hash.update(&buffer[..size]);
            if buffer[..size].iter().all(|b| *b == 0) {
                out.seek(SeekFrom::Current(size as i64))?;
            } else {
                out.write_all(&buffer[..size])?;
            }
            count += size as u64;
        }
        self.revalidate()?;
        if format!("{:x}", hash.finalize()) != self.pin.sha256 {
            return Err("held activation input changed during independent copy".into());
        }
        out.set_len(count)?;
        out.sync_all()?;
        let actual = pin_file(path)?;
        if actual.bytes != self.pin.bytes || actual.sha256 != self.pin.sha256 {
            return Err("activation output full readback differs".into());
        }
        Ok(actual)
    }
}
pub(super) fn pin_file(path: &Path) -> Result<FilePin> {
    let file = open_regular(path)?;
    let before = FileIdentity::read(file.metadata()?)?;
    let sha256 = hash_file(&file, before.bytes)?;
    if FileIdentity::read(file.metadata()?)? != before
        || FileIdentity::read(open_regular(path)?.metadata()?)? != before
    {
        return Err("activation output changed during pinning".into());
    }
    Ok(FilePin {
        path: path.into(),
        bytes: before.bytes,
        sha256,
    })
}
pub(super) fn new_file(path: &Path, mode: u32) -> Result<File> {
    if mode & !0o777 != 0 || mode & 0o022 != 0 {
        return Err("unsafe activation output mode".into());
    }
    let (dir, name) = parent(path)?;
    let m = dir.metadata()?;
    if !m.is_dir() || m.uid() != unsafe { libc::geteuid() } || m.mode() & 0o022 != 0 {
        return Err("activation output parent is not protected by this writer".into());
    }
    let file = open_at(
        &dir,
        &name,
        libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,
        0o600,
    )?;
    file.set_permissions(fs::Permissions::from_mode(mode))?;
    Ok(file)
}
pub(super) fn write_new(path: &Path, bytes: &[u8], mode: u32) -> Result<FilePin> {
    let mut file = new_file(path, mode)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    let actual = pin_file(path)?;
    if actual.bytes != bytes.len() as u64 || actual.sha256 != digest(bytes) {
        return Err("activation metadata readback differs".into());
    }
    Ok(actual)
}
pub(super) fn private_dir(path: &Path) -> Result<()> {
    let (dir, name) = parent(path)?;
    let m = dir.metadata()?;
    if m.uid() != unsafe { libc::geteuid() } || m.mode() & 0o022 != 0 {
        return Err("activation stage parent is not protected by its writer".into());
    }
    if unsafe { libc::mkdirat(dir.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let new = open_at(&dir, &name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
    new.set_permissions(fs::Permissions::from_mode(0o700))?;
    new.sync_all()?;
    Ok(())
}
pub(super) fn ensure_dir(root: &Path, relative: &str) -> Result<PathBuf> {
    if relative.is_empty()
        || relative.starts_with('/')
        || relative
            .split('/')
            .any(|p| p.is_empty() || p == "." || p == "..")
    {
        return Err("unsafe activation relative directory".into());
    }
    let mut dir = if root == Path::new("/") {
        File::open("/")?
    } else {
        let (parent, name) = parent(root)?;
        open_at(&parent, &name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?
    };
    let check = |f: &File| -> Result<()> {
        let m = f.metadata()?;
        if !m.is_dir() || m.uid() != unsafe { libc::geteuid() } || m.mode() & 0o022 != 0 {
            return Err("activation tree is outside its writer's custody".into());
        }
        Ok(())
    };
    check(&dir)?;
    let mut path = root.to_owned();
    for part in relative.split('/') {
        let name = CString::new(part)?;
        let created = unsafe { libc::mkdirat(dir.as_raw_fd(), name.as_ptr(), 0o755) } == 0;
        if !created && std::io::Error::last_os_error().raw_os_error() != Some(libc::EEXIST) {
            return Err(std::io::Error::last_os_error().into());
        }
        let next = open_at(&dir, &name, libc::O_RDONLY | libc::O_DIRECTORY, 0)?;
        check(&next)?;
        if created {
            next.set_permissions(fs::Permissions::from_mode(0o755))?;
            next.sync_all()?;
        }
        dir.sync_all()?;
        dir = next;
        path.push(part);
    }
    Ok(path)
}

pub(super) fn no_privilege_xattrs(file: &File) -> Result<()> {
    let mut names = vec![0u8; 65536];
    let count =
        unsafe { libc::flistxattr(file.as_raw_fd(), names.as_mut_ptr().cast(), names.len()) };
    if count < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    names.truncate(count as usize);
    if !names.is_empty() && names.last() != Some(&0) {
        return Err("malformed extended attribute names".into());
    }
    for name in names.split(|b| *b == 0).filter(|n| !n.is_empty()) {
        if name != b"security.selinux" {
            return Err(
                "activation file has unrelated capability, ACL or other extended state".into(),
            );
        }
    }
    Ok(())
}
pub(super) fn sync_parent(path: &Path) -> Result<()> {
    let (dir, _) = parent(path)?;
    let fd = unsafe {
        libc::openat(
            dir.as_raw_fd(),
            c".".as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    unsafe { File::from_raw_fd(fd) }.sync_all()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_input_replacement_and_mutation_fail() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("source");
        fs::write(&path, b"normal bytes").unwrap();
        let pin = pin_file(&path).unwrap();
        let held = HeldFile::open(&pin, 64).unwrap();
        fs::rename(&path, dir.path().join("old")).unwrap();
        fs::write(&path, b"normal bytes").unwrap();
        assert!(held.revalidate().is_err());
        let held = HeldFile::open(&pin, 64).unwrap();
        fs::write(&path, b"altered bytes").unwrap();
        assert!(held.revalidate().is_err());
    }
    #[test]
    fn input_parent_alias_and_wrong_content_are_rejected() {
        let dir = tempfile::tempdir().unwrap();
        let real = dir.path().join("real");
        fs::create_dir(&real).unwrap();
        let path = real.join("source");
        fs::write(&path, b"normal").unwrap();
        let mut pin = pin_file(&path).unwrap();
        std::os::unix::fs::symlink(&real, dir.path().join("alias")).unwrap();
        pin.path = dir.path().join("alias/source");
        assert!(HeldFile::open(&pin, 64).is_err());
        pin.path = path;
        pin.sha256 = "0".repeat(64);
        assert!(HeldFile::open(&pin, 64).is_err());
    }
    #[test]
    fn create_only_copy_cannot_overwrite_or_alias_original() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("source");
        fs::write(&source, b"normal source bytes").unwrap();
        let pin = pin_file(&source).unwrap();
        let input = HeldFile::open(&pin, 64).unwrap();
        let destination = dir.path().join("copy");
        let copied = input.copy_new(&destination, 0o400).unwrap();
        assert_eq!(copied.sha256, pin.sha256);
        assert_ne!(
            fs::metadata(&source).unwrap().ino(),
            fs::metadata(&destination).unwrap().ino()
        );
        assert!(input.copy_new(&source, 0o400).is_err());
        assert!(input.copy_new(&destination, 0o400).is_err());
        input.revalidate().unwrap();
    }
}
