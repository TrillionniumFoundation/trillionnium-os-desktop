//! Six fixed original CP3A storage bind/slave/shared operations.
//! No caller pathname, flag or namespace descriptor selects an operation.
use super::*;
use crate::production_mac::{MacStorageDirectoryWitness, StorageDirectoryRole};
use crate::production_namespace::OriginalInitStorageBindRequest;
use mount_helper::{ExpectedNode, Helper, InitialOperation, InitialResult};
use std::rc::Rc;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum OriginalInitStorageBindKind {
    BindInstaller,
    BindAndroidWritable,
    SlaveInstaller,
    SlaveAndroidWritable,
    SharedInstaller,
    SharedAndroidWritable,
}

impl OriginalInitStorageBindKind {
    pub(crate) const ALL: [Self; 6] = [
        Self::BindInstaller,
        Self::BindAndroidWritable,
        Self::SlaveInstaller,
        Self::SlaveAndroidWritable,
        Self::SharedInstaller,
        Self::SharedAndroidWritable,
    ];
    pub(crate) fn target(self) -> &'static CStr {
        match self {
            Self::BindInstaller | Self::SlaveInstaller | Self::SharedInstaller => c"/mnt/installer",
            Self::BindAndroidWritable
            | Self::SlaveAndroidWritable
            | Self::SharedAndroidWritable => c"/mnt/androidwritable",
        }
    }
    fn leaf(self) -> &'static CStr {
        match self {
            Self::BindInstaller | Self::SlaveInstaller | Self::SharedInstaller => c"installer",
            Self::BindAndroidWritable
            | Self::SlaveAndroidWritable
            | Self::SharedAndroidWritable => c"androidwritable",
        }
    }
    pub(crate) fn flags(self) -> u64 {
        match self {
            Self::BindInstaller | Self::BindAndroidWritable => 0x5000,
            Self::SlaveInstaller | Self::SlaveAndroidWritable => 0x8_0000,
            Self::SharedInstaller | Self::SharedAndroidWritable => 0x10_0000,
        }
    }
    pub(crate) fn is_bind(self) -> bool {
        matches!(self, Self::BindInstaller | Self::BindAndroidWritable)
    }
    fn original_index(self) -> usize {
        match self {
            Self::BindInstaller | Self::SlaveInstaller | Self::SharedInstaller => 1,
            Self::BindAndroidWritable
            | Self::SlaveAndroidWritable
            | Self::SharedAndroidWritable => 2,
        }
    }
    fn operation(self) -> InitialOperation {
        match self {
            Self::BindInstaller => InitialOperation::BindInstaller,
            Self::BindAndroidWritable => InitialOperation::BindAndroidWritable,
            Self::SlaveInstaller => InitialOperation::SlaveInstaller,
            Self::SlaveAndroidWritable => InitialOperation::SlaveAndroidWritable,
            Self::SharedInstaller => InitialOperation::SharedInstaller,
            Self::SharedAndroidWritable => InitialOperation::SharedAndroidWritable,
        }
    }
}

const LEAVES: [&CStr; 3] = [c"user", c"installer", c"androidwritable"];

fn names(file: &File) -> Result<BTreeSet<std::ffi::OsString>> {
    let mut result = BTreeSet::new();
    for entry in std::fs::read_dir(format!("/proc/self/fd/{}", file.as_raw_fd()))? {
        require(
            result.len() < 4,
            "bounded original storage directory inventory",
        )?;
        require(
            result.insert(entry?.file_name()),
            "duplicate original storage directory",
        )?;
    }
    Ok(result)
}

fn directory_shape(file: &File, uid: u32, gid: u32) -> Result<()> {
    let m = file.metadata()?;
    let mut fs: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut fs) })?;
    require(
        fs_type(file)? == 0x0102_1994
            && fs.f_flag as u64 & 15 == ACTIVATION_FLAGS
            && (fs.f_blocks as u64).checked_mul(fs.f_frsize as u64)
                == Some(init_storage::STORAGE_BYTES)
            && fs.f_files as u64 == init_storage::STORAGE_INODES
            && m.mode() == libc::S_IFDIR | 0o755
            && m.uid() == uid
            && m.gid() == gid
            && m.nlink() == 2
            && names(file)?.is_empty(),
        "original storage branch must be an empty mapped bounded tmpfs directory",
    )?;
    require_absent_xattr(file, c"security.capability")
}

#[derive(Debug)]
struct StorageDirectories {
    context: RuntimeMacOwner,
    labels: MacStorageDirectoryWitness,
    generation: ExecutedInitGeneration,
    uids: IdRange,
    gids: IdRange,
    root: File,
    root_identity: FileIdentity,
    root_mount: u64,
    namespace: File,
    parent: File,
    parent_identity: FileIdentity,
    parent_mount: u64,
    leaves: [File; 3],
    identities: [FileIdentity; 3],
}

/// Clones retain this one actual same-thread owner; they do not reacquire a
/// policy, adopt a numeric namespace or recreate a declaration as authority.
#[derive(Clone, Debug)]
pub(crate) struct OriginalInitStorageDirectories(Rc<StorageDirectories>);

impl OriginalInitStorageDirectories {
    pub(crate) fn revalidate(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        init.revalidate_capability_contract()?;
        let held = &self.0;
        let (mac, selection) = held.context.objects()?;
        held.context.require_pair(mac, init.selection())?;
        require(
            std::ptr::eq(selection, init.selection()) && init.generation()? == held.generation,
            "original storage directories belong to another owner",
        )?;
        let ns = init.mount_namespace()?.metadata()?;
        let old_ns = held.namespace.metadata()?;
        require(
            (ns.dev(), ns.ino()) == (old_ns.dev(), old_ns.ino()),
            "storage directories lost the original mount namespace",
        )?;
        held.labels
            .revalidate_init(mac, init)
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        let root = init.root_directory()?;
        self.verify_view(&root)?;
        init.revalidate().map_err(MountError::from)
    }

    pub(crate) fn verify_view(&self, root: &File) -> Result<()> {
        let held = &self.0;
        let (mac, selection) = held.context.objects()?;
        held.labels
            .revalidate(mac, selection)
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        let parent = open_leaf(&root, c"mnt", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let mapped_gid = held
            .gids
            .start
            .checked_add(1000)
            .ok_or(MountError::Rejected("storage parent mapped gid overflow"))?;
        for file in [&held.parent, &parent] {
            init_storage::verify_storage_root(file, held.uids.start, mapped_gid)?;
            require(
                FileIdentity::of(&file.metadata()?) == held.parent_identity
                    && mount_id(file)? == held.parent_mount,
                "original storage parent inode, metadata or mount changed",
            )?;
            require(
                names(file)?
                    == LEAVES
                        .into_iter()
                        .map(|p| std::ffi::OsString::from(p.to_str().unwrap()))
                        .collect(),
                "original storage directory set changed",
            )?;
        }
        for file in [root, &held.root] {
            require(
                FileIdentity::of(&file.metadata()?) == held.root_identity
                    && mount_id(file)? == held.root_mount,
                "storage graph lost its original held guest root",
            )?;
        }
        for (index, file) in held.leaves.iter().enumerate() {
            directory_shape(file, held.uids.start, held.gids.start)?;
            held.labels
                .node(mac, selection, file, StorageDirectoryRole::ALL[index])
                .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
            require(
                FileIdentity::of(&file.metadata()?) == held.identities[index]
                    && mount_id(file)? == held.parent_mount,
                "covered original storage directory changed",
            )?;
        }
        let user = open_leaf(&parent, c"user", libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            FileIdentity::of(&user.metadata()?) == held.identities[0]
                && mount_id(&user)? == held.parent_mount,
            "original storage source path changed",
        )?;
        held.context.objects()?;
        Ok(())
    }

    pub(crate) fn original_files(&self, init: &ExecutedInitWitness<'_>) -> Result<[File; 3]> {
        self.revalidate(init)?;
        Ok([
            self.0.leaves[0].try_clone()?,
            self.0.leaves[1].try_clone()?,
            self.0.leaves[2].try_clone()?,
        ])
    }

    pub(crate) fn parent_mount(&self, init: &ExecutedInitWitness<'_>) -> Result<u64> {
        self.revalidate(init)?;
        Ok(self.0.parent_mount)
    }

    fn same_owner(&self, other: &Self) -> bool {
        Rc::ptr_eq(&self.0, &other.0)
    }
}

#[derive(Debug)]
struct BindTarget {
    file: File,
    identity: FileIdentity,
    mount: u64,
}

#[derive(Debug)]
pub(crate) struct OriginalInitStorageBind {
    directories: OriginalInitStorageDirectories,
    generation: ExecutedInitGeneration,
    notification: crate::production_apex_seccomp::Notification,
    kind: OriginalInitStorageBindKind,
    target: Option<BindTarget>,
    helper: Option<Helper>,
    outcome: Option<InitialResult>,
    retired: bool,
}

impl OriginalInitStorageBind {
    fn original(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitStorageBindRequest<'_>,
    ) -> Result<()> {
        request.revalidate(init)?;
        require(
            !self.retired
                && init.generation()? == self.generation
                && request.generation() == self.generation
                && request.notification() == self.notification
                && request.kind() == self.kind,
            "storage operation differs from its original request",
        )?;
        self.directories.revalidate(init)?;
        let target = self
            .target
            .as_ref()
            .ok_or(MountError::Rejected("storage operation views retired"))?;
        require(
            FileIdentity::of(&target.file.metadata()?) == target.identity
                && mount_id(&target.file)? == target.mount,
            "original pre-operation target lost custody",
        )?;
        request.revalidate(init).map_err(MountError::from)
    }

    fn named_target(&self) -> Result<File> {
        open_leaf(
            &self.directories.0.parent,
            self.kind.leaf(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )
    }

    fn before(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitStorageBindRequest<'_>,
    ) -> Result<()> {
        self.original(init, request)?;
        let named = self.named_target()?;
        let held = self.target.as_ref().unwrap();
        require(
            FileIdentity::of(&named.metadata()?) == held.identity
                && mount_id(&named)? == held.mount,
            "original storage pre-operation target changed",
        )?;
        self.original(init, request)
    }

    fn after(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitStorageBindRequest<'_>,
    ) -> Result<i32> {
        self.original(init, request)?;
        let result = self.outcome.as_ref().ok_or(MountError::Rejected(
            "storage operation has no actual result",
        ))?;
        require(
            result.operation() == self.kind.operation() && (0..=4095).contains(&result.errno()),
            "storage operation result identity or errno differs",
        )?;
        let named = self.named_target()?;
        let held = self.target.as_ref().unwrap();
        if self.kind.is_bind() && result.errno() == 0 {
            require(
                FileIdentity::of(&named.metadata()?) == self.directories.0.identities[0]
                    && mount_id(&named)? != held.mount
                    && mount_id(&named)? != self.directories.0.parent_mount,
                "actual bind did not publish the original source on a distinct mount",
            )?;
            directory_shape(
                &named,
                self.directories.0.uids.start,
                self.directories.0.gids.start,
            )?;
            let (mac, selection) = self.directories.0.context.objects()?;
            self.directories
                .0
                .labels
                .node(mac, selection, &named, StorageDirectoryRole::User)
                .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        } else {
            require(
                FileIdentity::of(&named.metadata()?) == held.identity
                    && mount_id(&named)? == held.mount,
                "failed bind or propagation changed the original target identity",
            )?;
        }
        self.original(init, request)?;
        Ok(result.errno())
    }

    pub(crate) fn run(
        &mut self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitStorageBindRequest<'_>,
    ) -> Result<()> {
        self.before(init, request)?;
        require(
            self.helper.is_none() && self.outcome.is_none(),
            "original storage operation cannot be replayed",
        )?;
        let held = &self.directories.0;
        let target = &self.target.as_ref().unwrap().file;
        let expected = [
            ExpectedNode::of(&held.leaves[0])?,
            ExpectedNode::of(target)?,
            ExpectedNode::of(&held.root)?,
        ];
        self.helper = Some(Helper::spawn_initial(
            [&held.leaves[0], target, &held.root, &held.namespace],
            expected,
            self.kind.operation(),
            request.deadline(),
        )?);
        self.before(init, request)?;
        let helper = self.helper.as_mut().unwrap();
        helper.start()?;
        self.outcome = Some(helper.complete_initial(request.deadline())?);
        self.after(init, request)?;
        Ok(())
    }

    pub(crate) fn actual_errno(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitStorageBindRequest<'_>,
    ) -> Result<i32> {
        self.after(init, request)
    }

    pub(crate) fn actual_target(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitStorageBindRequest<'_>,
        directories: &OriginalInitStorageDirectories,
    ) -> Result<File> {
        require(
            self.directories.same_owner(directories) && self.after(init, request)? == 0,
            "published storage target requires its actual successful original owner",
        )?;
        let target = self.named_target()?;
        self.after(init, request)?;
        Ok(target)
    }

    pub(crate) fn retire_views(&mut self) -> Result<()> {
        if self.retired {
            return Ok(());
        }
        if let Some(helper) = &mut self.helper {
            helper.retire()?;
        }
        self.directories.0.context.objects()?;
        self.helper.take();
        self.target.take();
        self.retired = true;
        Ok(())
    }
}

impl Drop for OriginalInitStorageBind {
    fn drop(&mut self) {
        if !self.retired && self.helper.is_some() {
            if let Some(helper) = self.helper.take() {
                std::mem::forget(helper);
            }
            if let Some(target) = self.target.take() {
                std::mem::forget(target);
            }
            std::mem::forget(self.directories.clone());
        }
    }
}

impl PreparedRuntime {
    pub(crate) fn prepare_original_storage_directories(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        request: &OriginalInitStorageBindRequest<'_>,
    ) -> Result<OriginalInitStorageDirectories> {
        crate::production_devices::require_initial_broker()
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        request.revalidate(init)?;
        require(
            std::ptr::eq(self, init.runtime_owner()?)
                && request.kind() == OriginalInitStorageBindKind::BindInstaller,
            "storage directory admission requires the original first request",
        )?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("original runtime resources retired"))?;
        resources.matches_witness(&init.namespace_witness()?)?;
        let context = resources
            .apex_loops
            .try_borrow()
            .map_err(|_| MountError::Rejected("original MAC owner already borrowed"))?
            .owner()?;
        context.require_pair(mac, init.selection())?;
        let root = init.root_directory()?;
        let parent = open_leaf(&root, c"mnt", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let leaves = [
            open_leaf(&parent, LEAVES[0], libc::O_RDONLY | libc::O_DIRECTORY)?,
            open_leaf(&parent, LEAVES[1], libc::O_RDONLY | libc::O_DIRECTORY)?,
            open_leaf(&parent, LEAVES[2], libc::O_RDONLY | libc::O_DIRECTORY)?,
        ];
        let identities = [
            FileIdentity::of(&leaves[0].metadata()?),
            FileIdentity::of(&leaves[1].metadata()?),
            FileIdentity::of(&leaves[2].metadata()?),
        ];
        require(
            identities
                .iter()
                .map(|id| (id.dev, id.ino))
                .collect::<BTreeSet<_>>()
                .len()
                == 3,
            "three distinct original storage directory inodes required",
        )?;
        let labels = mac
            .original_storage_directories(init)
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        let value = OriginalInitStorageDirectories(Rc::new(StorageDirectories {
            context,
            labels,
            generation: request.generation(),
            uids: resources.uids,
            gids: resources.gids,
            root_identity: FileIdentity::of(&root.metadata()?),
            root_mount: mount_id(&root)?,
            namespace: init.mount_namespace()?.try_clone()?,
            parent_identity: FileIdentity::of(&parent.metadata()?),
            parent_mount: mount_id(&parent)?,
            root,
            parent,
            leaves,
            identities,
        }));
        value.revalidate(init)?;
        request.revalidate(init)?;
        Ok(value)
    }

    pub(crate) fn prepare_original_init_storage_bind(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        request: &OriginalInitStorageBindRequest<'_>,
        directories: &OriginalInitStorageDirectories,
    ) -> Result<OriginalInitStorageBind> {
        crate::production_devices::require_initial_broker()
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        request.revalidate(init)?;
        require(
            std::ptr::eq(self, init.runtime_owner()?),
            "storage operation has another runtime owner",
        )?;
        directories.revalidate(init)?;
        directories.0.context.require_pair(mac, init.selection())?;
        let kind = request.kind();
        let target = open_leaf(
            &directories.0.parent,
            kind.leaf(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let identity = FileIdentity::of(&target.metadata()?);
        let actual_mount = mount_id(&target)?;
        let expected_index = if kind.is_bind() {
            kind.original_index()
        } else {
            0
        };
        require(
            identity == directories.0.identities[expected_index]
                && if kind.is_bind() {
                    actual_mount == directories.0.parent_mount
                } else {
                    actual_mount != directories.0.parent_mount
                },
            "storage request target does not have the original phase identity",
        )?;
        let value = OriginalInitStorageBind {
            directories: directories.clone(),
            generation: request.generation(),
            notification: request.notification(),
            kind,
            target: Some(BindTarget {
                file: target,
                identity,
                mount: actual_mount,
            }),
            helper: None,
            outcome: None,
            retired: false,
        };
        value.before(init, request)?;
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_storage_branches_reject_real_directory_symlinks_and_non_tmpfs_inputs() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::create_dir(temp.path().join("user")).unwrap();
        std::os::unix::fs::symlink("user", temp.path().join("installer")).unwrap();
        let parent = File::open(temp.path()).unwrap();
        assert!(open_leaf(&parent, c"installer", libc::O_RDONLY | libc::O_DIRECTORY).is_err());
        let user = open_leaf(&parent, c"user", libc::O_RDONLY | libc::O_DIRECTORY).unwrap();
        let meta = user.metadata().unwrap();
        assert!(directory_shape(&user, meta.uid(), meta.gid()).is_err());
        assert_eq!(names(&parent).unwrap().len(), 2);
    }
}
