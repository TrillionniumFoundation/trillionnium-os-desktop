//! Separate the live preparation boundary from completed Android activation.
//!
//! Preparing an owned tree requires the actual installed MAC provider. Arming
//! its original init additionally requires the actual systemd lifetime owner.
//! Neither capability is an Android Ready capability. Only the later actual
//! init/APEX/linkerconfig, task-profile and final-exec providers can complete
//! ExecutionAdmission; those remaining contracts are still uninhabited.

use std::rc::Rc;
use std::time::{Duration, Instant};

use thiserror::Error;

use crate::production_devices::PreparedActivationDevices;
use crate::production_mac::{MacInitWitness, MacPreflight, MacSystemdWitness};
use crate::production_namespace::{ExecutedInitWitness, OwnedNamespaceWitness};
use crate::production_selection::ProductionSelection;

#[path = "production_execution_capabilities.rs"]
mod capabilities;
use capabilities::FinalExecutionObservation;

#[path = "production_execution_threads.rs"]
mod threads;
use threads::InitThreadPlacementObservation;

const PREPARATION_LIMIT: Duration = Duration::from_secs(120);

#[derive(Debug, Error)]
pub(crate) enum ExecutionError {
    #[error(
        "production activation is not qualified: actual init/APEX/linkerconfig activation, guest cgroup profiles and final capability/seccomp contracts are incomplete"
    )]
    Unqualified,
    #[error("production execution selection changed: {0}")]
    Selection(String),
    #[error("production execution identity changed: {0}")]
    Identity(String),
    #[error("production execution MAC observation failed: {0}")]
    Mac(String),
    #[error("production execution kernel-state observation failed: {0}")]
    KernelState(String),
    #[error("production activation device preparation failed: {0}")]
    Devices(String),
    #[error("production original-linkerconfig activation failed: {0}")]
    Activation(String),
    #[error("production preparation exceeded its original bounded deadline")]
    Deadline,
}

type Result<T> = std::result::Result<T, ExecutionError>;

fn before(deadline: Instant) -> Result<()> {
    if Instant::now() >= deadline {
        Err(ExecutionError::Deadline)
    } else {
        Ok(())
    }
}

/// This value retains the actual same-thread MAC provider, not a declaration
/// that it was installed or a result copied from an earlier qualification.
struct LivePreflight {
    host_uid: u32,
    base_cohort: String,
    runtime_manifest: String,
    mac: MacPreflight,
    selection: ProductionSelection,
}

impl LivePreflight {
    fn revalidate(&self, selection: &ProductionSelection) -> Result<()> {
        if !std::ptr::eq(selection, &self.selection) {
            return Err(ExecutionError::Selection(
                "MAC and selection must remain the original inseparable owner".into(),
            ));
        }
        selection
            .revalidate()
            .map_err(|error| ExecutionError::Selection(error.to_string()))?;
        if self.host_uid != selection.spec().host_uid
            || self.base_cohort != selection.base_cohort()
            || self.runtime_manifest != selection.runtime_manifest()
        {
            return Err(ExecutionError::Selection(
                "execution observation is not for this exact selection".into(),
            ));
        }
        self.mac
            .revalidate(selection)
            .map_err(|error| ExecutionError::Mac(error.to_string()))
    }

    fn revalidate_tree(
        &self,
        selection: &ProductionSelection,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        self.revalidate(selection)?;
        witness
            .revalidate_live_admission()
            .map_err(|error| ExecutionError::Identity(error.to_string()))?;
        let lease = witness
            .identity_lease()
            .map_err(|error| ExecutionError::Identity(error.to_string()))?;
        if lease.host_uid() != self.host_uid || lease.broker_cohort() != self.base_cohort {
            return Err(ExecutionError::Identity(
                "execution observation and actual owner reservation differ".into(),
            ));
        }
        self.revalidate(selection)
    }

    fn revalidate_manager(
        &self,
        selection: &ProductionSelection,
        witness: &OwnedNamespaceWitness<'_>,
        manager: &MacSystemdWitness,
    ) -> Result<()> {
        self.revalidate_tree(selection, witness)?;
        let owner = witness
            .systemd_owner(selection)
            .map_err(|error| ExecutionError::Identity(error.to_string()))?;
        manager
            .revalidate(&self.mac, &owner)
            .map_err(|error| ExecutionError::Mac(error.to_string()))?;
        self.revalidate_tree(selection, witness)
    }
}

/// One immutable pair of the original acquired provider and original selected
/// inputs. Cloning this private handle keeps those exact objects alive; it
/// never reacquires a provider, reconstructs a selection, or changes an epoch.
/// Rc also prevents ownership from crossing a thread.
#[derive(Clone)]
pub(crate) struct RuntimeMacOwner {
    live: Rc<LivePreflight>,
}

impl std::fmt::Debug for RuntimeMacOwner {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("RuntimeMacOwner").finish_non_exhaustive()
    }
}

impl RuntimeMacOwner {
    pub(crate) fn selection(&self) -> &ProductionSelection {
        &self.live.selection
    }

    pub(crate) fn objects(&self) -> Result<(&MacPreflight, &ProductionSelection)> {
        self.live.revalidate(&self.live.selection)?;
        Ok((&self.live.mac, &self.live.selection))
    }

    pub(crate) fn require_pair(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        if !std::ptr::eq(mac, &self.live.mac) || !std::ptr::eq(selection, &self.live.selection) {
            return Err(ExecutionError::Selection(
                "private resource cannot substitute either original MAC/selection object".into(),
            ));
        }
        self.live.revalidate(selection)
    }
}

/// Permits only the bounded construction of the selected original owned
/// resources. There is no PID, profile, installed-result or bool constructor.
/// It cannot arm init, observe Ready, or authorize an application operation.
pub(crate) struct PreparationAdmission {
    live: Rc<LivePreflight>,
    deadline: Instant,
}

impl PreparationAdmission {
    pub(crate) fn acquire(selection: ProductionSelection) -> Result<Self> {
        let deadline = Instant::now() + PREPARATION_LIMIT;
        selection
            .revalidate()
            .map_err(|error| ExecutionError::Selection(error.to_string()))?;
        before(deadline)?;
        let mac = MacPreflight::acquire(&selection)
            .map_err(|error| ExecutionError::Mac(error.to_string()))?;
        let value = Self {
            live: Rc::new(LivePreflight {
                host_uid: selection.spec().host_uid,
                base_cohort: selection.base_cohort().into(),
                runtime_manifest: selection.runtime_manifest().into(),
                mac,
                selection,
            }),
            deadline,
        };
        value.revalidate(&value.live.selection)?;
        Ok(value)
    }

    pub(crate) fn owner(&self) -> RuntimeMacOwner {
        RuntimeMacOwner {
            live: Rc::clone(&self.live),
        }
    }

    pub(crate) fn deadline(&self) -> Instant {
        self.deadline
    }

    pub(crate) fn revalidate(&self, selection: &ProductionSelection) -> Result<()> {
        before(self.deadline)?;
        self.live.revalidate(selection)?;
        before(self.deadline)
    }

    /// Borrow the manager already retained by this exact budgeted namespace
    /// owner. This does not open a replacement connection or adopt a manager.
    pub(crate) fn bind_tree(
        self,
        selection: &ProductionSelection,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<PreparedExecution> {
        self.revalidate(selection)?;
        self.live.revalidate_tree(selection, witness)?;
        let owner = witness
            .systemd_owner(selection)
            .map_err(|error| ExecutionError::Identity(error.to_string()))?;
        let manager = self
            .live
            .mac
            .observe_systemd_owner(&owner)
            .map_err(|error| ExecutionError::Mac(error.to_string()))?;
        let value = PreparedExecution {
            live: self.live,
            manager,
            deadline: self.deadline,
        };
        value.revalidate_tree(selection, witness)?;
        Ok(value)
    }
}

/// A pre-exec observation of the exact live MAC and manager owner. A separate
/// exact-image runtime profile selects the raw child's fixed subordinate-
/// userns capability boundary. The private zero-capability probe is unrelated.
pub(crate) struct PreparedExecution {
    live: Rc<LivePreflight>,
    manager: MacSystemdWitness,
    deadline: Instant,
}

impl PreparedExecution {
    pub(crate) fn runtime_mac_owner(
        &self,
        selection: &ProductionSelection,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<RuntimeMacOwner> {
        self.revalidate_tree(selection, witness)?;
        Ok(RuntimeMacOwner {
            live: Rc::clone(&self.live),
        })
    }

    pub(crate) fn deadline(&self) -> Instant {
        self.deadline
    }

    /// Borrow only the actual provider after revalidating this selected,
    /// executed original init. The activation coordinator cannot manufacture
    /// a policy approval from an input declaration or a recorded result.
    pub(crate) fn activation_mac<'a>(
        &'a self,
        init: &ExecutedInitWitness<'_>,
    ) -> Result<&'a MacPreflight> {
        self.revalidate_tree(
            init.selection(),
            &init
                .namespace_witness()
                .map_err(|error| ExecutionError::Identity(error.to_string()))?,
        )?;
        let actual = self
            .live
            .mac
            .observe_init(init)
            .map_err(|error| ExecutionError::Mac(error.to_string()))?;
        actual
            .revalidate(&self.live.mac, init)
            .map_err(|error| ExecutionError::Mac(error.to_string()))?;
        before(self.deadline)?;
        Ok(&self.live.mac)
    }

    /// Build the fixed listener on this actual owner's new DEV before its
    /// idmap/transfer. The MAC provider stays with this same prepared owner;
    /// no policy string or caller socket can replace it.
    pub(crate) fn prepare_activation_devices(
        &self,
        selection: &ProductionSelection,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<PreparedActivationDevices> {
        self.revalidate_tree(selection, witness)?;
        let context = self.runtime_mac_owner(selection, witness)?;
        let devices =
            PreparedActivationDevices::prepare(witness, selection, &self.live.mac, context)
                .map_err(|error| ExecutionError::Devices(error.to_string()))?;
        self.revalidate_tree(selection, witness)?;
        Ok(devices)
    }

    pub(crate) fn activation_device_transfer<'a>(
        &self,
        devices: &'a mut PreparedActivationDevices,
        selection: &ProductionSelection,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<std::os::fd::BorrowedFd<'a>> {
        self.revalidate_tree(selection, witness)?;
        devices
            .descriptor_for_transfer(witness, selection, &self.live.mac)
            .map_err(|error| ExecutionError::Devices(error.to_string()))
    }

    pub(crate) fn revalidate_tree(
        &self,
        selection: &ProductionSelection,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        before(self.deadline)?;
        self.live
            .revalidate_manager(selection, witness, &self.manager)?;
        before(self.deadline)
    }

    /// Consume preparation only after the normal owner has observed the real
    /// ExecArmed/CLOEXEC/original-ELF boundary. The init borrow cannot be made
    /// from caller-supplied process numbers, descriptors or stored records.
    pub(crate) fn observe_init(self, init: &ExecutedInitWitness<'_>) -> Result<ObservedExecution> {
        self.revalidate_tree(
            init.selection(),
            &init
                .namespace_witness()
                .map_err(|error| ExecutionError::Identity(error.to_string()))?,
        )?;
        let init_mac = self
            .live
            .mac
            .observe_init(init)
            .map_err(|error| ExecutionError::Mac(error.to_string()))?;
        let final_state = FinalExecutionObservation::observe(init)
            .map_err(|error| ExecutionError::KernelState(error.to_string()))?;
        let thread_placement = InitThreadPlacementObservation::observe(init)
            .map_err(|error| ExecutionError::KernelState(error.to_string()))?;
        self.revalidate_tree(
            init.selection(),
            &init
                .namespace_witness()
                .map_err(|error| ExecutionError::Identity(error.to_string()))?,
        )?;
        let value = ObservedExecution {
            live: self.live,
            manager: self.manager,
            init: init_mac,
            final_state,
            thread_placement,
            preparation_deadline: self.deadline,
        };
        value.revalidate_init(init)?;
        before(value.preparation_deadline)?;
        Ok(value)
    }
}

/// Actual executed-init MAC observation. This is still neither complete
/// APEX/linkerconfig activation nor permission to inspect applications.
pub(crate) struct ObservedExecution {
    live: Rc<LivePreflight>,
    manager: MacSystemdWitness,
    init: MacInitWitness,
    final_state: FinalExecutionObservation,
    thread_placement: InitThreadPlacementObservation,
    preparation_deadline: Instant,
}

impl ObservedExecution {
    fn revalidate_init(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        self.live.revalidate_manager(
            init.selection(),
            &init
                .namespace_witness()
                .map_err(|error| ExecutionError::Identity(error.to_string()))?,
            &self.manager,
        )?;
        self.init
            .revalidate(&self.live.mac, init)
            .map_err(|error| ExecutionError::Mac(error.to_string()))?;
        self.final_state
            .revalidate(init)
            .map_err(|error| ExecutionError::KernelState(error.to_string()))?;
        self.thread_placement
            .revalidate(init)
            .map_err(|error| ExecutionError::KernelState(error.to_string()))
    }
}

// The final contracts remain uninhabited, including in test builds. They need
// actual activation, task-profile and final-exec providers; no declaration,
// component fixture or added bool may make an unexecuted Android tree Ready.
enum VerifiedExecutionContracts {}

pub(crate) struct ExecutionAdmission {
    observed: ObservedExecution,
    contracts: VerifiedExecutionContracts,
}

impl ExecutionAdmission {
    /// This final gate is deliberately reached after actual original init
    /// observation. Its missing activation providers are not preconditions
    /// for creating that same init, and preparation cannot replace them.
    pub(crate) fn acquire(
        selection: &ProductionSelection,
        observed: ObservedExecution,
        init: &ExecutedInitWitness<'_>,
    ) -> Result<Self> {
        before(observed.preparation_deadline)?;
        observed.live.revalidate(selection)?;
        observed.revalidate_init(init)?;
        init.revalidate_linkerconfig_completion()
            .map_err(|error| ExecutionError::Activation(error.to_string()))?;
        before(observed.preparation_deadline)?;
        init.observe_pre_ready_input_threads(observed.preparation_deadline)
            .map_err(|error| ExecutionError::KernelState(error.to_string()))?;
        before(observed.preparation_deadline)?;
        Err(ExecutionError::Unqualified)
    }

    pub(crate) fn revalidate(&self, selection: &ProductionSelection) -> Result<()> {
        self.observed.live.revalidate(selection)?;
        match self.contracts {}
    }

    pub(crate) fn revalidate_tree(
        &self,
        selection: &ProductionSelection,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<()> {
        self.observed
            .live
            .revalidate_manager(selection, witness, &self.observed.manager)?;
        self.revalidate(selection)
    }

    pub(crate) fn revalidate_init(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        self.observed.revalidate_init(init)?;
        self.revalidate(init.selection())
    }
}
