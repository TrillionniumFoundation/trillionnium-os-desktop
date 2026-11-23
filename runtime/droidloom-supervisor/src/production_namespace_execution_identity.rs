//! A read-only borrow of the original, actually executed init owner.
//!
//! This is deliberately separate from ReadyTreeWitness. MAC observation and
//! activation need the actual init before Android is ready, but possession of
//! this borrow cannot authorize an application command, another clone, a
//! namespace transition or a new execution. No descriptor is duplicated or
//! detached from the existing tree retirement path.

use super::*;
use sha2::{Digest, Sha256};

#[path = "production_namespace_execution_devices.rs"]
mod devices;
pub(crate) use devices::ExecutedDevObservation;

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
    pub(super) fn init(&self) -> &TreeChild {
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

    /// Reborrow the same original tree for the MAC/manager observer. This
    /// performs kernel/host admission only, never calls execution admission,
    /// and therefore cannot recursively authorize its own MAC observation.
    pub(crate) fn namespace_witness(&self) -> Result<OwnedNamespaceWitness<'_>> {
        self.revalidate()?;
        self.owner.tree.witness()
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
        self.revalidate()?;
        self.init().current_mount_namespace()
    }

    pub(crate) fn default_mount_authority(&self) -> Result<DefaultMountAuthority<'_>> {
        self.revalidate()?;
        self.init()
            .default_mounts
            .get()
            .ok_or(NamespaceError::Rejected(
                "original default epoch is not issued",
            ))?
            .authority(self.init())
    }

    /// The original private guest root, checked without admitting any changed
    /// mount inventory. The caller must qualify each fixed target separately.
    pub(crate) fn root_directory(&self) -> Result<File> {
        self.revalidate()?;
        let root = held_child_root(self.init())?;
        self.owner
            .tree
            .runtime_observation
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "executed runtime root custody absent",
            ))?
            .verify_private_root(&root)?;
        self.revalidate()?;
        Ok(root)
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

    /// Original source created by one of init's actual three mount calls.
    /// The caller must separately validate the current visible placement.
    pub(crate) fn original_init_activation_root(
        &self,
        role: crate::production_runtime_assets::ActivationRootRole,
    ) -> Result<File> {
        self.revalidate_capability_contract()?;
        let root = {
            let mounts =
                self.owner.initial_mounts.try_borrow().map_err(|_| {
                    NamespaceError::Rejected("original tmpfs phase already borrowed")
                })?;
            mounts.original_root(self, role)?
        };
        self.revalidate()?;
        Ok(root)
    }

    /// Read-only input custody from the exact admitted system and the same
    /// live guest pathname. The loop provider must still verify all bytes,
    /// filesystem protections and original metadata before binding a device.
    pub(crate) fn original_builtin_apex(&self, index: usize) -> Result<File> {
        self.original_system_apex(index, false)
    }

    /// Only a fixed compressed member from this same admitted readonly system.
    /// Its output still requires separate byte verification and kernel seals.
    pub(crate) fn original_compressed_apex(&self, index: usize) -> Result<File> {
        self.original_system_apex(index, true)
    }

    fn original_system_apex(&self, index: usize, compressed: bool) -> Result<File> {
        self.revalidate_capability_contract()?;
        let fixed = if compressed {
            crate::production_execution_profile::apex_inputs::original_compressed(index)
        } else {
            crate::production_execution_profile::apex_inputs::original_builtin(index)
        }
        .map_err(NamespaceError::Rejected)?;
        let witness = self.namespace_witness()?;
        let original = match self.owner.tree.bases.as_ref() {
            Some(BaseMounts::Admitted(bases)) => {
                let original = if compressed {
                    bases.original_compressed_apex(&witness, index)
                } else {
                    bases.original_builtin_apex(&witness, index)
                };
                original.map_err(|e| NamespaceError::MountResource(e.to_string()))?
            }
            _ => return Err(NamespaceError::HostAdmissionRequired),
        };
        let root = held_child_root(self.init())?;
        let system = fixed_at(&root, c"system", true, true)?;
        let apex = fixed_at(&system, c"apex", true, true)?;
        let name = std::ffi::CString::new(fixed.input.container_file)
            .map_err(|_| NamespaceError::Rejected("fixed original APEX filename"))?;
        let probe = fixed_at(&apex, &name, false, false)?;
        witness
            .identity_lease()?
            .broker_reject_backing_body(&probe)?;
        if !probe.metadata()?.is_file() || Node::of(&probe)? != Node::of(&original)? {
            return Err(NamespaceError::Rejected(
                "guest APEX differs from the held original system inode",
            ));
        }
        let source = fixed_at(&apex, &name, false, true)?;
        witness
            .identity_lease()?
            .broker_reject_backing_body(&source)?;
        if Node::of(&source)? != Node::of(&original)?
            || writable_proc::held_mount_id(&source)? != writable_proc::held_mount_id(&system)?
            || writable_proc::held_mount_id(&apex)? != writable_proc::held_mount_id(&system)?
        {
            return Err(NamespaceError::Rejected(
                "guest original APEX mount or inode was replaced",
            ));
        }
        self.revalidate()?;
        Ok(source)
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

    pub(crate) fn revalidate_linkerconfig_completion(&self) -> Result<()> {
        self.revalidate()?;
        let completed = self
            .owner
            .linkerconfig
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "original linkerconfig execution and retirement have not completed",
            ))?;
        let deadline = super::activation_channel::monotonic_ns()?
            .checked_add(crate::production_activation_protocol::RETIREMENT_NS)
            .ok_or(NamespaceError::Rejected(
                "activation completion observation clock overflow",
            ))?;
        completed.revalidate(self, deadline)
    }

    pub(crate) fn revalidate_capability_contract(&self) -> Result<()> {
        self.revalidate()?;
        let runtime = self
            .owner
            .tree
            .runtime
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "executed runtime profile lost owner custody",
            ))?;
        self.owner
            .execution_profile
            .revalidate(runtime, &self.namespace_witness()?)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        self.revalidate()
    }

    /// Read-only revalidation of the same owner's actually activated guest
    /// hierarchy and fixed init placement. This cannot adopt a caller's
    /// cgroup, move a thread or issue execution admission.
    pub(crate) fn revalidate_guest_cgroup(&self) -> Result<()> {
        self.revalidate()?;
        self.owner.tree.require_cgroup_hierarchy_ready()?;
        self.revalidate()
    }
}

impl ExecutedNamespaces {
    /// Activation/MAC observation only. This is not a boot-complete check or
    /// an application executor, and no ReadyTreeWitness is issued here.
    pub(crate) fn init_witness<'a>(
        &'a mut self,
        selection: &'a ProductionSelection,
        admission: &PreparedExecution,
    ) -> Result<ExecutedInitWitness<'a>> {
        self.verify_prepared_exec(selection, admission)?;
        self.original_init_witness(selection)
    }

    /// Only the actually executed owner can create this kernel-only borrow.
    /// Keeping it separate lets the final admission recheck actual init MAC
    /// without calling itself through verify_exec(). It grants no Ready state.
    pub(super) fn original_init_witness<'a>(
        &'a self,
        selection: &'a ProductionSelection,
    ) -> Result<ExecutedInitWitness<'a>> {
        let witness = ExecutedInitWitness {
            owner: self,
            selection,
        };
        witness.revalidate()?;
        Ok(witness)
    }
}
