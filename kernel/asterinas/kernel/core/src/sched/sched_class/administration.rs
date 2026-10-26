// SPDX-License-Identifier: MPL-2.0

//! Sleepable policy writer serialization; rq readers use only the policy spinlock.

use core::ops::Deref;

use ostd::sync::MutexGuard;

use super::{LinuxSchedPolicy, Nice, SchedAttr, SchedPolicy};

#[derive(Debug)]
pub(super) struct AdministrationState {
    nice: Nice,
    user_idle: bool,
}

impl AdministrationState {
    pub(super) fn new(policy: SchedPolicy) -> Self {
        Self {
            nice: match policy {
                SchedPolicy::Fair(nice) => nice,
                _ => Nice::default(),
            },
            user_idle: false,
        }
    }
}

pub(crate) struct SchedAdministration<'a> {
    attr: &'a SchedAttr,
    state: MutexGuard<'a, AdministrationState>,
}

impl SchedAttr {
    pub(crate) fn administer(&self) -> SchedAdministration<'_> {
        ostd::task::atomic_mode::might_sleep();
        SchedAdministration {
            attr: self,
            state: self.administration.lock(),
        }
    }
}

impl Deref for SchedAdministration<'_> {
    type Target = SchedAttr;
    fn deref(&self) -> &Self::Target {
        self.attr
    }
}

impl SchedAdministration<'_> {
    pub(crate) fn nice(&self) -> Nice {
        self.state.nice
    }

    pub(crate) fn user_policy(&self) -> LinuxSchedPolicy {
        if self.state.user_idle {
            LinuxSchedPolicy::Idle
        } else {
            self.policy().into()
        }
    }

    pub(crate) fn set_policy(&mut self, policy: SchedPolicy) {
        if let SchedPolicy::Fair(nice) = policy {
            self.state.nice = nice;
        }
        self.state.user_idle = false;
        self.attr.apply_policy(policy);
    }

    pub(crate) fn set_user_idle(&mut self) {
        // Idle's queue weight does not replace the retained static nice.
        self.state.user_idle = true;
        self.attr.apply_policy(SchedPolicy::Fair(Nice::MAX));
    }

    /// Controlled tests only. The callback is pure under the short policy lock.
    #[cfg(ktest)]
    pub(crate) fn update_policy<T>(&mut self, update: impl FnOnce(&mut SchedPolicy) -> T) -> T {
        let value = self.attr.apply_policy_update(update);
        if let SchedPolicy::Fair(nice) = self.policy() {
            self.state.nice = nice;
        }
        value
    }
}

#[cfg(ktest)]
mod tests;
