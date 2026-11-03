//! Physical two-target descriptor handoff; not a Core, grant or writer fixture.
use super::*;
use std::io::Write;
use std::os::fd::AsRawFd;
use trill_ui_core::desktop_startup::CalculatorAckAction;
use trill_ui_core::notes_bootstrap::{NotesBootstrapAckAction, NOTES_BOOTSTRAP_SCHEMA_VERSION};

fn notes() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 1,
        incarnation: "2".repeat(32),
    }
}
fn calculator() -> CalculatorTargetIdentity {
    CalculatorTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 2,
        incarnation: "3".repeat(32),
    }
}
fn receive(channel: &UnixDatagram) -> (Vec<u8>, UnixStream, UnixDatagram) {
    let result =
        trill_ui_core::notes_private_unix::receive_channels(channel, Duration::from_secs(3))
            .unwrap();
    for fd in [result.1.as_raw_fd(), result.2.as_raw_fd()] {
        assert_ne!(
            unsafe { libc::fcntl(fd, libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
    }
    result
}
fn notes_ack(offer: &NotesBootstrapOffer) -> Vec<u8> {
    serde_json::to_vec(&NotesBootstrapAck {
        schema_version: NOTES_BOOTSTRAP_SCHEMA_VERSION,
        action: NotesBootstrapAckAction::NotesTargetRegistration,
        target: offer.target.clone(),
        destination_id: offer.destination_id.clone(),
        status: NotesBootstrapStatus::Attached,
    })
    .unwrap()
}

#[test]
fn one_reservation_releases_separate_notes_then_calculator_endpoints() {
    let (session, owner) = UnixDatagram::pair().unwrap();
    let (notes_effect, mut notes_app) = UnixStream::pair().unwrap();
    let (notes_recovery, notes_app_recovery) = UnixDatagram::pair().unwrap();
    let (calculator_effect, mut calculator_app) = UnixStream::pair().unwrap();
    let (calculator_recovery, calculator_app_recovery) = UnixDatagram::pair().unwrap();
    let parent = std::thread::spawn(move || {
        let raw = super::super::notes_bootstrap::receive_ack(
            &owner,
            Instant::now() + Duration::from_secs(3),
        )
        .unwrap();
        let reserved = DesktopStartupReservation::parse_exact(&raw).unwrap();
        assert_eq!(reserved.notes, notes());
        assert_eq!(reserved.calculator, calculator());
        owner
            .send(
                &serde_json::to_vec(&DesktopStartupActivation::from_reservation(&reserved))
                    .unwrap(),
            )
            .unwrap();
        let (raw, mut effect, recovery) = receive(&owner);
        let offered = NotesBootstrapOffer::parse_exact(&raw).unwrap();
        assert_eq!(offered.target, reserved.notes);
        owner.send(&notes_ack(&offered)).unwrap();
        effect.write_all(b"notes").unwrap();
        recovery.send(b"notes-read").unwrap();
        let (raw, mut calc_effect, calc_recovery) = receive(&owner);
        let offered = CalculatorBootstrapOffer::parse_exact(&raw).unwrap();
        assert_eq!(offered.target, reserved.calculator);
        let ack = CalculatorBootstrapAck {
            schema_version: 1,
            action: CalculatorAckAction::CalculatorTargetAck,
            target: offered.target,
            destination_id: offered.destination_id,
            status: CalculatorBootstrapStatus::Attached,
        };
        owner.send(&serde_json::to_vec(&ack).unwrap()).unwrap();
        calc_effect.write_all(b"calc").unwrap();
        calc_recovery.send(b"calc-read").unwrap();
        (effect, recovery, calc_effect, calc_recovery)
    });
    DesktopBootstrap::from_private_channel(session)
        .unwrap()
        .offer(
            (notes(), notes_effect, notes_recovery),
            CalculatorChannels {
                target: calculator(),
                effect: calculator_effect,
                recovery: calculator_recovery,
            },
        )
        .unwrap();
    let _held = parent.join().unwrap();
    let mut bytes = [0_u8; 16];
    notes_app
        .set_read_timeout(Some(Duration::from_secs(1)))
        .unwrap();
    notes_app.read_exact(&mut bytes[..5]).unwrap();
    assert_eq!(&bytes[..5], b"notes");
    calculator_app
        .set_read_timeout(Some(Duration::from_secs(1)))
        .unwrap();
    calculator_app.read_exact(&mut bytes[..4]).unwrap();
    assert_eq!(&bytes[..4], b"calc");
    for (channel, expected) in [
        (notes_app_recovery, b"notes-read".as_slice()),
        (calculator_app_recovery, b"calc-read".as_slice()),
    ] {
        channel
            .set_read_timeout(Some(Duration::from_secs(1)))
            .unwrap();
        let length = channel.recv(&mut bytes).unwrap();
        assert_eq!(&bytes[..length], expected);
    }
}

#[test]
fn wrong_calculator_activation_transfers_no_endpoints_and_closes_both_apps() {
    let (session, owner) = UnixDatagram::pair().unwrap();
    let (notes_effect, mut notes_app) = UnixStream::pair().unwrap();
    let (notes_recovery, _notes_app_recovery) = UnixDatagram::pair().unwrap();
    let (calculator_effect, mut calculator_app) = UnixStream::pair().unwrap();
    let (calculator_recovery, _calculator_app_recovery) = UnixDatagram::pair().unwrap();
    let parent = std::thread::spawn(move || {
        let raw = super::super::notes_bootstrap::receive_ack(
            &owner,
            Instant::now() + Duration::from_secs(3),
        )
        .unwrap();
        let reserved = DesktopStartupReservation::parse_exact(&raw).unwrap();
        let mut activation = DesktopStartupActivation::from_reservation(&reserved);
        activation.calculator.incarnation = "4".repeat(32);
        owner
            .send(&serde_json::to_vec(&activation).unwrap())
            .unwrap();
        owner
            .set_read_timeout(Some(Duration::from_millis(100)))
            .unwrap();
        assert!(owner.recv(&mut [0_u8; 1025]).is_err());
    });
    assert!(DesktopBootstrap::from_private_channel(session)
        .unwrap()
        .offer(
            (notes(), notes_effect, notes_recovery),
            CalculatorChannels {
                target: calculator(),
                effect: calculator_effect,
                recovery: calculator_recovery
            }
        )
        .is_err());
    for stream in [&mut notes_app, &mut calculator_app] {
        stream
            .set_read_timeout(Some(Duration::from_secs(1)))
            .unwrap();
        assert_eq!(stream.read(&mut [0_u8]).unwrap(), 0);
    }
    parent.join().unwrap();
}

#[test]
fn rejected_second_ack_does_not_report_partial_attachment_as_success() {
    let (session, owner) = UnixDatagram::pair().unwrap();
    let (notes_effect, mut notes_app) = UnixStream::pair().unwrap();
    let (notes_recovery, _notes_app_recovery) = UnixDatagram::pair().unwrap();
    let (calculator_effect, mut calculator_app) = UnixStream::pair().unwrap();
    let (calculator_recovery, _calculator_app_recovery) = UnixDatagram::pair().unwrap();
    let parent = std::thread::spawn(move || {
        let raw = super::super::notes_bootstrap::receive_ack(
            &owner,
            Instant::now() + Duration::from_secs(3),
        )
        .unwrap();
        let reserved = DesktopStartupReservation::parse_exact(&raw).unwrap();
        owner
            .send(
                &serde_json::to_vec(&DesktopStartupActivation::from_reservation(&reserved))
                    .unwrap(),
            )
            .unwrap();
        let (raw, effect, recovery) = receive(&owner);
        owner
            .send(&notes_ack(&NotesBootstrapOffer::parse_exact(&raw).unwrap()))
            .unwrap();
        let (raw, calc_effect, calc_recovery) = receive(&owner);
        let offer = CalculatorBootstrapOffer::parse_exact(&raw).unwrap();
        let ack = CalculatorBootstrapAck {
            schema_version: 1,
            action: CalculatorAckAction::CalculatorTargetAck,
            target: offer.target,
            destination_id: offer.destination_id,
            status: CalculatorBootstrapStatus::Rejected,
        };
        owner.send(&serde_json::to_vec(&ack).unwrap()).unwrap();
        (effect, recovery, calc_effect, calc_recovery)
    });
    assert!(DesktopBootstrap::from_private_channel(session)
        .unwrap()
        .offer(
            (notes(), notes_effect, notes_recovery),
            CalculatorChannels {
                target: calculator(),
                effect: calculator_effect,
                recovery: calculator_recovery
            }
        )
        .is_err());
    let _held = parent.join().unwrap();
    for stream in [&mut notes_app, &mut calculator_app] {
        stream
            .set_read_timeout(Some(Duration::from_secs(1)))
            .unwrap();
        assert_eq!(stream.read(&mut [0_u8]).unwrap(), 0);
    }
}
