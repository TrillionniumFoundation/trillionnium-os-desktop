//! Real original Fleet/Supervisor ownership; all state is under one fresh root.

use codex_hepta_agent_protocol::AuthBusObjectiveIngress;
use codex_hepta_contracts::AgentId;
use codex_hepta_evidence::HeptaEvidenceStore;
use codex_hepta_fleet::{AgentManifest, FleetRegistry, ResourceBudget, WorkspaceBinding};
use codex_hepta_paths::HeptaFleetRoot;
use codex_hepta_supervisor::{
    AgentCommand, AgentSupervisorSnapshot, Supervisor, SupervisorConfig, UnixProcessDriver,
};
use codex_hepta_types::Digest32;
use codex_state::SqliteConfig;
use codex_utils_absolute_path::AbsolutePathBuf;
use ed25519_dalek::SigningKey;
use serde_json::{Value, json};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use crate::original_objective_fixture::{PROFILE, trust};
use crate::{AGENT, Result, require};

const READY_TIMEOUT: Duration = Duration::from_secs(60);
const NO_TURN_CONFIG: &str = r#"
model = "objective-no-turn"
model_provider = "objective_no_turn"
approval_policy = "never"
sandbox_mode = "read-only"
[model_providers.objective_no_turn]
name = "Objective qualification: no model requests"
base_url = "http://127.0.0.1:1/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
requires_openai_auth = false
supports_websockets = false
"#;

pub struct Owner {
    pub supervisor: Supervisor<UnixProcessDriver>,
    pub agent: AgentId,
    pub socket: PathBuf,
    pub home: PathBuf,
    pub evidence: PathBuf,
    pub trust_file: PathBuf,
    pub uid: u32,
    observer: PathBuf,
    submitter: PathBuf,
}

pub fn write_private(path: &Path, bytes: &[u8]) -> Result<()> {
    let temporary = path.with_extension("new");
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(&temporary)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    fs::rename(&temporary, path)?;
    File::open(path.parent().ok_or("private file parent missing")?)?.sync_all()?;
    Ok(())
}

impl Owner {
    pub fn new(
        root: &Path,
        agentd: PathBuf,
        observer: PathBuf,
        submitter: PathBuf,
        key: &SigningKey,
    ) -> Result<Self> {
        let meta = fs::symlink_metadata(root)?;
        require(
            root.canonicalize()? == root
                && meta.is_dir()
                && meta.mode() & 0o077 == 0
                && fs::read_dir(root)?.next().is_none(),
            "probe root must be fresh, canonical and private",
        )?;
        let fleet = HeptaFleetRoot::parse(root.join("fleet"))?;
        let registry = FleetRegistry::initialize(fleet.clone())?;
        let workspace = root.join("workspace");
        fs::create_dir(&workspace)?;
        fs::write(
            workspace.join("qualification-marker.txt"),
            b"isolated objective marker\n",
        )?;
        let agent = AgentId::parse(AGENT).map_err(std::io::Error::other)?;
        let record = registry.register(AgentManifest::new(
            agent.clone(),
            WorkspaceBinding::new(workspace, &fleet)?,
            ResourceBudget::local_default(),
        )?)?;
        let home = record.layout.home_root().to_path_buf();
        fs::set_permissions(&home, fs::Permissions::from_mode(0o700))?;
        write_private(&home.join("config.toml"), NO_TURN_CONFIG.as_bytes())?;
        let trust_file = home.join("objective-trust.json");
        write_private(&trust_file, &serde_json::to_vec(&trust(key, false))?)?;
        let profile_file = home.join("objective-profile.json");
        write_private(&profile_file, PROFILE.as_bytes())?;
        let witness = root.join("witness");
        fs::create_dir(&witness)?;
        fs::set_permissions(&witness, fs::Permissions::from_mode(0o700))?;
        let checkpoint_file = witness.join("authbus-replay.json");
        let sqlite_home = AbsolutePathBuf::from_absolute_path(&home)?;
        let runtime = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()?;
        let frontier = runtime.block_on(async {
            let store =
                HeptaEvidenceStore::open(&SqliteConfig::from_sqlite_home(sqlite_home)).await?;
            let frontier = store.authbus_replay_frontier_digest().await?;
            drop(store);
            Ok::<_, Box<dyn std::error::Error>>(frontier)
        })?;
        drop(runtime);
        write_private(
            &checkpoint_file,
            &serde_json::to_vec(&json!({
                "schema_version":1,"agent_id":AGENT,"generation":1,"digest":frontier.to_string()
            }))?,
        )?;
        let evidence = root.join("probe-evidence");
        fs::create_dir(&evidence)?;
        write_private(
            &evidence.join("initial-public-trust.json"),
            &fs::read(&trust_file)?,
        )?;
        write_private(&evidence.join("admission-profile.json"), PROFILE.as_bytes())?;
        write_private(
            &evidence.join("initial-authbus-checkpoint.json"),
            &fs::read(&checkpoint_file)?,
        )?;
        let mut config = SupervisorConfig::local_default();
        config.health_timeout = READY_TIMEOUT;
        config.drain_timeout = Duration::from_secs(2);
        config.stop_grace = Duration::from_secs(1);
        let (supervisor, recovery) = Supervisor::recover(
            registry,
            UnixProcessDriver::new(256)?,
            config,
            Instant::now(),
        )?;
        require(
            recovery.faults.is_empty(),
            "original supervisor recovery fault",
        )?;
        let mut owner = Self {
            supervisor,
            agent,
            socket: record.layout.agentd_control_socket().to_path_buf(),
            home,
            evidence,
            trust_file,
            uid: meta.uid(),
            observer,
            submitter,
        };
        owner.supervisor.start(
            &owner.agent,
            AgentCommand::new(
                agentd,
                vec![
                    "--authbus-trust-file".into(),
                    owner.trust_file.as_os_str().to_owned(),
                    "--authbus-checkpoint-file".into(),
                    checkpoint_file.as_os_str().to_owned(),
                    "--objective-profile-file".into(),
                    profile_file.as_os_str().to_owned(),
                ],
            )?,
            Instant::now(),
        )?;
        Ok(owner)
    }

    pub fn snapshot(&self) -> Result<AgentSupervisorSnapshot> {
        self.supervisor
            .snapshot(&self.agent)
            .ok_or_else(|| "original supervisor snapshot missing".into())
    }

    pub fn tick(&mut self) -> Result<()> {
        require(
            self.supervisor.tick(Instant::now()).faults.is_empty(),
            "original supervisor tick fault",
        )
    }

    pub fn read(&self, spawn: u64, run: Option<&str>) -> Result<Value> {
        let mut command = Command::new(&self.observer);
        command
            .arg(&self.socket)
            .arg(AGENT)
            .arg(spawn.to_string())
            .arg(self.uid.to_string());
        if let Some(run) = run {
            command.arg(run);
        }
        let output = command.output()?;
        require(
            output.stdout.len() <= 65_536 && output.stderr.len() <= 1_024,
            "observer output exceeded bound",
        )?;
        require(
            output.status.success(),
            "observer did not accept original daemon cut",
        )?;
        Ok(serde_json::from_slice(&output.stdout)?)
    }

    pub fn wait_running(&mut self, previous: Option<u64>) -> Result<(u64, Value)> {
        let deadline = Instant::now() + READY_TIMEOUT;
        loop {
            self.tick()?;
            let snapshot = self.snapshot()?;
            if let Some(spawn) = snapshot.spawn_generation
                && previous.is_none_or(|value| spawn > value)
                && snapshot.healthy
                && let Ok(observed) = self.read(spawn, None)
                && observed["health"]["ready"] == true
                && observed["health"]["lifecycle"] == "running"
                && observed["health"]["process_id"].as_u64() == snapshot.process_system_id
                && observed["spawn_generation"] == spawn
            {
                let capabilities = observed["capabilities"]
                    .as_array()
                    .ok_or("capabilities missing")?;
                require(
                    capabilities
                        .iter()
                        .any(|entry| entry["id"] == "objective.start"),
                    "original objective capability absent",
                )?;
                require(
                    !capabilities.iter().any(|entry| {
                        matches!(
                            entry["id"].as_str(),
                            Some("intelligence.canonical_v1" | "automation.external_effect")
                        )
                    }),
                    "unexpected effect/canonical provider",
                )?;
                println!(
                    "{}",
                    json!({"event":"owner_running","spawn_generation":spawn,"observation":observed})
                );
                return Ok((spawn, observed));
            }
            if Instant::now() >= deadline {
                eprintln!("original owner readiness failed: {snapshot:?}");
                return Err("original owner readiness timed out".into());
            }
            thread::sleep(Duration::from_millis(100));
        }
    }

    pub fn submit(
        &self,
        request: &AuthBusObjectiveIngress,
        spawn: u64,
        request_id: u64,
        label: &str,
    ) -> Result<Value> {
        let pid = self
            .snapshot()?
            .process_system_id
            .ok_or("trusted original PID missing")?;
        let input = serde_json::to_vec(request)?;
        write_private(&self.evidence.join(format!("{label}-request.json")), &input)?;
        let mut child = Command::new(&self.submitter)
            .arg(&self.socket)
            .arg(AGENT)
            .arg(spawn.to_string())
            .arg(self.uid.to_string())
            .arg(pid.to_string())
            .arg(request_id.to_string())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;
        child
            .stdin
            .take()
            .ok_or("CLI stdin missing")?
            .write_all(&input)?;
        let output = child.wait_with_output()?;
        require(
            output.stdout.len() <= 16_384 && output.stderr.len() <= 1_024,
            "submission output exceeded bound",
        )?;
        write_private(
            &self.evidence.join(format!("{label}-stdout.json")),
            &output.stdout,
        )?;
        write_private(
            &self.evidence.join(format!("{label}-stderr.log")),
            &output.stderr,
        )?;
        let value: Value = serde_json::from_slice(&output.stdout)?;
        require(value["schema_version"] == 1, "submission schema drift")?;
        let expected_identity = json!({
            "request_id":request_id,"agent_id":AGENT,"spawn_generation":spawn,
            "peer_uid":self.uid,"peer_pid":pid,"issuer_id":request.issuer_id,
            "key_epoch":request.key_epoch,"message_id":request.message_id,
            "sequence":request.sequence,"expires_at_ms":request.expires_at_ms,
            "run_id":request.body.run_id,"objective_revision":request.body.objective_revision,
            "authority_epoch":request.body.authority_epoch,
            "runtime_body_digest":request.body.runtime_body_digest,
            "preference_state_digest":request.body.preference_state_digest,
            "model_tuple_digest":request.body.model_tuple_digest,
            "prompt_registry_digest":request.body.prompt_registry_digest,
            "artifact_set_digest":request.body.artifact_set_digest,
        });
        require(
            value["identity"] == expected_identity,
            "CLI identity differs from explicit owner and original signed request",
        )?;
        println!(
            "{}",
            json!({"event":"submission_observed","label":label,"exit_code":output.status.code(),"result":value})
        );
        let expected = match value["status"].as_str() {
            Some("admitted") => 0,
            Some("not_sent") => 10,
            Some("refused_before_publication") => 11,
            Some("submit_unknown") => 12,
            Some("conflict") => 13,
            _ => return Err("unknown CLI status".into()),
        };
        require(
            output.status.code() == Some(expected),
            "CLI status/exit disagreement",
        )?;
        Ok(value)
    }

    pub fn journal_path(&self) -> PathBuf {
        self.home.join("objective-run-start-v1/journal.bin")
    }

    pub fn journal_hash(&self) -> Result<String> {
        Ok(Digest32::of_bytes(&fs::read(self.journal_path())?).to_string())
    }

    pub fn stop(&mut self) -> Result<()> {
        self.supervisor.stop(&self.agent, Instant::now())?;
        let deadline = Instant::now() + Duration::from_secs(8);
        while self.snapshot()?.active {
            self.tick()?;
            require(Instant::now() < deadline, "original owner did not stop")?;
            thread::sleep(Duration::from_millis(25));
        }
        Ok(())
    }
}

impl Drop for Owner {
    fn drop(&mut self) {
        let _ = self.supervisor.kill(&self.agent);
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline {
            self.supervisor.tick(Instant::now());
            if self
                .supervisor
                .snapshot(&self.agent)
                .is_none_or(|snapshot| !snapshot.active)
            {
                break;
            }
            thread::sleep(Duration::from_millis(25));
        }
    }
}
