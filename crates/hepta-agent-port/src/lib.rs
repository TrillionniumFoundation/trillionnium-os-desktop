//! Connected exactly-one AgentPort bridge.
//!
//! The bridge accepts an already-connected Unix stream, authenticates it with
//! `hepta-agent-transport`, decodes one canonical Browser API request, invokes
//! one typed handler, constructs a response whose identity is copied from that
//! validated request, commits at most one response before the effective
//! monotonic deadline, and returns.
//!
//! It deliberately does not bind a socket path, create a listener, map a peer
//! to semantic authority, dispatch Servo, grant a capability, authorize an
//! external effect, or expose a deterministic transport nonce source.

#![forbid(unsafe_code)]

use hepta_agent_transport::{
    ClientConnection, PeerIdentity, PeerPolicy, ServerConnection, TransportError,
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
    /// Validate semantic admission before durable lifecycle facts are recorded.
    ///
    /// This hook must be bounded and must not dispatch browser work. `Some`
    /// refuses admission with a canonical failure response bound to the decoded
    /// request; `Err` closes the connection without lifecycle facts or dispatch.
    /// Passing preflight does not replace the handler's final authority checks.
    /// The default preserves existing handlers; product handlers must explicitly
    /// implement their attested admission policy here.
    fn preflight(
        &mut self,
        _context: &DispatchContext,
        _request: &BrowserRequest,
    ) -> Result<Option<BrowserWireError>, AgentPortError> {
        Ok(None)
    }

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
    serve_one_with_observer(stream, peer_policy, server_ceiling, handler, &mut observer)
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
    if server_ceiling.is_zero() {
        return Err(AgentPortError::DeadlineExceeded);
    }

    let accepted_at = Instant::now();
    let accepted_unix_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| AgentPortError::ClockBeforeUnixEpoch)?
        .as_millis();
    let server_deadline = accepted_at
        .checked_add(server_ceiling)
        .ok_or(AgentPortError::DeadlineExceeded)?;

    serve_one_until(
        stream,
        peer_policy,
        accepted_at,
        accepted_unix_ms,
        server_deadline,
        handler,
        observer,
    )
}

/// Serve one connection within the exact monotonic deadline reserved at ingress.
///
/// Queue wait and preflight never renew this budget. An already expired deadline
/// closes the consumed stream before a transport handshake or lifecycle callback.
/// The request's optional wall-clock deadline may only shorten this ceiling.
pub fn serve_one_before_with_observer<H, O>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    absolute_server_deadline: Instant,
    handler: &mut H,
    observer: &mut O,
) -> Result<ServiceEvidence, AgentPortError>
where
    H: BrowserRequestHandler,
    O: OperationLifecycleObserver,
{
    let accepted_at = Instant::now();
    if absolute_server_deadline <= accepted_at {
        return Err(AgentPortError::DeadlineExceeded);
    }
    let accepted_unix_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| AgentPortError::ClockBeforeUnixEpoch)?
        .as_millis();
    serve_one_until(
        stream,
        peer_policy,
        accepted_at,
        accepted_unix_ms,
        absolute_server_deadline,
        handler,
        observer,
    )
}

fn serve_one_until<H, O>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    accepted_at: Instant,
    accepted_unix_ms: u128,
    server_deadline: Instant,
    handler: &mut H,
    observer: &mut O,
) -> Result<ServiceEvidence, AgentPortError>
where
    H: BrowserRequestHandler,
    O: OperationLifecycleObserver,
{
    let mut connection =
        ServerConnection::accept(stream, peer_policy, remaining_until(server_deadline)?)?;
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
        canonical_request_sha256: request_sha256,
        effect_class: request.effect_class(),
        accepted_at,
        effective_deadline,
    };

    context.remaining()?;
    let refusal = handler.preflight(&context, &request)?;
    context.remaining()?;
    if let Some(error) = refusal {
        let response = prepare_response(&request, HandlerOutcome::Failure(error))?;
        return publish_response(&mut connection, &context, request, response);
    }
    observer.requested(&context, &request)?;
    if let Err(error) = context.remaining() {
        observer.interrupted(&context, &request, &error)?;
        return Err(error);
    }
    observer.dispatched(&context, &request)?;
    if let Err(error) = context.remaining() {
        observer.interrupted(&context, &request, &error)?;
        return Err(error);
    }

    let outcome = match handler.handle(&context, &request) {
        Ok(outcome) => outcome,
        Err(error) => {
            observer.interrupted(&context, &request, &error)?;
            return Err(error);
        }
    };

    if let Err(error) = context.remaining() {
        observer.interrupted(&context, &request, &error)?;
        return Err(error);
    }
    let response = match prepare_response(&request, outcome) {
        Ok(response) => response,
        Err(error) => {
            observer.interrupted(&context, &request, &error)?;
            return Err(error);
        }
    };
    observer.completed(&context, &request, &response.value, &response.sha256)?;
    publish_response(&mut connection, &context, request, response)
}

struct PreparedResponse {
    value: BrowserResponse,
    encoded: Vec<u8>,
    sha256: String,
}

fn prepare_response(
    request: &BrowserRequest,
    outcome: HandlerOutcome,
) -> Result<PreparedResponse, AgentPortError> {
    let value = bind_response(request, outcome)?;
    let encoded = encode_response(&value)?;
    let sha256 = sha256_hex(&encoded);
    Ok(PreparedResponse {
        value,
        encoded,
        sha256,
    })
}

fn publish_response(
    connection: &mut ServerConnection,
    context: &DispatchContext,
    request: BrowserRequest,
    response: PreparedResponse,
) -> Result<ServiceEvidence, AgentPortError> {
    connection.send_response(
        context.transport_sequence,
        response.encoded,
        context.remaining()?,
    )?;

    Ok(ServiceEvidence {
        transport_sequence: context.transport_sequence,
        request_id: request.request_id,
        session_id: request.session_id,
        session_generation: request.session_generation,
        request_sha256: context.canonical_request_sha256.clone(),
        response_sha256: response.sha256,
        effect_class: context.effect_class,
        response_ok: response.value.outcome.is_ok(),
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
            Self::Handler(_) => formatter.write_str("AgentPort handler failed"),
            Self::SelfCheckThreadPanicked => {
                formatter.write_str("AgentPort self-check thread panicked")
            }
            Self::SelfCheckInvariant(reason) => {
                write!(formatter, "AgentPort self-check invariant failed: {reason}")
            }
        }
    }
}

impl fmt::Debug for AgentPortError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        fmt::Display::fmt(self, formatter)
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
        self.invocation_count =
            self.invocation_count
                .checked_add(1)
                .ok_or(AgentPortError::SelfCheckInvariant(
                    "fixture invocation counter exhausted",
                ))?;
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
    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().map_err(TransportError::from)?;
    let client_policy = PeerPolicy::exact(PeerIdentity::from_stream(&client_stream)?);
    let server_policy = PeerPolicy::exact(PeerIdentity::from_stream(&server_stream)?);
    let server = std::thread::spawn(
        move || -> Result<(ServiceEvidence, usize), AgentPortError> {
            let mut handler = D0FixtureHandler::default();
            let evidence = serve_one(server_stream, server_policy, timeout, &mut handler)?;
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
    use hepta_browser_codec::{NavigationTarget, decode_response, encode_request};
    use std::io::Read;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::{Arc, Mutex};
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
            let evidence = serve_one(server_stream, server_policy, timeout, &mut handler)
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

    enum PreflightDecision {
        Accept,
        Refuse,
        Error,
        Expire,
        OversizedRefusal,
    }

    struct AdmissionHandler {
        decision: PreflightDecision,
        events: Arc<Mutex<Vec<&'static str>>>,
    }

    impl BrowserRequestHandler for AdmissionHandler {
        fn preflight(
            &mut self,
            context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<Option<BrowserWireError>, AgentPortError> {
            self.events.lock().unwrap().push("preflight");
            match self.decision {
                PreflightDecision::Accept => return Ok(None),
                PreflightDecision::Error => {
                    return Err(AgentPortError::Handler("admission failed".to_owned()));
                }
                PreflightDecision::Expire => {
                    while context.remaining().is_ok() {
                        thread::yield_now();
                    }
                }
                PreflightDecision::Refuse | PreflightDecision::OversizedRefusal => {}
            }
            let details = if matches!(self.decision, PreflightDecision::OversizedRefusal) {
                JsonObject::from([(
                    "bounded".to_owned(),
                    JsonValue::String("x".repeat(MAX_HANDLER_STRING_BYTES + 1)),
                )])
            } else {
                JsonObject::from([
                    (
                        "request_id".to_owned(),
                        JsonValue::String("replacement-request".to_owned()),
                    ),
                    (
                        "session_id".to_owned(),
                        JsonValue::String("replacement-session".to_owned()),
                    ),
                    ("session_generation".to_owned(), JsonValue::Integer(999)),
                ])
            };
            Ok(Some(BrowserWireError {
                code: BrowserErrorCode::PolicyDenied,
                message: "semantic admission refused".to_owned(),
                details: Some(details),
            }))
        }

        fn handle(
            &mut self,
            _context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<HandlerOutcome, AgentPortError> {
            self.events.lock().unwrap().push("handle");
            Ok(HandlerOutcome::Success(JsonObject::new()))
        }
    }

    struct AdmissionObserver(Arc<Mutex<Vec<&'static str>>>);

    impl OperationLifecycleObserver for AdmissionObserver {
        fn requested(
            &mut self,
            _context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<(), AgentPortError> {
            self.0.lock().unwrap().push("requested");
            Ok(())
        }

        fn dispatched(
            &mut self,
            _context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<(), AgentPortError> {
            self.0.lock().unwrap().push("dispatched");
            Ok(())
        }

        fn completed(
            &mut self,
            _context: &DispatchContext,
            _request: &BrowserRequest,
            response: &BrowserResponse,
            response_sha256: &str,
        ) -> Result<(), AgentPortError> {
            assert_eq!(
                sha256_hex(&encode_response(response).unwrap()),
                response_sha256
            );
            self.0.lock().unwrap().push("completed");
            Ok(())
        }

        fn interrupted(
            &mut self,
            _context: &DispatchContext,
            _request: &BrowserRequest,
            _error: &AgentPortError,
        ) -> Result<(), AgentPortError> {
            self.0.lock().unwrap().push("interrupted");
            Ok(())
        }
    }

    type PreflightExchange = (
        Result<ServiceEvidence, AgentPortError>,
        Result<Vec<u8>, TransportError>,
        Vec<&'static str>,
    );

    fn exercise_preflight(
        decision: PreflightDecision,
        request: &BrowserRequest,
    ) -> PreflightExchange {
        let timeout = Duration::from_secs(2);
        let ceiling = if matches!(decision, PreflightDecision::Expire) {
            Duration::from_millis(50)
        } else {
            timeout
        };
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let client_policy = policy(&client_stream);
        let server_policy = policy(&server_stream);
        let events = Arc::new(Mutex::new(Vec::new()));
        let server_events = Arc::clone(&events);
        let server = thread::spawn(move || {
            let mut handler = AdmissionHandler {
                decision,
                events: Arc::clone(&server_events),
            };
            let mut observer = AdmissionObserver(server_events);
            serve_one_with_observer(
                server_stream,
                server_policy,
                ceiling,
                &mut handler,
                &mut observer,
            )
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout)
            .expect("client connect");
        let sequence = client
            .send_request(encode_request(request).expect("encode request"), timeout)
            .expect("send request");
        let response = client.receive_response(sequence, timeout);
        let result = server.join().expect("server join");
        let events = events.lock().unwrap().clone();
        (result, response, events)
    }

    #[test]
    fn preflight_refusal_binds_identity_without_handler_or_lifecycle_facts() {
        let request = BrowserRequest {
            request_id: "admission:refused".to_owned(),
            session_id: Some("session-original".to_owned()),
            session_generation: Some(7),
            deadline_unix_ms: None,
            operation: BrowserOperation::SessionSnapshot,
        };
        let (result, encoded, events) = exercise_preflight(PreflightDecision::Refuse, &request);
        let evidence = result.expect("refusal response committed");
        let encoded = encoded.expect("receive refusal");
        let response = decode_response(&encoded).expect("canonical refusal").value;
        assert_eq!(events, ["preflight"]);
        assert_eq!(response.request_id, request.request_id);
        assert_eq!(response.session_id, request.session_id);
        assert_eq!(response.session_generation, request.session_generation);
        assert_eq!(
            response.outcome.expect_err("admission refused").code,
            BrowserErrorCode::PolicyDenied
        );
        assert_eq!(evidence.request_id, request.request_id);
        assert_eq!(evidence.session_id, request.session_id);
        assert_eq!(evidence.session_generation, request.session_generation);
        assert_eq!(evidence.response_sha256, sha256_hex(&encoded));
        assert!(!evidence.response_ok);
        assert!(evidence.response_committed);
    }

    #[test]
    fn preflight_error_closes_without_handler_response_or_lifecycle_facts() {
        let (result, response, events) =
            exercise_preflight(PreflightDecision::Error, &health_request());
        assert!(matches!(result, Err(AgentPortError::Handler(_))));
        assert!(response.is_err());
        assert_eq!(events, ["preflight"]);
    }

    #[test]
    fn accepted_preflight_preserves_durable_completion_order() {
        let (result, encoded, events) =
            exercise_preflight(PreflightDecision::Accept, &health_request());
        let evidence = result.expect("accepted response committed");
        let encoded = encoded.expect("receive response");
        let response = decode_response(&encoded).expect("canonical response").value;
        assert_eq!(
            events,
            [
                "preflight",
                "requested",
                "dispatched",
                "handle",
                "completed"
            ]
        );
        assert!(response.outcome.is_ok());
        assert!(evidence.response_ok);
        assert_eq!(evidence.response_sha256, sha256_hex(&encoded));
    }

    #[test]
    fn preflight_cannot_extend_deadline_or_publish_a_late_refusal() {
        let (result, response, events) =
            exercise_preflight(PreflightDecision::Expire, &health_request());
        assert!(matches!(result, Err(AgentPortError::DeadlineExceeded)));
        assert!(response.is_err());
        assert_eq!(events, ["preflight"]);
    }

    #[test]
    fn preflight_refusal_keeps_existing_response_resource_bounds() {
        let (result, response, events) =
            exercise_preflight(PreflightDecision::OversizedRefusal, &health_request());
        assert!(matches!(
            result,
            Err(AgentPortError::InvalidHandlerResult(_))
        ));
        assert!(response.is_err());
        assert_eq!(events, ["preflight"]);
    }

    #[test]
    fn expired_ingress_deadline_closes_before_handshake_or_admission() {
        let (mut client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let server_policy = policy(&server_stream);
        let events = Arc::new(Mutex::new(Vec::new()));
        let mut handler = AdmissionHandler {
            decision: PreflightDecision::Accept,
            events: Arc::clone(&events),
        };
        let mut observer = AdmissionObserver(Arc::clone(&events));
        let ingress_deadline = Instant::now();
        let result = serve_one_before_with_observer(
            server_stream,
            server_policy,
            ingress_deadline,
            &mut handler,
            &mut observer,
        );
        assert!(matches!(result, Err(AgentPortError::DeadlineExceeded)));
        assert!(events.lock().unwrap().is_empty());
        client_stream
            .set_read_timeout(Some(Duration::from_millis(50)))
            .unwrap();
        let mut challenge = [0; 1];
        assert_eq!(
            client_stream.read(&mut challenge).expect("closed stream"),
            0,
            "no transport challenge may be emitted after ingress expiry"
        );
    }

    struct DeadlineCaptureHandler {
        admitted_deadline: Option<Instant>,
    }

    impl BrowserRequestHandler for DeadlineCaptureHandler {
        fn preflight(
            &mut self,
            context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<Option<BrowserWireError>, AgentPortError> {
            self.admitted_deadline = Some(context.effective_deadline);
            Ok(None)
        }

        fn handle(
            &mut self,
            context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<HandlerOutcome, AgentPortError> {
            assert_eq!(self.admitted_deadline, Some(context.effective_deadline));
            Ok(HandlerOutcome::Success(JsonObject::new()))
        }
    }

    #[test]
    fn preflight_and_dispatch_retain_the_exact_ingress_deadline() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let client_policy = policy(&client_stream);
        let server_policy = policy(&server_stream);
        let ingress_deadline = Instant::now().checked_add(timeout).unwrap();
        let server = thread::spawn(move || {
            let mut handler = DeadlineCaptureHandler {
                admitted_deadline: None,
            };
            let mut observer = NoopOperationLifecycleObserver;
            let evidence = serve_one_before_with_observer(
                server_stream,
                server_policy,
                ingress_deadline,
                &mut handler,
                &mut observer,
            )
            .expect("serve within original ingress budget");
            (evidence, handler.admitted_deadline.unwrap())
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout)
            .expect("client connect");
        let sequence = client
            .send_request(
                encode_request(&health_request()).expect("encode request"),
                timeout,
            )
            .expect("send request");
        let response = client
            .receive_response(sequence, timeout)
            .expect("receive response");
        assert!(decode_response(&response).unwrap().value.outcome.is_ok());
        let (evidence, effective_deadline) = server.join().expect("server join");
        assert_eq!(effective_deadline, ingress_deadline);
        assert!(evidence.response_committed);
    }

    struct DeadlineObserver {
        wait_after_requested: bool,
        events: Vec<&'static str>,
    }

    impl DeadlineObserver {
        fn wait_for_expiry(&self, context: &DispatchContext) {
            while context.remaining().is_ok() {
                thread::yield_now();
            }
        }
    }

    impl OperationLifecycleObserver for DeadlineObserver {
        fn requested(
            &mut self,
            context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<(), AgentPortError> {
            self.events.push("requested");
            if self.wait_after_requested {
                self.wait_for_expiry(context);
            }
            Ok(())
        }

        fn dispatched(
            &mut self,
            context: &DispatchContext,
            _request: &BrowserRequest,
        ) -> Result<(), AgentPortError> {
            self.events.push("dispatched");
            if !self.wait_after_requested {
                self.wait_for_expiry(context);
            }
            Ok(())
        }

        fn interrupted(
            &mut self,
            _context: &DispatchContext,
            _request: &BrowserRequest,
            error: &AgentPortError,
        ) -> Result<(), AgentPortError> {
            assert!(matches!(error, AgentPortError::DeadlineExceeded));
            self.events.push("interrupted");
            Ok(())
        }
    }

    fn assert_deadline_interrupts_after_lifecycle_event(wait_after_requested: bool) {
        let server_ceiling = Duration::from_millis(50);
        let client_timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let client_policy = policy(&client_stream);
        let server_policy = policy(&server_stream);
        let server = thread::spawn(move || {
            let counter = Arc::new(AtomicUsize::new(0));
            let mut handler = CountingHandler(Arc::clone(&counter));
            let mut observer = DeadlineObserver {
                wait_after_requested,
                events: Vec::new(),
            };
            let result = serve_one_with_observer(
                server_stream,
                server_policy,
                server_ceiling,
                &mut handler,
                &mut observer,
            );
            (result, observer.events, counter.load(Ordering::SeqCst))
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, client_timeout)
            .expect("client connect");
        client
            .send_request(
                encode_request(&health_request()).expect("encode"),
                client_timeout,
            )
            .expect("send request");
        drop(client);
        let (result, events, invocation_count) = server.join().expect("server join");
        assert!(matches!(result, Err(AgentPortError::DeadlineExceeded)));
        assert_eq!(invocation_count, 0);
        if wait_after_requested {
            assert_eq!(events, ["requested", "interrupted"]);
        } else {
            assert_eq!(events, ["requested", "dispatched", "interrupted"]);
        }
    }

    #[test]
    fn deadline_after_requested_is_recorded_as_interrupted() {
        assert_deadline_interrupts_after_lifecycle_event(true);
    }

    #[test]
    fn deadline_after_dispatched_is_recorded_as_interrupted() {
        assert_deadline_interrupts_after_lifecycle_event(false);
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
            serve_one(server_stream, server_policy, timeout, &mut handler)
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
        let client_timeout = Duration::from_secs(1);
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let client_policy = policy(&client_stream);
        let server_policy = policy(&server_stream);
        let server = thread::spawn(move || {
            let mut handler = SlowHandler;
            serve_one(server_stream, server_policy, ceiling, &mut handler)
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, client_timeout)
            .expect("client connect");
        client
            .send_request(
                encode_request(&health_request()).expect("encode"),
                client_timeout,
            )
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

    #[test]
    fn handler_error_text_is_not_formatted_into_logs() {
        let error = AgentPortError::Handler(
            "secret page text and credential material must stay private".to_owned(),
        );
        for rendered in [error.to_string(), format!("{error:?}")] {
            assert_eq!(rendered, "AgentPort handler failed");
            assert!(!rendered.contains("secret"));
            assert!(!rendered.contains("credential"));
        }
    }
}
