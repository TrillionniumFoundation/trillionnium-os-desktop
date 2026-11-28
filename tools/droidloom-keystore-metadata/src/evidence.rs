use crate::{Result, snapshot};
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

const PROVIDER: &str = "Droidloom software KeyMint (KMR legacy v1)";
const KEYMINT_PIN: &str = "cfeefc94bf8c4f19d19dca193d376a1fc05e8e3e";
const INTERFACES_PIN: &str = "0162af698935100a590b7359581ac8b1b80693e5";
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Artifact {
    path: PathBuf,
    sha256: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Envelope {
    schema: u32,
    input_sha256: String,
    snapshot_receipt: Artifact,
    legacy_provenance: Artifact,
    replacement_observation: Artifact,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ColdCopy {
    schema: u32,
    method: String,
    input_sha256: String,
    sqlite_sidecars_absent: bool,
    cold_image_copy_receipt: Artifact,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Legacy {
    schema: u32,
    implementation: String,
    keymint_source_commit: String,
    interfaces_source_commit: String,
    default_service_executable: Artifact,
    custody_receipt: Artifact,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Replacement {
    schema: u32,
    service: String,
    observation_method: String,
    source_commit: String,
    security_level: i32,
    implementation_name: String,
    default_service_executable: Artifact,
    candidate_vendor_image: Artifact,
    runtime_receipt: Artifact,
}
fn digest_valid(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
fn check(artifact: &Artifact) -> Result<()> {
    if !digest_valid(&artifact.sha256, 64)
        || snapshot::hash_file(&artifact.path)?.sha256 != artifact.sha256
    {
        return Err("evidence_artifact_digest_mismatch");
    }
    Ok(())
}
fn decode<T: for<'de> Deserialize<'de>>(artifact: &Artifact) -> Result<T> {
    let (value, digest) = snapshot::read_json(&artifact.path)?;
    if !digest_valid(&artifact.sha256, 64) || digest != artifact.sha256 {
        return Err("evidence_artifact_digest_mismatch");
    }
    serde_json::from_value(value).map_err(|_| "evidence_structure_invalid")
}
pub(crate) fn verify(path: &Path, input_sha256: &str) -> Result<Value> {
    let (envelope_value, envelope_sha256) = snapshot::read_json(path)?;
    let envelope: Envelope =
        serde_json::from_value(envelope_value).map_err(|_| "evidence_envelope_invalid")?;
    if envelope.schema != 1 || envelope.input_sha256 != input_sha256 {
        return Err("evidence_input_binding_mismatch");
    }
    let cold: ColdCopy = decode(&envelope.snapshot_receipt)?;
    if cold.schema != 1
        || cold.method != "isolated-offline-filesystem-copy"
        || cold.input_sha256 != input_sha256
        || !cold.sqlite_sidecars_absent
    {
        return Err("offline_snapshot_provenance_missing");
    }
    check(&cold.cold_image_copy_receipt)?;
    let legacy: Legacy = decode(&envelope.legacy_provenance)?;
    if legacy.schema != 1
        || legacy.implementation != "aosp-rust-keymint-nonsecure"
        || legacy.keymint_source_commit != KEYMINT_PIN
        || legacy.interfaces_source_commit != INTERFACES_PIN
    {
        return Err("legacy_nonsecure_provenance_missing");
    }
    check(&legacy.default_service_executable)?;
    check(&legacy.custody_receipt)?;
    let replacement: Replacement = decode(&envelope.replacement_observation)?;
    if replacement.schema != 1
        || replacement.service != "android.hardware.security.keymint.IKeyMintDevice/default"
        || replacement.observation_method != "binder-getHardwareInfo"
        || replacement.security_level != 0
        || replacement.implementation_name != PROVIDER
        || !digest_valid(&replacement.source_commit, 40)
    {
        return Err("honest_software_runtime_observation_missing");
    }
    check(&replacement.default_service_executable)?;
    check(&replacement.candidate_vendor_image)?;
    check(&replacement.runtime_receipt)?;
    Ok(json!({
        "status": "external_provenance_artifact_bytes_verified",
        "envelope_sha256": envelope_sha256,
        "snapshot_receipt_sha256": envelope.snapshot_receipt.sha256,
        "legacy_provenance_sha256": envelope.legacy_provenance.sha256,
        "replacement_observation_sha256": envelope.replacement_observation.sha256,
        "source_commit": replacement.source_commit,
        "security_level": 0,
        "implementation_name": PROVIDER,
        "uuid_used_as_identity": false,
        "external_observation_claims_independently_attested_by_tool": false,
        "per_key_blob_authentication_verified_by_tool": false,
        "clone_experiment_only": true
    }))
}
