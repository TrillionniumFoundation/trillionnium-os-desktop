//! The normal read-only successor of an actually completed first once.
//! It does not reopen the old live mutation authority and does not grant a
//! qualification boot, complete App acceptance or permanent publication.
use super::returned_history::ReturnedOnceHistory;
use crate::{Result, cold_original_data::ReturnedWorkingPair};
use serde_json::{Value, json};

pub(crate) struct ReturnedWorkingCopyObservation {
    history: ReturnedOnceHistory,
    data: ReturnedWorkingPair,
}
impl ReturnedWorkingCopyObservation {
    pub(crate) fn observe(candidate: &str) -> Result<Self> {
        let mut history = ReturnedOnceHistory::open(candidate)?;
        let data = ReturnedWorkingPair::open(&mut history)?;
        let value = Self { history, data };
        value.guard()?;
        Ok(value)
    }
    pub(crate) fn guard(&self) -> Result<()> {
        self.data.guard(&self.history)
    }
    pub(crate) fn summary(&self) -> Result<Value> {
        self.guard()?;
        Ok(
            json!({"schema":"droidloom.returned-working-copy-observation.v1",
            "history":self.history.summary(),"actual_pair":self.data.summary(),
            "observation_scope":"normal-return-history-and-current-retired-copy",
            "old_live_retirement_reconstructed":false,"source_receipts_rewritten":false,
            "qualification_boot_authorized":false,"complete_application_run_observed":false,
            "production_ready":false,"permanent_service_enabled":false}),
        )
    }
}
pub(crate) fn inspect(candidate: &str) -> Result<Value> {
    let observation = ReturnedWorkingCopyObservation::observe(candidate)?;
    let report = observation.summary()?;
    observation.guard()?;
    Ok(report)
}
