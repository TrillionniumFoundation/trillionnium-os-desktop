//! PID-1 namespace construction after opaque user-namespace admission.
//!
//! This module is an unpublished preparation. Its privileged execution and
//! Android mounts/exec remain unqualified. The only creating process is the
//! previously attested fixed child; no external PID or serialized map grants
//! ownership. CLONE_PARENT makes the broker the actual parent of the new PID 1,
//! so waitid(P_PIDFD) proves its reap rather than trusting an intermediate exit.

use super::*;
use crate::production_devices::PreparedDevices;
use crate::production_mounts::PreparedMounts;
use crate::production_runtime_assets::PreparedRuntime;
use std::os::fd::BorrowedFd;
#[path = "production_namespace_binder_parent.rs"]
mod binder;
#[path = "production_namespace_execution_parent.rs"]
mod execution;
pub(crate) use execution::{ExecutedNamespaces, ReadyTreeWitness};
#[cfg(test)]
#[path = "production_namespace_postexec_parent.rs"]
mod private_postexec;
#[path = "production_namespace_runtime_parent.rs"]
mod runtime;
#[path = "production_namespace_writable_proc_parent.rs"]
mod writable_proc;

enum BaseMounts {
    Admitted(PreparedMounts),
    #[cfg(test)]
    PrivateControl(crate::production_mounts::private_control::PrivateControlMounts),
}
impl BaseMounts {
    fn descriptors<'a>(
        &'a mut self,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<[BorrowedFd<'a>; 2]> {
        match self {
            Self::Admitted(value) => value.descriptors_for_transfer(witness),
            #[cfg(test)]
            Self::PrivateControl(value) => value.descriptors_for_transfer(witness),
        }
        .map_err(|error| NamespaceError::MountResource(error.to_string()))
    }
    fn retire(self, retired: &RetiredTreeWitness<'_>) -> Result<()> {
        match self {
            Self::Admitted(value) => value.retire_after_tree(retired),
            #[cfg(test)]
            Self::PrivateControl(value) => value.retire_after_tree(retired),
        }
        .map(|_| ())
        .map_err(|error| NamespaceError::MountResource(error.to_string()))
    }
}

enum DeviceMounts {
    Admitted(PreparedDevices),
    #[cfg(test)]
    PrivateControl(crate::production_devices::private_control::PrivateControlDevices),
}
impl DeviceMounts {
    fn descriptor<'a>(&'a mut self, witness: &OwnedNamespaceWitness<'_>) -> Result<BorrowedFd<'a>> {
        match self {
            Self::Admitted(value) => value.descriptor_for_transfer(witness),
            #[cfg(test)]
            Self::PrivateControl(value) => value.descriptor_for_transfer(witness),
        }
        .map_err(|error| NamespaceError::DeviceResource(error.to_string()))
    }
    fn retire(self, retired: &RetiredTreeWitness<'_>) -> Result<()> {
        match self {
            Self::Admitted(value) => value.retire_after_tree(retired),
            #[cfg(test)]
            Self::PrivateControl(value) => value.retire_after_tree(retired),
        }
        .map(|_| ())
        .map_err(|error| NamespaceError::DeviceResource(error.to_string()))
    }
}

const PIDFD_GET_INFO: libc::c_ulong = 0xc050_ff0b;
const PIDFD_THREAD: u32 = libc::O_EXCL as u32;
const NS_GET_USERNS: libc::c_ulong = 0xb701;

#[repr(C)]
#[derive(Default)]
struct PidfdInfo {
    mask: u64,
    cgroup_id: u64,
    pid: u32,
    tgid: u32,
    ppid: u32,
    ruid: u32,
    rgid: u32,
    euid: u32,
    egid: u32,
    suid: u32,
    sgid: u32,
    fsuid: u32,
    fsgid: u32,
    exit_code: i32,
    coredump_mask: u32,
    coredump_signal: u32,
    supported_mask: u64,
}
const _: () = assert!(std::mem::size_of::<PidfdInfo>() == 80);

fn pidfd_info(fd: RawFd) -> Result<PidfdInfo> {
    let mut value = PidfdInfo {
        mask: 3,
        ..PidfdInfo::default()
    };
    // SAFETY: the UAPI structure is an initialized 80-byte output, and fd is
    // borrowed. Unsupported kernels reject this; there is no numeric fallback.
    if unsafe { libc::ioctl(fd, PIDFD_GET_INFO, &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if value.mask & 3 != 3 || value.pid <= 1 || value.tgid <= 1 {
        return Err(NamespaceError::Rejected("incomplete live pidfd identity"));
    }
    Ok(value)
}

/// Six actually held child-owned namespaces. No public constructor or FD export.
struct NamespaceSet {
    held: Vec<(&'static str, libc::c_int, libc::c_ulong, File, Node)>,
    userns: File,
    user_node: Node,
}

impl NamespaceSet {
    fn bind(pidfd: &OwnedFd, userns: &File, parent_thread: &OwnedFd) -> Result<Self> {
        let user = from_pidfd(pidfd, 0xff09, libc::CLONE_NEWUSER)?;
        let user_node = Node::of(userns)?;
        if Node::of(&user)? != user_node {
            return Err(NamespaceError::Rejected(
                "PID 1 has a foreign user namespace",
            ));
        }
        let descriptors = [
            ("pid", libc::CLONE_NEWPID, 0xff05),
            ("mnt", libc::CLONE_NEWNS, 0xff03),
            ("ipc", libc::CLONE_NEWIPC, 0xff02),
            ("uts", libc::CLONE_NEWUTS, 0xff0a),
            ("net", libc::CLONE_NEWNET, 0xff04),
            ("cgroup", libc::CLONE_NEWCGROUP, 0xff01),
        ];
        let mut held = Vec::new();
        for (name, kind, command) in descriptors {
            let file = from_pidfd(pidfd, command, kind)?;
            let node = Node::of(&file)?;
            let original = from_pidfd(parent_thread, command, kind)?;
            if node == Node::of(&original)? {
                return Err(NamespaceError::Rejected(
                    "required namespace was shared with the broker",
                ));
            }
            require_namespace_owner(&file, user_node)?;
            if kind == libc::CLONE_NEWPID {
                // Only the direct child of the broker's PID namespace is valid.
                let actual_parent = namespace_ioctl(&file, NS_GET_PARENT)?;
                if Node::of(&actual_parent)? != Node::of(&original)? {
                    return Err(NamespaceError::Rejected(
                        "new PID namespace has a foreign parent",
                    ));
                }
            }
            held.push((name, kind, command, file, node));
        }
        Ok(Self {
            held,
            userns: user,
            user_node,
        })
    }

    fn release_live_views_after_reap(&mut self) {
        // Holding mntns after its PID 1 has actually reaped would keep every
        // attached image mounted and prevent exact owned-loop retirement.
        // PIDns and userns still bind the opaque retirement witness.
        self.held.retain(|row| row.1 == libc::CLONE_NEWPID);
    }

    fn verify(&self, pidfd: &OwnedFd) -> Result<()> {
        if Node::of(&self.userns)? != self.user_node
            || Node::of(&from_pidfd(pidfd, 0xff09, libc::CLONE_NEWUSER)?)? != self.user_node
        {
            return Err(NamespaceError::Rejected(
                "PID 1 changed its admitted user namespace",
            ));
        }
        for (_, kind, command, file, expected) in &self.held {
            if Node::of(file)? != *expected
                || Node::of(&from_pidfd(pidfd, *command, *kind)?)? != *expected
            {
                return Err(NamespaceError::Rejected("held process namespace changed"));
            }
            require_namespace_owner(file, self.user_node)?;
        }
        Ok(())
    }
}

fn namespace_ioctl(file: &File, command: libc::c_ulong) -> Result<File> {
    // SAFETY: these two nsfs ioctls return an owned descriptor, never a PID.
    let fd = unsafe { libc::ioctl(file.as_raw_fd(), command, 0 as libc::c_ulong) };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: successful ioctl returned a new descriptor.
    let held = unsafe { File::from_raw_fd(fd) };
    check_fs(held.as_raw_fd(), NSFS_MAGIC)?;
    Ok(held)
}

fn require_namespace_owner(file: &File, expected: Node) -> Result<()> {
    let owner = namespace_ioctl(file, NS_GET_USERNS)?;
    if Node::of(&owner)? != expected {
        return Err(NamespaceError::Rejected(
            "namespace belongs to another user namespace",
        ));
    }
    Ok(())
}

fn from_pidfd(pidfd: &OwnedFd, command: libc::c_ulong, kind: libc::c_int) -> Result<File> {
    // SAFETY: PIDFD_GET_*_NAMESPACE returns a new nsfs FD for this held process.
    let raw = unsafe { libc::ioctl(pidfd.as_raw_fd(), command, 0 as libc::c_ulong) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    // SAFETY: successful descriptor-returning ioctl.
    let file = unsafe { File::from_raw_fd(raw) };
    check_fs(file.as_raw_fd(), NSFS_MAGIC)?;
    if unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) } != kind {
        return Err(NamespaceError::Rejected(
            "pidfd returned the wrong namespace type",
        ));
    }
    Ok(file)
}

/// Own both the mapped keeper and its PID-1 child until both are reaped.
/// Only opaque admitted base mounts and fresh empty tmpfs data may be added.
/// No original-data or Android exec input, and no runtime-qualified result.
pub(crate) struct IsolatedNamespaces {
    keeper: Option<MappedUserNamespace>,
    init: Option<TreeChild>,
    // Set only by successful actual waitid(P_PIDFD) of this exact PID 1.
    reaped_init: Option<ChildExit>,
    bases: Option<BaseMounts>,
    base_devices: Option<[u64; 2]>,
    devices: Option<DeviceMounts>,
    empty_root: bool,
    private_devices: bool,
    device_node: Option<Node>,
    process_filesystems: Option<ProcessFilesystems>,
    binder: Option<binder::BinderFilesystem>,
    writable_proc: Option<writable_proc::WritableProc>,
    runtime: Option<PreparedRuntime>,
    runtime_observation: Option<runtime::RuntimeObservation>,
}

/// Borrow created only from the READY owner, never from a numeric PID list.
pub(crate) struct CgroupTreeReadyWitness<'a> {
    tree: &'a IsolatedNamespaces,
}
impl CgroupTreeReadyWitness<'_> {
    pub(crate) fn revalidate_for_migration(&self, expected_payload: &File) -> Result<()> {
        let keeper = self
            .tree
            .keeper
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        keeper.owner.verify_kernel_owned()?;
        let child = self
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        child.verify()?;
        let r = keeper.owner.held()?;
        if self.tree.reaped_init.is_some()
            || r.tree_lifecycle.get() != TreeLifecycle::Bound
            || Node::of(
                r.clone_target
                    .as_ref()
                    .ok_or(NamespaceError::RetirementUnproven)?,
            )? != Node::of(expected_payload)?
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        let proof = r.tree_proof.borrow();
        let proof = proof.as_ref().ok_or(NamespaceError::RetirementUnproven)?;
        if proof.identity != child.identity
            || Node::of(&proof.pid_namespace)? != Node::of(child.pid_namespace())?
            || proof.exit.is_some()
            || pidfd_exited(&proof.pidfd)?
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        // Location before/after is checked by the cgroup capability itself.
        // No admission recursion: migration is deliberately InProgress here.
        Ok(())
    }
    pub(crate) fn keeper_host_pid(&self) -> u32 {
        self.tree
            .keeper
            .as_ref()
            .unwrap()
            .owner
            .resources
            .as_ref()
            .unwrap()
            .pid
    }
    pub(crate) fn tree_host_pid(&self) -> u32 {
        self.tree.init.as_ref().unwrap().identity.pid
    }
    pub(crate) fn keeper_proc_directory(&self) -> &File {
        self.tree
            .keeper
            .as_ref()
            .unwrap()
            .owner
            .resources
            .as_ref()
            .unwrap()
            .proc_dir
            .as_ref()
            .unwrap()
    }
    pub(crate) fn tree_proc_directory(&self) -> &File {
        &self.tree.init.as_ref().unwrap().proc_dir
    }
    pub(crate) fn keeper_pidfd(&self) -> BorrowedFd<'_> {
        self.tree
            .keeper
            .as_ref()
            .unwrap()
            .owner
            .resources
            .as_ref()
            .unwrap()
            .pidfd
            .as_fd()
    }
    pub(crate) fn tree_pidfd(&self) -> BorrowedFd<'_> {
        self.tree.init.as_ref().unwrap().pidfd.as_fd()
    }
    pub(crate) fn keeper_start_ticks(&self) -> u64 {
        self.tree
            .keeper
            .as_ref()
            .unwrap()
            .owner
            .resources
            .as_ref()
            .unwrap()
            .identity
            .unwrap()
            .start_ticks
    }
    pub(crate) fn tree_start_ticks(&self) -> u64 {
        self.tree.init.as_ref().unwrap().identity.start_ticks
    }
}

impl Owner {
    fn note_tree_requested(&self) -> Result<()> {
        let r = self.held()?;
        if r.tree_lifecycle.get() != TreeLifecycle::NeverRequested
            || r.tree_proof.borrow().is_some()
        {
            return Err(NamespaceError::Rejected(
                "only one owned PID1 may be requested",
            ));
        }
        r.tree_lifecycle.set(TreeLifecycle::MayExist);
        Ok(())
    }
    fn note_tree_bound(&self, child: &TreeChild) -> Result<()> {
        let r = self.held()?;
        if r.tree_lifecycle.get() != TreeLifecycle::MayExist || r.tree_proof.borrow().is_some() {
            return Err(NamespaceError::RetirementUnproven);
        }
        let proof = TreeRetirementProof {
            pidfd: child.pidfd.try_clone()?,
            pid_namespace: child.pid_namespace().try_clone()?,
            identity: child.identity,
            exit: None,
        };
        *r.tree_proof.borrow_mut() = Some(proof);
        r.tree_lifecycle.set(TreeLifecycle::Bound);
        Ok(())
    }
    fn note_tree_reaped(&self, child: &TreeChild, exit: &ChildExit) -> Result<()> {
        let r = self.held()?;
        if !matches!(
            r.tree_lifecycle.get(),
            TreeLifecycle::Bound | TreeLifecycle::Reaped
        ) || !pidfd_exited(&child.pidfd)?
            || exit.pid != child.identity.pid
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        let mut proof = r.tree_proof.borrow_mut();
        let proof = proof.as_mut().ok_or(NamespaceError::RetirementUnproven)?;
        if proof.identity != child.identity
            || Node::of(&proof.pid_namespace)? != Node::of(child.pid_namespace())?
            || !pidfd_exited(&proof.pidfd)?
            || proof.exit.as_ref().is_some_and(|old| old != exit)
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        proof.exit = Some(ChildExit {
            pid: exit.pid,
            status: exit.status,
            reason: exit.reason,
        });
        r.tree_lifecycle.set(TreeLifecycle::Reaped);
        Ok(())
    }
}

pub(crate) struct RetiredTreeWitness<'a> {
    tree: &'a IsolatedNamespaces,
}

impl RetiredTreeWitness<'_> {
    /// Permit only teardown of mounts captured for this same reaped tree.
    /// The scalar inputs are comparisons, never evidence of process ownership.
    pub(crate) fn verify_mount_retirement(
        &self,
        userns: &File,
        host_uid: u32,
        cohort: &str,
    ) -> Result<()> {
        let keeper = self
            .tree
            .keeper
            .as_ref()
            .ok_or(NamespaceError::Rejected("keeper custody absent"))?;
        keeper.owner.verify_kernel_owned()?;
        let r = keeper.owner.held()?;
        let init = self
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::Rejected("init custody absent"))?;
        let exit = self
            .tree
            .reaped_init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        if exit.pid != init.identity.pid
            || !matches!(
                exit.reason,
                libc::CLD_EXITED | libc::CLD_KILLED | libc::CLD_DUMPED
            )
            || !pidfd_exited(&init.pidfd)?
            || init.proc_context.is_some()
            || init.proc_mount.is_some()
            || init
                .namespaces
                .held
                .iter()
                .any(|row| row.1 != libc::CLONE_NEWPID)
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        let keeper_ns = r
            .userns
            .as_ref()
            .ok_or(NamespaceError::Rejected("keeper user namespace absent"))?;
        let expected_ns = Node::of(keeper_ns)?;
        if Node::of(userns)? != expected_ns || expected_ns != init.namespaces.user_node {
            return Err(NamespaceError::Rejected(
                "retired tree user namespace differs from mounted inputs",
            ));
        }
        let lease = r
            .authority
            .lease()
            .ok_or(NamespaceError::HostAdmissionRequired)?;
        if lease.host_uid() != host_uid || lease.broker_cohort() != cohort {
            return Err(NamespaceError::Rejected(
                "retired tree identity or cohort differs from mounted inputs",
            ));
        }
        // No new map/namespace authority is issued here. A changed public grant
        // must not redirect teardown to another process or block this already-
        // owned tree's retirement; the actual custody and immutable lease
        // binding determine which mounts may be released.
        Ok(())
    }
}

pub(super) struct TreeChild {
    pidfd: OwnedFd,
    control: OwnedFd,
    proc_root: File,
    proc_dir: File,
    proc_node: Node,
    identity: ProcessIdentity,
    parent_pid: u32,
    creator_tid: libc::pid_t,
    nonce: [u8; 16],
    uids: IdRange,
    gids: IdRange,
    namespaces: NamespaceSet,
    proc_context: Option<File>,
    proc_mount: Option<File>,
    #[cfg(test)]
    exited_before_barrier: std::cell::Cell<bool>,
}

#[derive(Debug)]
pub(crate) struct TreeExit {
    pub(crate) init: ChildExit,
    pub(crate) keeper: ChildExit,
}

impl IsolatedNamespaces {
    /// Consume an actually mapped keeper; callers cannot provide PID/map values.
    pub(crate) fn from_mapped(keeper: MappedUserNamespace) -> Result<Self> {
        keeper.owner.verify_owned()?;
        keeper.owner.verify_live_admission()?;
        let r = keeper.owner.held()?;
        let lease = r
            .authority
            .lease()
            .ok_or(NamespaceError::Rejected("held lease required"))?;
        let (uids, gids) = lease.broker_ranges();
        verify_map(&read_proc(r.proc_dir.as_ref().unwrap(), "uid_map")?, uids)?;
        verify_map(&read_proc(r.proc_dir.as_ref().unwrap(), "gid_map")?, gids)?;
        if read_proc(r.proc_dir.as_ref().unwrap(), "setgroups")? != b"allow\n" {
            return Err(NamespaceError::Rejected(
                "setgroups allow required for process-tree construction",
            ));
        }
        let parent_pidfd = self_thread_pidfd(r)?;
        let packet = Packet::new(r.nonce, Phase::PrepareTree, 0, r.parent_pid);
        // From this point a PID-1 child might exist even if its descriptor never
        // arrives. A failure cannot release the keeper's lease.
        keeper.owner.note_tree_requested()?;
        let mut known_child: Option<TreeChild> = None;
        let created: Result<()> = (|| {
            send_one_fd(r.control.as_raw_fd(), &packet, parent_pidfd.as_fd())?;
            let (pidfd, control) = receive_created_fds(&keeper.owner, uids.start, gids.start)?;
            // After bind, child ownership is established even if the later
            // ready/metadata qualification fails. Retain it for actual reap.
            known_child = Some(TreeChild::bind(
                &keeper.owner,
                pidfd,
                control,
                &parent_pidfd,
                uids,
                gids,
            )?);
            let child = known_child.as_mut().unwrap();
            keeper.owner.note_tree_bound(child)?;
            child.wait_ready()?;
            child.verify()?;
            keeper.owner.verify_owned()?;
            Ok(())
        })();
        match created {
            Ok(()) => {
                let value = Self {
                    keeper: Some(keeper),
                    init: known_child,
                    reaped_init: None,
                    bases: None,
                    base_devices: None,
                    devices: None,
                    empty_root: false,
                    private_devices: false,
                    device_node: None,
                    process_filesystems: None,
                    binder: None,
                    writable_proc: None,
                    runtime: None,
                    runtime_observation: None,
                };
                // Only now may the live audit consume the PID-namespace scope.
                // A rejection drops this whole owner and reaps PID 1 first.
                value.verify_live_admission()?;
                Ok(value)
            }
            Err(error) => {
                if let Some(mut child) = known_child.take() {
                    if let Ok(exit) = child.retire() {
                        keeper.owner.note_tree_reaped(&child, &exit)?;
                        // The only inner child has actually been reaped.
                        // Ordinary keeper Drop now proves its own exit too.
                        drop(child);
                        drop(keeper);
                        return Err(error);
                    }
                    std::mem::forget(child);
                }
                // A creation may have happened without a fully bound pidfd,
                // or the bound child did not prove exit. Keep the identity
                // reserved. Never signal an unvalidated numeric process.
                let _ = keeper.owner.send(Phase::Stop);
                let mut keeper = keeper;
                if let Some(resources) = keeper.owner.resources.take() {
                    std::mem::forget(resources);
                }
                Err(error)
            }
        }
    }

    /// Assemble only verified immutable bases and fresh tmpfs data. This API
    /// has no original-data, runtime, device or Android exec input.
    pub(crate) fn attach_empty_base(self, bases: PreparedMounts) -> Result<Self> {
        self.attach_base_inner(BaseMounts::Admitted(bases))
    }

    fn attach_base_inner(mut self, mut bases: BaseMounts) -> Result<Self> {
        self.verify_live_admission()?;
        if self.bases.is_some() || self.empty_root {
            return Err(NamespaceError::Rejected(
                "base descriptors already transferred",
            ));
        }
        let transfer: Result<[u64; 2]> = (|| {
            let witness = self.witness()?;
            let descriptors = bases.descriptors(&witness)?;
            let devices = [
                descriptor_device(descriptors[0])?,
                descriptor_device(descriptors[1])?,
            ];
            let child = self
                .init
                .as_ref()
                .ok_or(NamespaceError::Rejected("PID 1 absent"))?;
            let packet = Packet::new(child.nonce, Phase::MountEmptyBase, 0, child.parent_pid);
            send_base_fds(child.control.as_raw_fd(), &packet, descriptors)?;
            Ok(devices)
        })();
        // A send failure may still have reached the peer. The mount owner must
        // stay attached to this exact tree until its real PIDFD exit is proven.
        self.bases = Some(bases);
        let devices = transfer?;
        self.init
            .as_mut()
            .ok_or(NamespaceError::Rejected("PID 1 absent"))?
            .wait_empty_root_ready(devices)?;
        self.base_devices = Some(devices);
        self.empty_root = true;
        self.verify_live_admission()?;
        Ok(self)
    }

    /// Transfer only a descriptor from the admitted device resource for this
    /// same tree. A parked empty root is required; no arbitrary FD is accepted.
    pub(crate) fn attach_private_devices(self, devices: PreparedDevices) -> Result<Self> {
        self.attach_device_inner(DeviceMounts::Admitted(devices))
    }

    fn attach_device_inner(mut self, mut devices: DeviceMounts) -> Result<Self> {
        self.verify_live_admission()?;
        if !self.empty_root || self.devices.is_some() || self.private_devices {
            return Err(NamespaceError::Rejected(
                "private devices require one empty-root barrier",
            ));
        }
        let base_devices = self
            .base_devices
            .ok_or(NamespaceError::Rejected("base descriptor custody absent"))?;
        let transferred: Result<Node> = (|| {
            let witness = self.witness()?;
            let fd = devices.descriptor(&witness)?;
            let expected = descriptor_node(fd)?;
            let child = self
                .init
                .as_ref()
                .ok_or(NamespaceError::Rejected("PID 1 absent"))?;
            let packet = Packet::new(child.nonce, Phase::MountPrivateDev, 0, child.parent_pid);
            send_one_fd(child.control.as_raw_fd(), &packet, fd)?;
            Ok(expected)
        })();
        // A failed send may have delivered the mount; retain its real guard
        // before returning any error so only actual tree reap permits cleanup.
        self.devices = Some(devices);
        let expected = transferred?;
        self.init
            .as_mut()
            .ok_or(NamespaceError::Rejected("PID 1 absent"))?
            .wait_private_devices_ready(base_devices, expected)?;
        self.private_devices = true;
        self.device_node = Some(expected);
        self.verify_live_admission()?;
        Ok(self)
    }

    /// Create PID-bound read-only proc and one new devpts instance inside the
    /// already owned child. There is no external FD/path/map or exec argument.
    pub(crate) fn prepare_process_filesystems(mut self) -> Result<Self> {
        self.verify_live_admission()
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        if !self.empty_root || !self.private_devices || self.process_filesystems.is_some() {
            return Err(NamespaceError::Rejected(
                "process filesystems require one private DEV barrier",
            ));
        }
        let bases = self
            .base_devices
            .ok_or(NamespaceError::Rejected("base custody absent"))?;
        let dev = self
            .device_node
            .ok_or(NamespaceError::Rejected("private DEV custody absent"))?;
        {
            let child = self
                .init
                .as_ref()
                .ok_or(NamespaceError::Rejected("PID 1 absent"))?;
            child.verify_empty_root_mounts(bases, Some(dev), None)?;
            let root = held_child_root(child)?;
            verify_attached_devices(
                &root_subdirectory(&root, c"dev")?,
                child.uids.start,
                child.gids.start,
                dev,
                false,
            )?;
            send_packet(
                child.control.as_raw_fd(),
                &Packet::new(
                    child.nonce,
                    Phase::PrepareProcessFilesystems,
                    0,
                    child.parent_pid,
                ),
            )?;
        }
        // The exact owned raw PID 1 selects its own PID namespace when it creates
        // this proc superblock. No caller-supplied FD, path, PID or flags enter.
        self.init
            .as_mut()
            .ok_or(NamespaceError::Rejected("PID 1 absent"))?
            .receive_proc_context()
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        self.verify_live_admission()?;
        {
            let witness = self.witness()?;
            witness.identity_lease()?.broker_reject_backing_body(
                self.init
                    .as_ref()
                    .unwrap()
                    .proc_context
                    .as_ref()
                    .ok_or(NamespaceError::Rejected("owned proc context absent"))?,
            )?;
        }
        // The already-authorized root broker materializes only a detached mount.
        // It neither enters the child mount namespace nor changes a host mount.
        let resources = self
            .keeper
            .as_ref()
            .ok_or(NamespaceError::Rejected("keeper absent"))?
            .owner
            .held()?;
        let initial_user = resources
            .parent_userns
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "initial user namespace custody absent",
            ))?;
        require_privileged_initial_parent(&resources.proc_root, initial_user)?;
        let caller = self_thread_pidfd(resources)?;
        let broker_mnt = from_pidfd(&caller, 0xff03, libc::CLONE_NEWNS)?;
        require_namespace_owner(&broker_mnt, Node::of(initial_user)?)?;
        let broker_mnt_node = Node::of(&broker_mnt)?;
        let expected_proc = self
            .init
            .as_mut()
            .unwrap()
            .materialize_proc_context()
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        if Node::of(&from_pidfd(&caller, 0xff03, libc::CLONE_NEWNS)?)? != broker_mnt_node {
            return Err(NamespaceError::Rejected("broker mount namespace changed"));
        }
        let child = self.init.as_ref().unwrap();
        child
            .receive_phase(Phase::ProcessFilesystemsReady)
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let observed = child
            .verify_process_filesystems(bases, dev, None)
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        if observed.proc != expected_proc {
            return Err(NamespaceError::Rejected(
                "attached proc differs from broker-held mount",
            ));
        }
        self.process_filesystems = Some(observed);
        self.verify_live_admission()?;
        Ok(self)
    }

    pub(crate) fn configure_cgroup_hierarchy(&self) -> Result<()> {
        self.verify_live_admission()?;
        let r = self
            .keeper
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .owner
            .held()?;
        let witness = CgroupTreeReadyWitness { tree: self };
        match &r.authority {
            HeldAuthority::Budgeted(cgroup) => {
                cgroup
                    .move_keeper_outside(&witness)
                    .map_err(|e| NamespaceError::CgroupResource(e.to_string()))?;
                cgroup
                    .delegate_guest_hierarchy(&witness)
                    .map_err(|e| NamespaceError::CgroupResource(e.to_string()))?;
                self.verify_live_admission()
            }
            #[cfg(test)]
            _ => Err(NamespaceError::HostAdmissionRequired),
        }
    }

    pub(crate) fn witness(&self) -> Result<OwnedNamespaceWitness<'_>> {
        self.verify()?;
        Ok(OwnedNamespaceWitness {
            owner: &self
                .keeper
                .as_ref()
                .ok_or(NamespaceError::Rejected("tree retired"))?
                .owner,
            tree: Some(
                self.init
                    .as_ref()
                    .ok_or(NamespaceError::Rejected("PID 1 absent"))?,
            ),
        })
    }

    fn verify_live_admission(&self) -> Result<()> {
        let witness = self.witness()?;
        self.keeper
            .as_ref()
            .ok_or(NamespaceError::Rejected("tree retired"))?
            .owner
            .held()?
            .authority
            .revalidate_live(&witness)
    }

    pub(crate) fn verify(&self) -> Result<()> {
        if self.reaped_init.is_some() {
            return Err(NamespaceError::Rejected("PID 1 has already been reaped"));
        }
        self.keeper
            .as_ref()
            .ok_or(NamespaceError::Rejected("tree retired"))?
            .owner
            .verify_owned()?;
        self.init
            .as_ref()
            .ok_or(NamespaceError::Rejected("PID 1 absent"))?
            .verify()
    }

    /// Reap PID 1 while preserving the live keeper, identity and namespace FDs.
    /// The returned borrow cannot outlive or move independently of this owner.
    pub(crate) fn reap_init(&mut self) -> Result<RetiredTreeWitness<'_>> {
        if self.reaped_init.is_none() {
            let result = self
                .init
                .as_mut()
                .ok_or(NamespaceError::Rejected("PID 1 custody absent"))?
                .retire();
            match result {
                Ok(exit) => self.reaped_init = Some(exit),
                Err(error) => {
                    self.quarantine();
                    return Err(error);
                }
            }
        }
        self.keeper
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .owner
            .note_tree_reaped(
                self.init
                    .as_ref()
                    .ok_or(NamespaceError::RetirementUnproven)?,
                self.reaped_init
                    .as_ref()
                    .ok_or(NamespaceError::RetirementUnproven)?,
            )?;
        self.init
            .as_mut()
            .ok_or(NamespaceError::RetirementUnproven)?
            .release_live_views_after_reap();
        if let Err(error) = self.retire_runtime_after_reap() {
            self.quarantine();
            return Err(error);
        }
        Ok(RetiredTreeWitness { tree: self })
    }

    pub(crate) fn retire(mut self) -> Result<TreeExit> {
        let result = self.retire_inner();
        if result.is_err() {
            self.quarantine();
        }
        result
    }

    fn retire_runtime_after_reap(&mut self) -> Result<()> {
        if self.reaped_init.is_none() {
            return Err(NamespaceError::RetirementUnproven);
        }
        // These held role/source FDs pin the same runtime mount. Close them
        // only after actual PIDFD reap and before asking loop/mount retirement.
        self.runtime_observation.take();
        if let Some(runtime) = self.runtime.take() {
            runtime
                .retire_after_tree(&RetiredTreeWitness { tree: self })
                .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        }
        Ok(())
    }

    fn retire_inner(&mut self) -> Result<TreeExit> {
        if self.reaped_init.is_none() {
            let exit = self
                .init
                .as_mut()
                .ok_or(NamespaceError::Rejected("PID 1 custody absent"))?
                .retire()?;
            self.reaped_init = Some(exit);
        }
        self.keeper
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .owner
            .note_tree_reaped(
                self.init
                    .as_ref()
                    .ok_or(NamespaceError::RetirementUnproven)?,
                self.reaped_init
                    .as_ref()
                    .ok_or(NamespaceError::RetirementUnproven)?,
            )?;
        self.init
            .as_mut()
            .ok_or(NamespaceError::RetirementUnproven)?
            .release_live_views_after_reap();
        self.retire_runtime_after_reap()?;
        if let Some(devices) = self.devices.take() {
            devices.retire(&RetiredTreeWitness { tree: self })?;
        }
        if let Some(bases) = self.bases.take() {
            bases.retire(&RetiredTreeWitness { tree: self })?;
        }
        let prior = self.reaped_init.as_ref().unwrap();
        let init = ChildExit {
            pid: prior.pid,
            status: prior.status,
            reason: prior.reason,
        };
        // PIDFD/PIDns/userns stay held until keeper reap. Live-only namespace
        // references were closed after actual init reap, then exact loop
        // teardown released the additional reservation reference.
        let keeper = self
            .keeper
            .as_mut()
            .ok_or(NamespaceError::Rejected("keeper retired"))?
            .owner
            .retire()?;
        self.init.take();
        self.keeper.take();
        Ok(TreeExit { init, keeper })
    }

    fn quarantine(&mut self) {
        if let Some(observation) = self.runtime_observation.take() {
            std::mem::forget(observation);
        }
        if let Some(runtime) = self.runtime.take() {
            std::mem::forget(runtime);
        }
        // Neither component is dropped separately: an unproven inner exit must
        // not let the outer Owner's normal Drop release the shared identity.
        if let Some(devices) = self.devices.take() {
            std::mem::forget(devices);
        }
        if let Some(bases) = self.bases.take() {
            std::mem::forget(bases);
        }
        if let Some(init) = self.init.take() {
            std::mem::forget(init);
        }
        if let Some(mut keeper) = self.keeper.take() {
            if let Some(resources) = keeper.owner.resources.take() {
                std::mem::forget(resources);
            }
        }
    }
}
impl Drop for IsolatedNamespaces {
    fn drop(&mut self) {
        if self.keeper.is_some() && self.retire_inner().is_err() {
            self.quarantine();
        }
    }
}

fn self_thread_pidfd(r: &Resources) -> Result<OwnedFd> {
    if unsafe { libc::syscall(libc::SYS_gettid) } != libc::c_long::from(r.creator_tid) {
        return Err(NamespaceError::Rejected("creator thread changed"));
    }
    // This is the currently executing thread, not an external PID or a
    // fallback used to acquire child authority. Its FD only closes a PDEATHSIG
    // race for the nested child whose parent is outside its PID namespace.
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, r.creator_tid, PIDFD_THREAD) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let held = unsafe { OwnedFd::from_raw_fd(raw as i32) };
    let info = pidfd_info(held.as_raw_fd())?;
    if info.pid != r.creator_tid as u32 || info.tgid != r.parent_pid {
        return Err(NamespaceError::Rejected(
            "self thread pidfd identity differs",
        ));
    }
    Ok(held)
}

impl TreeChild {
    fn bind(
        keeper: &Owner,
        pidfd: OwnedFd,
        control: OwnedFd,
        parent_thread: &OwnedFd,
        uids: IdRange,
        gids: IdRange,
    ) -> Result<Self> {
        keeper.verify_owned()?;
        let r = keeper.held()?;
        let info = pidfd_info(pidfd.as_raw_fd())?;
        if info.pid != info.tgid || info.pid == r.pid || info.ppid != r.parent_pid {
            return Err(NamespaceError::Rejected(
                "received pidfd is not a new direct broker child",
            ));
        }
        require_pidfd_creds(&info, uids.start, gids.start)?;
        require_control_socket(&control)?;
        let proc_root = r.proc_root.try_clone()?;
        let proc_dir = open_proc_at(
            &proc_root,
            &info.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let identity = read_identity(&proc_dir, info.pid)?;
        if identity.parent != r.parent_pid {
            return Err(NamespaceError::Rejected(
                "PID 1 proc parent differs from clone parent",
            ));
        }
        let namespaces = NamespaceSet::bind(&pidfd, r.userns.as_ref().unwrap(), parent_thread)?;
        let value = Self {
            pidfd,
            control,
            proc_root,
            proc_node: Node::of(&proc_dir)?,
            proc_dir,
            identity,
            parent_pid: r.parent_pid,
            creator_tid: r.creator_tid,
            nonce: r.nonce,
            uids,
            gids,
            namespaces,
            proc_context: None,
            proc_mount: None,
            #[cfg(test)]
            exited_before_barrier: std::cell::Cell::new(false),
        };
        // This is the custody boundary; subsequent qualification failures
        // are handled by the caller with this retained, now-owned child.
        Ok(value)
    }

    pub(super) fn pid_namespace(&self) -> &File {
        // NamespaceSet::bind creates exactly one held entry of every kind.
        &self
            .namespaces
            .held
            .iter()
            .find(|row| row.1 == libc::CLONE_NEWPID)
            .expect("bound PID namespace")
            .3
    }

    pub(super) fn verify(&self) -> Result<()> {
        if unsafe { libc::syscall(libc::SYS_gettid) } != libc::c_long::from(self.creator_tid) {
            return Err(NamespaceError::Rejected(
                "tree moved away from its creating thread",
            ));
        }
        if pidfd_exited(&self.pidfd)? {
            #[cfg(test)]
            self.exited_before_barrier.set(true);
            return Err(NamespaceError::Rejected("PID 1 exited"));
        }
        let info = pidfd_info(self.pidfd.as_raw_fd())?;
        if info.pid != self.identity.pid
            || info.tgid != self.identity.pid
            || info.ppid != self.parent_pid
        {
            return Err(NamespaceError::Rejected("PID 1 pidfd ownership changed"));
        }
        require_pidfd_creds(&info, self.uids.start, self.gids.start)?;
        if Node::of(&self.proc_dir)? != self.proc_node
            || read_identity(&self.proc_dir, self.identity.pid)? != self.identity
        {
            return Err(NamespaceError::Rejected("PID 1 held proc identity changed"));
        }
        let named = open_proc_at(
            &self.proc_root,
            &self.identity.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        if Node::of(&named)? != self.proc_node {
            return Err(NamespaceError::Rejected("PID 1 proc name was replaced"));
        }
        self.namespaces.verify(&self.pidfd)?;
        verify_map(&read_proc(&self.proc_dir, "uid_map")?, self.uids)?;
        verify_map(&read_proc(&self.proc_dir, "gid_map")?, self.gids)?;
        if read_proc(&self.proc_dir, "setgroups")? != b"allow\n" {
            return Err(NamespaceError::Rejected("PID 1 lost setgroups allow"));
        }
        let status = read_proc(&self.proc_dir, "status")?;
        let ids = status_field(&status, "NSpid:")?
            .split_ascii_whitespace()
            .map(str::parse::<u32>)
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|_| NamespaceError::Rejected("malformed PID namespace identity"))?;
        if ids != [self.identity.pid, 1] {
            return Err(NamespaceError::Rejected(
                "owned process is not exactly the new PID 1",
            ));
        }
        Ok(())
    }

    fn wait_ready(&mut self) -> Result<()> {
        wait_readable(&self.control, &self.pidfd)?;
        let (packet, creds) = receive_packet(self.control.as_raw_fd())?;
        if !packet.matches(self.nonce, 1)
            || creds.pid != self.identity.pid as i32
            || creds.uid != self.uids.start
            || creds.gid != self.gids.start
        {
            return Err(NamespaceError::Rejected(
                "PID 1 ready peer identity differs",
            ));
        }
        if packet.phase == Phase::Failed as u32 && packet.errno > 0 {
            return Err(io::Error::from_raw_os_error(packet.errno).into());
        }
        if packet.phase != Phase::TreeReady as u32 || packet.errno != 0 {
            return Err(NamespaceError::Rejected(
                "PID 1 did not reach its fixed barrier",
            ));
        }
        require_empty_groups(&read_proc(&self.proc_dir, "status")?)?;
        // The child only made propagation private; it has not mounted an image
        // or read any user data. Inherited shared/slave propagation is forbidden.
        let mounts = read_proc(&self.proc_dir, "mountinfo")?;
        let text = std::str::from_utf8(&mounts)
            .map_err(|_| NamespaceError::Rejected("non-text mountinfo"))?;
        if text.is_empty() {
            return Err(NamespaceError::Rejected("empty mountinfo"));
        }
        for line in text.lines() {
            let (left, _) = line
                .split_once(" - ")
                .ok_or(NamespaceError::Rejected("incomplete mountinfo"))?;
            if left.split_ascii_whitespace().skip(6).any(|p| {
                p.starts_with("shared:")
                    || p.starts_with("master:")
                    || p.starts_with("propagate_from:")
            }) {
                return Err(NamespaceError::Rejected(
                    "new mount namespace still propagates to its parent",
                ));
            }
        }
        Ok(())
    }

    fn retire(&mut self) -> Result<ChildExit> {
        let _ = send_packet(
            self.control.as_raw_fd(),
            &Packet::new(self.nonce, Phase::Stop, 0, self.parent_pid),
        );
        if !wait_exited(&self.pidfd, RETIRE_TIMEOUT)? {
            signal_owned(&self.pidfd, libc::SIGKILL)?;
            if !wait_exited(&self.pidfd, RETIRE_TIMEOUT)? {
                return Err(NamespaceError::RetirementUnproven);
            }
        }
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        } != 0
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        let (pid, status) = unsafe { (info.si_pid(), info.si_status()) };
        if pid != self.identity.pid as i32
            || !matches!(
                info.si_code,
                libc::CLD_EXITED | libc::CLD_KILLED | libc::CLD_DUMPED
            )
        {
            return Err(NamespaceError::RetirementUnproven);
        }
        // Linux zap_pid_ns_processes waits for the remaining namespace tasks
        // before its child_reaper may be reaped. This is actual PIDFD reap,
        // not a claim based on an empty process-name search.
        let exit = ChildExit {
            pid: self.identity.pid,
            status,
            reason: info.si_code,
        };
        #[cfg(test)]
        if self.exited_before_barrier.get() || exit.reason != libc::CLD_EXITED || exit.status != 0 {
            eprintln!(
                "private owned-tree retirement: {}",
                private_retired_failure_diagnostic(
                    &self.control,
                    &exit,
                    self.nonce,
                    1,
                    self.uids.start,
                    self.gids.start
                )
            );
        }
        Ok(exit)
    }
}

fn require_pidfd_creds(info: &PidfdInfo, uid: u32, gid: u32) -> Result<()> {
    if [info.ruid, info.euid, info.suid, info.fsuid] != [uid; 4]
        || [info.rgid, info.egid, info.sgid, info.fsgid] != [gid; 4]
    {
        return Err(NamespaceError::Rejected(
            "PID 1 kernel credentials differ from the held lease",
        ));
    }
    Ok(())
}

fn require_control_socket(fd: &OwnedFd) -> Result<()> {
    for (key, expected) in [
        (libc::SO_TYPE, libc::SOCK_SEQPACKET),
        (libc::SO_DOMAIN, libc::AF_UNIX),
        (libc::SO_PASSCRED, 1),
    ] {
        let mut got = 0_i32;
        let mut len = std::mem::size_of::<i32>() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                fd.as_raw_fd(),
                libc::SOL_SOCKET,
                key,
                (&mut got as *mut i32).cast(),
                &mut len,
            )
        } != 0
            || len != std::mem::size_of::<i32>() as libc::socklen_t
            || got != expected
        {
            return Err(NamespaceError::Rejected(
                "received tree control descriptor is not the private credentialled socket",
            ));
        }
    }
    Ok(())
}

fn wait_readable(control: &OwnedFd, pidfd: &OwnedFd) -> Result<()> {
    wait_readable_until(control, pidfd, Instant::now() + PROTOCOL_TIMEOUT)
}

fn wait_readable_until(control: &OwnedFd, pidfd: &OwnedFd, deadline: Instant) -> Result<()> {
    loop {
        let now = Instant::now();
        if now >= deadline {
            return Err(io::Error::new(io::ErrorKind::TimedOut, "tree protocol deadline").into());
        }
        let millis = (deadline - now).as_millis().min(100) as i32;
        let mut events = [
            libc::pollfd {
                fd: control.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: pidfd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            },
        ];
        let rc = unsafe { libc::poll(events.as_mut_ptr(), 2, millis) };
        if rc < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e.into());
        }
        if events
            .iter()
            .any(|e| e.revents & (libc::POLLNVAL | libc::POLLERR) != 0)
        {
            return Err(NamespaceError::Rejected("tree descriptor failed"));
        }
        if events[0].revents & libc::POLLIN != 0 {
            return Ok(());
        }
        if events[0].revents & libc::POLLHUP != 0
            || events[1].revents & (libc::POLLIN | libc::POLLHUP) != 0
        {
            return Err(NamespaceError::Rejected(
                "tree child exited before its barrier",
            ));
        }
    }
}

// Only the private PID-1 control endpoint calls this receiver. It grants no
// authority by itself: TreeChild checks the actual PIDFD identity, nonce,
// SCM_CREDENTIALS, phase and single descriptor before any fsmount call.
fn receive_proc_context_record(fd: RawFd) -> Result<(Packet, libc::ucred, Option<File>)> {
    let mut packet = Packet::zeroed();
    let mut iov = libc::iovec {
        iov_base: (&mut packet as *mut Packet).cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 32];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = ancillary.as_mut_ptr().cast();
    msg.msg_controllen = std::mem::size_of_val(&ancillary);
    let n = unsafe { libc::recvmsg(fd, &mut msg, libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC) };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mut credentials = None;
    let mut descriptors = Vec::new();
    let mut rights_records = 0_usize;
    let mut bad = msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0;
    let mut header = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    while !header.is_null() {
        let h = unsafe { &*header };
        let base = unsafe { libc::CMSG_LEN(0) } as usize;
        if h.cmsg_len < base {
            bad = true;
            break;
        }
        let length = h.cmsg_len - base;
        let bytes = unsafe { libc::CMSG_DATA(header) };
        if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS {
            rights_records += 1;
            if length % std::mem::size_of::<i32>() != 0 {
                bad = true;
            }
            // Adopt every kernel-delivered descriptor even when rejecting a
            // malformed record; Vec drop closes all of them on every error.
            for i in 0..length / std::mem::size_of::<i32>() {
                let raw = unsafe {
                    std::ptr::read_unaligned(
                        bytes.add(i * std::mem::size_of::<i32>()).cast::<i32>(),
                    )
                };
                if raw < 0 {
                    bad = true;
                } else {
                    descriptors.push(unsafe { File::from_raw_fd(raw) });
                }
            }
        } else if h.cmsg_level == libc::SOL_SOCKET
            && h.cmsg_type == libc::SCM_CREDENTIALS
            && length == std::mem::size_of::<libc::ucred>()
            && credentials.is_none()
        {
            credentials = Some(unsafe { std::ptr::read_unaligned(bytes.cast::<libc::ucred>()) });
        } else {
            bad = true;
        }
        header = unsafe { libc::CMSG_NXTHDR(&msg, header) };
    }
    if bad || n as usize != std::mem::size_of::<Packet>() {
        return Err(NamespaceError::Rejected(
            "malformed proc context control record",
        ));
    }
    let credentials =
        credentials.ok_or(NamespaceError::Rejected("proc context credentials absent"))?;
    if packet.phase == Phase::Failed as u32
        && packet.errno > 0
        && descriptors.is_empty()
        && rights_records == 0
    {
        return Ok((packet, credentials, None));
    }
    if packet.phase != Phase::ProcContextReady as u32
        || packet.errno != 0
        || descriptors.len() != 1
        || rights_records != 1
    {
        return Err(NamespaceError::Rejected(
            "proc context needs exactly one fixed-phase descriptor",
        ));
    }
    Ok((packet, credentials, descriptors.pop()))
}

fn require_proc_context_shape(context: &File, proc_root: &File) -> Result<()> {
    // This shape check is only an early rejection. Kernel fsmount checks
    // fscontext_fops; provenance comes from the owned raw child and phase.
    let name = std::ffi::CString::new(format!("thread-self/fd/{}", context.as_raw_fd()))
        .map_err(|_| NamespaceError::Rejected("proc context descriptor name"))?;
    let mut target = [0_u8; 64];
    let count = unsafe {
        libc::readlinkat(
            proc_root.as_raw_fd(),
            name.as_ptr(),
            target.as_mut_ptr().cast(),
            target.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let flags = unsafe { libc::fcntl(context.as_raw_fd(), libc::F_GETFL) };
    let descriptor_flags = unsafe { libc::fcntl(context.as_raw_fd(), libc::F_GETFD) };
    if flags < 0 || descriptor_flags < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if count as usize != b"anon_inode:[fscontext]".len()
        || &target[..count as usize] != b"anon_inode:[fscontext]"
        || flags & libc::O_ACCMODE != libc::O_RDWR
        || descriptor_flags & libc::FD_CLOEXEC == 0
    {
        return Err(NamespaceError::Rejected(
            "proc context descriptor shape differs",
        ));
    }
    Ok(())
}

#[cfg(test)]
fn private_retired_failure_diagnostic(
    control: &OwnedFd,
    exit: &ChildExit,
    nonce: [u8; 16],
    packet_pid: u32,
    uid: u32,
    gid: u32,
) -> String {
    // This is called only after actual waitid(P_PIDFD) reap. It grants no
    // authority, sends nothing, and never changes the failed result. A queued
    // context is closed only now, under the same completed retirement.
    let status = format!(
        "actual owned PIDFD reap code={} status={}",
        exit.reason, exit.status
    );
    let mut notes = Vec::new();
    for _ in 0..2 {
        let mut event = libc::pollfd {
            fd: control.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        if unsafe { libc::poll(&mut event, 1, 0) } != 1 || event.revents & libc::POLLIN == 0 {
            break;
        }
        match receive_proc_context_record(control.as_raw_fd()) {
            Ok((packet, credentials, descriptor)) => {
                drop(descriptor);
                if !packet.matches(nonce, packet_pid)
                    || credentials.pid != exit.pid as i32
                    || credentials.uid != uid
                    || credentials.gid != gid
                {
                    notes.push("pending record peer/nonce rejected");
                    break;
                }
                if packet.phase == Phase::Failed as u32 && packet.errno > 0 {
                    let message = match child::processfs_private_failure(packet.errno) {
                        Some((stage, line, errno)) => {
                            format!("stage={stage} source-line={line} errno={errno}")
                        }
                        None => match child::binder_private_failure(packet.errno) {
                            Some((stage, line, errno)) => {
                                format!("binder stage={stage} source-line={line} errno={errno}")
                            }
                            None => match child::writable_proc_private_failure(packet.errno) {
                                Some((stage, line, errno)) => format!(
                                    "writable proc stage={stage} source-line={line} errno={errno}"
                                ),
                                None => match child::postexec_private_failure(packet.errno) {
                                    Some((stage, line, errno)) => format!(
                                        "post-exec stage={stage} source-line={line} errno={errno}"
                                    ),
                                    None => format!("errno={}", packet.errno),
                                },
                            },
                        },
                    };
                    return format!("{status}; authenticated queued Failed: {message}");
                }
                notes.push("authenticated context closed unused after actual reap");
            }
            Err(NamespaceError::Io(error)) if error.kind() == io::ErrorKind::WouldBlock => break,
            Err(_) => notes.push("pending non-failure/descriptor record rejected"),
        }
    }
    format!("{status}; no authenticated queued Failed; {notes:?}")
}

fn send_one_fd(socket: RawFd, packet: &Packet, fd: BorrowedFd<'_>) -> Result<()> {
    let mut iov = libc::iovec {
        iov_base: (packet as *const Packet).cast_mut().cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 8];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = ancillary.as_mut_ptr().cast();
    msg.msg_controllen = unsafe { libc::CMSG_SPACE(std::mem::size_of::<i32>() as u32) } as usize;
    let h = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    unsafe {
        (*h).cmsg_level = libc::SOL_SOCKET;
        (*h).cmsg_type = libc::SCM_RIGHTS;
        (*h).cmsg_len = libc::CMSG_LEN(std::mem::size_of::<i32>() as u32) as usize;
        std::ptr::write_unaligned(libc::CMSG_DATA(h).cast::<i32>(), fd.as_raw_fd());
    }
    let rc = unsafe { libc::sendmsg(socket, &msg, libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT) };
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if rc as usize != std::mem::size_of::<Packet>() {
        return Err(NamespaceError::Rejected("short tree construction request"));
    }
    Ok(())
}

fn descriptor_node(fd: BorrowedFd<'_>) -> Result<Node> {
    let mut value: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstat(fd.as_raw_fd(), &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if value.st_mode & libc::S_IFMT != libc::S_IFDIR {
        return Err(NamespaceError::Rejected(
            "private dev descriptor is not a directory",
        ));
    }
    Ok(Node {
        device: value.st_dev,
        inode: value.st_ino,
    })
}

fn descriptor_device(fd: BorrowedFd<'_>) -> Result<u64> {
    let mut value: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstat(fd.as_raw_fd(), &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(value.st_dev)
}

fn send_base_fds(socket: RawFd, packet: &Packet, fds: [BorrowedFd<'_>; 2]) -> Result<()> {
    let mut iov = libc::iovec {
        iov_base: (packet as *const Packet).cast_mut().cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut control = [0_usize; 8];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = control.as_mut_ptr().cast();
    msg.msg_controllen = unsafe { libc::CMSG_SPACE(8) } as usize;
    let h = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    unsafe {
        (*h).cmsg_level = libc::SOL_SOCKET;
        (*h).cmsg_type = libc::SCM_RIGHTS;
        (*h).cmsg_len = libc::CMSG_LEN(8) as usize;
        let data = libc::CMSG_DATA(h).cast::<i32>();
        std::ptr::write_unaligned(data, fds[0].as_raw_fd());
        std::ptr::write_unaligned(data.add(1), fds[1].as_raw_fd());
    }
    let n = unsafe { libc::sendmsg(socket, &msg, libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT) };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if n as usize != std::mem::size_of::<Packet>() {
        return Err(NamespaceError::Rejected(
            "incomplete fixed base descriptor transfer",
        ));
    }
    Ok(())
}

fn held_child_root(child: &TreeChild) -> Result<File> {
    child.verify()?;
    // Deliberately follow only this already PIDFD-bound proc inode's kernel
    // "root" link. No arbitrary process or caller pathname is accepted.
    let fd = unsafe {
        libc::openat(
            child.proc_dir.as_raw_fd(),
            c"root".as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    child.verify()?;
    Ok(file)
}

fn root_subdirectory(root: &File, name: &std::ffi::CStr) -> Result<File> {
    let fd = unsafe {
        libc::openat(
            root.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY
                | libc::O_DIRECTORY
                | libc::O_NOFOLLOW
                | libc::O_CLOEXEC
                | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}

fn filesystem_kind(file: &File) -> Result<libc::c_long> {
    let mut value: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(value.f_type)
}

impl TreeChild {
    fn release_live_views_after_reap(&mut self) {
        // Called only after this exact PIDFD's waitid reap, before creating a
        // RetiredTreeWitness. Unknown exit quarantines the whole TreeChild.
        self.proc_context.take();
        self.proc_mount.take();
        self.namespaces.release_live_views_after_reap();
    }

    fn receive_proc_context(&mut self) -> Result<()> {
        self.verify()?;
        if self.proc_context.is_some() || self.proc_mount.is_some() {
            return Err(NamespaceError::Rejected(
                "proc context was already consumed",
            ));
        }
        wait_readable(&self.control, &self.pidfd)?;
        let (packet, credentials, context) = receive_proc_context_record(self.control.as_raw_fd())?;
        if !packet.matches(self.nonce, 1)
            || credentials.pid != self.identity.pid as i32
            || credentials.uid != self.uids.start
            || credentials.gid != self.gids.start
        {
            return Err(NamespaceError::Rejected(
                "proc context peer identity differs",
            ));
        }
        if packet.phase == Phase::Failed as u32 && packet.errno > 0 {
            #[cfg(test)]
            if let Some((stage, line, errno)) = child::processfs_private_failure(packet.errno) {
                let cause = io::Error::from_raw_os_error(errno);
                return Err(io::Error::new(
                    cause.kind(),
                    format!(
                        "processfs child stage={stage} source-line={line} errno={errno}: {cause}"
                    ),
                )
                .into());
            }
            return Err(io::Error::from_raw_os_error(packet.errno).into());
        }
        if packet.phase != Phase::ProcContextReady as u32 || packet.errno != 0 {
            return Err(NamespaceError::Rejected("proc context phase differs"));
        }
        self.proc_context =
            Some(context.ok_or(NamespaceError::Rejected("proc context descriptor absent"))?);
        self.verify()
    }

    fn materialize_proc_context(&mut self) -> Result<Node> {
        self.verify()?;
        if self.proc_mount.is_some() {
            return Err(NamespaceError::Rejected("proc mount already materialized"));
        }
        let context = self
            .proc_context
            .as_ref()
            .ok_or(NamespaceError::Rejected("owned proc context absent"))?;
        require_proc_context_shape(context, &self.proc_root)?;
        // The only privileged operation delegated by this phase. These flags
        // are compile-time constants, never derived from a packet or JSON.
        let raw = unsafe {
            libc::syscall(
                libc::SYS_fsmount,
                context.as_raw_fd(),
                1_u32,
                1_u32 | 2 | 4 | 8,
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        if raw > i32::MAX as libc::c_long {
            return Err(NamespaceError::Rejected(
                "fsmount returned invalid descriptor",
            ));
        }
        self.proc_mount = Some(unsafe { File::from_raw_fd(raw as i32) });
        // Child closed its copy before waiting. Consume the context exactly
        // once; retain the mount itself through send failure and actual reap.
        self.proc_context.take();
        let mount = self.proc_mount.as_ref().unwrap();
        let expected = self.verify_owned_proc_mount(mount)?;
        self.verify()?;
        send_one_fd(
            self.control.as_raw_fd(),
            &Packet::new(self.nonce, Phase::ProcMountReady, 0, self.parent_pid),
            mount.as_fd(),
        )?;
        self.verify()?;
        Ok(expected)
    }

    fn verify_owned_proc_mount(&self, proc: &File) -> Result<Node> {
        self.verify()?;
        verify_process_statfs(proc, 0x9fa0, 1 | 2 | 4 | 8, 0)?;
        let node = Node::of(proc)?;
        if node.device == self.proc_root.metadata()?.dev() {
            return Err(NamespaceError::Rejected("private proc aliases broker proc"));
        }
        let one = root_subdirectory(proc, c"1")?;
        let ns = root_subdirectory(&one, c"ns")?;
        let pid = fixed_namespace_link(&ns, c"pid", libc::CLONE_NEWPID)?;
        let user = fixed_namespace_link(&ns, c"user", libc::CLONE_NEWUSER)?;
        let held_pid = self
            .namespaces
            .held
            .iter()
            .find(|row| row.1 == libc::CLONE_NEWPID)
            .ok_or(NamespaceError::Rejected(
                "owned PID namespace custody absent",
            ))?;
        if Node::of(&pid)? != held_pid.4 || Node::of(&user)? != self.namespaces.user_node {
            return Err(NamespaceError::Rejected(
                "detached proc does not describe owned PID 1",
            ));
        }
        let entries = root_subdirectory(proc, c".")?;
        let mut pids = std::collections::BTreeSet::new();
        let mut count = 0_usize;
        for entry in std::fs::read_dir(format!("/proc/self/fd/{}", entries.as_raw_fd()))? {
            count += 1;
            if count > 4096 {
                return Err(NamespaceError::Rejected("private proc listing bound"));
            }
            let name = entry?.file_name();
            use std::os::unix::ffi::OsStrExt;
            let bytes = name.as_bytes();
            if !bytes.is_empty() && bytes.iter().all(u8::is_ascii_digit) {
                pids.insert(name);
            }
        }
        if pids != std::collections::BTreeSet::from([std::ffi::OsString::from("1")]) {
            return Err(NamespaceError::Rejected(
                "detached proc contains foreign process IDs",
            ));
        }
        self.verify()?;
        Ok(node)
    }

    fn receive_phase(&self, wanted: Phase) -> Result<()> {
        wait_readable(&self.control, &self.pidfd)?;
        let (packet, credentials) = receive_packet(self.control.as_raw_fd())?;
        if !packet.matches(self.nonce, 1)
            || credentials.pid != self.identity.pid as i32
            || credentials.uid != self.uids.start
            || credentials.gid != self.gids.start
        {
            return Err(NamespaceError::Rejected("empty-root peer identity differs"));
        }
        if packet.phase == Phase::Failed as u32 && packet.errno > 0 {
            #[cfg(test)]
            if let Some((stage, source_line, errno)) =
                child::processfs_private_failure(packet.errno)
            {
                let source = io::Error::from_raw_os_error(errno);
                return Err(io::Error::new(
                    source.kind(),
                    format!("processfs child stage={stage} source-line={source_line} errno={errno}: {source}"),
                ).into());
            }
            #[cfg(test)]
            if let Some((stage, source_line, errno)) = child::binder_private_failure(packet.errno) {
                let source = io::Error::from_raw_os_error(errno);
                return Err(io::Error::new(source.kind(),
                    format!("binder child stage={stage} source-line={source_line} errno={errno}: {source}")).into());
            }
            #[cfg(test)]
            if let Some((stage, line, errno)) = child::writable_proc_private_failure(packet.errno) {
                let source = io::Error::from_raw_os_error(errno);
                return Err(io::Error::new(source.kind(),format!("writable proc child stage={stage} source-line={line} errno={errno}: {source}")).into());
            }
            #[cfg(test)]
            if let Some((stage, line, errno)) = child::runtime_private_failure(packet.errno) {
                let source = io::Error::from_raw_os_error(errno);
                return Err(io::Error::new(
                    source.kind(),
                    format!(
                        "runtime child stage={stage} source-line={line} errno={errno}: {source}"
                    ),
                )
                .into());
            }
            #[cfg(test)]
            if let Some((stage, line, errno)) = child::postexec_private_failure(packet.errno) {
                return Err(io::Error::other(format!("authenticated post-exec child Failed: stage={stage} source-line={line} errno={errno}")).into());
            }
            return Err(io::Error::from_raw_os_error(packet.errno).into());
        }
        if packet.phase != wanted as u32 || packet.errno != 0 {
            return Err(NamespaceError::Rejected(
                "empty-root protocol barrier differs",
            ));
        }
        Ok(())
    }

    fn wait_empty_root_ready(&mut self, devices: [u64; 2]) -> Result<()> {
        self.receive_phase(Phase::EmptyRootReady)?;
        self.verify_empty_root_mounts(devices, None, None)
    }

    fn wait_private_devices_ready(&mut self, bases: [u64; 2], devices: Node) -> Result<()> {
        self.receive_phase(Phase::PrivateDevReady)?;
        self.verify_empty_root_mounts(bases, Some(devices), None)?;
        let root = held_child_root(self)?;
        let private_dev = root_subdirectory(&root, c"dev")?;
        verify_attached_devices(
            &private_dev,
            self.uids.start,
            self.gids.start,
            devices,
            false,
        )?;
        self.verify()
    }

    fn verify_empty_root_mounts(
        &self,
        devices: [u64; 2],
        private_dev: Option<Node>,
        process_fs: Option<ProcessFilesystems>,
    ) -> Result<()> {
        self.verify_empty_root_mounts_with_binder(devices, private_dev, process_fs, None)
    }

    fn verify_empty_root_mounts_with_binder(
        &self,
        devices: [u64; 2],
        private_dev: Option<Node>,
        process_fs: Option<ProcessFilesystems>,
        binder: Option<binder::BinderFilesystem>,
    ) -> Result<()> {
        self.verify()?;
        let root = held_child_root(self)?;
        let data = root_subdirectory(&root, c"data")?;
        let metadata = root_subdirectory(&root, c"metadata")?;
        let system = root_subdirectory(&root, c"system")?;
        let vendor = root_subdirectory(&root, c"vendor")?;
        let mut private_devices = Vec::new();
        for file in [&root, &data, &metadata] {
            let stat = file.metadata()?;
            if filesystem_kind(file)? != 0x0102_1994
                || stat.uid() != self.uids.start
                || stat.gid() != self.gids.start
                || devices.contains(&stat.dev())
                || private_devices.contains(&stat.dev())
            {
                return Err(NamespaceError::Rejected(
                    "root/data/metadata are not distinct owned tmpfs",
                ));
            }
            private_devices.push(stat.dev());
        }
        if system.metadata()?.dev() != devices[0] || vendor.metadata()?.dev() != devices[1] {
            return Err(NamespaceError::Rejected(
                "assembled bases differ from transferred descriptors",
            ));
        }
        let mut private_paths = vec![
            ("/", private_devices[0]),
            ("/data", private_devices[1]),
            ("/metadata", private_devices[2]),
        ];
        if let Some(expected) = private_dev {
            let dev = root_subdirectory(&root, c"dev")?;
            if Node::of(&dev)? != expected
                || private_devices.contains(&expected.device)
                || devices.contains(&expected.device)
                || filesystem_kind(&dev)? != 0x0102_1994
            {
                return Err(NamespaceError::Rejected(
                    "private dev mount differs from transferred descriptor",
                ));
            }
            private_paths.push(("/dev", expected.device));
        }
        let mut observed_private = std::collections::BTreeSet::new();
        let mut observed_process = std::collections::BTreeSet::new();
        let mut observed_binder = false;
        let mounts = read_proc(&self.proc_dir, "mountinfo")?;
        let text = std::str::from_utf8(&mounts)
            .map_err(|_| NamespaceError::Rejected("non-text guest mount inventory"))?;
        if text.is_empty() {
            return Err(NamespaceError::Rejected("empty guest mount inventory"));
        }
        for line in text.lines() {
            let (left, right) = line
                .split_once(" - ")
                .ok_or(NamespaceError::Rejected("incomplete guest mount inventory"))?;
            let fields: Vec<_> = left.split_ascii_whitespace().collect();
            let right: Vec<_> = right.split_ascii_whitespace().collect();
            if fields.len() < 6 || right.len() < 3 {
                return Err(NamespaceError::Rejected("incomplete guest mount fields"));
            }
            if fields.iter().skip(6).any(|f| {
                f.starts_with("shared:")
                    || f.starts_with("master:")
                    || f.starts_with("propagate_from:")
            }) {
                return Err(NamespaceError::Rejected("guest mount propagation changed"));
            }
            let (major, minor) = fields[2]
                .split_once(':')
                .ok_or(NamespaceError::Rejected("invalid guest filesystem device"))?;
            let device = libc::makedev(
                major
                    .parse::<u32>()
                    .map_err(|_| NamespaceError::Rejected("guest major"))?,
                minor
                    .parse::<u32>()
                    .map_err(|_| NamespaceError::Rejected("guest minor"))?,
            );
            if right[0] == "binder" {
                let expected =
                    binder.ok_or(NamespaceError::Rejected("unadmitted Binder filesystem"))?;
                if observed_binder
                    || device != expected.root.device
                    || !binder::mount_options(fields[4], fields[3], fields[5], right[2])
                {
                    return Err(NamespaceError::Rejected(
                        "private Binder mount options or instance differ",
                    ));
                }
                observed_binder = true;
                continue;
            }
            if ["proc", "devpts"].contains(&right[0]) {
                let expected =
                    process_fs.ok_or(NamespaceError::Rejected("unadmitted process filesystem"))?;
                let expected_device = match (right[0], fields[4]) {
                    ("proc", "/proc") => expected.proc.device,
                    ("devpts", "/dev/pts") => expected.pts.device,
                    _ => {
                        return Err(NamespaceError::Rejected(
                            "process filesystem at unexpected target",
                        ));
                    }
                };
                if device != expected_device
                    || !observed_process.insert(fields[4])
                    || !process_mount_options(
                        right[0],
                        fields[4],
                        fields[5],
                        right[2],
                        self.uids.start,
                        self.gids.start,
                    )
                {
                    return Err(NamespaceError::Rejected(
                        "process filesystem mount options or instance differ",
                    ));
                }
                continue;
            }
            if right[0] == "tmpfs" {
                if !private_paths.contains(&(fields[4], device))
                    || !observed_private.insert(fields[4])
                {
                    return Err(NamespaceError::Rejected("unexpected guest writable mount"));
                }
            } else if !["ext4", "erofs"].contains(&right[0])
                || !devices.contains(&device)
                || !["ro", "nosuid", "nodev"]
                    .iter()
                    .all(|flag| fields[5].split(',').any(|v| v == *flag))
            {
                return Err(NamespaceError::Rejected(
                    "inherited or unverified guest mount",
                ));
            }
        }
        if observed_binder != binder.is_some() {
            return Err(NamespaceError::Rejected("expected Binder mount absent"));
        }
        if observed_process.len() != if process_fs.is_some() { 2 } else { 0 } {
            return Err(NamespaceError::Rejected(
                "missing expected process filesystem",
            ));
        }
        if observed_private.len() != private_paths.len() {
            return Err(NamespaceError::Rejected("missing expected private mount"));
        }
        self.verify()
    }
}

fn verify_attached_devices(
    root: &File,
    uid: u32,
    gid: u32,
    expected: Node,
    with_process_fs: bool,
) -> Result<()> {
    verify_attached_devices_with_binder(root, uid, gid, expected, with_process_fs, None)
}

fn verify_attached_devices_with_binder(
    root: &File,
    uid: u32,
    gid: u32,
    expected: Node,
    with_process_fs: bool,
    binder: Option<binder::BinderFilesystem>,
) -> Result<()> {
    if binder.is_some() && !with_process_fs {
        return Err(NamespaceError::Rejected(
            "Binder requires process filesystems",
        ));
    }
    if let Some(value) = binder {
        if Node::of(&root_subdirectory(root, c"binderfs")?)? != value.root {
            return Err(NamespaceError::Rejected(
                "private Binder directory differs from held observation",
            ));
        }
    }
    if Node::of(root)? != expected || filesystem_kind(root)? != 0x0102_1994 {
        return Err(NamespaceError::Rejected(
            "exact private dev filesystem required",
        ));
    }
    let meta = root.metadata()?;
    if meta.mode() != (libc::S_IFDIR | 0o755) || meta.uid() != uid || meta.gid() != gid {
        return Err(NamespaceError::Rejected(
            "private dev root identity differs",
        ));
    }
    let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatvfs(root.as_raw_fd(), &mut flags) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if flags.f_flag as u64 & (2 | 8) != 2 | 8
        || flags.f_flag as u64 & (1 | 4) != 0
        || (flags.f_blocks as u64).checked_mul(flags.f_frsize as u64) != Some(64 * 1024 * 1024)
        || flags.f_files != 16_384
    {
        return Err(NamespaceError::Rejected(
            "private dev flags or bounded capacity changed",
        ));
    }
    let specs = [
        (c"null", 1, 3),
        (c"zero", 1, 5),
        (c"full", 1, 7),
        (c"random", 1, 8),
        (c"urandom", 1, 9),
        (c"tty", 5, 0),
        (c"fuse", 10, 229),
    ];
    // open a new file description for a complete directory read. /proc is
    // reached only through our own held directory FD, never a guest-supplied PID.
    let directory = root_subdirectory(root, c".")?;
    let names = std::fs::read_dir(format!("/proc/self/fd/{}", directory.as_raw_fd()))?
        .take(8 + if with_process_fs { 2 } else { 0 } + if binder.is_some() { 4 } else { 0 })
        .map(|entry| entry.map(|entry| entry.file_name()))
        .collect::<io::Result<std::collections::BTreeSet<_>>>()?;
    let mut expected_names = specs
        .iter()
        .map(|(name, _, _)| {
            std::ffi::OsString::from(name.to_str().expect("fixed ASCII device name"))
        })
        .collect::<std::collections::BTreeSet<_>>();
    if with_process_fs {
        expected_names.insert(std::ffi::OsString::from("pts"));
        expected_names.insert(std::ffi::OsString::from("ptmx"));
    }
    if binder.is_some() {
        for name in ["binderfs", "binder", "hwbinder", "vndbinder"] {
            expected_names.insert(std::ffi::OsString::from(name));
        }
    }
    if names != expected_names {
        return Err(NamespaceError::Rejected(
            "private dev must contain only seven fixed nodes",
        ));
    }
    for (name, major, minor) in specs {
        let fd = unsafe {
            libc::openat(
                root.as_raw_fd(),
                name.as_ptr(),
                libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error().into());
        }
        let held = unsafe { File::from_raw_fd(fd) };
        let m = held.metadata()?;
        if m.dev() != expected.device
            || m.mode() != (libc::S_IFCHR | 0o666)
            || m.uid() != uid
            || m.gid() != gid
            || m.nlink() != 1
            || m.rdev() != libc::makedev(major, minor)
        {
            return Err(NamespaceError::Rejected(
                "private character node identity differs",
            ));
        }
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct ProcessFilesystems {
    proc: Node,
    pts: Node,
}

fn has_flags(value: &str, required: &[&str], forbidden: &[&str]) -> bool {
    let values: Vec<_> = value.split(',').collect();
    !values.iter().any(|v| v.is_empty())
        && values
            .iter()
            .copied()
            .collect::<std::collections::BTreeSet<_>>()
            .len()
            == values.len()
        && required.iter().all(|v| values.contains(v))
        && forbidden.iter().all(|v| !values.contains(v))
}

fn exact_option(options: &str, key: &str, expected: &str) -> bool {
    let prefix = format!("{key}=");
    let values: Vec<_> = options
        .split(',')
        .filter(|s| s.starts_with(&prefix))
        .collect();
    values.len() == 1 && values[0] == format!("{key}={expected}")
}

/// Check kernel mountinfo, including the init-userns rendering of mapped IDs.
/// Numeric values here are comparisons against this actual TreeChild's lease,
/// never credentials supplied by a request or an authorization constructor.
fn process_mount_options(
    kind: &str,
    path: &str,
    flags: &str,
    options: &str,
    uid: u32,
    gid: u32,
) -> bool {
    match (kind, path) {
        ("proc", "/proc") => {
            has_flags(flags, &["ro", "nosuid", "nodev", "noexec"], &["rw"])
                && exact_option(options, "gid", &(gid as u64 + 3009).to_string())
                && exact_option(options, "hidepid", "invisible")
                && !options
                    .split(',')
                    .any(|v| v.starts_with("subset=") || v.starts_with("pidns="))
        }
        ("devpts", "/dev/pts") => {
            has_flags(flags, &["rw", "nosuid", "noexec"], &["ro", "nodev"])
                && exact_option(options, "uid", &uid.to_string())
                && exact_option(options, "gid", &(gid as u64 + 5).to_string())
                && exact_option(options, "mode", "620")
                && exact_option(options, "ptmxmode", "666")
                && exact_option(options, "max", "1024")
        }
        _ => false,
    }
}

fn verify_process_statfs(
    file: &File,
    kind: libc::c_long,
    required: u64,
    forbidden: u64,
) -> Result<()> {
    let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if filesystem_kind(file)? != kind
        || flags.f_flag as u64 & required != required
        || flags.f_flag as u64 & forbidden != 0
    {
        return Err(NamespaceError::Rejected(
            "private process filesystem flags or type differ",
        ));
    }
    Ok(())
}

fn fixed_namespace_link(directory: &File, name: &std::ffi::CStr, kind: i32) -> Result<File> {
    // Only used for the exact "pid" / "user" nsfs links below this already
    // attached PID-bound proc filesystem. The resulting actual nsfs FD is
    // compared to independently held PIDFD-derived namespace descriptors.
    let raw = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let held = unsafe { File::from_raw_fd(raw) };
    check_fs(held.as_raw_fd(), NSFS_MAGIC)?;
    if unsafe { libc::ioctl(held.as_raw_fd(), NS_GET_NSTYPE, 0 as libc::c_ulong) } != kind {
        return Err(NamespaceError::Rejected(
            "private proc namespace link has wrong type",
        ));
    }
    Ok(held)
}

impl TreeChild {
    fn verify_process_filesystems(
        &self,
        bases: [u64; 2],
        dev_node: Node,
        prior: Option<ProcessFilesystems>,
    ) -> Result<ProcessFilesystems> {
        self.verify_process_filesystems_with_binder(bases, dev_node, prior, None)
    }

    fn verify_process_filesystems_with_binder(
        &self,
        bases: [u64; 2],
        dev_node: Node,
        prior: Option<ProcessFilesystems>,
        binder: Option<binder::BinderFilesystem>,
    ) -> Result<ProcessFilesystems> {
        self.verify()
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let root = held_child_root(self)
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let dev = root_subdirectory(&root, c"dev")
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let proc = root_subdirectory(&root, c"proc")
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let pts = root_subdirectory(&dev, c"pts")
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let got = ProcessFilesystems {
            proc: Node::of(&proc)
                .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?,
            pts: Node::of(&pts)
                .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?,
        };
        if prior.is_some_and(|expected| expected != got)
            || got.proc.device == got.pts.device
            || [
                dev_node.device,
                root.metadata()
                    .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?
                    .dev(),
                bases[0],
                bases[1],
            ]
            .contains(&got.proc.device)
            || [
                dev_node.device,
                root.metadata()
                    .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?
                    .dev(),
                bases[0],
                bases[1],
            ]
            .contains(&got.pts.device)
        {
            return Err(NamespaceError::Rejected(
                "private proc/devpts instance changed or aliased",
            ));
        }
        // Both comparisons are read-only root-host inputs, not inherited guest
        // mount handles. A copied or bind-mounted host proc/pts is inadmissible.
        for (path, guest) in [(c"/proc", got.proc), (c"/dev/pts", got.pts)] {
            let raw = unsafe {
                libc::open(
                    path.as_ptr(),
                    libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                )
            };
            if raw < 0 {
                return Err(processfs_parent_error(
                    io::Error::last_os_error().into(),
                    file!(),
                    line!(),
                ));
            }
            let host = unsafe { File::from_raw_fd(raw) };
            if host
                .metadata()
                .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?
                .dev()
                == guest.device
            {
                return Err(NamespaceError::Rejected(
                    "guest process filesystem aliases host instance",
                ));
            }
        }
        verify_process_statfs(&proc, 0x9fa0, 1 | 2 | 4 | 8, 0)
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        verify_process_statfs(&pts, 0x1cd1, 2 | 8, 1 | 4)
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let one = root_subdirectory(&proc, c"1")
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let ns = root_subdirectory(&one, c"ns")
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let pid = fixed_namespace_link(&ns, c"pid", libc::CLONE_NEWPID)
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let user = fixed_namespace_link(&ns, c"user", libc::CLONE_NEWUSER)
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let held_pid = self
            .namespaces
            .held
            .iter()
            .find(|row| row.1 == libc::CLONE_NEWPID)
            .ok_or(NamespaceError::Rejected(
                "owned PID namespace custody absent",
            ))
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        if Node::of(&pid).map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?
            != held_pid.4
            || Node::of(&user)
                .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?
                != self.namespaces.user_node
        {
            return Err(NamespaceError::Rejected(
                "private proc does not describe exact owned PID 1",
            ));
        }
        let entries = root_subdirectory(&proc, c".")
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let mut pids = std::collections::BTreeSet::new();
        let mut count = 0_usize;
        for entry in std::fs::read_dir(format!("/proc/self/fd/{}", entries.as_raw_fd()))
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?
        {
            count += 1;
            if count > 4096 {
                return Err(NamespaceError::Rejected("private proc listing bound"));
            }
            let name = entry
                .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?
                .file_name();
            use std::os::unix::ffi::OsStrExt;
            let bytes = name.as_bytes();
            if !bytes.is_empty() && bytes.iter().all(u8::is_ascii_digit) {
                pids.insert(name);
            }
        }
        if pids != std::collections::BTreeSet::from([std::ffi::OsString::from("1")]) {
            return Err(NamespaceError::Rejected(
                "construction proc contains foreign process IDs",
            ));
        }
        verify_attached_devices_with_binder(
            &dev,
            self.uids.start,
            self.gids.start,
            dev_node,
            true,
            binder,
        )
        .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let link_raw = unsafe {
            libc::openat(
                dev.as_raw_fd(),
                c"ptmx".as_ptr(),
                libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if link_raw < 0 {
            return Err(processfs_parent_error(
                io::Error::last_os_error().into(),
                file!(),
                line!(),
            ));
        }
        let link = unsafe { File::from_raw_fd(link_raw) };
        let m = link
            .metadata()
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let mut target = [0_u8; 32];
        let n = unsafe {
            libc::readlinkat(
                dev.as_raw_fd(),
                c"ptmx".as_ptr(),
                target.as_mut_ptr().cast(),
                target.len(),
            )
        };
        if n != 8
            || &target[..8] != b"pts/ptmx"
            || m.mode() != (libc::S_IFLNK | 0o777)
            || m.dev() != dev_node.device
            || m.uid() != self.uids.start
            || m.gid() != self.gids.start
        {
            return Err(NamespaceError::Rejected(
                "private ptmx link escapes its new instance",
            ));
        }
        let entries = root_subdirectory(&pts, c".")
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        let names = std::fs::read_dir(format!("/proc/self/fd/{}", entries.as_raw_fd()))
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?
            .take(2)
            .map(|row| row.map(|row| row.file_name()))
            .collect::<io::Result<Vec<_>>>()
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        if names != [std::ffi::OsString::from("ptmx")] {
            return Err(NamespaceError::Rejected(
                "parked devpts has foreign or unreleased slave",
            ));
        }
        let raw = unsafe {
            libc::openat(
                pts.as_raw_fd(),
                c"ptmx".as_ptr(),
                libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if raw < 0 {
            return Err(processfs_parent_error(
                io::Error::last_os_error().into(),
                file!(),
                line!(),
            ));
        }
        let ptmx = unsafe { File::from_raw_fd(raw) };
        let m = ptmx
            .metadata()
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        if m.mode() != (libc::S_IFCHR | 0o666)
            || m.dev() != got.pts.device
            || m.uid() != self.uids.start
            || m.gid() != self.gids.start
            || m.rdev() != libc::makedev(5, 2)
            || m.nlink() != 1
        {
            return Err(NamespaceError::Rejected(
                "private ptmx node identity differs",
            ));
        }
        self.verify_empty_root_mounts_with_binder(bases, Some(dev_node), Some(got), binder)
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        self.verify()
            .map_err(|error| processfs_parent_error(error.into(), file!(), line!()))?;
        Ok(got)
    }
}

fn receive_created_fds(keeper: &Owner, uid: u32, gid: u32) -> Result<(OwnedFd, OwnedFd)> {
    let r = keeper.held()?;
    wait_readable(&r.control, &r.pidfd)?;
    let mut packet = Packet::zeroed();
    let mut iov = libc::iovec {
        iov_base: (&mut packet as *mut Packet).cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut ancillary = [0_usize; 32];
    let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
    msg.msg_iov = &mut iov;
    msg.msg_iovlen = 1;
    msg.msg_control = ancillary.as_mut_ptr().cast();
    msg.msg_controllen = std::mem::size_of_val(&ancillary);
    let rc = unsafe {
        libc::recvmsg(
            r.control.as_raw_fd(),
            &mut msg,
            libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC,
        )
    };
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let mut credentials = None;
    let mut rights = Vec::new();
    let mut rights_messages = 0;
    let mut bad = msg.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0;
    let mut item = unsafe { libc::CMSG_FIRSTHDR(&msg) };
    while !item.is_null() {
        let h = unsafe { &*item };
        let base = unsafe { libc::CMSG_LEN(0) } as usize;
        if h.cmsg_len < base {
            bad = true;
            break;
        }
        let len = h.cmsg_len - base;
        let data = unsafe { libc::CMSG_DATA(item) };
        if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS {
            rights_messages += 1;
            if len != 2 * std::mem::size_of::<i32>() {
                bad = true;
            }
            for n in 0..len / std::mem::size_of::<i32>() {
                let fd = unsafe {
                    std::ptr::read_unaligned(data.add(n * std::mem::size_of::<i32>()).cast::<i32>())
                };
                // Every received descriptor is owned and closes on every error.
                rights.push(unsafe { OwnedFd::from_raw_fd(fd) });
            }
        } else if h.cmsg_level == libc::SOL_SOCKET
            && h.cmsg_type == libc::SCM_CREDENTIALS
            && len == std::mem::size_of::<libc::ucred>()
            && credentials.is_none()
        {
            credentials = Some(unsafe { std::ptr::read_unaligned(data.cast::<libc::ucred>()) });
        } else {
            bad = true;
        }
        item = unsafe { libc::CMSG_NXTHDR(&msg, item) };
    }
    let c = credentials.ok_or(NamespaceError::Rejected(
        "tree transfer has no kernel peer credentials",
    ))?;
    if bad
        || rc as usize != std::mem::size_of::<Packet>()
        || !packet.matches(r.nonce, r.pid)
        || c.pid != r.pid as i32
        || c.uid != uid
        || c.gid != gid
        || packet.phase != Phase::TreeSpawned as u32
        || packet.errno != 0
        || rights_messages != 1
        || rights.len() != 2
    {
        return Err(NamespaceError::Rejected(
            "tree FD transfer did not match the owned creator",
        ));
    }
    let control = rights.pop().unwrap();
    let pidfd = rights.pop().unwrap();
    Ok((pidfd, control))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::production_identity::tests::broker_fixture;
    use std::fs;

    fn proc_test_channel(passcred: bool) -> (OwnedFd, OwnedFd) {
        let mut raw = [-1_i32; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                    0,
                    raw.as_mut_ptr(),
                )
            },
            0
        );
        let receiver = unsafe { OwnedFd::from_raw_fd(raw[0]) };
        let sender = unsafe { OwnedFd::from_raw_fd(raw[1]) };
        if passcred {
            let one = 1_i32;
            assert_eq!(
                unsafe {
                    libc::setsockopt(
                        receiver.as_raw_fd(),
                        libc::SOL_SOCKET,
                        libc::SO_PASSCRED,
                        (&one as *const i32).cast(),
                        std::mem::size_of::<i32>() as libc::socklen_t,
                    )
                },
                0
            );
        }
        (receiver, sender)
    }

    fn send_proc_test_rights(fd: RawFd, packet: &Packet, rights: &[RawFd]) {
        let mut iov = libc::iovec {
            iov_base: (packet as *const Packet).cast_mut().cast(),
            iov_len: std::mem::size_of::<Packet>(),
        };
        let mut ancillary = [0_usize; 128];
        let mut msg: libc::msghdr = unsafe { std::mem::zeroed() };
        msg.msg_iov = &mut iov;
        msg.msg_iovlen = 1;
        msg.msg_control = ancillary.as_mut_ptr().cast();
        msg.msg_controllen =
            unsafe { libc::CMSG_SPACE(std::mem::size_of_val(rights) as u32) } as usize;
        assert!(msg.msg_controllen <= std::mem::size_of_val(&ancillary));
        let h = unsafe { libc::CMSG_FIRSTHDR(&msg) };
        unsafe {
            (*h).cmsg_level = libc::SOL_SOCKET;
            (*h).cmsg_type = libc::SCM_RIGHTS;
            (*h).cmsg_len = libc::CMSG_LEN(std::mem::size_of_val(rights) as u32) as usize;
            for (i, raw) in rights.iter().enumerate() {
                std::ptr::write_unaligned(libc::CMSG_DATA(h).cast::<i32>().add(i), *raw);
            }
        }
        assert_eq!(
            unsafe { libc::sendmsg(fd, &msg, libc::MSG_NOSIGNAL) },
            std::mem::size_of::<Packet>() as isize
        );
    }

    #[test]
    fn proc_context_receiver_requires_credentials_exact_phase_and_one_fd_without_leaks() {
        let nonce = [0x6d_u8; 16];
        let own_pid = unsafe { libc::getpid() } as u32;
        let packet = Packet::new(nonce, Phase::ProcContextReady, 0, own_pid);
        let input = File::open("/dev/null").unwrap();
        let (receiver, sender) = proc_test_channel(true);
        let fd_count = || fs::read_dir("/proc/self/fd").unwrap().count();
        let before = fd_count();
        send_one_fd(sender.as_raw_fd(), &packet, input.as_fd()).unwrap();
        let (actual, cred, received) = receive_proc_context_record(receiver.as_raw_fd()).unwrap();
        assert!(actual.matches(nonce, own_pid));
        assert_eq!(cred.pid, own_pid as i32);
        assert_eq!(
            (cred.uid, cred.gid),
            (unsafe { libc::getuid() }, unsafe { libc::getgid() })
        );
        let received = received.unwrap();
        assert_eq!(Node::of(&received).unwrap(), Node::of(&input).unwrap());
        assert_ne!(
            unsafe { libc::fcntl(received.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
        drop(received);
        assert_eq!(fd_count(), before);

        // These are real kernel SCM_RIGHTS messages, including truncation.
        // Rejection must close every delivered descriptor, not merely the first.
        for count in [2_usize, 96] {
            send_proc_test_rights(sender.as_raw_fd(), &packet, &vec![input.as_raw_fd(); count]);
            assert!(receive_proc_context_record(receiver.as_raw_fd()).is_err());
            assert_eq!(fd_count(), before);
        }
        let wrong = Packet::new(nonce, Phase::ProcessFilesystemsReady, 0, own_pid);
        send_one_fd(sender.as_raw_fd(), &wrong, input.as_fd()).unwrap();
        assert!(receive_proc_context_record(receiver.as_raw_fd()).is_err());
        assert_eq!(fd_count(), before);
        send_packet(sender.as_raw_fd(), &packet).unwrap();
        assert!(receive_proc_context_record(receiver.as_raw_fd()).is_err());
        assert_eq!(fd_count(), before);

        let (without_cred, no_cred_sender) = proc_test_channel(false);
        let count = fd_count();
        send_one_fd(no_cred_sender.as_raw_fd(), &packet, input.as_fd()).unwrap();
        assert!(receive_proc_context_record(without_cred.as_raw_fd()).is_err());
        assert_eq!(fd_count(), count);
        // A failure is still only data here; TreeChild authenticates peer and
        // nonce before consuming it and can never turn it into mount authority.
        let failure = Packet::new(nonce, Phase::Failed, libc::EPERM, own_pid);
        send_packet(sender.as_raw_fd(), &failure).unwrap();
        let (failed, _, descriptor) = receive_proc_context_record(receiver.as_raw_fd()).unwrap();
        assert_eq!(failed.errno, libc::EPERM);
        assert!(descriptor.is_none());
    }

    #[test]
    fn exited_child_queued_failed_is_preserved_after_actual_owned_reap() {
        let (pid, pidfd, control, _, _, nonce) =
            child::spawn(child::Mode::ExitWithPrivateDiagnostic).unwrap();
        let exited = wait_exited(&pidfd, RETIRE_TIMEOUT).unwrap_or(false);
        if !exited {
            let _ = signal_owned(&pidfd, libc::SIGKILL);
            let _ = wait_exited(&pidfd, RETIRE_TIMEOUT);
        }
        // Reap our exact child before observing its queued error. No PID is
        // adopted and the diagnostic cannot itself perform a wait or signal.
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        let reaped = unsafe {
            libc::waitid(
                libc::P_PIDFD,
                pidfd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG,
            )
        };
        assert!(exited);
        assert_eq!(reaped, 0);
        assert_eq!(unsafe { info.si_pid() }, pid as i32);
        let exit = ChildExit {
            pid,
            reason: info.si_code,
            status: unsafe { info.si_status() },
        };
        assert_eq!((exit.reason, exit.status), (libc::CLD_EXITED, 127));
        let observed = private_retired_failure_diagnostic(
            &control,
            &exit,
            nonce,
            pid,
            unsafe { libc::getuid() },
            unsafe { libc::getgid() },
        );
        assert!(
            observed.contains("actual owned PIDFD reap code=1 status=127"),
            "{observed}"
        );
        assert!(
            observed.contains("authenticated queued Failed: stage=1 source-line=123 errno=71"),
            "{observed}"
        );
    }

    #[test]
    fn proc_context_shape_rejects_device_and_unrelated_anon_inode() {
        let proc_root = File::open("/proc").unwrap();
        let device = File::open("/dev/null").unwrap();
        assert!(require_proc_context_shape(&device, &proc_root).is_err());
        let raw = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) };
        assert!(raw >= 0);
        let unrelated = unsafe { File::from_raw_fd(raw) };
        assert!(require_proc_context_shape(&unrelated, &proc_root).is_err());
    }

    #[test]
    fn current_thread_pidfd_is_kernel_bound_and_regular_files_are_rejected() {
        let (_root, lease) = broker_fixture();
        let mut owner = Owner::spawn(Some(lease), child::Mode::ParkOnly).unwrap();
        let held = owner.held().unwrap();
        let current = self_thread_pidfd(held).unwrap();
        let info = pidfd_info(current.as_raw_fd()).unwrap();
        assert_eq!(info.pid, held.creator_tid as u32);
        assert_eq!(info.tgid, held.parent_pid);
        let ns = from_pidfd(&current, 0xff05, libc::CLONE_NEWPID).unwrap();
        let actual = File::open("/proc/self/ns/pid").unwrap();
        assert_eq!(Node::of(&ns).unwrap(), Node::of(&actual).unwrap());
        let unrelated = File::open("/dev/null").unwrap();
        assert!(pidfd_info(unrelated.as_raw_fd()).is_err());
        assert_eq!(owner.retire().unwrap().reason, libc::CLD_EXITED);
    }

    #[test]
    fn tree_control_requires_real_unix_seqpacket_and_kernel_credentials() {
        let mut raw = [-1; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                    0,
                    raw.as_mut_ptr(),
                )
            },
            0
        );
        let first = unsafe { OwnedFd::from_raw_fd(raw[0]) };
        let _second = unsafe { OwnedFd::from_raw_fd(raw[1]) };
        assert!(require_control_socket(&first).is_err());
        let one = 1_i32;
        assert_eq!(
            unsafe {
                libc::setsockopt(
                    first.as_raw_fd(),
                    libc::SOL_SOCKET,
                    libc::SO_PASSCRED,
                    (&one as *const i32).cast(),
                    std::mem::size_of::<i32>() as libc::socklen_t,
                )
            },
            0
        );
        require_control_socket(&first).unwrap();
        let (stream, _) = std::os::unix::net::UnixStream::pair().unwrap();
        let stream: OwnedFd = stream.into();
        assert!(require_control_socket(&stream).is_err());
    }

    fn children() -> String {
        let tid = unsafe { libc::syscall(libc::SYS_gettid) };
        fs::read_to_string(format!("/proc/self/task/{tid}/children")).unwrap()
    }

    fn lease_available(root: &std::path::Path) -> bool {
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(root.join("registry/u1000.lease"))
            .unwrap();
        let rc = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
        if rc == 0 {
            assert_eq!(unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_UN) }, 0);
            true
        } else {
            assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
            false
        }
    }

    fn mapped_private(lease: IdentityLease, mode: child::Mode) -> MappedUserNamespace {
        let mut owner = Owner::spawn(Some(lease), mode).unwrap();
        owner.enter_userns().unwrap();
        let (uids, gids) = owner.install_maps().unwrap();
        owner.mapped_go(uids, gids).unwrap();
        MappedUserNamespace { owner }
    }

    // This fixed syscall control is independent of HostAdmission, real host
    // grants, Android mounts/exec and runtime qualification. Root must review
    // the exact source/binary and bounded private scope before invoking it.
    #[test]
    #[ignore = "requires separately reviewed root PID1 namespace syscall control"]
    fn privileged_private_pid1_namespace_controls() {
        assert_eq!(unsafe { libc::getuid() }, 0);
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let original_children = children();
        let original_uid = fs::read("/proc/self/uid_map").unwrap();
        let original_gid = fs::read("/proc/self/gid_map").unwrap();
        let original_mounts = fs::read("/proc/self/mountinfo").unwrap();
        let original_namespaces: Vec<_> = ["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"]
            .map(|name| Node::of(&File::open(format!("/proc/self/ns/{name}")).unwrap()).unwrap())
            .into_iter()
            .collect();

        let (root, lease) = broker_fixture();
        let mapped = mapped_private(lease, child::Mode::UserNamespace);
        assert!(
            mapped
                .owner
                .witness()
                .unwrap()
                .descendant_pid_namespace()
                .is_none()
        );
        let mut tree = IsolatedNamespaces::from_mapped(mapped).unwrap();
        tree.verify().unwrap();
        let init = tree.init.as_ref().unwrap();
        let init_pid = init.identity.pid;
        let init_start = init.identity.start_ticks;
        let pidns = Node::of(init.pid_namespace()).unwrap();
        let witness = tree.witness().unwrap();
        witness.revalidate().unwrap();
        assert_eq!(
            Node::of(witness.descendant_pid_namespace().unwrap()).unwrap(),
            pidns
        );
        assert_eq!(
            pidfd_info(init.pidfd.as_raw_fd()).unwrap().ppid,
            unsafe { libc::getpid() } as u32
        );
        let status = read_proc(&init.proc_dir, "status").unwrap();
        assert_eq!(
            status_field(&status, "NSpid:")
                .unwrap()
                .split_ascii_whitespace()
                .map(|value| value.parse::<u32>().unwrap())
                .collect::<Vec<_>>(),
            [init_pid, 1]
        );
        let fd_names: Vec<_> = fs::read_dir(format!("/proc/{init_pid}/fd"))
            .unwrap()
            .map(|entry| entry.unwrap().file_name())
            .collect();
        assert_eq!(fd_names, [std::ffi::OsString::from("3")]);
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
        assert!(!lease_available(root.path()));
        let userns = witness.user_namespace().try_clone().unwrap();
        let lease = witness.identity_lease().unwrap();
        let host_uid = lease.host_uid();
        let cohort = lease.broker_cohort().to_owned();
        drop(witness);
        {
            let retired = tree.reap_init().unwrap();
            retired
                .verify_mount_retirement(&userns, host_uid, &cohort)
                .unwrap();
            assert!(
                retired
                    .verify_mount_retirement(&userns, host_uid + 1, &cohort)
                    .is_err()
            );
            assert!(
                retired
                    .verify_mount_retirement(&userns, host_uid, &"0".repeat(64))
                    .is_err()
            );
            let foreign = File::open("/proc/self/ns/user").unwrap();
            assert!(
                retired
                    .verify_mount_retirement(&foreign, host_uid, &cohort)
                    .is_err()
            );
            assert!(!lease_available(root.path()));
        }
        let exit = tree.retire().unwrap();
        assert_eq!(exit.init.reason, libc::CLD_EXITED);
        assert_eq!(exit.init.status, 0);
        assert_eq!(exit.keeper.reason, libc::CLD_EXITED);
        assert_eq!(exit.keeper.status, 0);
        assert_eq!(children(), original_children);
        assert!(lease_available(root.path()));
        println!(
            "private PID1 control: pid={init_pid} start_ticks={init_start} pidns_inode={}; actual direct-parent pidfd/proc and six namespace ownership verified; fd3 only; private propagation; init+keeper actually reaped; production admission=false Android=0",
            pidns.inode
        );

        let (wrong_root, wrong_lease) = broker_fixture();
        let wrong = mapped_private(wrong_lease, child::Mode::TreeWrongReady);
        assert!(matches!(
            IsolatedNamespaces::from_mapped(wrong),
            Err(NamespaceError::Rejected(_))
        ));
        assert_eq!(children(), original_children);
        assert!(lease_available(wrong_root.path()));
        assert_eq!(fs::read("/proc/self/uid_map").unwrap(), original_uid);
        assert_eq!(fs::read("/proc/self/gid_map").unwrap(), original_gid);
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
        let after_namespaces: Vec<_> = ["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"]
            .map(|name| Node::of(&File::open(format!("/proc/self/ns/{name}")).unwrap()).unwrap())
            .into_iter()
            .collect();
        assert_eq!(after_namespaces, original_namespaces);
        println!(
            "wrong PID1 READY nonce rejected; bound init+keeper actually reaped; whole lease released only after actual exit; host maps/mounts/namespaces unchanged; production admission=false Android=0"
        );
    }

    #[test]
    #[ignore = "requires separately reviewed root loop/image namespace control"]
    fn privileged_private_empty_base_mount_controls() {
        assert_eq!(unsafe { libc::getuid() }, 0);
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let original_children = children();
        let original_mounts = fs::read("/proc/self/mountinfo").unwrap();
        let original_uid = fs::read("/proc/self/uid_map").unwrap();
        let original_gid = fs::read("/proc/self/gid_map").unwrap();

        let (identity_root, lease) = broker_fixture();
        let mapped = mapped_private(lease, child::Mode::EmptyRootControl);
        let tree = IsolatedNamespaces::from_mapped(mapped).unwrap();
        let controls = crate::production_mounts::private_control::prepare_private_control_mounts(
            &tree.witness().unwrap(),
        )
        .unwrap();
        controls.verify_images_unchanged().unwrap();
        let mut tree = tree
            .attach_base_inner(BaseMounts::PrivateControl(controls))
            .unwrap();
        assert!(tree.empty_root);
        let init = tree.init.as_ref().unwrap();
        let init_pid = init.identity.pid;
        let pidns = Node::of(init.pid_namespace()).unwrap();
        let fd_names: Vec<_> = fs::read_dir(format!("/proc/{init_pid}/fd"))
            .unwrap()
            .map(|item| item.unwrap().file_name())
            .collect();
        assert_eq!(fd_names, [std::ffi::OsString::from("3")]);
        send_packet(
            init.control.as_raw_fd(),
            &Packet::new(init.nonce, Phase::ProbeEmptyRoot, 0, init.parent_pid),
        )
        .unwrap();
        init.receive_phase(Phase::EmptyRootChecked).unwrap();
        match tree.bases.as_ref().unwrap() {
            BaseMounts::PrivateControl(value) => value.verify_images_unchanged().unwrap(),
            _ => panic!("test cannot substitute a production admission"),
        }
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
        let userns = tree
            .witness()
            .unwrap()
            .user_namespace()
            .try_clone()
            .unwrap();
        let (uid, cohort) = {
            let witness = tree.witness().unwrap();
            let lease = witness.identity_lease().unwrap();
            (lease.host_uid(), lease.broker_cohort().to_owned())
        };
        {
            let retired = tree.reap_init().unwrap();
            retired
                .verify_mount_retirement(&userns, uid, &cohort)
                .unwrap();
            let views = &retired.tree.init.as_ref().unwrap().namespaces.held;
            assert_eq!(views.len(), 1);
            assert_eq!(views[0].1, libc::CLONE_NEWPID);
            assert_eq!(Node::of(&views[0].3).unwrap(), pidns);
            assert!(!lease_available(identity_root.path()));
        }
        let exit = tree.retire().unwrap();
        assert_eq!((exit.init.reason, exit.init.status), (libc::CLD_EXITED, 0));
        assert_eq!(
            (exit.keeper.reason, exit.keeper.status),
            (libc::CLD_EXITED, 0)
        );
        assert!(lease_available(identity_root.path()));
        assert_eq!(children(), original_children);
        println!(
            "private empty-base control: actual readonly ext4/IDMAP descriptors consumed; distinct writable tmpfs data/metadata checked by PID 1; immutable probes reject EROFS; private pivot and fd3-only barrier; actual init reap then live namespace FD release then owned loop ENXIO then keeper reap; Android=0 production admission=false"
        );

        // Wrong nonce and a non-mount descriptor are separate real kernel
        // negative paths. They use the same fixed receiver and owned teardown.
        for bad_nonce in [true, false] {
            let (identity_root, lease) = broker_fixture();
            let mapped = mapped_private(lease, child::Mode::UserNamespace);
            let mut tree = IsolatedNamespaces::from_mapped(mapped).unwrap();
            let mut controls =
                crate::production_mounts::private_control::prepare_private_control_mounts(
                    &tree.witness().unwrap(),
                )
                .unwrap();
            let foreign = File::open("/dev/null").unwrap();
            {
                let witness = tree.witness().unwrap();
                let fds = controls.descriptors_for_transfer(&witness).unwrap();
                let init = tree.init.as_ref().unwrap();
                let mut nonce = init.nonce;
                if bad_nonce {
                    nonce[0] ^= 1;
                }
                let packet = Packet::new(nonce, Phase::MountEmptyBase, 0, init.parent_pid);
                let fds = if bad_nonce {
                    fds
                } else {
                    [fds[0], foreign.as_fd()]
                };
                send_base_fds(init.control.as_raw_fd(), &packet, fds).unwrap();
            }
            tree.bases = Some(BaseMounts::PrivateControl(controls));
            assert!(
                tree.init
                    .as_ref()
                    .unwrap()
                    .receive_phase(Phase::EmptyRootReady)
                    .is_err()
            );
            let exit = tree.retire().unwrap();
            assert_eq!(exit.init.reason, libc::CLD_EXITED);
            assert_ne!(exit.init.status, 0);
            assert_eq!(
                (exit.keeper.reason, exit.keeper.status),
                (libc::CLD_EXITED, 0)
            );
            assert!(lease_available(identity_root.path()));
            assert_eq!(children(), original_children);
            assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
            println!(
                "private empty-base negative: bad_nonce={bad_nonce}; rejected before ready; actual owned children and exact loops retired"
            );
        }
        assert_eq!(fs::read("/proc/self/uid_map").unwrap(), original_uid);
        assert_eq!(fs::read("/proc/self/gid_map").unwrap(), original_gid);
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
    }

    #[test]
    #[ignore = "requires separately reviewed root private-dev and loop/image control"]
    fn privileged_private_device_mount_controls() {
        assert_eq!(unsafe { libc::getuid() }, 0);
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let original_children = children();
        let original_mounts = fs::read("/proc/self/mountinfo").unwrap();
        let original_uid = fs::read("/proc/self/uid_map").unwrap();
        let original_gid = fs::read("/proc/self/gid_map").unwrap();
        let original_namespaces: Vec<_> = ["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"]
            .map(|name| Node::of(&File::open(format!("/proc/self/ns/{name}")).unwrap()).unwrap())
            .into_iter()
            .collect();
        let host_device_metadata = || {
            ["null", "zero", "full", "random", "urandom", "tty", "fuse"].map(|name| {
                fs::symlink_metadata(format!("/dev/{name}")).ok().map(|m| {
                    (
                        m.dev(),
                        m.ino(),
                        m.mode(),
                        m.uid(),
                        m.gid(),
                        m.rdev(),
                        m.nlink(),
                    )
                })
            })
        };
        let original_host_devices = host_device_metadata();

        let (identity_root, lease) = broker_fixture();
        let mapped = mapped_private(lease, child::Mode::DeviceRootControl);
        let tree = IsolatedNamespaces::from_mapped(mapped).unwrap();
        let bases = crate::production_mounts::private_control::prepare_private_control_mounts(
            &tree.witness().unwrap(),
        )
        .unwrap();
        let tree = tree
            .attach_base_inner(BaseMounts::PrivateControl(bases))
            .unwrap();
        let init = tree.init.as_ref().unwrap();
        send_packet(
            init.control.as_raw_fd(),
            &Packet::new(init.nonce, Phase::ProbeEmptyRoot, 0, init.parent_pid),
        )
        .unwrap();
        init.receive_phase(Phase::EmptyRootChecked).unwrap();
        let mut devices =
            crate::production_devices::private_control::prepare_private_control_devices(
                &tree.witness().unwrap(),
            )
            .unwrap();
        devices.verify_original_nodes().unwrap();

        // A real second owned tree is not authority for the first tree's DEV.
        // This uses no host grants and neither tree can exec Android.
        let (foreign_root, foreign_lease) = broker_fixture();
        let foreign = IsolatedNamespaces::from_mapped(mapped_private(
            foreign_lease,
            child::Mode::UserNamespace,
        ))
        .unwrap();
        assert!(
            devices
                .descriptor_for_transfer(&foreign.witness().unwrap())
                .is_err()
        );
        let foreign_exit = foreign.retire().unwrap();
        assert_eq!(
            (foreign_exit.init.reason, foreign_exit.init.status),
            (libc::CLD_EXITED, 0)
        );
        assert_eq!(
            (foreign_exit.keeper.reason, foreign_exit.keeper.status),
            (libc::CLD_EXITED, 0)
        );
        assert!(lease_available(foreign_root.path()));
        devices.verify_original_nodes().unwrap();

        let mut tree = tree
            .attach_device_inner(DeviceMounts::PrivateControl(devices))
            .unwrap();
        assert!(tree.empty_root && tree.private_devices);
        // This borrow comes from the exact owned fields, not a numeric PID or
        // a fabricated witness. The descriptor guard must reject a second send.
        {
            let witness = OwnedNamespaceWitness {
                owner: &tree.keeper.as_ref().unwrap().owner,
                tree: Some(tree.init.as_ref().unwrap()),
            };
            match tree.devices.as_mut().unwrap() {
                DeviceMounts::PrivateControl(value) => {
                    assert!(matches!(
                        value.descriptor_for_transfer(&witness),
                        Err(crate::production_devices::DeviceError::Rejected(
                            "one private dev FD transfer attempt"
                        ))
                    ));
                }
                _ => panic!("private control cannot fabricate production admission"),
            }
        }
        let init = tree.init.as_ref().unwrap();
        let init_pid = init.identity.pid;
        let fds: Vec<_> = fs::read_dir(format!("/proc/{init_pid}/fd"))
            .unwrap()
            .map(|entry| entry.unwrap().file_name())
            .collect();
        assert_eq!(fds, [std::ffi::OsString::from("3")]);
        send_packet(
            init.control.as_raw_fd(),
            &Packet::new(init.nonce, Phase::ProbePrivateDev, 0, init.parent_pid),
        )
        .unwrap();
        init.receive_phase(Phase::PrivateDevChecked).unwrap();
        match tree.bases.as_ref().unwrap() {
            BaseMounts::PrivateControl(value) => value.verify_images_unchanged().unwrap(),
            _ => panic!("private control cannot fabricate production admission"),
        }
        assert_eq!(host_device_metadata(), original_host_devices);
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
        assert!(!lease_available(identity_root.path()));
        {
            let retired = tree.reap_init().unwrap();
            let views = &retired.tree.init.as_ref().unwrap().namespaces.held;
            assert_eq!(views.len(), 1);
            assert_eq!(views[0].1, libc::CLONE_NEWPID);
            assert!(!lease_available(identity_root.path()));
        }
        let exit = tree.retire().unwrap();
        assert_eq!((exit.init.reason, exit.init.status), (libc::CLD_EXITED, 0));
        assert_eq!(
            (exit.keeper.reason, exit.keeper.status),
            (libc::CLD_EXITED, 0)
        );
        assert!(lease_available(identity_root.path()));
        assert_eq!(children(), original_children);
        println!(
            "private DEV control: actual seven fresh 0666 char nodes on bounded IDMAP tmpfs; exact guest root ownership and nosuid/noexec/dev flags; fresh base EROFS and tmpfs-data I/O preserved; null write and zero read; foreign-tree and second-transfer rejected; fd3 only; actual PID1 reap, live namespace close, DEV descriptor and loops retire, keeper reap; Android=0 production admission=false"
        );

        // Each path reaches the real device receiver after a fresh positive
        // base transfer. The only descriptor used as a substitute is O_PATH.
        for negative in ["wrong_nonce", "wrong_fd", "extra_fd"] {
            let (identity_root, lease) = broker_fixture();
            let mapped = mapped_private(lease, child::Mode::UserNamespace);
            let tree = IsolatedNamespaces::from_mapped(mapped).unwrap();
            let bases = crate::production_mounts::private_control::prepare_private_control_mounts(
                &tree.witness().unwrap(),
            )
            .unwrap();
            let mut tree = tree
                .attach_base_inner(BaseMounts::PrivateControl(bases))
                .unwrap();
            let mut devices =
                crate::production_devices::private_control::prepare_private_control_devices(
                    &tree.witness().unwrap(),
                )
                .unwrap();
            let unrelated = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open("/dev/null")
                .unwrap();
            {
                let witness = tree.witness().unwrap();
                let fd = devices.descriptor_for_transfer(&witness).unwrap();
                let init = tree.init.as_ref().unwrap();
                let mut nonce = init.nonce;
                if negative == "wrong_nonce" {
                    nonce[0] ^= 1;
                }
                let packet = Packet::new(nonce, Phase::MountPrivateDev, 0, init.parent_pid);
                if negative == "extra_fd" {
                    send_base_fds(init.control.as_raw_fd(), &packet, [fd, unrelated.as_fd()])
                        .unwrap();
                } else {
                    send_one_fd(
                        init.control.as_raw_fd(),
                        &packet,
                        if negative == "wrong_fd" {
                            unrelated.as_fd()
                        } else {
                            fd
                        },
                    )
                    .unwrap();
                }
            }
            tree.devices = Some(DeviceMounts::PrivateControl(devices));
            assert!(
                tree.init
                    .as_ref()
                    .unwrap()
                    .receive_phase(Phase::PrivateDevReady)
                    .is_err()
            );
            let exit = tree.retire().unwrap();
            assert_eq!(exit.init.reason, libc::CLD_EXITED);
            assert_ne!(exit.init.status, 0);
            assert_eq!(
                (exit.keeper.reason, exit.keeper.status),
                (libc::CLD_EXITED, 0)
            );
            assert!(lease_available(identity_root.path()));
            assert_eq!(children(), original_children);
            assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
            assert_eq!(host_device_metadata(), original_host_devices);
            println!(
                "private DEV negative: {negative}; exact receiver rejected; owned tree, device mount, base loops and keeper actually retired"
            );
        }
        assert_eq!(fs::read("/proc/self/uid_map").unwrap(), original_uid);
        assert_eq!(fs::read("/proc/self/gid_map").unwrap(), original_gid);
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
        let after_namespaces: Vec<_> = ["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"]
            .map(|name| Node::of(&File::open(format!("/proc/self/ns/{name}")).unwrap()).unwrap())
            .into_iter()
            .collect();
        assert_eq!(after_namespaces, original_namespaces);
        assert_eq!(host_device_metadata(), original_host_devices);
    }

    #[test]
    fn process_mounts_require_exact_targets_flags_and_mapped_ids() {
        let uid = 200000;
        let gid = 300000;
        let proc_options = "rw,gid=303009,hidepid=invisible";
        let pts_options = "rw,uid=200000,gid=300005,mode=620,ptmxmode=666,max=1024";
        assert!(process_mount_options(
            "proc",
            "/proc",
            "ro,nosuid,nodev,noexec,relatime",
            proc_options,
            uid,
            gid
        ));
        assert!(process_mount_options(
            "devpts",
            "/dev/pts",
            "rw,nosuid,noexec,relatime",
            pts_options,
            uid,
            gid
        ));
        for flags in [
            "rw,nosuid,nodev,noexec",
            "ro,nodev,noexec",
            "ro,nosuid,noexec",
            "ro,nosuid,nodev",
            "ro,ro,nosuid,nodev,noexec",
            "ro,nosuid,nodev,noexec,",
        ] {
            assert!(!process_mount_options(
                "proc",
                "/proc",
                flags,
                proc_options,
                uid,
                gid
            ));
        }
        for options in [
            "rw,gid=3009,hidepid=invisible",
            "rw,gid=303009,hidepid=off",
            "rw,gid=303009,hidepid=invisible,gid=303009",
            "rw,gid=303009,hidepid=invisible,subset=pid",
            "rw,gid=303009,hidepid=invisible,pidns=9",
        ] {
            assert!(!process_mount_options(
                "proc",
                "/proc",
                "ro,nosuid,nodev,noexec",
                options,
                uid,
                gid
            ));
        }
        for (kind, path) in [
            ("proc", "/host/proc"),
            ("devpts", "/dev/other"),
            ("tmpfs", "/proc"),
        ] {
            assert!(!process_mount_options(
                kind,
                path,
                "ro,nosuid,nodev,noexec",
                proc_options,
                uid,
                gid
            ));
        }
        for (a, b) in [
            ("uid=200000", "uid=0"),
            ("gid=300005", "gid=5"),
            ("mode=620", "mode=666"),
            ("ptmxmode=666", "ptmxmode=000"),
            ("max=1024", "max=1048576"),
        ] {
            assert!(!process_mount_options(
                "devpts",
                "/dev/pts",
                "rw,nosuid,noexec",
                &pts_options.replace(a, b),
                uid,
                gid
            ));
        }
        for flags in [
            "ro,nosuid,noexec",
            "rw,nosuid,nodev,noexec",
            "rw,noexec",
            "rw,nosuid",
        ] {
            assert!(!process_mount_options(
                "devpts",
                "/dev/pts",
                flags,
                pts_options,
                uid,
                gid
            ));
        }
    }

    #[test]
    #[ignore = "requires separately reviewed root private proc/devpts and loop/image control"]
    fn privileged_private_process_filesystem_controls() {
        assert_eq!(unsafe { libc::getuid() }, 0);
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let original_children = children();
        let original_mounts = fs::read("/proc/self/mountinfo").unwrap();
        let original_uid = fs::read("/proc/self/uid_map").unwrap();
        let original_gid = fs::read("/proc/self/gid_map").unwrap();
        let namespace_nodes = || {
            ["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"].map(|name| {
                Node::of(&File::open(format!("/proc/self/ns/{name}")).unwrap()).unwrap()
            })
        };
        let original_namespaces = namespace_nodes();
        let host_pty_identity = || {
            ["/dev/pts", "/dev/pts/ptmx"].map(|path| {
                let m = fs::symlink_metadata(path).unwrap();
                (
                    m.dev(),
                    m.ino(),
                    m.mode(),
                    m.uid(),
                    m.gid(),
                    m.rdev(),
                    m.nlink(),
                )
            })
        };
        let original_host_pty = host_pty_identity();
        let (identity_root, lease) = broker_fixture();
        let tree = IsolatedNamespaces::from_mapped(mapped_private(
            lease,
            child::Mode::ProcessFilesystemsControl,
        ))
        .unwrap();
        let bases = crate::production_mounts::private_control::prepare_private_control_mounts(
            &tree.witness().unwrap(),
        )
        .unwrap();
        let tree = tree
            .attach_base_inner(BaseMounts::PrivateControl(bases))
            .unwrap();
        let init = tree.init.as_ref().unwrap();
        send_packet(
            init.control.as_raw_fd(),
            &Packet::new(init.nonce, Phase::ProbeEmptyRoot, 0, init.parent_pid),
        )
        .unwrap();
        init.receive_phase(Phase::EmptyRootChecked).unwrap();
        let devices = crate::production_devices::private_control::prepare_private_control_devices(
            &tree.witness().unwrap(),
        )
        .unwrap();
        let tree = tree
            .attach_device_inner(DeviceMounts::PrivateControl(devices))
            .unwrap();
        let init = tree.init.as_ref().unwrap();
        send_packet(
            init.control.as_raw_fd(),
            &Packet::new(init.nonce, Phase::ProbePrivateDev, 0, init.parent_pid),
        )
        .unwrap();
        init.receive_phase(Phase::PrivateDevChecked).unwrap();
        let mut tree = tree.prepare_process_filesystems().unwrap();
        let observed = tree.process_filesystems.unwrap();
        assert!(tree.init.as_ref().unwrap().proc_context.is_none());
        assert!(tree.init.as_ref().unwrap().proc_mount.is_some());
        let init = tree.init.as_ref().unwrap();
        let fds: Vec<_> = fs::read_dir(format!("/proc/{}/fd", init.identity.pid))
            .unwrap()
            .map(|row| row.unwrap().file_name())
            .collect();
        assert_eq!(fds, [std::ffi::OsString::from("3")]);
        init.verify_process_filesystems(
            tree.base_devices.unwrap(),
            tree.device_node.unwrap(),
            Some(observed),
        )
        .unwrap();
        send_packet(
            init.control.as_raw_fd(),
            &Packet::new(
                init.nonce,
                Phase::ProbeProcessFilesystems,
                0,
                init.parent_pid,
            ),
        )
        .unwrap();
        init.receive_phase(Phase::ProcessFilesystemsChecked)
            .unwrap();
        init.verify_process_filesystems(
            tree.base_devices.unwrap(),
            tree.device_node.unwrap(),
            Some(observed),
        )
        .unwrap();
        let fds: Vec<_> = fs::read_dir(format!("/proc/{}/fd", init.identity.pid))
            .unwrap()
            .map(|row| row.unwrap().file_name())
            .collect();
        assert_eq!(fds, [std::ffi::OsString::from("3")]);
        match tree.bases.as_ref().unwrap() {
            BaseMounts::PrivateControl(value) => value.verify_images_unchanged().unwrap(),
            _ => panic!("private control cannot create production admission"),
        }
        assert_eq!(host_pty_identity(), original_host_pty);
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
        assert!(!lease_available(identity_root.path()));
        {
            let retired = tree.reap_init().unwrap();
            let views = &retired.tree.init.as_ref().unwrap().namespaces.held;
            assert_eq!(views.len(), 1);
            assert_eq!(views[0].1, libc::CLONE_NEWPID);
            assert!(retired.tree.init.as_ref().unwrap().proc_context.is_none());
            assert!(retired.tree.init.as_ref().unwrap().proc_mount.is_none());
            assert!(!lease_available(identity_root.path()));
        }
        let exit = tree.retire().unwrap();
        assert_eq!((exit.init.reason, exit.init.status), (libc::CLD_EXITED, 0));
        assert_eq!(
            (exit.keeper.reason, exit.keeper.status),
            (libc::CLD_EXITED, 0)
        );
        assert!(lease_available(identity_root.path()));
        assert_eq!(children(), original_children);
        println!(
            "private proc/devpts control: exact owned PID namespace with only PID1; read-only proc hidepid=invisible and mapped readproc GID; new devpts bounded1024 with mapped tty GID; relative private ptmx; exact-master TIOCGPTPEER and slave-to-master bytes; no host proc/pts bind; fd3 only; actual PID1 reap, live namespace close, DEV and loops retire, keeper reap; Android=0 production admission=false"
        );

        for negative in ["wrong_nonce", "extra_fd", "wrong_phase"] {
            let (identity_root, lease) = broker_fixture();
            let tree =
                IsolatedNamespaces::from_mapped(mapped_private(lease, child::Mode::UserNamespace))
                    .unwrap();
            let bases = crate::production_mounts::private_control::prepare_private_control_mounts(
                &tree.witness().unwrap(),
            )
            .unwrap();
            let tree = tree
                .attach_base_inner(BaseMounts::PrivateControl(bases))
                .unwrap();
            let devices =
                crate::production_devices::private_control::prepare_private_control_devices(
                    &tree.witness().unwrap(),
                )
                .unwrap();
            let tree = tree
                .attach_device_inner(DeviceMounts::PrivateControl(devices))
                .unwrap();
            let init = tree.init.as_ref().unwrap();
            let mut nonce = init.nonce;
            if negative == "wrong_nonce" {
                nonce[0] ^= 1;
            }
            let phase = if negative == "wrong_phase" {
                Phase::MountPrivateDev
            } else {
                Phase::PrepareProcessFilesystems
            };
            let packet = Packet::new(nonce, phase, 0, init.parent_pid);
            if negative == "extra_fd" {
                let unrelated = OpenOptions::new()
                    .read(true)
                    .custom_flags(libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                    .open("/dev/null")
                    .unwrap();
                send_one_fd(init.control.as_raw_fd(), &packet, unrelated.as_fd()).unwrap();
            } else {
                send_packet(init.control.as_raw_fd(), &packet).unwrap();
            }
            assert!(init.receive_phase(Phase::ProcessFilesystemsReady).is_err());
            let exit = tree.retire().unwrap();
            assert_eq!(exit.init.reason, libc::CLD_EXITED);
            assert_ne!(exit.init.status, 0);
            assert_eq!(
                (exit.keeper.reason, exit.keeper.status),
                (libc::CLD_EXITED, 0)
            );
            assert!(lease_available(identity_root.path()));
            assert_eq!(children(), original_children);
            assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
            assert_eq!(host_pty_identity(), original_host_pty);
            println!(
                "private proc/devpts negative: {negative}; no-extra-FD fixed receiver rejected before ready; owned PID1, mounts, loops and keeper actually retired"
            );
        }

        // An actual owned child sends a private /dev/null instead of its
        // already-created fs_context. The peer/nonce/phase are all legitimate,
        // so this exercises the broker's descriptor gate before fsmount.
        {
            let (identity_root, lease) = broker_fixture();
            let tree = IsolatedNamespaces::from_mapped(mapped_private(
                lease,
                child::Mode::ProcessFilesystemsBadContext,
            ))
            .unwrap();
            let bases = crate::production_mounts::private_control::prepare_private_control_mounts(
                &tree.witness().unwrap(),
            )
            .unwrap();
            let tree = tree
                .attach_base_inner(BaseMounts::PrivateControl(bases))
                .unwrap();
            let devices =
                crate::production_devices::private_control::prepare_private_control_devices(
                    &tree.witness().unwrap(),
                )
                .unwrap();
            let mut tree = tree
                .attach_device_inner(DeviceMounts::PrivateControl(devices))
                .unwrap();
            let init = tree.init.as_mut().unwrap();
            send_packet(
                init.control.as_raw_fd(),
                &Packet::new(
                    init.nonce,
                    Phase::PrepareProcessFilesystems,
                    0,
                    init.parent_pid,
                ),
            )
            .unwrap();
            init.receive_proc_context().unwrap();
            assert!(matches!(
                init.materialize_proc_context(),
                Err(NamespaceError::Rejected(
                    "proc context descriptor shape differs"
                ))
            ));
            assert!(init.proc_context.is_some());
            assert!(init.proc_mount.is_none());
            assert!(!lease_available(identity_root.path()));
            let exit = tree.retire().unwrap();
            assert_eq!((exit.init.reason, exit.init.status), (libc::CLD_EXITED, 0));
            assert_eq!(
                (exit.keeper.reason, exit.keeper.status),
                (libc::CLD_EXITED, 0)
            );
            assert!(lease_available(identity_root.path()));
            assert_eq!(children(), original_children);
            assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
            assert_eq!(host_pty_identity(), original_host_pty);
            println!(
                "private proc broker negative: wrong_context_fd; authenticated owned PID1 private DEV descriptor rejected before fsmount; context and mount custody closed after actual PID1 reap; DEV, loops and keeper actually retired"
            );
        }
        assert_eq!(fs::read("/proc/self/uid_map").unwrap(), original_uid);
        assert_eq!(fs::read("/proc/self/gid_map").unwrap(), original_gid);
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
        assert_eq!(namespace_nodes(), original_namespaces);
        assert_eq!(host_pty_identity(), original_host_pty);
    }
    #[test]
    #[ignore = "requires reviewed root private writable-proc and fixed SELinux xattr observation"]
    fn privileged_private_writable_proc_controls() {
        assert_eq!(unsafe { libc::getuid() }, 0);
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let original_children = children();
        let original_mounts = fs::read("/proc/self/mountinfo").unwrap();
        let maps = [
            fs::read("/proc/self/uid_map").unwrap(),
            fs::read("/proc/self/gid_map").unwrap(),
        ];
        let namespaces = || {
            ["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"].map(|name| {
                Node::of(&File::open(format!("/proc/self/ns/{name}")).unwrap()).unwrap()
            })
        };
        let original_namespaces = namespaces();
        for negative in [
            None,
            Some("wrong_nonce"),
            Some("extra_fd"),
            Some("wrong_phase"),
        ] {
            let (identity_root, lease) = broker_fixture();
            let mode = if negative.is_none() {
                child::Mode::WritableProcControl
            } else {
                child::Mode::UserNamespace
            };
            let tree = IsolatedNamespaces::from_mapped(mapped_private(lease, mode)).unwrap();
            let bases = crate::production_mounts::private_control::prepare_private_control_mounts(
                &tree.witness().unwrap(),
            )
            .unwrap();
            let tree = tree
                .attach_base_inner(BaseMounts::PrivateControl(bases))
                .unwrap();
            let devices =
                crate::production_devices::private_control::prepare_private_control_devices(
                    &tree.witness().unwrap(),
                )
                .unwrap();
            let mut tree = tree
                .attach_device_inner(DeviceMounts::PrivateControl(devices))
                .unwrap()
                .prepare_process_filesystems()
                .unwrap()
                .prepare_private_binder()
                .unwrap();
            if let Some(kind) = negative {
                let init = tree.init.as_ref().unwrap();
                let mut nonce = init.nonce;
                if kind == "wrong_nonce" {
                    nonce[0] ^= 1;
                }
                let phase = if kind == "wrong_phase" {
                    Phase::PrepareBinder
                } else {
                    Phase::PrepareWritableProc
                };
                let packet = Packet::new(nonce, phase, 0, init.parent_pid);
                if kind == "extra_fd" {
                    let unrelated = OpenOptions::new()
                        .read(true)
                        .custom_flags(libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                        .open("/dev/null")
                        .unwrap();
                    send_one_fd(init.control.as_raw_fd(), &packet, unrelated.as_fd()).unwrap();
                } else {
                    send_packet(init.control.as_raw_fd(), &packet).unwrap();
                }
                assert!(init.receive_phase(Phase::WritableProcReady).is_err());
            } else {
                tree = tree.prepare_writable_proc().unwrap();
                let init = tree.init.as_ref().unwrap();
                writable_proc::trace_private_proc_authority(init).unwrap();
                send_packet(
                    init.control.as_raw_fd(),
                    &Packet::new(init.nonce, Phase::ProbeWritableProc, 0, init.parent_pid),
                )
                .unwrap();
                let xattr_errno = writable_proc::receive_xattr_observation(init).unwrap();
                let mut observation = tree.writable_proc.take().unwrap();
                observation.verify(tree.init.as_ref().unwrap()).unwrap();
                tree.writable_proc = Some(observation);
                let root = held_child_root(tree.init.as_ref().unwrap()).unwrap();
                let dev = root_subdirectory(&root, c"dev").unwrap();
                let raw = unsafe {
                    libc::openat(
                        dev.as_raw_fd(),
                        c"selinux-xattr-private-observation".as_ptr(),
                        libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                    )
                };
                assert_eq!(raw, -1);
                assert_eq!(
                    io::Error::last_os_error().raw_os_error(),
                    Some(libc::ENOENT)
                );
                drop(dev);
                drop(root);
                println!(
                    "private writable-proc observation: exact owned PID1 oom_score_adj original bytes restored; global sysctl write opens denied without writes; fixed private DEV security.selinux boot_status_prop set/get errno={xattr_errno}; attribute_storage_supported={}; MAC_qualified=false Android=0",
                    xattr_errno == 0
                );
            }
            match tree.bases.as_ref().unwrap() {
                BaseMounts::PrivateControl(value) => value.verify_images_unchanged().unwrap(),
                _ => panic!("no production admission in private control"),
            }
            assert!(!lease_available(identity_root.path()));
            let exit = tree.retire().unwrap();
            assert_eq!(exit.init.reason, libc::CLD_EXITED);
            if negative.is_none() {
                assert_eq!(exit.init.status, 0);
            } else {
                assert_ne!(exit.init.status, 0);
            }
            assert_eq!(
                (exit.keeper.reason, exit.keeper.status),
                (libc::CLD_EXITED, 0)
            );
            assert!(lease_available(identity_root.path()));
            assert_eq!(children(), original_children);
            assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
            assert_eq!(fs::read("/proc/self/uid_map").unwrap(), maps[0]);
            assert_eq!(fs::read("/proc/self/gid_map").unwrap(), maps[1]);
            assert_eq!(namespaces(), original_namespaces);
            println!(
                "private writable-proc path {negative:?}: actual PID1 reap, live-view close, image/DEV retirement, keeper reap; original host namespace and public maps unchanged"
            );
        }
    }
    #[test]
    #[ignore = "requires root-reviewed sealed static ELF and same owned PID1 post-exec control"]
    fn privileged_private_postexec_proc_controls() {
        assert_eq!(unsafe { libc::getuid() }, 0);
        assert_eq!(unsafe { libc::geteuid() }, 0);
        let original_children = children();
        let original_mounts = fs::read("/proc/self/mountinfo").unwrap();
        let maps = [
            fs::read("/proc/self/uid_map").unwrap(),
            fs::read("/proc/self/gid_map").unwrap(),
        ];
        let namespaces = || {
            ["user", "pid", "mnt", "ipc", "uts", "net", "cgroup"].map(|name| {
                Node::of(&File::open(format!("/proc/self/ns/{name}")).unwrap()).unwrap()
            })
        };
        let original_namespaces = namespaces();
        let (identity_root, lease) = broker_fixture();
        let tree = IsolatedNamespaces::from_mapped(mapped_private(
            lease,
            child::Mode::PostExecProcControl,
        ))
        .unwrap();
        let bases = crate::production_mounts::private_control::prepare_private_control_mounts(
            &tree.witness().unwrap(),
        )
        .unwrap();
        let tree = tree
            .attach_base_inner(BaseMounts::PrivateControl(bases))
            .unwrap();
        let devices = crate::production_devices::private_control::prepare_private_control_devices(
            &tree.witness().unwrap(),
        )
        .unwrap();
        let mut tree = tree
            .attach_device_inner(DeviceMounts::PrivateControl(devices))
            .unwrap()
            .prepare_process_filesystems()
            .unwrap()
            .prepare_private_binder()
            .unwrap()
            .prepare_writable_proc()
            .unwrap();
        let observed = private_postexec::run_private(&mut tree).unwrap();
        match tree.bases.as_ref().unwrap() {
            BaseMounts::PrivateControl(value) => value.verify_images_unchanged().unwrap(),
            _ => panic!("no production admission in private post-exec control"),
        }
        assert!(!lease_available(identity_root.path()));
        let exit = tree.retire().unwrap();
        assert_eq!((exit.init.reason, exit.init.status), (libc::CLD_EXITED, 0));
        assert_eq!(
            (exit.keeper.reason, exit.keeper.status),
            (libc::CLD_EXITED, 0)
        );
        assert!(lease_available(identity_root.path()));
        assert_eq!(children(), original_children);
        assert_eq!(fs::read("/proc/self/mountinfo").unwrap(), original_mounts);
        assert_eq!(fs::read("/proc/self/uid_map").unwrap(), maps[0]);
        assert_eq!(fs::read("/proc/self/gid_map").unwrap(), maps[1]);
        assert_eq!(namespaces(), original_namespaces);
        println!(
            "private fixed post-exec: same PID1 and new mm, zero caps/NNP/locked securebits/dumpable0; actual host proc inode mapped ownership verified before CHECK; own original-value write/readback, protected-global open denials; security.selinux actual tmpfs errno={observed}; both owned PIDFD reaps and private mounts/loop retirement; Android=0 production_admission=false MAC_qualified=false"
        );
    }
}

fn processfs_parent_error(
    error: NamespaceError,
    source_file: &'static str,
    source_line: u32,
) -> NamespaceError {
    match error {
        NamespaceError::Io(source) => io::Error::new(
            source.kind(),
            format!("processfs parent {source_file}:{source_line}: {source}"),
        )
        .into(),
        other => other,
    }
}
