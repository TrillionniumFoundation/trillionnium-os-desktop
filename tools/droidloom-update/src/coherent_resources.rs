//! Finite readback work and conservative aggregate output-space admission.
//! Admission is an observation, not a filesystem quota or reservation. The
//! enclosing build service still owns its hard deadline and process cgroup.
use crate::util::{Result, fail};
use std::{
    cell::RefCell,
    fs::{self, File, OpenOptions},
    os::{
        fd::{AsRawFd, FromRawFd, OwnedFd},
        unix::{
            ffi::OsStrExt,
            fs::{MetadataExt, OpenOptionsExt},
            process::CommandExt,
        },
    },
    path::{Path, PathBuf},
    process::{Child, Command, ExitStatus, Stdio},
    time::{Duration, Instant},
};

pub(super) const GIB: u64 = 1024 * 1024 * 1024;
pub(super) const MAX_TREE: u64 = 32 * GIB;
// Two blocks per member plus receipt/allocator headroom. The physical storage
// host's reserve is separately enforced by its original storage service.
pub(super) const METADATA_ALLOWANCE: u64 = 200_000 * 8192 + GIB;
const RESERVE: u64 = 16 * GIB;
const WORK_LIMIT: Duration = Duration::from_secs(4 * 60 * 60);
const POLL: Duration = Duration::from_millis(50);
const TERM_GRACE: Duration = Duration::from_secs(2);
const KILL_GRACE: Duration = Duration::from_secs(3);

pub(super) fn output_ancestor(path: &Path) -> Result<PathBuf> {
    let raw = path.as_os_str().as_bytes();
    if !path.is_absolute()
        || (raw != b"/"
            && raw[1..]
                .split(|b| *b == b'/')
                .any(|p| p.is_empty() || p == b"." || p == b".."))
    {
        return fail("image output path must be absolute and unaliased");
    }
    for parent in path.ancestors() {
        match fs::symlink_metadata(parent) {
            Ok(m) if m.is_dir() && !m.file_type().is_symlink() => {
                super::ordinary_absolute(parent, true)?;
                return Ok(parent.to_owned());
            }
            Ok(_) => return fail("image output ancestor is not an ordinary directory"),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e.into()),
        }
    }
    fail("image output has no existing ordinary filesystem ancestor")
}

pub(super) fn prepare_output_directory(path: &Path) -> Result<()> {
    // Refuse an existing alias before create_dir_all can follow it and create
    // new descendants outside the admitted output tree.
    let ancestor = output_ancestor(path)?;
    require_output_volume(path, fs::symlink_metadata(&ancestor)?.dev())?;
    fs::create_dir_all(path)?;
    super::ordinary_absolute(path, true)?;
    require_output_volume(path, fs::symlink_metadata(path)?.dev())?;
    checkpoint()
}

fn require_output_volume(path: &Path, device: u64) -> Result<()> {
    ACTIVE.with(|cell| {
        let active = cell.borrow();
        let Some(state) = active.as_ref() else {
            return Ok(());
        };
        if state.spaces.is_empty() {
            return Ok(());
        }
        let space = state
            .spaces
            .iter()
            .rev()
            .find(|space| path.starts_with(&space.path))
            .ok_or("image output is outside its admitted directories")?;
        if device != space.identity.0 {
            return fail("image output crosses into an unadmitted filesystem");
        }
        Ok(())
    })
}

struct SpaceCheck {
    directory: File,
    path: PathBuf,
    identity: (u64, u64),
    floor: u64,
}
struct State {
    deadline: Instant,
    spaces: Vec<SpaceCheck>,
}
thread_local! {
    // Inspection is synchronous. Nested calls inherit the original deadline.
    static ACTIVE: RefCell<Option<State>> = const { RefCell::new(None) };
}
pub(super) struct Scope {
    owner: bool,
    previous_spaces: usize,
    // A scope must be dropped on the thread that owns its state.
    _thread: std::marker::PhantomData<std::rc::Rc<()>>,
}
impl Scope {
    pub(super) fn read_only() -> Result<Self> {
        Self::with_limit(WORK_LIMIT)
    }
    fn with_limit(limit: Duration) -> Result<Self> {
        let scope = ACTIVE.with(|cell| {
            let mut active = cell.borrow_mut();
            let owner = active.is_none();
            if owner {
                *active = Some(State {
                    deadline: Instant::now() + limit,
                    spaces: Vec::new(),
                });
            }
            Scope {
                owner,
                previous_spaces: active.as_ref().unwrap().spaces.len(),
                _thread: std::marker::PhantomData,
            }
        });
        checkpoint()?;
        Ok(scope)
    }
    pub(super) fn writing(directory: &Path, additional_bytes: u64) -> Result<Self> {
        let scope = Self::read_only()?;
        super::ordinary_absolute(directory, true)?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(directory)?;
        let metadata = file.metadata()?;
        let required = additional_bytes
            .checked_add(METADATA_ALLOWANCE)
            .ok_or("aggregate image space overflow")?;
        let floor = admission_floor(available(&file)?, required, RESERVE)?;
        ACTIVE.with(|cell| {
            cell.borrow_mut().as_mut().unwrap().spaces.push(SpaceCheck {
                directory: file,
                path: directory.to_owned(),
                identity: (metadata.dev(), metadata.ino()),
                floor,
            })
        });
        checkpoint()?;
        Ok(scope)
    }
}
impl Drop for Scope {
    fn drop(&mut self) {
        ACTIVE.with(|cell| {
            let mut active = cell.borrow_mut();
            if self.owner {
                *active = None;
            } else if let Some(state) = active.as_mut() {
                state.spaces.truncate(self.previous_spaces);
            }
        });
    }
}
fn admission_floor(available: u64, required: u64, reserve: u64) -> Result<u64> {
    let needed = required
        .checked_add(reserve)
        .ok_or("aggregate image space overflow")?;
    if available < needed {
        return fail(
            "insufficient aggregate space for complete image readback/staging and reserve",
        );
    }
    Ok(available - required)
}
fn available(directory: &File) -> Result<u64> {
    let mut value = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    // SAFETY: fstatvfs initializes the object on success; the fd remains owned.
    if unsafe { libc::fstatvfs(directory.as_raw_fd(), value.as_mut_ptr()) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let value = unsafe { value.assume_init() };
    (value.f_bavail as u64)
        .checked_mul(value.f_frsize as u64)
        .ok_or_else(|| "filesystem free-space arithmetic overflow".into())
}
pub(super) fn checkpoint() -> Result<()> {
    ACTIVE.with(|cell| {
        let active = cell.borrow();
        let Some(state) = active.as_ref() else {
            return Ok(());
        };
        if Instant::now() >= state.deadline {
            return fail("complete image readback deadline expired");
        }
        for space in &state.spaces {
            let now = fs::symlink_metadata(&space.path)?;
            if !now.is_dir()
                || now.file_type().is_symlink()
                || (now.dev(), now.ino()) != space.identity
            {
                return fail("admitted image output filesystem was replaced");
            }
            if available(&space.directory)? < space.floor {
                return fail("aggregate image output space or reserve exhausted during work");
            }
        }
        if Instant::now() >= state.deadline {
            return fail("complete image readback deadline expired");
        }
        Ok(())
    })
}
fn exited(fd: &OwnedFd, wait: Duration) -> Result<bool> {
    let mut poll = libc::pollfd {
        fd: fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    let millis = i32::try_from(wait.as_millis()).map_err(|_| "reader poll duration overflow")?;
    // SAFETY: poll points to one initialized record; pidfd remains owned.
    let result = unsafe { libc::poll(&mut poll, 1, millis) };
    if result < 0 {
        let error = std::io::Error::last_os_error();
        if error.kind() == std::io::ErrorKind::Interrupted {
            return Ok(false);
        }
        return Err(error.into());
    }
    if poll.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
        return fail("original image reader pidfd observation failed");
    }
    Ok(poll.revents & (libc::POLLIN | libc::POLLHUP) != 0)
}
fn signal_group(child: &Child, signal: i32) -> Result<()> {
    let pid = i32::try_from(child.id()).map_err(|_| "reader PID overflow")?;
    // The original child starts its own group and has not been reaped. Its
    // PID/PGID cannot be recycled. Never signal after child.wait().
    if unsafe { libc::kill(-pid, signal) } != 0 {
        let e = std::io::Error::last_os_error();
        if e.raw_os_error() != Some(libc::ESRCH) {
            return Err(e.into());
        }
    }
    Ok(())
}
fn reap_until(child: &mut Child, end: Instant) -> Result<ExitStatus> {
    let mut observation_error = None;
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                if let Some(error) = observation_error {
                    return fail(format!(
                        "original image reader {} reaped ({status}) after a reap observation error: {error}",
                        child.id()
                    ));
                }
                if Instant::now() >= end {
                    return fail(format!(
                        "original image reader {} reaped ({status}) after its retirement deadline",
                        child.id()
                    ));
                }
                return Ok(status);
            }
            Ok(None) => (),
            Err(error) => {
                observation_error.get_or_insert_with(|| error.to_string());
            }
        }
        let now = Instant::now();
        if now >= end {
            return fail(format!(
                "image reader {} termination remains unconfirmed; enclosing service retirement required; reap observation: {observation_error:?}",
                child.id()
            ));
        }
        std::thread::sleep(POLL.min(end.saturating_duration_since(now)));
    }
}
fn kill_and_reap<S>(child: &mut Child, signal: &mut S) -> Result<ExitStatus>
where
    S: FnMut(&Child, i32) -> Result<()>,
{
    // All group signals precede the first try_wait: the original child is still
    // owned and unreaped, so its PID/PGID cannot have been recycled.
    let signal_error = signal(child, libc::SIGKILL).err();
    let reaped = reap_until(child, Instant::now() + KILL_GRACE);
    match (signal_error, reaped) {
        (None, result) => result,
        (Some(error), Ok(status)) => fail(format!(
            "image reader KILL failed: {error}; original image reader {} reaped ({status})",
            child.id()
        )),
        (Some(error), Err(reap_error)) => {
            fail(format!("image reader KILL failed: {error}; {reap_error}"))
        }
    }
}
fn retire_with<S, P>(child: &mut Child, fd: &OwnedFd, mut signal: S, mut observe: P) -> Result<()>
where
    S: FnMut(&Child, i32) -> Result<()>,
    P: FnMut(&OwnedFd, Duration) -> Result<bool>,
{
    let mut errors = Vec::new();
    match signal(child, libc::SIGTERM) {
        Err(error) => errors.push(format!("image reader TERM failed: {error}")),
        Ok(()) => {
            let end = Instant::now() + TERM_GRACE;
            while Instant::now() < end {
                match observe(fd, POLL.min(end.saturating_duration_since(Instant::now()))) {
                    Ok(true) => break,
                    Ok(false) => (),
                    Err(error) => {
                        errors.push(format!("image reader pidfd observation failed: {error}"));
                        break;
                    }
                }
            }
        }
    }
    // TERM or pidfd-observation failure never skips escalation and bounded reap.
    match kill_and_reap(child, &mut signal) {
        Ok(status) if !errors.is_empty() => errors.push(format!(
            "original image reader {} reaped ({status})",
            child.id()
        )),
        Ok(_) => (),
        Err(error) => errors.push(error.to_string()),
    }
    if errors.is_empty() {
        Ok(())
    } else {
        fail(errors.join("; "))
    }
}
fn retire(child: &mut Child, fd: &OwnedFd) -> Result<()> {
    retire_with(child, fd, signal_group, exited)
}
pub(super) fn run_reader(command: &mut Command) -> Result<()> {
    if !ACTIVE.with(|cell| cell.borrow().is_some()) {
        return fail("image transformations require an explicit finite readback scope");
    }
    checkpoint()?;
    command.stdin(Stdio::null()).process_group(0);
    let mut child = command.spawn()?;
    // SAFETY: pidfd_open uses the original unreaped child and flags zero.
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
    if raw < 0 {
        let error = std::io::Error::last_os_error();
        return match kill_and_reap(&mut child, &mut signal_group) {
            Ok(status) => fail(format!(
                "cannot bind original image reader: {error}; original image reader {} reaped ({status})",
                child.id()
            )),
            Err(cleanup) => fail(format!(
                "cannot bind original image reader: {error}; {cleanup}"
            )),
        };
    }
    let fd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
    let result = (|| -> Result<()> {
        loop {
            checkpoint()?;
            if exited(&fd, POLL)? {
                break;
            }
        }
        checkpoint()
    })();
    if let Err(error) = result {
        return match retire(&mut child, &fd) {
            Ok(()) => fail(format!(
                "{error}; original image reader {} reaped",
                child.id()
            )),
            Err(cleanup) => fail(format!("{error}; {cleanup}")),
        };
    }
    // Fixed direct reader executables use no shell/detached helper. Retire the
    // group before reaping even on successful original-child exit.
    let status = kill_and_reap(&mut child, &mut signal_group)?;
    if !status.success() {
        return fail(format!("image reader failed ({status}): {command:?}"));
    }
    checkpoint()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn aggregate_space_rejects_combined_outputs_and_overflow() {
        assert_eq!(admission_floor(100, 60, 30).unwrap(), 40);
        assert!(admission_floor(100, 80, 30).is_err());
        assert!(admission_floor(u64::MAX, u64::MAX, 1).is_err());
    }
    #[test]
    fn nested_reader_scope_cannot_reset_an_expired_deadline() {
        assert!(
            Scope::with_limit(Duration::ZERO)
                .err()
                .unwrap()
                .to_string()
                .contains("deadline")
        );
        assert!(!ACTIVE.with(|cell| cell.borrow().is_some()));
        let scope = Scope::read_only().unwrap();
        ACTIVE.with(|cell| cell.borrow_mut().as_mut().unwrap().deadline = Instant::now());
        assert!(Scope::read_only().is_err());
        assert!(checkpoint().is_err());
        drop(scope);
        assert!(Scope::read_only().is_ok());
    }
    #[test]
    fn reader_rejects_absent_scope_before_spawning() {
        assert!(run_reader(&mut Command::new("/bin/true")).is_err());
    }
    #[test]
    fn successful_reader_finishes_inside_original_scope() {
        let _scope = Scope::read_only().unwrap();
        run_reader(&mut Command::new("/bin/true")).unwrap();
        checkpoint().unwrap();
    }
    #[test]
    fn original_reader_is_reaped_after_deadline() {
        let _scope = Scope::with_limit(Duration::from_millis(100)).unwrap();
        let start = Instant::now();
        let error = run_reader(Command::new("/bin/sleep").arg("10")).unwrap_err();
        assert!(error.to_string().contains("deadline"));
        assert!(!error.to_string().contains("unconfirmed"));
        assert!(
            error.to_string().contains("original image reader")
                && error.to_string().contains("reaped")
        );
        assert!(start.elapsed() < Duration::from_secs(6));
    }
    #[test]
    fn cleanup_errors_do_not_skip_original_child_reaping() {
        for fail_term in [true, false] {
            let mut child = Command::new("/bin/sleep")
                .arg("10")
                .stdin(Stdio::null())
                .process_group(0)
                .spawn()
                .unwrap();
            let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
            if raw < 0 {
                let error = std::io::Error::last_os_error();
                let cleanup = kill_and_reap(&mut child, &mut signal_group);
                panic!("test child pidfd binding failed: {error}; cleanup: {cleanup:?}");
            }
            let fd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
            let mut killed = false;
            let mut observed = false;
            let start = Instant::now();
            let result = retire_with(
                &mut child,
                &fd,
                |child, signal| {
                    if signal == libc::SIGTERM && fail_term {
                        return fail("injected TERM failure");
                    }
                    if signal == libc::SIGKILL {
                        killed = true;
                    }
                    signal_group(child, signal)
                },
                |_, _| {
                    observed = true;
                    fail("injected pidfd observation failure")
                },
            );
            let error = result.unwrap_err().to_string();
            assert!(killed);
            assert_eq!(observed, !fail_term);
            assert!(error.contains(if fail_term {
                "injected TERM failure"
            } else {
                "injected pidfd observation failure"
            }));
            assert!(error.contains("reaped") && !error.contains("unconfirmed"));
            assert!(child.try_wait().unwrap().is_some());
            assert!(start.elapsed() < Duration::from_secs(6));
        }
    }
    #[test]
    fn output_alias_is_rejected_before_creating_descendants() {
        let _scope = Scope::read_only().unwrap();
        let root = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        std::os::unix::fs::symlink(outside.path(), root.path().join("apex")).unwrap();
        assert!(
            prepare_output_directory(&root.path().join("apex/com.android.virt/nested")).is_err()
        );
        assert!(fs::read_dir(outside.path()).unwrap().next().is_none());
        let ordinary = root.path().join("ordinary/nested");
        prepare_output_directory(&ordinary).unwrap();
        assert!(ordinary.is_dir());
    }
}
