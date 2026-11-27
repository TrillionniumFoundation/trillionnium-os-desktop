//! Live normal Main plus one actual target package's working-copy directories.
//!
//! Only the source-owned normal inspector mints the two borrowed observations.
//! Saved JSON is comparison data. This component grants no UI, engine, account
//! content, application business or deployment qualification.
use crate::control::application_probe::{ApplicationInspection, RuntimeEpoch};
use crate::control::{
    ActualApplicationObservation, ActualUserZeroPackageInventoryObservation, ControlError,
    NativeApplicationInspector,
};
use crate::main_custody::{MainCustodyObservation, RuntimeMainCustody};
use crate::native_leaf_baseline_data::{HeldLeafData, LeafDataFacts};
use crate::native_leaf_baseline_programs::NormalHostPrograms;
use serde::Serialize;
use std::time::Instant;
use std::sync::Arc;
use crate::control::physical_qualification_channel::{WorkingNativeSourceCustody, WorkingQualificationOwner};

pub const SCHEMA: &str = "droidloom.native-leaf-baseline.v1";

fn before(end: Instant) -> Result<(), ControlError> {
    if Instant::now() >= end {
        Err(ControlError::Invalid(
            "original native leaf budget expired".into(),
        ))
    } else {
        Ok(())
    }
}

/// Serialize-only comparison projection borrowed from actual live observations.
#[derive(Serialize)]
pub struct NativeLeafBaselineFacts<'a> {
    pub schema: &'static str,
    pub application: &'a ApplicationInspection,
    pub main: &'a RuntimeMainCustody,
    pub data: &'a LeafDataFacts,
    pub peer: &'a crate::control::NativeInspectionPeer,
    pub comparison_only: bool,
    pub account_contents_read: bool,
    pub business_acceptance_evaluated: bool,
}

/// One row/pair's held target metadata. The original inspector remains outside
/// this borrow so its normal before/between/after operations can be reused.
/// No Clone, Deserialize, public fields or unchecked constructor exist.
pub struct NativeLeafBaselineObservation<'a> {
    main: &'a MainCustodyObservation,
    application: &'a ActualApplicationObservation,
    data: HeldLeafData,
    programs: NormalHostPrograms,
    deadline: Instant,
    full_bookend_after: Instant,
    inventory: Option<ActualUserZeroPackageInventoryObservation>,
    inventory_bookend: Option<ActualUserZeroPackageInventoryObservation>,
    working_source: Option<Arc<WorkingNativeSourceCustody>>,
    preparation_owner: Option<&'a WorkingQualificationOwner>,
}
impl<'a> NativeLeafBaselineObservation<'a> {
    /// Consume the caller's existing actual PM and Main observations. This
    /// captures fixed target metadata and issues no additional PM/Main RPC.
    pub fn capture_from_observed(
        inspector: &NativeApplicationInspector,
        main: &'a MainCustodyObservation,
        application: &'a ActualApplicationObservation,
        deadline: Instant,
    ) -> Result<Self, ControlError> {
        before(deadline)?;
        crate::native_leaf_baseline_data::package_paths(
            &application.facts().package,
            application.facts().user,
        )
        .map_err(|e| ControlError::Invalid(e.to_string()))?;
        inspector.require_observations_local(main, application, deadline)?;
        let programs = NormalHostPrograms::capture(main, deadline).map_err(|e| {
            ControlError::Invalid(format!("native leaf normal program custody: {e}"))
        })?;
        let data = HeldLeafData::capture(main.facts(), application.facts())
            .map_err(|e| ControlError::Invalid(format!("native leaf actual data metadata: {e}")))?;
        inspector.require_observations_local(main, application, deadline)?;
        data.verify()
            .map_err(|e| ControlError::Invalid(format!("native leaf data bookend: {e}")))?;
        before(deadline)?;
        Ok(Self {
            main,
            application,
            data,
            programs,
            deadline,
            full_bookend_after: Instant::now(),
            inventory: None,
            inventory_bookend: None,
            working_source: None,
            preparation_owner: None,
        })
    }
    pub fn facts(&self) -> NativeLeafBaselineFacts<'_> {
        NativeLeafBaselineFacts {
            schema: SCHEMA,
            application: self.application.facts(),
            main: self.main.facts(),
            data: self.data.facts(),
            peer: self.main.peer(),
            comparison_only: true,
            account_contents_read: false,
            business_acceptance_evaluated: false,
        }
    }
    pub fn application(&self) -> &ApplicationInspection {
        self.application.facts()
    }
    pub(crate) fn actual_application(&self) -> &ActualApplicationObservation {
        self.application
    }
    pub fn main(&self) -> &MainCustodyObservation {
        self.main
    }
    pub fn deadline(&self) -> Instant {
        self.deadline
    }
    /// Attach only the actual authenticated working owner. Saved comparison
    /// facts cannot create this value or renew the existing case deadline.
    pub fn attach_working_source(
        &mut self, source: &Arc<WorkingNativeSourceCustody>,
    ) -> Result<(), ControlError> {
        before(self.deadline)?;
        if self.working_source.is_some() || self.preparation_owner.is_some() || self.deadline > source.deadline() {
            return Err(ControlError::Invalid("working source already attached or original end extended".into()));
        }
        source.guard().map_err(|e| ControlError::Invalid(e.to_string()))?;
        self.working_source = Some(Arc::clone(source));
        Ok(())
    }
    /// Preparation borrows the real fixed parent before the suite child exists.
    /// Its source capture budget is the same original PID1-derived allowance.
    pub fn attach_preparation_owner(
        &mut self, owner: &'a WorkingQualificationOwner,
    ) -> Result<(), ControlError> {
        before(self.deadline)?;
        if self.preparation_owner.is_some() || self.working_source.is_some()
            || self.deadline > owner.preparation_deadline()
        {
            return Err(ControlError::Invalid("preparation owner already attached or deadline extended".into()));
        }
        owner.guard().map_err(ControlError::Invalid)?;
        self.preparation_owner = Some(owner);
        Ok(())
    }
    pub(crate) fn preparation_owner(&self) -> Option<&WorkingQualificationOwner> {
        self.preparation_owner
    }
    pub(crate) fn working_source_comparison(&self) -> Result<Option<serde_json::Value>, ControlError> {
        self.working_source.as_ref().map(|source| {
            source.guard().map_err(|e| ControlError::Invalid(e.to_string()))?;
            source.comparison().map_err(|e| ControlError::Invalid(e.to_string()))
        }).transpose()
    }

    /// Attach the fixed complete user-0 observation for IHG's original helper
    /// UID collision precondition. Target CE/DE directory custody is unchanged.
    pub fn attach_user_zero_inventory(
        &mut self,
        inspector: &NativeApplicationInspector,
        inventory: ActualUserZeroPackageInventoryObservation,
    ) -> Result<(), ControlError> {
        self.verify_local(inspector, self.deadline)?;
        if self.application.facts().package != "com.ihg.apps.android"
            || self.inventory.is_some()
            || inventory.observed_at() <= self.full_bookend_after
        {
            return Err(ControlError::Invalid(
                "fresh complete IHG inventory is required exactly once".into(),
            ));
        }
        inspector.require_inventory_local(
            self.main,
            self.application,
            &inventory,
            self.deadline,
        )?;
        self.inventory = Some(inventory);
        self.inventory_bookend = None;
        Ok(())
    }
    pub fn inventory_facts(
        &self,
    ) -> Option<&crate::package_inventory_observation::UserZeroPackageInventoryFacts> {
        self.inventory.as_ref().map(|i| i.facts())
    }
    pub fn requires_inventory_bookend(&self) -> bool {
        self.inventory.is_some()
    }
    /// Reuse one actual post query. No receipt or caller map can create it.
    /// Ordinary leaf execution must preserve the entire original table.
    pub fn record_inventory_bookend(
        &mut self,
        inspector: &NativeApplicationInspector,
        after: ActualUserZeroPackageInventoryObservation,
        until: Instant,
    ) -> Result<(), ControlError> {
        let end = until.min(self.deadline);
        self.verify_local(inspector, end)?;
        inspector.require_inventory_local(self.main, self.application, &after, end)?;
        let before = self.inventory.as_ref().ok_or_else(|| {
            ControlError::Invalid(
                "complete inventory was not observed before the invocation".into(),
            )
        })?;
        if after.observed_at() <= self.full_bookend_after
            || !before.facts().same_table(after.facts())
        {
            return Err(ControlError::Invalid(
                "complete user-0 table changed or post observation is stale".into(),
            ));
        }
        self.inventory_bookend = Some(after);
        Ok(())
    }

    /// The one source-owned IHG preparation factory calls this only after its
    /// actual fixed child, thirteen original commands, signed APK equality and
    /// fresh helper PM prove the exact singleton installation difference.
    pub(crate) fn record_fixed_ihg_install_bookend(
        &mut self,
        inspector: &NativeApplicationInspector,
        after: ActualUserZeroPackageInventoryObservation,
        until: Instant,
    ) -> Result<(), ControlError> {
        let end = until.min(self.deadline);
        self.verify_local(inspector, end)?;
        inspector.require_inventory_local(self.main, self.application, &after, end)?;
        if self.application.facts().package != crate::native_ihg_preparation::TARGET
            || self.inventory.is_none()
            || after.observed_at() <= self.full_bookend_after
        {
            return Err(ControlError::Invalid(
                "fixed IHG installation lacks a fresh actual post inventory".into(),
            ));
        }
        self.inventory_bookend = Some(after);
        Ok(())
    }

    /// G is local custody, not a new full Main/PM observation: all held/named
    /// proc, PIDFD, namespaces, mappings and target directories are checked, as
    /// are the normal peer and the two original opaque tokens. No RPC is sent.
    pub fn verify_local(
        &self,
        inspector: &NativeApplicationInspector,
        until: Instant,
    ) -> Result<(), ControlError> {
        let end = until.min(self.deadline);
        before(end)?;
        if let Some(source) = &self.working_source {
            source.guard().map_err(|e| ControlError::Invalid(e.to_string()))?;
        }
        if let Some(owner) = self.preparation_owner {
            owner.guard().map_err(ControlError::Invalid)?;
        }
        inspector.require_observations_local(self.main, self.application, end)?;
        for inventory in [&self.inventory, &self.inventory_bookend]
            .into_iter()
            .flatten()
        {
            inspector.require_inventory_local(self.main, self.application, inventory, end)?;
        }
        self.programs
            .verify(end)
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        self.data
            .verify()
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        inspector.require_observations_local(self.main, self.application, end)?;
        before(end)
    }

    /// Use the already-required actual post/between PM and full Main results.
    /// Both tokens must be newly observed after this context's last complete
    /// bookend. Saved JSON and a reused pre-leaf token cannot satisfy this gate.
    /// This method itself sends no RPC and does not renew the original lease.
    pub fn finish_from_observed(
        &mut self,
        inspector: &NativeApplicationInspector,
        after_main: &MainCustodyObservation,
        after_application: &ActualApplicationObservation,
        until: Instant,
    ) -> Result<(), ControlError> {
        let end = until.min(self.deadline);
        self.verify_local(inspector, end)?;
        inspector.require_observations_local(after_main, after_application, end)?;
        if self.inventory.is_some()
            && self
                .inventory_bookend
                .as_ref()
                .is_none_or(|i| i.observed_at() <= self.full_bookend_after)
        {
            return Err(ControlError::Invalid(
                "complete IHG user-0 inventory lacks a fresh actual post query".into(),
            ));
        }
        require_new_bookend(
            self.full_bookend_after,
            after_main.observed_at(),
            after_application.observed_at(),
        )?;
        if after_main.facts() != self.main.facts()
            || after_main.peer() != self.main.peer()
            || after_application.facts() != self.application.facts()
            || after_application.peer() != self.application.peer()
        {
            return Err(ControlError::Invalid(
                "actual Main or complete installed identity changed across native leaf".into(),
            ));
        }
        self.verify_local(inspector, end)?;
        self.programs
            .verify_contents(end)
            .map_err(|e| ControlError::Invalid(e.to_string()))?;
        self.verify_local(inspector, end)?;
        self.full_bookend_after = Instant::now();
        Ok(())
    }
    pub(crate) fn require_epoch(&self, epoch: &RuntimeEpoch) -> Result<(), String> {
        if &self.application.facts().epoch == epoch {
            Ok(())
        } else {
            Err("native leaf baseline belongs to another actual Main epoch".into())
        }
    }
    /// Comparison only, after the live factory exists. No document selects an
    /// owner, process, UID, mount or metadata path for this factory.
    pub fn compare(&self, value: &serde_json::Value) -> Result<(), ControlError> {
        if serde_json::to_value(self.facts())? != *value {
            Err(ControlError::Invalid(
                "saved native leaf facts differ from the live owner".into(),
            ))
        } else {
            Ok(())
        }
    }
}
fn require_new_bookend(
    previous: Instant,
    main: Instant,
    application: Instant,
) -> Result<(), ControlError> {
    if main <= previous || application <= previous {
        Err(ControlError::Invalid(
            "native leaf final observations predate its held context".into(),
        ))
    } else {
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    #[test]
    fn native_leaf_bookend_cannot_reuse_earlier_or_between_tokens() {
        let before = Instant::now();
        let after = before + Duration::from_millis(1);
        let latest = after + Duration::from_millis(1);
        require_new_bookend(before, after, after).unwrap();
        assert!(require_new_bookend(before, before, after).is_err());
        assert!(require_new_bookend(before, after, before).is_err());
        assert!(require_new_bookend(after, after, latest).is_err());
        require_new_bookend(after, latest, latest).unwrap();
    }
}
