//! Same-process, same installed child source custody for the H2 v2 pair.
//! This retains one actual parent/PID1 read per suite; per-case bindings borrow
//! the same witness and never renew its source or execution window.
use super::super::application_leaf_unit::qualification::working_peer::WorkingParent;
use super::{boot::BootOwner, source::WorkingSourceOrigin, source::require};
use crate::control::MainCustodyObservation;
use std::{
    cell::RefCell,
    rc::Rc,
    time::{Duration, Instant},
};

struct Inner {
    origin: WorkingSourceOrigin,
    boot: BootOwner,
    parent: WorkingParent,
}
thread_local! {
    // The normal physical dispatcher is one source-owned process/thread.
    // This cannot be populated from a report or by an external constructor.
    static SOURCE:RefCell<Option<Rc<Inner>>>=const {RefCell::new(None)};
}
/// Source custody only, never Main or application acceptance. No Deserialize,
/// Clone, caller boolean, PID, executable path or arbitrary unit entry point.
pub struct WorkingSourceWitness {
    inner: Rc<Inner>,
}
impl WorkingSourceWitness {
    pub fn capture(origin: &WorkingSourceOrigin) -> Result<Self, String> {
        origin.validate()?;
        SOURCE.with(|slot| {
            let mut slot = slot
                .try_borrow_mut()
                .map_err(|_| "working source acquisition reentered")?;
            if let Some(inner) = slot.as_ref() {
                require(
                    inner.origin == *origin,
                    "working suite cannot replace its first source owner",
                )?;
                let result = Self {
                    inner: Rc::clone(inner),
                };
                result.guard()?;
                return Ok(result);
            }
            let boot = BootOwner::open_child().map_err(|e| e.to_string())?;
            compare_boot(origin, &boot)?;
            let ceiling = Instant::now()
                + Duration::from_secs(
                    crate::native_working_contract::WorkingSchedule::selected().whole_suite_seconds,
                );
            let end = super::super::physical_qualification_channel::instant_until(
                origin.original_end_monotonic_ns,
                ceiling,
            )
            .map_err(|e| e.to_string())?;
            let parent = WorkingParent::capture(&origin.unit, end)?;
            let inner = Rc::new(Inner {
                origin: origin.clone(),
                boot,
                parent,
            });
            let result = Self {
                inner: Rc::clone(&inner),
            };
            result.guard()?;
            *slot = Some(inner);
            Ok(result)
        })
    }
    /// Borrow the one witness already admitted by this normal NativeRelease.
    /// This does not open a caller-selected source document or create an owner.
    pub(crate) fn retained_for_main(main: &MainCustodyObservation) -> Result<Option<Self>, String> {
        SOURCE.with(|slot| {
            let slot = slot
                .try_borrow()
                .map_err(|_| "working source borrow reentered")?;
            let Some(inner) = slot.as_ref() else {
                return Ok(None);
            };
            let result = Self {
                inner: Rc::clone(inner),
            };
            result.compare_main(main)?;
            Ok(Some(result))
        })
    }
    pub(crate) fn comparison(&self) -> &WorkingSourceOrigin {
        &self.inner.origin
    }
    pub fn guard(&self) -> Result<(), String> {
        self.inner.boot.guard().map_err(|e| e.to_string())?;
        self.inner.parent.guard()?;
        compare_boot(&self.inner.origin, &self.inner.boot)
    }
    /// The normal factory passes its actual opaque Main. A serialized origin's
    /// epoch/hash never manufactures Main or skips its owner/storage guards.
    pub fn compare_main(&self, main: &MainCustodyObservation) -> Result<(), String> {
        self.guard()?;
        self.inner
            .boot
            .compare_main(main)
            .map_err(|e| e.to_string())?;
        self.inner.origin.matches_main(main)?;
        self.guard()
    }
}
fn compare_boot(origin: &WorkingSourceOrigin, boot: &BootOwner) -> Result<(), String> {
    origin.validate()?;
    let c = boot.config();
    require(
        origin.candidate_id == c.candidate_id
            && origin.first_once_candidate == c.first_once_candidate
            && origin.boot_id == boot.boot_id()
            && origin.source_commit == c.host_source_commit
            && origin.source_tree == c.host_source_tree
            && origin.admitted_materials_sha256 == c.admitted_materials_sha256
            && origin.joint_policy_sha256 == c.joint_policy_sha256
            && origin.applications.bytes == c.applications.bytes
            && origin.applications.sha256 == c.applications.sha256
            && origin.selected_configuration.bytes == c.selection.bytes
            && origin.selected_configuration.sha256 == c.selection.sha256
            && origin.cell_configuration.bytes == c.cell.bytes
            && origin.cell_configuration.sha256 == c.cell.sha256,
        "v2 source origin differs from actual normal boot/source/runtime inputs",
    )
}
