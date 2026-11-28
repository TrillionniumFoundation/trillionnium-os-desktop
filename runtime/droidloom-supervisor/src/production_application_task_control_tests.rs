use super::*;
use std::os::fd::{AsRawFd, FromRawFd};

fn pair(pass_pidfd: bool) -> (File, File) {
    let (read, write) = protocol::socketpair().unwrap();
    let read = File::from(read);
    let enabled = i32::from(pass_pidfd);
    assert_eq!(
        unsafe {
            libc::setsockopt(
                read.as_raw_fd(),
                libc::SOL_SOCKET,
                SO_PASSPIDFD,
                (&enabled as *const i32).cast(),
                mem::size_of::<i32>() as libc::socklen_t,
            )
        },
        0
    );
    (read, File::from(write))
}

fn send(socket: &File, body: &[u8], right: Option<&File>) {
    let mut iov = libc::iovec {
        iov_base: body.as_ptr().cast_mut().cast(),
        iov_len: body.len(),
    };
    let mut header: libc::msghdr = unsafe { mem::zeroed() };
    let mut control = [0_usize; 8];
    header.msg_iov = &mut iov;
    header.msg_iovlen = 1;
    if let Some(right) = right {
        header.msg_control = control.as_mut_ptr().cast();
        header.msg_controllen = unsafe { libc::CMSG_SPACE(mem::size_of::<i32>() as u32) } as usize;
        let cmsg = unsafe { libc::CMSG_FIRSTHDR(&header) };
        unsafe {
            (*cmsg).cmsg_level = libc::SOL_SOCKET;
            (*cmsg).cmsg_type = libc::SCM_RIGHTS;
            (*cmsg).cmsg_len = libc::CMSG_LEN(mem::size_of::<i32>() as u32) as usize;
            std::ptr::write_unaligned(libc::CMSG_DATA(cmsg).cast::<i32>(), right.as_raw_fd());
        }
    }
    assert_eq!(
        unsafe {
            libc::sendmsg(
                socket.as_raw_fd(),
                &header,
                libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL,
            )
        },
        body.len() as isize
    );
}

fn pipe() -> (File, File) {
    let mut files = [-1_i32; 2];
    assert_eq!(
        unsafe { libc::pipe2(files.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) },
        0
    );
    unsafe { (File::from_raw_fd(files[0]), File::from_raw_fd(files[1])) }
}

#[test]
fn task_control_actual_records_require_kernel_credentials_and_message_pidfd() {
    let body = droidloom_task_control::encode_response(&ControlResponse::ServerHello {
        major: PROTOCOL_MAJOR,
        minor: 0,
    })
    .unwrap();
    let (reader, writer) = pair(true);
    send(&writer, &body, None);
    let value = receive_record(&reader).unwrap().unwrap();
    assert_eq!(value.body, body);
    assert_eq!(value.credentials.pid, unsafe { libc::getpid() });
    assert_eq!(value.credentials.uid, unsafe { libc::getuid() });
    let mut p = libc::pollfd {
        fd: value.pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    assert_eq!(unsafe { libc::poll(&mut p, 1, 0) }, 0);
    let info =
        std::fs::read_to_string(format!("/proc/self/fdinfo/{}", value.pidfd.as_raw_fd())).unwrap();
    assert!(
        info.lines()
            .any(|row| row == format!("Pid:\t{}", unsafe { libc::getpid() }))
    );
    let (reader, writer) = pair(false);
    send(&writer, &body, None);
    assert!(receive_record(&reader).is_err());
    // This observes real IPC; it constructs no Ready or same-tree authority.
}

#[test]
fn task_control_forbidden_rights_and_truncated_records_close_every_delivered_fd() {
    for body in [vec![1_u8; 8], vec![2_u8; MAX_RECORD_BYTES + 1]] {
        let (reader, writer) = pair(true);
        let (pipe_read, pipe_write) = pipe();
        send(&writer, &body, Some(&pipe_write));
        drop(pipe_write);
        assert!(receive_record(&reader).is_err());
        let mut byte = 0_u8;
        // A leaked received write FD makes this nonblocking read EAGAIN.
        // EOF proves cleanup without racing a process-global FD count.
        assert_eq!(
            unsafe { libc::read(pipe_read.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) },
            0
        );
    }
}

#[test]
fn task_control_session_refuses_replay_foreign_package_and_mismatched_binding() {
    let hello = ControlRequest::Hello {
        min_major: PROTOCOL_MAJOR,
        max_major: PROTOCOL_MAJOR,
    };
    let bound = ControlRequest::RegisterDirect {
        request_id: 1,
        package: "org.example.app".into(),
        task: 17,
        android_display: 0,
    };
    assert_eq!(
        requested_phase(Phase::Hello, &hello, "org.example.app").unwrap(),
        Phase::Register
    );
    assert_eq!(
        requested_phase(Phase::Register, &bound, "org.example.app").unwrap(),
        Phase::Bound
    );
    for (phase, request, package) in [
        (Phase::Hello, &bound, "org.example.app"),
        (Phase::Register, &hello, "org.example.app"),
        (Phase::Bound, &bound, "org.example.app"),
        (Phase::Failed, &hello, "org.example.app"),
        (Phase::Register, &bound, "org.other.app"),
    ] {
        assert!(requested_phase(phase, request, package).is_err());
    }
    let valid = ControlResponse::Bound {
        request_id: 1,
        object: 2,
        task: 17,
        display: 3,
        android_display: 0,
    };
    assert!(matching_response(&bound, &valid));
    for wrong in [
        ControlResponse::Bound {
            request_id: 2,
            object: 2,
            task: 17,
            display: 3,
            android_display: 0,
        },
        ControlResponse::Bound {
            request_id: 1,
            object: 2,
            task: 18,
            display: 3,
            android_display: 0,
        },
        ControlResponse::Bound {
            request_id: 1,
            object: 2,
            task: 17,
            display: 3,
            android_display: 1,
        },
        ControlResponse::Bound {
            request_id: 1,
            object: 0,
            task: 17,
            display: 3,
            android_display: 0,
        },
        ControlResponse::ServerHello {
            major: PROTOCOL_MAJOR,
            minor: 0,
        },
    ] {
        assert!(!matching_response(&bound, &wrong));
    }
}
