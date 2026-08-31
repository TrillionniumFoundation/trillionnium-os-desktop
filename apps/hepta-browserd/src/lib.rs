#![forbid(unsafe_code)]

//! TrillionniumOS browser daemon control core.
//!
//! The historical D0-D3 self-check remains isolated in `legacy`; the compiled
//! D4-D7 product-policy module is exercised through the public self-check as a
//! side-effect-free source integration. No integrated-image, hardware, signing,
//! external-network, or release authority is implied.

mod legacy;
pub mod product_policy;

pub use legacy::SelfCheckReport;

// Canonical machine-truth anchors retained at the public crate entry point.
// Product-policy compilation widens tested source coverage, not the promoted
// implementation or release claim represented by these two values.
pub const ACTIVE_PLAN_REVISION: &str = "2026-08-29-d6";
pub const IMPLEMENTATION_STAGE: &str = "D0R_D0C06_D0A01_COMPILE_VALIDATED";
pub const PRODUCT_POLICY_SOURCE_STAGE: &str = "D4_D7_COMPILED_SIDE_EFFECT_FREE_POLICY_CORE";

pub fn run_self_check() -> Result<SelfCheckReport, String> {
    let mut report = legacy::run_self_check()?;
    let policy = product_policy::run_self_check().map_err(|error| error.to_string())?;
    report.checks_run = report
        .checks_run
        .checked_add(policy.checks_run)
        .ok_or_else(|| "self-check counter overflow".to_owned())?;
    if policy.external_effect_authority
        || policy.private_key_authority
        || policy.hardware_qualified
        || policy.release_ready
    {
        return Err("product-policy self-check widened authority".to_owned());
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_self_check_includes_d4_d7_policy_without_authority_widening() {
        let report = run_self_check().expect("integrated source self-check must pass");
        assert!(report.ok);
        assert!(report.checks_run >= 15);
        assert!(report.to_json().contains(ACTIVE_PLAN_REVISION));
        assert_eq!(PRODUCT_POLICY_SOURCE_STAGE, "D4_D7_COMPILED_SIDE_EFFECT_FREE_POLICY_CORE");
    }
}
