//! Serial service of the original CP3A mount propagation requests.
//! The old private and original-tmpfs observations stay intact; this owner
//! alone records the exact subsequent propagation view and real helpers.
use super::super::runtime::InitialPropagationProjection;
use super::*;
use crate::production_runtime_assets::{
    OriginalInitPropagation, OriginalInitPropagationKind, OriginalInitStorage,
};

#[derive(Default)]
pub(super) struct InitialPropagation {
    workers: Vec<OriginalInitPropagation>,
    storage: Option<OriginalInitStorage>,
    projection: Option<InitialPropagationProjection>,
    complete: bool,
}

impl InitialPropagation {
    pub(super) fn verify_after(
        &self,
        mounts: &init_mounts::InitialMounts,
        observation: &super::super::runtime::RuntimeObservation,
        child: &TreeChild,
    ) -> Result<bool> {
        let Some(projection) = &self.projection else {
            if self.complete || !self.workers.is_empty() || self.storage.is_some() {
                return Err(NamespaceError::Rejected(
                    "propagation owner lost its phase view",
                ));
            }
            return Ok(false);
        };
        if !self.complete
            || self.storage.is_none()
            || !projection.complete()
            || self.workers.len() != OriginalInitPropagationKind::ALL.len()
        {
            return Err(NamespaceError::Rejected(
                "all original propagation calls must complete",
            ));
        }
        projection.verify_current(mounts.completed_projection()?, observation, child)?;
        Ok(true)
    }

    pub(super) fn completed_projection(&self) -> Result<&InitialPropagationProjection> {
        let projection = self
            .projection
            .as_ref()
            .ok_or(NamespaceError::Rejected("original propagation view absent"))?;
        if !self.complete
            || self.storage.is_none()
            || !projection.complete()
            || self.workers.len() != OriginalInitPropagationKind::ALL.len()
        {
            return Err(NamespaceError::Rejected(
                "original propagation phase is incomplete",
            ));
        }
        Ok(projection)
    }

    pub(super) fn retire_views(&mut self) -> Result<()> {
        for worker in &mut self.workers {
            worker
                .retire_views()
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        }
        if let Some(storage) = &mut self.storage {
            storage
                .retire_views()
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        }
        self.projection.take();
        self.storage.take();
        self.workers.clear();
        self.complete = false;
        Ok(())
    }
}

impl ExecutedNamespaces {
    pub(crate) fn service_original_init_propagation(
        mut self,
        selection: &ProductionSelection,
        prepared: &PreparedExecution,
    ) -> Result<Self> {
        let attempted =
            (|| -> Result<()> {
                self.verify_prepared_exec(selection, prepared)?;
                {
                    let owned = self.initial_propagation.try_borrow().map_err(|_| {
                        NamespaceError::Rejected("propagation owner already borrowed")
                    })?;
                    if owned.complete
                        || !owned.workers.is_empty()
                        || owned.projection.is_some()
                        || owned.storage.is_some()
                    {
                        return Err(NamespaceError::Rejected(
                            "original propagation phase already attempted",
                        ));
                    }
                }
                for kind in OriginalInitPropagationKind::ALL {
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
                    let mount_owner = self.tree.witness()?;
                    let mount_actors = self
                        .tree
                        .runtime
                        .as_ref()
                        .ok_or(NamespaceError::Rejected(
                            "original mount actor owner absent",
                        ))?
                        .native_mount_actor_guard(&mount_owner)
                        .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
                    let request = listener.original_init_propagation(
                        child,
                        &init,
                        prepared.deadline(),
                        mount_owner,
                        mount_actors,
                    )?;
                    if request.kind() != kind {
                        return Err(NamespaceError::Rejected(
                            "original propagation calls are out of order",
                        ));
                    }
                    let observation = self
                        .tree
                        .runtime_observation
                        .as_ref()
                        .ok_or(NamespaceError::Rejected("original runtime view absent"))?;
                    let mounts = self.initial_mounts.try_borrow().map_err(|_| {
                        NamespaceError::Rejected("original tmpfs phase already borrowed")
                    })?;
                    let mounts = mounts.completed_projection()?;
                    let mac = prepared
                        .activation_mac(&init)
                        .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                    let mut owned = self.initial_propagation.try_borrow_mut().map_err(|_| {
                        NamespaceError::Rejected("propagation owner already borrowed")
                    })?;
                    if owned.projection.is_none() {
                        if !owned.workers.is_empty()
                            || owned.storage.is_some()
                            || kind != OriginalInitPropagationKind::RootShared
                        {
                            return Err(NamespaceError::Rejected(
                                "propagation phase cannot be reconstructed",
                            ));
                        }
                        owned.projection = Some(InitialPropagationProjection::begin(
                            mounts,
                            observation,
                            child,
                        )?);
                    }
                    if kind == OriginalInitPropagationKind::RootShared {
                        if owned.storage.is_some() {
                            return Err(NamespaceError::Rejected(
                                "storage preparation cannot be replayed",
                            ));
                        }
                        owned.projection.as_ref().unwrap().verify_current(
                            mounts,
                            observation,
                            child,
                        )?;
                        request.revalidate(&init)?;
                        let storage = init
                            .runtime_owner()?
                            .prepare_original_init_storage(&init, mac, &request)
                            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                        // The real source and its future helper are under the
                        // original owner before any helper can leave READY.
                        owned.storage = Some(storage);
                        let InitialPropagation {
                            storage,
                            projection,
                            ..
                        } = &mut *owned;
                        let storage = storage.as_mut().unwrap();
                        storage
                            .run(&init, &request)
                            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                        projection.as_mut().unwrap().admit_storage(
                            mounts,
                            observation,
                            child,
                            &init,
                            &request,
                            storage,
                        )?;
                    }
                    owned.projection.as_ref().unwrap().verify_current(
                        mounts,
                        observation,
                        child,
                    )?;
                    request.revalidate(&init)?;
                    let worker = init
                        .runtime_owner()?
                        .prepare_original_init_propagation(&init, mac, &request)
                        .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                    owned.workers.push(worker);
                    let InitialPropagation {
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
                            mounts,
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
                            .verify_current(mounts, observation, child)?;
                    }
                    request.complete(&init, worker)?;
                    if errno != 0 {
                        return Err(io::Error::from_raw_os_error(errno).into());
                    }
                }
                {
                    let mut owned = self.initial_propagation.borrow_mut();
                    if owned.storage.is_none()
                        || owned.workers.len() != OriginalInitPropagationKind::ALL.len()
                        || !owned
                            .projection
                            .as_ref()
                            .is_some_and(InitialPropagationProjection::complete)
                    {
                        return Err(NamespaceError::Rejected(
                            "original propagation lacks complete real results",
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
