//! Sequential native init tmpfs calls with a separate exact post-mount view.
use super::super::runtime::InitialMountProjection;
use super::*;
use crate::production_runtime_assets::{ActivationRootRole, OriginalInitMount};

const ORDER: [ActivationRootRole; 3] = [
    ActivationRootRole::Apex,
    ActivationRootRole::BootstrapApex,
    ActivationRootRole::Linkerconfig,
];

#[derive(Default)]
pub(super) struct InitialMounts {
    workers: Vec<OriginalInitMount>,
    projection: Option<InitialMountProjection>,
    complete: bool,
}

impl InitialMounts {
    pub(super) fn completed_projection(&self) -> Result<&InitialMountProjection> {
        let projection = self
            .projection
            .as_ref()
            .ok_or(NamespaceError::Rejected("original tmpfs projection absent"))?;
        if !self.complete || !projection.complete() || self.workers.len() != ORDER.len() {
            return Err(NamespaceError::Rejected(
                "all original tmpfs calls required",
            ));
        }
        Ok(projection)
    }

    pub(super) fn verify_after(
        &self,
        observation: &super::super::runtime::RuntimeObservation,
        child: &TreeChild,
    ) -> Result<bool> {
        let Some(projection) = &self.projection else {
            if self.complete || !self.workers.is_empty() {
                return Err(NamespaceError::Rejected(
                    "original tmpfs phase lost its projection",
                ));
            }
            return Ok(false);
        };
        if !self.complete || !projection.complete() || self.workers.len() != ORDER.len() {
            return Err(NamespaceError::Rejected(
                "original tmpfs phase did not complete all calls",
            ));
        }
        projection.verify_current(observation, child)?;
        Ok(true)
    }

    pub(super) fn original_root(
        &self,
        init: &ExecutedInitWitness<'_>,
        role: ActivationRootRole,
    ) -> Result<File> {
        if !self.complete
            || !self
                .projection
                .as_ref()
                .is_some_and(InitialMountProjection::complete)
            || self.workers.len() != ORDER.len()
        {
            return Err(NamespaceError::Rejected(
                "original init tmpfs root has no completed phase",
            ));
        }
        self.workers
            .iter()
            .find(|w| w.role() == role)
            .ok_or(NamespaceError::Rejected(
                "completed original tmpfs source absent",
            ))?
            .original_root(init)
            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))
    }

    /// Only helper retirement and release of our additional views. Original
    /// attached mounts still belong to the guest tree and its subsequent reap.
    pub(super) fn retire_views(&mut self) -> Result<()> {
        for worker in &mut self.workers {
            worker
                .retire_views()
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        }
        self.projection.take();
        self.workers.clear();
        self.complete = false;
        Ok(())
    }
}

impl ExecutedNamespaces {
    pub(crate) fn service_original_init_mounts(
        mut self,
        selection: &ProductionSelection,
        prepared: &PreparedExecution,
    ) -> Result<Self> {
        let attempted = (|| -> Result<()> {
            self.verify_prepared_exec(selection, prepared)?;
            if !self.early_cleanup.borrow().is_complete() {
                return Err(NamespaceError::Rejected(
                    "original first-stage cleanup is incomplete",
                ));
            }
            {
                let child = self
                    .tree
                    .init
                    .as_ref()
                    .ok_or(NamespaceError::RetirementUnproven)?;
                let observation =
                    self.tree
                        .runtime_observation
                        .as_ref()
                        .ok_or(NamespaceError::Rejected(
                            "original prepared runtime view absent",
                        ))?;
                let mut owned = self.initial_mounts.try_borrow_mut().map_err(|_| {
                    NamespaceError::Rejected("original tmpfs owner already borrowed")
                })?;
                if owned.complete || !owned.workers.is_empty() || owned.projection.is_some() {
                    return Err(NamespaceError::Rejected(
                        "original tmpfs phase was already attempted",
                    ));
                }
                owned.projection = Some(InitialMountProjection::begin(observation, child)?);
            }
            for role in ORDER {
                let init = self.original_init_witness(selection)?;
                let child = self
                    .tree
                    .init
                    .as_ref()
                    .ok_or(NamespaceError::RetirementUnproven)?;
                let listener =
                    self.tree
                        .apex_notifications
                        .as_ref()
                        .ok_or(NamespaceError::Rejected(
                            "original init notification listener absent",
                        ))?;
                let request = listener.original_init_tmpfs(child, &init, prepared.deadline())?;
                if request.role() != role {
                    return Err(NamespaceError::Rejected(
                        "original init tmpfs calls are out of order",
                    ));
                }
                let observation =
                    self.tree
                        .runtime_observation
                        .as_ref()
                        .ok_or(NamespaceError::Rejected(
                            "original prepared runtime view absent",
                        ))?;
                let mac = prepared
                    .activation_mac(&init)
                    .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                let mut owned = self.initial_mounts.try_borrow_mut().map_err(|_| {
                    NamespaceError::Rejected("original tmpfs owner already borrowed")
                })?;
                owned
                    .projection
                    .as_ref()
                    .ok_or(NamespaceError::Rejected("original tmpfs view absent"))?
                    .verify_current(observation, child)?;
                let worker = init
                    .runtime_owner()?
                    .prepare_original_init_mount(&init, mac, &request)
                    .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                owned.workers.push(worker);
                // Disjoint borrows retain both actual resource and phase view;
                // the worker cannot be released before this owner stores it.
                let InitialMounts {
                    workers,
                    projection,
                    ..
                } = &mut *owned;
                let worker = workers.last_mut().unwrap();
                worker
                    .run(&init, &request)
                    .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                let errno = worker
                    .actual_errno(&init, &request)
                    .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                if errno == 0 {
                    projection.as_mut().unwrap().admit_actual(
                        observation,
                        child,
                        &init,
                        &request,
                        worker,
                    )?;
                } else {
                    projection
                        .as_ref()
                        .unwrap()
                        .verify_current(observation, child)?;
                }
                request.complete(&init, worker)?;
                if errno != 0 {
                    return Err(io::Error::from_raw_os_error(errno).into());
                }
            }
            {
                let mut owned = self.initial_mounts.borrow_mut();
                if owned.workers.len() != ORDER.len()
                    || !owned
                        .projection
                        .as_ref()
                        .is_some_and(InitialMountProjection::complete)
                {
                    return Err(NamespaceError::Rejected(
                        "original tmpfs phase lacks all actual results",
                    ));
                }
                owned.complete = true;
            }
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
