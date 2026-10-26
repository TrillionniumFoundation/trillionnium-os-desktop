// SPDX-License-Identifier: MPL-2.0

//! Cold lifecycle pin for an admitted Task's original raw CPU hierarchy.
//! This is neither a coherent live membership generation nor CPU authority.

use super::*;

/// A move-only route lease. Its final destruction belongs outside every rq
/// lock/IRQ scope: the retained original owner may drop its final controller or
/// node Arc. The fixed prepared tree is currently its only scheduler consumer.
pub(crate) struct CpuSchedulingRoute {
    owner: CpuChargeOwner,
}

impl core::fmt::Debug for CpuSchedulingRoute {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.write_str("CpuSchedulingRoute")
    }
}

impl CpuSchedulingRoute {
    /// Capture the actual live raw leaf under the membership lock, not the
    /// retained final-charge fallback of an exited Task. Holding membership
    /// excludes controller replacement until every original ancestor is pinned.
    pub(crate) fn capture(
        task: &Task,
        _membership: &CgroupMembership,
    ) -> ostd::Result<Option<Self>> {
        ostd::task::atomic_mode::might_sleep();
        let Some(thread) = task.as_posix_thread() else {
            return Ok(None);
        };
        if task.as_thread().is_none_or(|thread| thread.is_exited()) {
            return Err(ostd::Error::InvalidArgs);
        }
        let process = thread
            .weak_process()
            .upgrade()
            .ok_or(ostd::Error::InvalidArgs)?;
        let owner = CpuChargeOwner::from_cgroup(process.cgroup().get().cloned());
        let mut at = Some(owner.cpu.as_ref());
        while let Some(cpu) = at {
            if cpu
                .inner
                .as_ref()
                .unwrap()
                .scheduling_routes
                .fetch_update(Ordering::AcqRel, Ordering::Acquire, |old| {
                    old.checked_add(1)
                })
                .is_err()
            {
                // Refund only earlier successful increments. No temporary
                // container/path allocation is needed, even on partial failure.
                let mut rollback = Some(owner.cpu.as_ref());
                while let Some(previous) = rollback {
                    if core::ptr::eq(previous, cpu) {
                        break;
                    }
                    previous
                        .inner
                        .as_ref()
                        .unwrap()
                        .scheduling_routes
                        .fetch_sub(1, Ordering::AcqRel);
                    rollback = previous.parent.as_deref();
                }
                return Err(ostd::Error::Overflow);
            }
            at = cpu.parent.as_deref();
        }
        let route = Self { owner };
        if task.as_thread().unwrap().is_exited() || process.status().is_zombie() {
            return Err(ostd::Error::InvalidArgs);
        }
        Ok(Some(route))
    }

    pub(crate) fn group(&self) -> Option<CpuSchedulingGroup> {
        CpuSchedulingGroup::active(self.owner.cpu.clone())
    }
}

impl Drop for CpuSchedulingRoute {
    fn drop(&mut self) {
        let mut at = Some(self.owner.cpu.as_ref());
        while let Some(cpu) = at {
            let previous = cpu
                .inner
                .as_ref()
                .unwrap()
                .scheduling_routes
                .fetch_sub(1, Ordering::AcqRel);
            debug_assert!(previous > 0);
            at = cpu.parent.as_deref();
        }
        // CpuChargeOwner's existing node lease is refunded after these counters.
        // Its original CPU budget/debt was never changed by this route lease.
    }
}
