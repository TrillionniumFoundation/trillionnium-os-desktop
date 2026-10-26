//! Fresh trusted Root composition of the ORIGINAL Supervisor and Unix driver.
//! The supervisor owns Registry transitions/leases/health; no JSON writer does.
use std::collections::BTreeSet;
use std::io;
use std::os::fd::AsRawFd;
use std::os::fd::BorrowedFd;
use std::os::fd::FromRawFd;
use std::os::fd::OwnedFd;
use std::time::Duration;
use std::time::Instant;

use codex_hepta_agentd::HostAuthorityRegisteredIdentity;
use codex_hepta_agentd::HostAuthorityRegistration;
use codex_hepta_contracts::AgentId;
use codex_hepta_fleet::AgentLifecycle;
use codex_hepta_fleet::FleetRegistry;
use codex_hepta_supervisor::AdoptSpec;
use codex_hepta_supervisor::Adoption;
use codex_hepta_supervisor::AgentCommand;
use codex_hepta_supervisor::ProcessDriver;
use codex_hepta_supervisor::ProcessDriverError;
use codex_hepta_supervisor::SpawnSpec;
use codex_hepta_supervisor::SpawnedProcess;
use codex_hepta_supervisor::Supervisor;
use codex_hepta_supervisor::SupervisorConfig;
use codex_hepta_supervisor::UnixManagedProcess;
use codex_hepta_supervisor::UnixProcessDriver;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cfg(test)]
#[path = "supervisor_tests.rs"]
mod tests;

/// This finite first-deployment capability delegates one spawn to the original
/// driver. An uncertain spawn consumes it. Automatic lifecycle retries cannot
/// reuse inherited FD numbers or a previous Root handoff in another process.
pub(super) struct OneOriginalSpawn {
    driver: UnixProcessDriver,
    consumed: bool,
}

impl ProcessDriver for OneOriginalSpawn {
    type Process = UnixManagedProcess;

    fn spawn(
        &mut self,
        spec: &SpawnSpec,
    ) -> std::result::Result<SpawnedProcess<Self::Process>, ProcessDriverError> {
        if self.consumed {
            return Err(ProcessDriverError::new(
                "original fresh Root spawn capability is consumed",
            ));
        }
        self.consumed = true;
        self.driver.spawn(spec)
    }

    fn adopt(
        &mut self,
        _spec: &AdoptSpec,
    ) -> std::result::Result<Adoption<Self::Process>, ProcessDriverError> {
        // Fresh deployment never adopts a serialized PID. Successor recovery
        // needs its independent original retirement/material handoff.
        Ok(Adoption::Rejected)
    }
}

pub(super) struct OriginalOwner {
    supervisor: SupervisorLease,
    pub(super) registration: HostAuthorityRegistration,
    pub(super) pidfd: OwnedFd,
}

struct SupervisorLease {
    supervisor: Supervisor<OneOriginalSpawn>,
    agent: AgentId,
}

impl Drop for SupervisorLease {
    fn drop(&mut self) {
        let _ = self.supervisor.stop(&self.agent, Instant::now());
        let until = Instant::now() + Duration::from_secs(6);
        loop {
            let report = self.supervisor.tick(Instant::now());
            for fault in report.faults {
                eprintln!("original Supervisor cleanup: {fault:?}");
            }
            if self
                .supervisor
                .snapshot(&self.agent)
                .is_none_or(|s| s.process_system_id.is_none())
            {
                return;
            }
            if Instant::now() >= until {
                break;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        // Escalation remains the original Supervisor's own kill/reap path.
        // Never signal a rediscovered numeric PID or an unrelated process.
        let _ = self.supervisor.kill(&self.agent);
        let until = Instant::now() + Duration::from_secs(2);
        while Instant::now() < until {
            self.supervisor.tick(Instant::now());
            if self
                .supervisor
                .snapshot(&self.agent)
                .is_none_or(|s| s.process_system_id.is_none())
            {
                return;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        eprintln!("original Supervisor did not acknowledge cleanup");
    }
}

pub(super) struct OriginalMonitor {
    stop: std::sync::mpsc::Sender<()>,
    worker: Option<std::thread::JoinHandle<()>>,
}

impl OriginalOwner {
    pub(super) fn monitor(self) -> (HostAuthorityRegistration, OwnedFd, OriginalMonitor) {
        let Self {
            mut supervisor,
            registration,
            pidfd,
        } = self;
        let (stop, receiver) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || {
            loop {
                let report = supervisor.supervisor.tick(Instant::now());
                for fault in report.faults {
                    eprintln!("original Supervisor: {fault:?}");
                }
                match receiver.recv_timeout(Duration::from_millis(20)) {
                    Ok(()) | Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
                    Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {}
                }
            }
            // Drop stops and reaps through the retained original owner.
        });
        (
            registration,
            pidfd,
            OriginalMonitor {
                stop,
                worker: Some(worker),
            },
        )
    }
}

impl Drop for OriginalMonitor {
    fn drop(&mut self) {
        let _ = self.stop.send(());
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

pub(super) struct InheritOnce(Vec<(i32, i32)>);

impl InheritOnce {
    pub(super) fn new(descriptors: &[BorrowedFd<'_>]) -> io::Result<Self> {
        let mut guard = Self(Vec::new());
        let mut seen = BTreeSet::new();
        for descriptor in descriptors {
            let fd = descriptor.as_raw_fd();
            if fd < 3 || !seen.insert(fd) {
                return Err(io::Error::other(
                    "one distinct original inherited right per slot is required",
                ));
            }
            // SAFETY: the caller retains every borrowed descriptor. Only the
            // close-on-exec bit changes during this single original spawn.
            let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
            if flags < 0 || flags & libc::FD_CLOEXEC == 0 {
                return Err(io::Error::other("original rights must begin close-on-exec"));
            }
            guard.0.push((fd, flags));
            if unsafe { libc::fcntl(fd, libc::F_SETFD, flags & !libc::FD_CLOEXEC) } < 0 {
                return Err(io::Error::last_os_error());
            }
        }
        Ok(guard)
    }
}

impl Drop for InheritOnce {
    fn drop(&mut self) {
        for (fd, flags) in &self.0 {
            // SAFETY: every borrowed descriptor outlives this guard. Restore
            // the exact flags after the original driver has forked/executed.
            let _ = unsafe { libc::fcntl(*fd, libc::F_SETFD, *flags) };
        }
    }
}

pub(super) fn start_original(
    registry: FleetRegistry,
    agent: &AgentId,
    command: AgentCommand,
    rights: &[BorrowedFd<'_>],
    uid: u32,
    gid: u32,
) -> Result<OriginalOwner> {
    // SAFETY: these calls only read actual process credentials.
    if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 || uid == 0 || gid == 0 {
        return Err("explicit Root and actual non-Root product owner are required".into());
    }
    let before = registry.load_agent(agent)?;
    if registry.load()?.agents.len() != 1 || before.lifecycle.generation != 0 {
        return Err("fresh original Supervisor entry refuses existing lifecycle history".into());
    }
    let driver = OneOriginalSpawn {
        driver: UnixProcessDriver::new(256)?,
        consumed: false,
    };
    let (supervisor, recovery) = Supervisor::recover(
        registry.clone(),
        driver,
        SupervisorConfig::local_default(),
        Instant::now(),
    )?;
    if !recovery.faults.is_empty() {
        return Err("fresh Supervisor unexpectedly recovered active owners".into());
    }
    // Cleanup is armed even when start fails after retaining a real child.
    let mut supervisor = SupervisorLease {
        supervisor,
        agent: agent.clone(),
    };
    let inheritance = InheritOnce::new(rights)?;
    let start = supervisor.supervisor.start(agent, command, Instant::now());
    drop(inheritance);
    start?;
    // Do not tick/reap between taking the original snapshot and pidfd_open.
    // The original UnixManagedProcess still owns Child, so this numeric PID
    // cannot be recycled before its actual instance is pinned here.
    let snapshot = supervisor
        .supervisor
        .snapshot(agent)
        .ok_or("original Supervisor has no owner snapshot")?;
    let pid = snapshot
        .process_system_id
        .and_then(|value| u32::try_from(value).ok())
        .filter(|value| *value > 1)
        .ok_or("original Supervisor did not retain its actual child")?;
    // SAFETY: this names the still-retained original child, not a disk lease.
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: successful pidfd_open returns one fresh owned descriptor.
    let pidfd = unsafe { OwnedFd::from_raw_fd(raw as i32) };
    let record = registry.load_agent(agent)?;
    if record.lifecycle.lifecycle != AgentLifecycle::Starting
        || snapshot.spawn_generation != Some(record.lifecycle.generation)
    {
        return Err("original Starting generation changed before Root registration".into());
    }
    let end = Instant::now() + Duration::from_secs(5);
    let expected_uid = format!("Uid:\t{uid}\t{uid}\t{uid}\t{uid}");
    let expected_gid = format!("Gid:\t{gid}\t{gid}\t{gid}\t{gid}");
    loop {
        let status = std::fs::read_to_string(format!("/proc/{pid}/status"))?;
        if status.lines().any(|line| line == expected_uid)
            && status.lines().any(|line| line == expected_gid)
            && status.lines().any(|line| line == "NoNewPrivs:\t1")
            && status.lines().any(|line| {
                line.strip_prefix("Groups:")
                    .is_some_and(|value| value.trim().is_empty())
            })
            && status
                .lines()
                .filter(|line| line.starts_with("Cap"))
                .all(|line| {
                    line.split_once(':')
                        .is_some_and(|(_, value)| value.trim().bytes().all(|byte| byte == b'0'))
                })
        {
            break;
        }
        if Instant::now() >= end {
            return Err("original Agentd did not complete its credential drop".into());
        }
        std::thread::sleep(Duration::from_millis(5));
    }
    let stat = std::fs::read_to_string(format!("/proc/{pid}/stat"))?;
    let ticks = stat
        .rsplit_once(") ")
        .and_then(|(_, fields)| fields.split_whitespace().nth(19))
        .and_then(|value| value.parse().ok())
        .ok_or("original process start identity is missing")?;
    let registration = HostAuthorityRegistration {
        schema_version: 1,
        peer_pid: pid,
        boot_id: std::fs::read_to_string("/proc/sys/kernel/random/boot_id")?
            .trim()
            .into(),
        process_start_ticks: ticks,
        registered_identity: HostAuthorityRegisteredIdentity {
            agent_id: agent.clone(),
            spawn_generation: record.lifecycle.generation,
            fleet_root: registry.layout().fleet_root().as_path().to_path_buf(),
            workspace: record.manifest.workspace.as_path().to_path_buf(),
            resources: record.manifest.resources,
        },
        checkpoint_owner_agent_id: agent.clone(),
        publisher_epoch: 1,
    };
    Ok(OriginalOwner {
        supervisor,
        registration,
        pidfd,
    })
}
