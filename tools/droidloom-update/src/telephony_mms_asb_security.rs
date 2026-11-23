//! Official MmsProvider subscription-ownership repair on the existing complete-source builder.
//! Only the production Java hunk is adapted to the exact original source context.
//! No provider requests or device tests execute here; build receipts do not qualify DEX or runtime.
use super::*;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    io::Read,
    os::unix::{
        ffi::OsStrExt,
        fs::{MetadataExt, OpenOptionsExt},
    },
};

const PROJECT: &str = "packages/providers/TelephonyProvider";
const PROJECT_PIN: &str = "013b803626164c026025897b7dec45521c2cccab";
const CVE: &str = "CVE-2026-59005";
const JAVA: &str = "src/com/android/providers/telephony/MmsProvider.java";
const ORIGINAL_BYTES: u64 = 75335;
const ORIGINAL_SHA: &str = "c4c7c49f08c538a320e76e2a4e6c8e485d7a9806cab1a46104f8098a90298ddc";
const FIXED_BYTES: u64 = 75313;
const FIXED_SHA: &str = "5e3488a4809e49611ef63c3fa5397f82c0c9358132e2710ca131817211f767bc";
const PATCH: &str =
    "android/security/telephony-mms-asb/95af247d92b5c0b5d02dfa5ca2a62310e4cedbd6-production.patch";
const PATCH_BYTES: u64 = 1232;
const PATCH_SHA: &str = "f21989ebe9fa6009020459e778b7c1b9af3395473307f87fd3f4e5b01f1423df";
const INPUTS: &str = "droidloom-telephony-mms-asb-security-inputs.json";
const NORMAL: &str = "droidloom-telephony-mms-asb-security-normal-result.json";
const MAX_JSON: u64 = 64 * 1024 * 1024;
const MAX_APK: u64 = 1024 * 1024 * 1024;
const INSTALLED_APK: &str = "system/priv-app/TelephonyProvider/TelephonyProvider.apk";
const DEPENDENCIES: &[(&str, u64, &str)] = &[
    (
        "Android.bp",
        1275,
        "2230d066908a394ea19be6eb180225856f3bbe780c4edbf1781aa3fc137a9719",
    ),
    (
        "AndroidManifest.xml",
        7578,
        "c85291048f0dbffe058771cf6a3da2d3994092c0b27606c982b781467b894cbb",
    ),
    (
        "AndroidManifestHsum.xml",
        1896,
        "e9db62d96df4ae7b18df5da769756786378c9a07d756e383d8dc46f271eed7e4",
    ),
    (
        "src/com/android/providers/telephony/ProviderUtil.java",
        23852,
        "4e0e62bbc937986f53667c92234be8c3163f935e366533cf39a418f076397b0f",
    ),
];

#[derive(Clone, Debug, Serialize)]
struct FileRef {
    path: PathBuf,
    bytes: u64,
    sha256: String,
    identity: [u64; 9],
}

fn identity(meta: &fs::Metadata) -> Result<[u64; 9]> {
    Ok([
        meta.dev(),
        meta.ino(),
        u64::from(meta.mode()),
        u64::from(meta.uid()),
        u64::from(meta.gid()),
        meta.nlink(),
        meta.len(),
        (i128::from(meta.mtime()) * 1_000_000_000 + i128::from(meta.mtime_nsec())).try_into()?,
        (i128::from(meta.ctime()) * 1_000_000_000 + i128::from(meta.ctime_nsec())).try_into()?,
    ])
}

fn ordinary_parent(path: &Path) -> Result<()> {
    if !path.is_absolute()
        || path.as_os_str().as_bytes()[1..]
            .split(|byte| *byte == b'/')
            .any(|part| part.is_empty() || part == b"." || part == b"..")
    {
        return fail("Telephony MMS inputs require an absolute original path");
    }
    for parent in path.ancestors().skip(1) {
        let meta = fs::symlink_metadata(parent)?;
        if !meta.is_dir() || meta.file_type().is_symlink() {
            return fail("Telephony MMS input parent is not an original directory");
        }
    }
    Ok(())
}

fn pin(path: &Path, cap: u64) -> Result<FileRef> {
    ordinary_parent(path)?;
    let mut file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(path)?;
    let before = file.metadata()?;
    if !before.is_file() || before.nlink() != 1 || before.len() > cap {
        return fail("Telephony MMS input must be a bounded single-link regular file");
    }
    let expected = identity(&before)?;
    let mut state = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    let mut total = 0u64;
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        total = total
            .checked_add(n as u64)
            .ok_or("Telephony MMS input length overflow")?;
        if total > before.len() {
            return fail("Telephony MMS input grew while hashing");
        }
        state.update(&buffer[..n]);
    }
    if total != before.len()
        || identity(&file.metadata()?)? != expected
        || identity(&fs::symlink_metadata(path)?)? != expected
    {
        return fail("Telephony MMS input changed during complete read");
    }
    ordinary_parent(path)?;
    Ok(FileRef {
        path: path.to_owned(),
        bytes: total,
        sha256: hex::encode(state.finalize()),
        identity: expected,
    })
}

fn exact(path: &Path, bytes: u64, sha256: &str) -> Result<FileRef> {
    let actual = pin(path, bytes)?;
    if actual.bytes != bytes || actual.sha256 != sha256 {
        return fail(format!(
            "Telephony MMS complete input differs: {}",
            path.display()
        ));
    }
    Ok(actual)
}

fn recheck(original: &FileRef) -> Result<()> {
    let actual = pin(&original.path, original.bytes)?;
    if actual.bytes != original.bytes
        || actual.sha256 != original.sha256
        || actual.identity != original.identity
    {
        return fail("Telephony MMS original changed after binding");
    }
    Ok(())
}

fn bound_body(reference: &FileRef) -> Result<Vec<u8>> {
    ordinary_parent(&reference.path)?;
    let mut file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
        .open(&reference.path)?;
    if identity(&file.metadata()?)? != reference.identity {
        return fail("Telephony MMS original was replaced before reading its body");
    }
    let cap = reference
        .bytes
        .checked_add(1)
        .ok_or("Telephony MMS body bound overflow")?;
    let mut body = Vec::new();
    (&mut file).take(cap).read_to_end(&mut body)?;
    if body.len() as u64 != reference.bytes
        || hex::encode(Sha256::digest(&body)) != reference.sha256
        || identity(&file.metadata()?)? != reference.identity
        || identity(&fs::symlink_metadata(&reference.path)?)? != reference.identity
    {
        return fail("Telephony MMS original body changed during bounded read");
    }
    ordinary_parent(&reference.path)?;
    Ok(body)
}

pub(super) fn required_for_targets(targets: &[&str]) -> bool {
    targets
        .iter()
        .any(|name| matches!(*name, "TelephonyProvider" | "TelephonyProviderHsum"))
}

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if !request.complete_delivery()
        || !request.uses_production_full_source()
        || request.source_mode() != SoongDependencyMode::Strict
        || request
            .requested_targets()
            .contains(&"TelephonyProviderHsum")
        || ["TelephonyProvider", "module-info"].iter().any(|required| {
            request
                .requested_targets()
                .iter()
                .filter(|actual| *actual == required)
                .count()
                != 1
        })
    {
        return fail(
            "Telephony MMS repair requires the existing complete-product builder, strict complete source and the exact TelephonyProvider target with module-info",
        );
    }
    Ok(())
}

pub(super) fn validate_source_lock(repo: &Path, lock_path: &Path) -> Result<()> {
    if lock_path != repo.join(production_source::LOCK_PATH) {
        return fail("Telephony MMS repair requires the unchanged production source lock");
    }
    let reference = exact(
        lock_path,
        production_source::LOCK_BYTES as u64,
        production_source::LOCK_SHA,
    )?;
    let lock = droidloom_source::load_lock(lock_path)?;
    let rows: Vec<_> = lock
        .projects
        .iter()
        .filter(|p| p.path == Path::new(PROJECT))
        .collect();
    if rows.len() != 1
        || rows[0].name != "platform/packages/providers/TelephonyProvider"
        || rows[0].commit != PROJECT_PIN
    {
        return fail("Telephony MMS source lock has a foreign or ambiguous provider revision");
    }
    recheck(&reference)
}

pub(super) struct Projected {
    original_java: FileRef,
    original_dependencies: Vec<FileRef>,
    patch: FileRef,
}

fn originals(repo: &Path, source: &Path) -> Result<Projected> {
    let original_java = exact(
        &source.join(PROJECT).join(JAVA),
        ORIGINAL_BYTES,
        ORIGINAL_SHA,
    )?;
    let mut original_dependencies = Vec::new();
    for (relative, bytes, sha256) in DEPENDENCIES {
        original_dependencies.push(exact(&source.join(PROJECT).join(relative), *bytes, sha256)?);
    }
    let patch = exact(&repo.join(PATCH), PATCH_BYTES, PATCH_SHA)?;
    Ok(Projected {
        original_java,
        original_dependencies,
        patch,
    })
}

pub(super) fn validate_original(repo: &Path, source: &Path) -> Result<()> {
    originals(repo, source).map(|_| ())
}

fn check_journal(projection: &Projection, path: &Path, original: Option<&FileRef>) -> Result<()> {
    let rows: Vec<_> = projection
        .originals
        .iter()
        .filter(|item| item.path == path)
        .collect();
    if rows.len() != 1 {
        return fail("Telephony MMS original is not uniquely journaled");
    }
    let row = rows[0];
    match original {
        None if row.bytes.is_none() && row.modified.is_none() && row.permissions_mode.is_none() => {
            Ok(())
        }
        Some(original) => {
            let bytes = row
                .bytes
                .as_ref()
                .ok_or("Telephony MMS original bytes are absent from journal")?;
            let modified =
                std::time::UNIX_EPOCH + std::time::Duration::from_nanos(original.identity[7]);
            if bytes.len() as u64 != original.bytes
                || hex::encode(Sha256::digest(bytes)) != original.sha256
                || row.modified != Some(modified)
                || row.permissions_mode.map(u64::from) != Some(original.identity[2])
            {
                return fail(
                    "Telephony MMS journal does not preserve its actual original bytes, mode and time",
                );
            }
            Ok(())
        }
        _ => fail("Telephony MMS original absence is not preserved by the journal"),
    }
}

pub(super) fn project(
    projection: &mut Projection,
    repo: &Path,
    source: &Path,
) -> Result<Projected> {
    let before = originals(repo, source)?;
    projection.save_many(&[before.original_java.path.clone()])?;
    check_journal(
        projection,
        &before.original_java.path,
        Some(&before.original_java),
    )?;
    // The complete original is durable in the existing journal before the patch writes.
    recheck(&before.original_java)?;
    recheck(&before.patch)?;
    for original in &before.original_dependencies {
        recheck(original)?;
    }
    projection.patch(source, PROJECT, &before.patch.path)?;
    exact(&source.join(PROJECT).join(JAVA), FIXED_BYTES, FIXED_SHA)?;
    for original in &before.original_dependencies {
        recheck(original)?;
    }
    recheck(&before.patch)?;
    Ok(before)
}

pub(super) fn configure_command(
    request: FixedProductionRequest<'_>,
    product: &str,
    command: &mut Command,
) -> Result<()> {
    validate_request(request, product)?;
    enforce_strict_soong_dependencies(command);
    command.env("SELINUX_IGNORE_NEVERALLOWS", "false");
    // No subscription policy, HSUM selection, signing input, or source release is overridden.
    Ok(())
}

pub(super) struct InputReceipt {
    reference: FileRef,
    lock: FileRef,
    before: Projected,
    requested_targets: Vec<String>,
}

pub(super) fn input_receipt(
    repo: &Path,
    source: &Path,
    lock: &Path,
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
    projection: &Projection,
    before: Projected,
) -> Result<InputReceipt> {
    validate_request(request, product)?;
    validate_source_lock(repo, lock)?;
    let lock = exact(
        lock,
        production_source::LOCK_BYTES as u64,
        production_source::LOCK_SHA,
    )?;
    let fixed = exact(&source.join(PROJECT).join(JAVA), FIXED_BYTES, FIXED_SHA)?;
    check_journal(
        projection,
        &before.original_java.path,
        Some(&before.original_java),
    )?;
    recheck(&before.patch)?;
    for original in &before.original_dependencies {
        recheck(original)?;
    }
    let requested_targets: Vec<_> = request
        .requested_targets()
        .iter()
        .map(|s| (*s).to_owned())
        .collect();
    let value = json!({
        "schema": "droidloom-telephony-mms-asb-security-inputs-v1",
        "CVE_rows": [CVE],
        "source_lock": lock,
        "source_project": PROJECT,
        "source_project_revision": PROJECT_PIN,
        "source_release": PRODUCTION_TARGET_RELEASE,
        "build_variant": PRODUCTION_BUILD_VARIANT,
        "original_java": before.original_java,
        "effective_java": fixed,
        "original_java_git_blob": "769941b6649b01622289076b2cda7ebb65b509d5",
        "fixed_java_git_blob": "71bc82548bc19867b88655e3d6c1a936d34c9cae",
        "original_dependencies": before.original_dependencies,
        "official_production_patch": before.patch,
        "official_patch_commit": "95af247d92b5c0b5d02dfa5ca2a62310e4cedbd6",
        "official_patch_scope": "production hunk only; unchanged edit with exact-context adaptation",
        "official_test_hunks_included": false,
        "original_source_lock_changed": false,
        "requested_targets": requested_targets,
        "product": product,
        "effective_projection": projection.effective_inventory(repo, source)?,
        "required_normal_modules": ["TelephonyProvider"],
        "required_installed_APK": INSTALLED_APK,
        "strict_allow_missing_dependencies": "false",
        "selinux_ignore_neverallows": "false",
        "subscription_policy_or_HSUM_selection_overridden": false,
        "headless_system_user_variant_qualified": false,
        "QPR1_source_identity_claim": false,
        "binary_semantic_fix_qualified": false,
        "official_device_tests_executed": false,
        "production_signing_qualified": false,
        "whole_CVE_qualified": false,
        "runtime_qualified": false,
        "production_ready": false,
    });
    let path = out.join(INPUTS);
    write(&path, serde_json::to_vec_pretty(&value)?)?;
    let reference = pin(&path, MAX_JSON)?;
    Ok(InputReceipt {
        reference,
        lock,
        before,
        requested_targets,
    })
}

fn restored(original: &FileRef) -> Result<FileRef> {
    let actual = exact(&original.path, original.bytes, &original.sha256)?;
    // Projection restores complete bytes, permissions and mtime. It does not
    // promise that inode or ctime survives journaled replacement.
    if actual.identity[2..8] != original.identity[2..8] {
        return fail("Telephony MMS original mode/owner/link count/length/mtime was not restored");
    }
    Ok(actual)
}

fn completed_artifacts(out: &Path, product: &str) -> Result<(FileRef, FileRef)> {
    let root = out.join("target/product").join(product);
    let info = pin(&root.join("module-info.json"), MAX_JSON)?;
    let value: Value = serde_json::from_slice(&bound_body(&info)?)?;
    let row = value
        .get("TelephonyProvider")
        .ok_or("normal TelephonyProvider module-info row is missing")?;
    if row["path"] != json!([PROJECT]) {
        return fail("normal TelephonyProvider APK has a foreign or ambiguous source provider");
    }
    let expected = root.join(INSTALLED_APK);
    let paths = row["installed"]
        .as_array()
        .ok_or("normal TelephonyProvider installed paths are missing")?;
    let mut seen = std::collections::BTreeSet::new();
    let mut count = 0;
    for value in paths {
        let text = value
            .as_str()
            .ok_or("TelephonyProvider installed path is not a string")?;
        let path = Path::new(text);
        if !path.is_absolute()
            || text
                .split('/')
                .skip(1)
                .any(|part| part.is_empty() || part == "." || part == "..")
            || !seen.insert(path.to_owned())
        {
            return fail("TelephonyProvider installed path is aliased or duplicated");
        }
        if path == expected {
            count += 1;
        }
    }
    if count != 1 {
        return fail("normal TelephonyProvider APK is not the exact installed system artifact");
    }
    let apk = pin(&expected, MAX_APK)?;
    if apk.bytes == 0 {
        return fail("normal TelephonyProvider APK is empty");
    }
    recheck(&info)?;
    Ok((info, apk))
}

pub(super) fn normal_result(
    repo: &Path,
    source: &Path,
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
    input: InputReceipt,
) -> Result<()> {
    validate_request(request, product)?;
    validate_source_lock(repo, &input.lock.path)?;
    if input.reference.path != out.join(INPUTS)
        || input.before.original_java.path != source.join(PROJECT).join(JAVA)
        || input
            .requested_targets
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>()
            != request.requested_targets()
    {
        return fail(
            "Telephony MMS normal completion does not belong to its actual source/request",
        );
    }
    recheck(&input.reference)?;
    recheck(&input.lock)?;
    recheck(&input.before.patch)?;
    let java = restored(&input.before.original_java)?;
    for original in &input.before.original_dependencies {
        recheck(original)?;
    }
    let (module_info, apk) = completed_artifacts(out, product)?;
    recheck(&input.reference)?;
    recheck(&input.lock)?;
    let value = json!({
        "schema": "droidloom-telephony-mms-asb-security-normal-result-v1",
        "CVE_rows": [CVE],
        "inputs": input.reference,
        "requested_targets": input.requested_targets,
        "product": product,
        "normal_command_returned_success": true,
        "module_info": module_info,
        "APK": apk,
        "source_project_revision": PROJECT_PIN,
        "source_release": PRODUCTION_TARGET_RELEASE,
        "build_variant": PRODUCTION_BUILD_VARIANT,
        "restored_java": java,
        "unchanged_dependencies": input.before.original_dependencies,
        "original_source_bytes_mode_mtime_restored": true,
        "source_inode_or_ctime_restoration_claim": false,
        "strict_allow_missing_dependencies": "false",
        "selinux_ignore_neverallows": "false",
        "subscription_policy_or_HSUM_selection_overridden": false,
        "headless_system_user_variant_qualified": false,
        "QPR1_source_identity_claim": false,
        "installed_APK_verification_required_by_complete_normal": true,
        "artifact_identity_qualified": false,
        "binary_semantic_fix_qualified": false,
        "official_device_tests_executed": false,
        "production_signing_qualified": false,
        "whole_CVE_qualified": false,
        "runtime_qualified": false,
        "production_ready": false,
    });
    write(&out.join(NORMAL), serde_json::to_vec_pretty(&value)?)
}

#[cfg(test)]
#[path = "telephony_mms_asb_security_tests.rs"]
mod tests;
