//! Original Supervisor/Unix-driver observations plus explicit private-file custody.
use super::*;
use codex_hepta_fleet::{AgentManifest, FleetRegistry, ResourceBudget, WorkspaceBinding};
use codex_hepta_paths::HeptaFleetRoot;
use codex_hepta_supervisor::{AgentCommand, Supervisor, SupervisorConfig, UnixProcessDriver};
use std::time::{Duration, Instant};

struct OriginalFixture {
    supervisor: Supervisor<UnixProcessDriver>,
    agent: AgentId,
    directory: tempfile::TempDir,
}

impl OriginalFixture {
    fn new() -> Self {
        let directory = tempfile::tempdir().unwrap();
        let fleet = HeptaFleetRoot::parse(directory.path().join("fleet")).unwrap();
        let registry = FleetRegistry::initialize(fleet.clone()).unwrap();
        let workspace = directory.path().join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        let agent = AgentId::parse("a77c44fb-0e69-41f1-8eb8-4d4b9ef6d8b1").unwrap();
        registry
            .register(
                AgentManifest::new(
                    agent.clone(),
                    WorkspaceBinding::new(workspace, &fleet).unwrap(),
                    ResourceBudget::local_default(),
                )
                .unwrap(),
            )
            .unwrap();
        let (supervisor, recovery) = Supervisor::recover(
            registry,
            UnixProcessDriver::new(256).unwrap(),
            SupervisorConfig::local_default(),
            Instant::now(),
        )
        .unwrap();
        assert!(recovery.faults.is_empty());
        Self {
            supervisor,
            agent,
            directory,
        }
    }

    fn snapshot(&self) -> AgentSupervisorSnapshot {
        self.supervisor.snapshot(&self.agent).unwrap()
    }
}

impl Drop for OriginalFixture {
    fn drop(&mut self) {
        // Test cleanup signals only the real child retained by this original
        // Supervisor. It never rediscovers a PID or changes product cleanup.
        let _ = self.supervisor.kill(&self.agent);
        let end = Instant::now() + Duration::from_secs(2);
        loop {
            self.supervisor.tick(Instant::now());
            if self
                .supervisor
                .snapshot(&self.agent)
                .is_none_or(|value| value.process_system_id.is_none())
            {
                break;
            }
            assert!(
                Instant::now() < end,
                "test-owned original child was not reaped"
            );
            std::thread::sleep(Duration::from_millis(5));
        }
    }
}

fn stream_hex(document: &serde_json::Value, stream: &str) -> String {
    document["log_tail"]["chunks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|chunk| chunk["stream"] == stream)
        .map(|chunk| chunk["bytes_hex"].as_str().unwrap())
        .collect()
}

#[test]
fn actual_original_unix_logs_and_exit_are_retained_without_utf8_or_signal_inference() {
    let mut fixture = OriginalFixture::new();
    let release = fixture.directory.path().join("release-original-child");
    let command = AgentCommand::new("/bin/sh", vec![
        "-c".into(),
        "printf 'original-out\\n'; printf '\\377original-err\\000\\n' >&2; while [ ! -e \"$1\" ]; do sleep 0.01; done; exit 23".into(),
        "original-supervisor-diagnostic-fixture".into(),
        release.as_os_str().to_owned(),
    ]).unwrap();
    fixture
        .supervisor
        .start(&fixture.agent, command, Instant::now())
        .unwrap();
    let end = Instant::now() + Duration::from_secs(5);
    let before = loop {
        fixture.supervisor.tick(Instant::now());
        let snapshot = fixture.snapshot();
        let observed = FinalObservation::new(
            &fixture.agent,
            ObservationPhase::Monitor,
            CleanupObservation::Unconfirmed,
            None,
            Some(Captured::from_snapshot(snapshot.clone())),
        );
        let value = serde_json::to_value(observed).unwrap();
        if stream_hex(&value, "stdout") == "6f726967696e616c2d6f75740a"
            && stream_hex(&value, "stderr") == "ff6f726967696e616c2d657272000a"
        {
            break Captured::from_snapshot(snapshot);
        }
        assert!(
            Instant::now() < end,
            "original pipe/ring observation not available"
        );
        std::thread::sleep(Duration::from_millis(5));
    };
    std::fs::write(release, b"test-owned release\n").unwrap();
    let after = loop {
        fixture.supervisor.tick(Instant::now());
        let snapshot = fixture.snapshot();
        if snapshot
            .events
            .iter()
            .any(|event| matches!(event.kind, SupervisorEventKind::Exited(_)))
        {
            break Captured::from_snapshot(snapshot);
        }
        assert!(Instant::now() < end, "original exit was not observed");
        std::thread::sleep(Duration::from_millis(5));
    };
    let document = FinalObservation::new(
        &fixture.agent,
        ObservationPhase::Monitor,
        CleanupObservation::StopLoopReturned,
        Some(before),
        Some(after),
    );
    let value = serde_json::to_value(document).unwrap();
    assert!(
        value["before_cleanup"]["process_system_id"]
            .as_u64()
            .is_some()
    );
    assert_eq!(
        value["after_cleanup"]["process_system_id"],
        serde_json::Value::Null
    );
    assert_eq!(value["after_cleanup"]["last_agent_exit"]["success"], false);
    assert_eq!(value["after_cleanup"]["last_agent_exit"]["code"], 23);
    assert_eq!(
        stream_hex(&value, "stderr"),
        "ff6f726967696e616c2d657272000a"
    );
    assert_eq!(value["historical_ring_loss_and_late_pipe_bytes"], "unknown");
    assert_eq!(value["authority_granted"], false);
}

#[test]
fn full_original_ring_has_bounded_tail_and_preserves_exit_outside_event_tail() {
    let fixture = OriginalFixture::new();
    let mut snapshot = fixture.snapshot();
    snapshot.logs = (0..256)
        .map(|value| ProcessLog {
            stream: ProcessStream::Stderr,
            bytes: vec![value as u8; 4096],
        })
        .collect();
    snapshot.events = (0..128)
        .map(|generation| SupervisorEvent {
            generation,
            kind: SupervisorEventKind::DriverFault(
                "private-command-or-token-not-a-public-event-label".into(),
            ),
        })
        .collect();
    snapshot.events[0].kind = SupervisorEventKind::Exited(ProcessExit {
        success: false,
        code: Some(37),
    });
    let document = FinalObservation::new(
        &fixture.agent,
        ObservationPhase::Startup,
        CleanupObservation::Unconfirmed,
        Some(Captured::from_snapshot(snapshot.clone())),
        Some(Captured::from_snapshot(snapshot)),
    );
    let bytes = serde_json::to_vec(&document).unwrap();
    assert!(bytes.len() <= 65_536);
    assert!(!String::from_utf8_lossy(&bytes).contains("private-command-or-token"));
    let value: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(value["after_cleanup"]["last_agent_exit"]["code"], 37);
    assert_eq!(
        value["after_cleanup"]["events"].as_array().unwrap().len(),
        16
    );
    assert_eq!(value["after_cleanup"]["omitted_event_count"], 112);
    assert_eq!(value["log_tail"]["observed_entries"], 256);
    assert_eq!(value["log_tail"]["observed_bytes"], 1_048_576);
    assert_eq!(value["log_tail"]["retained_bytes"], 16_384);
    assert_eq!(value["log_tail"]["omitted_bytes"], 1_032_192);
    let tail = stream_hex(&value, "stderr");
    assert_eq!(
        tail,
        ["fc", "fd", "fe", "ff"]
            .map(|byte| byte.repeat(4096))
            .concat()
    );
}

#[test]
fn absent_exit_code_remains_null_and_missing_snapshot_remains_missing() {
    let event = SupervisorEvent {
        generation: 7,
        kind: SupervisorEventKind::Exited(ProcessExit {
            success: false,
            code: None,
        }),
    };
    let value = serde_json::to_value(EventObservation::from_event(&event)).unwrap();
    assert_eq!(value["exit"]["code"], serde_json::Value::Null);
    assert!(value["exit"].get("signal").is_none());
    let agent = AgentId::parse("a77c44fb-0e69-41f1-8eb8-4d4b9ef6d8b1").unwrap();
    let value = serde_json::to_value(FinalObservation::new(
        &agent,
        ObservationPhase::Startup,
        CleanupObservation::Unconfirmed,
        None,
        None,
    ))
    .unwrap();
    assert_eq!(value["before_cleanup"], serde_json::Value::Null);
    assert_eq!(value["after_cleanup"], serde_json::Value::Null);
    assert_eq!(value["log_snapshot"], "unavailable");
}

#[test]
fn shared_or_non_root_directory_never_becomes_a_diagnostic_sink() {
    use std::os::unix::fs::PermissionsExt;
    let directory = tempfile::tempdir().unwrap();
    std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o770)).unwrap();
    assert!(DiagnosticSink::prepare(directory.path()).is_err());
    assert!(!directory.path().join(FILE_NAME).exists());
}

#[test]
#[ignore = "requires actual Root and explicit protected TRILL_ROOT_DIAGNOSTIC_TEST_PARENT"]
fn actual_root_private_sink_refuses_replacement_and_owner_read() -> Result<()> {
    use std::os::unix::fs::PermissionsExt;
    let parent = std::env::var_os("TRILL_ROOT_DIAGNOSTIC_TEST_PARENT")
        .ok_or("explicit private diagnostic fixture parent required")?;
    private_directory(Path::new(&parent))?;
    let directory = tempfile::tempdir_in(parent)?;
    let admin = directory.path().join("admin");
    fs::directory_new(&admin, 0o700, None)?;
    let sink = DiagnosticSink::prepare(&admin)?;
    let agent = AgentId::parse("a77c44fb-0e69-41f1-8eb8-4d4b9ef6d8b1")?;
    sink.retain(
        &agent,
        ObservationPhase::Startup,
        CleanupObservation::Unconfirmed,
        None,
        None,
    )?;
    let file = admin.join(FILE_NAME);
    let before = std::fs::read(&file)?;
    let metadata = std::fs::symlink_metadata(&file)?;
    assert_eq!(metadata.mode() & 0o7777, 0o600);
    assert_eq!(metadata.uid(), 0);
    assert_eq!(metadata.nlink(), 1);
    let value: serde_json::Value = fs::read_root_json(&file)?;
    assert_eq!(value["scope"], "original_observed_supervisor_ring_only");
    assert!(
        sink.retain(
            &agent,
            ObservationPhase::Monitor,
            CleanupObservation::Unconfirmed,
            None,
            None
        )
        .is_err()
    );
    assert_eq!(std::fs::read(&file)?, before);
    assert!(DiagnosticSink::prepare(&admin).is_err());

    let mut command = std::process::Command::new("/usr/bin/test");
    command
        .arg("-r")
        .arg(&file)
        .env_clear()
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    super::super::process::drop_to_owner(&mut command, 60001, 60001);
    assert_eq!(command.status()?.code(), Some(1));

    let replaced = directory.path().join("replaced");
    fs::directory_new(&replaced, 0o700, None)?;
    let pinned = DiagnosticSink::prepare(&replaced)?;
    std::fs::rename(&replaced, directory.path().join("retained-original"))?;
    fs::directory_new(&replaced, 0o700, None)?;
    assert!(
        pinned
            .retain(
                &agent,
                ObservationPhase::Startup,
                CleanupObservation::Unconfirmed,
                None,
                None
            )
            .is_err()
    );
    assert!(!replaced.join(FILE_NAME).exists());
    std::fs::set_permissions(&replaced, std::fs::Permissions::from_mode(0o750))?;
    assert!(DiagnosticSink::prepare(&replaced).is_err());
    std::os::unix::fs::symlink(&admin, directory.path().join("alias"))?;
    assert!(DiagnosticSink::prepare(&directory.path().join("alias")).is_err());
    Ok(())
}
