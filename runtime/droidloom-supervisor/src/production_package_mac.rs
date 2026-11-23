//! Original loaded MAC custody acquired before package client connections.
//!
//! Only the two fixed installed package roles can issue preparation. The
//! selection, actual local process and loaded policy remain the same sealed
//! objects throughout both socket creation and final peer observations.
use super::*;
use crate::control::package::PackageProcess;
use crate::production_cgroup::PackageBrokerUnit;
use std::os::unix::net::UnixStream;
use std::time::Instant;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum PackageMacRole {
    Helper,
    Broker,
}

impl PackageMacRole {
    fn context(self) -> &'static str {
        match self {
            Self::Helper => HOST,
            Self::Broker => BROKER,
        }
    }
    fn apparmor(self) -> &'static [u8] {
        match self {
            Self::Helper => b"unconfined\n",
            Self::Broker => AA_BROKER,
        }
    }
}

struct PackageMacInputs {
    selection: ProductionSelection,
    local: PackageProcess,
    loaded: LoadedPolicyWitness,
    host_proc: Option<host_proc::HostProcView>,
    role: PackageMacRole,
    deadline: Instant,
}

/// A retained reference to the original, early in-memory inputs. Its only
/// constructor is private preparation below; serialized equality data,
/// process IDs, caller contexts and replacement policy inputs cannot issue it.
pub(crate) struct PackageMacOwner {
    original: Rc<PackageMacInputs>,
}

/// One preparation is consumed when the actual connected peer and manager
/// have passed their original descriptor checks. It is not a MAC grant.
pub(crate) struct PackageMacPreparation {
    owner: PackageMacOwner,
}

pub(crate) struct PackageMacWitness {
    manager: MacSystemdWitness,
    original: PackageMacOwner,
    peer: [u8; 32],
}

fn before(deadline: Instant) -> Result<()> {
    if Instant::now() >= deadline {
        return Err(io::Error::from_raw_os_error(libc::ETIMEDOUT).into());
    }
    Ok(())
}

fn require_local_role(local: &PackageProcess, role: PackageMacRole) -> Result<()> {
    local.revalidate()?;
    require(
        local.pid() == unsafe { libc::getpid() } as u32
            && local.is_broker() == matches!(role, PackageMacRole::Broker),
        "package MAC preparation requires this actual fixed local process",
    )?;
    require(
        context_matches(&self_attr::selinux_current()?, role.context()),
        "actual typed package local SELinux role differs",
    )?;
    require(
        proc_attr(local.proc(), true)? == role.apparmor(),
        "actual package local AppArmor role differs",
    )?;
    local.revalidate().map_err(MacError::Io)
}

impl PackageMacPreparation {
    pub(crate) fn helper(
        selection: ProductionSelection,
        local: PackageProcess,
        deadline: Instant,
    ) -> Result<Self> {
        Self::prepare(selection, local, PackageMacRole::Helper, deadline)
    }

    pub(crate) fn broker(
        selection: ProductionSelection,
        local: PackageProcess,
        deadline: Instant,
    ) -> Result<Self> {
        Self::prepare(selection, local, PackageMacRole::Broker, deadline)
    }

    fn prepare(
        selection: ProductionSelection,
        local: PackageProcess,
        role: PackageMacRole,
        deadline: Instant,
    ) -> Result<Self> {
        before(deadline)?;
        require(
            !selection.is_kernel_first(),
            "legacy package helpers cannot enter a kernel-first generation",
        )?;
        require_local_role(&local, role)?;
        let loaded = LoadedPolicyWitness::acquire(&selection)?;
        before(deadline)?;
        let host_proc = if loaded.declaration.scoped_contexts()? {
            Some(match role {
                PackageMacRole::Helper => {
                    host_proc::HostProcView::create_package_helper(&loaded, &selection)?
                }
                PackageMacRole::Broker => host_proc::HostProcView::create(&loaded, &selection)?,
            })
        } else {
            None
        };
        let owner = PackageMacOwner {
            original: Rc::new(PackageMacInputs {
                selection,
                local,
                loaded,
                host_proc,
                role,
                deadline,
            }),
        };
        owner.revalidate()?;
        Ok(Self { owner })
    }

    pub(crate) fn owner(&self) -> &PackageMacOwner {
        &self.owner
    }

    pub(crate) fn finish(
        self,
        peer: &PackageProcess,
        unit: &PackageBrokerUnit,
        stream: &UnixStream,
    ) -> Result<PackageMacWitness> {
        self.owner.revalidate()?;
        unit.require_original_owner(&self.owner)
            .map_err(|error| MacError::Owner(error.to_string()))?;
        peer.revalidate()?;
        require(
            self.owner.local().is_broker() != peer.is_broker(),
            "package manager MAC observation requires the two fixed roles",
        )?;
        let broker = if self.owner.local().is_broker() {
            self.owner.local()
        } else {
            peer
        };
        let manager = MacSystemdWitness::observe_package_owner(
            &self.owner,
            unit,
            broker,
            self.owner.deadline(),
        )?;
        let value = PackageMacWitness {
            manager,
            original: self.owner,
            peer: peer.binding(),
        };
        value.revalidate(peer, unit, stream)?;
        Ok(value)
    }
}

impl PackageMacOwner {
    pub(crate) fn revalidate(&self) -> Result<()> {
        let inputs = &self.original;
        before(inputs.deadline)?;
        inputs.loaded.revalidate(&inputs.selection)?;
        require_local_role(&inputs.local, inputs.role)?;
        match &inputs.host_proc {
            Some(view) => {
                require(
                    inputs.loaded.declaration.scoped_contexts()?,
                    "selected package proc view belongs to a different contract",
                )?;
                view.revalidate(&inputs.loaded, &inputs.selection)?;
            }
            None => require(
                !inputs.loaded.declaration.scoped_contexts()?,
                "selected package MAC owner lacks its original proc view",
            )?,
        }
        inputs.loaded.stable_epoch()?;
        before(inputs.deadline)
    }

    pub(crate) fn retain_original(&self) -> Result<Self> {
        self.revalidate()?;
        let value = Self {
            original: Rc::clone(&self.original),
        };
        value.revalidate()?;
        Ok(value)
    }

    pub(crate) fn same_original(&self, other: &Self) -> bool {
        Rc::ptr_eq(&self.original, &other.original)
    }

    pub(super) fn objects(&self) -> Result<(&LoadedPolicyWitness, &ProductionSelection)> {
        self.revalidate()?;
        Ok((&self.original.loaded, &self.original.selection))
    }

    pub(super) fn role(&self) -> PackageMacRole {
        self.original.role
    }

    pub(super) fn host_proc(&self) -> Option<&host_proc::HostProcView> {
        self.original.host_proc.as_ref()
    }

    pub(crate) fn selection(&self) -> &ProductionSelection {
        &self.original.selection
    }

    pub(crate) fn local(&self) -> &PackageProcess {
        &self.original.local
    }

    pub(crate) fn deadline(&self) -> Instant {
        self.original.deadline
    }
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
    pub(crate) fn selection(&self) -> &ProductionSelection {
        self.original.selection()
    }

    pub(crate) fn local(&self) -> &PackageProcess {
        self.original.local()
    }

    pub(crate) fn revalidate(
        &self,
        peer: &PackageProcess,
        unit: &PackageBrokerUnit,
        stream: &UnixStream,
    ) -> Result<()> {
        self.original.revalidate()?;
        unit.require_original_owner(&self.original)
            .map_err(|error| MacError::Owner(error.to_string()))?;
        let local = self.original.local();
        peer.revalidate()?;
        require(
            peer.binding() == self.peer && local.is_broker() != peer.is_broker(),
            "package fixed role generation changed",
        )?;
        for process in [local, peer] {
            if let Some(view) = self.original.host_proc() {
                view.for_package_process(&self.original, process)?;
            } else {
                let context = if process.is_broker() { BROKER } else { HOST };
                require(
                    context_matches(&proc_attr(process.proc(), false)?, context),
                    "actual package process SELinux role differs",
                )?;
            }
            let apparmor = if process.is_broker() {
                AA_BROKER
            } else {
                b"unconfined\n"
            };
            require(
                proc_attr(process.proc(), true)? == apparmor,
                "actual package process AppArmor role differs",
            )?;
        }
        let expected = if peer.is_broker() { BROKER } else { HOST };
        require(
            context_matches(&peer_security(stream)?, expected),
            "actual connected package peer SID differs from its held process",
        )?;
        let broker = if local.is_broker() { local } else { peer };
        self.manager.revalidate_package_owner(
            &self.original,
            unit,
            broker,
            self.original.deadline(),
        )?;
        peer.revalidate()?;
        self.original.revalidate()
    }
}
