//! Complete native preparation is a distinct typed path. It cannot turn the
//! historical selected public tree, or a baseline-only capture, into an
//! installed normal native release.
use crate::boot_files::{self, FilePin};
use crate::complete_identity::{AccountBinding, Inputs};
use crate::complete_native::{self, CompleteManifest};
use crate::complete_snapshot::{self, CompleteEntry, Snapshot, StaticDevice};
use crate::model::Identity;
use crate::{Result, ensure, fs};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

pub(super) const SCHEMA: &str = "droidloom.complete-ubuntu-native-prepared.v1";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct NativePlan {
    schema: String,
    work_directory: PathBuf,
    fixture_manifest: FilePin,
    fixture_root: PathBuf,
    native: Inputs,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PreparedMembers {
    schema: String,
    fixture_manifest_sha256: String,
    root_identity: Identity,
    entries: Vec<CompleteEntry>,
    static_devices: Vec<StaticDevice>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Prepared {
    pub schema: String,
    pub input_sha256: String,
    pub work_directory: PathBuf,
    pub root: PathBuf,
    pub root_identity: Identity,
    pub fixture_manifest: FilePin,
    pub prepared_members: FilePin,
    pub root_filesystem_uuid: String,
    pub network_connection_uuid: String,
    pub native_initialization: Value,
    pub gdm_account_binding: AccountBinding,
    pub complete_package_database: bool,
    pub normal_native_packages_installed: bool,
    pub guest_qualified: bool,
    pub production_ready: bool,
}

pub(super) struct Admission {
    pub prepared: Prepared,
    pub manifest: CompleteManifest,
}

fn read_manifest(pin: &FilePin) -> Result<CompleteManifest> {
    let result: CompleteManifest =
        serde_json::from_slice(&boot_files::read_pin(pin, 128 * 1024 * 1024)?)?;
    let source = complete_native::validate(&result)?;
    ensure(
        source.stage == "installed"
            && source.native_release.is_some()
            && source.native_transaction.is_some(),
        "complete native boot requires the actual successful normal installed transaction",
    )?;
    Ok(result)
}

pub(super) fn prepare(path: &Path, sha: &str) -> Result<()> {
    let plan: NativePlan = fs::read_json(&fs::absolute_string(path)?, sha)?;
    ensure(
        plan.schema == "droidloom.complete-ubuntu-native-boot-plan.v1",
        "unsupported complete native preparation plan",
    )?;
    let manifest = read_manifest(&plan.fixture_manifest)?;
    let authority = complete_native::validate(&manifest)?;
    ensure(
        plan.fixture_root == authority.root.path,
        "complete fixture source differs from the original captured root",
    )?;
    crate::boot::create_work(&plan.work_directory)?;
    fs::write_json(
        &fs::absolute_string(&plan.work_directory.join("INPUTS.json"))?,
        &plan,
        0,
    )?;
    let root = plan.work_directory.join("root");
    let cloned = complete_native::materialize(&manifest, &plan.fixture_manifest.sha256, &root)?;
    fs::write_json(
        &fs::absolute_string(&plan.work_directory.join("COMPLETE-CLONE.json"))?,
        &cloned,
        0,
    )?;
    let initialized =
        crate::complete_identity::initialize(&root, &plan.work_directory, &plan.native, &manifest)?;
    let binding: AccountBinding =
        serde_json::from_value(initialized["gdm_account_binding"].clone())?;
    let tree = Snapshot::open(&root)?;
    binding.verify(
        &tree.bytes("/etc/passwd", 1048576)?,
        &tree.bytes("/etc/group", 1048576)?,
    )?;
    let (entries, static_devices) = complete_snapshot::capture(&tree)?;
    let mut structural = manifest.clone();
    structural.entries = entries.clone();
    structural.static_devices = static_devices.clone();
    complete_native::validate_members(&structural)?;
    let members = PreparedMembers {
        schema: "droidloom.complete-native-prepared-members.v1".into(),
        fixture_manifest_sha256: plan.fixture_manifest.sha256.clone(),
        root_identity: fs::stat(&tree.root)?,
        entries,
        static_devices,
    };
    let members_path = plan.work_directory.join("PREPARED-MEMBERS.json");
    fs::write_json(&fs::absolute_string(&members_path)?, &members, 0)?;
    let prepared = Prepared {
        schema: SCHEMA.into(),
        input_sha256: sha.into(),
        work_directory: plan.work_directory.clone(),
        root,
        root_identity: members.root_identity.clone(),
        fixture_manifest: plan.fixture_manifest,
        prepared_members: boot_files::pin_file(&members_path)?,
        root_filesystem_uuid: plan.native.root_filesystem_uuid,
        network_connection_uuid: plan.native.network_connection_uuid,
        native_initialization: initialized,
        gdm_account_binding: binding,
        complete_package_database: true,
        normal_native_packages_installed: true,
        guest_qualified: false,
        production_ready: false,
    };
    let output = plan.work_directory.join("NATIVE-PREPARED.json");
    fs::write_json(&fs::absolute_string(&output)?, &prepared, 0)?;
    println!(
        "{}",
        json!({"receipt":boot_files::pin_file(&output)?,"guest_qualified":false,"production_ready":false})
    );
    Ok(())
}

pub(super) fn admit(value: &Value, receipt: &FilePin) -> Result<Admission> {
    let prepared: Prepared = serde_json::from_value(value.clone())?;
    ensure(
        prepared.schema == SCHEMA
            && prepared.complete_package_database
            && prepared.normal_native_packages_installed
            && !prepared.guest_qualified
            && !prepared.production_ready
            && fs::valid_digest(&prepared.input_sha256)
            && prepared.work_directory.parent()
                == Some(Path::new("/var/lib/droidloom-qualification"))
            && prepared.root == prepared.work_directory.join("root")
            && receipt.path == prepared.work_directory.join("NATIVE-PREPARED.json")
            && prepared.prepared_members.path
                == prepared.work_directory.join("PREPARED-MEMBERS.json"),
        "invalid complete native preparation authority",
    )?;
    let tree = Snapshot::open(&prepared.root)?;
    ensure(
        fs::stat(&tree.root)? == prepared.root_identity,
        "prepared complete root identity changed",
    )?;
    let manifest = read_manifest(&prepared.fixture_manifest)?;
    let members: PreparedMembers = serde_json::from_slice(&boot_files::read_pin(
        &prepared.prepared_members,
        128 * 1024 * 1024,
    )?)?;
    ensure(
        members.schema == "droidloom.complete-native-prepared-members.v1"
            && members.fixture_manifest_sha256 == prepared.fixture_manifest.sha256
            && members.root_identity == prepared.root_identity,
        "complete prepared member manifest has another authority",
    )?;
    let mut structural = manifest.clone();
    structural.entries = members.entries.clone();
    structural.static_devices = members.static_devices.clone();
    complete_native::validate_members(&structural)?;
    complete_snapshot::verify(&tree, &members.entries, &members.static_devices)?;
    prepared.gdm_account_binding.verify(
        &tree.bytes("/etc/passwd", 1048576)?,
        &tree.bytes("/etc/group", 1048576)?,
    )?;
    ensure(
        prepared.native_initialization["schema"] == "droidloom.complete-native-initialization.v1"
            && prepared.native_initialization["complete_package_database_preserved"] == true
            && prepared.native_initialization["normal_package_database_updated"] == false
            && prepared.native_initialization["gdm_account_binding"]
                == serde_json::to_value(&prepared.gdm_account_binding)?
            && prepared.native_initialization["accounts"]["groups"]["gdm"]
                == prepared.gdm_account_binding.gid,
        "complete initialization receipt is not bound to its actual account database",
    )?;
    // No package-manager operation occurs between capture and image creation.
    let original = manifest
        .entries
        .iter()
        .find(|e| e.path == "/var/lib/dpkg/status")
        .ok_or("source status absent")?;
    let (_, sha, _) = tree.regular("/var/lib/dpkg/status")?;
    ensure(
        matches!(&original.content,crate::model::Content::Regular{sha256}if *sha256==sha),
        "prepared complete package status differs from the real installed release",
    )?;
    Ok(Admission { prepared, manifest })
}
