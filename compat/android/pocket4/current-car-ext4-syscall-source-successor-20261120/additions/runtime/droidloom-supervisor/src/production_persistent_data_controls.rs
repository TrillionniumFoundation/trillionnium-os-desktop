//! Test-only syscall ownership wrapper. No PreparedExecution or production
//! selection is fabricated. Every kernel operation is the original provider's
//! actual WritableLoop, detached_data_mount and cleanup implementation.
use super::*;
use crate::production_identity::tests::persistent_fixture::{
    APP, PersistentFixture, START,
};

fn source_nodes(fixture: &PersistentFixture<'_>) -> Result<[FileIdentity; 2]> {
    fixture.verify()?;
    Ok([FileIdentity::of(&fixture.files()[0].metadata()?), FileIdentity::of(&fixture.files()[1].metadata()?)])
}

fn stable(left: FileIdentity, right: FileIdentity) -> bool {
    (left.dev, left.ino, left.mode, left.uid, left.gid, left.links, left.bytes)
        == (right.dev, right.ino, right.mode, right.uid, right.gid, right.links, right.bytes)
}

/// Opaque comparison custody captured before transfer. It cannot retire a loop
/// or create a provider. Only the original typed retirement result can finish it.
pub(crate) struct ExpectedRetirement {
    source: [File; 2],
    nodes: [FileIdentity; 2],
    devices: Vec<u64>,
    after_tree: bool,
}

/// This value is minted only after original real loop retirement (or a
/// header-only failure whose code never calls an allocator). Numeric devices,
/// booleans, JSON and model results are not accepted as a constructor.
pub(crate) struct VerifiedPrivateRetirement {
    source: [File; 2],
    nodes: [FileIdentity; 2],
    devices: Vec<u64>,
    readonly_view: bool,
}

impl VerifiedPrivateRetirement {
    pub(crate) fn matches_fixture(&self, fixture: &PersistentFixture<'_>) -> Result<()> {
        let current = source_nodes(fixture)?;
        for index in 0..2 {
            require(stable(self.nodes[index], current[index])
                && stable(self.nodes[index], FileIdentity::of(&self.source[index].metadata()?)),
                "only the same new fixture inodes may be removed after real retirement")?;
        }
        Ok(())
    }
    pub(crate) fn observation(&self) -> serde_json::Value {
        serde_json::json!({"actual_owned_loop_devices_unbound":self.devices,
            "readonly_view_retired":self.readonly_view,"production_ready":false})
    }
}

impl ExpectedRetirement {
    pub(crate) fn finish(self, actual: &PersistentDataRetirement) -> Result<VerifiedPrivateRetirement> {
        require(actual.images == self.devices.len()
            && actual.owned_filesystems_synced && actual.detached_descriptors_closed
            && actual.original_backing_files_synced_after_unbind
            && actual.after_owned_tree_exit == self.after_tree
            && actual.owned_loop_devices_observed_unbound == self.devices,
            "complete original typed persistent retirement must match exact owned loop set")?;
        Ok(VerifiedPrivateRetirement { source: self.source, nodes: self.nodes, devices: self.devices, readonly_view: false })
    }
}

pub(crate) struct PrivatePersistentData {
    prepared: Option<PreparedPersistentData>,
    source: [File; 2],
    nodes: [FileIdentity; 2],
}

impl PrivatePersistentData {
    pub(crate) fn prepare(fixture: &PersistentFixture<'_>, witness: &OwnedNamespaceWitness<'_>) -> Result<Self> {
        fixture.run().operation_time()?;
        fixture.verify_lease(witness.identity_lease()?)?;
        fixture.claim_body_access()?;
        require_complete_namespace(witness)?;
        require(witness.descendant_pid_namespace().is_some(), "real private PID1 owner required")?;
        let lease = witness.identity_lease()?;
        let retention = lease.broker_retain_reservation()?;
        let reservation_node = FileIdentity::of(&retention.metadata()?);
        let userns = witness.user_namespace().try_clone()?;
        let namespace = userns.metadata()?;
        let (uids, gids) = lease.broker_ranges();
        let backings = backings::private_control::open_fixture(fixture, witness)?;
        let source = [fixture.files()[0].try_clone()?, fixture.files()[1].try_clone()?];
        let nodes = source_nodes(fixture)?;
        let prepared = PreparedPersistentData {
            resources: Some(DataResources { backings, images: Vec::new(), userns,
                userns_identity: (namespace.dev(), namespace.ino()), uids, gids,
                host_uid: lease.host_uid(), cohort: lease.broker_cohort().to_owned(),
                // This sentinel is never accepted by or passed to a production
                // PreparedExecution. The separate test wrapper cannot construct it.
                selection_binding: [0; 32], reservation_retention: retention, reservation_node }),
            exported: false,
        };
        let mut value = Self { prepared: Some(prepared), source, nodes };
        value.matches(witness)?;
        let resources = value.prepared.as_mut().unwrap().resources.as_mut().unwrap();
        writable_loop::reject_aliases(&resources.backings.nodes, &resources.images)?;
        for index in 0..2 {
            fixture.verify_lease(witness.identity_lease()?)?;
            let binding = WritableLoop::attach(&resources.backings.files[index])?;
            // Custody is registered before each fallible actual mount/IDMAP.
            resources.images.push(MountedData { role: index, mount: None, binding, observed: None });
            resources.images[index].binding.verify()?;
            writable_loop::reject_aliases(&resources.backings.nodes, &resources.images)?;
            let mount = detached_data_mount(&resources.images[index].binding,
                &resources.backings.policies[index], &resources.userns, uids, gids)?;
            resources.images[index].mount = Some(mount);
            resources.images[index].observed = Some(PersistentRootObservation::capture(
                resources.images[index].mount.as_ref().unwrap())?);
            fixture.verify_lease(witness.identity_lease()?)?;
        }
        value.verify(witness)?;
        Ok(value)
    }

    fn matches(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        require_complete_namespace(witness)?;
        witness.revalidate_live_admission()?;
        let resources = self.prepared.as_ref().and_then(|p| p.resources.as_ref())
            .ok_or(MountError::Rejected("private persistent custody absent"))?;
        let lease = witness.identity_lease()?;
        let namespace = witness.user_namespace().metadata()?;
        require((namespace.dev(), namespace.ino()) == resources.userns_identity
            && (resources.userns.metadata()?.dev(), resources.userns.metadata()?.ino()) == resources.userns_identity
            && lease.host_uid() == resources.host_uid && lease.broker_cohort() == resources.cohort
            && lease.broker_ranges() == (resources.uids, resources.gids)
            && FileIdentity::of(&resources.reservation_retention.metadata()?) == resources.reservation_node,
            "same actual private namespace, typed lease and original reservation OFD")?;
        resources.backings.revalidate(witness)?;
        witness.revalidate_live_admission()?;
        Ok(())
    }

    pub(crate) fn verify(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        self.matches(witness)?;
        self.prepared.as_ref().ok_or(MountError::Rejected("private data retired"))?
            .revalidate_owned_lifetime(witness)
    }

    pub(crate) fn descriptors<'a>(&'a mut self, witness: &OwnedNamespaceWitness<'_>)
        -> Result<([BorrowedFd<'a>; 2], [PersistentRootObservation; 2])> {
        self.verify(witness)?;
        let prepared = self.prepared.as_mut().ok_or(MountError::Rejected("private data retired"))?;
        require(!prepared.exported, "exactly one private transfer attempt")?;
        let resources = prepared.resources.as_ref().ok_or(MountError::Rejected("private data resources absent"))?;
        let mut observations = Vec::new();
        for row in &resources.images {
            row.binding.verify()?;
            let mount = row.mount.as_ref().ok_or(MountError::Rejected("held private mount absent"))?;
            let observed = row.observed.ok_or(MountError::Rejected("actual private root absent"))?;
            require(require_detached(mount)? == observed.mount_id, "actual private mount stays detached before send")?;
            observed.verify(mount)?;
            observations.push(observed);
        }
        writable_loop::reject_aliases(&resources.backings.nodes, &resources.images)?;
        resources.backings.revalidate(witness)?;
        // Mark before the caller can attempt sendmsg, including an unknown result.
        prepared.exported = true;
        Ok(([resources.images[0].mount.as_ref().unwrap().as_fd(), resources.images[1].mount.as_ref().unwrap().as_fd()],
            [observations[0], observations[1]]))
    }

    pub(crate) fn duplicate_data_mount(&self) -> Result<File> {
        self.prepared.as_ref().and_then(|p| p.resources.as_ref()).and_then(|r| r.images.first())
            .and_then(|r| r.mount.as_ref()).ok_or(MountError::Rejected("actual data mount absent"))?.try_clone().map_err(Into::into)
    }

    fn expected(&self, after_tree: bool) -> Result<ExpectedRetirement> {
        let resources = self.prepared.as_ref().and_then(|p| p.resources.as_ref()).ok_or(MountError::Rejected("private data retired"))?;
        Ok(ExpectedRetirement { source: [self.source[0].try_clone()?, self.source[1].try_clone()?], nodes: self.nodes,
            devices: resources.images.iter().map(|r| r.binding.device).collect(), after_tree })
    }

    /// Borrowed test entry to the original cleanup implementation permits a
    /// deliberate live-holder negative followed by checked retirement after
    /// that exact holder closes. It never retries a send or constructs a witness.
    pub(crate) fn try_retire_untransferred(&mut self) -> Result<VerifiedPrivateRetirement> {
        let expected = self.expected(false)?;
        let prepared = self.prepared.as_mut().ok_or(MountError::Rejected("private data retired"))?;
        require(!prepared.exported, "attempted transfer requires real original tree retirement")?;
        let retired = prepared.cleanup(false)?;
        self.prepared.take();
        expected.finish(&retired)
    }

    /// Used only by the cfg(test) tree owner, which records PrivateControl in
    /// its existing role inventory. Package retirement must continue to reject.
    pub(crate) fn into_tree_custody(mut self) -> Result<(PreparedPersistentData, ExpectedRetirement)> {
        let expected = self.expected(true)?;
        let prepared = self.prepared.take().ok_or(MountError::Rejected("private data retired"))?;
        require(prepared.exported, "tree custody follows the actual export attempt")?;
        Ok((prepared, expected))
    }

    pub(crate) fn observation(&self) -> Result<serde_json::Value> {
        let resources = self.prepared.as_ref().and_then(|p| p.resources.as_ref()).ok_or(MountError::Rejected("private data retired"))?;
        let rows: Vec<_> = resources.images.iter().map(|row| {
            let node = row.observed.unwrap();
            serde_json::json!({"role":row.role,"device":node.device,"inode":node.inode,"mount_id":node.mount_id,
                "uid":node.uid,"gid":node.gid,"mode":node.mode})
        }).collect();
        Ok(serde_json::json!({"detached":rows,"userns":resources.userns_identity,
            "superblock_sha256":resources.backings.superblock_sha256,"actual_IDMAP":true,
            "production_admission":false}))
    }
}

/// Header-only real rejection uses the same readonly factory and never reaches
/// loop allocation. The full fixture digest is independently checked by caller.
pub(crate) fn header_rejection(fixture: &PersistentFixture<'_>, witness: &OwnedNamespaceWitness<'_>)
    -> Result<(String, VerifiedPrivateRetirement)> {
    fixture.verify_lease(witness.identity_lease()?)?;
    fixture.claim_body_access()?;
    match backings::private_control::open_fixture(fixture, witness) {
        Ok(_) => Err(MountError::Rejected("negative fixture unexpectedly passed actual header admission")),
        Err(error) => Ok((error.to_string(), VerifiedPrivateRetirement {
            source: [fixture.files()[0].try_clone()?, fixture.files()[1].try_clone()?],
            nodes: source_nodes(fixture)?, devices: Vec::new(), readonly_view: false,
        })),
    }
}

/// A distinct actual header/lease control with no loop allocator in its call
/// path, used for a foreign-namespace owner that never receives any mount.
pub(crate) fn header_only(fixture: &PersistentFixture<'_>, witness: &OwnedNamespaceWitness<'_>)
    -> Result<VerifiedPrivateRetirement> {
    fixture.verify_lease(witness.identity_lease()?)?;
    fixture.claim_body_access()?;
    let pair = backings::private_control::open_fixture(fixture, witness)?;
    pair.revalidate(witness)?;
    drop(pair);
    Ok(VerifiedPrivateRetirement { source: [fixture.files()[0].try_clone()?, fixture.files()[1].try_clone()?],
        nodes: source_nodes(fixture)?, devices: Vec::new(), readonly_view: false })
}

/// A fresh readonly/noload lifetime after the writable owner and tree retire.
/// It holds a newly acquired original lease, two actual read-only loop owners,
/// and their detached mounts. It never applies IDMAP to this disk view.
pub(crate) fn readonly_disk_observation(
    fixture: &PersistentFixture<'_>, prior: VerifiedPrivateRetirement,
) -> Result<(serde_json::Value, VerifiedPrivateRetirement)> {
    prior.matches_fixture(fixture)?;
    require(fixture.lease_available()?, "previous complete tree and original lease must be retired")?;
    fixture.run().operation_time()?;
    fixture.accept_retirement(&prior)?;
    let lease = fixture.reserve()?;
    fixture.verify_lease(&lease)?;
    fixture.claim_body_access()?;
    let nodes = source_nodes(fixture)?;
    struct DiskView { mount: Option<File>, binding: LoopBinding }
    struct DiskOwner { rows: Vec<DiskView>, lease: Option<crate::production_identity::IdentityLease> }
    impl Drop for DiskOwner {
        fn drop(&mut self) {
            for row in &mut self.rows { row.mount.take(); }
            let mut ok = true;
            for row in &mut self.rows {
                if row.binding.file.is_some() && row.binding.retire().is_err() { ok = false; }
            }
            if !ok {
                if let Some(lease) = self.lease.take() { std::mem::forget(lease); }
                let rows = std::mem::take(&mut self.rows); std::mem::forget(rows);
            }
        }
    }
    let mut owner = DiskOwner { rows: Vec::new(), lease: Some(lease) };
    let mut observations = Vec::new();
    let mut full_before = Vec::new();
    for (index, name) in [c"data.img", c"metadata.img"].into_iter().enumerate() {
        let source = open_leaf(fixture.parent(), name, libc::O_RDONLY | libc::O_NOATIME)?;
        require(stable(nodes[index], FileIdentity::of(&source.metadata()?)), "same retired original fixture for readonly view")?;
        let before = crate::production_identity::tests::persistent_fixture::digest(&source)?;
        full_before.push(before);
        let binding = LoopBinding::attach_extent(&source, FileIdentity::of(&source.metadata()?), LoopExtent::WholeImage)?;
        owner.rows.push(DiskView { mount: None, binding });
        let row = &mut owner.rows[index];
        row.binding.verify()?;
        let context = syscall_fd(unsafe { libc::syscall(libc::SYS_fsopen, c"ext4".as_ptr(), FSOPEN_CLOEXEC) })?;
        let loop_path = text_name(&format!("/proc/self/fd/{}", row.binding.file()?.as_raw_fd()))?;
        configure(&context, FSCONFIG_SET_STRING, c"source", Some(&loop_path))?;
        configure(&context, FSCONFIG_SET_FLAG, c"ro", None)?;
        configure(&context, FSCONFIG_SET_FLAG, c"noload", None)?;
        let created = unsafe { libc::syscall(libc::SYS_fsconfig, context.as_raw_fd(), FSCONFIG_CMD_CREATE,
            std::ptr::null::<libc::c_char>(), std::ptr::null::<libc::c_char>(), 0) };
        if created != 0 { return Err(io::Error::last_os_error().into()); }
        let mount = syscall_fd(unsafe { libc::syscall(libc::SYS_fsmount, context.as_raw_fd(), FSMOUNT_CLOEXEC, READONLY_FLAGS as u32) })?;
        require(fs_type(&mount)? == 0xef53 && mount.metadata()?.dev() == row.binding.device
            && mount.metadata()?.uid() == 0 && mount.metadata()?.gid() == 0,
            "actual readonly unmapped disk root must retain original guest zero")?;
        require_detached(&mount)?;
        row.mount = Some(mount);
        let root = row.mount.as_ref().unwrap();
        let root_file = open_leaf(root, c"root-seed", libc::O_RDONLY)?;
        let app_dir = open_leaf(root, c"private-app", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let app_file = open_leaf(&app_dir, c"app-probe", libc::O_RDONLY)?;
        let root_node = root_file.metadata()?;
        let app_node = app_file.metadata()?;
        require(root_node.uid() == 0 && root_node.gid() == 0 && app_node.uid() == APP && app_node.gid() == APP,
            "actual on-disk guest IDs must remain unchanged by IDMAP")?;
        for (file, expected) in [(&root_file, b"fixture-root-zero\n".as_slice()), (&app_file, b"fixture-guest-10061\n".as_slice())] {
            let mut body = vec![0; expected.len()];
            require(file.metadata()?.len() == expected.len() as u64, "fixed disposable probe size")?;
            file.read_exact_at(&mut body, 0)?;
            require(body == expected, "actual readonly disk probe contents")?;
        }
        observations.push(serde_json::json!({"role":index,"root_file":{"inode":root_node.ino(),"uid":root_node.uid(),"gid":root_node.gid()},
            "app_file":{"inode":app_node.ino(),"uid":app_node.uid(),"gid":app_node.gid()},"readonly":true,"noload":true,"idmapped":false}));
    }
    for row in &mut owner.rows { row.mount.take(); }
    let mut devices = Vec::new();
    for row in &mut owner.rows { devices.push(row.binding.retire()?); }
    fixture.verify_lease(owner.lease.as_ref().unwrap())?;
    for index in 0..2 {
        require(crate::production_identity::tests::persistent_fixture::digest(&fixture.files()[index])? == full_before[index],
            "readonly noload observation must leave the complete original fixture bytes unchanged")?;
    }
    owner.lease.take();
    require(fixture.lease_available()?, "fresh readonly lifetime fully retired")?;
    let proof = VerifiedPrivateRetirement { source: [fixture.files()[0].try_clone()?, fixture.files()[1].try_clone()?],
        nodes, devices, readonly_view: true };
    Ok((serde_json::json!({"files":observations,"whole_image_bytes_unchanged":true,"new_lease_retired":true,
        "guest_app_uid":APP,"mapped_host_uid":START + APP}), proof))
}
