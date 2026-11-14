//! The inspection CLI is read-only and never substitutes for root activation.
use std::{fs, process::Command};

#[test]
fn inspection_cli_is_available_and_reports_missing_inputs_without_root() {
    let directory = tempfile::tempdir().unwrap();
    let spec_path = directory.path().join("cell.json");
    let mut spec: serde_json::Value =
        serde_json::from_str(include_str!("../../../docs/examples/cell-spec-u1000.json")).unwrap();
    spec["image_dir"] = serde_json::json!(directory.path().join("missing-base"));
    spec["gapps_dir"] = serde_json::Value::Null;
    fs::write(&spec_path, serde_json::to_vec(&spec).unwrap()).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_droidloom-supervisor"))
        .arg("development-inspect")
        .arg("--spec")
        .arg(&spec_path)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    let error = String::from_utf8(output.stderr).unwrap();
    assert!(error.contains("missing-base/images/system.img"), "{error}");
    assert!(!error.contains("must be run as root"), "{error}");
    assert!(!directory.path().join("runtime").exists());
}
