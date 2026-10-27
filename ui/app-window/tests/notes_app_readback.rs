//! Same original Session recovery peer continues after its owned App exits.
//! Real receiver/helper/storage component evidence; no Root or grant is issued.
#![cfg(target_os = "linux")]

#[path = "../../session/src/notes_readback.rs"]
mod notes_readback;

use std::fs::File;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::fd::{BorrowedFd, OwnedFd};
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
use std::os::unix::net::UnixDatagram;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::Duration;
use trill_ui_core::notes::*;
use trill_ui_core::notes_store::NotesStore;

struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let mut nonce = [0_u8; 16];
        File::open("/dev/urandom")
            .unwrap()
            .read_exact(&mut nonce)
            .unwrap();
        let name = nonce
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        let root = std::env::temp_dir().join(format!("trill-original-app-readback-{name}"));
        std::fs::DirBuilder::new()
            .mode(0o700)
            .create(&root)
            .unwrap();
        Self(root)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
struct Process(Child);
impl Drop for Process {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn target() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 1,
        incarnation: "2".repeat(32),
    }
}
fn mutation() -> Vec<u8> {
    serde_json::to_vec(&NotesReplace {
        schema_version: NOTES_SCHEMA_VERSION,
        action: NotesReplaceAction::ReplaceNote,
        operation_id: "original-app-only-readback".into(),
        destination_id: target().destination_id(),
        target: target(),
        expected_revision: 0,
        text: "原 App 已退出，原身份只读回读".into(),
    })
    .unwrap()
}

fn continuation(kill: bool) {
    let root = Directory::new();
    let built_helper = PathBuf::from(env!("CARGO_BIN_EXE_trill-notes-recovery"))
        .canonicalize()
        .unwrap();
    // Cargo's executable can be hard-linked and group-writable in its cache.
    // Model the package's separate private installed inode with identical bytes;
    // do not weaken the production custody check to accept the build artifact.
    let raw_helper = std::fs::read(&built_helper).unwrap();
    let helper = root.0.join("installed-notes-recovery");
    let mut installed = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o500)
        .open(&helper)
        .unwrap();
    installed.write_all(&raw_helper).unwrap();
    installed.sync_all().unwrap();
    drop(installed);
    let helper_sha = sha256_hex(&raw_helper);
    assert_eq!(sha256_hex(&std::fs::read(&helper).unwrap()), helper_sha);
    let mut standby =
        notes_readback::Standby::prepare(&helper, &helper_sha, root.0.clone()).unwrap();
    let (original_owner, original_app_peer) = UnixDatagram::pair().unwrap();
    original_owner
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    original_owner
        .set_write_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    standby.bind(target(), &original_app_peer).unwrap();
    let mut application = Process(
        Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "app_writes_once_fixture",
                "--ignored",
                "--nocapture",
            ])
            .env("TRILL_READBACK_COMPONENT_ROOT", &root.0)
            .env_remove(notes_readback::HELPER_SHA_ENV)
            .stdin(Stdio::from(OwnedFd::from(original_app_peer)))
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap(),
    );
    standby.pin_original(&mut application.0).unwrap();
    let stdout = application.0.stdout.take().unwrap();
    let (sender, receiver) = std::sync::mpsc::sync_channel(1);
    let reader = std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            if line.is_ok_and(|line| line == "ORIGINAL_APP_STORED") {
                let _ = sender.send(());
                return;
            }
        }
    });
    let ready = receiver.recv_timeout(Duration::from_secs(10));
    if ready.is_err() {
        let _ = application.0.kill();
        let _ = application.0.wait();
    }
    reader.join().unwrap();
    ready.unwrap();
    assert!(
        standby.after_reap(&mut application.0).is_err(),
        "live App must retain its own receipt lane"
    );
    if kill {
        application.0.kill().unwrap();
    } else {
        original_owner.send(b"exit").unwrap();
    }
    let exit = application.0.wait().unwrap();
    assert_eq!(exit.success(), !kill);
    standby.after_reap(&mut application.0).unwrap();
    let payload = mutation();
    let query = serde_json::to_vec(&NotesObserve {
        schema_version: NOTES_SCHEMA_VERSION,
        action: NotesObserveAction::Observe,
        target: target(),
        operation_id: "original-app-only-readback".into(),
        payload_sha256: sha256_hex(&payload),
    })
    .unwrap();
    original_owner.send(&query).unwrap();
    let mut bytes = [0_u8; MAX_NOTES_RESPONSE_BYTES + 1];
    let length = original_owner.recv(&mut bytes).unwrap();
    let actual = NotesResponse::parse_exact(&bytes[..length]).unwrap();
    let expected = NotesDocument::new(target())
        .unwrap()
        .apply_exact(&payload)
        .unwrap();
    assert_eq!(actual, expected);
    standby.refresh().unwrap();
    assert!(
        NotesStore::recover(&root.0, &target()).is_err(),
        "same helper holds original incarnation lock"
    );
    // An effect-shaped payload on this exact original peer cannot mutate it.
    original_owner
        .set_read_timeout(Some(Duration::from_millis(100)))
        .unwrap();
    original_owner.send(&payload).unwrap();
    assert!(original_owner.recv(&mut bytes).is_err());
    original_owner
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    original_owner.send(&query).unwrap();
    let length = original_owner.recv(&mut bytes).unwrap();
    assert_eq!(
        NotesResponse::parse_exact(&bytes[..length]).unwrap(),
        expected
    );
    assert!(
        standby.after_reap(&mut application.0).is_err(),
        "one original continuation cannot rearm"
    );
    drop(standby);
    let recovered = NotesStore::recover(&root.0, &target()).unwrap();
    assert_eq!(recovered.revision(), 1);
    assert_eq!(recovered.text(), "原 App 已退出，原身份只读回读");
}

#[test]
fn normal_app_exit_keeps_original_receipt_without_a_new_effect_or_identity() {
    continuation(false);
}
#[test]
fn app_sigkill_keeps_original_receipt_without_a_new_effect_or_identity() {
    continuation(true);
}

#[test]
#[ignore = "child fixture selected explicitly by the owning process test"]
fn app_writes_once_fixture() -> io::Result<()> {
    let root = PathBuf::from(
        std::env::var_os("TRILL_READBACK_COMPONENT_ROOT")
            .ok_or_else(|| io::Error::other("component fixture root missing"))?,
    );
    let mut store = NotesStore::create(&root, target())?;
    store.apply_exact(&mutation())?;
    // SAFETY: the controlled child owns stdin's original datagram descriptor.
    let fd = unsafe { BorrowedFd::borrow_raw(0) }.try_clone_to_owned()?;
    let channel = UnixDatagram::from(fd);
    io::stdout().write_all(b"ORIGINAL_APP_STORED\n")?;
    io::stdout().flush()?;
    let mut request = [0_u8; 16];
    let length = channel.recv(&mut request)?;
    if &request[..length] != b"exit" {
        return Err(io::Error::other("unexpected fixture command"));
    }
    drop(store);
    Ok(())
}
