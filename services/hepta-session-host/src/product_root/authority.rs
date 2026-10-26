//! Fresh explicit Root administration through the ORIGINAL authority factories.
use super::{Result, config::Inputs, fs, geometry::Fresh};
use codex_hepta_agentd::{
    AgentdIdentity, DeploymentFinalUseIssuer, DeploymentGrantPolicy, HostAuthorityBootstrap,
    HostAuthorityConsumerConfig, HostAuthorityConsumersConfig, HostAuthorityRegistration,
    HostAuthorityServiceConfig, HostAuthoritySocketPaths, HostAuthorityWriterRegistration,
    HostIssuerRecordProfile, NotesThreadSeedReceipt, initialize_host_authority,
    register_host_writer_authorization,
};
use codex_hepta_contracts::authority_lease::{
    AuthorityLease, AuthorityLeaseBinding, AuthorityLeaseFrontier, AuthorityLeaseRegistry,
};
use codex_hepta_contracts::{
    AuthorityClock, HostAuthorityClock, HostAuthorityFrontierStore, RootAuthorityDirectory,
};
use codex_hepta_memory::NotesTargetIdentity;
use codex_hepta_types::Digest32;
use serde_json::json;
use std::path::PathBuf;
use std::sync::Arc;

pub(super) struct RegistrationFiles {
    pub config: PathBuf,
    pub registration: PathBuf,
    pub profile: PathBuf,
    pub objective: PathBuf,
    pub route: codex_hepta_agentd::text_session::AgentdTextSessionConfig,
    pub verifying_key: [u8; 32],
    pub signer_id: String,
}

pub(super) fn identity(registration: &HostAuthorityRegistration, fresh: &Fresh) -> AgentdIdentity {
    let i = &registration.registered_identity;
    AgentdIdentity {
        agent_id: i.agent_id.clone(),
        spawn_generation: i.spawn_generation,
        fleet_root: i.fleet_root.clone(),
        workspace: i.workspace.clone(),
        resources: i.resources.clone(),
        home_root: fresh.record.layout.home_root().to_path_buf(),
        run_root: fresh.record.layout.run_root().to_path_buf(),
        control_socket: fresh.record.layout.agentd_control_socket().to_path_buf(),
        app_server_socket: fresh.record.layout.app_server_socket().to_path_buf(),
        layout: fresh.record.layout.clone(),
    }
}

pub(super) fn initialize(
    inputs: &Inputs,
    fresh: &Fresh,
    registration: &HostAuthorityRegistration,
    seed: &NotesThreadSeedReceipt,
    target: &NotesTargetIdentity,
) -> Result<RegistrationFiles> {
    if !fresh.mounted() {
        return Err("original Root bind changed".into());
    }
    let actual = identity(registration, fresh);
    let signer_id = format!("desktop-root-{}", fresh.agent.as_str());
    let root_lease_id = format!("{signer_id}.issuer");
    let artifacts = json!({
        "schema":"trill.original-product-artifacts.v1",
        "agentd":fs::digest(&inputs.programs.agentd)?,
        "app_server":fs::digest(&inputs.programs.app_server)?,
        "authority_host":fs::digest(&inputs.programs.authority_host)?,
        "session":fs::digest(&inputs.programs.session)?,
        "shell":fs::digest(&inputs.programs.shell)?,
        "app_window":fs::digest(&inputs.programs.app_window)?,
        "human_provider":fs::digest(&inputs.programs.human_provider)?,
        "sdk":fs::digest(&inputs.sources.sdk)?,
        "source_freeze":fs::digest(&inputs.sources.source_freeze)?,
    });
    let artifact_set = Digest32::of_bytes(&serde_json::to_vec(&artifacts)?);
    fs::json_new(&fresh.admin.join("actual-artifacts.json"), &artifacts)?;
    let policies = vec![
        DeploymentGrantPolicy {
            subject_id: fresh.agent.to_string(),
            destination_id: DeploymentFinalUseIssuer::OBJECTIVE_DESTINATION.into(),
            scope_sha256: DeploymentFinalUseIssuer::objective_scope_digest(&actual),
            lifetime_ms: inputs.grant_lifetime_ms,
        },
        DeploymentGrantPolicy {
            subject_id: fresh.agent.to_string(),
            destination_id: DeploymentFinalUseIssuer::text_destination(&seed.thread_id)?,
            scope_sha256: DeploymentFinalUseIssuer::text_scope(&fresh.agent),
            lifetime_ms: inputs.grant_lifetime_ms,
        },
        DeploymentGrantPolicy {
            subject_id: fresh.agent.to_string(),
            destination_id: target.destination_id(),
            scope_sha256: target.scope_digest().into_array(),
            lifetime_ms: inputs.grant_lifetime_ms,
        },
    ];
    let root_binding = AuthorityLeaseBinding {
        principal_id: fresh.agent.to_string(),
        operation_class: "runtime.agentd.root_issuer".into(),
        destination_id: signer_id.clone(),
        scope_sha256: artifact_set.into_array(),
        payload_sha256: artifact_set.into_array(),
    };
    let bootstrap_path = fresh.admin.join("authority-bootstrap.json");
    let bootstrap = json!({ "schema_version":1, "required_bind":&fresh.bind,
        "signer_id":&signer_id, "policies":&policies, "lease_id":&root_lease_id,
        "lease_binding":root_binding, "lease_lifetime_ms":inputs.lifetime_ms });
    // Typed original schema validation, never a Desktop authority data model.
    let _: HostAuthorityBootstrap = serde_json::from_value(bootstrap.clone())?;
    fs::json_new(&bootstrap_path, &bootstrap)?;
    let initialized = initialize_host_authority(&fresh.authority, &bootstrap_path)?;
    let writer = {
        let root = RootAuthorityDirectory::open(&fresh.authority)?;
        let clock = Arc::new(HostAuthorityClock::open(
            root.clone(),
            "root-authority-clock-v1".into(),
        )?);
        let frontier = Arc::new(HostAuthorityFrontierStore::<AuthorityLeaseFrontier>::open(
            root,
            "root-authority-leases-v1".into(),
        )?);
        let leases = AuthorityLeaseRegistry::open_state_dir_with_trust(
            &fresh.authority.join("leases"),
            "root-authority-leases-v1".into(),
            clock.clone(),
            frontier,
        )?;
        let original = leases
            .read_lease(&root_lease_id)?
            .ok_or("original issuer lease is absent")?
            .lease;
        let now = clock.now_unix_ms()?;
        HostAuthorityWriterRegistration {
            registered_agent_id: fresh.agent.clone(),
            spawn_generation: actual.spawn_generation,
            owner_epoch: 1,
            local_lease_id: format!("{}.writer.{}", fresh.agent, actual.spawn_generation),
            local_lease_generation: 1,
            authority_lease: AuthorityLease {
                schema_version: 1,
                lease_id: format!("{}.authority-writer", fresh.agent),
                authority_epoch: original.authority_epoch,
                revision: 1,
                binding: AuthorityLeaseBinding {
                    principal_id: fresh.agent.to_string(),
                    operation_class: "runtime.agentd.production_writer".into(),
                    destination_id: fresh.agent.to_string(),
                    scope_sha256: DeploymentFinalUseIssuer::objective_scope_digest(&actual),
                    payload_sha256: artifact_set.into_array(),
                },
                issued_at_unix_ms: now,
                expires_at_unix_ms: original.expires_at_unix_ms,
            },
        }
    }; // Release the same original administrative clock/registry before open.
    let run = fresh.record.layout.run_root();
    let config = HostAuthorityServiceConfig {
        schema_version: 1,
        state_dir: fresh.authority.clone(),
        required_bind: fresh.bind.clone(),
        signer_id: signer_id.clone(),
        expected_verifying_key: initialized.verifying_key,
        lease_id: initialized.lease_id,
        lease_revision: initialized.lease_revision,
        writer: Some(writer),
        checkpoint_state_dir: Some(fresh.authority.join("checkpoint")),
        consumers: Some(HostAuthorityConsumersConfig {
            device: HostAuthorityConsumerConfig {
                state_dir: fresh.authority.join("device"),
                owner_id: signer_id.clone(),
            },
            notes: HostAuthorityConsumerConfig {
                state_dir: fresh.authority.join("notes"),
                owner_id: signer_id.clone(),
            },
        }),
        sockets: HostAuthoritySocketPaths {
            observation: run.join("root-observation.sock"),
            issuer: run.join("root-issuer.sock"),
            checkpoint: run.join("root-checkpoint.sock"),
            device_frontier: Some(run.join("root-device.sock")),
            notes_frontier: Some(run.join("root-notes.sock")),
        },
        peer_uid: inputs.uid,
        peer_gid: inputs.gid,
        timeout_ms: 5_000,
        lifetime_ms: inputs.lifetime_ms,
        issuer_record_profile: HostIssuerRecordProfile::TextRecovery,
    };
    let config_path = fresh.admin.join("authority-config.json");
    let registration_path = fresh.admin.join("owner-registration.json");
    fs::json_new(&config_path, &config)?;
    fs::json_new(&registration_path, registration)?;
    let proof = register_host_writer_authorization(&config_path)?;
    fs::json_new(&fresh.admin.join("original-writer-proof.json"), &proof)?;
    let route = codex_hepta_agentd::text_session::AgentdTextSessionConfig {
        control_socket: actual.control_socket.clone(),
        agent_id: actual.agent_id.clone(),
        spawn_generation: actual.spawn_generation,
        thread_id: seed.thread_id.clone(),
        app_server_session_id: seed.app_server_session_id.clone(),
        codex_home: actual.home_root.clone(),
    };
    let principal_scope = "organ.desktop.notes";
    let principal_scope_digest = Digest32::of_bytes(&serde_json::to_vec(&(
        "trill.desktop.original-notes-scope.v1",
        fresh.agent.as_str(),
        &signer_id,
    ))?);
    let objective = fresh
        .record
        .layout
        .home_root()
        .join("notes-thread-profile.json");
    let admission = codex_hepta_objective::thread_notes_admission_profile_json_v1(
        principal_scope,
        principal_scope_digest,
        &signer_id,
    )
    .map_err(std::io::Error::other)?;
    fs::write_new(&objective, admission.as_bytes())?;
    let profile = fresh.admin.join("notes-startup.json");
    fs::json_new(
        &profile,
        &json!({
            "schema":"hepta.root.notes_launch_profile.v1", "grant_lifetime_ms": inputs.grant_lifetime_ms,
            "interaction":{"kind":"original_thread_tool_v1", "route":&route, "seed":seed},
            "bindings": { "principal_scope":principal_scope,
                "principal_scope_digest": principal_scope_digest.to_string(), "issuer_id":&signer_id,
                "policy_generation":1, "locale":&inputs.locale,
                "runtime_body_digest":fs::digest(&inputs.sources.runtime_body)?,
                "preference_state_digest":fs::digest(&inputs.sources.preferences)?,
                "model_tuple_digest":seed.model_tuple_digest()?.to_string(),
                "prompt_registry_digest":fs::digest(&inputs.sources.prompt_registry)?,
                "artifact_set_digest":artifact_set.to_string() }
        }),
    )?;
    Ok(RegistrationFiles {
        config: config_path,
        registration: registration_path,
        profile,
        objective,
        route,
        verifying_key: initialized.verifying_key,
        signer_id,
    })
}
