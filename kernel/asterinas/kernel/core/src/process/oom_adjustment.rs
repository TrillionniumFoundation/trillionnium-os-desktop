// SPDX-License-Identifier: MPL-2.0

//! OOM adjustment authority and shared-address-space lifecycle.
//!
//! Lock order: process VMAR mutex (when publishing a VM change), transition
//! mutex, then one IRQ-safe adjustment-state spinlock. Writers capture capability before
//! the transition and never acquire VMAR, PID-table, TaskSet or credential
//! locks within it. Registry growth and VM-identity destruction occur outside
//! the transition. Dead weak storage can be reclaimed without a Process or VM
//! destructor. VMAR/transition mutexes may sleep; owner Drop only
//! invalidates state and never acquires the transition mutex.

use ostd::sync::LocalIrqDisabled;

use super::{
    CloneFlags, INIT_PROCESS_PID, Pid, Process, UserNamespace, VmarSnapshot,
    credentials::capabilities::CapSet, posix_thread::PosixThread,
};
use crate::{prelude::*, security::lsm::hooks as lsm_hooks, vm::vmar::Vmar};

pub(super) enum OomInit<'a> {
    Initial(i16),
    Fork {
        parent: &'a Process,
        flags: CloneFlags,
    },
}

pub(crate) struct OomScoreAdj(Arc<Adjustment>);

struct Adjustment {
    pid: Pid,
    state: SpinLock<State, LocalIrqDisabled>,
}

struct State {
    pair: Pair,
    vm: Option<VmarSnapshot>,
    is_vfork: bool,
}

#[derive(Clone, Copy)]
struct Pair {
    current: i16,
    authorized_min: i16,
}

// Weak entries neither retain a Process nor require owner Drop to sleep.
// A dead weak's destruction frees only its allocation, not Process or VM data.
static TRANSITIONS: Mutex<Vec<Weak<Adjustment>>> = Mutex::new(Vec::new());

impl OomScoreAdj {
    pub(super) fn new(pid: Pid, vmar: &Arc<Vmar>, init: OomInit<'_>) -> Self {
        let adjustment = Arc::new(Adjustment {
            pid,
            state: SpinLock::new(State {
                pair: Pair {
                    current: 0,
                    authorized_min: 0,
                },
                // A Weak retains the allocation identity, preventing address
                // reuse without retaining the old VM's physical mappings.
                vm: Some(Arc::downgrade(vmar).into()),
                is_vfork: matches!(&init, OomInit::Fork { flags, .. } if flags.contains(CloneFlags::CLONE_VFORK)),
            }),
        });
        let mut spare = Vec::new();
        loop {
            let mut registry = TRANSITIONS.lock();
            if registry.len() == registry.capacity() {
                registry.retain(|member| member.strong_count() != 0);
            }
            let required = registry.len().checked_add(1).expect("too many OOM members");
            if registry.capacity() < required && spare.capacity() < required {
                let capacity = required.checked_mul(2).unwrap_or(required);
                drop(registry);
                // Process construction already uses infallible Arc/Task
                // metadata. This stage does not claim full memory admission.
                spare = Vec::with_capacity(capacity);
                continue;
            }
            if registry.capacity() < required {
                spare.extend(registry.drain(..));
                core::mem::swap(&mut *registry, &mut spare);
            }
            let pair = match init {
                OomInit::Initial(value) => Pair {
                    current: value,
                    authorized_min: value,
                },
                OomInit::Fork { parent, .. } => parent.oom_score_adj().0.state.lock().pair,
            };
            adjustment.state.lock().pair = pair;
            registry.push(Arc::downgrade(&adjustment));
            drop(registry);
            // `spare` now contains only the old, empty vector allocation.
            drop(spare);
            return Self(adjustment);
        }
    }

    pub(crate) fn read(&self) -> i16 {
        self.0.state.lock().pair.current
    }

    pub(crate) fn write_from(&self, value: i32, writer: &PosixThread) -> Result<()> {
        let value = Self::validate_value(value)?;
        // Linux v6.2 uses capable(), i.e. the initial user namespace, for both
        // floor denial and privileged floor replacement. File DAC is separate.
        let privileged = lsm_hooks::on_capable(lsm_hooks::CapableContext::new(
            UserNamespace::get_init_singleton().as_ref(),
            writer,
            CapSet::SYS_RESOURCE,
        ))
        .is_ok();
        let registry = TRANSITIONS.lock();
        let vm = {
            let mut target = self.0.state.lock();
            if value < target.pair.authorized_min && !privileged {
                return_errno_with_message!(
                    Errno::EACCES,
                    "the OOM adjustment is below the authorized minimum"
                );
            }
            target.pair.current = value;
            if privileged {
                target.pair.authorized_min = value;
            }
            if target.is_vfork {
                None
            } else {
                target.vm.clone()
            }
        };
        if let Some(vm) = &vm {
            for member in registry.iter() {
                let Some(member) = member.upgrade() else {
                    continue;
                };
                if Arc::ptr_eq(&member, &self.0) || member.pid == INIT_PROCESS_PID {
                    continue;
                }
                let mut peer = member.state.lock();
                if peer.is_vfork || !peer.vm.as_ref().is_some_and(|peer_vm| peer_vm.ptr_eq(vm)) {
                    continue;
                }
                // Like Linux __set_oom_adj, an unprivileged propagation
                // changes current but never grants a new authorized floor.
                peer.pair.current = value;
                if privileged {
                    peer.pair.authorized_min = value;
                }
            }
        }
        drop(registry);
        drop(vm);
        Ok(())
    }

    pub(crate) fn validate_value(value: i32) -> Result<i16> {
        if !(OOM_SCORE_ADJ_MIN..=OOM_SCORE_ADJ_MAX).contains(&value) {
            return_errno_with_message!(Errno::EINVAL, "the OOM score adjustment is out of range");
        }
        Ok(value as i16)
    }

    /// Publishes the VM identity and its OOM membership in one transition.
    ///
    /// The caller holds the original process VMAR mutex. Returned old VM and
    /// replaced weak identity are destroyed after releasing the transition.
    pub(super) fn replace_vm(
        &self,
        slot: &mut Option<Arc<Vmar>>,
        new_vm: Option<Arc<Vmar>>,
    ) -> Option<Arc<Vmar>> {
        let identity = new_vm.as_ref().map(|vm| Arc::downgrade(vm).into());
        let (old_vm, old_identity) = {
            let _transition = TRANSITIONS.lock();
            let mut state = self.0.state.lock();
            let old_identity = core::mem::replace(&mut state.vm, identity);
            // Exec has a new VM and keeps its own pair; exit has no cohort.
            state.is_vfork = false;
            (core::mem::replace(slot, new_vm), old_identity)
        };
        drop(old_identity);
        old_vm
    }
}

impl Drop for OomScoreAdj {
    fn drop(&mut self) {
        // The last Process reference can disappear in atomic context. Never
        // wait on TRANSITIONS here. A concurrent writer serializes with this
        // invalidation on the same state spinlock and cannot revive the VM.
        let old_identity = self.0.state.lock().vm.take();
        drop(old_identity);
    }
}

const OOM_SCORE_ADJ_MIN: i32 = -1000;
const OOM_SCORE_ADJ_MAX: i32 = 1000;

#[cfg(ktest)]
mod tests;
