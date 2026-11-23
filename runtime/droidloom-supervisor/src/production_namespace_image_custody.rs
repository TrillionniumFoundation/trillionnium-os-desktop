//! An image-inspection borrow of the existing original Ready owner.
//! No numeric PID, saved receipt, caller-selected mount, or old host-namespace
//! baseline can construct the image owner used by this path.
use super::*;
use crate::control::application_custody::{CustodyNamespace, CustodyOwner};
use crate::production_mounts::custody::ObservedGalleryImage;

fn within(deadline: Instant) -> Result<()> {
    if Instant::now() >= deadline {
        return Err(NamespaceError::Rejected("image custody absolute deadline"));
    }
    Ok(())
}

impl ReadyTreeWitness<'_> {
    fn image_custody_owner(&mut self, deadline: Instant) -> Result<CustodyOwner> {
        within(deadline)?;
        self.revalidate_application()?;
        let authority = self.application_authority();
        authority.revalidate()?;
        let child = authority.child()?;
        let user = child.namespaces.userns.metadata()?;
        let mut namespaces = vec![CustodyNamespace {
            name: "user".into(), device: user.dev(), inode: user.ino(),
        }];
        for (name, kind) in [
            ("mount", libc::CLONE_NEWNS),
            ("pid", libc::CLONE_NEWPID),
            ("ipc", libc::CLONE_NEWIPC),
            ("uts", libc::CLONE_NEWUTS),
            ("net", libc::CLONE_NEWNET),
            ("cgroup", libc::CLONE_NEWCGROUP),
        ] {
            let held = child.namespaces.held.iter().find(|row| row.1 == kind)
                .ok_or(NamespaceError::Rejected("original image namespace absent"))?;
            let metadata = held.3.metadata()?;
            namespaces.push(CustodyNamespace {
                name: name.into(), device: metadata.dev(), inode: metadata.ino(),
            });
        }
        namespaces.sort_by(|a, b| a.name.cmp(&b.name));
        let observed = CustodyOwner {
            host_uid: self.selection.spec().host_uid,
            cell_host_pid: child.identity.pid,
            cell_start_ticks: child.identity.start_ticks,
            selection_binding_sha256: self.selection.package_binding().iter()
                .map(|byte| format!("{byte:02x}")).collect(),
            base_cohort_sha256: self.selection.base_cohort().into(),
            runtime_manifest_sha256: self.selection.runtime_manifest().into(),
            namespaces,
        };
        authority.revalidate()?;
        within(deadline)?;
        Ok(observed)
    }

    pub(crate) fn observe_gallery_image(
        &mut self,
        deadline: Instant,
    ) -> Result<(ObservedGalleryImage, CustodyOwner)> {
        let before = self.image_custody_owner(deadline)?;
        let observed = {
            let tree = &self.owner.tree;
            let witness = tree.witness()?;
            match tree.bases.as_ref().ok_or(NamespaceError::Rejected("original bases absent"))? {
                BaseMounts::Admitted(value) => value.observe_gallery_custody(&witness, deadline)
                    .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?,
                #[cfg(test)]
                BaseMounts::PrivateControl(_) => return Err(NamespaceError::HostAdmissionRequired),
            }
        };
        if self.image_custody_owner(deadline)? != before {
            return Err(NamespaceError::Rejected("original image owner changed during whole-image read"));
        }
        Ok((observed, before))
    }

    pub(crate) fn revalidate_gallery_image(
        &mut self,
        observed: &ObservedGalleryImage,
        original_owner: &CustodyOwner,
        deadline: Instant,
    ) -> Result<()> {
        if &self.image_custody_owner(deadline)? != original_owner {
            return Err(NamespaceError::Rejected("current image owner differs from original read"));
        }
        {
            let tree = &self.owner.tree;
            let witness = tree.witness()?;
            match tree.bases.as_ref().ok_or(NamespaceError::Rejected("original bases absent"))? {
                BaseMounts::Admitted(value) => value.revalidate_gallery_custody(&witness, observed, deadline)
                    .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?,
                #[cfg(test)]
                BaseMounts::PrivateControl(_) => return Err(NamespaceError::HostAdmissionRequired),
            }
        }
        if &self.image_custody_owner(deadline)? != original_owner {
            return Err(NamespaceError::Rejected("image owner changed during final read bookend"));
        }
        within(deadline)
    }

    pub(crate) fn complete_gallery_image(
        &mut self,
        observed: &mut ObservedGalleryImage,
        original_owner: &CustodyOwner,
        deadline: Instant,
    ) -> Result<()> {
        if &self.image_custody_owner(deadline)? != original_owner {
            return Err(NamespaceError::Rejected("image after-byte read requires the original owner"));
        }
        {
            let tree = &self.owner.tree;
            let witness = tree.witness()?;
            match tree.bases.as_ref().ok_or(NamespaceError::Rejected("original bases absent"))? {
                BaseMounts::Admitted(value) => value.complete_gallery_byte_bookend(&witness, observed, deadline)
                    .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?,
                #[cfg(test)]
                BaseMounts::PrivateControl(_) => return Err(NamespaceError::HostAdmissionRequired),
            }
        }
        if &self.image_custody_owner(deadline)? != original_owner {
            return Err(NamespaceError::Rejected("image owner changed during complete after-byte read"));
        }
        within(deadline)
    }
}
