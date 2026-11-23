use super::*;
use std::time::Duration;

#[test]
fn launch_capture_retains_actual_nonzero_status_and_both_streams_after_pidfd_reap() {
    // A real short private child exercises the changed capture contract. It
    // constructs no namespace/Ready witness and cannot run an Android command.
    worker::require_wait_semantics().unwrap();
    let (mut output, output_write) = pipe().unwrap();
    let (mut error, error_write) = pipe().unwrap();
    let stdout = b"Status: error\n\xff";
    let stderr = b"requested display is not ready\n";
    let mut pidfd = -1_i32;
    let arguments = CloneArgs {
        flags: libc::CLONE_PIDFD as u64,
        pidfd: (&mut pidfd as *mut i32) as u64,
        exit_signal: libc::SIGCHLD as u64,
        ..CloneArgs::default()
    };
    let mut mask = SignalMask::block().unwrap();
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &arguments, mem::size_of_val(&arguments)) };
    assert!(
        pid >= 0,
        "ordinary clone3 capture: {}",
        io::Error::last_os_error()
    );
    if pid == 0 {
        // The post-clone child uses only fixed raw syscalls before _exit.
        unsafe {
            if libc::write(
                output_write.as_raw_fd(),
                stdout.as_ptr().cast(),
                stdout.len(),
            ) != stdout.len() as isize
                || libc::write(
                    error_write.as_raw_fd(),
                    stderr.as_ptr().cast(),
                    stderr.len(),
                ) != stderr.len() as isize
            {
                libc::_exit(125);
            }
            libc::_exit(7);
        }
    }
    assert!(pidfd >= 0);
    let mut child = Child::owned(pid as u32, unsafe { OwnedFd::from_raw_fd(pidfd) });
    mask.restore().unwrap();
    drop(output_write);
    drop(error_write);
    let captured = collect(
        &mut child,
        &mut output,
        &mut error,
        Instant::now() + Duration::from_secs(2),
    )
    .unwrap();
    assert_eq!(captured.stdout, stdout);
    assert_eq!(captured.stderr, stderr);
    assert_eq!(
        captured.terminal,
        Terminal {
            code: libc::CLD_EXITED,
            status: 7
        }
    );
    assert_eq!(child.terminal, Some(captured.terminal));
    assert_eq!(exit_status(captured.terminal).unwrap().code(), Some(7));
    assert!(!exit_status(captured.terminal).unwrap().success());
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
