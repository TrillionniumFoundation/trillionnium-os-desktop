//! Sticky, read-only generation fencing for a complete application selection.
//!
//! This compares observation values. The daemon transport establishes kernel
//! custody; this scheduling gate never issues production HostAdmission or app
//! acceptance. Its state cannot be deserialized from a caller's JSON plan.

use droidloom_supervisor::control::application_probe::{RuntimeEpoch, RuntimeObservation};

pub(crate) struct RuntimeFence {
    expected: RuntimeEpoch,
    first: Option<RuntimeObservation>,
    error: Option<String>,
}

impl RuntimeFence {
    pub(crate) fn observe(
        expected: &RuntimeEpoch,
        actual: Result<RuntimeObservation, String>,
    ) -> Self {
        let mut fence = Self {
            expected: expected.clone(),
            first: None,
            error: None,
        };
        match actual {
            Ok(observation) if observation.epoch == *expected => fence.first = Some(observation),
            Ok(_) => fence.invalidate(
                "live runtime precondition differs from the independently pinned Main epoch".into(),
            ),
            Err(error) => {
                fence.invalidate(format!("live runtime precondition unavailable: {error}"))
            }
        }
        fence
    }

    pub(crate) fn ready_for_observation(&self) -> bool {
        self.first.is_some() && self.error.is_none()
    }

    pub(crate) fn check_epoch(&mut self, epoch: &RuntimeEpoch) -> bool {
        if self.ready_for_observation() && *epoch != self.expected {
            self.invalidate(
                "runtime generation changed during the selected application observation".into(),
            );
        }
        self.ready_for_observation()
    }

    pub(crate) fn recheck(&mut self, actual: Result<RuntimeObservation, String>) {
        if !self.ready_for_observation() {
            return;
        }
        match actual {
            Ok(observation) if self.first.as_ref() == Some(&observation) => {},
            Ok(_) => self.invalidate("runtime generation or owning lifecycle changed after a failed application operation".into()),
            Err(error) => self.invalidate(format!("runtime state became unavailable after a failed application operation: {error}")),
        }
    }

    pub(crate) fn transport_failed(&mut self, reason: &str) {
        self.invalidate(format!(
            "runtime control transport failed; further application operations refused: {reason}"
        ));
    }

    fn invalidate(&mut self, reason: String) {
        if self.error.is_none() {
            self.error = Some(reason);
        }
    }

    pub(crate) fn reason(&self) -> Option<&str> {
        self.error.as_deref()
    }

    pub(crate) fn first_observation(&self) -> Option<&RuntimeObservation> {
        self.first.as_ref()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use droidloom_supervisor::control::application_probe::RuntimeLifecycle;

    fn observed() -> RuntimeObservation {
        RuntimeObservation {
            epoch: RuntimeEpoch {
                boot_id: "unit-test-boot".into(),
                cell_host_pid: 10,
                framework_host_pid: 20,
                framework_start_ticks: 30,
            },
            lifecycle: RuntimeLifecycle::Development,
        }
    }

    #[test]
    fn unavailable_precondition_never_allows_an_application_operation() {
        let expected = observed();
        let fence = RuntimeFence::observe(&expected.epoch, Err("not running".into()));
        assert!(!fence.ready_for_observation());
        assert!(fence.first_observation().is_none());
        assert!(fence.reason().unwrap().contains("not running"));
    }

    #[test]
    fn every_physical_generation_field_is_required_before_the_first_operation() {
        let expected = observed();
        for field in 0..4 {
            let mut changed = expected.clone();
            match field {
                0 => changed.epoch.boot_id.push('x'),
                1 => changed.epoch.cell_host_pid += 1,
                2 => changed.epoch.framework_host_pid += 1,
                _ => changed.epoch.framework_start_ticks += 1,
            }
            assert!(!RuntimeFence::observe(&expected.epoch, Ok(changed)).ready_for_observation());
        }
    }

    #[test]
    fn matching_observation_preserves_its_actual_development_lifecycle() {
        let actual = observed();
        let mut fence = RuntimeFence::observe(&actual.epoch, Ok(actual.clone()));
        assert!(fence.ready_for_observation());
        assert!(fence.check_epoch(&actual.epoch));
        assert_eq!(fence.first_observation(), Some(&actual));
        assert_eq!(
            fence.first_observation().unwrap().lifecycle,
            RuntimeLifecycle::Development
        );
    }

    #[test]
    fn changed_generation_is_sticky_even_if_a_later_reply_repeats_old_values() {
        let actual = observed();
        let mut fence = RuntimeFence::observe(&actual.epoch, Ok(actual.clone()));
        let mut changed = actual.epoch.clone();
        changed.framework_start_ticks += 1;
        assert!(!fence.check_epoch(&changed));
        fence.recheck(Ok(actual.clone()));
        assert!(!fence.check_epoch(&actual.epoch));
        assert!(fence.reason().unwrap().contains("generation changed"));
    }

    #[test]
    fn failed_recheck_withholds_previous_observations_from_current_results() {
        let actual = observed();
        let mut fence = RuntimeFence::observe(&actual.epoch, Ok(actual.clone()));
        fence.recheck(Err("framework no longer ready".into()));
        assert!(!fence.ready_for_observation());
        assert_eq!(fence.first_observation(), Some(&actual));
        assert!(fence.reason().unwrap().contains("no longer ready"));
    }

    #[test]
    fn transport_failure_closes_the_fence_without_a_retry_or_freshness_claim() {
        let actual = observed();
        let mut fence = RuntimeFence::observe(&actual.epoch, Ok(actual.clone()));
        fence.transport_failed("socket response deadline");
        let reason = fence.reason().unwrap().to_owned();
        fence.recheck(Ok(actual));
        assert!(!fence.ready_for_observation());
        assert_eq!(fence.reason(), Some(reason.as_str()));
    }
}
