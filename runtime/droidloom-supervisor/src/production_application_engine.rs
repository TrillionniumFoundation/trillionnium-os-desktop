//! A running-only engine observation through the normal original owner.
//! The application must already be running. This API neither launches it nor
//! infers an engine from zygote presence, APK ABI, a saved receipt or absence.
use super::*;
use crate::engine_custody::{MAX_WIRE_BYTES, RuntimeEngineObservation};
use crate::production_selection::early_generation::{
    EarlyApplicationAuthority, EarlyFrameworkObservation,
};
use std::time::Instant;

struct EngineProbe<'a, 'owner> {
    owner: &'a EarlyApplicationAuthority<'owner>,
    framework: EarlyFrameworkObservation,
    reads: Vec<ReadReceipt>,
    first_failure: Option<ApplicationError>,
    deadline: Instant,
}
impl EngineProbe<'_, '_> {
    fn retain<T>(&mut self, result: Result<T>) -> std::result::Result<T, String> {
        result.map_err(|error| {
            let message = error.to_string();
            if self.first_failure.is_none()
                || matches!(&error, ApplicationError::RetirementUnproven)
            {
                self.first_failure = Some(error);
            }
            message
        })
    }
}
impl AndroidProbe for EngineProbe<'_, '_> {
    fn epoch(&mut self) -> std::result::Result<RuntimeEpoch, String> {
        let result = (|| {
            crate::production_host_admission::check_observation_before(self.deadline)?;
            self.owner
                .epoch(&self.framework)
                .map_err(observation_authority_error)
        })();
        self.retain(result)
    }
    fn command(&mut self, args: &[String]) -> std::result::Result<String, String> {
        let result = (|| {
            crate::production_host_admission::check_observation_before(self.deadline)?;
            require(self.reads.len() < 2, "engine installed-package query bound")?;
            self.owner
                .epoch(&self.framework)
                .map_err(observation_authority_error)?;
            let query = ApplicationRead::from_command(args)?;
            require(
                matches!(
                    &query,
                    ApplicationRead::PackageIdentity { .. } | ApplicationRead::PackagePaths { .. }
                ),
                "engine operation accepts PM metadata queries only",
            )?;
            let result = run_read_before(self.owner, &query, self.deadline)?;
            require(
                result.receipt.successful_retirement()
                    && result.receipt.query_waitid_code == libc::CLD_EXITED
                    && result.receipt.query_waitid_status == 0
                    && result.receipt.cgroup_removed,
                "engine package query lacks actual successful retirement",
            )?;
            self.owner
                .epoch(&self.framework)
                .map_err(observation_authority_error)?;
            self.reads.push(result.receipt);
            Ok(result.output)
        })();
        self.retain(result)
    }
}
fn metadata_fixed(
    owner: &EarlyApplicationAuthority<'_>,
    package: &str,
    budget: &RuntimeVintfBudget,
) -> Result<crate::control::application_probe::ApplicationMetadata> {
    let framework = owner
        .observe_framework()
        .map_err(observation_authority_error)?;
    let mut probe = EngineProbe {
        owner,
        framework,
        reads: Vec::new(),
        first_failure: None,
        deadline: budget.work_deadline(),
    };
    let result = crate::control::application_probe::inspect_metadata(&mut probe, package, 0);
    let result = match probe.first_failure.take() {
        Some(error) => Err(error),
        None => result.map_err(external),
    };
    let result = vintf::finish_vintf(
        result,
        || owner.revalidate().map_err(observation_authority_error),
        budget.work_deadline(),
        budget.operation_deadline(),
    )?;
    require(
        probe.reads.len() == 2,
        "engine metadata requires exactly the two fixed PM reads",
    )?;
    Ok(result)
}
pub(crate) fn observe_running_engine(
    owner: &EarlyApplicationAuthority<'_>,
    package: &str,
    user: u32,
    expected: &RuntimeEpoch,
    budget: &RuntimeVintfBudget,
) -> Result<RuntimeEngineObservation> {
    require(
        crate::engine_custody::selected_package(package)
            && user == 0
            && owner.request_deadline() == Some(budget.work_deadline()),
        "engine observation requires a selected user-0 package and the admitted deadline",
    )?;
    let deadline = budget.work_deadline();
    let result = (|| {
        let main = owner
            .observe_main_custody(expected, deadline)
            .map_err(observation_authority_error)?;
        let before = metadata_fixed(owner, package, budget)?;
        require(
            &before.epoch == expected,
            "engine PM query belongs to a different Main epoch",
        )?;
        let held = owner
            .begin_engine_observation(&before, &main, deadline)
            .map_err(observation_authority_error)?;
        let after = metadata_fixed(owner, package, budget)?;
        require(
            after == before,
            "actual installed package changed during engine observation",
        )?;
        require(
            owner
                .observe_main_custody(expected, deadline)
                .map_err(observation_authority_error)?
                == main,
            "actual Main or persistent resource changed during engine observation",
        )?;
        let observed = owner
            .complete_engine_observation(held, before, main, deadline)
            .map_err(observation_authority_error)?;
        require(
            serde_json::to_vec(&observed).map_err(external)?.len() <= MAX_WIRE_BYTES,
            "engine observation exceeds its fixed wire bound",
        )?;
        Ok(observed)
    })();
    vintf::finish_vintf(
        result,
        || owner.revalidate().map_err(observation_authority_error),
        deadline,
        budget.operation_deadline(),
    )
}
