//! Real in-process channel/callback regressions with synthetic replies and no
//! attested principal, native Servo, installed policy or external effect.
use super::event_loop::{
    CallbackPageRuntime, CallbackPumpResult, EngineCompletion, callback_engine_pair,
    closed_immutable_callback_engine_pair,
};
use super::*;
use crate::CancellationToken;
use hepta_browser_codec::JsonObject;
use std::time::Instant;

struct FixedReply(&'static str);
impl CallbackPageRuntime for FixedReply {
    fn start(
        &mut self,
        _: Option<&PageOwnerSnapshot>,
        _: BrowserActorMessage,
        done: EngineCompletion,
    ) {
        let _ = done.complete(Ok(reply(Some(self.0))));
    }
    fn retire(&mut self) {}
}
fn reply(url: Option<&str>) -> RuntimeReply {
    RuntimeReply {
        result: JsonObject::new(),
        current_url: url.map(str::to_owned),
    }
}
fn control() -> RequestControl {
    RequestControl {
        request_id: "url-scope-regression".into(),
        deadline: Instant::now() + Duration::from_secs(5),
        cancelled: false,
        cancellation: CancellationToken::new(),
        authority: None,
    }
}
fn owner(url: &str) -> PageOwnerSnapshot {
    let mut owner = super::tests::owner();
    owner.current_url = url.into();
    owner
}
fn exchange(
    closed: bool,
    url: &'static str,
    snapshot: bool,
) -> Result<RuntimeReply, RuntimeFailure> {
    let (wake, events) = mpsc::channel();
    let waker: Arc<dyn EngineEventLoopWaker> = Arc::new(move || {
        let _ = wake.send(());
    });
    let (mut port, mut engine) = if closed {
        closed_immutable_callback_engine_pair(FixedReply(url), waker)
    } else {
        callback_engine_pair(FixedReply(url), waker)
    };
    let worker = thread::spawn(move || {
        let reply = if snapshot {
            port.dispatch(Some(&owner(url)), BrowserActorMessage::Snapshot, &control())
        } else {
            port.dispatch(None, BrowserActorMessage::Health, &control())
        };
        (port, reply)
    });
    events.recv_timeout(Duration::from_secs(5)).unwrap();
    let result = engine.pump_one();
    assert!(matches!(
        result,
        CallbackPumpResult::Replied | CallbackPumpResult::Retired
    ));
    let (_port, reply) = worker.join().unwrap();
    reply
}
#[test]
fn original_callback_rejects_fixed_data_reply_and_closed_callback_delivers_it() {
    assert!(matches!(
        exchange(false, CLOSED_IMMUTABLE_DOCUMENT_URL, false),
        Err(RuntimeFailure::Internal(_))
    ));
    let result = exchange(true, CLOSED_IMMUTABLE_DOCUMENT_URL, false).unwrap();
    assert_eq!(
        result.current_url.as_deref(),
        Some(CLOSED_IMMUTABLE_DOCUMENT_URL)
    );
}
#[test]
fn closed_callback_preserves_real_url_through_subsequent_owner_snapshot() {
    let result = exchange(true, CLOSED_IMMUTABLE_DOCUMENT_URL, true).unwrap();
    assert_eq!(
        result.current_url.as_deref(),
        Some(CLOSED_IMMUTABLE_DOCUMENT_URL)
    );
    assert!(matches!(
        validate_owner(
            Some(&owner(CLOSED_IMMUTABLE_DOCUMENT_URL)),
            EngineUrlScope::D3Local
        ),
        Err(RuntimeFailure::PolicyDenied(_))
    ));
}
#[test]
fn closed_scope_refuses_every_other_document_and_original_scope_stays_local() {
    for url in [
        "about:blank",
        "http://127.0.0.1:8000/fixture",
        "https://example.invalid/",
        "data:text/html,<!DOCTYPE html>",
        "data:text/html,arbitrary",
        "file:///tmp/document",
    ] {
        assert!(!EngineUrlScope::ClosedImmutableReadOnly.allows(url));
        assert!(bound_reply(reply(Some(url)), EngineUrlScope::ClosedImmutableReadOnly).is_err());
        assert!(
            validate_owner(Some(&owner(url)), EngineUrlScope::ClosedImmutableReadOnly).is_err()
        );
    }
    for suffix in ["#fragment", "?query", " "] {
        let url = format!("{CLOSED_IMMUTABLE_DOCUMENT_URL}{suffix}");
        assert!(bound_reply(reply(Some(&url)), EngineUrlScope::ClosedImmutableReadOnly).is_err());
        assert!(
            validate_owner(Some(&owner(&url)), EngineUrlScope::ClosedImmutableReadOnly).is_err()
        );
    }
    for url in ["about:blank", "http://127.0.0.1:8000/fixture"] {
        assert!(bound_reply(reply(Some(url)), EngineUrlScope::D3Local).is_ok());
        assert!(validate_owner(Some(&owner(url)), EngineUrlScope::D3Local).is_ok());
    }
    assert!(
        bound_reply(
            reply(Some("https://example.invalid/")),
            EngineUrlScope::D3Local
        )
        .is_err()
    );
    assert!(bound_reply(reply(None), EngineUrlScope::ClosedImmutableReadOnly).is_ok());
}
#[test]
fn fixed_url_does_not_replace_existing_owner_token_and_fixture_guards() {
    for mutate in [0, 1, 2] {
        let mut invalid = owner(CLOSED_IMMUTABLE_DOCUMENT_URL);
        match mutate {
            0 => invalid.local_fixture_only = false,
            1 => invalid.session_id = "bad/session".into(),
            _ => invalid.webview_token = "bad/view".into(),
        }
        assert!(validate_owner(Some(&invalid), EngineUrlScope::ClosedImmutableReadOnly).is_err());
    }
}
