//! Both creation routes retain their original generation and the exact mapped user namespace.
use super::*;
use crate::production_identity::IdentityLease;
use crate::production_selection::early_generation::{EarlyBaseAdmission, EarlyBaseRetirement};

pub(super) trait DeviceTree {
    fn revalidate(&self) -> Result<()>;
    fn identity_lease(&self) -> Result<&IdentityLease>;
    fn proc_directory(&self) -> &File;
    fn user_namespace(&self) -> &File;
    fn descendant_pid_namespace(&self) -> Option<&File>;
}

impl DeviceTree for OwnedNamespaceWitness<'_> {
    fn revalidate(&self) -> Result<()> { Ok(OwnedNamespaceWitness::revalidate(self)?) }
    fn identity_lease(&self) -> Result<&IdentityLease> { Ok(OwnedNamespaceWitness::identity_lease(self)?) }
    fn proc_directory(&self) -> &File { OwnedNamespaceWitness::proc_directory(self) }
    fn user_namespace(&self) -> &File { OwnedNamespaceWitness::user_namespace(self) }
    fn descendant_pid_namespace(&self) -> Option<&File> { OwnedNamespaceWitness::descendant_pid_namespace(self) }
}

impl DeviceTree for EarlyBaseAdmission<'_> {
    fn revalidate(&self) -> Result<()> { Ok(EarlyBaseAdmission::revalidate(self)?) }
    fn identity_lease(&self) -> Result<&IdentityLease> {
        EarlyBaseAdmission::revalidate(self)?;
        Ok(EarlyBaseAdmission::identity_lease(self))
    }
    fn proc_directory(&self) -> &File { EarlyBaseAdmission::proc_directory(self) }
    fn user_namespace(&self) -> &File { EarlyBaseAdmission::user_namespace(self) }
    fn descendant_pid_namespace(&self) -> Option<&File> { Some(self.board().pid_namespace()) }
}

impl PreparedDevices {
    pub(crate) fn prepare_early(child: &EarlyBaseAdmission<'_>) -> Result<Self> {
        child.revalidate()?;
        let devices = Self::create_for_tree(child, None)?;
        child.revalidate()?;
        Ok(devices)
    }

    pub(crate) fn early_descriptor_for_transfer<'a>(&'a mut self, child: &EarlyBaseAdmission<'_>) -> Result<BorrowedFd<'a>> {
        require_initial_broker()?;
        child.revalidate()?;
        self.descriptor_after_admission(child)
    }

    pub(crate) fn retire_after_early_tree(mut self, retired: &EarlyBaseRetirement) -> Result<DeviceRetirement> {
        let r = self.resources.as_ref().ok_or(DeviceError::Rejected("early private device owner was retired"))?;
        retired.verify_mount_retirement(&r.userns, r.host_uid, &r.cohort)?;
        self.cleanup(true)
    }
}
