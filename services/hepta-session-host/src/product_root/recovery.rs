//! One explicit same-boot recovery episode. No fresh fallback or effect replay.
use super::{Result, authority, config::Inputs, fs, geometry::Product};
use codex_hepta_agentd::{
    HostAuthorityRegistration, HostAuthorityServiceConfig, HostSignedWriterAuthorizationV1,
    NotesThreadSeedReceipt, RetiredCheckpointPublisher,
};
use codex_hepta_memory::{CognitiveCheckpointPeerLifetime, NotesTargetIdentity};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::PathBuf;

/// A request to select original records after the canonical owner has opened.
/// Root does not resolve latest by reading the database or inventing an ID.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub(crate) enum RecoverySelection {
    ExactOperation { operation_id: String },
    LatestRecordedOriginalNotes,
}

impl RecoverySelection {
    pub(crate) fn from_arguments(
        mut args: impl Iterator<Item = std::ffi::OsString>,
    ) -> Result<Self> {
        let selection = match args.next().as_deref().and_then(std::ffi::OsStr::to_str) {
            Some("--operation-id") => Self::ExactOperation {
                operation_id: args
                    .next()
                    .ok_or("missing original operation selector")?
                    .into_string()
                    .map_err(|_| "operation selector must be UTF-8")?,
            },
            Some("--latest-original-notes") => Self::LatestRecordedOriginalNotes,
            _ => return Err("recovery requires an explicit original operation selector".into()),
        };
        if args.next().is_some() {
            return Err("unexpected or competing recovery selector".into());
        }
        selection.validate()?;
        Ok(selection)
    }

    fn validate(&self) -> Result<()> {
        if let Self::ExactOperation { operation_id } = self {
            codex_hepta_types::StableId::new(operation_id)?;
        }
        Ok(())
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Composition {
    schema: String,
    scope: String,
    registration: HostAuthorityRegistration,
    original_thread_seed: NotesThreadSeedReceipt,
    objective_profile: PathBuf,
    notes_state_dir: PathBuf,
    notes_target: NotesTargetIdentity,
    session_pid: u32,
    session_birth: String,
    bootstrap_model_turn_sent: bool,
}

pub(super) struct Existing {
    pub config: HostAuthorityServiceConfig,
    pub registration: HostAuthorityRegistration,
    pub proof: HostSignedWriterAuthorizationV1,
    pub seed: NotesThreadSeedReceipt,
    pub target: NotesTargetIdentity,
    pub profile: Value,
    pub selection: RecoverySelection,
}

impl Existing {
    pub(super) fn open(inputs: &Inputs, selection: RecoverySelection) -> Result<(Self, Product)> {
        selection.validate()?;
        let admin = inputs.prefix.join("admin");
        let original_inputs: Inputs = fs::read_root_json(&admin.join("original-inputs.json"))?;
        let mut expected = serde_json::to_value(original_inputs)?;
        let mut actual = serde_json::to_value(inputs)?;
        expected
            .as_object_mut()
            .ok_or("original input object")?
            .remove("environment");
        actual
            .as_object_mut()
            .ok_or("current input object")?
            .remove("environment");
        if expected != actual {
            return Err(
                "recovery source/program/identity inputs differ from the original deployment"
                    .into(),
            );
        }
        let config: HostAuthorityServiceConfig =
            fs::read_root_json(&admin.join("authority-config.json"))?;
        let registration: HostAuthorityRegistration =
            fs::read_root_json(&admin.join("owner-registration.json"))?;
        let composition: Composition = fs::read_root_json(&admin.join("actual-composition.json"))?;
        let seed: NotesThreadSeedReceipt =
            fs::read_root_json(&admin.join("original-thread-seed.json"))?;
        seed.verify_persisted()?;
        let proof = fs::read_root_json(&admin.join("original-writer-proof.json"))?;
        let profile: Value = fs::read_root_json(&admin.join("notes-startup.json"))?;
        let layout = codex_hepta_paths::HeptaFleetRoot::parse(
            registration.registered_identity.fleet_root.clone(),
        )?
        .layout()
        .agent(&registration.registered_identity.agent_id);
        if composition.schema != "trill.original-desktop-root.composition.v1"
            || composition.scope.len() > 4096
            || composition.bootstrap_model_turn_sent
            || serde_json::to_value(&composition.registration)?
                != serde_json::to_value(&registration)?
            || serde_json::to_value(&composition.original_thread_seed)?
                != serde_json::to_value(&seed)?
            || composition.notes_state_dir != inputs.prefix.join("u/notes")
            || composition.objective_profile != layout.home_root().join("notes-thread-profile.json")
            || seed.codex_home != layout.home_root()
            || profile["interaction"]["seed"] != serde_json::to_value(&seed)?
            || profile["interaction"]["kind"] != "original_thread_tool_v1"
            || profile["bindings"]["model_tuple_digest"] != seed.model_tuple_digest()?.to_string()
            || profile["grant_lifetime_ms"] != inputs.grant_lifetime_ms
        {
            return Err(
                "original composition/thread/Notes bindings differ or are incomplete".into(),
            );
        }
        composition.notes_target.validate()?;
        let boot = std::fs::read_to_string("/proc/sys/kernel/random/boot_id")?;
        let session = session_lifetime(
            composition.session_pid,
            &composition.session_birth,
            inputs.uid,
        )?;
        if registration.boot_id != boot.trim() || session.boot_id != registration.boot_id {
            return Err("product recovery supports only the original same boot".into());
        }
        // These original typed factories independently observe actual kernel
        // retirement. Serialized PIDs are never adopted or signalled here.
        let _owner_retired =
            RetiredCheckpointPublisher::observe(CognitiveCheckpointPeerLifetime {
                uid: inputs.uid,
                pid: registration.peer_pid,
                boot_id: registration.boot_id.clone(),
                process_start_ticks: registration.process_start_ticks,
            })?;
        let _session_retired = RetiredCheckpointPublisher::observe(session)?;
        let mut product = Product::open_existing(inputs, &config, &registration)?;
        let artifacts: Value = fs::read_root_json(&admin.join("actual-artifacts.json"))?;
        if artifacts != authority::artifacts(inputs)? {
            return Err(
                "recovery executable/source artifacts differ from original frozen files".into(),
            );
        }
        let stage = admin.join("recovery");
        // Existing means partial or an already consumed episode. No new target
        // is reserved on retry, even if policy CAS might already have committed.
        fs::directory_new(&stage, 0o700, None)?;
        product.admin = stage;
        let old = Self {
            config,
            registration,
            proof,
            seed,
            target: composition.notes_target,
            profile,
            selection,
        };
        old.stage(&product, "00-admitted", &serde_json::json!({"original_owner":old.registration,
            "old_target":old.target,"original_thread":old.seed,"operation_selector":old.selection,
            "scope":"same-boot existing state selected; no recovery success or operation outcome asserted"}))?;
        Ok((old, product))
    }

    pub(super) fn stage(
        &self,
        product: &Product,
        name: &str,
        value: &impl serde::Serialize,
    ) -> Result<()> {
        fs::json_new(&product.admin.join(format!("{name}.json")), value)
    }
}

fn session_lifetime(pid: u32, birth: &str, uid: u32) -> Result<CognitiveCheckpointPeerLifetime> {
    let fields = birth.split(':').collect::<Vec<_>>();
    if fields.len() != 3 || fields[1].parse::<u32>()? != pid || fields[2].parse::<u64>()? == 0 {
        return Err("original Session birth metadata is incomplete".into());
    }
    Ok(CognitiveCheckpointPeerLifetime {
        uid,
        pid,
        boot_id: fields[0].into(),
        process_start_ticks: fields[2].parse()?,
    })
}

#[cfg(test)]
#[path = "recovery_tests.rs"]
mod tests;
