//! Concrete Ready-owner Launch effects. No receipt, caller FD, path or numeric
//! PID constructs the owner. The production control route supplies the original
//! request deadline; required runtime and MAC checks remain mandatory.
use super::*;
use droidloom_task_control::{ControlRequest, ControlResponse};
use droidloom_task_launcher::effects::{
    AndroidCommand, LAUNCH_LIMIT, LaunchEffects, launch_prepared,
};
use droidloom_task_launcher::{LaunchError, LaunchRequest, TaskBinding};
use std::time::{Duration, Instant};

const READ_LIMIT: usize = 400;
const COMMAND_LIMIT: usize = 256;

pub(crate) struct LaunchObservation {
    pub(crate) binding: TaskBinding,
    pub(crate) application: ApplicationInspection,
    reads: Vec<ReadReceipt>,
    commands: Vec<LaunchCommandResult>,
    bridge: BridgeReceipt,
}

fn retired(receipt: &ReadReceipt) -> bool {
    receipt.cgroup_removed
        && receipt.successful_retirement()
        && receipt.query_waitid_code == libc::CLD_EXITED
}

struct Inspection<'a, 'borrow, 'owner> {
    ready: &'a mut Workflow<'borrow, 'owner>,
    framework: &'a WorkflowFramework,
    request: &'a LaunchRequest,
    original: Option<&'a ApplicationInspection>,
    reads: &'a mut Vec<ReadReceipt>,
    deadline: Instant,
    retirement_unproven: bool,
}

// AndroidProbe returns strings for portability. Retain an actual retirement
// failure separately so that this adapter cannot downgrade broker quarantine.
fn inspection_result<T>(
    result: Result<T>,
    retirement_unproven: &mut bool,
) -> std::result::Result<T, String> {
    if matches!(&result, Err(ApplicationError::RetirementUnproven)) {
        *retirement_unproven = true;
    }
    result.map_err(|error| error.to_string())
}

fn completed_inspection<T>(
    result: std::result::Result<T, String>,
    retirement_unproven: bool,
) -> Result<T> {
    if retirement_unproven {
        Err(ApplicationError::RetirementUnproven)
    } else {
        result.map_err(external)
    }
}

impl Inspection<'_, '_, '_> {
    fn inspect(&mut self) -> Result<ApplicationInspection> {
        let package = self.request.package.clone();
        let user = self.request.user;
        let result = crate::control::application_probe::inspect(self, &package, user);
        completed_inspection(result, self.retirement_unproven)
    }
}

impl AndroidProbe for Inspection<'_, '_, '_> {
    fn epoch(&mut self) -> std::result::Result<RuntimeEpoch, String> {
        let result = (|| {
            require(Instant::now() < self.deadline, "launch inspection deadline")?;
            let epoch = self.ready.application_epoch(self.framework)?;
            require(Instant::now() < self.deadline, "launch inspection deadline")?;
            Ok(epoch)
        })();
        inspection_result(result, &mut self.retirement_unproven)
    }
    fn command(&mut self, args: &[String]) -> std::result::Result<String, String> {
        let result = (|| -> Result<String> {
            require(
                Instant::now() < self.deadline && self.reads.len() < READ_LIMIT,
                "launch inspection bound",
            )?;
            let command = ApplicationRead::from_command(args)?;
            require(
                match &command {
                    ApplicationRead::PackageIdentity { package, user }
                    | ApplicationRead::PackagePaths { package, user } => {
                        *package == self.request.package && *user == self.request.user
                    }
                    ApplicationRead::ApkStat { path } | ApplicationRead::ApkSha256 { path } => {
                        // The initial pure inspection derives these from the real
                        // package manager. The second pass can read only that set.
                        self.original.is_none_or(|original| {
                            original.apks.iter().any(|apk| apk.path == *path)
                        })
                    }
                },
                "launch inspection escaped its package/user/APK set",
            )?;
            let result = self
                .ready
                .run_application_read_before(&command, self.deadline)?;
            require(
                retired(&result.receipt) && result.receipt.query_waitid_status == 0,
                "launch inspection child retirement incomplete",
            )?;
            self.reads.push(result.receipt);
            require(
                Instant::now() < self.deadline,
                "launch inspection completed after deadline",
            )?;
            Ok(result.output)
        })();
        inspection_result(result, &mut self.retirement_unproven)
    }
}

struct OwnerLaunch<'borrow, 'owner> {
    ready: Workflow<'borrow, 'owner>,
    framework: WorkflowFramework,
    request: LaunchRequest,
    original: ApplicationInspection,
    reads: Vec<ReadReceipt>,
    commands: Vec<LaunchCommandResult>,
    connection: ApplicationTaskControl,
    deadline: Instant,
}

impl OwnerLaunch<'_, '_> {
    fn fence(&mut self, request: &LaunchRequest, deadline: Instant) -> Result<()> {
        require(
            *request == self.request && deadline == self.deadline && Instant::now() < deadline,
            "launch request or shared absolute deadline changed",
        )?;
        let epoch = self
            .ready
            .application_epoch(&self.framework)
            .map_err(external)?;
        require(
            epoch == self.original.epoch,
            "launch original framework epoch changed",
        )?;
        self.ready
            .revalidate_task_control(&self.connection, deadline)
            .map_err(external)?;
        require(Instant::now() < deadline, "launch fence exceeded deadline")
    }
}

impl LaunchEffects for OwnerLaunch<'_, '_> {
    fn revalidate(
        &mut self,
        request: &LaunchRequest,
        deadline: Instant,
    ) -> std::result::Result<(), LaunchError> {
        self.fence(request, deadline)
            .map_err(|e| LaunchError::Control(e.to_string()))
    }
    fn android(
        &mut self,
        command: &AndroidCommand,
        deadline: Instant,
    ) -> std::result::Result<std::process::Output, LaunchError> {
        let result = (|| -> Result<std::process::Output> {
            let request = self.request.clone();
            self.fence(&request, deadline)?;
            require(
                self.connection.commands_allowed() && self.commands.len() < COMMAND_LIMIT,
                "launch command before Hello, after binding or above finite count",
            )?;
            let command = LaunchCommand::bind(command, &self.request)?;
            let result = self
                .ready
                .run_application_launch(&command, deadline)
                .map_err(external)?;
            require(
                retired(&result.receipt),
                "launch cmd did not exit normally and retire",
            )?;
            require(
                result.receipt.output_bytes == result.output.stdout.len()
                    && result.stderr_bytes == result.output.stderr.len(),
                "launch output receipt differs",
            )?;
            let output = result.output.clone();
            self.commands.push(result);
            self.fence(&request, deadline)?;
            Ok(output)
        })();
        result.map_err(|e| LaunchError::Control(e.to_string()))
    }
    fn exchange(
        &mut self,
        request: &ControlRequest,
        deadline: Instant,
    ) -> std::result::Result<ControlResponse, LaunchError> {
        let result = self
            .ready
            .exchange_task_control(&mut self.connection, request, deadline);
        result.map_err(|e| LaunchError::Control(e.to_string()))
    }
    fn wait(
        &mut self,
        interval: Duration,
        deadline: Instant,
    ) -> std::result::Result<(), LaunchError> {
        let result = (|| -> Result<()> {
            require(
                interval <= Duration::from_millis(50),
                "launch retry interval bound",
            )?;
            let request = self.request.clone();
            self.fence(&request, deadline)?;
            let until = Instant::now()
                .checked_add(interval)
                .ok_or_else(|| reject("launch wait overflow"))?
                .min(deadline);
            while Instant::now() < until {
                self.fence(&request, deadline)?;
                std::thread::sleep(
                    until
                        .saturating_duration_since(Instant::now())
                        .min(Duration::from_millis(10)),
                );
            }
            self.fence(&request, deadline)
        })();
        result.map_err(|e| LaunchError::Control(e.to_string()))
    }
}

pub(super) fn launch(
    mut ready: Workflow<'_, '_>,
    request: &LaunchRequest,
    deadline: Instant,
) -> Result<LaunchObservation> {
    // The public Launch entry owns this one absolute deadline. Selection and
    // Ready observation already consumed their share; no substep renews it.
    require(
        deadline
            .checked_duration_since(Instant::now())
            .is_some_and(|remaining| !remaining.is_zero() && remaining <= LAUNCH_LIMIT),
        "public Launch deadline expired or exceeds the fixed limit",
    )?;
    LaunchCommand::bind(
        &AndroidCommand::Start {
            request: request.clone(),
        },
        request,
    )?;
    let framework = ready.observe_application_framework()?;
    let mut reads = Vec::new();
    let original = {
        let mut probe = Inspection {
            ready: &mut ready,
            framework: &framework,
            request,
            original: None,
            reads: &mut reads,
            deadline,
            retirement_unproven: false,
        };
        probe.inspect()?
    };
    require(
        !reads.is_empty() && Instant::now() < deadline,
        "launch initial identity observation incomplete",
    )?;
    let connection = ready
        .open_application_task_control(&request.package, deadline)
        .map_err(external)?;
    let mut adapter = OwnerLaunch {
        ready,
        framework,
        request: request.clone(),
        original,
        reads,
        commands: Vec::new(),
        connection,
        deadline,
    };
    let result = (|| -> Result<(TaskBinding, ApplicationInspection)> {
        let binding = launch_prepared(&mut adapter, request, deadline).map_err(external)?;
        adapter.connection.complete()?;
        let observed = {
            let mut probe = Inspection {
                ready: &mut adapter.ready,
                framework: &adapter.framework,
                request,
                original: Some(&adapter.original),
                reads: &mut adapter.reads,
                deadline,
                retirement_unproven: false,
            };
            probe.inspect()?
        };
        require(
            observed == adapter.original
                && adapter.commands.iter().all(|row| retired(&row.receipt)),
            "launch package/UID/version/APK set changed or cmd retirement incomplete",
        )?;
        adapter.fence(request, deadline)?;
        Ok((binding, observed))
    })();
    // Close on both paths. A socket cleanup failure never becomes success,
    // and no second connector or activity is started to conceal it.
    let close = adapter.connection.close();
    let after = adapter.ready.revalidate_application().map_err(external);
    let (binding, application) = match result {
        Ok(value) => value,
        Err(operation) => {
            let close_error = close.err().map(|error| error.to_string());
            let owner_error = after.err().map(|error| error.to_string());
            return if close_error.is_none() && owner_error.is_none() {
                Err(operation)
            } else {
                Err(reject(format!(
                    "launch failed: {operation}; connection close: {close_error:?}; final owner check: {owner_error:?}"
                )))
            };
        }
    };
    let bridge = close?;
    after?;
    require(
        Instant::now() < deadline,
        "launch completed after absolute deadline",
    )?;
    Ok(LaunchObservation {
        binding,
        application,
        reads: adapter.reads,
        commands: adapter.commands,
        bridge,
    })
}

pub(super) fn observe_tasks(
    mut ready: Workflow<'_, '_>,
    expected: &ApplicationInspection,
    deadline: Instant,
) -> Result<crate::control::application_tasks::ApplicationTaskSnapshot> {
    use sha2::{Digest, Sha256};
    require(
        deadline
            .checked_duration_since(Instant::now())
            .is_some_and(|remaining| !remaining.is_zero() && remaining <= LAUNCH_LIMIT),
        "task observation deadline expired or exceeds the fixed limit",
    )?;
    let request = LaunchRequest {
        package: expected.package.clone(),
        component: None,
        user: expected.user,
        resolution: None,
    };
    // Only the fixed read command is selected. No task ID, shell, executable,
    // descriptor or launch argument can be provided through this public route.
    let command = LaunchCommand::bind(&AndroidCommand::ListTasks, &request)?;
    let framework = ready.observe_application_framework()?;
    let mut reads = Vec::new();
    let result = (|| {
        let original = {
            let mut probe = Inspection {
                ready: &mut ready,
                framework: &framework,
                request: &request,
                original: None,
                reads: &mut reads,
                deadline,
                retirement_unproven: false,
            };
            probe.inspect()?
        };
        require(
            original == *expected,
            "task observation expected identity or epoch changed",
        )?;
        require(
            ready.application_epoch(&framework)? == original.epoch,
            "task observation framework changed before the read",
        )?;
        let observed = ready.run_application_launch(&command, deadline)?;
        require(
            retired(&observed.receipt)
                && observed.receipt.query_waitid_status == 0
                && observed.output.status.success()
                && observed.output.stderr.is_empty(),
            "task observation command did not exit successfully and retire",
        )?;
        require(
            observed.operation_deadline <= deadline
                && Instant::now() < observed.operation_deadline
                && observed.receipt.output_bytes == observed.output.stdout.len()
                && observed.receipt.output_sha256
                    == format!("{:x}", Sha256::digest(&observed.output.stdout))
                && observed.stderr_bytes == observed.output.stderr.len()
                && observed.stderr_sha256
                    == format!("{:x}", Sha256::digest(&observed.output.stderr)),
            "task observation command output or absolute deadline differs",
        )?;
        require(
            ready.application_epoch(&framework)? == original.epoch,
            "task observation framework changed after the read",
        )?;
        let listing = std::str::from_utf8(&observed.output.stdout).map_err(external)?;
        let snapshot =
            crate::control::application_tasks::parse(&original, listing).map_err(external)?;
        let after = {
            let mut probe = Inspection {
                ready: &mut ready,
                framework: &framework,
                request: &request,
                original: Some(&original),
                reads: &mut reads,
                deadline,
                retirement_unproven: false,
            };
            probe.inspect()?
        };
        require(
            after == original
                && !reads.is_empty()
                && reads
                    .iter()
                    .all(|row| retired(row) && row.query_waitid_status == 0),
            "task observation installed APK identity changed or read retirement incomplete",
        )?;
        require(
            ready.application_epoch(&framework)? == original.epoch,
            "task observation framework changed at completion",
        )?;
        Ok(snapshot)
    })();
    // Preserve the actual owner's retirement failure on both success and error;
    // neither malformed stdout nor an identity mismatch skips the owner check.
    workflow::finish_effect(result, || ready.revalidate_application(), deadline)
}

#[cfg(test)]
mod task_observation_tests {
    use super::*;

    #[test]
    fn actual_retirement_failure_survives_the_string_probe_boundary() {
        let mut quarantined = false;
        let result =
            inspection_result::<()>(Err(ApplicationError::RetirementUnproven), &mut quarantined);
        assert!(quarantined);
        assert!(matches!(
            completed_inspection(result, quarantined),
            Err(ApplicationError::RetirementUnproven)
        ));
        // A later parser error or successful callback cannot erase that state.
        assert!(inspection_result(Ok(()), &mut quarantined).is_ok());
        assert!(matches!(
            completed_inspection::<()>(Err("secondary parser failure".into()), quarantined),
            Err(ApplicationError::RetirementUnproven)
        ));
    }

    #[test]
    fn ordinary_inspection_errors_do_not_invent_retirement_failure() {
        let mut quarantined = false;
        let result = inspection_result::<()>(Err(reject("different package")), &mut quarantined);
        assert!(!quarantined);
        assert!(matches!(
            completed_inspection(result, quarantined),
            Err(ApplicationError::Rejected(_))
        ));
        assert!(completed_inspection(Ok(()), quarantined).is_ok());
    }
}
