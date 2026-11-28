//! Original broker mount actors held by one native or apexd request.
//! The outer original RefMut remains held for the complete Request lifetime.
//! Only short inner borrows are released around Request/Bound validation.
use super::*;
use crate::production_capex_loop_request::MatchedApexdCapexSource;
use crate::production_namespace::{BoundApexdCapexRequest, OriginalApexdIoctlRequest};
use std::cell::{Ref, RefCell, RefMut};
use std::rc::Rc;

enum NativeActorLedger<'a> {
    Shared(Ref<'a, ApexLoops>),
    Exclusive(RefCell<RefMut<'a, ApexLoops>>),
}
impl<'a> NativeActorLedger<'a> {
    fn exclusive(&self) -> Result<&RefCell<RefMut<'a, ApexLoops>>> {
        match self {
            Self::Exclusive(held) => Ok(held),
            Self::Shared(_) => Err(MountError::Rejected(
                "original apexd request requires its exclusive retained actor ledger",
            )),
        }
    }
}

pub(crate) struct NativeMountActorGuard<'a> {
    resources: &'a RuntimeResources,
    loops: NativeActorLedger<'a>,
    requested: RefCell<Option<RetainedApexdCapexCustody>>,
}
impl<'a> NativeMountActorGuard<'a> {
    pub(crate) fn revalidate(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        match &self.loops {
            NativeActorLedger::Shared(loops) => {
                self.resources.matches_witness(witness)?;
                loops.revalidate()
            }
            NativeActorLedger::Exclusive(loops) => {
                self.resources.matches_input_witness(witness)?;
                let slot = self
                    .requested
                    .try_borrow()
                    .map_err(|_| MountError::Rejected("original requested ledger is active"))?
                    .as_ref()
                    .map(RetainedApexdCapexCustody::retain);
                let held = loops
                    .try_borrow()
                    .map_err(|_| MountError::Rejected("original apexd actor ledger is active"))?;
                match slot {
                    Some(slot) => held.revalidate_requested(&slot),
                    None => held.revalidate(),
                }
            }
        }
    }
    pub(crate) fn require_exclusive(&self) -> Result<()> {
        self.loops.exclusive().map(|_| ())
    }

    // Called only outside the inner ledger borrow. The Request proves this
    // guard's actual address, same actor, original namespace and notification.
    fn require_requested(
        &self,
        request: &OriginalApexdIoctlRequest<'a>,
        bound: &BoundApexdCapexRequest<'_>,
        slot: &RetainedApexdCapexCustody,
    ) -> Result<()> {
        bound
            .require_request(request)
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        request
            .require_actor_ledger(self)
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        let source = slot.source()?;
        source.require_request(request).map_err(MountError::Io)?;
        {
            let own = self
                .requested
                .try_borrow()
                .map_err(|_| MountError::Rejected("original requested ledger is active"))?;
            require(
                own.as_ref().is_some_and(|original| original.same(slot)),
                "requested slot belongs to this original exclusive guard",
            )?;
        }
        {
            let held = self
                .loops
                .exclusive()?
                .try_borrow()
                .map_err(|_| MountError::Rejected("original apexd actor ledger is active"))?;
            held.require_requested(slot)?;
        }
        request
            .require_actor_ledger(self)
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        bound
            .require_request(request)
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))
    }

    pub(crate) fn register_capex_custody(
        &self,
        request: &OriginalApexdIoctlRequest<'a>,
        bound: &BoundApexdCapexRequest<'_>,
        source: Rc<MatchedApexdCapexSource>,
    ) -> Result<RetainedApexdCapexCustody> {
        bound
            .require_request(request)
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        request
            .require_actor_ledger(self)
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        source.require_request(request).map_err(MountError::Io)?;
        let slot = RetainedApexdCapexCustody::new(source);
        {
            let mut own = self
                .requested
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("original requested ledger is active"))?;
            require(
                own.is_none(),
                "one original requested slot per exclusive guard",
            )?;
            *own = Some(slot.retain());
        }
        {
            let mut held = self
                .loops
                .exclusive()?
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("original apexd actor ledger is active"))?;
            // Same slot is inserted before pool movement or actual creation.
            // This method never calls Request or Bound.
            held.begin_requested(&slot)?;
        }
        self.require_requested(request, bound, &slot)?;
        Ok(slot)
    }

    pub(crate) fn configure_capex_custody(
        &self,
        request: &OriginalApexdIoctlRequest<'a>,
        bound: &BoundApexdCapexRequest<'_>,
        slot: &RetainedApexdCapexCustody,
    ) -> Result<()> {
        self.require_requested(request, bound, slot)?;
        // No ledger borrow exists here. The original pool is already owned
        // by this same registered slot and is never handed to the caller.
        slot.configure()?;
        self.require_requested(request, bound, slot)
    }

    pub(crate) fn commit_capex_custody(
        &self,
        request: &OriginalApexdIoctlRequest<'a>,
        bound: &BoundApexdCapexRequest<'_>,
        slot: &RetainedApexdCapexCustody,
    ) -> Result<CommittedApexdCapexCustody> {
        self.require_requested(request, bound, slot)?;
        {
            let mut held = self
                .loops
                .exclusive()?
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("original apexd actor ledger is active"))?;
            held.begin_requested_commit(slot)?;
        }
        // Pool has returned to the original ledger; the slot still owns the
        // device, full original source/MAC and exact immutable request stamp.
        self.require_requested(request, bound, slot)?;
        {
            let mut held = self
                .loops
                .exclusive()?
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("original apexd actor ledger is active"))?;
            held.finish_requested_commit(slot)?;
        }
        self.require_requested(request, bound, slot)?;
        slot.committed()
    }

    pub(crate) fn retire_capex_custody(
        &self,
        request: &OriginalApexdIoctlRequest<'a>,
        bound: &BoundApexdCapexRequest<'_>,
        slot: &RetainedApexdCapexCustody,
    ) -> Result<()> {
        self.require_requested(request, bound, slot)?;
        // Only this device retires here. Old rows keep their same pool alive.
        slot.retire_device()?;
        {
            let mut held = self
                .loops
                .exclusive()?
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("original apexd actor ledger is active"))?;
            held.return_requested_pool_after_retire(slot)?;
        }
        self.require_requested(request, bound, slot)?;
        {
            // Acquire both short cells before changing either; then the
            // original ledger and guard lose only this fully retired slot.
            let mut own = self
                .requested
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("original requested ledger is active"))?;
            require(
                own.as_ref().is_some_and(|original| original.same(slot)),
                "retirement must keep the original guard slot",
            )?;
            let mut held = self
                .loops
                .exclusive()?
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("original apexd actor ledger is active"))?;
            held.finish_requested_retirement(slot)?;
            drop(own.take());
        }
        // The last full request check preceded this purely in-memory
        // finalization. A recorded retirement intentionally prevents ordinary
        // runtime readiness; do not issue that stronger witness again here.
        Ok(())
    }
}

impl PreparedRuntime {
    pub(crate) fn native_mount_actor_guard(
        &self,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<NativeMountActorGuard<'_>> {
        require(
            self.exported,
            "native actor scope requires original transferred runtime",
        )?;
        let resources = self.resources.as_ref().ok_or(MountError::Rejected(
            "original native runtime already retired",
        ))?;
        resources.matches_witness(witness)?;
        let loops = resources
            .apex_loops
            .try_borrow()
            .map_err(|_| MountError::Rejected("original mount actor is active"))?;
        loops.revalidate()?;
        Ok(NativeMountActorGuard {
            resources,
            loops: NativeActorLedger::Shared(loops),
            requested: RefCell::new(None),
        })
    }

    pub(crate) fn apexd_mount_actor_guard(
        &self,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<NativeMountActorGuard<'_>> {
        require(
            self.exported,
            "apexd actor scope requires original transferred runtime",
        )?;
        let resources = self.resources.as_ref().ok_or(MountError::Rejected(
            "original apexd runtime already retired",
        ))?;
        resources.matches_witness(witness)?;
        let loops = resources
            .apex_loops
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("original mount actor is active"))?;
        loops.revalidate()?;
        let value = NativeMountActorGuard {
            resources,
            loops: NativeActorLedger::Exclusive(RefCell::new(loops)),
            requested: RefCell::new(None),
        };
        value.require_exclusive()?;
        value.revalidate(witness)?;
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requested_inner_release_keeps_original_outer_ledger_exclusive() {
        let original = RefCell::new(ApexLoops::default());
        let guard = NativeActorLedger::Exclusive(RefCell::new(original.borrow_mut()));
        {
            let inner = guard.exclusive().unwrap().try_borrow_mut().unwrap();
            assert!(guard.exclusive().unwrap().try_borrow_mut().is_err());
            assert!(original.try_borrow().is_err());
            assert!(original.try_borrow_mut().is_err());
            inner.revalidate().unwrap();
        }
        // External validation can take a short inner read, but no caller can
        // acquire another original pool/ledger or a Shared lane.
        guard
            .exclusive()
            .unwrap()
            .try_borrow()
            .unwrap()
            .revalidate()
            .unwrap();
        assert!(original.try_borrow().is_err());
        assert!(original.try_borrow_mut().is_err());
        drop(guard);
        original.try_borrow_mut().unwrap().revalidate().unwrap();
    }

    #[test]
    fn requested_mutation_lane_rejects_existing_shared_guard() {
        let original = RefCell::new(ApexLoops::default());
        let shared = NativeActorLedger::Shared(original.borrow());
        assert!(shared.exclusive().is_err());
        assert!(original.try_borrow_mut().is_err());
        drop(shared);
        assert!(original.try_borrow_mut().is_ok());
    }
}
