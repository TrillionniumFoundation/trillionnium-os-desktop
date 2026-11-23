//! Live, descriptor-owned persistent data and metadata for one admitted tree.
//!
//! This is separate from the public readonly base/APEX provider. Construction
//! requires actual prepared MAC/systemd admission, the same namespace witness,
//! its original durable identity lease, and explicit root-sealed selection v2.
//! No saved receipt, offset, boolean, user path or numeric PID creates a grant.

use super::*;
use super::early::BaseAuthority as _;
use crate::production_execution::PreparedExecution;
use crate::production_selection::{PersistentImagePolicy, ProductionSelection};

#[path = "production_persistent_data_early.rs"]
mod early_storage;
pub(crate) use early_storage::EarlyStorageAdmission;

#[path = "production_persistent_data_backings.rs"]
mod backings;
#[path = "production_persistent_data_loop.rs"]
mod writable_loop;
#[path = "production_persistent_data_superblock.rs"]
mod superblock;

#[cfg(test)]
#[path = "production_persistent_data_controls.rs"]
pub(crate) mod private_control;

use backings::OriginalBackingPair;
use writable_loop::WritableLoop;

trait StorageAuthority {
    type Namespace: early::BaseAuthority;
    fn namespace(&self) -> &Self::Namespace;
    fn selection(&self) -> &ProductionSelection;
    fn verify(&self) -> Result<()>;
}

struct LateStorageAdmission<'a, 'tree> {
    namespace: &'a OwnedNamespaceWitness<'tree>,
    selection: &'a ProductionSelection,
    prepared: &'a PreparedExecution,
}

impl<'tree> StorageAuthority for LateStorageAdmission<'_, 'tree> {
    type Namespace = OwnedNamespaceWitness<'tree>;
    fn namespace(&self) -> &Self::Namespace { self.namespace }
    fn selection(&self) -> &ProductionSelection { self.selection }
    fn verify(&self) -> Result<()> {
        self.prepared.revalidate_tree(self.selection, self.namespace)?;
        require(self.namespace.descendant_pid_namespace().is_some(),
            "actual admitted PID-1 tree required for persistent data")
    }
}


const DATA_FLAGS: u64 = MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV;

/// Compare-only projection captured from an actual owned detached mount.
/// These numbers cannot construct a provider, lease or namespace witness.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct PersistentRootObservation {
    pub(crate) device: u64,
    pub(crate) inode: u64,
    pub(crate) mount_id: u64,
    pub(crate) uid: u32,
    pub(crate) gid: u32,
    pub(crate) mode: u32,
}

impl PersistentRootObservation {
    fn capture(file: &File) -> Result<Self> {
        let node = file.metadata()?;
        let value = Self { device: node.dev(), inode: node.ino(), mount_id: mount_id(file)?,
            uid: node.uid(), gid: node.gid(), mode: node.mode() };
        value.verify(file)?;
        Ok(value)
    }

    pub(crate) fn verify(&self, file: &File) -> Result<()> {
        let node = file.metadata()?;
        let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
        zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) })?;
        require(node.dev() == self.device && node.ino() == self.inode
            && node.uid() == self.uid && node.gid() == self.gid && node.mode() == self.mode
            && node.is_dir() && fs_type(file)? == 0xef53 && mount_id(file)? == self.mount_id
            && flags.f_flag as u64 & (MOUNT_ATTR_RDONLY | DATA_FLAGS | 8) == DATA_FLAGS,
            "same actual mapped writable nosuid nodev executable ext4 root required")
    }
}

#[derive(Debug)]
struct MountedData {
    role: usize,
    mount: Option<File>,
    binding: WritableLoop,
    observed: Option<PersistentRootObservation>,
}

#[derive(Debug)]
struct DataResources {
    backings: OriginalBackingPair,
    images: Vec<MountedData>,
    userns: File,
    userns_identity: (u64, u64),
    uids: IdRange,
    gids: IdRange,
    host_uid: u32,
    cohort: String,
    selection_binding: [u8; 32],
    reservation_retention: File,
    reservation_node: FileIdentity,
}

impl DataResources {
    fn matches(&self, admission: &impl StorageAuthority) -> Result<()> {
        admission.verify()?;
        let witness = admission.namespace();
        let selection = admission.selection();
        require_complete_namespace(witness)?;
        let lease = witness.identity_lease()?;
        let namespace = witness.user_namespace().metadata()?;
        require((namespace.dev(), namespace.ino()) == self.userns_identity
            && (self.userns.metadata()?.dev(), self.userns.metadata()?.ino()) == self.userns_identity
            && lease.host_uid() == self.host_uid && lease.broker_cohort() == self.cohort
            && lease.broker_ranges() == (self.uids, self.gids)
            && selection.package_binding() == self.selection_binding
            && FileIdentity::of(&self.reservation_retention.metadata()?) == self.reservation_node,
            "persistent mounts require their same live namespace, selection and lease OFD")?;
        self.backings.revalidate(witness)?;
        admission.verify()?;
        Ok(())
    }

    fn cleanup(&mut self) -> Result<Vec<u64>> {
        // Called only before any send attempt or after the original complete
        // tree has actually retired. syncfs never runs against a caller path.
        for row in &self.images {
            if let Some(mount) = &row.mount {
                row.binding.verify()?;
                // fsmount/open_tree custody descriptors can be O_PATH; syncfs
                // needs an ordinary FD on the very same retained filesystem.
                let sync_root = open_leaf(mount, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
                require(mount_id(&sync_root)? == mount_id(mount)?
                    && sync_root.metadata()?.dev() == row.binding.device,
                    "sync only this exact owned persistent filesystem")?;
                zero_rc(unsafe { libc::syncfs(sync_root.as_raw_fd()) })?;
            }
        }
        for row in &mut self.images { drop(row.mount.take()); }
        let mut released = Vec::new();
        for row in &mut self.images {
            if row.binding.is_bound() { released.push(row.binding.retire()?); }
        }
        self.backings.durable_after_unbind()?;
        Ok(released)
    }
}

/// Not Clone or Deserialize. Unknown export/retirement keeps actual mounts,
/// loops, writable backing OFDs and the same durable reservation OFD alive.
#[derive(Debug)]
pub(crate) struct PreparedPersistentData {
    resources: Option<DataResources>,
    exported: bool,
}

#[derive(Debug, Serialize)]
pub(crate) struct PersistentDataRetirement {
    images: usize,
    owned_filesystems_synced: bool,
    detached_descriptors_closed: bool,
    owned_loop_devices_observed_unbound: Vec<u64>,
    original_backing_files_synced_after_unbind: bool,
    after_owned_tree_exit: bool,
}

impl PreparedPersistentData {
    /// Revalidate retained original resources without extending a preparation
    /// deadline or comparing initial IDs with later cloned mount IDs. The
    /// executed child graph is separately owned by NativeMountEpoch's complete
    /// actual old-to-new mapping, including /data and /metadata.
    pub(crate) fn revalidate_owned_lifetime(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        self.revalidate_lifetime(witness)
    }

    fn revalidate_lifetime(&self, witness: &impl early::BaseAuthority) -> Result<()> {
        let resources = self.resources.as_ref().ok_or(MountError::Rejected("persistent data custody absent"))?;
        witness.revalidate_live_admission()?;
        let lease = witness.identity_lease()?;
        let namespace = witness.user_namespace().metadata()?;
        require((namespace.dev(), namespace.ino()) == resources.userns_identity
            && lease.host_uid() == resources.host_uid && lease.broker_cohort() == resources.cohort
            && lease.broker_ranges() == (resources.uids, resources.gids)
            && FileIdentity::of(&resources.reservation_retention.metadata()?) == resources.reservation_node
            && resources.images.len() == 2 && resources.images[0].role == 0 && resources.images[1].role == 1,
            "original persistent owner and complete lease binding changed")?;
        resources.backings.revalidate(witness)?;
        for row in &resources.images {
            row.binding.verify()?;
            let mount = row.mount.as_ref().ok_or(MountError::Rejected("original persistent mount FD absent"))?;
            row.observed.ok_or(MountError::Rejected("original persistent root observation absent"))?.verify(mount)?;
        }
        witness.revalidate_live_admission()?;
        Ok(())
    }

    pub(crate) fn prepare(witness: &OwnedNamespaceWitness<'_>, selection: &ProductionSelection,
        prepared: &PreparedExecution) -> Result<Self> {
        Self::prepare_with(&LateStorageAdmission { namespace:witness, selection, prepared })
    }

    fn prepare_with(admission: &impl StorageAuthority) -> Result<Self> {
        let witness = admission.namespace();
        let selection = admission.selection();
        admission.verify()?;
        require_complete_namespace(witness)?;
        let lease = witness.identity_lease()?;
        let retention = lease.broker_retain_reservation()?;
        let reservation_node = FileIdentity::of(&retention.metadata()?);
        let userns = witness.user_namespace().try_clone()?;
        let namespace = userns.metadata()?;
        let (uids, gids) = lease.broker_ranges();
        let backings = OriginalBackingPair::open(admission)?;
        let mut value = Self {
            resources: Some(DataResources { backings, images: Vec::new(), userns,
                userns_identity: (namespace.dev(), namespace.ino()), uids, gids,
                host_uid: lease.host_uid(), cohort: lease.broker_cohort().to_owned(),
                selection_binding: selection.package_binding(),
                reservation_retention: retention, reservation_node }),
            exported: false,
        };
        let resources = value.resources.as_mut().ok_or(MountError::Rejected("persistent resource owner absent"))?;
        resources.matches(admission)?;
        writable_loop::reject_aliases(&resources.backings.nodes, &resources.images)?;
        for index in 0..2 {
            resources.matches(admission)?;
            let binding = WritableLoop::attach(&resources.backings.files[index])?;
            // Record ownership before any fallible verify/mount operation.
            resources.images.push(MountedData { role: index, mount: None, binding, observed: None });
            resources.images[index].binding.verify()?;
            writable_loop::reject_aliases(&resources.backings.nodes, &resources.images)?;
            let mount = detached_data_mount(&resources.images[index].binding,
                &resources.backings.policies[index], &resources.userns, uids, gids)?;
            resources.images[index].mount = Some(mount);
            let mount = resources.images[index].mount.as_ref().unwrap();
            resources.images[index].observed = Some(PersistentRootObservation::capture(mount)?);
            resources.matches(admission)?;
        }
        require(resources.images.len() == 2
            && resources.images[0].binding.device != resources.images[1].binding.device,
            "complete distinct original data and metadata mount set required")?;
        resources.matches(admission)?;
        Ok(value)
    }

    pub(crate) fn descriptors_for_transfer<'a>(&'a mut self, witness: &OwnedNamespaceWitness<'_>,
        selection: &ProductionSelection, prepared: &PreparedExecution)
        -> Result<([BorrowedFd<'a>; 2], [PersistentRootObservation; 2])> {
        self.transfer_with(&LateStorageAdmission { namespace:witness, selection, prepared })
    }

    fn transfer_with<'a>(&'a mut self, admission: &impl StorageAuthority)
        -> Result<([BorrowedFd<'a>; 2], [PersistentRootObservation; 2])> {
        require(!self.exported, "persistent mount descriptors transfer exactly once")?;
        let resources = self.resources.as_ref().ok_or(MountError::Rejected("persistent data already retired"))?;
        resources.matches(admission)?;
        require(resources.images.len() == 2 && resources.images[0].role == 0 && resources.images[1].role == 1,
            "exact data then metadata descriptor order required")?;
        let mut observations = Vec::with_capacity(2);
        for row in &resources.images {
            row.binding.verify()?;
            let mount = row.mount.as_ref().ok_or(MountError::Rejected("held persistent mount absent"))?;
            let observed = row.observed.ok_or(MountError::Rejected("actual persistent mount observation absent"))?;
            require(require_detached(mount)? == observed.mount_id, "persistent mount remains detached from broker")?;
            observed.verify(mount)?;
            observations.push(observed);
        }
        writable_loop::reject_aliases(&resources.backings.nodes, &resources.images)?;
        resources.matches(admission)?;
        self.exported = true;
        Ok(([
            resources.images[0].mount.as_ref().unwrap().as_fd(),
            resources.images[1].mount.as_ref().unwrap().as_fd(),
        ], [observations[0], observations[1]]))
    }

    pub(crate) fn retire_after_tree(mut self, retired: &RetiredTreeWitness<'_>) -> Result<PersistentDataRetirement> {
        let resources = self.resources.as_ref().ok_or(MountError::Rejected("persistent data already retired"))?;
        retired.verify_mount_retirement(&resources.userns, resources.host_uid, &resources.cohort)?;
        self.cleanup(true)
    }

    pub(crate) fn retire_untransferred(mut self) -> Result<PersistentDataRetirement> {
        require(!self.exported, "attempted persistent transfer requires original tree retirement")?;
        self.cleanup(false)
    }

    fn cleanup(&mut self, after_owned_tree_exit: bool) -> Result<PersistentDataRetirement> {
        let resources = self.resources.as_mut().ok_or(MountError::Rejected("persistent data already retired"))?;
        let images = resources.images.len();
        let released = resources.cleanup()?;
        // Only this successful path releases backing and reservation locks.
        drop(self.resources.take());
        Ok(PersistentDataRetirement { images, owned_filesystems_synced: true,
            detached_descriptors_closed: true, owned_loop_devices_observed_unbound: released,
            original_backing_files_synced_after_unbind: true, after_owned_tree_exit })
    }
}

impl Drop for PreparedPersistentData {
    fn drop(&mut self) {
        if !self.exported {
            if let Some(resources) = self.resources.as_mut() {
                if resources.cleanup().is_ok() { drop(self.resources.take()); return; }
            }
        }
        if let Some(resources) = self.resources.take() { std::mem::forget(resources); }
    }
}

fn detached_data_mount(binding: &WritableLoop, policy: &PersistentImagePolicy, userns: &File,
    uids: IdRange, gids: IdRange) -> Result<File> {
    binding.verify()?;
    let mapped = policy.mapped_root(uids, gids).map_err(MountError::Rejected)?;
    let context = syscall_fd(unsafe { libc::syscall(libc::SYS_fsopen, c"ext4".as_ptr(), FSOPEN_CLOEXEC) })?;
    let source = text_name(&format!("/proc/self/fd/{}", binding.file()?.as_raw_fd()))?;
    configure(&context, FSCONFIG_SET_STRING, c"source", Some(&source))?;
    configure(&context, FSCONFIG_SET_FLAG, c"rw", None)?;
    configure(&context, FSCONFIG_SET_STRING, c"errors", Some(c"remount-ro"))?;
    let created = unsafe { libc::syscall(libc::SYS_fsconfig, context.as_raw_fd(), FSCONFIG_CMD_CREATE,
        std::ptr::null::<libc::c_char>(), std::ptr::null::<libc::c_char>(), 0) };
    if created != 0 { return Err(io::Error::last_os_error().into()); }
    let mount = syscall_fd(unsafe { libc::syscall(libc::SYS_fsmount, context.as_raw_fd(), FSMOUNT_CLOEXEC, DATA_FLAGS as u32) })?;
    let original = mount.metadata()?;
    require(original.is_dir() && original.dev() == binding.device
        && original.uid() == policy.guest_root_uid && original.gid() == policy.guest_root_gid
        && original.mode() == libc::S_IFDIR | policy.guest_root_mode,
        "actual original on-disk root identity differs from the selected preimage")?;
    require_detached(&mount)?;
    let attr = MountAttr { attr_set: DATA_FLAGS | MOUNT_ATTR_IDMAP, attr_clr: 0, propagation: 0,
        userns_fd: u64::try_from(userns.as_raw_fd()).map_err(|_| MountError::Rejected("held user namespace descriptor"))? };
    let rc = unsafe { libc::syscall(libc::SYS_mount_setattr, mount.as_raw_fd(), c"".as_ptr(), AT_EMPTY_PATH,
        &attr, std::mem::size_of::<MountAttr>()) };
    if rc != 0 { return Err(io::Error::last_os_error().into()); }
    let observed = PersistentRootObservation::capture(&mount)?;
    require(observed.uid == mapped.0 && observed.gid == mapped.1 && observed.device == binding.device
        && observed.inode == original.ino() && observed.mode == original.mode()
        && require_detached(&mount)? == observed.mount_id,
        "actual IDMAP must preserve original filesystem inode and guest ownership")?;
    binding.verify()?;
    Ok(mount)
}
