//! Actual three-command preparation observations, from the original Ready owner.
use super::*;
use crate::main_custody::RuntimeMainCustody;
use crate::native_preparation_read::{PreparationReadKind, PreparationReadRequest};
use crate::production_execution_profile::query_inputs as fixed;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use sha2::{Digest, Sha256};
use std::time::Instant;

pub(super) fn binary(command: &PreparationReadKind) -> &'static CStr {
    match command {
        PreparationReadKind::BootCompleted => c"toolbox",
        _ => c"toybox",
    }
}
pub(super) fn arguments(request: &PreparationReadRequest) -> Result<Vec<CString>> {
    request.validate().map_err(external)?;
    request
        .kind()
        .literal_arguments()
        .iter()
        .map(|v| CString::new(*v).map_err(external))
        .collect()
}
/// Fixed source comparison only. This does not establish actual execution.
pub(crate) struct PreparationReadExecutionProfile {
    pub(crate) process_selinux: &'static str,
    pub(crate) process_apparmor: &'static str,
    pub(crate) executable_selinux: &'static str,
    pub(crate) executable_bytes: u64,
    pub(crate) executable_sha256: &'static str,
    pub(crate) guest_uid: u32,
}
pub(crate) fn preparation_read_execution_profile(
    command: &PreparationReadKind,
) -> std::result::Result<PreparationReadExecutionProfile, String> {
    // Bound typed arguments before returning a comparison profile.
    let _ = command.literal_arguments();
    let input = match binary(command).to_bytes() {
        b"toybox" => fixed::INPUTS[1],
        b"toolbox" => fixed::INPUTS[4],
        _ => {
            return Err("preparation read executable is outside the fixed selected profile".into());
        }
    };
    Ok(PreparationReadExecutionProfile {
        process_selinux: OperationDomain::PreparationRead.context(),
        process_apparmor: "droidloom-production-android (enforce)",
        executable_selinux: "u:object_r:droidloom_query_exec:s0",
        executable_bytes: input.bytes,
        executable_sha256: input.sha256,
        guest_uid: 0,
    })
}

/// Actual factory execution plus same live owner's before/after Main facts.
/// There is no deserializer, test constructor, or external success input.
pub(crate) struct PreparationReadObservation {
    request: PreparationReadRequest,
    before_main: RuntimeMainCustody,
    after_main: RuntimeMainCustody,
    actual: LaunchCommandResult,
}
impl PreparationReadObservation {
    pub(crate) fn request(&self) -> &PreparationReadRequest {
        &self.request
    }
    pub(crate) fn before_main(&self) -> &RuntimeMainCustody {
        &self.before_main
    }
    pub(crate) fn after_main(&self) -> &RuntimeMainCustody {
        &self.after_main
    }
    pub(crate) fn output(&self) -> &std::process::Output {
        &self.actual.output
    }
    pub(crate) fn receipt(&self) -> &ReadReceipt {
        &self.actual.receipt
    }
    pub(crate) fn stderr_bytes(&self) -> usize {
        self.actual.stderr_bytes
    }
    pub(crate) fn stderr_sha256(&self) -> &str {
        &self.actual.stderr_sha256
    }
}

pub(crate) fn execute_preparation_read(
    owner: &EarlyApplicationAuthority<'_>,
    request: PreparationReadRequest,
    admitted_deadline: Instant,
) -> Result<PreparationReadObservation> {
    request.validate().map_err(external)?;
    require(
        owner.request_deadline() == Some(admitted_deadline),
        "preparation read must borrow the original admitted absolute command end",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    let before_main = owner
        .observe_main_custody(&request.main().epoch, admitted_deadline)
        .map_err(observation_authority_error)?;
    require(
        &before_main == request.main(),
        "preparation read before-Main differs from the actual frontend's original observation",
    )?;
    let operation = ApplicationOperation::PreparationRead {
        value: request.clone(),
    };
    let result = factory_query::run(owner, &operation, admitted_deadline);
    let after = owner
        .observe_main_custody(&request.main().epoch, admitted_deadline)
        .map_err(observation_authority_error);
    // Preserve an actual failure; unproven retirement always remains quarantine.
    if matches!(&result, Err(ApplicationError::RetirementUnproven))
        || matches!(&after, Err(ApplicationError::RetirementUnproven))
    {
        return Err(ApplicationError::RetirementUnproven);
    }
    let actual = result?;
    let after_main = after?;
    require(
        &after_main == request.main() && after_main == before_main,
        "preparation read operation crossed complete Main or persistent-resource custody",
    )?;
    require(
        actual.operation_deadline <= admitted_deadline
            && actual.receipt.schema == 2
            && actual.receipt.cgroup_removed
            && matches!(
                &actual.receipt.lifecycle,
                ReadLifecycle::InstanceFactory {
                    release_acknowledged: true,
                    ..
                }
            )
            && actual.receipt.output_bytes == actual.output.stdout.len()
            && actual.receipt.output_sha256
                == format!("{:x}", Sha256::digest(&actual.output.stdout))
            && actual.stderr_bytes == actual.output.stderr.len()
            && actual.stderr_sha256 == format!("{:x}", Sha256::digest(&actual.output.stderr)),
        "preparation read actual factory retirement or complete captured output differs",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    request.validate().map_err(external)?;
    crate::production_host_admission::check_observation_before(admitted_deadline)?;
    // A real nonzero exit is retained verbatim for the existing operation journal.
    Ok(PreparationReadObservation {
        request,
        before_main,
        after_main,
        actual,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preparation_operation_uses_only_the_original_fifteen_descriptor_factory_path() {
        for kind in [
            PreparationReadKind::GuestUid,
            PreparationReadKind::GuestGid,
            PreparationReadKind::BootCompleted,
        ] {
            let request = crate::native_preparation_read::tests::comparison(kind);
            let operation = ApplicationOperation::PreparationRead { value: request };
            operation.validate().unwrap();
            assert_eq!(operation.domain(), OperationDomain::PreparationRead);
            assert_eq!(operation.domain().guest_uid(), 0);
            assert_eq!(operation.descriptor_count(), 15);
            assert_eq!(operation.output_limit(), 4096);
            assert!(!operation.uses_app_process());
            assert!(!operation.needs_content_jar());
            assert!(operation.install_input_bytes().is_none());
            let actual = operation.arguments().unwrap();
            let text: Vec<_> = actual.iter().map(|v| v.to_str().unwrap()).collect();
            assert_eq!(text, kind.literal_arguments());
        }
    }
}
