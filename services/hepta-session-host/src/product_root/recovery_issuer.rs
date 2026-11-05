//! Explicit Root continuation of the SAME original finite issuer.
//! Persist one postimage before CAS, reconcile only that postimage after a lost
//! reply, and reopen the original issuer at its new revision in rotate().
use super::{Result, config::Inputs, recovery::Existing};
use codex_hepta_agentd::{commit_host_issuer_lease_renewal, prepare_host_issuer_lease_renewal};
use codex_hepta_contracts::authority_lease::AuthorityLease;

pub(super) fn continue_joint(inputs: &Inputs, old: &Existing) -> Result<AuthorityLease> {
    if !inputs.is_desktop() || old.calculator.is_none() {
        return Err("issuer continuation requires the explicit original joint profile".into());
    }
    let source = old.source_admin.join("authority-config.json");
    let saved = old.issuer_plan()?;
    // Observe expiration before generating the bounded postimage. Waiting is
    // not a lease extension, and a retry must keep its already persisted plan.
    super::recovery_authority::wait_retirement(old, saved.as_ref())?;
    let plan = match saved {
        Some(plan) => plan,
        None => {
            let plan = prepare_host_issuer_lease_renewal(&source, inputs.lifetime_ms)?;
            old.record_issuer_plan(&plan)?;
            plan
        }
    };
    let renewed = commit_host_issuer_lease_renewal(&source, &plan)?;
    old.record_issuer_commit(&renewed)?;
    Ok(renewed)
}
