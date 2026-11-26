//! Live installed identity from source-admitted normal material batches.
//! A caller-provided hash, signer or passed report cannot construct authority.
//! New batches enter the compiled admission table through normal source review.
use super::*;
use serde_json::{Value, json};

const ADMISSIONS: &str = include_str!("runtime_identity_admissions.json");

// Keep the original descriptors throughout the live observations. Equal bytes at
// a replacement inode are not a substitute for the admitted input generation.
struct HeldDocument {
    pin: FilePin,
    file: std::fs::File,
    identity: [i128; 9],
}
fn identity(metadata: &std::fs::Metadata) -> [i128; 9] {
    use std::os::unix::fs::MetadataExt;
    [
        i128::from(metadata.dev()),
        i128::from(metadata.ino()),
        i128::from(metadata.mode()),
        i128::from(metadata.uid()),
        i128::from(metadata.gid()),
        i128::from(metadata.nlink()),
        i128::from(metadata.len()),
        i128::from(metadata.mtime()) * 1_000_000_000 + i128::from(metadata.mtime_nsec()),
        i128::from(metadata.ctime()) * 1_000_000_000 + i128::from(metadata.ctime_nsec()),
    ]
}
impl HeldDocument {
    fn open(pin: &FilePin) -> Result<(Self, Vec<u8>), String> {
        if !pin.path.is_absolute()
            || pin.path.canonicalize().map_err(|e| e.to_string())? != pin.path
            || pin.bytes == 0
            || pin.bytes > INPUT_LIMIT
            || !crate::release::valid_sha(&pin.sha256)
        {
            return Err("identity material is not a bounded canonical file pin".into());
        }
        let named = std::fs::symlink_metadata(&pin.path).map_err(|e| e.to_string())?;
        if !named.is_file() || named.len() != pin.bytes {
            return Err(
                "identity material is not a complete regular file of the pinned length".into(),
            );
        }
        let file = std::fs::File::open(&pin.path).map_err(|e| e.to_string())?;
        let value = Self {
            pin: pin.clone(),
            file,
            identity: identity(&named),
        };
        let raw = value.read()?;
        Ok((value, raw))
    }
    fn read(&self) -> Result<Vec<u8>, String> {
        use std::os::unix::fs::FileExt;
        let check = || -> Result<(), String> {
            if identity(&self.file.metadata().map_err(|e| e.to_string())?) != self.identity
                || identity(&std::fs::symlink_metadata(&self.pin.path).map_err(|e| e.to_string())?)
                    != self.identity
                || self.pin.path.canonicalize().map_err(|e| e.to_string())? != self.pin.path
            {
                return Err("held material generation, metadata or named file changed".into());
            }
            Ok(())
        };
        check()?;
        let mut bytes = vec![0; usize::try_from(self.pin.bytes).map_err(|e| e.to_string())?];
        self.file
            .read_exact_at(&mut bytes, 0)
            .map_err(|e| e.to_string())?;
        check()?;
        BytesPin::of(&self.pin).check(&bytes)?;
        Ok(bytes)
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
struct BytesPin {
    bytes: u64,
    sha256: String,
}
impl BytesPin {
    fn of(pin: &FilePin) -> Self {
        Self {
            bytes: pin.bytes,
            sha256: pin.sha256.clone(),
        }
    }
    fn matches(&self, pin: &FilePin) -> bool {
        self.bytes == pin.bytes && self.sha256 == pin.sha256
    }
    fn check(&self, raw: &[u8]) -> Result<(), String> {
        if self.bytes == 0
            || self.bytes > INPUT_LIMIT
            || !crate::release::valid_sha(&self.sha256)
            || raw.len() as u64 != self.bytes
            || hex::encode(Sha256::digest(raw)) != self.sha256
        {
            return Err("material bytes differ from the source-owned admission commitment".into());
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Admission {
    id: String,
    selection: BytesPin,
    signature_receipt: BytesPin,
    normal_import: BytesPin,
    normal_input_verification: BytesPin,
    package_count: usize,
    apk_file_count: usize,
    apk_total_bytes: u64,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Admissions {
    schema: String,
    batches: Vec<Admission>,
}
fn admissions() -> Result<Vec<Admission>, String> {
    let values: Admissions = serde_json::from_str(ADMISSIONS).map_err(|e| e.to_string())?;
    if values.schema != "droidloom.application-material-admissions.v1" {
        return Err("source-owned material admission schema differs".into());
    }
    let mut ids = BTreeSet::new();
    let mut selections = BTreeSet::new();
    for value in &values.batches {
        if value.id.is_empty()
            || !ids.insert(&value.id)
            || !selections.insert((&value.selection.sha256, value.selection.bytes))
            || !(1..=1024).contains(&value.package_count)
            || value.apk_file_count < value.package_count
            || value.apk_file_count > value.package_count * 64
            || value.apk_total_bytes == 0
            || [
                &value.selection,
                &value.signature_receipt,
                &value.normal_import,
                &value.normal_input_verification,
            ]
            .into_iter()
            .any(|pin| {
                pin.bytes == 0 || pin.bytes > INPUT_LIMIT || !crate::release::valid_sha(&pin.sha256)
            })
        {
            return Err("source-owned material admission is malformed or ambiguous".into());
        }
    }
    Ok(values.batches)
}

// Ignore only non-authoritative source annotations. All identity relationships
// below are also bound to complete, source-approved document hashes.
#[derive(Deserialize)]
struct Selection {
    schema: String,
    package_count: usize,
    apk_file_count: usize,
    apk_total_bytes: u64,
    this_is_an_executable_runtime_plan: bool,
    all_current_apk_hashes_match_verified_signature_receipt: bool,
    applications: Vec<SelectedApplication>,
}
#[derive(Deserialize)]
struct SelectedApplication {
    package: String,
    role: String,
    version_code: u64,
    version_name: String,
    signature_verification_source: FilePin,
    signer_certificates_sha256: Vec<String>,
    material_files: Vec<SelectedApk>,
}
#[derive(Deserialize)]
struct SelectedApk {
    path: PathBuf,
    bytes: u64,
    sha256: String,
    expected_normalized_pm_name: Option<String>,
    manifest_split_name: Option<String>,
    sdk37_signature_valid: bool,
    verified_signer_certificates_sha256: Vec<String>,
    metadata: ApkMetadata,
}
#[derive(Deserialize, Eq, PartialEq)]
struct ApkMetadata {
    name: String,
    #[serde(rename = "versionCode")]
    version_code: String,
    #[serde(rename = "versionName")]
    version_name: String,
    #[serde(default)]
    split: Option<String>,
}
#[derive(Deserialize)]
struct SignatureReceipt {
    schema: String,
    package_count: usize,
    file_count: usize,
    all_selected_materials_verified: bool,
    rows: Vec<SignedApplication>,
}
#[derive(Deserialize)]
struct SignedApplication {
    package: String,
    role: String,
    version_code: u64,
    version_name: String,
    signer_certificates_sha256: Vec<String>,
    all_file_signatures_and_hashes_verified: bool,
    files: Vec<SignedApk>,
}
#[derive(Deserialize)]
struct SignedApk {
    path: PathBuf,
    bytes: u64,
    sha256: String,
    sdk37_signature_valid: bool,
    verified_signer_certificates_sha256: Vec<String>,
    metadata: ApkMetadata,
}
fn signer_set(values: &[String]) -> Result<BTreeSet<String>, String> {
    let set: BTreeSet<_> = values.iter().cloned().collect();
    if set.is_empty()
        || set.len() > 16
        || set.len() != values.len()
        || set.iter().any(|s| !crate::release::valid_sha(s))
    {
        return Err("normal material signer set is empty, malformed or duplicated".into());
    }
    Ok(set)
}
struct VerifiedApk {
    bytes: u64,
    sha256: String,
    is_base: bool,
    manifest_split: Option<String>,
}
struct VerifiedApplication {
    version_code: u64,
    version_name: String,
    signers: BTreeSet<String>,
    apks: Vec<VerifiedApk>,
}

/// Only the source-table admission path constructs this value in production.
/// It has no Deserialize, Clone or public unchecked constructor.
pub(super) struct VerifiedMaterialBatch {
    admission: Admission,
    selection: FilePin,
    signature_receipt: FilePin,
    applications: BTreeMap<String, VerifiedApplication>,
    held_selection: HeldDocument,
    held_signature: HeldDocument,
}
fn parse_materials(
    admission: &Admission,
    selection: &[u8],
    signature: &[u8],
) -> Result<BTreeMap<String, VerifiedApplication>, String> {
    admission.selection.check(selection)?;
    admission.signature_receipt.check(signature)?;
    let selected: Selection = serde_json::from_slice(selection).map_err(|e| e.to_string())?;
    let signed: SignatureReceipt = serde_json::from_slice(signature).map_err(|e| e.to_string())?;
    if selected.schema != "p4-selected39-static-launch-inputs-v1"
        || selected.this_is_an_executable_runtime_plan
        || !selected.all_current_apk_hashes_match_verified_signature_receipt
        || signed.schema != "p4-selected39-materials-and-original-signers-handoff-v1"
        || !signed.all_selected_materials_verified
        || selected.package_count != admission.package_count
        || signed.package_count != admission.package_count
        || selected.applications.len() != admission.package_count
        || signed.rows.len() != admission.package_count
        || selected.apk_file_count != admission.apk_file_count
        || signed.file_count != admission.apk_file_count
        || selected.apk_total_bytes != admission.apk_total_bytes
    {
        return Err("normal material schemas or complete source-owned counts differ".into());
    }
    let signed_rows: BTreeMap<_, _> = signed
        .rows
        .iter()
        .map(|row| (row.package.as_str(), row))
        .collect();
    if signed_rows.len() != signed.rows.len() {
        return Err("signature receipt repeats a package".into());
    }
    let mut result = BTreeMap::new();
    let mut total_bytes = 0u64;
    let mut total_files = 0usize;
    for row in selected.applications {
        if !crate::valid_package(&row.package)
            || row.version_code == 0
            || row.version_name.is_empty()
            || row.version_name.len() > 256
            || !matches!(row.role.as_str(), "system" | "third_party")
            || !admission
                .signature_receipt
                .matches(&row.signature_verification_source)
            || row.material_files.is_empty()
            || row.material_files.len() > 64
        {
            return Err("selected application lacks an exact normal identity".into());
        }
        let signer = signed_rows
            .get(row.package.as_str())
            .ok_or("normal signature receipt is missing a selected package")?;
        let signers = signer_set(&row.signer_certificates_sha256)?;
        if signer.version_code != row.version_code
            || signer.version_name != row.version_name
            || signer.role != row.role
            || !signer.all_file_signatures_and_hashes_verified
            || signer_set(&signer.signer_certificates_sha256)? != signers
            || signer.files.len() != row.material_files.len()
        {
            return Err("normal signature row differs from the complete selected identity".into());
        }
        let signed_files: BTreeMap<_, _> = signer
            .files
            .iter()
            .map(|apk| ((apk.bytes, apk.sha256.as_str()), apk))
            .collect();
        if signed_files.len() != signer.files.len() {
            return Err("normal signature receipt duplicates APK bytes".into());
        }
        let mut identities = BTreeSet::new();
        let mut splits = BTreeSet::new();
        let mut bases = 0;
        let mut apks = Vec::new();
        for apk in row.material_files {
            let is_base = apk.expected_normalized_pm_name.as_deref() == Some("base.apk");
            if apk.bytes < 4
                || apk.bytes > 1024 * 1024 * 1024
                || !crate::release::valid_sha(&apk.sha256)
                || !identities.insert((apk.bytes, apk.sha256.clone()))
                || !splits.insert(apk.manifest_split_name.clone())
                || !apk.path.is_absolute()
                || !apk.sdk37_signature_valid
                || signer_set(&apk.verified_signer_certificates_sha256)? != signers
                || apk
                    .expected_normalized_pm_name
                    .as_deref()
                    .is_some_and(|n| n != "base.apk")
                || is_base != apk.manifest_split_name.is_none()
                || apk.metadata.name != row.package
                || apk.metadata.version_code.parse::<u64>().ok() != Some(row.version_code)
                || apk.metadata.split != apk.manifest_split_name
                || (is_base && apk.metadata.version_name != row.version_name)
            {
                return Err(
                    "normal APK identity, manifest base/split or signer binding differs".into(),
                );
            }
            let counterpart = signed_files
                .get(&(apk.bytes, apk.sha256.as_str()))
                .ok_or("selected APK is absent from the normal signed set")?;
            if counterpart.path != apk.path
                || !counterpart.sdk37_signature_valid
                || signer_set(&counterpart.verified_signer_certificates_sha256)? != signers
                || counterpart.metadata != apk.metadata
            {
                return Err("selected APK has no identical normal SDK signature record".into());
            }
            total_bytes = total_bytes
                .checked_add(apk.bytes)
                .ok_or("APK total overflow")?;
            total_files += 1;
            bases += usize::from(is_base);
            apks.push(VerifiedApk {
                bytes: apk.bytes,
                sha256: apk.sha256,
                is_base,
                manifest_split: apk.manifest_split_name,
            });
        }
        if bases != 1
            || result
                .insert(
                    row.package,
                    VerifiedApplication {
                        version_code: row.version_code,
                        version_name: row.version_name,
                        signers,
                        apks,
                    },
                )
                .is_some()
        {
            return Err("normal selection repeats a package or lacks exactly one base".into());
        }
    }
    if total_bytes != admission.apk_total_bytes || total_files != admission.apk_file_count {
        return Err("normal selection full APK byte/file totals differ".into());
    }
    Ok(result)
}

/// An unrecognized batch remains unqualified. Caller hashes cannot extend the
/// compiled source table, including when their documents claim passed=true.
pub(super) fn admit_plan(plan: &RuntimePlan) -> Result<Option<VerifiedMaterialBatch>, String> {
    let Some(selection) = &plan.source_selection else {
        return Ok(None);
    };
    let Some(admission) = admissions()?
        .into_iter()
        .find(|value| value.selection.matches(selection))
    else {
        return Ok(None);
    };
    let signature = plan
        .applications
        .iter()
        .filter_map(|app| app.expected_input.as_ref())
        .map(|input| &input.source_receipt)
        .next()
        .ok_or("admitted identity factory requires a normal signature receipt input")?;
    if !admission.signature_receipt.matches(signature)
        || plan
            .applications
            .iter()
            .filter_map(|app| app.expected_input.as_ref())
            .any(|input| !admission.signature_receipt.matches(&input.source_receipt))
    {
        return Err("runtime plan replaced the admitted normal signature receipt".into());
    }
    let (held_selection, selected_bytes) = HeldDocument::open(selection)?;
    let (held_signature, signature_bytes) = HeldDocument::open(signature)?;
    let applications = parse_materials(&admission, &selected_bytes, &signature_bytes)?;
    let requested: BTreeSet<_> = plan
        .applications
        .iter()
        .map(|app| app.package.as_str())
        .collect();
    if requested.len() != plan.applications.len()
        || requested != applications.keys().map(String::as_str).collect()
    {
        return Err("identity factory requires the complete admitted package roster".into());
    }
    Ok(Some(VerifiedMaterialBatch {
        admission,
        selection: selection.clone(),
        signature_receipt: signature.clone(),
        applications,
        held_selection,
        held_signature,
    }))
}

#[derive(Debug, Serialize)]
pub(super) struct IdentityApk {
    name: String,
    path: String,
    bytes: u64,
    sha256: String,
    manifest_split: Option<String>,
    signer_certificates_sha256: Vec<String>,
}
/// Output only. No Deserialize path can turn this report into acceptance.
#[derive(Debug, Serialize)]
pub(super) struct IdentityObservation {
    schema: &'static str,
    admission_id: String,
    selection: FilePin,
    signature_receipt: FilePin,
    normal_input_verification_commitment: BytesPin,
    package: String,
    android_user: u32,
    uid: u32,
    version_code: u64,
    version_name_from_verified_apk: String,
    epoch_before: RuntimeEpoch,
    epoch_after: RuntimeEpoch,
    apks: Vec<IdentityApk>,
    verified_facets: [&'static str; 8],
    unsupported_identity_facets: [&'static str; 2],
    apk_signatures_reexecuted: bool,
    normal_input_verifier_reexecuted: bool,
    latest_version_qualified: bool,
    original_data_migration_accepted: bool,
    complete_identity_gate_passed: bool,
    application_accepted: bool,
    production_ready: bool,
}
impl VerifiedMaterialBatch {
    pub(super) fn revalidate(&self) -> Result<(), String> {
        self.admission
            .selection
            .check(&self.held_selection.read()?)?;
        self.admission
            .signature_receipt
            .check(&self.held_signature.read()?)
    }
    pub(super) fn observe(
        &self,
        requested: &ApplicationPlan,
        user: u32,
        expected_epoch: &RuntimeEpoch,
        before: &ApplicationInspection,
        after: &ApplicationInspection,
    ) -> Result<IdentityObservation, String> {
        if before != after
            || before.epoch != *expected_epoch
            || before.package != requested.package
            || before.user != user
            || before.uid == 0
            || before.uid / 100_000 != user
        {
            return Err(
                "live identity, UID/user or owned Main epoch changed between observations".into(),
            );
        }
        let source = self
            .applications
            .get(&requested.package)
            .ok_or("live application is absent from the admitted batch")?;
        let expected = requested
            .expected_input
            .as_ref()
            .ok_or("identity factory has no installed-source binding for this application")?;
        if before.version_code != source.version_code
            || !source_matches(before, expected)
            || !self
                .admission
                .signature_receipt
                .matches(&expected.source_receipt)
            || before.apks.len() != source.apks.len()
        {
            return Err(
                "live version or full APK set differs from admitted normal material".into(),
            );
        }
        let source_apks: BTreeMap<_, _> = source
            .apks
            .iter()
            .map(|apk| ((apk.bytes, apk.sha256.as_str()), apk))
            .collect();
        let mut names = BTreeSet::new();
        let mut bodies = BTreeSet::new();
        let mut apks = Vec::new();
        for apk in &before.apks {
            if apk.name.is_empty()
                || apk.name.len() > 255
                || !apk.name.ends_with(".apk")
                || apk.name.contains(['/', '\\'])
                || !names.insert(apk.name.as_str())
                || !bodies.insert((apk.bytes, apk.sha256.as_str()))
                || !Path::new(&apk.path).is_absolute()
            {
                return Err("live APK identities contain a duplicate or malformed member".into());
            }
            let material = source_apks
                .get(&(apk.bytes, apk.sha256.as_str()))
                .ok_or("live APK bytes have no admitted signature evidence")?;
            if (apk.name == "base.apk") != material.is_base {
                return Err("live base APK differs from the admitted manifest base".into());
            }
            apks.push(IdentityApk {
                name: apk.name.clone(),
                path: apk.path.clone(),
                bytes: apk.bytes,
                sha256: apk.sha256.clone(),
                manifest_split: material.manifest_split.clone(),
                signer_certificates_sha256: source.signers.iter().cloned().collect(),
            });
        }
        if !names.contains("base.apk") || bodies.len() != source_apks.len() {
            return Err("live inspection omits an admitted APK split".into());
        }
        apks.sort_by(|left, right| left.name.cmp(&right.name));
        Ok(IdentityObservation {
            schema: "droidloom.application-live-material-identity.v1",
            admission_id: self.admission.id.clone(),
            selection: self.selection.clone(),
            signature_receipt: self.signature_receipt.clone(),
            normal_input_verification_commitment: self.admission.normal_input_verification.clone(),
            package: before.package.clone(),
            android_user: before.user,
            uid: before.uid,
            version_code: before.version_code,
            version_name_from_verified_apk: source.version_name.clone(),
            epoch_before: before.epoch.clone(),
            epoch_after: after.epoch.clone(),
            apks,
            verified_facets: [
                "package",
                "android_user",
                "stable_uid",
                "version_code",
                "version_name_from_identical_verified_base_apk",
                "complete_base_and_split_bytes",
                "signers_from_identical_sdk_verified_apks",
                "unchanged_live_main_epoch",
            ],
            unsupported_identity_facets: ["engine_mapping", "main_qualification_semantics"],
            apk_signatures_reexecuted: false,
            normal_input_verifier_reexecuted: false,
            latest_version_qualified: false,
            original_data_migration_accepted: false,
            complete_identity_gate_passed: false,
            application_accepted: false,
            production_ready: false,
        })
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AdmissionCandidateInput {
    schema: String,
    id: String,
    selection: FilePin,
    signature_receipt: FilePin,
    normal_import: FilePin,
    normal_input_verification: FilePin,
}
/// Prepare a review candidate for the next normal batch, never runtime authority.
/// The normal SDK producer and its retained signature evidence still need review.
pub(super) fn prepare_admission_files(path: &Path, sha256: &str) -> Result<Value, String> {
    let raw = crate::release::read_frozen(path, INPUT_LIMIT).map_err(|e| e.to_string())?;
    if !crate::release::valid_sha(sha256) || hex::encode(Sha256::digest(&raw)) != sha256 {
        return Err("material admission candidate input SHA-256 differs".into());
    }
    let input: AdmissionCandidateInput = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    if input.schema != "droidloom.application-material-admission-candidate-input.v1"
        || input.id.is_empty()
        || input.id.len() > 128
        || !input
            .id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"-_.".contains(&c))
    {
        return Err("material admission candidate schema or identifier differs".into());
    }
    let selection_raw = pinned(&input.selection)?;
    let signature_raw = pinned(&input.signature_receipt)?;
    let import_raw = pinned(&input.normal_import)?;
    let verification_raw = pinned(&input.normal_input_verification)?;
    let selection: Selection = serde_json::from_slice(&selection_raw).map_err(|e| e.to_string())?;
    let original: Value = serde_json::from_slice(&import_raw).map_err(|e| e.to_string())?;
    let verification: Value =
        serde_json::from_slice(&verification_raw).map_err(|e| e.to_string())?;
    let read_pin = |value: &Value| {
        serde_json::from_value::<FilePin>(value.clone())
            .map_err(|e| format!("normal admission reference: {e}"))
    };
    if original["schema"] != "droidloom.public-apk-import.v1"
        || !BytesPin::of(&input.selection).matches(&read_pin(&original["selection"])?)
        || !BytesPin::of(&input.signature_receipt).matches(&read_pin(&original["source_receipt"])?)
        || verification["schema"] != "droidloom.public-apk-inputs-verified.v1"
        || verification["scope"] != "source_materials_only"
        || !BytesPin::of(&input.normal_import).matches(&read_pin(&verification["import"])?)
        || verification["package_count"].as_u64() != Some(selection.package_count as u64)
        || verification["apk_file_count"].as_u64() != Some(selection.apk_file_count as u64)
        || verification["applications_installed"] != 0
        || verification["application_business_accepted"] != false
        || verification["production_ready"] != false
    {
        return Err("normal material import and verifier provenance do not form one batch".into());
    }
    let candidate = Admission {
        id: input.id,
        selection: BytesPin::of(&input.selection),
        signature_receipt: BytesPin::of(&input.signature_receipt),
        normal_import: BytesPin::of(&input.normal_import),
        normal_input_verification: BytesPin::of(&input.normal_input_verification),
        package_count: selection.package_count,
        apk_file_count: selection.apk_file_count,
        apk_total_bytes: selection.apk_total_bytes,
    };
    parse_materials(&candidate, &selection_raw, &signature_raw)?;
    for pin in [
        &input.selection,
        &input.signature_receipt,
        &input.normal_import,
        &input.normal_input_verification,
    ] {
        pinned(pin)?;
    }
    if crate::release::read_frozen(path, INPUT_LIMIT).map_err(|e| e.to_string())? != raw {
        return Err("material admission candidate inputs changed during verification".into());
    }
    Ok(json!({
        "schema":"droidloom.application-material-admission-candidate.v1",
        "input":{"path":path,"bytes":raw.len(),"sha256":sha256},
        "source_review_candidate":candidate,
        "sdk_signature_producer_review_required":true,
        "normal_source_release_required":true,
        "source_admission_table_modified":false,
        "runtime_authority_created":false,
        "application_accepted":false,
        "production_ready":false
    }))
}
#[cfg(test)]
#[path = "runtime_identity_tests.rs"]
mod tests;
