//! A camera.photo fact from the fixed live single-shutter/two-session producer.
//! Saved comparisons, scene-only observations and caller gate flags cannot
//! construct this type. No other Camera business gate is inferred.
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use droidloom_supervisor::control::{
    CameraPhotoCaseObservation, NativeApplicationInspector, camera_photo_case_window_seconds,
    run_camera_photo_case,
};
use droidloom_supervisor::main_custody::RuntimeMainCustody;
use droidloom_supervisor::native_leaf_baseline::NativeLeafBaselineObservation;
use serde_json::Value;
use std::time::Instant;

pub(super) fn window_seconds() -> u64 {
    camera_photo_case_window_seconds()
}

pub(super) struct CameraPhotoBusinessFact {
    observation: CameraPhotoCaseObservation,
}
impl CameraPhotoBusinessFact {
    pub(super) fn gate(&self) -> &'static str {
        "camera.photo"
    }
    pub(super) fn observation(&self) -> &CameraPhotoCaseObservation {
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
        Ok(serde_json::json!({
            "schema":"droidloom.native-camera-photo-business-fact.v1",
            "gate":self.gate(),"actual_case":self.observation.comparison()?,
            "whole_application_accepted":false
        }))
    }
}
pub(super) fn run(
    inspector: &mut NativeApplicationInspector,
    baseline: &mut NativeLeafBaselineObservation<'_>,
    original_end: Instant,
) -> Result<CameraPhotoBusinessFact, String> {
    let observation = run_camera_photo_case(inspector, baseline, original_end)?;
    let result = CameraPhotoBusinessFact { observation };
    result.guard_immutable()?;
    Ok(result)
}
