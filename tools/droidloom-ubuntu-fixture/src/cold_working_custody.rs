//! Linear source custody for the new working qualification. The historical
//! Returned observer and all four existing image OFDs remain owned here.
use super::{
    working_boot::WorkingBootSources, working_materials::WorkingMaterialSources,
    working_qualification::PreparedWorkingCopyObservation,
};
use crate::{Result, ensure};
use std::cell::RefCell;

pub(super) struct WorkingColdCustody {
    materials: WorkingMaterialSources,
    boot: WorkingBootSources,
    returned: RefCell<PreparedWorkingCopyObservation>,
}
impl WorkingColdCustody {
    pub(super) fn new(
        materials: WorkingMaterialSources,
        boot: WorkingBootSources,
        returned: PreparedWorkingCopyObservation,
    ) -> Result<Self> {
        materials.revalidate()?;
        boot.revalidate()?;
        returned.guard()?;
        ensure(
            materials.work() == returned.work()
                && materials.candidate() == boot.recovery().candidate_id,
            "working source projection changed its actual owner workspace or candidate",
        )?;
        let value = Self {
            materials,
            boot,
            returned: RefCell::new(returned),
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.returned
            .try_borrow()
            .map_err(|_| "working pair mutation is already in progress")?
            .guard()?;
        self.materials.revalidate()?;
        self.boot.revalidate()?;
        self.returned
            .try_borrow()
            .map_err(|_| "working pair mutation is already in progress")?
            .guard()
    }
    pub(super) fn materials(&self) -> &WorkingMaterialSources {
        &self.materials
    }
    pub(super) fn boot(&self) -> &WorkingBootSources {
        &self.boot
    }
}
