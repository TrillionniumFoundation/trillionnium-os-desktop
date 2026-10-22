//! Physical Linux descriptor-passing fixtures, not a production owner or
//! grant provider. The ordinary Notes application remains the sole executor.

use super::*;
use std::io::{Read, Write};
use std::sync::mpsc;
use trill_ui_core::notes_bootstrap::{NotesBootstrapAckAction, NOTES_BOOTSTRAP_SCHEMA_VERSION};

fn target() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 1,
        incarnation: "2".repeat(32),
    }
}

fn receive_offer(channel: &UnixDatagram) -> (NotesBootstrapOffer, OwnedFd) {
    channel
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let mut raw = [0u8; NOTES_BOOTSTRAP_MAX_BYTES + 1];
    let mut control = [0usize; 8];
    let mut iov = libc::iovec {
        iov_base: raw.as_mut_ptr().cast(),
        iov_len: raw.len(),
    };
    let mut message: libc::msghdr = unsafe { mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = control.as_mut_ptr().cast();
    message.msg_controllen = mem::size_of_val(&control);
    let count = unsafe { libc::recvmsg(channel.as_raw_fd(), &mut message, libc::MSG_CMSG_CLOEXEC) };
    assert!(count > 0 && count as usize <= NOTES_BOOTSTRAP_MAX_BYTES);
    assert_eq!(message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC), 0);
    let fd = unsafe {
        let header = libc::CMSG_FIRSTHDR(&message);
        assert!(!header.is_null());
        assert_eq!((*header).cmsg_level, libc::SOL_SOCKET);
        assert_eq!((*header).cmsg_type, libc::SCM_RIGHTS);
        assert_eq!(
            (*header).cmsg_len,
            libc::CMSG_LEN(mem::size_of::<RawFd>() as libc::c_uint) as usize
        );
        let fd = OwnedFd::from_raw_fd(libc::CMSG_DATA(header).cast::<RawFd>().read_unaligned());
        assert!(libc::CMSG_NXTHDR(&message, header).is_null());
        assert_ne!(
            libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) & libc::FD_CLOEXEC,
            0
        );
        fd
    };
    (
        NotesBootstrapOffer::parse_exact(&raw[..count as usize]).unwrap(),
        fd,
    )
}

fn ack(offer: &NotesBootstrapOffer, status: NotesBootstrapStatus) -> Vec<u8> {
    serde_json::to_vec(&NotesBootstrapAck {
        schema_version: NOTES_BOOTSTRAP_SCHEMA_VERSION,
        action: NotesBootstrapAckAction::NotesTargetRegistration,
        target: offer.target.clone(),
        destination_id: offer.destination_id.clone(),
        status,
    })
    .unwrap()
}

#[test]
fn one_private_datagram_transfers_the_exact_endpoint_with_cloexec() {
    let (session, parent) = UnixDatagram::pair().unwrap();
    let (endpoint, mut app) = UnixStream::pair().unwrap();
    let fixture = std::thread::spawn(move || {
        let (offer, fd) = receive_offer(&parent);
        assert_eq!(offer.target, target());
        let mut received = UnixStream::from(fd);
        require_socket_type(received.as_raw_fd(), libc::SOCK_STREAM).unwrap();
        assert!(received.local_addr().unwrap().is_unnamed());
        received.write_all(b"physical endpoint").unwrap();
        parent
            .send(&ack(&offer, NotesBootstrapStatus::Attached))
            .unwrap();
        received
    });
    NotesBootstrap::from_private_channel(session)
        .unwrap()
        .offer(target(), endpoint)
        .unwrap();
    let _retained_parent_endpoint = fixture.join().unwrap();
    let mut bytes = [0u8; 17];
    app.read_exact(&mut bytes).unwrap();
    assert_eq!(&bytes, b"physical endpoint");
}

#[test]
fn rejection_mismatch_and_invalid_ack_disable_transferred_aliases() {
    for mutation in 0..5 {
        let (session, parent) = UnixDatagram::pair().unwrap();
        let (endpoint, mut app) = UnixStream::pair().unwrap();
        let fixture = std::thread::spawn(move || {
            let (offer, received) = receive_offer(&parent);
            let raw = String::from_utf8(ack(&offer, NotesBootstrapStatus::Attached)).unwrap();
            let raw = match mutation {
                0 => String::from_utf8(ack(&offer, NotesBootstrapStatus::Rejected)).unwrap(),
                1 => raw.replace(&"2".repeat(32), &"3".repeat(32)),
                2 => raw.replacen('{', "{\"schema_version\":1,", 1),
                3 => raw.replacen('{', "{\"grant\":true,", 1),
                _ => "x".repeat(NOTES_BOOTSTRAP_MAX_BYTES + 1),
            };
            parent.send(raw.as_bytes()).unwrap();
            received
        });
        let outcome = NotesBootstrap::from_private_channel(session)
            .unwrap()
            .offer(target(), endpoint);
        assert!(outcome.is_err());
        if mutation == 0 {
            assert_eq!(outcome.unwrap_err().kind(), io::ErrorKind::PermissionDenied);
        }
        let _still_open_parent_alias = fixture.join().unwrap();
        app.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
        assert_eq!(
            app.read(&mut [0u8; 1]).unwrap(),
            0,
            "failed handoff shuts down even a retained duplicate"
        );
    }
}

#[test]
fn unexpected_ack_descriptor_is_rejected_and_closed() {
    let (session, parent) = UnixDatagram::pair().unwrap();
    let (endpoint, _app) = UnixStream::pair().unwrap();
    let (stray, mut stray_peer) = UnixStream::pair().unwrap();
    let fixture = std::thread::spawn(move || {
        let (offer, _received) = receive_offer(&parent);
        send_descriptor(
            &parent,
            &ack(&offer, NotesBootstrapStatus::Attached),
            stray.as_raw_fd(),
            Instant::now() + DEADLINE,
        )
        .unwrap();
        // Only the descriptor installed into the ACK receiver could retain
        // this socket after the fixture returns.
    });
    assert!(NotesBootstrap::from_private_channel(session)
        .unwrap()
        .offer(target(), endpoint)
        .is_err());
    fixture.join().unwrap();
    stray_peer
        .set_read_timeout(Some(Duration::from_secs(1)))
        .unwrap();
    assert_eq!(
        stray_peer.read(&mut [0; 1]).unwrap(),
        0,
        "no received fd leaks through rejected ACK"
    );
}

#[test]
fn timeout_disables_the_transferred_endpoint_without_a_second_offer() {
    let (session, parent) = UnixDatagram::pair().unwrap();
    let (endpoint, mut app) = UnixStream::pair().unwrap();
    let (give_fd, take_fd) = mpsc::sync_channel(1);
    let (release, hold) = mpsc::sync_channel(1);
    let fixture = std::thread::spawn(move || {
        let (_, received) = receive_offer(&parent);
        give_fd.send(received).unwrap();
        hold.recv_timeout(Duration::from_secs(6)).unwrap();
        parent.set_nonblocking(true).unwrap();
        assert!(
            parent.recv(&mut [0; 1]).is_err(),
            "sender never retries the offer"
        );
    });
    let start = Instant::now();
    assert!(NotesBootstrap::from_private_channel(session)
        .unwrap()
        .offer(target(), endpoint)
        .is_err());
    assert!(start.elapsed() < Duration::from_secs(5));
    let _retained_parent_alias = take_fd.recv_timeout(Duration::from_secs(1)).unwrap();
    app.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
    assert_eq!(app.read(&mut [0; 1]).unwrap(), 0);
    release.send(()).unwrap();
    fixture.join().unwrap();
}

#[test]
fn wrong_socket_type_and_noninitial_target_fail_before_offer() {
    let (stream, _peer) = UnixStream::pair().unwrap();
    let disguised = UnixDatagram::from(OwnedFd::from(stream));
    assert!(NotesBootstrap::from_private_channel(disguised).is_err());
    let (session, parent) = UnixDatagram::pair().unwrap();
    let (endpoint, _app) = UnixStream::pair().unwrap();
    let mut other = target();
    other.task_id = 2;
    assert!(NotesBootstrap::from_private_channel(session)
        .unwrap()
        .offer(other, endpoint)
        .is_err());
    parent.set_nonblocking(true).unwrap();
    assert!(parent.recv(&mut [0; 1]).is_err());
}
