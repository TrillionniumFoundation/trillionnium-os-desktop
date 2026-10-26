// SPDX-License-Identifier: MPL-2.0

//! Cold capacity for a future single-Task transfer. No live affinity operation
//! is enabled here. Existing producers preserve every promised physical slot.

use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Placement {
    Fair,
    RealTime(u8),
}

struct CapacityNeed {
    fair: Option<fair::FairCapacityNeed>,
    rt: Option<real_time::RtCapacityNeed>,
    throttled_required: usize,
    throttled_capacity: usize,
}

struct PreparedCapacity {
    fair: Option<fair::PreparedFairCapacity>,
    rt: Option<real_time::PreparedRtCapacity>,
    throttled: Option<Vec<Arc<Task>>>,
}

impl CapacityNeed {
    fn allocate(self) -> ostd::Result<PreparedCapacity> {
        ostd::task::atomic_mode::might_sleep();
        let fair = self.fair.map(|need| need.allocate()).transpose()?;
        let rt = self.rt.map(|need| need.allocate()).transpose()?;
        let throttled = if self.throttled_required > self.throttled_capacity {
            let mut storage = Vec::new();
            storage
                .try_reserve_exact(self.throttled_required)
                .map_err(|_| ostd::Error::NoMemory)?;
            Some(storage)
        } else {
            None
        };
        Ok(PreparedCapacity {
            fair,
            rt,
            throttled,
        })
    }
}

/// Move-only reservation, bound to the same scheduler instance and CPU layout.
/// Cancellation must occur outside every rq lock. A commit consumes it under
/// its destination lock before inserting, so Drop cannot refund it twice.
#[must_use]
pub(super) struct MigrationCapacity<'a> {
    scheduler: &'a ClassScheduler,
    cpu: CpuId,
    placement: Placement,
    rq_identity: usize,
    live: bool,
}

impl MigrationCapacity<'_> {
    pub(super) fn consume(&mut self, rq: &mut PerCpuClassRqSet) {
        assert!(self.live && rq.cpu == self.cpu);
        assert_eq!(
            self.rq_identity, rq as *const PerCpuClassRqSet as usize,
            "capacity ticket belongs to another runqueue"
        );
        rq.release_migration_capacity(self.placement);
        self.live = false;
    }
}

impl Drop for MigrationCapacity<'_> {
    fn drop(&mut self) {
        if self.live {
            let _irq = disable_local();
            self.scheduler.rqs[self.cpu.as_usize()]
                .lock()
                .release_migration_capacity(self.placement);
        }
    }
}

impl PerCpuClassRqSet {
    fn migration_capacity_need(&self, placement: Placement) -> ostd::Result<CapacityNeed> {
        if !self.fair.root_migration_supported() {
            // A closed prepared group tree is not a legacy-root route. Future
            // live non-root admission must provide its own lease/generation.
            return Err(ostd::Error::InvalidArgs);
        }
        let (fair, rt) = match placement {
            Placement::Fair => (Some(self.fair.capacity_need()?), None),
            Placement::RealTime(priority) => (None, Some(self.real_time.capacity_need(priority)?)),
        };
        let throttled_required = self
            .throttled
            .len()
            .checked_add(self.throttled_reserved)
            .and_then(|count| count.checked_add(1))
            .ok_or(ostd::Error::Overflow)?;
        Ok(CapacityNeed {
            fair,
            rt,
            throttled_required,
            throttled_capacity: self.throttled.capacity(),
        })
    }

    fn can_install_migration_capacity(
        &self,
        prepared: &PreparedCapacity,
        placement: Placement,
    ) -> bool {
        let Ok(need) = self.migration_capacity_need(placement) else {
            return false;
        };
        let class_fits = match placement {
            Placement::Fair => prepared
                .fair
                .as_ref()
                .is_some_and(|p| self.fair.can_install_capacity(p)),
            Placement::RealTime(priority) => prepared
                .rt
                .as_ref()
                .is_some_and(|p| self.real_time.can_install_capacity(p, priority)),
        };
        class_fits
            && (need.throttled_required <= self.throttled.capacity()
                || prepared
                    .throttled
                    .as_ref()
                    .is_some_and(|storage| storage.capacity() >= need.throttled_required))
    }

    fn install_migration_capacity(
        &mut self,
        prepared: &mut PreparedCapacity,
        placement: Placement,
    ) {
        assert!(self.can_install_migration_capacity(prepared, placement));
        match placement {
            Placement::Fair => self
                .fair
                .install_and_reserve(prepared.fair.as_mut().unwrap()),
            Placement::RealTime(priority) => self
                .real_time
                .install_and_reserve(prepared.rt.as_mut().unwrap(), priority),
        }
        let required = self.throttled.len() + self.throttled_reserved + 1;
        if self.throttled.capacity() < required {
            let mut replacement = prepared.throttled.take().unwrap();
            assert!(replacement.is_empty() && replacement.capacity() >= required);
            replacement.append(&mut self.throttled);
            prepared.throttled = Some(core::mem::replace(&mut self.throttled, replacement));
        }
        self.throttled_reserved += 1;
    }

    fn release_migration_capacity(&mut self, placement: Placement) {
        assert!(self.throttled_reserved > 0);
        match placement {
            Placement::Fair => self.fair.release_reservation(),
            Placement::RealTime(priority) => self.real_time.release_reservation(priority),
        }
        self.throttled_reserved -= 1;
    }
}

impl ClassScheduler {
    pub(super) fn reserve_migration_capacity(
        &self,
        cpu: CpuId,
        placement: Placement,
    ) -> ostd::Result<MigrationCapacity<'_>> {
        ostd::task::atomic_mode::might_sleep();
        let rq = self
            .rqs
            .get(cpu.as_usize())
            .ok_or(ostd::Error::InvalidArgs)?;
        for _ in 0..8 {
            let need = {
                let _irq = disable_local();
                let locked = rq.lock();
                let need = locked.migration_capacity_need(placement)?;
                need
            };
            let mut prepared = need.allocate()?;
            let installed = {
                let _irq = disable_local();
                let mut rq = rq.lock();
                if rq.can_install_migration_capacity(&prepared, placement) {
                    rq.install_migration_capacity(&mut prepared, placement);
                    Some(&*rq as *const PerCpuClassRqSet as usize)
                } else {
                    None
                }
            };
            // Both unused preparation and retired empty buffers are destroyed
            // with IRQs restored and no runqueue lock, including stale retries.
            drop(prepared);
            if let Some(rq_identity) = installed {
                return Ok(MigrationCapacity {
                    scheduler: self,
                    cpu,
                    placement,
                    rq_identity,
                    live: true,
                });
            }
        }
        Err(ostd::Error::NotEnoughResources)
    }
}

#[cfg(ktest)]
mod tests;
