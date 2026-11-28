//! Original CP3A init first-stage cleanup, through its real pending syscalls.
//! The two calls occur in either order in the pinned image. Each is performed
//! once; before/after complete mount inventories must remain unchanged because
//! these prepared original directories are not mounted first-stage ramdisks.
use super::*;
use crate::production_runtime_assets::OriginalInitCleanup;
use std::collections::BTreeSet;

#[derive(Default)]
pub(super) struct EarlyCleanup {
    workers: Vec<OriginalInitCleanup>,
    complete: bool,
}

impl EarlyCleanup {
    pub(super) fn is_complete(&self) -> bool {
        self.complete && self.workers.len() == 2
    }

    pub(super) fn retire(&mut self) -> Result<()> {
        for worker in &mut self.workers {
            worker
                .retire()
                .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
        }
        self.workers.clear();
        Ok(())
    }
}

impl ExecutedNamespaces {
    pub(crate) fn service_original_init_cleanup(
        mut self,
        selection: &ProductionSelection,
        prepared: &PreparedExecution,
    ) -> Result<Self> {
        let attempted = (|| -> Result<()> {
            self.verify_prepared_exec(selection, prepared)?;
            if self.early_cleanup.borrow().complete
                || !self.early_cleanup.borrow().workers.is_empty()
            {
                return Err(NamespaceError::Rejected(
                    "original init cleanup already attempted",
                ));
            }
            let mut seen = BTreeSet::new();
            for _ in 0..2 {
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
                let request = listener.original_init_unmount(child, &init, prepared.deadline())?;
                if !seen.insert(request.kind()) {
                    return Err(NamespaceError::Rejected(
                        "original init repeated a fixed cleanup target",
                    ));
                }
                let runtime_observation =
                    self.tree
                        .runtime_observation
                        .as_ref()
                        .ok_or(NamespaceError::Rejected(
                            "original runtime mount observation absent",
                        ))?;
                let before = runtime_observation.verify_current(child)?;
                if before
                    .records
                    .values()
                    .any(|row| row.target == request.kind().target())
                {
                    return Err(NamespaceError::Rejected(
                        "prepared first-stage cleanup target is a mountpoint",
                    ));
                }
                let mac = prepared
                    .activation_mac(&init)
                    .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
                let worker = init
                    .runtime_owner()?
                    .prepare_original_init_cleanup(&init, mac, &request)
                    .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
                {
                    let mut owned = self.early_cleanup.try_borrow_mut().map_err(|_| {
                        NamespaceError::Rejected("original init cleanup owner already borrowed")
                    })?;
                    owned.workers.push(worker);
                    let worker = owned.workers.last_mut().unwrap();
                    worker
                        .run(&init, &request)
                        .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
                    let after = runtime_observation.verify_current(child)?;
                    if before != after {
                        return Err(NamespaceError::Rejected(
                            "original cleanup changed the prepared mount inventory",
                        ));
                    }
                    request.complete(&init, worker)?;
                }
            }
            if seen.len() != 2 {
                return Err(NamespaceError::Rejected(
                    "original init cleanup coverage is incomplete",
                ));
            }
            self.early_cleanup.borrow_mut().complete = true;
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
