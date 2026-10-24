//! Real Linux socketpair I/O against an explicit application-model fixture.
//! These tests exercise the destination boundary, not a Hepta grant, live GUI,
//! production writer, compositor, or target kernel.
#![cfg(target_os = "linux")]

use std::io::{Read, Write};
use std::net::Shutdown;
use std::os::unix::net::{UnixDatagram, UnixStream};
use trill_ui_broker::notes::{
    NotesDispatchBinding, NotesDispatchOutcome, NotesObservation, NotesTarget, NotesTargetRejection,
};
use trill_ui_core::notes::{
    sha256_hex, NotesDocument, NotesObserve, NotesReplace, NotesReplaceAction, NotesResponse,
    NotesResult, NotesTargetIdentity,
};

fn identity() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 7,
        incarnation: "2".repeat(32),
    }
}

fn payload(operation: &str, revision: u64, text: &str) -> Vec<u8> {
    // A noncanonical byte representation is intentional: the target must
    // forward these original bytes, not its parsed/serialized reconstruction.
    let request = NotesReplace {
        schema_version: 1,
        action: NotesReplaceAction::ReplaceNote,
        operation_id: operation.into(),
        destination_id: identity().destination_id(),
        target: identity(),
        expected_revision: revision,
        text: text.into(),
    };
    let pretty = serde_json::to_string_pretty(&request).unwrap();
    format!("  {pretty}\n").into_bytes()
}

fn binding(raw: &[u8]) -> NotesDispatchBinding {
    let request = NotesReplace::parse_exact(raw).unwrap();
    NotesDispatchBinding {
        operation_id: request.operation_id,
        destination_id: request.destination_id,
        target: request.target,
        payload_sha256: sha256_hex(raw),
    }
}

fn receive(stream: &mut UnixStream) -> Vec<u8> {
    let mut prefix = [0; 4];
    stream.read_exact(&mut prefix).unwrap();
    let length = u32::from_be_bytes(prefix) as usize;
    assert!((1..=8192).contains(&length));
    let mut bytes = vec![0; length];
    stream.read_exact(&mut bytes).unwrap();
    bytes
}

fn respond(stream: &mut UnixStream, response: &NotesResponse) {
    let bytes = serde_json::to_vec(response).unwrap();
    stream
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .unwrap();
    stream.write_all(&bytes).unwrap();
}

#[test]
fn real_private_channel_preserves_exact_payload_and_reads_independent_application_receipt() {
    let (parent, mut app) = UnixStream::pair().unwrap();
    let (recovery, recovery_app) = UnixDatagram::pair().unwrap();
    let target = NotesTarget::from_private_channels(parent, recovery, identity()).unwrap();
    let raw = payload("fixture-operation", 0, "Notes 中文");
    let expected = raw.clone();
    let fixture = std::thread::spawn(move || {
        let mut document = NotesDocument::new(identity()).unwrap();
        let received = receive(&mut app);
        assert_eq!(received, expected);
        let applied = document.apply_exact(&received).unwrap();
        respond(&mut app, &applied);
        assert_eq!(document.text(), "Notes 中文");
        // Observe is a separate read, not a repeat of the mutation.
        let mut buffer = [0_u8; 8192];
        let length = recovery_app.recv(&mut buffer).unwrap();
        let query = NotesObserve::parse_exact(&buffer[..length]).unwrap();
        recovery_app
            .send(&serde_json::to_vec(&document.observe(&query).unwrap()).unwrap())
            .unwrap();
        assert_eq!(document.revision(), 1);
    });
    let NotesDispatchOutcome::Applied(receipt) = target.enter_exact(&raw, &binding(&raw)) else {
        panic!("fixture application must acknowledge its actual document mutation");
    };
    assert!(matches!(
        receipt.result,
        NotesResult::Applied {
            previous_revision: 0,
            revision: 1,
            ..
        }
    ));
    assert_eq!(
        target.observe("fixture-operation", &sha256_hex(&raw)),
        NotesObservation::Applied(receipt)
    );
    fixture.join().unwrap();
    assert!(
        target.into_initial_endpoint().is_err(),
        "a contacted target cannot become a fresh bootstrap endpoint"
    );
}

#[test]
fn private_bootstrap_consumes_only_a_fresh_target_handle() {
    let (owner, mut app) = UnixStream::pair().unwrap();
    let target = NotesTarget::from_private_channel(owner, identity()).unwrap();
    let (observed, mut endpoint) = target.into_initial_endpoint().unwrap();
    assert_eq!(observed, identity());
    endpoint.write_all(b"owned endpoint").unwrap();
    let mut bytes = [0; 14];
    app.read_exact(&mut bytes).unwrap();
    assert_eq!(&bytes, b"owned endpoint");
}

#[test]
fn malformed_or_misbound_requests_write_no_destination_bytes() {
    let (parent, mut app) = UnixStream::pair().unwrap();
    let target = NotesTarget::from_private_channel(parent, identity()).unwrap();
    let raw = payload("fixture-operation", 0, "bounded");
    for mutation in 0..4 {
        let mut wrong = binding(&raw);
        match mutation {
            0 => wrong.payload_sha256 = "f".repeat(64),
            1 => wrong.operation_id = "another-operation".into(),
            2 => wrong.destination_id.push('x'),
            _ => wrong.target.incarnation = "3".repeat(32),
        }
        assert_eq!(
            target.enter_exact(&raw, &wrong),
            NotesDispatchOutcome::Rejected(NotesTargetRejection::BindingMismatch)
        );
    }
    assert_eq!(
        target.enter_exact(b"{}", &binding(&raw)),
        NotesDispatchOutcome::Rejected(NotesTargetRejection::MalformedPayload)
    );
    app.set_nonblocking(true).unwrap();
    let error = app.read(&mut [0; 1]).unwrap_err();
    assert_eq!(error.kind(), std::io::ErrorKind::WouldBlock);
}

#[test]
fn lost_ack_after_actual_mutation_is_unknown_and_channel_never_replays() {
    let (parent, mut app) = UnixStream::pair().unwrap();
    let target = NotesTarget::from_private_channel(parent, identity()).unwrap();
    let raw = payload("fixture-lost-ack", 0, "effect happened");
    let fixture = std::thread::spawn(move || {
        let mut document = NotesDocument::new(identity()).unwrap();
        document.apply_exact(&receive(&mut app)).unwrap();
        assert_eq!(document.text(), "effect happened");
        // The destination really applied, then the reply transport vanished.
        // A caller must never describe the resulting error as NotApplied.
        app.shutdown(Shutdown::Both).unwrap();
        document.revision()
    });
    assert!(matches!(
        target.enter_exact(&raw, &binding(&raw)),
        NotesDispatchOutcome::Indeterminate(_)
    ));
    assert_eq!(
        target.enter_exact(&raw, &binding(&raw)),
        NotesDispatchOutcome::Rejected(NotesTargetRejection::ChannelUnavailable)
    );
    assert_eq!(
        target.observe("fixture-lost-ack", &sha256_hex(&raw)),
        NotesObservation::Unavailable
    );
    assert_eq!(fixture.join().unwrap(), 1);
}

#[test]
fn a_reply_for_another_incarnation_cannot_claim_completion() {
    let (parent, mut app) = UnixStream::pair().unwrap();
    let target = NotesTarget::from_private_channel(parent, identity()).unwrap();
    let raw = payload("fixture-reply-conflict", 0, "hello");
    let fixture = std::thread::spawn(move || {
        let mut document = NotesDocument::new(identity()).unwrap();
        let mut response = document.apply_exact(&receive(&mut app)).unwrap();
        response.target.incarnation = "9".repeat(32);
        respond(&mut app, &response);
    });
    assert!(matches!(
        target.enter_exact(&raw, &binding(&raw)),
        NotesDispatchOutcome::Indeterminate(_)
    ));
    fixture.join().unwrap();
}

#[test]
fn application_cas_refusal_is_not_presented_as_a_transport_success() {
    let (parent, mut app) = UnixStream::pair().unwrap();
    let target = NotesTarget::from_private_channel(parent, identity()).unwrap();
    let raw = payload("fixture-conflict", 0, "must not overwrite");
    let fixture = std::thread::spawn(move || {
        let mut document = NotesDocument::new(identity()).unwrap();
        document.local_edit("existing user text".into()).unwrap();
        let reply = document.apply_exact(&receive(&mut app)).unwrap();
        respond(&mut app, &reply);
        assert_eq!(document.text(), "existing user text");
    });
    assert!(matches!(
        target.enter_exact(&raw, &binding(&raw)),
        NotesDispatchOutcome::NotApplied(_)
    ));
    fixture.join().unwrap();
}
