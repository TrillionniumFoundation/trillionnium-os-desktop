//! Emit an isolated ordinary-pair source patch from an externally SHA-pinned lock.
//!
//! This example does not discover or approve source closure, materialize sources,
//! invoke Soong, or modify the input repository. The caller supplies the reviewed
//! frozen manifest SHA and the pinned superproject receipt SHA. The generated
//! patch still needs normal materialization and all ordinary-pair build gates.

use clap::Parser;
use droidloom_source::SparseSourceLock;
use droidloom_source::native_pair::build_plan;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const MAX_INPUT_BYTES: usize = 1024 * 1024;
const BASE_LOCK: &str = "android/manifest/m2-role-ingress-hal-provider-source-lock.json";
const PAIR_LOCK: &str = "android/native-generation-pair/source-lock.json";
const PAIR_SOURCE: &str = "tools/droidloom-update/src/native_generation_pair_build.rs";
const SOURCE_PROFILE: &str = "tools/droidloom-source/src/native_pair.rs";
const BASE_SHA: &str = "72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d";
const PREVIOUS_SHA: &str = "e07f2fac7e7a22c331cffc9a37d57706d64a4550165823afb2ef65c12b0d4a40";
const PAIR_TEMPLATE_SHA: &str = "865adbcca0ec52931c7d7fed6e0df41844fb76ab33f046ce83bdf68d7806282d";
const PROFILE_TEMPLATE: &str = include_str!("../src/native_pair.rs");
const PREVIOUS_PROJECT_COUNT: usize = 645;
const MAX_SPARSE_PATHS: usize = 336;

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
    if ok {
        Ok(())
    } else {
        Err(message.into().into())
    }
}

fn digest(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn authenticate(bytes: &[u8], expected: &str) -> Result<()> {
    need(
        bytes.len() <= MAX_INPUT_BYTES,
        "input exceeds the one-MiB bound",
    )?;
    need(
        expected.len() == 64
            && expected
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "expected SHA-256 must be an explicit lowercase digest",
    )?;
    need(
        digest(bytes) == expected,
        "complete input SHA-256 differs from the frozen manifest",
    )
}

fn read_exact(path: &Path, expected: &str) -> Result<Vec<u8>> {
    need(
        fs::symlink_metadata(path)?.is_file(),
        "input must be a regular non-symlink file",
    )?;
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take((MAX_INPUT_BYTES + 1) as u64)
        .read_to_end(&mut bytes)?;
    authenticate(&bytes, expected)?;
    Ok(bytes)
}

fn projects(value: &Value) -> Result<&Vec<Value>> {
    value["projects"]
        .as_array()
        .ok_or_else(|| "source projects absent".into())
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
    old_header
        .as_object_mut()
        .ok_or("old lock object absent")?
        .remove("projects");
    new_header
        .as_object_mut()
        .ok_or("frozen lock object absent")?
        .remove("projects");
    need(
        old_header == new_header,
        "source policy, links, status, superproject or header drift",
    )?;
    let before = projects(old)?;
    let after = projects(frozen)?;
    need(
        after.len() >= before.len(),
        "frozen lock removes existing projects",
    )?;
    for (previous, current) in before.iter().zip(after) {
        let mut left = previous.clone();
        let mut right = current.clone();
        left.as_object_mut()
            .ok_or("previous project object absent")?
            .remove("sparse_paths");
        right
            .as_object_mut()
            .ok_or("current project object absent")?
            .remove("sparse_paths");
        need(
            left == right,
            "existing project order, identity, purpose or revision drift",
        )?;
        let old_paths = sparse(previous)?;
        let new_paths = sparse(current)?;
        if old_paths.is_empty() {
            need(
                previous.get("sparse_paths") == current.get("sparse_paths"),
                "a full existing checkout cannot be changed into a sparse checkout",
            )?;
        } else {
            need(
                new_paths.starts_with(old_paths),
                "frozen sparse paths must retain the exact existing prefix; no removal, reordering or coalescing",
            )?;
        }
    }
    Ok(())
}

fn source_plan_checks(frozen: &Value) -> Result<SparseSourceLock> {
    let lock: SparseSourceLock = serde_json::from_value(frozen.clone())?;
    // The current Native profile has room through 656 projects. A larger or
    // wider closure needs an independently reviewed profile change first.
    // Validate the whole plan, including root links and cross-project policy.
    build_plan(&lock)?;
    Ok(lock)
}

fn upstream_projects(
    receipt: &Value,
    expected_commit: &str,
) -> Result<BTreeMap<String, (String, String)>> {
    need(
        receipt["commit"] == expected_commit,
        "superproject receipt commit drift",
    )?;
    let tree = receipt["gitlinks"]
        .as_str()
        .ok_or("original gitlinks absent")?;
    let modules = receipt["gitmodules"]
        .as_str()
        .ok_or("original .gitmodules absent")?;
    authenticate(
        tree.as_bytes(),
        receipt["gitlinks_sha256"]
            .as_str()
            .ok_or("gitlinks SHA absent")?,
    )?;
    authenticate(
        modules.as_bytes(),
        receipt["gitmodules_sha256"]
            .as_str()
            .ok_or("gitmodules SHA absent")?,
    )?;
    let mut commits = BTreeMap::new();
    for line in tree.lines() {
        let (metadata, path) = line
            .split_once('\t')
            .ok_or("malformed original Git tree entry")?;
        let parts: Vec<_> = metadata.split_whitespace().collect();
        need(parts.len() == 3, "malformed original Git metadata")?;
        if parts[0] == "160000" && parts[1] == "commit" {
            need(
                commits
                    .insert(path.to_owned(), parts[2].to_owned())
                    .is_none(),
                "duplicate superproject Gitlink",
            )?;
        }
    }
    let mut names = BTreeMap::new();
    let mut path: Option<String> = None;
    let mut url: Option<String> = None;
    let flush = |path: &mut Option<String>,
                 url: &mut Option<String>,
                 names: &mut BTreeMap<String, String>|
     -> Result<()> {
        if path.is_none() && url.is_none() {
            return Ok(());
        }
        let p = path.take().ok_or("submodule path absent")?;
        let u = url.take().ok_or("submodule URL absent")?;
        // The pinned origin is platform/superproject: ../art resolves to
        // platform/art, while ../../device/... resolves at the Android root.
        let name = if let Some(root) = u.strip_prefix("../../") {
            root.to_owned()
        } else if let Some(platform) = u.strip_prefix("../") {
            format!("platform/{platform}")
        } else {
            return Err("submodule URL is not official relative Android origin".into());
        };
        need(
            names.insert(p, name).is_none(),
            "duplicate .gitmodules path",
        )
    };
    for raw in modules.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with(';') {
            continue;
        }
        if line.starts_with('[') {
            flush(&mut path, &mut url, &mut names)?;
            need(
                line.starts_with("[submodule \"") && line.ends_with("\"]"),
                "unexpected .gitmodules section",
            )?;
        } else if let Some((key, value)) = line.split_once('=') {
            match key.trim() {
                "path" => need(
                    path.replace(value.trim().to_owned()).is_none(),
                    "duplicate submodule path key",
                )?,
                "url" => need(
                    url.replace(value.trim().to_owned()).is_none(),
                    "duplicate submodule URL key",
                )?,
                _ => {}
            }
        } else {
            return Err("malformed .gitmodules line".into());
        }
    }
    flush(&mut path, &mut url, &mut names)?;
    let mut result = BTreeMap::new();
    for (path, commit) in commits {
        let name = names
            .remove(&path)
            .ok_or("Gitlink has no original .gitmodules name")?;
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
    sparse_additions: Vec<(usize, usize, Vec<Value>)>,
}

fn prepare(
    base_bytes: &[u8],
    previous_bytes: &[u8],
    frozen_bytes: &[u8],
    expected_sha: &str,
    upstream: &Value,
) -> Result<Recipe> {
    authenticate(base_bytes, BASE_SHA)?;
    authenticate(previous_bytes, PREVIOUS_SHA)?;
    authenticate(frozen_bytes, expected_sha)?;
    let base: Value = serde_json::from_slice(base_bytes)?;
    let previous: Value = serde_json::from_slice(previous_bytes)?;
    let frozen: Value = serde_json::from_slice(frozen_bytes)?;
    need(
        projects(&base)?.len() == 225 && projects(&previous)?.len() == PREVIOUS_PROJECT_COUNT,
        "historical source counts drifted",
    )?;
    monotonic(&base, &previous)?;
    monotonic(&previous, &frozen)?;
    monotonic(&base, &frozen)?;
    let lock = source_plan_checks(&frozen)?;
    let originals = upstream_projects(upstream, &lock.superproject.commit)?;
    for project in &lock.projects {
        let path = project.path.to_str().ok_or("non-UTF8 project path")?;
        need(
            originals.get(path) == Some(&(project.name.clone(), project.commit.clone())),
            format!("project is not the exact original superproject name/Gitlink: {path}"),
        )?;
    }
    let mut sparse_additions = Vec::new();
    for (index, (old, new)) in projects(&previous)?
        .iter()
        .zip(projects(&frozen)?)
        .enumerate()
    {
        let before = sparse(old)?.len();
        let added = &sparse(new)?[before..];
        if !added.is_empty() {
            sparse_additions.push((index, before, added.to_vec()));
        }
    }
    Ok(Recipe {
        manifest_sha256: expected_sha.to_owned(),
        manifest_bytes: frozen_bytes.len(),
        project_count: lock.projects.len(),
        project_capacity: lock.projects.len().div_ceil(16) * 16,
        link_count: lock.links.len(),
        additions: projects(&frozen)?[PREVIOUS_PROJECT_COUNT..].to_vec(),
        sparse_additions,
    })
}

fn replace_once(source: &str, old: &str, new: &str) -> Result<String> {
    need(
        source.matches(old).count() == 1,
        format!("exact source edit anchor drift: {old}"),
    )?;
    Ok(source.replacen(old, new, 1))
}

fn rust_json(value: &impl serde::Serialize) -> Result<String> {
    // A quoted Rust string also escapes every delimiter that could appear in
    // reviewed JSON; no user-controlled text becomes Rust syntax.
    Ok(format!("{:?}", serde_json::to_string(value)?))
}

fn render(recipe: &Recipe, pair: &str, profile: &str) -> Result<(String, String)> {
    authenticate(pair.as_bytes(), PAIR_TEMPLATE_SHA)?;
    need(profile == PROFILE_TEMPLATE, "Native profile template drift")?;
    let mut pair = replace_once(
        pair,
        "const SOURCE_LOCK_BYTES: usize = 369917;",
        &format!(
            "const SOURCE_LOCK_BYTES: usize = {};",
            recipe.manifest_bytes
        ),
    )?;
    pair = replace_once(
        &pair,
        &format!("const SOURCE_LOCK_SHA: &str = \"{PREVIOUS_SHA}\";"),
        &format!(
            "const SOURCE_LOCK_SHA: &str = \"{}\";",
            recipe.manifest_sha256
        ),
    )?;
    if !recipe.additions.is_empty() || !recipe.sparse_additions.is_empty() {
        // Keep every historical validator intact. The new layer removes only
        // the exact reviewed suffixes, then checks the complete current645
        // predecessor through its existing validation chain.
        let signature =
            "fn validate_source_extension(base: &Value, extended: &Value) -> Result<()> {";
        pair = replace_once(
            &pair,
            signature,
            "fn validate_source_extension645(base: &Value, extended: &Value) -> Result<()> {",
        )?;
        let additions = rust_json(&recipe.additions)?;
        let sparse = rust_json(&recipe.sparse_additions)?;
        let validator = format!(
            r#"
// Exact append-only extension from frozen manifest SHA-256 {sha}.
// Source identity does not qualify materialization, Soong or runtime behavior.
fn validate_source_extension(base: &Value, extended: &Value) -> Result<()> {{
    let additions: Vec<Value> = serde_json::from_str({additions})?;
    let sparse: Vec<(usize, usize, Vec<Value>)> = serde_json::from_str({sparse})?;
    let mut previous = extended.clone();
    let projects = previous["projects"].as_array_mut().ok_or("frozen projects absent")?;
    if projects.len() != {count} || projects.get({previous}..) != Some(additions.as_slice()) {{
        return fail("frozen project suffix differs from the reviewed extension");
    }}
    projects.truncate({previous});
    for (index, before, added) in sparse {{
        let paths = projects.get_mut(index).and_then(|project| project.get_mut("sparse_paths"))
            .and_then(Value::as_array_mut).ok_or("frozen sparse project absent")?;
        if paths.get(before..) != Some(added.as_slice()) {{
            return fail("frozen sparse suffix differs from the reviewed extension");
        }}
        paths.truncate(before);
    }}
    validate_source_extension645(base, &previous)
}}

"#,
            sha = recipe.manifest_sha256,
            count = recipe.project_count,
            previous = PREVIOUS_PROJECT_COUNT
        );
        let anchor = "/// Explicit consumers of the complete Native profile select this monotonic provider extension.";
        pair = replace_once(&pair, anchor, &format!("{validator}{anchor}"))?;
    }
    pair = replace_once(
        &pair,
        "plan.projects.len() != 645 || plan.links.len() != 8",
        &format!(
            "plan.projects.len() != {} || plan.links.len() != {}",
            recipe.project_count, recipe.link_count
        ),
    )?;
    // Only the current positive fixture changes; the old 607/642/643 fixtures
    // and their immutable source hashes remain untouched.
    pair = replace_once(
        &pair,
        "(645,8,false)",
        &format!("({},8,false)", recipe.project_count),
    )?;
    let mut profile = replace_once(
        profile,
        "const NATIVE_SOURCE_PROJECT_COUNT: usize = 645;",
        &format!(
            "const NATIVE_SOURCE_PROJECT_COUNT: usize = {};",
            recipe.project_count
        ),
    )?;
    profile = replace_once(
        &profile,
        "assert_eq!(build_plan(&native).unwrap().projects.len(), 645);",
        &format!(
            "assert_eq!(build_plan(&native).unwrap().projects.len(), {});",
            recipe.project_count
        ),
    )?;
    Ok((pair, profile))
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
    let recipe = prepare(
        &base,
        &previous,
        &manifest,
        &args.expected_manifest_sha256,
        &serde_json::from_slice(&upstream)?,
    )?;
    let pair = read_exact(&args.repo.join(PAIR_SOURCE), PAIR_TEMPLATE_SHA)?;
    let profile = read_exact(
        &args.repo.join(SOURCE_PROFILE),
        &digest(PROFILE_TEMPLATE.as_bytes()),
    )?;
    let (new_pair, new_profile) = render(
        &recipe,
        std::str::from_utf8(&pair)?,
        std::str::from_utf8(&profile)?,
    )?;
    fs::create_dir(&args.output)?;
    let files = [
        (PAIR_SOURCE, pair.as_slice(), new_pair.as_bytes()),
        (SOURCE_PROFILE, profile.as_slice(), new_profile.as_bytes()),
        (PAIR_LOCK, previous.as_slice(), manifest.as_slice()),
    ];
    let mut patch = Vec::new();
    let mut hashes = BTreeMap::new();
    for (relative, old, new) in files {
        let old_path = args.output.join("base").join(relative);
        let new_path = args.output.join("candidate").join(relative);
        write_new(&old_path, old)?;
        write_new(&new_path, new)?;
        let diff = Command::new("/usr/bin/diff")
            .args([
                "-u",
                "--label",
                &format!("a/{relative}"),
                "--label",
                &format!("b/{relative}"),
            ])
            .arg(old_path)
            .arg(new_path)
            .output()?;
        need(
            matches!(diff.status.code(), Some(0 | 1)),
            "bounded source diff failed",
        )?;
        patch.extend(diff.stdout);
        hashes.insert(
            relative,
            json!({"before_sha256": digest(old), "after_sha256": digest(new)}),
        );
    }
    write_new(&args.output.join("frozen-source.patch"), &patch)?;
    let receipt = json!({"schema":"native-frozen-source-recipe-v1", "state":"DETACHED_PATCH_ONLY",
        "frozen_manifest_sha256":recipe.manifest_sha256, "manifest_bytes":recipe.manifest_bytes,
        "superproject_receipt_sha256":args.expected_superproject_sha256,
        "projects":recipe.project_count, "minimum_16_aligned_project_capacity":recipe.project_capacity,
        "links":recipe.link_count, "maximum_sparse_paths":MAX_SPARSE_PATHS, "files":hashes,
        "patch_sha256":digest(&patch), "source_changes":0, "source_closure_qualified":false,
        "normal_materialization_qualified":false, "Soong_invocations":0,
        "native_pair_artifact_qualified":false, "runtime_qualified":false});
    write_new(
        &args.output.join("recipe.json"),
        &serde_json::to_vec_pretty(&receipt)?,
    )?;
    println!("{}", serde_json::to_string_pretty(&receipt)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    const BASE: &[u8] =
        include_bytes!("../../../android/manifest/m2-role-ingress-hal-provider-source-lock.json");
    const PREVIOUS: &[u8] =
        include_bytes!("../../../android/native-generation-pair/source-lock.json");
    const PAIR: &str = include_str!("../../droidloom-update/src/native_generation_pair_build.rs");

    fn previous() -> Value {
        serde_json::from_slice(PREVIOUS).unwrap()
    }

    // These bytes are deliberately synthetic behavior-test input, not an
    // independently fetched superproject receipt or source-closure evidence.
    fn synthetic_receipt(lock: &Value) -> Value {
        let mut tree = String::new();
        let mut modules = String::new();
        for project in projects(lock).unwrap() {
            let path = project["path"].as_str().unwrap();
            let commit = project["commit"].as_str().unwrap();
            let name = project["name"].as_str().unwrap();
            let url = match name.strip_prefix("platform/") {
                Some(name) => format!("../{name}"),
                None => format!("../../{name}"),
            };
            tree.push_str(&format!("160000 commit {commit}\t{path}\n"));
            modules.push_str(&format!(
                "[submodule \"{path}\"]\n\tpath = {path}\n\turl = {url}\n"
            ));
        }
        json!({"commit":lock["superproject"]["commit"], "gitlinks_sha256":digest(tree.as_bytes()),
            "gitmodules_sha256":digest(modules.as_bytes()), "gitlinks":tree, "gitmodules":modules})
    }

    #[test]
    fn existing_exact_extension_is_retained() {
        authenticate(BASE, BASE_SHA).unwrap();
        authenticate(PREVIOUS, PREVIOUS_SHA).unwrap();
        monotonic(&serde_json::from_slice(BASE).unwrap(), &previous()).unwrap();
        monotonic(&previous(), &previous()).unwrap();
        let lock = source_plan_checks(&previous()).unwrap();
        assert_eq!(lock.projects.len(), 645);
        assert_eq!(lock.projects.len().div_ceil(16) * 16, 656);
    }

    #[test]
    fn frozen_bytes_reject_whitespace_drift_wrong_sha_and_over_budget() {
        let mut changed = PREVIOUS.to_vec();
        changed.push(b'\n');
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
            let mut bad = good.clone();
            bad[field] = json!("drift");
            assert!(monotonic(&good, &bad).is_err());
        }
        for field in ["commit", "name", "path", "purpose"] {
            let mut bad = good.clone();
            bad["projects"][0][field] = json!("drift");
            assert!(monotonic(&good, &bad).is_err());
        }
        let mut bad = good.clone();
        bad["projects"].as_array_mut().unwrap().pop();
        assert!(monotonic(&good, &bad).is_err());
        let mut bad = good.clone();
        bad["projects"][0]["sparse_paths"] = json!(["unrelated"]);
        assert!(monotonic(&good, &bad).is_err());
        let mut bad = good.clone();
        bad["projects"].as_array_mut().unwrap().swap(0, 1);
        assert!(monotonic(&good, &bad).is_err());
    }

    #[test]
    fn appended_providers_do_not_allow_duplicates_escapes_or_337_cones() {
        let good = previous();
        let mut duplicate = good.clone();
        duplicate["projects"]
            .as_array_mut()
            .unwrap()
            .push(good["projects"][0].clone());
        assert!(source_plan_checks(&duplicate).is_err());
        for sparse in [
            json!(["../outside"]),
            json!(["same", "same"]),
            json!((0..337).map(|i| format!("inputs/{i}")).collect::<Vec<_>>()),
        ] {
            let mut bad = good.clone();
            bad["projects"][0]["sparse_paths"] = sparse;
            assert!(source_plan_checks(&bad).is_err());
        }
        let mut bad = good;
        bad["projects"][0]["unexpected"] = json!(true);
        assert!(source_plan_checks(&bad).is_err());
    }

    #[test]
    fn complete_plan_keeps_project_capacity_and_root_link_checks() {
        let mut oversized = previous();
        for index in 0..12 {
            let mut project = oversized["projects"][0].clone();
            project["path"] = json!(format!("tools/recipe_fixture_{index}"));
            project["name"] = json!(format!("platform/tools/recipe_fixture_{index}"));
            oversized["projects"].as_array_mut().unwrap().push(project);
        }
        assert!(
            source_plan_checks(&oversized)
                .unwrap_err()
                .to_string()
                .contains("1 through 656")
        );
        let mut overlapping = previous();
        let mut project = overlapping["projects"][0].clone();
        project["path"] = json!("build");
        project["name"] = json!("platform/tools/recipe_fixture");
        overlapping["projects"]
            .as_array_mut()
            .unwrap()
            .push(project);
        assert!(
            source_plan_checks(&overlapping)
                .unwrap_err()
                .to_string()
                .contains("link target")
        );
    }

    #[test]
    fn current645_recipe_renders_the_real_profile_without_a_delta() {
        let recipe = prepare(
            BASE,
            PREVIOUS,
            PREVIOUS,
            PREVIOUS_SHA,
            &synthetic_receipt(&previous()),
        )
        .unwrap();
        assert_eq!(
            (
                recipe.project_count,
                recipe.project_capacity,
                recipe.link_count
            ),
            (645, 656, 8)
        );
        assert!(recipe.additions.is_empty());
        assert!(recipe.sparse_additions.is_empty());
        let (pair, profile) = render(&recipe, PAIR, PROFILE_TEMPLATE).unwrap();
        assert_eq!(pair, PAIR);
        assert_eq!(profile, PROFILE_TEMPLATE);
        assert!(render(&recipe, &format!("{PAIR}\n"), PROFILE_TEMPLATE).is_err());
        assert!(render(&recipe, PAIR, &format!("{PROFILE_TEMPLATE}\n")).is_err());
    }

    #[test]
    fn bounded_extension_preserves_the_history_and_edits_only_native_profile() {
        let mut frozen = previous();
        let index = projects(&frozen)
            .unwrap()
            .iter()
            .position(|p| !sparse(p).unwrap().is_empty())
            .unwrap();
        frozen["projects"][index]["sparse_paths"]
            .as_array_mut()
            .unwrap()
            .push(json!("recipe-fixture-cone"));
        let mut extra = frozen["projects"][0].clone();
        extra["path"] = json!("tools/recipe_fixture");
        extra["name"] = json!("platform/tools/recipe_fixture");
        frozen["projects"].as_array_mut().unwrap().push(extra);
        let bytes = serde_json::to_vec_pretty(&frozen).unwrap();
        let recipe = prepare(
            BASE,
            PREVIOUS,
            &bytes,
            &digest(&bytes),
            &synthetic_receipt(&frozen),
        )
        .unwrap();
        assert_eq!((recipe.project_count, recipe.project_capacity), (646, 656));
        assert_eq!(recipe.additions.len(), 1);
        assert_eq!(recipe.sparse_additions.len(), 1);
        let (pair, profile) = render(&recipe, PAIR, PROFILE_TEMPLATE).unwrap();
        let begin = PAIR.find("// Exact original additions").unwrap();
        let end = PAIR.find("fn validate_source_extension(base:").unwrap();
        assert!(
            pair.contains(&PAIR[begin..end]),
            "all earlier validators must remain byte-identical"
        );
        assert!(pair.contains("fn validate_source_extension645(base:"));
        assert!(pair.contains("validate_source_extension645(base, &previous)"));
        assert!(pair.contains("plan.projects.len() != 646 || plan.links.len() != 8"));
        assert!(profile.contains("const NATIVE_SOURCE_PROJECT_COUNT: usize = 646;"));
        assert!(profile.contains("const MAX_SPARSE_PATHS: usize = 336;"));
        assert!(!pair.contains("recipe_fixture_1"));
        for field in ["name", "commit"] {
            let mut wrong_origin = frozen.clone();
            wrong_origin["projects"][0][field] = json!(if field == "name" {
                "platform/tools/different"
            } else {
                "1111111111111111111111111111111111111111"
            });
            assert!(
                prepare(
                    BASE,
                    PREVIOUS,
                    &bytes,
                    &digest(&bytes),
                    &synthetic_receipt(&wrong_origin)
                )
                .is_err()
            );
        }
    }

    #[test]
    fn original_superproject_mapping_rejects_name_commit_and_payload_drift() {
        let tree = "160000 commit 1111111111111111111111111111111111111111\texternal/sample\n160000 commit 2222222222222222222222222222222222222222\tdevice/sample\n";
        let modules = "[submodule \"external/sample\"]\n\tpath = external/sample\n\turl = ../external/sample\n[submodule \"device/sample\"]\n\tpath = device/sample\n\turl = ../../device/sample\n";
        let good = json!({"commit":"superproject", "gitlinks":tree, "gitlinks_sha256":digest(tree.as_bytes()),
            "gitmodules":modules, "gitmodules_sha256":digest(modules.as_bytes())});
        let originals = upstream_projects(&good, "superproject").unwrap();
        assert_eq!(
            originals["external/sample"],
            ("platform/external/sample".to_owned(), "1".repeat(40))
        );
        assert_eq!(
            originals["device/sample"],
            ("device/sample".to_owned(), "2".repeat(40))
        );
        assert!(upstream_projects(&good, "different").is_err());
        let mut bad = good.clone();
        bad["gitlinks"] = json!(format!("{tree}\n"));
        assert!(upstream_projects(&bad, "superproject").is_err());
        let mut bad = good;
        bad["gitmodules_sha256"] = json!("0".repeat(64));
        assert!(upstream_projects(&bad, "superproject").is_err());
    }

    #[test]
    fn stale_or_repeated_patch_anchors_are_rejected() {
        assert!(replace_once("missing", "old", "new").is_err());
        assert!(replace_once("old old", "old", "new").is_err());
    }
}
