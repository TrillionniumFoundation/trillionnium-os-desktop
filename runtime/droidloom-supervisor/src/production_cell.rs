//! Normal production lifecycle. Every owner stays on the broker's one thread.
//!
//! Preparation first observes the actual installed MAC provider, then binds
//! the exact original systemd/cgroup owner before arming init. A separate final
//! activation gate remains required for Running and every application query.
//! No development runtime or previously recorded qualification is adopted.

use std::fmt;
use std::time::Instant;

use thiserror::Error;

use crate::CellSpec;
use crate::production_devices::PreparedDevices;
use crate::production_execution::{ExecutionAdmission, PreparationAdmission};
use crate::production_host_admission::HostAdmission;
use crate::production_identity::IdentityAuthority;
use crate::production_mounts::{PreparedMounts, VerifiedCohort};
use crate::production_namespace::{
    ExecutedNamespaces, IsolatedNamespaces, TreeExit, prepare_admitted_user_namespace,
};
use crate::production_readiness::BootProperty;
use crate::production_runtime_assets::PreparedRuntime;
use crate::production_selection::ProductionSelection;

#[derive(Debug, Error)]
pub(crate) enum CellError {
    #[error("production cell: {0}")]
    Rejected(String),
    #[error("production preparation exceeded its bounded deadline")]
    Deadline,
    #[error("production child/resource retirement was not proven: {0}")]
    Retirement(String),
}

type Result<T> = std::result::Result<T, CellError>;

fn rejected(error: impl fmt::Display) -> CellError {
    CellError::Rejected(error.to_string())
}

/// This is a controller fence, not a cleanup capability. An error after host
/// admission begins can include a worker/child whose Drop quarantined its
/// resources. Such an error cannot be reported as Stopped or retried silently.
pub(crate) struct StartFailure {
    pub(crate) error: CellError,
    pub(crate) retirement_requires_review: bool,
}

pub(crate) enum CellPoll {
    Live(BootProperty),
    Exited(TreeExit),
    FailedAfterRetirement { message: String, exit: TreeExit },
}

/// Contains IsolatedNamespaces through ExecutedNamespaces, so it cannot be
/// sent to another thread. All signal, wait, mount and lease custody remains
/// with the same owner that performed the original clone3 operations.
pub(crate) struct ProductionCell {
    selection: ProductionSelection,
    execution: ExecutionAdmission,
    tree: Option<ExecutedNamespaces>,
}

impl ProductionCell {
    pub(crate) fn start(
        selection: ProductionSelection,
        report: impl Fn(&str),
    ) -> std::result::Result<Self, StartFailure> {
        let preparation =
            PreparationAdmission::acquire(&selection).map_err(|error| StartFailure {
                error: rejected(error),
                retirement_requires_review: false,
            })?;
        preparation
            .revalidate(&selection)
            .map_err(|error| StartFailure {
                error: rejected(error),
                retirement_requires_review: false,
            })?;
        let deadline = preparation.deadline();
        let authority =
            IdentityAuthority::inspect(selection.spec()).map_err(|error| StartFailure {
                error: rejected(error),
                retirement_requires_review: false,
            })?;
        preparation
            .revalidate(&selection)
            .map_err(|error| StartFailure {
                error: rejected(error),
                retirement_requires_review: false,
            })?;
        // Reserve only after actual live MAC preflight. This is bounded
        // preparation, not completed Android activation or application Ready.
        let lease = authority
            .reserve(selection.spec(), selection.base_cohort())
            .map_err(|error| StartFailure {
                error: rejected(error),
                retirement_requires_review: false,
            })?;
        let admitted: Result<(ExecutedNamespaces, ExecutionAdmission)> = (|| {
            let step = |text| -> Result<()> {
                if Instant::now() >= deadline {
                    return Err(CellError::Deadline);
                }
                selection.revalidate().map_err(rejected)?;
                report(text);
                Ok(())
            };
            step("Checking production host admission and its owned resource budget...")?;
            let admission = HostAdmission::acquire(lease).map_err(rejected)?;
            let mapped = prepare_admitted_user_namespace(admission).map_err(rejected)?;
            let tree = IsolatedNamespaces::from_mapped(mapped).map_err(rejected)?;
            step("Checking MAC for the original systemd lifetime owner...")?;
            let prepared = preparation
                .bind_tree(&selection, &tree.witness().map_err(rejected)?)
                .map_err(rejected)?;

            step("Preparing the selected immutable Android bases...")?;
            let bases = {
                let witness = tree.witness().map_err(rejected)?;
                let verified = VerifiedCohort::load(&witness).map_err(rejected)?;
                PreparedMounts::prepare(&witness, verified).map_err(rejected)?
            };
            let tree = tree.attach_empty_base(bases).map_err(rejected)?;

            step("Preparing private device and process filesystems...")?;
            let devices =
                PreparedDevices::prepare(&tree.witness().map_err(rejected)?).map_err(rejected)?;
            let tree = tree.attach_private_devices(devices).map_err(rejected)?;
            let tree = tree.prepare_process_filesystems().map_err(rejected)?;
            let tree = tree.prepare_private_binder().map_err(rejected)?;
            let tree = tree.prepare_writable_proc().map_err(rejected)?;

            step("Checking the exact owned cgroup hierarchy...")?;
            // This operation moves only the attested keeper, delegates the
            // private hierarchy and verifies PID1's actual init leaf before
            // enabling its controllers. It does not qualify Android task profiles.
            // The later final admission still requires guest-side task
            // profiles and actual final confinement after init execution.
            tree.configure_cgroup_hierarchy().map_err(rejected)?;

            step("Preparing the selected same-cohort runtime inputs...")?;
            let runtime = PreparedRuntime::prepare(
                &tree.witness().map_err(rejected)?,
                selection.runtime_manifest(),
            )
            .map_err(rejected)?;
            let tree = tree.attach_runtime(runtime).map_err(rejected)?;
            step("Checking the final Android execution boundary...")?;
            let mut tree = tree
                .execute_runtime(&selection, &prepared)
                .map_err(rejected)?;
            step("Observing original init and complete Android activation...")?;
            let execution = {
                let init = tree.init_witness(&selection, &prepared).map_err(rejected)?;
                let observed = prepared.observe_init(&init).map_err(rejected)?;
                ExecutionAdmission::acquire(&selection, observed, &init).map_err(rejected)?
            };
            execution.revalidate(&selection).map_err(rejected)?;
            Ok((tree, execution))
        })();
        let (tree, execution) = admitted.map_err(|error| StartFailure {
            error,
            // Every consuming tree method attempts its real retirement on
            // error. Until a full result is returned, the controller does not
            // infer that Drop proved it; it keeps the session fenced.
            retirement_requires_review: true,
        })?;
        Ok(Self {
            selection,
            execution,
            tree: Some(tree),
        })
    }

    pub(crate) fn spec(&self) -> &CellSpec {
        self.selection.spec()
    }

    pub(crate) fn same_selection(&self, selection: &ProductionSelection) -> bool {
        self.selection.same_selection(selection)
    }

    pub(crate) fn host_pid(&self) -> Option<u32> {
        self.tree.as_ref().map(ExecutedNamespaces::host_pid)
    }

    pub(crate) fn poll(&mut self) -> Result<CellPoll> {
        let tree = self
            .tree
            .as_mut()
            .ok_or_else(|| CellError::Rejected("owned tree was already retired".into()))?;
        let observation = match tree.termination_observed() {
            Ok(true) => return self.stop().map(CellPoll::Exited),
            Ok(false) => tree.readiness(&self.selection, &self.execution),
            Err(error) => Err(error),
        };
        match observation {
            Ok(property) => Ok(CellPoll::Live(property)),
            Err(error) => {
                let message = error.to_string();
                let exit = self.stop()?;
                Ok(CellPoll::FailedAfterRetirement { message, exit })
            }
        }
    }

    pub(crate) fn stop(&mut self) -> Result<TreeExit> {
        let tree = self.tree.take().ok_or_else(|| {
            CellError::Retirement("owned tree was already consumed by retirement".into())
        })?;
        tree.retire()
            .map_err(|error| CellError::Retirement(error.to_string()))
    }

    pub(crate) fn inspect_application(
        &mut self,
        package: &str,
        user: u32,
    ) -> Result<crate::control::application_probe::ApplicationInspection> {
        let tree = self
            .tree
            .as_mut()
            .ok_or_else(|| rejected("production owner was retired"))?;
        let ready = tree
            .ready_witness(&self.selection, &self.execution)
            .map_err(rejected)?
            .ok_or_else(|| {
                rejected("production application inspection requires actual current readiness")
            })?;
        crate::production_application::inspect(ready, package, user).map_err(rejected)
    }
    pub(crate) fn open_browser(
        &mut self,
        expected: &crate::control::application_probe::ApplicationInspection,
        url: &str,
    ) -> Result<(
        crate::control::application_probe::ApplicationInspection,
        String,
    )> {
        let tree = self
            .tree
            .as_mut()
            .ok_or_else(|| rejected("production owner was retired"))?;
        let ready = tree
            .ready_witness(&self.selection, &self.execution)
            .map_err(rejected)?
            .ok_or_else(|| rejected("production browser requires actual current readiness"))?;
        crate::production_application::open_browser(ready, expected, url).map_err(rejected)
    }
}
