use super::*;

fn target() -> CalculatorTargetIdentity {
    CalculatorTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 2,
        incarnation: "2".repeat(32),
    }
}
fn applied() -> CalculatorDocument {
    let mut document = CalculatorDocument::new(target()).unwrap();
    let raw = serde_json::to_vec(&CalculatorEvaluate {
        schema_version: 1,
        action: CalculatorEvaluateAction::Evaluate,
        operation_id: "checkpoint-operation".into(),
        destination_id: target().destination_id(),
        target: target(),
        expected_revision: 0,
        left: "12".into(),
        operator: CalculatorOperator::Add,
        right: "30".into(),
    })
    .unwrap();
    document.apply_exact(&raw).unwrap();
    document
}
#[test]
fn checkpoint_preserves_pending_result_after_a_later_local_edit() {
    let mut document = applied();
    let pending = document.pending.clone();
    document
        .local_edit(CalculatorValueState {
            left: "draft".into(),
            ..Default::default()
        })
        .unwrap();
    let restored =
        CalculatorDocument::restore_checkpoint(&document.checkpoint().unwrap(), &target()).unwrap();
    assert_eq!(restored.revision(), 2);
    assert_eq!(restored.state().left, "draft");
    assert_eq!(restored.pending, pending);
}
#[test]
fn checkpoint_rejects_missing_evidence_wrong_domain_and_inconsistent_receipts() {
    let source =
        serde_json::from_slice::<serde_json::Value>(&applied().checkpoint().unwrap()).unwrap();
    for field in [
        "pending_receipt",
        "retired_receipt",
        "format",
        "revision",
        "state",
    ] {
        let mut changed = source.clone();
        changed.as_object_mut().unwrap().remove(field);
        assert!(CalculatorDocument::restore_checkpoint(
            &serde_json::to_vec(&changed).unwrap(),
            &target()
        )
        .is_err());
    }
    for (field, bad) in [
        ("format", serde_json::json!("trill.notes.checkpoint")),
        ("schema_version", serde_json::json!(2)),
        ("revision", serde_json::json!(0)),
        (
            "state",
            serde_json::json!({"left":"12","operator":"add","right":"30","result":"43"}),
        ),
    ] {
        let mut changed = source.clone();
        changed[field] = bad;
        assert!(CalculatorDocument::restore_checkpoint(
            &serde_json::to_vec(&changed).unwrap(),
            &target()
        )
        .is_err());
    }
    let mut other = target();
    other.incarnation = "3".repeat(32);
    assert!(
        CalculatorDocument::restore_checkpoint(&applied().checkpoint().unwrap(), &other).is_err()
    );
    let mut changed = source;
    changed["pending_receipt"]["result"]["revision"] = serde_json::json!(2);
    assert!(CalculatorDocument::restore_checkpoint(
        &serde_json::to_vec(&changed).unwrap(),
        &target()
    )
    .is_err());
}
