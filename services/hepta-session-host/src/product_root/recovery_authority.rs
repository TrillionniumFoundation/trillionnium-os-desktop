//! Original clock/registry inspection and exact same-issuer successor rotation.
use super::{
    Result,
    authority::{self, RegistrationFiles},
    config::Inputs,
    fs,
    geometry::Product,
    recovery::Existing,
};
use codex_hepta_agentd::{
    HostAuthorityRegistration, HostAuthorityServiceConfig, HostIssuerLeaseRenewalPlan,
    rotate_host_writer_authorization,
};
use codex_hepta_contracts::authority_lease::{
    AuthorityLease, AuthorityLeaseFrontier, AuthorityLeaseRegistry,
};
use codex_hepta_contracts::{
    AuthorityClock, HostAuthorityClock, HostAuthorityFrontierStore, RootAuthorityDirectory,
};
use serde_json::json;
use std::sync::Arc;
use std::time::{Duration, Instant};

pub(super) fn writer_expiry(now: u64, issuer_expiry: u64) -> Result<u64> {
    let allowance = issuer_expiry
        .checked_sub(now)
        .and_then(|left| left.checked_sub(60_000))
        .filter(|left| *left > 0)
        .ok_or("original issuer has no finite writer/recovery window")?;
    Ok(now
        .checked_add(allowance.min(180_000))
        .ok_or("writer expiry overflow")?)
}

pub(super) fn wait_retirement(
    existing: &Existing,
    renewal: Option<&HostIssuerLeaseRenewalPlan>,
) -> Result<AuthorityLease> {
    let config = &existing.config;
    super::geometry::verify_existing_bind(&config.required_bind)?;
    // Open-existing checks prevent registry initialization from replacing a
    // missing canonical owner. These reads are observations, never use tokens.
    for name in ["authority-leases.lock", "authority-leases.json"] {
        fs::root_file(&config.state_dir.join("leases").join(name), false)?;
    }
    let root = RootAuthorityDirectory::open(&config.state_dir)?;
    let clock = Arc::new(HostAuthorityClock::open(
        root.clone(),
        "root-authority-clock-v1".into(),
    )?);
    let frontier = Arc::new(HostAuthorityFrontierStore::<AuthorityLeaseFrontier>::open(
        root,
        "root-authority-leases-v1".into(),
    )?);
    let registry = AuthorityLeaseRegistry::open_state_dir_with_trust(
        &config.state_dir.join("leases"),
        "root-authority-leases-v1".into(),
        clock.clone(),
        frontier,
    )?;
    let old = config.writer.as_ref().ok_or("original writer absent")?;
    let joint = existing.calculator.is_some();
    if renewal.is_some() && !joint {
        return Err("legacy Notes recovery cannot adopt an issuer renewal plan".into());
    }
    let end = Instant::now() + Duration::from_secs(185);
    loop {
        let issuer = registry
            .read_lease(&config.lease_id)?
            .ok_or("original issuer lease missing")?
            .lease;
        let issuer_matches = match renewal {
            Some(plan) => {
                plan.signer_id == config.signer_id
                    && plan.verifying_key == config.expected_verifying_key
                    && plan.previous_lease.lease_id == config.lease_id
                    && plan.previous_lease.revision == config.lease_revision
                    && (issuer == plan.previous_lease || issuer == plan.renewed_lease)
            }
            None => issuer.revision == config.lease_revision,
        };
        let original_expiry = renewal.map_or(issuer.expires_at_unix_ms, |plan| {
            plan.previous_lease.expires_at_unix_ms
        });
        let epoch = registry.frontier()?.authority_epoch;
        if !issuer_matches
            || issuer.lease_id != config.lease_id
            || issuer.authority_epoch != epoch
            || old.authority_lease.authority_epoch != epoch
            || registry.read_revocation(&config.lease_id)?.is_some()
            || registry
                .read_revocation(&old.authority_lease.lease_id)?
                .is_some()
            || registry
                .read_lease(&old.authority_lease.lease_id)?
                .is_none_or(|value| value.lease != old.authority_lease)
            || old.authority_lease.expires_at_unix_ms >= original_expiry
        {
            return Err(
                "original writer/issuer changed, was revoked, or lost its original finite window"
                    .into(),
            );
        }
        let now = clock.now_unix_ms()?;
        if !joint {
            writer_expiry(
                now.max(old.authority_lease.expires_at_unix_ms),
                issuer.expires_at_unix_ms,
            )?;
        }
        if now >= old.authority_lease.expires_at_unix_ms {
            return Ok(issuer);
        }
        if Instant::now() >= end {
            return Err("original writer did not expire in its finite recovery window".into());
        }
        std::thread::sleep(Duration::from_millis(20));
    }
}

pub(super) fn rotate(
    inputs: &Inputs,
    product: &Product,
    old: &Existing,
    actual: &HostAuthorityRegistration,
    issuer: &AuthorityLease,
) -> Result<RegistrationFiles> {
    let mut registration = actual.clone();
    registration.publisher_epoch = old
        .registration
        .publisher_epoch
        .checked_add(1)
        .ok_or("publisher epoch exhausted")?;
    let mut config: HostAuthorityServiceConfig = old.config.clone();
    if issuer.lease_id != config.lease_id
        || (issuer.revision != config.lease_revision
            && (!inputs.is_desktop()
                || config.lease_revision.checked_add(1) != Some(issuer.revision)))
    {
        return Err(
            "successor requires the same original issuer and exact selected revision".into(),
        );
    }
    config.lease_revision = issuer.revision;
    let prior = config.writer.as_ref().ok_or("original writer absent")?;
    let mut writer = prior.clone();
    let now = {
        let root = RootAuthorityDirectory::open(&config.state_dir)?;
        let clock = HostAuthorityClock::open(root, "root-authority-clock-v1".into())?;
        clock.now_unix_ms()?
    }; // Release the original administrative clock before the issuer factory.
    writer.spawn_generation = registration.registered_identity.spawn_generation;
    writer.owner_epoch = prior
        .owner_epoch
        .checked_add(1)
        .ok_or("owner epoch exhausted")?;
    writer.local_lease_generation = prior
        .local_lease_generation
        .checked_add(1)
        .ok_or("local generation exhausted")?;
    writer.authority_lease.lease_id = format!(
        "{}.authority-writer.{}",
        product.agent, writer.spawn_generation
    );
    writer.authority_lease.revision = 1;
    writer.authority_lease.issued_at_unix_ms = now;
    writer.authority_lease.expires_at_unix_ms = writer_expiry(now, issuer.expires_at_unix_ms)?;
    config.writer = Some(writer);
    let config_path = product.admin.join("authority-config.json");
    let registration_path = product.admin.join("owner-registration.json");
    fs::json_new(&config_path, &config)?;
    fs::json_new(&registration_path, &registration)?;
    let proof = rotate_host_writer_authorization(
        &config_path,
        old.config.writer.as_ref().ok_or("original writer absent")?,
        &old.proof,
    )?;
    fs::json_new(&product.admin.join("successor-writer-proof.json"), &proof)?;
    old.stage(product, "10-writer-rotated", &json!({"proof":proof,"registration":registration,
        "original_key":config.expected_verifying_key,"scope":"original canonical rotation; material adoption pending"}))?;
    let actual = authority::identity(&registration, product);
    let mut route = serde_json::from_value::<
        codex_hepta_agentd::text_session::AgentdTextSessionConfig,
    >(old.profile["interaction"]["route"].clone())?;
    route.spawn_generation = actual.spawn_generation;
    route.control_socket = actual.control_socket;
    let mut profile = old.profile.clone();
    profile["interaction"]["route"] = serde_json::to_value(&route)?;
    let notes_recovery = json!({
        "helper":inputs.programs.app_window.with_file_name("trill-notes-recovery"),
        "helper_sha256":fs::digest(&inputs.programs.app_window.with_file_name("trill-notes-recovery"))?,
        "state_directory":product.user.join("notes"),
        "previous_target":old.target,"selector":old.selection.notes()
    });
    let profile_path = product.admin.join(if inputs.is_desktop() {
        profile["schema"] = "hepta.root.desktop_launch_profile.v2".into();
        profile["previous_recovery"] = json!({
            "notes":notes_recovery,
            "calculator":{
                "helper":inputs.programs.app_window.with_file_name("trill-calculator-recovery"),
                "helper_sha256":fs::digest(&inputs.programs.app_window.with_file_name("trill-calculator-recovery"))?,
                "state_directory":product.user.join("calculator"),
                "previous_target":old.calculator.as_ref().ok_or("original Calculator target absent")?,
                "selector":old.selection.calculator()?
            }
        });
        "desktop-startup.json"
    } else {
        profile["previous_recovery"] = notes_recovery;
        "notes-startup.json"
    });
    fs::json_new(&profile_path, &profile)?;
    Ok(RegistrationFiles {
        config: config_path,
        registration: registration_path,
        profile: profile_path,
        objective: product
            .record
            .layout
            .home_root()
            .join(inputs.objective_profile_name()),
        route,
        verifying_key: config.expected_verifying_key,
        signer_id: config.signer_id,
    })
}
