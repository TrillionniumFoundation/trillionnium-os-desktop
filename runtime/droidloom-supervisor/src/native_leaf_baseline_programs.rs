//! Fixed local ELF custody borrowed from the actual opaque Main selection.
//! Serializable pins are not authority. Only capture(&MainCustodyObservation)
//! reaches the two source-fixed names, after the normal inspector admitted Main.
//! No process is executed and no additional control request is issued.
use crate::main_custody::MainCustodyObservation;
use crate::normal_host_release::{MANAGER, NormalHostProgramPin, PRESENTER};
use sha2::{Digest, Sha256};
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path};
use std::time::Instant;

fn bad(why: &'static str) -> io::Error {
    io::Error::other(why)
}
fn before(end: Instant) -> io::Result<()> {
    if Instant::now() >= end {
        Err(bad("normal host ELF original budget expired"))
    } else {
        Ok(())
    }
}
fn f9(m: &std::fs::Metadata) -> [i128; 9] {
    [
        m.dev() as i128,
        m.ino() as i128,
        m.mode() as i128,
        m.uid() as i128,
        m.gid() as i128,
        m.nlink() as i128,
        m.len() as i128,
        m.mtime() as i128 * 1_000_000_000 + m.mtime_nsec() as i128,
        m.ctime() as i128 * 1_000_000_000 + m.ctime_nsec() as i128,
    ]
}
fn directory(fd: &File, owner: u32, group: u32) -> io::Result<[u64; 5]> {
    let m = fd.metadata()?;
    if !m.is_dir() || m.uid() != owner || m.gid() != group || m.mode() & 0o7022 != 0 {
        return Err(bad(
            "normal host ELF parent is not a protected original directory",
        ));
    }
    Ok([
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
    ])
}
fn open_child(parent: &File, name: &CStr, flags: i32) -> io::Result<File> {
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if fd < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(unsafe { File::from_raw_fd(fd) })
    }
}
struct Parent {
    name: CString,
    file: File,
    identity: [u64; 5],
}
struct HeldProgram {
    root: File,
    root_identity: [u64; 5],
    parents: Vec<Parent>,
    name: CString,
    file: File,
    identity: [i128; 9],
    bytes: u64,
    digest: String,
    owner: u32,
    group: u32,
}
impl HeldProgram {
    // Private root-relative primitive also supports isolated unprivileged tests.
    // The sole production caller supplies "/", owner/group 0 and the two constants.
    fn open(
        root: File,
        relative: &Path,
        pin: &NormalHostProgramPin,
        owner: u32,
        group: u32,
        end: Instant,
    ) -> io::Result<Self> {
        before(end)?;
        let root_identity = directory(&root, owner, group)?;
        let names = relative
            .components()
            .map(|p| match p {
                Component::Normal(n) => n
                    .to_str()
                    .ok_or_else(|| bad("normal program component is not UTF-8")),
                _ => Err(bad("normal program must have exact relative components")),
            })
            .collect::<io::Result<Vec<_>>>()?;
        if names.len() < 2 || names.len() > 16 {
            return Err(bad("normal program component bound"));
        }
        let mut parents: Vec<Parent> = Vec::new();
        for name in &names[..names.len() - 1] {
            before(end)?;
            let parent = parents.last().map_or(&root, |v| &v.file);
            let name =
                CString::new(*name).map_err(|_| bad("normal program component contains NUL"))?;
            let file = open_child(parent, &name, libc::O_PATH | libc::O_DIRECTORY)?;
            let identity = directory(&file, owner, group)?;
            parents.push(Parent {
                name,
                file,
                identity,
            });
        }
        let name = CString::new(
            *names
                .last()
                .ok_or_else(|| bad("normal program basename absent"))?,
        )
        .map_err(|_| bad("normal program basename contains NUL"))?;
        let parent = parents.last().map_or(&root, |v| &v.file);
        let file = open_child(parent, &name, libc::O_RDONLY | libc::O_NONBLOCK)?;
        let m = file.metadata()?;
        if !m.is_file()
            || m.uid() != owner
            || m.gid() != group
            || m.nlink() != 1
            || m.mode() & 0o7777 != 0o755
            || m.len() != pin.bytes
            || !(64..=crate::normal_host_release::MAX_PROGRAM_BYTES).contains(&pin.bytes)
        {
            return Err(bad(
                "normal host ELF must be the exact protected regular program",
            ));
        }
        let mut value = Self {
            root,
            root_identity,
            parents,
            name,
            file,
            identity: f9(&m),
            bytes: pin.bytes,
            digest: pin.sha256.clone(),
            owner,
            group,
        };
        value.verify_contents(end)?;
        Ok(value)
    }
    fn verify(&self, end: Instant) -> io::Result<()> {
        before(end)?;
        if directory(&self.root, self.owner, self.group)? != self.root_identity {
            return Err(bad("normal host ELF held root changed"));
        }
        let mut parent = &self.root;
        for row in &self.parents {
            before(end)?;
            let named = open_child(parent, &row.name, libc::O_PATH | libc::O_DIRECTORY)?;
            if directory(&named, self.owner, self.group)? != row.identity
                || directory(&row.file, self.owner, self.group)? != row.identity
            {
                return Err(bad("normal host ELF held/named parent changed"));
            }
            parent = &row.file;
        }
        let named = open_child(parent, &self.name, libc::O_RDONLY | libc::O_NONBLOCK)?;
        if f9(&named.metadata()?) != self.identity || f9(&self.file.metadata()?) != self.identity {
            return Err(bad("normal host ELF held/named identity changed"));
        }
        before(end)
    }
    fn verify_contents(&mut self, end: Instant) -> io::Result<()> {
        self.verify(end)?;
        self.file.seek(SeekFrom::Start(0))?;
        let mut hasher = Sha256::new();
        let mut bytes = 0u64;
        let mut block = [0u8; 65536];
        let mut header = Vec::with_capacity(64);
        loop {
            before(end)?;
            let n = self.file.read(&mut block)?;
            if n == 0 {
                break;
            }
            bytes = bytes
                .checked_add(n as u64)
                .ok_or_else(|| bad("normal program size overflow"))?;
            if bytes > self.bytes {
                return Err(bad("normal host ELF grew during read"));
            }
            if header.len() < 64 {
                header.extend_from_slice(&block[..n.min(64 - header.len())]);
            }
            hasher.update(&block[..n]);
        }
        if bytes != self.bytes
            || format!("{:x}", hasher.finalize()) != self.digest
            || header.len() != 64
            || &header[..6] != b"\x7fELF\x02\x01"
            || &header[18..20] != b"\x3e\x00"
        {
            return Err(bad(
                "normal host ELF bytes differ from the actual selected release",
            ));
        }
        self.verify(end)
    }
}
pub(crate) struct NormalHostPrograms {
    manager: HeldProgram,
    presenter: HeldProgram,
}
impl NormalHostPrograms {
    pub(crate) fn capture(main: &MainCustodyObservation, end: Instant) -> io::Result<Self> {
        before(end)?;
        let release = &main.facts().normal_host_release;
        release.validate().map_err(bad)?;
        if release.manager.bytes != main.peer().executable_bytes
            || release.manager.sha256 != main.peer().executable_sha256
        {
            return Err(bad(
                "normal selected manager differs from the authenticated actual peer",
            ));
        }
        let open = |pin: &NormalHostProgramPin, path: &'static str| -> io::Result<HeldProgram> {
            if pin.path != path {
                return Err(bad("normal host program path differs"));
            }
            let root = std::fs::OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open("/")?;
            HeldProgram::open(
                root,
                Path::new(
                    path.strip_prefix('/')
                        .ok_or_else(|| bad("normal program path"))?,
                ),
                pin,
                0,
                0,
                end,
            )
        };
        use std::os::unix::fs::OpenOptionsExt;
        let value = Self {
            manager: open(&release.manager, MANAGER)?,
            presenter: open(&release.presenter, PRESENTER)?,
        };
        value.verify(end)?;
        Ok(value)
    }
    pub(crate) fn verify(&self, end: Instant) -> io::Result<()> {
        self.manager.verify(end)?;
        self.presenter.verify(end)
    }
    pub(crate) fn verify_contents(&mut self, end: Instant) -> io::Result<()> {
        self.manager.verify_contents(end)?;
        self.presenter.verify_contents(end)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};
    use std::time::Duration;
    fn fixture() -> (tempfile::TempDir, NormalHostProgramPin) {
        let temp = tempfile::tempdir().unwrap();
        std::fs::create_dir(temp.path().join("bin")).unwrap();
        let mut raw = vec![0u8; 96];
        raw[..6].copy_from_slice(b"\x7fELF\x02\x01");
        raw[18..20].copy_from_slice(b"\x3e\x00");
        std::fs::write(temp.path().join("bin/program"), &raw).unwrap();
        std::fs::set_permissions(
            temp.path().join("bin/program"),
            std::fs::Permissions::from_mode(0o755),
        )
        .unwrap();
        let pin = NormalHostProgramPin {
            path: "unused test comparison".into(),
            bytes: raw.len() as u64,
            sha256: format!("{:x}", Sha256::digest(&raw)),
        };
        (temp, pin)
    }
    fn held(
        temp: &tempfile::TempDir,
        pin: &NormalHostProgramPin,
        end: Instant,
    ) -> io::Result<HeldProgram> {
        HeldProgram::open(
            File::open(temp.path())?,
            Path::new("bin/program"),
            pin,
            unsafe { libc::geteuid() },
            unsafe { libc::getegid() },
            end,
        )
    }
    #[test]
    fn native_leaf_program_holds_exact_bytes_and_rejects_replaced_named_inode() {
        let (t, p) = fixture();
        let end = Instant::now() + Duration::from_secs(3);
        let mut h = held(&t, &p, end).unwrap();
        h.verify_contents(end).unwrap();
        std::fs::rename(t.path().join("bin/program"), t.path().join("bin/old")).unwrap();
        std::fs::copy(t.path().join("bin/old"), t.path().join("bin/program")).unwrap();
        assert!(h.verify(end).is_err());
    }
    #[test]
    fn native_leaf_program_rejects_hash_links_writable_parent_and_expired_budget() {
        let (t, p) = fixture();
        let end = Instant::now() + Duration::from_secs(3);
        let mut wrong = p.clone();
        wrong.sha256 = "0".repeat(64);
        assert!(held(&t, &wrong, end).is_err());
        assert!(held(&t, &p, Instant::now()).is_err());
        std::fs::hard_link(t.path().join("bin/program"), t.path().join("other")).unwrap();
        assert!(held(&t, &p, end).is_err());
        std::fs::remove_file(t.path().join("other")).unwrap();
        std::fs::rename(t.path().join("bin/program"), t.path().join("original")).unwrap();
        symlink("../original", t.path().join("bin/program")).unwrap();
        assert!(held(&t, &p, end).is_err());
        std::fs::remove_file(t.path().join("bin/program")).unwrap();
        std::fs::rename(t.path().join("original"), t.path().join("bin/program")).unwrap();
        std::fs::set_permissions(t.path().join("bin"), std::fs::Permissions::from_mode(0o777))
            .unwrap();
        assert!(held(&t, &p, end).is_err());
    }
}
