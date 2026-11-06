//! Object- and connection-bound engine retirement completion bookkeeping.
//! Used by the real presenter around its drain, Wayland sync, and endpoint ACK.
//! This module does not decide whether buffers or engine windows are retired.

use std::collections::BTreeMap;
use droidloom_denial_protocol::{MAX_TASK_OBJECTS, RetirementNonce, TaskObjectId};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct RetirementToken {
    pub(super) generation: u64,
    pub(super) object: TaskObjectId,
    pub(super) nonce: RetirementNonce,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum RetirementError {
    Disconnected,
    GenerationExhausted,
    InvalidIdentity,
    AlreadyPending,
    Capacity,
    StaleOrMissing,
    WrongPhase,
    WrongCallback,
    ObjectStillLive,
}
impl std::fmt::Display for RetirementError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for RetirementError {}

#[derive(Debug)]
enum Phase<C> {
    AwaitingDrain,
    Barrier(C),
    CompletionAttempted,
}

#[derive(Debug)]
struct Pending<C> {
    token: RetirementToken,
    phase: Phase<C>,
}

#[derive(Debug)]
pub(super) struct EngineRetirements<C> {
    generation: u64,
    connected: bool,
    pending: BTreeMap<TaskObjectId, Pending<C>>,
}

impl<C: Eq> EngineRetirements<C> {
    pub(super) fn new() -> Self {
        Self { generation: 0, connected: false, pending: BTreeMap::new() }
    }

    pub(super) fn connect(&mut self) -> Result<(), RetirementError> {
        if self.connected || !self.pending.is_empty() {
            return Err(RetirementError::AlreadyPending);
        }
        self.generation = self.generation.checked_add(1)
            .ok_or(RetirementError::GenerationExhausted)?;
        self.connected = true;
        Ok(())
    }

    pub(super) fn disconnect(&mut self) {
        // Dropping callback handles does not assert that any old peer retired.
        self.connected = false;
        self.pending.clear();
    }

    pub(super) fn begin(
        &mut self, object: TaskObjectId, nonce: RetirementNonce,
    ) -> Result<RetirementToken, RetirementError> {
        if !self.connected { return Err(RetirementError::Disconnected); }
        if object.0 == 0 || nonce.0 == 0 { return Err(RetirementError::InvalidIdentity); }
        if self.pending.contains_key(&object) { return Err(RetirementError::AlreadyPending); }
        if self.pending.len() >= usize::try_from(MAX_TASK_OBJECTS).unwrap_or(usize::MAX) {
            return Err(RetirementError::Capacity);
        }
        let token = RetirementToken { generation: self.generation, object, nonce };
        self.pending.insert(object, Pending { token, phase: Phase::AwaitingDrain });
        Ok(token)
    }

    pub(super) fn drained(
        &self, mut object_exists: impl FnMut(TaskObjectId) -> bool,
    ) -> Vec<RetirementToken> {
        if !self.connected { return Vec::new(); }
        self.pending.values().filter_map(|entry| {
            (matches!(&entry.phase, Phase::AwaitingDrain) && !object_exists(entry.token.object))
                .then_some(entry.token)
        }).collect()
    }

    pub(super) fn bind_barrier(
        &mut self, token: RetirementToken, callback: C,
    ) -> Result<(), RetirementError> {
        let entry = self.current_mut(token)?;
        if !matches!(&entry.phase, Phase::AwaitingDrain) {
            return Err(RetirementError::WrongPhase);
        }
        entry.phase = Phase::Barrier(callback);
        Ok(())
    }

    pub(super) fn begin_completion(
        &mut self, token: RetirementToken, callback: &C, object_still_live: bool,
    ) -> Result<bool, RetirementError> {
        // Wayland callbacks from a disconnected endpoint are benign late
        // observations. They can never complete a new peer's identical object.
        if !self.connected || token.generation != self.generation { return Ok(false); }
        let entry = self.current_mut(token)?;
        match &entry.phase {
            Phase::Barrier(expected) if expected == callback => {}
            Phase::Barrier(_) => return Err(RetirementError::WrongCallback),
            _ => return Err(RetirementError::WrongPhase),
        }
        if object_still_live { return Err(RetirementError::ObjectStillLive); }
        // Record before crossing into endpoint.send_denial. A send error
        // cannot cause another ACK attempt or be converted into completion.
        entry.phase = Phase::CompletionAttempted;
        Ok(true)
    }

    pub(super) fn finish(
        &mut self, token: RetirementToken,
    ) -> Result<(), RetirementError> {
        let entry = self.current_mut(token)?;
        if !matches!(&entry.phase, Phase::CompletionAttempted) {
            return Err(RetirementError::WrongPhase);
        }
        self.pending.remove(&token.object);
        Ok(())
    }

    fn current_mut(
        &mut self, token: RetirementToken,
    ) -> Result<&mut Pending<C>, RetirementError> {
        if !self.connected || token.generation != self.generation {
            return Err(RetirementError::StaleOrMissing);
        }
        self.pending.get_mut(&token.object)
            .filter(|entry| entry.token == token)
            .ok_or(RetirementError::StaleOrMissing)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const OBJECT: TaskObjectId = TaskObjectId(7);
    const NONCE: RetirementNonce = RetirementNonce(9);

    fn pending() -> (EngineRetirements<u64>, RetirementToken) {
        let mut ledger = EngineRetirements::new();
        ledger.connect().unwrap();
        let token = ledger.begin(OBJECT, NONCE).unwrap();
        (ledger, token)
    }

    #[test]
    fn engine_drain_and_exact_callback_both_precede_completion() {
        let (mut ledger, token) = pending();
        assert!(ledger.drained(|_| true).is_empty());
        assert_eq!(ledger.drained(|_| false), vec![token]);
        assert_eq!(ledger.begin_completion(token, &11, false), Err(RetirementError::WrongPhase));
        ledger.bind_barrier(token, 11).unwrap();
        assert!(ledger.drained(|_| false).is_empty());
        assert!(ledger.begin_completion(token, &11, false).unwrap());
        ledger.finish(token).unwrap();
        assert!(ledger.pending.is_empty());
    }

    #[test]
    fn engine_live_object_blocks_callback_without_consuming_it() {
        let (mut ledger, token) = pending();
        ledger.bind_barrier(token, 11).unwrap();
        assert_eq!(ledger.begin_completion(token, &11, true), Err(RetirementError::ObjectStillLive));
        assert!(ledger.begin_completion(token, &11, false).unwrap());
    }

    #[test]
    fn engine_wrong_object_or_nonce_cannot_complete_owned_request() {
        let (mut ledger, token) = pending();
        ledger.bind_barrier(token, 11).unwrap();
        for wrong in [
            RetirementToken { object: TaskObjectId(8), ..token },
            RetirementToken { nonce: RetirementNonce(10), ..token },
        ] {
            assert_eq!(ledger.begin_completion(wrong, &11, false), Err(RetirementError::StaleOrMissing));
        }
        assert!(ledger.begin_completion(token, &11, false).unwrap());
    }

    #[test]
    fn engine_wrong_callback_preserves_original_barrier() {
        let (mut ledger, token) = pending();
        ledger.bind_barrier(token, 11).unwrap();
        assert_eq!(ledger.begin_completion(token, &12, false), Err(RetirementError::WrongCallback));
        assert!(ledger.begin_completion(token, &11, false).unwrap());
    }

    #[test]
    fn engine_disconnected_callback_produces_no_completion() {
        let (mut ledger, token) = pending();
        ledger.bind_barrier(token, 11).unwrap();
        ledger.disconnect();
        assert!(!ledger.begin_completion(token, &11, false).unwrap());
        assert!(ledger.pending.is_empty());
    }

    #[test]
    fn engine_old_peer_callback_cannot_complete_identical_new_tuple() {
        let (mut ledger, old) = pending();
        ledger.bind_barrier(old, 11).unwrap();
        ledger.disconnect();
        ledger.connect().unwrap();
        let new = ledger.begin(OBJECT, NONCE).unwrap();
        ledger.bind_barrier(new, 11).unwrap();
        assert_ne!(old.generation, new.generation);
        assert!(!ledger.begin_completion(old, &11, false).unwrap());
        assert!(ledger.begin_completion(new, &11, false).unwrap());
    }

    #[test]
    fn engine_duplicate_callback_cannot_retry_failed_ack_attempt() {
        let (mut ledger, token) = pending();
        ledger.bind_barrier(token, 11).unwrap();
        assert!(ledger.begin_completion(token, &11, false).unwrap());
        // Deliberately omit finish: endpoint ACK failed after the boundary.
        assert_eq!(ledger.begin_completion(token, &11, false), Err(RetirementError::WrongPhase));
        assert!(matches!(ledger.pending[&OBJECT].phase, Phase::CompletionAttempted));
    }

    #[test]
    fn engine_finish_without_callback_is_rejected() {
        let (mut ledger, token) = pending();
        assert_eq!(ledger.finish(token), Err(RetirementError::WrongPhase));
        ledger.bind_barrier(token, 11).unwrap();
        assert_eq!(ledger.finish(token), Err(RetirementError::WrongPhase));
    }

    #[test]
    fn engine_duplicate_object_cannot_replace_original_nonce() {
        let (mut ledger, token) = pending();
        assert_eq!(ledger.begin(OBJECT, RetirementNonce(10)), Err(RetirementError::AlreadyPending));
        assert_eq!(ledger.pending[&OBJECT].token, token);
    }

    #[test]
    fn engine_replayed_callback_after_finish_has_no_owner() {
        let (mut ledger, token) = pending();
        ledger.bind_barrier(token, 11).unwrap();
        assert!(ledger.begin_completion(token, &11, false).unwrap());
        ledger.finish(token).unwrap();
        assert_eq!(ledger.begin_completion(token, &11, false), Err(RetirementError::StaleOrMissing));
        assert_eq!(ledger.finish(token), Err(RetirementError::StaleOrMissing));
    }

    #[test]
    fn engine_bound_limits_reject_capacity_and_generation_wrap() {
        let mut ledger = EngineRetirements::<u64>::new();
        ledger.connect().unwrap();
        for n in 1..=u64::from(MAX_TASK_OBJECTS) {
            ledger.begin(TaskObjectId(n), RetirementNonce(n)).unwrap();
        }
        assert_eq!(ledger.begin(TaskObjectId(u64::from(MAX_TASK_OBJECTS) + 1), RetirementNonce(99)),
            Err(RetirementError::Capacity));
        ledger.disconnect();
        ledger.generation = u64::MAX;
        assert_eq!(ledger.connect(), Err(RetirementError::GenerationExhausted));
        assert!(!ledger.connected);
    }

    #[test]
    fn engine_invalid_identity_and_disconnected_requests_do_not_allocate() {
        let mut ledger = EngineRetirements::<u64>::new();
        assert_eq!(ledger.begin(OBJECT, NONCE), Err(RetirementError::Disconnected));
        ledger.connect().unwrap();
        assert_eq!(ledger.begin(TaskObjectId(0), NONCE), Err(RetirementError::InvalidIdentity));
        assert_eq!(ledger.begin(OBJECT, RetirementNonce(0)), Err(RetirementError::InvalidIdentity));
        assert!(ledger.pending.is_empty());
    }
}
