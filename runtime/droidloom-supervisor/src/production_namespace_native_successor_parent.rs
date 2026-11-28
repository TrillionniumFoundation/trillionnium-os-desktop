//! Same-owner progress for later inherited NEWNS requests.
//!
//! Only the original completed initial phase issues the successor owner.
//! Every operation remains bounded and owns the sole listener dispatch borrow;
//! the original APEX publication ledger is held throughout the real syscall.
use super::*;

impl IsolatedNamespaces {
    pub(super) fn progress_inherited_native(
        &self,
        deadline: Instant,
    ) -> Result<InheritedNativePoll> {
        self.verify_live_admission()?;
        self.require_cgroup_hierarchy_ready()?;
        let child = self
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        child.verify()?;
        let witness = self.witness()?;
        let runtime = self.runtime.as_ref().ok_or(NamespaceError::Rejected(
            "inherited native runtime owner absent",
        ))?;
        let actors = runtime
            .native_mount_actor_guard(&witness)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        let result = self
            .apex_notifications
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "inherited native listener owner absent",
            ))?
            .poll_inherited_native(deadline);
        let after = actors
            .revalidate(&witness)
            .map_err(|error| NamespaceError::RuntimeResource(error.to_string()));
        // Never allow a successful syscall result to hide a changed original
        // namespace lease, host helper ledger or PID-1 generation.
        let checked = (|| -> Result<InheritedNativePoll> {
            let outcome = result?;
            after?;
            child.verify()?;
            self.verify_live_admission()?;
            Ok(outcome)
        })();
        drop(actors);
        if checked.is_err() {
            // An application callback only borrows the cell. It cannot consume
            // the owning tree to reap it here. Start original PIDFD shutdown
            // and release any armed ptrace exit before returning the error;
            // the unchanged owning controller still owes full PID-1 reap.
            if !pidfd_exited(&child.pidfd)? {
                signal_owned(&child.pidfd, libc::SIGKILL)?;
            }
            self.apex_notifications
                .as_ref()
                .ok_or(NamespaceError::RetirementUnproven)?
                .retire_before_init_wait(child)?;
        }
        checked
    }
}

impl ExecutedNamespaces {
    /// The normal prepared-runtime entry for an already received apexd ioctl.
    /// This keeps the first request budget and acquires one exclusive original
    /// mount ledger before issuing any task/request witness. It does not
    /// manufacture a loop device or reply while that provider is unavailable.
    pub(crate) fn original_apexd_ioctl_before<'task>(
        &'task mut self,
        selection: &ProductionSelection,
        admission: &PreparedExecution,
    ) -> Result<OriginalApexdIoctlRequest<'task>> {
        self.verify_prepared_exec(selection, admission)?;
        self.tree.verify_live_admission()?;
        self.tree.require_cgroup_hierarchy_ready()?;
        let child = self
            .tree
            .init
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?;
        child.verify()?;
        let witness = self.tree.witness()?;
        let runtime = self.tree.runtime.as_ref().ok_or(NamespaceError::Rejected(
            "original apexd runtime owner absent",
        ))?;
        let original_bases = match self.tree.bases.as_ref() {
            Some(BaseMounts::Admitted(bases)) => bases,
            _ => return Err(NamespaceError::HostAdmissionRequired),
        };
        let actors = runtime
            .apexd_mount_actor_guard(&witness)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        actors
            .require_exclusive()
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        self.tree
            .apex_notifications
            .as_ref()
            .ok_or(NamespaceError::Rejected(
                "original apexd listener owner absent",
            ))?
            .original_apexd_ioctl(child, witness, original_bases, actors, admission.deadline())
    }

    pub(crate) fn service_inherited_native_before(
        &mut self,
        selection: &ProductionSelection,
        admission: &PreparedExecution,
    ) -> Result<InheritedNativePoll> {
        self.verify_prepared_exec(selection, admission)?;
        let deadline = admission
            .deadline()
            .min(Instant::now() + Duration::from_secs(10));
        let result = self.tree.progress_inherited_native(deadline);
        let after = self.verify_prepared_exec(selection, admission);
        let outcome = result?;
        after?;
        Ok(outcome)
    }

    pub(crate) fn service_inherited_native(
        &mut self,
        selection: &ProductionSelection,
        admission: &ExecutionAdmission,
        deadline: Instant,
    ) -> Result<InheritedNativePoll> {
        self.verify_exec(selection, admission)?;
        let deadline = deadline.min(Instant::now() + Duration::from_secs(10));
        let result = self.tree.progress_inherited_native(deadline);
        let after = self.verify_exec(selection, admission);
        let outcome = result?;
        after?;
        Ok(outcome)
    }
}
