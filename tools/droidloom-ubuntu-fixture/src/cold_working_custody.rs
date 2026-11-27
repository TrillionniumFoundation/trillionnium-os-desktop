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
    pair: RefCell<Option<crate::cold_original_data::WorkingPairTransaction>>,
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
            pair: RefCell::new(None),
        };
        value.revalidate()?;
        Ok(value)
    }
    fn guard_pair(&self) -> Result<()> {
        let returned = self
            .returned
            .try_borrow()
            .map_err(|_| "working Returned observation is already borrowed")?;
        let pair = self
            .pair
            .try_borrow()
            .map_err(|_| "working pair mutation is already in progress")?;
        match pair.as_ref() {
            Some(pair) => returned.guard_pair(pair),
            None => returned.guard(),
        }
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.guard_pair()?;
        self.materials.revalidate()?;
        self.boot.revalidate()?;
        self.guard_pair()
    }
    pub(super) fn advance_pair(&self, published: &super::PublishedWorkingRuntime) -> Result<()> {
        self.revalidate()?;
        let needed = self
            .pair
            .try_borrow()
            .map_err(|_| "working pair mutation is already in progress")?
            .is_none();
        if needed {
            // The actual factory calls Published.guard. No mutable RefCell
            // borrow is held across that recursive read-only source guard.
            let pair = self
                .returned
                .try_borrow()
                .map_err(|_| "working Returned observation is already borrowed")?
                .prepare_pair(published)?;
            let mut slot = self
                .pair
                .try_borrow_mut()
                .map_err(|_| "working pair mutation is already in progress")?;
            ensure(slot.is_none(), "a working pair transaction already exists")?;
            *slot = Some(pair);
        }
        self.revalidate()?;
        let result = {
            let returned = self
                .returned
                .try_borrow()
                .map_err(|_| "working Returned observation is already borrowed")?;
            let mut slot = self
                .pair
                .try_borrow_mut()
                .map_err(|_| "working pair mutation is already in progress")?;
            returned.advance_pair(slot.as_mut().ok_or("working pair transaction absent")?)
        };
        // The transaction and original four OFDs remain owned even on error.
        result?;
        self.revalidate()
    }
    pub(super) fn pair_exchanged(&self) -> Result<bool> {
        self.revalidate()?;
        let returned = self
            .returned
            .try_borrow()
            .map_err(|_| "working Returned observation is already borrowed")?;
        let pair = self
            .pair
            .try_borrow()
            .map_err(|_| "working pair mutation is already in progress")?;
        match pair.as_ref() {
            Some(pair) => returned.pair_exchanged(pair),
            None => Ok(false),
        }
    }
    pub(super) fn restore_pair_cold(&self) -> Result<()> {
        self.revalidate()?;
        let result = {
            let returned = self
                .returned
                .try_borrow()
                .map_err(|_| "working Returned observation is already borrowed")?;
            let mut slot = self
                .pair
                .try_borrow_mut()
                .map_err(|_| "working pair mutation is already in progress")?;
            match slot.as_mut() {
                Some(pair) => returned.restore_pair_cold(pair),
                None => Ok(()),
            }
        };
        result?;
        self.revalidate()
    }
    pub(super) fn materials(&self) -> &WorkingMaterialSources {
        &self.materials
    }
    pub(super) fn boot(&self) -> &WorkingBootSources {
        &self.boot
    }
}
