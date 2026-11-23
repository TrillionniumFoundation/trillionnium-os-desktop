//! Live MAC binding of the authenticated, original systemd lifetime owner.
//!
//! This observer cannot create a manager connection, adopt a PID, install a
//! unit, relabel a socket, signal a process, or issue Android readiness. The
//! cgroup owner supplies its existing kernel-authenticated manager connection
//! and original process/Invocation generation. The loaded MAC provider must
//! independently observe the same live manager and the fixed server inode.

use super::package::PackageMacOwner;
use super::*;
use crate::control::package::PackageProcess;
use crate::production_cgroup::{
    CgroupError, PackageBrokerUnit, SystemdOwnerGeneration, SystemdOwnerWitness,
};
use std::time::Instant;

const MANAGER_FILE: &str = "u:object_r:droidloom_manager_private_socket:s0";
const AA_MANAGER: &[u8] = b"unconfined\n";

fn original_systemd<T>(value: std::result::Result<T, CgroupError>) -> Result<T> {
    value.map_err(|error| match error {
        CgroupError::Io(error) => MacError::Io(error),
        other => MacError::Owner(other.to_string()),
    })
}

/// This is the O_PATH inode of /run/systemd/private held by the original
/// manager channel. Its connected client socket is a different kernel object
/// and cannot be used as evidence for the server sock_file label.
pub(super) fn manager_file_context(file: &File) -> Result<Vec<u8>> {
    let before = Node::of(file)?;
    require(
        before.mode & libc::S_IFMT == libc::S_IFSOCK,
        "manager sock_file must be the actual held socket inode",
    )?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        flags & libc::O_PATH != 0,
        "manager server inode must remain an original O_PATH descriptor",
    )?;
    // The exact target kernel rejects O_PATH in fgetxattr/getxattrat's fdget
    // branch. Follow only this process's owned FD alias; its owner brackets
    // this read with actual parent and named-inode revalidation.
    let alias = CString::new(format!("/proc/self/fd/{}", file.as_raw_fd()))
        .map_err(|_| MacError::Rejected("invalid original manager FD alias"))?;
    let mut bytes = [0_u8; 1024];
    let count = unsafe {
        libc::getxattr(
            alias.as_ptr(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        count > 0 && count as usize <= bytes.len(),
        "bounded actual manager server-inode label required",
    )?;
    require(
        Node::of(file)? == before,
        "manager server inode changed during its actual label observation",
    )?;
    Ok(bytes[..count as usize].to_vec())
}

fn systemd_decisions(loaded: &LoadedPolicyWitness) -> Result<()> {
    let mut sequence = Some(loaded.av_sequence);
    access(
        &loaded.root,
        BROKER,
        BROKER,
        "unix_stream_socket",
        &[
            "create", "connect", "getattr", "read", "write", "getopt", "setopt",
        ],
        true,
        &mut sequence,
    )?;
    access(
        &loaded.root,
        BROKER,
        loaded.declaration.manager(),
        "unix_stream_socket",
        &["connectto"],
        true,
        &mut sequence,
    )?;
    access(
        &loaded.root,
        BROKER,
        MANAGER_FILE,
        "sock_file",
        &["getattr", "write"],
        true,
        &mut sequence,
    )?;
    // GetUnitByPIDFD actually receives the original broker-created PIDFD.
    access(
        &loaded.root,
        loaded.declaration.manager(),
        BROKER,
        "fd",
        &["use"],
        true,
        &mut sequence,
    )?;
    access(
        &loaded.root,
        BROKER,
        loaded.declaration.manager(),
        "process",
        &["getattr"],
        true,
        &mut sequence,
    )?;
    // This preflight covers the broker and fixed bootstrap roles. The
    // selected policy's complete Android service-domain closure and actual
    // dual-LSM daemon-death retirement remain separate activation gates.
    let controlled: &[&str] = if loaded.declaration.early() {
        &[BROKER]
    } else {
        &[
            BROKER,
            INIT,
            "u:r:apexd:s0",
            LINKERCONFIG,
            "u:r:droidloom_query:s0",
            "u:r:droidloom_launch_read:s0",
            "u:r:droidloom_launch_start:s0",
        ]
    };
    for &target in controlled {
        access(
            &loaded.root,
            loaded.declaration.manager(),
            target,
            "process",
            &["getattr", "signull", "signal", "sigkill", "sigstop"],
            true,
            &mut sequence,
        )?;
    }
    let excluded: &[&str] = if loaded.declaration.early() {
        &[INIT, "u:r:apexd:s0", LINKERCONFIG, "u:r:untrusted_app:s0"]
    } else {
        &[
            INIT,
            "u:r:apexd:s0",
            LINKERCONFIG,
            "u:r:droidloom_query:s0",
            "u:r:droidloom_launch_read:s0",
            "u:r:droidloom_launch_start:s0",
        ]
    };
    for &source in excluded {
        access(
            &loaded.root,
            source,
            loaded.declaration.manager(),
            "unix_stream_socket",
            &["connectto"],
            false,
            &mut sequence,
        )?;
        access(
            &loaded.root,
            source,
            MANAGER_FILE,
            "sock_file",
            &["write"],
            false,
            &mut sequence,
        )?;
    }
    Ok(())
}

// Both variants borrow actual fixed providers. This private adapter cannot
// adopt arbitrary descriptors or turn the package helper into a MacPreflight.
enum ActualSystemdOwner<'a, 'prepared> {
    Prepared(&'a SystemdOwnerWitness<'prepared>),
    Package {
        unit: &'a PackageBrokerUnit,
        broker: &'a PackageProcess,
        deadline: Instant,
    },
}

impl ActualSystemdOwner<'_, '_> {
    fn revalidate(&self) -> Result<()> {
        original_systemd(match self {
            Self::Prepared(owner) => owner.revalidate(),
            Self::Package {
                unit,
                broker,
                deadline,
            } => unit.revalidate(broker, *deadline),
        })
    }
    fn generation(&self) -> Result<SystemdOwnerGeneration> {
        original_systemd(match self {
            Self::Prepared(owner) => owner.generation(),
            Self::Package {
                unit,
                broker,
                deadline,
            } => unit.generation(broker, *deadline),
        })
    }
    fn manager_pidfd(&self) -> BorrowedFd<'_> {
        match self {
            Self::Prepared(owner) => owner.manager_pidfd(),
            Self::Package { unit, .. } => unit.manager_pidfd(),
        }
    }
    fn manager_proc(&self) -> &File {
        match self {
            Self::Prepared(owner) => owner.manager_proc(),
            Self::Package { unit, .. } => unit.manager_proc(),
        }
    }
    fn broker_pidfd(&self) -> BorrowedFd<'_> {
        match self {
            Self::Prepared(owner) => owner.broker_pidfd(),
            Self::Package { broker, .. } => broker.pidfd(),
        }
    }
    fn broker_proc(&self) -> &File {
        match self {
            Self::Prepared(owner) => owner.broker_proc(),
            Self::Package { broker, .. } => broker.proc(),
        }
    }
    fn manager_connection(&self) -> &File {
        match self {
            Self::Prepared(owner) => owner.manager_connection(),
            Self::Package { unit, .. } => unit.manager_connection(),
        }
    }
    fn manager_socket_file(&self) -> &File {
        match self {
            Self::Prepared(owner) => owner.manager_socket_file(),
            Self::Package { unit, .. } => unit.manager_socket_file(),
        }
    }
    fn within_deadline(&self) -> Result<()> {
        if let Self::Package { deadline, .. } = self {
            if Instant::now() >= *deadline {
                return Err(io::Error::from_raw_os_error(libc::ETIMEDOUT).into());
            }
        }
        Ok(())
    }
}

/// Equality binding of live kernel observations only. Successful validation
/// does not manufacture process ownership or certify an unexecuted MAC fault
/// fixture; callers must retain the actual owner and all later phase gates.
pub(crate) struct MacSystemdWitness {
    provider: ProviderBinding,
    generation: SystemdOwnerGeneration,
    boot: String,
    manager_pidfd: DescriptorIdentity,
    manager_proc: DescriptorIdentity,
    broker_pidfd: DescriptorIdentity,
    broker_proc: DescriptorIdentity,
    connection: DescriptorIdentity,
    server_file: Node,
    _same_thread: PhantomData<Rc<()>>,
}

impl MacPreflight {
    pub(crate) fn observe_systemd_owner(
        &self,
        owner: &SystemdOwnerWitness<'_>,
    ) -> Result<MacSystemdWitness> {
        self.revalidate(owner.selection())?;
        let value = MacSystemdWitness::capture(&self.loaded, &ActualSystemdOwner::Prepared(owner))?;
        value.revalidate(self, owner)?;
        Ok(value)
    }
}

impl MacSystemdWitness {
    fn capture(loaded: &LoadedPolicyWitness, owner: &ActualSystemdOwner<'_, '_>) -> Result<Self> {
        owner.within_deadline()?;
        owner.revalidate()?;
        let value = Self {
            provider: loaded.binding(),
            generation: owner.generation()?,
            boot: loaded.boot.clone(),
            manager_pidfd: descriptor_identity(owner.manager_pidfd())?,
            manager_proc: descriptor_identity(owner.manager_proc().as_fd())?,
            broker_pidfd: descriptor_identity(owner.broker_pidfd())?,
            broker_proc: descriptor_identity(owner.broker_proc().as_fd())?,
            connection: descriptor_identity(owner.manager_connection().as_fd())?,
            server_file: Node::of(owner.manager_socket_file())?,
            _same_thread: PhantomData,
        };
        owner.within_deadline()?;
        Ok(value)
    }
    fn original_descriptors(&self, owner: &ActualSystemdOwner<'_, '_>) -> Result<()> {
        require(
            descriptor_identity(owner.manager_pidfd())? == self.manager_pidfd
                && descriptor_identity(owner.manager_proc().as_fd())? == self.manager_proc
                && descriptor_identity(owner.broker_pidfd())? == self.broker_pidfd
                && descriptor_identity(owner.broker_proc().as_fd())? == self.broker_proc
                && descriptor_identity(owner.manager_connection().as_fd())? == self.connection
                && Node::of(owner.manager_socket_file())? == self.server_file,
            "original systemd PIDFD/proc/connection/server-inode custody changed",
        )
    }

    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        owner: &SystemdOwnerWitness<'_>,
    ) -> Result<()> {
        // Keep the broker-only MacPreflight gate on the original prepared
        // owner path. Package observation below cannot create or borrow it.
        mac.revalidate(owner.selection())?;
        self.revalidate_actual(
            &mac.loaded,
            owner.selection(),
            &ActualSystemdOwner::Prepared(owner),
            mac.host_proc.as_ref(),
            None,
        )?;
        mac.revalidate(owner.selection())
    }

    pub(super) fn observe_package_owner(
        mac: &PackageMacOwner,
        unit: &PackageBrokerUnit,
        broker: &PackageProcess,
        deadline: Instant,
    ) -> Result<Self> {
        mac.revalidate()?;
        require(
            deadline == mac.deadline(),
            "original package MAC deadline differs",
        )?;
        original_systemd(unit.require_original_owner(mac))?;
        let (loaded, selection) = mac.objects()?;
        let owner = ActualSystemdOwner::Package {
            unit,
            broker,
            deadline,
        };
        owner.within_deadline()?;
        let value = Self::capture(loaded, &owner)?;
        value.revalidate_actual(loaded, selection, &owner, mac.host_proc(), Some(mac))?;
        mac.revalidate()?;
        owner.within_deadline()?;
        Ok(value)
    }

    pub(super) fn revalidate_package_owner(
        &self,
        mac: &PackageMacOwner,
        unit: &PackageBrokerUnit,
        broker: &PackageProcess,
        deadline: Instant,
    ) -> Result<()> {
        mac.revalidate()?;
        require(
            deadline == mac.deadline(),
            "original package MAC deadline differs",
        )?;
        original_systemd(unit.require_original_owner(mac))?;
        let (loaded, selection) = mac.objects()?;
        let owner = ActualSystemdOwner::Package {
            unit,
            broker,
            deadline,
        };
        self.revalidate_actual(loaded, selection, &owner, mac.host_proc(), Some(mac))?;
        mac.revalidate()?;
        owner.within_deadline()
    }

    fn revalidate_actual(
        &self,
        loaded: &LoadedPolicyWitness,
        selection: &ProductionSelection,
        owner: &ActualSystemdOwner<'_, '_>,
        host_proc: Option<&host_proc::HostProcView>,
        package_mac: Option<&PackageMacOwner>,
    ) -> Result<()> {
        owner.within_deadline()?;
        require(
            self.provider == loaded.binding() && self.boot == loaded.boot,
            "systemd MAC witness belongs to another provider or boot",
        )?;
        loaded.revalidate(selection)?;
        owner.revalidate()?;
        require(
            owner.generation()? == self.generation,
            "original systemd manager/broker start or unit Invocation changed",
        )?;
        self.original_descriptors(owner)?;
        require(
            self.connection.kind == libc::S_IFSOCK,
            "actual manager connection is not a socket",
        )?;
        match (owner, package_mac) {
            (ActualSystemdOwner::Prepared(_), None) => {}
            (ActualSystemdOwner::Package { unit, .. }, Some(mac)) => {
                let (original_loaded, original_selection) = mac.objects()?;
                require(
                    std::ptr::eq(original_loaded, loaded)
                        && std::ptr::eq(original_selection, selection),
                    "package manager observation replaced its original MAC pair",
                )?;
                original_systemd(unit.require_original_owner(mac))?;
            }
            _ => {
                return Err(MacError::Rejected(
                    "systemd owner and original MAC issuer differ",
                ));
            }
        }
        if loaded.declaration.scoped_contexts()? {
            match (host_proc, owner, package_mac) {
                (Some(view), ActualSystemdOwner::Prepared(prepared), None) => {
                    view.for_systemd_owner(loaded, prepared)?;
                }
                (
                    Some(view),
                    ActualSystemdOwner::Package {
                        unit,
                        broker,
                        deadline,
                    },
                    Some(mac),
                ) => {
                    require(
                        mac.host_proc()
                            .is_some_and(|original| std::ptr::eq(original, view)),
                        "package manager observation replaced its original selected proc view",
                    )?;
                    view.for_package_unit(mac, unit, broker, *deadline)?;
                }
                _ => {
                    return Err(MacError::Rejected(
                        "scoped manager observation lacks its original typed host proc owner",
                    ));
                }
            }
        } else {
            require(
                host_proc.is_none(),
                "legacy manager route cannot adopt a selected proc",
            )?;
            require(
                context_matches(
                    &proc_attr(owner.manager_proc(), false)?,
                    loaded.declaration.manager(),
                ),
                "actual original PID1 is not in the fixed host SELinux domain",
            )?;
            require(
                proc_attr(owner.manager_proc(), true)? == AA_MANAGER,
                "actual original PID1 AppArmor identity differs",
            )?;
            require(
                context_matches(&proc_attr(owner.broker_proc(), false)?, BROKER)
                    && proc_attr(owner.broker_proc(), true)? == AA_BROKER,
                "original effective-unit broker differs from the live MAC broker",
            )?;
        }
        // This is SO_PEERSEC on the authenticated client end, cross-checked
        // with the original live PID1. Never fgetxattr the client socket and
        // call that the server's label.
        require(
            context_matches(
                &actual_socket_security(owner.manager_connection().as_fd())?,
                loaded.declaration.manager(),
            ),
            "authenticated private manager socket peer differs from original PID1",
        )?;
        require(
            context_matches(
                &manager_file_context(owner.manager_socket_file())?,
                MANAGER_FILE,
            ),
            "actual manager server sock_file lacks its fixed dedicated label",
        )?;
        systemd_decisions(loaded)?;
        owner.revalidate()?;
        require(
            owner.generation()? == self.generation,
            "systemd generation changed during live MAC observations",
        )?;
        self.original_descriptors(owner)?;
        loaded.revalidate(selection)?;
        owner.within_deadline()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::OpenOptionsExt;

    #[test]
    fn actual_manager_server_inode_rejects_client_socket_and_regular_fd() {
        let mut pair = [-1; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_STREAM | libc::SOCK_CLOEXEC,
                    0,
                    pair.as_mut_ptr(),
                )
            },
            0
        );
        let sockets = unsafe { [File::from_raw_fd(pair[0]), File::from_raw_fd(pair[1])] };
        // A connected client socket is a socket inode too. Its own label
        // must never substitute for the separately held server pathname inode.
        for client in &sockets {
            match manager_file_context(client) {
                Err(MacError::Rejected(
                    "manager server inode must remain an original O_PATH descriptor",
                )) => {}
                other => panic!("connected client was not rejected precisely: {other:?}"),
            }
        }
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("regular");
        std::fs::write(&path, b"not a manager socket").unwrap();
        let held = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)
            .unwrap();
        match manager_file_context(&held) {
            Err(MacError::Rejected("manager sock_file must be the actual held socket inode")) => {}
            other => panic!("regular O_PATH inode was not rejected precisely: {other:?}"),
        }
    }
}
