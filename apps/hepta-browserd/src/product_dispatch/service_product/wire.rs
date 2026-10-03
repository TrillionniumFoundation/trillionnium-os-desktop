//! Actual same-original socket decode and response, surrounded by P1 proof.
use super::*;
use hepta_agent_port::{
    MAX_HANDLER_CONTAINER_ITEMS, MAX_HANDLER_JSON_DEPTH, MAX_HANDLER_KEY_BYTES,
    MAX_HANDLER_OBJECT_MEMBERS, MAX_HANDLER_STRING_BYTES,
};

pub(super) struct DecodedOriginal {
    pub(super) request: BrowserRequest,
    pub(super) context: DispatchContext,
    canonical: Vec<u8>,
}
pub(super) struct OriginalServiceWire {
    connection: ServerConnection,
    original_deadline: Instant,
}
pub(super) struct WirePublish {
    pub(super) result: Result<ServiceEvidence, ProductDispatchError>,
    pub(super) physical_write_return: bool,
}
pub(super) struct PreparedResponse {
    pub(super) value: BrowserResponse,
    pub(super) encoded: Vec<u8>,
    pub(super) sha256: String,
}

impl OriginalServiceWire {
    pub(super) fn receive_original(
        stream: UnixStream,
        original_deadline: Instant,
        peer: PeerIdentity,
        verifier: &ApprovedServiceRequestVerifier,
        session: &ApprovedServiceSessionVerifier,
    ) -> Result<(Self, DecodedOriginal), ProductDispatchError> {
        original_current(verifier, session, original_deadline)?;
        let accepted_at = Instant::now();
        let accepted_unix_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| ProductDispatchError::DispatchFailed)?
            .as_millis();
        let mut connection = ServerConnection::accept(
            stream,
            PeerPolicy::exact(peer),
            product_time_remaining(original_deadline)?,
        )
        .map_err(|_| ProductDispatchError::DispatchFailed)?;
        original_current(verifier, session, original_deadline)?;
        if connection.peer_identity() != peer {
            return Err(ProductDispatchError::PeerRefused);
        }
        original_current(verifier, session, original_deadline)?;
        let frame = connection
            .receive_request(product_time_remaining(original_deadline)?)
            .map_err(|_| ProductDispatchError::DispatchFailed)?;
        original_current(verifier, session, original_deadline)?;
        let decoded =
            decode_request(&frame.payload).map_err(|_| ProductDispatchError::DispatchFailed)?;
        if decoded.canonical_bytes != frame.payload
            || decoded.canonical_sha256 != executable_sha256(&frame.payload)
        {
            return Err(ProductDispatchError::PeerRefused);
        }
        let request = decoded.value;
        let effective_deadline =
            request_effective_deadline(accepted_at, accepted_unix_ms, original_deadline, &request)
                .map_err(port_error)?;
        let context = DispatchContext {
            peer,
            transport_sequence: frame.sequence,
            canonical_request_sha256: decoded.canonical_sha256,
            effect_class: request.effect_class(),
            accepted_at,
            effective_deadline,
        };
        original_current(verifier, session, effective_deadline)?;
        Ok((
            Self {
                connection,
                original_deadline,
            },
            DecodedOriginal {
                request,
                context,
                canonical: frame.payload,
            },
        ))
    }

    pub(super) fn publish_original(
        &mut self,
        decoded: &DecodedOriginal,
        response: PreparedResponse,
        verifier: &ApprovedServiceRequestVerifier,
        session: &ApprovedServiceSessionVerifier,
    ) -> WirePublish {
        let mut physical_write_return = false;
        let result = (|| {
            if decoded.context.effective_deadline > self.original_deadline
                || executable_sha256(&decoded.canonical) != decoded.context.canonical_request_sha256
                || self.connection.peer_identity() != decoded.context.peer
            {
                return Err(ProductDispatchError::PeerRefused);
            }
            original_current(verifier, session, decoded.context.effective_deadline)?;
            self.connection
                .send_response(
                    decoded.context.transport_sequence,
                    response.encoded,
                    decoded.context.remaining().map_err(port_error)?,
                )
                .map_err(|_| ProductDispatchError::DispatchFailed)?;
            physical_write_return = true;
            original_current(verifier, session, decoded.context.effective_deadline)?;
            Ok(ServiceEvidence {
                transport_sequence: decoded.context.transport_sequence,
                request_id: decoded.request.request_id.clone(),
                session_id: decoded.request.session_id.clone(),
                session_generation: decoded.request.session_generation,
                request_sha256: decoded.context.canonical_request_sha256.clone(),
                response_sha256: response.sha256,
                effect_class: decoded.context.effect_class,
                response_ok: response.value.outcome.is_ok(),
                response_committed: true,
            })
        })();
        WirePublish {
            result,
            physical_write_return,
        }
    }
}

pub(super) fn prepare_response(
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

fn sha256_hex(encoded: &[u8]) -> String {
    executable_sha256(encoded)
}
