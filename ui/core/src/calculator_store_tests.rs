use super::*;
use crate::calculator::*;
use std::fs::{self, DirBuilder};
use std::os::unix::fs::{symlink, DirBuilderExt, PermissionsExt};
use std::process::Command;

struct Directory(std::path::PathBuf);
impl Directory {
    fn new() -> Self {
        let mut nonce = [0_u8; 16];
        File::open("/dev/urandom")
            .unwrap()
            .read_exact(&mut nonce)
            .unwrap();
        let path = std::env::temp_dir().join(format!(
            "trill-calculator-store-{}",
            nonce.iter().map(|b| format!("{b:02x}")).collect::<String>()
        ));
        DirBuilder::new().mode(0o700).create(&path).unwrap();
        Self(path)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn target() -> CalculatorTargetIdentity {
    CalculatorTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 2,
        incarnation: "2".repeat(32),
    }
}
fn payload() -> Vec<u8> {
    serde_json::to_vec(&CalculatorEvaluate {
        schema_version: 1,
        action: CalculatorEvaluateAction::Evaluate,
        operation_id: "durable-operation".into(),
        destination_id: target().destination_id(),
        target: target(),
        expected_revision: 0,
        left: "12".into(),
        operator: CalculatorOperator::Add,
        right: "30".into(),
    })
    .unwrap()
}
fn observation() -> Vec<u8> {
    serde_json::to_vec(&CalculatorObserve {
        schema_version: 1,
        action: CalculatorObserveAction::Observe,
        target: target(),
        operation_id: "durable-operation".into(),
        payload_sha256: sha256_hex(&payload()),
    })
    .unwrap()
}
fn acknowledge(receipt: &[u8]) -> Vec<u8> {
    serde_json::to_vec(&CalculatorAcknowledge {
        schema_version: 1,
        action: CalculatorAcknowledgeAction::Acknowledge,
        target: target(),
        operation_id: "durable-operation".into(),
        payload_sha256: sha256_hex(&payload()),
        receipt_sha256: sha256_hex(receipt),
    })
    .unwrap()
}

#[test]
fn crash_writer_fixture() {
    let Some(path) = std::env::var_os("TRILL_CALCULATOR_STORE_CRASH_FIXTURE") else {
        return;
    };
    let mut app = CalculatorStore::create(Path::new(&path), target()).unwrap();
    let receipt = app.apply_exact(&payload()).unwrap();
    assert!(matches!(
        receipt.result,
        CalculatorResult::Applied { revision: 1, .. }
    ));
    // Deliberately bypass Drop after the real file/directory fsync returned.
    std::process::exit(0);
}

#[test]
fn process_exit_keeps_original_receipt_and_exact_retirement_without_replay() {
    let root = Directory::new();
    let status = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "calculator_store::tests::crash_writer_fixture",
            "--nocapture",
        ])
        .env("TRILL_CALCULATOR_STORE_CRASH_FIXTURE", &root.0)
        .status()
        .unwrap();
    assert!(status.success());
    assert!(CalculatorStore::create(&root.0, target()).is_err());
    let mut recovered = CalculatorStore::recover(&root.0, &target()).unwrap();
    assert_eq!(recovered.state().result, "42");
    assert_eq!(recovered.revision(), 1);
    let receipt = recovered.recovery_exact(&observation()).unwrap();
    let parsed = CalculatorResponse::parse_exact(&receipt).unwrap();
    assert!(matches!(
        parsed.result,
        CalculatorResult::Applied { revision: 1, .. }
    ));
    assert!(CalculatorStore::recover(&root.0, &target()).is_err());
    assert!(recovered.recovery_exact(&payload()).is_err());
    assert_eq!(
        recovered.apply_exact(&payload()).unwrap_err().kind(),
        io::ErrorKind::PermissionDenied
    );
    assert!(recovered
        .local_edit(CalculatorValueState::default())
        .is_err());
    let ack = acknowledge(&receipt);
    let first: CalculatorAcknowledged =
        serde_json::from_slice(&recovered.recovery_exact(&ack).unwrap()).unwrap();
    assert_eq!(first.status, CalculatorAcknowledgementStatus::Retired);
    drop(recovered); // model an ACK lost after durable retirement.
    let mut reopened = CalculatorStore::recover(&root.0, &target()).unwrap();
    let repeated: CalculatorAcknowledged =
        serde_json::from_slice(&reopened.recovery_exact(&ack).unwrap()).unwrap();
    assert_eq!(
        repeated.status,
        CalculatorAcknowledgementStatus::AlreadyRetired
    );
    assert!(!reopened.receipt_pending());
    let observation =
        CalculatorResponse::parse_exact(&reopened.recovery_exact(&observation()).unwrap()).unwrap();
    assert!(matches!(
        observation.result,
        CalculatorResult::Unknown {
            current_revision: 1
        }
    ));
    assert_eq!(reopened.state().result, "42");
}

#[test]
fn live_owner_lock_exact_target_and_failed_sync_freeze_are_preserved() {
    let root = Directory::new();
    let mut app = CalculatorStore::create(&root.0, target()).unwrap();
    assert!(CalculatorStore::recover(&root.0, &target()).is_err());
    let directory = root.0.join(name(&target()));
    symlink("/dev/null", directory.join("next.json")).unwrap();
    assert!(app.apply_exact(&payload()).is_err());
    assert!(app.is_frozen());
    assert!(app.recovery_exact(&observation()).is_err());
    assert_eq!(app.revision(), 0);
    drop(app);
    fs::remove_file(directory.join("next.json")).unwrap();
    let recovered = CalculatorStore::recover(&root.0, &target()).unwrap();
    assert_eq!(recovered.revision(), 0);
    assert!(!recovered.receipt_pending());
    drop(recovered);
    let mut other = target();
    other.incarnation = "3".repeat(32);
    assert!(CalculatorStore::recover(&root.0, &other).is_err());
    let file = directory.join("document.json");
    fs::set_permissions(&file, fs::Permissions::from_mode(0o644)).unwrap();
    assert!(CalculatorStore::recover(&root.0, &target()).is_err());
    fs::set_permissions(&file, fs::Permissions::from_mode(0o600)).unwrap();
    let duplicate = root.0.join("another-link");
    fs::hard_link(&file, &duplicate).unwrap();
    assert!(CalculatorStore::recover(&root.0, &target()).is_err());
}

#[test]
fn data_store_does_not_rebind_notes_or_corrupt_calculator_checkpoint() {
    let root = Directory::new();
    drop(CalculatorStore::create(&root.0, target()).unwrap());
    let file = root.0.join(name(&target())).join("document.json");
    let original = fs::read(&file).unwrap();
    let mut document: serde_json::Value = serde_json::from_slice(&original).unwrap();
    document["format"] = "trill.notes.checkpoint".into();
    fs::write(&file, serde_json::to_vec(&document).unwrap()).unwrap();
    assert!(CalculatorStore::recover(&root.0, &target()).is_err());
    fs::write(&file, &original[..original.len() / 2]).unwrap();
    assert!(CalculatorStore::recover(&root.0, &target()).is_err());
}
