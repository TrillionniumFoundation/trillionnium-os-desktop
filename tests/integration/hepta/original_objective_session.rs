//! Optional real Session/ctl consumer of one known, already published run.
//! Only the original owner admits work. This module performs read-only IPC.

use crate::original_objective_owner::{Owner, write_private};
use crate::{AGENT, Result, require};
use serde_json::{Value, json};
use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::Read;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const TIMEOUT: Duration = Duration::from_secs(20);
const FRESH_MS: u64 = 7_000;
const RUN_FIELDS: [&str; 7] = [
    "run_id",
    "revision",
    "phase",
    "authority_epoch",
    "generation",
    "terminal_observed",
    "idempotent",
];

fn now_ms() -> u64 {
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
                _ => return Err("unknown Objective Session option".into()),
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
            "Session ack deadline must be 1..120 seconds",
        )?;
        let phases = phases.map(PathBuf::from);
        if let Some(directory) = &phases {
            require(
                directory.is_absolute(),
                "Session phase directory must be absolute",
            )?;
            fs::DirBuilder::new().mode(0o700).create(directory)?;
            require(
                directory.canonicalize()? == *directory,
                "Session phase directory must be canonical",
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
            "Session exited during objective qualification",
        )?;
        Ok(child.id())
    }

    fn stop(&mut self) -> Result<()> {
        if let Some(mut child) = self.child.take() {
            let pid = child.id();
            // The owned Child handle pins the process identity through wait.
            let killed = child.kill();
            let status = child.wait()?;
            killed?;
            require(
                status.signal() == Some(9),
                "Session controlled stop was not confirmed",
            )?;
            println!(
                "{}",
                json!({"event":"objective_session_stopped","session_pid":pid,
                "session_instance":self.instance,"worker_tid":self.worker_tid,
                "signal":status.signal(),"exit_code":status.code()})
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
    run_id: String,
    expected_run: Option<Value>,
    sequence: u64,
}

impl SessionProbe {
    pub fn start(
        options: Options,
        root: &Path,
        owner: &Owner,
        spawn: u64,
        run_id: &str,
    ) -> Result<Self> {
        let runtime = root.join("objective-ui");
        fs::DirBuilder::new().mode(0o700).create(&runtime)?;
        let process = Self::launch(&options, &runtime, owner, spawn, run_id, 1)?;
        Ok(Self {
            options,
            runtime,
            process,
            run_id: run_id.to_string(),
            expected_run: None,
            sequence: 0,
        })
    }

    fn launch(
        options: &Options,
        runtime: &Path,
        owner: &Owner,
        spawn: u64,
        run_id: &str,
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
            .env("TRILL_HEPTA_RUN_ID", run_id)
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
        let output = Command::new(&self.options.ctl)
            .arg("snapshot")
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .env("LANG", "C.UTF-8")
            .env("XDG_RUNTIME_DIR", &self.runtime)
            .stdin(Stdio::null())
            .output()?;
        require(
            output.status.success()
                && output.stdout.len() <= 262_144
                && output.stderr.len() <= 4_096
                && started.elapsed() < Duration::from_secs(3),
            "actual Session snapshot IPC failed or exceeded bounds",
        )?;
        let value: Value = serde_json::from_slice(&output.stdout)?;
        require(
            value["type"] == "snapshot" && value["tasks"].as_array().is_some_and(Vec::is_empty),
            "Session projection created an unexpected host task",
        )?;
        let instance = value["session_instance"]
            .as_str()
            .ok_or("Session identity missing")?;
        require(
            instance.len() == 32 && instance.bytes().all(|byte| byte.is_ascii_hexdigit()),
            "Session identity is malformed",
        )?;
        if let Some(expected) = &self.process.instance {
            require(
                instance == expected,
                "Session instance changed without replacement",
            )?;
        } else {
            self.process.instance = Some(instance.to_owned());
        }
        let tids: Vec<_> = fs::read_dir(format!("/proc/{pid}/task"))?
            .filter_map(|entry| entry.ok())
            .filter_map(|entry| {
                (fs::read_to_string(entry.path().join("comm")).ok()?.trim() == "hepta-read-only")
                    .then(|| entry.file_name().to_string_lossy().parse::<u32>().ok())
                    .flatten()
            })
            .collect();
        require(
            tids.len() == 1,
            "one persistent Session observer worker required",
        )?;
        if let Some(expected) = self.process.worker_tid {
            require(tids[0] == expected, "Session observer worker changed")?;
        } else {
            self.process.worker_tid = Some(tids[0]);
        }
        self.process.live()?;
        Ok(value)
    }

    fn wait(&mut self, predicate: impl Fn(&Value) -> bool) -> Result<Value> {
        let deadline = Instant::now() + TIMEOUT;
        loop {
            self.process.live()?;
            if let Ok(value) = self.snapshot()
                && predicate(&value)
            {
                return Ok(value);
            }
            require(
                Instant::now() < deadline,
                "Session objective observation timed out",
            )?;
            thread::sleep(Duration::from_millis(100));
        }
    }

    pub fn observed(&mut self, owner: &Owner, spawn: u64) -> Result<()> {
        let expected = owner.read(spawn, Some(&self.run_id))?;
        require(
            expected["run_id"] == self.run_id
                && expected["phase"] == "admitted"
                && expected["terminal_observed"] == false,
            "original known run changed before Session observation",
        )?;
        let cut = now_ms();
        let pid = owner
            .snapshot()?
            .process_system_id
            .ok_or("original owner PID absent")?;
        let snapshot = self.wait(|value| {
            let run = &value["hepta"]["run"];
            health_matches(value, spawn, pid)
                && value["hepta"]["last_observation"]["current_generation"]
                    == expected["generation"]
                && run["connection"] == "observed"
                && run["error_code"].is_null()
                && run["run_id"] == expected["run_id"]
                && run_fields_match(&run["last_observation"], &expected)
                && fresh(&run["last_observation"]["sampled_unix_ms"], cut)
                && run["last_observation"]["observation_sequence"]
                    .as_u64()
                    .is_some_and(|n| n > 0)
                && fresh(&value["hepta"]["last_attempt_unix_ms"], cut)
                && fresh(&run["last_attempt_unix_ms"], cut)
                && run["observation_gap"] == false
        })?;
        self.expected_run = Some(expected.clone());
        self.phase(
            owner,
            "compiled_run_projected",
            snapshot,
            json!({"original_run":expected}),
        )
    }

    pub fn stale(&mut self, owner: &Owner) -> Result<()> {
        let expected = self
            .expected_run
            .clone()
            .ok_or("prior Session run observation required")?;
        let cut = now_ms();
        let first = self.wait(|value| {
            let run = &value["hepta"]["run"];
            run["connection"] == "stale"
                && run["observation_gap"] == true
                && run_fields_match(&run["last_observation"], &expected)
                && fresh(&value["hepta"]["last_attempt_unix_ms"], cut)
                && matches!(
                    run["error_code"].as_str(),
                    Some("protocol_mismatch" | "generation_fenced" | "owner_rejected")
                )
        })?;
        let retained = first["hepta"]["run"]["last_observation"].clone();
        let attempt = first["hepta"]["last_attempt_unix_ms"]
            .as_u64()
            .ok_or("stale attempt missing")?;
        let snapshot = self.wait(|value| {
            let run = &value["hepta"]["run"];
            run["connection"] == "stale"
                && run["observation_gap"] == true
                && run["last_observation"] == retained
                && run["last_attempt_unix_ms"] == first["hepta"]["run"]["last_attempt_unix_ms"]
                && run["error_code"] == first["hepta"]["run"]["error_code"]
                && value["hepta"]["last_attempt_unix_ms"]
                    .as_u64()
                    .is_some_and(|n| n > attempt)
        })?;
        self.phase(owner, "old_endpoint_run_stale", snapshot,
            json!({"first_stale_snapshot":first,"retained_run_unchanged_across_failed_samples":true}))
    }

    pub fn replace_missing(&mut self, owner: &Owner, spawn: u64) -> Result<()> {
        let previous_instance = self.process.instance.clone();
        self.process.stop()?;
        self.process = Self::launch(&self.options, &self.runtime, owner, spawn, &self.run_id, 2)?;
        let pid = owner
            .snapshot()?
            .process_system_id
            .ok_or("replacement original PID absent")?;
        let cut = now_ms();
        let run_id = self.run_id.clone();
        let snapshot = self.wait(|value| {
            let run = &value["hepta"]["run"];
            health_matches(value, spawn, pid)
                && run["run_id"] == run_id
                && run["connection"] == "projection_missing"
                && run["error_code"] == "run_projection_missing"
                && run["last_observation"].is_null()
                && fresh(&run["last_attempt_unix_ms"], cut)
                && run["observation_gap"] == false
        })?;
        require(
            self.process.instance != previous_instance,
            "explicit replacement reused Session instance",
        )?;
        self.phase(
            owner,
            "replacement_run_projection_missing",
            snapshot,
            json!({"historical_admission_still_requires_original_journal":true,
                "missing_projection_is_not_non_admission":true}),
        )?;
        self.process.stop()
    }

    fn phase(&mut self, owner: &Owner, name: &str, snapshot: Value, evidence: Value) -> Result<()> {
        self.sequence += 1;
        let original = owner.snapshot()?;
        let ack =
            json!({"sequence":self.sequence,"phase":name,"session_instance":self.process.instance});
        let record = json!({"event":"objective_session_phase_observed","sequence":self.sequence,"phase":name,
            "session_pid":self.process.live()?,"session_instance":self.process.instance,"worker_tid":self.process.worker_tid,
            "runtime_dir":self.runtime,"session_socket_path":self.runtime.join("trillionnium-ui/session.sock"),
            "recorded_unix_ms":now_ms(),"snapshot":snapshot,"evidence":evidence,
            "original":{"agent_id":AGENT,"spawn_generation":original.spawn_generation,
                "process_id":original.process_system_id,"active":original.active,"healthy":original.healthy},
            "ack":ack,"ack_timeout_seconds":self.options.ack_seconds,"capture_ack_is_coordination_only":true});
        write_private(
            &owner
                .evidence
                .join(format!("session-phase-{}.json", self.sequence)),
            &serde_json::to_vec_pretty(&record)?,
        )?;
        println!("{record}");
        if let Some(directory) = &self.options.phases {
            write_private(
                &directory.join(format!("phase-{}.json", self.sequence)),
                &serde_json::to_vec(&record)?,
            )?;
            let path = directory.join(format!("ack-{}.json", self.sequence));
            let deadline = Instant::now() + Duration::from_secs(self.options.ack_seconds);
            loop {
                self.process.live()?;
                if let Ok(before) = fs::symlink_metadata(&path) {
                    require(
                        before.is_file()
                            && before.uid() == owner.uid
                            && before.mode() & 0o777 == 0o600
                            && before.nlink() == 1
                            && before.len() <= 1_024,
                        "phase ack must be bounded private regular file",
                    )?;
                    let file = fs::File::open(&path)?;
                    let opened = file.metadata()?;
                    require(
                        before.dev() == opened.dev() && before.ino() == opened.ino(),
                        "phase ack identity changed",
                    )?;
                    let mut bytes = Vec::new();
                    file.take(1_025).read_to_end(&mut bytes)?;
                    require(
                        bytes.len() <= 1_024 && serde_json::from_slice::<Value>(&bytes)? == ack,
                        "phase acknowledgment does not match current Session cut",
                    )?;
                    break;
                }
                require(
                    Instant::now() < deadline,
                    "Session phase capture acknowledgment timed out",
                )?;
                thread::sleep(Duration::from_millis(50));
            }
        }
        Ok(())
    }
}

fn run_fields_match(observed: &Value, expected: &Value) -> bool {
    RUN_FIELDS
        .iter()
        .all(|field| !expected[*field].is_null() && observed[*field] == expected[*field])
}

fn health_matches(value: &Value, spawn: u64, pid: u64) -> bool {
    let hepta = &value["hepta"];
    hepta["connection"] == "observed"
        && hepta["last_observation"]["agent_id"] == AGENT
        && hepta["last_observation"]["spawn_generation"] == spawn
        && hepta["last_observation"]["health"]["process_id"] == pid
        && hepta["last_observation"]["health"]["ready"] == true
        && hepta["last_observation"]["health"]["lifecycle"] == "running"
}

fn fresh(value: &Value, cut: u64) -> bool {
    let now = now_ms();
    value
        .as_u64()
        .is_some_and(|time| time >= cut && time <= now && now - time <= FRESH_MS)
}
