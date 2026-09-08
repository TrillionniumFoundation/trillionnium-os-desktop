//! Real PageRuntime entrypoint tests; the control token comes from BrowserActor.
use super::*;
use hepta_agent_port::{BrowserRequestHandler, DispatchContext, HandlerOutcome};
use hepta_agent_transport::PeerIdentity;
use hepta_browser_actor::{BrowserActor, MechanismIdentity, PrincipalBinding, TaskFlowPrincipal};
use hepta_browser_codec::{BrowserOperation, BrowserRequest, EffectClass};
use hepta_session_core::SessionMachine;
use std::cell::RefCell;
use std::rc::Rc;
use std::time::{Duration, Instant};

struct Capture(Rc<RefCell<Option<RequestControl>>>);
impl PageRuntime for Capture {
    fn dispatch(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        c: &RequestControl,
    ) -> Result<RuntimeReply, RuntimeFailure> {
        *self.0.borrow_mut() = Some(c.clone());
        Ok(RuntimeReply {
            result: JsonObject::new(),
            current_url: None,
        })
    }
}
fn control() -> RequestControl {
    let slot = Rc::new(RefCell::new(None));
    let peer = PeerIdentity {
        pid: Some(82),
        uid: 1000,
        gid: 1001,
    };
    let binding = PrincipalBinding::bind(
        TaskFlowPrincipal {
            principal_id: "atomic-fixture-tests".into(),
            expected_uid: 1000,
            expected_gid: 1001,
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
    let mut actor = BrowserActor::new(binding, Capture(slot.clone()));
    let now = Instant::now();
    let ctx = DispatchContext {
        peer,
        transport_sequence: 1,
        canonical_request_sha256: "2".repeat(64),
        effect_class: EffectClass::Observation,
        accepted_at: now,
        effective_deadline: now + Duration::from_secs(10),
    };
    let request = BrowserRequest {
        request_id: "capture-control".into(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    };
    assert!(matches!(
        actor.handle(&ctx, &request).unwrap(),
        HandlerOutcome::Success(_)
    ));
    slot.borrow_mut().take().unwrap()
}
fn owner() -> PageOwnerSnapshot {
    PageOwnerSnapshot {
        session_id: "fixture-session".into(),
        session: SessionMachine::new().snapshot(),
        webview_token: "fixture-webview".into(),
        current_url: "http://127.0.0.1/fixture".into(),
        local_fixture_only: true,
    }
}
fn ready(owner: &PageOwnerSnapshot, count: u64) -> AtomicFixtureRuntime {
    let c = RuntimeCoordinates::from_owner(owner);
    AtomicFixtureRuntime {
        inner: DeterministicLocalRuntime::default(),
        semantic_snapshot: Some(SemanticSnapshot {
            target: semantic_target(&c).unwrap(),
            coordinates: c,
        }),
        applied_action_count: count,
    }
}
fn act(
    runtime: &mut AtomicFixtureRuntime,
    owner: &PageOwnerSnapshot,
    c: &RequestControl,
) -> Result<RuntimeReply, RuntimeFailure> {
    runtime.dispatch_page_act(
        Some(owner),
        semantic_target(&RuntimeCoordinates::from_owner(owner)).unwrap(),
        PageAction::Click,
        c,
    )
}
#[test]
fn atomic_action_count_wire_overflow_preserves_admission_and_effect_count() {
    let o = owner();
    let mut r = ready(&o, i64::MAX as u64);
    let before = r.semantic_snapshot.clone();
    assert!(act(&mut r, &o, &control()).is_err());
    assert_eq!(r.applied_action_count, i64::MAX as u64);
    assert_eq!(r.semantic_snapshot, before);
}
#[test]
fn atomic_mutation_epoch_wire_overflow_preserves_admission_and_effect_count() {
    let mut o = owner();
    o.session.revisions.mutation_epoch = i64::MAX as u64;
    let mut r = ready(&o, 0);
    let before = r.semantic_snapshot.clone();
    assert!(act(&mut r, &o, &control()).is_err());
    assert_eq!(r.applied_action_count, 0);
    assert_eq!(r.semantic_snapshot, before);
}
#[test]
fn atomic_observation_wire_overflow_never_publishes_an_unreturnable_target() {
    let mut o = owner();
    o.session.revisions.semantic_snapshot_revision = i64::MAX as u64;
    let mut r = ready(&o, 0);
    assert!(
        r.dispatch(
            Some(&o),
            BrowserActorMessage::Observe { fields: vec![] },
            &control()
        )
        .is_err()
    );
    assert!(r.semantic_snapshot.is_none());
    assert_eq!(r.applied_action_count, 0);
}
#[test]
fn atomic_cancellation_and_deadline_refuse_before_mutation() {
    for expired in [true, false] {
        let o = owner();
        let mut r = ready(&o, 0);
        let before = r.semantic_snapshot.clone();
        let mut c = control();
        if expired {
            c.deadline = Instant::now() - Duration::from_secs(1)
        } else {
            c.cancel()
        }
        assert!(act(&mut r, &o, &c).is_err());
        assert_eq!(r.applied_action_count, 0);
        assert_eq!(r.semantic_snapshot, before);
    }
}
#[test]
fn atomic_success_consumes_exact_snapshot_once() {
    let o = owner();
    let mut r = ready(&o, 0);
    let c = control();
    let reply = act(&mut r, &o, &c).unwrap();
    assert_eq!(reply.result["action_count"], JsonValue::Integer(1));
    assert_eq!(
        reply.result["servo_adapter_exercised"],
        JsonValue::Bool(false)
    );
    assert_eq!(r.applied_action_count, 1);
    assert!(r.semantic_snapshot.is_none());
    assert!(act(&mut r, &o, &c).is_err());
    assert_eq!(r.applied_action_count, 1);
}
#[test]
fn atomic_last_wire_representable_counter_is_admitted() {
    let o = owner();
    let mut r = ready(&o, i64::MAX as u64 - 1);
    let reply = act(&mut r, &o, &control()).unwrap();
    assert_eq!(reply.result["action_count"], JsonValue::Integer(i64::MAX));
    assert_eq!(r.applied_action_count, i64::MAX as u64);
}
#[test]
fn atomic_nonlocal_owner_and_changed_target_cannot_consume_admission() {
    let o = owner();
    let mut r = ready(&o, 0);
    let before = r.semantic_snapshot.clone();
    let c = control();
    let mut bad = o.clone();
    bad.local_fixture_only = false;
    assert!(act(&mut r, &bad, &c).is_err());
    let mut target = semantic_target(&RuntimeCoordinates::from_owner(&o)).unwrap();
    target.structural_fingerprint = "a".repeat(64);
    assert!(
        r.dispatch_page_act(Some(&o), target, PageAction::Click, &c)
            .is_err()
    );
    assert_eq!(r.applied_action_count, 0);
    assert_eq!(r.semantic_snapshot, before);
}

#[test]
fn stale_fixture_target_cannot_be_reparented_across_webviews() {
    let old = owner();
    let mut new = old.clone();
    new.session_id = "replacement-session".into();
    new.webview_token = "replacement-webview".into();
    let mut runtime = ready(&new, 0);
    let target = semantic_target(&RuntimeCoordinates::from_owner(&old)).unwrap();
    let result = runtime.dispatch_page_act(Some(&new), target, PageAction::Click, &control());
    assert!(
        result.is_err(),
        "old reference was reparented into a new WebView: {result:?}"
    );
    assert_eq!(runtime.applied_action_count, 0);
    assert!(runtime.semantic_snapshot.is_some());
}

#[test]
fn frame_scope_changes_even_when_only_outer_session_identity_changes() {
    let old = owner();
    let mut new = old.clone();
    new.session_id = "different-session".into();
    let mut runtime = ready(&new, 0);
    let stale = semantic_target(&RuntimeCoordinates::from_owner(&old)).unwrap();
    assert!(
        runtime
            .dispatch_page_act(Some(&new), stale, PageAction::Click, &control())
            .is_err()
    );
    assert_eq!(runtime.applied_action_count, 0);
    assert!(
        act(&mut runtime, &new, &control()).is_ok(),
        "refusal must preserve the fresh target"
    );
}

#[test]
fn frame_scope_rejects_invalid_owner_before_snapshot_publication() {
    let mut current = owner();
    let mut runtime = ready(&current, 0);
    current.webview_token = "bad\nview".into();
    assert!(
        runtime
            .dispatch(
                Some(&current),
                BrowserActorMessage::Observe { fields: vec![] },
                &control()
            )
            .is_err()
    );
    assert!(runtime.semantic_snapshot.is_none());
    assert_eq!(runtime.applied_action_count, 0);
}
