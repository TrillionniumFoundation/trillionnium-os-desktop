//! A read-only borrow of the original, actually executed init owner.
//!
//! This is deliberately separate from ReadyTreeWitness. MAC observation and
//! activation need the actual init before Android is ready, but possession of
//! this borrow cannot authorize an application command, another clone, a
//! namespace transition or a new execution. No descriptor is duplicated or
//! detached from the existing tree retirement path.

use super::*;
use sha2::{Digest, Sha256};

/// Equality is useful for binding observations to one original owner. The
/// fields and constructor are private: serializing these numbers or a digest
/// of them does not recreate a live owner capability.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct ExecutedInitGeneration {
    nonce: [u8; 16],
    identity: ProcessIdentity,
    proc_node: Node,
    pidfd_node: Node,
    user_node: Node,
    pid_node: Node,
}

impl ExecutedInitGeneration {
    /// Wire correlation only. The activation broker must also retain and
    /// revalidate the actual init borrow and actual helper peer PIDFD.
    pub(super) fn protocol_bytes(self) -> [u8; 32] {
        let mut digest = Sha256::new();
        digest.update(b"droidloom-owned-original-init-generation-v1\0");
        digest.update(self.nonce);
        digest.update(self.identity.pid.to_le_bytes());
        digest.update(self.identity.parent.to_le_bytes());
        digest.update(self.identity.start_ticks.to_le_bytes());
        for node in [
            self.proc_node,
            self.pidfd_node,
            self.user_node,
            self.pid_node,
        ] {
            digest.update(node.device.to_le_bytes());
            digest.update(node.inode.to_le_bytes());
        }
        digest.finalize().into()
    }
}

/// Issued only by ExecutedNamespaces::init_witness after the normal
/// authenticated ExecArmed, actual control CLOEXEC and original ELF check.
/// It borrows that same owner; an integer PID, supplied FD or recorded result
/// is never a constructor argument.
pub(crate) struct ExecutedInitWitness<'a> {
    owner: &'a ExecutedNamespaces,
    selection: &'a ProductionSelection,
}

impl ExecutedInitWitness<'_> {
    fn init(&self) -> &TreeChild {
        self.owner
            .tree
            .init
            .as_ref()
            .expect("executed owner retains init")
    }

    /// Rechecks the same creating thread, original PIDFD, held proc identity,
    /// maps, all held namespaces and existing live admission, then compares
    /// the actual executable to the original held init. This deliberately
    /// does not call the MAC observer, avoiding an admission recursion.
    ///
    /// The current strict namespace checks remain in force. An init-created
    /// default mount namespace needs the separately checked transition
    /// adapter; this accessor does not accept or adopt such a transition.
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.selection
            .revalidate()
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.owner.tree.verify_live_admission()?;
        let child = self.init();
        child.verify()?;
        let target = executable(child)?;
        self.owner
            .tree
            .runtime_observation
            .as_ref()
            .ok_or(NamespaceError::Rejected("executed runtime custody absent"))?
            .verify_executable_target(&target)?;
        drop(target);
        child.verify()
    }

    /// The init PIDFD, not the user-namespace keeper's PIDFD.
    pub(crate) fn pidfd(&self) -> BorrowedFd<'_> {
        self.init().pidfd.as_fd()
    }

    /// Readers must bracket observations with revalidate(). This is the
    /// original held proc inode, never a fresh lookup by a caller's PID.
    pub(crate) fn proc_directory(&self) -> &File {
        &self.init().proc_dir
    }

    pub(crate) fn user_namespace(&self) -> &File {
        &self.init().namespaces.userns
    }

    pub(crate) fn pid_namespace(&self) -> &File {
        self.init().pid_namespace()
    }

    pub(crate) fn mount_namespace(&self) -> Result<&File> {
        self.init()
            .namespaces
            .held
            .iter()
            .find(|row| row.1 == libc::CLONE_NEWNS)
            .map(|row| &row.3)
            .ok_or(NamespaceError::Rejected(
                "owned init mount namespace absent",
            ))
    }

    /// Compare-only data for the actual peer PIDFD info and SCM credentials.
    /// Neither value can authorize pidfd_open(), kill(), setns() or a command.
    pub(crate) fn host_pid(&self) -> u32 {
        self.init().identity.pid
    }

    pub(crate) fn mapped_root_ids(&self) -> (u32, u32) {
        (self.init().uids.start, self.init().gids.start)
    }

    /// The actual selected, sealed cohort retained by the owner issuer. MAC
    /// observations borrow this selection; no string or numeric identity can
    /// substitute for its live file and host-admission revalidation.
    pub(crate) fn selection(&self) -> &ProductionSelection {
        self.selection
    }

    /// Read-only custody for the fixed runtime input provider. That provider
    /// compares this actual object, not a digest or copied owner identifier.
    /// Shared access cannot transfer a mount or consume retirement authority.
    pub(crate) fn runtime_owner(
        &self,
    ) -> Result<&crate::production_runtime_assets::PreparedRuntime> {
        self.revalidate()?;
        self.owner
            .tree
            .runtime
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "original init runtime custody absent",
            ))
    }

    pub(crate) fn generation(&self) -> Result<ExecutedInitGeneration> {
        self.revalidate()?;
        let child = self.init();
        let mut metadata: libc::stat = unsafe { std::mem::zeroed() };
        if unsafe { libc::fstat(child.pidfd.as_raw_fd(), &mut metadata) } != 0 {
            return Err(io::Error::last_os_error().into());
        }
        let generation = ExecutedInitGeneration {
            nonce: child.nonce,
            identity: child.identity,
            proc_node: child.proc_node,
            pidfd_node: Node {
                device: metadata.st_dev,
                inode: metadata.st_ino,
            },
            user_node: child.namespaces.user_node,
            pid_node: Node::of(child.pid_namespace())?,
        };
        self.revalidate()?;
        Ok(generation)
    }
}

impl ExecutedNamespaces {
    /// Activation/MAC observation only. This is not a boot-complete check or
    /// an application executor, and no ReadyTreeWitness is issued here.
    pub(crate) fn init_witness<'a>(
        &'a mut self,
        selection: &'a ProductionSelection,
        admission: &ExecutionAdmission,
    ) -> Result<ExecutedInitWitness<'a>> {
        self.verify_exec(selection, admission)?;
        let witness = ExecutedInitWitness {
            owner: self,
            selection,
        };
        witness.revalidate()?;
        Ok(witness)
    }
}
