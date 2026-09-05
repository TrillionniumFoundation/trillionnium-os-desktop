//! Compiled D4-D7 product-policy core.
//!
//! The core is deliberately side-effect free, but it no longer accepts
//! self-asserted authority. Human actions are bound to the exact live lease,
//! signed evidence is authenticated against a sealed verifier registry,
//! network observations are bound to the exact permit and request, effect
//! commands are immutable and journaled through a hash chain, and update
//! promotion requires signed stage, boot, and health evidence.
//!
//! This module still owns no socket, resolver, proxy, signing key, bootloader,
//! block device, or external-effect executor. Those integrations remain
//! separate gates and cannot be inferred from a source-model pass.

#[cfg(test)]
use ed25519_compact::{KeyPair, Seed};
use ed25519_compact::{PublicKey, Signature};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use std::str::FromStr;

pub const MAX_HUMAN_LEASE_MS: u64 = 30_000;
pub const MAX_PERMIT_LIFETIME_SECONDS: u64 = 3_600;
pub const MAX_EVIDENCE_LIFETIME_SECONDS: u64 = 3_600;
pub const MAX_OBSERVATION_AGE_SECONDS: u64 = 60;
pub const MAX_DNS_ADDRESSES: usize = 16;
pub const MAX_REDIRECTS: u8 = 8;
const EMPTY_JOURNAL_SHA256: &str =
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

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

#[derive(Default)]
struct Canonical(Vec<u8>);

impl Canonical {
    fn text(&mut self, label: &str, value: &str) {
        self.0
            .extend_from_slice(&(label.len() as u64).to_be_bytes());
        self.0.extend_from_slice(label.as_bytes());
        self.0
            .extend_from_slice(&(value.len() as u64).to_be_bytes());
        self.0.extend_from_slice(value.as_bytes());
    }

    fn u64(&mut self, label: &str, value: u64) {
        self.text(label, &value.to_string());
    }

    fn u32(&mut self, label: &str, value: u32) {
        self.text(label, &value.to_string());
    }

    fn u8(&mut self, label: &str, value: u8) {
        self.text(label, &value.to_string());
    }

    fn bool(&mut self, label: &str, value: bool) {
        self.text(label, if value { "true" } else { "false" });
    }

    fn digest(self) -> String {
        sha256_hex(&self.0)
    }
}

fn sha256_hex(value: &[u8]) -> String {
    let digest = Sha256::digest(value);
    let mut output = String::with_capacity(64);
    const HEX: &[u8; 16] = b"0123456789abcdef";
    for byte in digest {
        output.push(HEX[usize::from(byte >> 4)] as char);
        output.push(HEX[usize::from(byte & 0x0f)] as char);
    }
    output
}

fn valid_token(value: &str, maximum: usize) -> bool {
    !value.is_empty()
        && value.len() <= maximum
        && value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-' | b'/')
        })
}

fn validate_token(value: &str, maximum: usize, code: &'static str) -> Result<(), PolicyError> {
    if valid_token(value, maximum) {
        Ok(())
    } else {
        Err(PolicyError::Invalid(code))
    }
}

fn validate_digest(value: &str) -> Result<(), PolicyError> {
    if value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        && value.bytes().any(|byte| byte != b'0')
    {
        Ok(())
    } else {
        Err(PolicyError::Invalid("INVALID_SHA256"))
    }
}

fn checked_successor(value: u64, code: &'static str) -> Result<u64, PolicyError> {
    value.checked_add(1).ok_or(PolicyError::Invalid(code))
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
    Human { lease_id: String },
    Agent { epoch: u64 },
}

impl Actor {
    pub fn human(lease_id: &str) -> Result<Self, PolicyError> {
        validate_token(lease_id, 128, "INVALID_HUMAN_LEASE")?;
        Ok(Self::Human {
            lease_id: lease_id.to_owned(),
        })
    }
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

    pub fn active_human_lease_id(&self) -> Option<&str> {
        self.human_lease
            .as_ref()
            .map(|lease| lease.lease_id.as_str())
    }

    pub fn reference(&self, node_id: &str, scope_id: &str) -> Result<TargetReference, PolicyError> {
        validate_token(node_id, 256, "INVALID_TARGET_REFERENCE")?;
        validate_token(scope_id, 256, "INVALID_TARGET_REFERENCE")?;
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
            if matches!(self.ime_owner.as_ref(), Some(Actor::Human { .. })) {
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
        self.agent_epoch = checked_successor(self.agent_epoch, "AGENT_EPOCH_OVERFLOW")?;
        Ok(())
    }

    pub fn gain_human_focus(
        &mut self,
        lease_id: &str,
        now_ms: u64,
        ttl_ms: u64,
    ) -> Result<(), PolicyError> {
        validate_token(lease_id, 128, "INVALID_HUMAN_LEASE")?;
        if ttl_ms == 0 || ttl_ms > MAX_HUMAN_LEASE_MS {
            return Err(PolicyError::Invalid("INVALID_HUMAN_LEASE"));
        }
        let expires_at_ms = now_ms
            .checked_add(ttl_ms)
            .ok_or(PolicyError::Invalid("LEASE_TIME_OVERFLOW"))?;
        let next_agent_epoch = checked_successor(self.agent_epoch, "AGENT_EPOCH_OVERFLOW")?;
        self.agent_epoch = next_agent_epoch;
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
        if self.active_human_lease_id() != Some(lease_id) {
            return Err(PolicyError::Denied("HUMAN_LEASE_MISMATCH"));
        }
        self.human_lease = None;
        if matches!(
            self.ime_owner.as_ref(),
            Some(Actor::Human { lease_id: owner }) if owner == lease_id
        ) {
            self.ime_owner = None;
        }
        Ok(())
    }

    fn authorize_actor(&mut self, actor: &Actor, now_ms: u64) -> Result<(), PolicyError> {
        self.expire_human_lease(now_ms);
        match actor {
            Actor::Human { lease_id } => {
                validate_token(lease_id, 128, "INVALID_HUMAN_LEASE")?;
                match self.human_lease.as_ref() {
                    Some(lease) if lease.lease_id == *lease_id => Ok(()),
                    Some(_) => Err(PolicyError::Denied("HUMAN_LEASE_MISMATCH")),
                    None => Err(PolicyError::Denied("HUMAN_LEASE_REQUIRED")),
                }
            }
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
            Some(Actor::Agent { .. }) if matches!(&actor, Actor::Human { .. }) => {
                self.ime_owner = Some(actor);
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
        if !matches!(
            self.drag.as_ref(),
            Some(drag) if &drag.actor == actor && &drag.target == target
        ) {
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
        let next = checked_successor(self.clipboard_version, "CLIPBOARD_VERSION_OVERFLOW")?;
        self.clipboard_version = next;
        self.clipboard_sha256 = Some(new_sha256.to_owned());
        Ok(next)
    }

    pub fn open_modal(&mut self, scope_id: &str) -> Result<(), PolicyError> {
        validate_token(scope_id, 256, "INVALID_MODAL_SCOPE")?;
        if self.modal_scope.is_some() {
            return Err(PolicyError::Conflict("MODAL_ALREADY_ACTIVE"));
        }
        self.modal_scope = Some(scope_id.to_owned());
        self.drag = None;
        Ok(())
    }

    pub fn navigation_committed(&mut self) -> Result<(), PolicyError> {
        let document_generation = checked_successor(
            self.revisions.document_generation,
            "DOCUMENT_GENERATION_OVERFLOW",
        )?;
        let semantic_snapshot_revision = checked_successor(
            self.revisions.semantic_snapshot_revision,
            "SEMANTIC_REVISION_OVERFLOW",
        )?;
        let mutation_epoch =
            checked_successor(self.revisions.mutation_epoch, "MUTATION_EPOCH_OVERFLOW")?;
        let agent_epoch = checked_successor(self.agent_epoch, "AGENT_EPOCH_OVERFLOW")?;
        self.revisions.document_generation = document_generation;
        self.revisions.semantic_snapshot_revision = semantic_snapshot_revision;
        self.revisions.mutation_epoch = mutation_epoch;
        self.agent_epoch = agent_epoch;
        self.clear_interactions();
        Ok(())
    }

    pub fn crash_recovered(&mut self) -> Result<(), PolicyError> {
        let session_generation = checked_successor(
            self.revisions.session_generation,
            "SESSION_GENERATION_OVERFLOW",
        )?;
        let document_generation = checked_successor(
            self.revisions.document_generation,
            "DOCUMENT_GENERATION_OVERFLOW",
        )?;
        let semantic_snapshot_revision = checked_successor(
            self.revisions.semantic_snapshot_revision,
            "SEMANTIC_REVISION_OVERFLOW",
        )?;
        let mutation_epoch =
            checked_successor(self.revisions.mutation_epoch, "MUTATION_EPOCH_OVERFLOW")?;
        let agent_epoch = checked_successor(self.agent_epoch, "AGENT_EPOCH_OVERFLOW")?;
        self.revisions.session_generation = session_generation;
        self.revisions.document_generation = document_generation;
        self.revisions.semantic_snapshot_revision = semantic_snapshot_revision;
        self.revisions.mutation_epoch = mutation_epoch;
        self.agent_epoch = agent_epoch;
        self.clear_interactions();
        Ok(())
    }

    pub fn minimize(&mut self) {
        self.minimized = true;
        self.drag = None;
    }

    pub fn restore(&mut self) {
        self.minimized = false;
    }

    pub(crate) fn state_sha256(&self) -> String {
        let mut canonical = Canonical::default();
        canonical.u64("session", self.revisions.session_generation);
        canonical.u64("document", self.revisions.document_generation);
        canonical.u64("semantic", self.revisions.semantic_snapshot_revision);
        canonical.u64("mutation", self.revisions.mutation_epoch);
        canonical.u64("agent_epoch", self.agent_epoch);
        if let Some(lease) = self.human_lease.as_ref() {
            canonical.text("lease", &lease.lease_id);
            canonical.u64("lease_expires", lease.expires_at_ms);
        } else {
            canonical.text("lease", "");
        }
        canonical.text("ime", &format!("{:?}", self.ime_owner));
        canonical.text("drag", &format!("{:?}", self.drag));
        canonical.text("modal", self.modal_scope.as_deref().unwrap_or(""));
        canonical.u64("clipboard_version", self.clipboard_version);
        canonical.text(
            "clipboard_sha256",
            self.clipboard_sha256.as_deref().unwrap_or(""),
        );
        canonical.bool("minimized", self.minimized);
        canonical.digest()
    }
}

// Authenticated evidence -----------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum VerifierRole {
    Publisher,
    CapabilityIssuer,
    NetworkObserver,
    UpdateManifest,
    UpdateBoot,
    UpdateHealth,
}

impl VerifierRole {
    const fn code(self) -> &'static str {
        match self {
            Self::Publisher => "publisher",
            Self::CapabilityIssuer => "capability-issuer",
            Self::NetworkObserver => "network-observer",
            Self::UpdateManifest => "update-manifest",
            Self::UpdateBoot => "update-boot",
            Self::UpdateHealth => "update-health",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvidenceEnvelopeParts {
    pub verifier_id: String,
    pub key_id: String,
    pub role: VerifierRole,
    pub trust_generation: u64,
    pub revocation_generation: u64,
    pub subject: String,
    pub payload_sha256: String,
    pub not_before_epoch: u64,
    pub expires_at_epoch: u64,
    pub nonce: String,
    pub signature: [u8; 64],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvidenceEnvelope {
    parts: EvidenceEnvelopeParts,
}

impl EvidenceEnvelope {
    pub fn parse(parts: EvidenceEnvelopeParts) -> Result<Self, PolicyError> {
        validate_token(&parts.verifier_id, 128, "INVALID_VERIFIER_ID")?;
        validate_digest(&parts.key_id)?;
        validate_token(&parts.subject, 128, "INVALID_EVIDENCE_SUBJECT")?;
        validate_digest(&parts.payload_sha256)?;
        validate_token(&parts.nonce, 128, "INVALID_EVIDENCE_NONCE")?;
        if parts.signature.iter().all(|byte| *byte == 0) {
            return Err(PolicyError::Invalid("INVALID_EVIDENCE_SIGNATURE"));
        }
        if parts.trust_generation == 0
            || parts.revocation_generation == 0
            || parts.expires_at_epoch < parts.not_before_epoch
            || parts.expires_at_epoch - parts.not_before_epoch > MAX_EVIDENCE_LIFETIME_SECONDS
        {
            return Err(PolicyError::Invalid("INVALID_EVIDENCE_TIME_OR_GENERATION"));
        }
        Ok(Self { parts })
    }

    pub fn verifier_id(&self) -> &str {
        &self.parts.verifier_id
    }

    pub fn key_id(&self) -> &str {
        &self.parts.key_id
    }

    pub fn payload_sha256(&self) -> &str {
        &self.parts.payload_sha256
    }

    fn authenticated_bytes(&self) -> Vec<u8> {
        let mut canonical = Canonical::default();
        canonical.text("verifier_id", &self.parts.verifier_id);
        canonical.text("key_id", &self.parts.key_id);
        canonical.text("role", self.parts.role.code());
        canonical.u64("trust_generation", self.parts.trust_generation);
        canonical.u64("revocation_generation", self.parts.revocation_generation);
        canonical.text("subject", &self.parts.subject);
        canonical.text("payload_sha256", &self.parts.payload_sha256);
        canonical.u64("not_before_epoch", self.parts.not_before_epoch);
        canonical.u64("expires_at_epoch", self.parts.expires_at_epoch);
        canonical.text("nonce", &self.parts.nonce);
        canonical.0
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct TrustedVerifierRecord {
    key_id: String,
    role: VerifierRole,
    public_key: [u8; 32],
    revoked: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifierEnrollment {
    verifier_id: String,
    role: VerifierRole,
    public_key: [u8; 32],
    revoked: bool,
}

impl VerifierEnrollment {
    pub fn new(
        verifier_id: &str,
        role: VerifierRole,
        public_key: [u8; 32],
        revoked: bool,
    ) -> Result<Self, PolicyError> {
        validate_token(verifier_id, 128, "INVALID_VERIFIER_ID")?;
        PublicKey::from_slice(&public_key)
            .map_err(|_| PolicyError::Invalid("INVALID_VERIFIER_PUBLIC_KEY"))?;
        Ok(Self {
            verifier_id: verifier_id.to_owned(),
            role,
            public_key,
            revoked,
        })
    }

    pub fn verifier_id(&self) -> &str {
        &self.verifier_id
    }

    pub fn key_id(&self) -> String {
        sha256_hex(&self.public_key)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrustedVerifierRegistry {
    trust_generation: u64,
    revocation_generation: u64,
    records: BTreeMap<String, TrustedVerifierRecord>,
}

struct EvidenceExpectation<'a> {
    role: VerifierRole,
    subject: &'a str,
    payload_sha256: &'a str,
    key_id: Option<&'a str>,
    now_epoch: u64,
}

#[cfg(test)]
struct EvidenceIssue<'a> {
    verifier_id: &'a str,
    subject: &'a str,
    payload_sha256: &'a str,
    not_before_epoch: u64,
    expires_at_epoch: u64,
    nonce: &'a str,
}

impl TrustedVerifierRegistry {
    pub fn closed() -> Self {
        Self {
            trust_generation: 1,
            revocation_generation: 1,
            records: BTreeMap::new(),
        }
    }

    pub fn from_enrollments(
        trust_generation: u64,
        revocation_generation: u64,
        enrollments: Vec<VerifierEnrollment>,
    ) -> Result<Self, PolicyError> {
        if trust_generation == 0 || revocation_generation == 0 || enrollments.is_empty() {
            return Err(PolicyError::Invalid("INVALID_TRUST_REGISTRY"));
        }
        let mut records = BTreeMap::new();
        for enrollment in enrollments {
            let verifier_id = enrollment.verifier_id;
            let public_key = enrollment.public_key;
            PublicKey::from_slice(&public_key)
                .map_err(|_| PolicyError::Invalid("INVALID_VERIFIER_PUBLIC_KEY"))?;
            let record = TrustedVerifierRecord {
                key_id: sha256_hex(&public_key),
                role: enrollment.role,
                public_key,
                revoked: enrollment.revoked,
            };
            if records.insert(verifier_id, record).is_some() {
                return Err(PolicyError::Invalid("DUPLICATE_VERIFIER_ID"));
            }
        }
        Ok(Self {
            trust_generation,
            revocation_generation,
            records,
        })
    }

    pub fn key_id(&self, verifier_id: &str) -> Option<&str> {
        self.records
            .get(verifier_id)
            .map(|record| record.key_id.as_str())
    }

    fn verify(
        &self,
        envelope: &EvidenceEnvelope,
        expectation: EvidenceExpectation<'_>,
    ) -> Result<(), PolicyError> {
        validate_token(expectation.subject, 128, "INVALID_EVIDENCE_SUBJECT")?;
        validate_digest(expectation.payload_sha256)?;
        if envelope.parts.role != expectation.role
            || envelope.parts.subject != expectation.subject
            || envelope.parts.payload_sha256 != expectation.payload_sha256
        {
            return Err(PolicyError::Denied("EVIDENCE_BINDING_MISMATCH"));
        }
        if envelope.parts.trust_generation != self.trust_generation
            || envelope.parts.revocation_generation != self.revocation_generation
        {
            return Err(PolicyError::Stale("EVIDENCE_REGISTRY_GENERATION_STALE"));
        }
        if expectation.now_epoch < envelope.parts.not_before_epoch
            || expectation.now_epoch > envelope.parts.expires_at_epoch
        {
            return Err(PolicyError::Stale("EVIDENCE_OUTSIDE_VALIDITY"));
        }
        let record = self
            .records
            .get(&envelope.parts.verifier_id)
            .ok_or(PolicyError::Denied("EVIDENCE_VERIFIER_NOT_TRUSTED"))?;
        if record.revoked {
            return Err(PolicyError::Denied("EVIDENCE_VERIFIER_REVOKED"));
        }
        if record.role != expectation.role || record.key_id != envelope.parts.key_id {
            return Err(PolicyError::Denied(
                "EVIDENCE_VERIFIER_ROLE_OR_KEY_MISMATCH",
            ));
        }
        if expectation
            .key_id
            .is_some_and(|key_id| key_id != envelope.parts.key_id)
        {
            return Err(PolicyError::Denied("EVIDENCE_KEY_BINDING_MISMATCH"));
        }
        let public_key = PublicKey::from_slice(&record.public_key)
            .map_err(|_| PolicyError::Invalid("INVALID_VERIFIER_PUBLIC_KEY"))?;
        let signature = Signature::from_slice(&envelope.parts.signature)
            .map_err(|_| PolicyError::Denied("EVIDENCE_AUTHENTICATION_FAILED"))?;
        public_key
            .verify(envelope.authenticated_bytes(), &signature)
            .map_err(|_| PolicyError::Denied("EVIDENCE_AUTHENTICATION_FAILED"))
    }

    #[cfg(test)]
    fn issue(&self, issue: EvidenceIssue<'_>) -> Result<EvidenceEnvelope, PolicyError> {
        let record = self
            .records
            .get(issue.verifier_id)
            .ok_or(PolicyError::Denied("EVIDENCE_VERIFIER_NOT_TRUSTED"))?;
        let key_pair = fixture_key_pair(issue.verifier_id)?;
        if sha256_hex(&key_pair.pk[..]) != record.key_id || key_pair.pk[..] != record.public_key[..]
        {
            return Err(PolicyError::Invalid("FIXTURE_VERIFIER_KEY_MISMATCH"));
        }
        let mut parts = EvidenceEnvelopeParts {
            verifier_id: issue.verifier_id.to_owned(),
            key_id: record.key_id.clone(),
            role: record.role,
            trust_generation: self.trust_generation,
            revocation_generation: self.revocation_generation,
            subject: issue.subject.to_owned(),
            payload_sha256: issue.payload_sha256.to_owned(),
            not_before_epoch: issue.not_before_epoch,
            expires_at_epoch: issue.expires_at_epoch,
            nonce: issue.nonce.to_owned(),
            signature: [1_u8; 64],
        };
        let unsigned = EvidenceEnvelope::parse(parts.clone())?;
        let signature = key_pair.sk.sign(unsigned.authenticated_bytes(), None);
        parts.signature.copy_from_slice(signature.as_ref());
        EvidenceEnvelope::parse(parts)
    }
}

#[cfg(test)]
fn fixture_seed(verifier_id: &str) -> Result<[u8; 32], PolicyError> {
    let byte = match verifier_id {
        "fixture-publisher" => 1,
        "fixture-publisher-next" => 2,
        "fixture-capability-issuer" => 3,
        "fixture-network-observer" => 4,
        "fixture-update-manifest" => 5,
        "fixture-update-boot" => 6,
        "fixture-update-health" => 7,
        _ => return Err(PolicyError::Denied("EVIDENCE_VERIFIER_NOT_TRUSTED")),
    };
    Ok([byte; 32])
}

#[cfg(test)]
fn fixture_key_pair(verifier_id: &str) -> Result<KeyPair, PolicyError> {
    Ok(KeyPair::from_seed(Seed::new(fixture_seed(verifier_id)?)))
}

#[cfg(test)]
fn fixture_enrollment(
    verifier_id: &str,
    role: VerifierRole,
) -> Result<VerifierEnrollment, PolicyError> {
    let key_pair = fixture_key_pair(verifier_id)?;
    let mut public_key = [0_u8; 32];
    public_key.copy_from_slice(&key_pair.pk[..]);
    VerifierEnrollment::new(verifier_id, role, public_key, false)
}

#[cfg(test)]
fn fixture_registry() -> TrustedVerifierRegistry {
    TrustedVerifierRegistry::from_enrollments(
        7,
        11,
        vec![
            fixture_enrollment("fixture-publisher", VerifierRole::Publisher)
                .expect("publisher fixture enrollment"),
            fixture_enrollment("fixture-publisher-next", VerifierRole::Publisher)
                .expect("publisher rotation fixture enrollment"),
            fixture_enrollment("fixture-capability-issuer", VerifierRole::CapabilityIssuer)
                .expect("capability fixture enrollment"),
            fixture_enrollment("fixture-network-observer", VerifierRole::NetworkObserver)
                .expect("network observer fixture enrollment"),
            fixture_enrollment("fixture-update-manifest", VerifierRole::UpdateManifest)
                .expect("update manifest fixture enrollment"),
            fixture_enrollment("fixture-update-boot", VerifierRole::UpdateBoot)
                .expect("update boot fixture enrollment"),
            fixture_enrollment("fixture-update-health", VerifierRole::UpdateHealth)
                .expect("update health fixture enrollment"),
        ],
    )
    .expect("internal fixture registry is valid")
}

#[cfg(test)]
pub(crate) fn test_registry() -> TrustedVerifierRegistry {
    fixture_registry()
}

#[cfg(test)]
pub(crate) struct TestEvidenceRequest<'a> {
    pub verifier_id: &'a str,
    pub subject: &'a str,
    pub payload_sha256: &'a str,
    pub not_before_epoch: u64,
    pub expires_at_epoch: u64,
    pub nonce: &'a str,
}

#[cfg(test)]
pub(crate) fn issue_test_evidence(
    registry: &TrustedVerifierRegistry,
    request: TestEvidenceRequest<'_>,
) -> EvidenceEnvelope {
    registry
        .issue(EvidenceIssue {
            verifier_id: request.verifier_id,
            subject: request.subject,
            payload_sha256: request.payload_sha256,
            not_before_epoch: request.not_before_epoch,
            expires_at_epoch: request.expires_at_epoch,
            nonce: request.nonce,
        })
        .expect("test evidence request is valid")
}

// D5 ------------------------------------------------------------------------

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
}

impl TrustedAppManifest {
    pub fn payload_sha256(&self) -> Result<String, PolicyError> {
        validate_token(&self.publisher_id, 128, "INVALID_TRUSTED_APP_MANIFEST")?;
        validate_digest(&self.publisher_key_sha256)?;
        validate_digest(&self.content_root_sha256)?;
        if self.version == 0 {
            return Err(PolicyError::Invalid("INVALID_TRUSTED_APP_MANIFEST"));
        }
        let mut canonical = Canonical::default();
        canonical.text("app_id", &self.app_id);
        canonical.text("publisher_id", &self.publisher_id);
        canonical.text("publisher_key_sha256", &self.publisher_key_sha256);
        canonical.u64("version", self.version);
        canonical.text("origin", &self.origin);
        canonical.text("content_root_sha256", &self.content_root_sha256);
        canonical.bool("csp_default_none", self.csp.default_none);
        canonical.bool("csp_script_self", self.csp.script_self);
        canonical.bool("csp_style_self", self.csp.style_self);
        canonical.bool("csp_connect_none", self.csp.connect_none);
        canonical.bool("csp_object_none", self.csp.object_none);
        canonical.bool("csp_frame_none", self.csp.frame_none);
        canonical.bool("csp_base_none", self.csp.base_none);
        canonical.bool("csp_form_none", self.csp.form_none);
        canonical.bool("csp_unsafe_source", self.csp.unsafe_source);
        canonical.bool("csp_external_origin", self.csp.external_origin);
        canonical.text(
            "service_worker_scope",
            self.service_worker_scope.as_deref().unwrap_or(""),
        );
        canonical.bool("revoked", self.revoked);
        Ok(canonical.digest())
    }
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
    pub fn derived_origin(app_id: &str, publisher_id: &str) -> Result<String, PolicyError> {
        let app = trillionnium_contract_core::DnsLabel::parse(app_id)
            .map_err(|_| PolicyError::Invalid("INVALID_TRUSTED_APP_ID"))?;
        let publisher = trillionnium_contract_core::DnsLabel::parse(publisher_id)
            .map_err(|_| PolicyError::Invalid("INVALID_TRUSTED_APP_PUBLISHER"))?;
        Ok(hepta_browser_contracts::TrustedAppIdentity::new(publisher, app).synthetic_origin())
    }

    fn rotation_payload_sha256(
        installed: &TrustedAppInstall,
        manifest: &TrustedAppManifest,
    ) -> String {
        let mut canonical = Canonical::default();
        canonical.text("app_id", &manifest.app_id);
        canonical.text("publisher_id", &manifest.publisher_id);
        canonical.text("old_key", &installed.publisher_key_sha256);
        canonical.text("new_key", &manifest.publisher_key_sha256);
        canonical.u64("old_version", installed.version);
        canonical.u64("new_version", manifest.version);
        canonical.digest()
    }

    pub fn admit(
        registry: &TrustedVerifierRegistry,
        manifest: &TrustedAppManifest,
        manifest_evidence: &EvidenceEnvelope,
        rotation_evidence: Option<&EvidenceEnvelope>,
        prior: Option<&TrustedAppInstall>,
        now_epoch: u64,
    ) -> Result<TrustedAppInstall, PolicyError> {
        let payload_sha256 = manifest.payload_sha256()?;
        registry.verify(
            manifest_evidence,
            EvidenceExpectation {
                role: VerifierRole::Publisher,
                subject: "trusted-app-manifest.v2",
                payload_sha256: &payload_sha256,
                key_id: Some(&manifest.publisher_key_sha256),
                now_epoch,
            },
        )?;
        if manifest.revoked {
            return Err(PolicyError::Denied("TRUSTED_APP_REVOKED"));
        }
        let expected_origin = Self::derived_origin(&manifest.app_id, &manifest.publisher_id)?;
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
            if installed.app_id != manifest.app_id
                || installed.publisher_id != manifest.publisher_id
            {
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
            if manifest.publisher_key_sha256 != installed.publisher_key_sha256 {
                let rotation = rotation_evidence
                    .ok_or(PolicyError::Denied("PUBLISHER_ROTATION_NOT_AUTHORIZED"))?;
                let rotation_payload = Self::rotation_payload_sha256(installed, manifest);
                registry.verify(
                    rotation,
                    EvidenceExpectation {
                        role: VerifierRole::Publisher,
                        subject: "trusted-app-key-rotation.v1",
                        payload_sha256: &rotation_payload,
                        key_id: Some(&installed.publisher_key_sha256),
                        now_epoch,
                    },
                )?;
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

impl Audience {
    const fn code(self) -> &'static str {
        match self {
            Self::Network => "network",
            Self::File => "file",
            Self::Notification => "notification",
            Self::Audio => "audio",
        }
    }
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

impl NetworkContext {
    const fn code(self) -> &'static str {
        match self {
            Self::TopLevel => "top-level",
            Self::Iframe => "iframe",
            Self::Worker => "worker",
            Self::ServiceWorker => "service-worker",
            Self::Prefetch => "prefetch",
            Self::WebSocket => "websocket",
            Self::Download => "download",
        }
    }
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
    pub evidence: EvidenceEnvelope,
}

impl CapabilityPermit {
    pub fn payload_sha256(&self) -> Result<String, PolicyError> {
        validate_token(&self.permit_id, 128, "INVALID_CAPABILITY_PERMIT")?;
        validate_token(&self.subject, 256, "INVALID_CAPABILITY_PERMIT")?;
        validate_token(&self.resource_id, 256, "INVALID_CAPABILITY_PERMIT")?;
        validate_token(&self.action, 128, "INVALID_CAPABILITY_PERMIT")?;
        validate_token(&self.nonce, 128, "INVALID_CAPABILITY_PERMIT")?;
        if self.maximum_uses == 0
            || self.expires_at_epoch < self.not_before_epoch
            || self.expires_at_epoch - self.not_before_epoch > MAX_PERMIT_LIFETIME_SECONDS
        {
            return Err(PolicyError::Invalid("INVALID_CAPABILITY_PERMIT"));
        }
        let mut canonical = Canonical::default();
        canonical.text("permit_id", &self.permit_id);
        canonical.text("subject", &self.subject);
        canonical.text("audience", self.audience.code());
        canonical.text("resource_id", &self.resource_id);
        canonical.text("action", &self.action);
        canonical.u64("not_before_epoch", self.not_before_epoch);
        canonical.u64("expires_at_epoch", self.expires_at_epoch);
        canonical.text("nonce", &self.nonce);
        canonical.u32("maximum_uses", self.maximum_uses);
        canonical.bool("revoked", self.revoked);
        Ok(canonical.digest())
    }
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
    pub method: String,
    pub payload_sha256: String,
    pub context: NetworkContext,
    pub redirect_count: u8,
}

impl NetworkRequest {
    pub fn request_sha256(&self) -> Result<String, PolicyError> {
        validate_token(&self.subject, 256, "INVALID_NETWORK_REQUEST")?;
        validate_token(&self.action, 128, "INVALID_NETWORK_REQUEST")?;
        validate_digest(&self.payload_sha256)?;
        if !matches!(
            self.method.as_str(),
            "DELETE" | "GET" | "HEAD" | "PATCH" | "POST" | "PUT"
        ) {
            return Err(PolicyError::Invalid("INVALID_NETWORK_METHOD"));
        }
        canonical_https_origin(&self.origin)?;
        let mut canonical = Canonical::default();
        canonical.text("subject", &self.subject);
        canonical.text("origin", &self.origin);
        canonical.text("action", &self.action);
        canonical.text("method", &self.method);
        canonical.text("payload_sha256", &self.payload_sha256);
        canonical.text("context", self.context.code());
        canonical.u8("redirect_count", self.redirect_count);
        Ok(canonical.digest())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetworkObservation {
    pub request_sha256: String,
    pub permit_sha256: String,
    pub resolver_id: String,
    pub dns_generation: u64,
    pub resolved_addresses: Vec<IpAddr>,
    pub connected_peer: IpAddr,
    pub proxy_id: String,
    pub direct_connection: bool,
    pub tls_verified: bool,
    pub tls_intercepted: bool,
    pub tls_peer_spki_sha256: String,
    pub observed_at_epoch: u64,
    pub evidence: EvidenceEnvelope,
}

impl NetworkObservation {
    pub fn observation_sha256(&self) -> Result<String, PolicyError> {
        validate_digest(&self.request_sha256)?;
        validate_digest(&self.permit_sha256)?;
        validate_token(&self.resolver_id, 128, "INVALID_NETWORK_OBSERVER")?;
        validate_token(&self.proxy_id, 128, "INVALID_NETWORK_OBSERVATION")?;
        validate_digest(&self.tls_peer_spki_sha256)?;
        if self.dns_generation == 0
            || self.resolved_addresses.is_empty()
            || self.resolved_addresses.len() > MAX_DNS_ADDRESSES
        {
            return Err(PolicyError::Invalid("INVALID_NETWORK_OBSERVATION"));
        }
        let mut canonical = Canonical::default();
        canonical.text("request_sha256", &self.request_sha256);
        canonical.text("permit_sha256", &self.permit_sha256);
        canonical.text("resolver_id", &self.resolver_id);
        canonical.u64("dns_generation", self.dns_generation);
        for (index, address) in self.resolved_addresses.iter().enumerate() {
            canonical.text(&format!("resolved_address_{index}"), &address.to_string());
        }
        canonical.text("connected_peer", &self.connected_peer.to_string());
        canonical.text("proxy_id", &self.proxy_id);
        canonical.bool("direct_connection", self.direct_connection);
        canonical.bool("tls_verified", self.tls_verified);
        canonical.bool("tls_intercepted", self.tls_intercepted);
        canonical.text("tls_peer_spki_sha256", &self.tls_peer_spki_sha256);
        canonical.u64("observed_at_epoch", self.observed_at_epoch);
        Ok(canonical.digest())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetworkDecision {
    permit_id: String,
    permit_use_ordinal: u32,
    subject: String,
    resource_id: String,
    action: String,
    method: String,
    payload_sha256: String,
    origin: String,
    connected_peer: IpAddr,
    request_sha256: String,
    observation_sha256: String,
    authority_generation: u64,
}

impl NetworkDecision {
    pub fn permit_id(&self) -> &str {
        &self.permit_id
    }

    pub fn permit_use_ordinal(&self) -> u32 {
        self.permit_use_ordinal
    }

    pub fn subject(&self) -> &str {
        &self.subject
    }

    pub fn resource_id(&self) -> &str {
        &self.resource_id
    }

    pub fn action(&self) -> &str {
        &self.action
    }

    pub fn method(&self) -> &str {
        &self.method
    }

    pub fn payload_sha256(&self) -> &str {
        &self.payload_sha256
    }

    pub fn origin(&self) -> &str {
        &self.origin
    }

    pub fn connected_peer(&self) -> IpAddr {
        self.connected_peer
    }

    pub fn request_sha256(&self) -> &str {
        &self.request_sha256
    }

    pub fn observation_sha256(&self) -> &str {
        &self.observation_sha256
    }

    pub fn authority_generation(&self) -> u64 {
        self.authority_generation
    }
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
        registry: &TrustedVerifierRegistry,
        permit: &CapabilityPermit,
        resource: &NetworkResource,
        request: &NetworkRequest,
        observation: &NetworkObservation,
        now_epoch: u64,
    ) -> Result<NetworkDecision, PolicyError> {
        let permit_sha256 = permit.payload_sha256()?;
        registry.verify(
            &permit.evidence,
            EvidenceExpectation {
                role: VerifierRole::CapabilityIssuer,
                subject: "capability-permit.v2",
                payload_sha256: &permit_sha256,
                key_id: None,
                now_epoch,
            },
        )?;
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
        validate_token(&resource.resource_id, 256, "INVALID_NETWORK_RESOURCE")?;
        validate_token(&resource.proxy_id, 128, "INVALID_NETWORK_RESOURCE")?;
        if resource.allowed_origins.is_empty() || resource.allowed_contexts.is_empty() {
            return Err(PolicyError::Invalid("INVALID_NETWORK_RESOURCE"));
        }
        for origin in &resource.allowed_origins {
            canonical_https_origin(origin)?;
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
        let prior_uses = self.uses(&permit.permit_id);
        if prior_uses >= permit.maximum_uses {
            return Err(PolicyError::Denied("PERMIT_REPLAY_LIMIT_REACHED"));
        }
        let request_sha256 = request.request_sha256()?;
        if !resource.allowed_origins.contains(&request.origin) {
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
        if observation.request_sha256 != request_sha256
            || observation.permit_sha256 != permit_sha256
        {
            return Err(PolicyError::Denied("NETWORK_OBSERVATION_BINDING_MISMATCH"));
        }
        if observation.observed_at_epoch > now_epoch
            || now_epoch - observation.observed_at_epoch > MAX_OBSERVATION_AGE_SECONDS
        {
            return Err(PolicyError::Stale("NETWORK_OBSERVATION_STALE"));
        }
        let observation_sha256 = observation.observation_sha256()?;
        registry.verify(
            &observation.evidence,
            EvidenceExpectation {
                role: VerifierRole::NetworkObserver,
                subject: "network-observation.v1",
                payload_sha256: &observation_sha256,
                key_id: None,
                now_epoch,
            },
        )?;
        if observation.direct_connection
            || observation.proxy_id != resource.proxy_id
            || !observation.tls_verified
            || observation.tls_intercepted
        {
            return Err(PolicyError::Denied("CONTROLLED_EGRESS_REQUIRED"));
        }
        let mut approved = BTreeSet::new();
        for address in &observation.resolved_addresses {
            if !is_global_unicast(*address) {
                return Err(PolicyError::Denied("NON_GLOBAL_IP_FORBIDDEN"));
            }
            if !approved.insert(*address) {
                return Err(PolicyError::Invalid("DUPLICATE_DNS_ADDRESS"));
            }
        }
        if !is_global_unicast(observation.connected_peer) {
            return Err(PolicyError::Denied("NON_GLOBAL_IP_FORBIDDEN"));
        }
        if !approved.contains(&observation.connected_peer) {
            return Err(PolicyError::Denied("CONNECTED_PEER_NOT_IN_DNS_SET"));
        }
        let next_uses = prior_uses
            .checked_add(1)
            .ok_or(PolicyError::Invalid("PERMIT_USE_OVERFLOW"))?;
        self.permit_nonces
            .entry(permit.permit_id.clone())
            .or_insert_with(|| permit.nonce.clone());
        self.uses.insert(permit.permit_id.clone(), next_uses);
        Ok(NetworkDecision {
            permit_id: permit.permit_id.clone(),
            permit_use_ordinal: next_uses,
            subject: permit.subject.clone(),
            resource_id: resource.resource_id.clone(),
            action: permit.action.clone(),
            method: request.method.clone(),
            payload_sha256: request.payload_sha256.clone(),
            origin: request.origin.clone(),
            connected_peer: observation.connected_peer,
            request_sha256,
            observation_sha256,
            authority_generation: observation.dns_generation,
        })
    }

    pub(crate) fn state_sha256(&self) -> String {
        let mut canonical = Canonical::default();
        for (permit_id, uses) in &self.uses {
            canonical.text("permit_id", permit_id);
            canonical.u32("uses", *uses);
            canonical.text(
                "nonce",
                self.permit_nonces
                    .get(permit_id)
                    .map(String::as_str)
                    .unwrap_or(""),
            );
        }
        canonical.digest()
    }
}

fn canonical_https_origin(value: &str) -> Result<(), PolicyError> {
    if !value.is_ascii() || value.bytes().any(|byte| byte <= 0x20 || byte == 0x7f) {
        return Err(PolicyError::Invalid("NETWORK_ORIGIN_NOT_CANONICAL"));
    }
    let authority = value
        .strip_prefix("https://")
        .ok_or(PolicyError::Invalid("NETWORK_ORIGIN_NOT_CANONICAL"))?;
    if authority.contains('/')
        || authority.contains('@')
        || authority.contains('\\')
        || authority.contains('#')
        || authority.contains('?')
        || authority.contains('[')
        || authority.contains(']')
    {
        return Err(PolicyError::Invalid("NETWORK_ORIGIN_NOT_CANONICAL"));
    }
    let host = authority
        .strip_suffix(":443")
        .ok_or(PolicyError::Invalid("NETWORK_ORIGIN_NOT_CANONICAL"))?;
    if host.is_empty()
        || host.len() > 253
        || host != host.to_ascii_lowercase()
        || !host.contains('.')
        || Ipv4Addr::from_str(host).is_ok()
        || Ipv6Addr::from_str(host).is_ok()
    {
        return Err(PolicyError::Invalid("NETWORK_ORIGIN_NOT_CANONICAL"));
    }
    for label in host.split('.') {
        let bytes = label.as_bytes();
        if bytes.is_empty()
            || bytes.len() > 63
            || !bytes[0].is_ascii_alphanumeric()
            || !bytes[bytes.len() - 1].is_ascii_alphanumeric()
            || !bytes
                .iter()
                .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'-')
        {
            return Err(PolicyError::Invalid("NETWORK_ORIGIN_NOT_CANONICAL"));
        }
    }
    Ok(())
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
        [192, 0, 0, _] | [192, 0, 2, _] | [192, 88, 99, _] | [198, 51, 100, _] | [203, 0, 113, _]
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
        || (segments[0] == 0x0100 && segments[1] == 0 && segments[2] == 0 && segments[3] == 0)
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

// D7 effect identity and durable journal -------------------------------------

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EffectCommand {
    effect_id: String,
    subject: String,
    resource_id: String,
    action: String,
    method: String,
    payload_sha256: String,
    permit_id: String,
    permit_use_ordinal: u32,
    authority_generation: u64,
    idempotency_key: String,
    request_sha256: String,
    observation_sha256: String,
    command_sha256: String,
}

impl EffectCommand {
    pub fn from_network(
        effect_id: &str,
        idempotency_key: &str,
        decision: &NetworkDecision,
    ) -> Result<Self, PolicyError> {
        let mut command = Self {
            effect_id: effect_id.to_owned(),
            subject: decision.subject.clone(),
            resource_id: decision.resource_id.clone(),
            action: decision.action.clone(),
            method: decision.method.clone(),
            payload_sha256: decision.payload_sha256.clone(),
            permit_id: decision.permit_id.clone(),
            permit_use_ordinal: decision.permit_use_ordinal,
            authority_generation: decision.authority_generation,
            idempotency_key: idempotency_key.to_owned(),
            request_sha256: decision.request_sha256.clone(),
            observation_sha256: decision.observation_sha256.clone(),
            command_sha256: String::new(),
        };
        command.validate_fields()?;
        command.command_sha256 = command.compute_sha256();
        Ok(command)
    }

    fn from_encoded_fields(fields: &[&str]) -> Result<Self, PolicyError> {
        if fields.len() != 13 {
            return Err(PolicyError::Invalid("EFFECT_JOURNAL_FIELD_COUNT_INVALID"));
        }
        let permit_use_ordinal = fields[7]
            .parse::<u32>()
            .map_err(|_| PolicyError::Invalid("EFFECT_JOURNAL_NUMBER_INVALID"))?;
        let authority_generation = fields[8]
            .parse::<u64>()
            .map_err(|_| PolicyError::Invalid("EFFECT_JOURNAL_NUMBER_INVALID"))?;
        let command = Self {
            effect_id: fields[0].to_owned(),
            subject: fields[1].to_owned(),
            resource_id: fields[2].to_owned(),
            action: fields[3].to_owned(),
            method: fields[4].to_owned(),
            payload_sha256: fields[5].to_owned(),
            permit_id: fields[6].to_owned(),
            permit_use_ordinal,
            authority_generation,
            idempotency_key: fields[9].to_owned(),
            request_sha256: fields[10].to_owned(),
            observation_sha256: fields[11].to_owned(),
            command_sha256: fields[12].to_owned(),
        };
        command.validate()?;
        Ok(command)
    }

    fn validate_fields(&self) -> Result<(), PolicyError> {
        validate_token(&self.effect_id, 128, "INVALID_EFFECT_OPERATION_ID")?;
        validate_token(&self.subject, 256, "INVALID_EFFECT_COMMAND")?;
        validate_token(&self.resource_id, 256, "INVALID_EFFECT_COMMAND")?;
        validate_token(&self.action, 128, "INVALID_EFFECT_COMMAND")?;
        validate_token(&self.method, 16, "INVALID_EFFECT_COMMAND")?;
        validate_digest(&self.payload_sha256)?;
        validate_token(&self.permit_id, 128, "INVALID_EFFECT_COMMAND")?;
        validate_token(&self.idempotency_key, 128, "INVALID_EFFECT_COMMAND")?;
        validate_digest(&self.request_sha256)?;
        validate_digest(&self.observation_sha256)?;
        if self.permit_use_ordinal == 0 || self.authority_generation == 0 {
            return Err(PolicyError::Invalid("INVALID_EFFECT_COMMAND"));
        }
        Ok(())
    }

    fn compute_sha256(&self) -> String {
        let mut canonical = Canonical::default();
        canonical.text("effect_id", &self.effect_id);
        canonical.text("subject", &self.subject);
        canonical.text("resource_id", &self.resource_id);
        canonical.text("action", &self.action);
        canonical.text("method", &self.method);
        canonical.text("payload_sha256", &self.payload_sha256);
        canonical.text("permit_id", &self.permit_id);
        canonical.u32("permit_use_ordinal", self.permit_use_ordinal);
        canonical.u64("authority_generation", self.authority_generation);
        canonical.text("idempotency_key", &self.idempotency_key);
        canonical.text("request_sha256", &self.request_sha256);
        canonical.text("observation_sha256", &self.observation_sha256);
        canonical.digest()
    }

    pub fn validate(&self) -> Result<(), PolicyError> {
        self.validate_fields()?;
        validate_digest(&self.command_sha256)?;
        if self.compute_sha256() != self.command_sha256 {
            return Err(PolicyError::Denied("EFFECT_COMMAND_DIGEST_MISMATCH"));
        }
        Ok(())
    }

    pub fn effect_id(&self) -> &str {
        &self.effect_id
    }

    pub fn subject(&self) -> &str {
        &self.subject
    }

    pub fn resource_id(&self) -> &str {
        &self.resource_id
    }

    pub fn action(&self) -> &str {
        &self.action
    }

    pub fn method(&self) -> &str {
        &self.method
    }

    pub fn payload_sha256(&self) -> &str {
        &self.payload_sha256
    }

    pub fn permit_id(&self) -> &str {
        &self.permit_id
    }

    pub fn permit_use_ordinal(&self) -> u32 {
        self.permit_use_ordinal
    }

    pub fn authority_generation(&self) -> u64 {
        self.authority_generation
    }

    pub fn idempotency_key(&self) -> &str {
        &self.idempotency_key
    }

    pub fn request_sha256(&self) -> &str {
        &self.request_sha256
    }

    pub fn observation_sha256(&self) -> &str {
        &self.observation_sha256
    }

    pub fn command_sha256(&self) -> &str {
        &self.command_sha256
    }

    fn encoded_fields(&self) -> [String; 13] {
        [
            self.effect_id.clone(),
            self.subject.clone(),
            self.resource_id.clone(),
            self.action.clone(),
            self.method.clone(),
            self.payload_sha256.clone(),
            self.permit_id.clone(),
            self.permit_use_ordinal.to_string(),
            self.authority_generation.to_string(),
            self.idempotency_key.clone(),
            self.request_sha256.clone(),
            self.observation_sha256.clone(),
            self.command_sha256.clone(),
        ]
    }
}

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

impl EffectState {
    const fn code(self) -> &'static str {
        match self {
            Self::Requested => "requested",
            Self::Prepared => "prepared",
            Self::Dispatched => "dispatched",
            Self::Applied => "applied",
            Self::NotApplied => "not-applied",
            Self::Indeterminate => "indeterminate",
            Self::Cancelled => "cancelled",
        }
    }

    fn parse(value: &str) -> Result<Self, PolicyError> {
        match value {
            "requested" => Ok(Self::Requested),
            "prepared" => Ok(Self::Prepared),
            "dispatched" => Ok(Self::Dispatched),
            "applied" => Ok(Self::Applied),
            "not-applied" => Ok(Self::NotApplied),
            "indeterminate" => Ok(Self::Indeterminate),
            "cancelled" => Ok(Self::Cancelled),
            _ => Err(PolicyError::Invalid("EFFECT_JOURNAL_STATE_INVALID")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProviderObservation {
    Applied,
    NotApplied,
    Unknown,
}

impl ProviderObservation {
    const fn code(self) -> &'static str {
        match self {
            Self::Applied => "applied",
            Self::NotApplied => "not-applied",
            Self::Unknown => "unknown",
        }
    }

    fn parse(value: &str) -> Result<Option<Self>, PolicyError> {
        match value {
            "" => Ok(None),
            "applied" => Ok(Some(Self::Applied)),
            "not-applied" => Ok(Some(Self::NotApplied)),
            "unknown" => Ok(Some(Self::Unknown)),
            _ => Err(PolicyError::Invalid("EFFECT_JOURNAL_OBSERVATION_INVALID")),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EffectRecord {
    pub sequence: u64,
    pub command: EffectCommand,
    pub state: EffectState,
    pub provider_id: Option<String>,
    pub attempt: u32,
    pub observation: Option<ProviderObservation>,
    pub previous_sha256: String,
    pub record_sha256: String,
}

impl EffectRecord {
    fn compute_sha256(
        sequence: u64,
        command: &EffectCommand,
        state: EffectState,
        provider_id: Option<&str>,
        attempt: u32,
        observation: Option<ProviderObservation>,
        previous_sha256: &str,
    ) -> String {
        let mut canonical = Canonical::default();
        canonical.u64("sequence", sequence);
        canonical.text("command_sha256", command.command_sha256());
        canonical.text("state", state.code());
        canonical.text("provider_id", provider_id.unwrap_or(""));
        canonical.u32("attempt", attempt);
        canonical.text(
            "observation",
            observation.map(ProviderObservation::code).unwrap_or(""),
        );
        canonical.text("previous_sha256", previous_sha256);
        canonical.digest()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct EffectOperation {
    command: EffectCommand,
    state: EffectState,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EffectJournal {
    operations: BTreeMap<String, EffectOperation>,
    records: Vec<EffectRecord>,
    head_sha256: String,
    next_sequence: u64,
}

impl Default for EffectJournal {
    fn default() -> Self {
        Self {
            operations: BTreeMap::new(),
            records: Vec::new(),
            head_sha256: EMPTY_JOURNAL_SHA256.to_owned(),
            next_sequence: 1,
        }
    }
}

impl EffectJournal {
    pub fn state(&self, effect_id: &str) -> Option<EffectState> {
        self.operations
            .get(effect_id)
            .map(|operation| operation.state)
    }

    pub fn command(&self, effect_id: &str) -> Option<&EffectCommand> {
        self.operations
            .get(effect_id)
            .map(|operation| &operation.command)
    }

    pub fn records(&self) -> &[EffectRecord] {
        &self.records
    }

    pub fn head_sha256(&self) -> &str {
        &self.head_sha256
    }

    fn append_record(
        &mut self,
        command: EffectCommand,
        state: EffectState,
        provider_id: Option<String>,
        attempt: u32,
        observation: Option<ProviderObservation>,
    ) -> Result<(), PolicyError> {
        command.validate()?;
        if provider_id
            .as_deref()
            .is_some_and(|provider| !valid_token(provider, 128))
        {
            return Err(PolicyError::Invalid("INVALID_PROVIDER_ID"));
        }
        let next_sequence =
            checked_successor(self.next_sequence, "EFFECT_JOURNAL_SEQUENCE_OVERFLOW")?;
        let record_sha256 = EffectRecord::compute_sha256(
            self.next_sequence,
            &command,
            state,
            provider_id.as_deref(),
            attempt,
            observation,
            &self.head_sha256,
        );
        let record = EffectRecord {
            sequence: self.next_sequence,
            command: command.clone(),
            state,
            provider_id,
            attempt,
            observation,
            previous_sha256: self.head_sha256.clone(),
            record_sha256: record_sha256.clone(),
        };
        self.operations.insert(
            command.effect_id.clone(),
            EffectOperation { command, state },
        );
        self.records.push(record);
        self.head_sha256 = record_sha256;
        self.next_sequence = next_sequence;
        Ok(())
    }

    pub fn request(&mut self, command: EffectCommand) -> Result<(), PolicyError> {
        command.validate()?;
        if self.operations.contains_key(command.effect_id()) {
            return Err(PolicyError::Conflict("EFFECT_OPERATION_ALREADY_EXISTS"));
        }
        self.append_record(command, EffectState::Requested, None, 0, None)
    }

    fn transition(
        &mut self,
        effect_id: &str,
        command_sha256: &str,
        expected: &[EffectState],
        next: EffectState,
    ) -> Result<(), PolicyError> {
        let operation = self
            .operations
            .get(effect_id)
            .ok_or(PolicyError::Denied("EFFECT_OPERATION_UNKNOWN"))?;
        if operation.command.command_sha256() != command_sha256 {
            return Err(PolicyError::Denied("EFFECT_COMMAND_BINDING_MISMATCH"));
        }
        if !expected.contains(&operation.state) {
            return Err(PolicyError::Denied("EFFECT_STATE_TRANSITION_REJECTED"));
        }
        self.append_record(operation.command.clone(), next, None, 0, None)
    }

    pub fn prepare(&mut self, effect_id: &str, command_sha256: &str) -> Result<(), PolicyError> {
        self.transition(
            effect_id,
            command_sha256,
            &[EffectState::Requested],
            EffectState::Prepared,
        )
    }

    pub fn mark_dispatched(
        &mut self,
        effect_id: &str,
        command_sha256: &str,
    ) -> Result<(), PolicyError> {
        self.transition(
            effect_id,
            command_sha256,
            &[EffectState::Prepared],
            EffectState::Dispatched,
        )
    }

    pub fn cancel_before_dispatch(
        &mut self,
        effect_id: &str,
        command_sha256: &str,
    ) -> Result<(), PolicyError> {
        self.transition(
            effect_id,
            command_sha256,
            &[EffectState::Requested, EffectState::Prepared],
            EffectState::Cancelled,
        )
    }

    pub fn reconcile(
        &mut self,
        effect_id: &str,
        command_sha256: &str,
        provider_id: &str,
        attempt: u32,
        observation: ProviderObservation,
    ) -> Result<EffectState, PolicyError> {
        validate_token(provider_id, 128, "INVALID_PROVIDER_ID")?;
        if attempt == 0 {
            return Err(PolicyError::Invalid("INVALID_PROVIDER_ATTEMPT"));
        }
        let operation = self
            .operations
            .get(effect_id)
            .ok_or(PolicyError::Denied("EFFECT_OPERATION_UNKNOWN"))?;
        if operation.command.command_sha256() != command_sha256 {
            return Err(PolicyError::Denied("EFFECT_COMMAND_BINDING_MISMATCH"));
        }
        if !matches!(
            operation.state,
            EffectState::Dispatched | EffectState::Indeterminate
        ) {
            return Err(PolicyError::Denied("EFFECT_RECONCILIATION_NOT_ALLOWED"));
        }
        let state = match observation {
            ProviderObservation::Applied => EffectState::Applied,
            ProviderObservation::NotApplied => EffectState::NotApplied,
            ProviderObservation::Unknown => EffectState::Indeterminate,
        };
        self.append_record(
            operation.command.clone(),
            state,
            Some(provider_id.to_owned()),
            attempt,
            Some(observation),
        )?;
        Ok(state)
    }

    pub fn automatic_replay_allowed(&self, _effect_id: &str) -> bool {
        false
    }

    pub fn encode(&self) -> String {
        let mut output = String::from("trillionnium-effect-journal-v1\n");
        for record in &self.records {
            let mut fields = vec![record.sequence.to_string(), record.state.code().to_owned()];
            fields.extend(record.command.encoded_fields());
            fields.push(record.provider_id.clone().unwrap_or_default());
            fields.push(record.attempt.to_string());
            fields.push(
                record
                    .observation
                    .map(ProviderObservation::code)
                    .unwrap_or("")
                    .to_owned(),
            );
            fields.push(record.previous_sha256.clone());
            fields.push(record.record_sha256.clone());
            output.push_str(&fields.join("|"));
            output.push('\n');
        }
        output
    }

    pub fn restore(encoded: &str) -> Result<Self, PolicyError> {
        let mut lines = encoded.lines();
        if lines.next() != Some("trillionnium-effect-journal-v1") {
            return Err(PolicyError::Invalid("EFFECT_JOURNAL_HEADER_INVALID"));
        }
        let mut journal = Self::default();
        for line in lines {
            if line.is_empty() {
                return Err(PolicyError::Invalid("EFFECT_JOURNAL_EMPTY_RECORD"));
            }
            let fields = line.split('|').collect::<Vec<_>>();
            if fields.len() != 20 {
                return Err(PolicyError::Invalid("EFFECT_JOURNAL_FIELD_COUNT_INVALID"));
            }
            let sequence = fields[0]
                .parse::<u64>()
                .map_err(|_| PolicyError::Invalid("EFFECT_JOURNAL_NUMBER_INVALID"))?;
            let state = EffectState::parse(fields[1])?;
            let command = EffectCommand::from_encoded_fields(&fields[2..15])?;
            let provider_id = if fields[15].is_empty() {
                None
            } else {
                Some(fields[15].to_owned())
            };
            let attempt = fields[16]
                .parse::<u32>()
                .map_err(|_| PolicyError::Invalid("EFFECT_JOURNAL_NUMBER_INVALID"))?;
            let observation = ProviderObservation::parse(fields[17])?;
            let previous_sha256 = fields[18];
            let record_sha256 = fields[19];
            if sequence != journal.next_sequence || previous_sha256 != journal.head_sha256 {
                return Err(PolicyError::Denied("EFFECT_JOURNAL_CHAIN_MISMATCH"));
            }
            let expected_record_sha256 = EffectRecord::compute_sha256(
                sequence,
                &command,
                state,
                provider_id.as_deref(),
                attempt,
                observation,
                previous_sha256,
            );
            if expected_record_sha256 != record_sha256 {
                return Err(PolicyError::Denied("EFFECT_JOURNAL_RECORD_DIGEST_MISMATCH"));
            }
            match state {
                EffectState::Requested => {
                    if provider_id.is_some() || attempt != 0 || observation.is_some() {
                        return Err(PolicyError::Invalid("EFFECT_JOURNAL_REQUEST_INVALID"));
                    }
                    journal.request(command.clone())?;
                }
                EffectState::Prepared => {
                    let existing = journal
                        .command(command.effect_id())
                        .ok_or(PolicyError::Denied("EFFECT_JOURNAL_TRANSITION_MISSING"))?;
                    if existing != &command {
                        return Err(PolicyError::Denied("EFFECT_JOURNAL_COMMAND_DRIFT"));
                    }
                    journal.prepare(command.effect_id(), command.command_sha256())?;
                }
                EffectState::Dispatched => {
                    let existing = journal
                        .command(command.effect_id())
                        .ok_or(PolicyError::Denied("EFFECT_JOURNAL_TRANSITION_MISSING"))?;
                    if existing != &command {
                        return Err(PolicyError::Denied("EFFECT_JOURNAL_COMMAND_DRIFT"));
                    }
                    journal.mark_dispatched(command.effect_id(), command.command_sha256())?;
                }
                EffectState::Cancelled => {
                    let existing = journal
                        .command(command.effect_id())
                        .ok_or(PolicyError::Denied("EFFECT_JOURNAL_TRANSITION_MISSING"))?;
                    if existing != &command {
                        return Err(PolicyError::Denied("EFFECT_JOURNAL_COMMAND_DRIFT"));
                    }
                    journal
                        .cancel_before_dispatch(command.effect_id(), command.command_sha256())?;
                }
                EffectState::Applied | EffectState::NotApplied | EffectState::Indeterminate => {
                    let provider = provider_id
                        .as_deref()
                        .ok_or(PolicyError::Invalid("EFFECT_JOURNAL_PROVIDER_MISSING"))?;
                    let observed = observation
                        .ok_or(PolicyError::Invalid("EFFECT_JOURNAL_OBSERVATION_MISSING"))?;
                    let expected_state = match observed {
                        ProviderObservation::Applied => EffectState::Applied,
                        ProviderObservation::NotApplied => EffectState::NotApplied,
                        ProviderObservation::Unknown => EffectState::Indeterminate,
                    };
                    if expected_state != state {
                        return Err(PolicyError::Invalid("EFFECT_JOURNAL_OBSERVATION_DRIFT"));
                    }
                    let existing = journal
                        .command(command.effect_id())
                        .ok_or(PolicyError::Denied("EFFECT_JOURNAL_TRANSITION_MISSING"))?;
                    if existing != &command {
                        return Err(PolicyError::Denied("EFFECT_JOURNAL_COMMAND_DRIFT"));
                    }
                    journal.reconcile(
                        command.effect_id(),
                        command.command_sha256(),
                        provider,
                        attempt,
                        observed,
                    )?;
                }
            }
            let restored = journal
                .records
                .last()
                .ok_or(PolicyError::Invalid("EFFECT_JOURNAL_RESTORE_EMPTY"))?;
            if restored.sequence != sequence
                || restored.previous_sha256 != previous_sha256
                || restored.record_sha256 != record_sha256
            {
                return Err(PolicyError::Denied("EFFECT_JOURNAL_RESTORE_MISMATCH"));
            }
        }
        Ok(journal)
    }

    pub(crate) fn state_sha256(&self) -> String {
        sha256_hex(self.encode().as_bytes())
    }
}

// D7 signed A/B update state -------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UpdateSlot {
    A,
    B,
}

impl UpdateSlot {
    const fn code(self) -> &'static str {
        match self {
            Self::A => "A",
            Self::B => "B",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateManifestParts {
    pub target: UpdateSlot,
    pub version: u64,
    pub rollback_index: u64,
    pub image_sha256: String,
    pub image_bytes: u64,
    pub sbom_sha256: String,
    pub provenance_sha256: String,
    pub source_commit_sha256: String,
    pub signer_key_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateManifest {
    parts: UpdateManifestParts,
    manifest_sha256: String,
}

impl UpdateManifest {
    fn compute_sha256(parts: &UpdateManifestParts) -> String {
        let mut canonical = Canonical::default();
        canonical.text("target", parts.target.code());
        canonical.u64("version", parts.version);
        canonical.u64("rollback_index", parts.rollback_index);
        canonical.text("image_sha256", &parts.image_sha256);
        canonical.u64("image_bytes", parts.image_bytes);
        canonical.text("sbom_sha256", &parts.sbom_sha256);
        canonical.text("provenance_sha256", &parts.provenance_sha256);
        canonical.text("source_commit_sha256", &parts.source_commit_sha256);
        canonical.text("signer_key_sha256", &parts.signer_key_sha256);
        canonical.digest()
    }

    fn validate_parts(parts: &UpdateManifestParts) -> Result<(), PolicyError> {
        if parts.version == 0 || parts.rollback_index == 0 || parts.image_bytes == 0 {
            return Err(PolicyError::Invalid("INVALID_UPDATE_MANIFEST"));
        }
        validate_digest(&parts.image_sha256)?;
        validate_digest(&parts.sbom_sha256)?;
        validate_digest(&parts.provenance_sha256)?;
        validate_digest(&parts.source_commit_sha256)?;
        validate_digest(&parts.signer_key_sha256)
    }

    pub fn new(parts: UpdateManifestParts) -> Result<Self, PolicyError> {
        Self::validate_parts(&parts)?;
        let manifest_sha256 = Self::compute_sha256(&parts);
        Ok(Self {
            parts,
            manifest_sha256,
        })
    }

    fn validate(&self) -> Result<(), PolicyError> {
        Self::validate_parts(&self.parts)?;
        if Self::compute_sha256(&self.parts) != self.manifest_sha256 {
            return Err(PolicyError::Denied("UPDATE_MANIFEST_DIGEST_MISMATCH"));
        }
        Ok(())
    }

    pub fn target(&self) -> UpdateSlot {
        self.parts.target
    }

    pub fn version(&self) -> u64 {
        self.parts.version
    }

    pub fn rollback_index(&self) -> u64 {
        self.parts.rollback_index
    }

    pub fn image_sha256(&self) -> &str {
        &self.parts.image_sha256
    }

    pub fn sbom_sha256(&self) -> &str {
        &self.parts.sbom_sha256
    }

    pub fn provenance_sha256(&self) -> &str {
        &self.parts.provenance_sha256
    }

    pub fn manifest_sha256(&self) -> &str {
        &self.manifest_sha256
    }

    pub fn signer_key_sha256(&self) -> &str {
        &self.parts.signer_key_sha256
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateActivationParts {
    pub target: UpdateSlot,
    pub boot_generation: u64,
    pub measured_image_sha256: String,
    pub measured_manifest_sha256: String,
    pub measured_sbom_sha256: String,
    pub measured_provenance_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateActivation {
    parts: UpdateActivationParts,
    payload_sha256: String,
}

impl UpdateActivation {
    fn compute_sha256(parts: &UpdateActivationParts) -> String {
        let mut canonical = Canonical::default();
        canonical.text("target", parts.target.code());
        canonical.u64("boot_generation", parts.boot_generation);
        canonical.text("measured_image_sha256", &parts.measured_image_sha256);
        canonical.text("measured_manifest_sha256", &parts.measured_manifest_sha256);
        canonical.text("measured_sbom_sha256", &parts.measured_sbom_sha256);
        canonical.text(
            "measured_provenance_sha256",
            &parts.measured_provenance_sha256,
        );
        canonical.digest()
    }

    fn validate_parts(parts: &UpdateActivationParts) -> Result<(), PolicyError> {
        if parts.boot_generation == 0 {
            return Err(PolicyError::Invalid("INVALID_UPDATE_ACTIVATION"));
        }
        validate_digest(&parts.measured_image_sha256)?;
        validate_digest(&parts.measured_manifest_sha256)?;
        validate_digest(&parts.measured_sbom_sha256)?;
        validate_digest(&parts.measured_provenance_sha256)
    }

    pub fn new(parts: UpdateActivationParts) -> Result<Self, PolicyError> {
        Self::validate_parts(&parts)?;
        let payload_sha256 = Self::compute_sha256(&parts);
        Ok(Self {
            parts,
            payload_sha256,
        })
    }

    fn validate(&self) -> Result<(), PolicyError> {
        Self::validate_parts(&self.parts)?;
        if Self::compute_sha256(&self.parts) != self.payload_sha256 {
            return Err(PolicyError::Denied("UPDATE_ACTIVATION_DIGEST_MISMATCH"));
        }
        Ok(())
    }

    pub fn payload_sha256(&self) -> &str {
        &self.payload_sha256
    }

    pub fn boot_generation(&self) -> u64 {
        self.parts.boot_generation
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateHealthClaimParts {
    pub target: UpdateSlot,
    pub boot_generation: u64,
    pub image_sha256: String,
    pub manifest_sha256: String,
    pub measured_state_sha256: String,
    pub healthy: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateHealthClaim {
    parts: UpdateHealthClaimParts,
    payload_sha256: String,
}

impl UpdateHealthClaim {
    fn compute_sha256(parts: &UpdateHealthClaimParts) -> String {
        let mut canonical = Canonical::default();
        canonical.text("target", parts.target.code());
        canonical.u64("boot_generation", parts.boot_generation);
        canonical.text("image_sha256", &parts.image_sha256);
        canonical.text("manifest_sha256", &parts.manifest_sha256);
        canonical.text("measured_state_sha256", &parts.measured_state_sha256);
        canonical.bool("healthy", parts.healthy);
        canonical.digest()
    }

    fn validate_parts(parts: &UpdateHealthClaimParts) -> Result<(), PolicyError> {
        if parts.boot_generation == 0 {
            return Err(PolicyError::Invalid("INVALID_UPDATE_HEALTH_CLAIM"));
        }
        validate_digest(&parts.image_sha256)?;
        validate_digest(&parts.manifest_sha256)?;
        validate_digest(&parts.measured_state_sha256)
    }

    pub fn new(parts: UpdateHealthClaimParts) -> Result<Self, PolicyError> {
        Self::validate_parts(&parts)?;
        let payload_sha256 = Self::compute_sha256(&parts);
        Ok(Self {
            parts,
            payload_sha256,
        })
    }

    fn validate(&self) -> Result<(), PolicyError> {
        Self::validate_parts(&self.parts)?;
        if Self::compute_sha256(&self.parts) != self.payload_sha256 {
            return Err(PolicyError::Denied("UPDATE_HEALTH_DIGEST_MISMATCH"));
        }
        Ok(())
    }

    pub fn payload_sha256(&self) -> &str {
        &self.payload_sha256
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PendingUpdate {
    manifest: UpdateManifest,
    activated: bool,
    boot_attempts: u8,
    boot_generation: Option<u64>,
    previous: UpdateSlot,
}

impl PendingUpdate {
    pub fn manifest(&self) -> &UpdateManifest {
        &self.manifest
    }

    pub fn activated(&self) -> bool {
        self.activated
    }

    pub fn boot_attempts(&self) -> u8 {
        self.boot_attempts
    }

    pub fn boot_generation(&self) -> Option<u64> {
        self.boot_generation
    }
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
        if current_version == 0 || rollback_index == 0 || maximum_boot_attempts == 0 {
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

    pub fn current_version(&self) -> u64 {
        self.current_version
    }

    pub fn rollback_index(&self) -> u64 {
        self.rollback_index
    }

    pub fn pending(&self) -> Option<&PendingUpdate> {
        self.pending.as_ref()
    }

    pub fn stage(
        &mut self,
        registry: &TrustedVerifierRegistry,
        manifest: UpdateManifest,
        evidence: &EvidenceEnvelope,
        now_epoch: u64,
    ) -> Result<(), PolicyError> {
        manifest.validate()?;
        registry.verify(
            evidence,
            EvidenceExpectation {
                role: VerifierRole::UpdateManifest,
                subject: "update-manifest.v1",
                payload_sha256: manifest.manifest_sha256(),
                key_id: Some(manifest.signer_key_sha256()),
                now_epoch,
            },
        )?;
        if self.pending.is_some() {
            return Err(PolicyError::Conflict("UPDATE_ALREADY_PENDING"));
        }
        if manifest.target() == self.active {
            return Err(PolicyError::Denied("ACTIVE_SLOT_WRITE_FORBIDDEN"));
        }
        if manifest.version() <= self.current_version
            || manifest.rollback_index() <= self.rollback_index
        {
            return Err(PolicyError::Denied("UPDATE_DOWNGRADE_FORBIDDEN"));
        }
        self.pending = Some(PendingUpdate {
            manifest,
            activated: false,
            boot_attempts: 0,
            boot_generation: None,
            previous: self.active,
        });
        Ok(())
    }

    pub fn activate_staged(
        &mut self,
        registry: &TrustedVerifierRegistry,
        activation: &UpdateActivation,
        evidence: &EvidenceEnvelope,
        now_epoch: u64,
    ) -> Result<UpdateSlot, PolicyError> {
        activation.validate()?;
        registry.verify(
            evidence,
            EvidenceExpectation {
                role: VerifierRole::UpdateBoot,
                subject: "update-boot-measurement.v1",
                payload_sha256: activation.payload_sha256(),
                key_id: None,
                now_epoch,
            },
        )?;
        let pending = self
            .pending
            .as_mut()
            .ok_or(PolicyError::Denied("NO_STAGED_UPDATE"))?;
        if pending.activated {
            return Err(PolicyError::Conflict("UPDATE_ALREADY_ACTIVATED"));
        }
        if activation.parts.target != pending.manifest.target()
            || activation.parts.measured_image_sha256 != pending.manifest.image_sha256()
            || activation.parts.measured_manifest_sha256 != pending.manifest.manifest_sha256()
            || activation.parts.measured_sbom_sha256 != pending.manifest.sbom_sha256()
            || activation.parts.measured_provenance_sha256 != pending.manifest.provenance_sha256()
        {
            return Err(PolicyError::Denied("UPDATE_BOOT_MEASUREMENT_MISMATCH"));
        }
        pending.activated = true;
        pending.boot_generation = Some(activation.boot_generation());
        self.active = pending.manifest.target();
        Ok(self.active)
    }

    pub fn record_boot_failure(&mut self, boot_generation: u64) -> Result<UpdateSlot, PolicyError> {
        let (must_rollback, previous) = {
            let pending = self
                .pending
                .as_mut()
                .ok_or(PolicyError::Denied("NO_PENDING_BOOT"))?;
            if !pending.activated {
                return Err(PolicyError::Denied("UPDATE_NOT_ACTIVATED"));
            }
            if pending.boot_generation != Some(boot_generation) {
                return Err(PolicyError::Stale("UPDATE_BOOT_GENERATION_MISMATCH"));
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

    pub fn confirm_healthy(
        &mut self,
        registry: &TrustedVerifierRegistry,
        claim: &UpdateHealthClaim,
        evidence: &EvidenceEnvelope,
        now_epoch: u64,
    ) -> Result<(), PolicyError> {
        claim.validate()?;
        registry.verify(
            evidence,
            EvidenceExpectation {
                role: VerifierRole::UpdateHealth,
                subject: "update-health.v1",
                payload_sha256: claim.payload_sha256(),
                key_id: None,
                now_epoch,
            },
        )?;
        let pending = self
            .pending
            .as_ref()
            .ok_or(PolicyError::Denied("NO_PENDING_BOOT"))?;
        if !pending.activated
            || self.active != pending.manifest.target()
            || pending.boot_generation != Some(claim.parts.boot_generation)
            || claim.parts.target != pending.manifest.target()
            || claim.parts.image_sha256 != pending.manifest.image_sha256()
            || claim.parts.manifest_sha256 != pending.manifest.manifest_sha256()
            || !claim.parts.healthy
        {
            return Err(PolicyError::Denied("UPDATE_HEALTH_BINDING_MISMATCH"));
        }
        let pending = self
            .pending
            .take()
            .ok_or(PolicyError::Denied("NO_PENDING_BOOT"))?;
        self.current_version = pending.manifest.version();
        self.rollback_index = pending.manifest.rollback_index();
        self.healthy = pending.manifest.target();
        Ok(())
    }

    pub(crate) fn state_sha256(&self) -> String {
        let mut canonical = Canonical::default();
        canonical.text("active", self.active.code());
        canonical.text("healthy", self.healthy.code());
        canonical.u64("current_version", self.current_version);
        canonical.u64("rollback_index", self.rollback_index);
        canonical.u8("maximum_boot_attempts", self.maximum_boot_attempts);
        if let Some(pending) = self.pending.as_ref() {
            canonical.text("pending_manifest", pending.manifest.manifest_sha256());
            canonical.bool("pending_activated", pending.activated);
            canonical.u8("pending_boot_attempts", pending.boot_attempts);
            canonical.u64(
                "pending_boot_generation",
                pending.boot_generation.unwrap_or_default(),
            );
            canonical.text("pending_previous", pending.previous.code());
        } else {
            canonical.text("pending_manifest", "");
        }
        canonical.digest()
    }
}

#[derive(Debug, Clone)]
#[cfg(test)]
struct NetworkFixtureBundle {
    permit: CapabilityPermit,
    resource: NetworkResource,
    request: NetworkRequest,
    observation: NetworkObservation,
}

#[cfg(test)]
fn issue_fixture(
    registry: &TrustedVerifierRegistry,
    verifier_id: &str,
    subject: &str,
    payload_sha256: &str,
    nonce: &str,
) -> EvidenceEnvelope {
    registry
        .issue(EvidenceIssue {
            verifier_id,
            subject,
            payload_sha256,
            not_before_epoch: 90,
            expires_at_epoch: 120,
            nonce,
        })
        .expect("internal fixture evidence is valid")
}

#[cfg(test)]
fn network_fixture_bundle(registry: &TrustedVerifierRegistry) -> NetworkFixtureBundle {
    let placeholder = sha256_hex(b"placeholder");
    let placeholder_evidence = issue_fixture(
        registry,
        "fixture-capability-issuer",
        "capability-permit.v2",
        &placeholder,
        "placeholder-capability",
    );
    let mut permit = CapabilityPermit {
        permit_id: "permit-self-check".to_owned(),
        subject: "taskflow:self-check".to_owned(),
        audience: Audience::Network,
        resource_id: "network:example".to_owned(),
        action: "http_request".to_owned(),
        not_before_epoch: 90,
        expires_at_epoch: 120,
        nonce: "nonce-self-check".to_owned(),
        maximum_uses: 2,
        revoked: false,
        evidence: placeholder_evidence,
    };
    let permit_sha256 = permit
        .payload_sha256()
        .expect("fixture permit payload is valid");
    permit.evidence = issue_fixture(
        registry,
        "fixture-capability-issuer",
        "capability-permit.v2",
        &permit_sha256,
        "capability-self-check",
    );
    let request = NetworkRequest {
        subject: permit.subject.clone(),
        origin: "https://example.com:443".to_owned(),
        action: permit.action.clone(),
        method: "POST".to_owned(),
        payload_sha256: "9".repeat(64),
        context: NetworkContext::TopLevel,
        redirect_count: 0,
    };
    let resource = NetworkResource {
        resource_id: permit.resource_id.clone(),
        allowed_origins: BTreeSet::from([request.origin.clone()]),
        allowed_contexts: BTreeSet::from([NetworkContext::TopLevel]),
        proxy_id: "egress-proxy".to_owned(),
        maximum_redirects: 2,
    };
    let request_sha256 = request
        .request_sha256()
        .expect("fixture request payload is valid");
    let peer = IpAddr::V4(Ipv4Addr::new(93, 184, 216, 34));
    let placeholder_observation = issue_fixture(
        registry,
        "fixture-network-observer",
        "network-observation.v1",
        &placeholder,
        "placeholder-observation",
    );
    let mut observation = NetworkObservation {
        request_sha256,
        permit_sha256,
        resolver_id: "resolver-self-check".to_owned(),
        dns_generation: 3,
        resolved_addresses: vec![peer],
        connected_peer: peer,
        proxy_id: resource.proxy_id.clone(),
        direct_connection: false,
        tls_verified: true,
        tls_intercepted: false,
        tls_peer_spki_sha256: "8".repeat(64),
        observed_at_epoch: 100,
        evidence: placeholder_observation,
    };
    let observation_sha256 = observation
        .observation_sha256()
        .expect("fixture observation payload is valid");
    observation.evidence = issue_fixture(
        registry,
        "fixture-network-observer",
        "network-observation.v1",
        &observation_sha256,
        "observation-self-check",
    );
    NetworkFixtureBundle {
        permit,
        resource,
        request,
        observation,
    }
}

#[cfg(test)]
pub(crate) struct TestNetworkBundle {
    pub permit: CapabilityPermit,
    pub resource: NetworkResource,
    pub request: NetworkRequest,
    pub observation: NetworkObservation,
}

#[cfg(test)]
pub(crate) fn test_network_bundle(registry: &TrustedVerifierRegistry) -> TestNetworkBundle {
    let fixture = network_fixture_bundle(registry);
    TestNetworkBundle {
        permit: fixture.permit,
        resource: fixture.resource,
        request: fixture.request,
        observation: fixture.observation,
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
    let mut collaboration = CollaborationController::default();
    collaboration.gain_human_focus("human-self-check", 10, 100)?;
    let human = Actor::human("human-self-check")?;
    collaboration.begin_ime(human.clone(), 11)?;
    collaboration.compare_and_swap_clipboard(&human, 0, &"7".repeat(64), 12)?;
    collaboration.end_ime(&human)?;
    collaboration.release_human_focus("human-self-check")?;

    let closed_registry = TrustedVerifierRegistry::closed();
    let manifest = TrustedAppManifest {
        app_id: "calculator".to_owned(),
        publisher_id: "trillionnium".to_owned(),
        publisher_key_sha256: "a".repeat(64),
        version: 1,
        origin: "https://calculator.trillionnium.apps.hepta.invalid".to_owned(),
        content_root_sha256: "6".repeat(64),
        csp: ClosedCsp::strict(),
        service_worker_scope: Some("/app/".to_owned()),
        revoked: false,
    };
    let manifest_payload = manifest.payload_sha256()?;
    let untrusted = EvidenceEnvelope::parse(EvidenceEnvelopeParts {
        verifier_id: "untrusted-self-check".to_owned(),
        key_id: "a".repeat(64),
        role: VerifierRole::Publisher,
        trust_generation: 1,
        revocation_generation: 1,
        subject: "trusted-app-manifest.v2".to_owned(),
        payload_sha256: manifest_payload,
        not_before_epoch: 90,
        expires_at_epoch: 120,
        nonce: "closed-registry-self-check".to_owned(),
        signature: [1_u8; 64],
    })?;
    if TrustedAppPolicy::admit(&closed_registry, &manifest, &untrusted, None, None, 100).is_ok() {
        return Err(PolicyError::Invalid("CLOSED_REGISTRY_ACCEPTED_EVIDENCE"));
    }

    canonical_https_origin("https://example.com:443")?;
    if canonical_https_origin("https://Example.com:443").is_ok() {
        return Err(PolicyError::Invalid(
            "ORIGIN_CANONICALIZER_SELF_CHECK_FAILED",
        ));
    }

    let decision = NetworkDecision {
        permit_id: "permit-self-check".to_owned(),
        permit_use_ordinal: 1,
        subject: "taskflow:self-check".to_owned(),
        resource_id: "network:example".to_owned(),
        action: "http_request".to_owned(),
        method: "POST".to_owned(),
        payload_sha256: "9".repeat(64),
        origin: "https://example.com:443".to_owned(),
        connected_peer: IpAddr::V4(Ipv4Addr::new(93, 184, 216, 34)),
        request_sha256: "8".repeat(64),
        observation_sha256: "7".repeat(64),
        authority_generation: 3,
    };
    let command =
        EffectCommand::from_network("effect-self-check", "idempotency-self-check", &decision)?;
    let mut effects = EffectJournal::default();
    effects.request(command.clone())?;
    effects.prepare(command.effect_id(), command.command_sha256())?;
    effects.mark_dispatched(command.effect_id(), command.command_sha256())?;
    effects.reconcile(
        command.effect_id(),
        command.command_sha256(),
        "provider-self-check",
        1,
        ProviderObservation::Unknown,
    )?;
    if effects.automatic_replay_allowed(command.effect_id())
        || EffectJournal::restore(&effects.encode())? != effects
    {
        return Err(PolicyError::Invalid("EFFECT_JOURNAL_SELF_CHECK_FAILED"));
    }

    let update_manifest = UpdateManifest::new(UpdateManifestParts {
        target: UpdateSlot::B,
        version: 2,
        rollback_index: 2,
        image_sha256: "2".repeat(64),
        image_bytes: 4096,
        sbom_sha256: "3".repeat(64),
        provenance_sha256: "4".repeat(64),
        source_commit_sha256: "5".repeat(64),
        signer_key_sha256: "d".repeat(64),
    })?;
    let update_evidence = EvidenceEnvelope::parse(EvidenceEnvelopeParts {
        verifier_id: "untrusted-update-self-check".to_owned(),
        key_id: "d".repeat(64),
        role: VerifierRole::UpdateManifest,
        trust_generation: 1,
        revocation_generation: 1,
        subject: "update-manifest.v1".to_owned(),
        payload_sha256: update_manifest.manifest_sha256().to_owned(),
        not_before_epoch: 90,
        expires_at_epoch: 120,
        nonce: "closed-update-self-check".to_owned(),
        signature: [1_u8; 64],
    })?;
    let mut update = UpdateController::new(UpdateSlot::A, 1, 1, 2)?;
    if update
        .stage(&closed_registry, update_manifest, &update_evidence, 100)
        .is_ok()
    {
        return Err(PolicyError::Invalid(
            "CLOSED_UPDATE_REGISTRY_ACCEPTED_EVIDENCE",
        ));
    }

    Ok(ProductPolicySelfCheck {
        checks_run: 5,
        external_effect_authority: false,
        private_key_authority: false,
        hardware_qualified: false,
        release_ready: false,
    })
}
#[cfg(test)]
mod tests {
    use super::*;

    fn evidence(
        registry: &TrustedVerifierRegistry,
        verifier_id: &str,
        subject: &str,
        payload_sha256: &str,
        nonce: &str,
    ) -> EvidenceEnvelope {
        issue_fixture(registry, verifier_id, subject, payload_sha256, nonce)
    }

    fn fixture_key_id(registry: &TrustedVerifierRegistry, verifier_id: &str) -> String {
        registry
            .key_id(verifier_id)
            .expect("fixture verifier is enrolled")
            .to_owned()
    }

    #[test]
    fn human_authority_is_bound_to_the_exact_live_lease() {
        let mut controller = CollaborationController::default();
        controller
            .gain_human_focus("lease-live", 100, 50)
            .expect("valid lease");
        let live = Actor::human("lease-live").expect("valid actor");
        let wrong = Actor::human("lease-stolen").expect("valid actor shape");
        let target = controller.reference("node", "root").expect("target");
        assert_eq!(
            controller
                .validate_target(&wrong, &target, 101)
                .expect_err("wrong lease cannot reuse human authority")
                .code(),
            "HUMAN_LEASE_MISMATCH"
        );
        assert_eq!(
            controller
                .begin_ime(wrong.clone(), 101)
                .expect_err("wrong lease cannot own IME")
                .code(),
            "HUMAN_LEASE_MISMATCH"
        );
        assert_eq!(
            controller
                .compare_and_swap_clipboard(&wrong, 0, &"2".repeat(64), 101)
                .expect_err("wrong lease cannot write clipboard")
                .code(),
            "HUMAN_LEASE_MISMATCH"
        );
        controller
            .start_drag(live.clone(), target.clone(), 101)
            .expect("live lease can drag");
        assert_eq!(
            controller
                .finish_drag(&wrong, &target, 101)
                .expect_err("wrong lease cannot finish another lease drag")
                .code(),
            "HUMAN_LEASE_MISMATCH"
        );
        controller
            .finish_drag(&live, &target, 101)
            .expect("live lease can finish its drag");
    }

    #[test]
    fn evidence_rejects_tamper_subject_generation_and_freshness() {
        let registry = fixture_registry();
        let payload = "2".repeat(64);
        let valid = evidence(
            &registry,
            "fixture-publisher",
            "trusted-app-manifest.v2",
            &payload,
            "evidence-valid",
        );
        let publisher_key_id = fixture_key_id(&registry, "fixture-publisher");
        registry
            .verify(
                &valid,
                EvidenceExpectation {
                    role: VerifierRole::Publisher,
                    subject: "trusted-app-manifest.v2",
                    payload_sha256: &payload,
                    key_id: Some(&publisher_key_id),
                    now_epoch: 100,
                },
            )
            .expect("valid evidence");

        let mut tampered = valid.clone();
        tampered.parts.payload_sha256 = "3".repeat(64);
        assert_eq!(
            registry
                .verify(
                    &tampered,
                    EvidenceExpectation {
                        role: VerifierRole::Publisher,
                        subject: "trusted-app-manifest.v2",
                        payload_sha256: &"3".repeat(64),
                        key_id: None,
                        now_epoch: 100,
                    },
                )
                .expect_err("signature must bind payload")
                .code(),
            "EVIDENCE_AUTHENTICATION_FAILED"
        );
        assert_eq!(
            registry
                .verify(
                    &valid,
                    EvidenceExpectation {
                        role: VerifierRole::Publisher,
                        subject: "other-subject.v1",
                        payload_sha256: &payload,
                        key_id: None,
                        now_epoch: 100,
                    },
                )
                .expect_err("subject mismatch")
                .code(),
            "EVIDENCE_BINDING_MISMATCH"
        );
        let mut stale_generation = valid.clone();
        stale_generation.parts.revocation_generation -= 1;
        assert_eq!(
            registry
                .verify(
                    &stale_generation,
                    EvidenceExpectation {
                        role: VerifierRole::Publisher,
                        subject: "trusted-app-manifest.v2",
                        payload_sha256: &payload,
                        key_id: None,
                        now_epoch: 100,
                    },
                )
                .expect_err("generation mismatch")
                .code(),
            "EVIDENCE_REGISTRY_GENERATION_STALE"
        );
        assert_eq!(
            registry
                .verify(
                    &valid,
                    EvidenceExpectation {
                        role: VerifierRole::Publisher,
                        subject: "trusted-app-manifest.v2",
                        payload_sha256: &payload,
                        key_id: None,
                        now_epoch: 121,
                    },
                )
                .expect_err("expired evidence")
                .code(),
            "EVIDENCE_OUTSIDE_VALIDITY"
        );
    }

    #[test]
    fn trusted_app_rotation_requires_old_key_authenticated_evidence() {
        let registry = fixture_registry();
        let initial = TrustedAppManifest {
            app_id: "notes".to_owned(),
            publisher_id: "publisher".to_owned(),
            publisher_key_sha256: fixture_key_id(&registry, "fixture-publisher"),
            version: 1,
            origin: "https://notes.publisher.apps.hepta.invalid".to_owned(),
            content_root_sha256: "2".repeat(64),
            csp: ClosedCsp::strict(),
            service_worker_scope: None,
            revoked: false,
        };
        let initial_evidence = evidence(
            &registry,
            "fixture-publisher",
            "trusted-app-manifest.v2",
            &initial.payload_sha256().expect("payload"),
            "initial-manifest",
        );
        let installed =
            TrustedAppPolicy::admit(&registry, &initial, &initial_evidence, None, None, 100)
                .expect("initial install");

        let rotated = TrustedAppManifest {
            publisher_key_sha256: fixture_key_id(&registry, "fixture-publisher-next"),
            version: 2,
            content_root_sha256: "3".repeat(64),
            ..initial
        };
        let rotated_evidence = evidence(
            &registry,
            "fixture-publisher-next",
            "trusted-app-manifest.v2",
            &rotated.payload_sha256().expect("rotated payload"),
            "rotated-manifest",
        );
        assert_eq!(
            TrustedAppPolicy::admit(
                &registry,
                &rotated,
                &rotated_evidence,
                None,
                Some(&installed),
                100,
            )
            .expect_err("rotation without predecessor proof")
            .code(),
            "PUBLISHER_ROTATION_NOT_AUTHORIZED"
        );
        let rotation_payload = TrustedAppPolicy::rotation_payload_sha256(&installed, &rotated);
        let rotation = evidence(
            &registry,
            "fixture-publisher",
            "trusted-app-key-rotation.v1",
            &rotation_payload,
            "rotation-proof",
        );
        TrustedAppPolicy::admit(
            &registry,
            &rotated,
            &rotated_evidence,
            Some(&rotation),
            Some(&installed),
            100,
        )
        .expect("old key authorizes new key");
    }

    #[test]
    fn network_observation_is_authenticated_and_exactly_bound() {
        let registry = fixture_registry();
        let fixture = network_fixture_bundle(&registry);
        let mut ledger = CapabilityLedger::default();
        let decision = ledger
            .authorize_network(
                &registry,
                &fixture.permit,
                &fixture.resource,
                &fixture.request,
                &fixture.observation,
                100,
            )
            .expect("valid observation");
        assert_eq!(decision.permit_use_ordinal(), 1);

        let mut mismatched = fixture.observation.clone();
        mismatched.connected_peer = IpAddr::V4(Ipv4Addr::new(1, 1, 1, 1));
        assert_eq!(
            CapabilityLedger::default()
                .authorize_network(
                    &registry,
                    &fixture.permit,
                    &fixture.resource,
                    &fixture.request,
                    &mismatched,
                    100,
                )
                .expect_err("observation evidence binds peer")
                .code(),
            "EVIDENCE_BINDING_MISMATCH"
        );

        let mut stale = fixture.observation.clone();
        stale.observed_at_epoch = 1;
        assert_eq!(
            CapabilityLedger::default()
                .authorize_network(
                    &registry,
                    &fixture.permit,
                    &fixture.resource,
                    &fixture.request,
                    &stale,
                    100,
                )
                .expect_err("stale observation")
                .code(),
            "NETWORK_OBSERVATION_STALE"
        );
    }

    #[test]
    fn origin_canonicalizer_rejects_ambiguous_authorities() {
        for origin in [
            "https://example.com",
            "https://Example.com:443",
            "https://user@example.com:443",
            "https://example.com:443/path",
            "https://127.0.0.1:443",
            "https://exa_mple.com:443",
            "https://例子.example:443",
        ] {
            assert_eq!(
                canonical_https_origin(origin)
                    .expect_err("ambiguous origin must fail")
                    .code(),
                "NETWORK_ORIGIN_NOT_CANONICAL"
            );
        }
        canonical_https_origin("https://example.com:443").expect("canonical origin");
    }

    #[test]
    fn effect_journal_round_trips_and_rejects_tamper() {
        let registry = fixture_registry();
        let fixture = network_fixture_bundle(&registry);
        let decision = CapabilityLedger::default()
            .authorize_network(
                &registry,
                &fixture.permit,
                &fixture.resource,
                &fixture.request,
                &fixture.observation,
                100,
            )
            .expect("decision");
        let command =
            EffectCommand::from_network("effect-1", "idempotency-1", &decision).expect("command");
        let mut journal = EffectJournal::default();
        journal.request(command.clone()).expect("request");
        journal
            .prepare(command.effect_id(), command.command_sha256())
            .expect("prepare");
        journal
            .mark_dispatched(command.effect_id(), command.command_sha256())
            .expect("dispatch");
        journal
            .reconcile(
                command.effect_id(),
                command.command_sha256(),
                "provider-1",
                1,
                ProviderObservation::Unknown,
            )
            .expect("reconcile");
        let encoded = journal.encode();
        assert_eq!(EffectJournal::restore(&encoded).expect("restore"), journal);
        let tampered = encoded.replacen("provider-1", "provider-2", 1);
        assert_eq!(
            EffectJournal::restore(&tampered)
                .expect_err("tamper must break record hash")
                .code(),
            "EFFECT_JOURNAL_RECORD_DIGEST_MISMATCH"
        );
        assert!(!journal.automatic_replay_allowed(command.effect_id()));
    }

    fn signed_update_fixture(
        registry: &TrustedVerifierRegistry,
    ) -> (
        UpdateManifest,
        EvidenceEnvelope,
        UpdateActivation,
        EvidenceEnvelope,
        UpdateHealthClaim,
        EvidenceEnvelope,
    ) {
        let manifest = UpdateManifest::new(UpdateManifestParts {
            target: UpdateSlot::B,
            version: 2,
            rollback_index: 6,
            image_sha256: "2".repeat(64),
            image_bytes: 4096,
            sbom_sha256: "3".repeat(64),
            provenance_sha256: "4".repeat(64),
            source_commit_sha256: "5".repeat(64),
            signer_key_sha256: fixture_key_id(registry, "fixture-update-manifest"),
        })
        .expect("manifest");
        let manifest_evidence = evidence(
            registry,
            "fixture-update-manifest",
            "update-manifest.v1",
            manifest.manifest_sha256(),
            "update-manifest",
        );
        let activation = UpdateActivation::new(UpdateActivationParts {
            target: UpdateSlot::B,
            boot_generation: 17,
            measured_image_sha256: manifest.image_sha256().to_owned(),
            measured_manifest_sha256: manifest.manifest_sha256().to_owned(),
            measured_sbom_sha256: manifest.sbom_sha256().to_owned(),
            measured_provenance_sha256: manifest.provenance_sha256().to_owned(),
        })
        .expect("activation");
        let activation_evidence = evidence(
            registry,
            "fixture-update-boot",
            "update-boot-measurement.v1",
            activation.payload_sha256(),
            "update-activation",
        );
        let health = UpdateHealthClaim::new(UpdateHealthClaimParts {
            target: UpdateSlot::B,
            boot_generation: 17,
            image_sha256: manifest.image_sha256().to_owned(),
            manifest_sha256: manifest.manifest_sha256().to_owned(),
            measured_state_sha256: "6".repeat(64),
            healthy: true,
        })
        .expect("health");
        let health_evidence = evidence(
            registry,
            "fixture-update-health",
            "update-health.v1",
            health.payload_sha256(),
            "update-health",
        );
        (
            manifest,
            manifest_evidence,
            activation,
            activation_evidence,
            health,
            health_evidence,
        )
    }

    #[test]
    fn update_requires_exact_boot_and_signed_health_identity() {
        let registry = fixture_registry();
        let (manifest, manifest_evidence, activation, activation_evidence, health, health_evidence) =
            signed_update_fixture(&registry);
        let mut update = UpdateController::new(UpdateSlot::A, 1, 5, 2).expect("baseline");
        update
            .stage(&registry, manifest, &manifest_evidence, 100)
            .expect("stage");
        update
            .activate_staged(&registry, &activation, &activation_evidence, 100)
            .expect("activate");
        assert_eq!(
            update
                .record_boot_failure(16)
                .expect_err("wrong boot generation")
                .code(),
            "UPDATE_BOOT_GENERATION_MISMATCH"
        );
        let mut wrong_health = health.clone();
        wrong_health.parts.measured_state_sha256 = "7".repeat(64);
        assert_eq!(
            update
                .confirm_healthy(&registry, &wrong_health, &health_evidence, 100)
                .expect_err("claim tamper invalidates evidence")
                .code(),
            "UPDATE_HEALTH_DIGEST_MISMATCH"
        );
        update
            .confirm_healthy(&registry, &health, &health_evidence, 100)
            .expect("health confirmation");
        assert_eq!(update.rollback_index(), 6);
        assert_eq!(update.healthy_slot(), UpdateSlot::B);
    }

    #[test]
    fn self_check_keeps_all_external_authority_closed() {
        let report = run_self_check().expect("self-check");
        assert_eq!(report.checks_run, 5);
        assert!(!report.external_effect_authority);
        assert!(!report.private_key_authority);
        assert!(!report.hardware_qualified);
        assert!(!report.release_ready);
    }
}
