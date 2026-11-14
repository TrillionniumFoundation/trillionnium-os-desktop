//! Fixed helper/broker MAC observation on the actual package connection.
//! Policy files, kernel notes, full loaded export, LSM order and actual policy
//! epoch retain the existing LoadedPolicyWitness gates. No relabel/load occurs.
use super::*;
use crate::control::package::PackageProcess;
use crate::production_cgroup::PackageBrokerUnit;
use std::os::unix::net::UnixStream;
use std::time::Instant;

pub(crate) struct PackageMacWitness {
    loaded: LoadedPolicyWitness,
    manager: MacSystemdWitness,
    local: [u8; 32],
    peer: [u8; 32],
    deadline: Instant,
}

fn before(deadline: Instant) -> Result<()> {
    if Instant::now() >= deadline {
        return Err(io::Error::from_raw_os_error(libc::ETIMEDOUT).into());
    }
    Ok(())
}

fn peer_security(stream: &UnixStream) -> Result<Vec<u8>> {
    let mut value = vec![0_u8; 256];
    let mut length = value.len() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERSEC,
            value.as_mut_ptr().cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        length > 0 && length as usize <= value.len(),
        "package peer MAC context bound",
    )?;
    value.truncate(length as usize);
    Ok(value)
}

impl PackageMacWitness {
    pub(crate) fn acquire(
        selection: &ProductionSelection,
        local: &PackageProcess,
        peer: &PackageProcess,
        unit: &PackageBrokerUnit,
        stream: &UnixStream,
        deadline: Instant,
    ) -> Result<Self> {
        before(deadline)?;
        require(
            local.is_broker() != peer.is_broker(),
            "package manager MAC observation requires one fixed broker",
        )?;
        let loaded = LoadedPolicyWitness::acquire(selection)?;
        let broker = if local.is_broker() { local } else { peer };
        let manager =
            MacSystemdWitness::observe_package_owner(&loaded, selection, unit, broker, deadline)?;
        let value = Self {
            loaded,
            manager,
            local: local.binding(),
            peer: peer.binding(),
            deadline,
        };
        value.revalidate(selection, local, peer, unit, stream)?;
        Ok(value)
    }

    pub(crate) fn revalidate(
        &self,
        selection: &ProductionSelection,
        local: &PackageProcess,
        peer: &PackageProcess,
        unit: &PackageBrokerUnit,
        stream: &UnixStream,
    ) -> Result<()> {
        before(self.deadline)?;
        self.loaded.revalidate(selection)?;
        local.revalidate()?;
        peer.revalidate()?;
        require(
            local.binding() == self.local
                && peer.binding() == self.peer
                && local.is_broker() != peer.is_broker(),
            "package fixed role generation changed",
        )?;
        for process in [local, peer] {
            let context = if process.is_broker() { BROKER } else { HOST };
            require(
                context_matches(&proc_attr(process.proc(), false)?, context),
                "actual package process SELinux role differs",
            )?;
            if process.is_broker() {
                require(
                    proc_attr(process.proc(), true)? == AA_BROKER,
                    "package broker lost the fixed enforcing AppArmor profile",
                )?;
            }
        }
        let expected = if peer.is_broker() { BROKER } else { HOST };
        require(
            context_matches(&peer_security(stream)?, expected),
            "actual connected package peer SID differs from its held process",
        )?;
        let broker = if local.is_broker() { local } else { peer };
        self.manager.revalidate_package_owner(
            &self.loaded,
            selection,
            unit,
            broker,
            self.deadline,
        )?;
        local.revalidate()?;
        peer.revalidate()?;
        self.loaded.stable_epoch()?;
        // Full original ELF and loaded-policy reads cannot extend the one
        // transaction deadline, including when the last read crosses it.
        before(self.deadline)
    }
}
