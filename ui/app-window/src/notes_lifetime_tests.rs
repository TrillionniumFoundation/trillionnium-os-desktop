//! Real process lifetime oracle; no Root, grant, model or reconnect is fabricated.
use super::*;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::PermissionsExt;
use std::process::{Child, Command as ProcessCommand, Stdio};
use std::time::Duration;
use trill_ui_core::notes::*;
use trill_ui_core::notes_lifetime::{SessionLifetimeSource, FD_ENV_V1, META_ENV_V1};

const ROLE: &str = "TRILL_TEST_LIFETIME_ROLE";
const CASE: &str = "TRILL_TEST_LIFETIME_CASE";
const PARENT: &str = "notes_organ::worker::lifetime_tests::original_session_parent_fixture";
const APP: &str = "notes_organ::worker::lifetime_tests::original_notes_app_fixture";

fn target() -> NotesTargetIdentity {
    NotesTargetIdentity {
        session_instance: "7".repeat(32),
        task_id: 42,
        incarnation: "8".repeat(32),
    }
}
fn mutation() -> Vec<u8> {
    serde_json::to_vec(&NotesReplace {
        schema_version: 1,
        action: NotesReplaceAction::ReplaceNote,
        operation_id: "original-session-effect".into(),
        destination_id: target().destination_id(),
        target: target(),
        expected_revision: 0,
        text: "真实父进程退出后可回读".into(),
    })
    .unwrap()
}
fn query() -> Vec<u8> {
    serde_json::to_vec(&NotesObserve {
        schema_version: 1,
        action: NotesObserveAction::Observe,
        target: target(),
        operation_id: "original-session-effect".into(),
        payload_sha256: sha256_hex(&mutation()),
    })
    .unwrap()
}
fn fixture_command(test: &str, role: &str) -> ProcessCommand {
    let mut command = ProcessCommand::new(std::env::current_exe().unwrap());
    command
        .args(["--exact", test, "--nocapture"])
        .env(ROLE, role);
    command
}

// This spawning thread deliberately exits while the Session process stays alive.
// A thread-parent/PDEATHSIG implementation fails the outer alive/locked assertion.
#[test]
fn original_session_parent_fixture() {
    if std::env::var(ROLE).as_deref() != Ok("session") {
        return;
    }
    let case = std::env::var(CASE).unwrap();
    let child = std::thread::spawn(move || {
        let mut command = fixture_command(APP, "app");
        command.stdin(Stdio::null());
        SessionLifetimeSource::capture_current(target(), StorageRequirement::DurableRequired)
            .unwrap()
            .inherit_into(&mut command)
            .unwrap();
        if case != "kill" && case != "exit" {
            let encoded = command
                .get_envs()
                .find(|(k, _)| *k == META_ENV_V1)
                .unwrap()
                .1
                .unwrap()
                .to_str()
                .unwrap()
                .to_owned();
            let mut meta: serde_json::Value = serde_json::from_str(&encoded).unwrap();
            match case.as_str() {
                "boot" => meta["boot_id"] = "different-boot".into(),
                "birth" => {
                    meta["process_start_ticks"] =
                        (meta["process_start_ticks"].as_u64().unwrap() + 1).into()
                }
                "uid" => meta["uid"] = (meta["uid"].as_u64().unwrap() + 1).into(),
                "gid" => meta["gid"] = (meta["gid"].as_u64().unwrap() + 1).into(),
                "parent" => meta["pid"] = (meta["pid"].as_u64().unwrap() + 1).into(),
                "target" => meta["target"]["task_id"] = 43.into(),
                "version" => meta["schema_version"] = 2.into(),
                "purpose" => meta["purpose"] = "grant_root".into(),
                "unknown" => meta["authority"] = true.into(),
                "partial" | "descriptor" | "duplicate" | "storage_missing" => {}
                _ => panic!("unknown test case"),
            }
            let mut encoded = serde_json::to_string(&meta).unwrap();
            if case == "duplicate" {
                encoded.insert_str(1, "\"schema_version\":1,");
            }
            command.env(META_ENV_V1, encoded);
            if case == "partial" {
                command.env_remove(META_ENV_V1);
            }
            if case == "descriptor" {
                command.env(FD_ENV_V1, "1");
            }
            if case == "storage_missing" {
                command.env_remove("TRILL_NOTES_STATE_DIR");
            }
        }
        command.spawn().unwrap()
    })
    .join()
    .unwrap();
    println!("PARENT_READY {}", child.id());
    std::io::stdout().flush().unwrap();
    let mut child = child;
    if case_is_negative() {
        assert!(child.wait().unwrap().success());
    } else {
        let mut barrier = [0_u8];
        std::io::stdin().read_exact(&mut barrier).unwrap();
        // Drop of Child does not kill the real child; this parent actually exits.
    }
}
fn case_is_negative() -> bool {
    !matches!(std::env::var(CASE).as_deref(), Ok("kill") | Ok("exit"))
}

#[test]
fn original_notes_app_fixture() {
    if std::env::var(ROLE).as_deref() != Ok("app") {
        return;
    }
    let lifetime = SessionLifetime::from_environment(&target());
    if case_is_negative() {
        if std::env::var(CASE).as_deref() == Ok("storage_missing") {
            assert!(start(egui::Context::default(), target(), lifetime.unwrap()).is_err());
        } else {
            assert!(lifetime.is_err());
        }
        println!("APP_REJECTED");
        return;
    }
    let lifetime = lifetime.unwrap().unwrap();
    let connection = start(egui::Context::default(), target(), Some(lifetime.clone())).unwrap();
    let (reply, receiver) = mpsc::sync_channel(1);
    connection
        .sender
        .send(Command::Protocol(super::super::Pending {
            bytes: mutation(),
            expires_at: Instant::now() + Duration::from_secs(2),
            recovery: false,
            reply,
        }))
        .unwrap();
    let receipt = receiver
        .recv_timeout(Duration::from_secs(3))
        .unwrap()
        .unwrap();
    println!("APP_READY {}", String::from_utf8(receipt).unwrap());
    std::io::stdout().flush().unwrap();
    let deadline = Instant::now() + Duration::from_secs(12);
    while !lifetime.has_ended() {
        assert!(Instant::now() < deadline, "real parent failed to exit");
        std::thread::sleep(Duration::from_millis(5));
    }
    // Keep Connection/sender alive: only the original lifetime fence can retire
    // the worker. Disconnection confirms that the worker dropped its real store.
    loop {
        match connection.sender.try_send(Command::ListSaved { id: 100 }) {
            Err(mpsc::TrySendError::Disconnected(_)) => break,
            Ok(()) | Err(mpsc::TrySendError::Full(_)) => {
                assert!(
                    Instant::now() < deadline,
                    "worker retained store after Session death"
                );
                std::thread::sleep(Duration::from_millis(5));
            }
        }
    }
    let mut channel = super::super::NotesAppChannel::from_worker(connection);
    channel.input_queue_changed(true);
    assert_eq!(channel.close_state(), super::super::NotesCloseState::Saving);
    let ctx = egui::Context::default();
    let frame = ctx.run(egui::RawInput::default(), |ctx| {
        assert!(channel.close_if_session_ended(ctx));
    });
    let commands = &frame.viewport_output[&egui::ViewportId::ROOT].commands;
    assert!(commands.contains(&egui::ViewportCommand::Close));
    assert!(!commands.contains(&egui::ViewportCommand::CancelClose));
    println!("APP_EXIT");
}

struct Root(std::path::PathBuf);
impl Root {
    fn new() -> Self {
        let mut random = [0_u8; 16];
        fs::File::open("/dev/urandom")
            .unwrap()
            .read_exact(&mut random)
            .unwrap();
        let suffix: String = random.iter().map(|v| format!("{v:02x}")).collect();
        let path = std::env::temp_dir().join(format!("trill-notes-lifetime-{suffix}"));
        fs::create_dir(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
        Self(path)
    }
}
impl Drop for Root {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
struct RunningParent(Child);
impl Drop for RunningParent {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
struct HeldApp(OwnedFd);
impl Drop for HeldApp {
    fn drop(&mut self) {
        // Test cleanup uses only the descriptor opened while this actual child
        // was live. A changed/reused numeric PID is never signalled.
        unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.0.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            );
        }
    }
}
fn start_parent(case: &str, root: &Root) -> (RunningParent, mpsc::Receiver<String>) {
    let mut child = fixture_command(PARENT, "session")
        .env(CASE, case)
        .env("TRILL_NOTES_STATE_DIR", &root.0)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let output = child.stdout.take().unwrap();
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        for line in BufReader::new(output).lines() {
            if tx.send(line.unwrap()).is_err() {
                break;
            }
        }
    });
    (RunningParent(child), rx)
}
fn next(rx: &mpsc::Receiver<String>) -> String {
    rx.recv_timeout(Duration::from_secs(8))
        .expect("bounded actual process progress")
}

#[test]
fn session_process_exit_retires_actual_store_despite_spawning_thread_exit() {
    for case in ["kill", "exit"] {
        let root = Root::new();
        let (mut parent, output) = start_parent(case, &root);
        let (mut pid, mut receipt) = (None, None);
        while pid.is_none() || receipt.is_none() {
            let line = next(&output);
            if let Some(value) = line.split_once("PARENT_READY ").map(|(_, value)| value) {
                pid = Some(value.parse::<u32>().unwrap());
            }
            if let Some(value) = line.split_once("APP_READY ").map(|(_, value)| value) {
                receipt = Some(value.as_bytes().to_vec());
            }
        }
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid.unwrap(), 0) };
        assert!(raw >= 0);
        let app_pidfd = HeldApp(unsafe { OwnedFd::from_raw_fd(raw as i32) });
        let mut poll = libc::pollfd {
            fd: app_pidfd.0.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        assert_eq!(
            unsafe { libc::poll(&mut poll, 1, 0) },
            0,
            "spawn thread exited, process stays alive"
        );
        assert_eq!(
            NotesStore::recover(&root.0, &target())
                .err()
                .unwrap()
                .kind(),
            io::ErrorKind::WouldBlock
        );
        if case == "kill" {
            parent.0.kill().unwrap();
        } else {
            parent.0.stdin.take().unwrap().write_all(&[1]).unwrap();
        }
        let status = parent.0.wait().unwrap();
        assert_eq!(status.success(), case == "exit");
        while !next(&output).contains("APP_EXIT") {}
        assert_eq!(
            unsafe { libc::poll(&mut poll, 1, 3000) },
            1,
            "actual App fixture exited"
        );
        let mut recovered = NotesStore::recover(&root.0, &target()).unwrap();
        assert_eq!(recovered.text(), "真实父进程退出后可回读");
        assert_eq!(recovered.revision(), 1);
        assert_eq!(
            recovered.recovery_exact(&query()).unwrap(),
            receipt.unwrap()
        );
        assert!(
            recovered.apply_exact(&mutation()).is_err(),
            "recovery never reopens effect capability"
        );
    }
}

#[test]
fn inherited_lifetime_rejects_changed_identity_and_missing_durable_storage() {
    for case in [
        "boot",
        "birth",
        "uid",
        "gid",
        "parent",
        "target",
        "version",
        "purpose",
        "unknown",
        "partial",
        "descriptor",
        "duplicate",
        "storage_missing",
    ] {
        let root = Root::new();
        let (mut parent, output) = start_parent(case, &root);
        while !next(&output).contains("APP_REJECTED") {}
        assert!(parent.0.wait().unwrap().success(), "case {case}");
        assert_eq!(
            fs::read_dir(&root.0).unwrap().count(),
            0,
            "case {case} created storage"
        );
    }
}
