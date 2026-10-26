//! Original empty replay frontier and trust enrollment for this fresh home.
use super::{Result, authority::RegistrationFiles, config::Inputs, fs, geometry::Fresh};
use codex_hepta_evidence::{HeptaEvidenceStore, ReplayCheckpoint};
use codex_state::SqliteConfig;
use codex_utils_absolute_path::AbsolutePathBuf;
use serde_json::json;
use std::path::PathBuf;

pub(super) async fn initialize(inputs: &Inputs, fresh: &Fresh) -> Result<PathBuf> {
    let home = AbsolutePathBuf::from_absolute_path(fresh.record.layout.home_root())?;
    let store = HeptaEvidenceStore::open(&SqliteConfig::from_sqlite_home(home)).await?;
    let result = async {
        if store.authbus_restore_checkpoint().await?.is_some() {
            return Err("fresh entry refuses an existing AuthBus replay checkpoint".into());
        }
        let digest = store.authbus_replay_frontier_digest().await?;
        store
            .initialize_authbus_restore_checkpoint(ReplayCheckpoint {
                generation: 1,
                digest,
            })
            .await?;
        let file = fresh.user.join("replay/authbus.json");
        fs::json_new_user(
            &file,
            &json!({ "schema_version":1,
            "agent_id":fresh.agent.as_str(), "generation":1, "digest":digest.to_string() }),
            inputs.uid,
            inputs.gid,
        )?;
        Ok::<_, Box<dyn std::error::Error>>(file)
    }
    .await;
    // The original SQLx pool must actually stop before custody transfer.
    store.close().await;
    result
}

pub(super) fn trust(fresh: &Fresh, files: &RegistrationFiles) -> Result<PathBuf> {
    let file = fresh
        .record
        .layout
        .home_root()
        .join("authbus-root-trust.json");
    fs::json_new(
        &file,
        &json!({
            "schema_version":1, "agent_id":fresh.agent.as_str(), "issuer_id":files.signer_id,
            "key_epoch":1, "public_key_hex":files.verifying_key.iter().map(|b| format!("{b:02x}")).collect::<String>(),
            "revoked":false, "thread_ids":[files.route.thread_id],
        }),
    )?;
    Ok(file)
}
