//! Compiled D4-D7 product-policy core.
//!
//! This module is deliberately side-effect free. It arbitrates human/Agent
//! ownership, trusted-application admission, capability use, controlled-egress
//! observations, effect reconciliation, and A/B update transitions. It does
//! not open files, create sockets, resolve DNS, execute an external effect,
//! switch a bootloader slot, access a signing key, or claim hardware/release
//! evidence.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};

pub const MAX_HUMAN_LEASE_MS: u64 = 30_000;
pub const MAX_PERMIT_LIFETIME_SECONDS: u64 = 3_600;
pub const MAX_DNS_ADDRESSES: usize = 16;
pub const MAX_REDIRECTS: u8 = 8;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyError {
    Invalid(&'static str),
    Denied(&'static str),
    Conflict(&'static str),
    Stale(&'static str),
}

impl PolicyError {
    pub const fn code(&self) -> &'static str {
        match self {
            Self::Invalid(code) | Self::Denied(code) | Self::Conflict(code) | Self::Stale(code) => {
                code
            }
        }
    }
}

impl fmt::Display for PolicyError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for PolicyError {}

fn valid_token(value: &str, maximum: usize) -> bool {
    !value.is_empty()
        && value.len() <= maximum
        && value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-' | b'/')
        })
}

fn validate_digest(value: &str) -> Result<(), PolicyError> {
    if value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        Ok(())
    } else {
        Err(PolicyError::Invalid("INVALID_SHA256"))
    }
}

fn increment(value: &mut u64) -> Result<(), PolicyError> {
    *value = value
        .checked_add(1)
        .ok_or(PolicyError::Invalid("REVISION_OVERFLOW"))?;
    Ok(())
}

// D4 ------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Revisions {
    pub session_generation: u64,
    pub document_generation: u64,
    pub semantic_snapshot_revision: u64,
    pub mutation_epoch: u64,
}

impl Default for Revisions {
    fn default() -> Self {
        Self {
            session_generation: 1,
            document_generation: 1,
            semantic_snapshot_revision: 1,
            mutation_epoch: 0,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TargetReference {
    pub node_id: String,
    pub scope_id: String,
    pub revisions: Revisions,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Actor {
    Human,
    Agent { epoch: u64 },
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct HumanLease {
    lease_id: String,
    expires_at_ms: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct DragState {
    actor: Actor,
    target: TargetReference,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CollaborationController {
    revisions: Revisions,
    human_lease: Option<HumanLease>,
    agent_epoch: u64,
    ime_owner: Option<Actor>,
    drag: Option<DragState>,
    modal_scope: Option<String>,
    clipboard_version: u64,
    clipboard_sha256: Option<String>,
    minimized: bool,
}

impl Default for CollaborationController {
    fn default() -> Self {
        Self {
            revisions: Revisions::default(),
            human_lease: None,
            agent_epoch: 1,
            ime_owner: None,
            drag: None,
            modal_scope: None,
            clipboard_version: 0,
            clipboard_sha256: None,
            minimized: false,
        }
    }
}

impl CollaborationController {
    pub fn revisions(&self) -> Revisions {
        self.revisions
    }

    pub fn current_agent_epoch(&self) -> u64 {
        self.agent_epoch
    }

    pub fn clipboard_version(&self) -> u64 {
        self.clipboard_version
    }

    pub fn is_minimized(&self) -> bool {
        self.minimized
    }

    pub fn reference(&self, node_id: &str, scope_id: &str) -> Result<TargetReference, PolicyError> {
        if !valid_token(node_id, 256) || !valid_token(scope_id, 256) {
            return Err(PolicyError::Invalid("INVALID_TARGET_REFERENCE"));
        }
        Ok(TargetReference {
            node_id: node_id.to_owned(),
            scope_id: scope_id.to_owned(),
            revisions: self.revisions,
        })
    }

    fn expire_human_lease(&mut self, now_ms: u64) {
        let expired = self
            .human_lease
            .as_ref()
            .is_some_and(|lease| now_ms >= lease.expires_at_ms);
        if expired {
            self.human_lease = None;
            if self.ime_owner == Some(Actor::Human) {
                self.ime_owner = None;
            }
        }
    }

    fn clear_interactions(&mut self) {
        self.human_lease = None;
        self.ime_owner = None;
        self.drag = None;
        self.modal_scope = None;
    }

    fn invalidate_agent(&mut self) -> Result<(), PolicyError> {
        increment(&mut self.agent_epoch)
    }

    pub fn gain_human_focus(
        &mut self,
        lease_id: &str,
        now_ms: u64,
        ttl_ms: u64,
    ) -> Result<(), PolicyError> {
        if !valid_token(lease_id, 128) || ttl_ms == 0 || ttl_ms > MAX_HUMAN_LEASE_MS {
            return Err(PolicyError::Invalid("INVALID_HUMAN_LEASE"));
        }
        let expires_at_ms = now_ms
            .checked_add(ttl_ms)
            .ok_or(PolicyError::Invalid("LEASE_TIME_OVERFLOW"))?;
        self.invalidate_agent()?;
        self.drag = None;
        if matches!(self.ime_owner.as_ref(), Some(Actor::Agent { .. })) {
            self.ime_owner = None;
        }
        self.human_lease = Some(HumanLease {
            lease_id: lease_id.to_owned(),
            expires_at_ms,
        });
        Ok(())
    }

    pub fn release_human_focus(&mut self, lease_id: &str) -> Result<(), PolicyError> {
        if self.human_lease.as_ref().map(|lease| lease.lease_id.as_str()) != Some(lease_id) {
            return Err(PolicyError::Denied("HUMAN_LEASE_MISMATCH"));
        }
        self.human_lease = None;
        if self.ime_owner == Some(Actor::Human) {
            self.ime_owner = None;
        }
        Ok(())
    }

    fn authorize_actor(&mut self, actor: &Actor, now_ms: u64) -> Result<(), PolicyError> {
        self.expire_human_lease(now_ms);
        match actor {
            Actor::Human if self.human_lease.is_some() => Ok(()),
            Actor::Human => Err(PolicyError::Denied("HUMAN_LEASE_REQUIRED")),
            Actor::Agent { .. } if self.human_lease.is_some() => {
                Err(PolicyError::Denied("HUMAN_LEASE_ACTIVE"))
            }
            Actor::Agent { epoch } if *epoch != self.agent_epoch => {
                Err(PolicyError::Stale("STALE_AGENT_EPOCH"))
            }
            Actor::Agent { .. } => Ok(()),
        }
    }

    pub fn begin_ime(&mut self, actor: Actor, now_ms: u64) -> Result<(), PolicyError> {
        self.authorize_actor(&actor, now_ms)?;
        match self.ime_owner.clone() {
            None => self.ime_owner = Some(actor),
            Some(Actor::Agent { .. }) if actor == Actor::Human => {
                self.ime_owner = Some(Actor::Human);
                self.drag = None;
                self.invalidate_agent()?;
            }
            Some(owner) if owner == actor => {
                return Err(PolicyError::Conflict("IME_ALREADY_OWNED"));
            }
            Some(_) => return Err(PolicyError::Conflict("IME_OWNED_BY_OTHER_ACTOR")),
        }
        Ok(())
    }

    pub fn end_ime(&mut self, actor: &Actor) -> Result<(), PolicyError> {
        if self.ime_owner.as_ref() != Some(actor) {
            return Err(PolicyError::Denied("IME_OWNER_MISMATCH"));
        }
        self.ime_owner = None;
        Ok(())
    }

    pub fn validate_target(
        &mut self,
        actor: &Actor,
        target: &TargetReference,
        now_ms: u64,
    ) -> Result<(), PolicyError> {
        self.authorize_actor(actor, now_ms)?;
        if target.revisions != self.revisions {
            return Err(PolicyError::Stale("STALE_TARGET_REFERENCE"));
        }
        if let Some(scope) = self.modal_scope.as_ref()
            && &target.scope_id != scope
        {
            return Err(PolicyError::Denied("TARGET_BEHIND_MODAL"));
        }
        Ok(())
    }

    pub fn start_drag(
        &mut self,
        actor: Actor,
        target: TargetReference,
        now_ms: u64,
    ) -> Result<(), PolicyError> {
        self.validate_target(&actor, &target, now_ms)?;
        if self.drag.is_some() {
            return Err(PolicyError::Conflict("DRAG_ALREADY_ACTIVE"));
        }
        self.drag = Some(DragState { actor, target });
        Ok(())
    }

    pub fn finish_drag(
        &mut self,
        actor: &Actor,
        target: &TargetReference,
        now_ms: u64,
    ) -> Result<(), PolicyError> {
        self.validate_target(actor, target, now_ms)?;
        if !matches!(self.drag.as_ref(), Some(drag) if &drag.actor == actor && &drag.target == target)
        {
            return Err(PolicyError::Denied("DRAG_BINDING_MISMATCH"));
        }
        self.drag = None;
        Ok(())
    }

    pub fn compare_and_swap_clipboard(
        &mut self,
        actor: &Actor,
        expected_version: u64,
        new_sha256: &str,
        now_ms: u64,
    ) -> Result<u64, PolicyError> {
        self.authorize_actor(actor, now_ms)?;
        validate_digest(new_sha256)?;
        if expected_version != self.clipboard_version {
            return Err(PolicyError::Conflict("CLIPBOARD_VERSION_CONFLICT"));
        }
        increment(&mut self.clipboard_version)?;
        self.clipboard_sha256 = Some(new_sha256.to_owned());
        Ok(self.clipboard_version)
    }

    pub fn open_modal(&mut self, scope_id: &str) -> Result<(), PolicyError> {
        if !valid_token(scope_id, 256) {
            return Err(PolicyError::Invalid("INVALID_MODAL_SCOPE"));
        }
        if self.modal_scope.is_some() {
            return Err(PolicyError::Conflict("MODAL_ALREADY_ACTIVE"));
        }
        self.modal_scope = Some(scope_id.to_owned());
        self.drag = None;
        Ok(())
    }

    pub fn navigation_committed(&mut self) -> Result<(), PolicyError> {
        increment(&mut self.revisions.document_generation)?;
        increment(&mut self.revisions.semantic_snapshot_revision)?;
        increment(&mut self.revisions.mutation_epoch)?;
        self.invalidate_agent()?;
        self.clear_interactions();
        Ok(())
    }

    pub fn crash_recovered(&mut self) -> Result<(), PolicyError> {
        increment(&mut self.revisions.session_generation)?;
        self.navigation_committed()
    }

    pub fn minimize(&mut self) {
        self.minimized = true;
        self.drag = None;
    }

    pub fn restore(&mut self) {
        self.minimized = false;
    }
}

// D5 ------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SignatureEvidence {
    verifier_id: String,
    key_sha256: String,
}

impl SignatureEvidence {
    pub fn from_external_verifier(
        verifier_id: &str,
        key_sha256: &str,
    ) -> Result<Self, PolicyError> {
        if !valid_token(verifier_id, 128) {
            return Err(PolicyError::Invalid("INVALID_VERIFIER_ID"));
        }
        validate_digest(key_sha256)?;
        Ok(Self {
            verifier_id: verifier_id.to_owned(),
            key_sha256: key_sha256.to_owned(),
        })
    }

    fn validate(&self) -> Result<(), PolicyError> {
        if !valid_token(&self.verifier_id, 128) {
            return Err(PolicyError::Invalid("INVALID_VERIFIER_ID"));
        }
        validate_digest(&self.key_sha256)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ClosedCsp {
    pub default_none: bool,
    pub script_self: bool,
    pub style_self: bool,
    pub connect_none: bool,
    pub object_none: bool,
    pub frame_none: bool,
    pub base_none: bool,
    pub form_none: bool,
    pub unsafe_source: bool,
    pub external_origin: bool,
}

impl ClosedCsp {
    pub const fn strict() -> Self {
        Self {
            default_none: true,
            script_self: true,
            style_self: true,
            connect_none: true,
            object_none: true,
            frame_none: true,
            base_none: true,
            form_none: true,
            unsafe_source: false,
            external_origin: false,
        }
    }

    const fn is_closed(self) -> bool {
        self.default_none
            && self.script_self
            && self.style_self
            && self.connect_none
            && self.object_none
            && self.frame_none
            && self.base_none
            && self.form_none
            && !self.unsafe_source
            && !self.external_origin
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrustedAppManifest {
    pub app_id: String,
    pub publisher_id: String,
    pub publisher_key_sha256: String,
    pub version: u64,
    pub origin: String,
    pub content_root_sha256: String,
    pub csp: ClosedCsp,
    pub service_worker_scope: Option<String>,
    pub revoked: bool,
    pub predecessor_rotation_verified: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrustedAppInstall {
    pub app_id: String,
    pub publisher_id: String,
    pub publisher_key_sha256: String,
    pub version: u64,
    pub origin: String,
    pub content_root_sha256: String,
    pub storage_partition: String,
}

#[derive(Debug, Default, Clone, Copy)]
pub struct TrustedAppPolicy;

impl TrustedAppPolicy {
    pub fn derived_origin(app_id: &str) -> Result<String, PolicyError> {
        let bytes = app_id.as_bytes();
        let edge_valid = |byte: u8| byte.is_ascii_lowercase() || byte.is_ascii_digit();
        let valid = !bytes.is_empty()
            && bytes.len() <= 128
            && edge_valid(bytes[0])
            && edge_valid(bytes[bytes.len() - 1])
            && bytes.iter().all(|byte| {
                byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'-')
            })
            && !app_id.contains("..");
        if !valid {
            return Err(PolicyError::Invalid("INVALID_TRUSTED_APP_ID"));
        }
        Ok(format!("https://{app_id}.trusted.invalid/"))
    }

    pub fn admit(
        manifest: &TrustedAppManifest,
        signature: &SignatureEvidence,
        prior: Option<&TrustedAppInstall>,
    ) -> Result<TrustedAppInstall, PolicyError> {
        signature.validate()?;
        if !valid_token(&manifest.publisher_id, 128) || manifest.version == 0 {
            return Err(PolicyError::Invalid("INVALID_TRUSTED_APP_MANIFEST"));
        }
        validate_digest(&manifest.publisher_key_sha256)?;
        validate_digest(&manifest.content_root_sha256)?;
        if manifest.revoked {
            return Err(PolicyError::Denied("TRUSTED_APP_REVOKED"));
        }
        if signature.key_sha256 != manifest.publisher_key_sha256 {
            return Err(PolicyError::Denied("SIGNATURE_KEY_MISMATCH"));
        }
        let expected_origin = Self::derived_origin(&manifest.app_id)?;
        if manifest.origin != expected_origin {
            return Err(PolicyError::Denied("TRUSTED_APP_ORIGIN_MISMATCH"));
        }
        if !manifest.csp.is_closed() {
            return Err(PolicyError::Denied("TRUSTED_APP_CSP_NOT_CLOSED"));
        }
        if let Some(scope) = manifest.service_worker_scope.as_deref()
            && (!scope.starts_with("/app/")
                || scope.contains("..")
                || scope.contains('\\')
                || scope.contains('?')
                || scope.contains('#'))
        {
            return Err(PolicyError::Denied("SERVICE_WORKER_SCOPE_ESCAPE"));
        }
        if let Some(installed) = prior {
            if installed.app_id != manifest.app_id || installed.publisher_id != manifest.publisher_id {
                return Err(PolicyError::Denied("TRUSTED_APP_IDENTITY_MISMATCH"));
            }
            if manifest.version < installed.version {
                return Err(PolicyError::Denied("TRUSTED_APP_DOWNGRADE"));
            }
            if manifest.version == installed.version
                && manifest.content_root_sha256 != installed.content_root_sha256
            {
                return Err(PolicyError::Denied("SAME_VERSION_CONTENT_CHANGED"));
            }
            if manifest.publisher_key_sha256 != installed.publisher_key_sha256
                && !manifest.predecessor_rotation_verified
            {
                return Err(PolicyError::Denied("PUBLISHER_ROTATION_NOT_AUTHORIZED"));
            }
        }
        Ok(TrustedAppInstall {
            app_id: manifest.app_id.clone(),
            publisher_id: manifest.publisher_id.clone(),
            publisher_key_sha256: manifest.publisher_key_sha256.clone(),
            version: manifest.version,
            origin: expected_origin,
            content_root_sha256: manifest.content_root_sha256.clone(),
            storage_partition: format!("trusted-app:{}:{}", manifest.publisher_id, manifest.app_id),
        })
    }
}

// D6 ------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Audience {
    Network,
    File,
    Notification,
    Audio,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum NetworkContext {
    TopLevel,
    Iframe,
    Worker,
    ServiceWorker,
    Prefetch,
    WebSocket,
    Download,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CapabilityPermit {
    pub permit_id: String,
    pub subject: String,
    pub audience: Audience,
    pub resource_id: String,
    pub action: String,
    pub not_before_epoch: u64,
    pub expires_at_epoch: u64,
    pub nonce: String,
    pub maximum_uses: u32,
    pub revoked: bool,
    pub signature: SignatureEvidence,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetworkResource {
    pub resource_id: String,
    pub allowed_origins: BTreeSet<String>,
    pub allowed_contexts: BTreeSet<NetworkContext>,
    pub proxy_id: String,
    pub maximum_redirects: u8,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetworkRequest {
    pub subject: String,
    pub origin: String,
    pub action: String,
    pub context: NetworkContext,
    pub resolved_addresses: Vec<IpAddr>,
    pub connected_peer: IpAddr,
    pub proxy_id: String,
    pub direct_connection: bool,
    pub tls_verified: bool,
    pub tls_intercepted: bool,
    pub redirect_count: u8,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetworkDecision {
    pub permit_id: String,
    pub origin: String,
    pub connected_peer: IpAddr,
    pub external_effect_executed: bool,
}

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct CapabilityLedger {
    uses: BTreeMap<String, u32>,
    permit_nonces: BTreeMap<String, String>,
}

impl CapabilityLedger {
    pub fn uses(&self, permit_id: &str) -> u32 {
        self.uses.get(permit_id).copied().unwrap_or(0)
    }

    pub fn authorize_network(
        &mut self,
        permit: &CapabilityPermit,
        resource: &NetworkResource,
        request: &NetworkRequest,
        now_epoch: u64,
    ) -> Result<NetworkDecision, PolicyError> {
        permit.signature.validate()?;
        if !valid_token(&permit.permit_id, 128)
            || !valid_token(&permit.subject, 256)
            || !valid_token(&permit.resource_id, 256)
            || !valid_token(&permit.action, 128)
            || !valid_token(&permit.nonce, 128)
            || permit.maximum_uses == 0
        {
            return Err(PolicyError::Invalid("INVALID_CAPABILITY_PERMIT"));
        }
        if permit.revoked {
            return Err(PolicyError::Denied("PERMIT_REVOKED"));
        }
        if permit.audience != Audience::Network {
            return Err(PolicyError::Denied("AUDIENCE_MISMATCH"));
        }
        if request.subject != permit.subject {
            return Err(PolicyError::Denied("SUBJECT_MISMATCH"));
        }
        if request.action != permit.action {
            return Err(PolicyError::Denied("ACTION_NOT_AUTHORIZED"));
        }
        if resource.resource_id != permit.resource_id {
            return Err(PolicyError::Denied("RESOURCE_MISMATCH"));
        }
        if permit.expires_at_epoch < permit.not_before_epoch
            || permit.expires_at_epoch - permit.not_before_epoch > MAX_PERMIT_LIFETIME_SECONDS
        {
            return Err(PolicyError::Invalid("PERMIT_TIME_RANGE_INVALID"));
        }
        if now_epoch < permit.not_before_epoch {
            return Err(PolicyError::Denied("PERMIT_NOT_YET_VALID"));
        }
        if now_epoch > permit.expires_at_epoch {
            return Err(PolicyError::Denied("PERMIT_EXPIRED"));
        }
        if let Some(existing_nonce) = self.permit_nonces.get(&permit.permit_id)
            && existing_nonce != &permit.nonce
        {
            return Err(PolicyError::Denied("PERMIT_ID_NONCE_CHANGED"));
        }
        if self.uses(&permit.permit_id) >= permit.maximum_uses {
            return Err(PolicyError::Denied("PERMIT_REPLAY_LIMIT_REACHED"));
        }
        if !resource.allowed_origins.contains(&request.origin)
            || !canonical_https_origin(&request.origin)
        {
            return Err(PolicyError::Denied("NETWORK_ORIGIN_NOT_AUTHORIZED"));
        }
        if !resource.allowed_contexts.contains(&request.context) {
            return Err(PolicyError::Denied("NETWORK_CONTEXT_NOT_AUTHORIZED"));
        }
        if resource.maximum_redirects > MAX_REDIRECTS
            || request.redirect_count > resource.maximum_redirects
        {
            return Err(PolicyError::Denied("REDIRECT_BUDGET_EXCEEDED"));
        }
        if request.direct_connection
            || request.proxy_id != resource.proxy_id
            || !request.tls_verified
            || request.tls_intercepted
        {
            return Err(PolicyError::Denied("CONTROLLED_EGRESS_REQUIRED"));
        }
        if request.resolved_addresses.is_empty()
            || request.resolved_addresses.len() > MAX_DNS_ADDRESSES
        {
            return Err(PolicyError::Invalid("DNS_ADDRESS_COUNT_INVALID"));
        }
        let mut approved = BTreeSet::new();
        for address in &request.resolved_addresses {
            if !is_global_unicast(*address) {
                return Err(PolicyError::Denied("NON_GLOBAL_IP_FORBIDDEN"));
            }
            if !approved.insert(*address) {
                return Err(PolicyError::Invalid("DUPLICATE_DNS_ADDRESS"));
            }
        }
        if !is_global_unicast(request.connected_peer) {
            return Err(PolicyError::Denied("NON_GLOBAL_IP_FORBIDDEN"));
        }
        if !approved.contains(&request.connected_peer) {
            return Err(PolicyError::Denied("CONNECTED_PEER_NOT_IN_DNS_SET"));
        }
        self.permit_nonces
            .entry(permit.permit_id.clone())
            .or_insert_with(|| permit.nonce.clone());
        let uses = self.uses.entry(permit.permit_id.clone()).or_default();
        *uses = uses
            .checked_add(1)
            .ok_or(PolicyError::Invalid("PERMIT_USE_OVERFLOW"))?;
        Ok(NetworkDecision {
            permit_id: permit.permit_id.clone(),
            origin: request.origin.clone(),
            connected_peer: request.connected_peer,
            external_effect_executed: false,
        })
    }
}

fn canonical_https_origin(value: &str) -> bool {
    let Some(authority) = value.strip_prefix("https://") else {
        return false;
    };
    !authority.is_empty()
        && !authority.contains('/')
        && !authority.contains('@')
        && !authority.contains('\\')
        && !authority.contains('#')
        && !authority.contains('?')
        && !authority.bytes().any(|byte| byte <= 0x20 || byte == 0x7f)
}

fn is_global_unicast(address: IpAddr) -> bool {
    match address {
        IpAddr::V4(value) => is_global_ipv4(value),
        IpAddr::V6(value) => is_global_ipv6(value),
    }
}

fn is_global_ipv4(address: Ipv4Addr) -> bool {
    let octets = address.octets();
    if octets[0] == 0
        || octets[0] == 10
        || octets[0] == 127
        || (octets[0] == 169 && octets[1] == 254)
        || (octets[0] == 172 && (16..=31).contains(&octets[1]))
        || (octets[0] == 192 && octets[1] == 168)
        || (octets[0] == 100 && (64..=127).contains(&octets[1]))
        || (octets[0] == 198 && (octets[1] == 18 || octets[1] == 19))
        || octets[0] >= 224
    {
        return false;
    }
    !matches!(
        octets,
        [192, 0, 0, _]
            | [192, 0, 2, _]
            | [192, 88, 99, _]
            | [198, 51, 100, _]
            | [203, 0, 113, _]
    )
}

fn is_global_ipv6(address: Ipv6Addr) -> bool {
    let segments = address.segments();
    if address.is_unspecified()
        || address.is_loopback()
        || (segments[0] & 0xfe00) == 0xfc00
        || (segments[0] & 0xffc0) == 0xfe80
        || (segments[0] & 0xffc0) == 0xfec0
        || (segments[0] & 0xff00) == 0xff00
        || segments[0] == 0x2002
        || (segments[0] == 0x2001 && segments[1] == 0)
        || (segments[0] == 0x2001 && segments[1] == 0x0db8)
        || (segments[0] == 0x0100
            && segments[1] == 0
            && segments[2] == 0
            && segments[3] == 0)
    {
        return false;
    }
    !(segments[0] == 0
        && segments[1] == 0
        && segments[2] == 0
        && segments[3] == 0
        && segments[4] == 0
        && segments[5] == 0xffff)
}

// D7 ------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EffectState {
    Requested,
    Prepared,
    Dispatched,
    Applied,
    NotApplied,
    Indeterminate,
    Cancelled,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProviderObservation {
    Applied,
    NotApplied,
    Unknown,
}

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct EffectJournal {
    operations: BTreeMap<String, EffectState>,
}

impl EffectJournal {
    pub fn state(&self, operation_id: &str) -> Option<EffectState> {
        self.operations.get(operation_id).copied()
    }

    pub fn request(&mut self, operation_id: &str) -> Result<(), PolicyError> {
        if !valid_token(operation_id, 128) {
            return Err(PolicyError::Invalid("INVALID_EFFECT_OPERATION_ID"));
        }
        if self.operations.contains_key(operation_id) {
            return Err(PolicyError::Conflict("EFFECT_OPERATION_ALREADY_EXISTS"));
        }
        self.operations
            .insert(operation_id.to_owned(), EffectState::Requested);
        Ok(())
    }

    pub fn prepare(&mut self, operation_id: &str) -> Result<(), PolicyError> {
        self.transition(operation_id, EffectState::Requested, EffectState::Prepared)
    }

    pub fn mark_dispatched(&mut self, operation_id: &str) -> Result<(), PolicyError> {
        self.transition(operation_id, EffectState::Prepared, EffectState::Dispatched)
    }

    pub fn cancel_before_dispatch(&mut self, operation_id: &str) -> Result<(), PolicyError> {
        if !matches!(
            self.state(operation_id),
            Some(EffectState::Requested | EffectState::Prepared)
        ) {
            return Err(PolicyError::Denied("EFFECT_CANCEL_AFTER_DISPATCH_FORBIDDEN"));
        }
        self.operations
            .insert(operation_id.to_owned(), EffectState::Cancelled);
        Ok(())
    }

    pub fn reconcile(
        &mut self,
        operation_id: &str,
        observation: ProviderObservation,
    ) -> Result<EffectState, PolicyError> {
        if !matches!(
            self.state(operation_id),
            Some(EffectState::Dispatched | EffectState::Indeterminate)
        ) {
            return Err(PolicyError::Denied("EFFECT_RECONCILIATION_NOT_ALLOWED"));
        }
        let state = match observation {
            ProviderObservation::Applied => EffectState::Applied,
            ProviderObservation::NotApplied => EffectState::NotApplied,
            ProviderObservation::Unknown => EffectState::Indeterminate,
        };
        self.operations.insert(operation_id.to_owned(), state);
        Ok(state)
    }

    pub fn automatic_replay_allowed(&self, operation_id: &str) -> bool {
        matches!(
            self.state(operation_id),
            Some(EffectState::Requested | EffectState::Prepared)
        )
    }

    fn transition(
        &mut self,
        operation_id: &str,
        expected: EffectState,
        next: EffectState,
    ) -> Result<(), PolicyError> {
        if self.state(operation_id) != Some(expected) {
            return Err(PolicyError::Denied("EFFECT_STATE_TRANSITION_REJECTED"));
        }
        self.operations.insert(operation_id.to_owned(), next);
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UpdateSlot {
    A,
    B,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PendingUpdate {
    pub target: UpdateSlot,
    pub previous: UpdateSlot,
    pub version: u64,
    pub rollback_index: u64,
    pub image_sha256: String,
    pub activated: bool,
    pub boot_attempts: u8,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateController {
    active: UpdateSlot,
    healthy: UpdateSlot,
    current_version: u64,
    rollback_index: u64,
    maximum_boot_attempts: u8,
    pending: Option<PendingUpdate>,
}

impl UpdateController {
    pub fn new(
        active: UpdateSlot,
        current_version: u64,
        rollback_index: u64,
        maximum_boot_attempts: u8,
    ) -> Result<Self, PolicyError> {
        if current_version == 0 || maximum_boot_attempts == 0 {
            return Err(PolicyError::Invalid("INVALID_UPDATE_BASELINE"));
        }
        Ok(Self {
            active,
            healthy: active,
            current_version,
            rollback_index,
            maximum_boot_attempts,
            pending: None,
        })
    }

    pub fn active_slot(&self) -> UpdateSlot {
        self.active
    }

    pub fn healthy_slot(&self) -> UpdateSlot {
        self.healthy
    }

    pub fn rollback_index(&self) -> u64 {
        self.rollback_index
    }

    pub fn pending(&self) -> Option<&PendingUpdate> {
        self.pending.as_ref()
    }

    pub fn stage(
        &mut self,
        target: UpdateSlot,
        version: u64,
        rollback_index: u64,
        image_sha256: &str,
    ) -> Result<(), PolicyError> {
        validate_digest(image_sha256)?;
        if self.pending.is_some() {
            return Err(PolicyError::Conflict("UPDATE_ALREADY_PENDING"));
        }
        if target == self.active {
            return Err(PolicyError::Denied("ACTIVE_SLOT_WRITE_FORBIDDEN"));
        }
        if version <= self.current_version || rollback_index <= self.rollback_index {
            return Err(PolicyError::Denied("UPDATE_DOWNGRADE_FORBIDDEN"));
        }
        self.pending = Some(PendingUpdate {
            target,
            previous: self.active,
            version,
            rollback_index,
            image_sha256: image_sha256.to_owned(),
            activated: false,
            boot_attempts: 0,
        });
        Ok(())
    }

    pub fn activate_staged(&mut self) -> Result<UpdateSlot, PolicyError> {
        let pending = self
            .pending
            .as_mut()
            .ok_or(PolicyError::Denied("NO_STAGED_UPDATE"))?;
        if pending.activated {
            return Err(PolicyError::Conflict("UPDATE_ALREADY_ACTIVATED"));
        }
        pending.activated = true;
        self.active = pending.target;
        Ok(self.active)
    }

    pub fn record_boot_failure(&mut self) -> Result<UpdateSlot, PolicyError> {
        let (must_rollback, previous) = {
            let pending = self
                .pending
                .as_mut()
                .ok_or(PolicyError::Denied("NO_PENDING_BOOT"))?;
            if !pending.activated {
                return Err(PolicyError::Denied("UPDATE_NOT_ACTIVATED"));
            }
            pending.boot_attempts = pending
                .boot_attempts
                .checked_add(1)
                .ok_or(PolicyError::Invalid("BOOT_ATTEMPT_OVERFLOW"))?;
            (
                pending.boot_attempts >= self.maximum_boot_attempts,
                pending.previous,
            )
        };
        if must_rollback {
            self.active = previous;
            self.pending = None;
        }
        Ok(self.active)
    }

    pub fn confirm_healthy(&mut self) -> Result<(), PolicyError> {
        let pending = self
            .pending
            .take()
            .ok_or(PolicyError::Denied("NO_PENDING_BOOT"))?;
        if !pending.activated || self.active != pending.target {
            self.pending = Some(pending);
            return Err(PolicyError::Denied("UPDATE_NOT_ACTIVE"));
        }
        self.current_version = pending.version;
        self.rollback_index = pending.rollback_index;
        self.healthy = pending.target;
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProductPolicySelfCheck {
    pub checks_run: u32,
    pub external_effect_authority: bool,
    pub private_key_authority: bool,
    pub hardware_qualified: bool,
    pub release_ready: bool,
}

pub fn run_self_check() -> Result<ProductPolicySelfCheck, PolicyError> {
    let digest_a = "a".repeat(64);
    let digest_b = "b".repeat(64);

    let mut collaboration = CollaborationController::default();
    collaboration.gain_human_focus("human-self-check", 10, 100)?;
    collaboration.begin_ime(Actor::Human, 11)?;
    collaboration.compare_and_swap_clipboard(&Actor::Human, 0, &digest_a, 12)?;
    collaboration.end_ime(&Actor::Human)?;
    collaboration.release_human_focus("human-self-check")?;

    let signature = SignatureEvidence::from_external_verifier("self-check-verifier", &digest_a)?;
    let manifest = TrustedAppManifest {
        app_id: "calculator".to_owned(),
        publisher_id: "trillionnium".to_owned(),
        publisher_key_sha256: digest_a.clone(),
        version: 1,
        origin: "https://calculator.trusted.invalid/".to_owned(),
        content_root_sha256: digest_b.clone(),
        csp: ClosedCsp::strict(),
        service_worker_scope: Some("/app/".to_owned()),
        revoked: false,
        predecessor_rotation_verified: false,
    };
    TrustedAppPolicy::admit(&manifest, &signature, None)?;

    let mut origins = BTreeSet::new();
    origins.insert("https://example.com:443".to_owned());
    let mut contexts = BTreeSet::new();
    contexts.insert(NetworkContext::TopLevel);
    let resource = NetworkResource {
        resource_id: "network:example".to_owned(),
        allowed_origins: origins,
        allowed_contexts: contexts,
        proxy_id: "egress-proxy".to_owned(),
        maximum_redirects: 2,
    };
    let permit = CapabilityPermit {
        permit_id: "permit-self-check".to_owned(),
        subject: "taskflow:self-check".to_owned(),
        audience: Audience::Network,
        resource_id: resource.resource_id.clone(),
        action: "http_request".to_owned(),
        not_before_epoch: 90,
        expires_at_epoch: 120,
        nonce: "nonce-self-check".to_owned(),
        maximum_uses: 1,
        revoked: false,
        signature,
    };
    let peer = IpAddr::V4(Ipv4Addr::new(93, 184, 216, 34));
    let request = NetworkRequest {
        subject: permit.subject.clone(),
        origin: "https://example.com:443".to_owned(),
        action: permit.action.clone(),
        context: NetworkContext::TopLevel,
        resolved_addresses: vec![peer],
        connected_peer: peer,
        proxy_id: resource.proxy_id.clone(),
        direct_connection: false,
        tls_verified: true,
        tls_intercepted: false,
        redirect_count: 0,
    };
    let decision = CapabilityLedger::default().authorize_network(&permit, &resource, &request, 100)?;
    if decision.external_effect_executed {
        return Err(PolicyError::Invalid("SOURCE_POLICY_EXECUTED_NETWORK"));
    }

    let mut effects = EffectJournal::default();
    effects.request("effect-self-check")?;
    effects.prepare("effect-self-check")?;
    effects.mark_dispatched("effect-self-check")?;
    effects.reconcile("effect-self-check", ProviderObservation::Unknown)?;
    if effects.automatic_replay_allowed("effect-self-check") {
        return Err(PolicyError::Invalid("INDETERMINATE_EFFECT_REPLAY_ALLOWED"));
    }
    let mut update = UpdateController::new(UpdateSlot::A, 1, 1, 2)?;
    update.stage(UpdateSlot::B, 2, 2, &digest_b)?;
    update.activate_staged()?;
    update.confirm_healthy()?;

    Ok(ProductPolicySelfCheck {
        checks_run: 4,
        external_effect_authority: false,
        private_key_authority: false,
        hardware_qualified: false,
        release_ready: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn digest(character: char) -> String {
        character.to_string().repeat(64)
    }

    #[test]
    fn human_preemption_and_reference_invalidation_are_fail_closed() {
        let mut controller = CollaborationController::default();
        let old_epoch = controller.current_agent_epoch();
        let target = controller.reference("node-1", "root").expect("valid target");
        controller.gain_human_focus("lease-1", 100, 50).expect("valid lease");
        assert_eq!(
            controller
                .validate_target(&Actor::Agent { epoch: old_epoch }, &target, 101)
                .expect_err("human lease must block Agent")
                .code(),
            "HUMAN_LEASE_ACTIVE"
        );
        controller.release_human_focus("lease-1").expect("release");
        controller.navigation_committed().expect("navigation");
        let epoch = controller.current_agent_epoch();
        assert_eq!(
            controller
                .validate_target(&Actor::Agent { epoch }, &target, 200)
                .expect_err("old target must be stale")
                .code(),
            "STALE_TARGET_REFERENCE"
        );
    }

    #[test]
    fn clipboard_is_compare_and_swap_and_modal_is_topmost() {
        let mut controller = CollaborationController::default();
        let actor = Actor::Agent {
            epoch: controller.current_agent_epoch(),
        };
        controller
            .compare_and_swap_clipboard(&actor, 0, &digest('a'), 0)
            .expect("first write");
        assert_eq!(
            controller
                .compare_and_swap_clipboard(&actor, 0, &digest('b'), 0)
                .expect_err("stale version")
                .code(),
            "CLIPBOARD_VERSION_CONFLICT"
        );
        let background = controller.reference("node", "root").expect("target");
        controller.open_modal("dialog").expect("modal");
        assert_eq!(
            controller
                .validate_target(&actor, &background, 0)
                .expect_err("background blocked")
                .code(),
            "TARGET_BEHIND_MODAL"
        );
    }

    #[test]
    fn trusted_app_rejects_origin_csp_downgrade_and_content_repin() {
        let key = digest('a');
        let signature = SignatureEvidence::from_external_verifier("test-verifier", &key)
            .expect("signature evidence");
        let manifest = TrustedAppManifest {
            app_id: "notes".to_owned(),
            publisher_id: "publisher".to_owned(),
            publisher_key_sha256: key,
            version: 2,
            origin: "https://notes.trusted.invalid/".to_owned(),
            content_root_sha256: digest('b'),
            csp: ClosedCsp::strict(),
            service_worker_scope: None,
            revoked: false,
            predecessor_rotation_verified: false,
        };
        let installed = TrustedAppPolicy::admit(&manifest, &signature, None).expect("install");
        let mut changed = manifest.clone();
        changed.content_root_sha256 = digest('c');
        assert_eq!(
            TrustedAppPolicy::admit(&changed, &signature, Some(&installed))
                .expect_err("content repin")
                .code(),
            "SAME_VERSION_CONTENT_CHANGED"
        );
        changed.version = 1;
        assert_eq!(
            TrustedAppPolicy::admit(&changed, &signature, Some(&installed))
                .expect_err("downgrade")
                .code(),
            "TRUSTED_APP_DOWNGRADE"
        );
    }

    fn network_fixture() -> (
        CapabilityPermit,
        NetworkResource,
        NetworkRequest,
        CapabilityLedger,
    ) {
        let signature = SignatureEvidence::from_external_verifier("test-verifier", &digest('a'))
            .expect("signature evidence");
        let resource = NetworkResource {
            resource_id: "network:example".to_owned(),
            allowed_origins: BTreeSet::from(["https://example.com:443".to_owned()]),
            allowed_contexts: BTreeSet::from([NetworkContext::TopLevel]),
            proxy_id: "proxy-1".to_owned(),
            maximum_redirects: 2,
        };
        let permit = CapabilityPermit {
            permit_id: "permit-1".to_owned(),
            subject: "taskflow:one".to_owned(),
            audience: Audience::Network,
            resource_id: resource.resource_id.clone(),
            action: "http_request".to_owned(),
            not_before_epoch: 10,
            expires_at_epoch: 20,
            nonce: "nonce-1".to_owned(),
            maximum_uses: 1,
            revoked: false,
            signature,
        };
        let peer = IpAddr::V4(Ipv4Addr::new(93, 184, 216, 34));
        let request = NetworkRequest {
            subject: permit.subject.clone(),
            origin: "https://example.com:443".to_owned(),
            action: permit.action.clone(),
            context: NetworkContext::TopLevel,
            resolved_addresses: vec![peer],
            connected_peer: peer,
            proxy_id: resource.proxy_id.clone(),
            direct_connection: false,
            tls_verified: true,
            tls_intercepted: false,
            redirect_count: 0,
        };
        (permit, resource, request, CapabilityLedger::default())
    }

    #[test]
    fn capability_is_use_bound_and_peer_must_match_global_dns_set() {
        let (permit, resource, request, mut ledger) = network_fixture();
        let decision = ledger
            .authorize_network(&permit, &resource, &request, 15)
            .expect("valid observation");
        assert!(!decision.external_effect_executed);
        assert_eq!(
            ledger
                .authorize_network(&permit, &resource, &request, 15)
                .expect_err("replay")
                .code(),
            "PERMIT_REPLAY_LIMIT_REACHED"
        );

        let (permit, resource, mut request, mut ledger) = network_fixture();
        request.connected_peer = IpAddr::V4(Ipv4Addr::new(10, 0, 0, 1));
        assert_eq!(
            ledger
                .authorize_network(&permit, &resource, &request, 15)
                .expect_err("private peer")
                .code(),
            "NON_GLOBAL_IP_FORBIDDEN"
        );
    }

    #[test]
    fn dispatched_effect_is_never_automatically_replayed() {
        let mut journal = EffectJournal::default();
        journal.request("effect-1").expect("request");
        journal.prepare("effect-1").expect("prepare");
        journal.mark_dispatched("effect-1").expect("dispatch marker");
        assert!(!journal.automatic_replay_allowed("effect-1"));
        assert_eq!(
            journal
                .reconcile("effect-1", ProviderObservation::Unknown)
                .expect("reconcile"),
            EffectState::Indeterminate
        );
        assert!(!journal.automatic_replay_allowed("effect-1"));
    }

    #[test]
    fn update_stages_only_inactive_slot_and_advances_index_after_health() {
        let mut update = UpdateController::new(UpdateSlot::A, 1, 5, 2).expect("baseline");
        assert_eq!(
            update
                .stage(UpdateSlot::A, 2, 6, &digest('a'))
                .expect_err("active write")
                .code(),
            "ACTIVE_SLOT_WRITE_FORBIDDEN"
        );
        update.stage(UpdateSlot::B, 2, 6, &digest('a')).expect("stage");
        update.activate_staged().expect("activate");
        assert_eq!(update.rollback_index(), 5);
        update.confirm_healthy().expect("healthy");
        assert_eq!(update.rollback_index(), 6);
        assert_eq!(update.healthy_slot(), UpdateSlot::B);
    }

    #[test]
    fn repeated_boot_failure_rolls_back_without_advancing_index() {
        let mut update = UpdateController::new(UpdateSlot::A, 1, 1, 2).expect("baseline");
        update.stage(UpdateSlot::B, 2, 2, &digest('a')).expect("stage");
        update.activate_staged().expect("activate");
        assert_eq!(update.record_boot_failure().expect("failure one"), UpdateSlot::B);
        assert_eq!(update.record_boot_failure().expect("failure two"), UpdateSlot::A);
        assert!(update.pending().is_none());
        assert_eq!(update.rollback_index(), 1);
    }

    #[test]
    fn self_check_keeps_all_external_authority_closed() {
        let report = run_self_check().expect("self-check");
        assert_eq!(report.checks_run, 4);
        assert!(!report.external_effect_authority);
        assert!(!report.private_key_authority);
        assert!(!report.hardware_qualified);
        assert!(!report.release_ready);
    }
}
