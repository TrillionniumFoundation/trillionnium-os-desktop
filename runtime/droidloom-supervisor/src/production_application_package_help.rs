//! Fixed cmd package help from the same actual Ready owner and complete Main.
use super::*;
use crate::main_custody::RuntimeMainCustody;
use crate::native_package_help::PackageHelpRequest;
use crate::production_execution_profile::query_inputs as fixed;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use sha2::{Digest, Sha256};
use std::time::Instant;

pub(super) fn arguments(request: &PackageHelpRequest) -> Result<Vec<CString>> {
    request.validate().map_err(external)?;
    crate::native_package_help::ARGUMENTS.iter()
        .map(|v| CString::new(*v).map_err(external))
        .collect()
}
pub(crate) fn package_help_execution_profile()
    -> super::preparation_read::PreparationReadExecutionProfile
{
    let input = fixed::INPUTS[0];
    super::preparation_read::PreparationReadExecutionProfile {
        process_selinux: OperationDomain::Query.context(),
        process_apparmor: "droidloom-production-android (enforce)",
        executable_selinux: "u:object_r:droidloom_query_exec:s0",
        executable_bytes: input.bytes,
        executable_sha256: input.sha256,
        guest_uid: 2000,
    }
}
/// Actual factory execution plus same live owner's before/after Main facts.
/// There is no deserializer, test constructor, or external success input.
pub(crate) struct PackageHelpObservation {
    request: PackageHelpRequest,
    before_main: RuntimeMainCustody,
    after_main: RuntimeMainCustody,
    actual: LaunchCommandResult,
}
impl PackageHelpObservation {
    pub(crate) fn request(&self) -> &PackageHelpRequest {
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

pub(crate) fn execute_package_help(
    owner: &EarlyApplicationAuthority<'_>,
    request: PackageHelpRequest,
    admitted_deadline: Instant,
) -> Result<PackageHelpObservation> {
    request.validate().map_err(external)?;
    require(
        owner.request_deadline() == Some(admitted_deadline),
        "package help must borrow the original admitted absolute command end",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    let before_main = owner
        .observe_main_custody(&request.main().epoch, admitted_deadline)
        .map_err(observation_authority_error)?;
    require(
        &before_main == request.main(),
        "package help before-Main differs from the actual frontend's original observation",
    )?;
    let operation = ApplicationOperation::PackageHelp {
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
        "package help operation crossed complete Main or persistent-resource custody",
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
        "package help actual factory retirement or complete captured output differs",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    request.validate().map_err(external)?;
    crate::production_host_admission::check_observation_before(admitted_deadline)?;
    // A real nonzero exit is retained verbatim for the existing operation journal.
    Ok(PackageHelpObservation {
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
    fn package_help_operation_uses_fixed_readonly_cmd_query_and_fifteen_descriptors() {
        let value = crate::native_package_help::tests::comparison();
        let operation = ApplicationOperation::PackageHelp { value };
        operation.validate().unwrap();
        assert_eq!(operation.binary(), c"cmd");
        assert_eq!(operation.domain(), OperationDomain::Query);
        assert_eq!(operation.domain().guest_uid(), 2000);
        assert_eq!(operation.descriptor_count(), 15);
        assert_eq!(operation.output_limit(), 65536);
        assert!(!operation.uses_app_process());
        assert!(!operation.needs_content_jar());
        assert!(operation.install_input_bytes().is_none());
        let actual = operation.arguments().unwrap();
        let text: Vec<_> = actual.iter().map(|v| v.to_str().unwrap()).collect();
        assert_eq!(text, ["/system/bin/cmd", "package", "help"]);
        let profile = package_help_execution_profile();
        assert_eq!(fixed::INPUTS[0].source_path, "/system/bin/cmd");
        assert_eq!(profile.process_selinux, "u:r:droidloom_query:s0");
        assert_eq!(profile.guest_uid, 2000);
        assert_eq!(profile.executable_bytes, fixed::INPUTS[0].bytes);
        assert_eq!(profile.executable_sha256, fixed::INPUTS[0].sha256);
    }
}
