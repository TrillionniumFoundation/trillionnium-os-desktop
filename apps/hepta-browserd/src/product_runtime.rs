//! Explicitly injected D6/D7 product authority runtime.
//!
//! The runtime has no ambient authority. A caller must supply both a trusted
//! verifier registry and an [`ExternalAuthority`] implementation before a
//! policy-authorized network effect can cross the dispatch boundary. The
//! backend receives an immutable [`EffectCommand`], never an underbound policy
//! decision. Authorization, permit consumption, and journal preparation are
//! one atomic coordinator transaction. Dispatch is journaled before the call;
//! every returned backend outcome or error is then recorded as a truthful
//! external-execution receipt and is never automatically replayed.

use crate::authority_coordinator::AuthorityCoordinator;
use crate::product_policy::{
    CapabilityPermit, EffectCommand, EffectState, NetworkDecision, NetworkObservation,
    NetworkRequest, NetworkResource, PolicyError, ProviderObservation, TrustedVerifierRegistry,
    UpdateSlot,
};
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExternalEffectObservation {
    Applied,
    NotApplied,
    Unknown,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExternalEffectReport {
    pub provider_id: String,
    pub command_sha256: String,
    pub attempt: u32,
    pub observation: ExternalEffectObservation,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExternalAuthorityError {
    Unavailable,
    Failed(&'static str),
}

impl fmt::Display for ExternalAuthorityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Unavailable => formatter.write_str("external authority is unavailable"),
            Self::Failed(code) => write!(formatter, "external authority failed: {code}"),
        }
    }
}

impl std::error::Error for ExternalAuthorityError {}

pub trait ExternalAuthority {
    /// Whether this instance is an explicitly injected effect-capable backend.
    /// Closed/default instances return false and are rejected before policy
    /// state is consumed.
    fn is_available(&self) -> bool;

    /// Stable provider identity bound into every dispatch/reconciliation
    /// receipt. The runtime validates this before consuming a permit.
    fn provider_id(&self) -> &str;

    /// Execute one immutable, already-authorized command. The report must bind
    /// the same provider, command digest, and attempt ordinal.
    fn execute_network(
        &mut self,
        command: &EffectCommand,
    ) -> Result<ExternalEffectReport, ExternalAuthorityError>;
}

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct ClosedExternalAuthority;

impl ExternalAuthority for ClosedExternalAuthority {
    fn is_available(&self) -> bool {
        false
    }

    fn provider_id(&self) -> &str {
        "closed-external-authority"
    }

    fn execute_network(
        &mut self,
        _command: &EffectCommand,
    ) -> Result<ExternalEffectReport, ExternalAuthorityError> {
        Err(ExternalAuthorityError::Unavailable)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProductRuntimeError {
    Policy(PolicyError),
    AuthorityUnavailable,
    Backend {
        code: &'static str,
        reconciled_state: EffectState,
    },
    Invariant(&'static str),
}

impl fmt::Display for ProductRuntimeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Policy(error) => write!(formatter, "product policy rejected operation: {error}"),
            Self::AuthorityUnavailable => {
                formatter.write_str("no explicit external authority backend is installed")
            }
            Self::Backend {
                code,
                reconciled_state,
            } => write!(
                formatter,
                "external backend failed with {code}; effect reconciled as {reconciled_state:?}"
            ),
            Self::Invariant(code) => write!(formatter, "product runtime invariant failed: {code}"),
        }
    }
}

impl std::error::Error for ProductRuntimeError {}

impl From<PolicyError> for ProductRuntimeError {
    fn from(error: PolicyError) -> Self {
        Self::Policy(error)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProductRuntimeExecution {
    pub decision: NetworkDecision,
    pub command: EffectCommand,
    pub effect_state: EffectState,
}

#[derive(Debug)]
pub struct ProductAuthorityRuntime<A> {
    coordinator: AuthorityCoordinator,
    registry: TrustedVerifierRegistry,
    authority: A,
}

impl ProductAuthorityRuntime<ClosedExternalAuthority> {
    pub fn closed() -> Result<Self, PolicyError> {
        Ok(Self {
            coordinator: AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2)?,
            registry: TrustedVerifierRegistry::closed(),
            authority: ClosedExternalAuthority,
        })
    }
}

impl<A: ExternalAuthority> ProductAuthorityRuntime<A> {
    pub fn new(
        coordinator: AuthorityCoordinator,
        registry: TrustedVerifierRegistry,
        authority: A,
    ) -> Self {
        Self {
            coordinator,
            registry,
            authority,
        }
    }

    pub fn coordinator(&self) -> &AuthorityCoordinator {
        &self.coordinator
    }

    pub fn authority_available(&self) -> bool {
        self.authority.is_available()
    }

    pub fn into_parts(self) -> (AuthorityCoordinator, TrustedVerifierRegistry, A) {
        (self.coordinator, self.registry, self.authority)
    }

    #[allow(clippy::too_many_arguments)]
    pub fn execute_network_effect(
        &mut self,
        operation_id: &str,
        effect_id: &str,
        idempotency_key: &str,
        permit: &CapabilityPermit,
        resource: &NetworkResource,
        request: &NetworkRequest,
        observation: &NetworkObservation,
        now_epoch: u64,
    ) -> Result<ProductRuntimeExecution, ProductRuntimeError> {
        if !self.authority.is_available() {
            return Err(ProductRuntimeError::AuthorityUnavailable);
        }
        let provider_id = self.authority.provider_id().to_owned();
        if !valid_runtime_identifier(&provider_id, 128) {
            return Err(ProductRuntimeError::Invariant(
                "INVALID_EXTERNAL_PROVIDER_ID",
            ));
        }

        let authorized = phase_operation_id(operation_id, "authorized")?;
        let dispatched = phase_operation_id(operation_id, "dispatched")?;
        let reconciled = phase_operation_id(operation_id, "reconciled")?;
        let (decision, command) = self.coordinator.authorize_and_prepare_network_effect(
            &authorized,
            effect_id,
            idempotency_key,
            &self.registry,
            permit,
            resource,
            request,
            observation,
            now_epoch,
        )?;
        self.coordinator.mark_effect_dispatched(
            &dispatched,
            command.effect_id(),
            command.command_sha256(),
        )?;

        let backend_result = self.authority.execute_network(&command);
        match backend_result {
            Ok(report) => {
                if report.provider_id != provider_id
                    || report.command_sha256 != command.command_sha256()
                    || report.attempt != 1
                {
                    let effect_state = self.coordinator.record_external_observation(
                        &reconciled,
                        command.effect_id(),
                        command.command_sha256(),
                        &provider_id,
                        1,
                        ProviderObservation::Unknown,
                    )?;
                    if effect_state != EffectState::Indeterminate {
                        return Err(ProductRuntimeError::Invariant(
                            "INVALID_PROVIDER_REPORT_NOT_QUARANTINED",
                        ));
                    }
                    return Err(ProductRuntimeError::Invariant(
                        "EXTERNAL_REPORT_BINDING_MISMATCH",
                    ));
                }
                let provider_observation = provider_observation(report.observation);
                let effect_state = self.coordinator.record_external_observation(
                    &reconciled,
                    command.effect_id(),
                    command.command_sha256(),
                    &provider_id,
                    report.attempt,
                    provider_observation,
                )?;
                if self
                    .coordinator
                    .automatic_effect_replay_allowed(command.effect_id())
                {
                    return Err(ProductRuntimeError::Invariant(
                        "DISPATCHED_EFFECT_REPLAY_ALLOWED",
                    ));
                }
                Ok(ProductRuntimeExecution {
                    decision,
                    command,
                    effect_state,
                })
            }
            Err(ExternalAuthorityError::Unavailable) => {
                let effect_state = self.coordinator.record_external_observation(
                    &reconciled,
                    command.effect_id(),
                    command.command_sha256(),
                    &provider_id,
                    1,
                    ProviderObservation::Unknown,
                )?;
                Err(ProductRuntimeError::Backend {
                    code: "AUTHORITY_BECAME_UNAVAILABLE_AFTER_DISPATCH",
                    reconciled_state: effect_state,
                })
            }
            Err(ExternalAuthorityError::Failed(code)) => {
                let effect_state = self.coordinator.record_external_observation(
                    &reconciled,
                    command.effect_id(),
                    command.command_sha256(),
                    &provider_id,
                    1,
                    ProviderObservation::Unknown,
                )?;
                Err(ProductRuntimeError::Backend {
                    code,
                    reconciled_state: effect_state,
                })
            }
        }
    }
}

fn valid_runtime_identifier(value: &str, maximum: usize) -> bool {
    !value.is_empty()
        && value.len() <= maximum
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-'))
}

fn phase_operation_id(
    operation_id: &str,
    phase: &'static str,
) -> Result<String, ProductRuntimeError> {
    if !valid_runtime_identifier(operation_id, 128) || operation_id.len() + phase.len() + 1 > 128 {
        return Err(ProductRuntimeError::Invariant(
            "INVALID_RUNTIME_OPERATION_ID",
        ));
    }
    Ok(format!("{operation_id}:{phase}"))
}

const fn provider_observation(observation: ExternalEffectObservation) -> ProviderObservation {
    match observation {
        ExternalEffectObservation::Applied => ProviderObservation::Applied,
        ExternalEffectObservation::NotApplied => ProviderObservation::NotApplied,
        ExternalEffectObservation::Unknown => ProviderObservation::Unknown,
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProductAuthorityRuntimeSelfCheck {
    pub checks_run: u32,
    pub authority_available: bool,
    pub receipts_emitted: usize,
    pub external_effect_executed: bool,
}

pub fn run_self_check() -> Result<ProductAuthorityRuntimeSelfCheck, ProductRuntimeError> {
    let runtime = ProductAuthorityRuntime::closed()?;
    if runtime.authority_available() || !runtime.coordinator().receipts().is_empty() {
        return Err(ProductRuntimeError::Invariant(
            "CLOSED_RUNTIME_HAS_AMBIENT_AUTHORITY",
        ));
    }
    Ok(ProductAuthorityRuntimeSelfCheck {
        checks_run: 1,
        authority_available: false,
        receipts_emitted: 0,
        external_effect_executed: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::product_policy::{test_network_bundle, test_registry};

    #[derive(Debug, Clone)]
    enum ScriptedResult {
        Observation(ExternalEffectObservation),
        MismatchedReport,
        Failure(&'static str),
    }

    #[derive(Debug, Clone)]
    struct ScriptedAuthority {
        provider_id: String,
        result: ScriptedResult,
        commands: Vec<EffectCommand>,
    }

    impl ScriptedAuthority {
        fn new(result: ScriptedResult) -> Self {
            Self {
                provider_id: "provider-1".to_owned(),
                result,
                commands: Vec::new(),
            }
        }
    }

    impl ExternalAuthority for ScriptedAuthority {
        fn is_available(&self) -> bool {
            true
        }

        fn provider_id(&self) -> &str {
            &self.provider_id
        }

        fn execute_network(
            &mut self,
            command: &EffectCommand,
        ) -> Result<ExternalEffectReport, ExternalAuthorityError> {
            self.commands.push(command.clone());
            match self.result {
                ScriptedResult::Observation(observation) => Ok(ExternalEffectReport {
                    provider_id: self.provider_id.clone(),
                    command_sha256: command.command_sha256().to_owned(),
                    attempt: 1,
                    observation,
                }),
                ScriptedResult::MismatchedReport => Ok(ExternalEffectReport {
                    provider_id: self.provider_id.clone(),
                    command_sha256: "f".repeat(64),
                    attempt: 1,
                    observation: ExternalEffectObservation::Applied,
                }),
                ScriptedResult::Failure(code) => Err(ExternalAuthorityError::Failed(code)),
            }
        }
    }

    #[test]
    fn closed_runtime_rejects_before_consuming_policy_state() {
        let registry = test_registry();
        let fixture = test_network_bundle(&registry);
        let mut runtime = ProductAuthorityRuntime::closed().expect("closed runtime");
        assert_eq!(
            runtime
                .execute_network_effect(
                    "operation",
                    "effect",
                    "idempotency",
                    &fixture.permit,
                    &fixture.resource,
                    &fixture.request,
                    &fixture.observation,
                    100,
                )
                .expect_err("closed runtime must reject"),
            ProductRuntimeError::AuthorityUnavailable
        );
        assert!(runtime.coordinator().receipts().is_empty());
        assert_eq!(
            runtime
                .coordinator()
                .capabilities()
                .uses(&fixture.permit.permit_id),
            0
        );
        assert_eq!(runtime.coordinator().effects().state("effect"), None);
    }

    #[test]
    fn policy_rejection_leaves_no_replayable_prepared_effect() {
        let registry = test_registry();
        let mut fixture = test_network_bundle(&registry);
        fixture.observation.request_sha256 = "f".repeat(64);
        let coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2).expect("coordinator");
        let authority = ScriptedAuthority::new(ScriptedResult::Observation(
            ExternalEffectObservation::Applied,
        ));
        let mut runtime = ProductAuthorityRuntime::new(coordinator, registry, authority);
        assert!(
            runtime
                .execute_network_effect(
                    "operation",
                    "effect",
                    "idempotency",
                    &fixture.permit,
                    &fixture.resource,
                    &fixture.request,
                    &fixture.observation,
                    100,
                )
                .is_err()
        );
        assert_eq!(runtime.coordinator().effects().state("effect"), None);
        assert_eq!(
            runtime
                .coordinator()
                .capabilities()
                .uses(&fixture.permit.permit_id),
            0
        );
    }

    #[test]
    fn backend_receives_exact_command_and_applied_result_is_truthful() {
        let registry = test_registry();
        let fixture = test_network_bundle(&registry);
        let coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2).expect("coordinator");
        let authority = ScriptedAuthority::new(ScriptedResult::Observation(
            ExternalEffectObservation::Applied,
        ));
        let mut runtime = ProductAuthorityRuntime::new(coordinator, registry, authority);
        let execution = runtime
            .execute_network_effect(
                "operation",
                "effect",
                "idempotency",
                &fixture.permit,
                &fixture.resource,
                &fixture.request,
                &fixture.observation,
                100,
            )
            .expect("scripted execution");
        assert_eq!(execution.effect_state, EffectState::Applied);
        assert_eq!(
            execution.command.payload_sha256(),
            fixture.request.payload_sha256
        );
        assert_eq!(execution.command.permit_id(), fixture.permit.permit_id);
        assert!(
            !runtime
                .coordinator()
                .automatic_effect_replay_allowed(execution.command.effect_id())
        );
        let receipt = runtime.coordinator().receipts().last().expect("receipt");
        assert!(receipt.external_effect_attempted);
        assert!(receipt.external_effect_executed);
        assert_eq!(
            receipt.command_sha256.as_deref(),
            Some(execution.command.command_sha256())
        );
        let (_, _, authority) = runtime.into_parts();
        assert_eq!(authority.commands, vec![execution.command]);
    }

    #[test]
    fn mismatched_provider_report_is_quarantined_as_indeterminate() {
        let registry = test_registry();
        let fixture = test_network_bundle(&registry);
        let coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2).expect("coordinator");
        let authority = ScriptedAuthority::new(ScriptedResult::MismatchedReport);
        let mut runtime = ProductAuthorityRuntime::new(coordinator, registry, authority);
        assert_eq!(
            runtime
                .execute_network_effect(
                    "operation",
                    "effect",
                    "idempotency",
                    &fixture.permit,
                    &fixture.resource,
                    &fixture.request,
                    &fixture.observation,
                    100,
                )
                .expect_err("mismatch must fail"),
            ProductRuntimeError::Invariant("EXTERNAL_REPORT_BINDING_MISMATCH")
        );
        assert_eq!(
            runtime.coordinator().effects().state("effect"),
            Some(EffectState::Indeterminate)
        );
        let receipt = runtime
            .coordinator()
            .receipts()
            .last()
            .expect("external receipt");
        assert!(receipt.external_effect_attempted);
        assert!(!receipt.external_effect_executed);
    }

    #[test]
    fn backend_failure_is_reconciled_before_error_returns() {
        let registry = test_registry();
        let fixture = test_network_bundle(&registry);
        let coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2).expect("coordinator");
        let authority = ScriptedAuthority::new(ScriptedResult::Failure("PROVIDER_FAILED"));
        let mut runtime = ProductAuthorityRuntime::new(coordinator, registry, authority);
        let error = runtime
            .execute_network_effect(
                "operation",
                "effect",
                "idempotency",
                &fixture.permit,
                &fixture.resource,
                &fixture.request,
                &fixture.observation,
                100,
            )
            .expect_err("backend failure must return an error");
        assert_eq!(
            error,
            ProductRuntimeError::Backend {
                code: "PROVIDER_FAILED",
                reconciled_state: EffectState::Indeterminate,
            }
        );
        assert_eq!(
            runtime.coordinator().effects().state("effect"),
            Some(EffectState::Indeterminate)
        );
        let receipt = runtime
            .coordinator()
            .receipts()
            .last()
            .expect("external receipt");
        assert!(receipt.external_effect_attempted);
        assert!(!receipt.external_effect_executed);
    }

    #[test]
    fn self_check_proves_no_default_external_authority() {
        let report = run_self_check().expect("self-check");
        assert_eq!(report.checks_run, 1);
        assert!(!report.authority_available);
        assert_eq!(report.receipts_emitted, 0);
        assert!(!report.external_effect_executed);
    }
}
