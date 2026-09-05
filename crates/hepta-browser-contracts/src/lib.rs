#![forbid(unsafe_code)]

//! Engine-neutral browser contract types for TrillionniumOS Desktop.
//! Wire serialization is defined by the JSON schemas under `/contracts` and
//! will be bound to the authenticated UDS carrier in D0C-2/D3.

use std::net::Ipv6Addr;
use std::str::FromStr;

use trillionnium_contract_core::{
    BoundedId, ContractViolation, DnsLabel, RefFreshness, RevisionClock, Sha256Hex,
    classify_reference,
};

pub const BROWSER_API_PROTOCOL: &str = "trillionnium.desktop.browser-api.v1";
pub const TRUSTED_SHELL_ORIGIN: &str = "https://shell.system.hepta.invalid";

// Keep the legacy, engine-neutral contract bound in lockstep with the
// canonical browser codec.  This type is used by a few callers before a wire
// request is built, so accepting a URL here that the codec/actor later reject
// would create a policy-validation gap.
const MAX_URL_BYTES: usize = 8_192;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UiMode {
    Headed,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProfileSpec {
    pub profile_id: BoundedId<128>,
    pub persistence: ProfilePersistence,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProfilePersistence {
    Ephemeral,
    Persistent,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrustedAppIdentity {
    pub publisher: DnsLabel,
    pub app_id: DnsLabel,
}

impl TrustedAppIdentity {
    pub fn new(publisher: DnsLabel, app_id: DnsLabel) -> Self {
        Self { publisher, app_id }
    }

    pub fn synthetic_origin(&self) -> String {
        format!(
            "https://{}.{}.apps.hepta.invalid",
            self.app_id.as_str(),
            self.publisher.as_str()
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NavigationTarget {
    TrustedShell,
    TrustedApp(TrustedAppIdentity),
    ExternalHttps(String),
    LocalHttpFixture(String),
}

impl NavigationTarget {
    pub fn validate(&self) -> Result<(), ContractViolation> {
        match self {
            Self::TrustedShell | Self::TrustedApp(_) => Ok(()),
            Self::ExternalHttps(url) if validate_navigation_url(url, UrlPolicy::ExternalHttps) => {
                Ok(())
            }
            Self::LocalHttpFixture(url)
                if validate_navigation_url(url, UrlPolicy::LoopbackHttp) =>
            {
                Ok(())
            }
            Self::ExternalHttps(_) | Self::LocalHttpFixture(_) => {
                Err(ContractViolation::InvalidCharacter { field: "url" })
            }
        }
    }

    pub fn origin_hint(&self) -> Option<String> {
        match self {
            Self::TrustedShell => Some(TRUSTED_SHELL_ORIGIN.to_string()),
            Self::TrustedApp(app) => Some(app.synthetic_origin()),
            Self::ExternalHttps(_) | Self::LocalHttpFixture(_) => None,
        }
    }
}

#[derive(Debug, Clone, Copy)]
enum UrlPolicy {
    ExternalHttps,
    LoopbackHttp,
}

/// Validate the URL authority using the same grammar as the canonical codec.
///
/// This intentionally does not resolve DNS or make a network request.  The
/// loopback policy is an exact host allow-list; in particular, a host prefix
/// such as `127.0.0.1.evil.example` is not a loopback address.  Userinfo and
/// backslashes are rejected before host parsing so authority smuggling cannot
/// reach a later browser parser with a different interpretation.
fn validate_navigation_url(value: &str, policy: UrlPolicy) -> bool {
    if value.is_empty()
        || value.len() > MAX_URL_BYTES
        || value.contains('\0')
        || value
            .chars()
            .any(|character| character <= '\u{001f}' || character == '\u{007f}')
    {
        return false;
    }

    let remainder = match policy {
        UrlPolicy::ExternalHttps => value.strip_prefix("https://"),
        UrlPolicy::LoopbackHttp => value.strip_prefix("http://"),
    };
    let Some(remainder) = remainder else {
        return false;
    };

    let authority_end = remainder.find(['/', '?', '#']).unwrap_or(remainder.len());
    let authority = &remainder[..authority_end];
    if authority.is_empty() || authority.contains(['@', '\\']) {
        return false;
    }

    let Some(host) = parse_navigation_authority_host(authority) else {
        return false;
    };
    !matches!(policy, UrlPolicy::LoopbackHttp)
        || matches!(host.as_str(), "localhost" | "127.0.0.1" | "::1")
}

fn parse_navigation_authority_host(authority: &str) -> Option<String> {
    if let Some(rest) = authority.strip_prefix('[') {
        let close = rest.find(']')?;
        let host = &rest[..close];
        Ipv6Addr::from_str(host).ok()?;
        validate_navigation_port_suffix(&rest[close + 1..])?;
        return Some(host.to_ascii_lowercase());
    }

    if authority.matches(':').count() > 1 {
        return None;
    }
    let (host, port) = match authority.rsplit_once(':') {
        Some((host, port)) => (host, Some(port)),
        None => (authority, None),
    };
    if host.is_empty()
        || host
            .chars()
            .any(|character| character.is_whitespace() || matches!(character, '/' | '?' | '#'))
    {
        return None;
    }
    if let Some(port) = port {
        validate_navigation_port(port)?;
    }
    Some(host.to_ascii_lowercase())
}

fn validate_navigation_port_suffix(suffix: &str) -> Option<()> {
    if suffix.is_empty() {
        Some(())
    } else {
        validate_navigation_port(suffix.strip_prefix(':')?)
    }
}

fn validate_navigation_port(port: &str) -> Option<()> {
    if port.is_empty() || port.len() > 5 || !port.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    port.parse::<u16>().ok().map(|_| ())
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ElementRef {
    pub session_generation: u64,
    pub document_generation: u64,
    pub semantic_snapshot_revision: u64,
    pub frame_id: BoundedId<64>,
    pub backend_node_key: Option<BoundedId<128>>,
    pub role: Option<String>,
    pub accessible_name_sha256: Option<Sha256Hex>,
    pub structural_fingerprint: Sha256Hex,
}

impl ElementRef {
    pub fn freshness(&self, current: RevisionClock) -> RefFreshness {
        classify_reference(
            current,
            self.session_generation,
            self.document_generation,
            self.semantic_snapshot_revision,
        )
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InteractionRisk {
    Observation,
    LocalOnly,
    PotentialExternalEffect,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PageAction {
    Click,
    Type { text: String },
    Press { key: String },
    Scroll { delta_x: i32, delta_y: i32 },
    Select { value: String },
}

impl PageAction {
    pub const fn interaction_risk(&self) -> InteractionRisk {
        match self {
            Self::Scroll { .. } => InteractionRisk::LocalOnly,
            Self::Click | Self::Type { .. } | Self::Press { .. } | Self::Select { .. } => {
                InteractionRisk::PotentialExternalEffect
            }
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ObservationFields {
    pub role: bool,
    pub name: bool,
    pub text: bool,
    pub href: bool,
    pub bounds: bool,
}

impl Default for ObservationFields {
    fn default() -> Self {
        Self {
            role: true,
            name: true,
            text: true,
            href: true,
            bounds: false,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WaitCondition {
    DocumentReady,
    UrlEquals(String),
    ElementPresent(ElementRef),
    TextPresent(String),
    NetworkIdle { quiet_window_ms: u64 },
}

#[derive(Debug, Clone, PartialEq, Eq)]
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
        fields: ObservationFields,
    },
    PageAct {
        target: ElementRef,
        action: PageAction,
    },
    PageWait {
        condition: WaitCondition,
        timeout_ms: u64,
    },
    PageExtract {
        schema_id: BoundedId<128>,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BrowserErrorCode {
    InvalidRequest,
    Unsupported,
    PolicyDenied,
    StaleSession,
    StaleDocument,
    StaleSnapshot,
    QueueFull,
    HumanControlActive,
    ImeCompositionActive,
    ModalBlocked,
    NavigationInProgress,
    CapabilityPending,
    Cancelled,
    DeadlineExceeded,
    BrowserCrashed,
    Indeterminate,
    Internal,
}

impl BrowserErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::InvalidRequest => "invalid_request",
            Self::Unsupported => "unsupported",
            Self::PolicyDenied => "policy_denied",
            Self::StaleSession => "stale_session",
            Self::StaleDocument => "stale_document",
            Self::StaleSnapshot => "stale_snapshot",
            Self::QueueFull => "queue_full",
            Self::HumanControlActive => "human_control_active",
            Self::ImeCompositionActive => "ime_composition_active",
            Self::ModalBlocked => "modal_blocked",
            Self::NavigationInProgress => "navigation_in_progress",
            Self::CapabilityPending => "capability_pending",
            Self::Cancelled => "cancelled",
            Self::DeadlineExceeded => "deadline_exceeded",
            Self::BrowserCrashed => "browser_crashed",
            Self::Indeterminate => "indeterminate",
            Self::Internal => "internal",
        }
    }
}

pub fn error_for_freshness(freshness: RefFreshness) -> Option<BrowserErrorCode> {
    match freshness {
        RefFreshness::Current => None,
        RefFreshness::StaleSession => Some(BrowserErrorCode::StaleSession),
        RefFreshness::StaleDocument => Some(BrowserErrorCode::StaleDocument),
        RefFreshness::StaleSnapshot => Some(BrowserErrorCode::StaleSnapshot),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use trillionnium_contract_core::{DnsLabel, RevisionClock, Sha256Hex};

    fn digest() -> Sha256Hex {
        Sha256Hex::parse("a".repeat(64)).expect("fixture digest")
    }

    #[test]
    fn trusted_apps_receive_distinct_tuple_origin_hosts() {
        let first = TrustedAppIdentity::new(
            DnsLabel::parse("foundation").unwrap(),
            DnsLabel::parse("workspace").unwrap(),
        );
        let second = TrustedAppIdentity::new(
            DnsLabel::parse("foundation").unwrap(),
            DnsLabel::parse("messages").unwrap(),
        );
        assert_ne!(first.synthetic_origin(), second.synthetic_origin());
        assert!(first.synthetic_origin().ends_with(".apps.hepta.invalid"));
    }

    #[test]
    fn external_navigation_requires_https_and_http_is_fixture_only() {
        assert!(
            NavigationTarget::ExternalHttps("https://example.com/".into())
                .validate()
                .is_ok()
        );
        assert!(
            NavigationTarget::ExternalHttps("http://example.com/".into())
                .validate()
                .is_err()
        );
        assert!(
            NavigationTarget::LocalHttpFixture("http://127.0.0.1:8080/".into())
                .validate()
                .is_ok()
        );
        assert!(
            NavigationTarget::LocalHttpFixture("http://192.168.1.10/".into())
                .validate()
                .is_err()
        );
    }

    #[test]
    fn navigation_urls_reject_authority_smuggling_and_invalid_ports() {
        for url in [
            "https://example.com",
            "https://EXAMPLE.COM/path",
            "https://example.com:443/path",
            "https://[::1]:443/",
        ] {
            assert!(
                NavigationTarget::ExternalHttps(url.into())
                    .validate()
                    .is_ok(),
                "expected valid external URL: {url}"
            );
        }
        for url in [
            "https://",
            "https://example.com:abc/",
            "https://example.com:",
            "https://example.com:65536/",
            "https://example.com:000000/",
            "https://example.com:443@evil.example/",
            "https://example.com\\@evil.example/",
            "https://exa mple.com/",
            "https://[::1",
            "https://[::1%25lo]/",
            "https://[v1.fe]/",
            "https://[::1]not-a-port/",
        ] {
            assert!(
                NavigationTarget::ExternalHttps(url.into())
                    .validate()
                    .is_err(),
                "unsafe external URL was accepted: {url}"
            );
        }

        for url in [
            "http://localhost",
            "http://LOCALHOST:8080/fixture",
            "http://127.0.0.1?ready=1",
            "http://[::1]:8080/fixture",
        ] {
            assert!(
                NavigationTarget::LocalHttpFixture(url.into())
                    .validate()
                    .is_ok(),
                "expected valid loopback URL: {url}"
            );
        }
        for url in [
            "http://127.0.0.1.evil.example/",
            "http://localhost.evil.example/",
            "http://127.0.0.1:80@evil.example/",
            "http://localhost@evil.example/",
            "http://localhost:abc/",
            "http://localhost:65536/",
            "http://localhost:80:90/",
            "http://localhost\\evil.example/",
            "http://[::1]not-a-port/",
            "http://[::1]:80@evil.example/",
            "http://::1/",
        ] {
            assert!(
                NavigationTarget::LocalHttpFixture(url.into())
                    .validate()
                    .is_err(),
                "unsafe loopback URL was accepted: {url}"
            );
        }
    }

    #[test]
    fn navigation_urls_enforce_bounded_text_and_control_character_rules() {
        let oversized = format!("https://example.com/{}", "a".repeat(MAX_URL_BYTES));
        assert!(
            NavigationTarget::ExternalHttps(oversized)
                .validate()
                .is_err()
        );
        for url in ["https://example.com/\u{0000}", "http://localhost/\u{001f}"] {
            assert!(
                match url.starts_with("https://") {
                    true => NavigationTarget::ExternalHttps(url.into()).validate(),
                    false => NavigationTarget::LocalHttpFixture(url.into()).validate(),
                }
                .is_err(),
                "control-containing URL was accepted: {url:?}"
            );
        }
    }

    #[test]
    fn mutating_ui_actions_are_not_mislabelled_read_only() {
        assert_eq!(
            PageAction::Click.interaction_risk(),
            InteractionRisk::PotentialExternalEffect
        );
        assert_eq!(
            PageAction::Type {
                text: "hello".into()
            }
            .interaction_risk(),
            InteractionRisk::PotentialExternalEffect
        );
        assert_eq!(
            PageAction::Scroll {
                delta_x: 0,
                delta_y: 10
            }
            .interaction_risk(),
            InteractionRisk::LocalOnly
        );
    }

    #[test]
    fn element_reference_uses_layered_revision_freshness() {
        let mut clock = RevisionClock::new();
        clock.on_semantic_snapshot();
        let element = ElementRef {
            session_generation: clock.session_generation,
            document_generation: clock.document_generation,
            semantic_snapshot_revision: clock.semantic_snapshot_revision,
            frame_id: BoundedId::parse("frame_id", "main").unwrap(),
            backend_node_key: None,
            role: Some("button".into()),
            accessible_name_sha256: Some(digest()),
            structural_fingerprint: digest(),
        };
        assert_eq!(element.freshness(clock), RefFreshness::Current);
        clock.on_dom_commit();
        assert_eq!(element.freshness(clock), RefFreshness::Current);
        clock.on_semantic_snapshot();
        assert_eq!(element.freshness(clock), RefFreshness::StaleSnapshot);
    }
}
