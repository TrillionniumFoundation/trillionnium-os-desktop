//! Original empty replay frontier and trust enrollment for this fresh home.
use super::{Result, authority::RegistrationFiles, config::Inputs, fs, geometry::Product};
use codex_hepta_evidence::{HeptaEvidenceStore, ReplayCheckpoint};
use codex_state::SqliteConfig;
use codex_utils_absolute_path::AbsolutePathBuf;
use serde_json::json;
use std::path::PathBuf;

pub(super) async fn initialize(inputs: &Inputs, fresh: &Product) -> Result<PathBuf> {
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

pub(super) fn trust(fresh: &Product, files: &RegistrationFiles) -> Result<PathBuf> {
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

/// Reuse only the actual existing external checkpoint. The original Agentd
/// verifies its durable frontier against the original evidence DB at startup.
/// No evidence database is opened/initialized by Root during recovery.
pub(super) fn existing(inputs: &Inputs, product: &Product) -> Result<PathBuf> {
    use std::os::unix::fs::MetadataExt;
    let file = product.user.join("replay/authbus.json");
    fs::user_directory(file.parent().ok_or("checkpoint parent")?, inputs.uid)?;
    let stat = std::fs::symlink_metadata(&file)?;
    if !stat.is_file()
        || stat.uid() != inputs.uid
        || stat.mode() & 0o7777 != 0o600
        || stat.nlink() != 1
        || stat.len() > 16384
    {
        return Err("existing original AuthBus checkpoint custody differs".into());
    }
    Ok(file)
}

pub(super) fn consumer_root(inputs: &Inputs, product: &Product) -> Result<PathBuf> {
    let path = product.record.layout.agent_root().join("final-use");
    fs::user_directory(&path, inputs.uid)?;
    for lane in ["device", "notes"] {
        let directory = path.join(lane);
        fs::user_directory(&directory, inputs.uid)?;
        for name in ["authority.lock", "authority.json", "authority.claims"] {
            use std::os::unix::fs::MetadataExt;
            let entry = directory.join(name);
            let m = std::fs::symlink_metadata(&entry)?;
            if !m.is_file()
                || m.uid() != inputs.uid
                || m.mode() & 0o7777 != 0o600
                || m.nlink() != 1
                || entry.canonicalize()? != entry
            {
                return Err(
                    "existing FinalUse state/journal is absent or changed; no empty initialization"
                        .into(),
                );
            }
        }
    }
    Ok(path)
}
