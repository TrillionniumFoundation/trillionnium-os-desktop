//! Original public APK material for one fresh normal qualification guest.
//! No Android command, signature change, account import or runtime acceptance.
use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
use rustix::{
    fs::{FileType, Mode},
    process::{Gid, Uid},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Read,
    path::Path,
};

pub const ROOT: &str = "/var/lib/droidloom-public-apks";
pub const STAGE: &str = "/var/lib/droidloom-public-apks/u1000";
const PACKAGES: usize = 39;
const SELECTED_PACKAGES: [&str; PACKAGES] = [
    "com.Hyatt.hyt",
    "com.MobileTicket",
    "com.amazon.mShop.android.shopping",
    "com.android.calendar",
    "com.android.camera2",
    "com.android.contacts",
    "com.android.deskclock",
    "com.android.dialer",
    "com.android.documentsui",
    "com.android.gallery3d",
    "com.android.messaging",
    "com.android.quicksearchbox",
    "com.android.settings",
    "com.bestbuy.android",
    "com.ehi.national.mobile",
    "com.google.android.gms",
    "com.hertz.android.digital",
    "com.hilton.android.hhonors",
    "com.ihg.apps.android",
    "com.jingdong.app.mall",
    "com.lianjia.beike",
    "com.marriott.mrt",
    "com.rytong.airchina",
    "com.rytong.ceair",
    "com.sankuai.meituan.takeoutnew",
    "com.sdu.didi.psnger",
    "com.ss.android.ugc.aweme",
    "com.szzc",
    "com.taobao.taobao",
    "com.tencent.mm",
    "com.united.mobile.android",
    "com.xunmeng.pinduoduo",
    "com.zhubajie.client",
    "com.zillow.android.streeteasy",
    "ctrip.android.view",
    "jp.co.ana.android.tabidachi",
    "org.fcitx.fcitx5.android",
    "org.mozilla.firefox",
    "tv.danmaku.bili",
];
const MAX_APKS: usize = 41 * 32;
const MAX_APP_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const REGISTRY_NAME: &str = "app-release-gates.json";
const REGISTRY_BYTES: u64 = 27_878;
const REGISTRY_SHA256: &str = "0b21f963898308b082f3808dd48165c1397badd1fa8a753c3a766e135b3cb3c8";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Cohort {
    Original39,
    Current41,
}
impl Cohort {
    fn count(self) -> usize {
        match self {
            Self::Original39 => 39,
            Self::Current41 => 41,
        }
    }
    fn from_count(count: usize) -> Result<Self> {
        match count {
            39 => Ok(Self::Original39),
            41 => Ok(Self::Current41),
            _ => Err("public cohort is neither the original39 nor current41 source".into()),
        }
    }
    fn from_packages<'a>(values: impl IntoIterator<Item = &'a str>) -> Result<Self> {
        let actual = values.into_iter().collect::<BTreeSet<_>>();
        let old = BTreeSet::from(SELECTED_PACKAGES);
        if actual == old {
            return Ok(Self::Original39);
        }
        let mut current = old;
        current.extend(["com.ss.android.lark", "com.ss.android.article.news"]);
        ensure(
            actual == current,
            "public package identities differ from both complete admitted cohorts",
        )?;
        Ok(Self::Current41)
    }
    fn registry(self) -> (u64, &'static str) {
        match self {
            Self::Original39 => (REGISTRY_BYTES, REGISTRY_SHA256),
            Self::Current41 => (
                32_688,
                "f99217aa675c23b8cb671e36af7b3c1d8aa068eeba719a4b985f47d1539c5bb5",
            ),
        }
    }
    fn execution(self) -> String {
        format!("p4-selected{}-execution-v3", self.count())
    }
    fn selection(self) -> String {
        format!("p4-selected{}-static-launch-inputs-v1", self.count())
    }
    fn signatures(self) -> String {
        format!(
            "p4-selected{}-materials-and-original-signers-handoff-v1",
            self.count()
        )
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ImportPlan {
    schema: String,
    execution: FilePin,
    selection: FilePin,
    source_receipt: FilePin,
    /// Optional original complete contract; never an alternative weaker gate set.
    #[serde(default)]
    gate_registry: Option<FilePin>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Material {
    pub source: FilePin,
    pub source_identity_before: Option<crate::model::Identity>,
    pub source_identity_after: Option<crate::model::Identity>,
    pub destination_identity: Option<crate::model::Identity>,
    pub guest_path: String,
    pub package: Option<String>,
    pub split: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct GateProfile {
    checks: BTreeMap<String, String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct PackageProfile {
    app: String,
    kind: String,
    profile: String,
    prerequisites: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct GateRegistry {
    schema: String,
    common_gates: BTreeMap<String, String>,
    profiles: BTreeMap<String, GateProfile>,
    packages: BTreeMap<String, PackageProfile>,
}

/// Only static source inputs. Main, expected_epoch and a preparation intent must
/// be produced later from the actual owned Android run; none is synthesized.
#[derive(Debug, Serialize)]
pub struct PreparationInputs {
    pub selection: FilePin,
    pub source_receipt: FilePin,
    pub gate_registry: FilePin,
    pub required_gates: BTreeMap<String, Vec<String>>,
}

#[derive(Debug, Serialize)]
pub struct Staged {
    pub schema: &'static str,
    pub import: FilePin,
    pub files: Vec<Material>,
    pub applications: Vec<Value>,
    pub package_count: usize,
    pub apk_file_count: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub runtime_preparation_inputs: Option<PreparationInputs>,
    pub original_userdata_imported: bool,
    pub applications_installed: usize,
    pub application_business_accepted: bool,
    pub guest_qualified: bool,
    pub production_ready: bool,
}

fn array<'a>(v: &'a Value, name: &str) -> Result<&'a Vec<Value>> {
    v[name]
        .as_array()
        .ok_or_else(|| format!("public APK array missing: {name}").into())
}
fn string<'a>(v: &'a Value, name: &str) -> Result<&'a str> {
    v[name]
        .as_str()
        .ok_or_else(|| format!("public APK string missing: {name}").into())
}
fn number(v: &Value, name: &str) -> Result<u64> {
    v[name]
        .as_u64()
        .ok_or_else(|| format!("public APK number missing: {name}").into())
}
fn pin(v: &Value) -> Result<FilePin> {
    let p = FilePin {
        path: string(v, "path")?.into(),
        bytes: number(v, "bytes")?,
        sha256: string(v, "sha256")?.into(),
    };
    fs::absolute_string(&p.path)?;
    ensure(
        p.bytes > 0 && fs::valid_digest(&p.sha256),
        "invalid public material pin",
    )?;
    Ok(p)
}
fn same_bytes(a: &FilePin, b: &FilePin) -> bool {
    a.bytes == b.bytes && a.sha256 == b.sha256
}
fn names(v: &Value, key: &str) -> Result<BTreeSet<String>> {
    let mut found = BTreeSet::new();
    for item in array(v, key)? {
        let name = item.as_str().ok_or("non-string signer identity")?;
        ensure(
            fs::valid_digest(name) && found.insert(name.into()),
            "invalid or repeated signer",
        )?;
    }
    ensure(!found.is_empty(), "empty signer set")?;
    Ok(found)
}
fn packages<'a>(v: &'a Value, field: &str) -> Result<BTreeMap<&'a str, &'a Value>> {
    let mut result = BTreeMap::new();
    for row in array(v, field)? {
        let package = string(row, "package")?;
        ensure(
            !package.is_empty()
                && package.len() <= 255
                && package.contains('.')
                && package
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"._".contains(&c))
                && result.insert(package, row).is_none(),
            "invalid or repeated selected package",
        )?;
    }
    Cohort::from_packages(result.keys().copied())?;
    Ok(result)
}
fn exclusions(v: &Value) -> Result<BTreeSet<&str>> {
    let mut result = BTreeSet::new();
    for row in array(v, "excluded_packages")? {
        ensure(
            row["status"] == "exempt_unverified" && result.insert(string(row, "package")?),
            "invalid or repeated exemption",
        )?;
    }
    ensure(
        result
            == BTreeSet::from([
                "com.enflick.android.TextNow",
                "com.pinger.textfree",
                "com.ubercab",
            ]),
        "selected public APK exemptions differ",
    )?;
    Ok(result)
}
fn split(v: &Value) -> Result<Option<String>> {
    if v.is_null() {
        Ok(None)
    } else {
        let name = v.as_str().ok_or("non-string split name")?;
        ensure(
            !name.is_empty()
                && name.len() <= 255
                && name
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"._".contains(&c)),
            "invalid split name",
        )?;
        Ok(Some(name.into()))
    }
}

fn validate(
    plan: &ImportPlan,
    execution: &Value,
    selection: &Value,
    receipt: &Value,
) -> Result<(Vec<Material>, Vec<Value>)> {
    let cohort = Cohort::from_count(usize::try_from(number(selection, "package_count")?)?)?;
    let apk_file_count = usize::try_from(number(execution, "file_count")?)?;
    ensure(
        (cohort.count()..=cohort.count() * 32).contains(&apk_file_count),
        "public APK count exceeds its exact complete selected cohort bounds",
    )?;
    ensure(
        plan.schema == "droidloom.public-apk-import.v1"
            && execution["schema"] == cohort.execution()
            && execution["scope"] == "fresh_isolated_vm_only"
            && execution["guest_stage"] == STAGE
            && selection["schema"] == cohort.selection()
            && execution["package_count"] == cohort.count()
            && selection["package_count"] == cohort.count()
            && selection["apk_file_count"] == apk_file_count
            && selection["all_current_apk_hashes_match_verified_signature_receipt"] == true,
        "public APK schemas, fixed scope, stage or complete counts differ",
    )?;
    ensure(
        same_bytes(&pin(&execution["source_materials"])?, &plan.source_receipt),
        "execution and admitted SDK signature receipt differ",
    )?;
    ensure(
        exclusions(execution)? == exclusions(selection)?,
        "selected exemptions differ",
    )?;
    ensure(
        receipt["schema"] == cohort.signatures()
            && receipt["all_selected_materials_verified"] == true
            && receipt["package_count"] == cohort.count()
            && receipt["file_count"] == apk_file_count
            && exclusions(receipt)? == exclusions(selection)?,
        "admitted signature receipt is not the complete verified selection",
    )?;
    let current = packages(selection, "applications")?;
    let verified = packages(receipt, "rows")?;
    let execution_rows = packages(execution, "rows")?;
    ensure(
        current.keys().eq(execution_rows.keys()) && current.keys().eq(verified.keys()),
        "selected package roster differs",
    )?;
    let mut files = Vec::new();
    let mut applications = Vec::new();
    let mut all_names = BTreeSet::new();
    let mut all_sources = BTreeSet::new();
    let mut total = 0u64;
    for (package, row) in execution_rows {
        let selected = current[package];
        let signed = verified[package];
        let version = number(row, "version_code")?;
        let role = string(row, "role")?;
        ensure(
            version > 0
                && row["version_code"] == selected["version_code"]
                && row["version_name"] == selected["version_name"]
                && row["role"] == selected["role"]
                && ["system", "third_party"].contains(&role)
                && same_bytes(
                    &pin(&selected["signature_verification_source"])?,
                    &plan.source_receipt,
                ),
            "selected version, role or signature receipt differs",
        )?;
        let signers = names(row, "signers_sha256")?;
        ensure(
            signers == names(selected, "signer_certificates_sha256")?
                && signers == names(signed, "signer_certificates_sha256")?
                && signed["version_code"] == row["version_code"]
                && signed["version_name"] == row["version_name"]
                && signed["role"] == row["role"]
                && signed["all_file_signatures_and_hashes_verified"] == true,
            "selected and SDK receipt package identities differ",
        )?;
        let originals = array(selected, "material_files")?;
        let signed_files = array(signed, "files")?;
        ensure(
            signed_files.len() == originals.len(),
            "SDK receipt split set differs",
        )?;
        let parts = array(row, "files")?;
        ensure(
            !parts.is_empty() && parts.len() <= 32 && parts.len() == originals.len(),
            "complete atomic APK split set is missing or exceeds the normal installer bound",
        )?;
        let mut splits = BTreeSet::new();
        let mut app_bytes = 0u64;
        let mut inputs = Vec::new();
        for part in parts {
            let hash = string(part, "sha256")?;
            let size = number(part, "bytes")?;
            let name = string(part, "name")?;
            let part_split = split(&part["split"])?;
            ensure(
                fs::valid_digest(hash)
                    && name == format!("{hash}.apk")
                    && (4..=MAX_APP_BYTES).contains(&size)
                    && splits.insert(part_split.clone())
                    && all_names.insert(name.to_owned()),
                "public APK name, size, duplicate hash or split differs",
            )?;
            let matching: Vec<_> = originals
                .iter()
                .filter(|f| f["sha256"] == hash && f["bytes"] == size)
                .collect();
            ensure(
                matching.len() == 1,
                "execution APK does not select exactly one original",
            )?;
            let original = matching[0];
            let signed_matches: Vec<_> = signed_files
                .iter()
                .filter(|f| {
                    f["sha256"] == hash && f["bytes"] == size && f["path"] == original["path"]
                })
                .collect();
            ensure(
                signed_matches.len() == 1
                    && signed_matches[0]["sdk37_signature_valid"] == true
                    && names(signed_matches[0], "verified_signer_certificates_sha256")? == signers
                    && signed_matches[0]["metadata"] == original["metadata"]
                    && split(&signed_matches[0]["metadata"]["split"])? == part_split,
                "APK is not the original SDK37-verified receipt member",
            )?;
            let source = pin(original)?;
            let source_name = fs::absolute_string(&source.path)?;
            ensure(
                source.path.starts_with("/home/alex/work")
                    && source.path.extension().is_some_and(|v| v == "apk")
                    && all_sources.insert(source_name)
                    && original["sdk37_signature_valid"] == true
                    && names(original, "verified_signer_certificates_sha256")? == signers
                    && split(&original["manifest_split_name"])? == part_split
                    && original["metadata"]["name"] == package
                    && original["metadata"]["versionCode"]
                        .as_str()
                        .and_then(|v| v.parse::<u64>().ok())
                        == Some(version),
                "original public APK source, SDK37 identity or complete split metadata differs",
            )?;
            let guest_path = format!("{STAGE}/{name}");
            inputs.push((part_split.clone(), guest_path.clone()));
            files.push(Material {
                source,
                source_identity_before: None,
                source_identity_after: None,
                destination_identity: None,
                guest_path,
                package: Some(package.into()),
                split: part_split,
            });
            app_bytes = app_bytes
                .checked_add(size)
                .ok_or("public APK size overflow")?;
        }
        ensure(
            splits.contains(&None) && app_bytes <= MAX_APP_BYTES,
            "one base APK and bounded full split set required",
        )?;
        total = total
            .checked_add(app_bytes)
            .ok_or("public APK total overflow")?;
        inputs.sort(); // Base is first; complete split order is deterministic.
        let mut install = vec![
            "/usr/bin/droidloomctl".to_owned(),
            "--json".into(),
            if inputs.len() == 1 {
                "install".into()
            } else {
                "install-multiple".into()
            },
            "--user".into(),
            "0".into(),
        ];
        install.extend(inputs.into_iter().map(|(_, path)| path));
        applications.push(json!({
            "package":package,"role":role,"version_code":version,"version_name":row["version_name"],
            "signers_sha256":signers,"original_account_install_blocked":row["original_account_install_blocked"],
            "original_signer_precondition":row["original_signer_precondition"],
            "inspect_argv":["/usr/bin/droidloomctl","--json","inspect",package,"--user","0"],
            "install_argv":install,"commands_executed":false,
            "runtime_epoch_binding_required":true,"post_install_full_inspection_required":true,
            "application_business_accepted":false
        }));
    }
    ensure(
        files.len() == apk_file_count
            && total <= 8 * 1024 * 1024 * 1024
            && selection["apk_total_bytes"] == total,
        "complete selected APK count or byte total differs",
    )?;
    Ok((files, applications))
}

fn registry_coverage(
    registry: &GateRegistry,
    applications: &[Value],
) -> Result<BTreeMap<String, Vec<String>>> {
    let selected = applications
        .iter()
        .map(|a| string(a, "package"))
        .collect::<Result<Vec<_>>>()?;
    let cohort = Cohort::from_packages(selected)?;
    let common = BTreeSet::from([
        "identity",
        "lifecycle",
        "stability",
        "data_permissions",
        "release_scope",
        "ui_observation",
    ]);
    ensure(
        registry.schema == "pocket4-app-release-gates-v1"
            && registry.packages.len() == cohort.count() + 7
            && registry
                .common_gates
                .keys()
                .map(String::as_str)
                .collect::<BTreeSet<_>>()
                == common
            && registry.common_gates.values().all(|v| !v.trim().is_empty())
            && !registry.profiles.is_empty(),
        "original complete application gate registry schema or common contracts differ",
    )?;
    for (profile, body) in &registry.profiles {
        ensure(
            !body.checks.is_empty()
                && body.checks.iter().all(|(id, text)| {
                    id.starts_with(&format!("{profile}.")) && !text.trim().is_empty()
                }),
            "application profile has an empty or mismatched business contract",
        )?;
    }
    for profile in registry.packages.values() {
        ensure(
            !profile.app.trim().is_empty()
                && !profile.kind.trim().is_empty()
                && profile.prerequisites.iter().all(|v| !v.trim().is_empty())
                && registry.profiles.contains_key(&profile.profile),
            "application registry profile or prerequisites are incomplete",
        )?;
    }
    let mut required = BTreeMap::new();
    for app in applications {
        let package = string(app, "package")?;
        let profile = registry.packages.get(package).ok_or_else(|| {
            format!("selected application has no original gate contract: {package}")
        })?;
        let gates = registry
            .common_gates
            .keys()
            .chain(registry.profiles[&profile.profile].checks.keys())
            .cloned()
            .collect();
        ensure(
            required.insert(package.to_owned(), gates).is_none(),
            "repeated selected application in registry coverage",
        )?;
    }
    ensure(
        required.len() == cohort.count(),
        "gate registry does not cover the exact complete selected cohort",
    )?;
    Ok(required)
}

fn guest_pin(source: &FilePin, name: &str) -> FilePin {
    FilePin {
        path: format!("{STAGE}/{name}").into(),
        bytes: source.bytes,
        sha256: source.sha256.clone(),
    }
}

fn preparation_inputs(
    plan: &ImportPlan,
    applications: &[Value],
) -> Result<Option<PreparationInputs>> {
    let Some(input) = &plan.gate_registry else {
        return Ok(None);
    };
    let selected = applications
        .iter()
        .map(|a| string(a, "package"))
        .collect::<Result<Vec<_>>>()?;
    let (registry_bytes, registry_sha256) = Cohort::from_packages(selected)?.registry();
    // Keep every original description and prerequisite byte-identical. A
    // structurally valid but reduced registry cannot replace this contract.
    ensure(
        input.bytes == registry_bytes && input.sha256 == registry_sha256,
        "gate registry must be the complete original canonical contract",
    )?;
    let raw = boot_files::read_pin(input, registry_bytes)?;
    let registry: GateRegistry = serde_json::from_slice(&raw)?;
    Ok(Some(PreparationInputs {
        selection: guest_pin(&plan.selection, "selected39-source-selection.json"),
        source_receipt: guest_pin(&plan.source_receipt, "selected39-signature-receipt.json"),
        gate_registry: guest_pin(input, REGISTRY_NAME),
        required_gates: registry_coverage(&registry, applications)?,
    }))
}

pub fn admit(input: &FilePin, fresh_normal: bool) -> Result<(Staged, Vec<(FilePin, String)>)> {
    ensure(
        fresh_normal,
        "public APK import requires a fresh normal guest without original userdata",
    )?;
    read_materials(input)
}

// Static parsing is also useful before a fresh guest exists. Only admit/install
// accepts the fresh-normal authority; this helper never creates a guest or data.
fn read_materials(input: &FilePin) -> Result<(Staged, Vec<(FilePin, String)>)> {
    let plan: ImportPlan = serde_json::from_slice(&boot_files::read_pin(input, 65536)?)?;
    let execution = boot_files::read_pin(&plan.execution, 1024 * 1024)?;
    let selection = boot_files::read_pin(&plan.selection, 2 * 1024 * 1024)?;
    let source_receipt = boot_files::read_pin(&plan.source_receipt, 2 * 1024 * 1024)?;
    let (files, applications) = validate(
        &plan,
        &serde_json::from_slice(&execution)?,
        &serde_json::from_slice(&selection)?,
        &serde_json::from_slice(&source_receipt)?,
    )?;
    let runtime_preparation_inputs = preparation_inputs(&plan, &applications)?;
    let mut provenance = vec![
        (plan.execution, format!("{STAGE}/selected39-execution.json")),
        (
            plan.selection,
            format!("{STAGE}/selected39-source-selection.json"),
        ),
        (
            plan.source_receipt,
            format!("{STAGE}/selected39-signature-receipt.json"),
        ),
    ];
    if let Some(registry) = plan.gate_registry {
        provenance.push((registry, format!("{STAGE}/{REGISTRY_NAME}")));
    }
    let package_count = applications.len();
    Ok((
        Staged {
            schema: "droidloom.public-apks-staged.v1",
            import: input.clone(),
            apk_file_count: files.len(),
            files,
            applications,
            package_count,
            runtime_preparation_inputs,
            original_userdata_imported: false,
            applications_installed: 0,
            application_business_accepted: false,
            guest_qualified: false,
            production_ready: false,
        },
        provenance,
    ))
}

fn check_source(source: &FilePin, apk: bool) -> Result<crate::model::Identity> {
    let (mut file, before) = boot_files::open_pin(source)?;
    ensure(
        before.nlink > 0
            && (before.uid == 0 || before.uid == 1000)
            && before.mode & 0o7022 == 0
            && fs::xattrs(&file)?.is_empty(),
        "public material has a foreign owner, write grant or privilege attribute",
    )?;
    if apk {
        let mut magic = [0; 4];
        file.read_exact(&mut magic)?;
        ensure(
            magic == *b"PK\x03\x04",
            "selected APK lacks its original ZIP header",
        )?;
    }
    ensure(
        fs::stat(&file)? == before,
        "public material changed during admission",
    )?;
    Ok(before)
}

fn hold_verified_source(
    source: &FilePin,
    apk: bool,
) -> Result<(std::fs::File, crate::model::Identity)> {
    let before = check_source(source, apk)?;
    let file = boot_files::checked_file(source)?;
    ensure(
        fs::stat(&file)? == before,
        "public input inode changed during complete hash verification",
    )?;
    Ok((file, before))
}

fn recheck_held_source(
    source: &FilePin,
    apk: bool,
    file: &std::fs::File,
    before: &crate::model::Identity,
) -> Result<()> {
    ensure(
        fs::stat(file)? == *before && check_source(source, apk)? == *before,
        "held public input or its named path changed during the complete check",
    )
}

/// Read-only check of the same pinned material contract consumed by install.
/// It does not infer a guest, Main, epoch, labels, installation or business result.
/// One source-admitted public document under the existing public-material
/// ownership rules. This keeps the actual descriptor across the successor
/// preparation; it does not grant installed-application or runtime authority.
pub(crate) struct VerifiedSourceDocument {
    pin: FilePin,
    file: std::fs::File,
    identity: crate::model::Identity,
}
impl VerifiedSourceDocument {
    pub(crate) fn observe(pin: &FilePin, limit: u64) -> Result<Self> {
        ensure(
            pin.bytes > 0 && pin.bytes <= limit,
            "bounded public source document required",
        )?;
        let (file, identity) = hold_verified_source(pin, false)?;
        let value = Self {
            pin: pin.clone(),
            file,
            identity,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn pin(&self) -> &FilePin {
        &self.pin
    }
    pub(crate) fn identity(&self) -> &crate::model::Identity {
        &self.identity
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        recheck_held_source(&self.pin, false, &self.file, &self.identity)
    }
    pub(crate) fn bytes(&self, limit: u64) -> Result<Vec<u8>> {
        use std::os::unix::fs::FileExt;
        ensure(
            self.pin.bytes <= limit,
            "public document read exceeds its source bound",
        )?;
        self.revalidate()?;
        let mut raw = vec![0; usize::try_from(self.pin.bytes)?];
        self.file.read_exact_at(&mut raw, 0)?;
        ensure(
            fs::digest(&raw) == self.pin.sha256
                && self.file.read_at(&mut [0], self.pin.bytes)? == 0,
            "held public document bytes changed or acquired a tail",
        )?;
        self.revalidate()?;
        Ok(raw)
    }
    pub(crate) fn json(&self, limit: u64) -> Result<Value> {
        Ok(serde_json::from_slice(&self.bytes(limit)?)?)
    }
}

/// Retained result of the real normal input verifier. It is neither a saved
/// report constructor nor an application/runtime authority. The same descriptors
/// remain held for the enclosing cold preparation.
pub(crate) struct VerifiedInputs {
    sources: Vec<(FilePin, bool)>,
    held: Vec<(std::fs::File, crate::model::Identity)>,
    report: Value,
}
impl VerifiedInputs {
    pub(crate) fn apk_sources(&self) -> Result<Vec<VerifiedApkSource<'_>>> {
        self.revalidate()?;
        Ok(self
            .sources
            .iter()
            .zip(&self.held)
            .filter(|((_, apk), _)| *apk)
            .map(|((pin, _), (file, identity))| VerifiedApkSource {
                pin,
                file,
                identity,
            })
            .collect())
    }
    pub(crate) fn report(&self) -> &Value {
        &self.report
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        ensure(
            self.sources.len() == self.held.len(),
            "public input custody roster differs",
        )?;
        for ((source, apk), (file, before)) in self.sources.iter().zip(&self.held) {
            recheck_held_source(source, *apk, file, before)?;
        }
        Ok(())
    }
}

/// Complete position-independent digest of an already-held APK inode. A shared
/// OFD cursor never selects which bytes are attested.
pub(crate) fn held_apk_hash(file: &std::fs::File, bytes: u64) -> Result<String> {
    use sha2::{Digest, Sha256};
    use std::os::unix::fs::FileExt;
    ensure(bytes > 0, "empty APK cannot be a public application")?;
    let before = crate::fs::stat(file)?;
    ensure(before.size == bytes, "held APK size differs before hashing")?;
    let mut digest = Sha256::new();
    let mut offset = 0;
    let mut buffer = vec![0_u8; 1024 * 1024];
    while offset < bytes {
        let count = usize::try_from((bytes - offset).min(buffer.len() as u64))?;
        file.read_exact_at(&mut buffer[..count], offset)?;
        digest.update(&buffer[..count]);
        offset += count as u64;
    }
    ensure(
        file.read_at(&mut [0], bytes)? == 0 && crate::fs::stat(file)? == before,
        "held APK changed or has an unlisted tail during complete hashing",
    )?;
    Ok(hex::encode(digest.finalize()))
}

/// A borrowed APK remains tied to the verifier's actual descriptor. It cannot
/// be reconstructed from a JSON report or a caller-selected pathname.
pub(crate) struct VerifiedApkSource<'a> {
    pin: &'a FilePin,
    file: &'a std::fs::File,
    identity: &'a crate::model::Identity,
}
impl VerifiedApkSource<'_> {
    pub(crate) fn pin(&self) -> &FilePin {
        self.pin
    }
    pub(crate) fn identity(&self) -> &crate::model::Identity {
        self.identity
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        recheck_held_source(self.pin, true, self.file, self.identity)
    }
    /// Copy from the held read-only source, never a reopened pathname. The
    /// caller owns the protected create-only destination and its publication.
    pub(crate) fn copy_to(&self, output: &mut std::fs::File) -> Result<()> {
        use sha2::{Digest, Sha256};
        use std::io::Write;
        use std::os::unix::fs::FileExt;
        self.revalidate()?;
        let target = crate::fs::stat(output)?;
        ensure(
            target.mode == 0o100400
                && target.uid == 0
                && target.gid == 0
                && target.nlink == 1
                && target.size == 0
                && (target.dev, target.ino) != (self.identity.dev, self.identity.ino)
                && crate::fs::xattrs(output)?.is_empty(),
            "APK copy requires a new independent protected root file",
        )?;
        let mut buffer = vec![0_u8; 1024 * 1024];
        let mut position = 0_u64;
        let mut digest = Sha256::new();
        while position < self.pin.bytes {
            ensure(
                crate::fs::stat(self.file)? == *self.identity,
                "held APK source changed before a copy chunk",
            )?;
            let count = usize::try_from((self.pin.bytes - position).min(buffer.len() as u64))?;
            self.file.read_exact_at(&mut buffer[..count], position)?;
            digest.update(&buffer[..count]);
            output.write_all(&buffer[..count])?;
            ensure(
                crate::fs::stat(self.file)? == *self.identity,
                "held APK source changed after a copy chunk",
            )?;
            position += count as u64;
        }
        ensure(
            self.file.read_at(&mut [0], self.pin.bytes)? == 0
                && hex::encode(digest.finalize()) == self.pin.sha256,
            "held APK copy has a different complete hash or unlisted tail",
        )?;
        output.sync_all()?;
        let after = crate::fs::stat(output)?;
        ensure(
            after.mode == target.mode
                && after.uid == target.uid
                && after.gid == target.gid
                && after.dev == target.dev
                && after.ino == target.ino
                && after.nlink == 1
                && after.size == self.pin.bytes
                && crate::fs::xattrs(output)?.is_empty(),
            "new APK copy changed its protected inode",
        )?;
        ensure(
            held_apk_hash(output, self.pin.bytes)? == self.pin.sha256
                && output.read_at(&mut [0], self.pin.bytes)? == 0
                && crate::fs::stat(output)? == after,
            "new APK complete readback differs from its held source",
        )?;
        self.revalidate()
    }
}

pub(crate) fn observe_inputs(config: &Path, expected: &str) -> Result<VerifiedInputs> {
    let input = boot_files::pin_file(config)?;
    ensure(input.sha256 == expected, "public APK import digest differs")?;
    let (staged, provenance) = read_materials(&input)?;
    let mut sources = vec![(input.clone(), false)];
    sources.extend(staged.files.iter().map(|item| (item.source.clone(), true)));
    sources.extend(provenance.into_iter().map(|(source, _)| (source, false)));
    let mut held = Vec::with_capacity(sources.len());
    for (source, apk) in &sources {
        held.push(hold_verified_source(source, *apk)?);
    }
    let mut verified = Vec::with_capacity(sources.len());
    for ((source, apk), (file, before)) in sources.iter().zip(&held) {
        recheck_held_source(source, *apk, file, before)?;
        verified.push(json!({
            "source":source,
            "apk":apk,
            "source_identity_before":before,
            "source_identity_after":fs::stat(file)?,
            "complete_sha256_verified":true
        }));
    }
    let report = json!({
        "schema":"droidloom.public-apk-inputs-verified.v1",
        "scope":"source_materials_only",
        "import":input,
        "package_count":staged.package_count,
        "apk_file_count":staged.apk_file_count,
        "applications":staged.applications,
        "sources":verified,
        "prospective_runtime_preparation_inputs":staged.runtime_preparation_inputs,
        "fresh_normal_guest_required_for_install":true,
        "sdk_signatures_reexecuted":false,
        "labels_checked":false,
        "ext4_readback_checked":false,
        "files_staged":false,
        "original_userdata_imported":false,
        "applications_installed":0,
        "application_business_accepted":false,
        "latest_qualification_evaluated":false,
        "guest_qualified":false,
        "production_ready":false
    });
    Ok(VerifiedInputs {
        sources,
        held,
        report,
    })
}

/// Preserve the original report-only API and its exact normal verification.
pub(crate) fn verify_inputs_report(config: &Path, expected: &str) -> Result<Value> {
    Ok(observe_inputs(config, expected)?.report)
}

pub fn verify_inputs(config: &Path, expected: &str) -> Result<()> {
    println!(
        "{}",
        serde_json::to_string_pretty(&verify_inputs_report(config, expected)?)?
    );
    Ok(())
}

fn list(file: &std::fs::File) -> Result<BTreeSet<String>> {
    let mut result = BTreeSet::new();
    for entry in rustix::fs::Dir::read_from(file)? {
        let entry = entry?;
        let name = entry.file_name().to_str()?.to_owned();
        if name != "." && name != ".." {
            result.insert(name);
        }
    }
    Ok(result)
}

pub fn install(root: &Path, work: &Path, input: &FilePin, fresh_normal: bool) -> Result<Staged> {
    let (mut staged, provenance) = admit(input, fresh_normal)?;
    for (source, guest_path) in provenance {
        staged.files.push(Material {
            source,
            guest_path,
            package: None,
            split: None,
            source_identity_before: None,
            source_identity_after: None,
            destination_identity: None,
        });
    }
    for item in &mut staged.files {
        item.source_identity_before = Some(check_source(&item.source, item.package.is_some())?);
    }
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let public = tree.dir(ROOT)?;
    let id = fs::stat(&public)?;
    ensure(
        id.uid == 0 && id.gid == 0 && id.mode & 0o7777 == 0o755 && list(&public)?.is_empty(),
        "normal public root must be root-owned 0755 and freshly empty",
    )?;
    tree.mkdir(STAGE)?;
    let directory = tree.dir(STAGE)?;
    for item in &mut staged.files {
        ensure(
            Some(check_source(&item.source, item.package.is_some())?)
                == item.source_identity_before,
            "original public input identity changed before copy",
        )?;
        let path = boot_files::guest_path(root, &item.guest_path)?;
        let copied_source = boot_files::copy_pin_with_identity(&item.source, &path, 0o400)?;
        ensure(
            Some(copied_source) == item.source_identity_before,
            "held original APK inode differs from the admitted source identity",
        )?;
        let pin = FilePin {
            path,
            bytes: item.source.bytes,
            sha256: item.source.sha256.clone(),
        };
        let (file, id) = boot_files::open_pin(&pin)?;
        ensure(
            id.nlink == 1 && fs::xattrs(&file)?.is_empty(),
            "copied material gained a link or privilege attribute",
        )?;
        rustix::fs::fchown(&file, Some(Uid::from_raw(1000)), Some(Gid::from_raw(1000)))?;
        rustix::fs::fchmod(&file, Mode::from_raw_mode(0o400))?;
        rustix::fs::fsync(&file)?;
        item.destination_identity = Some(fs::stat(&file)?);
    }
    // The original public collection may legitimately share hardlinks. It is
    // never edited; every F9 (including nlink) must survive the entire copy.
    for item in &mut staged.files {
        let after = check_source(&item.source, item.package.is_some())?;
        ensure(
            Some(after.clone()) == item.source_identity_before,
            "original public input identity changed during the complete copy",
        )?;
        item.source_identity_after = Some(after);
    }
    rustix::fs::fchown(
        &directory,
        Some(Uid::from_raw(1000)),
        Some(Gid::from_raw(1000)),
    )?;
    rustix::fs::fchmod(&directory, Mode::from_raw_mode(0o700))?;
    rustix::fs::fsync(&directory)?;
    verify_tree(root, &staged)?;
    fs::write_json(
        &fs::absolute_string(&work.join("PUBLIC-APKS-STAGED.json"))?,
        &staged,
        0,
    )?;
    Ok(staged)
}

pub fn guest_paths(staged: &Staged) -> Vec<String> {
    std::iter::once(STAGE.to_owned())
        .chain(staged.files.iter().map(|f| f.guest_path.clone()))
        .collect()
}

fn material_package_count(files: &[Material]) -> Result<usize> {
    Ok(Cohort::from_packages(files.iter().filter_map(|m| m.package.as_deref()))?.count())
}

fn provenance_count(files: &[Material]) -> Result<usize> {
    let mut paths = BTreeSet::new();
    let mut provenance = BTreeSet::new();
    let mut packages: BTreeMap<&str, BTreeSet<Option<&str>>> = BTreeMap::new();
    let mut app_bytes: BTreeMap<&str, u64> = BTreeMap::new();
    for item in files {
        let name = item
            .guest_path
            .strip_prefix(&format!("{STAGE}/"))
            .ok_or("public material lies outside the fixed UID directory")?;
        ensure(
            !name.is_empty() && !name.contains('/') && paths.insert(&item.guest_path),
            "public material path is nested, empty or repeated",
        )?;
        if item.package.is_none() {
            ensure(
                item.split.is_none(),
                "public provenance cannot be an APK split",
            )?;
            provenance.insert(name);
        } else {
            let package = item.package.as_deref().unwrap();
            ensure(
                fs::valid_digest(&item.source.sha256)
                    && name == format!("{}.apk", item.source.sha256)
                    && (4..=MAX_APP_BYTES).contains(&item.source.bytes)
                    && packages
                        .entry(package)
                        .or_default()
                        .insert(item.split.as_deref()),
                "public APK destination, byte bound or complete split identity differs",
            )?;
            let count = app_bytes.entry(package).or_default();
            *count = count
                .checked_add(item.source.bytes)
                .ok_or("public APK size overflow")?;
        }
    }
    let cohort = Cohort::from_packages(packages.keys().copied())?;
    ensure(
        packages
            .values()
            .all(|parts| parts.contains(&None) && parts.len() <= 32)
            && app_bytes.values().all(|bytes| *bytes <= MAX_APP_BYTES)
            && app_bytes.values().sum::<u64>() <= 8 * 1024 * 1024 * 1024,
        "public material package roster or bounded complete split set differs",
    )?;
    let apk_file_count: usize = packages.values().map(BTreeSet::len).sum();
    let mut expected = BTreeSet::from([
        "selected39-execution.json",
        "selected39-source-selection.json",
        "selected39-signature-receipt.json",
    ]);
    if provenance.contains(REGISTRY_NAME) {
        expected.insert(REGISTRY_NAME);
    }
    ensure(
        provenance == expected
            && (cohort.count()..=cohort.count() * 32).contains(&apk_file_count)
            && files.len() == apk_file_count + expected.len(),
        "public material set must contain every pinned APK and exactly the declared JSON inputs",
    )?;
    Ok(expected.len())
}

fn verify_tree(root: &Path, staged: &Staged) -> Result<()> {
    let provenance = provenance_count(&staged.files)?;
    ensure(
        (provenance == 4) == staged.runtime_preparation_inputs.is_some()
            && staged.package_count == material_package_count(&staged.files)?
            && staged.apk_file_count == staged.files.len() - provenance,
        "staged runtime preparation inputs differ from the actual registry material",
    )?;
    let stage = boot_files::guest_path(root, STAGE)?;
    let directory = fs::Tree::open(&fs::absolute_string(&stage)?, 1000)?;
    let id = fs::stat(&directory.root)?;
    ensure(
        id.uid == 1000 && id.gid == 1000 && id.mode & 0o7777 == 0o700,
        "public UID boundary changed",
    )?;
    let expected: BTreeSet<_> = staged
        .files
        .iter()
        .map(|f| f.guest_path.rsplit('/').next().unwrap().to_owned())
        .collect();
    ensure(
        expected.len() == staged.apk_file_count + provenance && list(&directory.root)? == expected,
        "public material directory is incomplete or has extra entries",
    )?;
    for item in &staged.files {
        let pin = FilePin {
            path: boot_files::guest_path(root, &item.guest_path)?,
            bytes: item.source.bytes,
            sha256: item.source.sha256.clone(),
        };
        let (file, id) = boot_files::open_pin(&pin)?;
        let copied = item
            .destination_identity
            .as_ref()
            .ok_or("public copy identity absent")?;
        ensure(
            id.dev == copied.dev
                && id.ino == copied.ino
                && id.mtime_sec == copied.mtime_sec
                && id.mtime_nsec == copied.mtime_nsec,
            "public payload inode or content timestamp changed",
        )?;
        ensure(
            FileType::from_raw_mode(id.mode) == FileType::RegularFile
                && id.nlink == 1
                && id.uid == 1000
                && id.gid == 1000
                && id.mode & 0o7777 == 0o400
                && fs::xattrs(&file)?.is_empty(),
            "public payload type, singleton identity, owner or read-only mode differs",
        )?;
    }
    Ok(())
}

pub fn validate_labels(staged: &Staged, labels: &Value) -> Result<()> {
    let rows = array(labels, "labels")?;
    for path in std::iter::once(ROOT.to_owned()).chain(guest_paths(staged)) {
        let expected = if path == ROOT {
            "droidloom_public_apk_root"
        } else if path == STAGE {
            "droidloom_public_apk_dir"
        } else {
            "droidloom_public_apk_input"
        };
        let selected: Vec<_> = rows.iter().filter(|row| row["path"] == path).collect();
        ensure(
            selected.len() == 1,
            "public APK label inventory missing or repeated",
        )?;
        let label = hex::decode(string(selected[0], "label_hex")?)?;
        ensure(
            label == format!("u:object_r:{expected}:s0\0").as_bytes(),
            "public APK input acquired another role label",
        )?;
    }
    Ok(())
}

pub fn verify_image(root: &Path, work: &Path, disk: &Path, staged: &Staged) -> Result<Value> {
    verify_tree(root, staged)?;
    let result = readback_bodies(work, disk, &staged.files)?;
    verify_tree(root, staged)?;
    Ok(result)
}

fn readback_bodies(work: &Path, disk: &Path, files: &[Material]) -> Result<Value> {
    let provenance = provenance_count(files)?;
    let output = work.join("public-apk-readback");
    boot_files::private_dir(&output)?;
    let disk_before = std::fs::symlink_metadata(disk)?;
    let mut rows = Vec::new();
    for (index, item) in files.iter().enumerate() {
        let body = output.join(format!("material-{index:03}"));
        let command = boot_files::run_logged(
            &output,
            &format!("material-{index:03}"),
            "/usr/sbin/debugfs",
            &[
                "-R".into(),
                format!(
                    "dump {} {}",
                    crate::boot_runtime::debugfs_command_path(&item.guest_path)?,
                    crate::boot_runtime::debugfs_command_path(&fs::absolute_string(&body)?)?
                ),
                disk.to_string_lossy().into(),
            ],
            60,
        )?;
        let actual = boot_files::pin_file(&body)?;
        ensure(
            same_bytes(&actual, &item.source),
            "actual ext4 public APK full content differs",
        )?;
        rows.push(json!({"guest_path":item.guest_path,"source":item.source,
            "actual":actual,"command":command,"full_content_matched":true}));
    }
    use std::os::unix::fs::MetadataExt;
    let disk_after = std::fs::symlink_metadata(disk)?;
    ensure(
        disk_before.dev() == disk_after.dev()
            && disk_before.ino() == disk_after.ino()
            && disk_before.len() == disk_after.len()
            && disk_before.mtime_nsec() == disk_after.mtime_nsec()
            && disk_before.mtime() == disk_after.mtime()
            && disk_before.ctime_nsec() == disk_after.ctime_nsec()
            && disk_before.ctime() == disk_after.ctime(),
        "root image changed during public APK readback",
    )?;
    Ok(
        json!({"schema":"droidloom.public-apks-ext4-readback.v1","files":rows,
        "package_count":material_package_count(files)?,"apk_file_count":files.len() - provenance,"provenance_file_count":provenance,
        "gate_registry_imported":provenance == 4,
        "all_original_bytes_matched":true,"readonly_ext4_reader":true,
        "applications_installed":0,"application_business_accepted":false,
        "guest_qualified":false,"production_ready":false}),
    )
}

#[cfg(test)]
#[path = "boot_public_apks_tests.rs"]
mod tests;

#[cfg(test)]
mod held_apk_copy_tests {
    use super::*;
    use std::{
        fs::{File, OpenOptions},
        io::{Seek, SeekFrom, Write},
        os::unix::fs::{FileExt, OpenOptionsExt, PermissionsExt},
    };
    fn source_fixture(directory: &Path) -> Result<(FilePin, File, crate::model::Identity)> {
        let path = directory.join("actual-source.apk");
        let raw = b"PK\x03\x04actual independent package bytes\n";
        std::fs::write(&path, raw)?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o400))?;
        let pin = boot_files::pin_file(&path)?;
        let (held, identity) = hold_verified_source(&pin, true)?;
        Ok((pin, held, identity))
    }
    fn target(directory: &Path) -> Result<File> {
        Ok(OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o400)
            .open(directory.join("copy.apk"))?)
    }
    #[test]
    fn held_apk_hash_uses_all_bytes_despite_shared_cursor_and_rejects_tail_size() -> Result<()> {
        let directory = tempfile::tempdir()?;
        let (pin, mut held, _) = source_fixture(directory.path())?;
        held.seek(SeekFrom::End(0))?;
        assert_eq!(held_apk_hash(&held, pin.bytes)?, pin.sha256);
        assert!(held_apk_hash(&held, pin.bytes - 1).is_err());
        assert!(held_apk_hash(&held, pin.bytes + 1).is_err());
        Ok(())
    }
    #[test]
    fn held_apk_copy_keeps_source_fd_and_creates_complete_independent_protected_inode() -> Result<()>
    {
        ensure(
            rustix::process::geteuid().is_root(),
            "root fixture required for real root publication",
        )?;
        let directory = tempfile::tempdir()?;
        let (pin, mut held, identity) = source_fixture(directory.path())?;
        held.seek(SeekFrom::End(0))?;
        let source = VerifiedApkSource {
            pin: &pin,
            file: &held,
            identity: &identity,
        };
        let mut output = target(directory.path())?;
        source.copy_to(&mut output)?;
        let after = crate::fs::stat(&output)?;
        assert_ne!((after.dev, after.ino), (identity.dev, identity.ino));
        assert_eq!(after.mode, 0o100400);
        assert_eq!(after.nlink, 1);
        assert_eq!(held_apk_hash(&output, pin.bytes)?, pin.sha256);
        assert_eq!(crate::fs::stat(&held)?, identity);
        let mut raw = vec![0; pin.bytes as usize];
        output.read_exact_at(&mut raw, 0)?;
        assert_eq!(crate::fs::digest(&raw), pin.sha256);
        Ok(())
    }
    #[test]
    fn held_apk_copy_rejects_same_bytes_named_replacement_before_any_destination_write()
    -> Result<()> {
        ensure(
            rustix::process::geteuid().is_root(),
            "root fixture required for real root publication",
        )?;
        let directory = tempfile::tempdir()?;
        let (pin, held, identity) = source_fixture(directory.path())?;
        let source = VerifiedApkSource {
            pin: &pin,
            file: &held,
            identity: &identity,
        };
        std::fs::rename(&pin.path, directory.path().join("retained-source.apk"))?;
        let mut replacement = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o400)
            .open(&pin.path)?;
        replacement.write_all(b"PK\x03\x04actual independent package bytes\n")?;
        replacement.sync_all()?;
        let mut output = target(directory.path())?;
        assert!(source.copy_to(&mut output).is_err());
        assert_eq!(crate::fs::stat(&output)?.size, 0);
        Ok(())
    }
    #[test]
    fn held_apk_copy_rejects_source_alias_and_preexisting_destination_tail() -> Result<()> {
        ensure(
            rustix::process::geteuid().is_root(),
            "root fixture required for real root publication",
        )?;
        let directory = tempfile::tempdir()?;
        let (pin, held, identity) = source_fixture(directory.path())?;
        let source = VerifiedApkSource {
            pin: &pin,
            file: &held,
            identity: &identity,
        };
        let mut alias = OpenOptions::new().read(true).write(true).open(&pin.path)?;
        assert!(source.copy_to(&mut alias).is_err());
        let mut output = target(directory.path())?;
        output.write_all(b"tail")?;
        output.sync_all()?;
        assert!(source.copy_to(&mut output).is_err());
        assert_eq!(crate::fs::stat(&output)?.size, 4);
        assert_eq!(crate::fs::stat(&held)?, identity);
        Ok(())
    }
}
