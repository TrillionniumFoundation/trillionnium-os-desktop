//! The production execution gate, separate from configuration and preparation.
//!
//! A selected manifest, an ordinary test, or a successful private probe cannot
//! issue this capability. The current tree has no implementation that can
//! construct VerifiedExecutionContracts. AndroidUnqualified also remains the
//! raw-child final-capability profile. The normal daemon therefore rejects
//! Start before creating a durable reservation or any owned child.

use thiserror::Error;

use crate::production_namespace::OwnedNamespaceWitness;
use crate::production_selection::ProductionSelection;

#[derive(Debug, Error)]
pub(crate) enum ExecutionError {
    #[error(
        "production execution is not qualified: guest MAC, init/APEX activation, guest cgroup profiles and final capability/seccomp contracts are incomplete"
    )]
    Unqualified,
    #[error("production execution selection changed: {0}")]
    Selection(String),
    #[error("production execution identity changed: {0}")]
    Identity(String),
}

type Result<T> = std::result::Result<T, ExecutionError>;

// Deliberately uninhabited, including in test builds. A future implementation
// must carry actual non-serializable MAC, activation, cgroup and final-exec
// witnesses here. Adding a bool, digest-only variant or test constructor would
// create authority without those providers and is not an implementation.
enum VerifiedExecutionContracts {}

/// Only this module may construct an execution capability. There is currently
/// no successful constructor, and no public JSON/PID/map/profile input.
pub(crate) struct ExecutionAdmission {
    host_uid: u32,
    base_cohort: String,
    runtime_manifest: String,
    contracts: VerifiedExecutionContracts,
}

impl ExecutionAdmission {
    pub(crate) fn acquire(selection: &ProductionSelection) -> Result<Self> {
        selection
            .revalidate()
            .map_err(|error| ExecutionError::Selection(error.to_string()))?;
        Err(ExecutionError::Unqualified)
    }

    pub(crate) fn revalidate(&self, selection: &ProductionSelection) -> Result<()> {
        selection
            .revalidate()
            .map_err(|error| ExecutionError::Selection(error.to_string()))?;
        if self.host_uid != selection.spec().host_uid
            || self.base_cohort != selection.base_cohort()
            || self.runtime_manifest != selection.runtime_manifest()
        {
            return Err(ExecutionError::Selection(
                "execution capability is not for this exact selection".into(),
            ));
        }
        match self.contracts {}
    }

    pub(crate) fn revalidate_tree(
        &self,
        selection: &ProductionSelection,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        self.revalidate(selection)?;
        let lease = witness
            .identity_lease()
            .map_err(|error| ExecutionError::Identity(error.to_string()))?;
        if lease.host_uid() != self.host_uid || lease.broker_cohort() != self.base_cohort {
            return Err(ExecutionError::Identity(
                "execution capability and actual owner reservation differ".into(),
            ));
        }
        match self.contracts {}
    }
}
