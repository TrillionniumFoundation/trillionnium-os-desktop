// SPDX-License-Identifier: MPL-2.0

//! Admission for external access to one existing Process or VMAR owner.
//! This is not an authority issuer or a journal. A committed fence is permanent
//! for that owner allocation; ordinary exec must not silently reopen it.

use crate::prelude::*;

pub(crate) struct ExternalMutationFence {
    state: Mutex<State>,
}

struct State {
    fenced: bool,
    active: u32,
}

impl ExternalMutationFence {
    pub(crate) fn new() -> Self {
        Self {
            state: Mutex::new(State {
                fenced: false,
                active: 0,
            }),
        }
    }

    /// The returned admission holds only a counter, never the mutex. Its
    /// lifetime covers the actual ptrace/alien-write/shared-clone operation,
    /// including faults, user copies and cleanup on every error path.
    pub(crate) fn enter(&self) -> Result<ExternalMutation<'_>> {
        let mut state = self.state.lock();
        if state.fenced {
            return_errno_with_message!(Errno::EPERM, "external access owner is fenced");
        }
        state.active = state.active.checked_add(1).ok_or_else(|| {
            Error::with_message(Errno::EOVERFLOW, "external access admission exhausted")
        })?;
        Ok(ExternalMutation { owner: self })
    }

    /// Reject in-flight work, then keep new admissions out while the caller
    /// validates all remaining owners. Dropping an uncommitted preparation
    /// changes nothing. Do not perform I/O or user copies while holding it.
    pub(crate) fn prepare_fence(&self) -> Result<PreparedExternalFence<'_>> {
        let state = self.state.lock();
        if state.active != 0 {
            return_errno_with_message!(Errno::EBUSY, "external access is in flight");
        }
        Ok(PreparedExternalFence { state })
    }

    pub(crate) fn is_fenced(&self) -> bool {
        self.state.lock().fenced
    }
}

pub(crate) struct ExternalMutation<'a> {
    owner: &'a ExternalMutationFence,
}

impl Drop for ExternalMutation<'_> {
    fn drop(&mut self) {
        let mut state = self.owner.state.lock();
        debug_assert!(state.active != 0);
        state.active -= 1;
    }
}

pub(crate) struct PreparedExternalFence<'a> {
    state: MutexGuard<'a, State>,
}

impl PreparedExternalFence<'_> {
    pub(crate) fn is_fenced(&self) -> bool {
        self.state.fenced
    }

    /// The caller commits only after all identity, tracer, alias and other
    /// in-flight checks have succeeded. There is intentionally no unseal API.
    pub(crate) fn commit(mut self) {
        self.state.fenced = true;
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::ktest;

    use super::*;

    #[ktest]
    fn in_flight_admission_rejects_fence_without_closing_the_owner() {
        let owner = ExternalMutationFence::new();
        let active = owner.enter().unwrap();
        assert_eq!(owner.prepare_fence().err().unwrap().error(), Errno::EBUSY);
        assert!(!owner.is_fenced());
        drop(active);
        let prepared = owner.prepare_fence().unwrap();
        drop(prepared);
        assert!(owner.enter().is_ok());
        owner.prepare_fence().unwrap().commit();
        assert_eq!(owner.enter().err().unwrap().error(), Errno::EPERM);
    }
}
