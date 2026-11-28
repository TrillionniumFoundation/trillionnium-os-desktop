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

fn namespace_error(error: crate::production_namespace::NamespaceError) -> ApplicationError {
    match error {
        crate::production_namespace::NamespaceError::RetirementUnproven => {
            ApplicationError::RetirementUnproven
        }
        error => external(error),
    }
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
        .map_err(namespace_error)?;
    authority.ready().map_err(namespace_error)?;
    finish_effect(
        effect(),
        || authority.ready().map_err(namespace_error),
        deadline,
    )
}

/// Always perform the original owner's postcheck, while preserving an actual
/// unproven child retirement above a secondary ready/deadline rejection.
pub(super) fn finish_effect<T>(
    result: Result<T>,
    postcheck: impl FnOnce() -> Result<()>,
    deadline: Instant,
) -> Result<T> {
    let after = postcheck();
    if matches!(&result, Err(ApplicationError::RetirementUnproven))
        || matches!(&after, Err(ApplicationError::RetirementUnproven))
    {
        return Err(ApplicationError::RetirementUnproven);
    }
    after?;
    require(
        Instant::now() < deadline,
        "early application workflow exceeded deadline",
    )?;
    result
}

impl Workflow<'_, '_> {
    pub(super) fn observe_gallery_image(
        &mut self,
        deadline: Instant,
    ) -> Result<(
        crate::production_mounts::custody::ObservedGalleryImage,
        crate::control::application_custody::CustodyOwner,
    )> {
        match self {
            Self::Legacy(ready) => ready
                .observe_gallery_image(deadline)
                .map_err(namespace_error),
            Self::Early(authority) => early_effect(authority, deadline, || {
                authority
                    .observe_gallery_image(deadline)
                    .map_err(namespace_error)
            }),
        }
    }
    pub(super) fn complete_gallery_image(
        &mut self,
        image: &mut crate::production_mounts::custody::ObservedGalleryImage,
        owner: &crate::control::application_custody::CustodyOwner,
        deadline: Instant,
    ) -> Result<()> {
        match self {
            Self::Legacy(ready) => ready
                .complete_gallery_image(image, owner, deadline)
                .map_err(namespace_error),
            Self::Early(authority) => early_effect(authority, deadline, || {
                authority
                    .complete_gallery_image(image, owner, deadline)
                    .map_err(namespace_error)
            }),
        }
    }
    pub(super) fn revalidate_gallery_image(
        &mut self,
        image: &crate::production_mounts::custody::ObservedGalleryImage,
        owner: &crate::control::application_custody::CustodyOwner,
        deadline: Instant,
    ) -> Result<()> {
        match self {
            Self::Legacy(ready) => ready
                .revalidate_gallery_image(image, owner, deadline)
                .map_err(namespace_error),
            Self::Early(authority) => early_effect(authority, deadline, || {
                authority
                    .revalidate_gallery_image(image, owner, deadline)
                    .map_err(namespace_error)
            }),
        }
    }
    pub(super) fn observe_application_framework(&mut self) -> Result<WorkflowFramework> {
        match self {
            Self::Legacy(ready) => ready
                .observe_application_framework()
                .map(WorkflowFramework::Legacy)
                .map_err(namespace_error),
            Self::Early(authority) => authority
                .observe_framework()
                .map(WorkflowFramework::Early)
                .map_err(namespace_error),
        }
    }
    pub(super) fn application_epoch(&mut self, held: &WorkflowFramework) -> Result<RuntimeEpoch> {
        match (self, held) {
            (Self::Legacy(ready), WorkflowFramework::Legacy(framework)) => {
                ready.application_epoch(framework).map_err(namespace_error)
            }
            (Self::Early(authority), WorkflowFramework::Early(framework)) => {
                authority.epoch(framework).map_err(namespace_error)
            }
            _ => Err(reject(
                "application framework witness belongs to another owner kind",
            )),
        }
    }
    pub(super) fn revalidate_application(&mut self) -> Result<()> {
        match self {
            Self::Legacy(ready) => ready.revalidate_application().map_err(namespace_error),
            Self::Early(authority) => authority.ready().map_err(namespace_error),
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
                .map_err(namespace_error),
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
                .map_err(namespace_error),
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
                .map_err(namespace_error),
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
                .map_err(namespace_error),
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
                .map_err(namespace_error),
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
                .map_err(namespace_error),
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
                .map_err(namespace_error),
            Self::Early(authority) => early_effect(authority, deadline, || {
                connection.exchange_early(authority, request, deadline)
            }),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn actual_namespace_retirement_failure_keeps_its_quarantine_type() {
        assert!(matches!(
            namespace_error(crate::production_namespace::NamespaceError::RetirementUnproven),
            ApplicationError::RetirementUnproven
        ));
        assert!(matches!(
            namespace_error(crate::production_namespace::NamespaceError::Rejected(
                "changed owner"
            )),
            ApplicationError::Rejected(_)
        ));
    }
    #[test]
    fn actual_retirement_failure_survives_postcheck_and_deadline_without_skipping_postcheck() {
        use std::cell::Cell;
        use std::time::Duration;
        let checked = Cell::new(false);
        let result: Result<()> = finish_effect(
            Err(ApplicationError::RetirementUnproven),
            || {
                checked.set(true);
                Err(reject("secondary ready rejection"))
            },
            Instant::now() - Duration::from_secs(1),
        );
        assert!(checked.get());
        assert!(matches!(result, Err(ApplicationError::RetirementUnproven)));
        let result = finish_effect(
            Ok(7),
            || Err(ApplicationError::RetirementUnproven),
            Instant::now() - Duration::from_secs(1),
        );
        assert!(matches!(result, Err(ApplicationError::RetirementUnproven)));
        assert!(finish_effect(Ok(7), || Ok(()), Instant::now() - Duration::from_secs(1)).is_err());
        assert_eq!(
            finish_effect(Ok(7), || Ok(()), Instant::now() + Duration::from_secs(1)).unwrap(),
            7
        );
    }
}
