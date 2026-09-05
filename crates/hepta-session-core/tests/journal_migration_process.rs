//! Independent SIGKILL matrix: exact source, private cfg(test) cutpoints only.
//! This does not remove kernel page cache, simulate a device, or prove power loss.
#![allow(dead_code, unused_imports)]
#[path = "../src/receipt_journal.rs"]
mod receipt_journal;
use receipt_journal::persistence_tests::{Action, Armed, ID, Temp, event};
use receipt_journal::*;
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::os::unix::fs::DirBuilderExt;
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

const CASES: &[&str] = &[
    "migration.before_directory_create",
    "migration.after_directory_create",
    "migration_marker.before_write",
    "migration_marker.partial_write",
    "migration.after_marker_sync",
    "migration_segment_0.before_write",
    "migration_segment_0.partial_write",
    "migration_segment_0.before_sync",
    "migration_segment_0.after_sync",
    "migration_segment_1.before_write",
    "migration_segment_1.partial_write",
    "migration_segment_1.before_sync",
    "migration_segment_1.after_sync",
    "migration.before_publish",
    "migration.after_publish",
    "migration.after_directory_sync",
];

fn sources(parent: &Path) -> [PathBuf; 2] {
    [parent.join("legacy/first"), parent.join("legacy/second")]
}
fn prepare(parent: &Path) {
    fs::DirBuilder::new()
        .mode(0o700)
        .create(parent.join("legacy"))
        .unwrap();
    let paths = sources(parent);
    let mut writer = ReceiptJournal::create(&paths[0], ID, 1).unwrap();
    for state in [LifecycleState::Requested, LifecycleState::Interrupted] {
        writer.append(event("prior", state)).unwrap();
    }
    let (_, mut writer) = writer.rotate(&paths[1], 2).unwrap();
    for state in [LifecycleState::Requested, LifecycleState::Dispatched] {
        let mut item = event("pending", state);
        item.effect_class = EffectClass::PotentialExternalEffect;
        writer.append(item).unwrap();
    }
}
fn snapshot(parent: &Path) -> BTreeMap<String, Vec<u8>> {
    fs::read_dir(parent)
        .unwrap()
        .map(|item| {
            let item = item.unwrap();
            (
                item.file_name().into_string().unwrap(),
                fs::read(item.path()).unwrap(),
            )
        })
        .collect()
}
struct KillOnDrop(Child);
impl Drop for KillOnDrop {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("--migration-child") {
        assert_eq!(args.len(), 3);
        let parent = PathBuf::from(&args[1]);
        assert!(
            parent
                .file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("hepta-persistence-cuts-")
        );
        assert!(CASES.contains(&args[2].as_str()));
        let _armed = Armed::new(&args[2], Action::Pause(parent.join("checkpoint")));
        let _ = ReceiptJournal::copy_legacy_chain_to_managed(
            sources(&parent),
            ID,
            parent.join("store"),
        );
        panic!("migration checkpoint not reached");
    }
    if args == ["--list"] {
        for case in CASES {
            println!("{case}: process-cut");
        }
        return;
    }
    assert!(
        args.iter()
            .all(|a| a == "--nocapture" || a.starts_with("--test-threads=")),
        "no silent filtering"
    );
    assert_eq!(CASES.len(), 16);
    for target in CASES {
        let temp = Temp::new();
        prepare(&temp.0);
        let original = snapshot(&temp.0.join("legacy"));
        let output = File::create(temp.0.join("child.log")).unwrap();
        let mut child = KillOnDrop(
            Command::new(std::env::current_exe().unwrap())
                .arg("--migration-child")
                .arg(&temp.0)
                .arg(target)
                .stdout(Stdio::from(output.try_clone().unwrap()))
                .stderr(Stdio::from(output))
                .spawn()
                .unwrap(),
        );
        let until = Instant::now() + Duration::from_secs(10);
        loop {
            if fs::read_to_string(temp.0.join("checkpoint"))
                .ok()
                .as_deref()
                == Some(target)
            {
                break;
            }
            assert!(
                child.0.try_wait().unwrap().is_none(),
                "premature child exit at {target}: {}",
                fs::read_to_string(temp.0.join("child.log")).unwrap()
            );
            assert!(Instant::now() < until, "checkpoint timeout {target}");
            std::thread::sleep(Duration::from_millis(3));
        }
        child.0.kill().unwrap();
        assert_eq!(child.0.wait().unwrap().signal(), Some(9));
        assert_eq!(
            snapshot(&temp.0.join("legacy")),
            original,
            "source changed at {target}"
        );
        let published = matches!(
            *target,
            "migration.after_publish" | "migration.after_directory_sync"
        );
        let result =
            ReceiptJournal::open_managed(temp.store(), ID, ManagedOpenPolicy::RECOVER_CRASH);
        assert_eq!(
            result.is_ok(),
            published,
            "wrong destination state at {target}"
        );
        if let Ok(mut writer) = result {
            let report = writer.inspect().unwrap();
            assert_eq!(report.unresolved.len(), 1);
            assert_eq!(report.unresolved[0].replay, ReplayDirective::NeverAutomatic);
            for (index, path) in sources(&temp.0).iter().enumerate() {
                assert_eq!(
                    fs::read(path).unwrap(),
                    fs::read(
                        temp.store()
                            .join(format!("segment-{:016}.journal", index + 1))
                    )
                    .unwrap()
                );
            }
            assert!(
                writer
                    .append(event("prior", LifecycleState::Requested))
                    .is_err()
            );
        }
        if temp.store().exists() {
            let before = snapshot(&temp.store());
            assert!(
                ReceiptJournal::copy_legacy_chain_to_managed(sources(&temp.0), ID, temp.store())
                    .is_err()
            );
            assert_eq!(snapshot(&temp.store()), before);
        }
        println!("migration-process-cut point={target} signal=9 preserved=PASS");
    }
    println!("migration-process-matrix: 16 passed; 0 failed; no physical-powerloss claim");
}
