//! Hand the PID 1 owner one detached Android root after all four inputs are under its lease.
use super::*;
use crate::production_identity::IdentityLease;

/// Implementations live in this broker. Each borrows a kernel-backed, generation-specific authority.
pub(super) trait BaseAuthority {
    fn revalidate(&self) -> Result<()>;
    fn revalidate_live_admission(&self) -> Result<()>;
    fn identity_lease(&self) -> Result<&IdentityLease>;
    fn proc_directory(&self) -> &File;
    fn user_namespace(&self) -> &File;
}

impl BaseAuthority for OwnedNamespaceWitness<'_> {
    fn revalidate(&self) -> Result<()> { Ok(OwnedNamespaceWitness::revalidate(self)?) }
    fn revalidate_live_admission(&self) -> Result<()> { Ok(OwnedNamespaceWitness::revalidate_live_admission(self)?) }
    fn identity_lease(&self) -> Result<&IdentityLease> { Ok(OwnedNamespaceWitness::identity_lease(self)?) }
    fn proc_directory(&self) -> &File { OwnedNamespaceWitness::proc_directory(self) }
    fn user_namespace(&self) -> &File { OwnedNamespaceWitness::user_namespace(self) }
}


pub(super) fn attach_vendor(system: &File, vendor: &File) -> Result<()> {
    let directory = || open_leaf(system, &text_name("vendor")?, libc::O_RDONLY | libc::O_DIRECTORY);
    let target = directory()?;
    let root_id = require_detached(system)?;
    let vendor_id = require_detached(vendor)?;
    require(root_id != vendor_id && mount_id(&target)? == root_id
        && target.metadata()?.dev() == system.metadata()?.dev(),
        "original GSI vendor target must be on the selected system filesystem")?;
    zero_rc(unsafe { libc::syscall(libc::SYS_move_mount,
        vendor.as_raw_fd(), c"".as_ptr(), target.as_raw_fd(), c"".as_ptr(),
        libc::MOVE_MOUNT_F_EMPTY_PATH | libc::MOVE_MOUNT_T_EMPTY_PATH) as i32 })?;
    let attached = directory()?;
    require(mount_id(&attached)? == vendor_id && attached.metadata()?.dev() == vendor.metadata()?.dev()
        && attached.metadata()?.ino() == vendor.metadata()?.ino() && require_detached(system)? == root_id,
        "the selected vendor root must occupy the original GSI vendor directory")
}

impl PreparedMounts {
    /// Borrow the complete root once. The holder retains the reservation and all four loop owners
    /// until the ordinary retirement witness proves the physical child can no longer use them.
    fn complete_root_for_transfer<'a>(
        &'a mut self, witness: &impl BaseAuthority,
    ) -> Result<BorrowedFd<'a>> {
        let resources = self.resources.as_ref().ok_or(MountError::Rejected("retired early image set"))?;
        resources.cohort.revalidate(witness)?;
        self.validate_held_images(witness)?;
        require(resources.images.len() == 4 && resources.cohort.system_ext_readiness.is_some(),
            "an early root requires all four selected images")?;
        let root = resources.images[0].mount.as_ref().ok_or(MountError::Rejected("missing system root"))?;
        let vendor = resources.images[1].mount.as_ref().ok_or(MountError::Rejected("missing vendor root"))?;
        attach_vendor(root, vendor)?;
        resources.matches_witness(witness)?;
        self.exported = true;
        Ok(root.as_fd())
    }
}

use crate::production_selection::early_generation::{EarlyBaseAdmission, EarlyBaseRetirement};

impl BaseAuthority for EarlyBaseAdmission<'_> {
    fn revalidate(&self) -> Result<()> { Ok(EarlyBaseAdmission::revalidate(self)?) }
    fn revalidate_live_admission(&self) -> Result<()> { Ok(EarlyBaseAdmission::revalidate(self)?) }
    fn identity_lease(&self) -> Result<&IdentityLease> {
        EarlyBaseAdmission::revalidate(self)?;
        Ok(EarlyBaseAdmission::identity_lease(self))
    }
    fn proc_directory(&self) -> &File { EarlyBaseAdmission::proc_directory(self) }
    fn user_namespace(&self) -> &File { EarlyBaseAdmission::user_namespace(self) }
}

impl PreparedMounts {
    pub(crate) fn prepare_early(child: &EarlyBaseAdmission<'_>) -> Result<Self> {
        let cohort = VerifiedCohort::from_authority(child)?;
        require(cohort.system_ext_lib64.is_some() && cohort.system_ext_readiness.is_some(),
            "early original Android needs its complete four-image release")?;
        Self::prepare_with_authority(child, cohort)
    }

    pub(crate) fn early_root_for_transfer<'a>(&'a mut self, child: &EarlyBaseAdmission<'_>) -> Result<BorrowedFd<'a>> {
        self.complete_root_for_transfer(child)
    }

    pub(crate) fn retire_after_early_tree(mut self, retired: &EarlyBaseRetirement) -> Result<MountRetirement> {
        let resources = self.resources.as_ref().ok_or(MountError::Rejected("early base has retired"))?;
        retired.verify_mount_retirement(&resources.userns, resources.cohort.host_uid, &resources.cohort.cohort)?;
        self.cleanup(true)
    }
}
