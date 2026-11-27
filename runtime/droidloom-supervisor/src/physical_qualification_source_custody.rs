//! Installed working qualification source custody. The private channel mints
//! this handle only after the actual parent acknowledges this exact child.
//! A path, report or copied historical lock cannot construct this authority.
use super::{ChildPeer, EXE, Plan, error, f9, sha};
use crate::native_working_contract::PayloadPin;
use serde_json::{Value, json};
use std::fs::{File, OpenOptions};
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::{FileExt, OpenOptionsExt};
use std::path::{Component, Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;

pub(super) const CHILD_LOCK_FDS: [i32; 2] = [4, 5];
const LOCK_NAMES: [&str; 2] = ["source.lock", "application.lock"];

fn root() -> io::Result<()> {
    // SAFETY: these calls only query this process's actual credentials.
    if unsafe {
        (
            libc::getuid(),
            libc::geteuid(),
            libc::getgid(),
            libc::getegid(),
        )
    } != (0, 0, 0, 0)
    {
        return Err(error(
            "working source custody requires the actual root owner",
        ));
    }
    Ok(())
}
fn live(end: Instant) -> io::Result<()> {
    if Instant::now() >= end {
        return Err(error("working source custody's original deadline expired"));
    }
    Ok(())
}
fn lock_metadata(pin: &[u64; 9]) -> io::Result<()> {
    if pin[2] != u64::from(libc::S_IFREG | 0o600) || pin[3..7] != [0, 0, 1, 0] {
        return Err(error(
            "working source lock is not a new empty private root inode",
        ));
    }
    Ok(())
}
fn same_payload(a: &PayloadPin, b: &PayloadPin) -> bool {
    a.bytes == b.bytes && a.sha256 == b.sha256
}

/// Every pathname component is opened relative to an already held directory.
/// Parent identities deliberately omit mutable directory size/timestamps.
struct Directory {
    path: PathBuf,
    chain: Vec<(PathBuf, File, [u64; 9])>,
}
impl Directory {
    fn open(path: &Path, private: bool) -> io::Result<Self> {
        if !path.is_absolute()
            || path
                .components()
                .any(|c| !matches!(c, Component::RootDir | Component::Normal(_)))
        {
            return Err(error(
                "working source directory is not a canonical absolute path",
            ));
        }
        let mut chain = Vec::new();
        let mut current = PathBuf::from("/");
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&current)?;
        let pin = f9(&file)?;
        if pin[2] & 0o170000 != u64::from(libc::S_IFDIR)
            || pin[3..5] != [0, 0]
            || pin[2] & 0o022 != 0
        {
            return Err(error("working source root directory ownership differs"));
        }
        chain.push((current.clone(), file, pin));
        for component in path.components() {
            let Component::Normal(name) = component else {
                continue;
            };
            let parent = &chain
                .last()
                .ok_or_else(|| error("working source root absent"))?
                .1;
            let anchored =
                PathBuf::from(format!("/proc/self/fd/{}", parent.as_raw_fd())).join(name);
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(anchored)?;
            let pin = f9(&file)?;
            if pin[2] & 0o170000 != u64::from(libc::S_IFDIR)
                || pin[3..5] != [0, 0]
                || pin[2] & 0o022 != 0
            {
                return Err(error("working source directory ownership or type differs"));
            }
            current.push(name);
            chain.push((current.clone(), file, pin));
        }
        if current != path
            || (private
                && chain
                    .last()
                    .ok_or_else(|| error("working runtime directory absent"))?
                    .2[2]
                    != u64::from(libc::S_IFDIR | 0o700))
        {
            return Err(error(
                "working runtime directory is not the exact private installed directory",
            ));
        }
        let result = Self {
            path: path.into(),
            chain,
        };
        result.guard()?;
        Ok(result)
    }
    fn anchored(&self, name: &str) -> io::Result<PathBuf> {
        if name.is_empty() || name.contains('/') || name == "." || name == ".." {
            return Err(error("working source child name is not a single component"));
        }
        Ok(PathBuf::from(format!(
            "/proc/self/fd/{}",
            self.chain
                .last()
                .ok_or_else(|| error("working directory absent"))?
                .1
                .as_raw_fd()
        ))
        .join(name))
    }
    fn guard(&self) -> io::Result<()> {
        for (index, (path, held, pin)) in self.chain.iter().enumerate() {
            let anchored = if index == 0 {
                PathBuf::from("/")
            } else {
                PathBuf::from(format!(
                    "/proc/self/fd/{}",
                    self.chain[index - 1].1.as_raw_fd()
                ))
                .join(
                    path.file_name()
                        .ok_or_else(|| error("working directory component absent"))?,
                )
            };
            let relative = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(anchored)?;
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(path)?;
            if f9(held)?[..5] != pin[..5]
                || f9(&relative)?[..5] != pin[..5]
                || f9(&named)?[..5] != pin[..5]
            {
                return Err(error("held working source directory changed"));
            }
        }
        Ok(())
    }
}
struct ScopedLock {
    file: File,
    pin: [u64; 9],
    name: &'static str,
}
impl ScopedLock {
    fn create(directory: &Directory, name: &'static str) -> io::Result<Self> {
        directory.guard()?;
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(directory.anchored(name)?)?;
        let pin = f9(&file)?;
        lock_metadata(&pin)?;
        // SAFETY: the exclusively created descriptor is held for this object's lifetime.
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let result = Self { file, pin, name };
        result.guard(directory)?;
        Ok(result)
    }
    fn inherit(directory: &Directory, fd: i32, name: &'static str) -> io::Result<Self> {
        // This private constructor is called exactly once after Hello ACK. FD4/5
        // were duplicated from the parent's still-held exclusive OFDs pre_exec.
        // SAFETY: fcntl validates the reserved inherited descriptor before ownership.
        if unsafe { libc::fcntl(fd, libc::F_GETFD) } < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: this function consumes the reserved descriptor once.
        let file = unsafe { File::from_raw_fd(fd) };
        if unsafe { libc::fcntl(file.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
            return Err(io::Error::last_os_error());
        }
        let pin = f9(&file)?;
        lock_metadata(&pin)?;
        // The actual parent still holds its exclusive flock. A separately opened
        // inode descriptor fails here; the inherited same OFD succeeds.
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(error(
                "working source descriptor does not share the parent's exclusive OFD",
            ));
        }
        let result = Self { file, pin, name };
        result.guard(directory)?;
        Ok(result)
    }
    fn guard(&self, directory: &Directory) -> io::Result<()> {
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(directory.anchored(self.name)?)?;
        if f9(&self.file)? != self.pin || f9(&named)? != self.pin {
            return Err(error("working source lock inode or full identity changed"));
        }
        lock_metadata(&self.pin)?;
        require_exclusive_conflict(&named)?;
        Ok(())
    }
    fn duplicate_for_exec(&self) -> io::Result<OwnedFd> {
        // SAFETY: duplicate only the held descriptor, away from stdio and FD3/4/5.
        let fd = unsafe { libc::fcntl(self.file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: fcntl returned a new owned descriptor.
        Ok(unsafe { OwnedFd::from_raw_fd(fd) })
    }
}
fn require_exclusive_conflict(independent: &File) -> io::Result<()> {
    // A new open description must conflict with the retained exclusive lock.
    // On unexpected success, close releases only this probe; no source OFD is unlocked.
    let result = unsafe { libc::flock(independent.as_raw_fd(), libc::LOCK_SH | libc::LOCK_NB) };
    if result == 0 {
        return Err(error("working source exclusive lock was lost"));
    }
    let e = io::Error::last_os_error();
    if e.kind() != io::ErrorKind::WouldBlock {
        return Err(e);
    }
    Ok(())
}
struct Executable {
    parent: Directory,
    file: File,
    pin: [u64; 9],
    payload: PayloadPin,
}
impl Executable {
    fn open(payload: &PayloadPin) -> io::Result<Self> {
        payload.validate(128 * 1024 * 1024)?;
        let path = Path::new(EXE);
        let parent = Directory::open(
            path.parent()
                .ok_or_else(|| error("applications parent absent"))?,
            false,
        )?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(parent.anchored("droidloom-applications")?)?;
        let pin = f9(&file)?;
        if pin[2] & 0o170000 != u64::from(libc::S_IFREG)
            || pin[2] & 0o6022 != 0
            || pin[2] & 0o111 == 0
            || pin[3..6] != [0, 0, 1]
            || pin[6] != payload.bytes
        {
            return Err(error("installed applications executable metadata differs"));
        }
        let result = Self {
            parent,
            file,
            pin,
            payload: payload.clone(),
        };
        result.guard()?;
        Ok(result)
    }
    fn guard(&self) -> io::Result<()> {
        self.parent.guard()?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(self.parent.anchored("droidloom-applications")?)?;
        let running = File::open("/proc/self/exe")?;
        if f9(&self.file)? != self.pin || f9(&named)? != self.pin || f9(&running)? != self.pin {
            return Err(error(
                "working source is not the actual admitted running applications ELF",
            ));
        }
        let mut raw = vec![0; self.payload.bytes as usize];
        self.file.read_exact_at(&mut raw, 0)?;
        if self.file.read_at(&mut [0; 1], self.payload.bytes)? != 0
            || sha(&raw) != self.payload.sha256
            || f9(&self.file)? != self.pin
            || f9(&named)? != self.pin
            || f9(&running)? != self.pin
        {
            return Err(error("whole admitted applications executable changed"));
        }
        Ok(())
    }
}

/// Parent-only custody is retained through child ACK/reaping and captured output.
/// Its fresh locks have no relationship to historical home-directory lock F9s.
pub(super) struct ParentWorkingNativeSourceCustody {
    directory: Directory,
    locks: [ScopedLock; 2],
    executable: Executable,
    pid: u32,
    end: Instant,
}
impl ParentWorkingNativeSourceCustody {
    pub(super) fn create(
        plan: &Plan,
        payload: &PayloadPin,
        runtime_evidence_directory: &Path,
        end: Instant,
    ) -> io::Result<Self> {
        root()?;
        live(end)?;
        plan.guard()?;
        if plan.working_runtime_evidence_directory()? != runtime_evidence_directory
            || !same_payload(plan.working_applications_pin()?, payload)
        {
            return Err(error(
                "working source inputs do not belong to the admitted installed plan",
            ));
        }
        let directory = Directory::open(runtime_evidence_directory, true)?;
        let executable = Executable::open(payload)?;
        let locks = [
            ScopedLock::create(&directory, LOCK_NAMES[0])?,
            ScopedLock::create(&directory, LOCK_NAMES[1])?,
        ];
        if locks[0].pin[..2] == locks[1].pin[..2] {
            return Err(error("working source lock roles share an inode"));
        }
        let result = Self {
            directory,
            locks,
            executable,
            pid: std::process::id(),
            end,
        };
        result.guard()?;
        plan.guard()?;
        Ok(result)
    }
    pub(super) fn duplicate_for_exec(&self) -> io::Result<[OwnedFd; 2]> {
        self.guard()?;
        Ok([
            self.locks[0].duplicate_for_exec()?,
            self.locks[1].duplicate_for_exec()?,
        ])
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        live(self.end)?;
        self.guard_immutable()
    }
    /// Retirement rechecks source custody without granting any new work window.
    pub(super) fn guard_immutable(&self) -> io::Result<()> {
        root()?;
        if std::process::id() != self.pid {
            return Err(error("working source parent process changed"));
        }
        self.directory.guard()?;
        for lock in &self.locks {
            lock.guard(&self.directory)?;
        }
        self.executable.guard()
    }
    pub(super) fn comparison(&self) -> io::Result<Value> {
        self.guard_immutable()?;
        Ok(comparison(
            &self.directory,
            &self.locks,
            &self.executable,
            self.pid,
        ))
    }
}
struct WorkingCustody {
    peer: Arc<ChildPeer>,
    plan: Arc<Plan>,
    directory: Directory,
    locks: [ScopedLock; 2],
    executable: Executable,
    pid: u32,
    end: Instant,
}

/// No Deserialize, public fields or caller-facing constructor. A retained handle
/// carries the authenticated parent/plan, inherited exclusive OFDs and original end.
pub struct WorkingNativeSourceCustody {
    inner: Arc<WorkingCustody>,
}
impl WorkingNativeSourceCustody {
    pub(super) fn from_hello(
        peer: Arc<ChildPeer>,
        plan: Arc<Plan>,
        end: Instant,
    ) -> io::Result<Self> {
        root()?;
        live(end)?;
        peer.guard()?;
        plan.guard()?;
        let directory = Directory::open(plan.working_runtime_evidence_directory()?, true)?;
        let executable = Executable::open(plan.working_applications_pin()?)?;
        let locks = [
            ScopedLock::inherit(&directory, CHILD_LOCK_FDS[0], LOCK_NAMES[0])?,
            ScopedLock::inherit(&directory, CHILD_LOCK_FDS[1], LOCK_NAMES[1])?,
        ];
        if locks[0].pin[..2] == locks[1].pin[..2] {
            return Err(error("inherited working lock roles share an inode"));
        }
        let result = Self {
            inner: Arc::new(WorkingCustody {
                peer,
                plan,
                directory,
                locks,
                executable,
                pid: std::process::id(),
                end,
            }),
        };
        result.guard()?;
        Ok(result)
    }
    pub(super) fn retained(&self) -> Self {
        Self {
            inner: Arc::clone(&self.inner),
        }
    }
    pub fn deadline(&self) -> Instant {
        self.inner.end
    }
    pub fn guard(&self) -> io::Result<()> {
        live(self.inner.end)?;
        self.guard_immutable()
    }
    /// Historical source comparison only; this cannot execute a case or renew its end.
    pub fn guard_immutable(&self) -> io::Result<()> {
        root()?;
        if self.inner.pid != std::process::id() {
            return Err(error("working source child process changed"));
        }
        self.inner.peer.guard()?;
        self.inner.plan.guard()?;
        self.inner.directory.guard()?;
        for lock in &self.inner.locks {
            lock.guard(&self.inner.directory)?;
        }
        self.inner.executable.guard()
    }
    pub fn applications_pin(&self) -> io::Result<(u64, &str)> {
        self.guard()?;
        Ok((
            self.inner.executable.payload.bytes,
            &self.inner.executable.payload.sha256,
        ))
    }
    pub fn comparison(&self) -> io::Result<Value> {
        self.guard_immutable()?;
        let mut value = comparison(
            &self.inner.directory,
            &self.inner.locks,
            &self.inner.executable,
            self.inner.pid,
        );
        value["physical_plan"] = json!({"path":self.inner.plan.path,
            "bytes":self.inner.plan.pin[6], "sha256":self.inner.plan.digest,
            "f9":self.inner.plan.pin});
        Ok(value)
    }
}
fn comparison(
    directory: &Directory,
    locks: &[ScopedLock; 2],
    executable: &Executable,
    pid: u32,
) -> Value {
    json!({"schema":"droidloom.working-native-source-custody.v1",
        "runtime_evidence_directory":directory.path,
        "fresh_source_lock":{"name":locks[0].name,"f9":locks[0].pin},
        "fresh_application_lock":{"name":locks[1].name,"f9":locks[1].pin},
        "applications":{"path":EXE,"bytes":executable.payload.bytes,
            "sha256":executable.payload.sha256,"f9":executable.pin},
        "actual_pid":pid,"historical_original_lock_identity_claimed":false,
        "runtime_qualified":false,"production_ready":false})
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    fn temporary() -> (PathBuf, File) {
        let path = std::env::temp_dir().join(format!(
            "droidloom-working-flock-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)
            .unwrap();
        (path, file)
    }
    #[test]
    fn inherited_open_description_keeps_exclusion_after_one_duplicate_closes() {
        let (path, file) = temporary();
        assert_eq!(
            unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        let duplicate = file.try_clone().unwrap();
        assert_eq!(
            unsafe { libc::flock(duplicate.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        let independent = File::open(&path).unwrap();
        require_exclusive_conflict(&independent).unwrap();
        drop(file);
        require_exclusive_conflict(&independent).unwrap();
        drop(duplicate);
        assert!(require_exclusive_conflict(&independent).is_err());
        drop(independent);
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn new_open_description_cannot_impersonate_inherited_exclusive_owner() {
        let (path, file) = temporary();
        assert_eq!(
            unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        let independent = File::open(&path).unwrap();
        assert_ne!(
            unsafe { libc::flock(independent.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
        drop(independent);
        drop(file);
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn replacement_inode_is_not_a_continuation_of_the_old_lock() {
        let (path, file) = temporary();
        let held = f9(&file).unwrap();
        std::fs::remove_file(&path).unwrap();
        let replacement = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)
            .unwrap();
        assert_ne!(held[..2], f9(&replacement).unwrap()[..2]);
        assert_ne!(held, f9(&file).unwrap());
        drop(replacement);
        drop(file);
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn lock_metadata_rejects_historical_or_mutated_identity_roles() {
        let pin = [1, 2, u64::from(libc::S_IFREG | 0o600), 0, 0, 1, 0, 8, 9];
        lock_metadata(&pin).unwrap();
        for (field, value) in [
            (2, u64::from(libc::S_IFREG | 0o640)),
            (3, 1000),
            (4, 1000),
            (5, 2),
            (6, 1),
        ] {
            let mut bad = pin;
            bad[field] = value;
            assert!(lock_metadata(&bad).is_err());
        }
        assert!(live(Instant::now()).is_err());
    }
}
