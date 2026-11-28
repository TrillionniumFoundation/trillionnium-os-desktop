//! Private engine identity captured by the normal immutable image composer.
//! A request cannot provide this value. The owner retains the same whole-image
//! file, loop and mount until the original Android generation has retired.
use super::*;
use crate::control::application_custody::CustodyFileIdentity;
use crate::engine_custody::{
    BridgeEngineImageSource, EngineFile, EngineImageSource, EngineKind, MAX_ENGINE_BYTES,
    NativeEngineImageSource,
};
use crate::production_selection::early_generation::EarlyBaseAdmission;
use std::time::Instant;

#[derive(Debug)]
pub(super) struct EngineOrigin {
    file: CustodyFileIdentity,
    sha256: String,
}
fn node(file: &File) -> Result<CustodyFileIdentity> {
    let n = FileIdentity::of(&file.metadata()?);
    Ok(CustodyFileIdentity {
        device: n.dev,
        inode: n.ino,
        mode: n.mode,
        uid: n.uid,
        gid: n.gid,
        links: n.links,
        bytes: n.bytes,
        modified: n.mtime,
        changed: n.ctime,
    })
}
pub(super) fn capture(resources: &MountResources) -> Result<EngineOrigin> {
    let row = resources
        .images
        .get(2)
        .ok_or(MountError::Rejected("engine image missing"))?;
    require(row.role == "system_ext_lib64", "fixed engine image role")?;
    row.binding.verify()?;
    let root = row
        .mount
        .as_ref()
        .ok_or(MountError::Rejected("engine mount missing"))?;
    verify_readonly_mount(root, row.fs, resources.uids, resources.gids, row.mount_id)?;
    // compose() has just compared this complete subtree to the actual selected
    // vendor. This is the same readonly held filesystem, with no new pathname.
    let file = open_leaf(root, c"libberberis_arm64.so", libc::O_RDONLY)?;
    let before = node(&file)?;
    require(
        before.device == root.metadata()?.dev()
            && before.mode & 0o177777 == 0o100644
            && before.links == 1
            && before.uid == resources.uids.start
            && before.gid == resources.gids.start
            && (64..=MAX_ENGINE_BYTES).contains(&before.bytes)
            && mount_id(&file)? == row.mount_id,
        "composed engine metadata or mount differs",
    )?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    let mut offset = 0;
    while offset < before.bytes {
        let count = (before.bytes - offset).min(buffer.len() as u64) as usize;
        file.read_exact_at(&mut buffer[..count], offset)?;
        hash.update(&buffer[..count]);
        offset += count as u64;
    }
    let again = open_leaf(root, c"libberberis_arm64.so", libc::O_RDONLY)?;
    require(
        node(&file)? == before && node(&again)? == before,
        "composed engine changed during capture",
    )?;
    row.binding.verify()?;
    Ok(EngineOrigin {
        file: before,
        sha256: format!("{:x}", hash.finalize()),
    })
}

impl PreparedMounts {
    pub(crate) fn observe_engine_origin_early(
        &self,
        witness: &EarlyBaseAdmission<'_>,
        kind: EngineKind,
        deadline: Instant,
        progress: &dyn Fn() -> io::Result<()>,
    ) -> Result<EngineImageSource> {
        // Same normal four-image, lease, readonly loop and full F9 bookends as
        // VINTF. No library body permission is added to the live broker.
        let rows = self.observe_vintf_mount_bindings_early(witness, deadline, progress)?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("engine owner retired"))?;
        if kind == EngineKind::NativeX86_64 {
            let image =
                rows.into_iter()
                    .find(|row| row.role == "system")
                    .ok_or(MountError::Rejected(
                        "selected system image observation absent",
                    ))?;
            require(
                image.file.bytes == crate::production_execution_profile::SYSTEM_BYTES
                    && image.sha256 == crate::production_execution_profile::SYSTEM_SHA256,
                "native runtime system differs from fixed normal source",
            )?;
            return Ok(EngineImageSource::NativeX86_64 {
                image: NativeEngineImageSource {
                    base_cohort_sha256: resources.cohort.cohort.clone(),
                    system_image: image,
                    art_input: crate::engine_custody::native_profile::art_input()
                        .map_err(MountError::Rejected)?,
                    whole_image_body_rehashed_by_this_observation: false,
                    apex_mount_owner_borrowed: false,
                },
            });
        }
        let held = resources
            .engine
            .as_ref()
            .ok_or(MountError::Rejected("normal engine capture absent"))?;
        let image = rows
            .into_iter()
            .find(|row| row.role == "system_ext_lib64")
            .ok_or(MountError::Rejected("engine image observation absent"))?;
        require(
            held.file.device == image.mount_root.device
                && held.file.uid == resources.uids.start
                && held.file.gid == resources.gids.start,
            "engine identity differs from original image or idmap",
        )?;
        let mut scoped = held.file;
        // The actual observer enters precisely this held USERNS. fstat there
        // reports namespace root for these same idmapped immutable inodes.
        scoped.uid = 0;
        scoped.gid = 0;
        let engine = EngineFile {
            identity: scoped,
            sha256: held.sha256.clone(),
        };
        require(
            crate::engine_custody::valid_engine(&engine),
            "invalid normal engine capture",
        )?;
        Ok(EngineImageSource::BerberisArm64 {
            image: BridgeEngineImageSource {
                base_cohort_sha256: resources.cohort.cohort.clone(),
                library_image: image,
                engine,
                whole_image_body_rehashed_by_this_observation: false,
            },
        })
    }
}
