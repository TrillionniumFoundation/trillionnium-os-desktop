//! Publish only an owned original builtin payload into the fixed bootstrap
//! view. This is the actual mount syscall provider, not an apexd completion
//! witness. Original apexd must request it, verify its own image and generate
//! its database and apex-info-list; no status file is synthesized here.
use super::*;
use mount_helper::{ExpectedNode, Helper};

fn filesystem(kind: apex_inputs::PayloadFilesystem) -> Filesystem {
    match kind {
        apex_inputs::PayloadFilesystem::Ext4 => Filesystem::Ext4,
        apex_inputs::PayloadFilesystem::Erofs => Filesystem::Erofs,
    }
}

fn fixed_target(index: usize) -> Result<CString> {
    let row = apex_inputs::original_builtin(index).map_err(MountError::Rejected)?;
    require(
        safe_module_name(&row.input.name) && row.input.version > 0,
        "compiled builtin APEX target identity",
    )?;
    text_name(&format!("{}@{}", row.input.name, row.input.version))
}

fn same_root(a: &File, b: &File) -> Result<()> {
    let a = a.metadata()?;
    let b = b.metadata()?;
    require(
        (a.dev(), a.ino(), a.mode(), a.uid(), a.gid())
            == (b.dev(), b.ino(), b.mode(), b.uid(), b.gid()),
        "bootstrap activation view is not the originally owned root inode",
    )
}

fn private_directory(file: &File, uid: u32, gid: u32, device: u64) -> Result<FileIdentity> {
    let m = file.metadata()?;
    require(
        m.mode() == libc::S_IFDIR | 0o755
            && m.uid() == uid
            && m.gid() == gid
            && m.nlink() == 2
            && m.dev() == device
            && fs_type(file)? == 0x0102_1994,
        "fixed APEX target must be an empty mapped-root private tmpfs directory",
    )?;
    let directory = open_leaf(file, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
    same_root(file, &directory)?;
    require_exact_xattr(
        &directory,
        c"security.selinux",
        b"u:object_r:apex_mnt_dir:s0\0",
    )?;
    require_absent_xattr(&directory, c"security.capability")?;
    require(
        std::fs::read_dir(format!("/proc/self/fd/{}", directory.as_raw_fd()))?
            .next()
            .transpose()?
            .is_none(),
        "APEX target directory is not completely empty",
    )?;
    let identity = FileIdentity::of(&m);
    require(
        FileIdentity::of(&directory.metadata()?) == identity,
        "APEX target changed during empty observation",
    )?;
    Ok(identity)
}

/// All fields are retained by ApexLoops before the child can mutate the guest
/// mount tree. A partial failure therefore cannot escape the original lease.
#[derive(Debug)]
pub(super) struct Publication {
    root: File,
    bootstrap: File,
    apex: File,
    original_bootstrap: File,
    target: File,
    target_identity: FileIdentity,
    name: CString,
    namespace: File,
    payload: File,
    payload_identity: FileIdentity,
    payload_mount: u64,
    fs: Filesystem,
    uids: IdRange,
    gids: IdRange,
    helper: Option<Helper>,
    observed: bool,
}

impl Publication {
    fn prepare(
        resources: &RuntimeResources,
        init: &ExecutedInitWitness<'_>,
        index: usize,
        binding: &PrivateLoopDevice,
        mac: &MacPreflight,
    ) -> Result<Self> {
        let fixed = apex_inputs::original_builtin(index).map_err(MountError::Rejected)?;
        require(
            binding.apex_index() == index,
            "private loop and publication role differ",
        )?;
        binding.revalidate(mac, init.selection())?;
        let root = init.root_directory()?;
        let bootstrap = open_leaf(&root, c"bootstrap-apex", libc::O_PATH | libc::O_DIRECTORY)?;
        let apex = open_leaf(&root, c"apex", libc::O_PATH | libc::O_DIRECTORY)?;
        let original_bootstrap =
            init.original_init_activation_root(ActivationRootRole::BootstrapApex)?;
        for view in [&bootstrap, &apex] {
            same_root(&original_bootstrap, view)?;
            verify_activation_root(
                view,
                ActivationRootRole::BootstrapApex,
                resources.uids.start,
                resources.gids.start,
            )?;
        }
        // Distinct mount IDs prove init made the bind in this namespace. An
        // unchanged /apex root or a caller-supplied alias cannot select it.
        require(
            mount_id(&bootstrap)? != mount_id(&apex)?,
            "original init bootstrap bind has not occurred",
        )?;
        let name = fixed_target(index)?;
        let target = open_leaf(&apex, &name, libc::O_PATH | libc::O_DIRECTORY)?;
        require(
            mount_id(&target)? == mount_id(&apex)?,
            "APEX target was already mounted or crossed another filesystem",
        )?;
        let target_identity = private_directory(
            &target,
            resources.uids.start,
            resources.gids.start,
            original_bootstrap.metadata()?.dev(),
        )?;
        let namespace = init.mount_namespace()?.try_clone()?;
        let payload = detached_original_apex_mount(
            binding,
            mac,
            init.selection(),
            &resources.userns,
            resources.uids,
            resources.gids,
        )?;
        let payload_identity = FileIdentity::of(&payload.metadata()?);
        let payload_mount = require_detached(&payload)?;
        Ok(Self {
            root,
            bootstrap,
            apex,
            original_bootstrap,
            target,
            target_identity,
            name,
            namespace,
            payload,
            payload_identity,
            payload_mount,
            fs: filesystem(fixed.filesystem),
            uids: resources.uids,
            gids: resources.gids,
            helper: None,
            observed: false,
        })
    }

    fn publish(&mut self, end: Instant) -> Result<()> {
        require(
            self.helper.is_none() && !self.observed,
            "APEX publication is single-use",
        )?;
        self.verify_container()?;
        let expected = [
            ExpectedNode::of(&self.payload)?,
            ExpectedNode::of(&self.target)?,
            ExpectedNode::of(&self.root)?,
        ];
        self.helper = Some(Helper::spawn(
            [&self.payload, &self.target, &self.root, &self.namespace],
            expected,
            end,
        )?);
        // The actual child is now owned by the runtime row. Only now may its
        // private barrier be released and any setns/move_mount take place.
        let helper = self.helper.as_mut().unwrap();
        helper.start()?;
        helper.complete(end)?;
        self.verify_published()?;
        self.observed = true;
        Ok(())
    }

    fn verify_container(&self) -> Result<()> {
        for view in [&self.bootstrap, &self.apex] {
            same_root(&self.original_bootstrap, view)?;
            verify_activation_root(
                view,
                ActivationRootRole::BootstrapApex,
                self.uids.start,
                self.gids.start,
            )?;
        }
        let bootstrap = open_leaf(
            &self.root,
            c"bootstrap-apex",
            libc::O_PATH | libc::O_DIRECTORY,
        )?;
        let apex = open_leaf(&self.root, c"apex", libc::O_PATH | libc::O_DIRECTORY)?;
        same_root(&bootstrap, &self.bootstrap)?;
        same_root(&apex, &self.apex)?;
        require(
            mount_id(&bootstrap)? == mount_id(&self.bootstrap)?
                && mount_id(&apex)? == mount_id(&self.apex)?,
            "original bootstrap bind mount identities changed",
        )?;
        require(
            private_directory(
                &self.target,
                self.uids.start,
                self.gids.start,
                self.original_bootstrap.metadata()?.dev(),
            )? == self.target_identity,
            "pinned original empty APEX mountpoint changed",
        )
    }

    fn verify_published(&self) -> Result<()> {
        self.verify_container()?;
        let visible = open_leaf(&self.apex, &self.name, libc::O_PATH | libc::O_DIRECTORY)?;
        require(
            FileIdentity::of(&self.payload.metadata()?) == self.payload_identity
                && FileIdentity::of(&visible.metadata()?) == self.payload_identity
                && mount_id(&visible)? == self.payload_mount
                && require_detached(&self.payload)? == self.payload_mount,
            "actual APEX publication differs from its held payload inode or mount",
        )?;
        for file in [&self.payload, &visible] {
            verify_readonly_mount(file, self.fs, self.uids, self.gids, self.payload_mount)?;
            let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
            zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) })?;
            require(
                flags.f_flag as u64 & (READONLY_FLAGS | 8 | 1024) == READONLY_FLAGS | 1024,
                "actual builtin payload lost fixed readonly nosuid nodev noatime execution flags",
            )?;
        }
        Ok(())
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        require(
            self.observed,
            "APEX mount publication has not completed its actual helper and readback",
        )?;
        self.verify_published()
    }

    pub(super) fn retire_helper(&mut self) -> Result<()> {
        if let Some(helper) = self.helper.as_mut() {
            helper.retire()?;
        }
        Ok(())
    }
}

impl PreparedRuntime {
    /// The finite syscall backend for a builtin original-apexd mount request.
    /// This publishes an actual filesystem; it never manufactures an apexd
    /// result, AVB signature verdict, database entry or activation witness.
    pub(crate) fn publish_original_builtin_apex_in_bootstrap(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        index: usize,
        end: Instant,
    ) -> Result<()> {
        crate::production_devices::require_initial_broker()
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        init.revalidate_capability_contract()?;
        require(
            std::ptr::eq(self, init.runtime_owner()?),
            "APEX mount provider has a different executed runtime owner",
        )?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("runtime owner retired"))?;
        resources.matches_witness(&init.namespace_witness()?)?;
        mac.revalidate(init.selection())
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        let generation = init.generation()?;
        require(
            Instant::now() < end,
            "APEX mount publication deadline expired",
        )?;
        // Prepare before taking the mutable syscall-owner borrow.
        let publication =
            {
                let loops = resources
                    .apex_loops
                    .try_borrow()
                    .map_err(|_| MountError::Rejected("APEX mount provider already active"))?;
                loops.owner()?.require_pair(mac, init.selection())?;
                loops.revalidate()?;
                let row = loops.rows.iter().find(|row| row.index == index).ok_or(
                    MountError::Rejected("APEX publication has no original owned loop"),
                )?;
                require(
                    row.generation == generation && row.publication.is_none(),
                    "APEX loop generation or one-shot publication differs",
                )?;
                // The original root accessor may repeat immutable resource
                // verification under this shared borrow. No mutable syscall
                // owner borrow has begun.
                Publication::prepare(
                    resources,
                    init,
                    index,
                    row.binding
                        .as_ref()
                        .ok_or(MountError::Rejected("APEX loop preparation incomplete"))?,
                    mac,
                )?
            };
        init.revalidate()?;
        mac.revalidate(init.selection())
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        {
            let mut loops = resources
                .apex_loops
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("APEX mount provider already active"))?;
            let row = loops
                .rows
                .iter_mut()
                .find(|row| row.index == index)
                .ok_or(MountError::Rejected("original APEX loop custody changed"))?;
            require(
                row.generation == generation && row.publication.is_none(),
                "APEX publication owner changed",
            )?;
            row.publication = Some(publication);
            row.publication.as_mut().unwrap().publish(end)?;
            row.binding
                .as_ref()
                .unwrap()
                .revalidate(mac, init.selection())?;
        }
        init.revalidate()?;
        mac.revalidate(init.selection())
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        resources.matches_witness(&init.namespace_witness()?)?;
        require(
            Instant::now() < end,
            "APEX publication exceeded original deadline",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn builtin_apex_publication_targets_cannot_select_capex_aliases_or_an_external_path() {
        let inputs = apex_inputs::original_inputs().unwrap();
        let mut names = BTreeSet::new();
        for (index, row) in inputs.iter().enumerate() {
            if row.input.container_file.ends_with(".apex") {
                let target = fixed_target(index).unwrap();
                let text = target.to_str().unwrap();
                assert_eq!(text, format!("{}@{}", row.input.name, row.input.version));
                assert!(!text.contains('/') && names.insert(text.to_owned()));
            } else {
                assert!(fixed_target(index).is_err());
            }
        }
        assert_eq!(names.len(), 10);
        assert!(fixed_target(38).is_err());
        assert!(fixed_target(usize::MAX).is_err());
    }

    #[test]
    fn builtin_apex_mountpoint_rejects_real_ordinary_directory_and_replacement_inode() {
        let directory = tempfile::tempdir().unwrap();
        let file = File::open(directory.path()).unwrap();
        let m = file.metadata().unwrap();
        assert!(private_directory(&file, m.uid(), m.gid(), m.dev()).is_err());
        let second = tempfile::tempdir().unwrap();
        let other = File::open(second.path()).unwrap();
        assert!(same_root(&file, &other).is_err());
        same_root(&file, &file.try_clone().unwrap()).unwrap();
    }
}
