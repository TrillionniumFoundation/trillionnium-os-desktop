//! A read-only borrow of the early service's actual original base-image owner.
//! No receipt, PID, pathname, or external descriptor can create this capability.
use super::*;
use crate::control::application_custody::{CustodyNamespace, CustodyOwner};
use crate::production_mounts::custody::ObservedGalleryImage;

impl EarlyApplicationAuthority<'_> {
    fn image_custody_owner(&self, deadline: Instant) -> Result<CustodyOwner> {
        self.progress_inherited_native(deadline)?;
        self.ready()?;
        let selected = self.base.board().selection();
        selected.revalidate().map_err(external)?;
        let user = self.base.user_namespace().metadata()?;
        let mut namespaces = vec![CustodyNamespace {
            name: "user".into(),
            device: user.dev(),
            inode: user.ino(),
        }];
        require(
            self.namespaces.len() == 6,
            "original image namespace set is incomplete",
        )?;
        for (name, held) in ["mount", "pid", "ipc", "uts", "net", "cgroup"]
            .into_iter()
            .zip(&self.namespaces)
        {
            let actual = held.metadata()?;
            namespaces.push(CustodyNamespace {
                name: name.into(),
                device: actual.dev(),
                inode: actual.ino(),
            });
        }
        namespaces.sort_by(|a, b| a.name.cmp(&b.name));
        let owner = CustodyOwner {
            host_uid: selected.spec().host_uid,
            cell_host_pid: self.init.pid,
            cell_start_ticks: self.init.start,
            selection_binding_sha256: selected
                .package_binding()
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect(),
            base_cohort_sha256: selected.base_cohort().into(),
            runtime_manifest_sha256: selected.runtime_manifest().into(),
            namespaces,
        };
        self.ready()?;
        require(Instant::now() < deadline, "early image owner deadline")?;
        Ok(owner)
    }

    pub(crate) fn observe_gallery_image(
        &self,
        deadline: Instant,
    ) -> Result<(ObservedGalleryImage, CustodyOwner)> {
        let owner = self.image_custody_owner(deadline)?;
        // Keep the existing frontend and stop signal progressing during the
        // whole-byte reads. The original owner is fully checked at bookends.
        let observed = self
            .images
            .observe_gallery_custody_early(self.base, deadline, self.progress)
            .map_err(external)?;
        observed
            .verify_originating_root(self.root)
            .map_err(external)?;
        require(
            self.image_custody_owner(deadline)? == owner,
            "early image owner changed during original whole-byte read",
        )?;
        Ok((observed, owner))
    }

    pub(crate) fn complete_gallery_image(
        &self,
        observed: &mut ObservedGalleryImage,
        owner: &CustodyOwner,
        deadline: Instant,
    ) -> Result<()> {
        require(
            &self.image_custody_owner(deadline)? == owner,
            "early image after-byte read requires the same original owner",
        )?;
        observed
            .verify_originating_root(self.root)
            .map_err(external)?;
        self.images
            .complete_gallery_byte_bookend_early(self.base, observed, deadline, self.progress)
            .map_err(external)?;
        observed
            .verify_originating_root(self.root)
            .map_err(external)?;
        require(
            &self.image_custody_owner(deadline)? == owner,
            "early image owner changed during complete after-byte read",
        )
    }

    pub(crate) fn revalidate_gallery_image(
        &self,
        observed: &ObservedGalleryImage,
        owner: &CustodyOwner,
        deadline: Instant,
    ) -> Result<()> {
        require(
            &self.image_custody_owner(deadline)? == owner,
            "early image observation belongs to another original owner",
        )?;
        observed
            .verify_originating_root(self.root)
            .map_err(external)?;
        self.images
            .revalidate_gallery_custody_early(self.base, observed, deadline)
            .map_err(external)?;
        require(
            &self.image_custody_owner(deadline)? == owner,
            "early image owner changed during final bookend",
        )
    }
}
