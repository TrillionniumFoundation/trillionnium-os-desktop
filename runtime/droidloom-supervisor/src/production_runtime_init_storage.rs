//! Fixed first-stage /mnt preparation before the original RootShared call.
//! This publishes one real bounded tmpfs while the original main task is held
//! at its received notification. It never completes that mount request: the
//! original propagation syscall still runs through its separate actual helper.
use super::*;
use crate::production_namespace::OriginalInitPropagationRequest;
use mount_helper::{ExpectedNode, Helper, InitialOperation, InitialResult};

pub(super) const STORAGE_BYTES: u64 = 16 * 1024 * 1024;
pub(super) const STORAGE_INODES: u64 = 4096;
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const TMPFS_LABEL: &[u8; 20] = b"u:object_r:tmpfs:s0\0";

fn storage_gid(gid: u32) -> Result<u32> {
    gid.checked_add(1000)
        .ok_or(MountError::Rejected("original storage mapped gid overflow"))
}

fn same_inode(a: &File, b: &File) -> Result<bool> {
    let a = a.metadata()?;
    let b = b.metadata()?;
    Ok((a.dev(), a.ino()) == (b.dev(), b.ino()))
}

fn flags(file: &File) -> Result<libc::statvfs> {
    let mut value: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut value) })?;
    Ok(value)
}

fn empty(file: &File) -> Result<()> {
    let m = FileIdentity::of(&file.metadata()?);
    require(
        file.metadata()?.nlink() == 2
            && std::fs::read_dir(format!("/proc/self/fd/{}", file.as_raw_fd()))?
                .next()
                .transpose()?
                .is_none()
            && FileIdentity::of(&file.metadata()?) == m,
        "storage preparation requires the actual empty original inode",
    )
}

/// Observe the actual synthesized root, not the GSI root directory's EA.
/// The root is the original 16 MiB child-created tmpfs, with its own inode.
fn verify_staging_root(file: &File, uid: u32, gid: u32) -> Result<()> {
    let readable = open_leaf(file, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
    let m = readable.metadata()?;
    let fs = flags(file)?;
    require(
        same_inode(file, &readable)?
            && fs_type(file)? == TMPFS_MAGIC
            && m.mode() == libc::S_IFDIR | 0o755
            && m.uid() == uid
            && m.gid() == gid
            && m.nlink() >= 2
            && fs.f_flag as u64 & 15 == MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV
            && (fs.f_blocks as u64).checked_mul(fs.f_frsize as u64) == Some(16 * 1024 * 1024),
        "original guest root must be the actually held 16 MiB writable tmpfs",
    )?;
    require_exact_xattr(&readable, c"security.selinux", TMPFS_LABEL)?;
    require_absent_xattr(&readable, c"security.capability")
}

pub(crate) fn verify_storage_root(file: &File, uid: u32, gid: u32) -> Result<()> {
    let readable = open_leaf(file, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
    let m = readable.metadata()?;
    let fs = flags(file)?;
    require(
        same_inode(file, &readable)?
            && fs_type(file)? == TMPFS_MAGIC
            && m.mode() == libc::S_IFDIR | 0o755
            && m.uid() == uid
            && m.gid() == gid
            && m.nlink() >= 2
            && fs.f_flag as u64 & 15 == ACTIVATION_FLAGS
            && (fs.f_blocks as u64).checked_mul(fs.f_frsize as u64) == Some(STORAGE_BYTES)
            && fs.f_files as u64 == STORAGE_INODES,
        "storage root must keep its original mapped bounded nosuid nodev noexec tmpfs",
    )?;
    require_exact_xattr(&readable, c"security.selinux", TMPFS_LABEL)?;
    require_absent_xattr(&readable, c"security.capability")
}

fn original_storage_target(resources: &RuntimeResources, root: &File) -> Result<File> {
    let target = open_leaf(root, c"mnt", libc::O_RDONLY | libc::O_DIRECTORY)?;
    let m = target.metadata()?;
    let fs = flags(&target)?;
    require(
        [0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&fs_type(&target)?)
            && m.mode() == libc::S_IFDIR | 0o755
            && m.uid() == resources.uids.start
            && m.gid() == storage_gid(resources.gids.start)?
            && fs.f_flag as u64 & 15 == MOUNT_ATTR_RDONLY | MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV
            && mount_id(&target)? != mount_id(root)?,
        "storage lower target must be the original readonly mapped image directory",
    )?;
    require_exact_xattr(&target, c"security.selinux", TMPFS_LABEL)?;
    require_absent_xattr(&target, c"security.capability")?;
    empty(&target)?;
    Ok(target)
}

#[derive(Debug)]
struct WritableStorageRoot {
    mount: File,
    root: File,
    node: (u64, u64),
    mount_id: u64,
}

impl WritableStorageRoot {
    fn prepare(userns: &File, uids: IdRange, gids: IdRange) -> Result<Self> {
        let context = syscall_fd(unsafe {
            libc::syscall(libc::SYS_fsopen, c"tmpfs".as_ptr(), FSOPEN_CLOEXEC)
        })?;
        for (key, value) in [
            (c"source", c"tmpfs"),
            (c"mode", c"0755"),
            (c"uid", c"0"),
            (c"gid", c"1000"),
            (c"size", c"16777216"),
            (c"nr_inodes", c"4096"),
        ] {
            configure(&context, FSCONFIG_SET_STRING, key, Some(value))?;
        }
        zero_rc(unsafe {
            libc::syscall(
                libc::SYS_fsconfig,
                context.as_raw_fd(),
                FSCONFIG_CMD_CREATE,
                std::ptr::null::<libc::c_char>(),
                std::ptr::null::<libc::c_char>(),
                0,
            )
        } as i32)?;
        let mount = syscall_fd(unsafe {
            libc::syscall(
                libc::SYS_fsmount,
                context.as_raw_fd(),
                FSMOUNT_CLOEXEC,
                ACTIVATION_FLAGS as u32,
            )
        })?;
        drop(context);
        require_detached(&mount)?;
        let root = open_leaf(&mount, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
        verify_storage_root(&root, 0, 1000)?;
        empty(&root)?;
        let m = root.metadata()?;
        let node = (m.dev(), m.ino());
        drop(root);
        let attr = MountAttr {
            attr_set: ACTIVATION_FLAGS | MOUNT_ATTR_IDMAP,
            attr_clr: 0,
            propagation: 0,
            userns_fd: u64::try_from(userns.as_raw_fd())
                .map_err(|_| MountError::Rejected("storage original user namespace FD"))?,
        };
        zero_rc(unsafe {
            libc::syscall(
                libc::SYS_mount_setattr,
                mount.as_raw_fd(),
                c"".as_ptr(),
                AT_EMPTY_PATH,
                &attr,
                std::mem::size_of::<MountAttr>(),
            )
        } as i32)?;
        let mount_id = require_detached(&mount)?;
        let root = open_leaf(&mount, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let value = Self {
            mount,
            root,
            node,
            mount_id,
        };
        value.verify_fresh(uids, gids)?;
        Ok(value)
    }

    fn root(&self) -> &File {
        &self.root
    }
    fn mount(&self) -> &File {
        &self.mount
    }

    fn verify_original_source(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        for file in [&self.mount, &self.root] {
            let m = file.metadata()?;
            require(
                (m.dev(), m.ino()) == self.node && mount_id(file)? == self.mount_id,
                "storage source lost its original held inode and mount",
            )?;
            verify_storage_root(file, uids.start, storage_gid(gids.start)?)?;
        }
        Ok(())
    }

    fn verify_fresh(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        self.verify_original_source(uids, gids)?;
        require(
            require_detached(&self.mount)? == self.mount_id
                && require_detached(&self.root)? == self.mount_id,
            "storage source must still be detached before publication",
        )?;
        empty(&self.root)
    }
}

#[derive(Debug)]
struct MountFiles {
    root: File,
    target: File,
    namespace: File,
    target_identity: FileIdentity,
    target_mount: u64,
    root_identity: FileIdentity,
    root_mount: u64,
    source: WritableStorageRoot,
}

/// Owns the actual new mount and worker. This is never constructed from a
/// receipt, pathname, caller namespace, numeric PID or claimed syscall result.
#[derive(Debug)]
pub(crate) struct OriginalInitStorage {
    context: RuntimeMacOwner,
    generation: ExecutedInitGeneration,
    notification: crate::production_apex_seccomp::Notification,
    uids: IdRange,
    gids: IdRange,
    files: Option<MountFiles>,
    helper: Option<Helper>,
    outcome: Option<InitialResult>,
    retired: bool,
}

impl OriginalInitStorage {
    fn files(&self) -> Result<&MountFiles> {
        self.files
            .as_ref()
            .ok_or(MountError::Rejected("original storage views retired"))
    }

    fn original(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        init.revalidate_capability_contract()?;
        require(
            !self.retired && init.generation()? == self.generation,
            "storage source belongs to another original executed init",
        )?;
        let (mac, selection) = self.context.objects()?;
        self.context.require_pair(mac, init.selection())?;
        require(
            std::ptr::eq(selection, init.selection()),
            "storage source selection is not the original paired owner",
        )?;
        let files = self.files()?;
        let actual_namespace = init.mount_namespace()?.metadata()?;
        let held_namespace = files.namespace.metadata()?;
        require(
            (actual_namespace.dev(), actual_namespace.ino())
                == (held_namespace.dev(), held_namespace.ino()),
            "original storage namespace changed",
        )?;
        let root = init.root_directory()?;
        verify_staging_root(&root, self.uids.start, self.gids.start)?;
        require(
            FileIdentity::of(&files.root.metadata()?) == files.root_identity
                && same_inode(&root, &files.root)?
                && mount_id(&root)? == files.root_mount
                && mount_id(&files.root)? == files.root_mount
                && FileIdentity::of(&files.target.metadata()?) == files.target_identity
                && mount_id(&files.target)? == files.target_mount,
            "original root or retained lower mount lost custody",
        )?;
        files.source.verify_original_source(self.uids, self.gids)?;
        self.context.objects()?;
        init.revalidate().map_err(MountError::from)
    }

    fn request(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<()> {
        request.revalidate(init)?;
        self.original(init)?;
        require(
            request.generation() == self.generation
                && request.notification() == self.notification
                && request.kind() == OriginalInitPropagationKind::RootShared,
            "storage guard belongs to another original pending request",
        )?;
        request.revalidate(init).map_err(MountError::from)
    }

    fn before_operation(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<()> {
        self.request(init, request)?;
        let files = self.files()?;
        files.source.verify_fresh(self.uids, self.gids)?;
        let visible = open_leaf(&files.root, c"mnt", libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            FileIdentity::of(&visible.metadata()?) == files.target_identity
                && mount_id(&visible)? == files.target_mount,
            "original lower target changed before actual move_mount",
        )?;
        self.request(init, request)
    }

    fn after_operation(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<i32> {
        self.request(init, request)?;
        let result = self.outcome.as_ref().ok_or(MountError::Rejected(
            "original storage operation has no actual outcome",
        ))?;
        require(
            result.operation() == InitialOperation::Storage && (0..=4095).contains(&result.errno()),
            "actual helper outcome has another finite operation or errno",
        )?;
        let files = self.files()?;
        let visible = open_leaf(&files.root, c"mnt", libc::O_RDONLY | libc::O_DIRECTORY)?;
        if result.errno() == 0 {
            require(
                same_inode(&visible, files.source.root())?
                    && mount_id(&visible)? == mount_id(files.source.mount())?,
                "native successful tmpfs publication is not the held new mount",
            )?;
            verify_storage_root(&visible, self.uids.start, storage_gid(self.gids.start)?)?;
        } else {
            require(
                FileIdentity::of(&visible.metadata()?) == files.target_identity
                    && mount_id(&visible)? == files.target_mount,
                "failed native tmpfs operation changed the original visible target",
            )?;
            files.source.verify_fresh(self.uids, self.gids)?;
        }
        self.request(init, request)?;
        Ok(result.errno())
    }

    pub(crate) fn run(
        &mut self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<()> {
        self.before_operation(init, request)?;
        require(
            self.helper.is_none() && self.outcome.is_none(),
            "original storage helper cannot be replayed",
        )?;
        let files = self.files()?;
        let expected = [
            ExpectedNode::of(files.source.mount())?,
            ExpectedNode::of(&files.target)?,
            ExpectedNode::of(&files.root)?,
        ];
        let helper = Helper::spawn_initial(
            [
                files.source.mount(),
                &files.target,
                &files.root,
                &files.namespace,
            ],
            expected,
            InitialOperation::Storage,
            request.deadline(),
        )?;
        self.helper = Some(helper);
        // The outer namespace guard already retains this value. Only now can
        // the actual original helper cross its creator READY/release barrier.
        self.before_operation(init, request)?;
        let helper = self.helper.as_mut().unwrap();
        helper.start()?;
        self.outcome = Some(helper.complete_initial(request.deadline())?);
        self.after_operation(init, request)?;
        Ok(())
    }

    pub(crate) fn actual_errno(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<i32> {
        self.after_operation(init, request)
    }

    pub(crate) fn published_root(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<File> {
        require(
            self.after_operation(init, request)? == 0,
            "failed native mount cannot issue a published root",
        )?;
        Ok(self.files()?.source.root().try_clone()?)
    }

    /// Borrowed source identity only. The caller must separately prove the
    /// current mount view; this never adopts an init-created bind or namespace.
    pub(crate) fn original_root(&self, init: &ExecutedInitWitness<'_>) -> Result<File> {
        self.original(init)?;
        let result = self.outcome.as_ref().ok_or(MountError::Rejected(
            "original storage operation did not run",
        ))?;
        require(
            result.operation() == InitialOperation::Storage && result.errno() == 0,
            "only the actual successful original operation has a source root",
        )?;
        let root = self.files()?.source.root().try_clone()?;
        self.original(init)?;
        Ok(root)
    }

    /// Reap the helper, then close only this owner's extra views. An attached
    /// mount remains in the original guest tree until that tree's actual reap.
    /// This method does not unmount it or claim global namespace retirement.
    pub(crate) fn retire_views(&mut self) -> Result<()> {
        if self.retired {
            return Ok(());
        }
        if let Some(helper) = self.helper.as_mut() {
            helper.retire()?;
        }
        self.context.objects()?;
        self.helper.take();
        self.files.take();
        self.retired = true;
        Ok(())
    }
}

impl Drop for OriginalInitStorage {
    fn drop(&mut self) {
        if !self.retired && self.helper.is_some() {
            if let Some(helper) = self.helper.take() {
                std::mem::forget(helper);
            }
            if let Some(files) = self.files.take() {
                std::mem::forget(files);
            }
            std::mem::forget(self.context.clone());
        }
    }
}

impl PreparedRuntime {
    pub(crate) fn prepare_original_init_storage(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<OriginalInitStorage> {
        crate::production_devices::require_initial_broker()
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        request.revalidate(init)?;
        require(
            std::ptr::eq(self, init.runtime_owner()?),
            "new storage source has another original runtime owner",
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
        require(
            request.kind() == OriginalInitPropagationKind::RootShared,
            "storage preparation requires the original first propagation barrier",
        )?;
        let root = init.root_directory()?;
        verify_staging_root(&root, resources.uids.start, resources.gids.start)?;
        let target = original_storage_target(resources, &root)?;
        let target_identity = FileIdentity::of(&target.metadata()?);
        let target_mount = mount_id(&target)?;
        let root_identity = FileIdentity::of(&root.metadata()?);
        let root_mount = mount_id(&root)?;
        let namespace = init.mount_namespace()?.try_clone()?;
        // Anonymous creation has no exported descriptor or mount attachment.
        // A failure here closes the fresh local filesystem without touching
        // any original guest or host inode.
        let source =
            WritableStorageRoot::prepare(&resources.userns, resources.uids, resources.gids)?;
        require(
            !same_inode(source.root(), &target)?
                && source.root().metadata()?.dev() != target.metadata()?.dev()
                && mount_id(source.mount())? != target_mount,
            "original mount must create a distinct new filesystem",
        )?;
        let value = OriginalInitStorage {
            context,
            generation: request.generation(),
            notification: request.notification(),
            uids: resources.uids,
            gids: resources.gids,
            files: Some(MountFiles {
                root,
                target,
                namespace,
                target_identity,
                target_mount,
                root_identity,
                root_mount,
                source,
            }),
            helper: None,
            outcome: None,
            retired: false,
        };
        value.before_operation(init, request)?;
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn original_storage_source_rejects_an_ordinary_directory_and_mapped_gid_overflow() {
        let dir = tempfile::tempdir().unwrap();
        let file = File::open(dir.path()).unwrap();
        let uid = unsafe { libc::geteuid() };
        let gid = unsafe { libc::getegid() };
        assert!(verify_storage_root(&file, uid, gid).is_err());
        assert!(verify_staging_root(&file, uid, gid).is_err());
        assert_eq!(storage_gid(200000).unwrap(), 201000);
        assert!(storage_gid(u32::MAX - 999).is_err());
        assert!(empty(&file).is_ok());
        std::fs::write(dir.path().join("foreign"), b"original data").unwrap();
        assert!(empty(&file).is_err());
    }
}
