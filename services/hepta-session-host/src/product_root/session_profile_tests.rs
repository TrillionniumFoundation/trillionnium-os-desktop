//! Wire-to-original-type boundary only. No process, grant or effect is created.
use super::reservation_targets;
use serde_json::{Value, json};

fn joint() -> Value {
    json!({
        "schema_version": 1,
        "action": "desktop_targets_reserved",
        "profile": "notes_calculator_v1",
        "notes": {
            "session_instance": "1".repeat(32),
            "task_id": 1,
            "incarnation": "2".repeat(32),
        },
        "calculator": {
            "session_instance": "1".repeat(32),
            "task_id": 2,
            "incarnation": "3".repeat(32),
        },
        "nonce": "4".repeat(32),
    })
}

fn legacy() -> Value {
    let target = joint()["notes"].clone();
    let target: trill_ui_core::notes::NotesTargetIdentity = serde_json::from_value(target).unwrap();
    serde_json::to_value(
        trill_ui_core::notes_startup::NotesStartupReservation::new(target, "4".repeat(32)).unwrap(),
    )
    .unwrap()
}

fn read(
    value: &Value,
    desktop: bool,
) -> super::Result<(
    codex_hepta_memory::NotesTargetIdentity,
    Option<codex_hepta_memory::CalculatorTargetIdentity>,
)> {
    reservation_targets(&serde_json::to_vec(value).unwrap(), desktop)
}

#[test]
fn joint_reservation_preserves_two_original_destination_types() {
    let (notes, calculator) = read(&joint(), true).unwrap();
    let calculator = calculator.unwrap();
    assert_eq!(notes.task_id, 1);
    assert_eq!(calculator.task_id, 2);
    assert_eq!(notes.session_instance, calculator.session_instance);
    assert_ne!(notes.incarnation, calculator.incarnation);
    assert_ne!(notes.destination_id(), calculator.destination_id());
    assert_eq!(
        calculator.destination_id(),
        format!("trill.calculator:{}:2:{}", "1".repeat(32), "3".repeat(32)),
    );
    assert_eq!(
        serde_json::to_value(&calculator).unwrap(),
        joint()["calculator"],
    );
}

#[test]
fn profile_selection_never_reinterprets_the_other_reservation() {
    assert!(read(&joint(), false).is_err());
    assert!(read(&legacy(), true).is_err());
    let (notes, calculator) = read(&legacy(), false).unwrap();
    assert_eq!(notes.task_id, 1);
    assert!(calculator.is_none());
}

#[test]
fn joint_reservation_refuses_cross_session_or_same_app_bindings() {
    for case in 0..5 {
        let mut value = joint();
        match case {
            0 => value["calculator"]["session_instance"] = "5".repeat(32).into(),
            1 => value["calculator"]["incarnation"] = value["notes"]["incarnation"].clone(),
            2 => value["calculator"]["task_id"] = 1.into(),
            3 => value["notes"]["task_id"] = 2.into(),
            4 => value["nonce"] = "0".repeat(32).into(),
            _ => unreachable!(),
        }
        assert!(read(&value, true).is_err(), "binding case {case}");
    }
}

#[test]
fn joint_reservation_refuses_unknown_fields_profile_and_unbounded_metadata() {
    let mut value = joint();
    value["profile"] = "notes".into();
    assert!(read(&value, true).is_err());
    value = joint();
    value["notes"]["permission"] = true.into();
    assert!(read(&value, true).is_err());
    value = joint();
    value["calculator"]["permission"] = true.into();
    assert!(read(&value, true).is_err());
    value = joint();
    value["authority"] = true.into();
    assert!(read(&value, true).is_err());
    let mut bytes = serde_json::to_vec(&joint()).unwrap();
    bytes.resize(
        trill_ui_core::desktop_startup::MAX_DESKTOP_BOOTSTRAP_BYTES + 1,
        b' ',
    );
    assert!(reservation_targets(&bytes, true).is_err());
}
