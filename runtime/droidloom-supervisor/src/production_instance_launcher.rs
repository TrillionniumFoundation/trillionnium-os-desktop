//! Every Android generation belongs to a live, fixed systemd launcher.
//! Boot-wide LSM preparation stays in board PID 1. Its kernel-lineage factory
//! creates each namespace tree for the fixed authenticated service client.
//! Only normal original-owner retirement releases the next generation.
use super::early_release::{UbuntuRoot, intake};
use super::*;

use std::os::unix::fs::{FileExt, OpenOptionsExt};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};
#[path = "production_instance_factory.rs"]
mod factory;
#[path = "production_instance_manager.rs"]
mod manager;
pub(crate) use factory::QueryEndpoint;
pub use factory::{run_instance_factory, run_instance_adopter};

const HANDOFF: &str = "/run/droidloom-early";
const STOP: &str = "/run/droidloom-early/readiness/shutdown-request";
const REQUEST_LABEL: &[u8] = b"u:object_r:p4_android_shutdown_request_t:s0";
const NAMESPACE_FILES: [(&str, &str, i32); 4] = [
    ("pidns", "pid", libc::CLONE_NEWPID),
    ("mntns", "mnt", libc::CLONE_NEWNS),
    ("userns", "user", libc::CLONE_NEWUSER),
    ("cgroupns-creation", "cgroup", libc::CLONE_NEWCGROUP),
];
#[repr(C)]
struct Plan {
    selection_sha256: [u8; 65],
    base_cohort_sha256: [u8; 65],
    host_uid: u32,
    uid_start: u32,
    uid_count: u32,
    gid_start: u32,
    gid_count: u32,
}
#[repr(C)]
struct NativeChild {
    pid: i32,
    pidfd: i32,
    lock: i32,
    namespaces: [i32; 4],
}
unsafe extern "C" {
    fn droidloom_instance_context() -> libc::c_int;
    fn droidloom_instance_spawn(plan: *const Plan, child: *mut NativeChild) -> libc::c_int;
}
fn invalid(reason: &'static str) -> io::Error {
    io::Error::other(reason)
}
fn cv(value: libc::c_int) -> io::Result<()> {
    if value < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}
fn digest(value: &str) -> io::Result<[u8; 65]> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(invalid("selected launcher digest is malformed"));
    }
    let mut result = [0; 65];
    result[..64].copy_from_slice(value.as_bytes());
    Ok(result)
}
fn identity(file: &File) -> io::Result<(u64, u64)> {
    let m = file.metadata()?;
    Ok((m.dev(), m.ino()))
}
fn named_identity(path: &Path) -> io::Result<(u64, u64)> {
    let node = std::fs::symlink_metadata(path)?;
    if node.file_type().is_symlink() {
        return Err(invalid("instance handle became a symbolic link"));
    }
    Ok((node.dev(), node.ino()))
}
fn check_fs(file: &File, magic: libc::c_long) -> io::Result<()> {
    let mut value = unsafe { std::mem::zeroed::<libc::statfs>() };
    cv(unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) })?;
    if value.f_type != magic {
        return Err(invalid("instance kernel object filesystem differs"));
    }
    Ok(())
}
fn ended(pidfd: &File) -> io::Result<bool> {
    check_fs(pidfd, 0x50494446)?;
    let mut value = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    loop {
        let result = unsafe { libc::poll(&mut value, 1, 0) };
        if result < 0 && io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
            continue;
        }
        cv(result)?;
        if value.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
            return Err(invalid("the original instance PIDFD is invalid"));
        }
        return Ok(result == 1 && value.revents & libc::POLLIN != 0);
    }
}
fn original_process(pid: u32) -> io::Result<File> {
    if pid <= 1 {
        return Err(invalid("an ordinary service process is required"));
    }
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
    if raw < 0 {
        return Err(io::Error::last_os_error());
    }
    let fd = unsafe { File::from_raw_fd(raw as i32) };
    if ended(&fd)? {
        return Err(invalid("resource owner already exited before custody"));
    }
    // Original Linux PID 1 separately authenticates the exact published
    // ExecStart, invocation and MainPID. Its broker role can enter only that
    // fixed executable; the broker performs its own selected-ELF admission.
    // A nondumpable service must never be inspected with extra SYS_PTRACE.
    for (lsm, expected) in [
        ("selinux", "u:r:droidloom_broker:s0"),
        ("apparmor", "droidloom-production-broker (enforce)"),
    ] {
        if std::fs::read_to_string(format!("/proc/{pid}/attr/{lsm}/current"))?
            .trim_end_matches(['\0', '\n'])
            != expected
        {
            return Err(invalid(
                "original resource owner has a different enforced role",
            ));
        }
    }
    if ended(&fd)? {
        return Err(invalid("original resource owner exited during admission"));
    }
    Ok(fd)
}
fn empty_readiness() -> io::Result<()> {
    // Original board policy prohibits kernel-domain directory enumeration.
    // Check the one fixed Android endpoint; original owner exit(0) separately
    // proves complete resource retirement before the factory removes any pin.
    match std::fs::symlink_metadata(format!("{HANDOFF}/readiness/droidloom_readiness")) {
        Err(e) if e.kind() == io::ErrorKind::NotFound => {}
        Err(e) => return Err(e),
        Ok(_) => {
            return Err(invalid(
                "the original Android readiness endpoint still exists",
            ));
        }
    }
    match std::fs::symlink_metadata("/run/droidloom-container/readiness.sock") {
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Ok(_) => Err(invalid("the public readiness endpoint has not retired")),
        Err(e) => Err(e),
    }
}
fn request(gid: u32, expected: u8) -> io::Result<File> {
    let held = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(STOP)?;
    let m = held.metadata()?;
    if !m.is_file()
        || m.uid() != 0
        || m.gid() != gid
        || m.mode() & 0o7777 != 0o640
        || m.nlink() != 1
        || m.len() != 1
    {
        return Err(invalid("the original shutdown request inode differs"));
    }
    check_fs(&held, libc::TMPFS_MAGIC)?;
    let mut label = [0u8; 128];
    let length = unsafe {
        libc::fgetxattr(
            held.as_raw_fd(),
            c"security.selinux".as_ptr(),
            label.as_mut_ptr().cast(),
            label.len(),
        )
    };
    if length < 0 {
        return Err(io::Error::last_os_error());
    }
    let bytes = &label[..length as usize];
    if bytes.strip_suffix(&[0]).unwrap_or(bytes) != REQUEST_LABEL {
        return Err(invalid(
            "shutdown request is not the boot-created typed inode",
        ));
    }
    let mut byte = [0];
    held.read_exact_at(&mut byte, 0)?;
    if byte[0] != expected {
        return Err(invalid("the original shutdown request phase differs"));
    }
    if named_identity(Path::new(STOP))? != identity(&held)? {
        return Err(invalid("shutdown request changed during admission"));
    }
    Ok(held)
}
struct Pin {
    name: &'static str,
    // Passed by the original child through its inherited private channel. No
    // ptrace credential crosses userns and no retiring bind mount is held open.
    object: File,
}
struct Child {
    pid: i32,
    pidfd: File,
    _lock: File,
    directory: File,
    pins: Vec<Pin>,
    generation: SealedFile,
    resources: SealedFile,
    fifo: File,
    stop: File,
    observer_gid: u32,
}
impl Child {
    fn spawn(plan: &Plan) -> io::Result<Self> {
        empty_readiness()?;
        let stop = request(
            plan.gid_start
                .checked_add(9999)
                .ok_or_else(|| invalid("observer GID overflow"))?,
            b'0',
        )?;
        let mut raw = NativeChild {
            pid: -1,
            pidfd: -1,
            lock: -1,
            namespaces: [-1; 4],
        };
        cv(unsafe { droidloom_instance_spawn(plan, &mut raw) })?;
        if raw.pid <= 1 || raw.pidfd < 0 || raw.lock < 0 || raw.namespaces.iter().any(|fd| *fd < 0)
        {
            return Err(invalid(
                "native creator did not retain its birth descriptors",
            ));
        }
        let pidfd = unsafe { File::from_raw_fd(raw.pidfd) };
        let lock = unsafe { File::from_raw_fd(raw.lock) };
        let directory = open_root_trusted(Path::new(HANDOFF)).map_err(io::Error::other)?;
        check_fs(&directory, libc::TMPFS_MAGIC)?;
        let mut pins = Vec::new();
        let objects = raw.namespaces.map(|fd| unsafe { File::from_raw_fd(fd) });
        for ((name, _space, kind), object) in NAMESPACE_FILES.into_iter().zip(objects) {
            check_fs(&object, 0x6e736673)?;
            if unsafe { libc::ioctl(object.as_raw_fd(), 0xb703u64) } != kind
                || identity(&object)? != named_identity(&Path::new(HANDOFF).join(name))?
            {
                return Err(invalid(
                    "published namespace is not the original clone namespace",
                ));
            }
            pins.push(Pin { name, object });
        }
        if identity(&pidfd)? != named_identity(&Path::new(HANDOFF).join("pidfd"))? {
            return Err(invalid(
                "published PIDFD is not the original clone descriptor",
            ));
        }
        let (generation, _) = SealedFile::read(&Path::new(HANDOFF).join("generation.json"), 4096)
            .map_err(io::Error::other)?;
        let (resources, _) = SealedFile::read(&Path::new(HANDOFF).join("resources.json"), 8192)
            .map_err(io::Error::other)?;
        let fifo = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(format!("{HANDOFF}/release"))?;
        let value = Self {
            pid: raw.pid,
            pidfd,
            _lock: lock,
            directory,
            pins,
            generation,
            resources,
            fifo,
            stop,
            observer_gid: plan.gid_start + 9999,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> io::Result<()> {
        if named_identity(Path::new(HANDOFF))? != identity(&self.directory)? {
            return Err(invalid("the original handoff directory changed"));
        }
        self.generation.revalidate().map_err(io::Error::other)?;
        self.resources.revalidate().map_err(io::Error::other)?;
        if named_identity(&Path::new(HANDOFF).join("pidfd"))? != identity(&self.pidfd)?
            || named_identity(&Path::new(HANDOFF).join("release"))? != identity(&self.fifo)?
            || named_identity(Path::new(STOP))? != identity(&self.stop)?
        {
            return Err(invalid("an original instance handoff inode changed"));
        }
        for pin in &self.pins {
            if named_identity(&Path::new(HANDOFF).join(pin.name))? != identity(&pin.object)? {
                return Err(invalid("an original instance namespace pin changed"));
            }
        }
        Ok(())
    }
    fn retire(self) -> io::Result<()> {
        self.revalidate()?;
        if !ended(&self.pidfd)? {
            return Err(invalid("the original Android PID 1 has not exited"));
        }
        empty_readiness()?;
        let stop = request(self.observer_gid, b'1')?;
        if identity(&stop)? != identity(&self.stop)? {
            return Err(invalid(
                "shutdown request was replaced after the original owner exited",
            ));
        }
        // The caller has just proved the exact selected resource owner's normal
        // exit(0). That path includes StopRequest, original PIDFD death, absence
        // of its exact /data and /metadata mount IDs and all resource retirement.
        // This launcher removes only its native handoff pins and records.
        for name in NAMESPACE_FILES.iter().map(|row| row.0).chain(["pidfd"]) {
            let expected = if name == "pidfd" {
                identity(&self.pidfd)?
            } else {
                identity(
                    &self
                        .pins
                        .iter()
                        .find(|pin| pin.name == name)
                        .ok_or_else(|| invalid("unknown original namespace"))?
                        .object,
                )?
            };
            if named_identity(&Path::new(HANDOFF).join(name))? != expected {
                return Err(invalid("namespace pin changed during retirement"));
            }
            let path = CString::new(format!("{HANDOFF}/{name}")).map_err(io::Error::other)?;
            cv(unsafe { libc::umount2(path.as_ptr(), 0) })?;
            let m = std::fs::symlink_metadata(format!("{HANDOFF}/{name}"))?;
            if !m.is_file()
                || m.uid() != 0
                || m.gid() != 0
                || m.nlink() != 1
                || m.mode() & 0o7777 != 0o400
            {
                return Err(invalid(
                    "unmounted handoff pin is not its private original mountpoint",
                ));
            }
            std::fs::remove_file(format!("{HANDOFF}/{name}"))?;
        }
        for name in ["generation.json", "resources.json", "release"] {
            std::fs::remove_file(format!("{HANDOFF}/{name}"))?;
        }
        stop.write_all_at(b"0", 0)?;
        stop.sync_data()?;
        let mut final_phase = [255];
        stop.read_exact_at(&mut final_phase, 0)?;
        if final_phase != [b'0'] {
            return Err(invalid("next-instance shutdown phase was not reset"));
        }
        // Reap only the child created with our retained PIDFD. No PID lookup or
        // signal can turn failed or timed-out shutdown into success.
        let mut info = unsafe { std::mem::zeroed::<libc::siginfo_t>() };
        cv(unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        })?;
        if unsafe { info.si_pid() } != self.pid {
            return Err(invalid("original Android child was not reaped"));
        }
        Ok(())
    }
}
/// Run the fixed per-generation launcher selected by the ordinary system manager.
/// It never exposes a request socket, command execution or a numeric PID API.
pub fn run_instance_launcher(shutdown: &AtomicBool) -> io::Result<()> {
    cv(unsafe { droidloom_instance_context() })?;
    let configuration = ConfigurationReadGuard::acquire()?;
    let Some((choice, _cell, _base)) =
        intake(UbuntuRoot::AfterSwitchRoot).map_err(io::Error::other)?
    else {
        return Err(invalid(
            "the instance launcher requires the selected shared-kernel release",
        ));
    };
    let manager = manager::Manager::acquire()?;
    let invocation = manager.verify_launcher()?;
    let child = factory::RemoteChild::connect()?;
    choice.revalidate().map_err(io::Error::other)?;
    manager.ready()?;
    let begin = Instant::now();
    let mut owner: Option<([u8; 16], u32, File)> = None;
    let mut observed_stop = None;
    loop {
        cv(unsafe { droidloom_instance_context() })?;
        configuration.revalidate()?;
        choice.revalidate().map_err(io::Error::other)?;
        child.revalidate()?;
        if manager.verify_launcher()? != invocation {
            return Err(invalid("the original instance-launcher invocation changed"));
        }
        let state = manager.owner()?;
        if let Some((id, pid, process)) = &owner {
            if state.clean_exit(id, *pid)? {
                if !ended(process)? {
                    return Err(invalid(
                        "resource-owner result preceded its original PIDFD exit",
                    ));
                }
                let observer = manager.observer()?;
                if observer.state == "inactive" && observer.main_pid == 0 {
                    if observer.exec_pid > 1
                        && (observer.code != 1
                            || observer.status != 0
                            || observer.result != "success")
                    {
                        return Err(invalid("the original observer did not retire normally"));
                    }
                    return child.retire();
                }
                if observer.state == "failed" {
                    return Err(invalid(
                        "the original observer failed during instance retirement",
                    ));
                }
            } else if ended(&child.pidfd)? && state.state == "active" {
                // Let the original owner observe the dead init and perform its
                // error cleanup. Its failed status can never release this slot.
            }
        } else if state.live() {
            let process = original_process(state.main_pid)?;
            let again = manager.owner()?;
            if again.invocation != state.invocation || again.main_pid != state.main_pid {
                return Err(invalid("resource owner changed during admission"));
            }
            owner = Some((state.invocation, state.main_pid, process));
        } else if begin.elapsed() > Duration::from_secs(240) || state.state == "failed" {
            return Err(invalid(
                "the original resource owner did not acquire this instance",
            ));
        }
        if shutdown.load(Ordering::Relaxed) {
            let first = observed_stop.get_or_insert_with(Instant::now);
            if first.elapsed() > Duration::from_secs(25) {
                return Err(invalid(
                    "launcher stop did not follow complete orderly owner retirement; original slot retained",
                ));
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn plan_digest_requires_the_exact_immutable_hash() {
        assert_eq!(digest(&"a".repeat(64)).unwrap()[64], 0);
        for bad in ["", "a", &"A".repeat(64), &"x".repeat(64), &"a".repeat(65)] {
            assert!(digest(bad).is_err());
        }
    }
}
