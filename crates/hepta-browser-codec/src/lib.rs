//! Strict canonical Browser API message codec.
//!
//! Transport bytes are not dispatched until they have passed recursive
//! duplicate-key rejection, typed decoding with `deny_unknown_fields`,
//! method-specific validation, and byte-for-byte canonical re-encoding.

use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fmt;
use url::Url;

pub const BROWSER_API_PROTOCOL: &str = "trillionnium.desktop.browser-api.v1";
pub const MAX_MESSAGE_BYTES: usize = 262_144;
pub const MAX_TIMEOUT_MS: u32 = 120_000;
pub const MAX_IDENTIFIER_BYTES: usize = 128;
pub const MAX_URL_BYTES: usize = 4_096;
pub const MAX_ACTION_TEXT_BYTES: usize = 65_536;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BrowserRequest {
    pub protocol: String,
    pub request_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_generation: Option<u64>,
    pub timeout_ms: u32,
    pub operation: BrowserOperation,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "method", content = "params")]
pub enum BrowserOperation {
    #[serde(rename = "session.create")]
    SessionCreate(SessionCreateParams),
    #[serde(rename = "page.navigate")]
    PageNavigate(PageNavigateParams),
    #[serde(rename = "page.observe")]
    PageObserve(PageObserveParams),
    #[serde(rename = "page.act")]
    PageAct(PageActParams),
    #[serde(rename = "page.wait")]
    PageWait(PageWaitParams),
    #[serde(rename = "page.extract")]
    PageExtract(PageExtractParams),
    #[serde(rename = "session.snapshot")]
    SessionSnapshot(SessionSnapshotParams),
    #[serde(rename = "session.close")]
    SessionClose(SessionCloseParams),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SessionCreateParams {
    pub profile_id: String,
    pub ui_mode: UiMode,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UiMode {
    Headed,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PageNavigateParams {
    pub url: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub expected_document_generation: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PageObserveParams {
    pub fields: Vec<ObserveField>,
    pub include_iframes: bool,
    pub max_nodes: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObserveField {
    Role,
    Name,
    Text,
    Href,
    Value,
    State,
    Bounds,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PageActParams {
    pub reference: ElementReference,
    pub action: PageAction,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ElementReference {
    pub frame_id: String,
    pub document_generation: u64,
    pub semantic_snapshot_revision: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub backend_node_id: Option<String>,
    pub role: String,
    pub accessible_name_sha256: String,
    pub structural_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case")]
pub enum PageAction {
    Click { button: MouseButton },
    Type { text: String, replace: bool },
    Press { key: String },
    Scroll { delta_x: i32, delta_y: i32 },
    Select { value: String },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MouseButton {
    Primary,
    Middle,
    Secondary,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EffectClass {
    ReadOnly,
    LocalInteraction,
    PotentialExternalEffect,
}

impl BrowserOperation {
    pub const fn effect_class(&self) -> EffectClass {
        match self {
            Self::SessionCreate(_)
            | Self::PageNavigate(_)
            | Self::PageObserve(_)
            | Self::PageWait(_)
            | Self::PageExtract(_)
            | Self::SessionSnapshot(_)
            | Self::SessionClose(_) => EffectClass::ReadOnly,
            Self::PageAct(PageActParams {
                action: PageAction::Scroll { .. },
                ..
            }) => EffectClass::LocalInteraction,
            Self::PageAct(_) => EffectClass::PotentialExternalEffect,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PageWaitParams {
    pub condition: WaitCondition,
    pub poll_interval_ms: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum WaitCondition {
    DocumentGenerationAtLeast { value: u64 },
    SemanticSnapshotAtLeast { value: u64 },
    TextPresent { text: String },
    UrlEquals { url: String },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PageExtractParams {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reference: Option<ElementReference>,
    pub fields: Vec<ExtractField>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExtractField {
    Role,
    Name,
    Text,
    Href,
    Value,
    State,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SessionSnapshotParams {
    pub include_screenshot: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SessionCloseParams {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BrowserResponse {
    pub protocol: String,
    pub request_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_generation: Option<u64>,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<BrowserWireError>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BrowserWireError {
    pub code: String,
    pub message: String,
    pub retryable: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecodedMessage<T> {
    pub value: T,
    pub canonical_bytes: Vec<u8>,
    pub canonical_sha256: String,
}

pub fn encode_request(request: &BrowserRequest) -> Result<Vec<u8>, CodecError> {
    request.validate()?;
    encode_canonical(request)
}

pub fn decode_request(encoded: &[u8]) -> Result<DecodedMessage<BrowserRequest>, CodecError> {
    decode_canonical(encoded, BrowserRequest::validate)
}

pub fn encode_response(response: &BrowserResponse) -> Result<Vec<u8>, CodecError> {
    response.validate()?;
    encode_canonical(response)
}

pub fn decode_response(encoded: &[u8]) -> Result<DecodedMessage<BrowserResponse>, CodecError> {
    decode_canonical(encoded, BrowserResponse::validate)
}

fn encode_canonical<T: Serialize>(value: &T) -> Result<Vec<u8>, CodecError> {
    let encoded = serde_json::to_vec(value).map_err(CodecError::Json)?;
    validate_message_size(&encoded)?;
    Ok(encoded)
}

fn decode_canonical<T>(
    encoded: &[u8],
    validate: impl FnOnce(&T) -> Result<(), CodecError>,
) -> Result<DecodedMessage<T>, CodecError>
where
    T: Serialize + for<'de> Deserialize<'de>,
{
    validate_message_size(encoded)?;
    let value = decode_unique_json(encoded)?;
    let typed = serde_json::from_value::<T>(value).map_err(CodecError::Json)?;
    validate(&typed)?;
    let canonical_bytes = encode_canonical(&typed)?;
    if encoded != canonical_bytes {
        return Err(CodecError::NonCanonicalEncoding);
    }
    Ok(DecodedMessage {
        canonical_sha256: sha256_hex(&canonical_bytes),
        canonical_bytes,
        value: typed,
    })
}

fn validate_message_size(encoded: &[u8]) -> Result<(), CodecError> {
    if encoded.is_empty() {
        return Err(CodecError::EmptyMessage);
    }
    if encoded.len() > MAX_MESSAGE_BYTES {
        return Err(CodecError::MessageTooLarge {
            length: encoded.len(),
            maximum: MAX_MESSAGE_BYTES,
        });
    }
    Ok(())
}

impl BrowserRequest {
    pub fn validate(&self) -> Result<(), CodecError> {
        validate_protocol(&self.protocol)?;
        validate_identifier("request_id", &self.request_id, true)?;
        if !(1..=MAX_TIMEOUT_MS).contains(&self.timeout_ms) {
            return Err(CodecError::InvalidTimeout(self.timeout_ms));
        }
        match &self.operation {
            BrowserOperation::SessionCreate(params) => {
                if self.session_id.is_some() || self.session_generation.is_some() {
                    return Err(CodecError::InvalidSessionBinding(
                        "session.create must not carry an existing session binding",
                    ));
                }
                validate_identifier("profile_id", &params.profile_id, false)?;
            }
            operation => {
                let session_id = self.session_id.as_deref().ok_or(
                    CodecError::InvalidSessionBinding("session operation requires session_id"),
                )?;
                validate_identifier("session_id", session_id, false)?;
                if self
                    .session_generation
                    .is_none_or(|generation| generation == 0)
                {
                    return Err(CodecError::InvalidSessionBinding(
                        "session operation requires a non-zero session_generation",
                    ));
                }
                operation.validate_params()?;
            }
        }
        Ok(())
    }
}

impl BrowserOperation {
    fn validate_params(&self) -> Result<(), CodecError> {
        match self {
            Self::SessionCreate(_) => Ok(()),
            Self::PageNavigate(params) => {
                validate_web_url(&params.url)?;
                if params.expected_document_generation == Some(0) {
                    return Err(CodecError::InvalidOperation(
                        "expected_document_generation must be non-zero when present",
                    ));
                }
                Ok(())
            }
            Self::PageObserve(params) => {
                validate_unique_nonempty(&params.fields, "observe fields")?;
                if !(1..=10_000).contains(&params.max_nodes) {
                    return Err(CodecError::InvalidOperation(
                        "max_nodes must be between 1 and 10000",
                    ));
                }
                Ok(())
            }
            Self::PageAct(params) => {
                params.reference.validate()?;
                params.action.validate()
            }
            Self::PageWait(params) => {
                if !(10..=1_000).contains(&params.poll_interval_ms) {
                    return Err(CodecError::InvalidOperation(
                        "poll_interval_ms must be between 10 and 1000",
                    ));
                }
                params.condition.validate()
            }
            Self::PageExtract(params) => {
                if let Some(reference) = &params.reference {
                    reference.validate()?;
                }
                validate_unique_nonempty(&params.fields, "extract fields")
            }
            Self::SessionSnapshot(_) => Ok(()),
            Self::SessionClose(params) => {
                if params.reason.as_ref().is_some_and(|reason| {
                    reason.is_empty() || reason.len() > 512 || reason.contains('\0')
                }) {
                    return Err(CodecError::InvalidOperation(
                        "close reason must be 1..=512 bytes without NUL",
                    ));
                }
                Ok(())
            }
        }
    }
}

impl ElementReference {
    pub fn validate(&self) -> Result<(), CodecError> {
        validate_identifier("frame_id", &self.frame_id, false)?;
        if self.document_generation == 0 || self.semantic_snapshot_revision == 0 {
            return Err(CodecError::InvalidReference(
                "document and semantic snapshot revisions must be non-zero",
            ));
        }
        if let Some(node_id) = &self.backend_node_id {
            validate_identifier("backend_node_id", node_id, true)?;
        }
        if self.role.is_empty() || self.role.len() > 128 || self.role.contains('\0') {
            return Err(CodecError::InvalidReference(
                "role must be 1..=128 bytes without NUL",
            ));
        }
        if !is_lower_sha256(&self.accessible_name_sha256)
            || !is_lower_sha256(&self.structural_sha256)
        {
            return Err(CodecError::InvalidReference(
                "reference fingerprints must be lowercase SHA-256",
            ));
        }
        Ok(())
    }
}

impl PageAction {
    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::Click { .. } => Ok(()),
            Self::Type { text, .. } => {
                if text.len() > MAX_ACTION_TEXT_BYTES || text.contains('\0') {
                    return Err(CodecError::InvalidOperation(
                        "typed text exceeds the bound or contains NUL",
                    ));
                }
                Ok(())
            }
            Self::Press { key } => {
                if key.is_empty() || key.len() > 64 || key.contains('\0') {
                    return Err(CodecError::InvalidOperation(
                        "key must be 1..=64 bytes without NUL",
                    ));
                }
                Ok(())
            }
            Self::Scroll { delta_x, delta_y } => {
                if delta_x.unsigned_abs() > 100_000 || delta_y.unsigned_abs() > 100_000 {
                    return Err(CodecError::InvalidOperation(
                        "scroll delta exceeds the per-operation bound",
                    ));
                }
                Ok(())
            }
            Self::Select { value } => {
                if value.len() > 4_096 || value.contains('\0') {
                    return Err(CodecError::InvalidOperation(
                        "selection value exceeds the bound or contains NUL",
                    ));
                }
                Ok(())
            }
        }
    }
}

impl WaitCondition {
    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::DocumentGenerationAtLeast { value }
            | Self::SemanticSnapshotAtLeast { value } => {
                if *value == 0 {
                    Err(CodecError::InvalidOperation(
                        "wait revision must be non-zero",
                    ))
                } else {
                    Ok(())
                }
            }
            Self::TextPresent { text } => {
                if text.is_empty() || text.len() > 4_096 || text.contains('\0') {
                    Err(CodecError::InvalidOperation(
                        "wait text must be 1..=4096 bytes without NUL",
                    ))
                } else {
                    Ok(())
                }
            }
            Self::UrlEquals { url } => validate_web_url(url),
        }
    }
}

impl BrowserResponse {
    pub fn validate(&self) -> Result<(), CodecError> {
        validate_protocol(&self.protocol)?;
        validate_identifier("request_id", &self.request_id, true)?;
        match (&self.session_id, self.session_generation) {
            (Some(session_id), Some(generation)) if generation > 0 => {
                validate_identifier("session_id", session_id, false)?;
            }
            (None, None) => {}
            _ => {
                return Err(CodecError::InvalidSessionBinding(
                    "response session_id and generation must appear together",
                ));
            }
        }
        match (self.ok, &self.result, &self.error) {
            (true, Some(result), None) if result.is_object() => Ok(()),
            (false, None, Some(error)) => error.validate(),
            _ => Err(CodecError::InvalidResponseShape),
        }
    }
}

impl BrowserWireError {
    fn validate(&self) -> Result<(), CodecError> {
        if self.code.is_empty()
            || self.code.len() > 64
            || !self.code.bytes().all(|byte| {
                byte.is_ascii_lowercase()
                    || byte.is_ascii_digit()
                    || matches!(byte, b'.' | b'_' | b'-')
            })
        {
            return Err(CodecError::InvalidError("invalid error code"));
        }
        if self.message.is_empty() || self.message.len() > 1_024 || self.message.contains('\0') {
            return Err(CodecError::InvalidError("invalid error message"));
        }
        Ok(())
    }
}

fn validate_protocol(protocol: &str) -> Result<(), CodecError> {
    if protocol == BROWSER_API_PROTOCOL {
        Ok(())
    } else {
        Err(CodecError::ProtocolMismatch)
    }
}

fn validate_identifier(
    field: &'static str,
    value: &str,
    allow_colon: bool,
) -> Result<(), CodecError> {
    if value.is_empty()
        || value.len() > MAX_IDENTIFIER_BYTES
        || !value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric()
                || matches!(byte, b'-' | b'_' | b'.')
                || allow_colon && byte == b':'
        })
    {
        return Err(CodecError::InvalidIdentifier(field));
    }
    Ok(())
}

fn validate_web_url(value: &str) -> Result<(), CodecError> {
    if value.is_empty() || value.len() > MAX_URL_BYTES || value.contains('\0') {
        return Err(CodecError::InvalidUrl);
    }
    let url = Url::parse(value).map_err(|_| CodecError::InvalidUrl)?;
    if !matches!(url.scheme(), "http" | "https")
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err(CodecError::InvalidUrl);
    }
    Ok(())
}

fn validate_unique_nonempty<T: Ord + Copy>(
    values: &[T],
    field: &'static str,
) -> Result<(), CodecError> {
    if values.is_empty() || values.len() > 32 {
        return Err(CodecError::InvalidCollection(field));
    }
    let unique: BTreeSet<_> = values.iter().copied().collect();
    if unique.len() != values.len() {
        return Err(CodecError::InvalidCollection(field));
    }
    Ok(())
}

fn is_lower_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
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

struct UniqueJson(Value);

impl<'de> Deserialize<'de> for UniqueJson {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(UniqueJsonVisitor)
    }
}

struct UniqueJsonVisitor;

impl<'de> Visitor<'de> for UniqueJsonVisitor {
    type Value = UniqueJson;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("JSON without duplicate object members")
    }

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
        Ok(UniqueJson(Value::Bool(value)))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
        Ok(UniqueJson(Value::Number(value.into())))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
        Ok(UniqueJson(Value::Number(value.into())))
    }

    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        serde_json::Number::from_f64(value)
            .map(Value::Number)
            .map(UniqueJson)
            .ok_or_else(|| E::custom("non-finite JSON number"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        self.visit_string(value.to_owned())
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
        Ok(UniqueJson(Value::String(value)))
    }

    fn visit_none<E>(self) -> Result<Self::Value, E> {
        Ok(UniqueJson(Value::Null))
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E> {
        Ok(UniqueJson(Value::Null))
    }

    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        UniqueJson::deserialize(deserializer)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut output = Vec::new();
        while let Some(value) = sequence.next_element::<UniqueJson>()? {
            output.push(value.0);
        }
        Ok(UniqueJson(Value::Array(output)))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut output = serde_json::Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if output.contains_key(&key) {
                return Err(de::Error::custom(format!("duplicate key {key}")));
            }
            output.insert(key, map.next_value::<UniqueJson>()?.0);
        }
        Ok(UniqueJson(Value::Object(output)))
    }
}

fn decode_unique_json(encoded: &[u8]) -> Result<Value, CodecError> {
    let mut deserializer = serde_json::Deserializer::from_slice(encoded);
    let UniqueJson(value) = UniqueJson::deserialize(&mut deserializer).map_err(CodecError::Json)?;
    deserializer.end().map_err(CodecError::Json)?;
    Ok(value)
}

#[derive(Debug)]
pub enum CodecError {
    Json(serde_json::Error),
    EmptyMessage,
    MessageTooLarge { length: usize, maximum: usize },
    NonCanonicalEncoding,
    ProtocolMismatch,
    InvalidIdentifier(&'static str),
    InvalidSessionBinding(&'static str),
    InvalidTimeout(u32),
    InvalidOperation(&'static str),
    InvalidReference(&'static str),
    InvalidCollection(&'static str),
    InvalidUrl,
    InvalidResponseShape,
    InvalidError(&'static str),
    SelfCheckInvariant,
}

impl fmt::Display for CodecError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(error) => write!(formatter, "invalid Browser API JSON: {error}"),
            Self::EmptyMessage => formatter.write_str("Browser API message is empty"),
            Self::MessageTooLarge { length, maximum } => write!(
                formatter,
                "Browser API message length {length} exceeds maximum {maximum}",
            ),
            Self::NonCanonicalEncoding => {
                formatter.write_str("Browser API JSON is not in canonical encoding")
            }
            Self::ProtocolMismatch => formatter.write_str("Browser API protocol mismatch"),
            Self::InvalidIdentifier(field) => {
                write!(formatter, "Browser API {field} is invalid")
            }
            Self::InvalidSessionBinding(reason) => {
                write!(formatter, "Browser API session binding is invalid: {reason}")
            }
            Self::InvalidTimeout(timeout) => {
                write!(formatter, "Browser API timeout {timeout}ms is invalid")
            }
            Self::InvalidOperation(reason) => {
                write!(formatter, "Browser API operation is invalid: {reason}")
            }
            Self::InvalidReference(reason) => {
                write!(formatter, "Browser API reference is invalid: {reason}")
            }
            Self::InvalidCollection(field) => {
                write!(formatter, "Browser API {field} collection is invalid")
            }
            Self::InvalidUrl => formatter.write_str("Browser API URL is invalid or unsafe"),
            Self::InvalidResponseShape => {
                formatter.write_str("Browser API response result/error shape is invalid")
            }
            Self::InvalidError(reason) => {
                write!(formatter, "Browser API error envelope is invalid: {reason}")
            }
            Self::SelfCheckInvariant => formatter.write_str("Browser API codec self-check failed"),
        }
    }
}

impl std::error::Error for CodecError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Json(error) => Some(error),
            _ => None,
        }
    }
}

pub fn self_check() -> Result<(), CodecError> {
    let request = BrowserRequest {
        protocol: BROWSER_API_PROTOCOL.to_owned(),
        request_id: "self-check:1".to_owned(),
        session_id: Some("session-self-check".to_owned()),
        session_generation: Some(1),
        timeout_ms: 2_000,
        operation: BrowserOperation::PageNavigate(PageNavigateParams {
            url: "https://fixture.hepta.invalid/".to_owned(),
            expected_document_generation: Some(1),
        }),
    };
    let encoded = encode_request(&request)?;
    let decoded = decode_request(&encoded)?;
    if decoded.value != request || decoded.canonical_sha256.len() != 64 {
        return Err(CodecError::SelfCheckInvariant);
    }
    let response = BrowserResponse {
        protocol: BROWSER_API_PROTOCOL.to_owned(),
        request_id: request.request_id,
        session_id: request.session_id,
        session_generation: request.session_generation,
        ok: true,
        result: Some(serde_json::json!({"accepted": true})),
        error: None,
    };
    let encoded = encode_response(&response)?;
    if decode_response(&encoded)?.value != response {
        return Err(CodecError::SelfCheckInvariant);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn navigate_request() -> BrowserRequest {
        BrowserRequest {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: "request:1".to_owned(),
            session_id: Some("session-1".to_owned()),
            session_generation: Some(1),
            timeout_ms: 5_000,
            operation: BrowserOperation::PageNavigate(PageNavigateParams {
                url: "https://example.test/path".to_owned(),
                expected_document_generation: Some(2),
            }),
        }
    }

    #[test]
    fn canonical_request_round_trip_is_stable() {
        let request = navigate_request();
        let first = encode_request(&request).unwrap();
        let decoded = decode_request(&first).unwrap();
        assert_eq!(decoded.value, request);
        assert_eq!(decoded.canonical_bytes, first);
        assert_eq!(decoded.canonical_sha256.len(), 64);
    }

    #[test]
    fn duplicate_keys_are_rejected_recursively() {
        let canonical = String::from_utf8(encode_request(&navigate_request()).unwrap()).unwrap();
        let duplicate_top = canonical.replacen(
            "\"protocol\":",
            "\"protocol\":\"trillionnium.desktop.browser-api.v1\",\"protocol\":",
            1,
        );
        assert!(decode_request(duplicate_top.as_bytes()).is_err());

        let duplicate_nested = canonical.replacen(
            "\"url\":",
            "\"url\":\"https://duplicate.test/\",\"url\":",
            1,
        );
        assert!(decode_request(duplicate_nested.as_bytes()).is_err());
    }

    #[test]
    fn noncanonical_whitespace_is_rejected() {
        let mut encoded = encode_request(&navigate_request()).unwrap();
        encoded.insert(0, b' ');
        assert!(matches!(
            decode_request(&encoded),
            Err(CodecError::NonCanonicalEncoding)
        ));
    }

    #[test]
    fn unknown_fields_are_rejected() {
        let canonical = String::from_utf8(encode_request(&navigate_request()).unwrap()).unwrap();
        let modified = canonical.replacen(
            "\"timeout_ms\":5000",
            "\"timeout_ms\":5000,\"unexpected\":true",
            1,
        );
        assert!(decode_request(modified.as_bytes()).is_err());
    }

    #[test]
    fn unsafe_navigation_schemes_are_rejected() {
        let mut request = navigate_request();
        let BrowserOperation::PageNavigate(params) = &mut request.operation else {
            unreachable!();
        };
        params.url = "javascript:alert(1)".to_owned();
        assert!(matches!(
            encode_request(&request),
            Err(CodecError::InvalidUrl)
        ));
    }

    #[test]
    fn session_create_forbids_existing_binding() {
        let request = BrowserRequest {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: "create:1".to_owned(),
            session_id: Some("already-present".to_owned()),
            session_generation: Some(1),
            timeout_ms: 1_000,
            operation: BrowserOperation::SessionCreate(SessionCreateParams {
                profile_id: "profile-1".to_owned(),
                ui_mode: UiMode::Headed,
            }),
        };
        assert!(matches!(
            encode_request(&request),
            Err(CodecError::InvalidSessionBinding(_))
        ));
    }

    #[test]
    fn semantic_reference_requires_nonzero_revisions_and_digests() {
        let reference = ElementReference {
            frame_id: "frame-1".to_owned(),
            document_generation: 0,
            semantic_snapshot_revision: 1,
            backend_node_id: None,
            role: "button".to_owned(),
            accessible_name_sha256: "a".repeat(64),
            structural_sha256: "b".repeat(64),
        };
        assert!(reference.validate().is_err());
    }

    #[test]
    fn mutations_are_classified_as_potential_external_effects() {
        let reference = ElementReference {
            frame_id: "frame-1".to_owned(),
            document_generation: 1,
            semantic_snapshot_revision: 1,
            backend_node_id: None,
            role: "button".to_owned(),
            accessible_name_sha256: "a".repeat(64),
            structural_sha256: "b".repeat(64),
        };
        let click = BrowserOperation::PageAct(PageActParams {
            reference: reference.clone(),
            action: PageAction::Click {
                button: MouseButton::Primary,
            },
        });
        let scroll = BrowserOperation::PageAct(PageActParams {
            reference,
            action: PageAction::Scroll {
                delta_x: 0,
                delta_y: 100,
            },
        });
        assert_eq!(
            click.effect_class(),
            EffectClass::PotentialExternalEffect
        );
        assert_eq!(scroll.effect_class(), EffectClass::LocalInteraction);
    }

    #[test]
    fn response_requires_exactly_one_result_or_error() {
        let response = BrowserResponse {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: "response:1".to_owned(),
            session_id: None,
            session_generation: None,
            ok: true,
            result: None,
            error: None,
        };
        assert!(matches!(
            encode_response(&response),
            Err(CodecError::InvalidResponseShape)
        ));
    }

    #[test]
    fn oversized_message_is_rejected_before_json_decode() {
        let encoded = vec![b' '; MAX_MESSAGE_BYTES + 1];
        assert!(matches!(
            decode_request(&encoded),
            Err(CodecError::MessageTooLarge { .. })
        ));
    }

    #[test]
    fn full_self_check_passes() {
        self_check().unwrap();
    }
}
