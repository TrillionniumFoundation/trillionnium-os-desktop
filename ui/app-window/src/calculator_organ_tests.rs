//! Private host transport/component tests; no original-owner qualification.
use super::*;
use std::time::Instant;
use trill_ui_core::calculator::*;

fn target() -> CalculatorTargetIdentity {
    CalculatorTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 2,
        incarnation: "2".repeat(32),
    }
}
fn request() -> Vec<u8> {
    serde_json::to_vec(&CalculatorEvaluate {
        schema_version: 1,
        action: CalculatorEvaluateAction::Evaluate,
        operation_id: "channel-fixture-1".into(),
        destination_id: target().destination_id(),
        target: target(),
        expected_revision: 0,
        left: "12".into(),
        operator: CalculatorOperator::Add,
        right: "30".into(),
    })
    .unwrap()
}
fn channel() -> (CalculatorAppChannel, UnixStream, UnixDatagram) {
    let (effect, owner) = UnixStream::pair().unwrap();
    let (recovery, observer) = UnixDatagram::pair().unwrap();
    owner
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    observer
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let channel = CalculatorAppChannel::from_channels(
        egui::Context::default(),
        target(),
        effect,
        recovery,
        None,
    )
    .unwrap();
    (channel, owner, observer)
}
fn drive<T>(channel: &mut CalculatorAppChannel, work: JoinHandle<T>) -> T {
    let deadline = Instant::now() + Duration::from_secs(4);
    while !work.is_finished() {
        assert!(Instant::now() < deadline, "bounded actual channel work");
        channel.poll();
        std::thread::sleep(Duration::from_millis(2));
    }
    work.join().ok().expect("channel thread passed")
}

#[test]
fn private_effect_and_independent_recovery_return_the_app_causal_receipt() {
    let (mut channel, mut owner, observer) = channel();
    let payload = request();
    let submitted = payload.clone();
    let operation = std::thread::spawn(move || {
        owner
            .write_all(&(submitted.len() as u32).to_be_bytes())
            .unwrap();
        owner.write_all(&submitted).unwrap();
        let mut prefix = [0_u8; 4];
        owner.read_exact(&mut prefix).unwrap();
        let size = u32::from_be_bytes(prefix) as usize;
        assert!(size > 0 && size <= MAX_CALCULATOR_RESPONSE_BYTES);
        let mut raw = vec![0_u8; size];
        owner.read_exact(&mut raw).unwrap();
        (owner, raw)
    });
    let (_owner, receipt_bytes) = drive(&mut channel, operation);
    let receipt = CalculatorResponse::parse_exact(&receipt_bytes).unwrap();
    assert_eq!(receipt.payload_sha256, sha256_hex(&payload));
    assert!(matches!(
        receipt.result,
        CalculatorResult::Applied { revision: 1, .. }
    ));
    assert_eq!(channel.state().result, "42");
    assert_eq!(channel.revision(), 1);

    let read = serde_json::to_vec(&CalculatorRead {
        schema_version: 1,
        action: CalculatorReadAction::ReadCalculator,
        target: target(),
        observation_id: "3".repeat(32),
    })
    .unwrap();
    let (observer, readback) = drive(
        &mut channel,
        std::thread::spawn(move || {
            observer.send(&read).unwrap();
            let mut raw = [0_u8; MAX_CALCULATOR_RESPONSE_BYTES + 1];
            let size = observer.recv(&mut raw).unwrap();
            (observer, raw[..size].to_vec())
        }),
    );
    let readback: CalculatorStateObservation = serde_json::from_slice(&readback).unwrap();
    assert_eq!(readback.state, *channel.state());
    assert_eq!(readback.state_sha256, channel.state().sha256());
    assert!(readback.receipt_pending);

    let observed = serde_json::to_vec(&CalculatorObserve {
        schema_version: 1,
        action: CalculatorObserveAction::Observe,
        target: target(),
        operation_id: receipt.operation_id.clone(),
        payload_sha256: receipt.payload_sha256.clone(),
    })
    .unwrap();
    let (observer, observed) = drive(
        &mut channel,
        std::thread::spawn(move || {
            observer.send(&observed).unwrap();
            let mut raw = [0_u8; MAX_CALCULATOR_RESPONSE_BYTES + 1];
            let size = observer.recv(&mut raw).unwrap();
            (observer, raw[..size].to_vec())
        }),
    );
    assert_eq!(observed, receipt_bytes);

    // This test's ACK is a component fixture. Production callers require the
    // original writer's typed durable-terminal permit before this datagram.
    let ack = serde_json::to_vec(&CalculatorAcknowledge {
        schema_version: 1,
        action: CalculatorAcknowledgeAction::Acknowledge,
        target: target(),
        operation_id: receipt.operation_id,
        payload_sha256: receipt.payload_sha256,
        receipt_sha256: sha256_hex(&receipt_bytes),
    })
    .unwrap();
    let retired = drive(
        &mut channel,
        std::thread::spawn(move || {
            observer.send(&ack).unwrap();
            let mut raw = [0_u8; MAX_CALCULATOR_RESPONSE_BYTES + 1];
            let size = observer.recv(&mut raw).unwrap();
            serde_json::from_slice::<CalculatorAcknowledged>(&raw[..size]).unwrap()
        }),
    );
    assert_eq!(retired.status, CalculatorAcknowledgementStatus::Retired);
    assert!(!channel.receipt_pending());
    assert_eq!(channel.revision(), 1);
}

#[test]
fn dropping_idle_channel_wakes_and_joins_both_private_workers() {
    let (channel, mut owner, _observer) = channel();
    let dropped = std::thread::spawn(move || drop(channel));
    let deadline = Instant::now() + Duration::from_secs(3);
    while !dropped.is_finished() {
        assert!(
            Instant::now() < deadline,
            "idle channel drop must be bounded"
        );
        std::thread::sleep(Duration::from_millis(2));
    }
    dropped.join().unwrap();
    assert_eq!(owner.read(&mut [0_u8]).unwrap(), 0);
}
