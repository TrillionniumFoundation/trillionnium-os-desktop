//! Emit an isolated ordinary-pair source patch from an externally SHA-pinned lock.
//!
//! This example does not discover or approve source closure, materialize sources,
//! invoke Soong, or modify the input repository. The caller supplies the reviewed
//! frozen manifest SHA and the pinned superproject receipt SHA. The generated
//! patch still needs normal materialization and all ordinary-pair build gates.

use clap::Parser;
use droidloom_source::{SparseSourceLock, build_plan};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const MAX_INPUT_BYTES: usize = 1024 * 1024;
const BASE_LOCK: &str = "android/manifest/m2-role-ingress-hal-provider-source-lock.json";
const PAIR_LOCK: &str = "android/native-generation-pair/source-lock.json";
const PAIR_SOURCE: &str = "tools/droidloom-update/src/native_generation_pair_build.rs";
const SOURCE_LIB: &str = "tools/droidloom-source/src/lib.rs";
const BASE_SHA: &str = "72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d";
const PREVIOUS_SHA: &str = "94d2a5d2e00d3b5d126752ee58337e71fb88a5763f7b977be4a56471f4e68ee6";
const PAIR_TEMPLATE_SHA: &str = "d512fe696a66c635920c8757497151d7f50841e11d3272137e4dee206eeeee82";
const SOURCE_TEMPLATE: &str = include_str!("../src/lib.rs");

#[derive(Parser)]
#[command(about = "Prepare a detached exact-source patch; never activate it")]
struct Args {
    #[arg(long)]
    repo: PathBuf,
    /// Exact source-lock.json selected by the independent closure review.
    #[arg(long)]
    frozen_manifest: PathBuf,
    /// Out-of-band SHA-256 of the complete frozen source-lock bytes.
    #[arg(long)]
    expected_manifest_sha256: String,
    /// Original superproject.json receipt with gitlinks and .gitmodules bytes.
    #[arg(long)]
    superproject: PathBuf,
    #[arg(long)]
    expected_superproject_sha256: String,
    /// A new directory; existing output is rejected.
    #[arg(long)]
    output: PathBuf,
}

fn need(ok: bool, message: impl Into<String>) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into().into()) }
}

fn digest(bytes: &[u8]) -> String { hex::encode(Sha256::digest(bytes)) }

fn authenticate(bytes: &[u8], expected: &str) -> Result<()> {
    need(bytes.len() <= MAX_INPUT_BYTES, "input exceeds the one-MiB bound")?;
    need(expected.len() == 64 && expected.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "expected SHA-256 must be an explicit lowercase digest")?;
    need(digest(bytes) == expected, "complete input SHA-256 differs from the frozen manifest")
}

fn read_exact(path: &Path, expected: &str) -> Result<Vec<u8>> {
    need(fs::symlink_metadata(path)?.is_file(), "input must be a regular non-symlink file")?;
    let mut bytes = Vec::new();
    fs::File::open(path)?.take((MAX_INPUT_BYTES + 1) as u64).read_to_end(&mut bytes)?;
    authenticate(&bytes, expected)?;
    Ok(bytes)
}

fn projects(value: &Value) -> Result<&Vec<Value>> {
    value["projects"].as_array().ok_or_else(|| "source projects absent".into())
}

fn sparse(value: &Value) -> Result<&[Value]> {
    match value.get("sparse_paths") {
        None => Ok(&[]),
        Some(Value::Array(paths)) => Ok(paths),
        _ => Err("sparse_paths must be an array".into()),
    }
}

/// Retain the existing ordered projects and sparse prefix exactly. The pair's
/// existing append-only validator can therefore represent every generated delta.
fn monotonic(old: &Value, frozen: &Value) -> Result<()> {
    let mut old_header = old.clone();
    let mut new_header = frozen.clone();
    old_header.as_object_mut().ok_or("old lock object absent")?.remove("projects");
    new_header.as_object_mut().ok_or("frozen lock object absent")?.remove("projects");
    need(old_header == new_header, "source policy, links, status, superproject or header drift")?;
    let before = projects(old)?;
    let after = projects(frozen)?;
    need(after.len() >= before.len(), "frozen lock removes existing projects")?;
    for (previous, current) in before.iter().zip(after) {
        let mut left = previous.clone();
        let mut right = current.clone();
        left.as_object_mut().ok_or("previous project object absent")?.remove("sparse_paths");
        right.as_object_mut().ok_or("current project object absent")?.remove("sparse_paths");
        need(left == right, "existing project order, identity, purpose or revision drift")?;
        let old_paths = sparse(previous)?;
        let new_paths = sparse(current)?;
        if old_paths.is_empty() {
            need(previous.get("sparse_paths") == current.get("sparse_paths"),
                "a full existing checkout cannot be changed into a sparse checkout")?;
        } else {
            need(new_paths.starts_with(old_paths),
                "frozen sparse paths must retain the exact existing prefix; no removal, reordering or coalescing")?;
        }
    }
    Ok(())
}

fn source_plan_checks(frozen: &Value) -> Result<SparseSourceLock> {
    let lock: SparseSourceLock = serde_json::from_value(frozen.clone())?;
    let mut paths = BTreeSet::new();
    let mut names = BTreeSet::new();
    need(!lock.projects.is_empty(), "empty project set")?;
    // The new exact project count is not active yet. Validate each project with
    // the existing validator without bypassing any per-project/path policy.
    for project in &lock.projects {
        need(paths.insert(project.path.clone()), "duplicate project path")?;
        need(names.insert(project.name.clone()), "duplicate project repository name")?;
        let mut single = lock.clone();
        single.projects = vec![project.clone()];
        single.links.clear();
        build_plan(&single)?;
        for link in &lock.links {
            need(!link.target.starts_with(&project.path), "new project overlaps an existing root link")?;
        }
    }
    Ok(lock)
}

fn upstream_projects(receipt: &Value, expected_commit: &str) -> Result<BTreeMap<String, (String, String)>> {
    need(receipt["commit"] == expected_commit, "superproject receipt commit drift")?;
    let tree = receipt["gitlinks"].as_str().ok_or("original gitlinks absent")?;
    let modules = receipt["gitmodules"].as_str().ok_or("original .gitmodules absent")?;
    authenticate(tree.as_bytes(), receipt["gitlinks_sha256"].as_str().ok_or("gitlinks SHA absent")?)?;
    authenticate(modules.as_bytes(), receipt["gitmodules_sha256"].as_str().ok_or("gitmodules SHA absent")?)?;
    let mut commits = BTreeMap::new();
    for line in tree.lines() {
        let (metadata, path) = line.split_once('\t').ok_or("malformed original Git tree entry")?;
        let parts: Vec<_> = metadata.split_whitespace().collect();
        need(parts.len() == 3, "malformed original Git metadata")?;
        if parts[0] == "160000" && parts[1] == "commit" {
            need(commits.insert(path.to_owned(), parts[2].to_owned()).is_none(), "duplicate superproject Gitlink")?;
        }
    }
    let mut names = BTreeMap::new();
    let mut path: Option<String> = None;
    let mut url: Option<String> = None;
    let flush = |path: &mut Option<String>, url: &mut Option<String>, names: &mut BTreeMap<String, String>| -> Result<()> {
        if path.is_none() && url.is_none() { return Ok(()); }
        let p = path.take().ok_or("submodule path absent")?;
        let u = url.take().ok_or("submodule URL absent")?;
        // The pinned origin is platform/superproject: ../art resolves to
        // platform/art, while ../../device/... resolves at the Android root.
        let name = if let Some(root) = u.strip_prefix("../../") {
            root.to_owned()
        } else if let Some(platform) = u.strip_prefix("../") {
            format!("platform/{platform}")
        } else { return Err("submodule URL is not official relative Android origin".into()); };
        need(names.insert(p, name).is_none(), "duplicate .gitmodules path")
    };
    for raw in modules.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with(';') { continue; }
        if line.starts_with('[') {
            flush(&mut path, &mut url, &mut names)?;
            need(line.starts_with("[submodule \"") && line.ends_with("\"]"), "unexpected .gitmodules section")?;
        } else if let Some((key, value)) = line.split_once('=') {
            match key.trim() {
                "path" => need(path.replace(value.trim().to_owned()).is_none(), "duplicate submodule path key")?,
                "url" => need(url.replace(value.trim().to_owned()).is_none(), "duplicate submodule URL key")?,
                _ => {},
            }
        } else { return Err("malformed .gitmodules line".into()); }
    }
    flush(&mut path, &mut url, &mut names)?;
    let mut result = BTreeMap::new();
    for (path, commit) in commits {
        let name = names.remove(&path).ok_or("Gitlink has no original .gitmodules name")?;
        result.insert(path, (name, commit));
    }
    Ok(result)
}

#[derive(Debug)]
struct Recipe {
    manifest_sha256: String,
    manifest_bytes: usize,
    project_count: usize,
    project_capacity: usize,
    link_count: usize,
    additions: Vec<Value>,
    sparse_additions: Vec<(String, String, String)>,
    display_sparse_paths: Vec<String>,
}

fn prepare(base_bytes: &[u8], previous_bytes: &[u8], frozen_bytes: &[u8], expected_sha: &str,
           upstream: &Value) -> Result<Recipe> {
    authenticate(base_bytes, BASE_SHA)?;
    authenticate(previous_bytes, PREVIOUS_SHA)?;
    authenticate(frozen_bytes, expected_sha)?;
    let base: Value = serde_json::from_slice(base_bytes)?;
    let previous: Value = serde_json::from_slice(previous_bytes)?;
    let frozen: Value = serde_json::from_slice(frozen_bytes)?;
    need(projects(&base)?.len() == 225 && projects(&previous)?.len() == 268, "historical source counts drifted")?;
    monotonic(&base, &previous)?;
    monotonic(&previous, &frozen)?;
    monotonic(&base, &frozen)?;
    let lock = source_plan_checks(&frozen)?;
    let originals = upstream_projects(upstream, &lock.superproject.commit)?;
    for project in &lock.projects {
        let path = project.path.to_str().ok_or("non-UTF8 project path")?;
        need(originals.get(path) == Some(&(project.name.clone(), project.commit.clone())),
            format!("project is not the exact original superproject name/Gitlink: {path}"))?;
    }
    let mut sparse_additions = Vec::new();
    for (old, new) in projects(&base)?.iter().zip(projects(&frozen)?) {
        for added in &sparse(new)?[sparse(old)?.len()..] {
            sparse_additions.push((old["path"].as_str().ok_or("project path absent")?.to_owned(),
                old["commit"].as_str().ok_or("project commit absent")?.to_owned(),
                added.as_str().ok_or("non-string sparse path")?.to_owned()));
        }
    }
    let display = lock.projects.iter()
        .find(|project| project.path == Path::new("frameworks/hardware/interfaces"))
        .ok_or("frozen display provider project absent")?;
    let display_sparse_paths = display.sparse_paths.iter().map(|path|
        path.to_str().map(str::to_owned).ok_or("non-UTF8 display source path"))
        .collect::<std::result::Result<Vec<_>, _>>()?;
    Ok(Recipe { manifest_sha256: expected_sha.to_owned(), manifest_bytes: frozen_bytes.len(),
        project_count: lock.projects.len(), project_capacity: lock.projects.len().div_ceil(16) * 16,
        link_count: lock.links.len(), additions: projects(&frozen)?[225..].to_vec(), sparse_additions,
        display_sparse_paths })
}

fn replace_once(source: &str, old: &str, new: &str) -> Result<String> {
    need(source.matches(old).count() == 1, format!("exact source edit anchor drift: {old}"))?;
    Ok(source.replacen(old, new, 1))
}

fn render(recipe: &Recipe, pair: &str, lib: &str) -> Result<(String, String)> {
    authenticate(pair.as_bytes(), PAIR_TEMPLATE_SHA)?;
    need(lib == SOURCE_TEMPLATE, "capacity source template drift")?;
    let mut pair = replace_once(pair, "const SOURCE_LOCK_BYTES: usize = 116325;",
        &format!("const SOURCE_LOCK_BYTES: usize = {};", recipe.manifest_bytes))?;
    pair = replace_once(&pair, &format!("const SOURCE_LOCK_SHA: &str = \"{PREVIOUS_SHA}\";"),
        &format!("const SOURCE_LOCK_SHA: &str = \"{}\";", recipe.manifest_sha256))?;
    let begin = pair.find("// Every added project is an original Gitlink").ok_or("provider constant anchor absent")?;
    let end = pair[begin..].find("\n\nfn validate_source_extension").ok_or("provider constant end absent")? + begin;
    let json = serde_json::to_string_pretty(&recipe.additions)?;
    let mut hashes = "#".to_owned();
    while json.contains(&format!("\"{hashes}")) { hashes.push('#'); }
    let additions = format!("// Exact original additions from frozen manifest SHA-256 {}.\n\
        // Closure qualification remains separate from this source attestation.\n\
        const PAIR_ADDITIONS_JSON: &str = r{hashes}\"{json}\"{hashes};", recipe.manifest_sha256);
    pair.replace_range(begin..end, &additions);
    let begin = pair.find("    for (path, commit, subtree) in [").ok_or("sparse delta anchor absent")?;
    let end = pair[begin..].find("    ] {").ok_or("sparse delta end absent")? + begin;
    let mut rows = "    for (path, commit, subtree) in [\n".to_owned();
    for (path, commit, subtree) in &recipe.sparse_additions {
        rows.push_str(&format!("        ({path:?}, {commit:?}, {subtree:?}),\n"));
    }
    pair.replace_range(begin..end, &rows);
    pair = replace_once(&pair, "plan.projects.len() != 268 || plan.links.len() != 8",
        &format!("plan.projects.len() != {} || plan.links.len() != {}", recipe.project_count, recipe.link_count))?;
    pair = replace_once(&pair, "(268, 8, false)",
        &format!("({}, {}, false)", recipe.project_count, recipe.link_count))?;
    // Preserve the exact-vs-generic negative control even when the frozen count
    // exactly fills its minimum aligned capacity; do not add artificial headroom.
    pair = replace_once(&pair, "        unlisted[\"projects\"].as_array_mut().unwrap().push(extra);",
        "        let last = unlisted[\"projects\"].as_array().unwrap().len() - 1;\n        unlisted[\"projects\"][last] = extra;")?;
    // The old positive fixture describes six paths. The frozen extension may
    // append additional exact inputs to this same project; keep the positive
    // assertion exact and keep negative controls aimed at the display input.
    let old_display = "        assert_eq!(paths, &vec![json!(\"devicestate/aidl\"), json!(\"location/altitude/aidl\"),\n            json!(\"sensorservice/aidl\"), json!(\"stats/aidl\"), json!(\"vibrator/aidl\"),\n            json!(\"automotive/display/1.0\")]);";
    let display_values = recipe.display_sparse_paths.iter()
        .map(|path| format!("json!({path:?})")).collect::<Vec<_>>().join(", ");
    pair = replace_once(&pair, old_display, &format!(
        "        assert_eq!(paths, &vec![{display_values}]);\n        let display_index = paths.iter().position(|path| path == \"automotive/display/1.0\").unwrap();"))?;
    pair = replace_once(&pair,
        "            *wider[\"projects\"][index][\"sparse_paths\"].as_array_mut().unwrap().last_mut().unwrap() =\n                json!(replacement);",
        "            wider[\"projects\"][index][\"sparse_paths\"][display_index] = json!(replacement);")?;
    pair = replace_once(&pair,
        "        previous[\"projects\"][index][\"sparse_paths\"].as_array_mut().unwrap().pop();",
        "        previous[\"projects\"][index][\"sparse_paths\"].as_array_mut().unwrap().remove(display_index);")?;
    let mut lib = replace_once(lib, "const NATIVE_SOURCE_PROJECT_COUNT: usize = 268;",
        &format!("const NATIVE_SOURCE_PROJECT_COUNT: usize = {};", recipe.project_count))?;
    lib = replace_once(&lib, "// The current ordinary pair authenticates 268 exact superproject projects.",
        &format!("// The current ordinary pair authenticates {} exact superproject projects.\n// Frozen manifest SHA-256: {}", recipe.project_count, recipe.manifest_sha256))?;
    Ok((pair, lib))
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<()> {
    fs::create_dir_all(path.parent().ok_or("output parent absent")?)?;
    let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

fn main() -> Result<()> {
    let args = Args::parse();
    let base = read_exact(&args.repo.join(BASE_LOCK), BASE_SHA)?;
    let previous = read_exact(&args.repo.join(PAIR_LOCK), PREVIOUS_SHA)?;
    let manifest = read_exact(&args.frozen_manifest, &args.expected_manifest_sha256)?;
    let upstream = read_exact(&args.superproject, &args.expected_superproject_sha256)?;
    let recipe = prepare(&base, &previous, &manifest, &args.expected_manifest_sha256,
        &serde_json::from_slice(&upstream)?)?;
    let pair = read_exact(&args.repo.join(PAIR_SOURCE), PAIR_TEMPLATE_SHA)?;
    let lib = read_exact(&args.repo.join(SOURCE_LIB), &digest(SOURCE_TEMPLATE.as_bytes()))?;
    let (new_pair, new_lib) = render(&recipe, std::str::from_utf8(&pair)?, std::str::from_utf8(&lib)?)?;
    fs::create_dir(&args.output)?;
    let files = [(PAIR_SOURCE, pair.as_slice(), new_pair.as_bytes()),
        (SOURCE_LIB, lib.as_slice(), new_lib.as_bytes()),
        (PAIR_LOCK, previous.as_slice(), manifest.as_slice())];
    let mut patch = Vec::new();
    let mut hashes = BTreeMap::new();
    for (relative, old, new) in files {
        let old_path = args.output.join("base").join(relative);
        let new_path = args.output.join("candidate").join(relative);
        write_new(&old_path, old)?;
        write_new(&new_path, new)?;
        let diff = Command::new("/usr/bin/diff").args(["-u", "--label", &format!("a/{relative}"),
            "--label", &format!("b/{relative}")]).arg(old_path).arg(new_path).output()?;
        need(matches!(diff.status.code(), Some(0 | 1)), "bounded source diff failed")?;
        patch.extend(diff.stdout);
        hashes.insert(relative, json!({"before_sha256": digest(old), "after_sha256": digest(new)}));
    }
    write_new(&args.output.join("frozen-source.patch"), &patch)?;
    let receipt = json!({"schema":"native-frozen-source-recipe-v1", "state":"DETACHED_PATCH_ONLY",
        "frozen_manifest_sha256":recipe.manifest_sha256, "manifest_bytes":recipe.manifest_bytes,
        "superproject_receipt_sha256":args.expected_superproject_sha256,
        "projects":recipe.project_count, "minimum_16_aligned_project_capacity":recipe.project_capacity,
        "links":recipe.link_count, "maximum_sparse_paths":288, "files":hashes,
        "patch_sha256":digest(&patch), "source_changes":0, "source_closure_qualified":false,
        "normal_materialization_qualified":false, "Soong_invocations":0,
        "native_pair_artifact_qualified":false, "runtime_qualified":false});
    write_new(&args.output.join("recipe.json"), &serde_json::to_vec_pretty(&receipt)?)?;
    println!("{}", serde_json::to_string_pretty(&receipt)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    const BASE: &[u8] = include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json");
    const PREVIOUS: &[u8] = include_bytes!("../../../android/native-generation-pair/source-lock.json");

    fn previous() -> Value { serde_json::from_slice(PREVIOUS).unwrap() }

    #[test]
    fn existing_exact_extension_is_retained() {
        authenticate(BASE, BASE_SHA).unwrap();
        authenticate(PREVIOUS, PREVIOUS_SHA).unwrap();
        monotonic(&serde_json::from_slice(BASE).unwrap(), &previous()).unwrap();
        monotonic(&previous(), &previous()).unwrap();
        let lock = source_plan_checks(&previous()).unwrap();
        assert_eq!(lock.projects.len(), 268);
        assert_eq!(lock.projects.len().div_ceil(16) * 16, 272);
    }

    #[test]
    fn frozen_bytes_reject_whitespace_drift_wrong_sha_and_over_budget() {
        let mut changed = PREVIOUS.to_vec(); changed.push(b'\n');
        assert!(authenticate(&changed, PREVIOUS_SHA).is_err());
        assert!(authenticate(PREVIOUS, BASE_SHA).is_err());
        assert!(authenticate(PREVIOUS, "not-a-digest").is_err());
        let too_big = vec![b'x'; MAX_INPUT_BYTES + 1];
        assert!(authenticate(&too_big, &digest(&too_big)).is_err());
    }

    #[test]
    fn monotonicity_rejects_header_project_revision_and_sparse_loss() {
        let good = previous();
        for field in ["status", "selected_at", "remote_base"] {
            let mut bad = good.clone(); bad[field] = json!("drift");
            assert!(monotonic(&good, &bad).is_err());
        }
        for field in ["commit", "name", "path", "purpose"] {
            let mut bad = good.clone(); bad["projects"][0][field] = json!("drift");
            assert!(monotonic(&good, &bad).is_err());
        }
        let mut bad = good.clone(); bad["projects"].as_array_mut().unwrap().pop();
        assert!(monotonic(&good, &bad).is_err());
        let mut bad = good.clone(); bad["projects"][0]["sparse_paths"] = json!(["unrelated"]);
        assert!(monotonic(&good, &bad).is_err());
        let mut bad = good.clone(); bad["projects"].as_array_mut().unwrap().swap(0, 1);
        assert!(monotonic(&good, &bad).is_err());
    }

    #[test]
    fn appended_providers_do_not_allow_duplicates_escapes_or_289_cones() {
        let good = previous();
        let mut duplicate = good.clone();
        duplicate["projects"].as_array_mut().unwrap().push(good["projects"][0].clone());
        assert!(source_plan_checks(&duplicate).is_err());
        for sparse in [json!(["../outside"]), json!(["same", "same"]),
            json!((0..289).map(|i| format!("inputs/{i}")).collect::<Vec<_>>())] {
            let mut bad = good.clone(); bad["projects"][0]["sparse_paths"] = sparse;
            assert!(source_plan_checks(&bad).is_err());
        }
        let mut bad = good; bad["projects"][0]["unexpected"] = json!(true);
        assert!(source_plan_checks(&bad).is_err());
    }

    #[test]
    fn original_superproject_mapping_rejects_name_commit_and_payload_drift() {
        let tree = "160000 commit 1111111111111111111111111111111111111111\texternal/sample\n160000 commit 2222222222222222222222222222222222222222\tdevice/sample\n";
        let modules = "[submodule \"external/sample\"]\n\tpath = external/sample\n\turl = ../external/sample\n[submodule \"device/sample\"]\n\tpath = device/sample\n\turl = ../../device/sample\n";
        let good = json!({"commit":"superproject", "gitlinks":tree, "gitlinks_sha256":digest(tree.as_bytes()),
            "gitmodules":modules, "gitmodules_sha256":digest(modules.as_bytes())});
        let originals = upstream_projects(&good, "superproject").unwrap();
        assert_eq!(originals["external/sample"], ("platform/external/sample".to_owned(), "1".repeat(40)));
        assert_eq!(originals["device/sample"], ("device/sample".to_owned(), "2".repeat(40)));
        assert!(upstream_projects(&good, "different").is_err());
        let mut bad = good.clone(); bad["gitlinks"] = json!(format!("{tree}\n"));
        assert!(upstream_projects(&bad, "superproject").is_err());
        let mut bad = good; bad["gitmodules_sha256"] = json!("0".repeat(64));
        assert!(upstream_projects(&bad, "superproject").is_err());
    }

    #[test]
    fn stale_or_repeated_patch_anchors_are_rejected() {
        assert!(replace_once("missing", "old", "new").is_err());
        assert!(replace_once("old old", "old", "new").is_err());
    }
}
