//! Ordinary owned-child controls exercise the real ExecTrace methods. They
//! do not create a Ready capability, label an inode, or qualify Android MAC.
use super::*;
use std::time::Duration;

fn fixture(early_exit: bool) -> (Child, File, OwnedFd, File) {
    worker::require_wait_semantics().unwrap();
    // Distribution alternatives may make this ordinary test utility a symlink.
    // Resolve the fixture once, then hold the actual regular ELF with NOFOLLOW.
    // Production executable admission and all held inode/digest checks are unchanged.
    let fixture_path = std::fs::canonicalize("/usr/bin/true").unwrap();
    let executable = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(fixture_path)
        .unwrap();
    assert!(executable.metadata().unwrap().is_file());
    let mut pipe = [-1_i32; 2];
    assert_eq!(
        unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC) },
        0
    );
    let gate_read = unsafe { OwnedFd::from_raw_fd(pipe[0]) };
    let gate_write = unsafe { OwnedFd::from_raw_fd(pipe[1]) };
    let argv = [c"true".as_ptr(), std::ptr::null()];
    let envp = [std::ptr::null::<libc::c_char>()];
    let mut pidfd = -1_i32;
    let args = CloneArgs {
        flags: libc::CLONE_PIDFD as u64,
        pidfd: (&mut pidfd as *mut i32) as u64,
        exit_signal: libc::SIGCHLD as u64,
        ..CloneArgs::default()
    };
    let mut mask = SignalMask::block().unwrap();
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, mem::size_of_val(&args)) };
    assert!(
        pid >= 0,
        "owned ordinary query clone: {}",
        io::Error::last_os_error()
    );
    if pid == 0 {
        // Raw child: only fixed pointers and syscalls until the one held
        // executable is entered. A lost parent cannot leave this gate parked.
        unsafe {
            libc::close(gate_write.as_raw_fd());
            let mut poll = libc::pollfd {
                fd: gate_read.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            if libc::poll(&mut poll, 1, 5000) != 1
                || poll.revents & libc::POLLIN == 0
                || poll.revents & (libc::POLLERR | libc::POLLNVAL) != 0
            {
                libc::_exit(125);
            }
            let mut value = 0_u8;
            if libc::read(gate_read.as_raw_fd(), (&mut value as *mut u8).cast(), 1) != 1
                || value != 7
            {
                libc::_exit(125);
            }
            libc::close(gate_read.as_raw_fd());
            if early_exit {
                libc::_exit(7);
            }
            let empty = 0_u64;
            if libc::syscall(
                libc::SYS_rt_sigprocmask,
                libc::SIG_SETMASK,
                &empty,
                std::ptr::null_mut::<u64>(),
                mem::size_of::<u64>(),
            ) != 0
            {
                libc::_exit(125);
            }
            libc::syscall(
                libc::SYS_execveat,
                executable.as_raw_fd(),
                c"".as_ptr(),
                argv.as_ptr(),
                envp.as_ptr(),
                libc::AT_EMPTY_PATH,
            );
            libc::_exit(126);
        }
    }
    assert!(pidfd >= 0);
    let child = Child::owned(pid as u32, unsafe { OwnedFd::from_raw_fd(pidfd) });
    mask.restore().unwrap();
    drop(gate_read);
    let proc = File::open(format!("/proc/{pid}")).unwrap();
    (child, proc, gate_write, executable)
}

fn release(gate: OwnedFd) {
    let value = 7_u8;
    assert_eq!(
        unsafe { libc::write(gate.as_raw_fd(), (&value as *const u8).cast(), 1) },
        1
    );
}

fn reaped_once(child: &Child) {
    let mut info: libc::siginfo_t = unsafe { mem::zeroed() };
    assert_eq!(
        unsafe {
            libc::waitid(
                libc::P_PIDFD,
                child.pidfd.as_raw_fd() as libc::id_t,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        },
        -1
    );
    assert_eq!(
        io::Error::last_os_error().raw_os_error(),
        Some(libc::ECHILD)
    );
}

#[test]
fn application_exec_stop_actual_non_main_tracer_continues_and_reaps_original() {
    std::thread::spawn(|| {
        assert_ne!(
            unsafe { libc::getpid() },
            unsafe { libc::syscall(libc::SYS_gettid) } as i32
        );
        let (mut child, proc, gate, original) = fixture(false);
        let pid = child.pid;
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut trace = ExecTrace::seize(&mut child, &proc).unwrap();
        release(gate);
        assert_eq!(trace.actual_exec_stop(deadline).unwrap(), u64::from(pid));
        assert!(trace.actual_exec_stop(deadline).is_err());
        let raw = unsafe {
            libc::openat(
                proc.as_raw_fd(),
                c"exe".as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC,
            )
        };
        assert!(raw >= 0);
        let actual = unsafe { File::from_raw_fd(raw) };
        assert_eq!(Node::of(&actual).unwrap(), Node::of(&original).unwrap());
        assert_eq!(
            digest(&actual, Node::of(&actual).unwrap(), deadline).unwrap(),
            digest(&original, Node::of(&original).unwrap(), deadline).unwrap()
        );
        trace.continue_original(deadline).unwrap();
        drop(trace);
        assert_eq!(
            child.wait(deadline).unwrap(),
            Terminal {
                code: libc::CLD_EXITED,
                status: 0
            }
        );
        reaped_once(&child);
    })
    .join()
    .unwrap();
}

#[test]
fn application_exec_stop_actual_stopped_query_retires_via_original_pidfd() {
    std::thread::spawn(|| {
        let (mut child, proc, gate, _original) = fixture(false);
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut trace = ExecTrace::seize(&mut child, &proc).unwrap();
        release(gate);
        trace.actual_exec_stop(deadline).unwrap();
        drop(trace);
        child.retire(deadline).unwrap();
        assert_eq!(
            child.terminal,
            Some(Terminal {
                code: libc::CLD_KILLED,
                status: libc::SIGKILL
            })
        );
        reaped_once(&child);
    })
    .join()
    .unwrap();
}

#[test]
fn application_exec_stop_actual_early_exit_never_issues_exec_observation() {
    std::thread::spawn(|| {
        let (mut child, proc, gate, _original) = fixture(true);
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut trace = ExecTrace::seize(&mut child, &proc).unwrap();
        release(gate);
        assert!(trace.actual_exec_stop(deadline).is_err());
        drop(trace);
        assert_eq!(
            child.wait(deadline).unwrap(),
            Terminal {
                code: libc::CLD_EXITED,
                status: 7
            }
        );
        reaped_once(&child);
    })
    .join()
    .unwrap();
}
