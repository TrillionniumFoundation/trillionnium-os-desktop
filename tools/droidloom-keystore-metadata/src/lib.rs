//! Clone-only Keystore metadata experiments. This crate has no in-place write path.
//!
//! SQLite only opens a fresh private copy owned by this process. The source is
//! read with O_NOFOLLOW/O_NOATIME; sidecars and links are refused. Hash equality
//! is not proof that a live database was quiescent. Clone preparation therefore
//! also needs external, digest-bound offline-copy and backend provenance.
//! Reports never assert per-key authentication or production readiness.
mod certificates;
mod database;
mod evidence;
mod snapshot;

use serde_json::{Value, json};
use std::path::PathBuf;

/// Errors are intentionally fixed, non-sensitive codes.
pub type Result<T> = std::result::Result<T, &'static str>;

/// Inputs for an audit or a new clone experiment.
pub struct Request {
    /// A cold copy named persistent.sqlite. Never opened by SQLite.
    pub input: PathBuf,
    /// Existing directory outside the input directory, for a new private child.
    pub workspace: PathBuf,
    /// Absent for audit; a provenance envelope for clone preparation.
    pub evidence: Option<PathBuf>,
}

/// Audit a cold copy or prepare a new clone. Never replace the source database.
pub fn run(request: &Request) -> Result<Value> {
    let copy = snapshot::PrivateCopy::new(&request.input, &request.workspace)?;
    let binding = request
        .evidence
        .as_ref()
        .map(|path| evidence::verify(path, &copy.input_sha256))
        .transpose()?;
    let mut db = database::open(copy.database_path())?;
    database::validate_schema(&db)?;
    let candidates = database::candidates(&db)?;
    let certificate_summary = certificates::summarize(&db)?;
    let before = database::fingerprints(&db, &Default::default())?;
    let expected = database::fingerprints(&db, &candidates.ids)?;
    let changed = if binding.is_some() {
        database::apply_to_private_copy(&mut db, &candidates, &expected)?
    } else {
        0
    };
    let after = database::fingerprints(&db, &Default::default())?;
    drop(db);
    copy.verify_input_unchanged()?;
    let output_sha = snapshot::hash_file(&copy.database_path())?.sha256;
    let mut report = json!({
        "schema": 1,
        "operation": if binding.is_some() { "prepare_clone_experiment" } else { "audit" },
        "input_sha256": copy.input_sha256,
        "input_bytes_unchanged": true,
        "input_sqlite_connections": 0,
        "source_quiescence_verified_by_tool": false,
        "sidecars_supported": false,
        "schema_source_commit": "cbb2ef1617a94d6cdf2dc2ccb7a545575dbb20cb",
        "schema_version": 2,
        "uuid_is_backend_identity": false,
        "backend_binding": binding,
        "counts": candidates.counts,
        "historical_certificate_attestation": certificate_summary,
        "changed_authorization_rows": changed,
        "before": before,
        "after": after,
        "output_database_sha256": output_sha,
        "invariants_verified": if changed > 0 { after == expected } else { after == before },
        "offline_keyblob_authentication_performed": false,
        "super_encryption_decrypted": false,
        "key_material_exported": false,
        "production_approved": false,
        "required_runtime_qualification": [
            "stock CP3A Keystore routing and KeyInfo on the isolated data copy",
            "original key operations through authenticated KeyMint upgrade",
            "HAT/lock-state/purpose/usage-count and caller/grant denial checks",
            "restart, idempotence and original-data preservation"
        ]
    });
    if request.evidence.is_some() {
        // Only our new private child is retained. There is no output-db/in-place flag.
        let output_dir = copy.directory().to_owned();
        report["output_directory"] = json!(output_dir);
        snapshot::write_new_json(&output_dir.join("CLONE-EXPERIMENT.json"), &report)?;
        std::fs::File::open(&output_dir)
            .and_then(|d| d.sync_all())
            .map_err(|_| "private_directory_sync_failed")?;
        copy.persist()?;
    }
    Ok(report)
}

#[cfg(test)]
mod tests;
