//! Deterministic D4-D7 authority coordination.
//!
//! This module composes the side-effect-free product-policy state machines and
//! emits an in-memory decision receipt for every admitted or rejected
//! transition.  It owns no file descriptor, socket, device, credential,
//! bootloader handle, signing key, or external-effect executor.

use crate::product_policy::{
    Actor, CapabilityLedger, CapabilityPermit, CollaborationController, EffectJournal,
    EffectState, NetworkDecision, NetworkRequest, NetworkResource, PolicyError,
    ProviderObservation, TargetReference, UpdateController, UpdateSlot,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PolicyDomain {
    Collaboration,
    Network,
    Effect,
    Update,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PolicyReceiptOutcome {
    Allowed,
    Denied(&'static str),
    EffectState(EffectState),
    UpdateSlot(UpdateSlot),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PolicyReceipt {
    pub sequence: u64,
    pub domain: PolicyDomain,
    pub operation_id: String,
    pub outcome: PolicyReceiptOutcome,
    pub external_effect_executed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuthorityCoordinator {
    collaboration: CollaborationController,
    capabilities: CapabilityLedger,
    effects: EffectJournal,
    updates: UpdateController,
    receipts: Vec<PolicyReceipt>,
    next_sequence: u64,
}

impl AuthorityCoordinator {
    pub fn new(
        active_slot: UpdateSlot,
        current_version: u64,
        rollback_index: u64,
        maximum_boot_attempts: u8,
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
        })
    }

    pub fn collaboration(&self) -> &CollaborationController {
        &self.collaboration
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

    pub fn gain_human_focus(
        &mut self,
        operation_id: &str,
        lease_id: &str,
        now_ms: u64,
        ttl_ms: u64,
    ) -> Result<(), PolicyError> {
        let result = self
            .collaboration
            .gain_human_focus(lease_id, now_ms, ttl_ms);
        self.finish(operation_id, PolicyDomain::Collaboration, result)
    }

    pub fn release_human_focus(
        &mut self,
        operation_id: &str,
        lease_id: &str,
    ) -> Result<(), PolicyError> {
        let result = self.collaboration.release_human_focus(lease_id);
        self.finish(operation_id, PolicyDomain::Collaboration, result)
    }

    pub fn validate_target(
        &mut self,
        operation_id: &str,
        actor: &Actor,
        target: &TargetReference,
        now_ms: u64,
    ) -> Result<(), PolicyError> {
        let result = self.collaboration.validate_target(actor, target, now_ms);
        self.finish(operation_id, PolicyDomain::Collaboration, result)
    }

    pub fn compare_and_swap_clipboard(
        &mut self,
        operation_id: &str,
        actor: &Actor,
        expected_version: u64,
        new_sha256: &str,
        now_ms: u64,
    ) -> Result<u64, PolicyError> {
        let result = self.collaboration.compare_and_swap_clipboard(
            actor,
            expected_version,
            new_sha256,
            now_ms,
        );
        self.finish(operation_id, PolicyDomain::Collaboration, result)
    }

    pub fn authorize_network(
        &mut self,
        operation_id: &str,
        permit: &CapabilityPermit,
        resource: &NetworkResource,
        request: &NetworkRequest,
        now_epoch: u64,
    ) -> Result<NetworkDecision, PolicyError> {
        let result = self
            .capabilities
            .authorize_network(permit, resource, request, now_epoch);
        match result {
            Ok(decision) => {
                if decision.external_effect_executed {
                    let error = PolicyError::Invalid("POLICY_EXECUTED_EXTERNAL_EFFECT");
                    self.record(
                        operation_id,
                        PolicyDomain::Network,
                        PolicyReceiptOutcome::Denied(error.code()),
                    )?;
                    return Err(error);
                }
                self.record(
                    operation_id,
                    PolicyDomain::Network,
                    PolicyReceiptOutcome::Allowed,
                )?;
                Ok(decision)
            }
            Err(error) => {
                self.record(
                    operation_id,
                    PolicyDomain::Network,
                    PolicyReceiptOutcome::Denied(error.code()),
                )?;
                Err(error)
            }
        }
    }

    pub fn request_effect(
        &mut self,
        operation_id: &str,
        effect_id: &str,
    ) -> Result<(), PolicyError> {
        let result = self.effects.request(effect_id);
        self.finish(operation_id, PolicyDomain::Effect, result)
    }

    pub fn prepare_effect(
        &mut self,
        operation_id: &str,
        effect_id: &str,
    ) -> Result<(), PolicyError> {
        let result = self.effects.prepare(effect_id);
        self.finish(operation_id, PolicyDomain::Effect, result)
    }

    pub fn mark_effect_dispatched(
        &mut self,
        operation_id: &str,
        effect_id: &str,
    ) -> Result<(), PolicyError> {
        let result = self.effects.mark_dispatched(effect_id);
        self.finish(operation_id, PolicyDomain::Effect, result)
    }

    pub fn reconcile_effect(
        &mut self,
        operation_id: &str,
        effect_id: &str,
        observation: ProviderObservation,
    ) -> Result<EffectState, PolicyError> {
        let result = self.effects.reconcile(effect_id, observation);
        match result {
            Ok(state) => {
                self.record(
                    operation_id,
                    PolicyDomain::Effect,
                    PolicyReceiptOutcome::EffectState(state),
                )?;
                Ok(state)
            }
            Err(error) => {
                self.record(
                    operation_id,
                    PolicyDomain::Effect,
                    PolicyReceiptOutcome::Denied(error.code()),
                )?;
                Err(error)
            }
        }
    }

    pub fn automatic_effect_replay_allowed(&self, effect_id: &str) -> bool {
        self.effects.automatic_replay_allowed(effect_id)
    }

    pub fn stage_update(
        &mut self,
        operation_id: &str,
        target: UpdateSlot,
        version: u64,
        rollback_index: u64,
        image_sha256: &str,
    ) -> Result<(), PolicyError> {
        let result = self
            .updates
            .stage(target, version, rollback_index, image_sha256);
        self.finish(operation_id, PolicyDomain::Update, result)
    }

    pub fn activate_update(&mut self, operation_id: &str) -> Result<UpdateSlot, PolicyError> {
        let result = self.updates.activate_staged();
        self.finish_with_slot(operation_id, result)
    }

    pub fn record_boot_failure(
        &mut self,
        operation_id: &str,
    ) -> Result<UpdateSlot, PolicyError> {
        let result = self.updates.record_boot_failure();
        self.finish_with_slot(operation_id, result)
    }

    pub fn confirm_update_healthy(&mut self, operation_id: &str) -> Result<(), PolicyError> {
        let result = self.updates.confirm_healthy();
        self.finish(operation_id, PolicyDomain::Update, result)
    }

    fn finish<T>(
        &mut self,
        operation_id: &str,
        domain: PolicyDomain,
        result: Result<T, PolicyError>,
    ) -> Result<T, PolicyError> {
        match result {
            Ok(value) => {
                self.record(operation_id, domain, PolicyReceiptOutcome::Allowed)?;
                Ok(value)
            }
            Err(error) => {
                self.record(
                    operation_id,
                    domain,
                    PolicyReceiptOutcome::Denied(error.code()),
                )?;
                Err(error)
            }
        }
    }

    fn finish_with_slot(
        &mut self,
        operation_id: &str,
        result: Result<UpdateSlot, PolicyError>,
    ) -> Result<UpdateSlot, PolicyError> {
        match result {
            Ok(slot) => {
                self.record(
                    operation_id,
                    PolicyDomain::Update,
                    PolicyReceiptOutcome::UpdateSlot(slot),
                )?;
                Ok(slot)
            }
            Err(error) => {
                self.record(
                    operation_id,
                    PolicyDomain::Update,
                    PolicyReceiptOutcome::Denied(error.code()),
                )?;
                Err(error)
            }
        }
    }

    fn record(
        &mut self,
        operation_id: &str,
        domain: PolicyDomain,
        outcome: PolicyReceiptOutcome,
    ) -> Result<(), PolicyError> {
        if operation_id.is_empty()
            || operation_id.len() > 128
            || !operation_id.bytes().all(|byte| {
                byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-')
            })
        {
            return Err(PolicyError::Invalid("INVALID_POLICY_OPERATION_ID"));
        }
        let sequence = self.next_sequence;
        self.next_sequence = self
            .next_sequence
            .checked_add(1)
            .ok_or(PolicyError::Invalid("POLICY_RECEIPT_SEQUENCE_OVERFLOW"))?;
        self.receipts.push(PolicyReceipt {
            sequence,
            domain,
            operation_id: operation_id.to_owned(),
            outcome,
            external_effect_executed: false,
        });
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuthorityCoordinatorSelfCheck {
    pub checks_run: u32,
    pub receipts_emitted: usize,
    pub external_effect_authority: bool,
}

pub fn run_self_check() -> Result<AuthorityCoordinatorSelfCheck, PolicyError> {
    let digest = "a".repeat(64);
    let mut coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2)?;

    let old_epoch = coordinator.collaboration().current_agent_epoch();
    let target = coordinator.collaboration().reference("node", "root")?;
    coordinator.gain_human_focus("d4.focus", "lease", 10, 100)?;
    let denied = coordinator
        .validate_target("d4.agent-denied", &Actor::Agent { epoch: old_epoch }, &target, 11)
        .expect_err("active human lease must preempt Agent work");
    if denied.code() != "HUMAN_LEASE_ACTIVE" {
        return Err(PolicyError::Invalid("COORDINATOR_D4_SELF_CHECK_FAILED"));
    }
    coordinator.release_human_focus("d4.release", "lease")?;

    coordinator.request_effect("d7.request", "effect")?;
    coordinator.prepare_effect("d7.prepare", "effect")?;
    coordinator.mark_effect_dispatched("d7.dispatched", "effect")?;
    let state = coordinator.reconcile_effect(
        "d7.reconcile",
        "effect",
        ProviderObservation::Unknown,
    )?;
    if state != EffectState::Indeterminate
        || coordinator.automatic_effect_replay_allowed("effect")
    {
        return Err(PolicyError::Invalid("COORDINATOR_D7_SELF_CHECK_FAILED"));
    }

    coordinator.stage_update("d7.update-stage", UpdateSlot::B, 2, 2, &digest)?;
    coordinator.activate_update("d7.update-activate")?;
    coordinator.confirm_update_healthy("d7.update-healthy")?;
    if coordinator.updates().active_slot() != UpdateSlot::B
        || coordinator.updates().rollback_index() != 2
    {
        return Err(PolicyError::Invalid("COORDINATOR_UPDATE_SELF_CHECK_FAILED"));
    }

    if coordinator
        .receipts()
        .iter()
        .any(|receipt| receipt.external_effect_executed)
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

    fn digest(character: char) -> String {
        character.to_string().repeat(64)
    }

    #[test]
    fn denied_and_allowed_transitions_are_receipted_in_order() {
        let mut coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2)
            .expect("coordinator baseline");
        let epoch = coordinator.collaboration().current_agent_epoch();
        let target = coordinator
            .collaboration()
            .reference("node", "root")
            .expect("target");
        coordinator
            .gain_human_focus("focus", "lease", 0, 100)
            .expect("focus");
        assert_eq!(
            coordinator
                .validate_target("blocked", &Actor::Agent { epoch }, &target, 1)
                .expect_err("Agent must be preempted")
                .code(),
            "HUMAN_LEASE_ACTIVE"
        );
        assert_eq!(coordinator.receipts().len(), 2);
        assert_eq!(coordinator.receipts()[0].sequence, 1);
        assert_eq!(coordinator.receipts()[1].sequence, 2);
        assert_eq!(
            coordinator.receipts()[1].outcome,
            PolicyReceiptOutcome::Denied("HUMAN_LEASE_ACTIVE")
        );
    }

    #[test]
    fn indeterminate_effect_is_reconciliation_only() {
        let mut coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2)
            .expect("coordinator baseline");
        coordinator.request_effect("request", "effect").expect("request");
        coordinator.prepare_effect("prepare", "effect").expect("prepare");
        coordinator
            .mark_effect_dispatched("dispatch", "effect")
            .expect("dispatch marker");
        assert_eq!(
            coordinator
                .reconcile_effect("reconcile", "effect", ProviderObservation::Unknown)
                .expect("reconcile"),
            EffectState::Indeterminate
        );
        assert!(!coordinator.automatic_effect_replay_allowed("effect"));
    }

    #[test]
    fn update_index_advances_only_after_health_confirmation() {
        let mut coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 4, 2)
            .expect("coordinator baseline");
        coordinator
            .stage_update("stage", UpdateSlot::B, 2, 5, &digest('b'))
            .expect("stage");
        coordinator.activate_update("activate").expect("activate");
        assert_eq!(coordinator.updates().rollback_index(), 4);
        coordinator
            .confirm_update_healthy("healthy")
            .expect("health confirmation");
        assert_eq!(coordinator.updates().rollback_index(), 5);
    }

    #[test]
    fn self_check_emits_no_external_authority() {
        let report = run_self_check().expect("self-check");
        assert_eq!(report.checks_run, 3);
        assert!(report.receipts_emitted >= 10);
        assert!(!report.external_effect_authority);
    }
}
