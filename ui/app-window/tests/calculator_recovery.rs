//! Real application helper processes. These fixture ACKs are not Root-owner permits.
#![cfg(target_os = "linux")]
use std::fs::{self, DirBuilder, File};
use std::io::{BufRead, BufReader, Read};
use std::os::fd::OwnedFd;
use std::os::unix::fs::DirBuilderExt;
use std::os::unix::net::UnixDatagram;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;
use trill_ui_core::calculator::*;
use trill_ui_core::calculator_store::CalculatorStore;

struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let mut nonce = [0_u8; 16];
        File::open("/dev/urandom")
            .unwrap()
            .read_exact(&mut nonce)
            .unwrap();
        let path = std::env::temp_dir().join(format!(
            "trill-calculator-helper-{}",
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
struct Helper {
    child: Child,
    channel: UnixDatagram,
}
impl Drop for Helper {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
impl Helper {
    fn start(root: &Path, target: &CalculatorTargetIdentity) -> Self {
        let (channel, inherited) = UnixDatagram::pair().unwrap();
        channel
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        channel
            .set_write_timeout(Some(Duration::from_secs(1)))
            .unwrap();
        let child = Command::new(env!("CARGO_BIN_EXE_trill-calculator-recovery"))
            .arg("--state-dir")
            .arg(root)
            .arg("--calculator-session")
            .arg(&target.session_instance)
            .arg("--calculator-incarnation")
            .arg(&target.incarnation)
            .arg("--task-id")
            .arg(target.task_id.to_string())
            .stdin(Stdio::from(OwnedFd::from(inherited)))
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap();
        let mut helper = Self { child, channel };
        let stdout = helper.child.stdout.take().unwrap();
        let (send, receive) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let mut line = String::new();
            let result = BufReader::new(stdout).read_line(&mut line).map(|_| line);
            let _ = send.send(result);
        });
        assert_eq!(
            receive
                .recv_timeout(Duration::from_secs(3))
                .unwrap()
                .unwrap(),
            "TRILL_CALCULATOR_RECOVERY_READY_V1\n"
        );
        helper
    }
    fn exchange(&self, bytes: &[u8]) -> Vec<u8> {
        self.channel.send(bytes).unwrap();
        let mut raw = [0_u8; MAX_CALCULATOR_RESPONSE_BYTES + 1];
        let size = self.channel.recv(&mut raw).unwrap();
        assert!(size > 0 && size <= MAX_CALCULATOR_RESPONSE_BYTES);
        raw[..size].to_vec()
    }
}

#[test]
fn real_helper_recovers_lost_application_reply_and_lost_retirement_ack_without_effects() {
    let root = Directory::new();
    let target = CalculatorTargetIdentity {
        session_instance: "1".repeat(32),
        task_id: 2,
        incarnation: "2".repeat(32),
    };
    let payload = serde_json::to_vec(&CalculatorEvaluate {
        schema_version: 1,
        action: CalculatorEvaluateAction::Evaluate,
        target: target.clone(),
        destination_id: target.destination_id(),
        operation_id: "actual-helper-fixture".into(),
        expected_revision: 0,
        left: "12".into(),
        operator: CalculatorOperator::Add,
        right: "30".into(),
    })
    .unwrap();
    let mut app = CalculatorStore::create(&root.0, target.clone()).unwrap();
    let receipt = serde_json::to_vec(&app.apply_exact(&payload).unwrap()).unwrap();
    drop(app);
    let observe = serde_json::to_vec(&CalculatorObserve {
        schema_version: 1,
        action: CalculatorObserveAction::Observe,
        target: target.clone(),
        operation_id: "actual-helper-fixture".into(),
        payload_sha256: sha256_hex(&payload),
    })
    .unwrap();
    let helper = Helper::start(&root.0, &target);
    assert_eq!(helper.exchange(&observe), receipt);
    // Even exact old mutation bytes cannot enter the readback parser.
    helper
        .channel
        .set_read_timeout(Some(Duration::from_millis(150)))
        .unwrap();
    helper.channel.send(&payload).unwrap();
    assert!(helper
        .channel
        .recv(&mut [0_u8; MAX_CALCULATOR_RESPONSE_BYTES + 1])
        .is_err());
    helper
        .channel
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    assert_eq!(helper.exchange(&observe), receipt);
    let read = serde_json::to_vec(&CalculatorRead {
        schema_version: 1,
        action: CalculatorReadAction::ReadCalculator,
        target: target.clone(),
        observation_id: "3".repeat(32),
    })
    .unwrap();
    let state: CalculatorStateObservation =
        serde_json::from_slice(&helper.exchange(&read)).unwrap();
    assert_eq!(state.revision, 1);
    assert_eq!(state.state.result, "42");
    assert!(state.receipt_pending);
    let ack = serde_json::to_vec(&CalculatorAcknowledge {
        schema_version: 1,
        action: CalculatorAcknowledgeAction::Acknowledge,
        target: target.clone(),
        operation_id: "actual-helper-fixture".into(),
        payload_sha256: sha256_hex(&payload),
        receipt_sha256: sha256_hex(&receipt),
    })
    .unwrap();
    let retired: CalculatorAcknowledged = serde_json::from_slice(&helper.exchange(&ack)).unwrap();
    assert_eq!(retired.status, CalculatorAcknowledgementStatus::Retired);
    drop(helper);
    let helper = Helper::start(&root.0, &target);
    let repeated: CalculatorAcknowledged = serde_json::from_slice(&helper.exchange(&ack)).unwrap();
    assert_eq!(
        repeated.status,
        CalculatorAcknowledgementStatus::AlreadyRetired
    );
    let state: CalculatorStateObservation =
        serde_json::from_slice(&helper.exchange(&read)).unwrap();
    assert_eq!(state.revision, 1);
    assert_eq!(state.state.result, "42");
    assert!(!state.receipt_pending);
    let observed = CalculatorResponse::parse_exact(&helper.exchange(&observe)).unwrap();
    assert!(matches!(
        observed.result,
        CalculatorResult::Unknown {
            current_revision: 1
        }
    ));
}
