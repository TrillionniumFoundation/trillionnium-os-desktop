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

struct Inspection<'a, 'owner> {
    ready: &'a mut ReadyTreeWitness<'owner>,
    framework: &'a FrameworkObservation,
    request: &'a LaunchRequest,
    original: Option<&'a ApplicationInspection>,
    reads: &'a mut Vec<ReadReceipt>,
    deadline: Instant,
}

impl AndroidProbe for Inspection<'_, '_> {
    fn epoch(&mut self) -> std::result::Result<RuntimeEpoch, String> {
        require(Instant::now() < self.deadline, "launch inspection deadline")
            .map_err(|e| e.to_string())?;
        let epoch = self
            .ready
            .application_epoch(self.framework)
            .map_err(|e| e.to_string())?;
        require(Instant::now() < self.deadline, "launch inspection deadline")
            .map_err(|e| e.to_string())?;
        Ok(epoch)
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
                .run_application_read_before(&command, self.deadline)
                .map_err(external)?;
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
        result.map_err(|e| e.to_string())
    }
}

struct OwnerLaunch<'a> {
    ready: ReadyTreeWitness<'a>,
    framework: FrameworkObservation,
    request: LaunchRequest,
    original: ApplicationInspection,
    reads: Vec<ReadReceipt>,
    commands: Vec<LaunchCommandResult>,
    connection: ApplicationTaskControl,
    deadline: Instant,
}

impl OwnerLaunch<'_> {
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

impl LaunchEffects for OwnerLaunch<'_> {
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
    mut ready: ReadyTreeWitness<'_>,
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
    let framework = ready.observe_application_framework().map_err(external)?;
    let mut reads = Vec::new();
    let original = {
        let mut probe = Inspection {
            ready: &mut ready,
            framework: &framework,
            request,
            original: None,
            reads: &mut reads,
            deadline,
        };
        crate::control::application_probe::inspect(&mut probe, &request.package, request.user)
            .map_err(external)?
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
            };
            crate::control::application_probe::inspect(&mut probe, &request.package, request.user)
                .map_err(external)?
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
