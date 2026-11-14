//! Normal production lifecycle. Every owner stays on the broker's one thread.
//!
//! The preparation chain is real, but its entry first requires an execution
//! capability that cannot currently be issued. No development runtime is
//! adopted, no user-data image is mounted, and Prepared never means Running.

use std::fmt;
use std::time::{Duration, Instant};

use thiserror::Error;

use crate::CellSpec;
use crate::production_devices::PreparedDevices;
use crate::production_execution::ExecutionAdmission;
use crate::production_host_admission::HostAdmission;
use crate::production_identity::IdentityAuthority;
use crate::production_mounts::{PreparedMounts, VerifiedCohort};
use crate::production_namespace::{
    ExecutedNamespaces, IsolatedNamespaces, TreeExit, prepare_admitted_user_namespace,
};
use crate::production_readiness::BootProperty;
use crate::production_runtime_assets::PreparedRuntime;
use crate::production_selection::ProductionSelection;

const PREPARATION_LIMIT: Duration = Duration::from_secs(120);

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
        let execution = ExecutionAdmission::acquire(&selection).map_err(|error| StartFailure {
            error: rejected(error),
            retirement_requires_review: false,
        })?;
        execution
            .revalidate(&selection)
            .map_err(|error| StartFailure {
                error: rejected(error),
                retirement_requires_review: false,
            })?;
        let authority =
            IdentityAuthority::inspect(selection.spec()).map_err(|error| StartFailure {
                error: rejected(error),
                retirement_requires_review: false,
            })?;
        // Acquire the exact selected reservation only after actual execution
        // contracts exist. No disposable fixture is reserved for host UID1000.
        let lease = authority
            .reserve(selection.spec(), selection.base_cohort())
            .map_err(|error| StartFailure {
                error: rejected(error),
                retirement_requires_review: false,
            })?;
        let began = Instant::now();
        let admitted: Result<ExecutedNamespaces> = (|| {
            let step = |text| -> Result<()> {
                if began.elapsed() >= PREPARATION_LIMIT {
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
            // This operation moves only the attested keeper and delegates the
            // private hierarchy. It does not qualify Android task profiles.
            // The separately required execution contracts still cover their
            // guest-side activation and final confinement.
            tree.configure_cgroup_hierarchy().map_err(rejected)?;

            step("Preparing the selected same-cohort runtime inputs...")?;
            let runtime = PreparedRuntime::prepare(
                &tree.witness().map_err(rejected)?,
                selection.runtime_manifest(),
            )
            .map_err(rejected)?;
            let tree = tree.attach_runtime(runtime).map_err(rejected)?;
            step("Checking the final Android execution boundary...")?;
            tree.execute_runtime(&selection, &execution)
                .map_err(rejected)
        })();
        let tree = admitted.map_err(|error| StartFailure {
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
}
