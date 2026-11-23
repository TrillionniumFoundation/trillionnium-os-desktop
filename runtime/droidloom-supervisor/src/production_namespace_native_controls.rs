//! Ordinary kernel controls for the real ptrace/NOTIFY ordering. These create
//! only private children and anonymous sockets. They do not construct a
//! production namespace, MAC owner, mount-epoch witness or Ready value.
use super::*;
use std::os::unix::fs::OpenOptionsExt;

#[repr(C)]
#[derive(Default)]
struct CloneArgs {
    flags: u64,
    pidfd: u64,
    child_tid: u64,
    parent_tid: u64,
    exit_signal: u64,
    stack: u64,
    stack_size: u64,
    tls: u64,
    set_tid: u64,
    set_tid_size: u64,
    cgroup: u64,
}

struct Child {
    pid: libc::pid_t,
    pidfd: Option<OwnedFd>,
    socket: File,
    _creator: OwnedFd,
    reaped: bool,
    nonce: [u8; 16],
}

impl Child {
    fn raw(&self) -> RawFd {
        self.pidfd.as_ref().unwrap().as_raw_fd()
    }

    fn trace_ready(&self) {
        self.readable();
        let (packet, peer) = receive_packet(self.socket.as_raw_fd()).unwrap();
        assert!(packet.matches(self.nonce, 1));
        assert_eq!(packet.phase, super::super::Phase::OriginalTraceReady as u32);
        assert_eq!(packet.errno, 0);
        assert_eq!(peer.pid, self.pid);
        assert_eq!(peer.uid, unsafe { libc::geteuid() });
        assert_eq!(peer.gid, unsafe { libc::getegid() });
        let proc = File::open(format!("/proc/{}", self.pid)).unwrap();
        tracer(
            &proc,
            read_identity(&proc, self.pid as u32).unwrap(),
            unsafe { libc::syscall(libc::SYS_gettid) } as i32,
        )
        .unwrap();
    }

    fn wait_stop(&self) -> i32 {
        let end = Instant::now() + Duration::from_secs(5);
        loop {
            assert!(Instant::now() < end, "actual fixture ptrace-stop deadline");
            let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
            assert_eq!(
                unsafe {
                    libc::waitid(
                        libc::P_PIDFD,
                        self.raw() as u32,
                        &mut info,
                        libc::WSTOPPED | libc::WNOHANG | libc::__WALL | libc::__WNOTHREAD,
                    )
                },
                0,
                "{}",
                io::Error::last_os_error()
            );
            let pid = unsafe { info.si_pid() };
            if pid != 0 {
                assert_eq!(pid, self.pid);
                assert_eq!(info.si_code, libc::CLD_TRAPPED);
                return unsafe { info.si_status() };
            }
            assert!(
                !pidfd_exited(self.pidfd.as_ref().unwrap()).unwrap(),
                "original fixture exited before expected stop"
            );
            std::thread::sleep(Duration::from_millis(1));
        }
    }

    fn reap(&mut self, expected: Option<(i32, i32)>) -> bool {
        if self.reaped {
            return true;
        }
        let end = Instant::now() + Duration::from_secs(5);
        loop {
            let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
            if unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    self.raw() as u32,
                    &mut info,
                    libc::WEXITED | libc::WNOHANG | libc::__WALL | libc::__WNOTHREAD,
                )
            } != 0
            {
                return false;
            }
            if unsafe { info.si_pid() } != 0 {
                if unsafe { info.si_pid() } != self.pid
                    || ![libc::CLD_EXITED, libc::CLD_KILLED, libc::CLD_DUMPED]
                        .contains(&info.si_code)
                {
                    return false;
                }
                self.reaped = true;
                if let Some(expected) = expected {
                    assert_eq!((info.si_code, unsafe { info.si_status() }), expected);
                }
                return true;
            }
            if Instant::now() >= end {
                return false;
            }
            std::thread::sleep(Duration::from_millis(1));
        }
    }

    fn signal_kill(&self) {
        let result = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.raw(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        };
        assert!(result == 0 || io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH));
    }

    fn readable(&self) {
        let end = Instant::now() + Duration::from_secs(5);
        loop {
            assert!(Instant::now() < end, "fixture socket deadline");
            let mut poll = [
                libc::pollfd {
                    fd: self.socket.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: self.raw(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let result = unsafe { libc::poll(poll.as_mut_ptr(), 2, 5) };
            assert!(result >= 0 || io::Error::last_os_error().kind() == io::ErrorKind::Interrupted);
            assert!(poll.iter().all(|p| p.revents & libc::POLLNVAL == 0));
            if poll[0].revents & libc::POLLIN != 0 {
                return;
            }
            assert_eq!(
                poll[1].revents, 0,
                "fixture exited without its actual packet"
            );
        }
    }

    fn listener(&self) -> File {
        self.readable();
        let mut token = 0_u8;
        let mut iov = libc::iovec {
            iov_base: (&mut token as *mut u8).cast(),
            iov_len: 1,
        };
        let mut ancillary = [0_usize; 8];
        let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = ancillary.as_mut_ptr().cast();
        message.msg_controllen = std::mem::size_of_val(&ancillary);
        let result = unsafe {
            libc::recvmsg(
                self.socket.as_raw_fd(),
                &mut message,
                libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
            )
        };
        assert_eq!(result, 1, "{}", io::Error::last_os_error());
        // Adopt every delivered descriptor before validating the envelope.
        let mut held = Vec::new();
        let mut credentials = None;
        let mut header = unsafe { libc::CMSG_FIRSTHDR(&message) };
        while !header.is_null() {
            let h = unsafe { &*header };
            assert_eq!(h.cmsg_level, libc::SOL_SOCKET);
            if h.cmsg_type == libc::SCM_CREDENTIALS {
                assert!(credentials.is_none());
                assert_eq!(h.cmsg_len, unsafe {
                    libc::CMSG_LEN(std::mem::size_of::<libc::ucred>() as u32)
                } as usize);
                credentials = Some(unsafe {
                    std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<libc::ucred>())
                });
                header = unsafe { libc::CMSG_NXTHDR(&message, header) };
                continue;
            }
            assert_eq!(h.cmsg_type, libc::SCM_RIGHTS);
            let base = unsafe { libc::CMSG_LEN(0) } as usize;
            assert!(h.cmsg_len >= base && (h.cmsg_len - base) % std::mem::size_of::<RawFd>() == 0);
            for n in 0..(h.cmsg_len - base) / std::mem::size_of::<RawFd>() {
                let raw = unsafe {
                    std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<RawFd>().add(n))
                };
                assert!(raw >= 0);
                held.push(unsafe { File::from_raw_fd(raw) });
            }
            header = unsafe { libc::CMSG_NXTHDR(&message, header) };
        }
        assert_eq!(message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC), 0);
        assert_eq!(token, 0x41);
        let credentials = credentials.unwrap();
        assert_eq!(credentials.pid, self.pid);
        assert_eq!(credentials.uid, unsafe { libc::geteuid() });
        assert_eq!(credentials.gid, unsafe { libc::getegid() });
        assert_eq!(held.len(), 1);
        held.pop().unwrap()
    }
}

impl Drop for Child {
    fn drop(&mut self) {
        if self.reaped {
            return;
        }
        let killed = unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.raw(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        };
        if (killed == 0 || io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH))
            && self.reap(None)
        {
            return;
        }
        if let Some(pidfd) = self.pidfd.take() {
            std::mem::forget(pidfd);
        }
        if std::thread::panicking() {
            eprintln!("original native control could not prove its exact PIDFD retirement");
        } else {
            panic!("original native control could not prove its exact PIDFD retirement");
        }
    }
}

unsafe fn child_exit(code: i32) -> ! {
    unsafe {
        libc::syscall(libc::SYS_exit_group, code);
        std::hint::unreachable_unchecked()
    }
}

unsafe fn send_listener(socket: RawFd, listener: RawFd) {
    unsafe {
        let token = 0x41_u8;
        let mut iov = libc::iovec {
            iov_base: (&token as *const u8).cast_mut().cast(),
            iov_len: 1,
        };
        let mut ancillary = [0_usize; 4];
        let mut message: libc::msghdr = std::mem::zeroed();
        message.msg_iov = &mut iov;
        message.msg_iovlen = 1;
        message.msg_control = ancillary.as_mut_ptr().cast();
        message.msg_controllen = libc::CMSG_SPACE(std::mem::size_of::<RawFd>() as u32) as usize;
        let header = libc::CMSG_FIRSTHDR(&message);
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of::<RawFd>() as u32) as usize;
        std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<RawFd>(), listener);
        if libc::syscall(
            libc::SYS_sendmsg,
            socket,
            &message,
            libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
        ) != 1
        {
            child_exit(126);
        }
    }
}

unsafe fn fixture(
    socket: RawFd,
    other: RawFd,
    creator: RawFd,
    parent: libc::pid_t,
    executable: RawFd,
    null: RawFd,
    mount_namespace: RawFd,
    exec: bool,
    nonce: [u8; 16],
) -> ! {
    unsafe {
        libc::syscall(libc::SYS_close, other);
        if libc::syscall(
            libc::SYS_prctl,
            libc::PR_SET_PDEATHSIG,
            libc::SIGKILL,
            0,
            0,
            0,
        ) != 0
            || libc::syscall(libc::SYS_getppid) != parent as libc::c_long
        {
            child_exit(126);
        }
        let mut p = libc::pollfd {
            fd: creator,
            events: libc::POLLIN,
            revents: 0,
        };
        if libc::syscall(libc::SYS_poll, &mut p, 1, 0) != 0 || p.revents != 0 {
            child_exit(126);
        }
        for fd in 0..3 {
            if (null != fd && libc::syscall(libc::SYS_dup3, null, fd, 0) != fd as libc::c_long)
                || libc::syscall(libc::SYS_fcntl, fd, libc::F_SETFD, 0) != 0
            {
                child_exit(126);
            }
        }
        if !exec {
            if libc::syscall(libc::SYS_prctl, libc::PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 {
                child_exit(126);
            }
            let listener = match wire::install() {
                Ok(fd) => fd,
                Err(_) => child_exit(126),
            };
            send_listener(socket, listener);
            libc::syscall(libc::SYS_close, listener);
        }
        // Delay before TRACEME: the parent must wait for the authenticated
        // post-syscall record, not reject a still-untraced original child.
        let pause = libc::timespec {
            tv_sec: 0,
            tv_nsec: 50_000_000,
        };
        if libc::syscall(
            libc::SYS_nanosleep,
            &pause,
            std::ptr::null_mut::<libc::timespec>(),
        ) != 0
        {
            child_exit(126);
        }
        if libc::syscall(libc::SYS_ptrace, libc::PTRACE_TRACEME, 0, 0, 0) != 0 {
            child_exit(126);
        }
        let ready = Packet::new(nonce, super::super::Phase::OriginalTraceReady, 0, 1);
        if libc::syscall(
            libc::SYS_sendto,
            socket,
            &ready,
            std::mem::size_of_val(&ready),
            libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
            std::ptr::null::<libc::sockaddr>(),
            0,
        ) != 40
        {
            child_exit(126);
        }
        let pid = libc::syscall(libc::SYS_getpid);
        let tid = libc::syscall(libc::SYS_gettid);
        if libc::syscall(libc::SYS_tgkill, pid, tid, libc::SIGSTOP) != 0 {
            child_exit(126);
        }
        if exec {
            let argv = [
                c"native-control".as_ptr(),
                c"--help".as_ptr(),
                std::ptr::null(),
            ];
            let env = [std::ptr::null::<libc::c_char>()];
            libc::syscall(
                libc::SYS_execveat,
                executable,
                c"".as_ptr(),
                argv.as_ptr(),
                env.as_ptr(),
                libc::AT_EMPTY_PATH,
            );
            child_exit(126);
        }
        let a = libc::syscall(
            libc::SYS_unshare,
            libc::CLONE_NEWNS as u64,
            0_u64,
            0_u64,
            0_u64,
            0_u64,
            0_u64,
        );
        let ae = if a == 0 { 0 } else { *libc::__errno_location() };
        let b = libc::syscall(
            libc::SYS_setns,
            mount_namespace as u64,
            libc::CLONE_NEWNS as u64,
            0_u64,
            0_u64,
            0_u64,
            0_u64,
        );
        let be = if b == 0 { 0 } else { *libc::__errno_location() };
        let observed = [ae, be];
        if libc::syscall(
            libc::SYS_sendto,
            socket,
            observed.as_ptr(),
            std::mem::size_of_val(&observed),
            libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
            std::ptr::null::<libc::sockaddr>(),
            0,
        ) != 8
        {
            child_exit(126);
        }
        child_exit(0)
    }
}

fn spawn(exec: bool, executable: &File, namespace: &File) -> Child {
    let mut sockets = [-1_i32; 2];
    assert_eq!(
        unsafe {
            libc::socketpair(
                libc::AF_UNIX,
                libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                0,
                sockets.as_mut_ptr(),
            )
        },
        0
    );
    let parent_socket = unsafe { File::from_raw_fd(sockets[0]) };
    let enabled = 1_i32;
    assert_eq!(
        unsafe {
            libc::setsockopt(
                parent_socket.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PASSCRED,
                (&enabled as *const i32).cast(),
                std::mem::size_of_val(&enabled) as _,
            )
        },
        0
    );
    let child_socket = unsafe { File::from_raw_fd(sockets[1]) };
    let null = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open("/dev/null")
        .unwrap();
    let tid = unsafe { libc::syscall(libc::SYS_gettid) };
    let creator = unsafe { libc::syscall(libc::SYS_pidfd_open, tid, PIDFD_THREAD) };
    assert!(creator >= 0, "{}", io::Error::last_os_error());
    let creator = unsafe { OwnedFd::from_raw_fd(creator as RawFd) };
    let parent = unsafe { libc::getpid() };
    let mut nonce = [0_u8; 16];
    assert_eq!(
        unsafe { libc::syscall(libc::SYS_getrandom, nonce.as_mut_ptr(), nonce.len(), 0) },
        16
    );
    let mut pidfd = -1_i32;
    let args = CloneArgs {
        flags: libc::CLONE_PIDFD as u64,
        pidfd: (&mut pidfd as *mut i32) as usize as u64,
        ..CloneArgs::default()
    };
    let pid = unsafe { libc::syscall(libc::SYS_clone3, &args, std::mem::size_of_val(&args)) };
    if pid == 0 {
        unsafe {
            fixture(
                child_socket.as_raw_fd(),
                parent_socket.as_raw_fd(),
                creator.as_raw_fd(),
                parent,
                executable.as_raw_fd(),
                null.as_raw_fd(),
                namespace.as_raw_fd(),
                exec,
                nonce,
            )
        }
    }
    assert!(pid > 0, "{}", io::Error::last_os_error());
    assert!(
        pid <= i32::MAX as libc::c_long && pidfd >= 0,
        "atomic clone PIDFD result"
    );
    let value = Child {
        pid: pid as i32,
        pidfd: Some(unsafe { OwnedFd::from_raw_fd(pidfd) }),
        socket: parent_socket,
        _creator: creator,
        reaped: false,
        nonce,
    };
    drop(child_socket);
    value
}

fn inputs() -> (File, File) {
    let executable = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
        .open(std::env::current_exe().unwrap())
        .unwrap();
    assert!(executable.metadata().unwrap().is_file());
    // This explicit proc nsfs magic link is a test input only. It cannot enter
    // a production constructor or replace the original PIDFD/namespace owner.
    let namespace = File::open("/proc/self/ns/mnt").unwrap();
    assert_eq!(filesystem_kind(&namespace).unwrap(), NSFS_MAGIC);
    (executable, namespace)
}

fn next_entry(child: &Child, number: libc::c_long) -> Entry {
    for _ in 0..1024 {
        assert_eq!(child.wait_stop(), SYSCALL_STOP);
        if let SyscallStop::Entry(entry) = syscall_info(child.pid as u32).unwrap() {
            if entry.number == number as u64 {
                return entry;
            }
        }
        control(child.pid as u32, libc::PTRACE_SYSCALL, 0).unwrap();
    }
    panic!("native fixture did not reach its actual entry");
}

fn received(child: &Child, listener: &File, entry: Entry) -> wire::Notification {
    control(child.pid as u32, libc::PTRACE_SYSCALL, 0).unwrap();
    let notification = super::super::apex_notifications::receive_native_control(
        listener,
        Instant::now() + Duration::from_secs(5),
    )
    .unwrap();
    assert_eq!(notification.pid, child.pid as u32);
    assert_eq!(notification.flags, 0);
    assert_eq!(notification.data.arch, ARCH_X86_64);
    assert_eq!(notification.data.nr as u64, entry.number);
    assert_eq!(
        notification.data.instruction_pointer,
        entry.instruction_pointer
    );
    assert_eq!(notification.data.args, entry.arguments);
    assert_eq!(
        unsafe { libc::ioctl(listener.as_raw_fd(), wire::ID_VALID, &notification.id) },
        0
    );
    notification
}

fn continue_and_exit(child: &Child, listener: &File, notification: wire::Notification) -> Exit {
    let response = wire::Response {
        id: notification.id,
        value: 0,
        error: 0,
        flags: 1,
    };
    assert_eq!(
        unsafe { libc::ioctl(listener.as_raw_fd(), wire::SEND, &response) },
        0,
        "{}",
        io::Error::last_os_error()
    );
    assert_eq!(child.wait_stop(), SYSCALL_STOP);
    let SyscallStop::Exit(exit) = syscall_info(child.pid as u32).unwrap() else {
        panic!("real original task exit-stop required");
    };
    assert_eq!(
        native_exit(child.pid as u32, notification.data.instruction_pointer).unwrap(),
        exit
    );
    assert!(native_exit(child.pid as u32, notification.data.instruction_pointer ^ 1).is_err());
    exit
}

#[test]
fn original_native_syscall_decode_rejects_abi_restart_and_fabricated_success() {
    let mut raw = [0_u8; 88];
    raw[0] = 1;
    raw[4..8].copy_from_slice(&ARCH_X86_64.to_ne_bytes());
    raw[24..32].copy_from_slice(&(libc::SYS_unshare as u64).to_ne_bytes());
    raw[32..40].copy_from_slice(&(libc::CLONE_NEWNS as u64).to_ne_bytes());
    assert!(matches!(
        decode_syscall_info(&raw, 80),
        Ok(SyscallStop::Entry(_))
    ));
    assert!(decode_syscall_info(&raw, 79).is_err());
    raw[1] = 1;
    assert!(decode_syscall_info(&raw, 80).is_err());
    raw[1] = 0;
    raw[4..8].copy_from_slice(&0x40000003_u32.to_ne_bytes());
    assert!(decode_syscall_info(&raw, 80).is_err());
    raw[4..8].copy_from_slice(&ARCH_X86_64.to_ne_bytes());
    raw[24..32].copy_from_slice(&(libc::SYS_unshare as u64 | 0x4000_0000).to_ne_bytes());
    assert!(decode_syscall_info(&raw, 80).is_err());
    for value in [-512, -513, -514, -516, -4096, 0, 1] {
        assert!((Exit { value, error: true }).namespace_errno().is_err());
    }
    for value in [-1, 1, 4095] {
        assert!(
            (Exit {
                value,
                error: false
            })
            .namespace_errno()
            .is_err()
        );
    }
    assert_eq!(
        (Exit {
            value: -libc::EPERM as i64,
            error: true
        })
        .namespace_errno()
        .unwrap(),
        libc::EPERM
    );
    assert_eq!(
        (Exit {
            value: 0,
            error: false
        })
        .namespace_errno()
        .unwrap(),
        0
    );
}

#[test]
fn original_native_actual_exec_event_exit_and_stopped_detach_use_original_pidfd() {
    let (executable, namespace) = inputs();
    let mut child = spawn(true, &executable, &namespace);
    child.trace_ready();
    assert_eq!(child.wait_stop(), libc::SIGSTOP);
    control(child.pid as u32, libc::PTRACE_SETOPTIONS, TRACE_OPTIONS).unwrap();
    control(child.pid as u32, libc::PTRACE_CONT, 0).unwrap();
    assert_eq!(child.wait_stop(), EXEC_STOP);
    control(child.pid as u32, libc::PTRACE_SYSCALL, 0).unwrap();
    assert_eq!(child.wait_stop(), SYSCALL_STOP);
    assert_eq!(
        syscall_info(child.pid as u32).unwrap(),
        SyscallStop::Exit(Exit {
            value: 0,
            error: false
        })
    );
    control(child.pid as u32, libc::PTRACE_DETACH, 0).unwrap();
    assert!(child.reap(Some((libc::CLD_EXITED, 0))));
}

#[test]
fn original_native_actual_notification_continue_observes_errno_and_pending_death() {
    // These operations must genuinely fail in this unprivileged fixture. No
    // seccomp-emulated errno is sent by this test; SEND contains CONTINUE only.
    assert_ne!(unsafe { libc::geteuid() }, 0);
    let (executable, namespace) = inputs();
    let mut child = spawn(false, &executable, &namespace);
    let listener = child.listener();
    child.trace_ready();
    assert_eq!(child.wait_stop(), libc::SIGSTOP);
    control(child.pid as u32, libc::PTRACE_SETOPTIONS, TRACE_OPTIONS).unwrap();
    control(child.pid as u32, libc::PTRACE_SYSCALL, 0).unwrap();
    let entry = next_entry(&child, libc::SYS_unshare);
    assert_eq!(entry.arguments[0], libc::CLONE_NEWNS as u64);
    let notification = received(&child, &listener, entry);
    let actual = continue_and_exit(&child, &listener, notification);
    assert_eq!(
        actual,
        Exit {
            value: -libc::EPERM as i64,
            error: true
        }
    );
    control(child.pid as u32, libc::PTRACE_SYSCALL, 0).unwrap();
    let entry = next_entry(&child, libc::SYS_setns);
    assert_eq!(
        &entry.arguments[..2],
        &[namespace.as_raw_fd() as u64, libc::CLONE_NEWNS as u64]
    );
    let held = unsafe {
        libc::syscall(
            libc::SYS_pidfd_getfd,
            child.raw(),
            entry.arguments[0] as i32,
            0,
        )
    };
    assert!(held >= 0, "{}", io::Error::last_os_error());
    let held = unsafe { File::from_raw_fd(held as RawFd) };
    assert_eq!(Node::of(&held).unwrap(), Node::of(&namespace).unwrap());
    let notification = received(&child, &listener, entry);
    let actual = continue_and_exit(&child, &listener, notification);
    assert_eq!(
        actual,
        Exit {
            value: -libc::EPERM as i64,
            error: true
        }
    );
    control(child.pid as u32, libc::PTRACE_DETACH, 0).unwrap();
    child.readable();
    let mut actual_child_errno = [0_i32; 2];
    assert_eq!(
        unsafe {
            libc::recv(
                child.socket.as_raw_fd(),
                actual_child_errno.as_mut_ptr().cast(),
                8,
                libc::MSG_DONTWAIT | libc::MSG_TRUNC,
            )
        },
        8
    );
    assert_eq!(actual_child_errno, [libc::EPERM, libc::EPERM]);
    assert!(child.reap(Some((libc::CLD_EXITED, 0))));

    let mut dying = spawn(false, &executable, &namespace);
    let listener = dying.listener();
    dying.trace_ready();
    assert_eq!(dying.wait_stop(), libc::SIGSTOP);
    control(dying.pid as u32, libc::PTRACE_SETOPTIONS, TRACE_OPTIONS).unwrap();
    control(dying.pid as u32, libc::PTRACE_SYSCALL, 0).unwrap();
    let entry = next_entry(&dying, libc::SYS_unshare);
    let notification = received(&dying, &listener, entry);
    dying.signal_kill();
    assert!(dying.reap(Some((libc::CLD_KILLED, libc::SIGKILL))));
    assert_eq!(
        unsafe { libc::ioctl(listener.as_raw_fd(), wire::ID_VALID, &notification.id) },
        -1
    );
    assert_eq!(
        io::Error::last_os_error().raw_os_error(),
        Some(libc::ENOENT)
    );
    let response = wire::Response {
        id: notification.id,
        value: 0,
        error: 0,
        flags: 1,
    };
    assert_eq!(
        unsafe { libc::ioctl(listener.as_raw_fd(), wire::SEND, &response) },
        -1
    );
    assert_eq!(
        io::Error::last_os_error().raw_os_error(),
        Some(libc::ENOENT)
    );
}

#[test]
fn original_native_actual_traced_parent_consumes_original_exit_exactly_once() {
    let (executable, namespace) = inputs();
    let mut child = spawn(true, &executable, &namespace);
    child.trace_ready();
    assert_eq!(child.wait_stop(), libc::SIGSTOP);
    // Use the same fixed original TRACEME options accepted by this helper.
    // TRACEEXEC is not TRACEEXIT; this child is killed without another exec.
    // All original parent/PIDFD wait and repeated-wait assertions stay real.
    control(child.pid as u32, libc::PTRACE_SETOPTIONS, TRACE_OPTIONS).unwrap();
    let proc = File::open(format!("/proc/{}", child.pid)).unwrap();
    let original = read_identity(&proc, child.pid as u32).unwrap();
    assert_eq!(
        successor::retirement_wait_route(original, original.pid, original, true).unwrap(),
        successor::RetirementWait::OriginalTree
    );
    assert!(successor::retirement_wait_route(original, original.pid + 1, original, true).is_err());
    assert!(successor::retirement_wait_route(original, original.pid, original, false).is_err());
    let mut foreign = original;
    foreign.pid += 1;
    assert!(successor::retirement_wait_route(foreign, foreign.pid, original, true).is_err());
    assert_eq!(
        successor::retirement_wait_route(foreign, foreign.pid, original, false).unwrap(),
        successor::RetirementWait::DescendantTraceReport
    );
    child.signal_kill();
    // There is intentionally no intermediary WEXITED wait for the OriginalTree
    // route. Only its original parent's same held PIDFD consumes the exit.
    assert!(child.reap(Some((libc::CLD_KILLED, libc::SIGKILL))));
    assert!(pidfd_exited(child.pidfd.as_ref().unwrap()).unwrap());
    let mut again: libc::siginfo_t = unsafe { std::mem::zeroed() };
    assert_eq!(
        unsafe {
            libc::waitid(
                libc::P_PIDFD,
                child.raw() as u32,
                &mut again,
                libc::WEXITED | libc::WNOHANG | libc::__WALL | libc::__WNOTHREAD,
            )
        },
        -1
    );
    assert_eq!(
        io::Error::last_os_error().raw_os_error(),
        Some(libc::ECHILD)
    );
}
