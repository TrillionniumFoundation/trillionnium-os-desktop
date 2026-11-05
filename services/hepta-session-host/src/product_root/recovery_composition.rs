//! Read the exact original profile and durable App identities from Root custody.
//! This metadata selects existing owners; it never supplies a receipt or Current.
use super::{Result, config::Inputs, fs, seed::ThreadSeed};
use codex_hepta_agentd::{
    DesktopThreadSeedReceipt, HostAuthorityRegistration, NotesThreadSeedReceipt,
};
use codex_hepta_memory::{CalculatorTargetIdentity, NotesTargetIdentity};
use serde::Deserialize;
use serde_json::Value;
use std::path::{Path, PathBuf};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Composition {
    pub schema: String,
    pub scope: String,
    pub registration: HostAuthorityRegistration,
    pub original_thread_seed: Value,
    pub objective_profile: PathBuf,
    pub notes_state_dir: PathBuf,
    pub notes_target: NotesTargetIdentity,
    pub session_pid: u32,
    pub session_birth: String,
    pub bootstrap_model_turn_sent: bool,
    #[serde(default)]
    pub profile: Option<String>,
    #[serde(default)]
    pub calculator_target: Option<CalculatorTargetIdentity>,
    #[serde(default)]
    pub calculator_state_dir: Option<PathBuf>,
}

pub(super) fn original_seed(inputs: &Inputs, admin: &Path, home: &Path) -> Result<ThreadSeed> {
    let path = admin.join("original-thread-seed.json");
    if inputs.is_desktop() {
        let seed: DesktopThreadSeedReceipt = fs::read_root_json(&path)?;
        seed.verify_persisted()?;
        if seed.codex_home != home {
            return Err("original Desktop seed home changed".into());
        }
        Ok(ThreadSeed::Desktop(seed))
    } else {
        let seed: NotesThreadSeedReceipt = fs::read_root_json(&path)?;
        seed.verify_persisted()?;
        if seed.codex_home != home {
            return Err("original Notes seed home changed".into());
        }
        Ok(ThreadSeed::Notes(seed))
    }
}

impl Composition {
    pub(super) fn validate(
        &self,
        inputs: &Inputs,
        registration: &HostAuthorityRegistration,
        seed: &ThreadSeed,
        profile: &Value,
        home: &Path,
        generation: u64,
    ) -> Result<()> {
        let joint = inputs.is_desktop();
        let expected_schema = if joint {
            "trill.original-desktop-root.composition.v3"
        } else {
            "trill.original-desktop-root.composition.v1"
        };
        let interaction = if joint {
            "original_desktop_thread_tool_v1"
        } else {
            "original_thread_tool_v1"
        };
        let launch_schema = if joint {
            if generation == 1 {
                "hepta.root.desktop_launch_profile.v1"
            } else {
                "hepta.root.desktop_launch_profile.v2"
            }
        } else {
            "hepta.root.notes_launch_profile.v1"
        };
        if self.schema != expected_schema
            || self.scope.len() > 4096
            || self.bootstrap_model_turn_sent
            || serde_json::to_value(&self.registration)? != serde_json::to_value(registration)?
            || self.original_thread_seed != serde_json::to_value(seed)?
            || self.notes_state_dir != inputs.prefix.join("u/notes")
            || self.objective_profile != home.join(inputs.objective_profile_name())
            || profile["schema"] != launch_schema
            || profile["interaction"]["seed"] != serde_json::to_value(seed)?
            || profile["interaction"]["kind"] != interaction
            || profile["bindings"]["model_tuple_digest"] != seed.model_tuple_digest()?.to_string()
            || profile["grant_lifetime_ms"] != inputs.grant_lifetime_ms
        {
            return Err(
                "original composition/thread/target bindings differ or are incomplete".into(),
            );
        }
        self.notes_target.validate()?;
        match (
            joint,
            &self.profile,
            &self.calculator_target,
            &self.calculator_state_dir,
        ) {
            (true, Some(name), Some(calculator), Some(state))
                if name == "notes_calculator_v1"
                    && profile["profile"] == "notes_calculator_v1"
                    && *state == inputs.prefix.join("u/calculator") =>
            {
                calculator.validate()?;
                if self.notes_target.task_id != 1
                    || calculator.task_id != 2
                    || self.notes_target.session_instance != calculator.session_instance
                    || self.notes_target.incarnation == calculator.incarnation
                {
                    return Err(
                        "original joint App identities do not share one distinct Session".into(),
                    );
                }
            }
            (false, None, None, None) => {}
            _ => {
                return Err(
                    "joint recovery requires its exact durable Calculator composition".into(),
                );
            }
        }
        Ok(())
    }
}
