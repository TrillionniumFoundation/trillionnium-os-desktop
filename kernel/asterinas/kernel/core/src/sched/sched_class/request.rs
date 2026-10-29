// SPDX-License-Identifier: MPL-2.0

//! One in-kernel affinity attempt. This is not a durable/native delivery log.
//! Finish and cancellation must occur outside every runqueue lock.

use alloc::sync::Arc;
use core::fmt;

use ostd::{
    cpu::{CpuId, CpuSet},
    sync::{LocalIrqDisabled, SpinLock, Waker},
    task::Task,
};

use super::capacity::{MigrationCapacity, Placement};
use crate::{prelude::Errno, thread::Thread};

pub(super) type Outcome = core::result::Result<(), Errno>;

#[derive(Clone, Copy)]
enum Stage {
    Pending,
    Claimed,
    Complete(Outcome),
}

struct State<'a> {
    stage: Stage,
    capacity: Option<MigrationCapacity<'a>>,
    controller: Option<Arc<Waker>>,
}

pub(super) struct AffinityRequest<'a> {
    generation: u64,
    destination: CpuId,
    placement: Placement,
    // Tick/physical-switch readers can interrupt a sleepable controller.
    // Protect the short state section against same-CPU IRQ reentry as well.
    state: SpinLock<State<'a>, LocalIrqDisabled>,
}

/// Return cancelled preparation to the outer caller for destruction after all
/// rq/IRQ scopes. Taking it from State prevents Drop under the state spinlock.
#[must_use]
pub(super) struct Finished<'a> {
    pub(super) changed: bool,
    pub(super) unused_capacity: Option<MigrationCapacity<'a>>,
}

impl<'a> AffinityRequest<'a> {
    pub(super) fn new(
        generation: u64,
        capacity: MigrationCapacity<'a>,
        controller: Option<Arc<Waker>>,
    ) -> ostd::Result<Arc<Self>> {
        ostd::task::atomic_mode::might_sleep();
        Arc::try_new(Self {
            generation,
            destination: capacity.destination(),
            placement: capacity.placement(),
            state: SpinLock::new(State {
                stage: Stage::Pending,
                capacity: Some(capacity),
                controller,
            }),
        })
        .map_err(|_| ostd::Error::NoMemory)
    }

    pub(super) fn generation(&self) -> u64 {
        self.generation
    }
    pub(super) fn destination(&self) -> CpuId {
        self.destination
    }
    pub(super) fn placement(&self) -> Placement {
        self.placement
    }

    pub(super) fn outcome(&self) -> Option<Outcome> {
        match self.state.lock().stage {
            Stage::Complete(outcome) => Some(outcome),
            _ => None,
        }
    }

    /// The sole off-CPU Task owner takes the already prepared destination.
    /// It must not call finish until it has either published or restored that
    /// owner; the flag is not itself permission to detach a runnable Task.
    pub(super) fn claim(&self) -> Option<MigrationCapacity<'a>> {
        let mut state = self.state.lock();
        if !matches!(state.stage, Stage::Pending) {
            return None;
        }
        state.stage = Stage::Claimed;
        Some(
            state
                .capacity
                .take()
                .expect("pending affinity capacity missing"),
        )
    }

    /// All external rq locks must already be released. Preserve the first
    /// terminal result and notify only after releasing the request spinlock.
    pub(super) fn finish(&self, outcome: Outcome) -> Finished<'a> {
        let (unused_capacity, controller) = {
            let mut state = self.state.lock();
            if matches!(state.stage, Stage::Complete(_)) {
                return Finished {
                    changed: false,
                    unused_capacity: None,
                };
            }
            state.stage = Stage::Complete(outcome);
            (state.capacity.take(), state.controller.take())
        };
        if let Some(controller) = controller {
            controller.wake_up();
        }
        Finished {
            changed: true,
            unused_capacity,
        }
    }

    /// A non-owner may acknowledge placement only before the Task owner has
    /// claimed its ticket. After claim, that owner completes after publication.
    pub(super) fn finish_if_pending(&self, outcome: Outcome) -> Option<Finished<'a>> {
        let (unused_capacity, controller) = {
            let mut state = self.state.lock();
            match state.stage {
                Stage::Claimed => return None,
                Stage::Complete(_) => {
                    return Some(Finished {
                        changed: false,
                        unused_capacity: None,
                    });
                }
                Stage::Pending => {
                    state.stage = Stage::Complete(outcome);
                    (state.capacity.take(), state.controller.take())
                }
            }
        };
        if let Some(controller) = controller {
            controller.wake_up();
        }
        Some(Finished {
            changed: true,
            unused_capacity,
        })
    }

    /// Policy writers yield without keeping the administration mutex or
    /// allocating a new waiter after activation. The actual external affinity
    /// caller uses its separately preallocated waiter; a self caller yields.
    pub(super) fn wait(&self) -> Outcome {
        loop {
            if let Some(outcome) = self.outcome() {
                return outcome;
            }
            Task::yield_now();
        }
    }
}

impl fmt::Debug for AffinityRequest<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("AffinityRequest")
            .field("generation", &self.generation)
            .field("destination", &self.destination)
            .field("placement", &self.placement)
            .finish_non_exhaustive()
    }
}

impl super::SchedAttr {
    pub(super) fn affinity_request(&self) -> Option<Arc<AffinityRequest<'static>>> {
        self.affinity_request.lock().clone()
    }

    pub(super) fn install_affinity_request(
        &self,
        request: Arc<AffinityRequest<'static>>,
        thread: &Thread,
        mask: &CpuSet,
    ) -> Option<Arc<AffinityRequest<'static>>> {
        let mut slot = self.affinity_request.lock();
        assert!(
            slot.as_ref().is_none_or(|old| old.outcome().is_some()),
            "unfinished affinity request replaced"
        );
        // Every producer consults this slot before publication. Keep the
        // request and complete mask publication indivisible to that observer;
        // no runqueue may be acquired while this guard is held.
        thread
            .atomic_cpu_affinity()
            .store(mask, core::sync::atomic::Ordering::Release);
        slot.replace(request)
    }

    pub(super) fn retire_affinity_request(
        &self,
        request: &Arc<AffinityRequest<'static>>,
    ) -> Option<Arc<AffinityRequest<'static>>> {
        let mut slot = self.affinity_request.lock();
        if slot.as_ref().is_some_and(|old| Arc::ptr_eq(old, request)) {
            slot.take()
        } else {
            None
        }
    }
}

#[cfg(ktest)]
mod tests;
