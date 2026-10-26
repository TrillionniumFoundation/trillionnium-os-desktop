//! Bounded physical custody helpers for new deployment files only.
use super::Result;
use serde::{Serialize, de::DeserializeOwned};
use sha2::{Digest, Sha256};
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::Path;

pub(super) fn root_directory(path: &Path) -> Result<()> {
    if !path.is_absolute() || path.canonicalize()? != path {
        return Err("Root path must be absolute and canonical".into());
    }
    for p in std::iter::once(path).chain(path.ancestors().skip(1)) {
        let m = std::fs::symlink_metadata(p)?;
        if !m.is_dir() || m.uid() != 0 || m.mode() & 0o022 != 0 {
            return Err(
                "Root ancestry must be physical, Root-owned and reject shared writes".into(),
            );
        }
    }
    Ok(())
}

pub(super) fn root_file(path: &Path, executable: bool) -> Result<File> {
    root_directory(path.parent().ok_or("file has no parent")?)?;
    if path.canonicalize()? != path {
        return Err("Root file aliases are refused".into());
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(path)?;
    let m = file.metadata()?;
    if !m.is_file()
        || m.uid() != 0
        || m.mode() & 0o022 != 0
        || m.nlink() != 1
        || m.len() > 2 * 1024 * 1024 * 1024
        || (executable && m.mode() & 0o111 == 0)
    {
        return Err("Root input must be bounded, single-link and protected".into());
    }
    if executable {
        let mut magic = [0; 4];
        file.read_exact(&mut magic)?;
        if magic != *b"\x7fELF" {
            return Err("the installed executable must be an actual ELF".into());
        }
        use std::io::Seek;
        file.rewind()?;
    }
    Ok(file)
}

pub(super) fn read_root_json<T: DeserializeOwned>(path: &Path) -> Result<T> {
    let mut file = root_file(path, false)?;
    if file.metadata()?.mode() & 0o7777 != 0o600
        || std::fs::metadata(path.parent().ok_or("missing parent")?)?.mode() & 0o7777 != 0o700
    {
        return Err("Root0600 input and Root0700 parent are required".into());
    }
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(65_537)
        .read_to_end(&mut bytes)?;
    if bytes.is_empty() || bytes.len() > 65_536 {
        return Err("Root JSON input bound".into());
    }
    Ok(serde_json::from_slice(&bytes)?)
}

/// Public frozen product documents may be Root0644 under a protected package;
/// they are not private administrative inputs or a source of authority.
pub(super) fn read_root_document<T: DeserializeOwned>(path: &Path) -> Result<T> {
    let mut file = root_file(path, false)?;
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(65_537)
        .read_to_end(&mut bytes)?;
    if bytes.is_empty() || bytes.len() > 65_536 {
        return Err("public product document bound".into());
    }
    Ok(serde_json::from_slice(&bytes)?)
}

pub(super) fn write_new(path: &Path, bytes: &[u8]) -> Result<()> {
    if bytes.is_empty() || bytes.len() > 65_536 {
        return Err("new deployment file bound".into());
    }
    let mut f = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    f.write_all(bytes)?;
    f.sync_all()?;
    File::open(path.parent().ok_or("new file has no parent")?)?.sync_all()?;
    Ok(())
}

pub(super) fn json_new(path: &Path, value: &impl Serialize) -> Result<()> {
    write_new(path, &serde_json::to_vec(value)?)
}

pub(super) fn digest(path: &Path) -> Result<String> {
    let mut f = root_file(path, false)?;
    let before = f.metadata()?;
    let mut hash = Sha256::new();
    let mut chunk = [0; 65_536];
    loop {
        let n = f.read(&mut chunk)?;
        if n == 0 {
            break;
        }
        hash.update(&chunk[..n]);
    }
    let after = f.metadata()?;
    let same = |m: &std::fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.len(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
        )
    };
    if same(&before) != same(&after) {
        return Err("Root input changed while hashing".into());
    }
    Ok(format!("{:x}", hash.finalize()))
}

pub(super) fn directory_new(path: &Path, mode: u32, owner: Option<(u32, u32)>) -> Result<()> {
    std::fs::DirBuilder::new().mode(mode).create(path)?;
    let f = File::open(path)?;
    if let Some((uid, gid)) = owner {
        // SAFETY: only the new pinned directory is changed; never traverse existing data.
        if unsafe { libc::fchown(f.as_raw_fd(), uid, gid) } != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
    }
    f.set_permissions(std::fs::Permissions::from_mode(mode))?;
    f.sync_all()?;
    File::open(path.parent().ok_or("directory has no parent")?)?.sync_all()?;
    Ok(())
}

pub(super) fn user_directory(path: &Path, uid: u32) -> Result<()> {
    let m = std::fs::symlink_metadata(path)?;
    if !path.is_absolute()
        || path.canonicalize()? != path
        || !m.is_dir()
        || m.uid() != uid
        || m.mode() & 0o077 != 0
    {
        return Err("actual private user directory required".into());
    }
    Ok(())
}

pub(super) fn json_new_user(path: &Path, value: &impl Serialize, uid: u32, gid: u32) -> Result<()> {
    let parent = path.parent().ok_or("user file has no parent")?;
    user_directory(parent, uid)?;
    let directory = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(parent)?;
    let name = std::ffi::CString::new(
        path.file_name()
            .ok_or("user file has no name")?
            .as_encoded_bytes(),
    )?;
    // SAFETY: create only under this pinned owner-controlled directory. No
    // pathname parent is re-resolved and no existing final file is replaced.
    let raw = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            0o600,
        )
    };
    if raw < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    use std::os::fd::FromRawFd;
    let mut file = unsafe { File::from_raw_fd(raw) };
    serde_json::to_writer(&mut file, value)?;
    file.flush()?;
    if unsafe { libc::fchown(file.as_raw_fd(), uid, gid) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    file.sync_all()?;
    directory.sync_all()?;
    Ok(())
}
