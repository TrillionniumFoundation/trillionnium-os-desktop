//! Execute only the original init's two fixed first-stage cleanup requests.
//! The helper stays under the original runtime/namespace owner; setup failure
//! is never turned into an emulated result for a syscall that did not run.
use super::*;
use crate::production_namespace::{OriginalInitUnmountKind, OriginalInitUnmountRequest};
use mount_helper::{ExpectedNode, Helper, InitialOperation, InitialResult};

fn operation(kind: OriginalInitUnmountKind) -> InitialOperation {
    match kind {
        OriginalInitUnmountKind::DebugRamdisk => InitialOperation::DebugRamdisk,
        OriginalInitUnmountKind::SecondStageResources => InitialOperation::SecondStageResources,
    }
}

fn cleanup_target(
    root: &File,
    kind: OriginalInitUnmountKind,
    uids: IdRange,
    gids: IdRange,
) -> Result<File> {
    let target = open_leaf(root, kind.name(), libc::O_RDONLY | libc::O_DIRECTORY)?;
    let metadata = target.metadata()?;
    require(
        metadata.mode() == libc::S_IFDIR | 0o755
            && metadata.uid() == uids.start
            && metadata.gid() == gids.start
            && metadata.nlink() == 2
            && mount_id(&target)? == mount_id(root)?
            && fs_type(&target)? == fs_type(root)?
            && [0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&fs_type(&target)?),
        "original first-stage target must remain the empty directory on the held readonly root",
    )?;
    let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(target.as_raw_fd(), &mut flags) })?;
    require(
        flags.f_flag as u64 & (READONLY_FLAGS | 8) == READONLY_FLAGS,
        "original first-stage target root protection differs",
    )?;
    require_exact_xattr(&target, c"security.selinux", b"u:object_r:tmpfs:s0\0")?;
    require_absent_xattr(&target, c"security.capability")?;
    require(
        std::fs::read_dir(format!("/proc/self/fd/{}", target.as_raw_fd()))?
            .next()
            .transpose()?
            .is_none()
            && FileIdentity::of(&target.metadata()?) == FileIdentity::of(&metadata),
        "original first-stage target must remain completely empty and unchanged",
    )?;
    Ok(target)
}

#[derive(Debug)]
struct CleanupFiles {
    root: File,
    target: File,
    namespace: File,
    identity: FileIdentity,
    target_mount: u64,
}

/// The namespace owner stores this guard before releasing the actual helper.
/// No PID, raw path, claimed errno or caller boolean constructs it.
#[derive(Debug)]
pub(crate) struct OriginalInitCleanup {
    context: RuntimeMacOwner,
    generation: ExecutedInitGeneration,
    notification: crate::production_apex_seccomp::Notification,
    kind: OriginalInitUnmountKind,
    uids: IdRange,
    gids: IdRange,
    files: Option<CleanupFiles>,
    helper: Option<Helper>,
    outcome: Option<InitialResult>,
    retired: bool,
}

impl OriginalInitCleanup {
    fn files(&self) -> Result<&CleanupFiles> {
        self.files.as_ref().ok_or(MountError::Rejected(
            "original init cleanup descriptors retired",
        ))
    }

    fn revalidate(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitUnmountRequest<'_>,
    ) -> Result<()> {
        request.revalidate(init)?;
        require(
            !self.retired
                && self.generation == init.generation()?
                && self.generation == request.generation()
                && self.notification == request.notification()
                && self.kind == request.kind(),
            "fixed cleanup belongs to another original init request",
        )?;
        let (mac, selection) = self.context.objects()?;
        self.context.require_pair(mac, init.selection())?;
        require(
            std::ptr::eq(selection, init.selection()),
            "cleanup original selection differs",
        )?;
        let files = self.files()?;
        let actual_namespace = init.mount_namespace()?.metadata()?;
        let held_namespace = files.namespace.metadata()?;
        require(
            (actual_namespace.dev(), actual_namespace.ino())
                == (held_namespace.dev(), held_namespace.ino()),
            "original init cleanup mount namespace changed",
        )?;
        let target = cleanup_target(&files.root, self.kind, self.uids, self.gids)?;
        require(
            FileIdentity::of(&files.target.metadata()?) == files.identity
                && FileIdentity::of(&target.metadata()?) == files.identity
                && mount_id(&target)? == files.target_mount
                && mount_id(&files.target)? == files.target_mount,
            "fixed cleanup target differs from its original held inode/mount",
        )?;
        self.context.objects()?;
        request.revalidate(init).map_err(MountError::from)
    }

    pub(crate) fn run(
        &mut self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitUnmountRequest<'_>,
    ) -> Result<()> {
        self.revalidate(init, request)?;
        require(
            self.helper.is_none() && self.outcome.is_none(),
            "original cleanup helper is single-use",
        )?;
        let files = self.files()?;
        let expected = [
            ExpectedNode::of(&files.target)?,
            ExpectedNode::of(&files.target)?,
            ExpectedNode::of(&files.root)?,
        ];
        let helper = Helper::spawn_initial(
            [&files.target, &files.target, &files.root, &files.namespace],
            expected,
            operation(self.kind),
            request.deadline(),
        )?;
        self.helper = Some(helper);
        // The atomic child PIDFD now belongs to this stored guard.
        self.revalidate(init, request)?;
        let helper = self.helper.as_mut().unwrap();
        helper.start()?;
        self.outcome = Some(helper.complete_initial(request.deadline())?);
        self.revalidate(init, request)?;
        require(
            self.outcome.as_ref().unwrap().operation() == operation(self.kind),
            "actual helper completed a different fixed operation",
        )
    }

    pub(crate) fn actual_errno(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitUnmountRequest<'_>,
    ) -> Result<i32> {
        self.revalidate(init, request)?;
        let result = self.outcome.as_ref().ok_or(MountError::Rejected(
            "fixed original syscall did not complete",
        ))?;
        require(
            result.operation() == operation(self.kind),
            "original syscall outcome role differs",
        )?;
        Ok(result.errno())
    }

    pub(crate) fn kind(&self) -> OriginalInitUnmountKind {
        self.kind
    }

    pub(crate) fn retire(&mut self) -> Result<()> {
        if self.retired {
            return Ok(());
        }
        if let Some(helper) = self.helper.as_mut() {
            helper.retire()?;
        }
        // Retire the actual child even if a later policy recheck fails. A lost
        // epoch still retains every descriptor and the original paired context.
        self.context.objects()?;
        self.helper.take();
        self.files.take();
        self.retired = true;
        Ok(())
    }
}

impl Drop for OriginalInitCleanup {
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
    pub(crate) fn prepare_original_init_cleanup(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        request: &OriginalInitUnmountRequest<'_>,
    ) -> Result<OriginalInitCleanup> {
        crate::production_devices::require_initial_broker()
            .map_err(|error| MountError::Io(io::Error::other(error.to_string())))?;
        request.revalidate(init)?;
        require(
            std::ptr::eq(self, init.runtime_owner()?),
            "cleanup has another executed runtime owner",
        )?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("original runtime retired"))?;
        resources.matches_witness(&init.namespace_witness()?)?;
        let context = resources
            .apex_loops
            .try_borrow()
            .map_err(|_| MountError::Rejected("original paired context is already borrowed"))?
            .owner()?;
        context.require_pair(mac, init.selection())?;
        let root = init.root_directory()?;
        let target = cleanup_target(&root, request.kind(), resources.uids, resources.gids)?;
        let identity = FileIdentity::of(&target.metadata()?);
        let target_mount = mount_id(&target)?;
        let namespace = init.mount_namespace()?.try_clone()?;
        let value = OriginalInitCleanup {
            context,
            generation: request.generation(),
            notification: request.notification(),
            kind: request.kind(),
            uids: resources.uids,
            gids: resources.gids,
            files: Some(CleanupFiles {
                root,
                target,
                namespace,
                identity,
                target_mount,
            }),
            helper: None,
            outcome: None,
            retired: false,
        };
        value.revalidate(init, request)?;
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_init_cleanup_rejects_ordinary_directories_before_any_helper_is_spawned() {
        let directory = tempfile::tempdir().unwrap();
        let root = File::open(directory.path()).unwrap();
        for kind in [
            OriginalInitUnmountKind::DebugRamdisk,
            OriginalInitUnmountKind::SecondStageResources,
        ] {
            std::fs::create_dir(directory.path().join(kind.name().to_str().unwrap())).unwrap();
            assert!(
                cleanup_target(
                    &root,
                    kind,
                    IdRange {
                        start: unsafe { libc::geteuid() },
                        count: 65536
                    },
                    IdRange {
                        start: unsafe { libc::getegid() },
                        count: 65536
                    },
                )
                .is_err()
            );
        }
    }
}
