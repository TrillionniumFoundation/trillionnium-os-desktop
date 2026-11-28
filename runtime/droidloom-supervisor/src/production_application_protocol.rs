//! Bounded authenticated seqpacket messages. Ancillary descriptors are always
//! adopted and closed on a malformed message, including truncated controls.
use super::*;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::time::Instant;

// The largest fixed request is Contacts' 17 inputs plus its owned cgroup leaf.
pub(super) const INPUT_FDS: usize = 18;
pub(super) const CONTENT_JAR: usize = 15;
pub(super) const ORIGINAL_CONTENT_JAR: usize = 16;
pub(super) const EXECUTABLE: usize = 10;
pub(super) const ORIGINAL_EXECUTABLE: usize = 11;
pub(super) const STDOUT: usize = 12;
pub(super) const STDERR: usize = 13;
pub(super) const GATE: usize = 14;
const MESSAGE_LIMIT: usize = 32768;

/// Wire fields are comparisons only. A real creator receipt is constructed
/// solely after an authenticated original factory stop with actual wait zero.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct FactoryHelperRetirement {
    pub(super) pid: u32,
    pub(super) waitid_code: i32,
    pub(super) waitid_status: i32,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(tag = "phase", deny_unknown_fields)]
pub(super) enum Message {
    FactoryRequest {
        nonce: [u8; 16],
        query: ApplicationOperation,
        deadline_ns: u64,
    },
    FactoryRejected {
        nonce: [u8; 16],
        message: String,
    },
    FactoryBorn {
        nonce: [u8; 16],
        pid: u32,
        pidfd_device: u64,
        pidfd_inode: u64,
    },
    FactoryBound {
        nonce: [u8; 16],
    },
    FactoryExecStopped {
        nonce: [u8; 16],
        pid: u32,
        pidfd_device: u64,
        pidfd_inode: u64,
        tracer_tid: u32,
        waitid_code: i32,
        waitid_status: i32,
        event_previous_tid: u64,
    },
    FactoryCalendarExecStopped {
        nonce: [u8; 16],
        pid: u32,
        pidfd_device: u64,
        pidfd_inode: u64,
        tracer_tid: u32,
        waitid_code: i32,
        waitid_status: i32,
        event_previous_tid: u64,
        stdio_creator: FactoryHelperRetirement,
        metadata_creator: FactoryHelperRetirement,
        metadata: super::metadata_observer::CalendarMetadataFields,
    },
    FactoryCalendarOutput {
        nonce: [u8; 16],
        stdout_hex: String,
        stderr_hex: String,
    },
    FactoryRelease {
        nonce: [u8; 16],
    },
    FactoryReleased {
        nonce: [u8; 16],
    },
    FactoryCancel {
        nonce: [u8; 16],
    },
    FactoryTerminated {
        nonce: [u8; 16],
        pid: u32,
        pidfd_device: u64,
        pidfd_inode: u64,
        waitid_code: i32,
        waitid_status: i32,
        released: bool,
        input_sources_verified: bool,
    },
    MetadataRequest {
        nonce: [u8; 16],
        role: super::metadata_observer::MetadataRole,
        deadline_ns: u64,
    },
    MetadataObserved {
        nonce: [u8; 16],
        role: super::metadata_observer::MetadataRole,
        selinux: String,
        apparmor: String,
        stat: String,
        status: String,
        host: super::metadata_observer::HostProcessMetadata,
    },
    MetadataRejected {
        nonce: [u8; 16],
        reason: String,
    },
    EngineRequest {
        nonce: [u8; 16],
        request: super::engine_observer::EngineTarget,
        deadline_ns: u64,
    },
    EngineObserved {
        nonce: [u8; 16],
        sample: super::engine_observer::EngineSample,
    },
    EngineNotTarget {
        nonce: [u8; 16],
    },
    EngineRejected {
        nonce: [u8; 16],
        reason: String,
    },
    Request {
        nonce: [u8; 16],
        query: ApplicationOperation,
        projection: QueryProjection,
        deadline_ns: u64,
    },
    BridgeRequest {
        nonce: [u8; 16],
        projection: QueryProjection,
        deadline_ns: u64,
    },
    BridgeConnected {
        nonce: [u8; 16],
    },
    BridgeRejected {
        nonce: [u8; 16],
        message: String,
    },
    Spawned {
        nonce: [u8; 16],
    },
    RejectedBeforeClone {
        nonce: [u8; 16],
        message: String,
    },
    Go {
        nonce: [u8; 16],
    },
    Armed {
        nonce: [u8; 16],
    },
}

pub(super) struct Received {
    pub(super) message: Message,
    pub(super) files: Vec<OwnedFd>,
    pub(super) peer: libc::ucred,
}

pub(super) fn socketpair() -> Result<(OwnedFd, OwnedFd)> {
    let mut fds = [-1; 2];
    if unsafe {
        libc::socketpair(
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
            fds.as_mut_ptr(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    let first = unsafe { OwnedFd::from_raw_fd(fds[0]) };
    let second = unsafe { OwnedFd::from_raw_fd(fds[1]) };
    for fd in [&first, &second] {
        let enabled = 1_i32;
        if unsafe {
            libc::setsockopt(
                fd.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PASSCRED,
                (&enabled as *const i32).cast(),
                mem::size_of_val(&enabled) as libc::socklen_t,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
    }
    Ok((first, second))
}

pub(super) fn encoded(message: &Message) -> Result<Vec<u8>> {
    let bytes = serde_json::to_vec(message).map_err(external)?;
    require(
        !bytes.is_empty() && bytes.len() <= MESSAGE_LIMIT,
        "application message size",
    )?;
    Ok(bytes)
}

pub(super) fn send(
    socket: RawFd,
    message: &Message,
    fds: &[RawFd],
    deadline: Instant,
) -> Result<()> {
    require(fds.len() <= INPUT_FDS, "too many application descriptors")?;
    let bytes = encoded(message)?;
    loop {
        crate::production_host_admission::check_observation_before(deadline)?;
        let mut iov = libc::iovec {
            iov_base: bytes.as_ptr().cast_mut().cast(),
            iov_len: bytes.len(),
        };
        let mut control = [0_usize; 64];
        let mut header: libc::msghdr = unsafe { mem::zeroed() };
        header.msg_iov = &mut iov;
        header.msg_iovlen = 1;
        if !fds.is_empty() {
            header.msg_control = control.as_mut_ptr().cast();
            header.msg_controllen =
                unsafe { libc::CMSG_SPACE(mem::size_of_val(fds) as u32) } as usize;
            let cmsg = unsafe { libc::CMSG_FIRSTHDR(&header) };
            require(!cmsg.is_null(), "application rights header absent")?;
            unsafe {
                (*cmsg).cmsg_level = libc::SOL_SOCKET;
                (*cmsg).cmsg_type = libc::SCM_RIGHTS;
                (*cmsg).cmsg_len = libc::CMSG_LEN(mem::size_of_val(fds) as u32) as usize;
                std::ptr::copy_nonoverlapping(
                    fds.as_ptr().cast::<u8>(),
                    libc::CMSG_DATA(cmsg),
                    mem::size_of_val(fds),
                );
            }
        }
        let count =
            unsafe { libc::sendmsg(socket, &header, libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT) };
        if count >= 0 {
            return require(
                count as usize == bytes.len(),
                "partial application seqpacket send",
            );
        }
        let error = io::Error::last_os_error();
        if error.kind() == io::ErrorKind::Interrupted {
            continue;
        }
        if error.kind() != io::ErrorKind::WouldBlock {
            return Err(error.into());
        }
        wait(socket, libc::POLLOUT, deadline)?;
    }
}

pub(super) fn receive(socket: RawFd, deadline: Instant) -> Result<Received> {
    loop {
        crate::production_host_admission::check_observation_before(deadline)?;
        let mut bytes = [0_u8; MESSAGE_LIMIT];
        let mut iov = libc::iovec {
            iov_base: bytes.as_mut_ptr().cast(),
            iov_len: bytes.len(),
        };
        let mut control = [0_usize; 128];
        let mut header: libc::msghdr = unsafe { mem::zeroed() };
        header.msg_iov = &mut iov;
        header.msg_iovlen = 1;
        header.msg_control = control.as_mut_ptr().cast();
        header.msg_controllen = mem::size_of_val(&control);
        let count = unsafe {
            libc::recvmsg(
                socket,
                &mut header,
                libc::MSG_CMSG_CLOEXEC | libc::MSG_DONTWAIT,
            )
        };
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            if error.kind() != io::ErrorKind::WouldBlock {
                return Err(error.into());
            }
            wait(socket, libc::POLLIN, deadline)?;
            continue;
        }
        let mut files = Vec::new();
        let mut peer = None;
        let mut malformed = false;
        let mut cmsg = unsafe { libc::CMSG_FIRSTHDR(&header) };
        while !cmsg.is_null() {
            let fixed = unsafe { libc::CMSG_LEN(0) } as usize;
            let size = unsafe { (*cmsg).cmsg_len };
            if size < fixed {
                malformed = true;
                break;
            }
            let size = size - fixed;
            let level = unsafe { (*cmsg).cmsg_level };
            let kind = unsafe { (*cmsg).cmsg_type };
            if level == libc::SOL_SOCKET && kind == libc::SCM_RIGHTS {
                if size % mem::size_of::<i32>() != 0 {
                    malformed = true;
                }
                for offset in
                    (0..size / mem::size_of::<i32>()).map(|index| index * mem::size_of::<i32>())
                {
                    let raw = unsafe {
                        std::ptr::read_unaligned(libc::CMSG_DATA(cmsg).add(offset).cast::<i32>())
                    };
                    if raw < 0 {
                        malformed = true;
                    } else {
                        files.push(unsafe { OwnedFd::from_raw_fd(raw) });
                    }
                }
            } else if level == libc::SOL_SOCKET
                && kind == libc::SCM_CREDENTIALS
                && size == mem::size_of::<libc::ucred>()
            {
                let value = unsafe {
                    std::ptr::read_unaligned(libc::CMSG_DATA(cmsg).cast::<libc::ucred>())
                };
                if peer.replace(value).is_some() {
                    malformed = true;
                }
            } else {
                malformed = true;
            }
            cmsg = unsafe { libc::CMSG_NXTHDR(&header, cmsg) };
        }
        require(
            count > 0
                && header.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) == 0
                && !malformed
                && files.len() <= INPUT_FDS,
            "application message truncated or malformed",
        )?;
        let message = serde_json::from_slice(&bytes[..count as usize]).map_err(external)?;
        let peer = peer.ok_or_else(|| reject("application sender credentials absent"))?;
        return Ok(Received {
            message,
            files,
            peer,
        });
    }
}

fn wait(fd: RawFd, events: i16, deadline: Instant) -> Result<()> {
    loop {
        let left = deadline.saturating_duration_since(Instant::now());
        crate::production_host_admission::check_observation_before(deadline)?;
        let mut poll = libc::pollfd {
            fd,
            events,
            revents: 0,
        };
        let count = unsafe { libc::poll(&mut poll, 1, left.as_millis().max(1).min(20) as i32) };
        if count < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error.into());
        }
        require(
            poll.revents & libc::POLLNVAL == 0,
            "application protocol descriptor invalid",
        )?;
        if count > 0 {
            return Ok(());
        }
    }
}

pub(super) fn monotonic_ns() -> Result<u64> {
    let mut value = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let seconds = u64::try_from(value.tv_sec).map_err(|_| reject("negative monotonic clock"))?;
    seconds
        .checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(value.tv_nsec as u64))
        .ok_or_else(|| reject("monotonic clock overflow"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::fd::AsFd;
    #[test]
    fn production_application_protocol_transfers_actual_fd_and_kernel_credentials() {
        let (left, right) = socketpair().unwrap();
        let source = File::open("/dev/null").unwrap();
        let nonce = [7; 16];
        let deadline = Instant::now() + std::time::Duration::from_secs(1);
        send(
            left.as_raw_fd(),
            &Message::Spawned { nonce },
            &[source.as_raw_fd()],
            deadline,
        )
        .unwrap();
        let received = receive(right.as_raw_fd(), deadline).unwrap();
        assert!(
            matches!(received.message, Message::Spawned { nonce: actual } if actual == [7; 16])
        );
        assert_eq!(received.peer.pid, unsafe { libc::getpid() });
        assert_eq!(received.files.len(), 1);
        let copy = File::from(received.files.into_iter().next().unwrap());
        assert_eq!(
            copy.metadata().unwrap().rdev(),
            source.metadata().unwrap().rdev()
        );
        assert_ne!(
            unsafe { libc::fcntl(copy.as_fd().as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
    }
    #[test]
    fn factory_contacts_request_transfers_all_inputs_and_rejects_excess_rights() {
        let (left, right) = socketpair().unwrap();
        let source = tempfile::tempfile().unwrap();
        let nonce = [13; 16];
        let deadline = Instant::now() + std::time::Duration::from_secs(1);
        let message = Message::FactoryRequest {
            nonce,
            query: super::super::operation::ApplicationOperation::ContactsRead {
                value: super::super::contacts::ContactsQuery::RawRows,
            },
            deadline_ns: monotonic_ns().unwrap() + 1_000_000_000,
        };
        // Both Contacts JAR descriptions and the final fixed budget description
        // must survive SCM_RIGHTS, with credentials and close-on-exec intact.
        let raw = vec![source.as_raw_fd(); 18];
        send(left.as_raw_fd(), &message, &raw, deadline).unwrap();
        let received = receive(right.as_raw_fd(), deadline).unwrap();
        assert_eq!(received.peer.pid, unsafe { libc::getpid() });
        assert_eq!(received.files.len(), 18);
        assert!(matches!(
            received.message,
            Message::FactoryRequest { nonce: actual, query:
                super::super::operation::ApplicationOperation::ContactsRead { .. }, .. }
                if actual == nonce
        ));
        let expected = source.metadata().unwrap();
        for descriptor in received.files {
            let file = File::from(descriptor);
            let actual = file.metadata().unwrap();
            assert_eq!(
                (actual.dev(), actual.ino()),
                (expected.dev(), expected.ino())
            );
            assert_ne!(
                unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
                0
            );
        }
        assert!(
            send(
                left.as_raw_fd(),
                &message,
                &vec![source.as_raw_fd(); 19],
                deadline
            )
            .is_err()
        );
        let mut pending = libc::pollfd {
            fd: right.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(unsafe { libc::poll(&mut pending, 1, 0) }, 0);
    }

    #[test]
    fn production_application_protocol_uses_one_absolute_deadline() {
        let (_left, right) = socketpair().unwrap();
        let began = Instant::now();
        assert!(
            receive(
                right.as_raw_fd(),
                began + std::time::Duration::from_millis(10)
            )
            .is_err()
        );
        assert!(began.elapsed() < std::time::Duration::from_secs(1));
    }
    #[test]
    fn factory_terminal_requires_explicit_source_evidence_without_rewriting_waitid() {
        let value = serde_json::json!({
            "phase": "FactoryTerminated",
            "nonce": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            "pid": 123,
            "pidfd_device": 4,
            "pidfd_inode": 5,
            "waitid_code": libc::CLD_EXITED,
            "waitid_status": 0,
            "released": true,
            "input_sources_verified": false
        });
        let decoded: Message = serde_json::from_value(value.clone()).unwrap();
        assert!(matches!(
            decoded,
            Message::FactoryTerminated {
                waitid_code: libc::CLD_EXITED,
                waitid_status: 0,
                released: true,
                input_sources_verified: false,
                ..
            }
        ));
        let mut missing = value.clone();
        missing
            .as_object_mut()
            .unwrap()
            .remove("input_sources_verified");
        assert!(serde_json::from_value::<Message>(missing).is_err());
        let mut invalid = value;
        invalid["input_sources_verified"] = serde_json::Value::Null;
        assert!(serde_json::from_value::<Message>(invalid).is_err());
    }

    #[test]
    fn calendar_factory_output_uses_actual_authenticated_socket_without_kernel_pipe_rights() {
        let (left, right) = socketpair().unwrap();
        let deadline = Instant::now() + std::time::Duration::from_secs(1);
        send(
            left.as_raw_fd(),
            &Message::FactoryCalendarOutput {
                nonce: [21; 16],
                stdout_hex: "00ff0a".into(),
                stderr_hex: String::new(),
            },
            &[],
            deadline,
        )
        .unwrap();
        let received = receive(right.as_raw_fd(), deadline).unwrap();
        assert_eq!(received.peer.pid, unsafe { libc::getpid() });
        assert!(received.files.is_empty());
        assert!(matches!(received.message, Message::FactoryCalendarOutput {
            nonce: [21,21,21,21,21,21,21,21,21,21,21,21,21,21,21,21], stdout_hex, stderr_hex
        } if stdout_hex == "00ff0a" && stderr_hex.is_empty()));
    }
}
