//! Deterministic D4-D7 authority coordination.
//!
//! Every transition is preflighted, applied to a staged clone, and committed
//! together with a hash-chained receipt. A policy error may append a denial
//! receipt, but it never commits partially-mutated domain state. Invalid
//! operation identity or receipt-sequence exhaustion changes neither state nor
//! receipts.
//!
//! This module owns no file descriptor, socket, resolver, proxy, device,
//! credential, bootloader handle, signing key, or external-effect executor.

use crate::product_policy::{
    Actor, CapabilityLedger, CapabilityPermit, CollaborationController, EffectCommand,
    EffectJournal, EffectState, EvidenceEnvelope, NetworkDecision, NetworkObservation,
    NetworkRequest, NetworkResource, PolicyError, ProviderObservation, TargetReference,
    TrustedVerifierRegistry, UpdateActivation, UpdateController, UpdateHealthClaim, UpdateManifest,
    UpdateSlot,
};
use sha2::{Digest, Sha256};
use std::sync::Arc;

const EMPTY_RECEIPT_SHA256: &str =
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PolicyDomain {
    Collaboration,
    Network,
    Effect,
    Update,
}

impl PolicyDomain {
    const fn code(self) -> &'static str {
        match self {
            Self::Collaboration => "collaboration",
            Self::Network => "network",
            Self::Effect => "effect",
            Self::Update => "update",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyReceiptOutcome {
    Allowed,
    Denied(&'static str),
    EffectState(EffectState),
    UpdateSlot(UpdateSlot),
}

impl PolicyReceiptOutcome {
    fn code(&self) -> String {
        match self {
            Self::Allowed => "allowed".to_owned(),
            Self::Denied(code) => format!("denied:{code}"),
            Self::EffectState(state) => format!("effect:{state:?}"),
            Self::UpdateSlot(slot) => format!("update:{slot:?}"),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PolicyReceipt {
    pub sequence: u64,
    pub domain: PolicyDomain,
    pub operation_id: String,
    pub outcome: PolicyReceiptOutcome,
    pub before_state_sha256: String,
    pub after_state_sha256: String,
    pub command_sha256: Option<String>,
    pub provider_id: Option<String>,
    /// True once control crossed the injected backend boundary, regardless of
    /// whether the provider later proved the effect was applied.
    pub external_effect_attempted: bool,
    /// True only for a provider observation cryptographically and structurally
    /// bound to this command with an `Applied` outcome.
    pub external_effect_executed: bool,
    pub previous_receipt_sha256: String,
    pub receipt_sha256: String,
}

/// Write-ahead receipt boundary for authority-state commits.
///
/// `append` is invoked on the fully formed receipt before the coordinator
/// publishes the staged in-memory state. A production implementation must
/// durably append or return an error; returning success without durability is
/// suitable only for source/self-check execution and carries no persistence
/// claim.
pub trait PolicyReceiptSink: std::fmt::Debug + Send + Sync {
    fn append(&self, receipt: &PolicyReceipt) -> Result<(), PolicyError>;
}

#[derive(Debug, Default)]
struct SourceOnlyReceiptSink;

impl PolicyReceiptSink for SourceOnlyReceiptSink {
    fn append(&self, _receipt: &PolicyReceipt) -> Result<(), PolicyError> {
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct AuthorityCoordinator {
    collaboration: CollaborationController,
    capabilities: CapabilityLedger,
    effects: EffectJournal,
    updates: UpdateController,
    receipts: Vec<PolicyReceipt>,
    next_sequence: u64,
    receipt_head_sha256: String,
    receipt_sink: Arc<dyn PolicyReceiptSink>,
}

impl PartialEq for AuthorityCoordinator {
    fn eq(&self, other: &Self) -> bool {
        self.collaboration == other.collaboration
            && self.capabilities == other.capabilities
            && self.effects == other.effects
            && self.updates == other.updates
            && self.receipts == other.receipts
            && self.next_sequence == other.next_sequence
            && self.receipt_head_sha256 == other.receipt_head_sha256
    }
}

impl Eq for AuthorityCoordinator {}

struct TransactionSuccess<T> {
    value: T,
    outcome: PolicyReceiptOutcome,
    command_sha256: Option<String>,
    provider_id: Option<String>,
    external_effect_attempted: bool,
    external_effect_executed: bool,
}

impl<T> TransactionSuccess<T> {
    fn allowed(value: T) -> Self {
        Self {
            value,
            outcome: PolicyReceiptOutcome::Allowed,
            command_sha256: None,
            provider_id: None,
            external_effect_attempted: false,
            external_effect_executed: false,
        }
    }

    fn effect(
        value: T,
        state: EffectState,
        command_sha256: &str,
        provider_id: Option<&str>,
        external_effect_attempted: bool,
        external_effect_executed: bool,
    ) -> Self {
        Self {
            value,
            outcome: PolicyReceiptOutcome::EffectState(state),
            command_sha256: Some(command_sha256.to_owned()),
            provider_id: provider_id.map(str::to_owned),
            external_effect_attempted,
            external_effect_executed,
        }
    }

    fn update(value: T, slot: UpdateSlot) -> Self {
        Self {
            value,
            outcome: PolicyReceiptOutcome::UpdateSlot(slot),
            command_sha256: None,
            provider_id: None,
            external_effect_attempted: false,
            external_effect_executed: false,
        }
    }
}

impl AuthorityCoordinator {
    pub fn new(
        active_slot: UpdateSlot,
        current_version: u64,
        rollback_index: u64,
        maximum_boot_attempts: u8,
    ) -> Result<Self, PolicyError> {
        Self::with_receipt_sink(
            active_slot,
            current_version,
            rollback_index,
            maximum_boot_attempts,
            Arc::new(SourceOnlyReceiptSink),
        )
    }

    pub fn with_receipt_sink(
        active_slot: UpdateSlot,
        current_version: u64,
        rollback_index: u64,
        maximum_boot_attempts: u8,
        receipt_sink: Arc<dyn PolicyReceiptSink>,
    ) -> Result<Self, PolicyError> {
        Ok(Self {
            collaboration: CollaborationController::default(),
            capabilities: CapabilityLedger::default(),
            effects: EffectJournal::default(),
            updates: UpdateController::new(
                active_slot,
                current_version,
                rollback_index,
                maximum_boot_attempts,
            )?,
            receipts: Vec::new(),
            next_sequence: 1,
            receipt_head_sha256: EMPTY_RECEIPT_SHA256.to_owned(),
            receipt_sink,
        })
    }

    pub fn collaboration(&self) -> &CollaborationController {
        &self.collaboration
    }

    pub fn capabilities(&self) -> &CapabilityLedger {
        &self.capabilities
    }

    pub fn effects(&self) -> &EffectJournal {
        &self.effects
    }

    pub fn updates(&self) -> &UpdateController {
        &self.updates
    }

    pub fn receipts(&self) -> &[PolicyReceipt] {
        &self.receipts
    }

    pub fn receipt_head_sha256(&self) -> &str {
        &self.receipt_head_sha256
    }

    pub fn state_sha256(&self) -> String {
        hash_fields(&[
            ("collaboration", self.collaboration.state_sha256()),
            ("capabilities", self.capabilities.state_sha256()),
            ("effects", self.effects.state_sha256()),
            ("updates", self.updates.state_sha256()),
        ])
    }

    pub fn gain_human_focus(
        &mut self,
        operation_id: &str,
        lease_id: &str,
        now_ms: u64,
        ttl_ms: u64,
    ) -> Result<(), PolicyError> {
        self.transact(operation_id, PolicyDomain::Collaboration, |staged| {
            staged
                .collaboration
                .gain_human_focus(lease_id, now_ms, ttl_ms)?;
            Ok(TransactionSuccess::allowed(()))
        })
    }

    pub fn release_human_focus(
        &mut self,
        operation_id: &str,
        lease_id: &str,
    ) -> Result<(), PolicyError> {
        self.transact(operation_id, PolicyDomain::Collaboration, |staged| {
            staged.collaboration.release_human_focus(lease_id)?;
            Ok(TransactionSuccess::allowed(()))
        })
    }

    pub fn begin_ime(
        &mut self,
        operation_id: &str,
        actor: Actor,
        now_ms: u64,
    ) -> Result<(), PolicyError> {
        self.transact(operation_id, PolicyDomain::Collaboration, move |staged| {
            staged.collaboration.begin_ime(actor, now_ms)?;
            Ok(TransactionSuccess::allowed(()))
        })
    }

    pub fn validate_target(
        &mut self,
        operation_id: &str,
        actor: &Actor,
        target: &TargetReference,
        now_ms: u64,
    ) -> Result<(), PolicyError> {
        self.transact(operation_id, PolicyDomain::Collaboration, |staged| {
            staged
                .collaboration
                .validate_target(actor, target, now_ms)?;
            Ok(TransactionSuccess::allowed(()))
        })
    }

    pub fn compare_and_swap_clipboard(
        &mut self,
        operation_id: &str,
        actor: &Actor,
        expected_version: u64,
        new_sha256: &str,
        now_ms: u64,
    ) -> Result<u64, PolicyError> {
        self.transact(operation_id, PolicyDomain::Collaboration, |staged| {
            let version = staged.collaboration.compare_and_swap_clipboard(
                actor,
                expected_version,
                new_sha256,
                now_ms,
            )?;
            Ok(TransactionSuccess::allowed(version))
        })
    }

    #[allow(clippy::too_many_arguments)]
    pub fn authorize_and_prepare_network_effect(
        &mut self,
        operation_id: &str,
        effect_id: &str,
        idempotency_key: &str,
        registry: &TrustedVerifierRegistry,
        permit: &CapabilityPermit,
        resource: &NetworkResource,
        request: &NetworkRequest,
        observation: &NetworkObservation,
        now_epoch: u64,
    ) -> Result<(NetworkDecision, EffectCommand), PolicyError> {
        self.transact(operation_id, PolicyDomain::Network, |staged| {
            let decision = staged.capabilities.authorize_network(
                registry,
                permit,
                resource,
                request,
                observation,
                now_epoch,
            )?;
            let command = EffectCommand::from_network(effect_id, idempotency_key, &decision)?;
            staged.effects.request(command.clone())?;
            staged
                .effects
                .prepare(command.effect_id(), command.command_sha256())?;
            Ok(TransactionSuccess {
                value: (decision, command.clone()),
                outcome: PolicyReceiptOutcome::Allowed,
                command_sha256: Some(command.command_sha256().to_owned()),
                provider_id: None,
                external_effect_attempted: false,
                external_effect_executed: false,
            })
        })
    }

    pub fn mark_effect_dispatched(
        &mut self,
        operation_id: &str,
        effect_id: &str,
        command_sha256: &str,
    ) -> Result<(), PolicyError> {
        self.transact(operation_id, PolicyDomain::Effect, |staged| {
            staged.effects.mark_dispatched(effect_id, command_sha256)?;
            Ok(TransactionSuccess::effect(
                (),
                EffectState::Dispatched,
                command_sha256,
                None,
                false,
                false,
            ))
        })
    }

    pub fn cancel_effect_before_dispatch(
        &mut self,
        operation_id: &str,
        effect_id: &str,
        command_sha256: &str,
    ) -> Result<(), PolicyError> {
        self.transact(operation_id, PolicyDomain::Effect, |staged| {
            staged
                .effects
                .cancel_before_dispatch(effect_id, command_sha256)?;
            Ok(TransactionSuccess::effect(
                (),
                EffectState::Cancelled,
                command_sha256,
                None,
                false,
                false,
            ))
        })
    }

    pub fn record_external_observation(
        &mut self,
        operation_id: &str,
        effect_id: &str,
        command_sha256: &str,
        provider_id: &str,
        attempt: u32,
        observation: ProviderObservation,
    ) -> Result<EffectState, PolicyError> {
        self.transact(operation_id, PolicyDomain::Effect, |staged| {
            let state = staged.effects.reconcile(
                effect_id,
                command_sha256,
                provider_id,
                attempt,
                observation,
            )?;
            Ok(TransactionSuccess::effect(
                state,
                state,
                command_sha256,
                Some(provider_id),
                true,
                matches!(observation, ProviderObservation::Applied),
            ))
        })
    }

    pub fn automatic_effect_replay_allowed(&self, effect_id: &str) -> bool {
        self.effects.automatic_replay_allowed(effect_id)
    }

    pub fn stage_update(
        &mut self,
        operation_id: &str,
        registry: &TrustedVerifierRegistry,
        manifest: UpdateManifest,
        evidence: &EvidenceEnvelope,
        now_epoch: u64,
    ) -> Result<(), PolicyError> {
        self.transact(operation_id, PolicyDomain::Update, move |staged| {
            staged
                .updates
                .stage(registry, manifest, evidence, now_epoch)?;
            Ok(TransactionSuccess::allowed(()))
        })
    }

    pub fn activate_update(
        &mut self,
        operation_id: &str,
        registry: &TrustedVerifierRegistry,
        activation: &UpdateActivation,
        evidence: &EvidenceEnvelope,
        now_epoch: u64,
    ) -> Result<UpdateSlot, PolicyError> {
        self.transact(operation_id, PolicyDomain::Update, |staged| {
            let slot = staged
                .updates
                .activate_staged(registry, activation, evidence, now_epoch)?;
            Ok(TransactionSuccess::update(slot, slot))
        })
    }

    pub fn record_boot_failure(
        &mut self,
        operation_id: &str,
        boot_generation: u64,
    ) -> Result<UpdateSlot, PolicyError> {
        self.transact(operation_id, PolicyDomain::Update, |staged| {
            let slot = staged.updates.record_boot_failure(boot_generation)?;
            Ok(TransactionSuccess::update(slot, slot))
        })
    }

    pub fn confirm_update_healthy(
        &mut self,
        operation_id: &str,
        registry: &TrustedVerifierRegistry,
        claim: &UpdateHealthClaim,
        evidence: &EvidenceEnvelope,
        now_epoch: u64,
    ) -> Result<(), PolicyError> {
        self.transact(operation_id, PolicyDomain::Update, |staged| {
            staged
                .updates
                .confirm_healthy(registry, claim, evidence, now_epoch)?;
            Ok(TransactionSuccess::allowed(()))
        })
    }

    fn transact<T, F>(
        &mut self,
        operation_id: &str,
        domain: PolicyDomain,
        transition: F,
    ) -> Result<T, PolicyError>
    where
        F: FnOnce(&mut Self) -> Result<TransactionSuccess<T>, PolicyError>,
    {
        validate_operation_id(operation_id)?;
        let following_sequence = self
            .next_sequence
            .checked_add(1)
            .ok_or(PolicyError::Invalid("POLICY_RECEIPT_SEQUENCE_OVERFLOW"))?;
        let before_state_sha256 = self.state_sha256();
        let mut staged = self.clone();
        match transition(&mut staged) {
            Ok(success) => {
                let after_state_sha256 = staged.state_sha256();
                staged.append_receipt(
                    operation_id,
                    domain,
                    success.outcome,
                    &before_state_sha256,
                    &after_state_sha256,
                    success.command_sha256.as_deref(),
                    success.provider_id.as_deref(),
                    success.external_effect_attempted,
                    success.external_effect_executed,
                    following_sequence,
                )?;
                *self = staged;
                Ok(success.value)
            }
            Err(error) => {
                let mut denied = self.clone();
                denied.append_receipt(
                    operation_id,
                    domain,
                    PolicyReceiptOutcome::Denied(error.code()),
                    &before_state_sha256,
                    &before_state_sha256,
                    None,
                    None,
                    false,
                    false,
                    following_sequence,
                )?;
                *self = denied;
                Err(error)
            }
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn append_receipt(
        &mut self,
        operation_id: &str,
        domain: PolicyDomain,
        outcome: PolicyReceiptOutcome,
        before_state_sha256: &str,
        after_state_sha256: &str,
        command_sha256: Option<&str>,
        provider_id: Option<&str>,
        external_effect_attempted: bool,
        external_effect_executed: bool,
        following_sequence: u64,
    ) -> Result<(), PolicyError> {
        validate_operation_id(operation_id)?;
        validate_sha256(before_state_sha256)?;
        validate_sha256(after_state_sha256)?;
        if let Some(command) = command_sha256 {
            validate_sha256(command)?;
        }
        if provider_id.is_some_and(|provider| !valid_identifier(provider, 128)) {
            return Err(PolicyError::Invalid("INVALID_PROVIDER_ID"));
        }
        let receipt_sha256 = hash_receipt(
            self.next_sequence,
            domain,
            operation_id,
            &outcome,
            before_state_sha256,
            after_state_sha256,
            command_sha256,
            provider_id,
            external_effect_attempted,
            external_effect_executed,
            &self.receipt_head_sha256,
        );
        let receipt = PolicyReceipt {
            sequence: self.next_sequence,
            domain,
            operation_id: operation_id.to_owned(),
            outcome,
            before_state_sha256: before_state_sha256.to_owned(),
            after_state_sha256: after_state_sha256.to_owned(),
            command_sha256: command_sha256.map(str::to_owned),
            provider_id: provider_id.map(str::to_owned),
            external_effect_attempted,
            external_effect_executed,
            previous_receipt_sha256: self.receipt_head_sha256.clone(),
            receipt_sha256: receipt_sha256.clone(),
        };
        self.receipt_sink.append(&receipt)?;
        self.receipts.push(receipt);
        self.next_sequence = following_sequence;
        self.receipt_head_sha256 = receipt_sha256;
        Ok(())
    }

    #[cfg(test)]
    fn force_next_sequence_for_test(&mut self, value: u64) {
        self.next_sequence = value;
    }
}

fn valid_identifier(value: &str, maximum: usize) -> bool {
    !value.is_empty()
        && value.len() <= maximum
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-'))
}

fn validate_operation_id(value: &str) -> Result<(), PolicyError> {
    if valid_identifier(value, 128) {
        Ok(())
    } else {
        Err(PolicyError::Invalid("INVALID_POLICY_OPERATION_ID"))
    }
}

fn validate_sha256(value: &str) -> Result<(), PolicyError> {
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

fn hash_fields(fields: &[(&str, String)]) -> String {
    let mut hasher = Sha256::new();
    for (label, value) in fields {
        hasher.update((label.len() as u64).to_be_bytes());
        hasher.update(label.as_bytes());
        hasher.update((value.len() as u64).to_be_bytes());
        hasher.update(value.as_bytes());
    }
    hex_digest(hasher.finalize())
}

#[allow(clippy::too_many_arguments)]
fn hash_receipt(
    sequence: u64,
    domain: PolicyDomain,
    operation_id: &str,
    outcome: &PolicyReceiptOutcome,
    before_state_sha256: &str,
    after_state_sha256: &str,
    command_sha256: Option<&str>,
    provider_id: Option<&str>,
    external_effect_attempted: bool,
    external_effect_executed: bool,
    previous_receipt_sha256: &str,
) -> String {
    hash_fields(&[
        ("sequence", sequence.to_string()),
        ("domain", domain.code().to_owned()),
        ("operation_id", operation_id.to_owned()),
        ("outcome", outcome.code()),
        ("before_state_sha256", before_state_sha256.to_owned()),
        ("after_state_sha256", after_state_sha256.to_owned()),
        (
            "command_sha256",
            command_sha256.unwrap_or_default().to_owned(),
        ),
        ("provider_id", provider_id.unwrap_or_default().to_owned()),
        (
            "external_effect_attempted",
            external_effect_attempted.to_string(),
        ),
        (
            "external_effect_executed",
            external_effect_executed.to_string(),
        ),
        (
            "previous_receipt_sha256",
            previous_receipt_sha256.to_owned(),
        ),
    ])
}

fn hex_digest(digest: impl AsRef<[u8]>) -> String {
    let digest = digest.as_ref();
    let mut output = String::with_capacity(digest.len() * 2);
    const HEX: &[u8; 16] = b"0123456789abcdef";
    for byte in digest {
        output.push(HEX[usize::from(*byte >> 4)] as char);
        output.push(HEX[usize::from(*byte & 0x0f)] as char);
    }
    output
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuthorityCoordinatorSelfCheck {
    pub checks_run: u32,
    pub receipts_emitted: usize,
    pub external_effect_authority: bool,
}

pub fn run_self_check() -> Result<AuthorityCoordinatorSelfCheck, PolicyError> {
    let mut coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2)?;
    let target = coordinator.collaboration().reference("node", "root")?;
    coordinator.gain_human_focus("d4.focus", "lease-live", 10, 100)?;
    let wrong_human = Actor::human("lease-wrong")?;
    let denied = coordinator
        .validate_target("d4.human-denied", &wrong_human, &target, 11)
        .expect_err("wrong human lease must fail closed");
    if denied.code() != "HUMAN_LEASE_MISMATCH" {
        return Err(PolicyError::Invalid("COORDINATOR_D4_SELF_CHECK_FAILED"));
    }
    coordinator.release_human_focus("d4.release", "lease-live")?;

    let before = coordinator.clone();
    let invalid = coordinator
        .gain_human_focus("invalid operation id", "lease", 20, 100)
        .expect_err("invalid operation identity must fail before mutation");
    if invalid.code() != "INVALID_POLICY_OPERATION_ID" || coordinator != before {
        return Err(PolicyError::Invalid(
            "COORDINATOR_ATOMICITY_SELF_CHECK_FAILED",
        ));
    }

    if coordinator
        .receipts()
        .iter()
        .any(|receipt| receipt.external_effect_attempted || receipt.external_effect_executed)
    {
        return Err(PolicyError::Invalid("COORDINATOR_WIDENED_AUTHORITY"));
    }

    Ok(AuthorityCoordinatorSelfCheck {
        checks_run: 3,
        receipts_emitted: coordinator.receipts().len(),
        external_effect_authority: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::product_policy::{
        TestEvidenceRequest, UpdateActivationParts, UpdateHealthClaimParts, UpdateManifestParts,
        issue_test_evidence, test_network_bundle, test_registry,
    };

    #[test]
    fn invalid_operation_and_sequence_exhaustion_commit_nothing() {
        let mut coordinator =
            AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2).expect("coordinator baseline");
        let baseline = coordinator.clone();
        assert_eq!(
            coordinator
                .gain_human_focus("contains space", "lease", 0, 100)
                .expect_err("invalid operation id")
                .code(),
            "INVALID_POLICY_OPERATION_ID"
        );
        assert_eq!(coordinator, baseline);

        coordinator.force_next_sequence_for_test(u64::MAX);
        let exhausted = coordinator.clone();
        assert_eq!(
            coordinator
                .gain_human_focus("valid.operation", "lease", 0, 100)
                .expect_err("sequence exhaustion")
                .code(),
            "POLICY_RECEIPT_SEQUENCE_OVERFLOW"
        );
        assert_eq!(coordinator, exhausted);
    }

    #[test]
    fn policy_denial_receipt_keeps_domain_state_unchanged() {
        let mut coordinator =
            AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2).expect("coordinator baseline");
        coordinator
            .gain_human_focus("focus", "lease-live", 0, 100)
            .expect("focus");
        let target = coordinator
            .collaboration()
            .reference("node", "root")
            .expect("target");
        let before = coordinator.state_sha256();
        let wrong = Actor::human("lease-wrong").expect("actor shape");
        assert_eq!(
            coordinator
                .validate_target("blocked", &wrong, &target, 1)
                .expect_err("wrong human lease")
                .code(),
            "HUMAN_LEASE_MISMATCH"
        );
        let receipt = coordinator.receipts().last().expect("denial receipt");
        assert_eq!(receipt.before_state_sha256, before);
        assert_eq!(receipt.after_state_sha256, before);
        assert_eq!(
            receipt.outcome,
            PolicyReceiptOutcome::Denied("HUMAN_LEASE_MISMATCH")
        );
    }

    #[test]
    fn rejected_network_authorization_creates_no_effect_and_consumes_no_permit() {
        let registry = test_registry();
        let mut fixture = test_network_bundle(&registry);
        fixture.observation.connected_peer = "1.1.1.1".parse().expect("IP");
        let mut coordinator =
            AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2).expect("coordinator baseline");
        assert!(
            coordinator
                .authorize_and_prepare_network_effect(
                    "network.authorize",
                    "effect-1",
                    "idempotency-1",
                    &registry,
                    &fixture.permit,
                    &fixture.resource,
                    &fixture.request,
                    &fixture.observation,
                    100,
                )
                .is_err()
        );
        assert_eq!(
            coordinator.capabilities().uses(&fixture.permit.permit_id),
            0
        );
        assert_eq!(coordinator.effects().state("effect-1"), None);
        let receipt = coordinator.receipts().last().expect("denial receipt");
        assert_eq!(receipt.before_state_sha256, receipt.after_state_sha256);
    }

    #[test]
    fn network_effect_identity_and_external_execution_are_receipted_truthfully() {
        let registry = test_registry();
        let fixture = test_network_bundle(&registry);
        let mut coordinator =
            AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2).expect("coordinator baseline");
        let (_, command) = coordinator
            .authorize_and_prepare_network_effect(
                "network.authorize",
                "effect-1",
                "idempotency-1",
                &registry,
                &fixture.permit,
                &fixture.resource,
                &fixture.request,
                &fixture.observation,
                100,
            )
            .expect("authorization and preparation");
        coordinator
            .mark_effect_dispatched(
                "effect.dispatch",
                command.effect_id(),
                command.command_sha256(),
            )
            .expect("dispatch");
        let state = coordinator
            .record_external_observation(
                "effect.observe",
                command.effect_id(),
                command.command_sha256(),
                "provider-1",
                1,
                ProviderObservation::Applied,
            )
            .expect("observation");
        assert_eq!(state, EffectState::Applied);
        let receipt = coordinator.receipts().last().expect("external receipt");
        assert!(receipt.external_effect_attempted);
        assert!(receipt.external_effect_executed);
        assert_eq!(receipt.provider_id.as_deref(), Some("provider-1"));
        assert_eq!(
            receipt.command_sha256.as_deref(),
            Some(command.command_sha256())
        );
        assert!(!coordinator.automatic_effect_replay_allowed(command.effect_id()));
        assert_eq!(
            EffectJournal::restore(&coordinator.effects().encode()).expect("restore"),
            coordinator.effects().clone()
        );
    }

    fn update_fixture(
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
            rollback_index: 2,
            image_sha256: "2".repeat(64),
            image_bytes: 4096,
            sbom_sha256: "3".repeat(64),
            provenance_sha256: "4".repeat(64),
            source_commit_sha256: "5".repeat(64),
            signer_key_sha256: registry
                .key_id("fixture-update-manifest")
                .expect("fixture update manifest key")
                .to_owned(),
        })
        .expect("manifest");
        let manifest_evidence = issue_test_evidence(
            registry,
            TestEvidenceRequest {
                verifier_id: "fixture-update-manifest",
                subject: "update-manifest.v1",
                payload_sha256: manifest.manifest_sha256(),
                not_before_epoch: 90,
                expires_at_epoch: 120,
                nonce: "manifest",
            },
        );
        let activation = UpdateActivation::new(UpdateActivationParts {
            target: UpdateSlot::B,
            boot_generation: 9,
            measured_image_sha256: manifest.image_sha256().to_owned(),
            measured_manifest_sha256: manifest.manifest_sha256().to_owned(),
            measured_sbom_sha256: manifest.sbom_sha256().to_owned(),
            measured_provenance_sha256: manifest.provenance_sha256().to_owned(),
        })
        .expect("activation");
        let activation_evidence = issue_test_evidence(
            registry,
            TestEvidenceRequest {
                verifier_id: "fixture-update-boot",
                subject: "update-boot-measurement.v1",
                payload_sha256: activation.payload_sha256(),
                not_before_epoch: 90,
                expires_at_epoch: 120,
                nonce: "activation",
            },
        );
        let health = UpdateHealthClaim::new(UpdateHealthClaimParts {
            target: UpdateSlot::B,
            boot_generation: 9,
            image_sha256: manifest.image_sha256().to_owned(),
            manifest_sha256: manifest.manifest_sha256().to_owned(),
            measured_state_sha256: "6".repeat(64),
            healthy: true,
        })
        .expect("health");
        let health_evidence = issue_test_evidence(
            registry,
            TestEvidenceRequest {
                verifier_id: "fixture-update-health",
                subject: "update-health.v1",
                payload_sha256: health.payload_sha256(),
                not_before_epoch: 90,
                expires_at_epoch: 120,
                nonce: "health",
            },
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
    fn signed_update_state_and_receipts_advance_atomically() {
        let registry = test_registry();
        let (manifest, manifest_evidence, activation, activation_evidence, health, health_evidence) =
            update_fixture(&registry);
        let mut coordinator =
            AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2).expect("coordinator baseline");
        coordinator
            .stage_update("update.stage", &registry, manifest, &manifest_evidence, 100)
            .expect("stage");
        coordinator
            .activate_update(
                "update.activate",
                &registry,
                &activation,
                &activation_evidence,
                100,
            )
            .expect("activate");
        assert_eq!(coordinator.updates().rollback_index(), 1);
        coordinator
            .confirm_update_healthy("update.healthy", &registry, &health, &health_evidence, 100)
            .expect("health");
        assert_eq!(coordinator.updates().rollback_index(), 2);
        assert_eq!(coordinator.updates().healthy_slot(), UpdateSlot::B);
    }

    #[derive(Debug)]
    struct AlwaysFailReceiptSink;

    impl PolicyReceiptSink for AlwaysFailReceiptSink {
        fn append(&self, _receipt: &PolicyReceipt) -> Result<(), PolicyError> {
            Err(PolicyError::Invalid("POLICY_RECEIPT_SINK_REJECTED"))
        }
    }

    #[test]
    fn receipt_sink_failure_publishes_no_domain_or_receipt_state() {
        let mut coordinator = AuthorityCoordinator::with_receipt_sink(
            UpdateSlot::A,
            1,
            1,
            2,
            Arc::new(AlwaysFailReceiptSink),
        )
        .expect("coordinator baseline");
        let before_state = coordinator.state_sha256();
        let before_head = coordinator.receipt_head_sha256().to_owned();
        assert_eq!(
            coordinator
                .gain_human_focus("focus", "lease-live", 0, 100)
                .expect_err("sink failure must abort transaction")
                .code(),
            "POLICY_RECEIPT_SINK_REJECTED"
        );
        assert_eq!(coordinator.state_sha256(), before_state);
        assert_eq!(coordinator.receipt_head_sha256(), before_head);
        assert!(coordinator.receipts().is_empty());
        assert_eq!(coordinator.collaboration().active_human_lease_id(), None);
    }

    #[test]
    fn self_check_emits_no_external_authority() {
        let report = run_self_check().expect("self-check");
        assert_eq!(report.checks_run, 3);
        assert!(report.receipts_emitted >= 3);
        assert!(!report.external_effect_authority);
    }
}
