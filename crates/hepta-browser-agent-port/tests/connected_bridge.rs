use hepta_agent_transport::{
    ClientConnection, FixedNonceSource, NONCE_BYTES, PeerIdentity, PeerPolicy,
};
use hepta_browser_agent_port::{
    AgentPortError, BrowserRequestHandler, BrowserResult, DispatchContext,
    serve_single_request,
};
use hepta_browser_codec::{
    BROWSER_API_PROTOCOL, BrowserOperation, BrowserRequest, BrowserWireError,
    EffectClass, ElementReference, MouseButton, PageActParams, PageAction,
    SessionSnapshotParams, decode_response, encode_request,
};
use serde_json::{Map, Value};
use std::os::unix::net::UnixStream;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

fn policies(client: &UnixStream, server: &UnixStream) -> (PeerPolicy, PeerPolicy) {
    (
        PeerPolicy::exact(PeerIdentity::from_stream(client).unwrap()),
        PeerPolicy::exact(PeerIdentity::from_stream(server).unwrap()),
    )
}

fn snapshot_request(request_id: &str) -> BrowserRequest {
    BrowserRequest {
        protocol: BROWSER_API_PROTOCOL.to_owned(),
        request_id: request_id.to_owned(),
        session_id: Some("session-1".to_owned()),
        session_generation: Some(1),
        timeout_ms: 2_000,
        operation: BrowserOperation::SessionSnapshot(SessionSnapshotParams {
            include_screenshot: false,
        }),
    }
}

struct RecordingHandler {
    calls: Arc<Mutex<Vec<String>>>,
}

impl BrowserRequestHandler for RecordingHandler {
    fn handle(
        &mut self,
        request: &BrowserRequest,
        context: &DispatchContext,
    ) -> Result<BrowserResult, BrowserWireError> {
        self.calls.lock().unwrap().push(request.request_id.clone());
        assert_eq!(context.effect_class(), EffectClass::ReadOnly);
        assert_eq!(context.transport_sequence(), 1);
        assert_eq!(context.canonical_request_sha256().len(), 64);
        assert!(context.remaining().is_ok());
        Ok(Map::from_iter([(
            "snapshot".to_owned(),
            Value::String("fixture".to_owned()),
        )]))
    }
}

#[test]
fn authenticated_canonical_request_dispatches_once_and_binds_response() {
    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().unwrap();
    let (client_policy, server_policy) = policies(&client_stream, &server_stream);
    let calls = Arc::new(Mutex::new(Vec::new()));
    let server_calls = calls.clone();
    let server = thread::spawn(move || {
        let mut handler = RecordingHandler {
            calls: server_calls,
        };
        serve_single_request(
            server_stream,
            server_policy,
            FixedNonceSource([0x44; NONCE_BYTES]),
            timeout,
            &mut handler,
        )
        .unwrap()
    });

    let request = snapshot_request("request:1");
    let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
    let sequence = client
        .send_request(encode_request(&request).unwrap(), timeout)
        .unwrap();
    let response = decode_response(&client.receive_response(sequence, timeout).unwrap())
        .unwrap()
        .value;
    assert!(response.ok);
    assert_eq!(response.request_id, request.request_id);
    assert_eq!(response.session_id, request.session_id);
    assert_eq!(response.session_generation, request.session_generation);
    assert_eq!(response.result.unwrap()["snapshot"], "fixture");

    let outcome = server.join().unwrap();
    assert_eq!(outcome.request_id, "request:1");
    assert_eq!(outcome.transport_sequence, 1);
    assert_eq!(outcome.canonical_request_sha256.len(), 64);
    assert_eq!(outcome.canonical_response_sha256.len(), 64);
    assert!(outcome.response_ok);
    assert_eq!(&*calls.lock().unwrap(), &["request:1"]);
}

struct RefuseEffects;

impl BrowserRequestHandler for RefuseEffects {
    fn handle(
        &mut self,
        _request: &BrowserRequest,
        context: &DispatchContext,
    ) -> Result<BrowserResult, BrowserWireError> {
        if context.effect_class() == EffectClass::PotentialExternalEffect {
            return Err(BrowserWireError {
                code: "policy.external_effect_disabled".to_owned(),
                message: "external mutation is disabled in D0".to_owned(),
                retryable: false,
            });
        }
        Ok(Map::new())
    }
}

fn click_request() -> BrowserRequest {
    BrowserRequest {
        protocol: BROWSER_API_PROTOCOL.to_owned(),
        request_id: "request:effect".to_owned(),
        session_id: Some("session-1".to_owned()),
        session_generation: Some(1),
        timeout_ms: 2_000,
        operation: BrowserOperation::PageAct(PageActParams {
            reference: ElementReference {
                frame_id: "frame-1".to_owned(),
                document_generation: 1,
                semantic_snapshot_revision: 1,
                backend_node_id: None,
                role: "button".to_owned(),
                accessible_name_sha256: "a".repeat(64),
                structural_sha256: "b".repeat(64),
            },
            action: PageAction::Click {
                button: MouseButton::Primary,
            },
        }),
    }
}

#[test]
fn potential_external_effect_is_returned_as_bound_typed_refusal() {
    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().unwrap();
    let (client_policy, server_policy) = policies(&client_stream, &server_stream);
    let server = thread::spawn(move || {
        serve_single_request(
            server_stream,
            server_policy,
            FixedNonceSource([0x55; NONCE_BYTES]),
            timeout,
            &mut RefuseEffects,
        )
        .unwrap()
    });
    let request = click_request();
    let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
    let sequence = client
        .send_request(encode_request(&request).unwrap(), timeout)
        .unwrap();
    let response = decode_response(&client.receive_response(sequence, timeout).unwrap())
        .unwrap()
        .value;
    assert!(!response.ok);
    assert_eq!(
        response.error.unwrap().code,
        "policy.external_effect_disabled"
    );
    assert_eq!(response.request_id, request.request_id);
    let outcome = server.join().unwrap();
    assert_eq!(outcome.effect_class, EffectClass::PotentialExternalEffect);
    assert!(!outcome.response_ok);
}

struct PanicIfCalled;

impl BrowserRequestHandler for PanicIfCalled {
    fn handle(
        &mut self,
        _request: &BrowserRequest,
        _context: &DispatchContext,
    ) -> Result<BrowserResult, BrowserWireError> {
        panic!("malformed payload must not reach the handler")
    }
}

#[test]
fn duplicate_key_payload_fails_before_dispatch() {
    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().unwrap();
    let (client_policy, server_policy) = policies(&client_stream, &server_stream);
    let server = thread::spawn(move || {
        let error = serve_single_request(
            server_stream,
            server_policy,
            FixedNonceSource([0x66; NONCE_BYTES]),
            timeout,
            &mut PanicIfCalled,
        )
        .unwrap_err();
        assert!(matches!(error, AgentPortError::Codec(_)));
    });
    let canonical =
        String::from_utf8(encode_request(&snapshot_request("request:bad")).unwrap()).unwrap();
    let duplicate = canonical.replacen(
        "\"request_id\":",
        "\"request_id\":\"request:shadow\",\"request_id\":",
        1,
    );
    let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
    client
        .send_request(duplicate.into_bytes(), timeout)
        .unwrap();
    server.join().unwrap();
}

struct SlowHandler;

impl BrowserRequestHandler for SlowHandler {
    fn handle(
        &mut self,
        _request: &BrowserRequest,
        _context: &DispatchContext,
    ) -> Result<BrowserResult, BrowserWireError> {
        thread::sleep(Duration::from_millis(40));
        Ok(Map::new())
    }
}

#[test]
fn expired_request_window_prevents_response_commit() {
    let (client_stream, server_stream) = UnixStream::pair().unwrap();
    let (client_policy, server_policy) = policies(&client_stream, &server_stream);
    let server = thread::spawn(move || {
        let error = serve_single_request(
            server_stream,
            server_policy,
            FixedNonceSource([0x77; NONCE_BYTES]),
            Duration::from_secs(1),
            &mut SlowHandler,
        )
        .unwrap_err();
        assert!(matches!(error, AgentPortError::DeadlineExceeded));
    });
    let mut request = snapshot_request("request:deadline");
    request.timeout_ms = 20;
    let mut client = ClientConnection::connect(
        client_stream,
        client_policy,
        Duration::from_secs(1),
    )
    .unwrap();
    client
        .send_request(
            encode_request(&request).unwrap(),
            Duration::from_secs(1),
        )
        .unwrap();
    server.join().unwrap();
}
