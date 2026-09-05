//! Reconstructing an actor must not make an old PageOwner current again.
use super::*;
use std::cell::Cell;

struct CountingRuntime {
    inner: DeterministicLocalRuntime,
    calls: Rc<Cell<usize>>,
}
impl PageRuntime for CountingRuntime {
    fn dispatch(
        &mut self,
        owner: Option<&PageOwnerSnapshot>,
        message: BrowserActorMessage,
        control: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        self.calls.set(self.calls.get() + 1);
        self.inner.dispatch(owner, message, control)
    }
}
fn actor() -> (BrowserActor<CountingRuntime>, Rc<Cell<usize>>) {
    let peer = PeerIdentity {
        pid: Some(std::process::id()),
        uid: 1000,
        gid: 1001,
    };
    let binding = PrincipalBinding::bind(
        TaskFlowPrincipal {
            principal_id: "restart-fixture".into(),
            expected_uid: peer.uid,
            expected_gid: peer.gid,
            expected_systemd_unit: "hepta-agent.service".into(),
            expected_cgroup_v2_path: "/system.slice/hepta-agent.service".into(),
            expected_executable_sha256: "1".repeat(64),
        },
        MechanismIdentity {
            peer,
            systemd_unit: "hepta-agent.service".into(),
            cgroup_v2_path: "/system.slice/hepta-agent.service".into(),
            executable_sha256: "1".repeat(64),
        },
    )
    .unwrap();
    let calls = Rc::new(Cell::new(0));
    (
        BrowserActor::new(
            binding,
            CountingRuntime {
                inner: DeterministicLocalRuntime::default(),
                calls: calls.clone(),
            },
        ),
        calls,
    )
}
fn ctx(actor: &BrowserActor<CountingRuntime>, request: &BrowserRequest) -> DispatchContext {
    let now = Instant::now();
    DispatchContext {
        peer: actor.binding.mechanism.peer,
        transport_sequence: 1,
        canonical_request_sha256: "2".repeat(64),
        effect_class: request.effect_class(),
        accepted_at: now,
        effective_deadline: now + Duration::from_secs(5),
    }
}
fn create(id: &str) -> BrowserRequest {
    BrowserRequest {
        request_id: id.into(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::SessionCreate {
            profile: ProfileSpec {
                profile_id: "ephemeral".into(),
                persistence: ProfilePersistence::Ephemeral,
            },
            ui_mode: "headed".into(),
        },
    }
}
fn create_owner(actor: &mut BrowserActor<CountingRuntime>, id: &str) -> PageOwnerSnapshot {
    let request = create(id);
    assert!(matches!(
        actor.handle(&ctx(actor, &request), &request).unwrap(),
        HandlerOutcome::Success(_)
    ));
    actor.page_owner().unwrap()
}

#[test]
fn reconstructed_actor_does_not_reissue_session_or_webview_identity() {
    let (mut first, _) = actor();
    let old = create_owner(&mut first, "first");
    drop(first);
    let (mut second, _) = actor();
    let new = create_owner(&mut second, "second");
    assert_ne!(
        old.session_id, new.session_id,
        "actor reconstruction reused a PageOwner identity"
    );
    assert_ne!(
        old.webview_token, new.webview_token,
        "actor reconstruction reused a WebView identity"
    );
}

#[test]
fn previous_incarnation_snapshot_is_rejected_before_dispatch() {
    let (mut first, _) = actor();
    let old = create_owner(&mut first, "first");
    drop(first);
    let (mut second, calls) = actor();
    let _new = create_owner(&mut second, "second");
    let request = BrowserRequest {
        request_id: "fresh-request-old-session".into(),
        session_id: Some(old.session_id),
        session_generation: Some(old.session.revisions.session_generation),
        deadline_unix_ms: None,
        operation: BrowserOperation::SessionSnapshot,
    };
    let outcome = second.handle(&ctx(&second, &request), &request).unwrap();
    assert!(
        matches!(
            outcome,
            HandlerOutcome::Failure(BrowserWireError {
                code: BrowserErrorCode::StaleSession,
                ..
            })
        ),
        "stale actor incarnation was admitted: {outcome:?}"
    );
    assert_eq!(calls.get(), 1, "stale session reached the runtime");
}

use hepta_agent_transport::{FixedNonceSource, NONCE_BYTES, NonceSource, TransportError};
struct CountedEntropy {
    calls: Rc<Cell<usize>>,
    mode: u8,
}
impl NonceSource for CountedEntropy {
    fn next_nonce(&mut self) -> Result<[u8; NONCE_BYTES], TransportError> {
        self.calls.set(self.calls.get() + 1);
        match self.mode {
            0 => Err(TransportError::Io(std::io::Error::other(
                "injected entropy failure",
            ))),
            1 => Ok([0; NONCE_BYTES]),
            2 => {
                std::thread::sleep(Duration::from_millis(30));
                Ok([3; NONCE_BYTES])
            }
            _ => Ok([4; NONCE_BYTES]),
        }
    }
}
fn inject(actor: &mut BrowserActor<CountingRuntime>, mode: u8) -> Rc<Cell<usize>> {
    let calls = Rc::new(Cell::new(0));
    actor.incarnation = incarnation::ActorIncarnation::with_source(CountedEntropy {
        calls: calls.clone(),
        mode,
    });
    calls
}

#[test]
fn entropy_failure_is_latched_without_dispatch_counter_change_or_fallback() {
    for mode in [0, 1] {
        let (mut current, backend_calls) = actor();
        let reads = inject(&mut current, mode);
        for id in ["first", "retry"] {
            let request = create(id);
            assert!(current.handle(&ctx(&current, &request), &request).is_err());
            assert!(current.page_owner().is_none());
            assert_eq!(current.session_counter, 0);
            assert_eq!(current.webview_counter, 0);
            assert_eq!(backend_calls.get(), 0);
        }
        assert_eq!(
            reads.get(),
            1,
            "failed entropy cannot recover to a predictable identity"
        );
    }
}

#[test]
fn entropy_is_lazy_and_acquired_only_once_across_close_create_cycles() {
    let (mut current, _) = actor();
    let reads = inject(&mut current, 3);
    assert_eq!(reads.get(), 0);
    let mut bad = create("bad");
    if let BrowserOperation::SessionCreate {
        ref mut ui_mode, ..
    } = bad.operation
    {
        *ui_mode = "headless".into();
    }
    assert!(matches!(
        current.handle(&ctx(&current, &bad), &bad).unwrap(),
        HandlerOutcome::Failure(_)
    ));
    assert_eq!(reads.get(), 0);
    let mut identities = BTreeSet::new();
    let mut views = BTreeSet::new();
    for n in 0..8 {
        let owner = create_owner(&mut current, &format!("create-{n}"));
        assert!(identities.insert(owner.session_id.clone()));
        assert!(views.insert(owner.webview_token.clone()));
        let duplicate = create("duplicate");
        assert!(matches!(
            current
                .handle(&ctx(&current, &duplicate), &duplicate)
                .unwrap(),
            HandlerOutcome::Failure(_)
        ));
        let close = BrowserRequest {
            request_id: format!("close-{n}"),
            session_id: Some(owner.session_id),
            session_generation: Some(owner.session.revisions.session_generation),
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionClose,
        };
        assert!(matches!(
            current.handle(&ctx(&current, &close), &close).unwrap(),
            HandlerOutcome::Success(_)
        ));
    }
    assert_eq!(reads.get(), 1);
    assert_eq!(current.session_counter, 8);
    assert_eq!(current.webview_counter, 8);
}

#[test]
fn entropy_read_does_not_extend_deadline_or_consume_identity_ordinal() {
    let (mut current, calls) = actor();
    let reads = inject(&mut current, 2);
    let request = create("expired-during-entropy");
    let mut context = ctx(&current, &request);
    context.effective_deadline = Instant::now() + Duration::from_millis(5);
    assert!(matches!(
        current.handle(&context, &request),
        Err(AgentPortError::DeadlineExceeded)
    ));
    assert!(current.page_owner().is_none());
    assert_eq!(current.session_counter, 0);
    assert_eq!(current.webview_counter, 0);
    assert_eq!(calls.get(), 0);
    let _ = create_owner(&mut current, "fresh-deadline");
    assert_eq!(
        reads.get(),
        1,
        "a namespace never exposed to a backend need not be re-read"
    );
    assert_eq!(current.session_counter, 1);
}

#[test]
fn counter_exhaustion_is_checked_before_entropy_or_backend_work() {
    for session in [true, false] {
        let (mut current, calls) = actor();
        let reads = inject(&mut current, 3);
        if session {
            current.session_counter = u64::MAX;
        } else {
            current.webview_counter = u64::MAX;
        }
        let request = create("exhausted");
        assert!(matches!(
            current.handle(&ctx(&current, &request), &request).unwrap(),
            HandlerOutcome::Failure(_)
        ));
        assert_eq!(reads.get(), 0);
        assert_eq!(calls.get(), 0);
    }
}

#[test]
fn namespaced_maximum_ordinal_remains_a_valid_opaque_v1_token() {
    let (mut current, _) = actor();
    current.incarnation =
        incarnation::ActorIncarnation::with_source(FixedNonceSource([0x55; NONCE_BYTES]));
    current.session_counter = u64::MAX - 1;
    current.webview_counter = u64::MAX - 1;
    let owner = create_owner(&mut current, "last-ordinal");
    assert!(owner.session_id.ends_with(&format!("-{}", u64::MAX)));
    assert!(owner.webview_token.ends_with(&format!("-{}", u64::MAX)));
    validate_token("session_id", &owner.session_id, 128).unwrap();
    validate_token(
        "webview_token",
        &owner.webview_token,
        MAX_WEBVIEW_TOKEN_BYTES,
    )
    .unwrap();
    let request = BrowserRequest {
        request_id: "snapshot".into(),
        session_id: Some(owner.session_id),
        session_generation: Some(owner.session.revisions.session_generation),
        deadline_unix_ms: None,
        operation: BrowserOperation::SessionSnapshot,
    };
    let encoded = hepta_browser_codec::encode_request(&request).unwrap();
    assert_eq!(
        hepta_browser_codec::decode_request(&encoded).unwrap().value,
        request
    );
}

#[test]
fn namespace_is_domain_separated_from_raw_entropy() {
    let mut state =
        incarnation::ActorIncarnation::with_source(FixedNonceSource([0x55; NONCE_BYTES]));
    let expected = executable_sha256(
        &[
            b"trillionnium.desktop.actor-incarnation.v1\0".as_slice(),
            &[0x55; NONCE_BYTES],
        ]
        .concat(),
    );
    assert_eq!(state.namespace().unwrap(), expected);
    assert_ne!(expected, "55".repeat(32));
}

#[test]
fn scoped_frame_identity_binds_all_axes_and_is_length_delimited() {
    let base = scoped_frame_id("session", "view", "main").unwrap();
    for tuple in [
        ("other", "view", "main"),
        ("session", "other", "main"),
        ("session", "view", "subframe"),
    ] {
        assert_ne!(base, scoped_frame_id(tuple.0, tuple.1, tuple.2).unwrap());
    }
    assert_ne!(
        scoped_frame_id("a", "b-c", "d").unwrap(),
        scoped_frame_id("a-b", "c", "d").unwrap()
    );
    assert_eq!(base, scoped_frame_id("session", "view", "main").unwrap());
    assert_eq!(base.len(), 64);
}

#[test]
fn scoped_frame_identity_rejects_invalid_inputs_and_bounds_valid_outputs() {
    for invalid in [
        "".to_owned(),
        "x".repeat(129),
        "a\nb".into(),
        "a/b".into(),
        "é".into(),
    ] {
        for axis in 0..3 {
            let mut values = ["session", "view", "main"];
            values[axis] = &invalid;
            assert!(scoped_frame_id(values[0], values[1], values[2]).is_err());
        }
    }
    let maximum = "x".repeat(128);
    assert_eq!(
        scoped_frame_id(&maximum, &maximum, &maximum).unwrap().len(),
        64
    );
}

#[test]
fn ordinary_runtime_refusal_never_reissues_reserved_session_identity() {
    struct RefusesOnce {
        ids: Rc<RefCell<Vec<String>>>,
        inner: DeterministicLocalRuntime,
    }
    impl PageRuntime for RefusesOnce {
        fn dispatch(
            &mut self,
            owner: Option<&PageOwnerSnapshot>,
            message: BrowserActorMessage,
            control: &RequestControl,
        ) -> Result<RuntimeReply, RuntimeFailure> {
            if let BrowserActorMessage::CreateSession { ref session_id, .. } = message {
                self.ids.borrow_mut().push(session_id.clone());
                if self.ids.borrow().len() == 1 {
                    return Err(RuntimeFailure::Unsupported("fixture refuses first create"));
                }
            }
            self.inner.dispatch(owner, message, control)
        }
    }
    let (seed, _) = actor();
    let ids = Rc::new(RefCell::new(Vec::new()));
    let mut current = BrowserActor::new(
        seed.binding.clone(),
        RefusesOnce {
            ids: ids.clone(),
            inner: DeterministicLocalRuntime::default(),
        },
    );
    let request = create("first");
    let context = ctx(&seed, &request);
    assert!(matches!(
        current.handle(&context, &request).unwrap(),
        HandlerOutcome::Failure(_)
    ));
    let request = create("second");
    assert!(matches!(
        current.handle(&context, &request).unwrap(),
        HandlerOutcome::Success(_)
    ));
    assert_eq!(ids.borrow().len(), 2);
    assert_ne!(ids.borrow()[0], ids.borrow()[1]);
    assert_eq!(current.session_counter, 2);
}
