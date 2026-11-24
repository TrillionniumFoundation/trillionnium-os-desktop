//! Read-only original production unit observation for a fixed package peer.
//! Reuses the authenticated manager endpoint, GetUnitByPIDFD and the complete
//! existing effective-unit validator. No Start/Stop or numeric-PID RPC exists.
use super::*;
use crate::control::package::PackageProcess;
use crate::production_mac::PackageMacOwner;

fn retained_cgroup_events(events: &File) -> io::Result<Vec<u8>> {
    if unsafe { libc::lseek(events.as_raw_fd(), 0, libc::SEEK_SET) } < 0 {
        return Err(io::Error::last_os_error());
    }
    let mut bytes = Vec::new();
    events.take(4097).read_to_end(&mut bytes)?;
    if bytes.len() > 4096 {
        return Err(io::Error::other("original cgroup events exceeded its bound"));
    }
    Ok(bytes)
}

// Called only with the retained, originally admitted running snapshot. A dead
// unit alone is insufficient: the exact invocation, command and clean exit
// must agree, and every unrelated effective property must remain unchanged.
fn validate_terminal(original: &Snapshot, unit: &Properties, service: &Properties) -> Result<()> {
    equal(unit, "ActiveState", Value::Text("inactive".into()))?;
    equal(unit, "SubState", Value::Text("dead".into()))?;
    equal(unit, "Job", Value::Job(0, "/".into()))?;
    equal(unit, "InvocationID", Value::Bytes(original.invocation.id.to_vec()))?;
    let (Value::U64(started), Value::U64(ended)) = (
        property(&original.unit, "StateChangeTimestampMonotonic")?,
        property(unit, "StateChangeTimestampMonotonic")?,
    ) else {
        return Err(CgroupError::Rejected("invalid terminal unit timestamp"));
    };
    require(*started > 0 && ended >= started, "terminal unit predates original invocation")?;
    require(unit.len() == original.unit.len() && original.unit.iter().all(|(name, value)| {
        matches!(name.as_str(), "ActiveState" | "SubState" | "Job" | "StateChangeTimestampMonotonic")
            || unit.get(name) == Some(value)
    }), "original loaded unit changed during package stop")?;
    equal(service, "MainPID", Value::U32(0))?;
    equal(service, "ControlPID", Value::U32(0))?;
    equal(service, "Result", Value::Text("success".into()))?;
    equal(service, "ExecMainCode", Value::I32(libc::CLD_EXITED))?;
    equal(service, "ExecMainStatus", Value::I32(0))?;
    let (Value::U64(started), Value::U64(ended)) = (
        property(&original.service, "ExecMainStartTimestampMonotonic")?,
        property(service, "ExecMainExitTimestampMonotonic")?,
    ) else {
        return Err(CgroupError::Rejected("invalid original command exit timestamp"));
    };
    require(*started > 0 && ended >= started, "original command has no terminal exit timestamp")?;
    let (Value::Commands(initial), Value::Commands(final_commands)) = (
        property(&original.service, "ExecStartEx")?, property(service, "ExecStartEx")?,
    ) else {
        return Err(CgroupError::Rejected("missing original command terminal record"));
    };
    require(initial.len() == 1 && final_commands.len() == 1, "original single command changed")?;
    let first = &initial[0];
    let last = &final_commands[0];
    require(last.path == first.path && last.arguments == first.arguments && last.flags == first.flags
        && last.pid == first.pid && last.started == first.started
        && last.exited[0] >= first.started[0] && last.exited[1] == *ended
        && last.code == libc::CLD_EXITED && last.status == 0,
        "terminal command is not the original clean broker exit")?;
    let group = property(service, "ControlGroup")?;
    let group_id = property(service, "ControlGroupId")?;
    require((group == &Value::Text(String::new()) && group_id == &Value::U64(0))
        || (group == property(&original.service, "ControlGroup")?
            && group_id == property(&original.service, "ControlGroupId")?),
        "terminal manager cgroup belongs to another generation")?;
    require(service.len() == original.service.len() && original.service.iter().all(|(name, value)| {
        matches!(name.as_str(), "MainPID" | "ExecMainCode" | "ExecMainStatus"
            | "ExecMainExitTimestampMonotonic" | "ExecStartEx" | "ControlGroup" | "ControlGroupId")
            || service.get(name) == Some(value)
    }), "original effective service changed during package stop")
}

pub(crate) struct PackageBrokerUnit {
    channel: ManagerChannel,
    mac_owner: PackageMacOwner,
    cgroup: File,
    cgroup_events: File,
    cgroup_node: NodeIdentity,
    original: Snapshot,
    broker_binding: [u8; 32],
}

impl PackageBrokerUnit {
    fn snapshot(
        channel: &ManagerChannel,
        group: &File,
        broker: &PackageProcess,
        deadline: Instant,
    ) -> Result<Snapshot> {
        before(deadline)?;
        broker.revalidate()?;
        require(
            broker.is_broker(),
            "package manager observation requires the fixed broker role",
        )?;
        channel.check_until(deadline)?;
        trusted_directory(group)?;
        cgroup_filesystem(group)?;
        require(
            parse_unified_cgroup(&proc_read(broker.proc(), c"cgroup")?)?
                == format!("{UNIT_CGROUP}/broker"),
            "package peer left the original broker subgroup",
        )?;
        let invocation = channel.bus.invocation(broker.pidfd(), deadline)?;
        require(
            invocation.unit == UNIT && invocation.path == UNIT_OBJECT,
            "package peer is not owned by the fixed production unit",
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
            broker.pid(),
            group.metadata()?.ino(),
        )?;
        require(
            channel.bus.invocation(broker.pidfd(), deadline)? == invocation,
            "package peer's original unit invocation changed",
        )?;
        broker.revalidate()?;
        channel.check_until(deadline)?;
        before(deadline)?;
        Ok(Snapshot {
            invocation,
            unit,
            service,
        })
    }

    pub(crate) fn capture(
        broker: &PackageProcess,
        mac_owner: PackageMacOwner,
        deadline: Instant,
    ) -> Result<Self> {
        mac_owner
            .revalidate()
            .map_err(|error| CgroupError::Io(io::Error::other(error.to_string())))?;
        require(
            deadline <= mac_owner.deadline(),
            "package unit cannot extend original MAC deadline",
        )?;
        let deadline = deadline.min(Instant::now() + DEADLINE);
        let channel = ManagerChannel::open_package(
            mac_owner
                .retain_original()
                .map_err(|error| CgroupError::Io(io::Error::other(error.to_string())))?,
            deadline,
        )?;
        let cgroup = open_absolute(
            c"/sys/fs/cgroup/system.slice/droidloom-production.service",
            libc::O_PATH | libc::O_DIRECTORY,
        )?;
        let original = Self::snapshot(&channel, &cgroup, broker, deadline)?;
        let cgroup_events = open_at(&cgroup, c"cgroup.events", libc::O_RDONLY | libc::O_NONBLOCK)?;
        cgroup_filesystem(&cgroup_events)?;
        retained_cgroup_events(&cgroup_events)?;
        let value = Self {
            channel,
            mac_owner,
            cgroup_node: NodeIdentity::of(&cgroup)?,
            cgroup,
            cgroup_events,
            original,
            broker_binding: broker.binding(),
        };
        value.revalidate(broker, deadline)?;
        Ok(value)
    }

    pub(crate) fn require_original_owner(&self, owner: &PackageMacOwner) -> Result<()> {
        self.mac_owner
            .revalidate()
            .map_err(|error| CgroupError::Io(io::Error::other(error.to_string())))?;
        owner
            .revalidate()
            .map_err(|error| CgroupError::Io(io::Error::other(error.to_string())))?;
        require(
            self.mac_owner.same_original(owner),
            "package manager connection belongs to different original MAC inputs",
        )
    }

    pub(crate) fn revalidate(&self, broker: &PackageProcess, deadline: Instant) -> Result<()> {
        self.mac_owner
            .revalidate()
            .map_err(|error| CgroupError::Io(io::Error::other(error.to_string())))?;
        require(
            deadline <= self.mac_owner.deadline(),
            "package unit cannot extend original MAC deadline",
        )?;
        let deadline = deadline.min(Instant::now() + DEADLINE);
        before(deadline)?;
        let named = open_absolute(
            c"/sys/fs/cgroup/system.slice/droidloom-production.service",
            libc::O_PATH | libc::O_DIRECTORY,
        )?;
        require(
            broker.binding() == self.broker_binding
                && NodeIdentity::of(&named)? == self.cgroup_node
                && NodeIdentity::of(&self.cgroup)? == self.cgroup_node,
            "package original broker/cgroup identity changed",
        )?;
        require(
            Self::snapshot(&self.channel, &self.cgroup, broker, deadline)? == self.original,
            "package original loaded unit or invocation changed",
        )?;
        before(deadline)
    }

    pub(crate) fn invocation(&self) -> [u8; 16] {
        self.original.invocation.id
    }

    pub(crate) fn revalidate_retired(&self, broker: &PackageProcess, deadline: Instant) -> Result<()> {
        self.mac_owner.revalidate().map_err(|error| CgroupError::Io(io::Error::other(error.to_string())))?;
        require(deadline <= self.mac_owner.deadline(), "terminal package deadline changed")?;
        let deadline = deadline.min(Instant::now() + DEADLINE);
        before(deadline)?;
        require(broker.binding() == self.broker_binding,
            "terminal package proof belongs to another original broker")?;
        broker.verify_exited_broker()?;
        self.channel.check_until(deadline)?;
        // Query the retained original unit object. GetUnitByPIDFD is a live
        // admission operation and must not be retried against a replacement PID.
        let unit = self.channel.bus.properties(&self.original.invocation, Interface::Unit, deadline)?;
        let service = self.channel.bus.properties(&self.original.invocation, Interface::Service, deadline)?;
        validate_terminal(&self.original, &unit, &service)?;
        cgroup_filesystem(&self.cgroup)?;
        require(NodeIdentity::of(&self.cgroup)? == self.cgroup_node,
            "original terminal cgroup descriptor changed")?;
        match open_absolute(c"/sys/fs/cgroup/system.slice/droidloom-production.service", libc::O_PATH | libc::O_DIRECTORY) {
            Ok(named) => {
                require(NodeIdentity::of(&named)? == self.cgroup_node,
                    "terminal production cgroup was replaced")?;
                // The real original cgroup.events population covers its whole
                // subtree; no additional cgroup.procs authority is needed.
                require(!populated(&self.cgroup)?,
                    "original production cgroup remains occupied")?;
            }
            Err(CgroupError::Io(error)) if error.kind() == io::ErrorKind::NotFound => {
                // kernfs directory nlink is not a deletion witness. The FD
                // opened before stop must report the kernel's dead-node state.
                match retained_cgroup_events(&self.cgroup_events) {
                    Err(error) if error.raw_os_error() == Some(libc::ENODEV) => {}
                    Err(error) => return Err(error.into()),
                    Ok(_) => return Err(CgroupError::Rejected("original cgroup events remain live after named group vanished")),
                }
            }
            Err(error) => return Err(error),
        }
        broker.verify_exited_broker()?;
        require(self.channel.bus.properties(&self.original.invocation, Interface::Unit, deadline)? == unit
            && self.channel.bus.properties(&self.original.invocation, Interface::Service, deadline)? == service,
            "terminal original unit changed across cgroup retirement observation")?;
        self.channel.check_until(deadline)?;
        before(deadline)
    }

    // These are borrowed original kernel objects from this unit's one
    // authenticated manager channel. No caller can substitute an endpoint,
    // process identifier, socket path, label, or generation record.
    pub(crate) fn manager_pidfd(&self) -> BorrowedFd<'_> {
        self.channel.endpoint.manager_pidfd()
    }
    pub(crate) fn manager_proc(&self) -> &File {
        self.channel.endpoint.manager_proc()
    }
    pub(crate) fn manager_connection(&self) -> &File {
        self.channel.endpoint.connection()
    }
    pub(crate) fn manager_socket_file(&self) -> &File {
        self.channel.endpoint.server_inode()
    }
    pub(crate) fn generation(
        &self,
        broker: &PackageProcess,
        deadline: Instant,
    ) -> Result<SystemdOwnerGeneration> {
        self.revalidate(broker, deadline)?;
        let generation = SystemdOwnerGeneration {
            invocation: self.original.invocation.id,
            endpoint: self.channel.endpoint.generation()?,
            cgroup: self.cgroup_node,
        };
        before(deadline)?;
        Ok(generation)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn observations() -> (Snapshot, Properties, Properties) {
        let command = super::super::bus::ExecCommand {
            path: BROKER_EXECUTABLE.into(),
            arguments: vec![BROKER_EXECUTABLE.into(), "--socket".into(), "/run/droidloom/control.sock".into()],
            flags: Vec::new(), started: [100, 10], exited: [0, 0], pid: 123,
            code: 0, status: 0,
        };
        let unit = Properties::from([
            ("ActiveState".into(), Value::Text("active".into())),
            ("SubState".into(), Value::Text("running".into())),
            ("Job".into(), Value::Job(0, "/".into())),
            ("InvocationID".into(), Value::Bytes(vec![7; 16])),
            ("StateChangeTimestampMonotonic".into(), Value::U64(10)),
            ("LoadState".into(), Value::Text("loaded".into())),
        ]);
        let service = Properties::from([
            ("MainPID".into(), Value::U32(123)),
            ("ExecMainPID".into(), Value::U32(123)),
            ("ControlPID".into(), Value::U32(0)),
            ("Result".into(), Value::Text("success".into())),
            ("ExecMainCode".into(), Value::I32(0)),
            ("ExecMainStatus".into(), Value::I32(0)),
            ("ExecMainStartTimestampMonotonic".into(), Value::U64(10)),
            ("ExecMainExitTimestampMonotonic".into(), Value::U64(0)),
            ("ExecStartEx".into(), Value::Commands(vec![command.clone()])),
            ("ControlGroup".into(), Value::Text(UNIT_CGROUP.into())),
            ("ControlGroupId".into(), Value::U64(15)),
            ("NRestarts".into(), Value::U32(0)),
        ]);
        let mut ended_unit = unit.clone();
        ended_unit.insert("ActiveState".into(), Value::Text("inactive".into()));
        ended_unit.insert("SubState".into(), Value::Text("dead".into()));
        ended_unit.insert("StateChangeTimestampMonotonic".into(), Value::U64(30));
        let mut ended_service = service.clone();
        ended_service.insert("MainPID".into(), Value::U32(0));
        ended_service.insert("ExecMainCode".into(), Value::I32(libc::CLD_EXITED));
        ended_service.insert("ExecMainExitTimestampMonotonic".into(), Value::U64(25));
        ended_service.insert("ExecStartEx".into(), Value::Commands(vec![super::super::bus::ExecCommand {
            exited: [125, 25], code: libc::CLD_EXITED, ..command
        }]));
        (Snapshot { invocation: Invocation { unit: UNIT.into(), path: UNIT_OBJECT.into(), id: [7; 16] }, unit, service }, ended_unit, ended_service)
    }

    #[test]
    fn terminal_package_observation_requires_the_original_clean_invocation_and_command() {
        let (original, unit, service) = observations();
        validate_terminal(&original, &unit, &service).unwrap();
        assert!(validate_terminal(&original, &original.unit, &original.service).is_err());
        for (name, value) in [
            ("InvocationID", Value::Bytes(vec![8; 16])),
            ("ActiveState", Value::Text("failed".into())),
            ("Job", Value::Job(9, "/org/freedesktop/systemd1/job/9".into())),
            ("StateChangeTimestampMonotonic", Value::U64(9)),
            ("LoadState", Value::Text("not-found".into())),
        ] {
            let mut changed = unit.clone(); changed.insert(name.into(), value);
            assert!(validate_terminal(&original, &changed, &service).is_err(), "{name}");
        }
        for (name, value) in [
            ("ExecMainPID", Value::U32(124)),
            ("Result", Value::Text("signal".into())),
            ("ExecMainCode", Value::I32(libc::CLD_KILLED)),
            ("ExecMainStatus", Value::I32(1)),
            ("NRestarts", Value::U32(1)),
            ("ControlGroupId", Value::U64(16)),
        ] {
            let mut changed = service.clone(); changed.insert(name.into(), value);
            assert!(validate_terminal(&original, &unit, &changed).is_err(), "{name}");
        }
        let mut changed = service.clone();
        let Value::Commands(commands) = changed.get_mut("ExecStartEx").unwrap() else { unreachable!() };
        commands[0].started[1] += 1;
        assert!(validate_terminal(&original, &unit, &changed).is_err());
        changed = service.clone(); changed.remove("ControlPID");
        assert!(validate_terminal(&original, &unit, &changed).is_err());
        let mut removed = service;
        removed.insert("ControlGroup".into(), Value::Text(String::new()));
        removed.insert("ControlGroupId".into(), Value::U64(0));
        validate_terminal(&original, &unit, &removed).unwrap();
    }
}
