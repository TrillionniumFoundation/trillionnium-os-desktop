//! Historical, opaque running-engine observations from one actual owned leaf.
//! The child can request only the fixed E checkpoint. Targets and authority
//! come from the parent's existing Main/PM tokens and original deadline.
use crate::control::application_probe::ApplicationInspection;
use crate::control::{
    EngineMappingObservation, MainCustodyObservation, NativeApplicationInspector,
};
use crate::native_leaf_baseline::NativeLeafBaselineObservation;
use serde::ser::{Serialize, SerializeStruct, Serializer};
use std::process::Output;
use std::time::{Duration, Instant};

// Reuse the existing whole-channel check limit. No per-route maximum is guessed
// and no descriptors or observations are preallocated for unexecuted requests.
pub(crate) const MAX_CHECKS: usize = crate::control::physical_qualification_channel::budget::resources::NATIVE_ENGINE_OBSERVATIONS;
const ENGINE_REQUEST_WINDOW: Duration = Duration::from_secs(70);

pub struct NativeLeafExecution {
    output: Output,
    engines: Option<NativeLeafEngineEvidence>,
}
impl NativeLeafExecution {
    pub fn into_parts(self) -> (Output, Option<NativeLeafEngineEvidence>) {
        (self.output, self.engines)
    }
}

/// No Deserialize, Clone, public fields or receipt constructor. Every item was
/// minted by the same actual Inspector while the fixed child was still running.
/// These are point observations; App PIDFD custody is not claimed after E ends.
pub struct NativeLeafEngineEvidence {
    observations: Vec<EngineMappingObservation>,
    started: Instant,
    retired: Instant,
}
impl std::fmt::Debug for NativeLeafEngineEvidence {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("NativeLeafEngineEvidence")
            .field("observations", &self.observations.len())
            .finish_non_exhaustive()
    }
}
impl Serialize for NativeLeafEngineEvidence {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut out = serializer.serialize_struct("NativeLeafEngineEvidence", 5)?;
        out.serialize_field("schema", "droidloom.native-leaf-running-engine-evidence.v1")?;
        out.serialize_field(
            "observations",
            &self
                .observations
                .iter()
                .map(EngineMappingObservation::facts)
                .collect::<Vec<_>>(),
        )?;
        out.serialize_field("owned_leaf_host_retirement_proved", &true)?;
        out.serialize_field(
            "continuous_app_process_custody_after_checkpoint_claimed",
            &false,
        )?;
        out.serialize_field("translation_business_success_verified", &false)?;
        out.end()
    }
}
impl NativeLeafEngineEvidence {
    pub fn observation_count(&self) -> usize {
        self.observations.len()
    }

    /// Compare retained opaque observations to the same actual completed row.
    /// No fresh E request is made after the business flow closed its App.
    pub fn require_identity(
        &self,
        main: &MainCustodyObservation,
        actual: &ApplicationInspection,
    ) -> Result<(), String> {
        if self.observations.is_empty()
            || self.observations.len() > MAX_CHECKS
            || self.retired < self.started
        {
            return Err("leaf has no bounded actual running-engine history".into());
        }
        let mut previous = self.started;
        for observation in &self.observations {
            if observation.application() != actual
                || observation.peer() != main.peer()
                || observation.facts().main != *main.facts()
                || !observation.facts().application.matches_inspection(actual)
                || observation.observed_at() <= previous
                || observation.observed_at() > self.retired
            {
                return Err("running-engine history differs from this actual Main, package, peer or invocation".into());
            }
            observation
                .facts()
                .validate(main.facts(), &observation.facts().application)?;
            previous = observation.observed_at();
        }
        Ok(())
    }
}

pub(crate) struct PendingLeafEngines {
    observations: Vec<EngineMappingObservation>,
    started: Instant,
    deadline: Instant,
}
impl PendingLeafEngines {
    pub(crate) fn new(deadline: Instant) -> Result<Self, String> {
        let started = Instant::now();
        if started >= deadline {
            return Err("running-engine leaf original deadline expired".into());
        }
        Ok(Self {
            observations: Vec::new(),
            started,
            deadline,
        })
    }
    pub(crate) fn capture(
        &mut self,
        baseline: &NativeLeafBaselineObservation<'_>,
        inspector: &mut NativeApplicationInspector,
        work_end: Instant,
    ) -> Result<(), String> {
        let end = work_end.min(self.deadline).min(baseline.deadline());
        if self.observations.len() >= MAX_CHECKS
            || !end
                .checked_duration_since(Instant::now())
                .is_some_and(|left| left >= ENGINE_REQUEST_WINDOW)
        {
            return Err("original leaf window cannot cover another actual engine request".into());
        }
        baseline
            .verify_local(inspector, end)
            .map_err(|e| e.to_string())?;
        let observed = inspector
            .observe_running_engine_until(baseline.main(), baseline.actual_application(), end)
            .map_err(|e| e.to_string())?;
        baseline
            .verify_local(inspector, end)
            .map_err(|e| e.to_string())?;
        let previous = self
            .observations
            .last()
            .map(EngineMappingObservation::observed_at)
            .unwrap_or(self.started);
        if observed.observed_at() <= previous || Instant::now() >= end {
            return Err(
                "actual engine observation is outside this original leaf invocation".into(),
            );
        }
        self.observations.push(observed);
        Ok(())
    }
    pub(crate) fn finish(self, output: Output) -> Result<NativeLeafExecution, String> {
        let retired = Instant::now();
        if !output.status.success() || retired >= self.deadline {
            return Err(
                "actual leaf did not complete successfully within its original deadline".into(),
            );
        }
        let engines = if self.observations.is_empty() {
            None
        } else {
            Some(NativeLeafEngineEvidence {
                observations: self.observations,
                started: self.started,
                retired,
            })
        };
        Ok(NativeLeafExecution { output, engines })
    }
}
