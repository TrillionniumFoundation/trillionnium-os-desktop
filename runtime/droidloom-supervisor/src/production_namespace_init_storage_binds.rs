//! Sequential custody of the original six storage bind/slave/shared calls.
use super::super::runtime::InitialStorageBindProjection;
use super::*;
use crate::production_runtime_assets::{
    OriginalInitStorageBind, OriginalInitStorageBindKind, OriginalInitStorageDirectories,
};

#[derive(Default)]
pub(super) struct InitialStorageBinds {
    workers: Vec<OriginalInitStorageBind>,
    directories: Option<OriginalInitStorageDirectories>,
    projection: Option<InitialStorageBindProjection>,
    complete: bool,
}

impl InitialStorageBinds {
    pub(super) fn native_snapshot(
        &self,
        previous: &init_propagation::InitialPropagation,
        mounts: &init_mounts::InitialMounts,
        observation: &super::super::runtime::RuntimeObservation,
        child: &TreeChild,
    ) -> Result<super::super::runtime::NativeStorageSnapshot> {
        if !self.verify_after(previous, mounts, observation, child)? {
            return Err(NamespaceError::Rejected(
                "original storage phase has not completed",
            ));
        }
        self.projection
            .as_ref()
            .ok_or(NamespaceError::RetirementUnproven)?
            .native_snapshot(
                previous.completed_projection()?,
                mounts.completed_projection()?,
                observation,
                child,
            )
    }

    pub(super) fn verify_after(
        &self,
        previous: &init_propagation::InitialPropagation,
        mounts: &init_mounts::InitialMounts,
        observation: &super::super::runtime::RuntimeObservation,
        child: &TreeChild,
    ) -> Result<bool> {
        let Some(projection) = &self.projection else {
            if self.complete || !self.workers.is_empty() || self.directories.is_some() {
                return Err(NamespaceError::Rejected(
                    "storage bind owner lost its phase view",
                ));
            }
            return Ok(false);
        };
        if !self.complete
            || !projection.complete()
            || self.directories.is_none()
            || self.workers.len() != OriginalInitStorageBindKind::ALL.len()
        {
            return Err(NamespaceError::Rejected(
                "all original storage binds must complete",
            ));
        }
        projection.verify_current(
            previous.completed_projection()?,
            mounts.completed_projection()?,
            observation,
            child,
        )?;
        Ok(true)
    }

    pub(super) fn retire_views(&mut self) -> Result<()> {
        for worker in &mut self.workers {
            worker
                .retire_views()
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
        }
        self.projection.take();
        self.directories.take();
        self.workers.clear();
        self.complete = false;
        Ok(())
    }
}

impl ExecutedNamespaces {
    pub(crate) fn service_original_init_storage_binds(
        mut self,
        selection: &ProductionSelection,
        prepared: &PreparedExecution,
    ) -> Result<Self> {
        let attempted =
            (|| -> Result<()> {
                self.verify_prepared_exec(selection, prepared)?;
                {
                    let owned = self.initial_storage_binds.try_borrow().map_err(|_| {
                        NamespaceError::Rejected("storage bind owner already borrowed")
                    })?;
                    if owned.complete
                        || !owned.workers.is_empty()
                        || owned.projection.is_some()
                        || owned.directories.is_some()
                    {
                        return Err(NamespaceError::Rejected(
                            "original storage bind phase already attempted",
                        ));
                    }
                }
                for kind in OriginalInitStorageBindKind::ALL {
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
                                "original storage notification listener absent",
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
                    let request = listener.original_init_storage_bind(
                        child,
                        &init,
                        prepared.deadline(),
                        mount_owner,
                        mount_actors,
                    )?;
                    if request.kind() != kind {
                        return Err(NamespaceError::Rejected(
                            "original storage mount calls are out of order",
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
                    let previous = self.initial_propagation.try_borrow().map_err(|_| {
                        NamespaceError::Rejected("original propagation phase already borrowed")
                    })?;
                    let previous = previous.completed_projection()?;
                    let mac = prepared
                        .activation_mac(&init)
                        .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                    let mut owned = self.initial_storage_binds.try_borrow_mut().map_err(|_| {
                        NamespaceError::Rejected("storage bind owner already borrowed")
                    })?;
                    if owned.projection.is_none() {
                        if !owned.workers.is_empty()
                            || owned.directories.is_some()
                            || kind != OriginalInitStorageBindKind::BindInstaller
                        {
                            return Err(NamespaceError::Rejected(
                                "original storage bind phase cannot be reconstructed",
                            ));
                        }
                        let directories = init
                            .runtime_owner()?
                            .prepare_original_storage_directories(&init, mac, &request)
                            .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                        owned.directories = Some(directories);
                        owned.projection = Some(InitialStorageBindProjection::begin(
                            previous,
                            mounts,
                            observation,
                            child,
                            &init,
                            &request,
                            owned.directories.as_ref().unwrap().clone(),
                        )?);
                    }
                    owned.projection.as_ref().unwrap().verify_current(
                        previous,
                        mounts,
                        observation,
                        child,
                    )?;
                    request.revalidate(&init)?;
                    let worker = init
                        .runtime_owner()?
                        .prepare_original_init_storage_bind(
                            &init,
                            mac,
                            &request,
                            owned.directories.as_ref().unwrap(),
                        )
                        .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
                    // The exact helper PIDFD belongs to this guard before release.
                    owned.workers.push(worker);
                    let InitialStorageBinds {
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
                            previous,
                            mounts,
                            observation,
                            child,
                            &init,
                            &request,
                            worker,
                        )?;
                    } else {
                        projection.as_ref().unwrap().verify_current(
                            previous,
                            mounts,
                            observation,
                            child,
                        )?;
                    }
                    request.complete(&init, worker)?;
                    if errno != 0 {
                        return Err(io::Error::from_raw_os_error(errno).into());
                    }
                }
                {
                    let mut owned = self.initial_storage_binds.borrow_mut();
                    if owned.directories.is_none()
                        || owned.workers.len() != OriginalInitStorageBindKind::ALL.len()
                        || !owned
                            .projection
                            .as_ref()
                            .is_some_and(InitialStorageBindProjection::complete)
                    {
                        return Err(NamespaceError::Rejected(
                            "original storage mounts lack all actual results",
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
