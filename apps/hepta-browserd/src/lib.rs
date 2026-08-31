#![forbid(unsafe_code)]

//! TrillionniumOS browser daemon control core.
//!
//! The historical D0-D3 self-check remains isolated in `legacy`.  The compiled
//! D4-D7 policy, deterministic authority coordinator, and explicitly injected
//! product-authority runtime are exercised through the public self-check as
//! side-effect-free source integrations.  No integrated-image, hardware,
//! signing, external-network, or release authority is implied.

mod legacy;
pub mod authority_coordinator;
pub mod product_policy;
pub mod product_runtime;

pub use legacy::SelfCheckReport;

// Canonical machine-truth anchors retained at the public crate entry point.
// Additional source compilation widens tested coverage, not the promoted
// implementation or release claim represented by these two values.
pub const ACTIVE_PLAN_REVISION: &str = "2026-08-29-d6";
pub const IMPLEMENTATION_STAGE: &str = "D0R_D0C06_D0A01_COMPILE_VALIDATED";
pub const PRODUCT_POLICY_SOURCE_STAGE: &str = "D4_D7_COMPILED_SIDE_EFFECT_FREE_POLICY_CORE";
pub const AUTHORITY_RUNTIME_SOURCE_STAGE: &str =
    "D4_D7_EXPLICIT_AUTHORITY_COORDINATION_SOURCE_CORE";

pub fn run_self_check() -> Result<SelfCheckReport, String> {
    let mut report = legacy::run_self_check()?;
    let policy = product_policy::run_self_check().map_err(|error| error.to_string())?;
    let coordinator =
        authority_coordinator::run_self_check().map_err(|error| error.to_string())?;
    let runtime = product_runtime::run_self_check().map_err(|error| error.to_string())?;

    let additional_checks = policy
        .checks_run
        .checked_add(coordinator.checks_run)
        .and_then(|value| value.checked_add(runtime.checks_run))
        .ok_or_else(|| "self-check counter overflow".to_owned())?;
    report.checks_run = report
        .checks_run
        .checked_add(additional_checks)
        .ok_or_else(|| "self-check counter overflow".to_owned())?;

    if policy.external_effect_authority
        || policy.private_key_authority
        || policy.hardware_qualified
        || policy.release_ready
        || coordinator.external_effect_authority
        || runtime.authority_available
        || runtime.external_effect_executed
    {
        return Err("D4-D7 source self-check widened authority".to_owned());
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_self_check_includes_d4_d7_layers_without_authority_widening() {
        let report = run_self_check().expect("integrated source self-check must pass");
        assert!(report.ok);
        assert!(report.checks_run >= 19);
        assert!(report.to_json().contains(ACTIVE_PLAN_REVISION));
        assert_eq!(
            PRODUCT_POLICY_SOURCE_STAGE,
            "D4_D7_COMPILED_SIDE_EFFECT_FREE_POLICY_CORE"
        );
        assert_eq!(
            AUTHORITY_RUNTIME_SOURCE_STAGE,
            "D4_D7_EXPLICIT_AUTHORITY_COORDINATION_SOURCE_CORE"
        );
    }
}
