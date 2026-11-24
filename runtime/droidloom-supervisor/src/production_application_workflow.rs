//! The two real application owners share the existing closed business flows.
//! The enum cannot be decoded or constructed from a public receipt. Each variant
//! retains its original owner and its corresponding physical framework witness.
use super::*;
use crate::production_selection::early_generation::{
    EarlyApplicationAuthority, EarlyFrameworkObservation,
};
use std::time::Instant;

pub(super) enum Workflow<'borrow, 'owner> {
    Legacy(ReadyTreeWitness<'owner>),
    Early(&'borrow EarlyApplicationAuthority<'owner>),
}
pub(super) enum WorkflowFramework {
    Legacy(FrameworkObservation),
    Early(EarlyFrameworkObservation),
}

fn early_effect<T>(
    authority: &EarlyApplicationAuthority<'_>,
    deadline: Instant,
    effect: impl FnOnce() -> Result<T>,
) -> Result<T> {
    require(
        Instant::now() < deadline,
        "early application workflow deadline",
    )?;
    authority
        .progress_inherited_native(deadline)
        .map_err(external)?;
    authority.ready().map_err(external)?;
    let result = effect();
    // Revalidate even after a rejected operation. Actual retirement failure is
    // preserved by the original owner's monotonic quarantine, never a receipt.
    let after = authority.ready().map_err(external);
    after?;
    require(
        Instant::now() < deadline,
        "early application workflow exceeded deadline",
    )?;
    result
}

impl Workflow<'_, '_> {
    pub(super) fn observe_application_framework(&mut self) -> Result<WorkflowFramework> {
        match self {
            Self::Legacy(ready) => ready
                .observe_application_framework()
                .map(WorkflowFramework::Legacy)
                .map_err(external),
            Self::Early(authority) => authority
                .observe_framework()
                .map(WorkflowFramework::Early)
                .map_err(external),
        }
    }
    pub(super) fn application_epoch(&mut self, held: &WorkflowFramework) -> Result<RuntimeEpoch> {
        match (self, held) {
            (Self::Legacy(ready), WorkflowFramework::Legacy(framework)) => {
                ready.application_epoch(framework).map_err(external)
            }
            (Self::Early(authority), WorkflowFramework::Early(framework)) => {
                authority.epoch(framework).map_err(external)
            }
            _ => Err(reject(
                "application framework witness belongs to another owner kind",
            )),
        }
    }
    pub(super) fn revalidate_application(&mut self) -> Result<()> {
        match self {
            Self::Legacy(ready) => ready.revalidate_application().map_err(external),
            Self::Early(authority) => authority.ready().map_err(external),
        }
    }
    pub(super) fn run_application_read_before(
        &mut self,
        query: &ApplicationRead,
        deadline: Instant,
    ) -> Result<ApplicationReadResult> {
        match self {
            Self::Legacy(ready) => ready
                .run_application_read_before(query, deadline)
                .map_err(external),
            Self::Early(authority) => early_effect(authority, deadline, || {
                run_read_before(*authority, query, deadline)
            }),
        }
    }
    pub(super) fn run_application_browser(
        &mut self,
        command: &BrowserCommand,
        deadline: Instant,
    ) -> Result<BrowserCommandResult> {
        match self {
            Self::Legacy(ready) => ready
                .run_application_browser(command, deadline)
                .map_err(external),
            Self::Early(authority) => early_effect(authority, deadline, || {
                run_browser_command(*authority, command, deadline)
            }),
        }
    }
    pub(super) fn run_application_contacts_read(
        &mut self,
        query: &ContactsQuery,
        deadline: Instant,
    ) -> Result<ContactsReadResult> {
        match self {
            Self::Legacy(ready) => ready
                .run_application_contacts_read(query, deadline)
                .map_err(external),
            Self::Early(authority) => early_effect(authority, deadline, || {
                run_contacts_read(*authority, query, deadline)
            }),
        }
    }
    pub(super) fn run_application_launch(
        &mut self,
        command: &LaunchCommand,
        deadline: Instant,
    ) -> Result<LaunchCommandResult> {
        match self {
            Self::Legacy(ready) => ready
                .run_application_launch(command, deadline)
                .map_err(external),
            Self::Early(authority) => early_effect(authority, deadline, || {
                run_launch_command(*authority, command, deadline)
            }),
        }
    }
    pub(super) fn open_application_task_control(
        &mut self,
        package: &str,
        deadline: Instant,
    ) -> Result<ApplicationTaskControl> {
        match self {
            Self::Legacy(ready) => ready
                .open_application_task_control(package, deadline)
                .map_err(external),
            Self::Early(authority) => early_effect(authority, deadline, || {
                task_control::connect_early(authority, package, deadline)
            }),
        }
    }
    pub(super) fn revalidate_task_control(
        &mut self,
        connection: &ApplicationTaskControl,
        deadline: Instant,
    ) -> Result<()> {
        match self {
            Self::Legacy(ready) => ready
                .revalidate_task_control(connection, deadline)
                .map_err(external),
            Self::Early(authority) => early_effect(authority, deadline, || {
                connection.revalidate_early(authority, deadline)
            }),
        }
    }
    pub(super) fn exchange_task_control(
        &mut self,
        connection: &mut ApplicationTaskControl,
        request: &droidloom_task_control::ControlRequest,
        deadline: Instant,
    ) -> Result<droidloom_task_control::ControlResponse> {
        match self {
            Self::Legacy(ready) => ready
                .exchange_task_control(connection, request, deadline)
                .map_err(external),
            Self::Early(authority) => early_effect(authority, deadline, || {
                connection.exchange_early(authority, request, deadline)
            }),
        }
    }
}
