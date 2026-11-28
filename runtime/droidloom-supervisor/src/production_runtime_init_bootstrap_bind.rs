//! The original CP3A bootstrap-apex recursive bind, with a real helper result.
//! This copies only the held original source into the held original /apex
//! target. It neither mounts an APEX payload nor changes propagation flags.
use super::*;
use crate::production_namespace::OriginalInitBootstrapBindRequest;
use mount_helper::{ExpectedNode, Helper, InitialOperation, InitialResult};

#[derive(Debug)]
struct Views {
    namespace: File,
    namespace_node: (u64, u64),
    root: File,
    root_identity: FileIdentity,
    root_mount: u64,
    source: File,
    source_identity: FileIdentity,
    source_mount: u64,
    target: File,
    target_identity: FileIdentity,
    target_mount: u64,
    uid: u32,
    gid: u32,
}

#[derive(Debug)]
pub(crate) struct OriginalInitBootstrapBind {
    context: RuntimeMacOwner,
    generation: ExecutedInitGeneration,
    notification: crate::production_apex_seccomp::Notification,
    views: Option<Views>,
    helper: Option<Helper>,
    outcome: Option<InitialResult>,
    retired: bool,
}

impl OriginalInitBootstrapBind {
    fn original(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitBootstrapBindRequest<'_>,
    ) -> Result<()> {
        request.revalidate(init)?;
        self.context.objects()?;
        let (mac, selection) = self.context.objects()?;
        self.context.require_pair(mac, init.selection())?;
        require(
            !self.retired
                && std::ptr::eq(selection, init.selection())
                && init.generation()? == self.generation
                && request.generation() == self.generation
                && request.notification() == self.notification,
            "bootstrap bind original request or context changed",
        )?;
        let v = self
            .views
            .as_ref()
            .ok_or(MountError::Rejected("bootstrap bind views retired"))?;
        let current = init.mount_namespace()?.metadata()?;
        let namespace = v.namespace.metadata()?;
        require(
            (current.dev(), current.ino()) == v.namespace_node
                && (namespace.dev(), namespace.ino()) == v.namespace_node,
            "bootstrap bind left the original mount namespace",
        )?;
        for (file, identity, mount) in [
            (&v.root, v.root_identity, v.root_mount),
            (&v.source, v.source_identity, v.source_mount),
            (&v.target, v.target_identity, v.target_mount),
        ] {
            require(
                FileIdentity::of(&file.metadata()?) == identity && mount_id(file)? == mount,
                "bootstrap bind lost an original descriptor",
            )?;
        }
        verify_activation_root(&v.source, ActivationRootRole::BootstrapApex, v.uid, v.gid)?;
        verify_activation_root(&v.target, ActivationRootRole::Apex, v.uid, v.gid)?;
        let root = init.root_directory()?;
        require(
            FileIdentity::of(&root.metadata()?) == v.root_identity
                && mount_id(&root)? == v.root_mount,
            "bootstrap bind guest root changed",
        )?;
        let source = open_leaf(&root, c"bootstrap-apex", libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            FileIdentity::of(&source.metadata()?) == v.source_identity
                && mount_id(&source)? == v.source_mount,
            "bootstrap bind source path changed",
        )?;
        request.revalidate(init).map_err(MountError::from)
    }

    fn before(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitBootstrapBindRequest<'_>,
    ) -> Result<()> {
        self.original(init, request)?;
        let v = self.views.as_ref().unwrap();
        let target = open_leaf(&v.root, c"apex", libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            FileIdentity::of(&target.metadata()?) == v.target_identity
                && mount_id(&target)? == v.target_mount,
            "bootstrap bind pre-operation target changed",
        )?;
        request
            .before_mount(init, &v.source, &v.target)
            .map_err(MountError::from)
    }

    fn after(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitBootstrapBindRequest<'_>,
    ) -> Result<i32> {
        self.original(init, request)?;
        let outcome = self.outcome.as_ref().ok_or(MountError::Rejected(
            "bootstrap bind has no actual helper result",
        ))?;
        require(
            outcome.operation() == InitialOperation::BindBootstrapApex
                && (0..=4095).contains(&outcome.errno()),
            "bootstrap bind result differs",
        )?;
        let v = self.views.as_ref().unwrap();
        let target = open_leaf(&v.root, c"apex", libc::O_RDONLY | libc::O_DIRECTORY)?;
        if outcome.errno() == 0 {
            require(
                FileIdentity::of(&target.metadata()?) == v.source_identity
                    && mount_id(&target)? != v.source_mount
                    && mount_id(&target)? != v.target_mount,
                "bootstrap bind did not publish the original source on a new mount",
            )?;
            verify_activation_root(&target, ActivationRootRole::BootstrapApex, v.uid, v.gid)?;
        } else {
            require(
                FileIdentity::of(&target.metadata()?) == v.target_identity
                    && mount_id(&target)? == v.target_mount,
                "failed bootstrap bind changed its target",
            )?;
        }
        self.original(init, request)?;
        Ok(outcome.errno())
    }

    pub(crate) fn run(
        &mut self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitBootstrapBindRequest<'_>,
    ) -> Result<()> {
        self.before(init, request)?;
        require(
            self.helper.is_none() && self.outcome.is_none(),
            "bootstrap bind cannot be replayed",
        )?;
        let v = self.views.as_ref().unwrap();
        let expected = [
            ExpectedNode::of(&v.source)?,
            ExpectedNode::of(&v.target)?,
            ExpectedNode::of(&v.root)?,
        ];
        self.helper = Some(Helper::spawn_initial(
            [&v.source, &v.target, &v.root, &v.namespace],
            expected,
            InitialOperation::BindBootstrapApex,
            request.deadline(),
        )?);
        // The exact helper is in this already-stored original owner before READY release.
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
        request: &OriginalInitBootstrapBindRequest<'_>,
    ) -> Result<i32> {
        self.after(init, request)
    }

    pub(crate) fn original_views(
        &self,
        init: &ExecutedInitWitness<'_>,
        request: &OriginalInitBootstrapBindRequest<'_>,
    ) -> Result<(&File, &File)> {
        self.after(init, request)?;
        let v = self.views.as_ref().unwrap();
        Ok((&v.source, &v.target))
    }

    pub(crate) fn retire_helper(&mut self) -> Result<()> {
        if let Some(helper) = self.helper.as_mut() {
            helper.retire()?;
        }
        Ok(())
    }

    pub(crate) fn retire_views(&mut self) -> Result<()> {
        if self.retired {
            return Ok(());
        }
        self.retire_helper()?;
        self.context.objects()?;
        self.helper.take();
        self.views.take();
        self.retired = true;
        Ok(())
    }
}

impl Drop for OriginalInitBootstrapBind {
    fn drop(&mut self) {
        if !self.retired && self.helper.is_some() {
            if let Some(helper) = self.helper.take() {
                std::mem::forget(helper);
            }
            if let Some(views) = self.views.take() {
                std::mem::forget(views);
            }
            std::mem::forget(self.context.clone());
        }
    }
}

impl PreparedRuntime {
    pub(crate) fn prepare_original_init_bootstrap_bind(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        request: &OriginalInitBootstrapBindRequest<'_>,
    ) -> Result<OriginalInitBootstrapBind> {
        crate::production_devices::require_initial_broker()
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        request.revalidate(init)?;
        require(
            std::ptr::eq(self, init.runtime_owner()?),
            "bootstrap bind runtime substituted",
        )?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("bootstrap bind runtime retired"))?;
        resources.matches_witness(&init.namespace_witness()?)?;
        let context = resources
            .apex_loops
            .try_borrow()
            .map_err(|_| MountError::Rejected("bootstrap bind mount actor active"))?
            .owner()?;
        context.require_pair(mac, init.selection())?;
        let root = init.root_directory()?;
        let source = init.original_init_activation_root(ActivationRootRole::BootstrapApex)?;
        let target = init.original_init_activation_root(ActivationRootRole::Apex)?;
        let namespace = init.mount_namespace()?.try_clone()?;
        let ns = namespace.metadata()?;
        let (uid, gid) = init.mapped_root_ids();
        let views = Views {
            namespace,
            namespace_node: (ns.dev(), ns.ino()),
            root_identity: FileIdentity::of(&root.metadata()?),
            root_mount: mount_id(&root)?,
            root,
            source_identity: FileIdentity::of(&source.metadata()?),
            source_mount: mount_id(&source)?,
            source,
            target_identity: FileIdentity::of(&target.metadata()?),
            target_mount: mount_id(&target)?,
            target,
            uid,
            gid,
        };
        require(
            (views.source_identity.dev, views.source_identity.ino)
                != (views.target_identity.dev, views.target_identity.ino),
            "original bootstrap and apex inodes must differ",
        )?;
        let value = OriginalInitBootstrapBind {
            context,
            generation: request.generation(),
            notification: request.notification(),
            views: Some(views),
            helper: None,
            outcome: None,
            retired: false,
        };
        value.before(init, request)?;
        Ok(value)
    }
}
