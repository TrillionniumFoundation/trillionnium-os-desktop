//! Strict canonical Browser API wire codec for TrillionniumOS Desktop.
//!
//! The codec is a semantic boundary, not a transport or effect authority. It
//! accepts bytes only after recursive duplicate-member rejection, bounded JSON
//! decoding, exact typed validation and byte-for-byte canonical re-encoding.

#![forbid(unsafe_code)]

use hepta_browser_contracts as domain;
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fmt;
use std::net::{Ipv4Addr, Ipv6Addr};
use trillionnium_contract_core::{BoundedId, ContractViolation, DnsLabel, Sha256Hex};

pub const BROWSER_API_PROTOCOL: &str = "trillionnium.desktop.browser-api.v1";
pub const MAX_MESSAGE_BYTES: usize = 262_144;
pub const MAX_JSON_DEPTH: usize = 32;
pub const MAX_CONTAINER_ITEMS: usize = 20_000;
pub const MAX_IDENTIFIER_BYTES: usize = 128;
pub const MAX_URL_BYTES: usize = 8_192;
pub const MAX_TYPE_TEXT_BYTES: usize = 131_072;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BrowserRequest {
    pub protocol: String,
    pub request_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_generation: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deadline_unix_ms: Option<u64>,
    pub operation: BrowserOperation,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum BrowserOperation {
    Health,
    SessionCreate {
        profile: ProfileSpec,
        ui_mode: UiMode,
    },
    SessionSnapshot,
    SessionClose,
    PageNavigate {
        target: NavigationTarget,
        expected_document_generation: u64,
    },
    PageObserve {
        fields: Vec<ObservationField>,
    },
    PageAct {
        target: ElementReference,
        action: PageAction,
    },
    PageWait {
        condition: WaitCondition,
        timeout_ms: u64,
    },
    PageExtract {
        schema_id: String,
    },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProfileSpec {
    pub profile_id: String,
    pub persistence: ProfilePersistence,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProfilePersistence {
    Ephemeral,
    Persistent,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UiMode {
    Headed,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum NavigationTarget {
    TrustedShell,
    TrustedApp { publisher: String, app_id: String },
    ExternalHttps { url: String },
    LocalHttpFixture { url: String },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObservationField {
    Role,
    Name,
    Text,
    Href,
    Bounds,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ElementReference {
    pub session_generation: u64,
    pub document_generation: u64,
    pub semantic_snapshot_revision: u64,
    pub frame_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub backend_node_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub accessible_name_sha256: Option<String>,
    pub structural_fingerprint: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum PageAction {
    Click,
    Type { text: String },
    Press { key: String },
    Scroll { delta_x: i64, delta_y: i64 },
    Select { value: String },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum WaitCondition {
    DocumentReady,
    UrlEquals { url: String },
    ElementPresent { target: ElementReference },
    TextPresent { text: String },
    NetworkIdle { quiet_window_ms: u64 },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EffectClass {
    Observation,
    LocalInteraction,
    PotentialExternalEffect,
}

impl BrowserOperation {
    pub const fn effect_class(&self) -> EffectClass {
        match self {
            Self::Health
            | Self::SessionSnapshot
            | Self::PageObserve { .. }
            | Self::PageWait { .. }
            | Self::PageExtract { .. } => EffectClass::Observation,
            Self::SessionCreate { .. }
            | Self::SessionClose
            | Self::PageAct {
                action: PageAction::Scroll { .. },
                ..
            } => EffectClass::LocalInteraction,
            Self::PageNavigate { .. } | Self::PageAct { .. } => {
                EffectClass::PotentialExternalEffect
            }
        }
    }

    pub const fn requires_session_binding(&self) -> bool {
        !matches!(self, Self::Health | Self::SessionCreate { .. })
    }
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
    pub retry: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<Map<String, Value>>,
}

impl BrowserWireError {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Result<Self, CodecError> {
        let code = code.into();
        let retry = retry_policy(&code)
            .ok_or_else(|| CodecError::UnknownErrorCode(code.clone()))?
            .to_owned();
        let error = Self {
            code,
            message: message.into(),
            retry,
            details: None,
        };
        error.validate()?;
        Ok(error)
    }

    pub fn validate(&self) -> Result<(), CodecError> {
        let expected = retry_policy(&self.code)
            .ok_or_else(|| CodecError::UnknownErrorCode(self.code.clone()))?;
        if self.retry != expected {
            return Err(CodecError::RetryPolicyMismatch {
                code: self.code.clone(),
                expected: expected.to_owned(),
                actual: self.retry.clone(),
            });
        }
        validate_text("error.message", &self.message, 1, 1_024)
    }
}

pub fn retry_policy(code: &str) -> Option<&'static str> {
    match code {
        "invalid_request" => Some("never"),
        "unsupported" => Some("after_upgrade"),
        "policy_denied" => Some("after_explicit_policy_change"),
        "stale_session" => Some("recreate_session"),
        "stale_document" | "stale_snapshot" => Some("observe_again"),
        "queue_full" => Some("bounded_backoff"),
        "human_control_active" => Some("after_human_release"),
        "ime_composition_active" => Some("after_ime_end"),
        "modal_blocked" => Some("after_modal_resolution"),
        "navigation_in_progress" => Some("after_navigation"),
        "capability_pending" => Some("after_capability_resolution"),
        "cancelled" | "deadline_exceeded" => Some("caller_decides"),
        "browser_crashed" => Some("after_recovery"),
        "indeterminate" => Some("never_automatic"),
        "internal" => Some("after_diagnosis"),
        _ => None,
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct DecodedRequest {
    pub value: BrowserRequest,
    pub domain_operation: domain::BrowserOperation,
    pub canonical_bytes: Vec<u8>,
    pub canonical_sha256: String,
    pub effect_class: EffectClass,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DecodedResponse {
    pub value: BrowserResponse,
    pub canonical_bytes: Vec<u8>,
    pub canonical_sha256: String,
}

pub fn encode_request(request: &BrowserRequest) -> Result<Vec<u8>, CodecError> {
    request.validate()?;
    request.to_domain_operation()?;
    canonical_bytes(request)
}

pub fn decode_request(encoded: &[u8]) -> Result<DecodedRequest, CodecError> {
    let raw = decode_unique_json(encoded)?;
    validate_request_raw_shape(&raw)?;
    let value: BrowserRequest = serde_json::from_value(raw)?;
    value.validate()?;
    let domain_operation = value.to_domain_operation()?;
    let canonical_bytes = canonical_bytes(&value)?;
    if encoded != canonical_bytes {
        return Err(CodecError::NonCanonicalEncoding);
    }
    Ok(DecodedRequest {
        effect_class: value.operation.effect_class(),
        domain_operation,
        canonical_sha256: sha256_hex(&canonical_bytes),
        canonical_bytes,
        value,
    })
}

pub fn encode_response(response: &BrowserResponse) -> Result<Vec<u8>, CodecError> {
    response.validate()?;
    canonical_bytes(response)
}

pub fn decode_response(encoded: &[u8]) -> Result<DecodedResponse, CodecError> {
    let raw = decode_unique_json(encoded)?;
    validate_response_raw_shape(&raw)?;
    let value: BrowserResponse = serde_json::from_value(raw)?;
    value.validate()?;
    let canonical_bytes = canonical_bytes(&value)?;
    if encoded != canonical_bytes {
        return Err(CodecError::NonCanonicalEncoding);
    }
    Ok(DecodedResponse {
        canonical_sha256: sha256_hex(&canonical_bytes),
        canonical_bytes,
        value,
    })
}

impl BrowserRequest {
    pub fn validate(&self) -> Result<(), CodecError> {
        if self.protocol != BROWSER_API_PROTOCOL {
            return Err(CodecError::ProtocolMismatch);
        }
        validate_identifier("request_id", &self.request_id, MAX_IDENTIFIER_BYTES)?;
        match (&self.session_id, self.session_generation) {
            (Some(session_id), Some(generation)) => {
                validate_identifier("session_id", session_id, MAX_IDENTIFIER_BYTES)?;
                if generation == 0 {
                    return Err(CodecError::InvalidSessionBinding);
                }
            }
            (None, None) => {}
            _ => return Err(CodecError::InvalidSessionBinding),
        }
        if self.operation.requires_session_binding() {
            if self.session_id.is_none() {
                return Err(CodecError::InvalidSessionBinding);
            }
        } else if self.session_id.is_some() {
            return Err(CodecError::InvalidSessionBinding);
        }
        self.operation.validate()
    }
}

impl BrowserRequest {
    pub fn to_domain_operation(&self) -> Result<domain::BrowserOperation, CodecError> {
        self.operation.to_domain()
    }
}

impl BrowserOperation {
    fn to_domain(&self) -> Result<domain::BrowserOperation, CodecError> {
        match self {
            Self::Health => Ok(domain::BrowserOperation::Health),
            Self::SessionCreate { profile, ui_mode } => {
                Ok(domain::BrowserOperation::SessionCreate {
                    profile: domain::ProfileSpec {
                        profile_id: BoundedId::<128>::parse(
                            "profile.profile_id",
                            profile.profile_id.clone(),
                        )
                        .map_err(CodecError::from_domain)?,
                        persistence: match profile.persistence {
                            ProfilePersistence::Ephemeral => domain::ProfilePersistence::Ephemeral,
                            ProfilePersistence::Persistent => {
                                domain::ProfilePersistence::Persistent
                            }
                        },
                    },
                    ui_mode: match ui_mode {
                        UiMode::Headed => domain::UiMode::Headed,
                    },
                })
            }
            Self::SessionSnapshot => Ok(domain::BrowserOperation::SessionSnapshot),
            Self::SessionClose => Ok(domain::BrowserOperation::SessionClose),
            Self::PageNavigate {
                target,
                expected_document_generation,
            } => Ok(domain::BrowserOperation::PageNavigate {
                target: target.to_domain()?,
                expected_document_generation: *expected_document_generation,
            }),
            Self::PageObserve { fields } => {
                let mut output = domain::ObservationFields {
                    role: false,
                    name: false,
                    text: false,
                    href: false,
                    bounds: false,
                };
                for field in fields {
                    match field {
                        ObservationField::Role => output.role = true,
                        ObservationField::Name => output.name = true,
                        ObservationField::Text => output.text = true,
                        ObservationField::Href => output.href = true,
                        ObservationField::Bounds => output.bounds = true,
                    }
                }
                Ok(domain::BrowserOperation::PageObserve { fields: output })
            }
            Self::PageAct { target, action } => Ok(domain::BrowserOperation::PageAct {
                target: target.to_domain()?,
                action: action.to_domain()?,
            }),
            Self::PageWait {
                condition,
                timeout_ms,
            } => Ok(domain::BrowserOperation::PageWait {
                condition: condition.to_domain()?,
                timeout_ms: *timeout_ms,
            }),
            Self::PageExtract { schema_id } => Ok(domain::BrowserOperation::PageExtract {
                schema_id: BoundedId::<128>::parse("schema_id", schema_id.clone())
                    .map_err(CodecError::from_domain)?,
            }),
        }
    }

    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::Health | Self::SessionSnapshot | Self::SessionClose => Ok(()),
            Self::SessionCreate {
                profile,
                ui_mode: _,
            } => validate_identifier("profile.profile_id", &profile.profile_id, 128),
            Self::PageNavigate {
                target,
                expected_document_generation,
            } => {
                if *expected_document_generation == 0 {
                    return Err(CodecError::InvalidRevision("expected_document_generation"));
                }
                target.validate()
            }
            Self::PageObserve { fields } => {
                if fields.is_empty() {
                    return Err(CodecError::InvalidCollection("fields"));
                }
                let unique: BTreeSet<_> = fields.iter().collect();
                if unique.len() != fields.len() {
                    return Err(CodecError::InvalidCollection("fields"));
                }
                Ok(())
            }
            Self::PageAct { target, action } => {
                target.validate()?;
                action.validate()
            }
            Self::PageWait {
                condition,
                timeout_ms,
            } => {
                if !(1..=300_000).contains(timeout_ms) {
                    return Err(CodecError::InvalidInteger("timeout_ms"));
                }
                condition.validate()
            }
            Self::PageExtract { schema_id } => validate_identifier("schema_id", schema_id, 128),
        }
    }
}

impl NavigationTarget {
    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::TrustedShell => Ok(()),
            Self::TrustedApp { publisher, app_id } => {
                validate_dns_label("publisher", publisher)?;
                validate_dns_label("app_id", app_id)
            }
            Self::ExternalHttps { url } => validate_url(url, UrlPolicy::ExternalHttps),
            Self::LocalHttpFixture { url } => validate_url(url, UrlPolicy::LocalHttpFixture),
        }
    }
}

impl NavigationTarget {
    fn to_domain(&self) -> Result<domain::NavigationTarget, CodecError> {
        match self {
            Self::TrustedShell => Ok(domain::NavigationTarget::TrustedShell),
            Self::TrustedApp { publisher, app_id } => Ok(domain::NavigationTarget::TrustedApp(
                domain::TrustedAppIdentity::new(
                    DnsLabel::parse(publisher.clone()).map_err(CodecError::from_domain)?,
                    DnsLabel::parse(app_id.clone()).map_err(CodecError::from_domain)?,
                ),
            )),
            Self::ExternalHttps { url } => Ok(domain::NavigationTarget::ExternalHttps(url.clone())),
            Self::LocalHttpFixture { url } => {
                Ok(domain::NavigationTarget::LocalHttpFixture(url.clone()))
            }
        }
    }
}

impl ElementReference {
    fn to_domain(&self) -> Result<domain::ElementRef, CodecError> {
        Ok(domain::ElementRef {
            session_generation: self.session_generation,
            document_generation: self.document_generation,
            semantic_snapshot_revision: self.semantic_snapshot_revision,
            frame_id: BoundedId::<64>::parse("frame_id", self.frame_id.clone())
                .map_err(CodecError::from_domain)?,
            backend_node_key: self
                .backend_node_key
                .clone()
                .map(|value| BoundedId::<128>::parse("backend_node_key", value))
                .transpose()
                .map_err(CodecError::from_domain)?,
            role: self.role.clone(),
            accessible_name_sha256: self
                .accessible_name_sha256
                .clone()
                .map(Sha256Hex::parse)
                .transpose()
                .map_err(CodecError::from_domain)?,
            structural_fingerprint: Sha256Hex::parse(self.structural_fingerprint.clone())
                .map_err(CodecError::from_domain)?,
        })
    }

    fn validate(&self) -> Result<(), CodecError> {
        if self.session_generation == 0 {
            return Err(CodecError::InvalidRevision("session_generation"));
        }
        if self.document_generation == 0 {
            return Err(CodecError::InvalidRevision("document_generation"));
        }
        if self.semantic_snapshot_revision == 0 {
            return Err(CodecError::InvalidRevision("semantic_snapshot_revision"));
        }
        validate_identifier("frame_id", &self.frame_id, 64)?;
        if let Some(value) = &self.backend_node_key {
            validate_identifier("backend_node_key", value, 128)?;
        }
        if let Some(value) = &self.role {
            validate_text("role", value, 1, 128)?;
        }
        if let Some(value) = &self.accessible_name_sha256 {
            validate_sha256("accessible_name_sha256", value)?;
        }
        validate_sha256("structural_fingerprint", &self.structural_fingerprint)
    }
}

impl PageAction {
    fn to_domain(&self) -> Result<domain::PageAction, CodecError> {
        match self {
            Self::Click => Ok(domain::PageAction::Click),
            Self::Type { text } => Ok(domain::PageAction::Type { text: text.clone() }),
            Self::Press { key } => Ok(domain::PageAction::Press { key: key.clone() }),
            Self::Scroll { delta_x, delta_y } => Ok(domain::PageAction::Scroll {
                delta_x: i32::try_from(*delta_x)
                    .map_err(|_| CodecError::InvalidInteger("scroll_delta"))?,
                delta_y: i32::try_from(*delta_y)
                    .map_err(|_| CodecError::InvalidInteger("scroll_delta"))?,
            }),
            Self::Select { value } => Ok(domain::PageAction::Select {
                value: value.clone(),
            }),
        }
    }

    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::Click => Ok(()),
            Self::Type { text } => validate_text("action.text", text, 0, MAX_TYPE_TEXT_BYTES),
            Self::Press { key } => validate_text("action.key", key, 1, 128),
            Self::Scroll { delta_x, delta_y } => {
                if !(-1_000_000..=1_000_000).contains(delta_x)
                    || !(-1_000_000..=1_000_000).contains(delta_y)
                {
                    return Err(CodecError::InvalidInteger("scroll_delta"));
                }
                Ok(())
            }
            Self::Select { value } => validate_text("action.value", value, 0, 65_536),
        }
    }
}

impl WaitCondition {
    fn to_domain(&self) -> Result<domain::WaitCondition, CodecError> {
        match self {
            Self::DocumentReady => Ok(domain::WaitCondition::DocumentReady),
            Self::UrlEquals { url } => Ok(domain::WaitCondition::UrlEquals(url.clone())),
            Self::ElementPresent { target } => {
                Ok(domain::WaitCondition::ElementPresent(target.to_domain()?))
            }
            Self::TextPresent { text } => Ok(domain::WaitCondition::TextPresent(text.clone())),
            Self::NetworkIdle { quiet_window_ms } => Ok(domain::WaitCondition::NetworkIdle {
                quiet_window_ms: *quiet_window_ms,
            }),
        }
    }

    fn validate(&self) -> Result<(), CodecError> {
        match self {
            Self::DocumentReady => Ok(()),
            Self::UrlEquals { url } => validate_text("condition.url", url, 1, MAX_URL_BYTES),
            Self::ElementPresent { target } => target.validate(),
            Self::TextPresent { text } => validate_text("condition.text", text, 0, 65_536),
            Self::NetworkIdle { quiet_window_ms } => {
                if !(1..=60_000).contains(quiet_window_ms) {
                    return Err(CodecError::InvalidInteger("quiet_window_ms"));
                }
                Ok(())
            }
        }
    }
}

impl BrowserResponse {
    pub fn success_for(request: &BrowserRequest, result: Map<String, Value>) -> Self {
        Self {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: request.request_id.clone(),
            session_id: request.session_id.clone(),
            session_generation: request.session_generation,
            ok: true,
            result: Some(Value::Object(result)),
            error: None,
        }
    }

    pub fn failure_for(request: &BrowserRequest, error: BrowserWireError) -> Self {
        Self {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: request.request_id.clone(),
            session_id: request.session_id.clone(),
            session_generation: request.session_generation,
            ok: false,
            result: None,
            error: Some(error),
        }
    }

    pub fn validate(&self) -> Result<(), CodecError> {
        if self.protocol != BROWSER_API_PROTOCOL {
            return Err(CodecError::ProtocolMismatch);
        }
        validate_identifier("request_id", &self.request_id, MAX_IDENTIFIER_BYTES)?;
        match (&self.session_id, self.session_generation) {
            (Some(id), Some(generation)) if generation > 0 => {
                validate_identifier("session_id", id, MAX_IDENTIFIER_BYTES)?;
            }
            (None, None) => {}
            _ => return Err(CodecError::InvalidSessionBinding),
        }
        match (self.ok, &self.result, &self.error) {
            (true, Some(Value::Object(_)), None) => Ok(()),
            (false, None, Some(error)) => error.validate(),
            _ => Err(CodecError::InvalidResponseShape),
        }
    }
}

#[derive(Debug, Clone, Copy)]
enum UrlPolicy {
    ExternalHttps,
    LocalHttpFixture,
}

fn validate_url(url: &str, policy: UrlPolicy) -> Result<(), CodecError> {
    validate_text("url", url, 1, MAX_URL_BYTES)?;
    if url
        .chars()
        .any(|ch| ch.is_whitespace() || ch <= '\u{1f}' || ch == '\u{7f}')
    {
        return Err(CodecError::InvalidUrl);
    }
    let (scheme, remainder) = url.split_once("://").ok_or(CodecError::InvalidUrl)?;
    let authority = remainder.split(['/', '?', '#']).next().unwrap_or_default();
    if authority.is_empty() || authority.contains('@') {
        return Err(CodecError::InvalidUrl);
    }
    let (host, port) = split_authority(authority)?;
    if port == Some(0) {
        return Err(CodecError::InvalidUrl);
    }
    match policy {
        UrlPolicy::ExternalHttps if scheme == "https" && validate_external_host(host) => Ok(()),
        UrlPolicy::LocalHttpFixture
            if scheme == "http" && matches!(host, "127.0.0.1" | "localhost" | "::1") =>
        {
            Ok(())
        }
        _ => Err(CodecError::InvalidUrl),
    }
}

fn validate_external_host(host: &str) -> bool {
    if host.parse::<Ipv4Addr>().is_ok() || host.parse::<Ipv6Addr>().is_ok() {
        return true;
    }
    if host.is_empty()
        || host.len() > 253
        || host.starts_with('.')
        || host.ends_with('.')
        || !host.is_ascii()
    {
        return false;
    }
    host.split('.').all(|label| {
        let bytes = label.as_bytes();
        !bytes.is_empty()
            && bytes.len() <= 63
            && bytes
                .first()
                .is_some_and(|byte| byte.is_ascii_alphanumeric())
            && bytes
                .last()
                .is_some_and(|byte| byte.is_ascii_alphanumeric())
            && bytes
                .iter()
                .all(|byte| byte.is_ascii_alphanumeric() || *byte == b'-')
    })
}

fn split_authority(authority: &str) -> Result<(&str, Option<u16>), CodecError> {
    if let Some(rest) = authority.strip_prefix('[') {
        let end = rest.find(']').ok_or(CodecError::InvalidUrl)?;
        let host = &rest[..end];
        let trailing = &rest[end + 1..];
        let port = if trailing.is_empty() {
            None
        } else {
            Some(parse_port(
                trailing.strip_prefix(':').ok_or(CodecError::InvalidUrl)?,
            )?)
        };
        return Ok((host, port));
    }
    match authority.rsplit_once(':') {
        Some((host, port)) if !host.contains(':') => Ok((host, Some(parse_port(port)?))),
        _ => Ok((authority, None)),
    }
}

fn parse_port(value: &str) -> Result<u16, CodecError> {
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(CodecError::InvalidUrl);
    }
    value.parse().map_err(|_| CodecError::InvalidUrl)
}

fn validate_identifier(field: &'static str, value: &str, maximum: usize) -> Result<(), CodecError> {
    validate_text(field, value, 1, maximum)?;
    if value
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-'))
    {
        Ok(())
    } else {
        Err(CodecError::InvalidIdentifier(field))
    }
}

fn validate_dns_label(field: &'static str, value: &str) -> Result<(), CodecError> {
    validate_text(field, value, 1, 63)?;
    let bytes = value.as_bytes();
    if bytes
        .first()
        .is_some_and(|byte| byte.is_ascii_alphanumeric())
        && bytes
            .last()
            .is_some_and(|byte| byte.is_ascii_alphanumeric())
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'-')
    {
        Ok(())
    } else {
        Err(CodecError::InvalidIdentifier(field))
    }
}

fn validate_sha256(field: &'static str, value: &str) -> Result<(), CodecError> {
    if value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        Ok(())
    } else {
        Err(CodecError::InvalidDigest(field))
    }
}

fn validate_text(
    field: &'static str,
    value: &str,
    minimum: usize,
    maximum: usize,
) -> Result<(), CodecError> {
    let length = value.len();
    if length < minimum || length > maximum || value.contains('\0') {
        Err(CodecError::InvalidText {
            field,
            length,
            maximum,
        })
    } else {
        Ok(())
    }
}

fn sort_json(value: Value) -> Value {
    match value {
        Value::Array(values) => Value::Array(values.into_iter().map(sort_json).collect()),
        Value::Object(values) => {
            let mut entries: Vec<_> = values.into_iter().collect();
            entries.sort_by(|left, right| left.0.cmp(&right.0));
            let mut output = Map::new();
            for (key, value) in entries {
                output.insert(key, sort_json(value));
            }
            Value::Object(output)
        }
        scalar => scalar,
    }
}

fn canonical_bytes<T: Serialize>(value: &T) -> Result<Vec<u8>, CodecError> {
    let value = sort_json(serde_json::to_value(value)?);
    let mut total = 0;
    measure_json(&value, 0, &mut total)?;
    let encoded = serde_json::to_vec(&value)?;
    if encoded.len() > MAX_MESSAGE_BYTES {
        return Err(CodecError::MessageTooLarge {
            length: encoded.len(),
            maximum: MAX_MESSAGE_BYTES,
        });
    }
    Ok(encoded)
}

fn decode_unique_json(encoded: &[u8]) -> Result<Value, CodecError> {
    if encoded.is_empty() || encoded.len() > MAX_MESSAGE_BYTES {
        return Err(CodecError::MessageTooLarge {
            length: encoded.len(),
            maximum: MAX_MESSAGE_BYTES,
        });
    }
    if encoded.starts_with(&[0xef, 0xbb, 0xbf]) {
        return Err(CodecError::Utf8BomForbidden);
    }
    let mut deserializer = serde_json::Deserializer::from_slice(encoded);
    let UniqueJson(value) = UniqueJson::deserialize(&mut deserializer)?;
    deserializer.end()?;
    let mut total = 0;
    measure_json(&value, 0, &mut total)?;
    Ok(value)
}

fn measure_json(value: &Value, depth: usize, total: &mut usize) -> Result<(), CodecError> {
    if depth > MAX_JSON_DEPTH {
        return Err(CodecError::JsonDepthExceeded);
    }
    match value {
        Value::Array(values) => {
            *total = total.saturating_add(values.len());
            if *total > MAX_CONTAINER_ITEMS {
                return Err(CodecError::ContainerItemsExceeded);
            }
            for value in values {
                measure_json(value, depth + 1, total)?;
            }
        }
        Value::Object(values) => {
            *total = total.saturating_add(values.len());
            if *total > MAX_CONTAINER_ITEMS {
                return Err(CodecError::ContainerItemsExceeded);
            }
            for value in values.values() {
                measure_json(value, depth + 1, total)?;
            }
        }
        Value::Number(number) if number.as_i64().is_none() && number.as_u64().is_none() => {
            return Err(CodecError::FloatingPointForbidden);
        }
        _ => {}
    }
    Ok(())
}

fn exact_keys(value: &Value, required: &[&str], optional: &[&str]) -> Result<(), CodecError> {
    let object = value.as_object().ok_or(CodecError::ExpectedObject)?;
    for key in required {
        if !object.contains_key(*key) {
            return Err(CodecError::MissingMember((*key).to_owned()));
        }
    }
    for key in object.keys() {
        if !required.contains(&key.as_str()) && !optional.contains(&key.as_str()) {
            return Err(CodecError::UnknownMember(key.clone()));
        }
    }
    Ok(())
}

fn validate_request_raw_shape(value: &Value) -> Result<(), CodecError> {
    exact_keys(
        value,
        &["protocol", "request_id", "operation"],
        &["session_id", "session_generation", "deadline_unix_ms"],
    )?;
    let operation = value
        .get("operation")
        .ok_or_else(|| CodecError::MissingMember("operation".to_owned()))?;
    let kind = operation
        .get("type")
        .and_then(Value::as_str)
        .ok_or_else(|| CodecError::MissingMember("operation.type".to_owned()))?;
    match kind {
        "health" | "session_snapshot" | "session_close" => exact_keys(operation, &["type"], &[]),
        "session_create" => {
            exact_keys(operation, &["type", "profile", "ui_mode"], &[])?;
            validate_profile_raw(
                operation
                    .get("profile")
                    .ok_or_else(|| CodecError::MissingMember("operation.profile".to_owned()))?,
            )
        }
        "page_navigate" => {
            exact_keys(
                operation,
                &["type", "target", "expected_document_generation"],
                &[],
            )?;
            validate_navigation_target_raw(
                operation
                    .get("target")
                    .ok_or_else(|| CodecError::MissingMember("operation.target".to_owned()))?,
            )
        }
        "page_observe" => exact_keys(operation, &["type", "fields"], &[]),
        "page_act" => {
            exact_keys(operation, &["type", "target", "action"], &[])?;
            validate_element_reference_raw(
                operation
                    .get("target")
                    .ok_or_else(|| CodecError::MissingMember("operation.target".to_owned()))?,
            )?;
            validate_page_action_raw(
                operation
                    .get("action")
                    .ok_or_else(|| CodecError::MissingMember("operation.action".to_owned()))?,
            )
        }
        "page_wait" => {
            exact_keys(operation, &["type", "condition", "timeout_ms"], &[])?;
            validate_wait_condition_raw(
                operation
                    .get("condition")
                    .ok_or_else(|| CodecError::MissingMember("operation.condition".to_owned()))?,
            )
        }
        "page_extract" => exact_keys(operation, &["type", "schema_id"], &[]),
        _ => Err(CodecError::UnknownOperation(kind.to_owned())),
    }
}

fn validate_profile_raw(value: &Value) -> Result<(), CodecError> {
    exact_keys(value, &["profile_id", "persistence"], &[])
}

fn validate_navigation_target_raw(value: &Value) -> Result<(), CodecError> {
    let kind = value
        .get("type")
        .and_then(Value::as_str)
        .ok_or_else(|| CodecError::MissingMember("target.type".to_owned()))?;
    match kind {
        "trusted_shell" => exact_keys(value, &["type"], &[]),
        "trusted_app" => exact_keys(value, &["type", "publisher", "app_id"], &[]),
        "external_https" | "local_http_fixture" => exact_keys(value, &["type", "url"], &[]),
        _ => Err(CodecError::UnknownOperation(format!(
            "navigation_target:{kind}"
        ))),
    }
}

fn validate_element_reference_raw(value: &Value) -> Result<(), CodecError> {
    exact_keys(
        value,
        &[
            "session_generation",
            "document_generation",
            "semantic_snapshot_revision",
            "frame_id",
            "structural_fingerprint",
        ],
        &["backend_node_key", "role", "accessible_name_sha256"],
    )
}

fn validate_page_action_raw(value: &Value) -> Result<(), CodecError> {
    let kind = value
        .get("type")
        .and_then(Value::as_str)
        .ok_or_else(|| CodecError::MissingMember("action.type".to_owned()))?;
    match kind {
        "click" => exact_keys(value, &["type"], &[]),
        "type" => exact_keys(value, &["type", "text"], &[]),
        "press" => exact_keys(value, &["type", "key"], &[]),
        "scroll" => exact_keys(value, &["type", "delta_x", "delta_y"], &[]),
        "select" => exact_keys(value, &["type", "value"], &[]),
        _ => Err(CodecError::UnknownOperation(format!("page_action:{kind}"))),
    }
}

fn validate_wait_condition_raw(value: &Value) -> Result<(), CodecError> {
    let kind = value
        .get("type")
        .and_then(Value::as_str)
        .ok_or_else(|| CodecError::MissingMember("condition.type".to_owned()))?;
    match kind {
        "document_ready" => exact_keys(value, &["type"], &[]),
        "url_equals" => exact_keys(value, &["type", "url"], &[]),
        "element_present" => {
            exact_keys(value, &["type", "target"], &[])?;
            validate_element_reference_raw(
                value
                    .get("target")
                    .ok_or_else(|| CodecError::MissingMember("condition.target".to_owned()))?,
            )
        }
        "text_present" => exact_keys(value, &["type", "text"], &[]),
        "network_idle" => exact_keys(value, &["type", "quiet_window_ms"], &[]),
        _ => Err(CodecError::UnknownOperation(format!(
            "wait_condition:{kind}"
        ))),
    }
}

fn validate_response_raw_shape(value: &Value) -> Result<(), CodecError> {
    exact_keys(
        value,
        &["protocol", "request_id", "ok"],
        &["session_id", "session_generation", "result", "error"],
    )?;
    if let Some(error) = value.get("error") {
        exact_keys(error, &["code", "message", "retry"], &["details"])?;
    }
    Ok(())
}

fn sha256_hex(encoded: &[u8]) -> String {
    format!("{:x}", Sha256::digest(encoded))
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
        formatter.write_str("bounded JSON without duplicate object members")
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

    fn visit_f64<E>(self, _value: f64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Err(E::custom("floating-point numbers are forbidden"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(UniqueJson(Value::String(value.to_owned())))
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
        while let Some(UniqueJson(value)) = sequence.next_element::<UniqueJson>()? {
            output.push(value);
        }
        Ok(UniqueJson(Value::Array(output)))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut output = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if output.contains_key(&key) {
                return Err(de::Error::custom(format!("duplicate JSON member: {key}")));
            }
            let UniqueJson(value) = map.next_value::<UniqueJson>()?;
            output.insert(key, value);
        }
        Ok(UniqueJson(Value::Object(output)))
    }
}

#[derive(Debug)]
pub enum CodecError {
    Json(serde_json::Error),
    MessageTooLarge {
        length: usize,
        maximum: usize,
    },
    Utf8BomForbidden,
    NonCanonicalEncoding,
    JsonDepthExceeded,
    ContainerItemsExceeded,
    FloatingPointForbidden,
    ExpectedObject,
    MissingMember(String),
    UnknownMember(String),
    UnknownOperation(String),
    ProtocolMismatch,
    InvalidSessionBinding,
    InvalidRevision(&'static str),
    InvalidCollection(&'static str),
    InvalidInteger(&'static str),
    InvalidIdentifier(&'static str),
    InvalidDigest(&'static str),
    InvalidText {
        field: &'static str,
        length: usize,
        maximum: usize,
    },
    InvalidUrl,
    InvalidResponseShape,
    UnknownErrorCode(String),
    RetryPolicyMismatch {
        code: String,
        expected: String,
        actual: String,
    },
    DomainContract(String),
    SelfCheckInvariant,
}

impl CodecError {
    fn from_domain(error: ContractViolation) -> Self {
        Self::DomainContract(error.to_string())
    }
}

impl fmt::Display for CodecError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(error) => write!(formatter, "Browser API JSON failed: {error}"),
            Self::MessageTooLarge { length, maximum } => {
                write!(
                    formatter,
                    "Browser API message length {length} exceeds {maximum}"
                )
            }
            Self::Utf8BomForbidden => formatter.write_str("Browser API UTF-8 BOM is forbidden"),
            Self::NonCanonicalEncoding => formatter.write_str("Browser API JSON is not canonical"),
            Self::JsonDepthExceeded => formatter.write_str("Browser API JSON nesting is too deep"),
            Self::ContainerItemsExceeded => {
                formatter.write_str("Browser API JSON has too many items")
            }
            Self::FloatingPointForbidden => formatter.write_str("Browser API floats are forbidden"),
            Self::ExpectedObject => formatter.write_str("Browser API expected an object"),
            Self::MissingMember(member) => write!(formatter, "Browser API missing member {member}"),
            Self::UnknownMember(member) => write!(formatter, "Browser API unknown member {member}"),
            Self::UnknownOperation(operation) => {
                write!(formatter, "Browser API operation {operation} is unknown")
            }
            Self::ProtocolMismatch => formatter.write_str("Browser API protocol mismatch"),
            Self::InvalidSessionBinding => {
                formatter.write_str("Browser API session binding is invalid")
            }
            Self::InvalidRevision(field) => {
                write!(formatter, "Browser API revision {field} is invalid")
            }
            Self::InvalidCollection(field) => {
                write!(formatter, "Browser API collection {field} is invalid")
            }
            Self::InvalidInteger(field) => {
                write!(formatter, "Browser API integer {field} is invalid")
            }
            Self::InvalidIdentifier(field) => {
                write!(formatter, "Browser API identifier {field} is invalid")
            }
            Self::InvalidDigest(field) => {
                write!(formatter, "Browser API digest {field} is invalid")
            }
            Self::InvalidText {
                field,
                length,
                maximum,
            } => write!(
                formatter,
                "Browser API text {field} length {length} exceeds contract {maximum}"
            ),
            Self::InvalidUrl => formatter.write_str("Browser API navigation URL is invalid"),
            Self::InvalidResponseShape => {
                formatter.write_str("Browser API response shape is invalid")
            }
            Self::UnknownErrorCode(code) => {
                write!(formatter, "Browser API error code {code} is unknown")
            }
            Self::RetryPolicyMismatch {
                code,
                expected,
                actual,
            } => write!(
                formatter,
                "Browser API retry policy for {code} expected {expected}, received {actual}"
            ),
            Self::DomainContract(message) => {
                write!(formatter, "Browser API domain conversion failed: {message}")
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

impl From<serde_json::Error> for CodecError {
    fn from(error: serde_json::Error) -> Self {
        Self::Json(error)
    }
}

pub fn self_check() -> Result<(), CodecError> {
    let request = BrowserRequest {
        protocol: BROWSER_API_PROTOCOL.to_owned(),
        request_id: "codec:self-check:1".to_owned(),
        session_id: Some("session-self-check".to_owned()),
        session_generation: Some(3),
        deadline_unix_ms: None,
        operation: BrowserOperation::PageNavigate {
            target: NavigationTarget::ExternalHttps {
                url: "https://example.test/path".to_owned(),
            },
            expected_document_generation: 7,
        },
    };
    let encoded = encode_request(&request)?;
    let decoded = decode_request(&encoded)?;
    if decoded.value != request
        || !matches!(
            decoded.domain_operation,
            domain::BrowserOperation::PageNavigate { .. }
        )
        || decoded.effect_class != EffectClass::PotentialExternalEffect
        || decoded.canonical_sha256.len() != 64
    {
        return Err(CodecError::SelfCheckInvariant);
    }
    let mut result = Map::new();
    result.insert("accepted".to_owned(), Value::Bool(true));
    let response = BrowserResponse::success_for(&request, result);
    let encoded = encode_response(&response)?;
    if decode_response(&encoded)?.value != response {
        return Err(CodecError::SelfCheckInvariant);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn domain_operation_matches_effect(
        operation: &domain::BrowserOperation,
        effect: EffectClass,
    ) -> bool {
        match operation {
            domain::BrowserOperation::Health
            | domain::BrowserOperation::SessionSnapshot
            | domain::BrowserOperation::PageObserve { .. }
            | domain::BrowserOperation::PageWait { .. }
            | domain::BrowserOperation::PageExtract { .. } => effect == EffectClass::Observation,
            domain::BrowserOperation::SessionCreate { .. }
            | domain::BrowserOperation::SessionClose
            | domain::BrowserOperation::PageAct {
                action: domain::PageAction::Scroll { .. },
                ..
            } => effect == EffectClass::LocalInteraction,
            domain::BrowserOperation::PageNavigate { .. }
            | domain::BrowserOperation::PageAct { .. } => {
                effect == EffectClass::PotentialExternalEffect
            }
        }
    }

    fn navigate_request() -> BrowserRequest {
        BrowserRequest {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: "request:navigate:1".to_owned(),
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

    #[test]
    fn reference_golden_vectors_round_trip_byte_exactly() {
        for encoded in [
            include_bytes!("../../../contracts/golden/golden-health-1.wire.json").as_slice(),
            include_bytes!("../../../contracts/golden/golden-create-1.wire.json").as_slice(),
            include_bytes!("../../../contracts/golden/golden-navigate-1.wire.json").as_slice(),
            include_bytes!("../../../contracts/golden/golden-click-1.wire.json").as_slice(),
        ] {
            let decoded = decode_request(encoded).unwrap();
            assert_eq!(encode_request(&decoded.value).unwrap(), encoded);
            assert!(domain_operation_matches_effect(
                &decoded.domain_operation,
                decoded.effect_class,
            ));
        }
        for encoded in [
            include_bytes!("../../../contracts/golden/golden-response-ok-1.wire.json").as_slice(),
            include_bytes!("../../../contracts/golden/golden-response-error-1.wire.json")
                .as_slice(),
        ] {
            let decoded = decode_response(encoded).unwrap();
            assert_eq!(encode_response(&decoded.value).unwrap(), encoded);
        }
    }

    #[test]
    fn canonical_round_trip_and_effect_class_are_stable() {
        let request = navigate_request();
        let encoded = encode_request(&request).unwrap();
        let decoded = decode_request(&encoded).unwrap();
        assert_eq!(decoded.value, request);
        assert_eq!(decoded.canonical_bytes, encoded);
        assert_eq!(decoded.effect_class, EffectClass::PotentialExternalEffect);
    }

    #[test]
    fn duplicate_and_noncanonical_json_fail_before_dispatch() {
        let duplicate = br#"{"operation":{"type":"health"},"protocol":"trillionnium.desktop.browser-api.v1","protocol":"x","request_id":"x"}"#;
        assert!(decode_request(duplicate).is_err());
        let mut whitespace = encode_request(&BrowserRequest {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: "health:1".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        })
        .unwrap();
        whitespace.insert(0, b' ');
        assert!(matches!(
            decode_request(&whitespace),
            Err(CodecError::NonCanonicalEncoding)
        ));
    }

    #[test]
    fn session_binding_is_operation_specific_and_paired() {
        let mut request = navigate_request();
        request.session_generation = None;
        assert!(matches!(
            encode_request(&request),
            Err(CodecError::InvalidSessionBinding)
        ));
        let mut health = request;
        health.operation = BrowserOperation::Health;
        health.session_generation = Some(1);
        assert!(matches!(
            encode_request(&health),
            Err(CodecError::InvalidSessionBinding)
        ));
    }

    #[test]
    fn navigation_and_mutating_actions_are_never_read_only() {
        assert_eq!(
            navigate_request().operation.effect_class(),
            EffectClass::PotentialExternalEffect
        );
        let action = BrowserOperation::PageAct {
            target: ElementReference {
                session_generation: 3,
                document_generation: 7,
                semantic_snapshot_revision: 11,
                frame_id: "main".to_owned(),
                backend_node_key: None,
                role: Some("button".to_owned()),
                accessible_name_sha256: Some("a".repeat(64)),
                structural_fingerprint: "b".repeat(64),
            },
            action: PageAction::Click,
        };
        assert_eq!(action.effect_class(), EffectClass::PotentialExternalEffect);
    }

    #[test]
    fn url_policy_rejects_userinfo_private_fixture_and_non_https_external() {
        for target in [
            NavigationTarget::ExternalHttps {
                url: "http://example.test/".to_owned(),
            },
            NavigationTarget::ExternalHttps {
                url: "https://user@example.test/".to_owned(),
            },
            NavigationTarget::LocalHttpFixture {
                url: "http://192.168.1.2/".to_owned(),
            },
        ] {
            let mut request = navigate_request();
            request.operation = BrowserOperation::PageNavigate {
                target,
                expected_document_generation: 7,
            };
            assert!(matches!(
                encode_request(&request),
                Err(CodecError::InvalidUrl)
            ));
        }
    }

    #[test]
    fn response_binding_and_retry_policy_are_fixed_by_the_codec() {
        let request = navigate_request();
        let error = BrowserWireError::new("policy_denied", "effect gate closed").unwrap();
        let response = BrowserResponse::failure_for(&request, error);
        let encoded = encode_response(&response).unwrap();
        assert_eq!(decode_response(&encoded).unwrap().value, response);
        let mut forged = response;
        forged.error.as_mut().unwrap().retry = "caller_decides".to_owned();
        assert!(matches!(
            encode_response(&forged),
            Err(CodecError::RetryPolicyMismatch { .. })
        ));
    }

    #[test]
    fn canonical_encoding_sorts_nested_object_keys() {
        let request = health_request_fixture();
        let mut result = Map::new();
        result.insert("zeta".to_owned(), Value::Bool(true));
        result.insert("alpha".to_owned(), Value::Bool(false));
        let encoded = encode_response(&BrowserResponse::success_for(&request, result)).unwrap();
        let text = String::from_utf8(encoded).unwrap();
        assert!(text.find("\"alpha\"").unwrap() < text.find("\"zeta\"").unwrap());
    }

    #[test]
    fn unknown_nested_members_fail_before_typed_decode() {
        let encoded = br#"{"operation":{"extra":true,"type":"health"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"health:1"}"#;
        assert!(
            matches!(decode_request(encoded), Err(CodecError::UnknownMember(member)) if member == "extra")
        );
    }

    fn health_request_fixture() -> BrowserRequest {
        BrowserRequest {
            protocol: BROWSER_API_PROTOCOL.to_owned(),
            request_id: "health:fixture:1".to_owned(),
            session_id: None,
            session_generation: None,
            deadline_unix_ms: None,
            operation: BrowserOperation::Health,
        }
    }

    #[test]
    fn full_self_check_passes() {
        self_check().unwrap();
    }
}
