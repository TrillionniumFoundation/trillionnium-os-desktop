//! Actual host systemd custody for the original production broker.
//!
//! AA label transitions clear PDEATHSIG. This provider binds the live host
//! manager, original broker PIDFD, Invocation and effective loaded unit to the
//! held production cgroup. It observes ownership; it does not authorize a MAC
//! transition, execute Android, restart a service or replace whole-tree reap.
use super::*;
use crate::production_selection::ProductionSelection;
use std::time::{Duration, Instant};

#[path = "production_unit_bus.rs"]
mod bus;
use bus::{Interface, Invocation, PrivateBus, Properties, Value};

use super::systemd_endpoint::{before, proc_read};
#[cfg(test)]
use super::systemd_endpoint::{pidfd_pid, proc_start};

const DEADLINE: Duration = Duration::from_secs(3);
const UNIT_OBJECT: &str = "/org/freedesktop/systemd1/unit/droidloom_2dproduction_2eservice";
const BROKER_EXECUTABLE: &str = "/usr/lib/droidloom/production/current/droidloomd";
const CAP_SETUID: u32 = 7;

struct ManagerChannel {
    // The sd-bus duplicate must close before the endpoint's original owners.
    bus: PrivateBus,
    endpoint: AuthenticatedManagerEndpoint,
}

impl ManagerChannel {
    fn open(deadline: Instant) -> Result<Self> {
        let endpoint = AuthenticatedManagerEndpoint::capture(deadline)?;
        let bus = PrivateBus::from_authenticated_socket(endpoint.connection(), deadline)?;
        let value = Self { bus, endpoint };
        value.check_until(deadline)?;
        Ok(value)
    }

    fn check_until(&self, deadline: Instant) -> Result<()> {
        self.endpoint.revalidate_until(deadline)
    }
}

fn property<'a>(properties: &'a Properties, name: &str) -> Result<&'a Value> {
    properties.get(name).ok_or(CgroupError::Rejected(
        "required effective unit property is absent",
    ))
}
fn equal(properties: &Properties, name: &str, expected: Value) -> Result<()> {
    require(
        property(properties, name)? == &expected,
        "effective loaded unit differs from fixed contract",
    )
}
fn nonzero_time(properties: &Properties, name: &str) -> Result<()> {
    require(
        matches!(property(properties, name)?, Value::U64(value) if *value > 0),
        "actual running unit generation timestamp required",
    )
}

fn validate_configuration(
    invocation: &Invocation,
    unit: &Properties,
    service: &Properties,
    broker: u32,
    cgroup: u64,
) -> Result<()> {
    require(
        invocation.unit == UNIT && invocation.path == UNIT_OBJECT,
        "original broker belongs to another systemd unit",
    )?;
    for (name, value) in [
        ("Id", UNIT),
        ("LoadState", "loaded"),
        ("ActiveState", "active"),
        ("SubState", "running"),
        (
            "FragmentPath",
            "/etc/systemd/system/droidloom-production.service",
        ),
        ("SourcePath", ""),
    ] {
        equal(unit, name, Value::Text(value.into()))?;
    }
    for name in ["Transient", "NeedDaemonReload"] {
        equal(unit, name, Value::Boolean(false))?;
    }
    equal(unit, "DropInPaths", Value::Strings(Vec::new()))?;
    equal(unit, "Job", Value::Job(0, "/".into()))?;
    equal(unit, "InvocationID", Value::Bytes(invocation.id.to_vec()))?;
    nonzero_time(unit, "StateChangeTimestampMonotonic")?;
    for (name, value) in [
        ("Type", "exec"),
        ("ExitType", "main"),
        ("Restart", "no"),
        ("KillMode", "control-group"),
        ("TimeoutStopFailureMode", "terminate"),
        ("User", "root"),
        ("Group", "root"),
        ("DelegateSubgroup", "broker"),
        ("ControlGroup", UNIT_CGROUP),
        ("Slice", "system.slice"),
        ("RootDirectory", ""),
        ("RootImage", ""),
        ("WorkingDirectory", "/"),
    ] {
        equal(service, name, Value::Text(value.into()))?;
    }
    for (name, value) in [
        ("RemainAfterExit", false),
        ("SendSIGKILL", true),
        ("SendSIGHUP", false),
        ("NoNewPrivileges", true),
        ("PrivateMounts", true),
        ("Delegate", true),
        ("DynamicUser", false),
    ] {
        equal(service, name, Value::Boolean(value))?;
    }
    for (name, value) in [
        ("MainPID", broker),
        ("ExecMainPID", broker),
        ("ControlPID", 0),
        ("NRestarts", 0),
        ("UMask", 0o077),
    ] {
        equal(service, name, Value::U32(value))?;
    }
    for (name, value) in [
        ("KillSignal", libc::SIGTERM),
        ("RestartKillSignal", libc::SIGTERM),
        ("FinalKillSignal", libc::SIGKILL),
        ("ExecMainCode", 0),
        ("ExecMainStatus", 0),
    ] {
        equal(service, name, Value::I32(value))?;
    }
    for (name, value) in [
        ("TimeoutStopUSec", 30_000_000),
        ("ExecMainExitTimestampMonotonic", 0),
        ("ControlGroupId", cgroup),
        ("MemoryMax", MEMORY_MAX),
        ("MemoryHigh", MEMORY_HIGH),
        ("MemorySwapMax", 0),
        ("TasksMax", PIDS_MAX),
        ("CPUQuotaPerSecUSec", 6_000_000),
        ("CPUQuotaPeriodUSec", 100_000),
        ("AmbientCapabilities", 1 << CAP_SETUID),
    ] {
        equal(service, name, Value::U64(value))?;
    }
    nonzero_time(service, "ExecMainStartTimestampMonotonic")?;
    equal(
        service,
        "AppArmorProfile",
        Value::Profile(false, "droidloom-production-broker".into()),
    )?;
    match property(service, "DelegateControllers")? {
        Value::Strings(values) => {
            let actual: BTreeSet<_> = values.iter().map(String::as_str).collect();
            require(
                values.len() == 4 && actual == REQUIRED_CONTROLLERS.into_iter().collect(),
                "effective manager delegation differs from fixed four controllers",
            )?;
        }
        _ => {
            return Err(CgroupError::Rejected(
                "effective manager delegation is not a string array",
            ));
        }
    }
    for name in [
        "ExecConditionEx",
        "ExecStartPreEx",
        "ExecStartPostEx",
        "ExecReloadEx",
        "ExecStopEx",
        "ExecStopPostEx",
    ] {
        equal(service, name, Value::Commands(Vec::new()))?;
    }
    match property(service, "ExecStartEx")? {
        Value::Commands(commands) if commands.len() == 1 => {
            let command = &commands[0];
            require(
                command.path == BROKER_EXECUTABLE
                    && command.arguments
                        == [BROKER_EXECUTABLE, "--socket", "/run/droidloom/control.sock"]
                    && command.flags.is_empty()
                    && command.pid == broker
                    && command.started.iter().all(|value| *value > 0)
                    && command.exited == [0, 0]
                    && command.code == 0
                    && command.status == 0,
                "actual original broker ExecStart differs",
            )?;
        }
        _ => {
            return Err(CgroupError::Rejected(
                "exactly one original broker ExecStart is required",
            ));
        }
    }
    Ok(())
}

#[derive(Eq, PartialEq)]
struct Snapshot {
    invocation: Invocation,
    unit: Properties,
    service: Properties,
}

/// The actual manager, original broker and held fixed cgroup issue this
/// observation. It is not a MAC, signal or Android readiness capability.
pub(super) struct EffectiveUnit {
    channel: ManagerChannel,
    cgroup: File,
    cgroup_node: NodeIdentity,
    original: Snapshot,
}

impl EffectiveUnit {
    fn snapshot(channel: &ManagerChannel, cgroup: &File, deadline: Instant) -> Result<Snapshot> {
        before(deadline)?;
        channel.check_until(deadline)?;
        trusted_directory(cgroup)?;
        cgroup_filesystem(cgroup)?;
        require(
            parse_unified_cgroup(&proc_read(channel.endpoint.observer_proc(), c"cgroup")?)?
                == format!("{UNIT_CGROUP}/broker"),
            "original broker left the fixed manager subgroup",
        )?;
        let invocation = channel
            .bus
            .invocation(channel.endpoint.observer_pidfd(), deadline)?;
        require(
            invocation.unit == UNIT && invocation.path == UNIT_OBJECT,
            "original broker manager owner is not the fixed production unit",
        )?;
        let unit = channel
            .bus
            .properties(&invocation, Interface::Unit, deadline)?;
        let service = channel
            .bus
            .properties(&invocation, Interface::Service, deadline)?;
        validate_configuration(
            &invocation,
            &unit,
            &service,
            channel.endpoint.observer_pid(),
            cgroup.metadata()?.ino(),
        )?;
        require(
            channel
                .bus
                .invocation(channel.endpoint.observer_pidfd(), deadline)?
                == invocation,
            "manager invocation changed during effective unit observation",
        )?;
        channel.check_until(deadline)?;
        before(deadline)?;
        Ok(Snapshot {
            invocation,
            unit,
            service,
        })
    }

    pub(super) fn open(cgroup: &File) -> Result<Self> {
        let deadline = Instant::now() + DEADLINE;
        let channel = ManagerChannel::open(deadline)?;
        let original = Self::snapshot(&channel, cgroup, deadline)?;
        let value = Self {
            channel,
            cgroup: cgroup.try_clone()?,
            cgroup_node: NodeIdentity::of(cgroup)?,
            original,
        };
        value.check_until(cgroup, deadline)?;
        Ok(value)
    }

    fn check_until(&self, cgroup: &File, deadline: Instant) -> Result<()> {
        before(deadline)?;
        require(
            NodeIdentity::of(cgroup)? == self.cgroup_node
                && NodeIdentity::of(&self.cgroup)? == self.cgroup_node,
            "effective manager cgroup custody changed",
        )?;
        let current = Self::snapshot(&self.channel, &self.cgroup, deadline)?;
        require(
            current == self.original,
            "original manager generation or effective unit changed",
        )?;
        before(deadline)
    }

    pub(super) fn check(&self, cgroup: &File) -> Result<()> {
        self.check_until(cgroup, Instant::now() + DEADLINE)
    }
}

/// Identity is copied only from the live provider; fields have no public
/// constructor and cannot be restored from a report or configuration file.
#[derive(Clone, Eq, PartialEq)]
pub(crate) struct SystemdOwnerGeneration {
    invocation: [u8; 16],
    endpoint: super::systemd_endpoint::ManagerEndpointGeneration,
    cgroup: NodeIdentity,
}

/// Read-only borrow of an already admitted owned hierarchy. The MAC provider
/// still has to observe actual manager and broker domains, socket labels and
/// precise signal/FD permissions under its current loaded policy epoch.
pub(crate) struct SystemdOwnerWitness<'a> {
    owner: &'a PreparedCgroup,
    selection: &'a ProductionSelection,
}

impl PreparedCgroup {
    pub(crate) fn systemd_owner<'a>(
        &'a self,
        selection: &'a ProductionSelection,
    ) -> Result<SystemdOwnerWitness<'a>> {
        let witness = SystemdOwnerWitness {
            owner: self,
            selection,
        };
        witness.revalidate()?;
        Ok(witness)
    }
}

impl SystemdOwnerWitness<'_> {
    fn effective(&self) -> &EffectiveUnit {
        &self.owner.get().unit_authority.effective
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.owner.revalidate()?;
        self.selection
            .revalidate()
            .map_err(|e| CgroupError::Owner(e.to_string()))?;
        let lease = self.owner.admission().lease();
        require(
            lease.host_uid() == self.selection.spec().host_uid
                && lease.broker_cohort() == self.selection.base_cohort(),
            "systemd owner belongs to another production selection",
        )
    }
    pub(crate) fn selection(&self) -> &ProductionSelection {
        self.selection
    }
    pub(crate) fn manager_pidfd(&self) -> BorrowedFd<'_> {
        self.effective().channel.endpoint.manager_pidfd()
    }
    pub(crate) fn manager_proc(&self) -> &File {
        self.effective().channel.endpoint.manager_proc()
    }
    pub(crate) fn broker_pidfd(&self) -> BorrowedFd<'_> {
        self.effective().channel.endpoint.observer_pidfd()
    }
    pub(crate) fn broker_proc(&self) -> &File {
        self.effective().channel.endpoint.observer_proc()
    }
    /// This is the client end. Use SO_PEERSEC to observe the actual manager;
    /// its own fgetxattr is not evidence for the server's socket domain.
    pub(crate) fn manager_connection(&self) -> &File {
        self.effective().channel.endpoint.connection()
    }
    pub(crate) fn manager_socket_file(&self) -> &File {
        self.effective().channel.endpoint.server_inode()
    }
    pub(crate) fn generation(&self) -> Result<SystemdOwnerGeneration> {
        self.revalidate()?;
        let effective = self.effective();
        Ok(SystemdOwnerGeneration {
            invocation: effective.original.invocation.id,
            endpoint: effective.channel.endpoint.generation()?,
            cgroup: effective.cgroup_node,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn kernel_process_generation_is_not_a_numeric_pid_claim() {
        let actual = std::fs::read_to_string("/proc/self/stat").unwrap();
        let pid = unsafe { libc::getpid() } as u32;
        assert!(proc_start(&actual, pid).unwrap() > 0);
        assert!(matches!(
            proc_start(&actual, pid + 1),
            Err(CgroupError::Rejected("held process PID changed"))
        ));
        assert!(matches!(
            proc_start(&format!("{pid} (a name with ) parens) S 1"), pid),
            Err(CgroupError::Rejected("short held process stat"))
        ));
        let regular = tempfile::tempfile().unwrap();
        assert!(matches!(
            pidfd_pid(&regular),
            Err(CgroupError::Rejected(
                "service owner PIDFD is not bound in the initial PID namespace"
            ))
        ));
    }

    #[test]
    #[ignore = "requires an initial-root sealed ELF in its own native systemd fixture unit"]
    fn actual_private_manager_original_pidfd_observation() {
        let deadline = Instant::now() + DEADLINE;
        let channel = ManagerChannel::open(deadline).expect("actual authenticated host manager");
        let invocation = channel
            .bus
            .invocation(channel.endpoint.observer_pidfd(), deadline)
            .unwrap();
        assert_eq!(
            invocation.unit,
            std::env::var("DROIDLOOM_SYSTEMD_FIXTURE_UNIT").unwrap()
        );
        let hex: String = invocation.id.iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(hex, std::env::var("INVOCATION_ID").unwrap());
        let unit = channel
            .bus
            .properties(&invocation, Interface::Unit, deadline)
            .unwrap();
        let service = channel
            .bus
            .properties(&invocation, Interface::Service, deadline)
            .unwrap();
        assert_eq!(
            property(&unit, "Id").unwrap(),
            &Value::Text(invocation.unit.clone())
        );
        assert_eq!(
            property(&unit, "InvocationID").unwrap(),
            &Value::Bytes(invocation.id.to_vec())
        );
        assert_eq!(
            property(&service, "MainPID").unwrap(),
            &Value::U32(channel.endpoint.observer_pid())
        );
        assert_eq!(
            property(&service, "ExecMainPID").unwrap(),
            &Value::U32(channel.endpoint.observer_pid())
        );
        let own =
            parse_unified_cgroup(&proc_read(channel.endpoint.observer_proc(), c"cgroup").unwrap()).unwrap();
        assert_eq!(
            property(&service, "ControlGroup").unwrap(),
            &Value::Text(own)
        );
        assert_eq!(
            channel
                .bus
                .invocation(channel.endpoint.observer_pidfd(), deadline)
                .unwrap(),
            invocation
        );
        channel.check_until(deadline).unwrap();
        before(deadline).unwrap();
        // A real transient fixture must never issue the fixed production
        // observation, even though its original manager and PIDFD are valid.
        assert!(matches!(
            validate_configuration(&invocation, &unit, &service, channel.endpoint.observer_pid(), 0),
            Err(CgroupError::Rejected(
                "original broker belongs to another systemd unit"
            ))
        ));
        eprintln!(
            "actual private manager: invocation={invocation:?}; unit={unit:?}; service={service:?}"
        );
    }
}
