//! Exact official Profiling source repair on the existing complete-source builder.
//! A successful build record does not qualify the resulting DEX, signing or runtime.
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

const PROJECT: &str = "packages/modules/Profiling";
const PROJECT_PIN: &str = "8b3abe8eebc0e97890977d9658038f4966aa7df6";
const CVE: &str = "CVE-2026-59016";
const JAVA: &str = "service/java/com/android/os/profiling/ProfilingService.java";
const ORIGINAL_BYTES: u64 = 189294;
const ORIGINAL_SHA: &str = "3ff227876f069da4b56b778b4d54d96e296115c9931409eab56faed90095caf7";
const FIXED_BYTES: u64 = 190650;
const FIXED_SHA: &str = "7b896a55aeed2ccba7b5bd9cc9abff5b516a51b53d87df907096f298aa027dca";
const PATCH: &str = "android/security/profiling-asb/a7abbb79d9a30d6efe687c84407dae7a8d6dae67.patch";
const PATCH_BYTES: u64 = 2107;
const PATCH_SHA: &str = "574e027a0f580a4e6f629c22c45eff1a6ba2a00c00757e04aa243a93ed484407";
const INPUTS: &str = "droidloom-profiling-asb-security-inputs.json";
const NORMAL: &str = "droidloom-profiling-asb-security-normal-result.json";
const MAX_JSON: u64 = 64 * 1024 * 1024;
const MAX_APEX: u64 = 1024 * 1024 * 1024;
const BLUEPRINTS: &[(&str, u64, &str)] = &[
    (
        "service/Android.bp",
        2574,
        "257f66a0138ac5754037e047d3eacefffdc862d15540c57661c5b22b559309ca",
    ),
    (
        "apex/Android.bp",
        3308,
        "9dc6ff30f147abdb4e5fb885aeddd7410cf22ede9405dc92a5a1694cb8ec6182",
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
        return fail("Profiling inputs require an absolute original path");
    }
    for parent in path.ancestors().skip(1) {
        let meta = fs::symlink_metadata(parent)?;
        if !meta.is_dir() || meta.file_type().is_symlink() {
            return fail("Profiling input parent is not an original directory");
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
        return fail("Profiling input must be a bounded single-link regular file");
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
            .ok_or("Profiling input length overflow")?;
        if total > before.len() {
            return fail("Profiling input grew while hashing");
        }
        state.update(&buffer[..n]);
    }
    if total != before.len()
        || identity(&file.metadata()?)? != expected
        || identity(&fs::symlink_metadata(path)?)? != expected
    {
        return fail("Profiling input changed during complete read");
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
            "Profiling complete input differs: {}",
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
        return fail("Profiling original changed after binding");
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
        return fail("Profiling original was replaced before reading its body");
    }
    let cap = reference
        .bytes
        .checked_add(1)
        .ok_or("Profiling body bound overflow")?;
    let mut body = Vec::new();
    (&mut file).take(cap).read_to_end(&mut body)?;
    if body.len() as u64 != reference.bytes
        || hex::encode(Sha256::digest(&body)) != reference.sha256
        || identity(&file.metadata()?)? != reference.identity
        || identity(&fs::symlink_metadata(&reference.path)?)? != reference.identity
    {
        return fail("Profiling original body changed during bounded read");
    }
    ordinary_parent(&reference.path)?;
    Ok(body)
}

pub(super) fn required_for_targets(targets: &[&str]) -> bool {
    targets
        .iter()
        .any(|name| matches!(*name, "com.android.profiling" | "service-profiling"))
}

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if !request.complete_delivery()
        || !request.uses_production_full_source()
        || request.source_mode() != SoongDependencyMode::Strict
        || ["com.android.profiling", "service-profiling", "module-info"]
            .iter()
            .any(|required| {
                request
                    .requested_targets()
                    .iter()
                    .filter(|actual| *actual == required)
                    .count()
                    != 1
            })
    {
        return fail(
            "Profiling repair requires the existing complete-product builder, strict complete source and both normal Profiling targets with module-info",
        );
    }
    Ok(())
}

pub(super) fn validate_source_lock(repo: &Path, lock_path: &Path) -> Result<()> {
    if lock_path != repo.join(production_source::LOCK_PATH) {
        return fail("Profiling repair requires the unchanged production source lock");
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
        || rows[0].name != "platform/packages/modules/Profiling"
        || rows[0].commit != PROJECT_PIN
    {
        return fail("Profiling source lock has a foreign or ambiguous provider revision");
    }
    recheck(&reference)
}

pub(super) struct Projected {
    original_java: FileRef,
    original_blueprints: Vec<FileRef>,
    patch: FileRef,
}

fn originals(repo: &Path, source: &Path) -> Result<Projected> {
    let original_java = exact(
        &source.join(PROJECT).join(JAVA),
        ORIGINAL_BYTES,
        ORIGINAL_SHA,
    )?;
    let mut original_blueprints = Vec::new();
    for (relative, bytes, sha256) in BLUEPRINTS {
        original_blueprints.push(exact(&source.join(PROJECT).join(relative), *bytes, sha256)?);
    }
    let patch = exact(&repo.join(PATCH), PATCH_BYTES, PATCH_SHA)?;
    Ok(Projected {
        original_java,
        original_blueprints,
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
        return fail("Profiling original is not uniquely journaled");
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
                .ok_or("Profiling original bytes are absent from journal")?;
            let modified =
                std::time::UNIX_EPOCH + std::time::Duration::from_nanos(original.identity[7]);
            if bytes.len() as u64 != original.bytes
                || hex::encode(Sha256::digest(bytes)) != original.sha256
                || row.modified != Some(modified)
                || row.permissions_mode.map(u64::from) != Some(original.identity[2])
            {
                return fail(
                    "Profiling journal does not preserve its actual original bytes, mode and time",
                );
            }
            Ok(())
        }
        _ => fail("Profiling original absence is not preserved by the journal"),
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
    for original in &before.original_blueprints {
        recheck(original)?;
    }
    projection.patch(source, PROJECT, &before.patch.path)?;
    exact(&source.join(PROJECT).join(JAVA), FIXED_BYTES, FIXED_SHA)?;
    for original in &before.original_blueprints {
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
    // No Profiling/anomaly release flag, signing input, or source release is overridden.
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
    for original in &before.original_blueprints {
        recheck(original)?;
    }
    let requested_targets: Vec<_> = request
        .requested_targets()
        .iter()
        .map(|s| (*s).to_owned())
        .collect();
    let value = json!({
        "schema": "droidloom-profiling-asb-security-inputs-v1",
        "CVE_rows": [CVE],
        "source_lock": lock,
        "source_project": PROJECT,
        "source_project_revision": PROJECT_PIN,
        "source_release": PRODUCTION_TARGET_RELEASE,
        "build_variant": PRODUCTION_BUILD_VARIANT,
        "original_java": before.original_java,
        "effective_java": fixed,
        "original_java_git_blob": "503e67870c33d5869d9a41a357d76d8c586221a0",
        "fixed_java_git_blob": "411433836a84dc9a0c957581b8df0ac5a1340683",
        "original_blueprints": before.original_blueprints,
        "official_complete_patch": before.patch,
        "official_patch_commit": "a7abbb79d9a30d6efe687c84407dae7a8d6dae67",
        "original_source_lock_changed": false,
        "requested_targets": requested_targets,
        "product": product,
        "effective_projection": projection.effective_inventory(repo, source)?,
        "required_normal_modules": ["com.android.profiling", "service-profiling"],
        "required_APEX_payload_members": crate::coherent_images::PROFILING_APEX_MEMBERS,
        "strict_allow_missing_dependencies": "false",
        "selinux_ignore_neverallows": "false",
        "Profiling_release_flags_overridden": false,
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
        return fail("Profiling original mode/owner/link count/length/mtime was not restored");
    }
    Ok(actual)
}

fn completed_artifacts(out: &Path, product: &str) -> Result<(FileRef, FileRef)> {
    let root = out.join("target/product").join(product);
    let info = pin(&root.join("module-info.json"), MAX_JSON)?;
    let value: Value = serde_json::from_slice(&bound_body(&info)?)?;
    for (module, provider) in [
        ("com.android.profiling", "packages/modules/Profiling/apex"),
        ("service-profiling", "packages/modules/Profiling/service"),
    ] {
        if value.get(module).is_none() || value[module]["path"] != json!([provider]) {
            return fail("normal Profiling module has a foreign or ambiguous source provider");
        }
    }
    let paths = value["com.android.profiling"]["installed"]
        .as_array()
        .ok_or("normal Profiling installed paths are missing")?;
    let allowed = [
        root.join("system/apex/com.android.profiling.apex"),
        root.join("system/apex/com.android.profiling.capex"),
    ];
    let mut seen = std::collections::BTreeSet::new();
    let mut selected = None;
    for value in paths {
        let text = value
            .as_str()
            .ok_or("Profiling installed path is not a string")?;
        let path = Path::new(text);
        if !path.is_absolute()
            || text
                .split('/')
                .skip(1)
                .any(|part| part.is_empty() || part == "." || part == "..")
            || !seen.insert(path.to_owned())
        {
            return fail("Profiling installed path is aliased or duplicated");
        }
        if allowed.iter().any(|expected| path == expected)
            && selected.replace(path.to_owned()).is_some()
        {
            return fail("normal Profiling APEX container is ambiguous");
        }
    }
    let path = selected.ok_or("normal Profiling APEX is not installed in the system partition")?;
    let apex = pin(&path, MAX_APEX)?;
    if apex.bytes == 0 {
        return fail("normal Profiling APEX is empty");
    }
    recheck(&info)?;
    Ok((info, apex))
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
        return fail("Profiling normal completion does not belong to its actual source/request");
    }
    recheck(&input.reference)?;
    recheck(&input.lock)?;
    recheck(&input.before.patch)?;
    let java = restored(&input.before.original_java)?;
    for original in &input.before.original_blueprints {
        recheck(original)?;
    }
    let (module_info, apex) = completed_artifacts(out, product)?;
    recheck(&input.reference)?;
    recheck(&input.lock)?;
    let value = json!({
        "schema": "droidloom-profiling-asb-security-normal-result-v1",
        "CVE_rows": [CVE],
        "inputs": input.reference,
        "requested_targets": input.requested_targets,
        "product": product,
        "normal_command_returned_success": true,
        "module_info": module_info,
        "APEX": apex,
        "source_project_revision": PROJECT_PIN,
        "source_release": PRODUCTION_TARGET_RELEASE,
        "build_variant": PRODUCTION_BUILD_VARIANT,
        "restored_java": java,
        "unchanged_blueprints": input.before.original_blueprints,
        "original_source_bytes_mode_mtime_restored": true,
        "source_inode_or_ctime_restoration_claim": false,
        "strict_allow_missing_dependencies": "false",
        "selinux_ignore_neverallows": "false",
        "Profiling_release_flags_overridden": false,
        "QPR1_source_identity_claim": false,
        "APEX_payload_verification_required_by_complete_normal": true,
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
#[path = "profiling_asb_security_tests.rs"]
mod tests;
