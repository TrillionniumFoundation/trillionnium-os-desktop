use super::*;
use serde_json::json;

fn reservation() -> DesktopStartupReservation {
    DesktopStartupReservation::new(
        NotesTargetIdentity {
            session_instance: "1".repeat(32),
            task_id: 1,
            incarnation: "2".repeat(32),
        },
        CalculatorTargetIdentity {
            session_instance: "1".repeat(32),
            task_id: 2,
            incarnation: "3".repeat(32),
        },
        "4".repeat(32),
    )
    .unwrap()
}

#[test]
fn reservation_requires_distinct_targets_in_one_session() {
    let original = reservation();
    assert_eq!(
        DesktopStartupReservation::parse_exact(&serde_json::to_vec(&original).unwrap()).unwrap(),
        original
    );
    for field in ["session", "task", "incarnation", "nonce", "version"] {
        let mut value = original.clone();
        match field {
            "session" => value.calculator.session_instance = "5".repeat(32),
            "task" => value.calculator.task_id = value.notes.task_id,
            "incarnation" => value.calculator.incarnation = value.notes.incarnation.clone(),
            "nonce" => value.nonce = "0".repeat(32),
            _ => value.schema_version = 2,
        }
        assert!(
            DesktopStartupReservation::parse_exact(&serde_json::to_vec(&value).unwrap()).is_err(),
            "{field}"
        );
    }
}

#[test]
fn activation_binds_both_targets_and_nonce() {
    let original = reservation();
    let activation = DesktopStartupActivation::from_reservation(&original);
    let raw = serde_json::to_vec(&activation).unwrap();
    assert!(DesktopStartupActivation::parse_exact(&raw)
        .unwrap()
        .matches(&original));
    for field in ["notes", "calculator", "nonce"] {
        let mut value = activation.clone();
        match field {
            "notes" => value.notes.incarnation = "6".repeat(32),
            "calculator" => value.calculator.incarnation = "6".repeat(32),
            _ => value.nonce = "6".repeat(32),
        }
        assert!(
            !DesktopStartupActivation::parse_exact(&serde_json::to_vec(&value).unwrap())
                .unwrap()
                .matches(&original)
        );
    }
    let mut unknown: serde_json::Value = serde_json::from_slice(&raw).unwrap();
    unknown["grant"] = json!(true);
    assert!(DesktopStartupActivation::parse_exact(&serde_json::to_vec(&unknown).unwrap()).is_err());
    assert!(
        DesktopStartupActivation::parse_exact(&serde_json::to_vec(&original).unwrap()).is_err()
    );
}

#[test]
fn calculator_offer_and_ack_do_not_alias_notes_or_other_incarnations() {
    let original = reservation();
    let offer = CalculatorBootstrapOffer::new(original.calculator).unwrap();
    let mut ack = CalculatorBootstrapAck {
        schema_version: 1,
        action: CalculatorAckAction::CalculatorTargetAck,
        target: offer.target.clone(),
        destination_id: offer.destination_id.clone(),
        status: CalculatorBootstrapStatus::Attached,
    };
    assert!(
        CalculatorBootstrapAck::parse_exact(&serde_json::to_vec(&ack).unwrap())
            .unwrap()
            .matches(&offer)
    );
    ack.target.incarnation = "7".repeat(32);
    assert!(CalculatorBootstrapAck::parse_exact(&serde_json::to_vec(&ack).unwrap()).is_err());
    ack.destination_id = ack.target.destination_id();
    assert!(
        !CalculatorBootstrapAck::parse_exact(&serde_json::to_vec(&ack).unwrap())
            .unwrap()
            .matches(&offer)
    );
    let notes = crate::notes_bootstrap::NotesBootstrapOffer::new(original.notes).unwrap();
    assert!(CalculatorBootstrapOffer::parse_exact(&serde_json::to_vec(&notes).unwrap()).is_err());
    let mut value = serde_json::to_value(&offer).unwrap();
    value["destination_id"] = json!(notes.destination_id);
    assert!(CalculatorBootstrapOffer::parse_exact(&serde_json::to_vec(&value).unwrap()).is_err());
}

#[test]
fn startup_is_bounded_and_rejects_unknown_profile() {
    assert!(DesktopStartupReservation::parse_exact(&[]).is_err());
    assert!(
        DesktopStartupReservation::parse_exact(&vec![b' '; MAX_DESKTOP_BOOTSTRAP_BYTES + 1])
            .is_err()
    );
    let mut value = serde_json::to_value(reservation()).unwrap();
    value["profile"] = json!("notes");
    assert!(DesktopStartupReservation::parse_exact(&serde_json::to_vec(&value).unwrap()).is_err());
}
