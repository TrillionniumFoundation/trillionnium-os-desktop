use super::*;
use crate::notes_bootstrap::{NotesBootstrapAck, NotesBootstrapOffer};
use crate::notes_startup::{NotesStartupActivation, NotesStartupReservation};

fn fixture() -> serde_json::Value {
    serde_json::from_str(include_str!("../../../tests/ui/notes-model-v1.json")).unwrap()
}

#[test]
fn canonical_model_round_trip_preserves_distinct_protocol_domains() {
    let contract = fixture();
    let target: NotesTargetIdentity = serde_json::from_value(contract["target"].clone()).unwrap();
    assert_eq!(target.destination_id(), contract["destination_id"]);
    assert_eq!(target.scope_sha256(), contract["scope_sha256"]);
    assert_eq!(target.predecessor_sha256(0), contract["predecessor_sha256"]);
    let request = contract["wire"]["request_utf8"].as_str().unwrap();
    let expected = NotesResponse::parse_exact(
        contract["wire"]["response_utf8"]
            .as_str()
            .unwrap()
            .as_bytes(),
    )
    .unwrap();
    let mut document = NotesDocument::new(target.clone()).unwrap();
    assert_eq!(document.apply_exact(request.as_bytes()).unwrap(), expected);
    assert_eq!(
        document.checkpoint().unwrap(),
        contract["checkpoint"]["current_utf8"]
            .as_str()
            .unwrap()
            .as_bytes()
    );
    let mut legacy = NotesDocument::restore_checkpoint(
        contract["checkpoint"]["legacy_utf8"]
            .as_str()
            .unwrap()
            .as_bytes(),
        &target,
    )
    .unwrap();
    let observe = serde_json::to_vec(&NotesObserve {
        schema_version: 1,
        action: NotesObserveAction::Observe,
        target: target.clone(),
        operation_id: expected.operation_id.clone(),
        payload_sha256: expected.payload_sha256.clone(),
    })
    .unwrap();
    assert_eq!(
        NotesResponse::parse_exact(&legacy.recovery_exact(&observe).unwrap()).unwrap(),
        expected
    );
    assert_eq!(legacy.checkpoint().unwrap(), document.checkpoint().unwrap());
    let offer = NotesBootstrapOffer::parse_exact(
        contract["bootstrap"]["offer_utf8"]
            .as_str()
            .unwrap()
            .as_bytes(),
    )
    .unwrap();
    assert_eq!(offer.target, target);
    let ack = NotesBootstrapAck::parse_exact(
        contract["bootstrap"]["ack_utf8"]
            .as_str()
            .unwrap()
            .as_bytes(),
    )
    .unwrap();
    assert!(ack.matches(&offer));
    let reservation = NotesStartupReservation::parse_exact(
        contract["startup"]["reservation_utf8"]
            .as_str()
            .unwrap()
            .as_bytes(),
    )
    .unwrap();
    let activation = NotesStartupActivation::parse_exact(
        contract["startup"]["activation_utf8"]
            .as_str()
            .unwrap()
            .as_bytes(),
    )
    .unwrap();
    assert!(activation.matches(&reservation));
    assert_eq!(reservation.target, target);
}

#[test]
fn checkpoint_rejects_unknown_mixed_duplicate_or_missing_fields() {
    let contract = fixture();
    let target: NotesTargetIdentity = serde_json::from_value(contract["target"].clone()).unwrap();
    let raw = contract["checkpoint"]["current_utf8"].as_str().unwrap();
    let current: serde_json::Value = serde_json::from_str(raw).unwrap();
    for (field, value) in [
        ("format", serde_json::json!("another.document")),
        ("schema_version", serde_json::json!(1)),
        ("schema_version", serde_json::json!(3)),
        ("unexpected", serde_json::json!(true)),
    ] {
        let mut changed = current.clone();
        changed[field] = value;
        assert!(
            NotesDocument::restore_checkpoint(&serde_json::to_vec(&changed).unwrap(), &target)
                .is_err()
        );
    }
    for field in ["format", "pending_receipt", "retired_receipt"] {
        let mut changed = current.clone();
        changed.as_object_mut().unwrap().remove(field);
        assert!(
            NotesDocument::restore_checkpoint(&serde_json::to_vec(&changed).unwrap(), &target)
                .is_err()
        );
    }
    for changed in [
        raw.replacen('{', "{\"schema_version\":2,", 1),
        raw.replacen('{', "{\"format\":\"trill.notes.checkpoint\",", 1),
    ] {
        assert!(NotesDocument::restore_checkpoint(changed.as_bytes(), &target).is_err());
    }
    let legacy = contract["checkpoint"]["legacy_utf8"].as_str().unwrap();
    let mut missing: serde_json::Value = serde_json::from_str(legacy).unwrap();
    missing.as_object_mut().unwrap().remove("pending_receipt");
    assert!(
        NotesDocument::restore_checkpoint(&serde_json::to_vec(&missing).unwrap(), &target).is_err()
    );
    let mut other = target.clone();
    other.incarnation = "4".repeat(32);
    assert!(NotesDocument::restore_checkpoint(raw.as_bytes(), &other).is_err());
    assert!(NotesDocument::restore_checkpoint(legacy.as_bytes(), &other).is_err());
}
