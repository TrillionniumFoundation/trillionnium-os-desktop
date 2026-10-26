#![cfg(target_os = "linux")]

//! Process fixtures are isolated from the parallel, in-process NotesStore suite.
//! Even CLOEXEC descriptors survive fork until exec. Serializing these process
//! scenarios prevents an unrelated fixture from temporarily inheriting a live
//! test's flock open-file description. Production lock acquisition stays fail-fast.

use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::net::UnixStream;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::time::Duration;
use trill_ui_core::notes::*;
use trill_ui_core::notes_store::NotesStore;

#[path = "common/notes_store.rs"]
mod common;
use common::*;

static PROCESS_SCENARIO: Mutex<()> = Mutex::new(());

#[test]
fn fork_inherits_the_lock_until_exec_even_after_the_parent_store_is_dropped() {
    let _serial = PROCESS_SCENARIO.lock().unwrap();
    let root = Directory::new();
    let mut app = NotesStore::create(&root.0, target()).unwrap();
    let receipt = app.apply_exact(&request()).unwrap();
    let (mut ready_parent, ready_child) = UnixStream::pair().unwrap();
    let (mut release_parent, release_child) = UnixStream::pair().unwrap();
    ready_parent
        .set_read_timeout(Some(Duration::from_secs(10)))
        .unwrap();
    release_child
        .set_read_timeout(Some(Duration::from_secs(10)))
        .unwrap();

    // Command::spawn waits for exec. Pause its child in pre_exec on another
    // thread, while the test controls exactly when the inherited lock may close.
    // The hook performs only async-signal-safe syscalls on already-owned fds.
    let spawn = std::thread::spawn(move || {
        let ready_fd = ready_child.as_raw_fd();
        let release_fd = release_child.as_raw_fd();
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--ignored",
                "--exact",
                "exec_then_wait_fixture",
                "--nocapture",
            ])
            .env("TRILL_NOTES_INHERITED_LOCK_CHILD", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        unsafe {
            command.pre_exec(move || {
                let mut byte = 1_u8;
                if libc::write(ready_fd, (&byte as *const u8).cast(), 1) != 1 {
                    return Err(io::Error::last_os_error());
                }
                if libc::read(release_fd, (&mut byte as *mut u8).cast(), 1) != 1 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let child = command.spawn();
        // Keep the hook's raw fds owned until spawn has returned after exec.
        drop((ready_child, release_child));
        child
    });
    let reached_fork = ready_parent.read_exact(&mut [0]);
    drop(app);
    let inherited_lock = NotesStore::recover(&root.0, &target());
    let released = release_parent.write_all(&[1]);
    let mut child = spawn.join().unwrap().unwrap();
    // Successful spawn means exec has closed CLOEXEC descriptors. The new test
    // process waits on stdin, so recovery must succeed before process death.
    let still_alive = child.try_wait().unwrap().is_none();
    let after_exec = NotesStore::recover(&root.0, &target());
    let _ = child.kill();
    child.wait().unwrap();

    // Clean up the subprocess before assertions, including on a failed check.
    reached_fork.unwrap();
    released.unwrap();
    assert!(still_alive, "exec fixture must retain a live process");
    match inherited_lock {
        Err(error) => assert_eq!(error.kind(), io::ErrorKind::WouldBlock),
        Ok(_) => panic!("the fork child still owns the inherited flock"),
    }
    let mut recovered = after_exec.unwrap();
    assert_eq!(
        NotesResponse::parse_exact(&recovered.recovery_exact(&query()).unwrap()).unwrap(),
        receipt
    );
    assert!(recovered.apply_exact(&request()).is_err());
    assert!(recovered
        .local_edit("must not restore effect access".into())
        .is_err());
}

#[test]
#[ignore = "subprocess fixture, launched explicitly by its parent test"]
fn exec_then_wait_fixture() {
    assert_eq!(
        std::env::var("TRILL_NOTES_INHERITED_LOCK_CHILD").unwrap(),
        "1"
    );
    let _ = std::io::stdin().read(&mut [0]);
}

#[test]
fn restored_copy_survives_process_death_while_original_receipt_remains_recoverable() {
    let _serial = PROCESS_SCENARIO.lock().unwrap();
    let root = Directory::new();
    let mut original = NotesStore::create(&root.0, target()).unwrap();
    let receipt = original.apply_exact(&request()).unwrap();
    drop(original);
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--ignored",
            "--exact",
            "restore_then_wait_fixture",
            "--nocapture",
        ])
        .env("TRILL_NOTES_RESTORE_TEST_CHILD_ROOT", &root.0)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let output = child.stdout.take().unwrap();
    let (send, receive) = mpsc::channel();
    let reader = std::thread::spawn(move || {
        for line in BufReader::new(output).lines() {
            if line.is_ok_and(|line| line == "NOTES_RESTORED_BEFORE_EXIT") {
                let _ = send.send(());
                return;
            }
        }
    });
    let committed = receive.recv_timeout(Duration::from_secs(10));
    let _ = child.kill();
    let status = child.wait().unwrap();
    reader.join().unwrap();
    assert!(
        committed.is_ok(),
        "restoring child did not persist within the deadline"
    );
    assert!(!status.success());
    let mut restored = NotesStore::recover(&root.0, &reopened_target()).unwrap();
    assert_eq!(restored.text(), "重启后仍可核对的原始效果");
    assert_eq!(restored.revision(), 1);
    assert_eq!(
        read_state(&mut restored, &reopened_target())["receipt_pending"],
        false
    );
    assert!(restored.apply_exact(&request()).is_err());
    let mut original = NotesStore::recover(&root.0, &target()).unwrap();
    assert_eq!(
        NotesResponse::parse_exact(&original.recovery_exact(&query()).unwrap()).unwrap(),
        receipt
    );
}

#[test]
#[ignore = "subprocess fixture, launched explicitly by its parent test"]
fn restore_then_wait_fixture() {
    let Some(root) = std::env::var_os("TRILL_NOTES_RESTORE_TEST_CHILD_ROOT") else {
        return;
    };
    let root = PathBuf::from(root);
    let mut copy = NotesStore::create(&root, reopened_target()).unwrap();
    let selected = NotesStore::saved_documents(&root, &reopened_target())
        .unwrap()
        .documents
        .remove(0);
    copy.restore_saved_text(&root, &selected, 0).unwrap();
    println!("NOTES_RESTORED_BEFORE_EXIT");
    std::io::stdout().flush().unwrap();
    let mut one = [0_u8; 1];
    let _ = std::io::stdin().read(&mut one);
    drop(copy);
}

#[test]
fn durable_receipt_survives_sigkill_before_delivery() {
    let _serial = PROCESS_SCENARIO.lock().unwrap();
    let root = Directory::new();
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--ignored",
            "--exact",
            "persist_then_wait_fixture",
            "--nocapture",
        ])
        .env("TRILL_NOTES_TEST_CHILD_ROOT", &root.0)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let output = child.stdout.take().unwrap();
    let (send, receive) = mpsc::channel();
    let reader = std::thread::spawn(move || {
        for line in BufReader::new(output).lines() {
            if line.is_ok_and(|line| line == "NOTES_DURABLE_BEFORE_REPLY") {
                let _ = send.send(());
                return;
            }
        }
    });
    let committed = receive.recv_timeout(Duration::from_secs(10));
    let _ = child.kill();
    let status = child.wait().unwrap();
    reader.join().unwrap();
    assert!(
        committed.is_ok(),
        "child did not persist before the bounded deadline"
    );
    assert!(!status.success());
    let mut recovered = NotesStore::recover(&root.0, &target()).unwrap();
    let observed =
        NotesResponse::parse_exact(&recovered.recovery_exact(&query()).unwrap()).unwrap();
    let mut expected = NotesDocument::new(target()).unwrap();
    assert_eq!(observed, expected.apply_exact(&request()).unwrap());
    assert_eq!(recovered.text(), "重启后仍可核对的原始效果");
    assert_eq!(recovered.revision(), 1);
    assert!(recovered.apply_exact(&request()).is_err());
}

#[test]
#[ignore = "subprocess fixture, launched explicitly by its parent test"]
fn persist_then_wait_fixture() {
    let Some(root) = std::env::var_os("TRILL_NOTES_TEST_CHILD_ROOT") else {
        return;
    };
    let mut store = NotesStore::create(&PathBuf::from(root), target()).unwrap();
    store.apply_exact(&request()).unwrap();
    // No effect receipt is delivered. The parent kills this real process
    // while it still holds the incarnation lock, then opens recovery alone.
    println!("NOTES_DURABLE_BEFORE_REPLY");
    std::io::stdout().flush().unwrap();
    let mut one = [0_u8; 1];
    let _ = std::io::stdin().read(&mut one);
    drop(store);
}
