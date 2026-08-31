//! Explicitly injected D6/D7 product authority runtime.
//!
//! The runtime has no ambient authority.  A caller must supply an
//! [`ExternalAuthority`] implementation before a policy-authorized network
//! effect can cross the dispatch boundary.  The built-in
//! [`ClosedExternalAuthority`] rejects before a permit is consumed or an effect
//! journal entry is opened.  Once dispatch is marked, any backend error or
//! unknown result is reconciled as `Indeterminate` and is never automatically
//! replayed.

use crate::authority_coordinator::AuthorityCoordinator;
use crate::product_policy::{
    CapabilityPermit, EffectState, NetworkDecision, NetworkRequest, NetworkResource, PolicyError,
    ProviderObservation, UpdateSlot,
};
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExternalEffectObservation {
    Applied,
    NotApplied,
    Unknown,
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

    /// Execute one already-authorized network effect and return the provider's
    /// observed outcome.  The policy decision itself never performs I/O.
    fn execute_network(
        &mut self,
        decision: &NetworkDecision,
    ) -> Result<ExternalEffectObservation, ExternalAuthorityError>;
}

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct ClosedExternalAuthority;

impl ExternalAuthority for ClosedExternalAuthority {
    fn is_available(&self) -> bool {
        false
    }

    fn execute_network(
        &mut self,
        _decision: &NetworkDecision,
    ) -> Result<ExternalEffectObservation, ExternalAuthorityError> {
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
    pub effect_state: EffectState,
}

#[derive(Debug)]
pub struct ProductAuthorityRuntime<A> {
    coordinator: AuthorityCoordinator,
    authority: A,
}

impl ProductAuthorityRuntime<ClosedExternalAuthority> {
    pub fn closed() -> Result<Self, PolicyError> {
        Ok(Self {
            coordinator: AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2)?,
            authority: ClosedExternalAuthority,
        })
    }
}

impl<A: ExternalAuthority> ProductAuthorityRuntime<A> {
    pub fn new(coordinator: AuthorityCoordinator, authority: A) -> Self {
        Self {
            coordinator,
            authority,
        }
    }

    pub fn coordinator(&self) -> &AuthorityCoordinator {
        &self.coordinator
    }

    pub fn authority_available(&self) -> bool {
        self.authority.is_available()
    }

    pub fn into_parts(self) -> (AuthorityCoordinator, A) {
        (self.coordinator, self.authority)
    }

    pub fn execute_network_effect(
        &mut self,
        operation_id: &str,
        effect_id: &str,
        permit: &CapabilityPermit,
        resource: &NetworkResource,
        request: &NetworkRequest,
        now_epoch: u64,
    ) -> Result<ProductRuntimeExecution, ProductRuntimeError> {
        if !self.authority.is_available() {
            return Err(ProductRuntimeError::AuthorityUnavailable);
        }

        let requested = phase_operation_id(operation_id, "requested")?;
        let prepared = phase_operation_id(operation_id, "prepared")?;
        let authorized = phase_operation_id(operation_id, "authorized")?;
        let dispatched = phase_operation_id(operation_id, "dispatched")?;
        let reconciled = phase_operation_id(operation_id, "reconciled")?;

        self.coordinator.request_effect(&requested, effect_id)?;
        self.coordinator.prepare_effect(&prepared, effect_id)?;
        let decision = self.coordinator.authorize_network(
            &authorized,
            permit,
            resource,
            request,
            now_epoch,
        )?;
        self.coordinator
            .mark_effect_dispatched(&dispatched, effect_id)?;

        let backend_result = self.authority.execute_network(&decision);
        match backend_result {
            Ok(observation) => {
                let provider = provider_observation(observation);
                let effect_state = self.coordinator.reconcile_effect(
                    &reconciled,
                    effect_id,
                    provider,
                )?;
                if effect_state == EffectState::Indeterminate
                    && self.coordinator.automatic_effect_replay_allowed(effect_id)
                {
                    return Err(ProductRuntimeError::Invariant(
                        "INDETERMINATE_EFFECT_REPLAY_ALLOWED",
                    ));
                }
                Ok(ProductRuntimeExecution {
                    decision,
                    effect_state,
                })
            }
            Err(ExternalAuthorityError::Unavailable) => {
                let effect_state = self.coordinator.reconcile_effect(
                    &reconciled,
                    effect_id,
                    ProviderObservation::Unknown,
                )?;
                Err(ProductRuntimeError::Backend {
                    code: "AUTHORITY_BECAME_UNAVAILABLE_AFTER_DISPATCH",
                    reconciled_state: effect_state,
                })
            }
            Err(ExternalAuthorityError::Failed(code)) => {
                let effect_state = self.coordinator.reconcile_effect(
                    &reconciled,
                    effect_id,
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

fn phase_operation_id(
    operation_id: &str,
    phase: &'static str,
) -> Result<String, ProductRuntimeError> {
    if operation_id.is_empty()
        || operation_id.len() + phase.len() + 1 > 128
        || !operation_id.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-')
        })
    {
        return Err(ProductRuntimeError::Invariant(
            "INVALID_RUNTIME_OPERATION_ID",
        ));
    }
    Ok(format!("{operation_id}:{phase}"))
}

const fn provider_observation(
    observation: ExternalEffectObservation,
) -> ProviderObservation {
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
    use crate::product_policy::{
        Audience, CapabilityPermit, NetworkContext, SignatureEvidence,
    };
    use std::collections::BTreeSet;
    use std::net::{IpAddr, Ipv4Addr};

    #[derive(Debug)]
    struct ScriptedAuthority {
        result: Result<ExternalEffectObservation, ExternalAuthorityError>,
    }

    impl ExternalAuthority for ScriptedAuthority {
        fn is_available(&self) -> bool {
            true
        }

        fn execute_network(
            &mut self,
            _decision: &NetworkDecision,
        ) -> Result<ExternalEffectObservation, ExternalAuthorityError> {
            self.result
        }
    }

    fn fixture() -> (CapabilityPermit, NetworkResource, NetworkRequest) {
        let digest = "a".repeat(64);
        let signature = SignatureEvidence::from_external_verifier("test-verifier", &digest)
            .expect("signature evidence");
        let resource = NetworkResource {
            resource_id: "network:example".to_owned(),
            allowed_origins: BTreeSet::from(["https://example.com:443".to_owned()]),
            allowed_contexts: BTreeSet::from([NetworkContext::TopLevel]),
            proxy_id: "proxy".to_owned(),
            maximum_redirects: 2,
        };
        let permit = CapabilityPermit {
            permit_id: "permit".to_owned(),
            subject: "taskflow:one".to_owned(),
            audience: Audience::Network,
            resource_id: resource.resource_id.clone(),
            action: "http_request".to_owned(),
            not_before_epoch: 10,
            expires_at_epoch: 20,
            nonce: "nonce".to_owned(),
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
        (permit, resource, request)
    }

    #[test]
    fn closed_runtime_rejects_before_consuming_policy_state() {
        let (permit, resource, request) = fixture();
        let mut runtime = ProductAuthorityRuntime::closed().expect("closed runtime");
        assert_eq!(
            runtime
                .execute_network_effect(
                    "operation",
                    "effect",
                    &permit,
                    &resource,
                    &request,
                    15,
                )
                .expect_err("closed runtime must reject"),
            ProductRuntimeError::AuthorityUnavailable
        );
        assert!(runtime.coordinator().receipts().is_empty());
    }

    #[test]
    fn unknown_provider_result_is_indeterminate_and_not_replayed() {
        let (permit, resource, request) = fixture();
        let coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2)
            .expect("coordinator");
        let authority = ScriptedAuthority {
            result: Ok(ExternalEffectObservation::Unknown),
        };
        let mut runtime = ProductAuthorityRuntime::new(coordinator, authority);
        let execution = runtime
            .execute_network_effect(
                "operation",
                "effect",
                &permit,
                &resource,
                &request,
                15,
            )
            .expect("scripted execution");
        assert_eq!(execution.effect_state, EffectState::Indeterminate);
        assert!(!runtime
            .coordinator()
            .automatic_effect_replay_allowed("effect"));
        assert!(!execution.decision.external_effect_executed);
    }

    #[test]
    fn backend_failure_is_reconciled_before_error_returns() {
        let (permit, resource, request) = fixture();
        let coordinator = AuthorityCoordinator::new(UpdateSlot::A, 1, 1, 2)
            .expect("coordinator");
        let authority = ScriptedAuthority {
            result: Err(ExternalAuthorityError::Failed("PROVIDER_FAILED")),
        };
        let mut runtime = ProductAuthorityRuntime::new(coordinator, authority);
        let error = runtime
            .execute_network_effect(
                "operation",
                "effect",
                &permit,
                &resource,
                &request,
                15,
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
        assert!(!runtime
            .coordinator()
            .automatic_effect_replay_allowed("effect"));
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
