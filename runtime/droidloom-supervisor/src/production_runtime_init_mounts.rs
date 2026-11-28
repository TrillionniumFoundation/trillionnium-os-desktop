//! Actual new tmpfs roots for the original init's three mount syscalls.
//! The new filesystem is distinct from the prepared placeholder. The original
//! owner retains it before the fixed helper starts; only the native operation
//! and original PIDFD exit can supply the response.
use super::super::activation_mounts::WritableRoot;
use super::*;
use crate::production_namespace::OriginalInitTmpfsRequest;
use mount_helper::{ExpectedNode, Helper, InitialOperation, InitialResult};

fn operation(role: ActivationRootRole) -> InitialOperation {
    match role {
        ActivationRootRole::Apex => InitialOperation::Apex,
        ActivationRootRole::BootstrapApex => InitialOperation::BootstrapApex,
        ActivationRootRole::Linkerconfig => InitialOperation::Linkerconfig,
    }
}

fn same_inode(left: &File, right: &File) -> Result<bool> {
    let a = left.metadata()?;
    let b = right.metadata()?;
    Ok((a.dev(), a.ino()) == (b.dev(), b.ino()))
}

fn original_target(
    resources: &RuntimeResources,
    root: &File,
    role: ActivationRootRole,
) -> Result<File> {
    let prepared = resources
        .activation_roots
        .as_ref()
        .ok_or(MountError::Rejected(
            "original prepared activation roots absent",
        ))?
        .original_root(role);
    let target = open_leaf(root, role.name(), libc::O_RDONLY | libc::O_DIRECTORY)?;
    require(
        same_inode(prepared, &target)? && mount_id(&target)? != mount_id(root)?,
        "original init mount target differs from its prepared placeholder",
    )?;
    for file in [prepared, &target] {
        verify_activation_root(file, role, resources.uids.start, resources.gids.start)?;
    }
    let before = FileIdentity::of(&target.metadata()?);
    require(
        target.metadata()?.nlink() == 2
            && std::fs::read_dir(format!("/proc/self/fd/{}", target.as_raw_fd()))?
                .next()
                .transpose()?
                .is_none()
            && FileIdentity::of(&target.metadata()?) == before,
        "original placeholder must be empty before its native replacement",
    )?;
    Ok(target)
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
    source: WritableRoot,
}

/// Owns the actual new mount and worker. This is never constructed from a
/// receipt, pathname, caller namespace, numeric PID or claimed syscall result.
#[derive(Debug)]
pub(crate) struct OriginalInitMount {
    context: RuntimeMacOwner,
    generation: ExecutedInitGeneration,
    notification: crate::production_apex_seccomp::Notification,
    role: ActivationRootRole,
    uids: IdRange,
    gids: IdRange,
    files: Option<MountFiles>,
    helper: Option<Helper>,
    outcome: Option<InitialResult>,
    retired: bool,
}

impl OriginalInitMount {
    fn files(&self) -> Result<&MountFiles> {
        self.files
            .as_ref()
            .ok_or(MountError::Rejected("original tmpfs views retired"))
    }

    fn original(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        init.revalidate_capability_contract()?;
        require(
            !self.retired && init.generation()? == self.generation,
            "tmpfs source belongs to another original executed init",
        )?;
        let (mac, selection) = self.context.objects()?;
        self.context.require_pair(mac, init.selection())?;
        require(
            std::ptr::eq(selection, init.selection()),
            "tmpfs source selection is not the original paired owner",
        )?;
        let files = self.files()?;
        let actual_namespace = init.mount_namespace()?.metadata()?;
        let held_namespace = files.namespace.metadata()?;
        require(
            (actual_namespace.dev(), actual_namespace.ino())
                == (held_namespace.dev(), held_namespace.ino()),
            "original tmpfs namespace changed",
        )?;
        let root = init.root_directory()?;
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
        request: &OriginalInitTmpfsRequest<'_>,
    ) -> Result<()> {
        request.revalidate(init)?;
        self.original(init)?;
        require(
            request.generation() == self.generation
                && request.notification() == self.notification
                && request.role() == self.role,
            "tmpfs guard belongs to another original pending request",
        )?;
        request.revalidate(init).map_err(MountError::from)
    }

    fn before_operation(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitTmpfsRequest<'_>,
    ) -> Result<()> {
        self.request(init, request)?;
        let files = self.files()?;
        files.source.verify_fresh(self.uids, self.gids)?;
        let visible = open_leaf(
            &files.root,
            self.role.name(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
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
        request: &OriginalInitTmpfsRequest<'_>,
    ) -> Result<i32> {
        self.request(init, request)?;
        let result = self.outcome.as_ref().ok_or(MountError::Rejected(
            "original tmpfs operation has no actual outcome",
        ))?;
        require(
            result.operation() == operation(self.role) && (0..=4095).contains(&result.errno()),
            "actual helper outcome has another finite operation or errno",
        )?;
        let files = self.files()?;
        let visible = open_leaf(
            &files.root,
            self.role.name(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        if result.errno() == 0 {
            require(
                same_inode(&visible, files.source.root())?
                    && mount_id(&visible)? == mount_id(files.source.mount())?,
                "native successful tmpfs publication is not the held new mount",
            )?;
            verify_activation_root(&visible, self.role, self.uids.start, self.gids.start)?;
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
        request: &OriginalInitTmpfsRequest<'_>,
    ) -> Result<()> {
        self.before_operation(init, request)?;
        require(
            self.helper.is_none() && self.outcome.is_none(),
            "original tmpfs helper cannot be replayed",
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
            operation(self.role),
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
        request: &OriginalInitTmpfsRequest<'_>,
    ) -> Result<i32> {
        self.after_operation(init, request)
    }

    pub(crate) fn published_root(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitTmpfsRequest<'_>,
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
        let result = self
            .outcome
            .as_ref()
            .ok_or(MountError::Rejected("original tmpfs operation did not run"))?;
        require(
            result.operation() == operation(self.role) && result.errno() == 0,
            "only the actual successful original operation has a source root",
        )?;
        let root = self.files()?.source.root().try_clone()?;
        self.original(init)?;
        Ok(root)
    }

    pub(crate) fn role(&self) -> ActivationRootRole {
        self.role
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

impl Drop for OriginalInitMount {
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
    pub(crate) fn prepare_original_init_mount(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        request: &OriginalInitTmpfsRequest<'_>,
    ) -> Result<OriginalInitMount> {
        crate::production_devices::require_initial_broker()
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        request.revalidate(init)?;
        require(
            std::ptr::eq(self, init.runtime_owner()?),
            "new tmpfs source has another original runtime owner",
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
        let role = request.role();
        let root = init.root_directory()?;
        let target = original_target(resources, &root, role)?;
        let target_identity = FileIdentity::of(&target.metadata()?);
        let target_mount = mount_id(&target)?;
        let root_identity = FileIdentity::of(&root.metadata()?);
        let root_mount = mount_id(&root)?;
        let namespace = init.mount_namespace()?.try_clone()?;
        // Anonymous creation has no exported descriptor or mount attachment.
        // A failure here closes the fresh local filesystem without touching
        // any original guest or host inode.
        let source = WritableRoot::prepare_original_init(
            role,
            &resources.userns,
            resources.uids,
            resources.gids,
        )?;
        require(
            !same_inode(source.root(), &target)?
                && source.root().metadata()?.dev() != target.metadata()?.dev()
                && mount_id(source.mount())? != target_mount,
            "original mount must create a distinct new filesystem",
        )?;
        let value = OriginalInitMount {
            context,
            generation: request.generation(),
            notification: request.notification(),
            role,
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
