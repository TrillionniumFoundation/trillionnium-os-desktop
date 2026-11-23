//! Admit the original data pair only while the exact early generation is under the selected manager.
use super::*;
use crate::production_cgroup::PreparedCgroup;
use crate::production_execution::RuntimeMacOwner;
use crate::production_mac::MacSystemdWitness;
use crate::production_selection::early_generation::{EarlyBaseAdmission, EarlyBaseRetirement};

pub(crate) struct EarlyStorageAdmission<'a, 'generation> {
    child: &'a EarlyBaseAdmission<'generation>,
    group: &'a PreparedCgroup,
    mac: &'a RuntimeMacOwner,
    manager: MacSystemdWitness,
}

impl<'a, 'generation> EarlyStorageAdmission<'a, 'generation> {
    pub(crate) fn acquire(
        child: &'a EarlyBaseAdmission<'generation>, group: &'a PreparedCgroup,
        mac: &'a RuntimeMacOwner,
    ) -> Result<Self> {
        child.revalidate()?;
        group.revalidate_early_member(child, mac).map_err(io::Error::other)?;
        let (runtime, selection) = mac.objects()?;
        let systemd = group.systemd_owner(selection).map_err(io::Error::other)?;
        let manager = runtime.observe_systemd_owner(&systemd).map_err(io::Error::other)?;
        let admission = Self { child, group, mac, manager };
        admission.revalidate_persistent(selection)?;
        Ok(admission)
    }

    pub(crate) fn revalidate_persistent(&self, selection: &ProductionSelection) -> Result<()> {
        self.child.revalidate()?;
        let (mac, _) = self.mac.objects()?;
        self.mac.require_pair(mac, selection)?;
        self.group.revalidate_early_member(self.child, self.mac).map_err(io::Error::other)?;
        let owner = self.group.systemd_owner(selection).map_err(io::Error::other)?;
        self.manager.revalidate(mac, &owner).map_err(io::Error::other)?;
        require(self.child.identity_lease().host_uid() == selection.spec().host_uid
            && self.child.identity_lease().broker_cohort() == selection.base_cohort(),
            "the original selected data pair must belong to the same live early Android generation")?;
        self.child.revalidate()?;
        Ok(())
    }
}

impl<'generation> StorageAuthority for EarlyStorageAdmission<'_, 'generation> {
    type Namespace = EarlyBaseAdmission<'generation>;
    fn namespace(&self) -> &Self::Namespace { self.child }
    fn selection(&self) -> &ProductionSelection { self.mac.selection() }
    fn verify(&self) -> Result<()> { self.revalidate_persistent(self.mac.selection()) }
}

impl PreparedPersistentData {
    pub(crate) fn prepare_early(admission: &EarlyStorageAdmission<'_, '_>) -> Result<Self> {
        Self::prepare_with(admission)
    }

    pub(crate) fn early_descriptors_for_transfer<'a>(
        &'a mut self, admission: &EarlyStorageAdmission<'_, '_>,
    ) -> Result<([BorrowedFd<'a>; 2], [PersistentRootObservation; 2])> {
        self.transfer_with(admission)
    }

    pub(crate) fn revalidate_early_lifetime(&self, admission: &EarlyStorageAdmission<'_, '_>) -> Result<()> {
        admission.verify()?;
        self.revalidate_lifetime(admission.child)?;
        admission.verify()
    }

    pub(crate) fn retire_after_early_tree(mut self, retired: &EarlyBaseRetirement) -> Result<PersistentDataRetirement> {
        let resources = self.resources.as_ref().ok_or(MountError::Rejected("early persistent data has retired"))?;
        retired.verify_mount_retirement(&resources.userns, resources.host_uid, &resources.cohort)?;
        self.cleanup(true)
    }
}
