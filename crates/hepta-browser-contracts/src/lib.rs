#![forbid(unsafe_code)]

//! Engine-neutral browser contract types for TrillionniumOS Desktop.
//! Wire serialization is defined by the JSON schemas under `/contracts` and
//! will be bound to the authenticated UDS carrier in D0C-2/D3.

use trillionnium_contract_core::{
    BoundedId, ContractViolation, DnsLabel, RefFreshness, RevisionClock, Sha256Hex,
    classify_reference,
};

pub const BROWSER_API_PROTOCOL: &str = "trillionnium.desktop.browser-api.v1";
pub const TRUSTED_SHELL_ORIGIN: &str = "https://shell.system.hepta.invalid";

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
            Self::ExternalHttps(url) if url.starts_with("https://") => Ok(()),
            Self::LocalHttpFixture(url)
                if url.starts_with("http://127.0.0.1/")
                    || url.starts_with("http://127.0.0.1:")
                    || url.starts_with("http://localhost/")
                    || url.starts_with("http://localhost:")
                    || url.starts_with("http://[::1]/")
                    || url.starts_with("http://[::1]:") =>
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
