// SPDX-License-Identifier: MPL-2.0

//! Prepared replacement delegations on the same original CPU owner.
//!
//! The trusted Process transaction fences/reaps both predecessor images and
//! drains their original D namespaces before calling commit. This layer owns
//! only canonical CPU authorization; it never resets D, quota or accounting.

use alloc::vec::Vec;

use super::{watchdog::WatchdogOutcome, *};
use crate::prelude::{Errno, Error};

/// The original immutable watchdog terminal moved out at policy replacement.
/// It contains only Copy values, never a manager, grant origin or D namespace.
/// None records a policy that had not fired at this exact owner cut.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct CpuPolicyRetirement {
    terminal: Option<(WatchdogOutcome, Option<u64>)>,
}

impl CpuPolicyRetirement {
    pub(super) fn from_retired(policy: &TrustedCpuManagement) -> Self {
        Self {
            terminal: policy.watchdog.terminal,
        }
    }

    pub(crate) fn status_code(self) -> u8 {
        self.terminal.map_or(0, |(outcome, _)| outcome.code())
    }

    pub(crate) fn evaluated_ns(self) -> Option<u64> {
        self.terminal.and_then(|(_, time)| time)
    }

    pub(crate) fn resource_receipt(self) -> Option<os_control::NativeResourceReceipt> {
        match self.terminal {
            Some((WatchdogOutcome::Restored(receipt), _)) => Some(receipt),
            _ => None,
        }
    }
}

/// All fallible preparation precedes owner publication. Dropping an uncommitted
/// plan destroys only its fresh snapshots; no previous owner state changes.
pub(crate) struct PreparedCpuSuccessor {
    predecessors: [Arc<NativeCpuManager>; 2],
    managers: [Arc<NativeCpuManager>; 2],
    grants: Option<[ManagementGrantState; 2]>,
    issued_ns: u64,
    expires_ns: u64,
}

impl NativeCpuManager {
    #[cfg(feature = "g2-trusted-daemon")]
    pub(crate) fn prepare_successor_pair(
        predecessors: [Arc<Self>; 2],
        publishers: [PublisherId; 2],
    ) -> crate::prelude::Result<PreparedCpuSuccessor> {
        let issued = aster_time::try_read_monotonic_sample()
            .and_then(|sample| sample.checked_nanos())
            .ok_or_else(|| {
                Error::with_message(Errno::EIO, "successor requires the original clock")
            })?;
        PreparedCpuSuccessor::prepare(predecessors, publishers, issued)
    }
}

impl PreparedCpuSuccessor {
    pub(super) fn prepare(
        predecessors: [Arc<NativeCpuManager>; 2],
        publishers: [PublisherId; 2],
        issued_ns: u64,
    ) -> crate::prelude::Result<Self> {
        if predecessors[0].index != 0
            || predecessors[1].index != 1
            || !Arc::ptr_eq(&predecessors[0].observer, &predecessors[1].observer)
            || publishers[0] == publishers[1]
            || publishers.iter().any(|publisher| {
                predecessors
                    .iter()
                    .any(|previous| previous.publisher() == *publisher)
            })
        {
            return Err(Error::with_message(
                Errno::ESTALE,
                "successor requires a fresh pair on one owner",
            ));
        }
        let expires_ns = issued_ns
            .checked_add(INITIAL_LEASE_NS)
            .ok_or_else(|| Error::with_message(Errno::EOVERFLOW, "successor lease overflow"))?;
        let recovery_expires_ns = expires_ns.checked_add(RECOVERY_GRACE_NS).ok_or_else(|| {
            Error::with_message(Errno::EOVERFLOW, "successor recovery endpoint overflow")
        })?;
        let observer = &predecessors[0].observer;
        let make = |index: usize, end: u64| -> crate::prelude::Result<_> {
            let state = ManagementGrantState::new(ManagementGrantConfig {
                id: ManagementGrantId::new(publishers[index].bytes()),
                publisher: publishers[index],
                target: observer.target.id(),
                stable_object_id: observer.target.stable_object_id(),
                epoch: 1,
                issued_at_ns: issued_ns,
                expires_at_ns: end,
                max_cap_ns: MAX_INITIAL_CAP_NS,
            })
            .map_err(|_| Error::with_message(Errno::EINVAL, "invalid successor delegation"))?;
            let grant = NativeGrant::from_management(
                observer.target.clone(),
                state.snapshot().unwrap(),
                Vec::new(),
            )
            .map_err(|_| Error::with_message(Errno::EINVAL, "invalid successor target"))?;
            let manager = Arc::new(NativeCpuManager {
                observer: observer.clone(),
                grant,
                index,
                issued_ns,
                expires_ns: end,
            });
            Ok((state, manager))
        };
        let [(manager_state, manager), (recovery_state, recovery)] =
            [make(0, expires_ns)?, make(1, recovery_expires_ns)?];
        Ok(Self {
            predecessors,
            managers: [manager, recovery],
            grants: Some([manager_state, recovery_state]),
            issued_ns,
            expires_ns,
        })
    }

    pub(crate) fn managers(&self) -> [Arc<NativeCpuManager>; 2] {
        [self.managers[0].clone(), self.managers[1].clone()]
    }

    /// Publish only after the original Process transaction has prepared every
    /// image, slot and parent relation. This does not revive any old snapshot.
    #[cfg(feature = "g2-trusted-daemon")]
    pub(crate) fn commit(mut self) -> crate::prelude::Result<CpuPolicyRetirement> {
        if ostd::cpu::all_cpus().count() != 1 {
            return Err(Error::with_message(
                Errno::EOPNOTSUPP,
                "successor requires N0",
            ));
        }
        let _membership = CgroupMembership::write_lock();
        let retired = crate::sched::with_current_cpu_bandwidth_settled(|now| self.commit_at(now))?;
        drop(_membership);
        // commit_at moved this entire old policy out under the same CpuMax
        // lock that published its replacement. No old tick can mutate it,
        // including one that fired after preparation but before that cut.
        let receipt = CpuPolicyRetirement::from_retired(&retired);
        // Destruction of old origin/status references is outside bandwidth,
        // runqueue and membership locks, just as all new allocation was.
        drop(retired);
        Ok(receipt)
    }

    pub(super) fn commit_at(
        &mut self,
        now: Option<u64>,
    ) -> crate::prelude::Result<TrustedCpuManagement> {
        let now = now
            .filter(|now| *now >= self.issued_ns && *now < self.expires_ns)
            .ok_or_else(|| {
                Error::with_message(Errno::ESTALE, "successor clock cut is outside its lease")
            })?;
        let observer = &self.managers[0].observer;
        let current = observer.node.controller().cpu.read();
        if !Arc::ptr_eq(&current.get(), &observer.owner) {
            return Err(Error::with_message(
                Errno::ESTALE,
                "successor CPU owner was replaced",
            ));
        }
        let control = observer.owner.inner.as_ref().unwrap().control()?;
        let mut state = control.max.lock();
        if self.grants.is_none()
            || state.is_detached
            || !state.watchdog_registered
            || now < state.max.last_observed_ns
            || state.max.accounting_fault
            || state.max.period_ns() != CPU_PERIOD_NS
            || state
                .native
                .as_ref()
                .is_none_or(|native| native.is_fenced())
        {
            return Err(Error::with_message(
                Errno::ESTALE,
                "successor owner is unavailable",
            ));
        }
        let previous = state
            .trusted_management
            .as_ref()
            .ok_or_else(|| Error::with_message(Errno::ESTALE, "previous CPU policy disappeared"))?;
        if previous
            .grants
            .iter()
            .zip(&self.predecessors)
            .any(|(grant, predecessor)| {
                !grant.owns_snapshot(predecessor.delegation()) || !grant.is_revoked()
            })
        {
            return Err(Error::with_message(
                Errno::EBUSY,
                "both exact previous delegations must be closed",
            ));
        }
        let workload = previous
            .watchdog
            .workload
            .as_ref()
            .filter(|workload| !workload.is_zombie())
            .ok_or_else(|| Error::with_message(Errno::ESTALE, "original workload ended"))?
            .clone();
        let mut watchdog = WatchdogState::new();
        watchdog.armed = true;
        watchdog.delegation = Some(self.managers[0].delegation().clone());
        watchdog.workload = Some(workload);
        let replacement = TrustedCpuManagement {
            grants: self.grants.take().unwrap(),
            manager_expires_ns: self.expires_ns,
            restore_cap_ns: previous.restore_cap_ns,
            manager_closed: ManagerClosure::Open,
            // The original source of the unchanged current cap survives the
            // delegation transition, including zero/user-pause ambiguity.
            budget_cause: previous.budget_cause,
            recovery_consumed: false,
            watchdog,
        };
        Ok(state.trusted_management.replace(replacement).unwrap())
    }
}
