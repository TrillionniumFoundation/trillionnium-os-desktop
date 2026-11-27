//! Whole Settings permission-interface gate from the fixed actual native case.
//! Parsing a comparison or receiving only one visible page cannot mint it.
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    NativeApplicationInspector, SettingsPermissionCaseObservation, run_settings_permission_case,
    settings_permission_case_window_seconds,
};
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation;
use serde_json::Value;
use std::time::Instant;

pub(super) fn window_seconds() -> u64 {
    settings_permission_case_window_seconds()
}
pub(super) struct SettingsPermissionsBusinessFact {
    observation: SettingsPermissionCaseObservation,
}
impl SettingsPermissionsBusinessFact {
    pub(super) fn gate(&self) -> &'static str {
        "settings.permissions"
    }
    pub(super) fn observation(&self) -> &SettingsPermissionCaseObservation {
        &self.observation
    }
    pub(super) fn guard_immutable(&self) -> Result<(), String> {
        self.observation.verify_retained()
    }
    pub(super) fn require_subject(
        &self,
        main: &RuntimeMainCustody,
        application: &ApplicationInspection,
    ) -> Result<(), String> {
        self.observation.require_subject(main, application)
    }
    pub(super) fn comparison(&self) -> Result<Value, String> {
        self.guard_immutable()?;
        Ok(
            serde_json::json!({"schema":"droidloom.native-settings-permissions-business-fact.v1",
            "gate":self.gate(),"actual_case":self.observation.comparison()?,
            "partial_pages_are_gate_evidence":false,"whole_application_accepted":false}),
        )
    }
}
pub(super) fn run(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    original_end: Instant,
) -> Result<SettingsPermissionsBusinessFact, String> {
    let observation = run_settings_permission_case(inspector, baseline, original_end)?;
    let result = SettingsPermissionsBusinessFact { observation };
    result.guard_immutable()?;
    Ok(result)
}
