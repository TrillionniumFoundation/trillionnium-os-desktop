//! Live normal Main plus one actual target package's working-copy directories.
//!
//! Only the source-owned normal inspector mints the two borrowed observations.
//! Saved JSON is comparison data. This component grants no UI, engine, account
//! content, application business or deployment qualification.
use crate::control::application_probe::{ApplicationInspection, RuntimeEpoch};
use crate::control::{ActualApplicationObservation, ControlError, NativeApplicationInspector};
use crate::main_custody::{MainCustodyObservation, RuntimeMainCustody};
use crate::native_leaf_baseline_data::{HeldLeafData, LeafDataFacts};
use serde::Serialize;
use std::time::Instant;

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
    deadline: Instant,
    full_bookend_after: Instant,
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
            deadline,
            full_bookend_after: Instant::now(),
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
    pub fn main(&self) -> &MainCustodyObservation {
        self.main
    }
    pub fn deadline(&self) -> Instant {
        self.deadline
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
        inspector.require_observations_local(self.main, self.application, end)?;
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
