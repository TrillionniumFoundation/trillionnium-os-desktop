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
    pub(super) fn fresh_working_return_owner(&self) -> Result<super::WorkingReturnOwner> {
        self.returned
            .try_borrow()
            .map_err(|_| "working prior owner is already borrowed")?
            .history()
            .fresh_working_return_owner()
    }
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
    fn guard_pair_label_custody(&self) -> Result<()> {
        let returned = self
            .returned
            .try_borrow()
            .map_err(|_| "working Returned observation is already borrowed")?;
        let pair = self
            .pair
            .try_borrow()
            .map_err(|_| "working pair mutation is already in progress")?;
        match pair.as_ref() {
            Some(pair) => returned.guard_pair_label_custody(pair),
            None => Err("working label window lacks the actual exchanged pair".into()),
        }
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
    pub(super) fn revalidate_label_custody(&self) -> Result<()> {
        self.guard_pair_label_custody()?;
        self.materials.revalidate_label_custody()?;
        self.boot.revalidate_label_custody()?;
        self.guard_pair_label_custody()
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
    pub(super) fn prepare_selection(
        &self,
        labels: &crate::cold_original_data::labels::WorkingLabelsApplied,
    ) -> Result<crate::cold_original_data::WorkingSelectionTransaction> {
        self.revalidate()?;
        self.returned
            .try_borrow()
            .map_err(|_| "working returned source already borrowed")?
            .prepare_selection(
                self.pair
                    .try_borrow()
                    .map_err(|_| "working pair already borrowed")?
                    .as_ref()
                    .ok_or("working pair missing")?,
                labels,
            )
    }
    pub(super) fn accept_selection(
        &self,
        proof: std::rc::Rc<crate::cold_original_data::WorkingSelectionProof>,
    ) -> Result<()> {
        let returned = self
            .returned
            .try_borrow()
            .map_err(|_| "working returned source already borrowed")?;
        let mut pair = self
            .pair
            .try_borrow_mut()
            .map_err(|_| "working pair already borrowed")?;
        returned.accept_selection(pair.as_mut().ok_or("working pair missing")?, proof)
    }
    pub(super) fn revalidate_selection_owner(&self) -> Result<()> {
        self.returned
            .try_borrow()
            .map_err(|_| "working returned source already borrowed")?
            .history()
            .guard_working_label_custody()
    }
    pub(super) fn prepare_working_label_custody(&self) -> Result<()> {
        self.revalidate()?;
        {
            let returned = self
                .returned
                .try_borrow()
                .map_err(|_| "working returned source is already borrowed")?;
            let mut pair = self
                .pair
                .try_borrow_mut()
                .map_err(|_| "working pair is already being changed")?;
            returned.begin_pair_label_custody(
                pair.as_mut().ok_or("working pair has not been exchanged")?,
            )?;
        }
        self.revalidate()
    }
    pub(super) fn working_label_targets(&self) -> Result<Vec<(std::path::PathBuf, std::fs::File)>> {
        self.revalidate()?;
        let returned = self
            .returned
            .try_borrow()
            .map_err(|_| "working returned source is already borrowed")?;
        let pair = self
            .pair
            .try_borrow()
            .map_err(|_| "working pair is already being changed")?;
        returned.pair_label_targets(pair.as_ref().ok_or("working pair has not been exchanged")?)
    }
    pub(super) fn accept_working_label_custody(
        &self,
        batch: &crate::cold_original_data::labels::WorkingLabelBatch,
    ) -> Result<()> {
        let mut returned = self
            .returned
            .try_borrow_mut()
            .map_err(|_| "working returned source is already borrowed")?;
        let mut pair = self
            .pair
            .try_borrow_mut()
            .map_err(|_| "working pair is already being changed")?;
        returned.accept_working_owner_labels(batch)?;
        returned.accept_pair_label_batch(
            pair.as_mut()
                .ok_or("working label batch has no exchanged pair")?,
            batch,
        )?;
        self.materials.accept_label_batch(batch)?;
        // GRUB and publication checkpoints are advanced by this same batch
        // before the dispatcher invokes the full source guard.
        Ok(())
    }

    pub(super) fn current_owner_evidence(&self) -> Result<serde_json::Value> {
        self.revalidate()?;
        let evidence = self
            .returned
            .try_borrow()
            .map_err(|_| "working returned owner is already borrowed")?
            .history()
            .current_owner_evidence();
        self.revalidate()?;
        Ok(evidence)
    }
    pub(super) fn retained_cold_clone(&self) -> Result<crate::boot_files::FilePin> {
        self.revalidate()?;
        let pin = self
            .returned
            .try_borrow()
            .map_err(|_| "working returned source is already borrowed")?
            .history()
            .retained_cold_clone()?;
        self.revalidate()?;
        Ok(pin)
    }
    pub(super) fn materials(&self) -> &WorkingMaterialSources {
        &self.materials
    }
    pub(super) fn boot(&self) -> &WorkingBootSources {
        &self.boot
    }
}
