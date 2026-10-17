//! An external qualification driver linked to the unchanged original Hepta
//! FleetRegistry and Supervisor libraries. It launches the actual Agentd bin
//! and invokes the separately built observer CLI. No protocol DTO or owner is
//! substituted. This file is built by run_original_agentd.py, not by the small
//! observer crate; formatting/source review alone is not execution evidence.

use codex_hepta_contracts::AgentId;
use codex_hepta_fleet::{AgentManifest, FleetRegistry, ResourceBudget, WorkspaceBinding};
use codex_hepta_paths::HeptaFleetRoot;
use codex_hepta_supervisor::{
    AgentCommand, AgentSupervisorSnapshot, Supervisor, SupervisorConfig, UnixProcessDriver,
};
use serde_json::{Value, json};
use std::error::Error;
use std::fs;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant};

type Result<T> = std::result::Result<T, Box<dyn Error>>;
const AGENT: &str = "22222222-2222-4222-8222-222222222222";
const READY_TIMEOUT: Duration = Duration::from_secs(60);

// These are original, documented configuration keys. The loopback endpoint
// has no mock service or responses. No model turn is submitted by this probe.
const NO_TURN_CONFIG: &str = r#"
model = "observer-no-turn"
model_provider = "observer_no_turn"
approval_policy = "never"
sandbox_mode = "read-only"

[model_providers.observer_no_turn]
name = "Observer qualification: no model requests"
base_url = "http://127.0.0.1:1/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
requires_openai_auth = false
supports_websockets = false
"#;

fn require(condition: bool, message: &str) -> Result<()> {
    if !condition {
        return Err(std::io::Error::other(message).into());
    }
    Ok(())
}

struct Probe {
    supervisor: Supervisor<UnixProcessDriver>,
    agent: AgentId,
    socket: PathBuf,
    observer: PathBuf,
    uid: u32,
}

impl Probe {
    fn new(root: &Path, agentd: PathBuf, observer: PathBuf) -> Result<Self> {
        let metadata = fs::symlink_metadata(root)?;
        require(
            root.canonicalize()? == root
                && metadata.is_dir()
                && metadata.mode() & 0o077 == 0
                && fs::read_dir(root)?.next().is_none(),
            "probe needs a new empty canonical private directory",
        )?;
        let fleet = HeptaFleetRoot::parse(root.join("fleet"))?;
        let registry = FleetRegistry::initialize(fleet.clone())?;
        let workspace = root.join("workspace");
        fs::create_dir(&workspace)?;
        let agent = AgentId::parse(AGENT).map_err(std::io::Error::other)?;
        let manifest = AgentManifest::new(
            agent.clone(),
            WorkspaceBinding::new(workspace, &fleet)?,
            ResourceBudget::local_default(),
        )?;
        let record = registry.register(manifest)?;
        fs::write(
            record.layout.home_root().join("config.toml"),
            NO_TURN_CONFIG,
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
        let mut probe = Self {
            supervisor,
            agent,
            socket: record.layout.agentd_control_socket().to_path_buf(),
            observer,
            uid: metadata.uid(),
        };
        // The original process driver assigns the registered child identity,
        // generation, workspace and home/run environment. No hand-written
        // registry transition, lease or authority grant is created here.
        probe.supervisor.start(
            &probe.agent,
            AgentCommand::new(agentd, Vec::new())?,
            Instant::now(),
        )?;
        Ok(probe)
    }

    fn snapshot(&self) -> Result<AgentSupervisorSnapshot> {
        self.supervisor
            .snapshot(&self.agent)
            .ok_or_else(|| std::io::Error::other("original supervisor snapshot missing").into())
    }

    fn tick(&mut self) -> Result<()> {
        require(
            self.supervisor.tick(Instant::now()).faults.is_empty(),
            "original supervisor tick fault",
        )
    }

    fn read(&self, spawn: u64, run_id: Option<&str>) -> Result<Value> {
        let mut command = Command::new(&self.observer);
        command
            .arg(&self.socket)
            .arg(AGENT)
            .arg(spawn.to_string())
            .arg(self.uid.to_string());
        if let Some(run) = run_id {
            command.arg(run);
        }
        // The facade has its five-second I/O deadline; the outer Python
        // harness also bounds and terminates this entire private process group.
        let output = command.output()?;
        require(
            output.stdout.len() <= 65_536 && output.stderr.len() <= 1_024,
            "observer diagnostic output exceeded bound",
        )?;
        require(
            output.status.success(),
            "observer rejected this original daemon cut",
        )?;
        Ok(serde_json::from_slice(&output.stdout)?)
    }

    fn checked_phase(&self, spawn: u64, phase: &str, offset: u64) -> Result<Value> {
        let observed = self.read(spawn, None)?;
        let snapshot = self.snapshot()?;
        require(
            observed["agent_id"] == AGENT
                && observed["spawn_generation"].as_u64() == Some(spawn)
                && observed["current_generation"].as_u64() == spawn.checked_add(offset)
                && observed["health"]["lifecycle"] == phase
                && observed["health"]["process_id"].as_u64() == snapshot.process_system_id
                && observed["health"]["fenced"] == false
                && observed["health"]["ready"] == (phase == "running"),
            "observer phase/PID disagrees with original supervisor",
        )?;
        let capabilities = observed["capabilities"]
            .as_array()
            .ok_or("capability projection missing")?;
        require(
            capabilities.iter().all(|entry| {
                !matches!(
                    entry["id"].as_str(),
                    Some(
                        "objective.start"
                            | "automation.external_effect"
                            | "intelligence.canonical_v1"
                    )
                )
            }),
            "unexpected production objective/effect provider in no-authority profile",
        )?;
        let events = observed["events"]
            .as_array()
            .ok_or("event projection missing")?;
        require(
            events.iter().any(|event| {
                event["lifecycle"] == "starting" && event["generation"].as_u64() == Some(spawn)
            }),
            "original process-local starting history missing",
        )?;
        println!(
            "{}",
            json!({"event":"phase_observed", "observation":observed})
        );
        Ok(observed)
    }

    fn wait_starting(&self, spawn: u64) -> Result<Value> {
        // Without a supervisor tick, only its original health-probe thread
        // runs; the original owner has not yet promoted Starting to Running.
        let deadline = Instant::now() + READY_TIMEOUT;
        loop {
            if let Ok(observed) = self.checked_phase(spawn, "starting", 0) {
                return Ok(observed);
            }
            require(
                Instant::now() < deadline,
                "original Starting readiness timed out",
            )?;
            thread::sleep(Duration::from_millis(100));
        }
    }

    fn wait_running(&mut self, previous_spawn: Option<u64>) -> Result<(u64, Value)> {
        let deadline = Instant::now() + READY_TIMEOUT;
        loop {
            self.tick()?;
            let snapshot = self.snapshot()?;
            if let Some(spawn) = snapshot.spawn_generation
                && previous_spawn.is_none_or(|previous| spawn > previous)
                && snapshot.healthy
                && let Ok(observed) = self.checked_phase(spawn, "running", 1)
            {
                return Ok((spawn, observed));
            }
            require(
                Instant::now() < deadline,
                "original Running readiness timed out",
            )?;
            thread::sleep(Duration::from_millis(100));
        }
    }

    fn stop_and_confirm(&mut self) -> Result<()> {
        self.supervisor.stop(&self.agent, Instant::now())?;
        let deadline = Instant::now() + Duration::from_secs(5);
        while self.snapshot()?.active {
            self.tick()?;
            require(Instant::now() < deadline, "original process did not stop")?;
            thread::sleep(Duration::from_millis(25));
        }
        Ok(())
    }
}

impl Drop for Probe {
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

fn run() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    require(
        args.len() == 4,
        "usage: probe agentd-bin observer-bin private-root hold-seconds",
    )?;
    let hold: u64 = args[3].to_string_lossy().parse()?;
    require(hold <= 30, "hold is bounded to 30 seconds")?;
    let mut probe = Probe::new(
        Path::new(&args[2]),
        PathBuf::from(&args[0]),
        PathBuf::from(&args[1]),
    )?;
    let spawn = probe
        .snapshot()?
        .spawn_generation
        .ok_or("original spawn missing")?;
    println!(
        "{}",
        json!({"event":"trusted_endpoint", "evidence_class":"original_agentd_probe_in_progress_not_pass",
        "socket_path":probe.socket, "agent_id":AGENT,"spawn_generation":spawn,"peer_uid":probe.uid})
    );
    let starting = probe.wait_starting(spawn)?;
    let (running_spawn, running) = probe.wait_running(None)?;
    require(
        running_spawn == spawn,
        "unexpected replacement during first startup",
    )?;
    require(
        starting["health"]["process_id"] == running["health"]["process_id"],
        "PID changed during promotion",
    )?;
    require(
        probe
            .read(spawn, Some("observer-qualification:absent"))?
            .is_null(),
        "fresh owner unexpectedly contains a run",
    )?;
    println!("{}", json!({"event":"ready_window", "hold_seconds":hold}));
    let until = Instant::now() + Duration::from_secs(hold);
    while Instant::now() < until {
        probe.tick()?;
        thread::sleep(Duration::from_millis(100));
    }
    // Actual owner transition + actual Agentd Drain RPC; do not tick it to
    // completion until the read-only observer has sampled the Draining phase.
    probe.supervisor.drain(&probe.agent, Instant::now())?;
    let draining = probe.checked_phase(spawn, "draining", 2)?;
    require(
        draining["health"]["process_id"] == running["health"]["process_id"],
        "PID changed during drain",
    )?;
    probe.supervisor.restart(&probe.agent, Instant::now())?;
    let (new_spawn, restarted) = probe.wait_running(Some(spawn))?;
    require(
        restarted["health"]["process_id"] != running["health"]["process_id"],
        "restart did not replace process",
    )?;
    require(
        probe.read(spawn, None).is_err(),
        "old spawn was accepted by replacement process",
    )?;
    probe.checked_phase(new_spawn, "running", 1)?;
    probe.stop_and_confirm()?;
    require(
        probe.read(new_spawn, None).is_err(),
        "stopped daemon still produced a successful observation",
    )?;
    println!(
        "{}",
        json!({"event":"acceptance_pass", "evidence_class":"original_agentd_process_readonly_observer",
        "old_spawn":spawn,"new_spawn":new_spawn,"checks":["original_starting","original_running","bounded_capabilities_events",
        "missing_run_read","same_process_draining","original_restart","old_spawn_rejected","controlled_stop"],
        "objective_submission":false,"model_turn":false,"device_effect":false})
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("original-agentd-probe failed: {error}");
        std::process::exit(1);
    }
}
