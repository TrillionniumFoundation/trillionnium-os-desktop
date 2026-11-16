use std::collections::BTreeSet;
use std::os::unix::fs::{DirBuilderExt, MetadataExt};
use std::{env, fs, path::{Path, PathBuf}, process::{Command, ExitCode}};

struct Pin { path: &'static str, bytes: u64, sha256: &'static str, legacy: bool }
const PINS: &[Pin] = &[
    Pin { path: "tools/droidloom-source/src/lib.rs", bytes: 114801, sha256: "3cef5ac4c844b1b2ba66d2cc3f4e536349b58d88e43a4365316734dadd560750", legacy: false },
    Pin { path: "android/manifest/audio-bridge-source-lock.json", bytes: 239516, sha256: "22ae84b8d0747e371096035f46e636a00990d2a7b4cae8c5727f56fa946d1ee3", legacy: false },
    Pin { path: "tools/droidloom-source/tests/fixtures/audio-source321-before-allgraph.json", bytes: 145316, sha256: "2466de84fa9aeac43b4b5792efabbc27ea419652830e339844fa21fd67554bd9", legacy: true },
    Pin { path: "Cargo.toml", bytes: 468, sha256: "d56f8766070fceb2ad324eccfe9d5d140f6bacc3ca246fbea8306476573da4af", legacy: true },
    Pin { path: "Cargo.lock", bytes: 8043, sha256: "a20b2cd585658108f98a28a6d925c7cf3ecb3cb30c18f68c163e1035bcae5fbc", legacy: true },
];
const TESTS: &[&str] = &[
    "audio_r12_original_provider_closure_is_a_four_selector_extension",
    "audio_released_sdks_extend_the_actual_r11_lock_without_repinning",
    "audio_ondeviceintelligence_extends_actual_430_by_four_original_api_inputs",
    "audio_pasit_extends_the_actual_425_source_with_only_five_original_projects",
    "audio_rkpd_apex_extends_the_actual_425_source_by_one_original_cone",
    "audio_allgraph_extends_the_actual_previous_source_without_changing_commits",
    "audio_cts_sts_recursive_closure_is_a_monotonic_pinned_extension",
    "audio_error_prone_jimfs_is_one_monotonic_pinned_project",
    "audio_cts_compilation_is_one_monotonic_same_commit_cone",
    "audio_source_capacity_is_bound_to_the_exact_frozen_lock",
    "audio_reconciliation_preserves_existing_gatekeeper_purpose",
    "audio_junit_extension_keeps_the_actual_previous_projects_unchanged",
    "audio_api35_cts_extension_preserves_the_previous_materialized_plan",
    "project_bound_admits_superproject_gitlink_extensions_but_not_unbounded_sync",
    "source_lock_preserves_exact_sparse_paths_through_the_368_bound",
    "source_lock_rejects_369_sparse_paths_without_truncating_them",
    "bounded_sparse_paths_reject_duplicates_and_escapes_at_the_new_boundary",
    "actual_git_checkout_preserves_355_cones_and_hidden_blueprints",
    "plan_uses_only_exact_official_projects",
    "platform_compat_uses_its_official_tools_namespace",
    "traversal_and_full_sync_policy_are_rejected_together",
    "duplicate_projects_and_moving_refs_are_rejected",
    "root_links_are_relative_to_their_parent",
    "exact_local_git_fetch_and_manifest_link_are_verified",
    "reconciliation_accepts_only_monotonic_plan_expansion",
    "reconciliation_accepts_bounded_sparse_path_expansion",
    "materialized_verification_rejects_dirty_projects",
];
const SUMMARY: &str = "test result: ok. 27 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;";

fn hash(path: &Path) -> Result<String, String> {
    let out = Command::new("/usr/bin/sha256sum").arg("--").arg(path).output().map_err(|e| e.to_string())?;
    if !out.status.success() { return Err(format!("sha256sum failed: {}", path.display())); }
    let text = String::from_utf8(out.stdout).map_err(|e| e.to_string())?;
    let sha = text.split_whitespace().next().ok_or("empty checksum")?;
    if sha.len() != 64 || !sha.bytes().all(|b| b.is_ascii_hexdigit()) { return Err("invalid checksum".into()); }
    Ok(sha.to_owned())
}
fn regular(root: &Path, relative: &str) -> Result<PathBuf, String> {
    if !fs::symlink_metadata(root).map_err(|e| e.to_string())?.is_dir() { return Err("source root is not a real directory".into()); }
    let mut path = root.to_path_buf();
    let parts: Vec<_> = relative.split('/').collect();
    for (index, part) in parts.iter().enumerate() {
        if part.is_empty() || *part == "." || *part == ".." { return Err("unsafe input path".into()); }
        path.push(part);
        let meta = fs::symlink_metadata(&path).map_err(|e| format!("{}: {e}", path.display()))?;
        if index + 1 == parts.len() {
            if !meta.is_file() || meta.nlink() != 1 { return Err(format!("input must be a single-link regular file: {}", path.display())); }
        } else if !meta.is_dir() { return Err("input parent is not a real directory".into()); }
    }
    Ok(path)
}
fn verify(root: &Path, pin: &Pin) -> Result<PathBuf, String> {
    let path = regular(root, pin.path)?;
    if fs::metadata(&path).map_err(|e| e.to_string())?.len() != pin.bytes || hash(&path)? != pin.sha256 {
        return Err(format!("exact source pin differs: {}", path.display()));
    }
    Ok(path)
}
fn check_inputs(capsule: &Path, legacy: &Path) -> Result<(), String> {
    for pin in PINS { verify(&if pin.legacy { legacy.join("harness") } else { capsule.join("source") }, pin)?; }
    Ok(())
}
fn check_work(work: &Path) -> Result<(), String> {
    for pin in PINS { verify(work, pin)?; }
    Ok(())
}
fn prepare(capsule: &Path, legacy: &Path, work: &Path) -> Result<(), String> {
    if !work.is_absolute() { return Err("work must be an absolute fresh directory".into()); }
    let parent = work.parent().ok_or("work has no parent")?.canonicalize().map_err(|e| e.to_string())?;
    let resolved = parent.join(work.file_name().ok_or("work has no file name")?);
    for root in [capsule, legacy] {
        if resolved.starts_with(root.canonicalize().map_err(|e| e.to_string())?) { return Err("work must be outside source capsules".into()); }
    }
    fs::DirBuilder::new().mode(0o700).create(&resolved).map_err(|e| format!("work must be new: {e}"))?;
    for pin in PINS {
        let input = verify(&if pin.legacy { legacy.join("harness") } else { capsule.join("source") }, pin)?;
        let output = resolved.join(pin.path);
        fs::create_dir_all(output.parent().ok_or("missing output parent")?).map_err(|e| e.to_string())?;
        fs::copy(input, output).map_err(|e| e.to_string())?;
    }
    check_work(&resolved)
}
fn result(work: &Path, log_path: &Path, rustc_path: &Path) -> Result<String, String> {
    check_work(work)?;
    for path in [log_path, rustc_path] {
        let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
        if !meta.is_file() || meta.nlink() != 1 || meta.len() > 4 * 1024 * 1024 { return Err("invalid bounded result input".into()); }
    }
    let log = fs::read_to_string(log_path).map_err(|e| e.to_string())?;
    if log.matches(SUMMARY).count() != 1 { return Err("all 27 tests must actually pass without filtering or ignoring".into()); }
    let actual: Vec<_> = log.lines().filter_map(|line| line.strip_prefix("test tests::")?.strip_suffix(" ... ok")).collect();
    let unique: BTreeSet<_> = actual.iter().copied().collect();
    let expected: BTreeSet<_> = TESTS.iter().copied().collect();
    if actual.len() != 27 || unique.len() != 27 || unique != expected { return Err("actual test names differ from the complete current library".into()); }
    let rustc = fs::read_to_string(rustc_path).map_err(|e| e.to_string())?;
    if !rustc.trim().starts_with("rustc 1.93.0 ") { return Err("expected pinned Rust 1.93.0".into()); }
    hash(log_path)
}
fn run() -> Result<(), String> {
    let args: Vec<_> = env::args().collect();
    if args.len() < 5 { return Err("usage: source-ci prepare CAPSULE LEGACY_CAPSULE NEW_WORK; or source-ci result CAPSULE LEGACY_CAPSULE WORK LOG RUSTC_VERSION".into()); }
    let mode = args[1].as_str(); let capsule = Path::new(&args[2]); let legacy = Path::new(&args[3]); let work = Path::new(&args[4]);
    check_inputs(capsule, legacy)?;
    let (passed, digest) = match mode {
        "prepare" if args.len() == 5 => { prepare(capsule, legacy, work)?; (0, String::new()) },
        "result" if args.len() == 7 => (27, result(work, Path::new(&args[5]), Path::new(&args[6]))?),
        _ => return Err("unexpected mode or arguments".into()),
    };
    check_inputs(capsule, legacy)?;
    println!("{{\"schema\":\"audio-r12-current-source-ci-v1\",\"mode\":\"{}\",\"source_inputs\":5,\"expected_tests\":27,\"tests_passed\":{},\"failed\":0,\"ignored\":0,\"filtered_out\":0,\"actual_log_sha256\":\"{}\",\"source_bytes_unchanged\":true,\"source_materialized\":false,\"complete_apex_qualified\":false,\"runtime_qualified\":false}}", mode, passed, digest);
    Ok(())
}
fn main() -> ExitCode { match run() { Ok(()) => ExitCode::SUCCESS, Err(e) => { eprintln!("current Audio source verification failed: {e}"); ExitCode::FAILURE } } }
