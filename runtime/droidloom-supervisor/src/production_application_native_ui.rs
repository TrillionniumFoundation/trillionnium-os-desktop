//! Native UI commands executed only by the original kernel-first factory.
//! Literal wrappers are translated to their selected stock executable and JAR;
//! no host namespace helper, shell, caller path or caller label is executed.
use super::*;
use crate::main_custody::RuntimeMainCustody;
use crate::native_application_ui_gateway::{EntryCheck, GatewayCommand, GatewayRequest};
use crate::production_execution_profile::query_inputs as fixed;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use sha2::{Digest, Sha256};
use std::time::Instant;

pub(super) fn binary(command: &GatewayCommand) -> &'static CStr {
    match command {
        GatewayCommand::EntryCheck {
            check: EntryCheck::BootCompleted,
        } => c"toolbox",
        GatewayCommand::EntryCheck { .. } | GatewayCommand::CameraClock {} => c"toybox",
        GatewayCommand::TaskList {}
        | GatewayCommand::TaskRemove { .. }
        | GatewayCommand::SettingsStart { .. }
        | GatewayCommand::SettingsBack {}
        | GatewayCommand::CameraMenu {}
        | GatewayCommand::PackageIdentity { .. }
        | GatewayCommand::PackagePaths { .. }
        | GatewayCommand::PackageLauncher { .. } => c"cmd",
        GatewayCommand::Helper { .. }
        | GatewayCommand::CameraImageIds {}
        | GatewayCommand::CameraImageRow { .. }
        | GatewayCommand::CalendarCounts {} => c"app_process64",
        GatewayCommand::WindowDisplays {} | GatewayCommand::SettingsWindow {} => c"dumpsys",
        GatewayCommand::ScreenCapture {} => c"screencap",
    }
}
pub(super) const fn needs_am_jar(command: &GatewayCommand) -> bool {
    matches!(command, GatewayCommand::Helper { .. })
}
pub(super) const fn needs_content_jar(command: &GatewayCommand) -> bool {
    matches!(
        command,
        GatewayCommand::CameraImageIds {} | GatewayCommand::CameraImageRow { .. }
    )
}
pub(super) const fn uses_app_process(command: &GatewayCommand) -> bool {
    needs_am_jar(command) || needs_content_jar(command)
        || matches!(command, GatewayCommand::CalendarCounts {})
}
pub(super) fn domain(command: &GatewayCommand) -> OperationDomain {
    match command {
        GatewayCommand::PackageIdentity { .. } | GatewayCommand::PackagePaths { .. } => {
            OperationDomain::Query
        }
        GatewayCommand::PackageLauncher { .. } => OperationDomain::LaunchRead,
        GatewayCommand::CalendarCounts {} => OperationDomain::CalendarCounts,
        _ if command.guest_uid() == 0 => OperationDomain::NativeUiRead,
        _ => OperationDomain::NativeUi,
    }
}
pub(super) fn arguments(request: &GatewayRequest) -> Result<Vec<CString>> {
    request.validate().map_err(external)?;
    let command = request.command();
    let literal = command.literal_arguments().map_err(external)?;
    let values = match command {
        GatewayCommand::Helper { .. }
        | GatewayCommand::CameraImageIds {}
        | GatewayCommand::CameraImageRow { .. } => {
            // Same selected ART interpreter discipline as the Contacts observer.
            // The optional stock am wrapper's task-profile adjustment is not
            // used: the real query remains in its original bounded owned cgroup.
            let class = if needs_am_jar(command) {
                "com.android.commands.am.Am"
            } else {
                "com.android.commands.content.Content"
            };
            let mut values = vec![
                "/system/bin/app_process64".into(),
                "-Xint".into(),
                "-Xusejit:false".into(),
                "/system/bin".into(),
                class.into(),
            ];
            values.extend(literal.into_iter().skip(1));
            values
        }
        GatewayCommand::EntryCheck {
            check: EntryCheck::BootCompleted,
        } => vec![
            "/system/bin/toolbox".into(),
            "getprop".into(),
            "sys.boot_completed".into(),
        ],
        GatewayCommand::CameraClock {} => {
            vec!["/system/bin/toybox".into(), "date".into(), "+%s".into()]
        }
        GatewayCommand::SettingsBack {} => vec![
            "/system/bin/cmd".into(),
            "input".into(),
            "keyevent".into(),
            "4".into(),
        ],
        GatewayCommand::CameraMenu {} => vec![
            "/system/bin/cmd".into(),
            "input".into(),
            "keyevent".into(),
            "82".into(),
        ],
        _ => literal,
    };
    values
        .into_iter()
        .map(|v| CString::new(v).map_err(external))
        .collect()
}

/// Fixed source comparison only. This does not establish actual execution.
pub(crate) struct NativeUiExecutionProfile {
    pub(crate) process_selinux: &'static str,
    pub(crate) process_apparmor: &'static str,
    pub(crate) executable_selinux: &'static str,
    pub(crate) executable_bytes: u64,
    pub(crate) executable_sha256: &'static str,
    pub(crate) guest_uid: u32,
}
pub(crate) fn native_ui_execution_profile(
    command: &GatewayCommand,
) -> std::result::Result<NativeUiExecutionProfile, String> {
    // Bound typed arguments before returning a comparison profile.
    command.literal_arguments()?;
    let input = match binary(command).to_bytes() {
        b"cmd" => fixed::INPUTS[0],
        b"toybox" => fixed::INPUTS[1],
        b"app_process64" => fixed::INPUTS[2],
        b"toolbox" => fixed::INPUTS[4],
        b"dumpsys" => fixed::NATIVE_UI_INPUTS[1],
        b"screencap" => fixed::NATIVE_UI_INPUTS[2],
        _ => return Err("native UI executable is outside the fixed selected profile".into()),
    };
    Ok(NativeUiExecutionProfile {
        process_selinux: domain(command).context(),
        process_apparmor: "droidloom-production-android (enforce)",
        executable_selinux: if uses_app_process(command) {
            "u:object_r:droidloom_provider_exec:s0"
        } else {
            "u:object_r:droidloom_query_exec:s0"
        },
        executable_bytes: input.bytes,
        executable_sha256: input.sha256,
        guest_uid: command.guest_uid(),
    })
}

/// Actual factory execution plus same live owner's before/after Main facts.
/// There is no deserializer, test constructor, or external success input.
pub(crate) struct NativeUiObservation {
    request: GatewayRequest,
    before_main: RuntimeMainCustody,
    after_main: RuntimeMainCustody,
    actual: LaunchCommandResult,
}
impl NativeUiObservation {
    pub(crate) fn request(&self) -> &GatewayRequest {
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

pub(crate) fn execute_native_ui(
    owner: &EarlyApplicationAuthority<'_>,
    request: GatewayRequest,
    admitted_deadline: Instant,
) -> Result<NativeUiObservation> {
    request.validate().map_err(external)?;
    require(
        owner.request_deadline() == Some(admitted_deadline),
        "native UI must borrow the original admitted absolute command end",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    let before_main = owner
        .observe_main_custody(&request.main().epoch, admitted_deadline)
        .map_err(observation_authority_error)?;
    require(
        &before_main == request.main(),
        "native UI before-Main differs from the actual frontend's original observation",
    )?;
    let result = if matches!(request.command(), GatewayCommand::CalendarCounts {}) {
        super::calendar_counts::run(owner, admitted_deadline)
    } else {
        let operation = ApplicationOperation::NativeUi { value: request.clone() };
        factory_query::run(owner, &operation, admitted_deadline)
    };
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
        "native UI operation crossed complete Main or persistent-resource custody",
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
        "native UI actual factory retirement or complete captured output differs",
    )?;
    owner
        .check_request_deadline()
        .map_err(observation_authority_error)?;
    request.validate().map_err(external)?;
    crate::production_host_admission::check_observation_before(admitted_deadline)?;
    // A real nonzero exit is retained verbatim for the existing operation journal.
    Ok(NativeUiObservation {
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
    fn calendar_counts_traceexec_profile_requires_independent_guest_and_original_art() {
        let command = GatewayCommand::CalendarCounts {};
        let profile = native_ui_execution_profile(&command).unwrap();
        assert_eq!(profile.guest_uid, crate::native_calendar_counts::OBSERVER_UID);
        assert_eq!(domain(&command), OperationDomain::CalendarCounts);
        assert_eq!(profile.process_selinux, OperationDomain::CalendarCounts.context());
        assert_eq!(profile.executable_selinux, "u:object_r:droidloom_provider_exec:s0");
        assert_eq!(profile.executable_bytes, fixed::INPUTS[2].bytes);
        assert_eq!(profile.executable_sha256, fixed::INPUTS[2].sha256);
        assert!(uses_app_process(&command));
        assert!(!needs_content_jar(&command) && !needs_am_jar(&command));
    }

    #[test]
    fn native_leaf_package_gateway_retains_original_query_and_launch_read_roles() {
        for (command, expected) in [
            (GatewayCommand::PackageIdentity { package: "com.android.contacts".into() },
                OperationDomain::Query),
            (GatewayCommand::PackagePaths { package: "com.android.contacts".into() },
                OperationDomain::Query),
            (GatewayCommand::PackageLauncher { package: "com.android.contacts".into() },
                OperationDomain::LaunchRead),
        ] {
            let actual = native_ui_execution_profile(&command).unwrap();
            assert_eq!(domain(&command), expected);
            assert_eq!(actual.process_selinux, expected.context());
            assert_eq!(actual.guest_uid, 2000);
            assert_eq!(actual.executable_bytes, fixed::INPUTS[0].bytes);
            assert_eq!(actual.executable_sha256, fixed::INPUTS[0].sha256);
            assert_eq!(actual.executable_selinux, "u:object_r:droidloom_query_exec:s0");
            assert!(!uses_app_process(&command));
        }
    }

    #[test]
    fn native_ui_fixed_executable_roles_retain_original_bytes_and_guest_identities() {
        for (command, selected, uid) in [
            (
                GatewayCommand::EntryCheck {
                    check: EntryCheck::GuestUid,
                },
                fixed::INPUTS[1],
                0,
            ),
            (
                GatewayCommand::EntryCheck {
                    check: EntryCheck::BootCompleted,
                },
                fixed::INPUTS[4],
                0,
            ),
            (
                GatewayCommand::TaskRemove { task: 17 },
                fixed::INPUTS[0],
                2000,
            ),
            (
                GatewayCommand::CameraImageRow { row: 19 },
                fixed::INPUTS[2],
                0,
            ),
            (
                GatewayCommand::WindowDisplays {},
                fixed::NATIVE_UI_INPUTS[1],
                0,
            ),
            (
                GatewayCommand::ScreenCapture {},
                fixed::NATIVE_UI_INPUTS[2],
                0,
            ),
            (GatewayCommand::SettingsBack {}, fixed::INPUTS[0], 2000),
            (GatewayCommand::CameraMenu {}, fixed::INPUTS[0], 2000),
        ] {
            let profile = native_ui_execution_profile(&command).unwrap();
            assert_eq!(profile.executable_bytes, selected.bytes);
            assert_eq!(profile.executable_sha256, selected.sha256);
            assert_eq!(profile.guest_uid, uid);
            assert_eq!(domain(&command).guest_uid(), uid);
            assert_eq!(
                profile.process_apparmor,
                "droidloom-production-android (enforce)"
            );
            assert_eq!(
                uses_app_process(&command),
                needs_content_jar(&command) || needs_am_jar(&command)
            );
        }
        assert!(native_ui_execution_profile(&GatewayCommand::TaskRemove { task: 0 }).is_err());
        assert!(
            native_ui_execution_profile(&GatewayCommand::CameraImageRow { row: u64::MAX }).is_err()
        );
    }
}
