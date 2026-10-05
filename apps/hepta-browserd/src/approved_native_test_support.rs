//! Default-off, one-Create qualification diagnostics. This is not a product
//! API, authority check, logger, or claim about which endpoint closed first.
//!
//! The native fixture enrolls its existing actor worker and arms only after
//! complete Health. No reset exists. The failure assertion freezes a fixed
//! label before its existing pipe sample; empty means only no capture at that
//! sample. Earlier gates, a panic, or the post-service owner check may bypass
//! capture. Success closes the slot before the next admission.
//!
//! Feature-off builds omit this module and both service hooks. Feature-enabled
//! but unenrolled consumers still pay bounded atomic checks and a stack guard;
//! enrolled unarmed entries also track TLS nesting, without classifying errors.
//! Cargo feature union (including all-features) is not a security boundary.

use hepta_agent_port::AgentPortError;
use hepta_agent_transport::TransportError;
use std::cell::Cell;
use std::marker::PhantomData;
use std::rc::Rc;
use std::sync::atomic::{AtomicU8, Ordering};

const UNARMED: u8 = 0;
const ARMED_EMPTY: u8 = 1;
const CLASS_FIRST: u8 = 2;
const CLASS_LAST: u8 = 37;
const CLOSED: u8 = 38;
const INVALID: u8 = 39;
const FROZEN: u8 = 128;
const UNCLAIMED: u8 = 0;
const ENROLLED: u8 = 1;
const ENROLLMENT_REFUSED: u8 = 2;

#[derive(Clone, Copy)]
#[repr(u8)]
enum ServiceErrorClass {
    Codec = CLASS_FIRST,
    AgentDeadlineExceeded,
    ClockBeforeUnixEpoch,
    InvalidHandlerResult,
    Handler,
    AgentSelfCheckThreadPanicked,
    AgentSelfCheckInvariant,
    TransportUnsupportedPlatform,
    TransportInvalidPeerCredentials,
    TransportUnauthorizedPeer,
    TransportInvalidMagic,
    TransportUnsupportedVersion,
    TransportUnknownFrameKind,
    TransportReservedFlags,
    TransportInvalidSessionNonce,
    TransportFrameTooLarge,
    TransportPayloadDigestMismatch,
    TransportDeadlineOrTimeout,
    TransportUnexpectedEof,
    TransportInvalidChallenge,
    TransportUnexpectedFrameKind,
    TransportSessionNonceMismatch,
    TransportSequenceMismatch,
    TransportSequenceExhausted,
    TransportSelfCheckThreadPanicked,
    TransportIoConnectionReset,
    TransportIoConnectionAborted,
    TransportIoBrokenPipe,
    TransportIoNotConnected,
    TransportIoUnexpectedEof,
    TransportIoTimedOut,
    TransportIoWouldBlock,
    TransportIoInterrupted,
    TransportIoInvalidInput,
    TransportIoPermissionDenied,
    TransportIoOther,
}

// Seven non-Transport AgentPort variants and the same closed 29 Transport/Io
// categories as the existing approved native Agent receive classifier.
const CLASS_LABELS: [&str; 36] = [
    "codec",
    "agent-deadline-exceeded",
    "clock-before-unix-epoch",
    "invalid-handler-result",
    "handler",
    "agent-self-check-thread-panicked",
    "agent-self-check-invariant",
    "transport-unsupported-platform",
    "transport-invalid-peer-credentials",
    "transport-unauthorized-peer",
    "transport-invalid-magic",
    "transport-unsupported-version",
    "transport-unknown-frame-kind",
    "transport-reserved-flags",
    "transport-invalid-session-nonce",
    "transport-frame-too-large",
    "transport-payload-digest-mismatch",
    "transport-deadline-or-timeout",
    "transport-unexpected-eof",
    "transport-invalid-challenge",
    "transport-unexpected-frame-kind",
    "transport-session-nonce-mismatch",
    "transport-sequence-mismatch",
    "transport-sequence-exhausted",
    "transport-self-check-thread-panicked",
    "transport-io-connection-reset",
    "transport-io-connection-aborted",
    "transport-io-broken-pipe",
    "transport-io-not-connected",
    "transport-io-unexpected-eof",
    "transport-io-timed-out",
    "transport-io-would-block",
    "transport-io-interrupted",
    "transport-io-invalid-input",
    "transport-io-permission-denied",
    "transport-io-other",
];

fn classify(error: &AgentPortError) -> ServiceErrorClass {
    match error {
        AgentPortError::Codec(_) => ServiceErrorClass::Codec,
        AgentPortError::DeadlineExceeded => ServiceErrorClass::AgentDeadlineExceeded,
        AgentPortError::ClockBeforeUnixEpoch => ServiceErrorClass::ClockBeforeUnixEpoch,
        AgentPortError::InvalidHandlerResult(_) => ServiceErrorClass::InvalidHandlerResult,
        AgentPortError::Handler(_) => ServiceErrorClass::Handler,
        AgentPortError::SelfCheckThreadPanicked => ServiceErrorClass::AgentSelfCheckThreadPanicked,
        AgentPortError::SelfCheckInvariant(_) => ServiceErrorClass::AgentSelfCheckInvariant,
        AgentPortError::Transport(error) => match error {
            TransportError::UnsupportedPlatform => ServiceErrorClass::TransportUnsupportedPlatform,
            TransportError::InvalidPeerCredentials => {
                ServiceErrorClass::TransportInvalidPeerCredentials
            }
            TransportError::UnauthorizedPeer => ServiceErrorClass::TransportUnauthorizedPeer,
            TransportError::InvalidMagic => ServiceErrorClass::TransportInvalidMagic,
            TransportError::UnsupportedVersion(_) => ServiceErrorClass::TransportUnsupportedVersion,
            TransportError::UnknownFrameKind(_) => ServiceErrorClass::TransportUnknownFrameKind,
            TransportError::ReservedFlags(_) => ServiceErrorClass::TransportReservedFlags,
            TransportError::InvalidSessionNonce => ServiceErrorClass::TransportInvalidSessionNonce,
            TransportError::FrameTooLarge { .. } => ServiceErrorClass::TransportFrameTooLarge,
            TransportError::PayloadDigestMismatch => {
                ServiceErrorClass::TransportPayloadDigestMismatch
            }
            TransportError::DeadlineExceeded => ServiceErrorClass::TransportDeadlineOrTimeout,
            TransportError::UnexpectedEof => ServiceErrorClass::TransportUnexpectedEof,
            TransportError::InvalidChallenge => ServiceErrorClass::TransportInvalidChallenge,
            TransportError::UnexpectedFrameKind => ServiceErrorClass::TransportUnexpectedFrameKind,
            TransportError::SessionNonceMismatch => {
                ServiceErrorClass::TransportSessionNonceMismatch
            }
            TransportError::SequenceMismatch { .. } => ServiceErrorClass::TransportSequenceMismatch,
            TransportError::SequenceExhausted => ServiceErrorClass::TransportSequenceExhausted,
            TransportError::SelfCheckThreadPanicked => {
                ServiceErrorClass::TransportSelfCheckThreadPanicked
            }
            TransportError::Io(error) => match error.kind() {
                std::io::ErrorKind::ConnectionReset => {
                    ServiceErrorClass::TransportIoConnectionReset
                }
                std::io::ErrorKind::ConnectionAborted => {
                    ServiceErrorClass::TransportIoConnectionAborted
                }
                std::io::ErrorKind::BrokenPipe => ServiceErrorClass::TransportIoBrokenPipe,
                std::io::ErrorKind::NotConnected => ServiceErrorClass::TransportIoNotConnected,
                std::io::ErrorKind::UnexpectedEof => ServiceErrorClass::TransportIoUnexpectedEof,
                std::io::ErrorKind::TimedOut => ServiceErrorClass::TransportIoTimedOut,
                std::io::ErrorKind::WouldBlock => ServiceErrorClass::TransportIoWouldBlock,
                std::io::ErrorKind::Interrupted => ServiceErrorClass::TransportIoInterrupted,
                std::io::ErrorKind::InvalidInput => ServiceErrorClass::TransportIoInvalidInput,
                std::io::ErrorKind::PermissionDenied => {
                    ServiceErrorClass::TransportIoPermissionDenied
                }
                _ => ServiceErrorClass::TransportIoOther,
            },
        },
    }
}

fn label(state: u8) -> &'static str {
    match state & !FROZEN {
        UNARMED => "diagnostic-unarmed",
        ARMED_EMPTY => "no-capture-at-sample",
        CLASS_FIRST..=CLASS_LAST => CLASS_LABELS
            .get(usize::from((state & !FROZEN) - CLASS_FIRST))
            .copied()
            .unwrap_or("diagnostic-invalid-scope"),
        CLOSED => "create-already-finished",
        _ => "diagnostic-invalid-scope",
    }
}

struct Recorder {
    slot: AtomicU8,
    enrollment: AtomicU8,
}

impl Recorder {
    const fn new() -> Self {
        Self {
            slot: AtomicU8::new(UNARMED),
            enrollment: AtomicU8::new(UNCLAIMED),
        }
    }

    fn arm(&self) -> bool {
        self.slot
            .compare_exchange(UNARMED, ARMED_EMPTY, Ordering::AcqRel, Ordering::Acquire)
            .is_ok()
    }

    // Only monotone open transitions exist: unarmed -> armed -> class ->
    // invalid -> closed. Frozen and closed states never change. A failed CAS
    // must have observed progress along that finite chain; four explicit
    // attempts suffice, with no retry loop or wait. Capture itself uses one CAS.
    fn transition_once(&self, state: u8, target: u8) -> Option<u8> {
        if state & FROZEN != 0 || state == CLOSED || state == target {
            return None;
        }
        self.slot
            .compare_exchange(state, target, Ordering::AcqRel, Ordering::Acquire)
            .err()
    }

    fn transition_open(&self, target: u8) {
        let state = self.slot.load(Ordering::Acquire);
        if let Some(state) = self.transition_once(state, target)
            && let Some(state) = self.transition_once(state, target)
            && let Some(state) = self.transition_once(state, target)
        {
            let _ = self.transition_once(state, target);
        }
    }

    fn enroll(&self, thread: &ThreadState) -> bool {
        if self
            .enrollment
            .compare_exchange(UNCLAIMED, ENROLLED, Ordering::AcqRel, Ordering::Acquire)
            .is_err()
        {
            self.enrollment.store(ENROLLMENT_REFUSED, Ordering::Release);
            self.transition_open(INVALID);
            return false;
        }
        thread.enrolled.set(true);
        true
    }

    fn enter(&self, thread: &ThreadState, state_at_entry: u8) -> Entry {
        if !thread.enrolled.get() {
            return Entry::inert();
        }
        if thread.in_service.replace(true) {
            thread.invalid.set(true);
            self.transition_open(INVALID);
            return Entry::inert();
        }
        Entry {
            owns_scope: true,
            eligible: state_at_entry == ARMED_EMPTY
                && !thread.invalid.get()
                && self.enrollment.load(Ordering::Acquire) == ENROLLED,
        }
    }

    fn capture(&self, thread: &ThreadState, entry: &mut Entry, error: &AgentPortError) {
        let eligible = std::mem::replace(&mut entry.eligible, false);
        if !eligible
            || !entry.owns_scope
            || !thread.enrolled.get()
            || !thread.in_service.get()
            || thread.invalid.get()
            || self.enrollment.load(Ordering::Acquire) != ENROLLED
            || self.slot.load(Ordering::Acquire) != ARMED_EMPTY
        {
            return;
        }
        // Borrow ends in the caller before its original Result/map_err/drop.
        // No original error, payload, binding, string, or resource is retained.
        let class = classify(error) as u8;
        let _ = self
            .slot
            .compare_exchange(ARMED_EMPTY, class, Ordering::AcqRel, Ordering::Acquire);
    }

    fn freeze(&self) -> &'static str {
        // Linearizes against capture/close/invalidate. Low bits cannot change
        // once frozen, including when cleanup or another freeze runs later.
        label(self.slot.fetch_or(FROZEN, Ordering::AcqRel))
    }

    fn unenroll(&self, thread: &ThreadState) {
        thread.enrolled.set(false);
        if thread.in_service.get() {
            thread.invalid.set(true);
            self.transition_open(INVALID);
        }
        // The process-wide claim is intentionally never released.
    }
}

struct ThreadState {
    enrolled: Cell<bool>,
    in_service: Cell<bool>,
    invalid: Cell<bool>,
}

impl ThreadState {
    const fn new() -> Self {
        Self {
            enrolled: Cell::new(false),
            in_service: Cell::new(false),
            invalid: Cell::new(false),
        }
    }
}

struct Entry {
    owns_scope: bool,
    eligible: bool,
}

impl Entry {
    const fn inert() -> Self {
        Self {
            owns_scope: false,
            eligible: false,
        }
    }

    fn leave(&mut self, thread: &ThreadState) {
        self.eligible = false;
        if std::mem::replace(&mut self.owns_scope, false) {
            thread.in_service.set(false);
        }
    }
}

static RECORDER: Recorder = Recorder::new();
thread_local! {
    static ACTOR_SCOPE: ThreadState = const { ThreadState::new() };
}

/// A scope on the explicitly enrolled existing actor worker. This cannot be
/// transferred/shared across threads and contains no product/error resource.
#[must_use]
pub struct ActorThreadEnrollment {
    owns_scope: bool,
    not_send_or_sync: PhantomData<Rc<()>>,
}

/// Enroll one existing worker once. A second enrollment is inert and invalidates
/// an unfrozen diagnostic. This never grants or changes product authority.
pub fn enroll_actor_thread() -> ActorThreadEnrollment {
    let owns_scope = ACTOR_SCOPE
        .try_with(|thread| RECORDER.enroll(thread))
        .unwrap_or(false);
    ActorThreadEnrollment {
        owns_scope,
        not_send_or_sync: PhantomData,
    }
}

impl Drop for ActorThreadEnrollment {
    fn drop(&mut self) {
        if self.owns_scope {
            let _ = ACTOR_SCOPE.try_with(|thread| RECORDER.unenroll(thread));
        }
    }
}

/// Arm only after complete Health, before the fixture's sole Create admission.
/// False means the one irreversible arm has already been consumed or closed.
pub fn arm_create() -> bool {
    RECORDER.arm()
}

/// Freeze the existing failure assertion's fixed snapshot without any I/O.
/// `no-capture-at-sample` is not evidence that service has not returned.
pub fn freeze_create_failure() -> &'static str {
    RECORDER.freeze()
}

/// Close immediately after successful Create, before another admission.
pub fn close_after_success() {
    RECORDER.transition_open(CLOSED);
}

pub(crate) struct ServiceEntryGuard {
    entry: Entry,
    not_send_or_sync: PhantomData<Rc<()>>,
}

pub(crate) fn service_entry() -> ServiceEntryGuard {
    let state = RECORDER.slot.load(Ordering::Acquire);
    let entry = if state & FROZEN != 0
        || state == CLOSED
        || RECORDER.enrollment.load(Ordering::Acquire) != ENROLLED
    {
        Entry::inert()
    } else {
        ACTOR_SCOPE
            .try_with(|thread| RECORDER.enter(thread, state))
            .unwrap_or(Entry::inert())
    };
    ServiceEntryGuard {
        entry,
        not_send_or_sync: PhantomData,
    }
}

impl ServiceEntryGuard {
    pub(crate) fn capture(&mut self, error: &AgentPortError) {
        if self.entry.eligible {
            let _ = ACTOR_SCOPE.try_with(|thread| RECORDER.capture(thread, &mut self.entry, error));
        }
    }
}

impl Drop for ServiceEntryGuard {
    fn drop(&mut self) {
        if self.entry.owns_scope {
            let _ = ACTOR_SCOPE.try_with(|thread| self.entry.leave(thread));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ProductDispatchError;
    use hepta_browser_codec::CodecError;
    use std::io::ErrorKind;
    use std::sync::Arc;
    use std::sync::atomic::AtomicUsize;

    // Every recorder control owns private state. None arms, resets, or enrolls
    // the native global slot shared with the real coordinator control.
    fn enrolled() -> (Recorder, ThreadState) {
        let recorder = Recorder::new();
        let thread = ThreadState::new();
        assert!(recorder.enroll(&thread));
        (recorder, thread)
    }

    fn enter(recorder: &Recorder, thread: &ThreadState) -> Entry {
        recorder.enter(thread, recorder.slot.load(Ordering::Acquire))
    }

    fn codec() -> AgentPortError {
        AgentPortError::Codec(CodecError::NonCanonicalEncoding)
    }

    #[test]
    fn unarmed_and_wrong_worker_do_not_capture() {
        let (unarmed, worker) = enrolled();
        let mut entry = enter(&unarmed, &worker);
        unarmed.capture(&worker, &mut entry, &codec());
        entry.leave(&worker);
        assert_eq!(unarmed.freeze(), "diagnostic-unarmed");

        let (recorder, _worker) = enrolled();
        assert!(recorder.arm());
        let wrong_worker = ThreadState::new();
        let mut entry = enter(&recorder, &wrong_worker);
        recorder.capture(&wrong_worker, &mut entry, &codec());
        entry.leave(&wrong_worker);
        assert_eq!(recorder.freeze(), "no-capture-at-sample");
    }

    #[test]
    fn pre_arm_entry_cannot_become_eligible_when_it_returns() {
        let (recorder, worker) = enrolled();
        let mut entry = enter(&recorder, &worker);
        assert!(recorder.arm());
        recorder.capture(&worker, &mut entry, &codec());
        entry.leave(&worker);
        assert_eq!(recorder.freeze(), "no-capture-at-sample");
    }

    #[test]
    fn nested_entry_invalidates_without_clearing_outer_scope() {
        for arm_before_outer in [false, true] {
            let (recorder, worker) = enrolled();
            if arm_before_outer {
                assert!(recorder.arm());
            }
            let mut outer = enter(&recorder, &worker);
            if !arm_before_outer {
                assert!(recorder.arm());
            }
            let mut inner = enter(&recorder, &worker);
            recorder.capture(&worker, &mut inner, &codec());
            inner.leave(&worker);
            assert!(worker.in_service.get());
            recorder.capture(&worker, &mut outer, &codec());
            outer.leave(&worker);
            assert!(!worker.in_service.get());
            assert_eq!(recorder.freeze(), "diagnostic-invalid-scope");
        }
    }

    #[test]
    fn stale_scope_and_repeated_capture_cannot_replace_first_error() {
        let (recorder, worker) = enrolled();
        assert!(recorder.arm());
        let mut stale = enter(&recorder, &worker);
        stale.leave(&worker);
        let mut current = enter(&recorder, &worker);
        recorder.capture(&worker, &mut stale, &codec());
        assert_eq!(recorder.slot.load(Ordering::Acquire), ARMED_EMPTY);
        recorder.capture(&worker, &mut current, &AgentPortError::DeadlineExceeded);
        recorder.capture(&worker, &mut current, &codec());
        current.leave(&worker);
        let mut next = enter(&recorder, &worker);
        recorder.capture(&worker, &mut next, &codec());
        next.leave(&worker);
        assert_eq!(recorder.freeze(), "agent-deadline-exceeded");
    }

    #[test]
    fn freeze_capture_interleavings_and_late_cleanup_preserve_snapshot() {
        // Deterministically cover both linearized race orders without sleeps,
        // additional workers, or a global reset.
        for capture_before_freeze in [false, true] {
            let (recorder, worker) = enrolled();
            assert!(recorder.arm());
            let mut entry = enter(&recorder, &worker);
            if capture_before_freeze {
                recorder.capture(&worker, &mut entry, &codec());
            }
            let expected = if capture_before_freeze {
                "codec"
            } else {
                "no-capture-at-sample"
            };
            assert_eq!(recorder.freeze(), expected);
            let frozen = recorder.slot.load(Ordering::Acquire);
            recorder.capture(&worker, &mut entry, &AgentPortError::DeadlineExceeded);
            recorder.transition_open(CLOSED);
            assert!(!recorder.enroll(&ThreadState::new()));
            recorder.unenroll(&worker);
            entry.leave(&worker);
            assert!(!recorder.arm());
            assert_eq!(recorder.freeze(), expected);
            assert_eq!(recorder.slot.load(Ordering::Acquire), frozen);
        }
    }

    #[test]
    fn duplicate_enrollment_is_inert_and_never_releases_the_claim() {
        let (recorder, worker) = enrolled();
        assert!(recorder.arm());
        assert!(!recorder.enroll(&worker));
        assert!(worker.enrolled.get());
        let mut entry = enter(&recorder, &worker);
        recorder.capture(&worker, &mut entry, &codec());
        entry.leave(&worker);
        recorder.unenroll(&worker);
        let other_worker = ThreadState::new();
        assert!(!recorder.enroll(&other_worker));
        assert!(!other_worker.enrolled.get());
        assert_eq!(recorder.freeze(), "diagnostic-invalid-scope");
    }

    #[test]
    fn rearm_refused_and_success_closes_before_any_later_capture() {
        let (recorder, worker) = enrolled();
        assert!(recorder.arm());
        assert!(!recorder.arm());
        let mut entry = enter(&recorder, &worker);
        recorder.transition_open(CLOSED);
        recorder.capture(&worker, &mut entry, &codec());
        entry.leave(&worker);
        assert!(!recorder.arm());
        assert_eq!(recorder.freeze(), "create-already-finished");

        let never_armed = Recorder::new();
        assert_eq!(never_armed.freeze(), "diagnostic-unarmed");
        assert!(!never_armed.arm());
    }

    #[test]
    fn classifier_has_exactly_36_fixed_classes_and_ignores_private_fields() {
        let agent_errors = [
            AgentPortError::Codec(CodecError::UnknownOperation("private operation".into())),
            AgentPortError::DeadlineExceeded,
            AgentPortError::ClockBeforeUnixEpoch,
            AgentPortError::InvalidHandlerResult("private result"),
            AgentPortError::Handler("private handler".into()),
            AgentPortError::SelfCheckThreadPanicked,
            AgentPortError::SelfCheckInvariant("private invariant"),
        ];
        let transport_errors = [
            TransportError::UnsupportedPlatform,
            TransportError::InvalidPeerCredentials,
            TransportError::UnauthorizedPeer,
            TransportError::InvalidMagic,
            TransportError::UnsupportedVersion(u16::MAX),
            TransportError::UnknownFrameKind(u8::MAX),
            TransportError::ReservedFlags(u8::MAX),
            TransportError::InvalidSessionNonce,
            TransportError::FrameTooLarge {
                length: usize::MAX,
                maximum: 1,
            },
            TransportError::PayloadDigestMismatch,
            TransportError::DeadlineExceeded,
            TransportError::UnexpectedEof,
            TransportError::InvalidChallenge,
            TransportError::UnexpectedFrameKind,
            TransportError::SessionNonceMismatch,
            TransportError::SequenceMismatch {
                expected: u64::MAX,
                actual: 0,
            },
            TransportError::SequenceExhausted,
            TransportError::SelfCheckThreadPanicked,
        ];
        let io_kinds = [
            ErrorKind::ConnectionReset,
            ErrorKind::ConnectionAborted,
            ErrorKind::BrokenPipe,
            ErrorKind::NotConnected,
            ErrorKind::UnexpectedEof,
            ErrorKind::TimedOut,
            ErrorKind::WouldBlock,
            ErrorKind::Interrupted,
            ErrorKind::InvalidInput,
            ErrorKind::PermissionDenied,
            ErrorKind::Other,
        ];
        // Independent expected vector protects the enum-to-label order too.
        let expected = [
            "codec",
            "agent-deadline-exceeded",
            "clock-before-unix-epoch",
            "invalid-handler-result",
            "handler",
            "agent-self-check-thread-panicked",
            "agent-self-check-invariant",
            "transport-unsupported-platform",
            "transport-invalid-peer-credentials",
            "transport-unauthorized-peer",
            "transport-invalid-magic",
            "transport-unsupported-version",
            "transport-unknown-frame-kind",
            "transport-reserved-flags",
            "transport-invalid-session-nonce",
            "transport-frame-too-large",
            "transport-payload-digest-mismatch",
            "transport-deadline-or-timeout",
            "transport-unexpected-eof",
            "transport-invalid-challenge",
            "transport-unexpected-frame-kind",
            "transport-session-nonce-mismatch",
            "transport-sequence-mismatch",
            "transport-sequence-exhausted",
            "transport-self-check-thread-panicked",
            "transport-io-connection-reset",
            "transport-io-connection-aborted",
            "transport-io-broken-pipe",
            "transport-io-not-connected",
            "transport-io-unexpected-eof",
            "transport-io-timed-out",
            "transport-io-would-block",
            "transport-io-interrupted",
            "transport-io-invalid-input",
            "transport-io-permission-denied",
            "transport-io-other",
        ];
        let mut seen = std::collections::BTreeSet::new();
        let errors = agent_errors
            .into_iter()
            .chain(transport_errors.into_iter().map(AgentPortError::Transport))
            .chain(io_kinds.into_iter().map(|kind| {
                AgentPortError::Transport(TransportError::Io(std::io::Error::new(
                    kind,
                    "private IO",
                )))
            }));
        for (index, error) in errors.enumerate() {
            let class = classify(&error) as u8;
            assert_eq!(usize::from(class - CLASS_FIRST), index);
            let fixed = label(class);
            assert_eq!(fixed, expected[index]);
            assert!(!fixed.contains("private"));
            assert!(seen.insert(fixed));
        }
        assert_eq!(seen.len(), 36);
        assert_eq!(seen, CLASS_LABELS.into_iter().collect());
        assert_eq!(
            classify(&AgentPortError::Transport(TransportError::Io(
                std::io::Error::from(ErrorKind::NotFound),
            ))) as u8,
            CLASS_LAST
        );
        assert_eq!(
            classify(&AgentPortError::Codec(CodecError::NonCanonicalEncoding)) as u8,
            CLASS_FIRST
        );
    }

    struct PrivatePayload(Arc<AtomicUsize>);
    impl std::fmt::Debug for PrivatePayload {
        fn fmt(&self, _output: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            panic!("diagnostic must not format an error");
        }
    }
    impl std::fmt::Display for PrivatePayload {
        fn fmt(&self, _output: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            panic!("diagnostic must not format an error");
        }
    }
    impl std::error::Error for PrivatePayload {}
    impl Drop for PrivatePayload {
        fn drop(&mut self) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }

    #[test]
    fn capture_borrows_without_formatting_retaining_or_changing_error_drop() {
        let (recorder, worker) = enrolled();
        assert!(recorder.arm());
        let mut entry = enter(&recorder, &worker);
        let drops = Arc::new(AtomicUsize::new(0));
        let result: Result<(), AgentPortError> = Err(AgentPortError::Transport(TransportError::Io(
            std::io::Error::other(PrivatePayload(Arc::clone(&drops))),
        )));
        if let Err(error) = &result {
            recorder.capture(&worker, &mut entry, error);
        }
        assert_eq!(drops.load(Ordering::SeqCst), 0);
        let outward = result.map_err(|_| ProductDispatchError::DispatchFailed);
        assert_eq!(outward, Err(ProductDispatchError::DispatchFailed));
        assert_eq!(drops.load(Ordering::SeqCst), 1);
        entry.leave(&worker);
        assert_eq!(recorder.freeze(), "transport-io-other");
        assert_eq!(drops.load(Ordering::SeqCst), 1);
    }
}
