//! Check retained inputs and replay exact changes before executing source tests.
//! Host evidence and application contracts do not grant Android runtime credit.
#![deny(unsafe_code)]

use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::os::unix::fs::{DirBuilderExt, MetadataExt};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, ExitCode};

type Result<T> = std::result::Result<T, String>;

fn string<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value.get(key).and_then(Value::as_str).ok_or_else(|| format!("missing string {key}"))
}

fn number(value: &Value, key: &str) -> Result<u64> {
    value.get(key).and_then(Value::as_u64).ok_or_else(|| format!("missing unsigned integer {key}"))
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn regular(root: &Path, relative: &str) -> Result<PathBuf> {
    let root_meta = fs::symlink_metadata(root).map_err(|e| e.to_string())?;
    if !root_meta.is_dir() || root_meta.file_type().is_symlink() {
        return Err("input root is not a real directory".into());
    }
    let rel = Path::new(relative);
    if relative.is_empty() || rel.is_absolute() || relative.contains('\\')
        || !rel.components().all(|c| matches!(c, Component::Normal(_)))
        || rel.components().count() != relative.split('/').count()
    {
        return Err(format!("unsafe relative path: {relative}"));
    }
    let mut path = root.to_path_buf();
    let parts: Vec<_> = rel.components().collect();
    for (index, part) in parts.iter().enumerate() {
        path.push(part.as_os_str());
        let meta = fs::symlink_metadata(&path).map_err(|e| format!("{relative}: {e}"))?;
        if meta.file_type().is_symlink() || (index + 1 < parts.len() && !meta.is_dir()) {
            return Err(format!("aliased or non-directory path: {relative}"));
        }
        if index + 1 == parts.len() && (!meta.is_file() || meta.nlink() != 1) {
            return Err(format!("input is not a single-link regular file: {relative}"));
        }
    }
    Ok(path)
}

fn read(root: &Path, relative: &str) -> Result<Vec<u8>> {
    fs::read(regular(root, relative)?).map_err(|e| e.to_string())
}

fn read_json(root: &Path, relative: &str) -> Result<Value> {
    serde_json::from_slice(&read(root, relative)?).map_err(|e| e.to_string())
}

fn check_pin(root: &Path, pin: &Value) -> Result<Vec<u8>> {
    let path = string(pin, "path")?;
    let bytes = read(root, path)?;
    if bytes.len() as u64 != number(pin, "bytes")? || digest(&bytes) != string(pin, "sha256")? {
        return Err(format!("input content differs: {path}"));
    }
    Ok(bytes)
}

fn inventory(root: &Path, here: &Path, files: &mut BTreeSet<String>) -> Result<()> {
    for entry in fs::read_dir(here).map_err(|e| e.to_string())? {
        let path = entry.map_err(|e| e.to_string())?.path();
        let meta = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
        if meta.file_type().is_symlink() {
            return Err(format!("symlink in retained tree: {}", path.display()));
        }
        if meta.is_dir() {
            inventory(root, &path, files)?;
        } else if meta.is_file() && meta.nlink() == 1 {
            let relative = path.strip_prefix(root).map_err(|e| e.to_string())?.to_str()
                .ok_or("non-UTF-8 retained path")?.to_string();
            files.insert(relative);
        } else {
            return Err(format!("unexpected retained file type: {}", path.display()));
        }
    }
    Ok(())
}

fn exact_manifest(capsule: &Path) -> Result<usize> {
    let manifest = read_json(capsule, "FILES.json")?;
    let files = manifest.get("files").and_then(Value::as_object).ok_or("missing file inventory")?;
    let mut expected: BTreeSet<String> = files.keys().cloned().collect();
    expected.insert("FILES.json".into());
    let mut actual = BTreeSet::new();
    inventory(capsule, capsule, &mut actual)?;
    if actual != expected {
        return Err(format!("capsule membership differs: missing={:?}, extra={:?}",
            expected.difference(&actual).collect::<Vec<_>>(), actual.difference(&expected).collect::<Vec<_>>()));
    }
    for (relative, expected) in files {
        let bytes = read(capsule, relative)?;
        if bytes.len() as u64 != number(expected, "bytes")? || digest(&bytes) != string(expected, "sha256")? {
            return Err(format!("retained file differs: {relative}"));
        }
    }
    Ok(files.len())
}

fn apply_patch(root: &Path, patch: &Path, check: bool) -> Result<()> {
    let mut command = Command::new("/usr/bin/git");
    command.arg("-C").arg(root).arg("apply");
    if check { command.arg("--check"); }
    let out = command.arg("--whitespace=nowarn").arg("--").arg(patch).output().map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(format!("exact patch replay failed: {}", String::from_utf8_lossy(&out.stderr)));
    }
    Ok(())
}

fn control_sources(repo: &Path, capsule: &Path, source: &Value) -> Result<usize> {
    let child = capsule.join("control-deadline");
    let binding = read_json(&child, "SOURCE_BINDING.json")?;
    let origin = "75492962a9b9afdd6b9f28fec979b9c40419ec0b";
    if string(&binding, "origin_commit")? != origin {
        return Err("control dependency workspace origin differs".into());
    }
    false_flag(&binding, "runtime_qualified")?;
    false_flag(&binding, "production_ready")?;
    let files = array(&binding, "files")?;
    if files.len() != 48 { return Err("control requires its complete 48-file source closure".into()); }
    let before = check_pin(repo, &source["before"])?;
    let after = check_pin(capsule, &source["after"])?;
    let target = "runtime/droidloom-supervisor/src/control.rs";
    if read(&child, &format!("preimage/{target}"))? != before {
        return Err("control's retained preimage differs from the published Settings source".into());
    }
    let mut expected = BTreeSet::new();
    let mut modified = 0;
    for pin in files {
        let path = string(pin, "path")?;
        let relative = path.strip_prefix("source/").ok_or("source binding escapes its subtree")?;
        if !expected.insert(relative.to_string()) || string(pin, "repository_path")? != relative
            || string(pin, "origin_commit")? != origin {
            return Err("duplicate or mismatched control dependency binding".into());
        }
        let bytes = check_pin(&child, pin)?;
        match pin.get("modified").and_then(Value::as_bool) {
            Some(true) => {
                modified += 1;
                if relative != target || bytes != after || number(pin, "origin_bytes")? != before.len() as u64
                    || string(pin, "origin_sha256")? != digest(&before) {
                    return Err("unreviewed change in the complete supervisor source closure".into());
                }
            }
            Some(false) => {
                if number(pin, "origin_bytes")? != bytes.len() as u64 || string(pin, "origin_sha256")? != digest(&bytes) {
                    return Err(format!("unchanged original dependency differs: {relative}"));
                }
            }
            None => return Err("source binding lacks explicit modification state".into()),
        }
    }
    let root = child.join("source");
    let mut actual = BTreeSet::new();
    inventory(&root, &root, &mut actual)?;
    if modified != 1 || actual != expected {
        return Err("complete supervisor source inventory or delta differs".into());
    }
    Ok(files.len())
}

fn replay(repo: &Path, capsule: &Path, out: &Path) -> Result<Value> {
    let file_count = exact_manifest(capsule)?;
    let pins = read_json(capsule, "SOURCE-PINS.json")?;
    let sources = pins.get("sources").and_then(Value::as_array).ok_or("missing source pins")?;
    if sources.len() != 2 { return Err("exactly two reviewed source changes are required".into()); }
    fs::DirBuilder::new().mode(0o700).create(out).map_err(|e| format!("replay output must be new: {e}"))?;
    let mut records = Vec::new();
    let mut names = BTreeSet::new();
    for source in sources {
        let name = string(source, "name")?;
        if !name.bytes().all(|b| b.is_ascii_lowercase() || b == b'-') || !names.insert(name.to_string()) {
            return Err("duplicate or invalid source scope".into());
        }
        let before = check_pin(repo, &source["before"])?;
        let after = check_pin(capsule, &source["after"])?;
        check_pin(capsule, &source["patch"])?;
        let relative = string(source, "target")?;
        if relative != "runtime/droidloom-supervisor/src/production_readiness.rs"
            && relative != "runtime/droidloom-supervisor/src/control.rs" {
            return Err("unreviewed patch target".into());
        }
        let tree = out.join(name);
        let target = tree.join(relative);
        fs::create_dir_all(target.parent().ok_or("missing target parent")?).map_err(|e| e.to_string())?;
        fs::write(&target, &before).map_err(|e| e.to_string())?;
        let patch = regular(capsule, string(&source["patch"], "path")?)?.canonicalize().map_err(|e| e.to_string())?;
        apply_patch(&tree, &patch, true)?;
        apply_patch(&tree, &patch, false)?;
        let mut actual = BTreeSet::new();
        inventory(&tree, &tree, &mut actual)?;
        if actual != BTreeSet::from([relative.to_string()]) || read(&tree, relative)? != after {
            return Err(format!("patch output differs from the delivered source: {name}"));
        }
        records.push(json!({"name": name, "patch_sha256": string(&source["patch"], "sha256")?, "verified_source_bytes": after.len()}));
    }
    if names != BTreeSet::from(["readiness-snapshot".to_string(), "control-deadline".to_string()]) {
        return Err("the two expected source changes are required".into());
    }
    let control = sources.iter().find(|value| value["name"] == "control-deadline").ok_or("control source missing")?;
    let control_files = control_sources(repo, capsule, control)?;
    Ok(json!({"schema": "pocket4-e3df-exact-source-replay-v1", "retained_files": file_count,
        "source_changes": records, "control_source_files": control_files,
        "runtime_qualified": false, "android_starts": 0}))
}

fn tests(capsule: &Path, readiness: &Path, control: &Path) -> Result<Value> {
    let expected = read_json(capsule, "EXPECTED-TESTS.json")?;
    let mut records = Vec::new();
    for (scope, path, count) in [("readiness", readiness, 5_usize), ("control_deadline", control, 6_usize)] {
        let wanted = expected.get(scope).and_then(Value::as_array).ok_or("missing expected test names")?;
        let mut wanted_names = BTreeMap::new();
        for name in wanted { wanted_names.insert(name.as_str().ok_or("invalid test name")?.to_string(), 1_usize); }
        if wanted_names.len() != count || wanted.len() != count { return Err(format!("unexpected test inventory: {scope}")); }
        let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
        let mut observed = BTreeMap::new();
        for line in text.lines() {
            if let Some(name) = line.strip_prefix("test ").and_then(|s| s.strip_suffix(" ... ok")) {
                *observed.entry(name.to_string()).or_insert(0_usize) += 1;
            }
        }
        let prefix = format!("test result: ok. {count} passed; 0 failed; 0 ignored; 0 measured;");
        let summaries: Vec<_> = text.lines().filter(|line| line.starts_with("test result:")).collect();
        if observed != wanted_names || summaries.len() != 1 || !summaries[0].starts_with(&prefix) {
            return Err(format!("exact executed test names/count differ: {scope}"));
        }
        records.push(json!({"scope": scope, "passed": count, "log_sha256": digest(text.as_bytes())}));
    }
    Ok(json!({"schema": "pocket4-e3df-executed-source-tests-v1", "tests": records,
        "runtime_qualified": false, "android_starts": 0}))
}

fn array<'a>(value: &'a Value, key: &str) -> Result<&'a Vec<Value>> {
    value.get(key).and_then(Value::as_array).ok_or_else(|| format!("missing array {key}"))
}

fn false_flag(value: &Value, key: &str) -> Result<()> {
    if value.get(key) != Some(&Value::Bool(false)) {
        return Err(format!("non-runtime candidate must retain false {key}"));
    }
    Ok(())
}

fn string_set(values: &[Value]) -> Result<BTreeSet<String>> {
    let mut names = BTreeSet::new();
    for value in values {
        let name = value.as_str().filter(|v| !v.is_empty()).ok_or("invalid string member")?;
        if !names.insert(name.to_string()) { return Err(format!("duplicate string member: {name}")); }
    }
    Ok(names)
}

fn reference(pin: &Value, references: &mut BTreeMap<String, (u64, String)>) -> Result<()> {
    let path = string(pin, "path")?;
    let sha = string(pin, "sha256")?;
    let bytes = number(pin, "bytes")?;
    if !Path::new(path).is_absolute() || path.contains('\0') || path.contains('\n')
        || sha.len() != 64 || !sha.bytes().all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v)) {
        return Err("invalid retained host reference".into());
    }
    let binding = (bytes, sha.to_string());
    if let Some(previous) = references.insert(path.to_string(), binding.clone()) {
        if previous != binding { return Err(format!("conflicting retained host reference: {path}")); }
    }
    // This validates only the binding. The host path is intentionally never opened.
    Ok(())
}

fn applications(capsule: &Path) -> Result<Value> {
    let root = capsule.join("application-candidates");
    let raw = read(&root, "CANDIDATE42.json")?;
    let catalog: Value = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    let q = read_json(&root, "QUALIFICATION.json")?;
    if string(&catalog, "schema")? != "final-selected-42-production-application-candidates-v1"
        || string(&q, "schema")? != "pocket4-application-candidate-reconciliation-qualification-v1" {
        return Err("unknown application contract schema".into());
    }
    let pin = &q["candidate_manifest"];
    if string(pin, "relative_path")? != "CANDIDATE42.json" || number(pin, "bytes")? != raw.len() as u64
        || string(pin, "sha256")? != digest(&raw) || pin["schema"] != catalog["schema"] {
        return Err("application qualification names a different candidate manifest".into());
    }
    for key in ["production_ready", "runtime_qualified", "canonical_selector_modified", "current_modified"] {
        false_flag(&q, key)?;
    }
    for key in ["new_runtime_accepted_count", "installs", "uninstalls", "Android_actions", "new_signature_verifier_executions_in_this_revision"] {
        if number(&q, key)? != 0 { return Err(format!("unexpected application execution claim: {key}")); }
    }
    false_flag(&catalog, "production_ready")?;
    if number(&catalog, "new_runtime_accepted_count")? != 0
        || number(&catalog, "installed_or_uninstalled_by_this_manifest")? != 0
        || number(&catalog, "final_selected_denominator")? != 42
        || number(&q, "candidate_count")? != 42 || number(&q, "complete_candidate_gate_contracts")? != 42 {
        return Err("candidate count or zero-runtime boundary differs".into());
    }
    let common: BTreeSet<_> = ["identity", "lifecycle", "stability", "data_permissions", "release_scope", "ui_observation"]
        .into_iter().map(String::from).collect();
    if string_set(array(&q, "required_common_gates")?)? != common {
        return Err("common acceptance contract changed".into());
    }
    let required = string_set(array(&q, "required_packages")?)?;
    let candidates = array(&catalog, "selected_candidates")?;
    if required.len() != 42 || candidates.len() != 42 { return Err("exactly 42 candidates are required".into()); }
    let mut packages = BTreeSet::new();
    let mut official = BTreeMap::new();
    let mut business_gates = 0;
    let mut references = BTreeMap::new();
    for candidate in candidates {
        let package = string(candidate, "package")?;
        if package.split('.').any(|part| part.is_empty()) || !packages.insert(package.to_string()) {
            return Err(format!("duplicate or invalid package: {package}"));
        }
        if string_set(array(candidate, "common_gate_ids")?)? != common {
            return Err(format!("missing common gates: {package}"));
        }
        let business = candidate.get("business_gate_definitions").and_then(Value::as_object).ok_or("missing business gates")?;
        if business.is_empty() || business.iter().any(|(name, description)| name.is_empty()
            || description.as_str().is_none_or(|text| text.trim().is_empty())) {
            return Err(format!("incomplete business gate definitions: {package}"));
        }
        business_gates += business.len();
        let acceptance = &candidate["new_runtime_acceptance"];
        false_flag(acceptance, "accepted")?;
        if string(acceptance, "state")? != "NOT_RUN" || !array(acceptance, "evidence")?.is_empty()
            || !acceptance["cohort"].is_null() {
            return Err(format!("unexpected runtime evidence promotion: {package}"));
        }
        if package == "org.mozilla.firefox" {
            let actual: BTreeSet<_> = business.keys().cloned().collect();
            if actual.len() != 6 || actual != string_set(array(&q, "firefox_business_gates")?)? {
                return Err("Firefox business gate contract differs".into());
            }
        }
        if let Some(proposed) = candidate.get("proposed_official_input") {
            if string(proposed, "package")? != package { return Err("official input package differs".into()); }
            for key in ["runtime_accepted", "production_ready", "selected_in_canonical_selector", "installed_by_this_revision"] {
                false_flag(proposed, key)?;
            }
            reference(&proposed["artifact"], &mut references)?;
            reference(&proposed["source_catalog"], &mut references)?;
            for evidence in array(proposed, "retained_evidence_readback")? { reference(evidence, &mut references)?; }
            let signers = string_set(array(proposed, "signer_certificate_sha256")?)?;
            if signers.is_empty() || signers.iter().any(|sha| sha.len() != 64
                || !sha.bytes().all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))) {
                return Err("invalid retained signer fingerprint".into());
            }
            official.insert(package.to_string(), proposed);
        }
    }
    if packages != required || official.len() != 13 || number(&q, "complete_signed_inputs_reconciled")? != 13 {
        return Err("package or official-input inventory differs".into());
    }
    let qualifications = array(&q, "input_qualifications")?;
    if qualifications.len() != 13 { return Err("exactly 13 retained input qualifications are required".into()); }
    let mut qualified_packages = BTreeSet::new();
    let mut apk_bytes = 0_u64;
    let mut referenced_evidence = 0_u64;
    let mut rebound = 0_u64;
    for input in qualifications {
        let package = string(input, "package")?;
        if !qualified_packages.insert(package.to_string()) { return Err("duplicate input qualification".into()); }
        let proposed = official.get(package).ok_or("qualification has no candidate")?;
        for key in ["artifact", "source_catalog", "signer_certificate_sha256", "version_name", "version_code", "native_abis", "canonical_custody"] {
            if input.get(key).is_none() || input.get(key) != proposed.get(key) {
                return Err(format!("retained source binding differs: {package}/{key}"));
            }
        }
        let count = array(proposed, "retained_evidence_readback")?.len() as u64;
        if number(input, "evidence_files_read_back")? != count { return Err("host evidence count differs".into()); }
        referenced_evidence += count;
        rebound += number(input, "retired_staging_references_rebound")?;
        apk_bytes += number(&input["artifact"], "bytes")?;
    }
    if apk_bytes != number(&q, "full_APK_bytes_read_back")?
        || rebound != number(&q, "retired_staging_source_references_rebound_by_exact_size_and_sha256")? {
        return Err("host receipt totals differ".into());
    }
    reference(&q["base_selector"], &mut references)?;
    reference(&q["retained_host_review"], &mut references)?;
    Ok(json!({"schema": "pocket4-e3df-application-contract-check-v1", "unique_candidates": packages.len(),
        "common_gates_per_candidate": common.len(), "business_gate_definitions": business_gates,
        "official_input_bindings": official.len(), "retained_evidence_references": referenced_evidence,
        "distinct_host_references": references.len(), "host_reported_APK_bytes": apk_bytes,
        "APK_bytes_opened_on_runner": 0, "signature_verifier_executions_on_runner": 0,
        "runtime_acceptances": 0, "runtime_qualified": false, "canonical_selector_modified": false}))
}

fn run() -> Result<Value> {
    let args: Vec<_> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("replay") if args.len() == 5 => replay(Path::new(&args[2]), Path::new(&args[3]), Path::new(&args[4])),
        Some("tests") if args.len() == 5 => tests(Path::new(&args[2]), Path::new(&args[3]), Path::new(&args[4])),
        Some("inventory") if args.len() == 3 => Ok(json!({"verified_files": exact_manifest(Path::new(&args[2]))?, "runtime_qualified": false})),
        Some("applications") if args.len() == 3 => applications(Path::new(&args[2])),
        _ => Err("usage: qualify replay REPO CAPSULE NEW_OUTPUT | tests CAPSULE READINESS_LOG CONTROL_LOG | inventory CAPSULE | applications CAPSULE".into()),
    }
}

fn main() -> ExitCode {
    match run() {
        Ok(value) => { println!("{value}"); ExitCode::SUCCESS }
        Err(error) => { eprintln!("qualification rejected: {error}"); ExitCode::FAILURE }
    }
}
