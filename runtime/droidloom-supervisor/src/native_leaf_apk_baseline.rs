//! Actual original APK custody attached to the existing native leaf context.
//! G remains its existing local Main/data guard. Explicit APK requests consume
//! the one source-owned subject; completed records preserve only that interval.
use super::*;
use crate::control::{FinishedNativeLeafApkCustody, NativeLeafApkCopy, NativeLeafApkCustody};
use std::cell::RefCell;
use std::time::Duration;
use crate::production_application::apk_scope::{Scope, NativeLeafApkRoute, NativeLeafPreparationRole};

struct CompletedInterval {
    custody: FinishedNativeLeafApkCustody,
    // Preparation uses the same primary baseline, while this original opaque
    // token proves the separately selected fixed role. It is never cloned.
    role_application: Option<ActualApplicationObservation>,
}
#[derive(Default)]
pub(super) struct ApkState {
    owner: Option<NativeLeafApkCustody>,
    role_application: Option<ActualApplicationObservation>,
    finished: Vec<CompletedInterval>,
    history_taken: bool,
    failure: Option<String>,
}
impl ApkState {
    fn remember(&mut self, error: &ControlError) {
        if self.failure.is_none() { self.failure = Some(error.to_string()); }
        // Disconnect asks the original broker to retire its real child. It is
        // not, by itself, a statement that retirement was successful.
        self.owner.take();
    }
    fn ready(&self) -> Result<(), ControlError> {
        if let Some(error) = &self.failure {
            return Err(ControlError::Invalid(format!("original APK custody first failure: {error}")));
        }
        if self.history_taken {
            return Err(ControlError::Invalid("APK history was already consumed".into()));
        }
        Ok(())
    }
}
pub(super) fn empty() -> RefCell<ApkState> { RefCell::new(ApkState::default()) }

/// Output-only history of the actual source-owned reader intervals. All
/// original APK descriptors have already been closed by the real reaped
/// reader. This value cannot start another reader or renew a deadline.
pub struct NativeLeafApkHistory {
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    intervals: Vec<CompletedInterval>,
}
impl std::fmt::Debug for NativeLeafApkHistory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("NativeLeafApkHistory")
            .field("package", &self.application.package)
            .field("intervals", &self.intervals.len()).finish_non_exhaustive()
    }
}
impl NativeLeafApkHistory {
    fn verify(&self) -> Result<(), ControlError> {
        if !(1..=2).contains(&self.intervals.len()) {
            return Err(ControlError::Invalid("APK history has no complete bounded interval".into()));
        }
        for interval in &self.intervals {
            let application = interval.role_application.as_ref().map_or(
                &self.application, |actual| actual.facts());
            interval.custody.require_immutable_subject(&self.main, application)?;
        }
        Ok(())
    }
    pub fn require_subject(&self, main: &RuntimeMainCustody, application: &ApplicationInspection,
        route: NativeLeafApkRoute, intervals: usize) -> Result<(), ControlError>
    {
        self.verify()?;
        if &self.main != main || &self.application != application
            || self.intervals.len() != intervals || !(1..=2).contains(&intervals)
            || (intervals == 2 && route != NativeLeafApkRoute::ClockPair)
            || self.intervals.iter().any(|interval| interval.role_application.is_some()
                || interval.custody.scope() != (Scope::Business { route }))
        {
            return Err(ControlError::Invalid("APK history differs from the actual whole business subject".into()));
        }
        Ok(())
    }
    pub fn require_preparation_subject(&self, main: &RuntimeMainCustody,
        application: &ApplicationInspection, role: NativeLeafPreparationRole) -> Result<(), ControlError>
    {
        self.verify()?;
        if &self.main != main || &self.application != application || self.intervals.len() != 1
            || self.intervals[0].role_application.as_ref().is_none_or(|actual|
                actual.facts().package != role.package())
            || self.intervals[0].custody.scope() != Scope::preparation(role)
        {
            return Err(ControlError::Invalid("APK history differs from its actual fixed preparation role".into()));
        }
        Ok(())
    }
    pub fn comparison(&self) -> Result<serde_json::Value, ControlError> {
        self.verify()?;
        Ok(serde_json::json!({"schema":"droidloom.native-leaf-apk-history.v1",
            "main":self.main, "primary_application":self.application,
            "intervals":self.intervals.iter().map(|v|v.custody.comparison()).collect::<Vec<_>>(),
            "all_original_readers_retired":true, "comparison_only":true,
            "continuous_original_custody_after_retirement":false, "business_accepted":false}))
    }
}
impl NativeLeafBaselineObservation<'_> {
    /// Normal Rust fixes the whole original role group before business.
    pub fn capture_apks_until(&self, inspector: &NativeApplicationInspector,
        route: NativeLeafApkRoute, end: Instant) -> Result<(), ControlError>
    {
        self.capture_apk_scope_until(inspector, Scope::Business { route }, None, end)
    }
    /// Keep the original primary baseline/QUAL while consuming the real PM
    /// token for one fixed identity role. No role is represented by primary PM.
    pub fn capture_preparation_apks_until(&self, inspector: &NativeApplicationInspector,
        role: NativeLeafPreparationRole, actual_role_pm: ActualApplicationObservation, end: Instant)
        -> Result<(), ControlError>
    {
        if role.case().package() != self.application.facts().package
            || actual_role_pm.facts().package != role.package()
        {
            return Err(ControlError::Invalid("preparation role differs from its primary case or actual PM".into()));
        }
        self.capture_apk_scope_until(inspector, Scope::preparation(role), Some(actual_role_pm), end)
    }
    fn capture_apk_scope_until(&self, inspector: &NativeApplicationInspector, scope: Scope,
        role_application: Option<ActualApplicationObservation>, end: Instant) -> Result<(), ControlError>
    {
        scope.validate().map_err(ControlError::Invalid)?;
        let actual = role_application.as_ref().unwrap_or(self.application);
        if actual.facts().package != scope.subject_package()
            || scope.is_preparation() != role_application.is_some()
        {
            return Err(ControlError::Invalid("APK scope differs from the actually borrowed role".into()));
        }
        let request_end = end.min(self.deadline).min(Instant::now() + scope.begin_cap());
        self.verify_local(inspector, request_end)?;
        inspector.require_observations_local(self.main, actual, request_end)?;
        let mut state = self.apk.borrow_mut(); state.ready()?;
        if state.owner.is_some() || state.role_application.is_some()
            || state.finished.len() >= if scope == (Scope::Business { route: NativeLeafApkRoute::ClockPair }) { 2 } else { 1 }
            || state.finished.iter().any(|prior| prior.custody.scope() != scope)
        {
            return Err(ControlError::Invalid("original APK interval is already captured or belongs to another scope".into()));
        }
        let result = inspector.begin_native_leaf_apk_until(
            self.main, actual, scope, self.deadline, request_end);
        match result {
            Ok(owner) => { state.owner = Some(owner); state.role_application = role_application; Ok(()) }
            Err(error) => { state.remember(&error); Err(error) }
        }
    }
    pub(crate) fn has_apk_scope(&self) -> bool {
        let state=self.apk.borrow();
        state.owner.is_some() || state.role_application.is_some() || !state.finished.is_empty()
            || state.failure.is_some() || state.history_taken
    }
    /// Resolve from the actual retained business reader. Python cannot submit
    /// a fixture kind or promote a preparation reader into business authority.
    pub(crate) fn owned_fixture_route(&self) -> Result<Option<NativeLeafApkRoute>,ControlError> {
        let state=self.apk.borrow();state.ready()?;
        match state.owner.as_ref().map(|owner|owner.source_scope()).transpose()? {
            Some(Scope::Business{route}) if crate::native_leaf_fixture_material::NativeLeafFixtureKind::for_route(route).is_ok()=>Ok(Some(route)),
            _=>Ok(None),
        }
    }
    pub(crate) fn apk_package_read_until(&self,inspector:&NativeApplicationInspector,
        kind:crate::production_application::apk_protocol::PackageReadKind,ordinal:u8,end:Instant)
        ->Result<(serde_json::Value,bool),ControlError>
    {
        let end=end.min(self.deadline);self.verify_local(inspector,end)?;
        let mut state=self.apk.borrow_mut();state.ready()?;
        let ApkState{owner,role_application,..}=&mut *state;
        let actual=role_application.as_ref().unwrap_or(self.application);
        let result=(||{
            let owner=owner.as_mut().ok_or_else(||
                ControlError::Invalid("fixed role PM read has no original captured APK owner".into()))?;
            let read=owner.package_read(inspector,self.main,actual,kind,ordinal,end)?;
            let successful=read.output().status.success() && read.output().stderr.is_empty();
            Ok((read.comparison()?,successful))
        })();
        match &result {
            Err(error)=>state.remember(error),
            Ok((_,false))=>state.remember(&ControlError::Invalid(
                "actual fixed role PM query failed or emitted diagnostics".into())),
            Ok((_,true))=>{},
        }
        result
    }
    pub(crate) fn apk_finish_reserve(&self) -> Option<Duration> {
        self.apk.borrow().owner.as_ref().map(NativeLeafApkCustody::finish_reserve)
    }
    pub(crate) fn apk_begin_until(&self, inspector: &NativeApplicationInspector, end: Instant)
        -> Result<serde_json::Value, ControlError>
    {
        let end = end.min(self.deadline); self.verify_local(inspector, end)?;
        let mut state = self.apk.borrow_mut(); state.ready()?;
        let result = (|| {
            let owner = state.owner.as_ref().ok_or_else(||
                ControlError::Invalid("normal Rust did not capture APK custody before the child".into()))?;
            let actual = state.role_application.as_ref().unwrap_or(self.application);
            owner.require_local(inspector, self.main, actual, end)?;
            owner.comparison()
        })();
        if let Err(error) = &result { state.remember(error); }
        result
    }
    pub(crate) fn apk_next_copy_until(&self, inspector: &NativeApplicationInspector, end: Instant)
        -> Result<NativeLeafApkCopy, ControlError>
    {
        let end = end.min(self.deadline); self.verify_local(inspector, end)?;
        let mut state = self.apk.borrow_mut(); state.ready()?;
        let ApkState { owner, role_application, .. } = &mut *state;
        let actual = role_application.as_ref().unwrap_or(self.application);
        let result = owner.as_mut().ok_or_else(||
            ControlError::Invalid("APK capture is required before copy".into()))
            .and_then(|owner| owner.next_copy(inspector, self.main, actual, end));
        if let Err(error) = &result { state.remember(error); }
        result
    }
    pub(crate) fn apk_guard_until(&self, inspector: &NativeApplicationInspector, full: bool, end: Instant)
        -> Result<serde_json::Value, ControlError>
    {
        let end = end.min(self.deadline); self.verify_local(inspector, end)?;
        let mut state = self.apk.borrow_mut(); state.ready()?;
        let ApkState { owner, role_application, .. } = &mut *state;
        let actual = role_application.as_ref().unwrap_or(self.application);
        let result = (|| {
            let owner = owner.as_mut().ok_or_else(|| ControlError::Invalid("APK actual capture is absent".into()))?;
            owner.guard(inspector, self.main, actual, full, end)?;
            let comparison = owner.comparison()?;
            Ok(serde_json::json!({"schema":"droidloom.native-leaf-apk-guard.v1",
                "custody":comparison, "full_sha256_checked":full, "comparison_only":true}))
        })();
        if let Err(error) = &result { state.remember(error); }
        result
    }
    pub(super) fn finish_apk_from_observed(&mut self, inspector: &NativeApplicationInspector,
        after_main: &MainCustodyObservation, after_application: &ActualApplicationObservation, end: Instant)
        -> Result<(), ControlError>
    {
        let reserve = self.apk_finish_reserve();
        let end = end.min(self.deadline);
        let end = reserve.map_or(end, |cap| end.min(Instant::now() + cap));
        let state = self.apk.get_mut(); state.ready()?;
        for prior in &state.finished {
            let actual = prior.role_application.as_ref().unwrap_or(after_application);
            prior.custody.require_subject(inspector, after_main, actual, end)?;
        }
        if let Some(owner) = state.owner.take() {
            let actual = state.role_application.as_ref().unwrap_or(after_application);
            let result = owner.finish(inspector, after_main, actual, end);
            match result {
                Ok(finished) => {
                    finished.require_subject(inspector, after_main, actual, end)?;
                    let role_application = state.role_application.take();
                    state.finished.push(CompletedInterval { custody: finished, role_application });
                }
                Err(error) => { state.remember(&error); return Err(error); }
            }
        }
        Ok(())
    }
    /// Consume completed actual intervals before the original baseline end.
    /// Retaining this history adds no RPC and keeps no already-retired reader alive.
    pub fn take_apk_history_until(&mut self, inspector: &NativeApplicationInspector, end: Instant)
        -> Result<NativeLeafApkHistory, ControlError>
    {
        let end = end.min(self.deadline); self.verify_local(inspector, end)?;
        let state = self.apk.get_mut(); state.ready()?;
        if state.owner.is_some() || state.role_application.is_some()
            || !(1..=2).contains(&state.finished.len())
        {
            return Err(ControlError::Invalid("APK history requires every actual reader to have completed".into()));
        }
        for prior in &state.finished {
            let actual = prior.role_application.as_ref().unwrap_or(self.application);
            prior.custody.require_subject(inspector, self.main, actual, end)?;
        }
        let history = NativeLeafApkHistory { main: self.main.facts().clone(),
            application: self.application.facts().clone(), intervals: std::mem::take(&mut state.finished) };
        history.verify()?;
        state.history_taken = true;
        Ok(history)
    }
}
