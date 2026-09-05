//! Separate process-fault target: fork/spawn cannot temporarily inherit the
//! descriptors used by parallel same-process lock lifetime regression tests.
//! Assertions and default parallelism remain intact in both test executables.
use hepta_session_core::{
    JournalOpenPolicy, ReceiptEffectClass, ReceiptJournal, ReceiptLifecycleState as State,
};
use std::fs;
use std::path::PathBuf;
#[path = "support/journal_chain_fixture.rs"]
mod fixture;
use fixture::*;

// Executed in a separate child only when the parent supplies this private test
// directory. With no environment input this is a no-op helper test, not ignored.
#[test]
fn process_writer_fixture() {
    let Some(root) = std::env::var_os("HEPTA_CHAIN_TEST_CHILD_ROOT") else {
        return;
    };
    let root = PathBuf::from(root);
    let mut writer = ReceiptJournal::open_chain(
        [
            root.join("segment-1.journal"),
            root.join("segment-2.journal"),
        ],
        ID,
        JournalOpenPolicy::STRICT,
    )
    .unwrap();
    for state in [State::Requested, State::Dispatched] {
        let mut value = event("killed-operation", state);
        value.effect_class = ReceiptEffectClass::PotentialExternalEffect;
        writer.append(value).unwrap();
    }
    fs::write(root.join("child-ready"), b"ready").unwrap();
    std::thread::sleep(std::time::Duration::from_secs(30));
}

#[test]
fn killed_writer_chain_recovery_retains_indeterminate_facts_without_replay() {
    struct ChildGuard(std::process::Child);
    impl Drop for ChildGuard {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    let root = Temp::new();
    let (first, second) = rotated(&root);
    let child = std::process::Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "process_writer_fixture", "--nocapture"])
        .env("HEPTA_CHAIN_TEST_CHILD_ROOT", &root.0)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap();
    let mut child = ChildGuard(child);
    for _ in 0..400 {
        if root.path("child-ready").exists() {
            break;
        }
        assert!(
            child.0.try_wait().unwrap().is_none(),
            "child died before durable dispatch"
        );
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
    assert!(
        root.path("child-ready").exists(),
        "bounded child readiness timed out"
    );
    child.0.kill().unwrap();
    child.0.wait().unwrap();
    assert!(matches!(
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::STRICT),
        Err(hepta_session_core::JournalError::StaleWriterLease)
    ));
    let before = fs::read(&second).unwrap();
    let mut writer =
        ReceiptJournal::open_chain([&first, &second], ID, JournalOpenPolicy::RECOVER_CRASH)
            .unwrap();
    let report = writer.inspect().unwrap();
    assert_eq!(report.unresolved.len(), 1);
    assert_eq!(
        report.unresolved[0].replay,
        hepta_session_core::ReplayDirective::NeverAutomatic
    );
    assert!(writer.append(event("prior-id", State::Requested)).is_err());
    assert!(
        writer
            .append(event("killed-operation", State::Requested))
            .is_err()
    );
    assert_eq!(fs::read(&second).unwrap(), before);
}
