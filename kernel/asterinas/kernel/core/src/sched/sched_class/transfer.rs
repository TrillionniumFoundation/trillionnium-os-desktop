// SPDX-License-Identifier: MPL-2.0

//! Physical queue removal tokens used by the affinity request state machine.
//! A caller must restore or commit every live token
//! under its original rq; no second runnable staging queue is introduced.

use super::*;

enum SourcePlacement {
    Fair(fair::RemovedFair),
    RealTime(real_time::RemovedRt),
    Throttled(Arc<Task>),
}

#[must_use]
pub(super) struct RemovedEntity {
    cpu: CpuId,
    rq_identity: usize,
    placement: SourcePlacement,
    debt: u64,
    live: bool,
}

impl RemovedEntity {
    pub(super) fn task(&self) -> &Arc<Task> {
        match &self.placement {
            SourcePlacement::Fair(token) => token.task(),
            SourcePlacement::RealTime(token) => token.task(),
            SourcePlacement::Throttled(task) => task,
        }
    }

    pub(super) fn debt(&self) -> u64 {
        self.debt
    }
}

/// The production control path must wrap a detached entry before doing any
/// fallible work. Before publication Drop restores; afterwards it only refunds
/// the old physical slot. Never drop it while any rq lock is held.
pub(super) struct QueuedRemoval<'a> {
    scheduler: &'a ClassScheduler,
    token: Option<RemovedEntity>,
    published: bool,
}

impl<'a> QueuedRemoval<'a> {
    pub(super) fn new(scheduler: &'a ClassScheduler, token: RemovedEntity) -> Self {
        Self {
            scheduler,
            token: Some(token),
            published: false,
        }
    }
    pub(super) fn task(&self) -> &Arc<Task> {
        self.token.as_ref().unwrap().task()
    }
    pub(super) fn debt(&self) -> u64 {
        self.token.as_ref().unwrap().debt()
    }
    pub(super) fn disarm_rollback(&mut self) {
        assert!(!self.published);
        self.published = true;
    }
}

impl Drop for QueuedRemoval<'_> {
    fn drop(&mut self) {
        let Some(mut token) = self.token.take() else {
            return;
        };
        let _irq = disable_local();
        let mut rq = self.scheduler.rqs[token.cpu.as_usize()].lock();
        if self.published {
            rq.commit_removed_task(&mut token);
        } else {
            rq.restore_removed_task(token);
        }
    }
}

impl PerCpuClassRqSet {
    pub(super) fn take_queued_task(
        &mut self,
        task: &Arc<Task>,
    ) -> ostd::Result<Option<RemovedEntity>> {
        if !self.fair.root_migration_supported() {
            return Err(ostd::Error::InvalidArgs);
        }
        // Reserved incoming, physical outgoing and a Wait/Exit retry are not
        // selectable queued Tasks. Their producer must perform the handoff.
        if self
            .current
            .as_ref()
            .is_some_and(|(entity, _)| Arc::ptr_eq(&entity.0, task))
            || self
                .dequeued
                .as_ref()
                .is_some_and(|old| Arc::ptr_eq(&old.entity.0, task))
            || self
                .switching
                .as_ref()
                .is_some_and(|pending| Arc::ptr_eq(&pending.previous.entity.0, task))
        {
            return Ok(None);
        }
        let relative_debt = self.fair.debt(task)?;
        let (placement, debt) = if let Some(token) = self.fair.take_task(task)? {
            let debt = token.debt();
            (SourcePlacement::Fair(token), debt)
        } else if let Some(token) = self.real_time.take_task(task) {
            (SourcePlacement::RealTime(token), relative_debt)
        } else if let Some(index) = self
            .throttled
            .iter()
            .position(|queued| Arc::ptr_eq(queued, task))
        {
            let task = self.throttled.swap_remove(index);
            // Throttled Tasks own no FAIR/RT queued weight. Only preserve the
            // released vector slot; their original bandwidth owner is intact.
            self.throttled_reserved += 1;
            (SourcePlacement::Throttled(task), relative_debt)
        } else {
            return Ok(None);
        };
        Ok(Some(RemovedEntity {
            cpu: self.cpu,
            rq_identity: self as *const PerCpuClassRqSet as usize,
            placement,
            debt,
            live: true,
        }))
    }

    pub(super) fn restore_removed_task(&mut self, mut token: RemovedEntity) {
        assert!(token.live && token.cpu == self.cpu);
        assert_eq!(
            token.rq_identity, self as *const PerCpuClassRqSet as usize,
            "removal belongs to another runqueue"
        );
        match token.placement {
            SourcePlacement::Fair(fair) => self.fair.restore_task(fair),
            SourcePlacement::RealTime(rt) => self.real_time.restore_task(rt),
            SourcePlacement::Throttled(task) => {
                assert!(self.throttled_reserved > 0);
                self.throttled_reserved -= 1;
                assert!(self.throttled.len() < self.throttled.capacity());
                self.throttled.push(task);
            }
        }
        token.live = false;
    }

    pub(super) fn commit_removed_task(&mut self, token: &mut RemovedEntity) {
        assert!(token.live && token.cpu == self.cpu);
        assert_eq!(
            token.rq_identity, self as *const PerCpuClassRqSet as usize,
            "removal belongs to another runqueue"
        );
        match &mut token.placement {
            SourcePlacement::Fair(fair) => self.fair.commit_removed(fair),
            SourcePlacement::RealTime(rt) => self.real_time.commit_removed(rt),
            SourcePlacement::Throttled(_) => {
                assert!(self.throttled_reserved > 0);
                self.throttled_reserved -= 1;
            }
        }
        token.live = false;
    }
}

#[cfg(ktest)]
mod tests;
