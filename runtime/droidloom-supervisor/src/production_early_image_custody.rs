//! A read-only borrow of the early service's actual original base-image owner.
//! No receipt, PID, pathname, or external descriptor can create this capability.
use super::*;
use crate::control::application_custody::{CustodyNamespace, CustodyOwner};
use crate::production_mounts::custody::ObservedGalleryImage;

impl EarlyApplicationAuthority<'_> {
    pub(crate) fn runtime_vintf_binding(
        &self,
        held: &EarlyFrameworkObservation,
        deadline: Instant,
    ) -> Result<crate::control::runtime_vintf::RuntimeVintfBinding> {
        self.verify_framework_processes(held)?;
        let owner = self.image_custody_owner(deadline)?;
        let base_images = self
            .images
            .observe_vintf_mount_bindings_early(&self.base, deadline, self.progress)
            .map_err(external)?;
        let root = held.framework_metadata.root.metadata()?;
        let root_id = crate::control::application_custody::CustodyFileIdentity {
            device: root.dev(),
            inode: root.ino(),
            mode: root.mode(),
            uid: root.uid(),
            gid: root.gid(),
            links: root.nlink(),
            bytes: root.len(),
            modified: (root.mtime(), root.mtime_nsec()),
            changed: (root.ctime(), root.ctime_nsec()),
        };
        require(
            base_images.first().is_some_and(|image| {
                (image.mount_root.device, image.mount_root.inode) == (root.dev(), root.ino())
            }),
            "framework root is not the actual selected base filesystem",
        )?;
        let mut framework_namespaces = Vec::new();
        for (name, file) in ["user", "pid", "mount", "ipc", "uts", "net", "cgroup"]
            .into_iter()
            .zip(&held.framework_metadata.namespaces)
        {
            let node = file.metadata()?;
            framework_namespaces.push(CustodyNamespace {
                name: name.into(),
                device: node.dev(),
                inode: node.ino(),
            });
        }
        require(
            framework_namespaces.len() == 7,
            "incomplete framework namespace set",
        )?;
        framework_namespaces.sort_by(|a, b| a.name.cmp(&b.name));
        self.verify_framework_processes(held)?;
        require(
            self.image_custody_owner(deadline)? == owner,
            "VINTF owner changed",
        )?;
        Ok(crate::control::runtime_vintf::RuntimeVintfBinding {
            owner,
            framework_namespaces,
            framework_root: root_id,
            base_images,
            image_bodies_rehashed_by_this_observation: false,
        })
    }
    pub(super) fn image_custody_owner(&self, deadline: Instant) -> Result<CustodyOwner> {
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
            .observe_gallery_custody_early(&self.base, deadline, self.progress)
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
            .complete_gallery_byte_bookend_early(&self.base, observed, deadline, self.progress)
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
            .revalidate_gallery_custody_early(&self.base, observed, deadline)
            .map_err(external)?;
        require(
            &self.image_custody_owner(deadline)? == owner,
            "early image owner changed during final bookend",
        )
    }
}
