#![forbid(unsafe_code)]

//! D0C-04 connected-stream AgentPort for TrillionniumOS Desktop.
//!
//! The crate composes the authenticated AF_UNIX carrier and canonical Browser
//! API codec. It serves exactly one request on an already-connected stream. It
//! does not create a listener, dispatch a BrowserActor, call Servo, grant a
//! capability, authorize an external effect, or retry an operation.

use std::fmt;
use std::os::unix::net::UnixStream;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use hepta_agent_transport::{
    ClientConnection, PeerIdentity, PeerPolicy, ServerConnection, TransportError,
};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserOperation, BrowserRequest, BrowserResponse, BrowserWireError,
    CodecError, DecodedMessage, EffectClass, JsonObject, JsonValue, decode_request,
    decode_response, encode_request, encode_response,
};
use sha2::{Digest, Sha256};

pub const DEFAULT_SERVER_CEILING: Duration = Duration::from_secs(20);
pub const MAX_HANDLER_OBJECT_MEMBERS: usize = 1_024;
pub const MAX_HANDLER_AGGREGATE_ITEMS: usize = 4_096;
pub const MAX_HANDLER_VALUE_DEPTH: usize = 16;
pub const MAX_HANDLER_KEY_BYTES: usize = 128;
pub const MAX_HANDLER_STRING_BYTES: usize = 131_072;

pub type DecodedRequest = DecodedMessage<BrowserRequest>;

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
        remaining_until(self.effective_deadline, "handler_or_response")
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum HandlerReply {
    Success(JsonObject),
    Failure(BrowserWireError),
}

pub trait BrowserRequestHandler {
    fn handle(&mut self, request: &BrowserRequest, context: &DispatchContext) -> HandlerReply;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceEvidence {
    pub peer: PeerIdentity,
    pub transport_sequence: u64,
    pub canonical_request_sha256: String,
    pub canonical_response_sha256: String,
    pub effect_class: EffectClass,
    pub response_committed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceOutcome {
    pub request_id: String,
    pub evidence: ServiceEvidence,
}

#[derive(Debug)]
pub enum AgentPortError {
    Transport(TransportError),
    Codec(CodecError),
    ClockBeforeUnixEpoch,
    DeadlineOverflow,
    DeadlineExceeded {
        phase: &'static str,
    },
    LateResultDiscarded {
        request_id: String,
        transport_sequence: u64,
        canonical_request_sha256: String,
    },
    HandlerOutputBound {
        reason: &'static str,
    },
    SelfCheckThreadPanicked,
    SelfCheckInvariant(&'static str),
}

impl fmt::Display for AgentPortError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(error) => write!(formatter, "AgentPort transport failed: {error}"),
            Self::Codec(error) => write!(formatter, "AgentPort Browser codec failed: {error}"),
            Self::ClockBeforeUnixEpoch => {
                formatter.write_str("AgentPort wall clock is before the Unix epoch")
            }
            Self::DeadlineOverflow => formatter.write_str("AgentPort deadline overflowed"),
            Self::DeadlineExceeded { phase } => {
                write!(formatter, "AgentPort deadline expired during {phase}")
            }
            Self::LateResultDiscarded {
                request_id,
                transport_sequence,
                ..
            } => write!(
                formatter,
                "AgentPort discarded late handler result for request {request_id} sequence {transport_sequence}",
            ),
            Self::HandlerOutputBound { reason } => {
                write!(formatter, "AgentPort rejected handler output: {reason}")
            }
            Self::SelfCheckThreadPanicked => {
                formatter.write_str("AgentPort self-check server thread panicked")
            }
            Self::SelfCheckInvariant(message) => {
                write!(formatter, "AgentPort self-check invariant failed: {message}")
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

pub fn serve_connected_once<H: BrowserRequestHandler>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    server_ceiling: Duration,
    handler: &mut H,
) -> Result<ServiceOutcome, AgentPortError> {
    serve_connected_once_with_clocks(
        stream,
        peer_policy,
        server_ceiling,
        SystemTime::now(),
        Instant::now(),
        handler,
    )
}

fn serve_connected_once_with_clocks<H: BrowserRequestHandler>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    server_ceiling: Duration,
    accepted_wall: SystemTime,
    accepted_at: Instant,
    handler: &mut H,
) -> Result<ServiceOutcome, AgentPortError> {
    if server_ceiling.is_zero() {
        return Err(AgentPortError::DeadlineExceeded {
            phase: "connection_acceptance",
        });
    }
    let server_deadline = accepted_at
        .checked_add(server_ceiling)
        .ok_or(AgentPortError::DeadlineOverflow)?;
    let mut connection = ServerConnection::accept(
        stream,
        peer_policy,
        remaining_until(server_deadline, "transport_authentication")?,
    )?;
    let peer = connection.peer_identity();
    let received = connection.receive_request(remaining_until(
        server_deadline,
        "transport_request_receive",
    )?)?;
    let decoded = decode_request(&received.payload)?;
    let request = decoded.value;
    let effective_deadline = effective_deadline(
        accepted_wall,
        accepted_at,
        server_deadline,
        request.deadline_unix_ms,
    )?;
    if Instant::now() >= effective_deadline {
        return Err(AgentPortError::DeadlineExceeded {
            phase: "before_handler_dispatch",
        });
    }
    let context = DispatchContext {
        peer,
        transport_sequence: received.sequence,
        canonical_request_sha256: decoded.canonical_sha256.clone(),
        effect_class: request.effect_class(),
        accepted_at,
        effective_deadline,
    };
    let reply = handler.handle(&request, &context);
    if Instant::now() >= effective_deadline {
        return Err(AgentPortError::LateResultDiscarded {
            request_id: request.request_id,
            transport_sequence: received.sequence,
            canonical_request_sha256: decoded.canonical_sha256,
        });
    }
    validate_handler_reply(&reply)?;
    let response = match reply {
        HandlerReply::Success(result) => BrowserResponse::success(
            request.request_id.clone(),
            request.session_id.clone(),
            request.session_generation,
            result,
        )?,
        HandlerReply::Failure(error) => BrowserResponse::failure(
            request.request_id.clone(),
            request.session_id.clone(),
            request.session_generation,
            error,
        )?,
    };
    let encoded_response = encode_response(&response)?;
    let response_sha256 = sha256_hex(&encoded_response);
    if Instant::now() >= effective_deadline {
        return Err(AgentPortError::LateResultDiscarded {
            request_id: request.request_id,
            transport_sequence: received.sequence,
            canonical_request_sha256: decoded.canonical_sha256,
        });
    }
    connection.send_response(
        received.sequence,
        encoded_response,
        remaining_until(effective_deadline, "transport_response_commit")?,
    )?;
    Ok(ServiceOutcome {
        request_id: request.request_id,
        evidence: ServiceEvidence {
            peer,
            transport_sequence: received.sequence,
            canonical_request_sha256: decoded.canonical_sha256,
            canonical_response_sha256: response_sha256,
            effect_class: context.effect_class,
            response_committed: true,
        },
    })
}

fn effective_deadline(
    accepted_wall: SystemTime,
    accepted_at: Instant,
    server_deadline: Instant,
    request_deadline_unix_ms: Option<u64>,
) -> Result<Instant, AgentPortError> {
    let Some(request_deadline_unix_ms) = request_deadline_unix_ms else {
        return Ok(server_deadline);
    };
    let accepted_unix_ms = accepted_wall
        .duration_since(UNIX_EPOCH)
        .map_err(|_| AgentPortError::ClockBeforeUnixEpoch)?
        .as_millis();
    let accepted_unix_ms = u64::try_from(accepted_unix_ms)
        .map_err(|_| AgentPortError::DeadlineOverflow)?;
    if request_deadline_unix_ms <= accepted_unix_ms {
        return Err(AgentPortError::DeadlineExceeded {
            phase: "request_admission",
        });
    }
    let request_delta = Duration::from_millis(request_deadline_unix_ms - accepted_unix_ms);
    let request_deadline = accepted_at
        .checked_add(request_delta)
        .ok_or(AgentPortError::DeadlineOverflow)?;
    Ok(server_deadline.min(request_deadline))
}

fn remaining_until(
    deadline: Instant,
    phase: &'static str,
) -> Result<Duration, AgentPortError> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|remaining| !remaining.is_zero())
        .ok_or(AgentPortError::DeadlineExceeded { phase })
}

fn validate_handler_reply(reply: &HandlerReply) -> Result<(), AgentPortError> {
    let mut aggregate_items = 0_usize;
    match reply {
        HandlerReply::Success(object) => validate_json_object(object, 0, &mut aggregate_items),
        HandlerReply::Failure(error) => {
            if error.message.is_empty() || error.message.len() > 1_024 {
                return Err(AgentPortError::HandlerOutputBound {
                    reason: "typed error message is empty or too large",
                });
            }
            if let Some(details) = &error.details {
                validate_json_object(details, 0, &mut aggregate_items)?;
            }
            Ok(())
        }
    }
}

fn validate_json_object(
    object: &JsonObject,
    depth: usize,
    aggregate_items: &mut usize,
) -> Result<(), AgentPortError> {
    if depth > MAX_HANDLER_VALUE_DEPTH {
        return Err(AgentPortError::HandlerOutputBound {
            reason: "JSON nesting depth exceeded",
        });
    }
    if object.len() > MAX_HANDLER_OBJECT_MEMBERS {
        return Err(AgentPortError::HandlerOutputBound {
            reason: "too many object members",
        });
    }
    *aggregate_items = aggregate_items
        .checked_add(object.len())
        .ok_or(AgentPortError::HandlerOutputBound {
            reason: "aggregate item counter overflowed",
        })?;
    if *aggregate_items > MAX_HANDLER_AGGREGATE_ITEMS {
        return Err(AgentPortError::HandlerOutputBound {
            reason: "aggregate container item bound exceeded",
        });
    }
    for (key, value) in object {
        if key.is_empty()
            || key.len() > MAX_HANDLER_KEY_BYTES
            || key.chars().any(char::is_control)
        {
            return Err(AgentPortError::HandlerOutputBound {
                reason: "object key is empty, too large, or contains a control character",
            });
        }
        validate_json_value(value, depth + 1, aggregate_items)?;
    }
    Ok(())
}

fn validate_json_value(
    value: &JsonValue,
    depth: usize,
    aggregate_items: &mut usize,
) -> Result<(), AgentPortError> {
    if depth > MAX_HANDLER_VALUE_DEPTH {
        return Err(AgentPortError::HandlerOutputBound {
            reason: "JSON nesting depth exceeded",
        });
    }
    match value {
        JsonValue::Null | JsonValue::Bool(_) | JsonValue::Integer(_) => Ok(()),
        JsonValue::String(value) => {
            if value.len() > MAX_HANDLER_STRING_BYTES {
                Err(AgentPortError::HandlerOutputBound {
                    reason: "string value is too large",
                })
            } else {
                Ok(())
            }
        }
        JsonValue::Array(values) => {
            *aggregate_items = aggregate_items
                .checked_add(values.len())
                .ok_or(AgentPortError::HandlerOutputBound {
                    reason: "aggregate item counter overflowed",
                })?;
            if *aggregate_items > MAX_HANDLER_AGGREGATE_ITEMS {
                return Err(AgentPortError::HandlerOutputBound {
                    reason: "aggregate container item bound exceeded",
                });
            }
            for value in values {
                validate_json_value(value, depth + 1, aggregate_items)?;
            }
            Ok(())
        }
        JsonValue::Object(object) => validate_json_object(object, depth, aggregate_items),
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let digest = Sha256::digest(bytes);
    let mut output = String::with_capacity(64);
    for byte in digest {
        output.push(char::from(HEX[usize::from(byte >> 4)]));
        output.push(char::from(HEX[usize::from(byte & 0x0f)]));
    }
    output
}

pub struct D0ClosedHandler;

impl BrowserRequestHandler for D0ClosedHandler {
    fn handle(&mut self, request: &BrowserRequest, _context: &DispatchContext) -> HandlerReply {
        if matches!(&request.operation, BrowserOperation::Health) {
            return HandlerReply::Success(JsonObject::from([
                ("agent_port_ready".to_owned(), JsonValue::Bool(true)),
                (
                    "browser_runtime_available".to_owned(),
                    JsonValue::Bool(false),
                ),
                ("mechanism_only".to_owned(), JsonValue::Bool(true)),
            ]));
        }
        let (code, message) = if request.effect_class() == EffectClass::PotentialExternalEffect {
            (
                BrowserErrorCode::PolicyDenied,
                "external-effect authority is closed in D0",
            )
        } else {
            (
                BrowserErrorCode::Unsupported,
                "BrowserActor and Servo runtime are not implemented",
            )
        };
        HandlerReply::Failure(BrowserWireError {
            code,
            message: message.to_owned(),
            details: None,
        })
    }
}

pub fn self_check() -> Result<(), AgentPortError> {
    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().map_err(TransportError::from)?;
    let client_policy = PeerPolicy::exact(PeerIdentity::from_stream(&client_stream)?);
    let server_policy = PeerPolicy::exact(PeerIdentity::from_stream(&server_stream)?);
    let server = std::thread::spawn(move || {
        let mut handler = D0ClosedHandler;
        serve_connected_once(server_stream, server_policy, timeout, &mut handler)
    });
    let mut client = ClientConnection::connect(client_stream, client_policy, timeout)?;
    let request = BrowserRequest {
        request_id: "self-check:agent-port:1".to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    };
    let sequence = client.send_request(encode_request(&request)?, timeout)?;
    let response_bytes = client.receive_response(sequence, timeout)?;
    let response = decode_response(&response_bytes)?.value;
    match response.outcome {
        Ok(result) if result.get("agent_port_ready") == Some(&JsonValue::Bool(true)) => {}
        _ => {
            return Err(AgentPortError::SelfCheckInvariant(
                "health response was not bound to the closed D0 handler",
            ));
        }
    }
    let outcome = server
        .join()
        .map_err(|_| AgentPortError::SelfCheckThreadPanicked)??;
    if !outcome.evidence.response_committed
        || outcome.evidence.transport_sequence != sequence
        || outcome.evidence.canonical_request_sha256.len() != 64
        || outcome.evidence.canonical_response_sha256.len() != 64
    {
        return Err(AgentPortError::SelfCheckInvariant(
            "connected AgentPort evidence was incomplete",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::thread;

    fn policies(
        client: &UnixStream,
        server: &UnixStream,
    ) -> Result<(PeerPolicy, PeerPolicy), AgentPortError> {
        Ok((
            PeerPolicy::exact(PeerIdentity::from_stream(client)?),
            PeerPolicy::exact(PeerIdentity::from_stream(server)?),
        ))
    }

    fn run_request<H: BrowserRequestHandler + Send + 'static>(
        request: BrowserRequest,
        mut handler: H,
    ) -> Result<(BrowserResponse, ServiceOutcome), AgentPortError> {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().map_err(TransportError::from)?;
        let (client_policy, server_policy) = policies(&client_stream, &server_stream)?;
        let server = thread::spawn(move || {
            serve_connected_once(server_stream, server_policy, timeout, &mut handler)
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout)?;
        let sequence = client.send_request(encode_request(&request)?, timeout)?;
        let response = decode_response(&client.receive_response(sequence, timeout)?)?.value;
        let outcome = server
            .join()
            .map_err(|_| AgentPortError::SelfCheckThreadPanicked)??;
        Ok((response, outcome))
    }

    struct CountingHandler {
        calls: Arc<AtomicUsize>,
        reply: HandlerReply,
    }

    impl BrowserRequestHandler for CountingHandler {
        fn handle(&mut self, _request: &BrowserRequest, _context: &DispatchContext) -> HandlerReply {
            self.calls.fetch_add(1, Ordering::SeqCst);
            self.reply.clone()
        }
    }

    #[test]
    fn canonical_health_dispatches_exactly_once_and_binds_response() {
        let calls = Arc::new(AtomicUsize::new(0));
        let request = BrowserRequest {
            request_id: "test:health:1".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };
        let (response, outcome) = run_request(
            request.clone(),
            CountingHandler {
                calls: Arc::clone(&calls),
                reply: HandlerReply::Success(JsonObject::from([(
                    "accepted".to_owned(),
                    JsonValue::Bool(true),
                )])),
            },
        )
        .expect("connected request must succeed");
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert_eq!(response.request_id, request.request_id);
        assert_eq!(response.session_id, None);
        assert_eq!(outcome.evidence.transport_sequence, 1);
        assert!(outcome.evidence.response_committed);
    }

    #[test]
    fn navigation_is_propagated_as_potential_effect_and_denied() {
        let request = BrowserRequest {
            request_id: "test:navigate:1".to_owned(),
            session_id: Some("session-one".to_owned()),
            session_generation: Some(1),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageNavigate {
                target: hepta_browser_codec::NavigationTarget::ExternalHttps {
                    url: "https://example.com/".to_owned(),
                },
                expected_document_generation: 1,
            },
        };
        let (response, outcome) = run_request(request, D0ClosedHandler)
            .expect("typed denial must be committed");
        assert_eq!(
            outcome.evidence.effect_class,
            EffectClass::PotentialExternalEffect
        );
        match response.outcome {
            Err(error) => assert_eq!(error.code, BrowserErrorCode::PolicyDenied),
            Ok(_) => panic!("navigation must not be authorized"),
        }
    }

    #[test]
    fn duplicate_member_fails_before_handler_invocation() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let (client_policy, server_policy) = policies(&client_stream, &server_stream).expect("policy");
        let calls = Arc::new(AtomicUsize::new(0));
        let server_calls = Arc::clone(&calls);
        let server = thread::spawn(move || {
            let mut handler = CountingHandler {
                calls: server_calls,
                reply: HandlerReply::Success(JsonObject::new()),
            };
            serve_connected_once(server_stream, server_policy, timeout, &mut handler)
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout)
            .expect("client connection");
        let malformed = br#"{"operation":{"type":"health"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"dup","request_id":"dup"}"#.to_vec();
        client
            .send_request(malformed, timeout)
            .expect("send malformed request");
        let error = server
            .join()
            .expect("server thread")
            .expect_err("duplicate must fail");
        assert!(matches!(error, AgentPortError::Codec(_)));
        assert_eq!(calls.load(Ordering::SeqCst), 0);
    }

    struct SlowHandler;

    impl BrowserRequestHandler for SlowHandler {
        fn handle(&mut self, _request: &BrowserRequest, _context: &DispatchContext) -> HandlerReply {
            thread::sleep(Duration::from_millis(25));
            HandlerReply::Success(JsonObject::new())
        }
    }

    #[test]
    fn late_handler_result_is_discarded_without_response_commit() {
        let timeout = Duration::from_millis(10);
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let (client_policy, server_policy) = policies(&client_stream, &server_stream).expect("policy");
        let server = thread::spawn(move || {
            let mut handler = SlowHandler;
            serve_connected_once(server_stream, server_policy, timeout, &mut handler)
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout)
            .expect("client connection");
        let request = BrowserRequest {
            request_id: "test:late:1".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };
        client
            .send_request(encode_request(&request).expect("encode"), timeout)
            .expect("send");
        let error = server
            .join()
            .expect("server thread")
            .expect_err("late result must fail");
        assert!(matches!(
            error,
            AgentPortError::LateResultDiscarded { .. }
                | AgentPortError::DeadlineExceeded { .. }
        ));
    }

    #[test]
    fn oversized_handler_output_is_rejected_without_response_commit() {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().expect("socketpair");
        let (client_policy, server_policy) = policies(&client_stream, &server_stream).expect("policy");
        let server = thread::spawn(move || {
            let mut handler = CountingHandler {
                calls: Arc::new(AtomicUsize::new(0)),
                reply: HandlerReply::Success(JsonObject::from([(
                    "oversized".to_owned(),
                    JsonValue::String("x".repeat(MAX_HANDLER_STRING_BYTES + 1)),
                )])),
            };
            serve_connected_once(server_stream, server_policy, timeout, &mut handler)
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout)
            .expect("client connection");
        let request = BrowserRequest {
            request_id: "test:output-bound:1".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        };
        client
            .send_request(encode_request(&request).expect("encode"), timeout)
            .expect("send");
        let error = server
            .join()
            .expect("server thread")
            .expect_err("oversized output must fail");
        assert!(matches!(
            error,
            AgentPortError::HandlerOutputBound { .. }
        ));
    }

    #[test]
    fn full_connected_self_check_passes() {
        self_check().expect("AgentPort self-check must pass");
    }
}
