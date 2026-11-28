//! Compare the original writable owner with fixed roots in its live framework.
//! This borrows already-admitted resources. It does not open an image body,
//! read private transaction receipts, create a loop, mount, or mutate a label.
use super::*;
use crate::main_custody::{
    MainBackingCustody, MainBackingIdentity, MainDataRole, MainLoopIdentity, MainMountRoot,
    MainNodeIdentity, MainOriginalCopyOrigin, MainPersistentCustody,
};

fn root(value: PersistentRootObservation) -> MainMountRoot {
    MainMountRoot {
        device: value.device,
        inode: value.inode,
        mount_id: value.mount_id,
        uid: value.uid,
        gid: value.gid,
        mode: value.mode,
    }
}

impl PreparedPersistentData {
    pub(crate) fn observe_main_custody(
        &self,
        admission: &EarlyStorageAdmission<'_, '_>,
        framework_root: &File,
    ) -> Result<MainPersistentCustody> {
        self.revalidate_early_lifetime(admission)?;
        let owner = admission.namespace();
        let selected = admission.selection();
        selected.revalidate().map_err(io::Error::other)?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("Main persistent owner has retired"))?;
        require(
            self.exported
                && resources.selection_binding == selected.package_binding()
                && resources.host_uid == selected.spec().host_uid
                && resources.cohort == selected.base_cohort(),
            "Main observation requires this actual exported selected data pair",
        )?;
        let mut values = Vec::new();
        let mut live_roots = Vec::new();
        for (index, (name, role)) in [
            (c"data", MainDataRole::Data),
            (c"metadata", MainDataRole::Metadata),
        ]
        .into_iter()
        .enumerate()
        {
            owner.revalidate()?;
            let row = &resources.images[index];
            require(row.role == index, "Main persistent role order changed")?;
            let retained = row
                .observed
                .ok_or(MountError::Rejected("Main retained persistent root absent"))?;
            let retained_fd = row.mount.as_ref().ok_or(MountError::Rejected(
                "Main retained mount descriptor absent",
            ))?;
            row.binding.verify()?;
            retained.verify(retained_fd)?;
            let live_root = open_leaf(framework_root, name, libc::O_PATH | libc::O_DIRECTORY)?;
            let actual = PersistentRootObservation::capture(&live_root)?;
            let retained_root = root(retained);
            let framework_mount = root(actual);
            require(
                retained_root.same_filesystem_root(&framework_mount)
                    && actual.mount_id != retained.mount_id
                    && actual.device == row.binding.device,
                "framework data root is not the cloned original writable filesystem",
            )?;
            let backing = MainBackingIdentity::of(&resources.backings.files[index].metadata()?);
            let old = resources.backings.nodes[index];
            require(
                backing.stable7()
                    == [
                        old.dev,
                        old.ino,
                        u64::from(old.mode),
                        u64::from(old.uid),
                        u64::from(old.gid),
                        old.links,
                        old.bytes,
                    ],
                "Main backing identity changed while mounted",
            )?;
            values.push(MainBackingCustody {
                role,
                backing,
                loop_binding: MainLoopIdentity {
                    node: MainNodeIdentity::of(&row.binding.file()?.metadata()?),
                    block_device: row.binding.device,
                },
                retained_root,
                framework_root: framework_mount,
            });
            live_roots.push((name, live_root, actual));
        }
        // Revalidate the same selected policy and all original lease/backing/
        // loop descriptors after the fixed path lookup. Then compare held and
        // named framework roots again without reading any private file body.
        self.revalidate_early_lifetime(admission)?;
        selected.revalidate().map_err(io::Error::other)?;
        for (name, held, observed) in &live_roots {
            observed.verify(held)?;
            observed.verify(&open_leaf(
                framework_root,
                name,
                libc::O_PATH | libc::O_DIRECTORY,
            )?)?;
        }
        let backings: [MainBackingCustody; 2] = values
            .try_into()
            .map_err(|_| MountError::Rejected("Main requires exactly two persistent backings"))?;
        let policy = selected
            .persistent_data_policy()
            .map_err(io::Error::other)?;
        let original_copy_origin = policy
            .original_copy
            .as_ref()
            .map(|copy| {
                copy.verify_working([backings[0].backing.stable7(), backings[1].backing.stable7()])
                    .map_err(io::Error::other)?;
                Ok::<_, io::Error>(MainOriginalCopyOrigin {
                    schema: copy.schema.clone(),
                    working_copy_sha256: copy.working_copy_sha256.clone(),
                    cold_clone_sha256: copy.cold_clone_sha256.clone(),
                    original: copy.original,
                    working: copy.working,
                })
            })
            .transpose()?;
        let observed = MainPersistentCustody {
            host_uid: resources.host_uid,
            base_cohort_sha256: resources.cohort.clone(),
            selection_binding_sha256: resources
                .selection_binding
                .iter()
                .map(|v| format!("{v:02x}"))
                .collect(),
            user_namespace: MainNodeIdentity::of(&resources.userns.metadata()?),
            reservation_lease: MainNodeIdentity::of(&resources.reservation_retention.metadata()?),
            backings,
            original_copy_origin,
            fresh_diagnostic_origin: resources.backings.fresh.as_ref()
                .map(|proof| proof.comparison(&resources.backings.files)).transpose()?,
        };
        admission.verify()?;
        Ok(observed)
    }

    pub(crate) fn claim_fresh_meituan_installation(&self, admission: &EarlyStorageAdmission<'_, '_>) -> Result<()> {
        self.revalidate_early_lifetime(admission)?;
        let resources = self.resources.as_ref().ok_or(MountError::Rejected("EMPTY storage owner retired"))?;
        require(self.exported, "EMPTY installation requires the actual exported live pair")?;
        let proof = resources.backings.fresh.as_ref()
            .ok_or(MountError::Rejected("normal existing data has no positive EMPTY capability"))?;
        proof.claim_installation(&resources.backings.files)?;
        self.revalidate_early_lifetime(admission)
    }
}
