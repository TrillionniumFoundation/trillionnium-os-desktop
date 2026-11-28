//! Exact Settings AddAccount source repair and its normal APK consumer.
//!
//! The 651-project lock remains unchanged. Four original build inputs omitted
//! by its sparse Settings selection are supplied from that same project commit,
//! journaled explicitly, and restored to their original state. This does not
//! identify the CP2A source profile as CP3A or qualify Android execution.
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

const PROJECT: &str = "packages/apps/Settings";
const PROJECT_PIN: &str = "213829fb67f5e070029e0513a088f31bc8f5c1ed";
const CVE: &str = "CVE-2026-58943";
const JAVA: &str = "src/com/android/settings/accounts/AddAccountSettings.java";
const ORIGINAL_BYTES: u64 = 11049;
const ORIGINAL_SHA: &str = "6d72c50a8883676d20544d61301afb4998fd8ad7be428ceee9c4d41915d66a36";
const FIXED_BYTES: u64 = 12221;
const FIXED_SHA: &str = "7c46eb5b516eb2de1b669daebeb7656f061ef347f33f2a6f92f95d8836f4c7f0";
const BP_BYTES: u64 = 6448;
const BP_SHA: &str = "a2f9de37f38ce72b44adfff18e8553640e7255f80de3f00b248ec7c2f537e115";
const PATCH: &str = "android/security/settings-asb/9c7b03ebb0471c18b3d30a21873308d917570c8e.patch";
const PATCH_BYTES: u64 = 3256;
const PATCH_SHA: &str = "2ec497de1552ee5df5a3edb15d7ad68cb81e2e588edec8976352599dedb6a399";
const INPUTS: &str = "droidloom-settings-asb-security-inputs.json";
const NORMAL: &str = "droidloom-settings-asb-security-normal-result.json";
const INSTALLED_APK: &str = "system_ext/priv-app/Settings/Settings.apk";
const MAX_JSON: u64 = 64 * 1024 * 1024;
const MAX_APK: u64 = 1024 * 1024 * 1024;

struct Provider {
    relative: &'static str,
    recipe: &'static str,
    bytes: &'static [u8],
    sha256: &'static str,
    git_blob: &'static str,
}

const PROVIDERS: &[Provider] = &[
    Provider {
        relative: "AndroidManifest.xml",
        recipe: "android/security/settings-asb/providers/AndroidManifest.xml",
        bytes: include_bytes!(
            "../../../android/security/settings-asb/providers/AndroidManifest.xml"
        ),
        sha256: "04eae21c25f1b1525933d3b82b3e4643065d9f390cbc785971d61f1422aca998",
        git_blob: "c0cd7748c8f2b3cf0f280600cb023aa18257f78c",
    },
    Provider {
        relative: "NOTICE",
        recipe: "android/security/settings-asb/providers/NOTICE",
        bytes: include_bytes!("../../../android/security/settings-asb/providers/NOTICE"),
        sha256: "38751245389e1e23f73e6f5384b5cbe7fa972cc4410c5adc9c04b082a0b9561a",
        git_blob: "c5b1efa7aac764ae6d8da63476a2d5cec02a6a5d",
    },
    Provider {
        relative: "proguard.flags",
        recipe: "android/security/settings-asb/providers/proguard.flags",
        bytes: include_bytes!("../../../android/security/settings-asb/providers/proguard.flags"),
        sha256: "987a4a8c3613db2e9776a96b1f6fda7c592677351bdb78cc4689ad69d72ba4fe",
        git_blob: "b648707f6d659b1b000b7c711f9d221863cdbf59",
    },
    Provider {
        relative: "lint-baseline.xml",
        recipe: "android/security/settings-asb/providers/lint-baseline.xml",
        bytes: include_bytes!("../../../android/security/settings-asb/providers/lint-baseline.xml"),
        sha256: "ccb3cd41693f1fc1df1eafa83049a0d630ec15b6602802fb18b8244691d965eb",
        git_blob: "07f7a72a2b0840e5d81b2e72668374c85d1154fd",
    },
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
        return fail("Settings inputs require an absolute original path");
    }
    for parent in path.ancestors().skip(1) {
        let meta = fs::symlink_metadata(parent)?;
        if !meta.is_dir() || meta.file_type().is_symlink() {
            return fail("Settings input parent is not an original directory");
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
        return fail("Settings input must be a bounded single-link regular file");
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
            .ok_or("Settings input length overflow")?;
        if total > before.len() {
            return fail("Settings input grew while hashing");
        }
        state.update(&buffer[..n]);
    }
    if total != before.len()
        || identity(&file.metadata()?)? != expected
        || identity(&fs::symlink_metadata(path)?)? != expected
    {
        return fail("Settings input changed during complete read");
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
            "Settings complete input differs: {}",
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
        return fail("Settings original changed after binding");
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
        return fail("Settings original was replaced before reading its body");
    }
    let cap = reference
        .bytes
        .checked_add(1)
        .ok_or("Settings body bound overflow")?;
    let mut body = Vec::new();
    (&mut file).take(cap).read_to_end(&mut body)?;
    if body.len() as u64 != reference.bytes
        || hex::encode(Sha256::digest(&body)) != reference.sha256
        || identity(&file.metadata()?)? != reference.identity
        || identity(&fs::symlink_metadata(&reference.path)?)? != reference.identity
    {
        return fail("Settings original body changed during bounded read");
    }
    ordinary_parent(&reference.path)?;
    Ok(body)
}

pub(super) fn required_for_targets(targets: &[&str]) -> bool {
    targets
        .iter()
        .any(|name| matches!(*name, "Settings" | "Settings-core"))
}

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if !request.uses_production_full_source()
        || request.source_mode() != SoongDependencyMode::Strict
        || ["Settings", "module-info"].iter().any(|required| {
            request
                .requested_targets()
                .iter()
                .filter(|actual| *actual == required)
                .count()
                != 1
        })
    {
        return fail(
            "Settings repair requires strict complete-source Settings and module-info targets",
        );
    }
    Ok(())
}

pub(super) fn validate_source_lock(repo: &Path, lock_path: &Path) -> Result<()> {
    if lock_path != repo.join(production_source::LOCK_PATH) {
        return fail("Settings repair requires the unchanged production source lock");
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
        || rows[0].name != "platform/packages/apps/Settings"
        || rows[0].commit != PROJECT_PIN
    {
        return fail("Settings source lock has a foreign or ambiguous provider revision");
    }
    recheck(&reference)
}

fn optional_provider(source: &Path, provider: &Provider) -> Result<Option<FileRef>> {
    let path = source.join(PROJECT).join(provider.relative);
    ordinary_parent(&path)?;
    match fs::symlink_metadata(&path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
        Ok(_) => exact(&path, provider.bytes.len() as u64, provider.sha256).map(Some),
    }
}

pub(super) struct Projected {
    original_java: FileRef,
    original_bp: FileRef,
    original_providers: Vec<Option<FileRef>>,
    recipe: Vec<FileRef>,
}

pub(super) fn validate_original(repo: &Path, source: &Path) -> Result<()> {
    originals(repo, source).map(|_| ())
}

fn originals(repo: &Path, source: &Path) -> Result<Projected> {
    let original_java = exact(
        &source.join(PROJECT).join(JAVA),
        ORIGINAL_BYTES,
        ORIGINAL_SHA,
    )?;
    let original_bp = exact(&source.join(PROJECT).join("Android.bp"), BP_BYTES, BP_SHA)?;
    let mut recipe = vec![exact(&repo.join(PATCH), PATCH_BYTES, PATCH_SHA)?];
    let mut original_providers = Vec::new();
    for provider in PROVIDERS {
        let input = exact(
            &repo.join(provider.recipe),
            provider.bytes.len() as u64,
            provider.sha256,
        )?;
        if bound_body(&input)? != provider.bytes {
            return fail("Settings compiled provider differs from the original recipe file");
        }
        recipe.push(input);
        original_providers.push(optional_provider(source, provider)?);
    }
    Ok(Projected {
        original_java,
        original_bp,
        original_providers,
        recipe,
    })
}

fn check_journal(projection: &Projection, path: &Path, original: Option<&FileRef>) -> Result<()> {
    let rows: Vec<_> = projection
        .originals
        .iter()
        .filter(|item| item.path == path)
        .collect();
    if rows.len() != 1 {
        return fail("Settings original is not uniquely journaled");
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
                .ok_or("Settings original bytes are absent from journal")?;
            let modified =
                std::time::UNIX_EPOCH + std::time::Duration::from_nanos(original.identity[7]);
            if bytes.len() as u64 != original.bytes
                || hex::encode(Sha256::digest(bytes)) != original.sha256
                || row.modified != Some(modified)
                || row.permissions_mode.map(u64::from) != Some(original.identity[2])
            {
                return fail(
                    "Settings journal does not preserve its actual original bytes, mode and time",
                );
            }
            Ok(())
        }
        _ => fail("Settings original absence is not preserved by the journal"),
    }
}

pub(super) fn project(
    projection: &mut Projection,
    repo: &Path,
    source: &Path,
) -> Result<Projected> {
    let before = originals(repo, source)?;
    let paths: Vec<_> = std::iter::once(source.join(PROJECT).join(JAVA))
        .chain(
            PROVIDERS
                .iter()
                .map(|p| source.join(PROJECT).join(p.relative)),
        )
        .collect();
    projection.save_many(&paths)?;
    check_journal(
        projection,
        &before.original_java.path,
        Some(&before.original_java),
    )?;
    for (provider, original) in PROVIDERS.iter().zip(&before.original_providers) {
        check_journal(
            projection,
            &source.join(PROJECT).join(provider.relative),
            original.as_ref(),
        )?;
    }
    // Complete validation and durable preregistration precede every source write.
    recheck(&before.original_java)?;
    recheck(&before.original_bp)?;
    for reference in &before.recipe {
        recheck(reference)?;
    }
    for reference in before.original_providers.iter().flatten() {
        recheck(reference)?;
    }
    for (provider, original) in PROVIDERS.iter().zip(&before.original_providers) {
        let path = source.join(PROJECT).join(provider.relative);
        match original {
            Some(reference) => recheck(reference)?,
            None => {
                if optional_provider(source, provider)?.is_some() {
                    return fail("Settings supplemental provider appeared after journal capture");
                }
                projection.put(&path, provider.bytes)?;
            }
        }
        exact(&path, provider.bytes.len() as u64, provider.sha256)?;
    }
    projection.patch(source, PROJECT, &repo.join(PATCH))?;
    exact(&source.join(PROJECT).join(JAVA), FIXED_BYTES, FIXED_SHA)?;
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
    let bp = exact(&source.join(PROJECT).join("Android.bp"), BP_BYTES, BP_SHA)?;
    check_journal(
        projection,
        &before.original_java.path,
        Some(&before.original_java),
    )?;
    let mut providers = Vec::new();
    for (provider, original) in PROVIDERS.iter().zip(&before.original_providers) {
        let path = source.join(PROJECT).join(provider.relative);
        check_journal(projection, &path, original.as_ref())?;
        providers.push(json!({
            "project_relative_path": provider.relative,
            "source_project_revision": PROJECT_PIN,
            "original_git_blob": provider.git_blob,
            "recipe_path": repo.join(provider.recipe),
            "originally_absent": original.is_none(),
            "original": original,
            "effective": exact(&path, provider.bytes.len() as u64, provider.sha256)?,
        }));
    }
    for reference in &before.recipe {
        recheck(reference)?;
    }
    let requested_targets: Vec<_> = request
        .requested_targets()
        .iter()
        .map(|s| (*s).to_owned())
        .collect();
    let value = json!({
        "schema": "droidloom-settings-asb-security-inputs-v1",
        "CVE_rows": [CVE],
        "source_lock": lock,
        "source_project": PROJECT,
        "source_project_revision": PROJECT_PIN,
        "source_release": PRODUCTION_TARGET_RELEASE,
        "build_variant": PRODUCTION_BUILD_VARIANT,
        "original_java": before.original_java,
        "effective_java": fixed,
        "original_java_git_blob": "85e942b199058c68a9eaa025deec49b8d3190ea6",
        "fixed_java_git_blob": "34f87f1a3521eac075c8773db22da9d5296804d0",
        "original_android_bp": before.original_bp,
        "effective_android_bp": bp,
        "official_complete_patch": before.recipe[0],
        "official_patch_commit": "9c7b03ebb0471c18b3d30a21873308d917570c8e",
        "same_fix_alias_not_replayed": "b70d3754d990391f9f7bda92c9fbf659cd2e01f2",
        "additional_original_provider_inputs": providers,
        "additional_inputs_in_original_sparse_lock": false,
        "original_source_lock_changed": false,
        "requested_targets": requested_targets,
        "product": product,
        "effective_projection": projection.effective_inventory(repo, source)?,
        "required_installed_module": ["Settings", PROJECT, INSTALLED_APK],
        "strict_allow_missing_dependencies": "false",
        "selinux_ignore_neverallows": "false",
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
        return fail("Settings original mode/owner/link count/length/mtime was not restored");
    }
    Ok(actual)
}

fn completed_artifacts(out: &Path, product: &str) -> Result<(FileRef, FileRef)> {
    let root = out.join("target/product").join(product);
    let info = pin(&root.join("module-info.json"), MAX_JSON)?;
    let value: Value = serde_json::from_slice(&bound_body(&info)?)?;
    let row = value
        .get("Settings")
        .ok_or("normal Settings module-info row is missing")?;
    if row["path"] != json!([PROJECT]) {
        return fail("normal Settings APK has a foreign or ambiguous source provider");
    }
    let expected = root.join(INSTALLED_APK);
    let paths = row["installed"]
        .as_array()
        .ok_or("normal Settings installed paths are missing")?;
    let mut seen = std::collections::BTreeSet::new();
    let mut count = 0;
    for value in paths {
        let text = value
            .as_str()
            .ok_or("Settings installed path is not a string")?;
        let path = Path::new(text);
        if !path.is_absolute()
            || text
                .split('/')
                .skip(1)
                .any(|part| part.is_empty() || part == "." || part == "..")
            || !seen.insert(path.to_owned())
        {
            return fail("Settings installed path is aliased or duplicated");
        }
        if path == expected {
            count += 1;
        }
    }
    if count != 1 {
        return fail("normal Settings APK is not the exact installed system_ext artifact");
    }
    let apk = pin(&expected, MAX_APK)?;
    if apk.bytes == 0 {
        return fail("normal Settings APK is empty");
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
        return fail("Settings normal completion does not belong to its actual source/request");
    }
    recheck(&input.reference)?;
    recheck(&input.lock)?;
    for reference in &input.before.recipe {
        recheck(reference)?;
    }
    let java = restored(&input.before.original_java)?;
    let bp = restored(&input.before.original_bp)?;
    let mut providers = Vec::new();
    for (provider, original) in PROVIDERS.iter().zip(&input.before.original_providers) {
        let actual = match original {
            Some(reference) => Some(restored(reference)?),
            None => {
                if optional_provider(source, provider)?.is_some() {
                    return fail(
                        "Settings originally absent provider was not removed by restoration",
                    );
                }
                None
            }
        };
        providers.push(json!({"project_relative_path": provider.relative, "restored": actual, "originally_absent": original.is_none()}));
    }
    let (module_info, apk) = completed_artifacts(out, product)?;
    recheck(&input.reference)?;
    recheck(&input.lock)?;
    let value = json!({
        "schema": "droidloom-settings-asb-security-normal-result-v1",
        "CVE_rows": [CVE],
        "inputs": input.reference,
        "requested_targets": input.requested_targets,
        "product": product,
        "normal_command_returned_success": true,
        "module_info": module_info,
        "APK": apk,
        "required_installed_module": ["Settings", PROJECT, INSTALLED_APK],
        "source_project_revision": PROJECT_PIN,
        "source_release": PRODUCTION_TARGET_RELEASE,
        "build_variant": PRODUCTION_BUILD_VARIANT,
        "restored_java": java,
        "restored_android_bp": bp,
        "restored_supplemental_providers": providers,
        "original_source_bytes_mode_mtime_and_absence_restored": true,
        "source_inode_or_ctime_restoration_claim": false,
        "strict_allow_missing_dependencies": "false",
        "selinux_ignore_neverallows": "false",
        "QPR1_source_identity_claim": false,
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
#[path = "settings_asb_security_tests.rs"]
mod tests;
