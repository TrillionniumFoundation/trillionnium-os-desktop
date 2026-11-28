//! A running-only engine observation through the normal original owner.
//! The application must already be running. This API neither launches it nor
//! infers an engine from zygote presence, APK ABI, a saved receipt or absence.
use super::*;
use crate::engine_custody::{
    EngineAbiComparison, EngineKind, MAX_WIRE_BYTES, RuntimeEngineObservation,
};
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
        let abi_before = read_runtime_abi(owner, package, deadline)?;
        let principal = abi_before.main_process(before.uid, package)?;
        // AMS selects only one of these two fixed comparison modes. The owner
        // independently enumerates original PIDFDs and then joins the real PIDNS
        // number below; no AMS PID opens proc or constructs process authority.
        let kind = match (principal.required_abi(), principal.instruction_set()) {
            (Some("x86_64"), None | Some("x86_64")) => EngineKind::NativeX86_64,
            (Some("arm64-v8a"), None | Some("arm64") | Some("x86_64")) => EngineKind::BerberisArm64,
            _ => {
                return Err(reject(
                    "actual required ABI has no fixed positive runtime branch",
                ));
            }
        };
        let held = owner
            .begin_engine_observation(&before, &main, kind, deadline)
            .map_err(observation_authority_error)?;
        let process = held.process();
        let first_abi =
            abi_before.match_process(process.guest_pid, before.uid, &process.command)?;
        require(
            first_abi == principal,
            "AMS main record differs from the independently held task",
        )?;
        let abi_after = read_runtime_abi(owner, package, deadline)?;
        let last_abi = abi_after.match_process(process.guest_pid, before.uid, &process.command)?;
        require(
            first_abi == last_abi,
            "actual AMS process ABI or start sequence changed",
        )?;
        let runtime_abi = EngineAbiComparison {
            guest_pid: first_abi.guest_pid(),
            uid: first_abi.uid(),
            user: first_abi.user(),
            process_name: first_abi.process_name().into(),
            required_abi: first_abi
                .required_abi()
                .ok_or_else(|| reject("AMS required ABI absent"))?
                .into(),
            instruction_set: first_abi.instruction_set().map(str::to_owned),
            start_seq: first_abi.start_seq(),
            before_query_sha256: abi_before.receipt().output_sha256.clone(),
            after_query_sha256: abi_after.receipt().output_sha256.clone(),
        };
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
            .complete_engine_observation(held, before, main, runtime_abi, deadline)
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
