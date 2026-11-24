//! Incremental continuation of a completed native distribution and vendor build.
//! Original failed output remains an explicit cache generation; a fresh directory
//! records preserved inputs, the new normal vendor command and final assembly.
use super::*;
use std::os::unix::fs::MetadataExt;

const VENDOR_RESULT: &str = "droidloom-production-full654-vendor-normal-result.json";
const ARCHIVE: &str = "soong/.intermediates/vendor/droidloom/android/native-bridge/official-vendor/droidloom_cp3a_native_bridge_package/android_common/droidloom_cp3a_native_bridge_package.zip";

fn real_directory(path: &Path) -> Result<()> {
    if !path.is_absolute() || path.canonicalize()? != path {
        return fail("resume requires canonical absolute directories");
    }
    for parent in path.ancestors() {
        let m = fs::symlink_metadata(parent)?;
        if !m.is_dir() || m.file_type().is_symlink() {
            return fail("resume directory or parent is aliased");
        }
    }
    Ok(())
}

fn original_lock(path: &Path) -> Result<([u64; 2], crate::util::Lock)> {
    let before = fs::symlink_metadata(path)?;
    if !before.is_file() || before.file_type().is_symlink() || before.nlink() != 1 {
        return fail("resume requires the existing regular source lock");
    }
    let held = crate::util::Lock::acquire(path)?;
    let after = fs::symlink_metadata(path)?;
    if before.dev() != after.dev() || before.ino() != after.ino() {
        return fail("resume lock identity changed");
    }
    Ok(([before.dev(), before.ino()], held))
}

fn prior_result(value: &Value, built: &Path) -> Result<()> {
    if value["schema"] != "droidloom-production-full654-vendor-normal-result-v1"
        || value["normal_command_returned_success"] != true
        || value["source_projection_restored"] != true
        || value["build_variant"] != PRODUCTION_BUILD_VARIANT
        || value["source_release"] != PRODUCTION_TARGET_RELEASE
        || value["vendor_image"]["path"]
            != built
                .join("vendor/target/product/droidloom_x86_64/vendor.img")
                .to_string_lossy()
                .as_ref()
        || value["requested_targets"].as_array().is_none_or(|targets| {
            ![
                "vendorimage",
                "secilc",
                "checkvintf",
                "host_init_verifier",
                "droidloom-readiness",
                keymint_test::TARGET,
            ]
            .iter()
            .all(|target| targets.iter().any(|item| item == *target))
        })
    {
        return fail(
            "resume requires a completed strict normal vendor command from the selected output",
        );
    }
    Ok(())
}

fn read_bound(path: &Path, expected: &str) -> Result<(Artifact, Value)> {
    let file = artifact(path, 64 * 1024 * 1024)?;
    if file.sha256 != expected {
        return fail("resume input receipt digest differs");
    }
    let value = serde_json::from_slice(&fs::read(path)?)?;
    file.check()?;
    Ok((file, value))
}

fn validate_native(value: &Value, inputs: &VerifiedVendorInputs) -> Result<()> {
    let expected = serde_json::to_value(inputs.receipt()?)?;
    if value["schema"] != expected["schema"]
        || value["profile_sha256"] != expected["profile_sha256"]
        || value["source_system_sha256"] != expected["source_system_sha256"]
        || value["files"] != expected["files"]
        || value["phase"] != "normal-native-distribution"
        || value["requested_targets"] != json!(NATIVE_TARGETS)
        || value["build_variant"] != PRODUCTION_BUILD_VARIANT
        || value["source_release"] != PRODUCTION_TARGET_RELEASE
        || value["source_lock"]["sha256"] != production_source::LOCK_SHA
        || value["strict_allow_missing_dependencies"] != "false"
        || value["selinux_ignore_neverallows"] != "false"
    {
        return fail("retained native distribution uses different strict official inputs");
    }
    Ok(())
}

fn collect_references(
    value: &Value,
    root: &Path,
    found: &mut BTreeMap<PathBuf, (u64, String)>,
) -> Result<()> {
    match value {
        Value::Object(values) => {
            if let (Some(path), Some(bytes), Some(sha)) = (
                values.get("path").and_then(Value::as_str),
                values.get("bytes").and_then(Value::as_u64),
                values.get("sha256").and_then(Value::as_str),
            ) {
                let path = PathBuf::from(path);
                if path.starts_with(root) {
                    if path.components().any(|p| {
                        !matches!(
                            p,
                            std::path::Component::RootDir | std::path::Component::Normal(_)
                        )
                    }) || sha.len() != 64
                        || !sha
                            .bytes()
                            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
                    {
                        return fail("invalid prior output reference");
                    }
                    if let Some(previous) = found.insert(path, (bytes, sha.into())) {
                        if previous != (bytes, sha.into()) {
                            return fail("conflicting prior output references");
                        }
                    }
                }
            }
            for child in values.values() {
                collect_references(child, root, found)?;
            }
        }
        Value::Array(values) => {
            for child in values {
                collect_references(child, root, found)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn preserve(
    root: &Path,
    output: &Path,
    references: &BTreeMap<PathBuf, (u64, String)>,
) -> Result<Value> {
    preserve_from(root, root, output, references)
}

fn preserve_from(
    root: &Path,
    source_root: &Path,
    output: &Path,
    references: &BTreeMap<PathBuf, (u64, String)>,
) -> Result<Value> {
    let mut rows = Vec::new();
    let mut total = 0u64;
    for (original, (bytes, sha)) in references {
        let path = source_root.join(original.strip_prefix(root)?);
        total = total
            .checked_add(*bytes)
            .ok_or("prior outputs size overflow")?;
        if total > 2 * 1024 * 1024 * 1024 {
            return fail("prior output preservation exceeds 2 GiB");
        }
        let before = fs::symlink_metadata(&path)?;
        if !before.is_file()
            || before.file_type().is_symlink()
            || before.nlink() != 1
            || before.len() != *bytes
            || path.canonicalize()? != path
            || hash(&path)? != *sha
        {
            return fail("prior normal output identity or content changed");
        }
        let destination = output.join(original.strip_prefix(root)?);
        fs::create_dir_all(destination.parent().ok_or("preserved output parent")?)?;
        if destination.symlink_metadata().is_ok() {
            return fail("prior preservation destination exists");
        }
        crate::util::copy(&path, &destination)?;
        if hash(&destination)? != *sha || f9(&before)? != f9(&fs::symlink_metadata(&path)?)? {
            return fail("prior normal output changed during preservation");
        }
        rows.push(json!({"original":original,"preserved":destination,"bytes":bytes,"sha256":sha}));
    }
    Ok(json!({"files":rows,"bytes":total}))
}



fn supplemental_native_references(
    required: &BTreeMap<PathBuf, (u64, String)>,
    retained: &BTreeMap<PathBuf, (u64, String)>,
    allowed: &BTreeMap<PathBuf, (u64, String)>,
) -> Result<BTreeMap<PathBuf, (u64, String)>> {
    let mut added = BTreeMap::new();
    for (path, value) in required {
        if retained.get(path) == Some(value) { continue; }
        if retained.contains_key(path) || allowed.get(path) != Some(value) {
            return fail("retained evidence differs beyond the explicitly pinned native receipts");
        }
        added.insert(path.clone(), value.clone());
    }
    if retained.keys().any(|path| !required.contains_key(path)) {
        return fail("retained evidence contains an unaccounted prior output");
    }
    Ok(added)
}

struct RetainedPrior {
    receipt: Artifact,
    root: PathBuf,
    references: BTreeMap<PathBuf, (u64, String)>,
}

fn retained_references(value: &Value, built: &Path, root: &Path) -> Result<BTreeMap<PathBuf, (u64, String)>> {
    let rows = value["files"].as_array().ok_or("prior preservation files are absent")?;
    if rows.is_empty() || rows.len() > 4096 {
        return fail("prior preservation file count is not bounded");
    }
    let mut found = BTreeMap::new();
    let mut total = 0u64;
    for row in rows {
        let original = PathBuf::from(row["original"].as_str().ok_or("prior original path")?);
        let relative = original.strip_prefix(built)?;
        if relative.as_os_str().is_empty() || relative.components().any(|part| !matches!(part, std::path::Component::Normal(_))) {
            return fail("prior retained path escapes the selected output");
        }
        let expected = root.join(relative);
        if row["preserved"].as_str() != expected.to_str() {
            return fail("prior retained path is not the original generation-relative file");
        }
        let bytes = row["bytes"].as_u64().ok_or("prior retained bytes")?;
        total = total.checked_add(bytes).ok_or("prior retained size overflow")?;
        collect_references(&json!({"path":original,"bytes":bytes,"sha256":row["sha256"]}), built, &mut found)?;
    }
    if found.len() != rows.len() || total > 2 * 1024 * 1024 * 1024 || value["bytes"] != total {
        return fail("prior retained references are duplicated, incomplete or oversized");
    }
    Ok(found)
}

impl RetainedPrior {
    fn load(
        path: &Path, sha: &str, built: &Path, out: &Path,
        native_sha: &str, vendor_sha: &str, package_identity: [u64;2], source_identity: [u64;2],
    ) -> Result<Self> {
        let parent = path.parent().ok_or("prior attempt parent")?;
        real_directory(parent)?;
        if path != parent.join("resume-attempt.json") || out.starts_with(parent) || parent.starts_with(out)
            || parent.starts_with(built) || built.starts_with(parent) {
            return fail("retained resume attempt aliases the output or cache");
        }
        let (receipt, value) = read_bound(path, sha)?;
        if value["schema"] != "droidloom-official-vendor-incremental-resume-v1"
            || value["previous_output"].as_str() != built.to_str()
            || value["fresh_assembly_output"].as_str() != parent.to_str()
            || value["native_receipt"]["sha256"] != native_sha
            || value["previous_vendor_receipt"]["sha256"] != vendor_sha
            || value["package_lock_device_inode"] != json!(package_identity)
            || value["source_lock_device_inode"] != json!(source_identity)
        {
            return fail("retained attempt is not the same pinned original native/vendor generation and locks");
        }
        let root = parent.join("previous-output");
        real_directory(&root)?;
        let references = retained_references(&value["preserved"], built, &root)?;
        receipt.check()?;
        Ok(Self { receipt, root, references })
    }
}

pub(crate) struct NativeVerification {
    projection_pin: Artifact,
    source_pin: Artifact,
    archive_pin: Artifact,
    official_input_pin: Artifact,
    projection: Value,
    native_source: Value,
    local_inputs: Value,
}

fn comparable_projection(mut value: Value) -> Value {
    // The producer checkout is explicitly reselected; every projected byte,
    // patch, requested target and the materialized source manifest must match.
    if let Some(lock) = value.get_mut("source_lock").and_then(Value::as_object_mut) {
        lock.remove("path");
    }
    value
}

fn compare_native_inputs(
    expected: &Value,
    actual: &Value,
    old_source: &Value,
    current_source: &Value,
) -> Result<()> {
    if comparable_projection(expected.clone()) != comparable_projection(actual.clone()) {
        return fail(
            "retained native distribution differs from the current normal native projection",
        );
    }
    if old_source != current_source {
        return fail("retained native distribution uses different NativeBridge source files");
    }
    Ok(())
}

fn native_local_inputs(repo: &Path, previous: &Path, commit: &str) -> Result<Value> {
    // The translation package is generated in its own package from pinned
    // HOST_MODULES/GUEST_MODULES. Frontend/composer modules in the root blueprint
    // are validated by the normal vendor build and are not native archive inputs.
    const ROOTS: &[&str] = &[
        "LICENSE",
        "LICENSES",
        "runtime/droidloom-cpu-placement",
        "android/container-bootstrap",
        "android/lmkd-compat",
        "android/runtime",
        "android/native-bridge",
        "android/selinux-compat",
        "android/device",
        "device",
        "android/mesa",
    ];
    if commit.len() != 40
        || !commit
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    {
        return fail("previous normal native producer requires an exact commit");
    }
    real_directory(previous)?;
    let git = |root: &Path, args: &[&str]| -> Result<String> {
        crate::util::output(
            Command::new("/usr/bin/git")
                .arg("-C")
                .arg(root)
                .args(args)
                .env("GIT_OPTIONAL_LOCKS", "0")
                .env("GIT_TERMINAL_PROMPT", "0"),
        )
    };
    if git(previous, &["rev-parse", "HEAD"])?.trim() != commit {
        return fail("previous normal native producer commit changed");
    }
    let current = git(repo, &["rev-parse", "HEAD"])?;
    for root in [previous, repo] {
        let mut args = vec![
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignored",
            "--",
        ];
        args.extend_from_slice(ROOTS);
        if !git(root, &args)?.trim().is_empty() {
            return fail("native producer inputs contain uncommitted or additional files");
        }
    }
    let mut paths = BTreeMap::new();
    for relative in ROOTS {
        let old_selector = format!("{commit}:{relative}");
        let current_selector = format!("{}:{relative}", current.trim());
        let old = git(previous, &["rev-parse", "--verify", &old_selector])?;
        let new = git(repo, &["rev-parse", "--verify", &current_selector])?;
        if old.trim() != new.trim() {
            return fail(format!("local native producer inputs changed: {relative}"));
        }
        paths.insert(*relative, old.trim().to_owned());
    }
    Ok(
        json!({"previous_producer":previous,"previous_commit":commit,
        "current_producer":repo,"current_commit":current.trim(),"unchanged_git_objects":paths,
        "framework_frontend_is_not_a_native_distribution_input":true}),
    )
}

impl NativeVerification {
    fn load(
        repo: &Path,
        native: &Path,
        projection_sha: &str,
        source_sha: &str,
        producer_commit: &str,
    ) -> Result<Self> {
        let (projection_pin, projection) = read_bound(
            &native.join("droidloom-production-full654-inputs.json"),
            projection_sha,
        )?;
        let (source_pin, native_source) = read_bound(
            &native.join("target/product/droidloom_x86_64/droidloom-native-bridge-source.json"),
            source_sha,
        )?;
        if projection["schema"] != "droidloom-production-full654-inputs-v1"
            || projection["requested_targets"] != json!(NATIVE_TARGETS)
            || projection["effective_projection"]["files"]
                .as_object()
                .is_none_or(|v| v.is_empty())
            || projection["effective_projection"]["patches"]
                .as_object()
                .is_none_or(|v| v.is_empty())
            || native_source["files"]
                .as_object()
                .is_none_or(|v| v.is_empty())
        {
            return fail(
                "retained native build lacks its complete normal projection and source receipts",
            );
        }
        let lock_path = PathBuf::from(
            projection["source_lock"]["path"]
                .as_str()
                .ok_or("native producer source lock path absent")?,
        );
        let suffix = Path::new(production_source::LOCK_PATH);
        if !lock_path.ends_with(suffix) {
            return fail("native producer source lock has an unexpected path");
        }
        let mut previous = lock_path;
        for _ in suffix.components() {
            previous.pop();
        }
        let local_inputs = native_local_inputs(repo, &previous, producer_commit)?;
        let archive_pin = artifact(&native.join(ARCHIVE), 512 * 1024 * 1024)?;
        let official_input_pin = artifact(&native.join(INPUT_NAME), 64 * 1024 * 1024)?;
        Ok(Self {
            projection_pin,
            source_pin,
            archive_pin,
            official_input_pin,
            projection,
            native_source,
            local_inputs,
        })
    }

    pub(crate) fn compare(&self, out: &Path, current_source: &Value) -> Result<()> {
        self.projection_pin.check()?;
        self.source_pin.check()?;
        self.archive_pin.check()?;
        self.official_input_pin.check()?;
        let actual: Value = serde_json::from_slice(&fs::read(
            out.join("droidloom-production-full654-inputs.json"),
        )?)?;
        compare_native_inputs(
            &self.projection,
            &actual,
            &self.native_source,
            current_source,
        )
    }

    fn run(
        &self,
        repo: &Path,
        source: &Path,
        out: &Path,
        work: &Path,
        inputs: &VerifiedVendorInputs,
        jobs: usize,
    ) -> Result<Value> {
        let projected = out.join("native-projection-check");
        fs::create_dir(&projected)?;
        build_targets_with_fixed_request_and_native_verification(
            repo,
            source,
            &projected,
            work,
            "droidloom_x86_64",
            jobs,
            FixedProductionRequest::OfficialGsiVendor(Request {
                inputs,
                phase: Phase::Native,
            }),
            Some(self),
        )?;
        self.projection_pin.check()?;
        self.source_pin.check()?;
        self.archive_pin.check()?;
        self.official_input_pin.check()?;
        let record = json!({"schema":"droidloom-native-reuse-verification-v1",
            "previous_projection":self.projection_pin,"previous_native_source":self.source_pin,
            "retained_native_archive":self.archive_pin,"official_native_inputs":self.official_input_pin,
            "current_projection":artifact(&projected.join("droidloom-production-full654-inputs.json"),64*1024*1024)?,
            "local_producer_inputs":self.local_inputs,"projected_files_and_patches_identical":true,
            "native_source_files_identical":true,"normal_native_command_repeated":false,
            "source_projection_restored":true,"runtime_qualified":false,"production_ready":false});
        write(
            &out.join("native-reuse-verified.json"),
            serde_json::to_vec_pretty(&record)?,
        )?;
        Ok(record)
    }
}

pub(crate) fn run(
    repo: &Path,
    work: &Path,
    built: &Path,
    out: &Path,
    system: &Path,
    references: &Path,
    native_inputs_sha: &str,
    vendor_result_sha: &str,
    jobs: usize,
    native_projection_sha: &str,
    native_source_sha: &str,
    native_producer_commit: &str,
    verify_native_only: bool,
    previous_attempt: Option<&Path>,
    previous_attempt_sha: Option<&str>,
) -> Result<()> {
    if unsafe { libc::getuid() } == 0 {
        return fail("resume runs as the normal build account");
    }
    for directory in [repo, work, built] {
        real_directory(directory)?;
    }
    crate::native_generation_art::validated_output(work, out)?;
    if out.starts_with(built)
        || built.starts_with(out)
        || built.starts_with(work)
        || work.starts_with(built)
    {
        return fail("resume output, completed cache and source workspace overlap");
    }
    let (package_identity, _package_lock) = original_lock(&work.join("package-build.lock"))?;
    let (source_identity, _source_lock) = original_lock(&work.join("aosp-source-update.lock"))?;
    if work.join("source-projection.json").exists() {
        return fail("unfinished source projection requires explicit source recovery first");
    }
    if built.join(RESULT_NAME).exists() {
        return fail("a completed release is not a failed-build resume candidate");
    }
    let inputs = droidloom_image::official_vendor_inputs::verify_vendor_inputs(system, references)?;
    let native = built.join("native");
    let vendor = built.join("vendor");
    real_directory(&native)?;
    real_directory(&vendor)?;
    let (native_receipt, native_value) = read_bound(&native.join(INPUT_NAME), native_inputs_sha)?;
    validate_native(&native_value, &inputs)?;
    let native_verification = NativeVerification::load(
        repo,
        &native,
        native_projection_sha,
        native_source_sha,
        native_producer_commit,
    )?;
    let retained = match (previous_attempt, previous_attempt_sha) {
        (None, None) => None,
        (Some(path), Some(sha)) => Some(RetainedPrior::load(path, sha, built, out,
            native_inputs_sha, vendor_result_sha, package_identity, source_identity)?),
        _ => return fail("retained previous attempt and its digest must be selected together"),
    };
    let read_root = retained.as_ref().map_or(built, |value| value.root.as_path());
    let (vendor_receipt, vendor_value) =
        read_bound(&read_root.join("vendor").join(VENDOR_RESULT), vendor_result_sha)?;
    prior_result(&vendor_value, built)?;
    let lock = repo.join(production_source::LOCK_PATH);
    let source_lock = droidloom_source::load_lock(&lock)?;
    let source = work.join("aosp-source");
    production_source::verify_source_workspace(&lock, &source_lock, &source)?;
    droidloom_source::production_car::verify_materialized(&lock, &source_lock, &source)?;

    fs::create_dir(out)?;
    if verify_native_only {
        crate::assemble::prepare_vendor_build_tools(repo, work, jobs)?;
        native_verification.run(repo, &source, out, work, &inputs, jobs)?;
        return Ok(());
    }
    let mut preserved = BTreeMap::new();
    let mut receipts = Vec::new();
    for relative in [
        format!("native/{INPUT_NAME}"),
        "native/droidloom-production-full654-inputs.json".into(),
        "native/target/product/droidloom_x86_64/droidloom-native-bridge-source.json".into(),
        format!("vendor/{INPUT_NAME}"),
        "vendor/droidloom-production-full654-inputs.json".into(),
        format!("vendor/{VENDOR_RESULT}"),
        "official-vendor-attempt.json".into(),
    ] {
        let file = if relative == "native/droidloom-production-full654-inputs.json" {
            native_verification.projection_pin.path.clone()
        } else if relative == "native/target/product/droidloom_x86_64/droidloom-native-bridge-source.json" {
            native_verification.source_pin.path.clone()
        } else { read_root.join(&relative) };
        let pin = artifact(&file, 64 * 1024 * 1024).map_err(|error| format!("prior resume input {}: {error}", file.display()))?;
        let value: Value = serde_json::from_slice(&fs::read(&file)?)?;
        pin.check()?;
        collect_references(&value, built, &mut preserved)?;
        preserved.insert(built.join(relative), (pin.bytes, pin.sha256.clone()));
        receipts.push(pin);
    }
    let archive = artifact(&native.join(ARCHIVE), 512 * 1024 * 1024)?;
    preserved.insert(
        archive.path.clone(),
        (archive.bytes, archive.sha256.clone()),
    );
    let supplemental = if let Some(previous) = &retained {
        previous.receipt.check()?;
        let allowed = BTreeMap::from([
            (native_verification.projection_pin.path.clone(), (native_verification.projection_pin.bytes, native_verification.projection_pin.sha256.clone())),
            (native_verification.source_pin.path.clone(), (native_verification.source_pin.bytes, native_verification.source_pin.sha256.clone())),
        ]);
        supplemental_native_references(&preserved, &previous.references, &allowed)?
    } else { BTreeMap::new() };
    let prior: BTreeMap<_,_> = preserved.iter().filter(|(path,_)| !supplemental.contains_key(*path))
        .map(|(path,value)| (path.clone(),value.clone())).collect();
    let mut preservation = preserve_from(built, read_root, &out.join("previous-output"), &prior)?;
    if !supplemental.is_empty() {
        let additional = preserve_from(built, built, &out.join("previous-output"), &supplemental)?;
        preservation["files"].as_array_mut().ok_or("preserved file rows")?
            .extend(additional["files"].as_array().ok_or("supplemental native rows")?.iter().cloned());
        preservation["bytes"] = json!(preservation["bytes"].as_u64().ok_or("preserved bytes")?
            .checked_add(additional["bytes"].as_u64().ok_or("supplemental native bytes")?).ok_or("preservation size overflow")?);
    }
    if let Some(previous) = &retained { previous.receipt.check()?; }

    for receipt in &receipts {
        receipt.check()?;
    }
    let mut provenance = json!({
        "schema":"droidloom-official-vendor-incremental-resume-v1",
        "native_build_repeated":false,"native_receipt":native_receipt,
        "package_lock_device_inode":package_identity,"source_lock_device_inode":source_identity,
        "previous_vendor_receipt":vendor_receipt,"previous_output":built,
        "retained_previous_attempt":retained.as_ref().map(|value| &value.receipt),
        "supplemental_pinned_native_receipts":supplemental.keys().collect::<Vec<_>>(),
        "fresh_assembly_output":out,"preserved":preservation,
        "normal_vendor_targets":VENDOR_TARGETS,"runtime_qualified":false,
        "production_ready":false,"userdata_attached":false
    });
    write(
        &out.join("resume-attempt.json"),
        serde_json::to_vec_pretty(&provenance)?,
    )?;
    native_receipt.check()?;
    vendor_receipt.check()?;
    crate::assemble::prepare_vendor_build_tools(repo, work, jobs)?;
    provenance["native_reuse_preflight"] =
        native_verification.run(repo, &source, out, work, &inputs, jobs)?;
    write(
        &out.join("resume-attempt.json"),
        serde_json::to_vec_pretty(&provenance)?,
    )?;
    let bridge = check_bridge(&archive.path, &out.join("native-vendor-inputs"), &inputs)?;
    // Keep the original native source receipt and archive. The new vendor phase
    // consumes that checked binary input and normally rebuilds changed targets.
    build_targets_with_fixed_request(
        repo,
        &source,
        &vendor,
        work,
        "droidloom_x86_64",
        jobs,
        FixedProductionRequest::OfficialGsiVendor(Request {
            inputs: &inputs,
            phase: Phase::Vendor(&bridge),
        }),
    )?;
    native_receipt.check()?;
    archive.check()?;
    finish(
        repo,
        &native,
        &vendor,
        &bridge,
        out,
        "droidloom_x86_64",
        &inputs,
        Some(provenance),
    )
}

#[cfg(test)]
mod tests {
    use super::*;


    #[test]
    fn older_retention_only_adds_the_explicitly_pinned_native_receipt() {
        let source = PathBuf::from("/built/native/source.json");
        let vendor = PathBuf::from("/built/vendor.img");
        let source_value = (10, "a".repeat(64));
        let prior = BTreeMap::from([(vendor.clone(), (3, "b".repeat(64)))]);
        let mut required = prior.clone();
        required.insert(source.clone(), source_value.clone());
        let allowed = BTreeMap::from([(source.clone(), source_value.clone())]);
        assert_eq!(supplemental_native_references(&required, &prior, &allowed).unwrap(), allowed);
        required.insert(PathBuf::from("/built/unselected"), (3, "c".repeat(64)));
        assert!(supplemental_native_references(&required, &prior, &allowed).is_err());
        required.remove(&PathBuf::from("/built/unselected"));
        required.get_mut(&source).unwrap().1 = "d".repeat(64);
        assert!(supplemental_native_references(&required, &prior, &allowed).is_err());
        required.insert(source, source_value);
        required.get_mut(&vendor).unwrap().1 = "d".repeat(64);
        assert!(supplemental_native_references(&required, &prior, &allowed).is_err());
    }

    #[test]
    fn saved_success_survives_mutated_cache_but_not_mutated_saved_bytes() {
        let temp = tempfile::tempdir().unwrap();
        let built = temp.path().join("built");
        let retained = temp.path().join("retained");
        fs::create_dir(&built).unwrap();
        fs::create_dir(&retained).unwrap();
        fs::write(built.join("vendor.img"), b"new").unwrap();
        fs::write(retained.join("vendor.img"), b"old").unwrap();
        let refs = BTreeMap::from([(built.join("vendor.img"), (3, hash(&retained.join("vendor.img")).unwrap()))]);
        let saved = temp.path().join("next");
        preserve_from(&built, &retained, &saved, &refs).unwrap();
        assert_eq!(fs::read(saved.join("vendor.img")).unwrap(), b"old");
        assert_eq!(fs::read(built.join("vendor.img")).unwrap(), b"new");
        fs::write(retained.join("vendor.img"), b"bad").unwrap();
        assert!(preserve_from(&built, &retained, &temp.path().join("reject"), &refs).is_err());
    }

    #[test]
    fn saved_receipt_rejects_redirected_or_duplicated_members() {
        let sha = "a".repeat(64);
        let built = Path::new("/selected/cache");
        let root = Path::new("/selected/attempt/previous-output");
        let row = json!({"original":"/selected/cache/vendor.img","preserved":"/selected/attempt/previous-output/vendor.img","bytes":3,"sha256":sha});
        let good = json!({"files":[row.clone()],"bytes":3});
        assert!(retained_references(&good,built,root).is_ok());
        let mut redirected = good.clone();
        redirected["files"][0]["preserved"] = "/elsewhere/vendor.img".into();
        assert!(retained_references(&redirected,built,root).is_err());
        let mut escaped = good.clone();
        escaped["files"][0]["original"] = "/selected/cache/../elsewhere/vendor.img".into();
        assert!(retained_references(&escaped,built,root).is_err());
        assert!(retained_references(&json!({"files":[row.clone(),row],"bytes":6}),built,root).is_err());
    }

    #[test]
    fn reused_native_requires_identical_projected_bytes_and_external_sources() {
        let previous = json!({"source_lock":{"path":"/old/lock","sha256":"same"},"effective_projection":{"files":{"native.cpp":"old"},"patches":{"fix.patch":"same"}},"requested_targets":NATIVE_TARGETS});
        let source = json!({"commit":"original","files":{"bridge.cpp":"same"}});
        let mut current = previous.clone();
        current["source_lock"]["path"] = "/new/lock".into();
        assert!(compare_native_inputs(&previous, &current, &source, &source).is_ok());
        current["effective_projection"]["files"]["native.cpp"] = "changed".into();
        assert!(compare_native_inputs(&previous, &current, &source, &source).is_err());
        current = previous.clone();
        current["requested_targets"] = json!(["other"]);
        assert!(compare_native_inputs(&previous, &current, &source, &source).is_err());
        let mut changed = source.clone();
        changed["files"]["bridge.cpp"] = "changed".into();
        assert!(compare_native_inputs(&previous, &previous, &source, &changed).is_err());
    }

    #[test]
    fn resume_requires_completed_selected_vendor() {
        let root = Path::new("/original");
        let mut value = json!({"schema":"droidloom-production-full654-vendor-normal-result-v1",
            "normal_command_returned_success":true,"source_projection_restored":true,
            "build_variant":"user","source_release":"cp2a",
            "vendor_image":{"path":"/original/vendor/target/product/droidloom_x86_64/vendor.img"},
            "requested_targets": ["vendorimage","secilc","checkvintf","host_init_verifier","droidloom-readiness",keymint_test::TARGET]});
        assert!(prior_result(&value, root).is_ok());
        value["normal_command_returned_success"] = false.into();
        assert!(prior_result(&value, root).is_err());
        value["normal_command_returned_success"] = true.into();
        assert!(prior_result(&value, Path::new("/other")).is_err());
        value["requested_targets"] = json!(["vendorimage"]);
        assert!(prior_result(&value, root).is_err());
    }
    #[test]
    fn changed_prior_file_cannot_enter_incremental_build() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("built");
        fs::create_dir(&root).unwrap();
        let file = root.join("vendor.img");
        fs::write(&file, b"old").unwrap();
        let expected = hash(&file).unwrap();
        let refs = BTreeMap::from([(file.clone(), (3, expected))]);
        fs::write(&file, b"new").unwrap();
        assert!(preserve(&root, &temp.path().join("saved"), &refs).is_err());
        assert!(!temp.path().join("saved").exists());
    }
    #[test]
    fn preserve_prior_bytes_without_aliasing_the_cache() {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().join("built");
        fs::create_dir(&root).unwrap();
        let file = root.join("vendor.img");
        fs::write(&file, b"old").unwrap();
        let refs = BTreeMap::from([(file.clone(), (3, hash(&file).unwrap()))]);
        let saved = temp.path().join("saved");
        preserve(&root, &saved, &refs).unwrap();
        fs::write(&file, b"new").unwrap();
        assert_eq!(fs::read(saved.join("vendor.img")).unwrap(), b"old");
        assert!(preserve(&root, &saved, &refs).is_err());
    }
}
