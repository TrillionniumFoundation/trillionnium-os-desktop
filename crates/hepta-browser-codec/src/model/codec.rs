#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecodedMessage<T> {
    pub value: T,
    pub canonical_bytes: Vec<u8>,
    pub canonical_sha256: String,
}

pub fn decode_request(encoded: &[u8]) -> Result<DecodedMessage<BrowserRequest>, CodecError> {
    decode_message(encoded, BrowserRequest::from_json)
}

pub fn encode_request(request: &BrowserRequest) -> Result<Vec<u8>, CodecError> {
    request.to_json()?.canonical_bytes().map_err(CodecError::Json)
}

pub fn decode_response(encoded: &[u8]) -> Result<DecodedMessage<BrowserResponse>, CodecError> {
    decode_message(encoded, BrowserResponse::from_json)
}

pub fn encode_response(response: &BrowserResponse) -> Result<Vec<u8>, CodecError> {
    response.to_json()?.canonical_bytes().map_err(CodecError::Json)
}

fn decode_message<T>(
    encoded: &[u8],
    convert: impl FnOnce(JsonValue) -> Result<T, CodecError>,
) -> Result<DecodedMessage<T>, CodecError> {
    if encoded.is_empty() || encoded.len() > MAX_MESSAGE_BYTES {
        return Err(CodecError::Json(JsonError::MessageSize {
            length: encoded.len(),
            maximum: MAX_MESSAGE_BYTES,
        }));
    }
    let raw = decode_unique(encoded).map_err(CodecError::Json)?;
    let canonical_bytes = raw.canonical_bytes().map_err(CodecError::Json)?;
    let value = convert(raw)?;
    if encoded != canonical_bytes {
        return Err(CodecError::NonCanonicalEncoding);
    }
    Ok(DecodedMessage {
        canonical_sha256: sha256_hex(&canonical_bytes),
        canonical_bytes,
        value,
    })
}

pub fn self_check() -> Result<(), CodecError> {
    let request = BrowserRequest {
        request_id: "self-check:codec:1".to_owned(),
        session_id: Some("session-self-check".to_owned()),
        session_generation: Some(1),
        deadline_unix_ms: None,
        operation: BrowserOperation::PageNavigate {
            target: NavigationTarget::LocalHttpFixture {
                url: "http://127.0.0.1:8080/fixture".to_owned(),
            },
            expected_document_generation: 1,
        },
    };
    if request.effect_class() != EffectClass::PotentialExternalEffect {
        return Err(CodecError::SelfCheckInvariant(
            "navigation was not classified as a potential external effect",
        ));
    }
    let encoded = encode_request(&request)?;
    let decoded = decode_request(&encoded)?;
    if decoded.value != request || decoded.canonical_sha256.len() != 64 {
        return Err(CodecError::SelfCheckInvariant(
            "request canonical round trip failed",
        ));
    }
    let response = BrowserResponse::failure(
        request.request_id,
        request.session_id,
        request.session_generation,
        BrowserWireError {
            code: BrowserErrorCode::PolicyDenied,
            message: "external-effect authority is closed in D0".to_owned(),
            details: None,
        },
    )?;
    let encoded = encode_response(&response)?;
    if decode_response(&encoded)?.value != response {
        return Err(CodecError::SelfCheckInvariant(
            "response canonical round trip failed",
        ));
    }
    Ok(())
}
