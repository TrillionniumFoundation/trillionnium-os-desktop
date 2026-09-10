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
/// block that can be cleared only by an explicit durable-receipt reconciliation.
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
        if reference.generation() != self.generation {
            return Err(ProductRuntimeError::StaleGeneration);
        }
        Ok(())
    }

    /// Execute one operation without implicit retry.
    pub fn dispatch<T>(
        &mut self,
        reference: SemanticReference,
        operation: impl FnOnce(&mut A) -> DispatchCompletion<T>,
    ) -> Result<T, ProductRuntimeError> {
        self.validate_reference(reference)?;
        if self.replay_blocked {
            return Err(ProductRuntimeError::IndeterminateAfterDispatch);
        }
        if self.state == RuntimeState::CrashLoopOpen {
            return Err(ProductRuntimeError::CrashLoopOpen);
        }
        if self.state != RuntimeState::Ready {
            return Err(ProductRuntimeError::RuntimeUnavailable);
        }
        let actor = self
            .actor
            .as_mut()
            .ok_or(ProductRuntimeError::RuntimeUnavailable)?;
        match operation(actor) {
            DispatchCompletion::Completed(value) => Ok(value),
            DispatchCompletion::NotDispatched => Err(ProductRuntimeError::RuntimeUnavailable),
            DispatchCompletion::IndeterminateAfterDispatch => {
                self.replay_blocked = true;
                self.state = RuntimeState::ReplayReconciliationRequired;
                Err(ProductRuntimeError::IndeterminateAfterDispatch)
            }
        }
    }

    /// Invalidate the current generation after a content-runtime crash.
    ///
    /// Trusted service state survives, but the actor is dropped and the factory is
    /// not called. Reconstruction is therefore explicit and independently auditable.
    pub fn content_process_crashed(&mut self) -> Result<CrashTransition, ProductRuntimeError> {
        if self.state == RuntimeState::CrashLoopOpen {
            return Err(ProductRuntimeError::CrashLoopOpen);
        }
        let previous = self.generation;
        self.generation = previous.checked_next()?;
        self.actor = None;
        self.consecutive_crashes = self
            .consecutive_crashes
            .checked_add(1)
            .ok_or(ProductRuntimeError::CrashLoopOpen)?;
        if self.consecutive_crashes >= self.policy.max_consecutive_crashes() {
            self.state = RuntimeState::CrashLoopOpen;
        } else if self.replay_blocked {
            self.state = RuntimeState::ReplayReconciliationRequired;
        } else {
            self.state = RuntimeState::NeedsReconstruction;
        }
        Ok(CrashTransition {
            previous,
            current: self.generation,
            replay_blocked: self.replay_blocked,
            consecutive_crashes: self.consecutive_crashes,
        })
    }

    /// Explicitly construct the actor reserved for the current generation.
    pub fn reconstruct(&mut self) -> Result<RuntimeGeneration, ProductRuntimeError> {
        if self.state == RuntimeState::CrashLoopOpen {
            return Err(ProductRuntimeError::CrashLoopOpen);
        }
        if self.replay_blocked {
            return Err(ProductRuntimeError::IndeterminateAfterDispatch);
        }
        if self.actor.is_some() {
            self.state = RuntimeState::Ready;
            return Ok(self.generation);
        }
        let actor = (self.factory)(self.generation)
            .map_err(|_| ProductRuntimeError::ReconstructionFailed)?;
        self.actor = Some(actor);
        self.state = RuntimeState::Ready;
        Ok(self.generation)
    }

    /// Record a stable service cycle and reset only the crash-loop counter.
    pub fn acknowledge_stable_cycle(&mut self) {
        self.consecutive_crashes = 0;
    }

    /// Clear the replay latch after external durable-receipt reconciliation.
    ///
    /// This method neither reconstructs the actor nor replays a command.
    pub fn reconcile_indeterminate(&mut self) {
        self.replay_blocked = false;
        self.state = if self.actor.is_some() {
            RuntimeState::Ready
        } else {
            RuntimeState::NeedsReconstruction
        };
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
    fn indeterminate_dispatch_latches_until_reconciliation() {
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
        runtime.reconcile_indeterminate();
        assert_eq!(
            runtime.dispatch(reference, |_| DispatchCompletion::Completed(9_u8)),
            Ok(9)
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
}
