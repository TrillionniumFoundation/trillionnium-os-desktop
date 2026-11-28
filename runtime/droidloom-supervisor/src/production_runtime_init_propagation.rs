//! Finite original CP3A mount propagation operations in the held guest tree.
//! Each result is the real mount syscall plus the original helper PIDFD exit.
use super::*;
use crate::production_namespace::OriginalInitPropagationRequest;
use mount_helper::{ExpectedNode, Helper, InitialOperation, InitialResult};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum OriginalInitPropagationKind {
    RootShared,
    ApexPrivate,
    LinkerconfigPrivate,
}

impl OriginalInitPropagationKind {
    pub(crate) const ALL: [Self; 3] = [
        Self::RootShared,
        Self::ApexPrivate,
        Self::LinkerconfigPrivate,
    ];

    pub(crate) fn target(self) -> &'static CStr {
        match self {
            Self::RootShared => c"/",
            Self::ApexPrivate => c"/apex",
            Self::LinkerconfigPrivate => c"/linkerconfig",
        }
    }

    pub(crate) fn flags(self) -> u64 {
        match self {
            Self::RootShared => 0x10_4000,
            Self::ApexPrivate | Self::LinkerconfigPrivate => 0x4_0000,
        }
    }

    fn operation(self) -> InitialOperation {
        match self {
            Self::RootShared => InitialOperation::RootShared,
            Self::ApexPrivate => InitialOperation::ApexPrivate,
            Self::LinkerconfigPrivate => InitialOperation::LinkerconfigPrivate,
        }
    }

    fn open_target(self, root: &File) -> Result<File> {
        match self {
            Self::RootShared => Ok(root.try_clone()?),
            Self::ApexPrivate => open_leaf(root, c"apex", libc::O_RDONLY | libc::O_DIRECTORY),
            Self::LinkerconfigPrivate => {
                open_leaf(root, c"linkerconfig", libc::O_RDONLY | libc::O_DIRECTORY)
            }
        }
    }
}

#[derive(Debug)]
struct PropagationFiles {
    root: File,
    target: File,
    namespace: File,
    root_identity: FileIdentity,
    target_identity: FileIdentity,
    root_mount: u64,
    target_mount: u64,
}

/// Only the original PreparedRuntime and pending native init request can
/// construct this guard. It neither accepts a path/flag argument nor enters a
/// user namespace. The outer same-thread owner stores it before helper release.
#[derive(Debug)]
pub(crate) struct OriginalInitPropagation {
    context: RuntimeMacOwner,
    generation: ExecutedInitGeneration,
    notification: crate::production_apex_seccomp::Notification,
    kind: OriginalInitPropagationKind,
    files: Option<PropagationFiles>,
    helper: Option<Helper>,
    outcome: Option<InitialResult>,
    retired: bool,
}

impl OriginalInitPropagation {
    fn files(&self) -> Result<&PropagationFiles> {
        self.files
            .as_ref()
            .ok_or(MountError::Rejected("original propagation views retired"))
    }

    fn request(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<()> {
        request.revalidate(init)?;
        require(
            !self.retired
                && init.generation()? == self.generation
                && request.generation() == self.generation
                && request.notification() == self.notification
                && request.kind() == self.kind,
            "propagation guard belongs to another original request",
        )?;
        let (mac, selection) = self.context.objects()?;
        self.context.require_pair(mac, init.selection())?;
        require(
            std::ptr::eq(selection, init.selection()),
            "propagation selection is not the original paired owner",
        )?;
        let files = self.files()?;
        let actual_ns = init.mount_namespace()?.metadata()?;
        let held_ns = files.namespace.metadata()?;
        require(
            (actual_ns.dev(), actual_ns.ino()) == (held_ns.dev(), held_ns.ino()),
            "original propagation mount namespace changed",
        )?;
        let root = init.root_directory()?;
        let target = self.kind.open_target(&root)?;
        require(
            FileIdentity::of(&root.metadata()?) == files.root_identity
                && FileIdentity::of(&files.root.metadata()?) == files.root_identity
                && FileIdentity::of(&target.metadata()?) == files.target_identity
                && FileIdentity::of(&files.target.metadata()?) == files.target_identity
                && mount_id(&root)? == files.root_mount
                && mount_id(&files.root)? == files.root_mount
                && mount_id(&target)? == files.target_mount
                && mount_id(&files.target)? == files.target_mount,
            "propagation target lost its held original inode or mount",
        )?;
        self.context.objects()?;
        request.revalidate(init).map_err(MountError::from)
    }

    pub(crate) fn run(
        &mut self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<()> {
        self.request(init, request)?;
        require(
            self.helper.is_none() && self.outcome.is_none(),
            "original propagation helper cannot be replayed",
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
            self.kind.operation(),
            request.deadline(),
        )?;
        self.helper = Some(helper);
        self.request(init, request)?;
        let helper = self.helper.as_mut().unwrap();
        helper.start()?;
        self.outcome = Some(helper.complete_initial(request.deadline())?);
        self.actual_errno(init, request)?;
        Ok(())
    }

    pub(crate) fn actual_errno(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<i32> {
        self.request(init, request)?;
        let result = self.outcome.as_ref().ok_or(MountError::Rejected(
            "propagation operation has no actual helper result",
        ))?;
        require(
            result.operation() == self.kind.operation() && (0..=4095).contains(&result.errno()),
            "propagation helper result has another operation or errno",
        )?;
        self.request(init, request)?;
        Ok(result.errno())
    }

    pub(crate) fn retire_views(&mut self) -> Result<()> {
        if self.retired {
            return Ok(());
        }
        if let Some(helper) = &mut self.helper {
            helper.retire()?;
        }
        self.context.objects()?;
        self.helper.take();
        self.files.take();
        self.retired = true;
        Ok(())
    }
}

impl Drop for OriginalInitPropagation {
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
    pub(crate) fn prepare_original_init_propagation(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        request: &OriginalInitPropagationRequest<'_>,
    ) -> Result<OriginalInitPropagation> {
        crate::production_devices::require_initial_broker()
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        request.revalidate(init)?;
        require(
            std::ptr::eq(self, init.runtime_owner()?),
            "propagation request has another original runtime owner",
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
        let kind = request.kind();
        let root = init.root_directory()?;
        let target = kind.open_target(&root)?;
        let root_identity = FileIdentity::of(&root.metadata()?);
        let target_identity = FileIdentity::of(&target.metadata()?);
        let root_mount = mount_id(&root)?;
        let target_mount = mount_id(&target)?;
        let namespace = init.mount_namespace()?.try_clone()?;
        let value = OriginalInitPropagation {
            context,
            generation: request.generation(),
            notification: request.notification(),
            kind,
            files: Some(PropagationFiles {
                root,
                target,
                namespace,
                root_identity,
                target_identity,
                root_mount,
                target_mount,
            }),
            helper: None,
            outcome: None,
            retired: false,
        };
        value.request(init, request)?;
        Ok(value)
    }
}
