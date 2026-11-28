//! Fixed native-source CURRENT and the two original lock inodes.
//!
//! Only this module changes a worker thread's fsuid/fsgid, and only for the
//! compiled user-owned parent chain. The invoking thread and TGID retain their
//! original root credentials. No command, RPC, fork, or caller closure runs
//! with that temporary file identity. All user-phase paths use openat/fstatat;
//! /proc/self/fd is not traversable there without a DAC override capability.
use std::{
    ffi::{CStr, CString},
    fs::{self, File},
    io::{self, Write},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::fs::{FileExt, MetadataExt},
    },
    time::Instant,
};

pub const CURRENT: &str = "/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json";
const CURRENT_C: &CStr = c"/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json";
const CURRENT_NAME: &CStr = c"CONTINUATION_CURRENT.json";
const PARENTS: [&CStr; 4] = [c"home", c"alex", c"work", c"pocket4-android-final"];
const LOCK_NAMES: [&CStr; 2] = [
    c".CONTINUATION_CURRENT.lock",
    c".qpr1-kernel-control-8b88.lock",
];
const LIMIT: u64 = 2 * 1024 * 1024;
const FLAGS: i32 = libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK;

fn deny(s: &str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, s)
}
fn need(v: bool, s: &str) -> io::Result<()> {
    if v { Ok(()) } else { Err(deny(s)) }
}
fn fs_ids() -> (u32, u32) {
    // Linux's impossible UID/GID is the non-mutating query form.
    unsafe {
        (
            libc::syscall(libc::SYS_setfsuid, u32::MAX) as u32,
            libc::syscall(libc::SYS_setfsgid, u32::MAX) as u32,
        )
    }
}
fn root_thread() -> io::Result<()> {
    let (mut ruid, mut euid, mut suid) = (0, 0, 0);
    let (mut rgid, mut egid, mut sgid) = (0, 0, 0);
    if unsafe { libc::getresuid(&mut ruid, &mut euid, &mut suid) } != 0
        || unsafe { libc::getresgid(&mut rgid, &mut egid, &mut sgid) } != 0
    {
        return Err(io::Error::last_os_error());
    }
    need(
        [ruid, euid, suid] == [0; 3] && [rgid, egid, sgid] == [0; 3] && fs_ids() == (0, 0),
        "fixed native source access requires the original root thread",
    )
}
struct UserFiles {
    restored: bool,
}
impl UserFiles {
    fn enter() -> io::Result<Self> {
        root_thread()?;
        need(
            unsafe { libc::syscall(libc::SYS_gettid) } != unsafe { libc::getpid() } as libc::c_long,
            "temporary native file identity must not affect the TGID leader",
        )?;
        let mut out = Self { restored: false };
        let old_gid = unsafe { libc::syscall(libc::SYS_setfsgid, 1000_u32) } as u32;
        let old_uid = unsafe { libc::syscall(libc::SYS_setfsuid, 1000_u32) } as u32;
        if old_uid != 0 || old_gid != 0 || fs_ids() != (1000, 1000) {
            let _ = out.restore();
            return Err(deny("exact native file identity switch failed"));
        }
        Ok(out)
    }
    fn restore(&mut self) -> io::Result<()> {
        // Restore before any privileged path, RPC, caller continuation or exit.
        unsafe {
            libc::syscall(libc::SYS_setfsuid, 0_u32);
            libc::syscall(libc::SYS_setfsgid, 0_u32);
        }
        root_thread()?;
        self.restored = true;
        Ok(())
    }
}
impl Drop for UserFiles {
    fn drop(&mut self) {
        if !self.restored {
            // A failed explicit readback is reported by the enclosing worker.
            // This thread is joined and destroyed; it is never a pooled worker.
            unsafe {
                libc::syscall(libc::SYS_setfsuid, 0_u32);
                libc::syscall(libc::SYS_setfsgid, 0_u32);
            }
        }
    }
}
fn worker<T: Send>(f: impl FnOnce() -> io::Result<T> + Send) -> io::Result<T> {
    root_thread()?;
    let result = std::thread::scope(|scope| {
        scope
            .spawn(move || {
                root_thread()?;
                let result = f();
                root_thread()?;
                result
            })
            .join()
            .map_err(|_| deny("fixed native source worker panicked"))?
    });
    root_thread()?;
    result
}
fn user_files<T>(f: impl FnOnce() -> io::Result<T>) -> io::Result<T> {
    let mut identity = UserFiles::enter()?;
    let result = f();
    identity.restore()?;
    result
}
fn open_at(parent: i32, name: &CStr, flags: i32, mode: u32) -> io::Result<File> {
    let fd = unsafe { libc::openat(parent, name.as_ptr(), flags | FLAGS, mode) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
fn ns(s: i64, n: i64) -> io::Result<u64> {
    u64::try_from(i128::from(s) * 1_000_000_000 + i128::from(n))
        .map_err(|_| deny("negative native source timestamp"))
}
pub(crate) fn identity(m: &fs::Metadata) -> io::Result<[u64; 9]> {
    Ok([
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
        m.nlink(),
        m.len(),
        ns(m.mtime(), m.mtime_nsec())?,
        ns(m.ctime(), m.ctime_nsec())?,
    ])
}
fn named(parent: i32, name: &CStr) -> io::Result<[u64; 9]> {
    let mut m: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatat(parent, name.as_ptr(), &mut m, libc::AT_SYMLINK_NOFOLLOW) } != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok([
        m.st_dev,
        m.st_ino,
        u64::from(m.st_mode),
        u64::from(m.st_uid),
        u64::from(m.st_gid),
        m.st_nlink,
        m.st_size
            .try_into()
            .map_err(|_| deny("negative native source size"))?,
        ns(m.st_mtime, m.st_mtime_nsec)?,
        ns(m.st_ctime, m.st_ctime_nsec)?,
    ])
}
fn parent_ok(p: &[u64; 6]) -> bool {
    p[2] & libc::S_IFMT as u64 == libc::S_IFDIR as u64
        && p[2] & 0o022 == 0
        && (p[3..5] == [0, 0] || p[3..5] == [1000, 1000])
}
struct Parent {
    file: File,
    pin: [u64; 6],
}
struct Parents {
    rows: Vec<Parent>,
}
impl Parents {
    fn capture() -> io::Result<Self> {
        need(
            fs_ids() == (1000, 1000),
            "fixed parent walk requires its exact user file identity",
        )?;
        let root = open_at(libc::AT_FDCWD, c"/", libc::O_PATH | libc::O_DIRECTORY, 0)?;
        let pin: [u64; 6] = identity(&root.metadata()?)?[..6].try_into().unwrap();
        need(
            parent_ok(&pin) && pin[3..5] == [0, 0],
            "native source root changed",
        )?;
        let mut value = Self {
            rows: vec![Parent { file: root, pin }],
        };
        for name in PARENTS {
            let file = open_at(
                value.last().as_raw_fd(),
                name,
                libc::O_PATH | libc::O_DIRECTORY,
                0,
            )?;
            let pin: [u64; 6] = identity(&file.metadata()?)?[..6].try_into().unwrap();
            need(
                parent_ok(&pin),
                "native source parent is writable by another owner",
            )?;
            value.rows.push(Parent { file, pin });
        }
        value.guard()?;
        Ok(value)
    }
    fn last(&self) -> &File {
        &self
            .rows
            .last()
            .expect("fixed nonempty native source chain")
            .file
    }
    fn guard(&self) -> io::Result<()> {
        need(
            fs_ids() == (1000, 1000) && self.rows.len() == PARENTS.len() + 1,
            "complete native source parent walk required",
        )?;
        for (i, row) in self.rows.iter().enumerate() {
            need(
                parent_ok(&row.pin) && identity(&row.file.metadata()?)?[..6] == row.pin,
                "held native source parent changed",
            )?;
            let actual = if i == 0 {
                named(libc::AT_FDCWD, c"/")?
            } else {
                named(self.rows[i - 1].file.as_raw_fd(), PARENTS[i - 1])?
            };
            need(
                actual[..6] == row.pin,
                "native source parent name was replaced",
            )?;
        }
        Ok(())
    }
}
fn body(file: &File, size: u64) -> io::Result<Vec<u8>> {
    need(size > 0 && size <= LIMIT, "bounded native CURRENT required")?;
    let mut bytes = vec![0; size as usize];
    file.read_exact_at(&mut bytes, 0)?;
    need(
        file.read_at(&mut [0_u8; 1], size)? == 0,
        "native CURRENT grew",
    )?;
    Ok(bytes)
}

/// Read-only custody of the one fixed CURRENT. No path, UID, FD or JSON can
/// construct this value. It grants neither source adoption nor qualification.
pub struct NativeCurrent {
    parents: Parents,
    file: File,
    pin: [u64; 9],
    raw: Vec<u8>,
    pid: u32,
}
impl NativeCurrent {
    pub fn capture() -> io::Result<Self> {
        worker(|| {
            user_files(|| {
                let parents = Parents::capture()?;
                let file = open_at(parents.last().as_raw_fd(), CURRENT_NAME, libc::O_RDONLY, 0)?;
                let pin = identity(&file.metadata()?)?;
                need(
                    pin[2..6] == [0o100600, 1000, 1000, 1] && pin[6] > 0 && pin[6] <= LIMIT,
                    "native CURRENT must retain its exact original owner/mode",
                )?;
                let raw = body(&file, pin[6])?;
                let out = Self {
                    parents,
                    file,
                    pin,
                    raw,
                    pid: std::process::id(),
                };
                out.guard_user()?;
                Ok(out)
            })
        })
    }
    fn guard_user(&self) -> io::Result<()> {
        need(
            self.pid == std::process::id(),
            "native CURRENT belongs to another process",
        )?;
        self.parents.guard()?;
        need(
            identity(&self.file.metadata()?)? == self.pin
                && named(self.parents.last().as_raw_fd(), CURRENT_NAME)? == self.pin
                && named(libc::AT_FDCWD, CURRENT_C)? == self.pin
                && body(&self.file, self.pin[6])? == self.raw
                && identity(&self.file.metadata()?)? == self.pin
                && named(self.parents.last().as_raw_fd(), CURRENT_NAME)? == self.pin
                && named(libc::AT_FDCWD, CURRENT_C)? == self.pin,
            "native CURRENT full held/named bookend changed",
        )?;
        self.parents.guard()
    }
    pub fn guard(&self) -> io::Result<()> {
        worker(|| user_files(|| self.guard_user()))
    }
    /// Counts the fixed held root/ancestor/file OFDs; it grants no source authority.
    pub const fn retained_descriptor_bound() -> usize { PARENTS.len() + 2 }
    pub fn bytes(&self) -> &[u8] {
        &self.raw
    }
    pub fn file_identity(&self) -> [u64; 9] {
        self.pin
    }
    pub(crate) fn held_file(&self) -> &File {
        &self.file
    }

    /// The legacy explicit root adopter already owns the original exclusive
    /// locks and validates its one-field relation. This is only the fixed
    /// filesystem CAS; it cannot mint a WorkingSourceWitness or Complete.
    pub fn replace_adopted_source(
        &self,
        locks: &crate::control::NativeApplicationSourceLocks,
        after: &[u8],
        release_sha256: &str,
    ) -> io::Result<[u64; 9]> {
        locks.validate_for_adoption()?;
        let mut renamed = false;
        let out = self.replace_named(after, release_sha256, None, &mut renamed, true)?;
        locks.validate_for_adoption()?;
        Ok(out)
    }
    pub(crate) fn replace(
        &self,
        after: &[u8],
        release_sha256: &str,
        end: Option<Instant>,
        renamed: &mut bool,
    ) -> io::Result<[u64; 9]> {
        self.replace_named(after, release_sha256, end, renamed, false)
    }
    fn replace_named(
        &self,
        after: &[u8],
        release_sha256: &str,
        end: Option<Instant>,
        renamed: &mut bool,
        legacy: bool,
    ) -> io::Result<[u64; 9]> {
        need(
            !*renamed
                && !after.is_empty()
                && after.len() < LIMIT as usize
                && release_sha256.len() == 64
                && release_sha256
                    .bytes()
                    .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v)),
            "one exact bounded native source replacement required",
        )?;
        let prefix = if legacy {
            ".native-leaf-adoption"
        } else {
            ".working-native-source"
        };
        let temporary = CString::new(format!(
            "{prefix}-{}-{release_sha256}.new",
            std::process::id()
        ))
        .map_err(|_| deny("invalid fixed native source temporary"))?;
        worker(|| {
            user_files(|| {
                let before_end = || {
                    need(
                        end.is_none_or(|v| Instant::now() < v),
                        "native source CAS exhausted its original end",
                    )
                };
                before_end()?;
                self.guard_user()?;
                let directory = open_at(
                    self.parents.last().as_raw_fd(),
                    c".",
                    libc::O_RDONLY | libc::O_DIRECTORY,
                    0,
                )?;
                let mut file = open_at(
                    directory.as_raw_fd(),
                    &temporary,
                    libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,
                    0o600,
                )?;
                // fsuid/fsgid, not chown, creates this exact user-owned inode.
                file.write_all(after)?;
                file.sync_all()?;
                let pin = identity(&file.metadata()?)?;
                need(
                    pin[2..6] == [0o100600, 1000, 1000, 1]
                        && pin[6] == after.len() as u64
                        && named(directory.as_raw_fd(), &temporary)? == pin
                        && body(&file, pin[6])? == after
                        && identity(&file.metadata()?)? == pin,
                    "new native CURRENT inode/body changed before CAS",
                )?;
                self.guard_user()?;
                before_end()?;
                if unsafe {
                    libc::renameat(
                        directory.as_raw_fd(),
                        temporary.as_ptr(),
                        directory.as_raw_fd(),
                        CURRENT_NAME.as_ptr(),
                    )
                } != 0
                {
                    return Err(io::Error::last_os_error());
                }
                // Remains true even if fsync/readback/credential restoration fails.
                // The owner records this actual mutation and never retries it.
                *renamed = true;
                directory.sync_all()?;
                self.parents.guard()?;
                let actual = identity(&file.metadata()?)?;
                need(
                    actual[..8] == pin[..8]
                        && actual[8] >= pin[8]
                        && named(directory.as_raw_fd(), CURRENT_NAME)? == actual
                        && named(libc::AT_FDCWD, CURRENT_C)? == actual
                        && body(&file, actual[6])? == after
                        && identity(&file.metadata()?)? == actual,
                    "committed native CURRENT readback differs",
                )?;
                before_end()?;
                Ok(actual)
            })
        })
    }
}

/// Internal fixed lock custody. The files are root:root 0600: the user phase
/// only locates O_PATH inodes. The actual read/flock happens after restoring
/// root, through the worker's deliberate kernel magic link to that same inode.
pub(crate) struct NativeSourceLock {
    parents: Parents,
    file: File,
    pin: [u64; 9],
    index: usize,
    pid: u32,
}
impl NativeSourceLock {
    pub(crate) fn open(index: usize, pin: [u64; 9], exclusive: bool) -> io::Result<Self> {
        need(
            index < LOCK_NAMES.len() && pin[2..7] == [0o100600, 0, 0, 1, 0],
            "only the original two zero-length root source locks are admitted",
        )?;
        worker(|| {
            let (parents, path) = user_files(|| {
                let parents = Parents::capture()?;
                let path = open_at(
                    parents.last().as_raw_fd(),
                    LOCK_NAMES[index],
                    libc::O_PATH,
                    0,
                )?;
                need(
                    identity(&path.metadata()?)? == pin
                        && named(parents.last().as_raw_fd(), LOCK_NAMES[index])? == pin,
                    "fixed original source lock identity differs",
                )?;
                parents.guard()?;
                Ok((parents, path))
            })?;
            root_thread()?;
            let alias = CString::new(format!("/proc/thread-self/fd/{}", path.as_raw_fd())).unwrap();
            // This single kernel magic-link open is intentional and root-only.
            let fd = unsafe {
                libc::open(
                    alias.as_ptr(),
                    libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NONBLOCK,
                )
            };
            if fd < 0 {
                return Err(io::Error::last_os_error());
            }
            let file = unsafe { File::from_raw_fd(fd) };
            need(
                identity(&file.metadata()?)? == pin && identity(&path.metadata()?)? == pin,
                "source lock magic-link open differs from its held O_PATH inode",
            )?;
            if unsafe {
                libc::flock(
                    file.as_raw_fd(),
                    (if exclusive {
                        libc::LOCK_EX
                    } else {
                        libc::LOCK_SH
                    }) | libc::LOCK_NB,
                )
            } != 0
            {
                return Err(io::Error::last_os_error());
            }
            user_files(|| {
                parents.guard()?;
                need(
                    named(parents.last().as_raw_fd(), LOCK_NAMES[index])? == pin
                        && identity(&file.metadata()?)? == pin,
                    "original source lock changed during acquisition",
                )
            })?;
            Ok(Self {
                parents,
                file,
                pin,
                index,
                pid: std::process::id(),
            })
        })
    }
    pub(crate) fn guard(&self) -> io::Result<()> {
        worker(|| {
            user_files(|| {
                need(
                    self.pid == std::process::id() && self.index < LOCK_NAMES.len(),
                    "same-process fixed lock custody required",
                )?;
                self.parents.guard()?;
                need(
                    identity(&self.file.metadata()?)? == self.pin
                        && named(self.parents.last().as_raw_fd(), LOCK_NAMES[self.index])?
                            == self.pin,
                    "held original source lock changed",
                )?;
                self.parents.guard()
            })
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_native_source_parents_reject_foreign_owners_and_shared_writes() {
        for p in [[1, 2, 0o040755, 0, 0, 3], [1, 2, 0o040700, 1000, 1000, 2]] {
            assert!(parent_ok(&p));
        }
        for p in [
            [1, 2, 0o040775, 1000, 1000, 2],
            [1, 2, 0o040707, 0, 0, 2],
            [1, 2, 0o040755, 1001, 1000, 2],
            [1, 2, 0o040755, 1000, 1001, 2],
            [1, 2, 0o120755, 1000, 1000, 2],
        ] {
            assert!(!parent_ok(&p));
        }
        assert_eq!(PARENTS.len(), 4);
        assert_eq!(LOCK_NAMES.len(), 2);
        assert_eq!(CURRENT_NAME.to_bytes(), b"CONTINUATION_CURRENT.json");
    }
    #[test]
    fn fixed_native_source_nonroot_cannot_enter_user_scope_or_mint_current() {
        if unsafe { libc::geteuid() } == 0 {
            return;
        }
        assert!(root_thread().is_err());
        assert!(UserFiles::enter().is_err());
        assert!(NativeCurrent::capture().is_err());
    }
}


#[cfg(test)]
mod descriptor_budget_tests {
    use super::*;
    #[test]
    fn fixed_native_current_and_lock_parent_chain_matches_whole_suite_budget() {
        assert_eq!(NativeCurrent::retained_descriptor_bound(),
            crate::control::physical_qualification_channel::budget::resources::SOURCE_CHAIN_DESCRIPTORS);
        assert_eq!(LOCK_NAMES.len(),2);
    }
}
