//! Kernel transport fixtures only; not Root, human or product qualification.
use super::*;
use std::io::Read;
use std::os::unix::net::UnixStream;

fn actual() -> libc::ucred {
    // SAFETY: read only the actual test process credentials.
    unsafe {
        libc::ucred {
            pid: libc::getpid(),
            uid: libc::getuid(),
            gid: libc::getgid(),
        }
    }
}

fn send_right(socket: &UnixDatagram, right: i32) {
    let mut byte = b'k';
    let mut vector = libc::iovec {
        iov_base: std::ptr::from_mut(&mut byte).cast(),
        iov_len: 1,
    };
    let mut control = [0usize; 8];
    let mut message: libc::msghdr = unsafe { mem::zeroed() };
    message.msg_iov = &mut vector;
    message.msg_iovlen = 1;
    message.msg_control = control.as_mut_ptr().cast();
    message.msg_controllen = unsafe { libc::CMSG_SPACE(mem::size_of::<i32>() as u32) } as usize;
    // SAFETY: all ancillary pointers refer to the exact bounded live buffers;
    // the supplied original descriptor remains held throughout the send.
    unsafe {
        let header = libc::CMSG_FIRSTHDR(&message);
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN(mem::size_of::<i32>() as u32) as usize;
        libc::CMSG_DATA(header).cast::<i32>().write_unaligned(right);
        assert_eq!(libc::sendmsg(socket.as_raw_fd(), &message, 0), 1);
    }
}

#[test]
fn metadata_peek_keeps_exact_original_packet_and_kernel_credential() {
    let (root, sender) = UnixDatagram::pair().unwrap();
    passcred(&root).unwrap();
    sender.send(b"original metadata").unwrap();
    let end = Instant::now() + Duration::from_secs(1);
    let (peek, rights) = metadata(&root, actual(), ReadMode::Peek, Rights::None, end).unwrap();
    assert!(rights.is_empty());
    let (consumed, rights) =
        metadata(&root, actual(), ReadMode::Consume, Rights::None, end).unwrap();
    assert!(rights.is_empty());
    assert_eq!(peek, consumed);
    assert_eq!(consumed, b"original metadata");
}

#[test]
fn wrong_actual_sender_and_truncated_metadata_are_rejected() {
    let (root, sender) = UnixDatagram::pair().unwrap();
    passcred(&root).unwrap();
    sender.send(b"original").unwrap();
    let mut different = actual();
    different.pid += 1;
    assert!(
        metadata(
            &root,
            different,
            ReadMode::Consume,
            Rights::None,
            Instant::now() + Duration::from_secs(1)
        )
        .is_err()
    );
    sender.send(&vec![b'x'; 16_385]).unwrap();
    assert!(
        metadata(
            &root,
            actual(),
            ReadMode::Consume,
            Rights::None,
            Instant::now() + Duration::from_secs(1)
        )
        .is_err()
    );
}

#[test]
fn rejected_unexpected_rights_are_actually_closed() {
    let (root, sender) = UnixDatagram::pair().unwrap();
    passcred(&root).unwrap();
    let (right, mut witness) = UnixStream::pair().unwrap();
    send_right(&sender, right.as_raw_fd());
    drop(right);
    assert!(
        metadata(
            &root,
            actual(),
            ReadMode::Consume,
            Rights::None,
            Instant::now() + Duration::from_secs(1)
        )
        .is_err()
    );
    witness
        .set_read_timeout(Some(Duration::from_secs(1)))
        .unwrap();
    let mut byte = [0];
    assert_eq!(
        witness.read(&mut byte).unwrap(),
        0,
        "a rejected SCM_RIGHTS duplicate must not keep the real peer alive"
    );
}

#[test]
fn metadata_wait_uses_only_the_remaining_original_episode() {
    let (root, _sender) = UnixDatagram::pair().unwrap();
    passcred(&root).unwrap();
    let end = Instant::now() + Duration::from_millis(250);
    std::thread::sleep(Duration::from_millis(200));
    assert!(metadata(&root, actual(), ReadMode::Consume, Rights::None, end).is_err());
    assert!(root.read_timeout().unwrap().unwrap() <= Duration::from_millis(60));
    assert!(remaining(end).is_err());
}
