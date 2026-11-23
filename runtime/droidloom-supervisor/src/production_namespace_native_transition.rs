//! The original init's native NEWNS round trip, observed at real syscall stops.
//! Old fixed-namespace witnesses are used only before unshare and after the
//! actual bootstrap restoration. The temporary default epoch has its own
//! complete copied mount graph and retains every original descriptor.
use super::super::original_ptrace::NativeKind;
use super::*;

impl ExecutedNamespaces {
    pub(crate) fn service_original_init_native_namespaces(
        mut self,
        selection: &ProductionSelection,
        prepared: &PreparedExecution,
    ) -> Result<Self> {
        let attempted =
            (|| -> Result<()> {
                self.verify_prepared_exec(selection, prepared)?;
                let mount_owner = self.tree.witness()?;
                let mount_actors = self
                    .tree
                    .runtime
                    .as_ref()
                    .ok_or(NamespaceError::Rejected(
                        "original native actor owner absent",
                    ))?
                    .native_mount_actor_guard(&mount_owner)
                    .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
                let trace = self
                    .tree
                    .original_trace
                    .as_ref()
                    .ok_or(NamespaceError::Rejected("original native observer absent"))?
                    .clone();
                {
                    let original = trace
                        .try_borrow()
                        .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?;
                    original.matches_original(
                        self.tree
                            .init
                            .as_ref()
                            .ok_or(NamespaceError::RetirementUnproven)?,
                    )?;
                    original.matches_deadline(prepared.deadline())?;
                }
                // No notification receiver is started until the actual original
                // syscall entry is stopped. Ordinary calls preserve their native
                // arguments/results and signal delivery under the finite tracer.
                loop {
                    if trace
                        .try_borrow_mut()
                        .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                        .pump_ordinary()?
                    {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(1));
                }
                if trace
                    .try_borrow()
                    .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                    .next_native_kind()?
                    != Some(NativeKind::Unshare)
                {
                    return Err(NamespaceError::Rejected(
                        "original native order requires unshare first",
                    ));
                }
                let snapshot =
                    {
                        let child = self
                            .tree
                            .init
                            .as_ref()
                            .ok_or(NamespaceError::RetirementUnproven)?;
                        let runtime = self.tree.runtime_observation.as_ref().ok_or(
                            NamespaceError::Rejected("original runtime observation absent"),
                        )?;
                        let mounts = self.initial_mounts.try_borrow().map_err(|_| {
                            NamespaceError::Rejected("original mount phase already borrowed")
                        })?;
                        let previous = self.initial_propagation.try_borrow().map_err(|_| {
                            NamespaceError::Rejected("original propagation phase already borrowed")
                        })?;
                        self.initial_storage_binds
                            .try_borrow()
                            .map_err(|_| {
                                NamespaceError::Rejected("original storage phase already borrowed")
                            })?
                            .native_snapshot(&previous, &mounts, runtime, child)?
                    };
                trace
                    .try_borrow_mut()
                    .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                    .begin_unshare(snapshot)?;
                self.tree
                    .apex_notifications
                    .as_ref()
                    .ok_or(NamespaceError::Rejected("original native listener absent"))?
                    .original_native_namespace(prepared.deadline())?
                    .execute_original()?;
                loop {
                    if trace
                        .try_borrow_mut()
                        .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                        .observe_native_exit()?
                    {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(1));
                }
                {
                    let mut original = trace
                        .try_borrow_mut()
                        .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?;
                    let observed = original.observed_exit()?;
                    if !observed.is_unshare() {
                        return Err(NamespaceError::Rejected("native unshare exit kind changed"));
                    }
                    let errno = observed.errno()?;
                    if errno != 0 {
                        return Err(io::Error::from_raw_os_error(errno).into());
                    }
                    // This admits only the exact actual full copied graph. It
                    // does not relax the old bootstrap witness or its verifier.
                    original.resume_after_unshare()?;
                }
                loop {
                    if trace
                        .try_borrow_mut()
                        .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                        .pump_ordinary()?
                    {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(1));
                }
                if trace
                    .try_borrow()
                    .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                    .next_native_kind()?
                    != Some(NativeKind::RestoreBootstrap)
                {
                    return Err(NamespaceError::Rejected(
                        "original native order requires bootstrap setns",
                    ));
                }
                trace
                    .try_borrow_mut()
                    .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                    .begin_restore_bootstrap()?;
                self.tree
                    .apex_notifications
                    .as_ref()
                    .ok_or(NamespaceError::Rejected("original native listener absent"))?
                    .original_native_namespace(prepared.deadline())?
                    .execute_original()?;
                loop {
                    if trace
                        .try_borrow_mut()
                        .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?
                        .observe_native_exit()?
                    {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(1));
                }
                {
                    let mut original = trace
                        .try_borrow_mut()
                        .map_err(|_| NamespaceError::Rejected("original trace already borrowed"))?;
                    let observed = original.observed_exit()?;
                    if observed.is_unshare() {
                        return Err(NamespaceError::Rejected(
                            "native restoration exit kind changed",
                        ));
                    }
                    let errno = observed.errno()?;
                    if errno != 0 {
                        return Err(io::Error::from_raw_os_error(errno).into());
                    }
                    original.detach_after_restore()?;
                    // The default namespace stays held by the same original tree.
                    // This borrow confirms the completed two-epoch observation;
                    // it is not yet permission for apexd mounts or later callers.
                    original.observed_default_namespace()?;
                }
                self.tree
                    .apex_notifications
                    .as_ref()
                    .ok_or(NamespaceError::Rejected(
                        "original inherited listener absent at handoff",
                    ))?
                    .handoff_successors(
                        self.tree
                            .init
                            .as_ref()
                            .ok_or(NamespaceError::RetirementUnproven)?,
                    )?;
                mount_actors
                    .revalidate(&mount_owner)
                    .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
                drop(mount_actors);
                drop(mount_owner);
                self.verify_prepared_exec(selection, prepared)?;
                Ok(())
            })();
        match attempted {
            Ok(()) => Ok(self),
            Err(error) => {
                if self.retire().is_err() {
                    Err(NamespaceError::RetirementUnproven)
                } else {
                    Err(error)
                }
            }
        }
    }
}
