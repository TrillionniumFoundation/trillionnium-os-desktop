//! Connected exactly-one AgentPort bridge.
//!
//! The bridge accepts an already-connected Unix stream, authenticates it with
//! `hepta-agent-transport`, decodes one canonical Browser API request, invokes
//! one typed handler and constructs a request-bound canonical response. It does
//! not bind a socket path, authorize an effect or dispatch Servo itself.

#![forbid(unsafe_code)]

use hepta_agent_transport::{PeerIdentity, PeerPolicy, ServerConnection, TransportError};
use hepta_browser_codec::{
    BrowserOperation, BrowserRequest, BrowserResponse, BrowserWireError, CodecError,
    DecodedRequest, EffectClass, decode_request, encode_response,
};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::fmt;
use std::os::unix::net::UnixStream;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

pub const DEFAULT_SERVER_CEILING: Duration = Duration::from_secs(20);
pub const MAX_HANDLER_RESULT_MEMBERS: usize = 1_024;

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
        self.effective_deadline
            .checked_duration_since(Instant::now())
            .filter(|remaining| !remaining.is_zero())
            .ok_or(AgentPortError::DeadlineExceeded)
    }
}

#[derive(Debug)]
pub enum HandlerOutcome {
    Success(Map<String, Value>),
    Failure(BrowserWireError),
}

pub trait BrowserRequestHandler {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &DecodedRequest,
    ) -> Result<HandlerOutcome, AgentPortError>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceEvidence {
    pub peer: PeerIdentity,
    pub transport_sequence: u64,
    pub request_sha256: String,
    pub response_sha256: String,
    pub effect_class: EffectClass,
    pub response_committed: bool,
}

pub fn serve_one<H: BrowserRequestHandler>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    server_ceiling: Duration,
    handler: &mut H,
) -> Result<ServiceEvidence, AgentPortError> {
    if server_ceiling.is_zero() {
        return Err(AgentPortError::DeadlineExceeded);
    }
    let accepted_at = Instant::now();
    let accepted_unix_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| AgentPortError::ClockBeforeUnixEpoch)?
        .as_millis();
    let mut connection = ServerConnection::accept(stream, peer_policy, server_ceiling)?;
    let peer = connection.peer_identity();
    let request_frame = connection.receive_request(remaining(accepted_at, server_ceiling)?)?;
    let decoded = decode_request(&request_frame.payload)?;
    let effective_deadline =
        effective_deadline(accepted_at, accepted_unix_ms, server_ceiling, &decoded)?;
    let context = DispatchContext {
        peer,
        transport_sequence: request_frame.sequence,
        canonical_request_sha256: decoded.canonical_sha256.clone(),
        effect_class: decoded.effect_class,
        accepted_at,
        effective_deadline,
    };
    context.remaining()?;
    let outcome = handler.handle(&context, &decoded)?;
    context.remaining()?;
    let response = bind_response(&decoded.value, outcome)?;
    let encoded = encode_response(&response)?;
    let response_sha256 = sha256_hex(&encoded);
    connection.send_response(request_frame.sequence, encoded, context.remaining()?)?;
    Ok(ServiceEvidence {
        peer,
        transport_sequence: request_frame.sequence,
        request_sha256: decoded.canonical_sha256,
        response_sha256,
        effect_class: decoded.effect_class,
        response_committed: true,
    })
}

fn bind_response(
    request: &BrowserRequest,
    outcome: HandlerOutcome,
) -> Result<BrowserResponse, AgentPortError> {
    match outcome {
        HandlerOutcome::Success(result) => {
            if result.len() > MAX_HANDLER_RESULT_MEMBERS {
                return Err(AgentPortError::InvalidHandlerResult);
            }
            Ok(BrowserResponse::success_for(request, result))
        }
        HandlerOutcome::Failure(error) => {
            error.validate()?;
            Ok(BrowserResponse::failure_for(request, error))
        }
    }
}

fn effective_deadline(
    accepted_at: Instant,
    accepted_unix_ms: u128,
    server_ceiling: Duration,
    decoded: &DecodedRequest,
) -> Result<Instant, AgentPortError> {
    let server_deadline = accepted_at
        .checked_add(server_ceiling)
        .ok_or(AgentPortError::DeadlineExceeded)?;
    let Some(request_unix_ms) = decoded.value.deadline_unix_ms else {
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

fn remaining(started: Instant, ceiling: Duration) -> Result<Duration, AgentPortError> {
    let deadline = started
        .checked_add(ceiling)
        .ok_or(AgentPortError::DeadlineExceeded)?;
    deadline
        .checked_duration_since(Instant::now())
        .filter(|remaining| !remaining.is_zero())
        .ok_or(AgentPortError::DeadlineExceeded)
}

fn sha256_hex(encoded: &[u8]) -> String {
    format!("{:x}", Sha256::digest(encoded))
}

#[derive(Debug)]
pub enum AgentPortError {
    Transport(TransportError),
    Codec(CodecError),
    DeadlineExceeded,
    ClockBeforeUnixEpoch,
    InvalidHandlerResult,
    Handler(String),
    SelfCheckThreadPanicked,
    SelfCheckInvariant,
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
            Self::InvalidHandlerResult => {
                formatter.write_str("AgentPort handler result violates the bridge contract")
            }
            Self::Handler(message) => write!(formatter, "AgentPort handler failed: {message}"),
            Self::SelfCheckThreadPanicked => {
                formatter.write_str("AgentPort self-check thread panicked")
            }
            Self::SelfCheckInvariant => {
                formatter.write_str("AgentPort self-check invariant failed")
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

pub fn self_check() -> Result<(), AgentPortError> {
    use hepta_agent_transport::{ClientConnection, PeerIdentity};

    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().map_err(TransportError::from)?;
    let client_policy = PeerPolicy::exact(PeerIdentity::from_stream(&client_stream)?);
    let server_policy = PeerPolicy::exact(PeerIdentity::from_stream(&server_stream)?);
    let server = std::thread::spawn(move || -> Result<ServiceEvidence, AgentPortError> {
        let mut handler = D0FixtureHandler::default();
        let evidence = serve_one(server_stream, server_policy, timeout, &mut handler)?;
        if handler.invocation_count != 1 {
            return Err(AgentPortError::SelfCheckInvariant);
        }
        Ok(evidence)
    });

    let request = BrowserRequest {
        protocol: hepta_browser_codec::BROWSER_API_PROTOCOL.to_owned(),
        request_id: "agent-port:self-check:1".to_owned(),
        session_id: None,
        session_generation: None,
        deadline_unix_ms: None,
        operation: BrowserOperation::Health,
    };
    let mut client = ClientConnection::connect(client_stream, client_policy, timeout)?;
    let sequence = client.send_request(hepta_browser_codec::encode_request(&request)?, timeout)?;
    let response =
        hepta_browser_codec::decode_response(&client.receive_response(sequence, timeout)?)?;
    let evidence = server
        .join()
        .map_err(|_| AgentPortError::SelfCheckThreadPanicked)??;
    let response = response.value;
    let result = response
        .result
        .as_ref()
        .and_then(Value::as_object)
        .ok_or(AgentPortError::SelfCheckInvariant)?;
    if !response.ok
        || sequence != 1
        || evidence.transport_sequence != sequence
        || !evidence.response_committed
        || result.get("agent_port_ready") != Some(&Value::Bool(true))
        || result.get("browser_runtime_available") != Some(&Value::Bool(false))
    {
        return Err(AgentPortError::SelfCheckInvariant);
    }
    Ok(())
}

/// Fail-closed D0 fixture handler. Observation requests receive a mechanism
/// acknowledgement. Potential external effects are denied with the normative
/// retry policy. This is not the future BrowserActor.
#[derive(Debug, Default)]
pub struct D0FixtureHandler {
    pub invocation_count: usize,
}

impl BrowserRequestHandler for D0FixtureHandler {
    fn handle(
        &mut self,
        context: &DispatchContext,
        request: &DecodedRequest,
    ) -> Result<HandlerOutcome, AgentPortError> {
        self.invocation_count = self.invocation_count.saturating_add(1);
        if context.effect_class == EffectClass::PotentialExternalEffect {
            return Ok(HandlerOutcome::Failure(BrowserWireError::new(
                "policy_denied",
                "external effects remain closed before the effect barrier",
            )?));
        }
        if !matches!(&request.value.operation, BrowserOperation::Health) {
            return Ok(HandlerOutcome::Failure(BrowserWireError::new(
                "unsupported",
                "the Servo BrowserActor is not connected in the D0 fixture",
            )?));
        }
        let mut result = Map::new();
        result.insert("agent_port_ready".to_owned(), Value::Bool(true));
        result.insert("browser_runtime_available".to_owned(), Value::Bool(false));
        result.insert("mechanism_only".to_owned(), Value::Bool(true));
        Ok(HandlerOutcome::Success(result))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use hepta_agent_transport::{ClientConnection, PeerIdentity};
    use hepta_browser_codec::{
        BROWSER_API_PROTOCOL, BrowserOperation, NavigationTarget, decode_response, encode_request,
    };
    use std::thread;

    fn policy(stream: &UnixStream) -> PeerPolicy {
        PeerPolicy::exact(PeerIdentity::from_stream(stream).unwrap())
    }

    fn health_request() -> BrowserRequest {
        BrowserRequest {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: "bridge:health:1".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        }
    }

    fn navigate_request() -> BrowserRequest {
        BrowserRequest {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: "bridge:navigate:1".to_owned(),
            session_id: Some("session-1".to_owned()),
            session_generation: Some(3),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageNavigate {
                target: NavigationTarget::ExternalHttps {
                    url: "https://example.test/path".to_owned(),
                },
                expected_document_generation: 7,
            },
        }
    }

    fn round_trip(request: BrowserRequest) -> (ServiceEvidence, BrowserResponse, usize) {
        let timeout = Duration::from_secs(2);
        let (client_stream, server_stream) = UnixStream::pair().unwrap();
        let client_policy = policy(&client_stream);
        let server_policy = policy(&server_stream);
        let server = thread::spawn(move || {
            let mut handler = D0FixtureHandler::default();
            let evidence = serve_one(server_stream, server_policy, timeout, &mut handler).unwrap();
            (evidence, handler.invocation_count)
        });
        let mut client = ClientConnection::connect(client_stream, client_policy, timeout).unwrap();
        let sequence = client
            .send_request(encode_request(&request).unwrap(), timeout)
            .unwrap();
        let response = decode_response(&client.receive_response(sequence, timeout).unwrap())
            .unwrap()
            .value;
        let (evidence, count) = server.join().unwrap();
        (evidence, response, count)
    }

    #[test]
    fn observation_dispatches_exactly_once_and_binds_response() {
        let request = health_request();
        let (evidence, response, count) = round_trip(request.clone());
        assert_eq!(count, 1);
        assert_eq!(evidence.transport_sequence, 1);
        assert!(evidence.response_committed);
        assert_eq!(response.request_id, request.request_id);
        assert!(response.ok);
    }

    #[test]
    fn navigation_reaches_handler_as_effect_and_is_denied() {
        let request = navigate_request();
        let (evidence, response, count) = round_trip(request.clone());
        assert_eq!(count, 1);
        assert_eq!(evidence.effect_class, EffectClass::PotentialExternalEffect);
        assert_eq!(response.request_id, request.request_id);
        assert_eq!(response.session_id, request.session_id);
        assert_eq!(response.session_generation, request.session_generation);
        assert!(!response.ok);
        assert_eq!(response.error.unwrap().code, "policy_denied");
    }

    #[test]
    fn browser_dependent_observation_is_truthfully_unsupported() {
        let request = BrowserRequest {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: "bridge:observe:1".to_owned(),
            session_id: Some("session-1".to_owned()),
            session_generation: Some(3),
            deadline_unix_ms: None,
            operation: BrowserOperation::PageObserve {
                fields: vec![hepta_browser_codec::ObservationField::Role],
            },
        };
        let (_, response, count) = round_trip(request);
        assert_eq!(count, 1);
        assert!(!response.ok);
        assert_eq!(response.error.unwrap().code, "unsupported");
    }

    struct SlowHandler;

    impl BrowserRequestHandler for SlowHandler {
        fn handle(
            &mut self,
            _context: &DispatchContext,
            _request: &DecodedRequest,
        ) -> Result<HandlerOutcome, AgentPortError> {
            thread::sleep(Duration::from_millis(20));
            Ok(HandlerOutcome::Success(Map::new()))
        }
    }

    #[test]
    fn late_handler_result_is_not_committed() {
        let timeout = Duration::from_millis(5);
        let (client_stream, server_stream) = UnixStream::pair().unwrap();
        let server_policy = policy(&server_stream);
        let client_policy = policy(&client_stream);
        let server = thread::spawn(move || {
            let mut handler = SlowHandler;
            serve_one(server_stream, server_policy, timeout, &mut handler)
        });
        let mut client =
            ClientConnection::connect(client_stream, client_policy, Duration::from_secs(1))
                .unwrap();
        client
            .send_request(
                encode_request(&health_request()).unwrap(),
                Duration::from_secs(1),
            )
            .unwrap();
        assert!(matches!(
            server.join().unwrap(),
            Err(AgentPortError::DeadlineExceeded)
        ));
    }

    #[test]
    fn connected_stack_self_check_passes_without_listener() {
        self_check().unwrap();
    }
}
