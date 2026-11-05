//! Same-boot recovery of the exact selected original generation.
//! No fresh fallback, repeated spawn or effect replay.
use super::recovery_preparation::RecoveryPreparation;
use super::{Result, authority, config::Inputs, fs, geometry::Product};
use codex_hepta_agentd::{
    HostAuthorityRegistration, HostAuthorityServiceConfig, HostSignedWriterAuthorizationV1,
    RetiredCheckpointPublisher,
};
use codex_hepta_memory::{
    CalculatorTargetIdentity, CognitiveCheckpointPeerLifetime, NotesTargetIdentity,
};
use serde_json::Value;
use std::path::PathBuf;
use std::sync::Arc;

use super::recovery_composition::Composition;
pub(crate) use super::recovery_selection::RecoverySelection;

pub(super) struct Existing {
    pub config: HostAuthorityServiceConfig,
    pub registration: HostAuthorityRegistration,
    pub proof: HostSignedWriterAuthorizationV1,
    pub seed: super::seed::ThreadSeed,
    pub calculator: Option<CalculatorTargetIdentity>,
    pub generation: u64,
    pub source_admin: PathBuf,
    pub target: NotesTargetIdentity,
    pub profile: Value,
    pub selection: RecoverySelection,
    preparation: Arc<RecoveryPreparation>,
}

impl Existing {
    pub(super) fn open(
        inputs: &Inputs,
        selection: RecoverySelection,
        generation: u64,
    ) -> Result<(Self, Product)> {
        selection.validate_for(inputs)?;
        let admin = inputs.prefix.join("admin");
        let preparation = Arc::new(RecoveryPreparation::acquire(&admin, generation)?);
        let source_admin = super::recovery_selection::generation_directory(&admin, generation)?;
        fs::root_directory(&source_admin)?;
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
            fs::read_root_json(&source_admin.join("authority-config.json"))?;
        let registration: HostAuthorityRegistration =
            fs::read_root_json(&source_admin.join("owner-registration.json"))?;
        let writer = config
            .writer
            .as_ref()
            .ok_or("original writer registration absent")?;
        if writer.local_lease_generation != generation
            || writer.spawn_generation != registration.registered_identity.spawn_generation
            || writer.registered_agent_id != registration.registered_identity.agent_id
        {
            return Err(
                "selected generation differs from the original writer and actual registration"
                    .into(),
            );
        }
        let composition: Composition =
            fs::read_root_json(&source_admin.join("actual-composition.json"))?;
        let proof = fs::read_root_json(&source_admin.join(if generation == 1 {
            "original-writer-proof.json"
        } else {
            "successor-writer-proof.json"
        }))?;
        let profile: Value = fs::read_root_json(&source_admin.join(if inputs.is_desktop() {
            "desktop-startup.json"
        } else {
            "notes-startup.json"
        }))?;
        let layout = codex_hepta_paths::HeptaFleetRoot::parse(
            registration.registered_identity.fleet_root.clone(),
        )?
        .layout()
        .agent(&registration.registered_identity.agent_id);
        let seed = super::recovery_composition::original_seed(inputs, &admin, layout.home_root())?;
        composition.validate(
            inputs,
            &registration,
            &seed,
            &profile,
            layout.home_root(),
            generation,
        )?;
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
        let mut product =
            Product::open_existing(inputs, &config, &registration, preparation.clone())?;
        let artifacts: Value = fs::read_root_json(&admin.join("actual-artifacts.json"))?;
        if artifacts != authority::artifacts(inputs)? {
            return Err(
                "recovery executable/source artifacts differ from original frozen files".into(),
            );
        }
        product.admin = preparation.directory.clone();
        let old = Self {
            config,
            registration,
            proof,
            seed,
            calculator: composition.calculator_target,
            generation,
            source_admin,
            target: composition.notes_target,
            profile,
            selection,
            preparation,
        };
        old.preparation.admit(&serde_json::json!({"original_owner":old.registration,
            "old_target":old.target,"old_calculator":old.calculator,"original_thread":old.seed,"operation_selector":old.selection,"previous_generation":old.generation,
            "scope":"same-boot existing state selected; no recovery success or operation outcome asserted"}))?;
        Ok((old, product))
    }

    pub(super) fn stage(
        &self,
        product: &Product,
        name: &str,
        value: &impl serde::Serialize,
    ) -> Result<()> {
        if name == "05-old-sockets-retired" {
            return self.preparation.sockets_retired(value);
        }
        fs::json_new(&product.admin.join(format!("{name}.json")), value)
    }

    pub(super) fn issuer_plan(
        &self,
    ) -> Result<Option<codex_hepta_agentd::HostIssuerLeaseRenewalPlan>> {
        self.preparation.issuer_plan()
    }

    pub(super) fn record_issuer_plan(
        &self,
        plan: &codex_hepta_agentd::HostIssuerLeaseRenewalPlan,
    ) -> Result<()> {
        self.preparation.issuer_planned(plan)
    }

    pub(super) fn record_issuer_commit(
        &self,
        lease: &codex_hepta_contracts::authority_lease::AuthorityLease,
    ) -> Result<()> {
        self.preparation.issuer_committed(lease)
    }

    pub(super) fn consume_spawn(&self) -> Result<()> {
        self.preparation.consume_spawn()
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
