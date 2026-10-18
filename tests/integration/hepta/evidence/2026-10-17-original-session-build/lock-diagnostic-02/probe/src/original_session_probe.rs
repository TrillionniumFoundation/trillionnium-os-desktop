//! Optional real Session/ctl consumer of the original owner's endpoint.
//! This module neither speaks Agentd RPC nor changes the original lifecycle.

use super::{AGENT, Probe, Result, require};
use serde_json::{Value, json};
use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const SAMPLE_TIMEOUT: Duration = Duration::from_secs(20);
const FRESH_MS: u64 = 7_000;
pub const CHECKS: [&str; 8] = [
    "persistent_session_starting",
    "persistent_session_running",
    "persistent_session_draining",
    "same_worker_same_instance",
    "old_spawn_stale_ipc_responsive",
    "explicit_session_replacement",
    "replacement_running",
    "stopped_stale_ipc_responsive",
];

fn unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .min(u128::from(u64::MAX)) as u64
}

pub struct Options {
    session: PathBuf,
    ctl: PathBuf,
    phases: Option<PathBuf>,
    ack_seconds: u64,
}

impl Options {
    pub fn read(args: &[OsString]) -> Result<Option<Self>> {
        if args.is_empty() {
            return Ok(None);
        }
        require(
            args.len() % 2 == 0,
            "Session options require name/value pairs",
        )?;
        let mut session = None;
        let mut ctl = None;
        let mut phases = None;
        let mut ack_seconds = None;
        for pair in args.chunks_exact(2) {
            let slot = match pair[0].to_str() {
                Some("--session-bin") => &mut session,
                Some("--ctl-bin") => &mut ctl,
                Some("--session-phase-dir") => &mut phases,
                Some("--session-ack-seconds") => &mut ack_seconds,
                _ => return Err("unknown Session probe option".into()),
            };
            require(
                slot.replace(pair[1].clone()).is_none(),
                "duplicate Session option",
            )?;
        }
        let session = PathBuf::from(session.ok_or("--session-bin required")?);
        let ctl = PathBuf::from(ctl.ok_or("--ctl-bin required")?);
        for path in [&session, &ctl] {
            let metadata = fs::symlink_metadata(path)?;
            require(
                path.is_absolute()
                    && path.canonicalize()? == *path
                    && metadata.is_file()
                    && metadata.mode() & 0o111 != 0,
                "Session/ctl must name canonical executable files",
            )?;
        }
        let ack_seconds = ack_seconds
            .map(|value| value.to_string_lossy().parse::<u64>())
            .transpose()?
            .unwrap_or(60);
        require(
            (1..=120).contains(&ack_seconds),
            "ack deadline must be 1..120 seconds",
        )?;
        let phases = phases.map(PathBuf::from);
        if let Some(directory) = &phases {
            require(directory.is_absolute(), "phase directory must be absolute")?;
            fs::DirBuilder::new().mode(0o700).create(directory)?;
            require(
                directory.canonicalize()? == *directory,
                "phase directory must be canonical",
            )?;
        }
        Ok(Some(Self {
            session,
            ctl,
            phases,
            ack_seconds,
        }))
    }
}

/// This process's sole Child handle pins its PID until kill/wait is complete.
/// No child groups or global process matching; the outer Python guard bounds
/// the entire original probe group if a child cannot be reaped promptly.
struct OwnedSession {
    child: Option<Child>,
    instance: Option<String>,
    worker_tid: Option<u32>,
}

impl OwnedSession {
    fn live(&mut self) -> Result<u32> {
        let child = self.child.as_mut().ok_or("Session already stopped")?;
        require(
            child.try_wait()?.is_none(),
            "Session exited during qualification",
        )?;
        Ok(child.id())
    }

    fn stop(&mut self) -> Result<()> {
        if let Some(mut child) = self.child.take() {
            let pid = child.id();
            // Child::kill checks any exit already reaped by try_wait. Never
            // issue a numeric kill after giving up the owned Child handle.
            let killed = child.kill();
            let status = child.wait()?;
            killed?;
            require(
                status.signal() == Some(9),
                "owned Session stop was not confirmed",
            )?;
            println!(
                "{}",
                json!({"event":"session_stopped", "session_pid":pid,
                "session_instance":self.instance, "worker_tid":self.worker_tid,
                "exit_code":status.code(), "signal":status.signal()})
            );
        }
        Ok(())
    }
}

impl Drop for OwnedSession {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

pub struct SessionProbe {
    options: Options,
    runtime: PathBuf,
    process: OwnedSession,
    first_instance: Option<String>,
    first_pid: u32,
    sequence: u64,
    retained: Option<Value>,
}

impl SessionProbe {
    pub fn start(options: Options, root: &Path, owner: &Probe, spawn: u64) -> Result<Self> {
        let runtime = root.join("ui-runtime");
        fs::DirBuilder::new().mode(0o700).create(&runtime)?;
        let process = Self::launch(&options, &runtime, owner, spawn, 1)?;
        let first_pid = process.child.as_ref().ok_or("Session child missing")?.id();
        Ok(Self {
            options,
            runtime,
            process,
            first_instance: None,
            first_pid,
            sequence: 0,
            retained: None,
        })
    }

    fn launch(
        options: &Options,
        runtime: &Path,
        owner: &Probe,
        spawn: u64,
        ordinal: u64,
    ) -> Result<OwnedSession> {
        let log = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(runtime.join(format!("session-{ordinal}.log")))?;
        let child = Command::new(&options.session)
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .env("LANG", "C.UTF-8")
            .env("XDG_RUNTIME_DIR", runtime)
            .env("TRILL_HEPTA_AGENTD_SOCKET", &owner.socket)
            .env("TRILL_HEPTA_AGENT_ID", AGENT)
            .env("TRILL_HEPTA_SPAWN_GENERATION", spawn.to_string())
            .env("TRILL_HEPTA_PEER_UID", owner.uid.to_string())
            .stdin(Stdio::null())
            .stdout(log.try_clone()?)
            .stderr(log)
            .spawn()?;
        Ok(OwnedSession {
            child: Some(child),
            instance: None,
            worker_tid: None,
        })
    }

    fn snapshot(&mut self) -> Result<Value> {
        let pid = self.process.live()?;
        let started = Instant::now();
        // Invoke the production client. Its existing IPC has fixed read/write
        // deadlines; the outer probe deadline also bounds this child group.
        let output = Command::new(&self.options.ctl)
            .arg("snapshot")
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .env("LANG", "C.UTF-8")
            .env("XDG_RUNTIME_DIR", &self.runtime)
            .stdin(Stdio::null())
            .output()?;
        require(output.status.success(), "actual trill-ctl snapshot failed")?;
        require(
            output.stdout.len() <= 262_144 && output.stderr.len() <= 4_096,
            "Session diagnostic output exceeded bound",
        )?;
        require(
            started.elapsed() < Duration::from_secs(3),
            "Session IPC was not responsive",
        )?;
        let snapshot: Value = serde_json::from_slice(&output.stdout)?;
        require(
            snapshot["type"] == "snapshot",
            "Session response is not a snapshot",
        )?;
        require(
            snapshot["tasks"].as_array().is_some_and(Vec::is_empty),
            "read-only Session qualification unexpectedly created a host task",
        )?;
        let instance = snapshot["session_instance"]
            .as_str()
            .ok_or("Session identity missing")?;
        require(
            instance.len() == 32 && instance.bytes().all(|c| c.is_ascii_hexdigit()),
            "Session identity is malformed",
        )?;
        if let Some(expected) = &self.process.instance {
            require(
                instance == expected,
                "Session instance changed without explicit replacement",
            )?;
        } else {
            self.process.instance = Some(instance.into());
        }
        let threads = fs::read_dir(format!("/proc/{pid}/task"))?
            .filter_map(|entry| entry.ok())
            .filter_map(|entry| {
                (fs::read_to_string(entry.path().join("comm")).ok()?.trim() == "hepta-read-only")
                    .then(|| entry.file_name().to_string_lossy().parse::<u32>().ok())
                    .flatten()
            })
            .collect::<Vec<_>>();
        require(
            threads.len() == 1,
            "one real persistent Session observer thread required",
        )?;
        if let Some(expected) = self.process.worker_tid {
            require(threads[0] == expected, "Session observer worker changed")?;
        } else {
            self.process.worker_tid = Some(threads[0]);
        }
        self.process.live()?;
        Ok(snapshot)
    }

    /// Wait for an actual qualifying IPC sample. Time merely bounds retries;
    /// it never substitutes for the lifecycle/freshness/identity predicates.
    fn wait_snapshot(&mut self, predicate: impl Fn(&Value) -> bool) -> Result<Value> {
        let deadline = Instant::now() + SAMPLE_TIMEOUT;
        loop {
            self.process.live()?;
            if let Ok(snapshot) = self.snapshot() {
                if predicate(&snapshot) {
                    return Ok(snapshot);
                }
            }
            require(
                Instant::now() < deadline,
                "Session phase observation timed out",
            )?;
            thread::sleep(Duration::from_millis(100));
        }
    }

    pub fn observed(
        &mut self,
        owner: &Probe,
        spawn: u64,
        phase: &str,
        offset: u64,
        name: &str,
    ) -> Result<()> {
        let pid = owner
            .snapshot()?
            .process_system_id
            .ok_or("original PID missing")?;
        let cut = unix_ms();
        let snapshot = self.wait_snapshot(|value| {
            observed_matches(value, spawn, pid, phase, offset, cut, unix_ms())
        })?;
        if self.first_instance.is_none() {
            self.first_instance = self.process.instance.clone();
        }
        self.retained = Some(snapshot["hepta"]["last_observation"].clone());
        self.phase(owner, name, snapshot, Value::Null)
    }

    pub fn stale(&mut self, owner: &Probe, name: &str) -> Result<()> {
        let retained = self
            .retained
            .clone()
            .ok_or("stale phase needs a prior observation")?;
        let cut = unix_ms();
        let first = self.wait_snapshot(|value| {
            stale_matches(value, &retained, cut, unix_ms())
                && if name == "old_spawn_stale" {
                    matches!(
                        value["hepta"]["error_code"].as_str(),
                        Some("protocol_mismatch" | "generation_fenced" | "owner_rejected")
                    )
                } else {
                    value["hepta"]["error_code"] == "unavailable"
                }
        })?;
        let first_attempt = first["hepta"]["last_attempt_unix_ms"]
            .as_u64()
            .ok_or("first stale attempt timestamp missing")?;
        let snapshot = self.wait_snapshot(|value| {
            stale_matches(value, &first["hepta"]["last_observation"], cut, unix_ms())
                && value["hepta"]["last_observation"] == first["hepta"]["last_observation"]
                && value["hepta"]["error_code"] == first["hepta"]["error_code"]
                && value["hepta"]["last_attempt_unix_ms"]
                    .as_u64()
                    .is_some_and(|attempt| attempt > first_attempt)
        })?;
        self.phase(
            owner,
            name,
            snapshot,
            json!({"first_stale_snapshot":first,
            "preceding_live_observation":retained,
            "later_failure_preserves_exact_last_observation":true}),
        )
    }

    fn phase(
        &mut self,
        owner: &Probe,
        name: &str,
        snapshot: Value,
        stale_verification: Value,
    ) -> Result<()> {
        self.sequence += 1;
        let actual = owner.snapshot()?;
        let ack = json!({"sequence":self.sequence, "phase":name,
            "session_instance":self.process.instance});
        let record = json!({"event":"session_phase_observed", "sequence":self.sequence,
            "phase":name, "session_pid":self.process.live()?, "session_instance":self.process.instance,
            "worker_tid":self.process.worker_tid, "runtime_dir":self.runtime,
            "session_socket_path":self.runtime.join("trillionnium-ui/session.sock"),
            "recorded_unix_ms":unix_ms(), "snapshot":snapshot, "stale_verification":stale_verification,
            "original":{"agent_id":AGENT, "spawn_generation":actual.spawn_generation,
                "process_id":actual.process_system_id, "active":actual.active, "healthy":actual.healthy},
            "ack":ack, "ack_timeout_seconds":self.options.ack_seconds,
            "capture_ack_is_coordination_only":true});
        println!("{record}");
        if let Some(directory) = &self.options.phases {
            write_json_new(directory, &format!("phase-{}", self.sequence), &record)?;
            let path = directory.join(format!("ack-{}.json", self.sequence));
            let deadline = Instant::now() + Duration::from_secs(self.options.ack_seconds);
            loop {
                self.process.live()?;
                if let Ok(metadata) = fs::symlink_metadata(&path) {
                    require(
                        metadata.is_file()
                            && metadata.uid() == owner.uid
                            && metadata.mode() & 0o777 == 0o600
                            && metadata.nlink() == 1
                            && metadata.len() <= 1_024,
                        "phase acknowledgment must be a bounded private regular file",
                    )?;
                    let file = File::open(&path)?;
                    let opened = file.metadata()?;
                    require(
                        metadata.dev() == opened.dev() && metadata.ino() == opened.ino(),
                        "phase acknowledgment identity changed",
                    )?;
                    let mut bytes = Vec::new();
                    file.take(1_025).read_to_end(&mut bytes)?;
                    require(bytes.len() <= 1_024, "phase acknowledgment exceeded bound")?;
                    let received: Value = serde_json::from_slice(&bytes)?;
                    require(
                        received == ack,
                        "phase acknowledgment does not match current cut",
                    )?;
                    println!(
                        "{}",
                        json!({"event":"session_phase_acknowledged", "ack":ack,
                        "capture_ack_is_coordination_only":true})
                    );
                    break;
                }
                require(
                    Instant::now() < deadline,
                    "Session phase acknowledgment timed out",
                )?;
                thread::sleep(Duration::from_millis(100));
            }
        }
        Ok(())
    }

    pub fn replace(&mut self, owner: &Probe, spawn: u64) -> Result<()> {
        require(
            self.sequence == 4,
            "replacement requires all first-Session phases",
        )?;
        self.process.stop()?;
        // Keep the runtime directory inode: a continuously running Shell can
        // reconnect through the production Session stale-socket recovery.
        self.process = Self::launch(&self.options, &self.runtime, owner, spawn, 2)?;
        self.retained = None;
        Ok(())
    }

    pub fn finish(&mut self) -> Result<Value> {
        require(
            self.sequence == 6 && self.process.instance != self.first_instance,
            "replacement Session identity and all six phases required",
        )?;
        let second_pid = self.process.live()?;
        let second_instance = self.process.instance.clone();
        self.process.stop()?;
        Ok(json!({"event":"session_acceptance_pass",
            "evidence_class":"original_agentd_persistent_session_readonly",
            "checks":CHECKS, "first_session_pid":self.first_pid,
            "first_session_instance":self.first_instance, "replacement_session_pid":second_pid,
            "replacement_session_instance":second_instance,
            "objective_submission":false, "model_turn":false, "device_effect":false,
            "shell_capture_qualified_by_this_record":false}))
    }
}

fn fresh_timestamp(value: &Value, cut: u64, now: u64) -> bool {
    value
        .as_u64()
        .is_some_and(|sample| sample >= cut && sample <= now && now - sample <= FRESH_MS)
}

fn observed_matches(
    value: &Value,
    spawn: u64,
    pid: u64,
    phase: &str,
    offset: u64,
    cut: u64,
    now: u64,
) -> bool {
    let view = &value["hepta"];
    let last = &view["last_observation"];
    view["connection"] == "observed"
        && view["error_code"].is_null()
        && fresh_timestamp(&view["last_attempt_unix_ms"], cut, now)
        && fresh_timestamp(&last["sampled_unix_ms"], cut, now)
        && last["agent_id"] == AGENT
        && last["spawn_generation"].as_u64() == Some(spawn)
        && last["current_generation"].as_u64() == spawn.checked_add(offset)
        && last["health"]["process_id"].as_u64() == Some(pid)
        && last["health"]["lifecycle"] == phase
        && last["health"]["fenced"] == false
        && last["health"]["ready"] == (phase == "running")
        && last["history_gap"] == false
        && last["source_changed"] == false
        && last["events"].as_array().is_some_and(|events| {
            !events.is_empty()
                && events.len() <= 16
                && events.iter().any(|event| {
                    event["lifecycle"] == phase
                        && event["generation"].as_u64() == spawn.checked_add(offset)
                })
        })
}

fn stale_matches(value: &Value, retained: &Value, cut: u64, now: u64) -> bool {
    let view = &value["hepta"];
    // Original restart drains an already-draining process again; stop may
    // legally publish Draining after our Running screenshot. A final success
    // can therefore add old-spawn events or advance its lifecycle. First pin
    // that actual historical cut, then stale() requires exact retention over
    // a later failed worker poll. Never assume the pre-capture cut is final.
    let last = &view["last_observation"];
    view["connection"] == "stale"
        && fresh_timestamp(&view["last_attempt_unix_ms"], cut, now)
        && matches!(
            view["error_code"].as_str(),
            Some(
                "protocol_mismatch"
                    | "generation_fenced"
                    | "owner_rejected"
                    | "unavailable"
                    | "peer_denied"
            )
        )
        && last["agent_id"] == retained["agent_id"]
        && last["spawn_generation"] == retained["spawn_generation"]
        && last["health"]["process_id"] == retained["health"]["process_id"]
        && last["health"]["fenced"] == false
        && last["current_generation"]
            .as_u64()
            .zip(last["spawn_generation"].as_u64())
            .is_some_and(|(current, spawn)| match current.checked_sub(spawn) {
                Some(0) => {
                    last["health"]["lifecycle"] == "starting" && last["health"]["ready"] == false
                }
                Some(1) => {
                    last["health"]["lifecycle"] == "running" && last["health"]["ready"] == true
                }
                Some(2) => {
                    last["health"]["lifecycle"] == "draining" && last["health"]["ready"] == false
                }
                _ => false,
            })
        && [
            "current_generation",
            "sampled_unix_ms",
            "next_cursor",
            "latest_cursor",
        ]
        .iter()
        .all(|key| {
            last[key]
                .as_u64()
                .zip(retained[key].as_u64())
                .is_some_and(|(next, old)| next >= old)
        })
        && last["events"]
            .as_array()
            .zip(retained["events"].as_array())
            .is_some_and(|(next, old)| next.len() <= 16 && next.starts_with(old))
        && last["capabilities"] == retained["capabilities"]
        && last["sampled_unix_ms"]
            .as_u64()
            .zip(view["last_attempt_unix_ms"].as_u64())
            .is_some_and(|(sample, attempt)| sample <= attempt)
        && last["history_gap"] == false
        && last["source_changed"] == false
}

fn write_json_new(directory: &Path, name: &str, value: &Value) -> Result<()> {
    let temporary = directory.join(format!("{name}.tmp"));
    let target = directory.join(format!("{name}.json"));
    require(!target.try_exists()?, "phase record already exists")?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&temporary)?;
    writeln!(file, "{value}")?;
    file.sync_all()?;
    fs::rename(temporary, target)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn live_cut() -> Value {
        json!({"sampled_unix_ms":10, "agent_id":AGENT, "spawn_generation":1,
            "current_generation":2, "health":{"process_id":123,"lifecycle":"running",
                "ready":true,"promotion_ready":true,"fenced":false},
            "capabilities":[], "events":[{"cursor":1,"lifecycle":"starting","generation":1},
                {"cursor":2,"lifecycle":"running","generation":2}],
            "next_cursor":2, "latest_cursor":2, "history_gap":false,"source_changed":false})
    }

    #[test]
    fn actual_stop_can_publish_draining_after_the_last_live_capture() {
        let before = live_cut();
        let mut final_success = before.clone();
        final_success["sampled_unix_ms"] = json!(22);
        final_success["current_generation"] = json!(3);
        final_success["health"]["lifecycle"] = json!("draining");
        final_success["health"]["ready"] = json!(false);
        final_success["events"]
            .as_array_mut()
            .unwrap()
            .push(json!({"cursor":3,"lifecycle":"draining","generation":3}));
        final_success["next_cursor"] = json!(3);
        final_success["latest_cursor"] = json!(3);
        let first = json!({"hepta":{"connection":"stale","error_code":"unavailable",
            "last_attempt_unix_ms":30,"last_observation":final_success}});
        assert!(stale_matches(&first, &before, 20, 31));
        let mut later = first.clone();
        later["hepta"]["last_attempt_unix_ms"] = json!(40);
        assert!(stale_matches(
            &later,
            &first["hepta"]["last_observation"],
            20,
            41
        ));
        assert_eq!(
            later["hepta"]["last_observation"],
            first["hepta"]["last_observation"]
        );
    }

    #[test]
    fn stale_cut_cannot_rebind_spawn_erase_history_or_claim_fresh_success() {
        let before = live_cut();
        let valid = json!({"hepta":{"connection":"stale","error_code":"protocol_mismatch",
            "last_attempt_unix_ms":30,"last_observation":before}});
        assert!(stale_matches(&valid, &before, 20, 31));
        for replacement in [
            json!({"spawn_generation":5}),
            json!({"events":[]}),
            json!({"sampled_unix_ms":100}),
            json!({"current_generation":1}),
        ] {
            let mut invalid = valid.clone();
            for (key, value) in replacement.as_object().unwrap() {
                invalid["hepta"]["last_observation"][key] = value.clone();
            }
            assert!(!stale_matches(&invalid, &before, 20, 31));
        }
        let mut invalid = valid;
        invalid["hepta"]["connection"] = json!("observed");
        assert!(!stale_matches(&invalid, &before, 20, 31));
    }
}
