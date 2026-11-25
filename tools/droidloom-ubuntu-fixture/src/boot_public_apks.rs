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
const APKS: usize = 65;
const MAX_APP_BYTES: u64 = 2 * 1024 * 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ImportPlan {
    schema: String,
    execution: FilePin,
    selection: FilePin,
    source_receipt: FilePin,
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

#[derive(Debug, Serialize)]
pub struct Staged {
    pub schema: &'static str,
    pub import: FilePin,
    pub files: Vec<Material>,
    pub applications: Vec<Value>,
    pub package_count: usize,
    pub apk_file_count: usize,
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
    ensure(
        result.len() == PACKAGES,
        "public APK input must contain the complete selected 39",
    )?;
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
    ensure(
        plan.schema == "droidloom.public-apk-import.v1"
            && execution["schema"] == "p4-selected39-execution-v3"
            && execution["scope"] == "fresh_isolated_vm_only"
            && execution["guest_stage"] == STAGE
            && selection["schema"] == "p4-selected39-static-launch-inputs-v1"
            && execution["package_count"] == PACKAGES
            && execution["file_count"] == APKS
            && selection["package_count"] == PACKAGES
            && selection["apk_file_count"] == APKS
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
        receipt["schema"] == "p4-selected39-materials-and-original-signers-handoff-v1"
            && receipt["all_selected_materials_verified"] == true
            && receipt["package_count"] == PACKAGES
            && receipt["file_count"] == APKS
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
                    && signed_matches[0]["metadata"] == original["metadata"],
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
        files.len() == APKS
            && total <= 8 * 1024 * 1024 * 1024
            && selection["apk_total_bytes"] == total,
        "complete selected APK count or byte total differs",
    )?;
    Ok((files, applications))
}

pub fn admit(input: &FilePin, fresh_normal: bool) -> Result<(Staged, Vec<(FilePin, String)>)> {
    ensure(
        fresh_normal,
        "public APK import requires a fresh normal guest without original userdata",
    )?;
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
    let provenance = vec![
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
    Ok((
        Staged {
            schema: "droidloom.public-apks-staged.v1",
            import: input.clone(),
            files,
            applications,
            package_count: PACKAGES,
            apk_file_count: APKS,
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

fn verify_tree(root: &Path, staged: &Staged) -> Result<()> {
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
        expected.len() == APKS + 3 && list(&directory.root)? == expected,
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
    ensure(
        files.len() == APKS + 3,
        "ext4 public material set is incomplete",
    )?;
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
        "package_count":PACKAGES,"apk_file_count":APKS,"provenance_file_count":3,
        "all_original_bytes_matched":true,"readonly_ext4_reader":true,
        "applications_installed":0,"application_business_accepted":false,
        "guest_qualified":false,"production_ready":false}),
    )
}

#[cfg(test)]
#[path = "boot_public_apks_tests.rs"]
mod tests;
