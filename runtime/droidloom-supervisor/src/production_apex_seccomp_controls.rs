//! Real isolated seccomp replacement-listener counterexample and negative control.
//! These fixtures exercise getppid only; they create no mount/namespace or
//! production witness, and every filter lives in a disposable test process.
use super::*;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::time::{Duration, Instant};

struct Process {
    child: Option<std::process::Child>,
    pidfd: Option<OwnedFd>,
}
impl Drop for Process {
    fn drop(&mut self) {
        if let Some(child) = self.child.as_mut() {
            if child.try_wait().ok().flatten().is_none() {
                if let Some(pidfd) = &self.pidfd {
                    unsafe {
                        libc::syscall(
                            libc::SYS_pidfd_send_signal,
                            pidfd.as_raw_fd(),
                            libc::SIGKILL,
                            std::ptr::null::<libc::siginfo_t>(),
                            0,
                        );
                    }
                } else {
                    let _ = child.kill();
                }
            }
            let _ = child.wait();
        }
    }
}

fn probe_filter(flags: u32) -> libc::c_long {
    let filter = [
        op(0x20, 0, 0, 4),
        op(0x15, 1, 0, ARCH),
        result(KILL),
        op(0x20, 0, 0, 0),
        eq(libc::SYS_getppid, 1),
        result(NOTIFY),
        result(ALLOW),
    ];
    let program = libc::sock_fprog {
        len: filter.len() as u16,
        filter: filter.as_ptr().cast_mut(),
    };
    unsafe { libc::syscall(libc::SYS_seccomp, 1, flags, &program) }
}

fn probe_listener() -> OwnedFd {
    let raw = probe_filter(8);
    assert!(
        raw >= 0,
        "actual probe listener: {}",
        io::Error::last_os_error()
    );
    unsafe { OwnedFd::from_raw_fd(raw as i32) }
}

fn isolated() {
    let expected = unsafe { libc::syscall(libc::SYS_getppid) };
    assert!(expected > 0);
    assert_eq!(
        unsafe { libc::syscall(libc::SYS_prctl, libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) },
        0
    );
    let original = probe_listener();
    // The kernel rejects a second live listener anywhere in this filter chain.
    // Keeping the original FD is therefore part of the exclusion proof.
    assert_eq!(probe_filter(8), -1);
    assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EBUSY));
    // A later same-priority filter without NEW_LISTENER is legal, but selects
    // no listener: native getppid is not executed and the result is ENOSYS.
    assert_eq!(probe_filter(0), 0);
    assert_eq!(unsafe { libc::syscall(libc::SYS_getppid) }, -1);
    assert_eq!(
        io::Error::last_os_error().raw_os_error(),
        Some(libc::ENOSYS)
    );
    let mut old = libc::pollfd {
        fd: original.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    assert_eq!(unsafe { libc::poll(&mut old, 1, 0) }, 0);
    // Only actual closure of the sole listener removes the kernel duplicate
    // gate. A new listener can then supersede the still inherited NOTIFY
    // filters. Production never treats that closure as retained custody.
    drop(original);
    let replacement = probe_listener();
    let (tx, rx) = std::sync::mpsc::sync_channel(1);
    let worker = std::thread::spawn(move || {
        let tid = unsafe { libc::syscall(libc::SYS_gettid) };
        tx.send(tid as u32).unwrap();
        // CONTINUE below must return the actual native parent, not a synthetic
        // value supplied by either listener.
        unsafe { libc::syscall(libc::SYS_getppid) }
    });
    let tid = rx.recv_timeout(Duration::from_secs(2)).unwrap();
    let mut pending = libc::pollfd {
        fd: replacement.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    assert_eq!(unsafe { libc::poll(&mut pending, 1, 2000) }, 1);
    assert_ne!(pending.revents & libc::POLLIN, 0);
    let mut n = Notification::default();
    assert_eq!(
        unsafe { libc::ioctl(replacement.as_raw_fd(), RECV, &mut n) },
        0
    );
    assert_eq!(n.pid, tid);
    assert_eq!(n.data.nr, libc::SYS_getppid as i32);
    assert_eq!(n.data.arch, ARCH);
    assert_eq!(n.flags, 0);
    let response = Response {
        id: n.id,
        value: 0,
        error: 0,
        flags: 1,
    };
    assert_eq!(
        unsafe { libc::ioctl(replacement.as_raw_fd(), SEND, &response) },
        0
    );
    assert_eq!(worker.join().unwrap(), expected);
    drop(replacement);

    // install() obtains the sole production listener before its own filter
    // takes effect. Only later FILTER+NEW_LISTENER installations are denied.
    let raw = unsafe { install() }.unwrap();
    let listener = unsafe { OwnedFd::from_raw_fd(raw) };
    let allow = [result(ALLOW)];
    let program = libc::sock_fprog {
        len: 1,
        filter: allow.as_ptr().cast_mut(),
    };
    for flags in [8_u32, 9, 10, 0x28] {
        assert_eq!(
            unsafe { libc::syscall(libc::SYS_seccomp, 1, flags, &program) },
            -1
        );
        assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EPERM));
    }
    // Existing Android no-listener filters, PR_SET_SECCOMP and TSYNC continue
    // to execute their native kernel operations.
    assert_eq!(
        unsafe { libc::syscall(libc::SYS_seccomp, 1, 0, &program) },
        0
    );
    assert_eq!(
        unsafe { libc::syscall(libc::SYS_seccomp, 1, 1, &program) },
        0
    );
    assert_eq!(
        unsafe { libc::syscall(libc::SYS_prctl, libc::PR_SET_SECCOMP, 2, &program, 0, 0) },
        0
    );
    let action = KILL;
    assert_eq!(
        unsafe { libc::syscall(libc::SYS_seccomp, 2, 0, &action) },
        0
    );
    assert_eq!(
        unsafe { libc::syscall(libc::SYS_seccomp, 2, 8, &action) },
        -1
    );
    assert_eq!(
        io::Error::last_os_error().raw_os_error(),
        Some(libc::EINVAL)
    );
    let mut sizes = Sizes::default();
    assert_eq!(
        unsafe { libc::syscall(libc::SYS_seccomp, 3, 0, &mut sizes) },
        0
    );
    assert_eq!(
        (sizes.notification, sizes.response, sizes.data),
        (80, 24, 64)
    );
    drop(listener);
}

#[test]
fn apex_actual_later_listener_supersedes_notify_and_original_filter_prevents_replacement() {
    const CHILD: &str = "DROIDLOOM_NATIVE_LISTENER_REPLACEMENT_CONTROL";
    if std::env::var_os(CHILD).is_some() {
        isolated();
        return;
    }
    let mut process = Process {
        child: None,
        pidfd: None,
    };
    process.child=Some(std::process::Command::new(std::env::current_exe().unwrap())
        .args(["--exact",
            "production_apex_seccomp::controls::apex_actual_later_listener_supersedes_notify_and_original_filter_prevents_replacement",
            "--test-threads=1"])
        .env(CHILD,"1").stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped()).spawn().unwrap());
    let raw = unsafe {
        libc::syscall(
            libc::SYS_pidfd_open,
            process.child.as_ref().unwrap().id(),
            0,
        )
    };
    assert!(
        raw >= 0,
        "isolated listener control PIDFD: {}",
        io::Error::last_os_error()
    );
    process.pidfd = Some(unsafe { OwnedFd::from_raw_fd(raw as i32) });
    let deadline = Instant::now() + Duration::from_secs(10);
    while process
        .child
        .as_mut()
        .unwrap()
        .try_wait()
        .unwrap()
        .is_none()
    {
        assert!(
            Instant::now() < deadline,
            "isolated listener control deadline"
        );
        std::thread::sleep(Duration::from_millis(2));
    }
    let output = process.child.take().unwrap().wait_with_output().unwrap();
    assert!(
        output.status.success(),
        "isolated listener control stdout={:?}, stderr={:?}",
        output.stdout,
        output.stderr
    );
}
