//! Headless real-process qualification of the existing receiver and helper.
//! This fixture grants no authority and makes no original-owner terminal claim.
#![cfg(target_os = "linux")]

use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::os::fd::OwnedFd;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixDatagram;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;
use trill_ui_core::notes::*;
use trill_ui_core::notes_recovery::*;
use trill_ui_core::notes_store::NotesStore;

struct Directory(PathBuf);

impl Directory {
    fn new() -> Self {
        let mut random = [0_u8; 16];
        fs::File::open("/dev/urandom")
            .unwrap()
            .read_exact(&mut random)
            .unwrap();
        let suffix = random
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let path = std::env::temp_dir().join(format!("trill-notes-helper-{suffix}"));
        fs::create_dir(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        Self(path)
    }
}

impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

struct Process(Child);

impl Process {
    fn kill(&mut self) {
        self.0.kill().unwrap();
        assert!(!self.0.wait().unwrap().success());
    }

    fn ready(&mut self, expected: &'static str) {
        let output = self.0.stdout.take().unwrap();
        let (sender, receiver) = mpsc::sync_channel(1);
        let reader = std::thread::spawn(move || {
            for line in BufReader::new(output).lines() {
                if line.is_ok_and(|line| line == expected) {
                    let _ = sender.send(());
                    return;
                }
            }
        });
        let result = receiver.recv_timeout(Duration::from_secs(10));
        if result.is_err() {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
        reader.join().unwrap();
        result.expect("controlled child did not reach the bounded ready barrier");
    }
}

impl Drop for Process {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn target() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "a".repeat(32),
        task_id: 7,
        incarnation: "b".repeat(32),
    }
}

fn mutation() -> Vec<u8> {
    serde_json::to_vec(&NotesReplace {
        schema_version: 1,
        action: NotesReplaceAction::ReplaceNote,
        operation_id: "same-operation-across-processes".into(),
        destination_id: target().destination_id(),
        target: target(),
        expected_revision: 0,
        text: "persist once / 崩溃后独立回读".into(),
    })
    .unwrap()
}

fn helper(root: &Directory) -> (Process, UnixDatagram) {
    let (parent, child) = UnixDatagram::pair().unwrap();
    parent
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    parent
        .set_write_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    let mut process = Process(
        Command::new(env!("CARGO_BIN_EXE_trill-notes-recovery"))
            .arg("--state-dir")
            .arg(&root.0)
            .args([
                "--notes-session",
                &target().session_instance,
                "--task-id",
                "7",
                "--notes-incarnation",
                &target().incarnation,
            ])
            .stdin(Stdio::from(OwnedFd::from(child)))
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap(),
    );
    process.ready("TRILL_NOTES_RECOVERY_READY_V1");
    (process, parent)
}

fn exchange(channel: &UnixDatagram, request: &[u8]) -> Vec<u8> {
    channel.send(request).unwrap();
    let mut response = [0_u8; MAX_NOTES_RESPONSE_BYTES + 1];
    let length = channel.recv(&mut response).unwrap();
    assert!((1..=MAX_NOTES_RESPONSE_BYTES).contains(&length));
    response[..length].to_vec()
}

#[test]
fn process_crash_and_lost_retirement_ack_recover_without_replaying_the_effect() {
    let root = Directory::new();
    let mut application = Process(
        Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "persist_without_reply_fixture",
                "--nocapture",
                "--format=terse",
                "--test-threads=1",
            ])
            .env("TRILL_HELPER_PROCESS_TEST_ROOT", &root.0)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap(),
    );
    application.ready("APPLICATION_SYNCED_NO_RECEIPT_DELIVERED");
    application.kill();
    let raw = mutation();
    let query = serde_json::to_vec(&NotesObserve {
        schema_version: 1,
        action: NotesObserveAction::Observe,
        target: target(),
        operation_id: "same-operation-across-processes".into(),
        payload_sha256: sha256_hex(&raw),
    })
    .unwrap();
    let (mut recovery, channel) = helper(&root);
    let receipt_raw = exchange(&channel, &query);
    let receipt = NotesResponse::parse_exact(&receipt_raw).unwrap();
    let mut expected = NotesDocument::new(target()).unwrap();
    assert_eq!(receipt, expected.apply_exact(&raw).unwrap());
    assert!(
        NotesStore::recover(&root.0, &target()).is_err(),
        "helper retains the exclusive lock"
    );

    // This is a recovery-only descriptor: an exact old mutation cannot replay.
    channel
        .set_read_timeout(Some(Duration::from_millis(100)))
        .unwrap();
    channel.send(&raw).unwrap();
    assert!(channel
        .recv(&mut [0_u8; MAX_NOTES_RESPONSE_BYTES + 1])
        .is_err());
    channel
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    assert_eq!(exchange(&channel, &query), receipt_raw);

    let mut ack = NotesAcknowledge {
        schema_version: 1,
        action: NotesAcknowledgeAction::AcknowledgeTerminal,
        target: target(),
        operation_id: receipt.operation_id.clone(),
        payload_sha256: receipt.payload_sha256.clone(),
        receipt_sha256: "0".repeat(64),
    };
    let response: NotesRetirementResponse =
        serde_json::from_slice(&exchange(&channel, &serde_json::to_vec(&ack).unwrap())).unwrap();
    assert_eq!(response.status, NotesRetirementStatus::Unknown);
    assert_eq!(exchange(&channel, &query), receipt_raw);

    // Retire durably but discard the actual ACK, then kill that helper too.
    ack.receipt_sha256 = sha256_hex(&receipt_raw);
    let ack_raw = serde_json::to_vec(&ack).unwrap();
    // Consume and deliberately lose the helper's actual reply at the transport
    // fixture boundary. A reply is emitted only after file + directory sync.
    drop(exchange(&channel, &ack_raw));
    let checkpoint = root
        .0
        .join(format!("{}-7-{}", "a".repeat(32), "b".repeat(32)))
        .join("document.json");
    recovery.kill();
    drop(channel);
    let (_restarted, channel) = helper(&root);
    let response: NotesRetirementResponse =
        serde_json::from_slice(&exchange(&channel, &ack_raw)).unwrap();
    assert_eq!(response.status, NotesRetirementStatus::AlreadyReleased);
    assert_eq!(
        NotesResponse::parse_exact(&exchange(&channel, &query))
            .unwrap()
            .result,
        NotesResult::Unknown {
            current_revision: 1
        }
    );
    let state: serde_json::Value = serde_json::from_slice(&fs::read(&checkpoint).unwrap()).unwrap();
    assert_eq!(state["revision"], 1);
    assert_eq!(state["text"], "persist once / 崩溃后独立回读");
}

#[test]
fn persist_without_reply_fixture() {
    let Some(root) = std::env::var_os("TRILL_HELPER_PROCESS_TEST_ROOT") else {
        return;
    };
    let mut store = NotesStore::create(&PathBuf::from(root), target()).unwrap();
    store.apply_exact(&mutation()).unwrap();
    println!("APPLICATION_SYNCED_NO_RECEIPT_DELIVERED");
    std::io::stdout().flush().unwrap();
    let _ = std::io::stdin().read(&mut [0_u8; 1]);
    drop(store);
}
