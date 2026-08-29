//! Connected exactly-one AgentPort bridge.
//!
//! The bridge accepts an already-connected Unix stream, authenticates it with
//! `hepta-agent-transport`, decodes one canonical Browser API request, invokes
//! one typed handler, constructs a response whose identity is copied from that
//! validated request, commits at most one response before the effective
//! monotonic deadline, and returns.
//!
//! It deliberately does not bind a socket path, create a listener, map a peer
//! to semantic authority, dispatch Servo, grant a capability, or authorize an
//! external effect.

#![forbid(unsafe_code)]

use hepta_agent_transport::{
    NonceSource, OsNonceSource, PeerIdentity, PeerPolicy, ServerConnection, TransportError,
};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, BrowserResponse, BrowserWireError,
    CodecError, EffectClass, JsonObject, JsonValue, decode_request, encode_response,
};
use sha2::{Digest, Sha256};
use std::fmt;
use std::os::unix::net::UnixStream;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

pub const DEFAULT_SERVER_CEILING: Duration = Duration::from_secs(20);
pub const MAX_HANDLER_OBJECT_MEMBERS: usize = 1_024;
pub const MAX_HANDLER_CONTAINER_ITEMS: usize = 4_096;
pub const MAX_HANDLER_JSON_DEPTH: usize = 16;
pub const MAX_HANDLER_KEY_BYTES: usize = 128;
pub const MAX_HANDLER_STRING_BYTES: usize = 131_072;

#[derive(Debug, Clone)]
pub struct DispatchContext {
    pub peer: PeerIdentity,
    pub transport_sequence: u64,
    pub canonical_request_sha256: String,
    pub effect_class: EffectClass,
    pub accepted_at: Instant,
    pub effective_deadline: Instant,
}

impl DispatchContext {
    pub fn remaining(&self) -> Result<Duration, AgentPortError> {
        remaining_until(self.effective_deadline)
    }
}

#[derive(Debug)]
pub enum HandlerOutcome {
    Success(JsonObject),
    Failure(BrowserWireError),
}

pub trait BrowserRequestHandler {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError>;
}

/// Durable lifecycle hook around one admitted BrowserActor operation.
///
/// `requested` and `dispatched` run before the handler. `completed` runs only
/// after a bounded canonical response has been constructed and hashed, but
/// before transport commit. Any observer failure is fail-closed. If execution
/// may have started and no terminal record can be written, recovery sees the
/// last durable `dispatched` event and must not automatically replay a
/// potential external effect.
pub trait OperationLifecycleObserver {
    fn requested(
        &mut self,
        _context: &DispatchContext,
        _request: &BrowserRequest,
    ) -> Result<(), AgentPortError> {
        Ok(())
    }

    fn dispatched(
        &mut self,
        _context: &DispatchContext,
        _request: &BrowserRequest,
    ) -> Result<(), AgentPortError> {
        Ok(())
    }

    fn completed(
        &mut self,
        _context: &DispatchContext,
        _request: &BrowserRequest,
        _response: &BrowserResponse,
        _canonical_response_sha256: &str,
    ) -> Result<(), AgentPortError> {
        Ok(())
    }

    fn interrupted(
        &mut self,
        _context: &DispatchContext,
        _request: &BrowserRequest,
        _error: &AgentPortError,
    ) -> Result<(), AgentPortError> {
        Ok(())
    }
}

#[derive(Debug, Default)]
pub struct NoopOperationLifecycleObserver;

impl OperationLifecycleObserver for NoopOperationLifecycleObserver {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceEvidence {
    pub peer: PeerIdentity,
    pub transport_sequence: u64,
    pub request_id: String,
    pub session_id: Option<String>,
    pub session_generation: Option<u64>,
    pub request_sha256: String,
    pub response_sha256: String,
    pub effect_class: EffectClass,
    pub response_ok: bool,
    pub response_committed: bool,
}

pub fn serve_one<H: BrowserRequestHandler>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    server_ceiling: Duration,
    handler: &mut H,
) -> Result<ServiceEvidence, AgentPortError> {
    let mut observer = NoopOperationLifecycleObserver;
    serve_one_with_nonce_source_and_observer(
        stream,
        peer_policy,
        OsNonceSource,
        server_ceiling,
        handler,
        &mut observer,
    )
}

pub fn serve_one_with_observer<H, O>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    server_ceiling: Duration,
    handler: &mut H,
    observer: &mut O,
) -> Result<ServiceEvidence, AgentPortError>
where
    H: BrowserRequestHandler,
    O: OperationLifecycleObserver,
{
    serve_one_with_nonce_source_and_observer(
        stream,
        peer_policy,
        OsNonceSource,
        server_ceiling,
        handler,
        observer,
    )
}

pub fn serve_one_with_nonce_source<S, H>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    nonce_source: S,
    server_ceiling: Duration,
    handler: &mut H,
) -> Result<ServiceEvidence, AgentPortError>
where
    S: NonceSource,
    H: BrowserRequestHandler,
{
    let mut observer = NoopOperationLifecycleObserver;
    serve_one_with_nonce_source_and_observer(
        stream,
        peer_policy,
        nonce_source,
        server_ceiling,
        handler,
        &mut observer,
    )
}

pub fn serve_one_with_nonce_source_and_observer<S, H, O>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    nonce_source: S,
    server_ceiling: Duration,
    handler: &mut H,
    observer: &mut O,
) -> Result<ServiceEvidence, AgentPortError>
where
    S: NonceSource,
    H: BrowserRequestHandler,
    O: OperationLifecycleObserver,
{
    if server_ceiling.is_zero() {
        return Err(AgentPortError::DeadlineExceeded);
    }

    // Wall and monotonic clocks are sampled once at acceptance. Transport,
    // decode, handler execution and response commit all consume the same
    // server budget. Later wall-clock movement cannot extend the deadline.
    let accepted_at = Instant::now();
    let accepted_unix_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| AgentPortError::ClockBeforeUnixEpoch)?
        .as_millis();
    let server_deadline = accepted_at
        .checked_add(server_ceiling)
        .ok_or(AgentPortError::DeadlineExceeded)?;

    let mut connection = ServerConnection::accept_with_nonce_source(
        stream,
        peer_policy,
        nonce_source,
        remaining_until(server_deadline)?,
    )?;
    let peer = connection.peer_identity();
    let request_frame = connection.receive_request(remaining_until(server_deadline)?)?;
    let decoded = decode_request(&request_frame.payload)?;
    let request_sha256 = sha256_hex(&request_frame.payload);
    let request = decoded.value;
    let effective_deadline =
        request_effective_deadline(accepted_at, accepted_unix_ms, server_deadline, &request)?;
    let context = DispatchContext {
        peer,
        transport_sequence: request_frame.sequence,
        canonical_request_sha256: request_sha256.clone(),
        effect_class: request.effect_class(),
        accepted_at,
        effective_deadline,
    };

    context.remaining()?;
    observer.requested(&context, &request)?;
    context.remaining()?;
    observer.dispatched(&context, &request)?;
    context.remaining()?;

    let outcome = match handler.handle(&context, &request) {
        Ok(outcome) => outcome,
        Err(error) => {
            observer.interrupted(&context, &request, &error)?;
            return Err(error);
        }
    };

    // A synchronous handler may return after its budget. Such a result is
    // discarded and no response frame is committed.
    if let Err(error) = context.remaining() {
        observer.interrupted(&context, &request, &error)?;
        return Err(error);
    }
    let response = match bind_response(&request, outcome) {
        Ok(response) => response,
        Err(error) => {
            observer.interrupted(&context, &request, &error)?;
            return Err(error);
        }
    };
    let response_ok = response.outcome.is_ok();
    let encoded = match encode_response(&response) {
        Ok(encoded) => encoded,
        Err(error) => {
            let error = AgentPortError::Codec(error);
            observer.interrupted(&context, &request, &error)?;
            return Err(error);
        }
    };
    let response_sha256 = sha256_hex(&encoded);
    observer.completed(&context, &request, &response, &response_sha256)?;
    connection.send_response(request_frame.sequence, encoded, context.remaining()?)?;

    Ok(ServiceEvidence {
        peer,
        transport_sequence: request_frame.sequence,
        request_id: request.request_id,
        session_id: request.session_id,
        session_generation: request.session_generation,
        request_sha256,
        response_sha256,
        effect_class: context.effect_class,
        response_ok,
        response_committed: true,
    })
}

fn bind_response(
    request: &BrowserRequest,
    outcome: HandlerOutcome,
) -> Result<BrowserResponse, AgentPortError> {
    match outcome {
        HandlerOutcome::Success(result) => {
            validate_handler_object(&result)?;
            BrowserResponse::success(
                request.request_id.clone(),
                request.session_id.clone(),
                request.session_generation,
                result,
            )
            .map_err(AgentPortError::Codec)
        }
        HandlerOutcome::Failure(error) => {
            if let Some(details) = &error.details {
                validate_handler_object(details)?;
            }
            BrowserResponse::failure(
                request.request_id.clone(),
                request.session_id.clone(),
                request.session_generation,
                error,
            )
            .map_err(AgentPortError::Codec)
        }
    }
}

fn validate_handler_object(object: &JsonObject) -> Result<(), AgentPortError> {
    if object.len() > MAX_HANDLER_OBJECT_MEMBERS {
        return Err(AgentPortError::InvalidHandlerResult(
            "top-level result has too many members",
        ));
    }
    let mut items = 0_usize;
    validate_object(object, 0, &mut items)
}

fn validate_object(
    object: &JsonObject,
    depth: usize,
    items: &mut usize,
) -> Result<(), AgentPortError> {
    if depth > MAX_HANDLER_JSON_DEPTH {
        return Err(AgentPortError::InvalidHandlerResult(
            "handler JSON exceeds the depth bound",
        ));
    }
    note_items(items, object.len())?;
    for (key, value) in object {
        if key.is_empty() || key.len() > MAX_HANDLER_KEY_BYTES || key.chars().any(char::is_control)
        {
            return Err(AgentPortError::InvalidHandlerResult(
                "handler JSON contains an invalid object key",
            ));
        }
        validate_value(value, depth + 1, items)?;
    }
    Ok(())
}

fn validate_value(
    value: &JsonValue,
    depth: usize,
    items: &mut usize,
) -> Result<(), AgentPortError> {
    if depth > MAX_HANDLER_JSON_DEPTH {
        return Err(AgentPortError::InvalidHandlerResult(
            "handler JSON exceeds the depth bound",
        ));
    }
    match value {
        JsonValue::String(value) if value.len() > MAX_HANDLER_STRING_BYTES => Err(
            AgentPortError::InvalidHandlerResult("handler JSON string exceeds the byte bound"),
        ),
        JsonValue::Array(values) => {
            note_items(items, values.len())?;
            for value in values {
                validate_value(value, depth + 1, items)?;
            }
            Ok(())
        }
        JsonValue::Object(object) => validate_object(object, depth, items),
        JsonValue::Null | JsonValue::Bool(_) | JsonValue::Integer(_) | JsonValue::String(_) => {
            Ok(())
        }
    }
}

fn note_items(items: &mut usize, additional: usize) -> Result<(), AgentPortError> {
    *items = items
        .checked_add(additional)
        .ok_or(AgentPortError::InvalidHandlerResult(
            "handler JSON item count overflowed",
        ))?;
    if *items > MAX_HANDLER_CONTAINER_ITEMS {
        return Err(AgentPortError::InvalidHandlerResult(
            "handler JSON exceeds the aggregate item bound",
        ));
    }
    Ok(())
}

fn request_effective_deadline(
    accepted_at: Instant,
    accepted_unix_ms: u128,
    server_deadline: Instant,
    request: &BrowserRequest,
) -> Result<Instant, AgentPortError> {
    let Some(request_unix_ms) = request.deadline_unix_ms else {
        return Ok(server_deadline);
    };
    let request_unix_ms = u128::from(request_unix_ms);
    if request_unix_ms <= accepted_unix_ms {
        return Err(AgentPortError::DeadlineExceeded);
    }
    let request_remaining_ms = request_unix_ms - accepted_unix_ms;
    let request_remaining_ms =
        u64::try_from(request_remaining_ms).map_err(|_| AgentPortError::DeadlineExceeded)?;
    let request_deadline = accepted_at
        .checked_add(Duration::from_millis(request_remaining_ms))
        .ok_or(AgentPortError::DeadlineExceeded)?;
    Ok(std::cmp::min(server_deadline, request_deadline))
}

fn remaining_until(deadline: Instant) -> Result<Duration, AgentPortError> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|remaining| !remaining.is_zero())
        .ok_or(AgentPortError::DeadlineExceeded)
}

fn sha256_hex(encoded: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let digest = Sha256::digest(encoded);
    let mut output = String::with_capacity(64);
    for byte in digest {
        output.push(HEX[usize::from(byte >> 4)] as char);
        output.push(HEX[usize::from(byte & 0x0f)] as char);
    }
    output
}

#[derive(Debug)]
pub enum AgentPortError {
    Transport(TransportError),
    Codec(CodecError),
    DeadlineExceeded,
    ClockBeforeUnixEpoch,
    InvalidHandlerResult(&'static str),
    Handler(String),
    SelfCheckThreadPanicked,
    SelfCheckInvariant(&'static str),
}

impl fmt::Display for AgentPortError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(error) => write!(formatter, "AgentPort transport failed: {error}"),
            Self::Codec(error) => write!(formatter, "AgentPort codec failed: {error}"),
            Self::DeadlineExceeded => formatter.write_str("AgentPort deadline expired"),
            Self::ClockBeforeUnixEpoch => {
                formatter.write_str("AgentPort wall clock precedes Unix epoch")
            }
            Self::InvalidHandlerResult(reason) => {
                write!(formatter, "AgentPort handler result is invalid: {reason}")
            }
            Self::Handler(message) => write!(formatter, "AgentPort handler failed: {message}"),
            Self::SelfCheckThreadPanicked => {
                formatter.write_str("AgentPort self-check thread panicked")
            }
            Self::SelfCheckInvariant(reason) => {
                write!(formatter, "AgentPort self-check invariant failed: {reason}")
            }
        }
    }
}

impl std::error::Error for AgentPortError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Transport(error) => Some(error),
            Self::Codec(error) => Some(error),
            _ => None,
        }
    }
}

impl From<TransportError> for AgentPortError {
    fn from(error: TransportError) -> Self {
        Self::Transport(error)
    }
}

impl From<CodecError> for AgentPortError {
    fn from(error: CodecError) -> Self {
        Self::Codec(error)
    }
}

/// Fail-closed D0 fixture handler. It succeeds only for health, refuses every
/// potential external effect, and reports browser-dependent operations as
/// unsupported. It is not the future BrowserActor.
#[derive(Debug, Default)]
pub struct D0FixtureHandler {
    pub invocation_count: usize,
}

impl BrowserRequestHandler for D0FixtureHandler {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &BrowserRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        self.invocation_count = self.invocation_count.saturating_add(1);
        if context.effect_class == EffectClass::PotentialExternalEffect {
            return Ok(HandlerOutcome::Failure(BrowserWireError {
                code: BrowserErrorCode::PolicyDenied,
                message: "external effects remain closed before the effect barrier".to_owned(),
                details: None,
            }));
        }
        if !matches!(&request.operation, BrowserOperation::Health) {
            return Ok(HandlerOutcome::Failure(BrowserWireError {
                code: BrowserErrorCode::Unsupported,
                message: "the Servo BrowserActor is not connected in the D0 fixture".to_owned(),
                details: None,
            }));
        }
        let mut result = JsonObject::new();
        result.insert("agent_port_ready".to_owned(), JsonValue::Bool(true));
        result.insert(
            "browser_runtime_available".to_owned(),
            JsonValue::Bool(false),
        );
        result.insert("mechanism_only".to_owned(), JsonValue::Bool(true));
        Ok(HandlerOutcome::Success(result))
    }
}

pub fn self_check() -> Result<(), AgentPortError> {
    use hepta_agent_transport::{ClientConnection, FixedNonceSource, NONCE_BYTES};

    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().map_err(TransportError::from)?;
    let client_policy = PeerPolicy::exact(PeerIdentity::from_stream(&client_stream)?);
    let server_policy = PeerPolicy::exact(PeerIdentity::from_stream(&server_stream)?);
    let server = std::thread::spawn(
        move || -> Result<(ServiceEvidence, usize), AgentPortError> {
            let mut handler = D0FixtureHandler::default();
            let evidence = serve_one_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([0x2a; NONCE_BYTES]),
                timeout,
                &mut handler,
            )?;
            Ok((evidence, handler.invocation_count))
        },
    );

    let request = BrowserRequest {
        request_id: "agent-port:self-check:1".to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    };
    let mut client = ClientConnection::connect(client_stream, client_policy, timeout)?;
    let sequence = client.send_request(hepta_browser_codec::encode_request(&request)?, timeout)?;
    let response =
        hepta_browser_codec::decode_response(&client.receive_response(sequence, timeout)?)?.value;
    let (evidence, invocation_count) = server
        .join()
        .map_err(|_| AgentPortError::SelfCheckThreadPanicked)??;
    let result = response
        .outcome
        .map_err(|_| AgentPortError::SelfCheckInvariant("health returned an error"))?;
    if invocation_count != 1
        || sequence != 1
        || evidence.transport_sequence != sequence
        || evidence.request_id != request.request_id
        || evidence.request_sha256.len() != 64
        || evidence.response_sha256.len() != 64
        || !evidence.response_ok
        || !evidence.response_committed
        || result.get("agent_port_ready") != Some(&JsonValue::Bool(true))
        || result.get("browser_runtime_available") != Some(&JsonValue::Bool(false))
        || result.get("mechanism_only") != Some(&JsonValue::Bool(true))
    {
        return Err(AgentPortError::SelfCheckInvariant(
            "connected health round trip did not preserve every invariant",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use hepta_agent_transport::{ClientConnection, FixedNonceSource, NONCE_BYTES};
    use hepta_browser_codec::{NavigationTarget, decode_response, encode_request};
    use std::sync::Arc;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::thread;

    fn policy(stream: &UnixStream) -> PeerPolicy {
        PeerPolicy::exact(PeerIdentity::from_stream(stream).expect("peer identity"))
    }

    fn health_request() -> BrowserRequest {
        BrowserRequest {
            request_id: "bridge:health:1".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        }
    }

    #[test]
    fn connected_health_dispatches_exactly_once_and_binds_response() {
        self_check().expect("connected self-check");
    }

    #[test]
    fn potential_external_navigation_is_denied_without_downgrade() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let client_policy = policy(&client_stream);
        let server_policy = policy(&server_stream);
        let server = thread::spawn(move || {
            let mut handler = D0FixtureHandler::default();
            let evidence = serve_one_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([0x33; NONCE_BYTES]),
                timeout,
                &mut handler,
            )
            .expect("serve navigation");
            (evidence, handler.invocation_count)
        });
        let request = BrowserRequest {
            request_id: "bridge:navigate:1".to_owned(),
            session_id: Some("session-1".to_owned()),
            session_generation: Some(1),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageNavigate {
                target: NavigationTarget::ExternalHttps {
                    url: "https://example.com/".to_owned(),
                },
                expected_document_generation: 1,
            },
        };
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout)
            .expect("client connect");
        let sequence = client
            .send_request(encode_request(&request).expect("encode"), timeout)
            .expect("send");
        let response = decode_response(
            &client
                .receive_response(sequence, timeout)
                .expect("receive response"),
        )
        .expect("decode response")
        .value;
        let (evidence, invocation_count) = server.join().expect("server join");
        let error = response.outcome.expect_err("navigation must be refused");
        assert_eq!(invocation_count, 1);
        assert_eq!(evidence.effect_class, EffectClass::PotentialExternalEffect);
        assert!(!evidence.response_ok);
        assert_eq!(error.code, BrowserErrorCode::PolicyDenied);
    }

    struct CountingHandler(Arc<AtomicUsize>);

    impl BrowserRequestHandler for CountingHandler {
        fn handle(
            &mut self,
            _context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<HandlerOutcome, AgentPortError> {
            self.0.fetch_add(1, Ordering::SeqCst);
            Ok(HandlerOutcome::Success(JsonObject::new()))
        }
    }

    #[test]
    fn noncanonical_request_fails_before_handler_invocation() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let client_policy = policy(&client_stream);
        let server_policy = policy(&server_stream);
        let count = Arc::new(AtomicUsize::new(0));
        let server_count = Arc::clone(&count);
        let server = thread::spawn(move || {
            let mut handler = CountingHandler(server_count);
            serve_one_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([0x44; NONCE_BYTES]),
                timeout,
                &mut handler,
            )
        });
        let canonical = encode_request(&health_request()).expect("encode health");
        let mut noncanonical = b" ".to_vec();
        noncanonical.extend_from_slice(&canonical);
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout)
            .expect("client connect");
        client
            .send_request(noncanonical, timeout)
            .expect("send request");
        drop(client);
        let error = server
            .join()
            .expect("server join")
            .expect_err("noncanonical request must fail");
        assert!(matches!(
            error,
            AgentPortError::Codec(CodecError::NonCanonicalEncoding)
        ));
        assert_eq!(count.load(Ordering::SeqCst), 0);
    }

    struct SlowHandler;

    impl BrowserRequestHandler for SlowHandler {
        fn handle(
            &mut self,
            _context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<HandlerOutcome, AgentPortError> {
            thread::sleep(Duration::from_millis(30));
            Ok(HandlerOutcome::Success(JsonObject::new()))
        }
    }

    #[test]
    fn late_handler_result_is_not_committed() {
        let ceiling = Duration::from_millis(10);
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let client_policy = policy(&client_stream);
        let server_policy = policy(&server_stream);
        let server = thread::spawn(move || {
            let mut handler = SlowHandler;
            serve_one_with_nonce_source(
                server_stream,
                server_policy,
                FixedNonceSource([0x55; NONCE_BYTES]),
                ceiling,
                &mut handler,
            )
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, ceiling)
            .expect("client connect");
        client
            .send_request(encode_request(&health_request()).expect("encode"), ceiling)
            .expect("send request");
        let error = server
            .join()
            .expect("server join")
            .expect_err("late handler result must fail");
        assert!(matches!(error, AgentPortError::DeadlineExceeded));
    }

    #[test]
    fn handler_result_depth_is_bounded() {
        let mut value = JsonValue::Null;
        for index in 0..=MAX_HANDLER_JSON_DEPTH {
            value = JsonValue::Object(JsonObject::from([(format!("level-{index}"), value)]));
        }
        let object = match value {
            JsonValue::Object(object) => object,
            _ => unreachable!("fixture root is object"),
        };
        assert!(matches!(
            validate_handler_object(&object),
            Err(AgentPortError::InvalidHandlerResult(_))
        ));
    }
}
