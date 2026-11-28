//! Exact official Telephony SMS source repair on the existing complete-source builder.
//! The unchanged sparse lock omits three original module inputs. Their exact bytes
//! are journaled with both patched files and restored to their original presence
//! or absence. A normal build record does not qualify DEX, signing or runtime.
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

const PROJECT: &str = "frameworks/opt/telephony";
const PROJECT_PIN: &str = "aef289516bea6118d88cd45c63742cd4abe2c596";
const CVE: &str = "CVE-2026-58964";
const JAVA: &str = "src/java/com/android/internal/telephony/SmsUsageMonitor.java";
const TEST: &str =
    "tests/telephonytests/src/com/android/internal/telephony/SmsUsageMonitorShortCodeTest.java";
const ORIGINAL_BYTES: u64 = 30103;
const ORIGINAL_SHA: &str = "8096cd102d86535699bb75134ca4a59b151d9e27666f7c96328480958b3a215f";
const FIXED_BYTES: u64 = 30243;
const FIXED_SHA: &str = "ad191ccd8842ebd4c3ebe45f6387d3e1149b155c71db20dd61bd31c22a2d0d1c";
const ORIGINAL_TEST_BYTES: u64 = 31030;
const ORIGINAL_TEST_SHA: &str = "d842ba84150715139feb5e33c80744248b08ba13d8035ff1710bcae122d04b69";
const FIXED_TEST_BYTES: u64 = 31435;
const FIXED_TEST_SHA: &str = "bb9e1cbf70d09736c210b17077951f3af07213a8d73e1bc9f3bfb3c9997578de";
const PATCH: &str =
    "android/security/telephony-sms-asb/16a5582a886409268005f8e78710cbda7ffd6552.patch";
const PATCH_BYTES: u64 = 2088;
const PATCH_SHA: &str = "b2472a412a948a03909c0ed61902a14cb5a5178e043e7c3b687a17f5b787d340";
const INPUTS: &str = "droidloom-telephony-sms-asb-security-inputs.json";
const NORMAL: &str = "droidloom-telephony-sms-asb-security-normal-result.json";
const MAX_JSON: u64 = 64 * 1024 * 1024;
const MAX_JAR: u64 = 512 * 1024 * 1024;
const BLUEPRINTS: &[(&str, u64, &str)] = &[(
    "Android.bp",
    3881,
    "58b09b827fa1c36b492c723ac57d85e7a0284392fd06830714e98da16d08f032",
)];

struct Provider {
    relative: &'static str,
    recipe: &'static str,
    bytes: &'static [u8],
    sha256: &'static str,
    git_blob: &'static str,
}

const PROVIDERS: &[Provider] = &[
    Provider {
        relative: "jarjar-rules-shared.txt",
        recipe: "android/security/telephony-sms-asb/providers/jarjar-rules-shared.txt",
        bytes: include_bytes!(
            "../../../android/security/telephony-sms-asb/providers/jarjar-rules-shared.txt"
        ),
        sha256: "4c3b0d2f24bba824fc470d2b7cece6edb60afcd594099d9cb298dfdd1e22184d",
        git_blob: "01bdb758f7deb8362878a3ff793f7a5435be96af",
    },
    Provider {
        relative: "proguard.flags",
        recipe: "android/security/telephony-sms-asb/providers/proguard.flags",
        bytes: include_bytes!(
            "../../../android/security/telephony-sms-asb/providers/proguard.flags"
        ),
        sha256: "9161d2acb6606e24a5e131bdac12af77a152c543f2401511d1a90bb34a6766ff",
        git_blob: "75e67ffaeb9dba9ea80a344735bc9968c5c003de",
    },
    Provider {
        relative: "lint-baseline.xml",
        recipe: "android/security/telephony-sms-asb/providers/lint-baseline.xml",
        bytes: include_bytes!(
            "../../../android/security/telephony-sms-asb/providers/lint-baseline.xml"
        ),
        sha256: "d3066585e46cc68743f69a8f73578430fee053e27e48a2ff313b0be341dee758",
        git_blob: "bb2433c69717658216701df24f15dc8bbcf32c15",
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
        return fail("Telephony SMS inputs require an absolute original path");
    }
    for parent in path.ancestors().skip(1) {
        let meta = fs::symlink_metadata(parent)?;
        if !meta.is_dir() || meta.file_type().is_symlink() {
            return fail("Telephony SMS input parent is not an original directory");
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
        return fail("Telephony SMS input must be a bounded single-link regular file");
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
            .ok_or("Telephony SMS input length overflow")?;
        if total > before.len() {
            return fail("Telephony SMS input grew while hashing");
        }
        state.update(&buffer[..n]);
    }
    if total != before.len()
        || identity(&file.metadata()?)? != expected
        || identity(&fs::symlink_metadata(path)?)? != expected
    {
        return fail("Telephony SMS input changed during complete read");
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
            "Telephony SMS complete input differs: {}",
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
        return fail("Telephony SMS original changed after binding");
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
        return fail("Telephony SMS original was replaced before reading its body");
    }
    let cap = reference
        .bytes
        .checked_add(1)
        .ok_or("Telephony SMS body bound overflow")?;
    let mut body = Vec::new();
    (&mut file).take(cap).read_to_end(&mut body)?;
    if body.len() as u64 != reference.bytes
        || hex::encode(Sha256::digest(&body)) != reference.sha256
        || identity(&file.metadata()?)? != reference.identity
        || identity(&fs::symlink_metadata(&reference.path)?)? != reference.identity
    {
        return fail("Telephony SMS original body changed during bounded read");
    }
    ordinary_parent(&reference.path)?;
    Ok(body)
}

pub(super) fn required_for_targets(targets: &[&str]) -> bool {
    targets.contains(&"telephony-common")
}

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if !request.complete_delivery()
        || !request.uses_production_full_source()
        || request.source_mode() != SoongDependencyMode::Strict
        || ["telephony-common", "module-info"].iter().any(|required| {
            request
                .requested_targets()
                .iter()
                .filter(|actual| *actual == required)
                .count()
                != 1
        })
    {
        return fail(
            "Telephony SMS repair requires the existing complete-product builder, strict complete source and the normal telephony-common target with module-info",
        );
    }
    Ok(())
}

pub(super) fn validate_source_lock(repo: &Path, lock_path: &Path) -> Result<()> {
    if lock_path != repo.join(production_source::LOCK_PATH) {
        return fail("Telephony SMS repair requires the unchanged production source lock");
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
        || rows[0].name != "platform/frameworks/opt/telephony"
        || rows[0].commit != PROJECT_PIN
    {
        return fail("Telephony SMS source lock has a foreign or ambiguous provider revision");
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
    original_test: FileRef,
    original_blueprints: Vec<FileRef>,
    original_providers: Vec<Option<FileRef>>,
    provider_recipes: Vec<FileRef>,
    patch: FileRef,
}

fn originals(repo: &Path, source: &Path) -> Result<Projected> {
    let original_java = exact(
        &source.join(PROJECT).join(JAVA),
        ORIGINAL_BYTES,
        ORIGINAL_SHA,
    )?;
    let original_test = exact(
        &source.join(PROJECT).join(TEST),
        ORIGINAL_TEST_BYTES,
        ORIGINAL_TEST_SHA,
    )?;
    let mut original_blueprints = Vec::new();
    for (relative, bytes, sha256) in BLUEPRINTS {
        original_blueprints.push(exact(&source.join(PROJECT).join(relative), *bytes, sha256)?);
    }
    let patch = exact(&repo.join(PATCH), PATCH_BYTES, PATCH_SHA)?;
    let mut original_providers = Vec::new();
    let mut provider_recipes = Vec::new();
    for provider in PROVIDERS {
        let input = exact(
            &repo.join(provider.recipe),
            provider.bytes.len() as u64,
            provider.sha256,
        )?;
        if bound_body(&input)? != provider.bytes {
            return fail("Telephony SMS compiled provider differs from the original recipe file");
        }
        provider_recipes.push(input);
        original_providers.push(optional_provider(source, provider)?);
    }
    Ok(Projected {
        original_java,
        original_test,
        original_blueprints,
        original_providers,
        provider_recipes,
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
        return fail("Telephony SMS original is not uniquely journaled");
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
                .ok_or("Telephony SMS original bytes are absent from journal")?;
            let modified =
                std::time::UNIX_EPOCH + std::time::Duration::from_nanos(original.identity[7]);
            if bytes.len() as u64 != original.bytes
                || hex::encode(Sha256::digest(bytes)) != original.sha256
                || row.modified != Some(modified)
                || row.permissions_mode.map(u64::from) != Some(original.identity[2])
            {
                return fail(
                    "Telephony SMS journal does not preserve its actual original bytes, mode and time",
                );
            }
            Ok(())
        }
        _ => fail("Telephony SMS original absence is not preserved by the journal"),
    }
}

pub(super) fn project(
    projection: &mut Projection,
    repo: &Path,
    source: &Path,
) -> Result<Projected> {
    let before = originals(repo, source)?;
    let paths: Vec<_> = [
        before.original_java.path.clone(),
        before.original_test.path.clone(),
    ]
    .into_iter()
    .chain(
        PROVIDERS
            .iter()
            .map(|provider| source.join(PROJECT).join(provider.relative)),
    )
    .collect();
    projection.save_many(&paths)?;
    for original in [&before.original_java, &before.original_test] {
        check_journal(projection, &original.path, Some(original))?;
    }
    for (provider, original) in PROVIDERS.iter().zip(&before.original_providers) {
        check_journal(
            projection,
            &source.join(PROJECT).join(provider.relative),
            original.as_ref(),
        )?;
    }
    // All five original states are durably recorded before any source write.
    recheck(&before.original_java)?;
    recheck(&before.original_test)?;
    recheck(&before.patch)?;
    for original in &before.original_blueprints {
        recheck(original)?;
    }
    for recipe in &before.provider_recipes {
        recheck(recipe)?;
    }
    for (provider, original) in PROVIDERS.iter().zip(&before.original_providers) {
        match original {
            Some(reference) => recheck(reference)?,
            None if optional_provider(source, provider)?.is_none() => (),
            None => {
                return fail("Telephony SMS supplemental provider appeared after journal capture");
            }
        }
    }
    for (provider, original) in PROVIDERS.iter().zip(&before.original_providers) {
        let path = source.join(PROJECT).join(provider.relative);
        match original {
            Some(reference) => recheck(reference)?,
            None => {
                if optional_provider(source, provider)?.is_some() {
                    return fail("Telephony SMS supplemental provider appeared before projection");
                }
                projection.put(&path, provider.bytes)?;
            }
        }
        exact(&path, provider.bytes.len() as u64, provider.sha256)?;
    }
    projection.patch(source, PROJECT, &before.patch.path)?;
    exact(&source.join(PROJECT).join(JAVA), FIXED_BYTES, FIXED_SHA)?;
    exact(
        &source.join(PROJECT).join(TEST),
        FIXED_TEST_BYTES,
        FIXED_TEST_SHA,
    )?;
    for original in &before.original_blueprints {
        recheck(original)?;
    }
    recheck(&before.patch)?;
    for recipe in &before.provider_recipes {
        recheck(recipe)?;
    }
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
    // No telephony feature flag, signing input, or source release is overridden.
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
    let fixed_test = exact(
        &source.join(PROJECT).join(TEST),
        FIXED_TEST_BYTES,
        FIXED_TEST_SHA,
    )?;
    for original in [&before.original_java, &before.original_test] {
        check_journal(projection, &original.path, Some(original))?;
    }
    recheck(&before.patch)?;
    for original in &before.original_blueprints {
        recheck(original)?;
    }
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
    for recipe in &before.provider_recipes {
        recheck(recipe)?;
    }
    let requested_targets: Vec<_> = request
        .requested_targets()
        .iter()
        .map(|s| (*s).to_owned())
        .collect();
    let value = json!({
        "schema": "droidloom-telephony-sms-asb-security-inputs-v1",
        "CVE_rows": [CVE],
        "source_lock": lock,
        "source_project": PROJECT,
        "source_project_revision": PROJECT_PIN,
        "source_release": PRODUCTION_TARGET_RELEASE,
        "build_variant": PRODUCTION_BUILD_VARIANT,
        "original_java": before.original_java,
        "effective_java": fixed,
        "original_test": before.original_test,
        "effective_test": fixed_test,
        "original_java_git_blob": "4e7677e5f9c16268751eb91046f0510a1c45946d",
        "fixed_java_git_blob": "5b1b83d80cd8ef614f55d5e9977f83254278ed18",
        "original_test_git_blob": "1e1e43f34d90fac6f82d95222dec3fbb28da0f74",
        "fixed_test_git_blob": "56a9cbaae5ed3a5a63c3d8ca52c6de33ba4431f6",
        "original_blueprints": before.original_blueprints,
        "official_complete_patch": before.patch,
        "official_patch_commit": "16a5582a886409268005f8e78710cbda7ffd6552",
        "additional_original_provider_inputs": providers,
        "additional_provider_recipes": before.provider_recipes,
        "additional_inputs_in_original_sparse_lock": false,
        "original_source_lock_changed": false,
        "requested_targets": requested_targets,
        "product": product,
        "effective_projection": projection.effective_inventory(repo, source)?,
        "required_normal_modules": ["telephony-common"],
        "required_system_image_member": "framework/telephony-common.jar",
        "strict_allow_missing_dependencies": "false",
        "selinux_ignore_neverallows": "false",
        "telephony_feature_flags_overridden": false,
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
        return fail("Telephony SMS original mode/owner/link count/length/mtime was not restored");
    }
    Ok(actual)
}

fn completed_artifacts(out: &Path, product: &str) -> Result<(FileRef, FileRef)> {
    let root = out.join("target/product").join(product);
    let info = pin(&root.join("module-info.json"), MAX_JSON)?;
    let value: Value = serde_json::from_slice(&bound_body(&info)?)?;
    if value.get("telephony-common").is_none()
        || value["telephony-common"]["path"] != json!([PROJECT])
    {
        return fail("normal Telephony SMS module has a foreign or ambiguous source provider");
    }
    let paths = value["telephony-common"]["installed"]
        .as_array()
        .ok_or("normal Telephony SMS installed paths are missing")?;
    let expected = root.join("system/framework/telephony-common.jar");
    let mut seen = std::collections::BTreeSet::new();
    let mut selected = None;
    for value in paths {
        let text = value
            .as_str()
            .ok_or("Telephony SMS installed path is not a string")?;
        let path = Path::new(text);
        if !path.is_absolute()
            || text
                .split('/')
                .skip(1)
                .any(|part| part.is_empty() || part == "." || part == "..")
            || !seen.insert(path.to_owned())
        {
            return fail("Telephony SMS installed path is aliased or duplicated");
        }
        if path == expected.as_path() && selected.replace(path.to_owned()).is_some() {
            return fail("normal Telephony SMS JAR is ambiguous");
        }
    }
    let path =
        selected.ok_or("normal Telephony SMS JAR is not installed in the system partition")?;
    let jar = pin(&path, MAX_JAR)?;
    if jar.bytes == 0 {
        return fail("normal Telephony SMS JAR is empty");
    }
    recheck(&info)?;
    Ok((info, jar))
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
        || input.before.original_test.path != source.join(PROJECT).join(TEST)
        || input
            .requested_targets
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>()
            != request.requested_targets()
    {
        return fail(
            "Telephony SMS normal completion does not belong to its actual source/request",
        );
    }
    recheck(&input.reference)?;
    recheck(&input.lock)?;
    recheck(&input.before.patch)?;
    for recipe in &input.before.provider_recipes {
        recheck(recipe)?;
    }
    let java = restored(&input.before.original_java)?;
    let test = restored(&input.before.original_test)?;
    for original in &input.before.original_blueprints {
        recheck(original)?;
    }
    let mut providers = Vec::new();
    for (provider, original) in PROVIDERS.iter().zip(&input.before.original_providers) {
        let actual = match original {
            Some(reference) => Some(restored(reference)?),
            None => {
                if optional_provider(source, provider)?.is_some() {
                    return fail(
                        "Telephony SMS originally absent provider was not removed by restoration",
                    );
                }
                None
            }
        };
        providers.push(json!({
            "project_relative_path": provider.relative,
            "restored": actual,
            "originally_absent": original.is_none(),
        }));
    }
    let (module_info, jar) = completed_artifacts(out, product)?;
    recheck(&input.reference)?;
    recheck(&input.lock)?;
    let value = json!({
        "schema": "droidloom-telephony-sms-asb-security-normal-result-v1",
        "CVE_rows": [CVE],
        "inputs": input.reference,
        "requested_targets": input.requested_targets,
        "product": product,
        "normal_command_returned_success": true,
        "module_info": module_info,
        "JAR": jar,
        "source_project_revision": PROJECT_PIN,
        "source_release": PRODUCTION_TARGET_RELEASE,
        "build_variant": PRODUCTION_BUILD_VARIANT,
        "restored_java": java,
        "restored_test": test,
        "unchanged_blueprints": input.before.original_blueprints,
        "restored_supplemental_providers": providers,
        "original_source_bytes_mode_mtime_and_absence_restored": true,
        "source_inode_or_ctime_restoration_claim": false,
        "strict_allow_missing_dependencies": "false",
        "selinux_ignore_neverallows": "false",
        "telephony_feature_flags_overridden": false,
        "QPR1_source_identity_claim": false,
        "system_image_JAR_verification_required_by_complete_normal": true,
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
#[path = "telephony_sms_asb_security_tests.rs"]
mod tests;
