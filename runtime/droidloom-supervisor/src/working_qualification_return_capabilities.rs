//! Working-only credential custody for independent return metadata.
//! The three historical maintenance capabilities remain unchanged. A fourth
//! permitted bit is usable only inside the fixed PID1 read scope; it is absent
//! from the bounding set and is removed before every maintenance child exec.
use crate::native_once_capabilities::{self as original, Snapshot};
use std::{
    io,
    marker::PhantomData,
    rc::Rc,
    time::{Duration, Instant},
};

const SYS_PTRACE: u32 = 19;
const SETPCAP: u32 = 8;
const PTRACE: u64 = 1 << SYS_PTRACE;
pub(crate) const BOOTSTRAP: u64 = original::MAINTENANCE | PTRACE | (1 << SETPCAP);
const PERMITTED: u64 = original::MAINTENANCE | PTRACE;

#[repr(C)]
struct Header {
    version: u32,
    pid: i32,
}
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct Data {
    effective: u32,
    permitted: u32,
    inheritable: u32,
}

fn denied(why: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why)
}
fn checked(value: libc::c_long) -> io::Result<()> {
    if value < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}
fn set(effective: u64, permitted: u64) -> io::Result<()> {
    let header = Header {
        version: 0x2008_0522,
        pid: 0,
    };
    let data = [
        Data {
            effective: effective as u32,
            permitted: permitted as u32,
            inheritable: 0,
        },
        Data {
            effective: (effective >> 32) as u32,
            permitted: (permitted >> 32) as u32,
            inheritable: 0,
        },
    ];
    checked(unsafe { libc::syscall(libc::SYS_capset, &header, data.as_ptr()) })
}
fn initial() -> Snapshot {
    Snapshot {
        effective: BOOTSTRAP,
        permitted: BOOTSTRAP,
        inheritable: 0,
        ambient: 0,
        bounding: BOOTSTRAP,
        no_new_privs: false,
    }
}
fn sealed(effective: u64) -> Snapshot {
    Snapshot {
        effective,
        permitted: PERMITTED,
        inheritable: 0,
        ambient: 0,
        bounding: original::MAINTENANCE,
        no_new_privs: true,
    }
}
fn root() -> io::Result<()> {
    let mut ids = [1u32; 6];
    checked(unsafe { libc::getresuid(&mut ids[0], &mut ids[1], &mut ids[2]) } as _)?;
    checked(unsafe { libc::getresgid(&mut ids[3], &mut ids[4], &mut ids[5]) } as _)?;
    if ids != [0; 6] {
        return Err(denied(
            "working return lost its actual original root credentials",
        ));
    }
    Ok(())
}
fn one_thread() -> io::Result<()> {
    let pid = std::process::id();
    if unsafe { libc::syscall(libc::SYS_gettid) } as u32 != pid {
        return Err(denied(
            "working return metadata custody belongs only to its original main thread",
        ));
    }
    let mut entries = std::fs::read_dir("/proc/self/task")?;
    let only = entries
        .next()
        .transpose()?
        .ok_or_else(|| denied("working return task disappeared"))?;
    if only.file_name() != std::ffi::OsString::from(pid.to_string()) || entries.next().is_some() {
        return Err(denied(
            "working return refuses a second thread with different capability custody",
        ));
    }
    Ok(())
}
fn kernel_state(effective: u64) -> io::Result<()> {
    root()?;
    if original::inspect()? != sealed(effective)
        || unsafe { libc::prctl(libc::PR_GET_DUMPABLE, 0, 0, 0, 0) } != 0
    {
        return Err(denied("working return credential seal changed"));
    }
    Ok(())
}

/// Called before any normal return input, bus or evidence construction. The
/// unit's five initial bits are not the running parent's bounding contract.
pub(crate) fn seal() -> io::Result<()> {
    root()?;
    one_thread()?;
    if original::inspect()? != initial() {
        return Err(denied(
            "working return lacks its exact five-bit normal bootstrap contract",
        ));
    }
    // SETPCAP is used only to make both extra bounding bits irrecoverable.
    for bit in [SYS_PTRACE, SETPCAP] {
        checked(unsafe { libc::prctl(libc::PR_CAPBSET_DROP, bit, 0, 0, 0) } as _)?;
    }
    set(0, PERMITTED)?;
    checked(unsafe {
        libc::prctl(
            libc::PR_CAP_AMBIENT,
            libc::PR_CAP_AMBIENT_CLEAR_ALL,
            0,
            0,
            0,
        )
    } as _)?;
    checked(unsafe { libc::prctl(libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) } as _)?;
    checked(unsafe { libc::prctl(libc::PR_SET_DUMPABLE, 0, 0, 0, 0) } as _)?;
    revalidate()
}

/// Required outside every fixed metadata scope and immediately before spawn.
pub(crate) fn revalidate() -> io::Result<()> {
    one_thread()?;
    kernel_state(0)
}

/// Only the containing retired-parent module can construct this scope. It
/// accepts no target, pathname, callback, descriptor transfer or child command.
/// That module opens precisely PID1's seven namespace handles and executable;
/// no bus call, whole-file hash, output write or spawn occurs while E_PTRACE is
/// raised. MAC separately denies attach/write and every other process target.
pub(super) struct Pid1ReadScope {
    pid: u32,
    tid: libc::c_long,
    end: Instant,
    active: bool,
    _thread: PhantomData<Rc<()>>,
}
impl Pid1ReadScope {
    pub(super) fn enter(original_end: Instant) -> io::Result<Self> {
        revalidate()?;
        if Instant::now() >= original_end {
            return Err(denied(
                "fixed PID1 read has exhausted the original return end",
            ));
        }
        let mut value = Self {
            pid: std::process::id(),
            tid: unsafe { libc::syscall(libc::SYS_gettid) },
            end: original_end.min(Instant::now() + Duration::from_secs(2)),
            active: false,
            _thread: PhantomData,
        };
        set(PTRACE, PERMITTED)?;
        value.active = true;
        value.guard()?;
        Ok(value)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        if !self.active
            || self.pid != std::process::id()
            || self.tid != unsafe { libc::syscall(libc::SYS_gettid) }
            || Instant::now() >= self.end
        {
            return Err(denied(
                "fixed PID1 metadata scope changed thread or exceeded its immutable bound",
            ));
        }
        kernel_state(PTRACE)
    }
    fn restore_or_abort(&mut self) {
        if !self.active {
            return;
        }
        // No recoverable error may return with the effective bit left raised,
        // including an unexpected partial capability loss or an unwind.
        if self.pid != std::process::id()
            || self.tid != unsafe { libc::syscall(libc::SYS_gettid) }
            || set(0, PERMITTED).is_err()
            || kernel_state(0).is_err()
        {
            std::process::abort();
        }
        self.active = false;
    }
    pub(super) fn finish(mut self) -> io::Result<()> {
        let in_time = Instant::now() < self.end;
        self.restore_or_abort();
        revalidate()?;
        if !in_time {
            return Err(denied(
                "fixed PID1 metadata read exceeded its original scope",
            ));
        }
        Ok(())
    }
}
impl Drop for Pid1ReadScope {
    fn drop(&mut self) {
        self.restore_or_abort();
    }
}

/// Executed only in the actual freshly forked normal maintenance child, before
/// execveat. A successful child cannot carry P_PTRACE even before exec; the
/// unchanged historical seal then independently checks E0/P3/B3/I0/A0/NNP1.
pub(super) fn seal_maintenance_child() -> io::Result<()> {
    kernel_state(0)?;
    set(0, original::MAINTENANCE)?;
    original::revalidate()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs::File,
        os::fd::{AsRawFd, FromRawFd},
        process::Command,
    };
    const TEST: &str = "control::application_command::application_leaf_unit::qualification::retirement::capabilities::tests::actual_working_return_scope_and_exec_are_kernel_enforced";

    fn wait(pid: i32) -> io::Result<i32> {
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) } as i32;
        if raw < 0 {
            return Err(io::Error::last_os_error());
        }
        let handle = unsafe { File::from_raw_fd(raw) };
        let mut status = 0;
        if unsafe { libc::waitpid(pid, &mut status, 0) } != pid {
            return Err(io::Error::last_os_error());
        }
        let mut poll = libc::pollfd {
            fd: handle.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut poll, 1, 0) }, 1);
        assert_ne!(poll.revents & libc::POLLIN, 0);
        Ok(status)
    }
    fn denied_pid1() {
        for name in ["cgroup", "ipc", "mnt", "net", "pid", "user", "uts"] {
            let error = File::open(format!("/proc/1/ns/{name}")).unwrap_err();
            assert_eq!(error.raw_os_error(), Some(libc::EACCES));
        }
        assert_eq!(
            File::open("/proc/1/exe").unwrap_err().raw_os_error(),
            Some(libc::EACCES)
        );
    }
    fn isolated_child() -> io::Result<()> {
        // This child is the only thread after fork; its full-capability parent
        // remains this fresh namespace's live PID1, never the physical PID1.
        assert_ne!(std::process::id(), 1);
        File::open("/proc/1/exe")?;
        for bit in 0..=40 {
            if BOOTSTRAP & (1u64 << bit) == 0 {
                checked(unsafe { libc::prctl(libc::PR_CAPBSET_DROP, bit, 0, 0, 0) } as _)?;
            }
        }
        set(BOOTSTRAP, BOOTSTRAP)?;
        seal()?;
        denied_pid1();
        {
            let scope = Pid1ReadScope::enter(Instant::now() + Duration::from_secs(10))?;
            for name in ["cgroup", "ipc", "mnt", "net", "pid", "user", "uts"] {
                scope.guard()?;
                File::open(format!("/proc/1/ns/{name}"))?;
            }
            File::open("/proc/1/exe")?;
            scope.finish()?;
        }
        revalidate()?;
        denied_pid1();
        assert_eq!(
            set(BOOTSTRAP, BOOTSTRAP).unwrap_err().raw_os_error(),
            Some(libc::EPERM)
        );
        revalidate()?;

        // A restoration failure is terminal. There is no returning a normal
        // Result after the permitted PTRACE bit has unexpectedly disappeared.
        let broken = unsafe { libc::fork() };
        if broken < 0 {
            return Err(io::Error::last_os_error());
        }
        if broken == 0 {
            let scope = Pid1ReadScope::enter(Instant::now() + Duration::from_secs(10)).unwrap();
            set(0, original::MAINTENANCE).unwrap();
            drop(scope);
            unsafe {
                libc::_exit(90);
            }
        }
        let status = wait(broken)?;
        assert!(libc::WIFSIGNALED(status));
        assert_eq!(libc::WTERMSIG(status), libc::SIGABRT);
        revalidate()?;

        let mut command = Command::new(std::env::current_exe()?);
        command
            .args(["--exact", TEST, "--ignored", "--nocapture"])
            .env("DROIDLOOM_WORKING_RETURN_CAPS_TEST", "exec");
        use std::os::unix::process::CommandExt;
        unsafe {
            command.pre_exec(seal_maintenance_child);
        }
        let output = command.output()?;
        print!("{}", String::from_utf8_lossy(&output.stdout));
        eprint!("{}", String::from_utf8_lossy(&output.stderr));
        assert!(output.status.success());
        assert!(
            String::from_utf8_lossy(&output.stdout).contains("working_return_actual_child_caps=")
        );
        revalidate()?;
        println!(
            "working_return_actual_scope=8_descriptor_reads;restoration=SIGABRT;exec=original_three"
        );
        Ok(())
    }

    #[test]
    #[ignore = "requires a protected root runner; all credential mutations stay inside fresh user/PID namespaces"]
    fn actual_working_return_scope_and_exec_are_kernel_enforced() -> io::Result<()> {
        match std::env::var("DROIDLOOM_WORKING_RETURN_CAPS_TEST")
            .ok()
            .as_deref()
        {
            Some(phase) => {
                assert_ne!(
                    std::fs::read_link("/proc/self/ns/user")?,
                    std::path::Path::new("user:[4026531837]")
                );
                root()?;
                if phase == "exec" {
                    let actual = original::inspect()?;
                    assert_eq!(
                        actual,
                        Snapshot {
                            effective: original::MAINTENANCE,
                            permitted: original::MAINTENANCE,
                            inheritable: 0,
                            ambient: 0,
                            bounding: original::MAINTENANCE,
                            no_new_privs: true
                        }
                    );
                    assert_eq!(
                        set(PTRACE, original::MAINTENANCE | PTRACE)
                            .unwrap_err()
                            .raw_os_error(),
                        Some(libc::EPERM)
                    );
                    denied_pid1();
                    println!("working_return_actual_child_caps={actual:?}");
                    return Ok(());
                }
                assert_eq!(phase, "namespace");
                assert_eq!(std::process::id(), 1);
                let child = unsafe { libc::fork() };
                if child < 0 {
                    return Err(io::Error::last_os_error());
                }
                if child == 0 {
                    let result = std::panic::catch_unwind(isolated_child);
                    let code = match result {
                        Ok(Ok(())) => 0,
                        Ok(Err(error)) => {
                            eprintln!("isolated working return capability failure: {error}");
                            92
                        }
                        Err(_) => 93,
                    };
                    unsafe {
                        libc::_exit(code);
                    }
                }
                let status = wait(child)?;
                assert!(libc::WIFEXITED(status));
                assert_eq!(libc::WEXITSTATUS(status), 0);
                Ok(())
            }
            None => {
                let output = Command::new("/usr/bin/unshare")
                    .args([
                        "--user",
                        "--map-root-user",
                        "--mount",
                        "--pid",
                        "--fork",
                        "--mount-proc",
                    ])
                    .arg(std::env::current_exe()?)
                    .args(["--exact", TEST, "--ignored", "--nocapture"])
                    .env("DROIDLOOM_WORKING_RETURN_CAPS_TEST", "namespace")
                    .output()?;
                print!("{}", String::from_utf8_lossy(&output.stdout));
                eprint!("{}", String::from_utf8_lossy(&output.stderr));
                assert!(output.status.success());
                assert!(
                    String::from_utf8_lossy(&output.stdout)
                        .contains("working_return_actual_scope=8_descriptor_reads")
                );
                Ok(())
            }
        }
    }
}
