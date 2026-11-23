//! Read-only original production unit observation for a fixed package peer.
//! Reuses the authenticated manager endpoint, GetUnitByPIDFD and the complete
//! existing effective-unit validator. No Start/Stop or numeric-PID RPC exists.
use super::*;
use crate::control::package::PackageProcess;
use crate::production_mac::PackageMacOwner;

pub(crate) struct PackageBrokerUnit {
    channel: ManagerChannel,
    mac_owner: PackageMacOwner,
    cgroup: File,
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
        let value = Self {
            channel,
            mac_owner,
            cgroup_node: NodeIdentity::of(&cgroup)?,
            cgroup,
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
