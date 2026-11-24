//! Readonly evidence from the original, descriptor-owned base mounts.
//! No path, digest, loop number, PID, or success value is accepted from a
//! request. The only APK member is the fixed original CP3A Gallery member.
use super::*;
use crate::control::application_custody::{
    CustodyCohort, CustodyFileIdentity, CustodyImage, CustodyImageMember, CustodyNamespace,
    GALLERY_BYTES, GALLERY_SHA256, GALLERY_SOURCE_PATH, SYSTEM_BYTES, SYSTEM_SHA256,
};
use crate::production_selection::early_generation::EarlyBaseAdmission;
use std::time::{Duration, Instant};

/// Only this module can create the live observation. The wire projection is
/// not deserializable into this owner; the original APK descriptor is retained
/// until the complete PM/query bookend has been checked.
pub(crate) struct ObservedGalleryImage {
    cohort: CustodyCohort,
    apk: CustodyImageMember,
    apk_file: File,
    after: Option<(CustodyCohort, CustodyImageMember)>,
}
impl ObservedGalleryImage {
    pub(crate) fn verify_originating_root(&self, root: &File) -> Result<()> {
        let actual = identity(root)?;
        require(
            actual.device == self.cohort.system.mount_root.device
                && actual.inode == self.cohort.system.mount_root.inode
                && mount_id(root)? == self.cohort.system.mount_id,
            "image custody root differs from the original transferred system mount",
        )
    }
    pub(crate) fn evidence(
        &self,
    ) -> Result<(
        CustodyCohort,
        CustodyImageMember,
        CustodyCohort,
        CustodyImageMember,
    )> {
        let (cohort, apk) = self.after.as_ref().ok_or(MountError::Rejected(
            "actual complete after-byte observation absent",
        ))?;
        Ok((
            self.cohort.clone(),
            self.apk.clone(),
            cohort.clone(),
            apk.clone(),
        ))
    }
}

fn identity(file: &File) -> Result<CustodyFileIdentity> {
    let value = FileIdentity::of(&file.metadata()?);
    Ok(CustodyFileIdentity {
        device: value.dev,
        inode: value.ino,
        mode: value.mode,
        uid: value.uid,
        gid: value.gid,
        links: value.links,
        bytes: value.bytes,
        modified: value.mtime,
        changed: value.ctime,
    })
}

fn before_deadline(deadline: Instant) -> Result<()> {
    require(Instant::now() < deadline, "whole-image inspection deadline")
}

fn complete_hash(
    file: &File,
    bytes: u64,
    deadline: Instant,
    progress: &dyn Fn() -> io::Result<()>,
) -> Result<String> {
    before_deadline(deadline)?;
    let before = identity(file)?;
    require(before.bytes == bytes, "whole-byte inspection size differs")?;
    let mut sha = Sha256::new();
    let mut block = vec![0_u8; 1024 * 1024];
    let mut offset = 0;
    let mut next_progress = Instant::now();
    while offset < bytes {
        before_deadline(deadline)?;
        if Instant::now() >= next_progress {
            progress()?;
            before_deadline(deadline)?;
            next_progress = Instant::now() + Duration::from_millis(25);
        }
        let count = ((bytes - offset).min(block.len() as u64)) as usize;
        file.read_exact_at(&mut block[..count], offset)?;
        sha.update(&block[..count]);
        offset += count as u64;
    }
    require(
        identity(file)? == before,
        "whole-byte inspection inode changed",
    )?;
    before_deadline(deadline)?;
    Ok(format!("{:x}", sha.finalize()))
}

fn fixed_path(file: &SealedFile) -> Result<String> {
    let name = file
        .name
        .to_str()
        .map_err(|_| MountError::Rejected("image name encoding"))?;
    file.parent_path
        .join(name)
        .to_str()
        .map(str::to_owned)
        .ok_or(MountError::Rejected("fixed image path encoding"))
}

fn image_observation(
    resources: &MountResources,
    row: &MountedImage,
    declaration: &ImageDeclaration,
    source: &SealedFile,
    full_hash: bool,
    deadline: Instant,
    progress: &dyn Fn() -> io::Result<()>,
) -> Result<CustodyImage> {
    before_deadline(deadline)?;
    source.revalidate()?;
    require(
        row.binding.source == source.identity
            && matches!(row.binding.extent, LoopExtent::WholeImage)
            && source.identity.bytes == declaration.bytes,
        "same whole-image source and exact declared size",
    )?;
    row.binding.verify()?;
    let mount = row
        .mount
        .as_ref()
        .ok_or(MountError::Rejected("held base mount absent"))?;
    verify_readonly_mount(mount, row.fs, resources.uids, resources.gids, row.mount_id)?;
    let digest_value = if full_hash {
        complete_hash(&source.file, source.identity.bytes, deadline, progress)?
    } else {
        // Only revalidation of an opaque observation can reach this branch.
        // Complete bytes were read at creation; exact file/path F9 and all
        // held loop/mount resources must still equal that original bookend.
        declaration.sha256.clone()
    };
    require(
        digest_value == declaration.sha256,
        "selected complete image digest differs",
    )?;
    let loop_file = row.binding.file()?;
    let actual = loop_status(loop_file)?.ok_or(MountError::Rejected("owned loop is unbound"))?;
    owned_loop_info(&actual, source.identity, row.binding.index, (0, 0))?;
    let mut vfs: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(mount.as_raw_fd(), &mut vfs) })?;
    let mount_root = identity(mount)?;
    require(
        mount_root.device == row.binding.device,
        "filesystem is not on the owned loop",
    )?;
    source.revalidate()?;
    row.binding.verify()?;
    before_deadline(deadline)?;
    Ok(CustodyImage {
        role: row.role.into(),
        path: fixed_path(source)?,
        file: identity(&source.file)?,
        sha256: digest_value,
        loop_node: identity(loop_file)?,
        loop_device: row.binding.device,
        loop_number: actual.number,
        loop_source_device: actual.device,
        loop_source_inode: actual.inode,
        loop_offset: actual.offset,
        loop_size_limit: actual.size_limit,
        loop_flags: actual.flags,
        mount_id: mount_id(mount)?,
        mount_root,
        mount_flags: vfs.f_flag as u64,
        filesystem: match row.fs {
            Filesystem::Ext4 => "ext4",
            Filesystem::Erofs => "erofs",
        }
        .into(),
    })
}

fn cohort_observation(
    resources: &MountResources,
    witness: &impl early::BaseAuthority,
    full_hash: bool,
    deadline: Instant,
    progress: &dyn Fn() -> io::Result<()>,
) -> Result<CustodyCohort> {
    before_deadline(deadline)?;
    witness.revalidate_live_admission()?;
    resources.matches_witness(witness)?;
    resources.cohort.revalidate(witness)?;
    require_complete_namespace(witness)?;
    require(
        resources.has_declared_set(),
        "complete ordered admitted base-image set",
    )?;
    let raw = resources.cohort.manifest.bounded_bytes(MAX_MANIFEST)?;
    let manifest_sha256 = format!("{:x}", Sha256::digest(&raw));
    require(
        manifest_sha256 == resources.cohort.cohort,
        "same reserved complete manifest bytes",
    )?;
    let declaration: CohortDeclaration = serde_json::from_slice(&raw)?;
    declaration.validate()?;
    require(
        declaration.system.bytes == SYSTEM_BYTES && declaration.system.sha256 == SYSTEM_SHA256,
        "image-installed Gallery requires the complete original CP3A system image",
    )?;
    let system = image_observation(
        resources,
        &resources.images[0],
        &declaration.system,
        &resources.cohort.system,
        full_hash,
        deadline,
        progress,
    )?;
    let vendor = image_observation(
        resources,
        &resources.images[1],
        &declaration.vendor,
        &resources.cohort.vendor,
        full_hash,
        deadline,
        progress,
    )?;
    let user = resources.userns.metadata()?;
    resources.cohort.revalidate(witness)?;
    resources.matches_witness(witness)?;
    witness.revalidate_live_admission()?;
    before_deadline(deadline)?;
    Ok(CustodyCohort {
        manifest_path: fixed_path(&resources.cohort.manifest)?,
        manifest: identity(&resources.cohort.manifest.file)?,
        manifest_sha256,
        host_uid: resources.cohort.host_uid,
        user_namespace: CustodyNamespace {
            name: "user".into(),
            device: user.dev(),
            inode: user.ino(),
        },
        uid_range: (resources.uids.start, resources.uids.count),
        gid_range: (resources.gids.start, resources.gids.count),
        system,
        vendor,
    })
}

fn original_gallery(
    resources: &MountResources,
    witness: &impl early::BaseAuthority,
    body: bool,
) -> Result<File> {
    resources.matches_witness(witness)?;
    resources.cohort.revalidate(witness)?;
    let row = resources
        .images
        .first()
        .ok_or(MountError::Rejected("original system mount absent"))?;
    require(row.role == "system", "original system image role")?;
    row.binding.verify()?;
    let mount = row
        .mount
        .as_ref()
        .ok_or(MountError::Rejected("original system root absent"))?;
    verify_readonly_mount(mount, row.fs, resources.uids, resources.gids, row.mount_id)?;
    let mut parent = mount.try_clone()?;
    for name in [c"system", c"product", c"app", c"Gallery2"] {
        parent = open_leaf(&parent, name, libc::O_PATH | libc::O_DIRECTORY)?;
        require(
            mount_id(&parent)? == row.mount_id,
            "original Gallery directory crossed a mount",
        )?;
    }
    let probe = open_leaf(&parent, c"Gallery2.apk", libc::O_PATH)?;
    witness
        .identity_lease()?
        .broker_reject_backing_body(&probe)?;
    require(
        probe.metadata()?.is_file()
            && probe.metadata()?.len() == GALLERY_BYTES
            && mount_id(&probe)? == row.mount_id,
        "original Gallery is not the bounded member of the admitted system mount",
    )?;
    if !body {
        return Ok(probe);
    }
    let file = open_leaf(&parent, c"Gallery2.apk", libc::O_RDONLY)?;
    require(
        identity(&file)? == identity(&probe)?,
        "Gallery replaced before its body open",
    )?;
    witness
        .identity_lease()?
        .broker_reject_backing_body(&file)?;
    require(
        mount_id(&file)? == row.mount_id,
        "Gallery body crossed the admitted mount",
    )?;
    resources.cohort.revalidate(witness)?;
    Ok(file)
}

impl PreparedMounts {
    pub(crate) fn observe_gallery_custody(
        &self,
        witness: &OwnedNamespaceWitness<'_>,
        deadline: Instant,
    ) -> Result<ObservedGalleryImage> {
        self.observe_gallery_custody_with_authority(witness, deadline, &|| Ok(()))
    }
    pub(crate) fn complete_gallery_byte_bookend(
        &self,
        witness: &OwnedNamespaceWitness<'_>,
        observed: &mut ObservedGalleryImage,
        deadline: Instant,
    ) -> Result<()> {
        self.complete_gallery_byte_bookend_with_authority(witness, observed, deadline, &|| Ok(()))
    }
    pub(crate) fn revalidate_gallery_custody(
        &self,
        witness: &OwnedNamespaceWitness<'_>,
        observed: &ObservedGalleryImage,
        deadline: Instant,
    ) -> Result<()> {
        self.revalidate_gallery_custody_with_authority(witness, observed, deadline)
    }
    pub(crate) fn observe_gallery_custody_early(
        &self,
        witness: &EarlyBaseAdmission<'_>,
        deadline: Instant,
        progress: &dyn Fn() -> io::Result<()>,
    ) -> Result<ObservedGalleryImage> {
        self.observe_gallery_custody_with_authority(witness, deadline, progress)
    }
    pub(crate) fn complete_gallery_byte_bookend_early(
        &self,
        witness: &EarlyBaseAdmission<'_>,
        observed: &mut ObservedGalleryImage,
        deadline: Instant,
        progress: &dyn Fn() -> io::Result<()>,
    ) -> Result<()> {
        self.complete_gallery_byte_bookend_with_authority(witness, observed, deadline, progress)
    }
    pub(crate) fn revalidate_gallery_custody_early(
        &self,
        witness: &EarlyBaseAdmission<'_>,
        observed: &ObservedGalleryImage,
        deadline: Instant,
    ) -> Result<()> {
        self.revalidate_gallery_custody_with_authority(witness, observed, deadline)
    }
    fn observe_gallery_custody_with_authority(
        &self,
        witness: &impl early::BaseAuthority,
        deadline: Instant,
        progress: &dyn Fn() -> io::Result<()>,
    ) -> Result<ObservedGalleryImage> {
        require(
            self.exported,
            "Gallery observation requires actual base transfer",
        )?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("base resources retired"))?;
        let cohort = cohort_observation(resources, witness, true, deadline, progress)?;
        let apk_file = original_gallery(resources, witness, true)?;
        let sha256 = complete_hash(&apk_file, GALLERY_BYTES, deadline, progress)?;
        require(
            sha256 == GALLERY_SHA256,
            "original Gallery full body differs",
        )?;
        let apk = CustodyImageMember {
            path: GALLERY_SOURCE_PATH.into(),
            file: identity(&apk_file)?,
            sha256,
            mount_id: mount_id(&apk_file)?,
        };
        let observed = ObservedGalleryImage {
            cohort,
            apk,
            apk_file,
            after: None,
        };
        self.revalidate_gallery_custody_with_authority(witness, &observed, deadline)?;
        Ok(observed)
    }

    /// Exactly one complete after-byte pass. Metadata-only bookends cannot
    /// fill this slot, and the wire evidence accessor rejects an empty slot.
    fn complete_gallery_byte_bookend_with_authority(
        &self,
        witness: &impl early::BaseAuthority,
        observed: &mut ObservedGalleryImage,
        deadline: Instant,
        progress: &dyn Fn() -> io::Result<()>,
    ) -> Result<()> {
        require(
            observed.after.is_none(),
            "single complete after-byte observation required",
        )?;
        self.revalidate_gallery_custody_with_authority(witness, observed, deadline)?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("base resources retired"))?;
        let cohort = cohort_observation(resources, witness, true, deadline, progress)?;
        let apk = CustodyImageMember {
            path: GALLERY_SOURCE_PATH.into(),
            file: identity(&observed.apk_file)?,
            sha256: complete_hash(&observed.apk_file, GALLERY_BYTES, deadline, progress)?,
            mount_id: mount_id(&observed.apk_file)?,
        };
        require(
            cohort == observed.cohort && apk == observed.apk,
            "actual complete image or original APK after-byte read differs",
        )?;
        self.revalidate_gallery_custody_with_authority(witness, observed, deadline)?;
        observed.after = Some((cohort, apk));
        Ok(())
    }

    fn revalidate_gallery_custody_with_authority(
        &self,
        witness: &impl early::BaseAuthority,
        observed: &ObservedGalleryImage,
        deadline: Instant,
    ) -> Result<()> {
        require(self.exported, "same transferred base resources required")?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("base resources retired"))?;
        let current = cohort_observation(resources, witness, false, deadline, &|| Ok(()))?;
        require(
            current == observed.cohort,
            "whole-image custody changed during PM inspection",
        )?;
        let again = original_gallery(resources, witness, false)?;
        require(
            identity(&again)? == observed.apk.file
                && identity(&observed.apk_file)? == observed.apk.file
                && mount_id(&again)? == observed.apk.mount_id
                && mount_id(&observed.apk_file)? == observed.apk.mount_id,
            "same original Gallery descriptor and path bookend required",
        )?;
        resources.cohort.revalidate(witness)?;
        witness.revalidate_live_admission()?;
        before_deadline(deadline)
    }
}

#[cfg(test)]
mod progress_tests {
    use super::*;
    use std::cell::Cell;
    use std::io::Write;

    #[test]
    fn complete_source_read_progresses_and_stops_on_original_frontend_failure() {
        let mut file = tempfile::tempfile().unwrap();
        let bytes = vec![7u8; 1024 * 1024 + 13];
        file.write_all(&bytes).unwrap();
        let calls = Cell::new(0usize);
        let wanted = format!("{:x}", Sha256::digest(&bytes));
        let actual = complete_hash(
            &file,
            bytes.len() as u64,
            Instant::now() + Duration::from_secs(5),
            &|| {
                calls.set(calls.get() + 1);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(actual, wanted);
        assert!(calls.get() > 0);
        let stopped = complete_hash(
            &file,
            bytes.len() as u64,
            Instant::now() + Duration::from_secs(5),
            &|| {
                Err(io::Error::new(
                    io::ErrorKind::Interrupted,
                    "original owner stopped",
                ))
            },
        );
        assert!(
            matches!(stopped, Err(MountError::Io(ref error)) if error.kind() == io::ErrorKind::Interrupted)
        );
        assert!(complete_hash(&file, bytes.len() as u64, Instant::now(), &|| Ok(())).is_err());
    }
}
