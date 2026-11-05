//! Argument and generation locators confer no Root, Current or App authority.
use super::*;

#[test]
fn joint_selection_requires_both_original_app_records_or_the_explicit_latest_pair() {
    let parse = |args: &[&str]| {
        RecoverySelection::from_desktop_arguments(args.iter().map(std::ffi::OsString::from))
    };
    let (generation, latest) =
        parse(&["--previous-generation", "2", "--latest-original-desktop"]).unwrap();
    assert_eq!(generation, 2);
    assert_eq!(
        serde_json::to_value(latest.notes()).unwrap(),
        serde_json::json!({"kind":"latest_recorded_original_notes"})
    );
    assert_eq!(
        serde_json::to_value(latest.calculator().unwrap()).unwrap(),
        serde_json::json!({"kind":"latest_recorded_original_calculator"})
    );
    let (_, exact) = parse(&[
        "--previous-generation",
        "1",
        "--notes-operation-id",
        "old-notes",
        "--calculator-operation-id",
        "old-calculator",
    ])
    .unwrap();
    assert_eq!(
        serde_json::to_value(exact.notes()).unwrap(),
        serde_json::json!({"kind":"exact_operation","operation_id":"old-notes"})
    );
    for args in [
        vec!["--latest-original-desktop"],
        vec!["--previous-generation", "0", "--latest-original-desktop"],
        vec!["--previous-generation", "1", "--latest-original-notes"],
        vec![
            "--previous-generation",
            "1",
            "--notes-operation-id",
            "only-notes",
        ],
        vec![
            "--previous-generation",
            "1",
            "--notes-operation-id",
            "same",
            "--calculator-operation-id",
            "same",
        ],
        vec![
            "--previous-generation",
            "1",
            "--latest-original-desktop",
            "--operation-id",
            "old",
        ],
        vec![
            "--previous-generation",
            "1",
            "--notes-operation-id",
            "bad/id",
            "--calculator-operation-id",
            "calc",
        ],
    ] {
        assert!(parse(&args).is_err(), "accepted {args:?}");
    }
    assert!(
        RecoverySelection::LatestRecordedOriginalNotes
            .calculator()
            .is_err()
    );
}

#[test]
fn generation_locator_is_bounded_numeric_and_never_a_path_from_the_peer() {
    let admin = std::path::Path::new("/root/original/admin");
    assert_eq!(generation_directory(admin, 1).unwrap(), admin);
    assert_eq!(
        generation_directory(admin, 2).unwrap(),
        admin.join("recovery-2")
    );
    assert_eq!(
        generation_directory(admin, 3).unwrap(),
        admin.join("recovery-3")
    );
    assert!(successor_generation(0).is_err());
    assert!(successor_generation(u64::MAX).is_err());
}
