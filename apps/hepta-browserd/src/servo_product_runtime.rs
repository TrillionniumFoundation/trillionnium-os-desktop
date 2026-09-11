//! Product-facing supervision for the exact-pin Servo BrowserActor runtime.
//!
//! The trusted browser service survives a content-runtime crash, invalidates all
//! generation-bound semantic references, requires explicit reconstruction, and
//! never replays a possibly dispatched operation automatically.

use hepta_browser_actor::ServoBrowserActor;
use std::fmt;
use std::num::NonZeroU32;

/// Monotonic identity of one reconstructed content-runtime incarnation.
#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct RuntimeGeneration(u64);

impl RuntimeGeneration {
    /// First generation assigned to a newly started product runtime.
    pub const INITIAL: Self = Self(1);

    /// Integer representation used in evidence and semantic references.
    #[must_use]
    pub const fn get(self) -> u64 {
        self.0
    }

    fn checked_next(self) -> Result<Self, ProductRuntimeError> {
        self.0
            .checked_add(1)
            .map(Self)
            .ok_or(ProductRuntimeError::GenerationExhausted)
    }
}

/// A semantic reference that is valid only in the generation that minted it.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct SemanticReference {
    generation: RuntimeGeneration,
    revision: u64,
}

impl SemanticReference {
    /// Bind an opaque semantic revision to a runtime generation.
    #[must_use]
    pub const fn new(generation: RuntimeGeneration, revision: u64) -> Self {
        Self {
            generation,
            revision,
        }
    }

    /// Generation that minted this reference.
    #[must_use]
    pub const fn generation(self) -> RuntimeGeneration {
        self.generation
    }

    /// Opaque semantic revision within the generation.
    #[must_use]
    pub const fn revision(self) -> u64 {
        self.revision
    }
}

/// Maximum consecutive content-runtime crashes before fail-closed lockout.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RestartPolicy {
    max_consecutive_crashes: NonZeroU32,
}

impl RestartPolicy {
    /// Construct a bounded policy. Zero is rejected rather than reinterpreted.
    pub fn new(max_consecutive_crashes: u32) -> Result<Self, ProductRuntimeError> {
        let max_consecutive_crashes = NonZeroU32::new(max_consecutive_crashes)
            .ok_or(ProductRuntimeError::InvalidRestartPolicy)?;
        Ok(Self {
            max_consecutive_crashes,
        })
    }

    /// Configured crash-loop threshold.
    #[must_use]
    pub const fn max_consecutive_crashes(self) -> u32 {
        self.max_consecutive_crashes.get()
    }
}

/// Observable lifecycle state of the trusted browser service.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RuntimeState {
    /// A concrete BrowserActor is available for a new operation.
    Ready,
    /// Trusted chrome survived, but explicit reconstruction is required.
    NeedsReconstruction,
    /// A prior operation may have reached Servo and needs reconciliation.
    ReplayReconciliationRequired,
    /// The bounded crash threshold opened and blocks reconstruction.
    CrashLoopOpen,
    /// Runtime identity is exhausted; this service lifecycle is permanently retired.
    GenerationExhausted,
}

/// Completion classification returned by exactly one dispatch attempt.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DispatchCompletion<T> {
    /// The operation produced one terminal result.
    Completed(T),
    /// The adapter proved that Servo dispatch never occurred.
    NotDispatched,
    /// Dispatch may have occurred, so automatic replay is forbidden.
    IndeterminateAfterDispatch,
}

/// Generation transition caused by a content-runtime crash.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CrashTransition {
    /// Generation invalidated by the crash.
    pub previous: RuntimeGeneration,
    /// New generation reserved for explicit reconstruction.
    pub current: RuntimeGeneration,
    /// Whether an indeterminate operation continues to forbid replay.
    pub replay_blocked: bool,
    /// Consecutive crashes since the last stable cycle.
    pub consecutive_crashes: u32,
}

/// Redacted, closed failure vocabulary for the product-runtime supervisor.
#[derive(Clone, Copy, Eq, PartialEq)]
pub enum ProductRuntimeError {
    /// Restart threshold was configured as zero.
    InvalidRestartPolicy,
    /// The generation counter cannot advance without wrapping.
    GenerationExhausted,
    /// A semantic revision has not been published.
    InvalidSemanticRevision,
    /// No journal-bound reconciliation authority is implemented in this candidate.
    ReconciliationEvidenceRequired,
    /// The caller supplied a reference from another generation.
    StaleGeneration,
    /// No BrowserActor is available until reconstruction succeeds.
    RuntimeUnavailable,
    /// The bounded crash threshold is open.
    CrashLoopOpen,
    /// A command may have reached Servo and needs reconciliation.
    IndeterminateAfterDispatch,
    /// Factory reconstruction failed; implementation details stay redacted.
    ReconstructionFailed,
}

impl ProductRuntimeError {
    /// Stable redacted code suitable for receipts and logs.
    #[must_use]
    pub const fn code(self) -> &'static str {
        match self {
            Self::InvalidRestartPolicy => "invalid_restart_policy",
            Self::GenerationExhausted => "generation_exhausted",
            Self::InvalidSemanticRevision => "invalid_semantic_revision",
            Self::ReconciliationEvidenceRequired => "reconciliation_evidence_required",
            Self::StaleGeneration => "stale_generation",
            Self::RuntimeUnavailable => "runtime_unavailable",
            Self::CrashLoopOpen => "crash_loop_open",
            Self::IndeterminateAfterDispatch => "indeterminate_after_dispatch",
            Self::ReconstructionFailed => "reconstruction_failed",
        }
    }
}

impl fmt::Debug for ProductRuntimeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl fmt::Display for ProductRuntimeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for ProductRuntimeError {}

/// Trusted product-service supervisor around one concrete BrowserActor incarnation.
///
/// The factory is called once at startup and thereafter only by [`Self::reconstruct`].
/// `dispatch` never retries its closure. An indeterminate completion latches a replay
/// block. This candidate has no journal-bound clearing authority and therefore
/// refuses reconciliation rather than trusting an unbound caller assertion.
pub struct BrowserdRuntimeSupervisor<A, F>
where
    F: FnMut(RuntimeGeneration) -> Result<A, ProductRuntimeError>,
{
    actor: Option<A>,
    factory: F,
    generation: RuntimeGeneration,
    policy: RestartPolicy,
    consecutive_crashes: u32,
    replay_blocked: bool,
    state: RuntimeState,
}

impl<A, F> BrowserdRuntimeSupervisor<A, F>
where
    F: FnMut(RuntimeGeneration) -> Result<A, ProductRuntimeError>,
{
    /// Start the trusted service and construct its first BrowserActor.
    pub fn start(mut factory: F, policy: RestartPolicy) -> Result<Self, ProductRuntimeError> {
        let generation = RuntimeGeneration::INITIAL;
        let actor = factory(generation).map_err(|_| ProductRuntimeError::ReconstructionFailed)?;
        Ok(Self {
            actor: Some(actor),
            factory,
            generation,
            policy,
            consecutive_crashes: 0,
            replay_blocked: false,
            state: RuntimeState::Ready,
        })
    }

    /// Current runtime generation.
    #[must_use]
    pub const fn generation(&self) -> RuntimeGeneration {
        self.generation
    }

    /// Current lifecycle state.
    #[must_use]
    pub const fn state(&self) -> RuntimeState {
        self.state
    }

    /// Whether policy currently forbids replay.
    #[must_use]
    pub const fn replay_blocked(&self) -> bool {
        self.replay_blocked
    }

    /// Mint a semantic reference bound to the current generation.
    #[must_use]
    pub const fn semantic_reference(&self, revision: u64) -> SemanticReference {
        SemanticReference::new(self.generation, revision)
    }

    /// Validate a reference before it reaches BrowserActor.
    pub fn validate_reference(
        &self,
        reference: SemanticReference,
    ) -> Result<(), ProductRuntimeError> {
        self.require_live_lifecycle()?;
        if reference.revision() == 0 {
            return Err(ProductRuntimeError::InvalidSemanticRevision);
        }
        if reference.generation() != self.generation {
            return Err(ProductRuntimeError::StaleGeneration);
        }
        Ok(())
    }

    fn require_live_lifecycle(&self) -> Result<(), ProductRuntimeError> {
        match self.state {
            RuntimeState::GenerationExhausted => Err(ProductRuntimeError::GenerationExhausted),
            RuntimeState::CrashLoopOpen => Err(ProductRuntimeError::CrashLoopOpen),
            _ => Ok(()),
        }
    }

    /// Execute once, with uncertainty latched before control leaves the supervisor.
    /// A panic or unwinding adapter cannot leave the object available for a retry.
    pub fn dispatch<T>(
        &mut self,
        reference: SemanticReference,
        operation: impl FnOnce(&mut A) -> DispatchCompletion<T>,
    ) -> Result<T, ProductRuntimeError> {
        self.validate_reference(reference)?;
        if self.replay_blocked {
            return Err(ProductRuntimeError::IndeterminateAfterDispatch);
        }
        if self.state != RuntimeState::Ready {
            return Err(ProductRuntimeError::RuntimeUnavailable);
        }
        let actor = self
            .actor
            .as_mut()
            .ok_or(ProductRuntimeError::RuntimeUnavailable)?;
        self.replay_blocked = true;
        self.state = RuntimeState::ReplayReconciliationRequired;
        match operation(actor) {
            DispatchCompletion::Completed(value) => {
                self.replay_blocked = false;
                self.state = RuntimeState::Ready;
                Ok(value)
            }
            DispatchCompletion::NotDispatched => {
                self.replay_blocked = false;
                self.state = RuntimeState::Ready;
                Err(ProductRuntimeError::RuntimeUnavailable)
            }
            DispatchCompletion::IndeterminateAfterDispatch => {
                Err(ProductRuntimeError::IndeterminateAfterDispatch)
            }
        }
    }

    /// Retire a crashed actor before any subsequent operation or reconstruction.
    /// Terminal state is committed before dropping a potentially panicking actor.
    pub fn content_process_crashed(&mut self) -> Result<CrashTransition, ProductRuntimeError> {
        self.require_live_lifecycle()?;
        if self.actor.is_none() {
            return Err(ProductRuntimeError::RuntimeUnavailable);
        }
        let previous = self.generation;
        let next = match previous.checked_next() {
            Ok(next) => next,
            Err(error) => {
                self.state = RuntimeState::GenerationExhausted;
                self.replay_blocked = true;
                self.actor = None;
                return Err(error);
            }
        };
        let Some(crashes) = self.consecutive_crashes.checked_add(1) else {
            self.state = RuntimeState::CrashLoopOpen;
            self.replay_blocked = true;
            self.actor = None;
            return Err(ProductRuntimeError::CrashLoopOpen);
        };
        self.generation = next;
        self.consecutive_crashes = crashes;
        self.state = if crashes >= self.policy.max_consecutive_crashes() {
            RuntimeState::CrashLoopOpen
        } else if self.replay_blocked {
            RuntimeState::ReplayReconciliationRequired
        } else {
            RuntimeState::NeedsReconstruction
        };
        self.actor = None;
        Ok(CrashTransition {
            previous,
            current: self.generation,
            replay_blocked: self.replay_blocked,
            consecutive_crashes: crashes,
        })
    }

    /// Explicitly reconstruct once. Factory error or panic retires this lifecycle.
    pub fn reconstruct(&mut self) -> Result<RuntimeGeneration, ProductRuntimeError> {
        self.require_live_lifecycle()?;
        if self.replay_blocked {
            return Err(ProductRuntimeError::IndeterminateAfterDispatch);
        }
        if self.actor.is_some() && self.state == RuntimeState::Ready {
            return Ok(self.generation);
        }
        if self.state != RuntimeState::NeedsReconstruction {
            return Err(ProductRuntimeError::RuntimeUnavailable);
        }
        self.state = RuntimeState::CrashLoopOpen;
        let actor = (self.factory)(self.generation)
            .map_err(|_| ProductRuntimeError::ReconstructionFailed)?;
        self.actor = Some(actor);
        self.state = RuntimeState::Ready;
        Ok(self.generation)
    }

    /// Reset a crash counter only for a currently usable, non-uncertain actor.
    /// This is not an installed boot-health or durable reconciliation receipt.
    pub fn acknowledge_stable_cycle(&mut self) {
        if self.state == RuntimeState::Ready && !self.replay_blocked && self.actor.is_some() {
            self.consecutive_crashes = 0;
        }
    }

    /// Refuse an unbound assertion of durable reconciliation.
    /// A future clearing API must bind the exact pending request and journal fact.
    /// This method changes no state and cannot clear a crash-loop or replay latch.
    pub fn reconcile_indeterminate(&mut self) -> Result<(), ProductRuntimeError> {
        self.require_live_lifecycle()?;
        Err(ProductRuntimeError::ReconciliationEvidenceRequired)
    }

}

/// Product package binding to the concrete exact-pin Servo BrowserActor type.
pub type ProductServoRuntime<F> = BrowserdRuntimeSupervisor<ServoBrowserActor, F>;

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::rc::Rc;

    #[derive(Debug, Eq, PartialEq)]
    struct TestActor {
        generation: RuntimeGeneration,
        calls: u32,
    }

    fn policy(limit: u32) -> RestartPolicy {
        RestartPolicy::new(limit).expect("valid policy")
    }

    #[test]
    fn stale_reference_is_rejected_after_reconstruction() {
        let mut runtime = BrowserdRuntimeSupervisor::start(
            |generation| Ok(TestActor { generation, calls: 0 }),
            policy(3),
        )
        .expect("start");
        let stale = runtime.semantic_reference(7);
        runtime.content_process_crashed().expect("crash");
        runtime.reconstruct().expect("reconstruct");
        assert_eq!(
            runtime.validate_reference(stale),
            Err(ProductRuntimeError::StaleGeneration)
        );
        let current = runtime.semantic_reference(8);
        let result = runtime
            .dispatch(current, |actor| {
                actor.calls += 1;
                DispatchCompletion::Completed((actor.generation, actor.calls))
            })
            .expect("dispatch");
        assert_eq!(result, (runtime.generation(), 1));
    }

    #[test]
    fn crash_never_reconstructs_or_replays_implicitly() {
        let calls = Rc::new(Cell::new(0_u32));
        let observed = Rc::clone(&calls);
        let mut runtime = BrowserdRuntimeSupervisor::start(
            move |generation| {
                observed.set(observed.get() + 1);
                Ok(TestActor { generation, calls: 0 })
            },
            policy(4),
        )
        .expect("start");
        assert_eq!(calls.get(), 1);
        runtime.content_process_crashed().expect("crash");
        assert_eq!(calls.get(), 1);
        runtime.reconstruct().expect("explicit reconstruction");
        assert_eq!(calls.get(), 2);
    }

    #[test]
    fn indeterminate_dispatch_refuses_unbound_reconciliation() {
        let mut runtime = BrowserdRuntimeSupervisor::start(
            |generation| Ok(TestActor { generation, calls: 0 }),
            policy(3),
        )
        .expect("start");
        let reference = runtime.semantic_reference(1);
        assert_eq!(
            runtime.dispatch(reference, |_| {
                DispatchCompletion::<()>::IndeterminateAfterDispatch
            }),
            Err(ProductRuntimeError::IndeterminateAfterDispatch)
        );
        assert_eq!(
            runtime.dispatch(reference, |_| DispatchCompletion::Completed(())),
            Err(ProductRuntimeError::IndeterminateAfterDispatch)
        );
        assert_eq!(
            runtime.reconcile_indeterminate(),
            Err(ProductRuntimeError::ReconciliationEvidenceRequired)
        );
        assert!(runtime.replay_blocked());
        assert_eq!(
            runtime.dispatch(reference, |_| DispatchCompletion::Completed(9_u8)),
            Err(ProductRuntimeError::IndeterminateAfterDispatch)
        );
    }

    #[test]
    fn crash_loop_opens_at_configured_bound() {
        let mut runtime = BrowserdRuntimeSupervisor::start(
            |generation| Ok(TestActor { generation, calls: 0 }),
            policy(2),
        )
        .expect("start");
        runtime.content_process_crashed().expect("first crash");
        runtime.reconstruct().expect("first reconstruction");
        runtime.content_process_crashed().expect("second crash");
        assert_eq!(runtime.state(), RuntimeState::CrashLoopOpen);
        assert_eq!(runtime.reconstruct(), Err(ProductRuntimeError::CrashLoopOpen));
    }

    #[test]
    fn stable_cycle_resets_only_crash_counter() {
        let mut runtime = BrowserdRuntimeSupervisor::start(
            |generation| Ok(TestActor { generation, calls: 0 }),
            policy(2),
        )
        .expect("start");
        runtime.content_process_crashed().expect("first crash");
        runtime.reconstruct().expect("reconstruct");
        runtime.acknowledge_stable_cycle();
        let transition = runtime.content_process_crashed().expect("new-window crash");
        assert_eq!(transition.consecutive_crashes, 1);
        assert_eq!(runtime.state(), RuntimeState::NeedsReconstruction);
    }

    #[test]
    fn errors_are_redacted_and_stable() {
        assert_eq!(
            format!("{:?}", ProductRuntimeError::ReconstructionFailed),
            "reconstruction_failed"
        );
        assert_eq!(
            ProductRuntimeError::IndeterminateAfterDispatch.to_string(),
            "indeterminate_after_dispatch"
        );
    }

    #[test]
    fn generation_exhaustion_retires_actor_and_all_entrypoints() {
        let mut runtime = BrowserdRuntimeSupervisor::start(|_| Ok(()), policy(3)).unwrap();
        runtime.generation = RuntimeGeneration(u64::MAX);
        let reference = runtime.semantic_reference(1);
        assert_eq!(runtime.content_process_crashed(), Err(ProductRuntimeError::GenerationExhausted));
        assert!(runtime.actor.is_none());
        assert_eq!(runtime.state(), RuntimeState::GenerationExhausted);
        assert_eq!(runtime.validate_reference(reference), Err(ProductRuntimeError::GenerationExhausted));
        assert_eq!(runtime.reconstruct(), Err(ProductRuntimeError::GenerationExhausted));
        assert_eq!(runtime.reconcile_indeterminate(), Err(ProductRuntimeError::GenerationExhausted));
        runtime.acknowledge_stable_cycle();
        assert_eq!(runtime.state(), RuntimeState::GenerationExhausted);
    }

    #[test]
    fn panic_after_possible_dispatch_preserves_replay_latch() {
        let mut runtime = BrowserdRuntimeSupervisor::start(|_| Ok(()), policy(3)).unwrap();
        let reference = runtime.semantic_reference(1);
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _ = runtime.dispatch::<()>(reference, |_| panic!("simulated adapter panic"));
        }));
        assert!(result.is_err());
        assert!(runtime.replay_blocked());
        assert_eq!(runtime.state(), RuntimeState::ReplayReconciliationRequired);
        assert_eq!(runtime.reconstruct(), Err(ProductRuntimeError::IndeterminateAfterDispatch));
        assert_eq!(runtime.dispatch(reference, |_| DispatchCompletion::Completed(())), Err(ProductRuntimeError::IndeterminateAfterDispatch));
    }

    #[test]
    fn reconciliation_and_stable_ack_cannot_unlock_crash_loop() {
        let mut runtime = BrowserdRuntimeSupervisor::start(|_| Ok(()), policy(1)).unwrap();
        runtime.content_process_crashed().unwrap();
        runtime.acknowledge_stable_cycle();
        assert_eq!(runtime.reconcile_indeterminate(), Err(ProductRuntimeError::CrashLoopOpen));
        assert_eq!(runtime.reconstruct(), Err(ProductRuntimeError::CrashLoopOpen));
        assert_eq!(runtime.consecutive_crashes, 1);
    }

    #[test]
    fn duplicate_crash_notification_does_not_consume_another_generation() {
        let mut runtime = BrowserdRuntimeSupervisor::start(|_| Ok(()), policy(3)).unwrap();
        runtime.content_process_crashed().unwrap();
        let generation = runtime.generation();
        assert_eq!(runtime.content_process_crashed(), Err(ProductRuntimeError::RuntimeUnavailable));
        assert_eq!(runtime.generation(), generation);
        assert_eq!(runtime.consecutive_crashes, 1);
    }

    #[test]
    fn zero_revision_is_rejected_before_dispatch() {
        let mut runtime = BrowserdRuntimeSupervisor::start(|_| Ok(()), policy(3)).unwrap();
        let reference = runtime.semantic_reference(0);
        assert_eq!(runtime.dispatch(reference, |_| panic!("must not execute")), Err::<(), _>(ProductRuntimeError::InvalidSemanticRevision));
        assert!(!runtime.replay_blocked());
    }

    #[test]
    fn proven_not_dispatched_does_not_latch_uncertainty() {
        let mut runtime = BrowserdRuntimeSupervisor::start(|_| Ok(()), policy(3)).unwrap();
        let reference = runtime.semantic_reference(1);
        assert_eq!(runtime.dispatch(reference, |_| DispatchCompletion::<()>::NotDispatched), Err(ProductRuntimeError::RuntimeUnavailable));
        assert!(!runtime.replay_blocked());
        assert_eq!(runtime.state(), RuntimeState::Ready);
    }

    #[test]
    fn failed_reconstruction_cannot_be_retried_in_same_lifecycle() {
        let mut attempts = 0;
        let mut runtime = BrowserdRuntimeSupervisor::start(|_| {
            attempts += 1;
            if attempts == 1 { Ok(()) } else { Err(ProductRuntimeError::ReconstructionFailed) }
        }, policy(3)).unwrap();
        runtime.content_process_crashed().unwrap();
        assert_eq!(runtime.reconstruct(), Err(ProductRuntimeError::ReconstructionFailed));
        assert_eq!(runtime.reconstruct(), Err(ProductRuntimeError::CrashLoopOpen));
    }

    #[test]
    fn crash_count_exhaustion_retires_actor() {
        let mut runtime = BrowserdRuntimeSupervisor::start(|_| Ok(()), policy(u32::MAX)).unwrap();
        runtime.consecutive_crashes = u32::MAX;
        assert_eq!(runtime.content_process_crashed(), Err(ProductRuntimeError::CrashLoopOpen));
        assert!(runtime.actor.is_none());
        assert_eq!(runtime.state(), RuntimeState::CrashLoopOpen);
    }

}
