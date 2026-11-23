//! Apply the complete upstream AVB allocation-failure correction to every
//! production651 projection, including transitive libavb consumers. The project
//! revision and Android.bp remain unchanged; projection v2 restores the original
//! body, permissions and nanosecond modification time.
use super::*;
use sha2::{Digest, Sha256};
use std::io::{Read, Seek, SeekFrom};
use std::os::unix::fs::MetadataExt;
use std::os::unix::fs::OpenOptionsExt;

const PROJECT: &str = "external/avb";
const ORIGINAL_PIN: &str = "ba2dec4b035b0a3b61c5f8f8a74d86bcd450b1ee";
const COMMITS: &[&str] = &["2264ece3807d01298a23e5ef3cafa6de3772b994"];
const ALTERNATE_COMMIT: &str = "119d66ea37241def63e715658ac02c414bd3d0e5";
const PATCHES: &[(&str, u64, &str)] = &[(
    "android/security/avb-rsa/2264ece3807d01298a23e5ef3cafa6de3772b994.patch",
    1199,
    "fe9f6e5906f7bba4985036d5848ab7afc3f7cb3c5a0c268fe87036e55bf91edc",
)];
const ORIGINALS: &[(&str, u64, &str)] = &[(
    "libavb/avb_rsa.c",
    33474,
    "cd2d62fe8107bf72632d64d80a95a78c6d93ff4c25ab2b490824c21d21e874d3",
)];
const FIXED: &[(&str, u64, &str)] = &[(
    "libavb/avb_rsa.c",
    33612,
    "1820b82a68e77b70732e50918927bd2bfc37855c6ca7285bdd1b30f425e60151",
)];
const BP: (&str, u64, &str) = (
    "Android.bp",
    11126,
    "c383995eff501f09a7041dab473748c5e05baa6c3fe5b987e8bb3af68c5580d7",
);
const CONSUMER_TARGETS: &[&str] = &["libfs_mgr", "apexd", "module-info"];
const CONSUMER_PROJECTS: &[(&str, &str)] = &[
    (
        "system/fs/fs_mgr",
        "157112fcbaa00b6e84c63146cfde249c56cd652c",
    ),
    ("system/apex", "ce2bb9f710183c864040401d859874b5723e44d8"),
];
const CONSUMER_PROVIDERS: &[(&str, u64, &str)] = &[
    (
        "system/fs/fs_mgr/Android.bp",
        7570,
        "2bbe1b15b003c1a7d8d3d972ffb2f2d688da3250384ffab582972c5dd54286c9",
    ),
    (
        "system/apex/apexd/Android.bp",
        24966,
        "30d2561601d92a0b373061743c8eafab143380f03f023bb1ff4a6921f8dbdc96",
    ),
];
const CONSUMER_OUTPUTS: &[(&str, &str, &str)] = &[
    ("libfs_mgr", "system/fs/fs_mgr", "system/lib64/libfs_mgr.so"),
    ("apexd", "system/apex/apexd", "system/bin/apexd"),
];

fn consumer_pair_requested(request: FixedProductionRequest<'_>) -> bool {
    request
        .requested_targets()
        .iter()
        .any(|target| matches!(*target, "libfs_mgr" | "apexd"))
}

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if !request.uses_production_full_source()
        || request.source_mode() != SoongDependencyMode::Strict
    {
        return fail("AVB security projection requires the complete strict production651 source");
    }
    if consumer_pair_requested(request)
        && CONSUMER_TARGETS.iter().any(|required| {
            request
                .requested_targets()
                .iter()
                .filter(|actual| *actual == required)
                .count()
                != 1
        })
    {
        return fail(
            "AVB consumer output binding requires the actual libfs_mgr, apexd and module-info targets together",
        );
    }
    Ok(())
}

pub(super) fn validate_source_lock(repo: &Path, lock: &Path) -> Result<()> {
    if lock != production_source::source_lock_path(repo)? {
        return fail("AVB security projection lost the original production651 source lock");
    }
    let value: serde_json::Value = serde_json::from_slice(&fs::read(lock)?)?;
    let projects = value["projects"]
        .as_array()
        .ok_or("AVB source projects missing")?;
    let selected: Vec<_> = projects
        .iter()
        .filter(|row| row["path"] == PROJECT)
        .collect();
    if selected.len() != 1 || selected[0]["commit"] != ORIGINAL_PIN {
        return fail("AVB original production project revision differs");
    }
    for (path, commit) in CONSUMER_PROJECTS {
        let selected: Vec<_> = projects.iter().filter(|row| row["path"] == *path).collect();
        if selected.len() != 1 || selected[0]["commit"] != *commit {
            return fail("AVB consumer original project revision differs");
        }
    }
    Ok(())
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

fn original_path(root: &Path, relative: &str) -> Result<PathBuf> {
    if !root.is_absolute() || root.canonicalize()? != root {
        return fail("avb source and recipe roots must be canonical absolute directories");
    }
    let mut path = root.to_path_buf();
    for component in Path::new(relative).components() {
        if !matches!(component, std::path::Component::Normal(_)) {
            return fail("avb input must have only confined relative components");
        }
        path.push(component.as_os_str());
        let meta = fs::symlink_metadata(&path)?;
        if meta.file_type().is_symlink() {
            return fail("avb original input or parent is an alias");
        }
    }
    Ok(path)
}

fn exact(root: &Path, relative: &str, bytes: u64, expected: &str) -> Result<PathBuf> {
    let path = original_path(root, relative)?;
    let before = fs::symlink_metadata(&path)?;
    if !before.is_file()
        || before.nlink() != 1
        || before.mode() & 0o111 != 0
        || before.len() != bytes
        || hash(&path)? != expected
    {
        return fail(format!(
            "avb original or official fixed input differs: {relative}"
        ));
    }
    let after = fs::symlink_metadata(&path)?;
    let identity = |m: &fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.uid(),
            m.gid(),
            m.nlink(),
            m.len(),
            (m.mtime(), m.mtime_nsec()),
            (m.ctime(), m.ctime_nsec()),
        )
    };
    if identity(&before) != identity(&after) {
        return fail("avb input changed during complete verification");
    }
    Ok(path)
}

fn original_bp(source: &Path) -> Result<()> {
    exact(source, &format!("{PROJECT}/{}", BP.0), BP.1, BP.2)?;
    for (relative, bytes, expected) in CONSUMER_PROVIDERS {
        exact(source, relative, *bytes, expected)?;
    }
    Ok(())
}

pub(super) fn validate_original(repo: &Path, source: &Path) -> Result<()> {
    for (relative, bytes, expected) in ORIGINALS {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    original_bp(source)?;
    for (relative, bytes, expected) in PATCHES {
        exact(repo, relative, *bytes, expected)?;
    }
    Ok(())
}

fn validate_fixed(source: &Path) -> Result<()> {
    for (relative, bytes, expected) in FIXED {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    original_bp(source)
}

pub(super) fn project(projection: &mut Projection, repo: &Path, source: &Path) -> Result<()> {
    validate_original(repo, source)?;
    // Capture the complete original body and metadata before the official patch.
    for (relative, _, _) in ORIGINALS {
        projection.save(&source.join(PROJECT).join(relative))?;
    }
    for (relative, _, _) in PATCHES {
        projection.patch(source, PROJECT, &repo.join(relative))?;
    }
    validate_fixed(source)
}

pub(super) fn input_receipt(
    repo: &Path,
    source: &Path,
    lock: &Path,
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
    projection: &Projection,
) -> Result<PathBuf> {
    validate_fixed(source)?;
    validate_request(request, product)?;
    validate_source_lock(repo, lock)?;
    let mut inputs = request.description(product)?;
    let mut patches = Vec::new();
    for (number, (relative, bytes, expected)) in PATCHES.iter().enumerate() {
        let path = exact(repo, relative, *bytes, expected)?;
        patches.push(
            serde_json::json!({"path": path, "bytes": bytes, "sha256": expected,
            "official_commit": COMMITS[number]}),
        );
    }
    let effective: Vec<_> = FIXED.iter().map(|(relative, bytes, expected)|
        serde_json::json!({"path": source.join(PROJECT).join(relative), "bytes": bytes, "sha256": expected})).collect();
    inputs["schema"] = "droidloom-avb-security-inputs-v2".into();
    inputs["CVE"] = "CVE-2026-58956".into();
    inputs["source_lock"] = serde_json::json!({"path": lock, "sha256": hash(lock)?});
    inputs["original_project_pin"] = ORIGINAL_PIN.into();
    inputs["upstream_bug"] = "A-461507723".into();
    inputs["alternate_commit_not_replayed"] = ALTERNATE_COMMIT.into();
    inputs["original_file_equals_official_patch_preimage"] = true.into();
    inputs["official_patches_in_order"] = patches.into();
    inputs["effective_upstream_files"] = effective.into();
    inputs["original_Android_bp_sha256"] = BP.2.into();
    inputs["consumer_pair_requested"] = consumer_pair_requested(request).into();
    inputs["required_consumer_targets"] = serde_json::json!(CONSUMER_TARGETS);
    inputs["required_installed_consumer_modules"] = serde_json::json!(CONSUMER_OUTPUTS);
    inputs["original_consumer_projects"] = serde_json::json!(CONSUMER_PROJECTS);
    inputs["original_consumer_providers"] = serde_json::json!(CONSUMER_PROVIDERS);
    inputs["consumer_output_identity_bound"] = false.into();
    inputs["effective_projection"] = projection.effective_inventory(repo, source)?;
    inputs["strict_allow_missing_dependencies"] = "false".into();
    inputs["selinux_ignore_neverallows"] = "false".into();
    inputs["regression_executed"] = false.into();
    inputs["artifact_identity_qualified"] = false.into();
    inputs["whole_security_bulletin_qualified"] = false.into();
    inputs["binary_semantic_fix_qualified"] = false.into();
    inputs["runtime_qualified"] = false.into();
    inputs["production_ready"] = false.into();
    let path = out.join("droidloom-avb-security-inputs.json");
    write(&path, serde_json::to_vec_pretty(&inputs)?)?;
    Ok(path)
}

pub(super) fn normal_result(
    repo: &Path,
    source: &Path,
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
) -> Result<()> {
    validate_request(request, product)?;
    validate_original(repo, source)?;
    let consumer_pair = consumer_pair_requested(request);
    let artifacts = if consumer_pair {
        completed_consumer_artifacts(out, product)?
    } else {
        Vec::new()
    };
    let input = out.join("droidloom-avb-security-inputs.json");
    write(
        &out.join("droidloom-avb-security-normal-result.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "schema": "droidloom-avb-security-normal-result-v2", "CVE": "CVE-2026-58956",
            "inputs": {"path": input, "sha256": hash(&input)?}, "requested_targets": request.requested_targets(),
            "product": product, "normal_command_returned_success": true,
            "original_source_restored": true, "original_Android_bp_preserved": true,
            "consumer_pair_requested": consumer_pair,
            "consumer_output_identity_bound": consumer_pair,
            "actual_output_files": artifacts,
            "required_consumer_targets": CONSUMER_TARGETS,
            "required_installed_consumer_modules": CONSUMER_OUTPUTS,
            "original_consumer_providers_preserved": true,
            "source_release": PRODUCTION_TARGET_RELEASE, "build_variant": PRODUCTION_BUILD_VARIANT,
            "QPR1_source_identity_claim": false, "artifact_identity_qualified": false,
            "regression_executed": false, "binary_semantic_fix_qualified": false,
            "whole_security_bulletin_qualified": false, "runtime_qualified": false, "production_ready": false,
        }))?,
    )?;
    Ok(())
}

fn output_identity(m: &fs::Metadata) -> (u64, u64, u32, u32, u32, u64, u64, i64, i64, i64, i64) {
    (
        m.dev(),
        m.ino(),
        m.mode(),
        m.uid(),
        m.gid(),
        m.nlink(),
        m.len(),
        m.mtime(),
        m.mtime_nsec(),
        m.ctime(),
        m.ctime_nsec(),
    )
}

fn require_consumer_elf(file: &mut fs::File, bytes: u64, module: &str) -> Result<()> {
    let mut header = [0_u8; 64];
    file.seek(SeekFrom::Start(0))?;
    file.read_exact(&mut header)?;
    let u16_at = |i: usize| u16::from_le_bytes(header[i..i + 2].try_into().unwrap());
    let u32_at = |i: usize| u32::from_le_bytes(header[i..i + 4].try_into().unwrap());
    let u64_at = |i: usize| u64::from_le_bytes(header[i..i + 8].try_into().unwrap());
    let kind = u16_at(16);
    if &header[..7] != b"\x7fELF\x02\x01\x01"
        || u16_at(18) != 62
        || u32_at(20) != 1
        || u16_at(52) != 64
        || !matches!(kind, 2 | 3)
        || (module == "libfs_mgr" && kind != 3)
    {
        return fail("AVB consumer is not the expected x86_64 little-endian ELF64 output");
    }
    let offset = u64_at(32);
    let count = u16_at(56) as u64;
    if u16_at(54) != 56
        || !(1..=1024).contains(&count)
        || offset < 64
        || offset
            .checked_add(count * 56)
            .filter(|end| *end <= bytes)
            .is_none()
    {
        return fail("AVB consumer ELF program headers are truncated or unbounded");
    }
    let mut executable = false;
    for number in 0..count {
        let mut p = [0_u8; 56];
        file.seek(SeekFrom::Start(offset + number * 56))?;
        file.read_exact(&mut p)?;
        let kind = u32::from_le_bytes(p[..4].try_into().unwrap());
        let flags = u32::from_le_bytes(p[4..8].try_into().unwrap());
        let start = u64::from_le_bytes(p[8..16].try_into().unwrap());
        let length = u64::from_le_bytes(p[32..40].try_into().unwrap());
        let memory = u64::from_le_bytes(p[40..48].try_into().unwrap());
        if kind == 1 {
            if length > memory
                || start
                    .checked_add(length)
                    .filter(|end| *end <= bytes)
                    .is_none()
            {
                return fail("AVB consumer ELF load segment escapes its actual file");
            }
            executable |= flags & 1 != 0 && length != 0;
        }
    }
    if !executable {
        return fail("AVB consumer ELF lacks a file-backed executable load segment");
    }
    Ok(())
}

fn output_file(out: &Path, path: &Path, elf_module: Option<&str>) -> Result<serde_json::Value> {
    let relative = path
        .strip_prefix(out)
        .map_err(|_| "AVB output escaped its owned output root")?;
    let text = relative.to_str().ok_or("AVB output is not UTF-8")?;
    let path = original_path(out, text)?;
    let before = fs::symlink_metadata(&path)?;
    let limit = if elf_module.is_some() {
        256 * 1024 * 1024_u64
    } else {
        128 * 1024 * 1024_u64
    };
    if !before.is_file() || before.nlink() != 1 || before.len() == 0 || before.len() > limit {
        return fail("AVB output is not a bounded nonempty single-link regular file");
    }
    let mut file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&path)?;
    if output_identity(&file.metadata()?) != output_identity(&before) {
        return fail("AVB output changed while opening the original inode");
    }
    if let Some(module) = elf_module {
        require_consumer_elf(&mut file, before.len(), module)?;
    }
    file.seek(SeekFrom::Start(0))?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 65536];
    let mut observed = 0_u64;
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        observed = observed
            .checked_add(count as u64)
            .ok_or("AVB output size overflow")?;
        if observed > before.len() {
            return fail("AVB output grew during whole-file hashing");
        }
        digest.update(&buffer[..count]);
    }
    let after = file.metadata()?;
    let named = original_path(out, text)?;
    if observed != before.len()
        || output_identity(&before) != output_identity(&after)
        || output_identity(&fs::symlink_metadata(named)?) != output_identity(&after)
    {
        return fail("AVB output changed during whole-file hashing or pathname revalidation");
    }
    Ok(
        serde_json::json!({"path": path, "bytes": after.len(), "sha256": format!("{:x}", digest.finalize()),
        "device": after.dev(), "inode": after.ino(), "mode": after.mode(), "uid": after.uid(),
        "gid": after.gid(), "nlink": after.nlink(), "mtime_seconds": after.mtime(),
        "mtime_nanoseconds": after.mtime_nsec(), "ctime_seconds": after.ctime(),
        "ctime_nanoseconds": after.ctime_nsec(), "ELF64_x86_64_checked": elf_module.is_some()}),
    )
}

fn completed_consumer_artifacts(out: &Path, product: &str) -> Result<Vec<serde_json::Value>> {
    if product != "droidloom_x86_64" {
        return fail("AVB output product differs from the fixed request");
    }
    let product_out = out.join("target/product").join(product);
    let info_path = product_out.join("module-info.json");
    let info_ref = output_file(out, &info_path, None)?;
    let mut bytes = Vec::new();
    fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&info_path)?
        .take(128 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 128 * 1024 * 1024 {
        return fail("AVB module metadata exceeded its bounded reader");
    }
    if Some(bytes.len() as u64) != info_ref["bytes"].as_u64()
        || format!("{:x}", Sha256::digest(&bytes))
            != info_ref["sha256"]
                .as_str()
                .ok_or("AVB module metadata hash missing")?
    {
        return fail("AVB parsed module metadata differs from the complete original body");
    }
    let info: serde_json::Value = serde_json::from_slice(&bytes)?;
    let mut outputs = Vec::new();
    for (module, provider, relative) in CONSUMER_OUTPUTS {
        let row = info
            .get(*module)
            .ok_or("AVB consumer module is absent from this output's metadata")?;
        let providers = row["path"]
            .as_array()
            .ok_or("AVB consumer source provider metadata is missing")?;
        if providers.len() != 1 || providers[0].as_str() != Some(*provider) {
            return fail("AVB consumer has a different or ambiguous original source provider");
        }
        let installed = row["installed"]
            .as_array()
            .ok_or("AVB consumer has no installed output metadata")?;
        if installed.is_empty() || installed.len() > 128 {
            return fail("AVB installed output metadata is unbounded");
        }
        let expected = product_out.join(relative);
        let mut names = std::collections::BTreeSet::new();
        let mut selected = 0;
        for value in installed {
            let name = value
                .as_str()
                .ok_or("AVB installed output path is not a string")?;
            let path = Path::new(name);
            if !names.insert(name)
                || !path.is_absolute()
                || !path.starts_with(&product_out)
                || name
                    .split('/')
                    .skip(1)
                    .any(|part| matches!(part, "" | "." | ".."))
            {
                return fail(
                    "AVB installed metadata escaped its product output or repeated a path",
                );
            }
            selected += usize::from(path == expected);
        }
        if selected != 1 {
            return fail("AVB consumer lacks its exact installed output path");
        }
        outputs.push(serde_json::json!({"module": module, "provider": provider,
            "artifact": output_file(out, &expected, Some(*module))?}));
    }
    let mut identities = std::collections::BTreeSet::new();
    for (output, (module, _, relative)) in outputs.iter().zip(CONSUMER_OUTPUTS) {
        let artifact = &output["artifact"];
        let identity = (
            artifact["device"]
                .as_u64()
                .ok_or("AVB artifact device missing")?,
            artifact["inode"]
                .as_u64()
                .ok_or("AVB artifact inode missing")?,
        );
        if !identities.insert(identity)
            || output_file(out, &product_out.join(relative), Some(*module))? != *artifact
        {
            return fail("AVB consumer output set is aliased or changed during complete binding");
        }
    }
    if output_file(out, &info_path, None)? != info_ref {
        return fail("AVB module metadata changed while binding the two actual consumers");
    }
    outputs.push(serde_json::json!({"module_info": info_ref}));
    Ok(outputs)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{PermissionsExt, symlink};

    fn fixture(root: &Path) -> (PathBuf, PathBuf) {
        let repo = root.join("recipe");
        let source = root.join("source");
        write(
            &source.join(PROJECT).join(ORIGINALS[0].0),
            include_bytes!("../../../android/security/avb-rsa/fixtures/libavb/avb_rsa.c"),
        )
        .unwrap();
        write(
            &source.join(PROJECT).join(BP.0),
            include_bytes!("../../../android/security/avb-rsa/fixtures/Android.bp"),
        )
        .unwrap();
        write(
            &repo.join(PATCHES[0].0),
            include_bytes!(
                "../../../android/security/avb-rsa/2264ece3807d01298a23e5ef3cafa6de3772b994.patch"
            ),
        )
        .unwrap();
        for (relative, bytes) in [
            (
                "system/fs/fs_mgr/Android.bp",
                include_bytes!(
                    "../../../android/security/avb-rsa/fixtures/system/fs/fs_mgr/Android.bp"
                )
                .as_slice(),
            ),
            (
                "system/apex/apexd/Android.bp",
                include_bytes!(
                    "../../../android/security/avb-rsa/fixtures/system/apex/apexd/Android.bp"
                )
                .as_slice(),
            ),
        ] {
            write(&source.join(relative), bytes).unwrap();
        }
        (repo, source)
    }

    fn unchanged_file_identity(
        path: &Path,
    ) -> (u64, u64, u32, u32, u32, u64, u64, i64, i64, i64, i64) {
        let m = fs::symlink_metadata(path).unwrap();
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.uid(),
            m.gid(),
            m.nlink(),
            m.len(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
        )
    }

    #[test]
    fn avb_consumer_pair_requires_actual_targets_and_original_providers() {
        let product = "droidloom_x86_64";
        let full =
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, crate::android::TARGETS);
        validate_request(full, product).unwrap();
        assert!(consumer_pair_requested(full));
        for request in [
            FixedProductionRequest::VendorImageOnProductionSource,
            FixedProductionRequest::WmSecurityOnProductionSource,
            FixedProductionRequest::FrameworkAsbOnProductionSource,
        ] {
            validate_request(request, product).unwrap();
            assert!(!consumer_pair_requested(request));
        }
        for targets in [
            &["libfs_mgr"][..],
            &["apexd"],
            &["libfs_mgr", "apexd"],
            &["libfs_mgr", "apexd", "module-info", "apexd"],
        ] {
            assert!(
                validate_request(
                    FixedProductionRequest::Existing(SoongDependencyMode::Strict, targets),
                    product
                )
                .is_err()
            );
        }
        for (relative, _, _) in CONSUMER_PROVIDERS {
            let directory = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(directory.path());
            validate_original(&repo, &source).unwrap();
            let path = source.join(relative);
            let mut bytes = fs::read(&path).unwrap();
            bytes.push(b'\n');
            fs::write(&path, &bytes).unwrap();
            let journal = directory.path().join("projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            assert!(project(&mut projection, &repo, &source).is_err());
            assert!(projection.originals.is_empty());
            assert!(!journal.exists());
            assert_eq!(fs::read(path).unwrap(), bytes);
        }
    }

    // Synthetic format fixtures are never executed and do not represent a
    // compiled AVB fix. They exercise only the real file/metadata reader.
    fn consumer_elf_fixture(marker: u8) -> Vec<u8> {
        let mut bytes = vec![0_u8; 128];
        bytes[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
        bytes[16..18].copy_from_slice(&3_u16.to_le_bytes());
        bytes[18..20].copy_from_slice(&62_u16.to_le_bytes());
        bytes[20..24].copy_from_slice(&1_u32.to_le_bytes());
        bytes[32..40].copy_from_slice(&64_u64.to_le_bytes());
        bytes[52..54].copy_from_slice(&64_u16.to_le_bytes());
        bytes[54..56].copy_from_slice(&56_u16.to_le_bytes());
        bytes[56..58].copy_from_slice(&1_u16.to_le_bytes());
        bytes[64..68].copy_from_slice(&1_u32.to_le_bytes());
        bytes[68..72].copy_from_slice(&5_u32.to_le_bytes());
        bytes[96..104].copy_from_slice(&128_u64.to_le_bytes());
        bytes[104..112].copy_from_slice(&128_u64.to_le_bytes());
        bytes[127] = marker;
        bytes
    }

    fn consumer_output_fixture(out: &Path, product: &str) -> serde_json::Value {
        let product_out = out.join("target/product").join(product);
        let mut info = serde_json::json!({});
        for (number, (module, provider, relative)) in CONSUMER_OUTPUTS.iter().enumerate() {
            let path = product_out.join(relative);
            write(&path, consumer_elf_fixture(number as u8)).unwrap();
            info[*module] = serde_json::json!({"path": [provider], "installed": [path]});
        }
        write(
            &product_out.join("module-info.json"),
            serde_json::to_vec(&info).unwrap(),
        )
        .unwrap();
        info
    }

    #[test]
    fn avb_actual_output_binding_rejects_wrong_provider_path_alias_and_elf() {
        let directory = tempfile::tempdir().unwrap();
        let out = directory.path().canonicalize().unwrap();
        let product = "droidloom_x86_64";
        let product_out = out.join("target/product").join(product);
        let info_path = product_out.join("module-info.json");
        let info = consumer_output_fixture(&out, product);
        let outputs = completed_consumer_artifacts(&out, product).unwrap();
        assert_eq!(outputs.len(), 3);
        for (number, (module, provider, relative)) in CONSUMER_OUTPUTS.iter().enumerate() {
            assert_eq!(outputs[number]["module"], *module);
            assert_eq!(outputs[number]["provider"], *provider);
            assert_eq!(
                outputs[number]["artifact"]["sha256"],
                hash(&product_out.join(relative)).unwrap()
            );
            assert_eq!(outputs[number]["artifact"]["ELF64_x86_64_checked"], true);
        }
        assert_ne!(
            outputs[0]["artifact"]["inode"],
            outputs[1]["artifact"]["inode"]
        );
        for mutation in 0..8 {
            let mut bad = info.clone();
            match mutation {
                0 => {
                    bad.as_object_mut().unwrap().remove("apexd");
                }
                1 => {
                    bad["libfs_mgr"]["path"] = serde_json::json!(["system/core/fs_mgr"]);
                }
                2 => {
                    bad["apexd"]["path"] =
                        serde_json::json!(["system/apex/apexd", "foreign/provider"]);
                }
                3 => {
                    bad["apexd"]["installed"] =
                        serde_json::json!([product_out.join("system/bin/apexd.microdroid")]);
                }
                4 => {
                    bad["libfs_mgr"]["installed"] = serde_json::json!([
                        out.join("target/product/foreign/system/lib64/libfs_mgr.so")
                    ]);
                }
                5 => {
                    let original = bad["libfs_mgr"]["installed"][0].clone();
                    bad["libfs_mgr"]["installed"] = serde_json::json!([original.clone(), original]);
                }
                6 => {
                    bad["libfs_mgr"]["installed"] =
                        serde_json::json!(["system/lib64/libfs_mgr.so"]);
                }
                _ => {
                    bad["apexd"]["installed"] =
                        serde_json::json!([product_out.join("system/bin/../bin/apexd")]);
                }
            }
            write(&info_path, serde_json::to_vec(&bad).unwrap()).unwrap();
            assert!(
                completed_consumer_artifacts(&out, product).is_err(),
                "metadata mutation {mutation}"
            );
        }
        // Other explicitly named product variants cannot substitute for the
        // exact system consumer; they also need not be executed or collected.
        let mut variants = info.clone();
        variants["libfs_mgr"]["installed"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!(
                product_out.join("recovery/root/system/lib64/libfs_mgr.so")
            ));
        write(&info_path, serde_json::to_vec(&variants).unwrap()).unwrap();
        completed_consumer_artifacts(&out, product).unwrap();
        variants["libfs_mgr"]["installed"]
            .as_array_mut()
            .unwrap()
            .remove(0);
        write(&info_path, serde_json::to_vec(&variants).unwrap()).unwrap();
        assert!(completed_consumer_artifacts(&out, product).is_err());
        write(&info_path, serde_json::to_vec(&info).unwrap()).unwrap();
        for (number, (_, _, relative)) in CONSUMER_OUTPUTS.iter().enumerate() {
            let path = product_out.join(relative);
            let original = consumer_elf_fixture(number as u8);
            for mutation in 0..5 {
                let mut bad = original.clone();
                match mutation {
                    0 => {
                        bad.truncate(63);
                    }
                    1 => {
                        bad[18..20].copy_from_slice(&183_u16.to_le_bytes());
                    }
                    2 => {
                        bad[68..72].copy_from_slice(&4_u32.to_le_bytes());
                    }
                    3 => {
                        bad[32..40].copy_from_slice(&u64::MAX.to_le_bytes());
                    }
                    _ => {
                        bad[96..104].copy_from_slice(&129_u64.to_le_bytes());
                    }
                }
                write(&path, &bad).unwrap();
                assert!(
                    completed_consumer_artifacts(&out, product).is_err(),
                    "ELF mutation {mutation}"
                );
            }
            write(&path, &original).unwrap();
            let saved = out.join(format!("saved-{number}"));
            fs::rename(&path, &saved).unwrap();
            assert!(completed_consumer_artifacts(&out, product).is_err());
            symlink(&saved, &path).unwrap();
            assert!(completed_consumer_artifacts(&out, product).is_err());
            fs::remove_file(&path).unwrap();
            fs::hard_link(&saved, &path).unwrap();
            assert!(completed_consumer_artifacts(&out, product).is_err());
            fs::remove_file(&path).unwrap();
            fs::rename(&saved, &path).unwrap();
            completed_consumer_artifacts(&out, product).unwrap();
        }
        let lib_parent = product_out.join("system/lib64");
        let saved_parent = out.join("saved-lib64");
        fs::rename(&lib_parent, &saved_parent).unwrap();
        symlink(&saved_parent, &lib_parent).unwrap();
        assert!(completed_consumer_artifacts(&out, product).is_err());
        fs::remove_file(&lib_parent).unwrap();
        fs::rename(saved_parent, lib_parent).unwrap();
        completed_consumer_artifacts(&out, product).unwrap();
    }

    #[test]
    fn avb_official_projection_restores_single_original_after_save_and_apply() {
        // Cover a durable save before any patch, ordinary successful restore,
        // and recovery after the official patch completed but its owner was lost.
        for stage in 0..3 {
            let d = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(d.path());
            let original = source.join(PROJECT).join(ORIGINALS[0].0);
            let bp = source.join(PROJECT).join(BP.0);
            let patch = repo.join(PATCHES[0].0);
            fs::set_permissions(&original, fs::Permissions::from_mode(0o640)).unwrap();
            let modified =
                std::time::UNIX_EPOCH + std::time::Duration::new(1_700_000_123, 987_654_321);
            fs::File::open(&original)
                .unwrap()
                .set_modified(modified)
                .unwrap();
            let original_bytes = fs::read(&original).unwrap();
            let original_mode = fs::metadata(&original).unwrap().mode();
            let preserved =
                [&bp, &patch].map(|p| (fs::read(p).unwrap(), unchanged_file_identity(p)));
            let journal = d.path().join("source-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            if stage == 0 {
                validate_original(&repo, &source).unwrap();
                projection.save(&original).unwrap();
                assert!(projection.applied_patches.is_empty());
            } else {
                project(&mut projection, &repo, &source).unwrap();
                validate_fixed(&source).unwrap();
                assert_eq!(projection.applied_patches.len(), 1);
                assert_eq!(
                    projection.applied_patches.get(&patch).unwrap(),
                    PATCHES[0].2
                );
                assert_ne!(fs::read(&original).unwrap(), original_bytes);
            }
            assert_eq!(projection.originals.len(), 1);
            assert_eq!(projection.originals[0].path, original);
            let saved = decode_projection_journal(&fs::read(&journal).unwrap(), &source).unwrap();
            assert_eq!(saved.len(), 1);
            assert_eq!(saved[0].bytes.as_ref().unwrap(), &original_bytes);
            assert_eq!(saved[0].permissions_mode, Some(original_mode));
            assert_eq!(saved[0].modified, Some(modified));
            if stage == 1 {
                projection.restore().unwrap();
            } else {
                std::mem::forget(projection);
                recover(&journal, &source).unwrap();
            }
            validate_original(&repo, &source).unwrap();
            assert_eq!(fs::read(&original).unwrap(), original_bytes);
            let after = fs::metadata(&original).unwrap();
            assert_eq!(after.mode(), original_mode);
            assert_eq!(after.modified().unwrap(), modified);
            for (p, before) in [&bp, &patch].into_iter().zip(preserved) {
                assert_eq!((fs::read(p).unwrap(), unchanged_file_identity(p)), before);
            }
            assert!(!journal.exists());
        }
    }
    #[test]
    fn avb_changed_inputs_alias_hardlink_and_exec_mode_fail_before_journal() {
        // Each source, unchanged build definition and official patch is checked
        // independently. A failure must not capture or mutate any input.
        for role in 0..3 {
            for kind in 0..6 {
                let d = tempfile::tempdir().unwrap();
                let (repo, source) = fixture(d.path());
                validate_original(&repo, &source).unwrap();
                let paths = [
                    source.join(PROJECT).join(ORIGINALS[0].0),
                    source.join(PROJECT).join(BP.0),
                    repo.join(PATCHES[0].0),
                ];
                let selected = &paths[role];
                match kind {
                    0 | 1 => {
                        let mut body = fs::read(selected).unwrap();
                        if kind == 0 {
                            body[0] ^= 1;
                        } else {
                            body.push(b'\n');
                        }
                        fs::write(selected, body).unwrap();
                    }
                    2 => {
                        let target = d.path().join("aliased-file");
                        fs::rename(selected, &target).unwrap();
                        symlink(target, selected).unwrap();
                    }
                    3 => {
                        let parent = selected.parent().unwrap();
                        let target = d.path().join("aliased-parent");
                        fs::rename(parent, &target).unwrap();
                        symlink(target, parent).unwrap();
                    }
                    4 => fs::hard_link(selected, d.path().join("second-link")).unwrap(),
                    5 => fs::set_permissions(selected, fs::Permissions::from_mode(0o700)).unwrap(),
                    _ => unreachable!(),
                }
                let before = paths
                    .each_ref()
                    .map(|p| (fs::read(p).unwrap(), unchanged_file_identity(p)));
                let journal = d.path().join("source-projection.json");
                let mut projection = Projection::new(journal.clone()).unwrap();
                assert!(
                    project(&mut projection, &repo, &source).is_err(),
                    "role {role} kind {kind}"
                );
                assert!(projection.originals.is_empty());
                assert!(projection.applied_patches.is_empty());
                assert!(!journal.exists());
                assert_eq!(
                    paths
                        .each_ref()
                        .map(|p| (fs::read(p).unwrap(), unchanged_file_identity(p))),
                    before
                );
            }
        }
    }
    #[test]
    fn avb_production651_requests_keep_original_lock_targets_and_strict_user() {
        const PROBE: &str = "DROIDLOOM_TEST_AVB_STRICT_ENV_CHILD";
        const CASE: &str = "android::avb_security::tests::avb_production651_requests_keep_original_lock_targets_and_strict_user";
        if std::env::var_os(PROBE).is_none() {
            let child = Command::new(std::env::current_exe().unwrap())
                .args(["--exact", CASE, "--test-threads=1"])
                .env(PROBE, "1")
                .env("TARGET_BUILD_VARIANT", "eng")
                .env("TARGET_RELEASE", "cp3a")
                .env("ALLOW_MISSING_DEPENDENCIES", "true")
                .env("SELINUX_IGNORE_NEVERALLOWS", "true")
                .output()
                .unwrap();
            assert!(
                child.status.success(),
                "status={:?}\nstdout:\n{}\nstderr:\n{}",
                child.status.code(),
                String::from_utf8_lossy(&child.stdout),
                String::from_utf8_lossy(&child.stderr)
            );
            assert!(String::from_utf8_lossy(&child.stdout).contains("1 passed; 0 failed"));
            return;
        }
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        let lock = production_source::source_lock_path(&repo).unwrap();
        assert_eq!(lock, repo.join(production_source::LOCK_PATH));
        assert_eq!(hash(&lock).unwrap(), production_source::LOCK_SHA);
        validate_source_lock(&repo, &lock).unwrap();
        let d = tempfile::tempdir().unwrap();
        let foreign_lock = d.path().join("copied-lock.json");
        fs::write(&foreign_lock, fs::read(&lock).unwrap()).unwrap();
        assert!(validate_source_lock(&repo, &foreign_lock).is_err());
        let native_lock = FixedProductionRequest::NativePair
            .source_lock(&repo)
            .unwrap();
        assert_ne!(native_lock, lock);
        assert!(validate_source_lock(&repo, &native_lock).is_err());
        let component_targets = ["netbpfload", "libservice-connectivity", "libnetd_updatable"];
        for (request, complete_product) in [
            (
                FixedProductionRequest::Existing(
                    SoongDependencyMode::Strict,
                    crate::android::TARGETS,
                ),
                true,
            ),
            (FixedProductionRequest::VendorImageOnProductionSource, false),
            (FixedProductionRequest::WmSecurityOnProductionSource, false),
            (
                FixedProductionRequest::FrameworkAsbOnProductionSource,
                false,
            ),
            (
                FixedProductionRequest::Existing(SoongDependencyMode::Strict, &component_targets),
                false,
            ),
        ] {
            validate_request(request, "droidloom_x86_64").unwrap();
            assert!(validate_request(request, "another_product").is_err());
            assert_eq!(request.source_lock(&repo).unwrap(), lock);
            assert_eq!(request.source_mode(), SoongDependencyMode::Strict);
            let targets = request.soong_targets(d.path(), "droidloom_x86_64").unwrap();
            // Complete delivery requests real modules and whole APEXes. The
            // separate component route keeps all three exact intermediate paths.
            let expected_targets = request.requested_targets().iter().map(|name| {
                if complete_product {
                    return PathBuf::from(*name);
                }
                match *name {
                    "netbpfload" => d.path().join("soong/.intermediates/packages/modules/Connectivity/bpf/loader/netbpfload/android_x86_64/netbpfload"),
                    "libservice-connectivity" => d.path().join("soong/.intermediates/packages/modules/Connectivity/service/libservice-connectivity/android_x86_64_shared/libservice-connectivity.so"),
                    "libnetd_updatable" => d.path().join("soong/.intermediates/packages/modules/Connectivity/bpf/netd/libnetd_updatable/android_x86_64_shared_cfi/libnetd_updatable.so"),
                    _ => PathBuf::from(*name),
                }
            }).collect::<Vec<_>>();
            assert_eq!(targets, expected_targets);
            let mut command = production_soong_command(
                d.path(),
                d.path(),
                d.path(),
                "droidloom_x86_64",
                2,
                &targets,
            )
            .unwrap();
            request
                .configure_dependencies(&mut command, "droidloom_x86_64")
                .unwrap();
            configure_command(request, "droidloom_x86_64", &mut command).unwrap();
            for (key, value) in [
                ("TARGET_BUILD_VARIANT", "user"),
                ("TARGET_RELEASE", "cp2a"),
                ("ALLOW_MISSING_DEPENDENCIES", "false"),
                ("SELINUX_IGNORE_NEVERALLOWS", "false"),
            ] {
                assert!(
                    command
                        .get_envs()
                        .any(|(k, v)| k == key && v == Some(std::ffi::OsStr::new(value)))
                );
            }
            let mut expected = vec![std::ffi::OsString::from("--make-mode"), "-j2".into()];
            expected.extend(targets.iter().map(|p| p.as_os_str().to_owned()));
            assert_eq!(
                command.get_args().collect::<Vec<_>>(),
                expected.iter().map(|s| s.as_os_str()).collect::<Vec<_>>()
            );
            assert_eq!(
                request.description("droidloom_x86_64").unwrap()["runtime_qualified"],
                false
            );
        }
        for request in [
            FixedProductionRequest::NativePair,
            FixedProductionRequest::LibpngSecurityOnAudioSource,
            FixedProductionRequest::Existing(
                SoongDependencyMode::AudioApexTargetClosure,
                &["com.android.hardware.audio.droidloom"],
            ),
        ] {
            assert!(validate_request(request, "droidloom_x86_64").is_err());
        }
    }
}
