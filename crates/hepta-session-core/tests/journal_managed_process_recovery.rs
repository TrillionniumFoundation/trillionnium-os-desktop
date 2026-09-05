//! Process termination target is separate from in-process lock lifetime tests.
use hepta_session_core::{
    ManagedOpenPolicy as Policy, ReceiptEffectClass, ReceiptJournal,
    ReceiptLifecycleState as State, ReplayDirective,
};
use std::fs;
use std::os::unix::process::ExitStatusExt;
use std::path::PathBuf;
#[allow(dead_code)]
#[path = "support/journal_chain_fixture.rs"]
mod fixture;
use fixture::*;

#[test]
fn managed_process_child() {
    let Some(parent) = std::env::var_os("HEPTA_MANAGED_TEST_ROOT") else {
        return;
    };
    let parent = PathBuf::from(parent);
    let root = parent.join("store");
    let mode = std::env::var("HEPTA_MANAGED_TEST_MODE").unwrap();
    let mut writer = ReceiptJournal::create_managed(&root, ID, 1).unwrap();
    for state in [State::Requested, State::Interrupted] {
        writer.append(event("prior", state)).unwrap();
    }
    let (_, mut writer) = writer.rotate_managed(2).unwrap();
    if mode == "dispatched" {
        for state in [State::Requested, State::Dispatched] {
            let mut value = event("uncertain", state);
            value.effect_class = ReceiptEffectClass::PotentialExternalEffect;
            writer.append(value).unwrap();
        }
    }
    fs::write(parent.join("ready"), b"synced").unwrap();
    std::thread::sleep(std::time::Duration::from_secs(30));
    drop(writer);
}
fn killed_store(mode: &str) -> Temp {
    struct ChildGuard(std::process::Child);
    impl Drop for ChildGuard {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    let temp = Temp::new();
    let mut child = ChildGuard(
        std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "managed_process_child", "--nocapture"])
            .env("HEPTA_MANAGED_TEST_ROOT", &temp.0)
            .env("HEPTA_MANAGED_TEST_MODE", mode)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .unwrap(),
    );
    for _ in 0..400 {
        if temp.path("ready").exists() {
            break;
        }
        assert!(
            child.0.try_wait().unwrap().is_none(),
            "writer exited before durable checkpoint"
        );
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
    assert!(temp.path("ready").exists(), "bounded readiness timeout");
    child.0.kill().unwrap();
    assert_eq!(child.0.wait().unwrap().signal(), Some(9));
    temp
}
#[test]
fn managed_sigkill_after_acknowledged_rotation_selects_committed_successor() {
    let temp = killed_store("rotated");
    let root = temp.path("store");
    let mut writer = ReceiptJournal::open_managed(&root, ID, Policy::STRICT).unwrap();
    assert_eq!(
        writer.path().file_name().unwrap(),
        "segment-0000000000000002.journal"
    );
    assert!(writer.append(event("prior", State::Requested)).is_err());
    assert_eq!(
        writer
            .append(event("fresh", State::Requested))
            .unwrap()
            .sequence,
        3
    );
}
#[test]
fn managed_sigkill_preserves_dispatched_external_facts_and_never_replays() {
    let temp = killed_store("dispatched");
    let root = temp.path("store");
    let path = root.join("segment-0000000000000002.journal");
    let before = fs::read(&path).unwrap();
    let mut writer = ReceiptJournal::open_managed(&root, ID, Policy::RECOVER_CRASH).unwrap();
    let report = writer.inspect().unwrap();
    assert_eq!(report.unresolved.len(), 1);
    assert_eq!(report.unresolved[0].receipt_id, "uncertain");
    assert_eq!(report.unresolved[0].replay, ReplayDirective::NeverAutomatic);
    assert!(writer.append(event("prior", State::Requested)).is_err());
    assert!(writer.append(event("uncertain", State::Requested)).is_err());
    assert_eq!(fs::read(&path).unwrap(), before);
}
