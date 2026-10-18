//! Actual Session executable and Unix IPC against a scripted fixed-v2 peer.
//! This is read-only host evidence, not an original Agentd or an effect test.
use serde_json::{json, Value};
use std::fs::{self, Permissions};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::os::unix::net::UnixListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU8, AtomicUsize, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use trill_ui_core::hepta::{HeptaConnectionState, HeptaProjection, HeptaRunConnectionState};
use trill_ui_core::{request_at, Request, Response};

const AGENT: &str = "11111111-1111-4111-8111-111111111111";
const PRESENT: u8 = 0;
const MISSING: u8 = 1;
const OLD_SPAWN: u8 = 2;
const HELD_RUN: u8 = 3;
const HELD_RUNTIME: u8 = 4;
static NEXT_RUNTIME: AtomicUsize = AtomicUsize::new(1);

#[derive(Default)]
struct Control {
    mode: AtomicU8,
    run_held: AtomicBool,
    runtime_held: AtomicBool,
    hold_capabilities: AtomicBool,
    stopping: AtomicBool,
    run_reads: AtomicUsize,
}

struct Harness {
    child: Child,
    runtime: PathBuf,
    control: Arc<Control>,
    fixture: Option<JoinHandle<()>>,
}

impl Harness {
    fn new(run_id: Option<&str>, mode: u8) -> Self {
        let runtime = std::env::temp_dir().join(format!(
            "trill-run-{}-{}",
            std::process::id(),
            NEXT_RUNTIME.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&runtime).unwrap();
        fs::set_permissions(&runtime, Permissions::from_mode(0o700)).unwrap();
        let socket = runtime.join("owner.sock");
        let listener = UnixListener::bind(&socket).unwrap();
        fs::set_permissions(&socket, Permissions::from_mode(0o600)).unwrap();
        listener.set_nonblocking(true).unwrap();
        let control = Arc::new(Control::default());
        control.mode.store(mode, Ordering::SeqCst);
        let worker_control = Arc::clone(&control);
        let expected_run = run_id.unwrap_or("unconfigured:must-not-read").to_owned();
        let fixture = thread::spawn(move || serve(listener, &expected_run, &worker_control));
        let child = Command::new(env!("CARGO_BIN_EXE_trill-session"))
            .env("XDG_RUNTIME_DIR", &runtime)
            .env("TRILL_HEPTA_AGENTD_SOCKET", socket)
            .env("TRILL_HEPTA_AGENT_ID", AGENT)
            .env("TRILL_HEPTA_SPAWN_GENERATION", "7")
            .env(
                "TRILL_HEPTA_PEER_UID",
                fs::metadata(&runtime).unwrap().uid().to_string(),
            )
            .env_remove("TRILL_HEPTA_RUN_ID")
            .envs(run_id.map(|run_id| ("TRILL_HEPTA_RUN_ID", run_id)))
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        Self {
            child,
            runtime,
            control,
            fixture: Some(fixture),
        }
    }

    fn snapshot(&mut self) -> (HeptaProjection, String) {
        let started = Instant::now();
        loop {
            let before = Instant::now();
            if let Ok(response) = request_at(
                &self.runtime.join("trillionnium-ui/session.sock"),
                &Request::Snapshot,
            ) {
                assert!(
                    before.elapsed() < Duration::from_millis(750),
                    "run observer blocked Session IPC"
                );
                let Response::Snapshot {
                    hepta,
                    tasks,
                    session_instance,
                    ..
                } = response
                else {
                    panic!("expected snapshot");
                };
                assert!(tasks.is_empty(), "a run observation created a HostTask");
                return (hepta, session_instance);
            }
            assert!(self.child.try_wait().unwrap().is_none(), "Session exited");
            assert!(
                started.elapsed() < Duration::from_secs(3),
                "Session IPC unavailable"
            );
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn until(&mut self, predicate: impl Fn(&HeptaProjection) -> bool) -> HeptaProjection {
        let started = Instant::now();
        loop {
            let (view, _) = self.snapshot();
            if predicate(&view) {
                return view;
            }
            assert!(
                started.elapsed() < Duration::from_secs(4),
                "expected projection not received: {view:?}"
            );
            thread::sleep(Duration::from_millis(20));
        }
    }
}

impl Drop for Harness {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        self.control.stopping.store(true, Ordering::SeqCst);
        if let Some(fixture) = self.fixture.take() {
            let result = fixture.join();
            if !thread::panicking() {
                result.unwrap();
            }
        }
        let _ = fs::remove_dir_all(&self.runtime);
    }
}

fn hold(control: &Control, condition: impl Fn() -> bool) {
    let started = Instant::now();
    while condition() && !control.stopping.load(Ordering::SeqCst) {
        assert!(
            started.elapsed() < Duration::from_secs(8),
            "fixture hold was not released"
        );
        thread::sleep(Duration::from_millis(10));
    }
}

fn serve(listener: UnixListener, expected_run: &str, control: &Control) {
    let mut fixtures: Value = serde_json::from_str(include_str!(
        "../../../services/hepta-os/tests/fixtures/agentd_v2_payloads.json"
    ))
    .unwrap();
    fixtures["health"]["process_id"] = json!(std::process::id());
    fixtures["run_status"]["run"]["run_id"] = json!(expected_run);
    while !control.stopping.load(Ordering::SeqCst) {
        let (mut connection, _) = match listener.accept() {
            Ok(connection) => connection,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(5));
                continue;
            }
            Err(error) => panic!("fixture accept failed: {error}"),
        };
        connection
            .set_read_timeout(Some(Duration::from_secs(1)))
            .unwrap();
        connection
            .set_write_timeout(Some(Duration::from_secs(1)))
            .unwrap();
        let mut frame = Vec::new();
        BufReader::new((&mut connection).take(65_537))
            .read_until(b'\n', &mut frame)
            .unwrap();
        let request: Value = serde_json::from_slice(&frame).unwrap();
        assert_eq!(request["schema_version"], 2);
        assert_eq!(request["spawn_generation"], 7);
        let method = &request["method"];
        let payload = match method["type"].as_str().unwrap() {
            "health" => fixtures["health"].clone(),
            "capabilities" => {
                if control.mode.load(Ordering::SeqCst) == HELD_RUNTIME {
                    control.runtime_held.store(true, Ordering::SeqCst);
                    hold(control, || {
                        control.mode.load(Ordering::SeqCst) == HELD_RUNTIME
                    });
                }
                hold(control, || control.hold_capabilities.load(Ordering::SeqCst));
                fixtures["capabilities"].clone()
            }
            "events" => {
                let after = method["after_cursor"].as_u64().unwrap();
                let events: Vec<Value> = fixtures["events"]["events"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .filter(|event| event["cursor"].as_u64().unwrap() > after)
                    .take(method["limit"].as_u64().unwrap() as usize)
                    .cloned()
                    .collect();
                let next = events
                    .last()
                    .map_or(after, |event| event["cursor"].as_u64().unwrap());
                json!({"type":"events","events":events,"gap":false,"next_cursor":next,"latest_cursor":3})
            }
            "run_status" => {
                assert_eq!(
                    method["run_id"], expected_run,
                    "observer selected a different run identity"
                );
                control.run_reads.fetch_add(1, Ordering::SeqCst);
                if control.mode.load(Ordering::SeqCst) == HELD_RUN {
                    control.run_held.store(true, Ordering::SeqCst);
                    hold(control, || control.mode.load(Ordering::SeqCst) == HELD_RUN);
                }
                if control.mode.load(Ordering::SeqCst) == MISSING {
                    json!({"type":"run_status","run":null})
                } else {
                    fixtures["run_status"].clone()
                }
            }
            other => panic!("Session called a method outside the read-only subset: {other}"),
        };
        let spawn = if control.mode.load(Ordering::SeqCst) == OLD_SPAWN {
            6
        } else {
            7
        };
        let mut response = serde_json::to_vec(&json!({
            "schema_version":2,"request_id":request["request_id"],"agent_id":AGENT,
            "spawn_generation":spawn,"current_generation":spawn+1,"payload":payload,
        }))
        .unwrap();
        response.push(b'\n');
        // The Session may already have timed out or stopped during a fault.
        let _ = connection.write_all(&response);
    }
}

#[test]
fn exact_known_run_projects_only_owner_metadata_and_retains_it_on_null_and_old_spawn() {
    let run_id = format!("known:{}", "r".repeat(122));
    let mut harness = Harness::new(Some(&run_id), PRESENT);
    let first = harness.until(|view| {
        view.run
            .as_ref()
            .is_some_and(|run| run.connection == HeptaRunConnectionState::Observed)
    });
    assert_eq!(first.connection, HeptaConnectionState::Observed);
    assert!(
        first
            .runtime_sample_clock
            .as_deref()
            .unwrap()
            .observation_sequence
            > 0
    );
    let run = first.run.as_ref().unwrap();
    assert_eq!(run.run_id, run_id);
    let first_sample_age = run.sample_age_at_snapshot_ms.unwrap();
    let last = run.last_observation.clone().unwrap();
    assert_eq!(last.run_id, run_id);
    assert_eq!(last.revision, 4);
    assert_eq!(last.phase, "indeterminate");
    assert_eq!(
        last.generation, 6,
        "run generation is not the current daemon generation"
    );
    assert_eq!(last.authority_epoch, 9);
    assert!(!last.terminal_observed);
    let serialized = serde_json::to_string(&first).unwrap();
    for private in [
        "private fixture detail",
        "context_digest",
        "fence_digest",
        "cancel_reason",
        "/private-fixture/",
    ] {
        assert!(
            !serialized.contains(private),
            "private run/runtime detail leaked"
        );
    }

    harness.control.mode.store(MISSING, Ordering::SeqCst);
    let missing = harness.until(|view| {
        view.run
            .as_ref()
            .is_some_and(|run| run.connection == HeptaRunConnectionState::ProjectionMissing)
    });
    assert_eq!(missing.connection, HeptaConnectionState::Observed);
    let missing = missing.run.unwrap();
    let missing_sample_age = missing.sample_age_at_snapshot_ms.unwrap();
    assert!(missing_sample_age >= first_sample_age);
    assert_eq!(missing.last_observation.as_ref(), Some(&last));
    assert_eq!(
        missing.error_code.as_deref(),
        Some("run_projection_missing")
    );
    assert!(missing.observation_gap);
    assert!(missing.last_attempt_unix_ms.unwrap() > last.sampled_unix_ms);

    harness.control.mode.store(OLD_SPAWN, Ordering::SeqCst);
    let fenced = harness.until(|view| view.connection == HeptaConnectionState::Stale);
    assert_eq!(fenced.error_code.as_deref(), Some("protocol_mismatch"));
    let failed_again =
        harness.until(|view| view.last_attempt_unix_ms > fenced.last_attempt_unix_ms);
    assert_eq!(failed_again.connection, HeptaConnectionState::Stale);
    assert_eq!(failed_again.last_observation, fenced.last_observation);
    assert_eq!(
        failed_again
            .runtime_sample_clock
            .as_deref()
            .unwrap()
            .observation_sequence,
        fenced
            .runtime_sample_clock
            .as_deref()
            .unwrap()
            .observation_sequence
    );
    assert!(
        failed_again
            .runtime_sample_clock
            .as_deref()
            .unwrap()
            .sample_age_at_snapshot_ms
            >= fenced
                .runtime_sample_clock
                .as_deref()
                .unwrap()
                .sample_age_at_snapshot_ms
    );
    let run = fenced.run.unwrap();
    assert!(run.sample_age_at_snapshot_ms.unwrap() >= missing_sample_age);
    assert_eq!(run.connection, HeptaRunConnectionState::Stale);
    assert_eq!(run.last_observation.as_ref(), Some(&last));
    assert!(run.observation_gap);
}

#[test]
fn a_slow_successful_run_read_never_retimestamps_health_or_blocks_host_dispatch() {
    let mut harness = Harness::new(Some("known:slow-read"), HELD_RUN);
    let initial = harness.until(|view| view.connection == HeptaConnectionState::Observed);
    let runtime_sample = initial.last_observation.unwrap().sampled_unix_ms;
    let runtime_attempt = initial.last_attempt_unix_ms;
    let runtime_clock = initial.runtime_sample_clock.as_deref().unwrap();
    assert!(runtime_attempt.unwrap() >= runtime_sample);
    let started = Instant::now();
    while !harness.control.run_held.load(Ordering::SeqCst) {
        assert!(started.elapsed() < Duration::from_secs(2));
        thread::sleep(Duration::from_millis(10));
    }
    let held = Instant::now();
    while held.elapsed() < Duration::from_millis(900) {
        let (view, session_instance) = harness.snapshot();
        assert_eq!(
            view.last_observation.unwrap().sampled_unix_ms,
            runtime_sample
        );
        assert_eq!(view.last_attempt_unix_ms, runtime_attempt);
        assert_eq!(
            view.runtime_sample_clock
                .as_deref()
                .unwrap()
                .observation_sequence,
            runtime_clock.observation_sequence
        );
        assert!(
            view.runtime_sample_clock
                .as_deref()
                .unwrap()
                .sample_age_at_snapshot_ms
                >= runtime_clock.sample_age_at_snapshot_ms
        );
        assert_eq!(
            view.run.unwrap().connection,
            HeptaRunConnectionState::Connecting
        );
        let before = Instant::now();
        let response = request_at(
            &harness.runtime.join("trillionnium-ui/session.sock"),
            &Request::Cancel {
                id: u64::MAX,
                expected_instance: session_instance,
            },
        )
        .unwrap();
        assert!(matches!(response, Response::Error { .. }));
        assert!(before.elapsed() < Duration::from_millis(750));
        thread::sleep(Duration::from_millis(20));
    }
    // Permit the closing run health check but hold the next complete health/
    // capability poll. This makes timestamp comparison independent of races
    // against the worker's next one-second polling interval.
    harness
        .control
        .hold_capabilities
        .store(true, Ordering::SeqCst);
    harness.control.mode.store(PRESENT, Ordering::SeqCst);
    let fresh_run = harness.until(|view| {
        view.run
            .as_ref()
            .is_some_and(|run| run.connection == HeptaRunConnectionState::Observed)
    });
    assert_eq!(
        fresh_run.last_observation.unwrap().sampled_unix_ms,
        runtime_sample
    );
    assert_eq!(fresh_run.last_attempt_unix_ms, runtime_attempt);
    assert_eq!(
        fresh_run
            .runtime_sample_clock
            .as_deref()
            .unwrap()
            .observation_sequence,
        runtime_clock.observation_sequence
    );
    assert!(
        fresh_run
            .runtime_sample_clock
            .as_deref()
            .unwrap()
            .sample_age_at_snapshot_ms
            >= 900
    );
    let run = fresh_run.run.unwrap();
    assert!(run.sample_age_at_snapshot_ms.unwrap() >= 900);
    let sample = run.last_observation.unwrap();
    assert!(sample.sampled_unix_ms >= runtime_sample);
    assert!(run.last_attempt_unix_ms.unwrap() >= sample.sampled_unix_ms + 900);
    assert_eq!(sample.observation_sequence, 1);
}

#[test]
fn an_endpoint_without_a_run_id_reports_runtime_age_and_never_reads_a_run() {
    let mut harness = Harness::new(None, PRESENT);
    let view = harness.until(|view| view.connection == HeptaConnectionState::Observed);
    assert!(view.run.is_none());
    let serialized = serde_json::to_value(view).unwrap();
    assert_eq!(serialized.as_object().unwrap().len(), 5);
    assert!(
        serialized["runtime_sample_clock"]["observation_sequence"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert!(serialized["runtime_sample_clock"]["sample_age_at_snapshot_ms"].is_u64());
    assert!(serialized.get("run").is_none());
    assert_eq!(harness.control.run_reads.load(Ordering::SeqCst), 0);
}

#[test]
fn a_slow_successful_runtime_poll_counts_its_whole_read_and_keeps_session_ipc_live() {
    let mut harness = Harness::new(None, HELD_RUNTIME);
    let started = Instant::now();
    while !harness.control.runtime_held.load(Ordering::SeqCst) {
        assert!(started.elapsed() < Duration::from_secs(2));
        thread::sleep(Duration::from_millis(10));
    }
    let held = Instant::now();
    while held.elapsed() < Duration::from_millis(900) {
        let (view, _) = harness.snapshot();
        assert_eq!(view.connection, HeptaConnectionState::Connecting);
        assert!(view.runtime_sample_clock.is_none());
        thread::sleep(Duration::from_millis(20));
    }
    harness.control.mode.store(PRESENT, Ordering::SeqCst);
    let observed = harness.until(|view| view.connection == HeptaConnectionState::Observed);
    let clock = observed.runtime_sample_clock.as_deref().unwrap();
    assert_eq!(clock.observation_sequence, 1);
    assert!(
        clock.sample_age_at_snapshot_ms >= 900,
        "slow successful poll was retimestamped on completion"
    );
    let sample = observed.last_observation.unwrap();
    assert!(observed.last_attempt_unix_ms.unwrap() >= sample.sampled_unix_ms + 900);
    assert!(observed.run.is_none());
    assert_eq!(harness.control.run_reads.load(Ordering::SeqCst), 0);
}
