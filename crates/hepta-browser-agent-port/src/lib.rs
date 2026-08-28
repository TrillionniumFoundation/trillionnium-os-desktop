//! Connected-stream AgentPort request bridge.
//!
//! This crate composes the authenticated AF_UNIX carrier and strict canonical
//! Browser API codec. It accepts an already-connected stream, dispatches at
//! most one request to a typed handler, binds the response to the exact request,
//! and returns. It does not bind a socket path, create a listener, own a Servo
//! object, or authorize an external effect.

use hepta_agent_transport::{
    NonceSource, PeerIdentity, PeerPolicy, ServerConnection, TransportError,
};
use hepta_browser_codec::{
    BROWSER_API_PROTOCOL, BrowserRequest, BrowserResponse, BrowserWireError, CodecError,
    EffectClass, decode_request, encode_response,
};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::fmt;
use std::os::unix::net::UnixStream;
use std::time::{Duration, Instant};

pub type BrowserResult = Map<String, Value>;

pub trait BrowserRequestHandler {
    fn handle(
        &mut self,
        request: &BrowserRequest,
        context: &DispatchContext,
    ) -> Result<BrowserResult, BrowserWireError>;
}

#[derive(Debug, Clone)]
pub struct DispatchContext {
    peer: PeerIdentity,
    transport_sequence: u64,
    canonical_request_sha256: String,
    effect_class: EffectClass,
    deadline: Instant,
}

impl DispatchContext {
    pub const fn peer(&self) -> PeerIdentity {
        self.peer
    }

    pub const fn transport_sequence(&self) -> u64 {
        self.transport_sequence
    }

    pub fn canonical_request_sha256(&self) -> &str {
        &self.canonical_request_sha256
    }

    pub const fn effect_class(&self) -> EffectClass {
        self.effect_class
    }

    pub const fn deadline(&self) -> Instant {
        self.deadline
    }

    pub fn remaining(&self) -> Result<Duration, AgentPortError> {
        remaining_until(self.deadline)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServeOutcome {
    pub peer: PeerIdentity,
    pub transport_sequence: u64,
    pub request_id: String,
    pub session_id: Option<String>,
    pub session_generation: Option<u64>,
    pub effect_class: EffectClass,
    pub canonical_request_sha256: String,
    pub canonical_response_sha256: String,
    pub response_ok: bool,
}

pub fn serve_single_request<S, H>(
    stream: UnixStream,
    peer_policy: PeerPolicy,
    nonce_source: S,
    server_ceiling: Duration,
    handler: &mut H,
) -> Result<ServeOutcome, AgentPortError>
where
    S: NonceSource,
    H: BrowserRequestHandler,
{
    if server_ceiling.is_zero() {
        return Err(AgentPortError::DeadlineExceeded);
    }
    let started = Instant::now();
    let server_deadline = started
        .checked_add(server_ceiling)
        .ok_or(AgentPortError::DeadlineExceeded)?;

    let mut connection = ServerConnection::accept_with_nonce_source(
        stream,
        peer_policy,
        nonce_source,
        remaining_until(server_deadline)?,
    )?;
    let received = connection.receive_request(remaining_until(server_deadline)?)?;
    let decoded = decode_request(&received.payload)?;

    let request_window = Duration::from_millis(u64::from(decoded.value.timeout_ms));
    let request_deadline = started
        .checked_add(request_window)
        .ok_or(AgentPortError::DeadlineExceeded)?
        .min(server_deadline);
    let context = DispatchContext {
        peer: connection.peer_identity(),
        transport_sequence: received.sequence,
        canonical_request_sha256: decoded.canonical_sha256.clone(),
        effect_class: decoded.value.operation.effect_class(),
        deadline: request_deadline,
    };
    context.remaining()?;

    let response = match handler.handle(&decoded.value, &context) {
        Ok(result) => BrowserResponse {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: decoded.value.request_id.clone(),
            session_id: decoded.value.session_id.clone(),
            session_generation: decoded.value.session_generation,
            ok: true,
            result: Some(Value::Object(result)),
            error: None,
        },
        Err(error) => BrowserResponse {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: decoded.value.request_id.clone(),
            session_id: decoded.value.session_id.clone(),
            session_generation: decoded.value.session_generation,
            ok: false,
            result: None,
            error: Some(error),
        },
    };
    let encoded_response = encode_response(&response)?;
    let response_sha256 = sha256_hex(&encoded_response);
    connection.send_response(
        received.sequence,
        encoded_response,
        remaining_until(request_deadline)?,
    )?;

    Ok(ServeOutcome {
        peer: context.peer,
        transport_sequence: received.sequence,
        request_id: decoded.value.request_id,
        session_id: decoded.value.session_id,
        session_generation: decoded.value.session_generation,
        effect_class: context.effect_class,
        canonical_request_sha256: context.canonical_request_sha256,
        canonical_response_sha256: response_sha256,
        response_ok: response.ok,
    })
}

fn remaining_until(deadline: Instant) -> Result<Duration, AgentPortError> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|remaining| !remaining.is_zero())
        .ok_or(AgentPortError::DeadlineExceeded)
}

fn sha256_hex(value: &[u8]) -> String {
    let digest = Sha256::digest(value);
    let mut output = String::with_capacity(64);
    for byte in digest {
        use std::fmt::Write as _;
        write!(&mut output, "{byte:02x}").expect("writing to String cannot fail");
    }
    output
}

struct SelfCheckHandler;

impl BrowserRequestHandler for SelfCheckHandler {
    fn handle(
        &mut self,
        _request: &BrowserRequest,
        context: &DispatchContext,
    ) -> Result<BrowserResult, BrowserWireError> {
        if context.effect_class() != EffectClass::ReadOnly {
            return Err(BrowserWireError {
                code: "self_check.effect_class".to_owned(),
                message: "unexpected self-check effect class".to_owned(),
                retryable: false,
            });
        }
        Ok(Map::from_iter([(
            "agent_port".to_owned(),
            Value::String("ok".to_owned()),
        )]))
    }
}

pub fn self_check() -> Result<(), AgentPortError> {
    use hepta_agent_transport::{
        ClientConnection, FixedNonceSource, NONCE_BYTES,
    };
    use hepta_browser_codec::{
        BrowserOperation, SessionSnapshotParams, decode_response, encode_request,
    };

    let timeout = Duration::from_secs(2);
    let (client_stream, server_stream) = UnixStream::pair().map_err(TransportError::Io)?;
    let client_policy = PeerPolicy::exact(PeerIdentity::from_stream(&client_stream)?);
    let server_policy = PeerPolicy::exact(PeerIdentity::from_stream(&server_stream)?);
    let server = std::thread::spawn(move || {
        serve_single_request(
            server_stream,
            server_policy,
            FixedNonceSource([0x2a; NONCE_BYTES]),
            timeout,
            &mut SelfCheckHandler,
        )
    });

    let request = BrowserRequest {
        protocol: BROWSER_API_PROTOCOL.to_owned(),
        request_id: "agent-port:self-check".to_owned(),
        session_id: Some("session-self-check".to_owned()),
        session_generation: Some(1),
        timeout_ms: 2_000,
        operation: BrowserOperation::SessionSnapshot(SessionSnapshotParams {
            include_screenshot: false,
        }),
    };
    let mut client = ClientConnection::connect(client_stream, client_policy, timeout)?;
    let sequence = client.send_request(encode_request(&request)?, timeout)?;
    let response = decode_response(&client.receive_response(sequence, timeout)?)?.value;
    if !response.ok
        || response.request_id != request.request_id
        || response
            .result
            .as_ref()
            .and_then(|value| value.get("agent_port"))
            != Some(&Value::String("ok".to_owned()))
    {
        return Err(AgentPortError::SelfCheckInvariant);
    }
    let outcome = server
        .join()
        .map_err(|_| AgentPortError::SelfCheckThreadPanicked)??;
    if !outcome.response_ok
        || outcome.effect_class != EffectClass::ReadOnly
        || outcome.canonical_request_sha256.len() != 64
        || outcome.canonical_response_sha256.len() != 64
    {
        return Err(AgentPortError::SelfCheckInvariant);
    }
    Ok(())
}

#[derive(Debug)]
pub enum AgentPortError {
    Transport(TransportError),
    Codec(CodecError),
    DeadlineExceeded,
    SelfCheckInvariant,
    SelfCheckThreadPanicked,
}

impl fmt::Display for AgentPortError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(error) => write!(formatter, "AgentPort transport failed: {error}"),
            Self::Codec(error) => write!(formatter, "AgentPort message failed: {error}"),
            Self::DeadlineExceeded => {
                formatter.write_str("AgentPort request deadline expired")
            }
            Self::SelfCheckInvariant => {
                formatter.write_str("AgentPort self-check invariant failed")
            }
            Self::SelfCheckThreadPanicked => {
                formatter.write_str("AgentPort self-check thread panicked")
            }
        }
    }
}

impl std::error::Error for AgentPortError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Transport(error) => Some(error),
            Self::Codec(error) => Some(error),
            Self::DeadlineExceeded
            | Self::SelfCheckInvariant
            | Self::SelfCheckThreadPanicked => None,
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
