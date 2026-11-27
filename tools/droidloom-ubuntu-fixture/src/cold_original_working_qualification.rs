//! The normal read-only successor of an actually completed first once.
//! It does not reopen the old live mutation authority and does not grant a
//! qualification boot, complete App acceptance or permanent publication.
use super::returned_history::ReturnedOnceHistory;
use crate::{
    Result,
    boot_files::FilePin,
    boot_runtime::LabelTools,
    cold_original_data::{PreparedReturnedPair, ReturnedWorkingPair, labels::OriginalLabelSources},
};
use serde_json::{Value, json};
use std::{fs::File, path::Path};

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
    pub(super) fn observe_working(
        candidate: &str,
        working_candidate: &str,
        input: &FilePin,
    ) -> Result<Self> {
        let mut history = ReturnedOnceHistory::open_working(candidate, working_candidate, input)?;
        let data = ReturnedWorkingPair::open(&mut history)?;
        let value = Self { history, data };
        value.guard()?;
        Ok(value)
    }
    pub(super) fn history(&self) -> &ReturnedOnceHistory {
        &self.history
    }
    pub(super) fn prepare_normal_sources(
        self,
        candidate: &str,
        prepared: &FilePin,
        tools: &LabelTools,
    ) -> Result<(PreparedWorkingCopyObservation, OriginalLabelSources)> {
        self.guard()?;
        let (data, sources) =
            self.data
                .prepare_normal_sources(&self.history, candidate, prepared, tools)?;
        let value = PreparedWorkingCopyObservation {
            history: self.history,
            data,
        };
        value.guard()?;
        Ok((value, sources))
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

/// This consumes the cold Returned observation; it cannot be used to reopen the
/// old live retirement authority or as a live-runtime parent metadata guard.
pub(super) struct PreparedWorkingCopyObservation {
    history: ReturnedOnceHistory,
    data: PreparedReturnedPair,
}
impl PreparedWorkingCopyObservation {
    pub(super) fn recovery_directory(&self, candidate: &str) -> Result<std::path::PathBuf> {
        self.guard()?;
        self.data.recovery_directory(candidate)
    }
    pub(super) fn prepare_recovery(&mut self, candidate: &str, input: &FilePin) -> Result<FilePin> {
        self.guard()?;
        let receipt = self
            .data
            .prepare_recovery(&self.history, candidate, input)?;
        self.guard()?;
        Ok(receipt)
    }
    pub(super) fn guard(&self) -> Result<()> {
        self.data.guard(&self.history)
    }
    pub(super) fn history(&self) -> &ReturnedOnceHistory {
        &self.history
    }
    pub(super) fn work(&self) -> &Path {
        self.data.work()
    }
    pub(super) fn work_file(&self) -> &File {
        self.data.work_file()
    }
    pub(super) fn summary(&self) -> Result<Value> {
        self.guard()?;
        Ok(
            json!({"schema":"droidloom.working-qualification-cold-custody.v1",
            "history":self.history.summary(),"actual_pair":self.data.summary(),
            "old_live_retirement_reconstructed":false,"boot_armed":false,
            "private_images_written":false,"runtime_parent_freeze":false}),
        )
    }
}
