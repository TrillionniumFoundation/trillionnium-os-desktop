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
    let (raw, effect, recovery) =
        trill_ui_core::notes_private_unix::receive_channels(channel, Duration::from_secs(3))
            .unwrap();
    for fd in [effect.as_raw_fd(), recovery.as_raw_fd()] {
        assert_ne!(
            unsafe { libc::fcntl(fd, libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
    }
    (
        NotesBootstrapOffer::parse_exact(&raw).unwrap(),
        OwnedFd::from(effect),
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
    let (recovery, _recovery_app) = UnixDatagram::pair().unwrap();
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
        .offer(target(), endpoint, recovery)
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
        let (recovery, _recovery_app) = UnixDatagram::pair().unwrap();
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
            .offer(target(), endpoint, recovery);
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
    let (recovery, _recovery_app) = UnixDatagram::pair().unwrap();
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
        .offer(target(), endpoint, recovery)
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
    let (recovery, _recovery_app) = UnixDatagram::pair().unwrap();
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
        .offer(target(), endpoint, recovery)
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
    let (recovery, _recovery_app) = UnixDatagram::pair().unwrap();
    let mut other = target();
    other.task_id = 2;
    assert!(NotesBootstrap::from_private_channel(session)
        .unwrap()
        .offer(other, endpoint, recovery)
        .is_err());
    parent.set_nonblocking(true).unwrap();
    assert!(parent.recv(&mut [0; 1]).is_err());
}
