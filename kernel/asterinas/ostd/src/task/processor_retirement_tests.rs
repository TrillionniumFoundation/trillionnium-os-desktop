// SPDX-License-Identifier: MPL-2.0

//! Real active-root ownership across the scheduler's IRQ-restoration cut.

use alloc::{boxed::Box, sync::Arc};
use core::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

use super::release_previous_resources;
use crate::{
    mm::{VmSpace, vm_space::PageTableCharge},
    prelude::ktest,
};

static LIVE_ROOT_CHARGES: AtomicUsize = AtomicUsize::new(0);
static DROPPED_IN_ATOMIC_MODE: AtomicBool = AtomicBool::new(false);

#[derive(Debug)]
struct RootCharge;

impl Drop for RootCharge {
    fn drop(&mut self) {
        if !crate::arch::irq::is_local_enabled()
            || crate::task::preempt::cpu_local::get_guard_count() != 0
        {
            DROPPED_IN_ATOMIC_MODE.store(true, Ordering::Relaxed);
        }
        LIVE_ROOT_CHARGES.fetch_sub(1, Ordering::Relaxed);
    }
}

fn charge_root() -> crate::Result<Box<dyn PageTableCharge>> {
    LIVE_ROOT_CHARGES.fetch_add(1, Ordering::Relaxed);
    Ok(Box::new(RootCharge))
}

fn retire_last_active_root(next: Option<&Arc<VmSpace>>) {
    assert!(crate::arch::irq::is_local_enabled());
    assert_eq!(crate::task::preempt::cpu_local::get_guard_count(), 0);
    drop(VmSpace::deactivate_current());
    assert_eq!(LIVE_ROOT_CHARGES.load(Ordering::Relaxed), 0);
    DROPPED_IN_ATOMIC_MODE.store(false, Ordering::Relaxed);

    let space = Arc::new(VmSpace::try_new_with_page_table_charger(charge_root).unwrap());
    assert_eq!(LIVE_ROOT_CHARGES.load(Ordering::Relaxed), 1);
    assert!(space.activate_retiring_old().is_none());
    let old_root = crate::arch::mm::current_page_table_paddr();
    let weak = Arc::downgrade(&space);
    // Only the actual CPU-local activation now owns the VmSpace. The hardware
    // separately owns a processor Frame reference to its root.
    drop(space);

    let irq_guard = crate::irq::disable_local();
    let retired = if let Some(next) = next {
        next.activate_retiring_old()
    } else {
        VmSpace::deactivate_current()
    };
    assert!(retired.is_some());
    assert_ne!(crate::arch::mm::current_page_table_paddr(), old_root);
    assert_eq!(weak.strong_count(), 1);
    assert_eq!(LIVE_ROOT_CHARGES.load(Ordering::Relaxed), 1);
    assert!(!DROPPED_IN_ATOMIC_MODE.load(Ordering::Relaxed));
    if let Some(next) = next {
        assert!(next.activate_retiring_old().is_none());
    } else {
        assert!(VmSpace::deactivate_current().is_none());
    }

    // Exercise the very release cut used by after_switching_to, not a mock
    // destructor. It consumes the forgotten outer IRQ guard's restoration.
    core::mem::forget(irq_guard);
    release_previous_resources(None, retired);
    assert!(crate::arch::irq::is_local_enabled());
    assert_eq!(LIVE_ROOT_CHARGES.load(Ordering::Relaxed), 0);
    assert!(!DROPPED_IN_ATOMIC_MODE.load(Ordering::Relaxed));
    assert!(weak.upgrade().is_none());
    drop(VmSpace::deactivate_current());
}

#[ktest]
fn kernel_only_switch_releases_last_active_root_after_irq_restore() {
    retire_last_active_root(None);
}

#[ktest]
fn user_to_user_switch_releases_last_active_root_after_irq_restore() {
    let next = Arc::new(VmSpace::new());
    retire_last_active_root(Some(&next));
}
