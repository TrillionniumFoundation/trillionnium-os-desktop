#![forbid(unsafe_code)]

//! D0 browser daemon scaffold. This is a deterministic contract, transport,
//! and session self-check only: it does not start Servo, bind a listener, or
//! perform an external network operation.

use hepta_browser_contracts::BROWSER_API_PROTOCOL;
use hepta_session_core::{
    ControlSource, ControlState, DEFAULT_HUMAN_LEASE_TTL_MS, SessionEffect, SessionEvent,
    SessionMachine, SessionPhase,
};
use trillionnium_contract_core::LeaseId;

pub const ACTIVE_PLAN_REVISION: &str = "2026-08-28-d5";
pub const IMPLEMENTATION_STAGE: &str = "D0R_D0C02_SOURCE";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SelfCheckReport {
    pub ok: bool,
    pub protocol: &'static str,
    pub plan_revision: &'static str,
    pub implementation_stage: &'static str,
    pub checks_run: u32,
    pub final_session_generation: u64,
    pub final_document_generation: u64,
    pub final_snapshot_revision: u64,
    pub final_mutation_epoch: u64,
}

impl SelfCheckReport {
    pub fn to_json(&self) -> String {
        format!(
            concat!(
                "{{\"schema\":\"trillionnium.desktop.browserd-self-check.v1\",",
                "\"ok\":{},\"protocol\":\"{}\",\"plan_revision\":\"{}\",",
                "\"implementation_stage\":\"{}\",\"checks_run\":{},",
                "\"final_revisions\":{{\"session_generation\":{},",
                "\"document_generation\":{},\"semantic_snapshot_revision\":{},",
                "\"mutation_epoch\":{}}}}}"
            ),
            self.ok,
            self.protocol,
            self.plan_revision,
            self.implementation_stage,
            self.checks_run,
            self.final_session_generation,
            self.final_document_generation,
            self.final_snapshot_revision,
            self.final_mutation_epoch,
        )
    }
}

pub fn run_self_check() -> Result<SelfCheckReport, String> {
    let mut checks_run = 0_u32;

    hepta_agent_transport::self_check().map_err(|error| error.to_string())?;
    checks_run += 1;

    let mut machine = SessionMachine::new();

    machine
        .apply(SessionEvent::BeginAgentMutation, 0)
        .map_err(|error| error.to_string())?;
    checks_run += 1;

    let lease_id =
        LeaseId::parse("lease_id", "self-check-human").map_err(|error| error.to_string())?;
    let effects = machine
        .apply(
            SessionEvent::HumanFocusGained {
                lease_id: lease_id.clone(),
                ttl_ms: DEFAULT_HUMAN_LEASE_TTL_MS,
            },
            10,
        )
        .map_err(|error| error.to_string())?;
    if !effects.contains(&SessionEffect::InterruptAgentWork) {
        return Err("human focus did not interrupt Agent work".into());
    }
    checks_run += 1;

    machine
        .apply(
            SessionEvent::ImeStarted {
                lease_id: lease_id.clone(),
            },
            11,
        )
        .map_err(|error| error.to_string())?;
    if machine.snapshot().control != ControlState::HumanImeComposing {
        return Err("IME state was not entered".into());
    }
    checks_run += 1;

    machine
        .apply(SessionEvent::DomCommitted, 12)
        .map_err(|error| error.to_string())?;
    machine
        .apply(SessionEvent::SemanticSnapshotPublished, 13)
        .map_err(|error| error.to_string())?;
    checks_run += 1;

    machine
        .apply(
            SessionEvent::ImeEnded {
                lease_id: lease_id.clone(),
            },
            14,
        )
        .map_err(|error| error.to_string())?;
    machine
        .apply(SessionEvent::HumanFocusReleased { lease_id }, 15)
        .map_err(|error| error.to_string())?;
    checks_run += 1;

    machine
        .apply(
            SessionEvent::NavigationStarted {
                source: ControlSource::Agent,
            },
            20,
        )
        .map_err(|error| error.to_string())?;
    machine
        .apply(SessionEvent::NavigationCommitted, 21)
        .map_err(|error| error.to_string())?;
    if machine.snapshot().revisions.document_generation != 2 {
        return Err("navigation did not advance document generation".into());
    }
    checks_run += 1;

    machine
        .apply(SessionEvent::BrowserCrashed, 30)
        .map_err(|error| error.to_string())?;
    if machine.snapshot().phase != SessionPhase::Recovering {
        return Err("crash did not enter recovery".into());
    }
    machine
        .apply(SessionEvent::Recovered, 31)
        .map_err(|error| error.to_string())?;
    checks_run += 1;

    let snapshot = machine.snapshot();
    Ok(SelfCheckReport {
        ok: true,
        protocol: BROWSER_API_PROTOCOL,
        plan_revision: ACTIVE_PLAN_REVISION,
        implementation_stage: IMPLEMENTATION_STAGE,
        checks_run,
        final_session_generation: snapshot.revisions.session_generation,
        final_document_generation: snapshot.revisions.document_generation,
        final_snapshot_revision: snapshot.revisions.semantic_snapshot_revision,
        final_mutation_epoch: snapshot.revisions.mutation_epoch,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn self_check_exercises_transport_preemption_revision_and_recovery() {
        let report = run_self_check().expect("self-check must pass");
        assert!(report.ok);
        assert!(report.checks_run >= 8);
        assert_eq!(report.final_session_generation, 2);
        assert!(report.final_document_generation >= 3);
        assert!(report.to_json().contains(ACTIVE_PLAN_REVISION));
    }
}
