//! Exact-commit sparse AOSP source materialization.
//!
//! This tool intentionally does not invoke an unrestricted repo sync. It
//! accepts only a bounded lock whose projects are pinned to Git commits from
//! one AOSP superproject, fetches those commits into a staging directory,
//! verifies every resulting HEAD, creates the manifest-declared root links,
//! and then publishes the source tree atomically.

#![forbid(unsafe_code)]

use std::collections::BTreeSet;
use std::ffi::OsStr;
use std::fs;
use std::io::{self, BufReader, Write as _};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tempfile::Builder;
use thiserror::Error;

const MAX_LOCK_BYTES: u64 = 1024 * 1024;
// This independent audio builder consumes the exact pinned audio lock below.
// Keep the smallest finite 16-project boundary; URL/commit/path checks remain.
const AUDIO_SOURCE_PROJECT_COUNT: usize = 430;
const MAX_PROJECTS: usize = AUDIO_SOURCE_PROJECT_COUNT.div_ceil(16) * 16;
const MAX_LINKS: usize = 64;
// The fixed original-provider closure retains 355 exact CTS paths.
// 368 is its smallest 16-aligned bound. Do not truncate or coalesce
// paths, or relax the unchanged URL, revision, normalization and duplicate checks.
const MAX_SPARSE_PATHS: usize = 368;
const OFFICIAL_REMOTE: &str = "https://android.googlesource.com/";

/// Exact sparse-source lock selected for one milestone.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SparseSourceLock {
    /// Lock schema revision.
    pub schema_version: u32,
    /// Human-readable selection date.
    pub selected_at: String,
    /// Closure maturity; a seed must not be represented as build-proven.
    pub status: String,
    /// Upstream URL prefix applied to project names.
    pub remote_base: String,
    /// AOSP superproject that authenticates every project Gitlink.
    pub superproject: SuperprojectLock,
    /// Fail-closed source expansion policy.
    pub policy: SparsePolicy,
    /// Root links otherwise supplied by the AOSP repo manifest.
    #[serde(default)]
    pub links: Vec<RootLink>,
    /// Exact projects in the current closure.
    pub projects: Vec<SparseProject>,
}

/// Immutable AOSP superproject identity.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SuperprojectLock {
    /// Android Git project name.
    pub name: String,
    /// Auditable source ref used when the lock was generated.
    #[serde(rename = "ref")]
    pub source_ref: String,
    /// Exact superproject commit.
    pub commit: String,
}

/// Policy preventing accidental expansion into a full AOSP checkout.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
#[allow(
    clippy::struct_excessive_bools,
    reason = "the lock keeps each fail-closed source policy independently auditable"
)]
pub struct SparsePolicy {
    /// Must remain false.
    pub allow_unrestricted_repo_sync: bool,
    /// Must remain true.
    pub require_exact_commits: bool,
    /// Must remain true.
    pub add_dependencies_only_from_superproject: bool,
    /// Must remain true while reusing the verified CI base.
    pub base_partitions_come_from_aosp_ci_artifact: bool,
}

/// One exact upstream project.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SparseProject {
    /// Checkout-relative path.
    pub path: PathBuf,
    /// Android Git project name below the official remote.
    pub name: String,
    /// Exact 40-digit lowercase Git commit.
    pub commit: String,
    /// Why this project belongs in the closure.
    pub purpose: String,
    /// Optional project-relative directories checked out in Git cone mode.
    #[serde(default)]
    pub sparse_paths: Vec<PathBuf>,
}

/// One root link copied from the pinned repo manifest.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RootLink {
    /// Source-tree-relative existing path.
    pub source: PathBuf,
    /// Source-tree-relative link to create.
    pub target: PathBuf,
}

/// Network-free exact materialization plan.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MaterializationPlan {
    /// Schema revision.
    pub schema_version: u32,
    /// Exact AOSP superproject commit.
    pub superproject_commit: String,
    /// Ordered project fetches.
    pub projects: Vec<PlannedProject>,
    /// Ordered root links created after checkout.
    pub links: Vec<RootLink>,
    /// Explicit proof that this is not an unrestricted repo checkout.
    pub unrestricted_repo_sync: bool,
}

/// One immutable project fetch.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PlannedProject {
    /// Checkout-relative path.
    pub path: PathBuf,
    /// Exact Android Git URL.
    pub url: String,
    /// Exact commit to fetch and verify.
    pub commit: String,
    /// Auditable inclusion reason.
    pub purpose: String,
    /// Optional project-relative directories checked out in Git cone mode.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub sparse_paths: Vec<PathBuf>,
}

/// Manifest written beside a successfully materialized source tree.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MaterializedManifest {
    /// Manifest schema revision.
    pub schema_version: u32,
    /// SHA-256 of the source lock that drove materialization.
    pub source_lock_sha256: String,
    /// Fully validated immutable plan.
    pub plan: MaterializationPlan,
}

/// Invalid input, local I/O, or exact Git operation failure.
#[derive(Debug, Error)]
pub enum SourceError {
    /// Filesystem operation failed.
    #[error("{context}: {source}")]
    Io {
        /// Operation context.
        context: String,
        /// Underlying I/O error.
        source: io::Error,
    },
    /// Lock JSON was malformed.
    #[error("invalid sparse source lock {path}: {source}")]
    Json {
        /// Lock path.
        path: PathBuf,
        /// JSON parser failure.
        source: serde_json::Error,
    },
    /// One or more lock invariants failed.
    #[error("invalid sparse source lock: {}", .0.join("; "))]
    Invalid(Vec<String>),
    /// An exact Git operation failed.
    #[error("command {program} failed ({status}): {stderr}")]
    Command {
        /// Program name.
        program: String,
        /// Exit status rendering.
        status: String,
        /// Bounded stderr.
        stderr: String,
    },
    /// A checked-out HEAD did not match its lock.
    #[error("project {path} resolved to {actual}, expected {expected}")]
    RevisionMismatch {
        /// Project checkout path.
        path: PathBuf,
        /// Expected exact commit.
        expected: String,
        /// Actual HEAD.
        actual: String,
    },
}

/// Read a bounded sparse lock.
///
/// # Errors
///
/// Rejects oversized, unreadable, or malformed JSON input.
pub fn load_lock(path: &Path) -> Result<SparseSourceLock, SourceError> {
    let metadata = fs::metadata(path).map_err(|source| io_error("stat source lock", source))?;
    if metadata.len() > MAX_LOCK_BYTES {
        return Err(SourceError::Invalid(vec![format!(
            "lock is {} bytes; maximum is {MAX_LOCK_BYTES}",
            metadata.len()
        )]));
    }
    let bytes = fs::read(path).map_err(|source| io_error("read source lock", source))?;
    serde_json::from_slice(&bytes).map_err(|source| SourceError::Json {
        path: path.to_path_buf(),
        source,
    })
}

/// Validate the sparse policy and return a deterministic, network-free plan.
///
/// # Errors
///
/// Returns every structural or source-expansion policy violation discovered.
pub fn build_plan(lock: &SparseSourceLock) -> Result<MaterializationPlan, SourceError> {
    let mut problems = Vec::new();
    validate_header(lock, &mut problems);
    validate_projects(lock, &mut problems);
    validate_links(lock, &mut problems);
    if !problems.is_empty() {
        return Err(SourceError::Invalid(problems));
    }

    Ok(MaterializationPlan {
        schema_version: 1,
        superproject_commit: lock.superproject.commit.clone(),
        projects: lock
            .projects
            .iter()
            .map(|project| PlannedProject {
                path: project.path.clone(),
                url: format!("{}{}", lock.remote_base, project.name),
                commit: project.commit.clone(),
                purpose: project.purpose.clone(),
                sparse_paths: project.sparse_paths.clone(),
            })
            .collect(),
        links: lock.links.clone(),
        unrestricted_repo_sync: false,
    })
}

fn validate_header(lock: &SparseSourceLock, problems: &mut Vec<String>) {
    if lock.schema_version != 1 {
        problems.push(format!(
            "unsupported schema version {}",
            lock.schema_version
        ));
    }
    if lock.selected_at.trim().is_empty() {
        problems.push("selected_at must not be empty".into());
    }
    if lock.status != "seed_not_yet_build_proven" && lock.status != "build_proven" {
        problems.push(format!("unknown closure status {:?}", lock.status));
    }
    if lock.remote_base != OFFICIAL_REMOTE {
        problems.push(format!("remote_base must be {OFFICIAL_REMOTE}"));
    }
    if lock.superproject.name != "platform/superproject" {
        problems.push("superproject must be platform/superproject".into());
    }
    if !lock
        .superproject
        .source_ref
        .starts_with("refs/heads/android-")
    {
        problems.push("superproject ref must be a named Android release ref".into());
    }
    if !is_commit(&lock.superproject.commit) {
        problems.push("superproject commit must be exact lowercase SHA-1".into());
    }
    if lock.policy.allow_unrestricted_repo_sync {
        problems.push("unrestricted repo sync must remain disabled".into());
    }
    if !lock.policy.require_exact_commits
        || !lock.policy.add_dependencies_only_from_superproject
        || !lock.policy.base_partitions_come_from_aosp_ci_artifact
    {
        problems.push("all fail-closed sparse-source policy flags must remain enabled".into());
    }
}

fn validate_projects(lock: &SparseSourceLock, problems: &mut Vec<String>) {
    if lock.projects.is_empty() || lock.projects.len() > MAX_PROJECTS {
        problems.push(format!(
            "projects must contain 1 through {MAX_PROJECTS} entries"
        ));
    }
    let mut paths = BTreeSet::new();
    let mut names = BTreeSet::new();
    for project in &lock.projects {
        if !is_normal_relative(&project.path) {
            problems.push(format!(
                "project path {} is not normalized and relative",
                project.path.display()
            ));
        }
        if !paths.insert(project.path.clone()) {
            problems.push(format!("duplicate project path {}", project.path.display()));
        }
        if !is_project_name(&project.name) {
            problems.push(format!("invalid Android project name {:?}", project.name));
        }
        if !names.insert(project.name.clone()) {
            problems.push(format!("duplicate Android project {:?}", project.name));
        }
        if !is_commit(&project.commit) {
            problems.push(format!(
                "project {} does not use an exact lowercase SHA-1",
                project.path.display()
            ));
        }
        if project.purpose.trim().is_empty() || project.purpose.len() > 255 {
            problems.push(format!(
                "project {} has an empty or oversized purpose",
                project.path.display()
            ));
        }
        if project.sparse_paths.len() > MAX_SPARSE_PATHS {
            problems.push(format!(
                "project {} has more than {MAX_SPARSE_PATHS} sparse paths",
                project.path.display()
            ));
        }
        let mut sparse_paths = BTreeSet::new();
        for sparse_path in &project.sparse_paths {
            if !is_normal_relative(sparse_path) {
                problems.push(format!(
                    "project {} sparse path {} is not normalized and relative",
                    project.path.display(),
                    sparse_path.display()
                ));
            }
            if !sparse_paths.insert(sparse_path) {
                problems.push(format!(
                    "project {} repeats sparse path {}",
                    project.path.display(),
                    sparse_path.display()
                ));
            }
        }
    }
}

fn validate_links(lock: &SparseSourceLock, problems: &mut Vec<String>) {
    if lock.links.len() > MAX_LINKS {
        problems.push(format!("links exceed the {MAX_LINKS}-entry bound"));
    }
    let project_paths: Vec<&Path> = lock
        .projects
        .iter()
        .map(|project| project.path.as_path())
        .collect();
    let mut targets = BTreeSet::new();
    for link in &lock.links {
        if !is_normal_relative(&link.source) || !is_normal_relative(&link.target) {
            problems.push("root link paths must be normalized and relative".into());
        }
        if !project_paths
            .iter()
            .any(|project| link.source.starts_with(project))
        {
            problems.push(format!(
                "link source {} is not inside a selected project",
                link.source.display()
            ));
        }
        if project_paths
            .iter()
            .any(|project| link.target == *project || link.target.starts_with(project))
        {
            problems.push(format!(
                "link target {} overlaps a selected project",
                link.target.display()
            ));
        }
        if !targets.insert(link.target.clone()) {
            problems.push(format!("duplicate root link {}", link.target.display()));
        }
    }
}

/// Fetch, verify, link, and atomically publish one sparse source tree.
///
/// The output must not exist. A failure before publication removes the staging
/// directory and never exposes a partial source tree at the destination.
///
/// # Errors
///
/// Returns for invalid locks, existing output, Git failures, revision mismatch,
/// missing link sources, or local I/O errors.
pub fn materialize(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    let plan = build_plan(lock)?;
    if destination.exists() {
        return Err(SourceError::Invalid(vec![format!(
            "destination {} already exists",
            destination.display()
        )]));
    }
    let parent = destination
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent).map_err(|source| io_error("create output parent", source))?;
    let staging = Builder::new()
        .prefix(".droidloom-source-")
        .tempdir_in(parent)
        .map_err(|source| io_error("create source staging directory", source))?;

    for project in &plan.projects {
        materialize_project(staging.path(), project)?;
    }
    for link in &plan.links {
        create_root_link(staging.path(), link)?;
    }

    let manifest = MaterializedManifest {
        schema_version: 1,
        source_lock_sha256: sha256_file(lock_path)?,
        plan,
    };
    let json = serde_json::to_vec_pretty(&manifest)
        .map_err(|error| SourceError::Invalid(vec![format!("serialize manifest: {error}")]))?;
    fs::write(staging.path().join(".droidloom-source-manifest.json"), json)
        .map_err(|source| io_error("write materialized manifest", source))?;
    fs::rename(staging.path(), destination)
        .map_err(|source| io_error("publish sparse source tree atomically", source))?;
    Ok(manifest)
}

/// Reconcile a verified materialization with an expanded exact source lock.
///
/// Existing projects must be clean and still resolve to the same URL and
/// commit recorded by the new plan. The new plan must be a strict extension of
/// the published manifest: reconciliation never changes or removes an input.
/// A sparse project may add explicitly locked paths at the same commit; it may
/// not drop a previously materialized sparse path.
/// Each missing project is staged and renamed independently, so interruption
/// leaves either a complete exact checkout or no checkout at that path. The
/// manifest is replaced atomically only after the complete tree verifies.
///
/// # Errors
///
/// Returns for an unrecognized destination, a non-monotonic plan change,
/// dirty/mismatched existing projects, Git failures, or invalid root links.
pub fn reconcile(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    let plan = build_plan(lock)?;
    let old_manifest_path = destination.join(".droidloom-source-manifest.json");
    let old_bytes = fs::read(&old_manifest_path)
        .map_err(|source| io_error("read existing materialized manifest", source))?;
    let old = serde_json::from_slice::<MaterializedManifest>(&old_bytes).map_err(|source| {
        SourceError::Json {
            path: old_manifest_path,
            source,
        }
    })?;
    validate_plan_extension(&old.plan, &plan)?;

    for project in &plan.projects {
        let checkout = destination.join(&project.path);
        if checkout.exists() {
            verify_project(&checkout, project)?;
            apply_sparse_checkout(&checkout, project)?;
            verify_project(&checkout, project)?;
        } else {
            install_missing_project(destination, project)?;
            verify_project(&checkout, project)?;
        }
    }
    for link in &plan.links {
        ensure_root_link(destination, link)?;
    }

    let manifest = MaterializedManifest {
        schema_version: 1,
        source_lock_sha256: sha256_file(lock_path)?,
        plan,
    };
    write_manifest_atomically(destination, &manifest)?;
    Ok(manifest)
}

/// Verify a published source tree against the current exact lock without
/// fetching or modifying it.
///
/// # Errors
///
/// Returns when the manifest does not exactly match the lock, a project is
/// dirty or has the wrong origin/commit, or a declared root link is missing or
/// points somewhere else.
pub fn verify_materialized(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    let expected_plan = build_plan(lock)?;
    let manifest_path = destination.join(".droidloom-source-manifest.json");
    let bytes = fs::read(&manifest_path)
        .map_err(|source| io_error("read materialized manifest", source))?;
    let manifest = serde_json::from_slice::<MaterializedManifest>(&bytes).map_err(|source| {
        SourceError::Json {
            path: manifest_path,
            source,
        }
    })?;

    let mut problems = Vec::new();
    if manifest.schema_version != 1 {
        problems.push("materialized manifest is not schema version 1".into());
    }
    if manifest.source_lock_sha256 != sha256_file(lock_path)? {
        problems.push("materialized manifest source-lock hash does not match".into());
    }
    if manifest.plan != expected_plan {
        problems.push("materialized manifest plan does not exactly match the lock".into());
    }
    if !problems.is_empty() {
        return Err(SourceError::Invalid(problems));
    }

    for project in &manifest.plan.projects {
        verify_project(&destination.join(&project.path), project)?;
    }
    for link in &manifest.plan.links {
        verify_root_link(destination, link)?;
    }
    Ok(manifest)
}

fn validate_plan_extension(
    old: &MaterializationPlan,
    new: &MaterializationPlan,
) -> Result<(), SourceError> {
    let mut problems = Vec::new();
    if old.schema_version != 1 || old.unrestricted_repo_sync {
        problems.push("existing manifest is not a bounded schema-v1 plan".into());
    }
    if old.superproject_commit != new.superproject_commit {
        problems.push("reconciliation cannot change the AOSP superproject commit".into());
    }
    for project in &old.projects {
        let replacement = new.projects.iter().find(|candidate| {
            candidate.path == project.path
                && candidate.url == project.url
                && candidate.commit == project.commit
                && candidate.purpose == project.purpose
        });
        let compatible = replacement.is_some_and(|candidate| {
            candidate.sparse_paths == project.sparse_paths
                || project.sparse_paths.is_empty()
                || project
                    .sparse_paths
                    .iter()
                    .all(|path| candidate.sparse_paths.contains(path))
        });
        if !compatible {
            problems.push(format!(
                "reconciliation cannot change or remove project {} or its existing sparse paths",
                project.path.display()
            ));
        }
    }
    for link in &old.links {
        if !new.links.contains(link) {
            problems.push(format!(
                "reconciliation cannot change or remove root link {}",
                link.target.display()
            ));
        }
    }
    if problems.is_empty() {
        Ok(())
    } else {
        Err(SourceError::Invalid(problems))
    }
}

fn verify_project(checkout: &Path, project: &PlannedProject) -> Result<(), SourceError> {
    let head = run_git_output(checkout, &[OsStr::new("rev-parse"), OsStr::new("HEAD")])?;
    let actual = String::from_utf8_lossy(&head.stdout).trim().to_owned();
    if actual != project.commit {
        return Err(SourceError::RevisionMismatch {
            path: project.path.clone(),
            expected: project.commit.clone(),
            actual,
        });
    }
    let remote = run_git_output(
        checkout,
        &[
            OsStr::new("remote"),
            OsStr::new("get-url"),
            OsStr::new("origin"),
        ],
    )?;
    if String::from_utf8_lossy(&remote.stdout).trim() != project.url {
        return Err(SourceError::Invalid(vec![format!(
            "project {} origin does not match {}",
            project.path.display(),
            project.url
        )]));
    }
    let status = run_git_output(checkout, &[OsStr::new("status"), OsStr::new("--porcelain")])?;
    if !status.stdout.is_empty() {
        return Err(SourceError::Invalid(vec![format!(
            "project {} has local changes",
            project.path.display()
        )]));
    }
    Ok(())
}

fn install_missing_project(root: &Path, project: &PlannedProject) -> Result<(), SourceError> {
    let parent = root
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let staging = Builder::new()
        .prefix(".droidloom-project-")
        .tempdir_in(parent)
        .map_err(|source| io_error("create project staging directory", source))?;
    materialize_project(staging.path(), project)?;
    let checkout = root.join(&project.path);
    let checkout_parent = checkout
        .parent()
        .ok_or_else(|| SourceError::Invalid(vec!["project path has no parent".into()]))?;
    fs::create_dir_all(checkout_parent)
        .map_err(|source| io_error("create missing project parent", source))?;
    fs::rename(staging.path().join(&project.path), &checkout)
        .map_err(|source| io_error("publish exact project atomically", source))?;
    Ok(())
}

fn ensure_root_link(root: &Path, link: &RootLink) -> Result<(), SourceError> {
    let target = root.join(&link.target);
    match fs::symlink_metadata(&target) {
        Ok(_) => verify_root_link(root, link),
        Err(error) if error.kind() == io::ErrorKind::NotFound => create_root_link(root, link),
        Err(error) => Err(io_error("stat existing root link", error)),
    }
}

fn verify_root_link(root: &Path, link: &RootLink) -> Result<(), SourceError> {
    fs::symlink_metadata(root.join(&link.source))
        .map_err(|source| io_error("stat root link source", source))?;
    let target = root.join(&link.target);
    let metadata = fs::symlink_metadata(&target)
        .map_err(|source| io_error("stat root link target", source))?;
    if !metadata.file_type().is_symlink() {
        return Err(SourceError::Invalid(vec![format!(
            "root link target {} exists and is not a symlink",
            link.target.display()
        )]));
    }
    let expected = relative_path(
        link.target.parent().unwrap_or_else(|| Path::new("")),
        &link.source,
    );
    let actual =
        fs::read_link(&target).map_err(|source| io_error("read existing root link", source))?;
    if actual != expected {
        return Err(SourceError::Invalid(vec![format!(
            "root link {} resolves through {}, expected {}",
            link.target.display(),
            actual.display(),
            expected.display()
        )]));
    }
    Ok(())
}

fn write_manifest_atomically(
    root: &Path,
    manifest: &MaterializedManifest,
) -> Result<(), SourceError> {
    let json = serde_json::to_vec_pretty(manifest)
        .map_err(|error| SourceError::Invalid(vec![format!("serialize manifest: {error}")]))?;
    let mut temporary = Builder::new()
        .prefix(".droidloom-manifest-")
        .tempfile_in(root)
        .map_err(|source| io_error("create temporary materialized manifest", source))?;
    temporary
        .write_all(&json)
        .and_then(|()| temporary.as_file().sync_all())
        .map_err(|source| io_error("write temporary materialized manifest", source))?;
    temporary
        .persist(root.join(".droidloom-source-manifest.json"))
        .map_err(|error| io_error("publish materialized manifest atomically", error.error))?;
    Ok(())
}

fn materialize_project(root: &Path, project: &PlannedProject) -> Result<(), SourceError> {
    let checkout = root.join(&project.path);
    let parent = checkout
        .parent()
        .ok_or_else(|| SourceError::Invalid(vec!["project path has no parent".into()]))?;
    fs::create_dir_all(parent).map_err(|source| io_error("create project parent", source))?;
    run(
        "git",
        &[
            OsStr::new("init"),
            OsStr::new("--quiet"),
            OsStr::new("--initial-branch=droidloom"),
            checkout.as_os_str(),
        ],
    )?;
    run_git(
        &checkout,
        &[
            OsStr::new("remote"),
            OsStr::new("add"),
            OsStr::new("origin"),
            OsStr::new(&project.url),
        ],
    )?;
    apply_sparse_checkout(&checkout, project)?;
    run_git(
        &checkout,
        &[
            OsStr::new("fetch"),
            OsStr::new("--quiet"),
            OsStr::new("--depth=1"),
            OsStr::new("--filter=blob:none"),
            OsStr::new("origin"),
            OsStr::new(&project.commit),
        ],
    )?;
    run_git(
        &checkout,
        &[
            OsStr::new("checkout"),
            OsStr::new("--quiet"),
            OsStr::new("--detach"),
            OsStr::new("FETCH_HEAD"),
        ],
    )?;
    let head = run_git_output(&checkout, &[OsStr::new("rev-parse"), OsStr::new("HEAD")])?;
    let actual = String::from_utf8_lossy(&head.stdout).trim().to_owned();
    if actual != project.commit {
        return Err(SourceError::RevisionMismatch {
            path: project.path.clone(),
            expected: project.commit.clone(),
            actual,
        });
    }
    Ok(())
}

fn apply_sparse_checkout(checkout: &Path, project: &PlannedProject) -> Result<(), SourceError> {
    if project.sparse_paths.is_empty() {
        return Ok(());
    }
    run_git(
        checkout,
        &[
            OsStr::new("sparse-checkout"),
            OsStr::new("init"),
            OsStr::new("--cone"),
        ],
    )?;
    let mut arguments = vec![
        OsStr::new("sparse-checkout"),
        OsStr::new("set"),
        OsStr::new("--cone"),
        // Droidloom's bounded plans may name an individual pinned prebuilt.
        // Git's cone implementation supports that pattern but requires this
        // explicit acknowledgement because the path is not a directory.
        OsStr::new("--skip-checks"),
        OsStr::new("--"),
    ];
    arguments.extend(project.sparse_paths.iter().map(|path| path.as_os_str()));
    run_git(checkout, &arguments)
}

fn create_root_link(root: &Path, link: &RootLink) -> Result<(), SourceError> {
    let source = root.join(&link.source);
    fs::symlink_metadata(&source).map_err(|error| {
        io_error(
            &format!("stat root link source {}", link.source.display()),
            error,
        )
    })?;
    let target = root.join(&link.target);
    let target_parent = target
        .parent()
        .ok_or_else(|| SourceError::Invalid(vec!["root link target has no parent".into()]))?;
    fs::create_dir_all(target_parent).map_err(|source| io_error("create link parent", source))?;
    let relative_source = relative_path(
        link.target.parent().unwrap_or_else(|| Path::new("")),
        &link.source,
    );
    std::os::unix::fs::symlink(relative_source, &target)
        .map_err(|source| io_error("create AOSP root link", source))
}

fn relative_path(from: &Path, to: &Path) -> PathBuf {
    let from_parts: Vec<_> = from.components().collect();
    let to_parts: Vec<_> = to.components().collect();
    let common = from_parts
        .iter()
        .zip(&to_parts)
        .take_while(|(left, right)| left == right)
        .count();
    let mut result = PathBuf::new();
    for _ in common..from_parts.len() {
        result.push("..");
    }
    for component in &to_parts[common..] {
        result.push(component.as_os_str());
    }
    result
}

fn is_normal_relative(path: &Path) -> bool {
    !path.as_os_str().is_empty()
        && !path.is_absolute()
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn is_project_name(name: &str) -> bool {
    (name.starts_with("platform/")
        || name.starts_with("kernel/")
        || name.starts_with("toolchain/")
        || name == "tools/platform-compat")
        && name.len() <= 255
        && name
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
}

fn is_commit(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn run_git(checkout: &Path, args: &[&OsStr]) -> Result<(), SourceError> {
    run_git_output(checkout, args).map(drop)
}

fn run_git_output(checkout: &Path, args: &[&OsStr]) -> Result<Output, SourceError> {
    let mut all_args = vec![OsStr::new("-C"), checkout.as_os_str()];
    all_args.extend_from_slice(args);
    run_output("git", &all_args)
}

fn run(program: &str, args: &[&OsStr]) -> Result<(), SourceError> {
    run_output(program, args).map(drop)
}

fn run_output(program: &str, args: &[&OsStr]) -> Result<Output, SourceError> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|source| io_error(&format!("execute {program}"), source))?;
    if output.status.success() {
        Ok(output)
    } else {
        Err(SourceError::Command {
            program: program.to_owned(),
            status: output.status.to_string(),
            stderr: String::from_utf8_lossy(&output.stderr)
                .chars()
                .take(4096)
                .collect(),
        })
    }
}

fn sha256_file(path: &Path) -> Result<String, SourceError> {
    let file = fs::File::open(path).map_err(|source| io_error("open lock for SHA-256", source))?;
    let mut reader = BufReader::new(file);
    let mut hash = Sha256::new();
    io::copy(&mut reader, &mut hash).map_err(|source| io_error("read lock for SHA-256", source))?;
    Ok(hex::encode(hash.finalize()))
}

fn io_error(context: &str, source: io::Error) -> SourceError {
    SourceError::Io {
        context: context.to_owned(),
        source,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_lock() -> SparseSourceLock {
        SparseSourceLock {
            schema_version: 1,
            selected_at: "2026-08-14".into(),
            status: "seed_not_yet_build_proven".into(),
            remote_base: OFFICIAL_REMOTE.into(),
            superproject: SuperprojectLock {
                name: "platform/superproject".into(),
                source_ref: "refs/heads/android-17.0.0_r1".into(),
                commit: "28f0bbddc24d56c8ec5a8df5342ac7a292184039".into(),
            },
            policy: SparsePolicy {
                allow_unrestricted_repo_sync: false,
                require_exact_commits: true,
                add_dependencies_only_from_superproject: true,
                base_partitions_come_from_aosp_ci_artifact: true,
            },
            links: vec![RootLink {
                source: "build/make/core".into(),
                target: "build/core".into(),
            }],
            projects: vec![SparseProject {
                path: "build/make".into(),
                name: "platform/build".into(),
                commit: "5ce6f787337d0223710bf7d4a16dbe6d2a35f777".into(),
                purpose: "product rules".into(),
                sparse_paths: Vec::new(),
            }],
        }
    }

    #[test]
    fn audio_released_sdks_extend_the_actual_r11_lock_without_repinning() {
        let old_raw = audio_before_released_sdk_lock();
        let new_raw = include_str!("../../../android/manifest/audio-bridge-source-lock.json");
        let old: SparseSourceLock = serde_json::from_str(&old_raw).unwrap();
        let new: SparseSourceLock = serde_json::from_str(new_raw).unwrap();
        assert_eq!(old.projects.len(), 430);
        assert_eq!(new.projects.len(), 430);
        let before = build_plan(&old).unwrap();
        let after = build_plan(&new).unwrap();
        validate_plan_extension(&before, &after).unwrap();
        assert!(validate_plan_extension(&after, &before).is_err());
        let old_value: serde_json::Value = serde_json::from_str(&old_raw).unwrap();
        let new_value: serde_json::Value = serde_json::from_str(new_raw).unwrap();
        for (before, after) in old_value["projects"].as_array().unwrap().iter()
            .zip(new_value["projects"].as_array().unwrap()) {
            if before["path"] == "prebuilts/sdk" {
                for key in ["path", "name", "commit", "purpose"] {
                    assert_eq!(before[key], after[key], "{key}");
                }
                let selected_before = before["sparse_paths"].as_array().unwrap();
                let selected_after = after["sparse_paths"].as_array().unwrap();
                assert_eq!(&selected_after[..selected_before.len()], selected_before.as_slice());
                let added: Vec<_> = selected_after[selected_before.len()..].iter()
                    .map(|path| path.as_str().unwrap()).collect();
                assert_eq!(added, vec![
            "4/public/android.jar",
            "4/public/framework.aidl",
            "7/public/android.jar",
            "7/public/framework.aidl",
            "15/public/android.jar",
            "15/public/framework.aidl",
            "16/public/android.jar",
            "16/public/framework.aidl",
            "19/public/android.jar",
            "19/public/framework.aidl",
            "21/public/android.jar",
            "21/public/framework.aidl",
            "22/public/android.jar",
            "22/public/framework.aidl",
            "23/public/android.jar",
            "23/public/framework.aidl",
            "24/public/android.jar",
            "24/public/framework.aidl",
            "25/public/android.jar",
            "25/public/framework.aidl",
            "26/public/android.jar",
            "26/public/framework.aidl",
            "27/public/android.jar",
            "27/public/framework.aidl",
            "33/public/android.jar",
            "33/public/framework.aidl",
            "33/public/core-for-system-modules.jar",
            "37.0/public/android.jar",
            "37.0/public/framework.aidl",
            "37.0/public/core-for-system-modules.jar",
            "31/system/android.jar",
            "35/system/android.jar",
            "36/public/android.jar",
            "36/public/framework.aidl",
            "36/public/core-for-system-modules.jar",
                ]);
            } else {
                assert_eq!(before, after);
            }
        }
        for key in ["superproject", "links", "policy", "remote_base", "schema_version", "selected_at", "status"] {
            assert_eq!(old_value[key], new_value[key], "{key}");
        }
        assert_eq!(MAX_PROJECTS, 432);
        assert_eq!(MAX_SPARSE_PATHS, 368);
        assert_eq!(new.projects.iter().map(|p| p.sparse_paths.len()).max(), Some(355));
    }

    fn audio_before_released_sdk_lock() -> String {
        let mut previous = include_str!("../../../android/manifest/audio-bridge-source-lock.json").to_owned();
        for path in [
            "4/public/android.jar",
            "4/public/framework.aidl",
            "7/public/android.jar",
            "7/public/framework.aidl",
            "15/public/android.jar",
            "15/public/framework.aidl",
            "16/public/android.jar",
            "16/public/framework.aidl",
            "19/public/android.jar",
            "19/public/framework.aidl",
            "21/public/android.jar",
            "21/public/framework.aidl",
            "22/public/android.jar",
            "22/public/framework.aidl",
            "23/public/android.jar",
            "23/public/framework.aidl",
            "24/public/android.jar",
            "24/public/framework.aidl",
            "25/public/android.jar",
            "25/public/framework.aidl",
            "26/public/android.jar",
            "26/public/framework.aidl",
            "27/public/android.jar",
            "27/public/framework.aidl",
            "33/public/android.jar",
            "33/public/framework.aidl",
            "33/public/core-for-system-modules.jar",
            "37.0/public/android.jar",
            "37.0/public/framework.aidl",
            "37.0/public/core-for-system-modules.jar",
            "31/system/android.jar",
            "35/system/android.jar",
            "36/public/android.jar",
            "36/public/framework.aidl",
            "36/public/core-for-system-modules.jar",
        ] {
            let added = format!(",\n        \"{path}\"");
            assert_eq!(previous.matches(&added).count(), 1);
            previous = previous.replacen(&added, "", 1);
        }
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "45496b24c055fca9aa1f3fae7bd5c7c3c99cb46721150690645bf5d059159de2");
        previous
    }

    fn audio_before_ondeviceintelligence_lock() -> String {
        let mut previous = audio_before_released_sdk_lock();
        for path in [
            "36/public/api/service-ondeviceintelligence.txt",
            "36/public/api/service-ondeviceintelligence-removed.txt",
            "36/system-server/api/service-ondeviceintelligence.txt",
            "36/system-server/api/service-ondeviceintelligence-removed.txt",
        ] {
            let added = format!(",\n        \"{path}\"");
            assert_eq!(previous.matches(&added).count(), 1);
            previous = previous.replacen(&added, "", 1);
        }
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "78cc10ee7459926ec151e6224e6341d1b33397801330499e5d7f1a13fadb997a");
        previous
    }

    #[test]
    fn audio_ondeviceintelligence_extends_actual_430_by_four_original_api_inputs() {
        let old_raw = audio_before_ondeviceintelligence_lock();
        let new_owned = audio_before_released_sdk_lock();
        let new_raw = new_owned.as_str();
        let old: SparseSourceLock = serde_json::from_str(&old_raw).unwrap();
        let new: SparseSourceLock = serde_json::from_str(new_raw).unwrap();
        let before = build_plan(&old).unwrap();
        let after = build_plan(&new).unwrap();
        assert_eq!(before.projects.len(), 430);
        assert_eq!(after.projects.len(), 430);
        validate_plan_extension(&before, &after).unwrap();
        assert!(validate_plan_extension(&after, &before).is_err());
        let old_value: serde_json::Value = serde_json::from_str(&old_raw).unwrap();
        let new_value: serde_json::Value = serde_json::from_str(new_raw).unwrap();
        for (before, after) in old_value["projects"].as_array().unwrap().iter()
            .zip(new_value["projects"].as_array().unwrap()) {
            if before["path"] == "prebuilts/sdk" {
                for key in ["path", "name", "commit", "purpose"] {
                    assert_eq!(before[key], after[key], "{key}");
                }
                let selected_before = before["sparse_paths"].as_array().unwrap();
                let selected_after = after["sparse_paths"].as_array().unwrap();
                assert_eq!(&selected_after[..selected_before.len()], selected_before.as_slice());
                assert_eq!(selected_after.len(), selected_before.len() + 4);
            } else {
                assert_eq!(before, after);
            }
        }
        assert_eq!(new.projects.iter().map(|p| p.sparse_paths.len()).max(), Some(355));
        for key in ["superproject", "links", "policy", "remote_base", "schema_version", "selected_at", "status"] {
            assert_eq!(old_value[key], new_value[key], "{key}");
        }
    }

    fn audio_before_pasit_lock() -> String {
        let current_owned = audio_before_ondeviceintelligence_lock();
        let current = current_owned.as_str();
        let (prefix, _) = current.split_once(",\n    {\n      \"path\": \"tools/test/desktop/mobly\",").unwrap();
        let previous = format!("{prefix}\n  ]\n}}\n");
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "1dd0671551fb3c07cac4bb9b587346421321a6e4809494299f7b6daa4c49371c");
        previous
    }

    #[test]
    fn audio_pasit_extends_the_actual_425_source_with_only_five_original_projects() {
        let old: SparseSourceLock = serde_json::from_str(&audio_before_pasit_lock()).unwrap();
        let current: SparseSourceLock = serde_json::from_str(&audio_before_ondeviceintelligence_lock()).unwrap();
        let before = build_plan(&old).unwrap();
        let after = build_plan(&current).unwrap();
        assert_eq!(before.projects.len(), 425);
        assert_eq!(after.projects.len(), 430);
        assert_eq!(after.projects.iter().filter(|project|
            !before.projects.iter().any(|old| old.path == project.path)).count(), 5);
        assert_eq!(current.projects.iter().map(|p| p.sparse_paths.len()).max(), Some(355));
        validate_plan_extension(&before, &after).unwrap();
        assert!(validate_plan_extension(&after, &before).is_err());
        let mut repinned = after;
        repinned.projects.iter_mut().find(|p| p.path == Path::new("cts")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_plan_extension(&before, &repinned).is_err());
    }

    // Reconstruct the exact previously qualified lock without changing its
    // commits, purposes, field order or existing source cones.

    #[test]
    fn audio_rkpd_apex_extends_the_actual_425_source_by_one_original_cone() {
        let current_owned = audio_before_pasit_lock();
        let current = current_owned.as_str();
        let current_project = r###"    {
      "path": "packages/modules/RemoteKeyProvisioning",
      "name": "platform/packages/modules/RemoteKeyProvisioning",
      "commit": "d88e2305f9186661fe75ee2f00c8b250a76fdabe",
      "purpose": "Pinned original provider and physical source inputs for the retained strict full Audio APEX graph",
      "sparse_paths": [
        "app/Android.bp",
        "app/AndroidManifest.xml",
        "app/TEST_MAPPING",
        "app/aidl",
        "app/lint-baseline.xml",
        "app/proguard.flags",
        "app/res",
        "app/src",
        "app/sysconfig",
        "flags",
        "system-server/Android.bp",
        "system-server/TEST_MAPPING",
        "system-server/api",
        "system-server/src",
        "util",
        "system-server",
        "apex"
      ]
    }"###;
        let original_project = r###"    {
      "path": "packages/modules/RemoteKeyProvisioning",
      "name": "platform/packages/modules/RemoteKeyProvisioning",
      "commit": "d88e2305f9186661fe75ee2f00c8b250a76fdabe",
      "purpose": "Pinned original provider and physical source inputs for the retained strict full Audio APEX graph",
      "sparse_paths": [
        "app/Android.bp",
        "app/AndroidManifest.xml",
        "app/TEST_MAPPING",
        "app/aidl",
        "app/lint-baseline.xml",
        "app/proguard.flags",
        "app/res",
        "app/src",
        "app/sysconfig",
        "flags",
        "system-server/Android.bp",
        "system-server/TEST_MAPPING",
        "system-server/api",
        "system-server/src",
        "util",
        "system-server"
      ]
    }"###;
        assert_eq!(current.matches(current_project).count(), 1);
        let previous = current.replacen(current_project, original_project, 1);
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "5bacc225ebb2cf9f793b5c439205a4d27ec43144c04cae8e16e5197b300e57b7");
        let old: SparseSourceLock = serde_json::from_str(&previous).unwrap();
        let new: SparseSourceLock = serde_json::from_str(current).unwrap();
        let before = build_plan(&old).unwrap();
        let after = build_plan(&new).unwrap();
        assert_eq!(before.projects.len(), 425);
        assert_eq!(after.projects.len(), 425);
        assert_eq!(new.projects.iter().map(|p| p.sparse_paths.len()).max(), Some(355));
        validate_plan_extension(&before, &after).unwrap();
        assert!(validate_plan_extension(&after, &before).is_err());
        let mut wrong = after;
        wrong.projects.iter_mut().find(|p|
            p.path == Path::new("packages/modules/RemoteKeyProvisioning")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_plan_extension(&before, &wrong).is_err());
    }

    fn audio_before_allgraph_lock() -> &'static str {
        let raw = include_str!("../tests/fixtures/audio-source321-before-allgraph.json");
        assert_eq!(format!("{:x}", Sha256::digest(raw.as_bytes())), "2466de84fa9aeac43b4b5792efabbc27ea419652830e339844fa21fd67554bd9");
        raw
    }

    #[test]
    fn audio_allgraph_extends_the_actual_previous_source_without_changing_commits() {
        let old: SparseSourceLock = serde_json::from_str(audio_before_allgraph_lock()).unwrap();
        let current: SparseSourceLock = serde_json::from_str(&audio_before_pasit_lock()).unwrap();
        let before = build_plan(&old).unwrap();
        let after = build_plan(&current).unwrap();
        assert_eq!(before.projects.len(), 321);
        assert_eq!(after.projects.len(), 425);
        assert_eq!(current.projects.iter().map(|p| p.sparse_paths.len()).max(), Some(355));
        validate_plan_extension(&before, &after).unwrap();
        assert!(validate_plan_extension(&after, &before).is_err());
        let mut changed = after;
        changed.projects.iter_mut().find(|p| p.path == Path::new("cts")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_plan_extension(&before, &changed).is_err());
    }

    fn audio_before_cts_sts_lock() -> String {
        let mut previous = audio_before_allgraph_lock().to_owned();
        for (after, before) in [
            (r###"    {
      "path": "cts",
      "name": "platform/cts",
      "commit": "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd",
      "purpose": "Pinned host JSON compatibility library required by the ProtoLog generator",
      "sparse_paths": [
        "Android.bp",
        "common/device-side/nativetesthelper/Android.bp",
        "common/device-side/nativetesthelper/jni",
        "common/device-side/nativetesthelper/src",
        "libs/json",
        "common/device-side/util-axt",
        "libs/shim",
        "libs/install",
        "hostsidetests/stagedinstall",
        "hostsidetests/appsecurity/test-apps/PrivilegedUpdateApp",
        "tools/cts-tradefed",
        "libs/runner",
        "tests/core/runner-axt",
        "libs/vogar-expect",
        "hostsidetests/compilation",
        "hostsidetests/appcompat/host/lib",
        "hostsidetests/appsecurity/certs",
        "hostsidetests/appsecurity/res",
        "hostsidetests/appsecurity/src",
        "hostsidetests/appsecurity/test-apps/AppAccessData",
        "hostsidetests/appsecurity/test-apps/AppDataIsolationTestApp",
        "hostsidetests/appsecurity/test-apps/AppWithData",
        "hostsidetests/appsecurity/test-apps/DeclarePermissionsWithSpacesApp",
        "hostsidetests/appsecurity/test-apps/DeviceIdentifiers",
        "hostsidetests/appsecurity/test-apps/DuplicatePermissionDeclareApp",
        "hostsidetests/appsecurity/test-apps/DuplicatePermissionSameGroup",
        "hostsidetests/appsecurity/test-apps/InstrumentationAppDiffCert",
        "hostsidetests/appsecurity/test-apps/KeyRotationTest",
        "hostsidetests/appsecurity/test-apps/KeyStoreManagerTest",
        "hostsidetests/appsecurity/test-apps/ListeningPortsApp",
        "hostsidetests/appsecurity/test-apps/MalformedDuplicatePermission",
        "hostsidetests/appsecurity/test-apps/PackageInstallerPermissionRequestApp",
        "hostsidetests/appsecurity/test-apps/PackageInstallerWhitelistApp",
        "hostsidetests/appsecurity/test-apps/PermissionDeclareApp",
        "hostsidetests/appsecurity/test-apps/PermissionDeclareAppCompat",
        "hostsidetests/appsecurity/test-apps/ReadSettingsFieldsApp",
        "hostsidetests/appsecurity/test-apps/RoleSecurityTestApp",
        "hostsidetests/appsecurity/test-apps/SimpleAppInstall",
        "hostsidetests/appsecurity/test-apps/SimpleAppInstallDiffCert",
        "hostsidetests/appsecurity/test-apps/StatsdSecurityApp",
        "hostsidetests/appsecurity/test-apps/TargetInstrumentationApp",
        "hostsidetests/appsecurity/test-apps/UsePermissionDiffCert",
        "hostsidetests/appsecurity/test-apps/UseProcessFailActivity",
        "hostsidetests/appsecurity/test-apps/V32HybridSigningScheme",
        "hostsidetests/appsecurity/test-apps/V3SigningSchemeRotation",
        "hostsidetests/appsecurity/test-apps/keysets/malBadKey",
        "hostsidetests/appsecurity/test-apps/keysets/malNoDef",
        "hostsidetests/appsecurity/test-apps/keysets/malOneDef",
        "hostsidetests/appsecurity/test-apps/keysets/permDef",
        "hostsidetests/appsecurity/test-apps/keysets/permUse",
        "hostsidetests/appsecurity/test-apps/keysets/testApp",
        "hostsidetests/appsecurity/test-apps/keysets/uA",
        "hostsidetests/appsecurity/test-apps/keysets/uAuB",
        "hostsidetests/appsecurity/test-apps/keysets/uB",
        "hostsidetests/appsecurity/test-apps/keysets/uBsharedUser",
        "hostsidetests/appsecurity/test-apps/keysets/uEcA",
        "hostsidetests/appsecurity/test-apps/keysets/uNone",
        "hostsidetests/appsecurity/test-apps/tinyapp",
        "hostsidetests/statsdatom/Android.bp",
        "hostsidetests/statsdatom/apps/adpfapp",
        "hostsidetests/statsdatom/apps/expressloghelperapp",
        "hostsidetests/statsdatom/apps/statsdapp",
        "hostsidetests/statsdatom/configs/AndroidTestTelecom.xml",
        "hostsidetests/statsdatom/express/src",
        "hostsidetests/statsdatom/lib/src",
        "hostsidetests/statsdatom/statsd/src",
        "hostsidetests/statsdatom/telecom/src",
        "hostsidetests/utils",
        "tests/tests/telecom",
        "tests/tests/telecom-apps/ConnectionServiceVoipAppClone",
        "tests/tests/telecom-apps/ConnectionServiceVoipAppMain",
        "tests/tests/telecom-apps/ManagedConnectionService",
        "tests/tests/telecom-apps/ManagedConnectionServiceClone",
        "tests/tests/telecom-apps/TransactionalVoipAppClone",
        "tests/tests/telecom-apps/TransactionalVoipAppMain",
        "tests/tests/telecom-apps/Utils",
        "tests/tests/telecom-cuj"
      ]
    },
"###, r###"    {
      "path": "cts",
      "name": "platform/cts",
      "commit": "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd",
      "purpose": "Pinned host JSON compatibility library required by the ProtoLog generator",
      "sparse_paths": [
        "Android.bp",
        "common/device-side/nativetesthelper/Android.bp",
        "common/device-side/nativetesthelper/jni",
        "common/device-side/nativetesthelper/src",
        "libs/json",
        "common/device-side/util-axt",
        "libs/shim",
        "libs/install",
        "hostsidetests/stagedinstall",
        "hostsidetests/appsecurity/test-apps/PrivilegedUpdateApp",
        "tools/cts-tradefed",
        "libs/runner",
        "tests/core/runner-axt",
        "libs/vogar-expect",
        "hostsidetests/compilation"
      ]
    },
"###),
            (r###"    {
      "path": "external/bouncycastle",
      "name": "platform/external/bouncycastle",
      "commit": "c404048739e9a35cd51ad82906aadf910cca09dd",
      "purpose": "Pinned Java crypto provider required by the host APK signing tool",
      "sparse_paths": [
        "Android.bp",
        "src",
        "bcpkix/src/main/java",
        "bcprov/src/main/java",
        "repackaged_platform/bcpkix/src/main/java",
        "repackaged_platform/bcprov/src/main/java"
      ]
    },
"###, r###"    {
      "path": "external/bouncycastle",
      "name": "platform/external/bouncycastle",
      "commit": "c404048739e9a35cd51ad82906aadf910cca09dd",
      "purpose": "Pinned Java crypto provider required by the host APK signing tool",
      "sparse_paths": [
        "Android.bp",
        "src"
      ]
    },
"###),
            (r###"    {
      "path": "external/compiler-rt",
      "name": "platform/external/compiler-rt",
      "commit": "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7",
      "purpose": "Original compiler-rt CFI blocklist required by selected libmediaplayerservice sanitizer flags",
      "sparse_paths": [
        "lib/cfi",
        "lib/builtins/comparedf2.c",
        "lib/builtins/mulodi4.c"
      ]
    },
"###, r###"    {
      "path": "external/compiler-rt",
      "name": "platform/external/compiler-rt",
      "commit": "a36a1bcac7ec7ac9be29d8b0b5e669d53f7886f7",
      "purpose": "Original compiler-rt CFI blocklist required by selected libmediaplayerservice sanitizer flags",
      "sparse_paths": [
        "lib/cfi"
      ]
    },
"###),
            (r###"    {
      "path": "external/cronet",
      "name": "platform/external/cronet",
      "commit": "e184145f12ee023d07372bd6db33341b671cee27",
      "purpose": "Pinned Cronet Tethering APEX defaults from Android17 original superproject",
      "sparse_paths": [
        "Android.bp",
        "android/Android.bp",
        "stable/components/cronet/android",
        "android/flags",
        "android/tools/classes_collector",
        "tot",
        "android/java/src/android/net/http/BidirectionalStream.java",
        "android/java/src/android/net/http/BidirectionalStreamBuilderWrapper.java",
        "android/java/src/android/net/http/BidirectionalStreamCallbackWrapper.java",
        "android/java/src/android/net/http/BidirectionalStreamWrapper.java",
        "android/java/src/android/net/http/CallbackException.java",
        "android/java/src/android/net/http/CallbackExceptionWrapper.java",
        "android/java/src/android/net/http/ConnectionMigrationOptions.java",
        "android/java/src/android/net/http/CronetEngineWrapper.java",
        "android/java/src/android/net/http/CronetExceptionTranslationUtils.java",
        "android/java/src/android/net/http/CronetExceptionWrapper.java",
        "android/java/src/android/net/http/DnsOptions.java",
        "android/java/src/android/net/http/HeaderBlock.java",
        "android/java/src/android/net/http/HeaderBlockImpl.java",
        "android/java/src/android/net/http/HeaderBlockWrapper.java",
        "android/java/src/android/net/http/HttpEngine.java",
        "android/java/src/android/net/http/HttpEngineJavaClasses.java",
        "android/java/src/android/net/http/HttpException.java",
        "android/java/src/android/net/http/InlineExecutionProhibitedException.java",
        "android/java/src/android/net/http/NetworkException.java",
        "android/java/src/android/net/http/NetworkExceptionWrapper.java",
        "android/java/src/android/net/http/Proxy.java",
        "android/java/src/android/net/http/ProxyOptions.java",
        "android/java/src/android/net/http/QuicException.java",
        "android/java/src/android/net/http/QuicExceptionWrapper.java",
        "android/java/src/android/net/http/QuicOptions.java",
        "android/java/src/android/net/http/UploadDataProvider.java",
        "android/java/src/android/net/http/UploadDataProviderWrapper.java",
        "android/java/src/android/net/http/UploadDataSink.java",
        "android/java/src/android/net/http/UploadDataSinkWrapper.java",
        "android/java/src/android/net/http/UrlRequest.java",
        "android/java/src/android/net/http/UrlRequestBuilderWrapper.java",
        "android/java/src/android/net/http/UrlRequestCallbackWrapper.java",
        "android/java/src/android/net/http/UrlRequestStatusListenerWrapper.java",
        "android/java/src/android/net/http/UrlRequestWrapper.java",
        "android/java/src/android/net/http/UrlResponseInfo.java",
        "android/java/src/android/net/http/UrlResponseInfoWrapper.java",
        "stable/build/Android.bp",
        "stable/build/util/LASTCHANGE",
        "stable/build/util/android_chrome_version.py",
        "stable/build/util/version.py",
        "stable/chrome/VERSION"
      ]
    },
"###, r###"    {
      "path": "external/cronet",
      "name": "platform/external/cronet",
      "commit": "e184145f12ee023d07372bd6db33341b671cee27",
      "purpose": "Pinned Cronet Tethering APEX defaults from Android17 original superproject",
      "sparse_paths": [
        "Android.bp",
        "android/Android.bp",
        "stable/components/cronet/android",
        "android/flags",
        "android/tools/classes_collector",
        "tot"
      ]
    },
"###),
            (r###"    {
      "path": "external/escapevelocity",
      "name": "platform/external/escapevelocity",
      "commit": "03b11f293548ad5fd65b5164b46aca08a96968f5",
      "purpose": "Template interpreter statically used by AutoValue processor",
      "sparse_paths": [
        "Android.bp",
        "src/main/java",
        "src/main"
      ]
    },
"###, r###"    {
      "path": "external/escapevelocity",
      "name": "platform/external/escapevelocity",
      "commit": "03b11f293548ad5fd65b5164b46aca08a96968f5",
      "purpose": "Template interpreter statically used by AutoValue processor",
      "sparse_paths": [
        "Android.bp",
        "src/main/java"
      ]
    },
"###),
            (r###"    {
      "path": "external/libbpf",
      "name": "platform/external/libbpf",
      "commit": "9723b4de6459ab48b361aed3bae5df3c1bd20cb8",
      "purpose": "Pinned BPF headers required by the Android memory-event programs",
      "sparse_paths": [
        "Android.bp",
        "src",
        "android/bpf_stub.c"
      ]
    },
"###, r###"    {
      "path": "external/libbpf",
      "name": "platform/external/libbpf",
      "commit": "9723b4de6459ab48b361aed3bae5df3c1bd20cb8",
      "purpose": "Pinned BPF headers required by the Android memory-event programs",
      "sparse_paths": [
        "Android.bp",
        "src"
      ]
    },
"###),
            (r###"    {
      "path": "external/protobuf",
      "name": "platform/external/protobuf",
      "commit": "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab",
      "purpose": "Pinned aprotoc host tool required by Android native stub generation",
      "sparse_paths": [
        "Android.bp",
        "java/core/src/main",
        "java/core/src/stubs",
        "python/google/protobuf/internal/python_edition_defaults.py.template",
        "src/google/protobuf",
        "third_party/utf8_range",
        "upb",
        "upb_generator",
        "rust/cpp_kernel",
        "python/google",
        "java/lite/proguard.pgcfg",
        "javanano/src/device/main/java/com/google/protobuf/nano",
        "javanano/src/main/java/com/google/protobuf/nano"
      ]
    },
"###, r###"    {
      "path": "external/protobuf",
      "name": "platform/external/protobuf",
      "commit": "db06feae31e2a10ffc7ddaccd9e285ff7c13c0ab",
      "purpose": "Pinned aprotoc host tool required by Android native stub generation",
      "sparse_paths": [
        "Android.bp",
        "java/core/src/main",
        "java/core/src/stubs",
        "python/google/protobuf/internal/python_edition_defaults.py.template",
        "src/google/protobuf",
        "third_party/utf8_range",
        "upb",
        "upb_generator",
        "rust/cpp_kernel",
        "python/google"
      ]
    },
"###),
            (r###"    {
      "path": "packages/modules/Bluetooth",
      "name": "platform/packages/modules/Bluetooth",
      "commit": "c77db469de80f86660bc053bec4dee0c5d4b947c",
      "purpose": "Pinned Bluetooth audio session library linked by the upstream core audio service",
      "sparse_paths": [
        "flags",
        "framework/aidl-export",
        "framework/api",
        "system/audio_bluetooth_hw",
        "system/build/Android.bp",
        "system/test",
        "android/app/aidl",
        "common/Android.bp",
        "common/bluetooth/constants",
        "framework/java",
        "service/aidl",
        "tools/lint",
        "framework/tests/util"
      ]
    },
"###, r###"    {
      "path": "packages/modules/Bluetooth",
      "name": "platform/packages/modules/Bluetooth",
      "commit": "c77db469de80f86660bc053bec4dee0c5d4b947c",
      "purpose": "Pinned Bluetooth audio session library linked by the upstream core audio service",
      "sparse_paths": [
        "flags",
        "framework/aidl-export",
        "framework/api",
        "system/audio_bluetooth_hw",
        "system/build/Android.bp",
        "system/test",
        "android/app/aidl",
        "common/Android.bp",
        "common/bluetooth/constants",
        "framework/java",
        "service/aidl",
        "tools/lint"
      ]
    },
"###),
            (r###"    {
      "path": "packages/modules/ConfigInfrastructure",
      "name": "platform/packages/modules/ConfigInfrastructure",
      "commit": "333bc8067efc529ef4d197fec2f4f2cae1ad2ece",
      "purpose": "Configuration flags used by system-server services",
      "sparse_paths": [
        "aconfigd/Android.bp",
        "aconfigd/proto"
      ]
    },
"###, r###"    {
      "path": "packages/modules/ConfigInfrastructure",
      "name": "platform/packages/modules/ConfigInfrastructure",
      "commit": "333bc8067efc529ef4d197fec2f4f2cae1ad2ece",
      "purpose": "Configuration flags used by system-server services",
      "sparse_paths": [
        "aconfigd/Android.bp"
      ]
    },
"###),
            (r###"    {
      "path": "packages/modules/Connectivity",
      "name": "platform/packages/modules/Connectivity",
      "commit": "347fbd34b368d19f0d87e908ea101eed3601a731",
      "purpose": "Pinned BPF client headers required by the Android memory-event client",
      "sparse_paths": [
        "Android.bp",
        "Tethering/Android.bp",
        "Tethering/apex/Android.bp",
        "Tethering/common/TetheringLib",
        "Vcn/flags",
        "Vcn/framework-b",
        "bpf",
        "bpf/headers/include/bpf/BpfUtils.h",
        "bpf/loader/Android.bp",
        "bpf/loader/NetBpfLoad.cpp",
        "bpf/netd/Android.bp",
        "bpf/netd/BpfHandler.cpp",
        "common",
        "framework",
        "framework-t",
        "service",
        "service/Android.bp",
        "service/jni/com_android_server_connectivity_ClatCoordinator.cpp",
        "service/jni/com_android_server_connectivity_LocalNetEventListener.cpp",
        "staticlibs/device/com/android/net/module/util/IIpv4PrefixRequest.aidl",
        "staticlibs/device/com/android/net/module/util/IRoutingCoordinator.aidl",
        "staticlibs/native/bpfmapjni/com_android_net_module_util_Bpf.cpp",
        "staticlibs/netd",
        "tests",
        "tools",
        "nearby/framework/Android.bp",
        "nearby/framework/java",
        "thread/framework/Android.bp",
        "thread/framework/java",
        "staticlibs/client-libs",
        "staticlibs/testutils",
        "Tethering/apex/hiddenapi",
        "staticlibs/device",
        "staticlibs/framework"
      ]
    },
"###, r###"    {
      "path": "packages/modules/Connectivity",
      "name": "platform/packages/modules/Connectivity",
      "commit": "347fbd34b368d19f0d87e908ea101eed3601a731",
      "purpose": "Pinned BPF client headers required by the Android memory-event client",
      "sparse_paths": [
        "Android.bp",
        "Tethering/Android.bp",
        "Tethering/apex/Android.bp",
        "Tethering/common/TetheringLib",
        "Vcn/flags",
        "Vcn/framework-b",
        "bpf",
        "bpf/headers/include/bpf/BpfUtils.h",
        "bpf/loader/Android.bp",
        "bpf/loader/NetBpfLoad.cpp",
        "bpf/netd/Android.bp",
        "bpf/netd/BpfHandler.cpp",
        "common",
        "framework",
        "framework-t",
        "service",
        "service/Android.bp",
        "service/jni/com_android_server_connectivity_ClatCoordinator.cpp",
        "service/jni/com_android_server_connectivity_LocalNetEventListener.cpp",
        "staticlibs/device/com/android/net/module/util/IIpv4PrefixRequest.aidl",
        "staticlibs/device/com/android/net/module/util/IRoutingCoordinator.aidl",
        "staticlibs/native/bpfmapjni/com_android_net_module_util_Bpf.cpp",
        "staticlibs/netd",
        "tests",
        "tools",
        "nearby/framework/Android.bp",
        "nearby/framework/java",
        "thread/framework/Android.bp",
        "thread/framework/java",
        "staticlibs/client-libs",
        "staticlibs/testutils"
      ]
    },
"###),
            (r###"    {
      "path": "packages/modules/Telephony",
      "name": "platform/packages/modules/Telephony",
      "commit": "d83f23a96fbe6d68942d8d7245dbd3db91e9c711",
      "purpose": "Exact original transitive provider required by retained audio closure consumers",
      "sparse_paths": [
        "framework",
        "telecom/framework",
        "telecom/flags",
        "flags",
        "libs/libphonenumber",
        "tests/mcts/Android.bp",
        "tests/mcts/AndroidTest.xml",
        "tests/mcts/telecom-cuj"
      ]
    },
"###, r###"    {
      "path": "packages/modules/Telephony",
      "name": "platform/packages/modules/Telephony",
      "commit": "d83f23a96fbe6d68942d8d7245dbd3db91e9c711",
      "purpose": "Exact original transitive provider required by retained audio closure consumers",
      "sparse_paths": [
        "framework",
        "telecom/framework",
        "telecom/flags",
        "flags",
        "libs/libphonenumber"
      ]
    },
"###),
            (r###"    {
      "path": "packages/modules/Wifi",
      "name": "platform/packages/modules/Wifi",
      "commit": "67beff9acf0e91046d2a9a36a68cb06ef263d1f1",
      "purpose": "Framework Wi-Fi annotations used by framework headers",
      "sparse_paths": [
        "framework/Android.bp",
        "framework/api",
        "flags",
        "framework/aidl-export",
        "framework/java"
      ]
    },
"###, r###"    {
      "path": "packages/modules/Wifi",
      "name": "platform/packages/modules/Wifi",
      "commit": "67beff9acf0e91046d2a9a36a68cb06ef263d1f1",
      "purpose": "Framework Wi-Fi annotations used by framework headers",
      "sparse_paths": [
        "framework/Android.bp",
        "framework/api",
        "flags"
      ]
    },
"###),
            (r###"    {
      "path": "platform_testing",
      "name": "platform/platform_testing",
      "commit": "6abefd291d50dee240ed2b22572d273175f070da",
      "purpose": "Android17 superproject-gitlink-pinned Rust rdroidtest provider",
      "sparse_paths": [
        "Android.bp",
        "libraries/annotations",
        "libraries/compatibility-common-util/Android.bp",
        "libraries/compatibility-common-util/src",
        "libraries/rdroidtest",
        "libraries/tradefed-error-prone",
        "libraries/motion/src",
        "libraries/motion/compose/src",
        "libraries/motion/compose/values/src",
        "libraries/screenshot/src/main",
        "libraries/screenshot/proto",
        "libraries/uiautomator-helpers/src",
        "libraries/runner/src/main/java",
        "libraries/device-collectors/src/main/java",
        "libraries/collectors-helper/adservices/src",
        "libraries/collectors-helper/app/src",
        "libraries/collectors-helper/generic/src",
        "libraries/collectors-helper/jank/src",
        "libraries/collectors-helper/lyric/src",
        "libraries/collectors-helper/memory/src",
        "libraries/collectors-helper/perfetto/src",
        "libraries/collectors-helper/power/src",
        "libraries/collectors-helper/simpleperf/src",
        "libraries/collectors-helper/system/src",
        "libraries/collectors-helper/utilities/src",
        "libraries/junitxml/src",
        "libraries/flag-helpers/junit",
        "libraries/metrics-helper",
        "libraries/screenshot/utils/compose",
        "libraries/health/rules",
        "libraries/app-helpers/interfaces",
        "libraries/health/utils",
        "libraries/notes-role-test-helper",
        "libraries/system-helpers/package-helper",
        "libraries/collectors-helper/statsd",
        "libraries/uinput-device-test-helper",
        "libraries/system-helpers/user-helper",
        "libraries/flicker",
        "libraries/device-collectors/src/main/platform-collectors",
        "libraries/system-helpers/accessibility-helper",
        "libraries/system-helpers/account-helper",
        "libraries/system-helpers/activity-helper",
        "libraries/app-helpers/core",
        "libraries/system-helpers/commands-helper",
        "libraries/system-helpers/connectivity-helper",
        "libraries/system-helpers/device-helper",
        "utils/dpad",
        "libraries/launcher-helper",
        "libraries/system-helpers/permission-helper",
        "libraries/system-helpers/settings-helper",
        "libraries/system-helpers/sysui-helper",
        "libraries/app-helpers/spectatio/spectatio-util",
        "libraries/systemui-tapl",
        "libraries/systemui-helper",
        "libraries/tapl-common",
        "scripts",
        "libraries/sts-common-util/host-side/Android.bp",
        "libraries/sts-common-util/host-side/res",
        "libraries/sts-common-util/host-side/src",
        "libraries/sts-common-util/util/Android.bp",
        "libraries/sts-common-util/util/src"
      ]
    },
"###, r###"    {
      "path": "platform_testing",
      "name": "platform/platform_testing",
      "commit": "6abefd291d50dee240ed2b22572d273175f070da",
      "purpose": "Android17 superproject-gitlink-pinned Rust rdroidtest provider",
      "sparse_paths": [
        "Android.bp",
        "libraries/annotations",
        "libraries/compatibility-common-util/Android.bp",
        "libraries/compatibility-common-util/src",
        "libraries/rdroidtest",
        "libraries/tradefed-error-prone",
        "libraries/motion/src",
        "libraries/motion/compose/src",
        "libraries/motion/compose/values/src",
        "libraries/screenshot/src/main",
        "libraries/screenshot/proto",
        "libraries/uiautomator-helpers/src",
        "libraries/runner/src/main/java",
        "libraries/device-collectors/src/main/java",
        "libraries/collectors-helper/adservices/src",
        "libraries/collectors-helper/app/src",
        "libraries/collectors-helper/generic/src",
        "libraries/collectors-helper/jank/src",
        "libraries/collectors-helper/lyric/src",
        "libraries/collectors-helper/memory/src",
        "libraries/collectors-helper/perfetto/src",
        "libraries/collectors-helper/power/src",
        "libraries/collectors-helper/simpleperf/src",
        "libraries/collectors-helper/system/src",
        "libraries/collectors-helper/utilities/src",
        "libraries/junitxml/src",
        "libraries/flag-helpers/junit",
        "libraries/metrics-helper",
        "libraries/screenshot/utils/compose",
        "libraries/health/rules",
        "libraries/app-helpers/interfaces",
        "libraries/health/utils",
        "libraries/notes-role-test-helper",
        "libraries/system-helpers/package-helper",
        "libraries/collectors-helper/statsd",
        "libraries/uinput-device-test-helper",
        "libraries/system-helpers/user-helper",
        "libraries/flicker",
        "libraries/device-collectors/src/main/platform-collectors",
        "libraries/system-helpers/accessibility-helper",
        "libraries/system-helpers/account-helper",
        "libraries/system-helpers/activity-helper",
        "libraries/app-helpers/core",
        "libraries/system-helpers/commands-helper",
        "libraries/system-helpers/connectivity-helper",
        "libraries/system-helpers/device-helper",
        "utils/dpad",
        "libraries/launcher-helper",
        "libraries/system-helpers/permission-helper",
        "libraries/system-helpers/settings-helper",
        "libraries/system-helpers/sysui-helper",
        "libraries/app-helpers/spectatio/spectatio-util",
        "libraries/systemui-tapl",
        "libraries/systemui-helper",
        "libraries/tapl-common",
        "scripts"
      ]
    },
"###),
            (r###"    {
      "path": "prebuilts/sdk",
      "name": "platform/prebuilts/sdk",
      "commit": "0f07e8d60ab0aba46129e427101f96ba459a95c1",
      "purpose": "Pinned Android 17 released API tracking required by full vendor-image graph validation",
      "sparse_paths": [
        "28/public",
        "29/public",
        "29/system",
        "30/public",
        "31/public",
        "34/public",
        "34/system/android.jar",
        "37.0/module-lib/api",
        "37.0/public/api",
        "37.0/system-server/api",
        "37.0/system/api",
        "37.0/test/api",
        "8/public",
        "9/public",
        "Android.bp",
        "current/androidx/Android.bp",
        "current/androidx/m2repository/androidx/annotation/annotation-experimental/1.6.0",
        "current/androidx/m2repository/androidx/annotation/annotation-jvm/1.10.0",
        "current/androidx/m2repository/androidx/collection/collection-jvm/1.7.0-alpha01",
        "current/androidx/m2repository/androidx/core/core-animation-testing/1.0.0",
        "current/androidx/m2repository/androidx/core/core-animation/1.0.0",
        "current/androidx/m2repository/androidx/core/core/1.20.0-alpha01",
        "current/androidx/m2repository/androidx/leanback/leanback/1.3.0-alpha01",
        "current/androidx/m2repository/androidx/transition/transition-ktx/1.7.0-rc01",
        "current/androidx/m2repository/androidx/transition/transition/1.7.0-rc01",
        "current/androidx/m2repository/androidx/webkit/webkit/1.12.0-alpha02",
        "current/core",
        "current/module-lib",
        "current/public",
        "current/system",
        "current/system-server",
        "extensions/19/module-lib",
        "extensions/19/public",
        "extensions/19/system",
        "extensions/19/system-server",
        "tools/Android.bp",
        "tools/core-lambda-stubs.jar",
        "update_prebuilts",
        "current/androidx",
        "18/public",
        "current/multidex",
        "current/test",
        "current/support/v7/appcompat/res",
        "current/support/manifests/android-support-v7-appcompat",
        "current/extras/material-design-x",
        "36/public/api/framework-ondeviceintelligence.txt",
        "36/public/api/framework-ondeviceintelligence-removed.txt",
        "36/system/api/framework-ondeviceintelligence.txt",
        "36/system/api/framework-ondeviceintelligence-removed.txt",
        "36/module-lib/api/framework-ondeviceintelligence.txt",
        "36/module-lib/api/framework-ondeviceintelligence-removed.txt",
        "current/androidx-legacy",
        "current/extras/app-toolkit",
        "35/public/android.jar",
        "35/public/framework.aidl",
        "35/public/core-for-system-modules.jar",
        "tools/darwin/bin/aapt2",
        "tools/linux/bin/aapt2",
        "tools/windows/bin/aapt2.exe"
      ]
    },
"###, r###"    {
      "path": "prebuilts/sdk",
      "name": "platform/prebuilts/sdk",
      "commit": "0f07e8d60ab0aba46129e427101f96ba459a95c1",
      "purpose": "Pinned Android 17 released API tracking required by full vendor-image graph validation",
      "sparse_paths": [
        "28/public",
        "29/public",
        "29/system",
        "30/public",
        "31/public",
        "34/public",
        "34/system/android.jar",
        "37.0/module-lib/api",
        "37.0/public/api",
        "37.0/system-server/api",
        "37.0/system/api",
        "37.0/test/api",
        "8/public",
        "9/public",
        "Android.bp",
        "current/androidx/Android.bp",
        "current/androidx/m2repository/androidx/annotation/annotation-experimental/1.6.0",
        "current/androidx/m2repository/androidx/annotation/annotation-jvm/1.10.0",
        "current/androidx/m2repository/androidx/collection/collection-jvm/1.7.0-alpha01",
        "current/androidx/m2repository/androidx/core/core-animation-testing/1.0.0",
        "current/androidx/m2repository/androidx/core/core-animation/1.0.0",
        "current/androidx/m2repository/androidx/core/core/1.20.0-alpha01",
        "current/androidx/m2repository/androidx/leanback/leanback/1.3.0-alpha01",
        "current/androidx/m2repository/androidx/transition/transition-ktx/1.7.0-rc01",
        "current/androidx/m2repository/androidx/transition/transition/1.7.0-rc01",
        "current/androidx/m2repository/androidx/webkit/webkit/1.12.0-alpha02",
        "current/core",
        "current/module-lib",
        "current/public",
        "current/system",
        "current/system-server",
        "extensions/19/module-lib",
        "extensions/19/public",
        "extensions/19/system",
        "extensions/19/system-server",
        "tools/Android.bp",
        "tools/core-lambda-stubs.jar",
        "update_prebuilts",
        "current/androidx",
        "18/public",
        "current/multidex",
        "current/test",
        "current/support/v7/appcompat/res",
        "current/support/manifests/android-support-v7-appcompat",
        "current/extras/material-design-x",
        "36/public/api/framework-ondeviceintelligence.txt",
        "36/public/api/framework-ondeviceintelligence-removed.txt",
        "36/system/api/framework-ondeviceintelligence.txt",
        "36/system/api/framework-ondeviceintelligence-removed.txt",
        "36/module-lib/api/framework-ondeviceintelligence.txt",
        "36/module-lib/api/framework-ondeviceintelligence-removed.txt",
        "current/androidx-legacy",
        "current/extras/app-toolkit",
        "35/public/android.jar",
        "35/public/framework.aidl",
        "35/public/core-for-system-modules.jar"
      ]
    },
"###),
            (r###"    {
      "path": "system/gsid",
      "name": "platform/system/gsid",
      "commit": "35a92d40f529b605fad8ff622691e76901044cc8",
      "purpose": "Original Android 17 libgsi_headers for fs_mgr libfstab",
      "sparse_paths": [
        "Android.bp",
        "include",
        "aidl/android/gsi/AvbPublicKey.aidl",
        "aidl/android/gsi/GsiProgress.aidl",
        "aidl/android/gsi/IGsiService.aidl",
        "aidl/android/gsi/IGsiServiceCallback.aidl",
        "aidl/android/gsi/IImageService.aidl",
        "aidl/android/gsi/IProgressCallback.aidl",
        "aidl/android/gsi/MappedImage.aidl"
      ]
    },
"###, r###"    {
      "path": "system/gsid",
      "name": "platform/system/gsid",
      "commit": "35a92d40f529b605fad8ff622691e76901044cc8",
      "purpose": "Original Android 17 libgsi_headers for fs_mgr libfstab",
      "sparse_paths": [
        "Android.bp",
        "include"
      ]
    },
"###),
            (r###"    {
      "path": "system/logging",
      "name": "platform/system/logging",
      "commit": "d35ba620451b28512f46ebb5421f783fd77968d5",
      "purpose": "Android native logging",
      "sparse_paths": [
        "liblog",
        "rust",
        "logd/Android.bp",
        "logd/CommandListener.cpp",
        "logd/CompressionEngine.cpp",
        "logd/LogAudit.cpp",
        "logd/LogBufferElement.cpp",
        "logd/LogBufferTest.cpp",
        "logd/LogKlog.cpp",
        "logd/LogListener.cpp",
        "logd/LogPermissions.cpp",
        "logd/LogReader.cpp",
        "logd/LogReaderList.cpp",
        "logd/LogReaderThread.cpp",
        "logd/LogSize.cpp",
        "logd/LogStatistics.cpp",
        "logd/LogTags.cpp",
        "logd/LogdLock.cpp",
        "logd/LogdNativeService.cpp",
        "logd/PkgIds.cpp",
        "logd/PruneList.cpp",
        "logd/ReplayMessages.cpp",
        "logd/SerializedFlushToState.cpp",
        "logd/SerializedFlushToStateTest.cpp",
        "logd/SerializedLogBuffer.cpp",
        "logd/SerializedLogBufferTest.cpp",
        "logd/SerializedLogChunk.cpp",
        "logd/SerializedLogChunkTest.cpp",
        "logd/SimpleLogBuffer.cpp",
        "logd/TrustyLog.cpp",
        "logd/auditctl.cpp",
        "logd/binder",
        "logd/device_test_config.xml",
        "logd/flags",
        "logd/libaudit",
        "logd/logd_test.cpp",
        "logd/logtagd.rc",
        "logd/main.cpp"
      ]
    },
"###, r###"    {
      "path": "system/logging",
      "name": "platform/system/logging",
      "commit": "d35ba620451b28512f46ebb5421f783fd77968d5",
      "purpose": "Android native logging",
      "sparse_paths": [
        "liblog",
        "rust"
      ]
    },
"###),
            (r###"    {
      "path": "system/update_engine",
      "name": "platform/system/update_engine",
      "commit": "4591637f51644f5429f9e2fe589ab22b92f61842",
      "purpose": "Pinned update-engine headers and metadata protos required by init second stage",
      "sparse_paths": [
        "Android.bp",
        "fuzzers",
        "liburing_cpp",
        "binder_bindings/android/os/IUpdateEngine.aidl",
        "binder_bindings/android/os/IUpdateEngineCallback.aidl",
        "stable"
      ]
    },
"###, r###"    {
      "path": "system/update_engine",
      "name": "platform/system/update_engine",
      "commit": "4591637f51644f5429f9e2fe589ab22b92f61842",
      "purpose": "Pinned update-engine headers and metadata protos required by init second stage",
      "sparse_paths": [
        "Android.bp",
        "fuzzers",
        "liburing_cpp"
      ]
    },
"###),
            (r###"    {
      "path": "system/vold",
      "name": "platform/system/vold",
      "commit": "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e",
      "purpose": "Pinned filesystem-encryption headers and library required by init second stage",
      "sparse_paths": [
        "Utils.cpp",
        "tests",
        "aconfig/flags.aconfig",
        "binder/android/os/IVold.aidl",
        "binder/android/os/IVoldListener.aidl",
        "binder/android/os/IVoldMountCallback.aidl",
        "binder/android/os/IVoldTaskListener.aidl"
      ]
    },
"###, r###"    {
      "path": "system/vold",
      "name": "platform/system/vold",
      "commit": "6d20a0078c2bcaa2499dc5d032f337bfe1182d9e",
      "purpose": "Pinned filesystem-encryption headers and library required by init second stage",
      "sparse_paths": [
        "Utils.cpp",
        "tests",
        "aconfig/flags.aconfig"
      ]
    },
"###),
            (r###"    {
      "path": "external/caliper",
      "name": "platform/external/caliper",
      "commit": "d7bb09dccd464969498584337b0e68a9347b4d40",
      "purpose": "Original Caliper host providers required by retained STS utilities and their original sibling modules",
      "sparse_paths": [
        "caliper",
        "examples",
        "lib"
      ]
    },
"###, r###""###),
            (r###"    {
      "path": "external/mime-support",
      "name": "platform/external/mime-support",
      "commit": "9d71d482603aac054815958c9834ae1cd036f024",
      "purpose": "Original Debian MIME tables required by the retained framework MIME source filegroups",
      "sparse_paths": [
        "mime.types",
        "mime.types-alt"
      ]
    },
"###, r###""###),
            (r###"    {
      "path": "packages/modules/NpuManager",
      "name": "platform/packages/modules/NpuManager",
      "commit": "d194f8ada2cab31b8487fb3aaac6fd383fc7e07f",
      "purpose": "Original libandroid NPU shim, Rust AIDL provider and original SDK siblings required by the retained native graph",
      "sparse_paths": [
        "flags",
        "framework",
        "ndk"
      ]
    },
"###, r###""###),
            (r###"    {
      "path": "system/liburingutils",
      "name": "platform/system/liburingutils",
      "commit": "3d6286bdd07ec68ee6a411381e56c1aaa6e11247",
      "purpose": "Original io_uring socket helpers required by the retained logd provider and its original sibling tests",
      "sparse_paths": [
        "include",
        "src"
      ]
    },
"###, r###""###),
        ] {
            assert_eq!(previous.matches(after).count(), 1);
            previous = previous.replacen(after, before, 1);
        }
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "dbcfc28fe99865aae9b103daebdab120a8fdcb932202da183f3fd5b62e41b593");
        previous
    }

    #[test]
    fn audio_cts_sts_recursive_closure_is_a_monotonic_pinned_extension() {
        let old: SparseSourceLock = serde_json::from_str(&audio_before_cts_sts_lock()).unwrap();
        let current: SparseSourceLock = serde_json::from_str(audio_before_allgraph_lock()).unwrap();
        let before = build_plan(&old).unwrap();
        let after = build_plan(&current).unwrap();
        assert_eq!(before.projects.len(), 317);
        assert_eq!(after.projects.len(), 321);
        validate_plan_extension(&before, &after).unwrap();
        assert!(validate_plan_extension(&after, &before).is_err());
        let mut changed = after;
        changed.projects.iter_mut().find(|p| p.path == Path::new("cts")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_plan_extension(&before, &changed).is_err());
    }

    fn audio_before_jimfs_lock() -> String {
        let raw_owned = audio_before_cts_sts_lock();
        let raw = raw_owned.as_str();
        let added = r###"    {
      "path": "external/jimfs",
      "name": "platform/external/jimfs",
      "commit": "cd18acbf0036a7c6a3443e7e58b5091cacf327cf",
      "purpose": "Original Jimfs library and annotation generator required by the retained Error Prone test helper in the complete Audio APEX graph",
      "sparse_paths": [
        "jimfs"
      ]
    },
"###;
        assert_eq!(raw.matches(added).count(), 1);
        let previous = raw.replacen(added, "", 1);
        assert_eq!(format!("{:x}", Sha256::digest(previous.as_bytes())),
            "617a55af8ad550d4534220d0621a76b9a7556951a850ebac9356ebaec3fff19e");
        previous
    }

    #[test]
    fn audio_error_prone_jimfs_is_one_monotonic_pinned_project() {
        let raw_owned = audio_before_cts_sts_lock();
        let raw = raw_owned.as_str();
        let current_lock: SparseSourceLock = serde_json::from_str(raw).unwrap();
        let previous_lock: SparseSourceLock = serde_json::from_str(&audio_before_jimfs_lock()).unwrap();
        let previous = build_plan(&previous_lock).unwrap();
        let current = build_plan(&current_lock).unwrap();
        assert_eq!(previous.projects.len(), 316);
        assert_eq!(current.projects.len(), 317);
        validate_plan_extension(&previous, &current).unwrap();
        assert!(validate_plan_extension(&current, &previous).is_err());
        let project = current.projects.iter().find(|p| p.path == Path::new("external/jimfs")).unwrap();
        assert_eq!(project.commit, "cd18acbf0036a7c6a3443e7e58b5091cacf327cf");
        let mut changed = current;
        changed.projects.iter_mut().find(|p| p.path == Path::new("external/error_prone")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_plan_extension(&previous, &changed).is_err());
    }

    #[test]
    fn audio_cts_compilation_is_one_monotonic_same_commit_cone() {
        let raw_owned = audio_before_jimfs_lock();
        let raw = raw_owned.as_str();
        let current_lock: SparseSourceLock = serde_json::from_str(raw).unwrap();
        let current = build_plan(&current_lock).unwrap();
        let addition = "\"libs/vogar-expect\",\n        \"hostsidetests/compilation\"";
        assert_eq!(raw.matches(addition).count(), 1);
        let old_raw = raw.replacen(addition, "\"libs/vogar-expect\"", 1);
        assert_eq!(format!("{:x}", Sha256::digest(old_raw.as_bytes())),
            "c104640627a1beb35b25423656e751a4b56ac17287505c0ee2efeeb7d0419560");
        let old_lock: SparseSourceLock = serde_json::from_str(&old_raw).unwrap();
        let cts = old_lock.projects.iter().find(|p| p.path == Path::new("cts")).unwrap();
        assert_eq!(cts.commit, "3d1bf2a7eb2b7aaa4636c854ef481f256c40c2dd");
        let old = build_plan(&old_lock).unwrap();
        assert_eq!(old.projects.len(), 316);
        assert_eq!(current.projects.len(), 316);
        validate_plan_extension(&old, &current).unwrap();
        assert!(validate_plan_extension(&current, &old).is_err());
        let mut wrong = current;
        wrong.projects.iter_mut().find(|p| p.path == Path::new("cts")).unwrap()
            .commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_plan_extension(&old, &wrong).is_err());
    }

    #[test]
    fn audio_source_capacity_is_bound_to_the_exact_frozen_lock() {
        let raw = include_str!("../../../android/manifest/audio-bridge-source-lock.json");
        assert_eq!(format!("{:x}", Sha256::digest(raw.as_bytes())),
            "db5187942e23ef535cfc53ebe47e98ef3e258a9f79d225a621f8fd20cded9a91");
        let lock: SparseSourceLock = serde_json::from_str(raw).unwrap();
        assert_eq!(lock.projects.len(), AUDIO_SOURCE_PROJECT_COUNT);
        assert_eq!(MAX_PROJECTS, 432);
        assert_eq!(MAX_PROJECTS % 16, 0);
        assert!(MAX_PROJECTS - 16 < AUDIO_SOURCE_PROJECT_COUNT);
        assert!(AUDIO_SOURCE_PROJECT_COUNT <= MAX_PROJECTS);
        assert!(build_plan(&lock).is_ok());
    }

    #[test]
    fn audio_reconciliation_preserves_existing_gatekeeper_purpose() {
        let raw = include_str!("../../../android/manifest/audio-bridge-source-lock.json");
        let lock: SparseSourceLock = serde_json::from_str(raw).unwrap();
        let current = build_plan(&lock).unwrap();
        let mut previous = current.clone();
        let security = previous.projects.iter_mut()
            .find(|project| project.path == Path::new("system/security")).unwrap();
        for added in ["hals/Android.bp", "hals/derive", "hals/wire"] {
            let index = security.sparse_paths.iter()
                .position(|path| path == Path::new(added)).unwrap();
            security.sparse_paths.remove(index);
        }
        validate_plan_extension(&previous, &current).unwrap();

        let mut rejected = current;
        let gatekeeper = rejected.projects.iter_mut()
            .find(|project| project.path == Path::new("system/gatekeeper")).unwrap();
        assert_eq!(gatekeeper.purpose,
            "Same-superproject complete Gatekeeper Rust and header source required by the retained nonsecure Gatekeeper provider in the strict full Audio APEX graph");
        gatekeeper.purpose = "Original Gatekeeper Rust providers and their real source dependencies required by the retained libgk_ta_nonsecure consumer in the strict audio APEX graph".into();
        let SourceError::Invalid(problems) = validate_plan_extension(&previous, &rejected).unwrap_err() else {
            panic!("the actual failed Audio308 purpose change must remain rejected");
        };
        assert_eq!(problems, vec![
            "reconciliation cannot change or remove project system/gatekeeper or its existing sparse paths"
        ]);
    }

    #[test]
    fn audio_junit_extension_keeps_the_actual_previous_projects_unchanged() {
        let lock: SparseSourceLock = serde_json::from_str(&audio_before_jimfs_lock()).unwrap();
        let mut lock = lock;
        lock.projects.retain(|project| ![Path::new("tools/deviceinfra/prebuilts"), Path::new("external/deqp"), Path::new("external/deqp-deps/SPIRV-Headers"), Path::new("external/deqp-deps/SPIRV-Tools"), Path::new("external/deqp-deps/amber"), Path::new("external/deqp-deps/glslang"), Path::new("external/easymock")].contains(&project.path.as_path()));
        let current = build_plan(&lock).unwrap();
        let mut previous = current.clone();
        previous.projects.retain(|project| project.path != Path::new("external/junit-params"));
        assert_eq!(previous.projects.len(), 308);
        assert_eq!(current.projects.len(), 309);
        validate_plan_extension(&previous, &current).unwrap();
        let provider = current.projects.iter()
            .find(|project| project.path == Path::new("external/junit-params")).unwrap();
        assert_eq!(provider.url, "https://android.googlesource.com/platform/external/junit-params");
        assert_eq!(provider.commit, "1a5f3f8b0c829e257386c56cfda5e5a442377282");
        assert_eq!(provider.sparse_paths, vec![PathBuf::from("lib"), PathBuf::from("src")]);
    }


    #[test]
    fn audio_api35_cts_extension_preserves_the_previous_materialized_plan() {
        let lock: SparseSourceLock = serde_json::from_str(&audio_before_jimfs_lock()).unwrap();
        let current = build_plan(&lock).unwrap();
        let mut previous = current.clone();
        previous.projects.retain(|p| ![Path::new("tools/deviceinfra/prebuilts"), Path::new("external/deqp"), Path::new("external/deqp-deps/SPIRV-Headers"), Path::new("external/deqp-deps/SPIRV-Tools"), Path::new("external/deqp-deps/amber"), Path::new("external/deqp-deps/glslang"), Path::new("external/easymock")].contains(&p.path.as_path()));
        for (relative, added) in [
            ("prebuilts/sdk", &["35/public/android.jar", "35/public/framework.aidl", "35/public/core-for-system-modules.jar"][..]),
            ("cts", &["libs/shim", "libs/install", "hostsidetests/stagedinstall", "hostsidetests/appsecurity/test-apps/PrivilegedUpdateApp", "tools/cts-tradefed", "libs/runner", "tests/core/runner-axt", "libs/vogar-expect"][..]),
            ("external/e2fsprogs", &["debugfs", "lib", "misc", "e2fsck"][..]),
            ("platform_testing", &["scripts"][..]),
        ] {
            let project = previous.projects.iter_mut().find(|p| p.path == Path::new(relative)).unwrap();
            project.sparse_paths.retain(|p| !added.iter().any(|added| p == Path::new(added)));
        }
        assert_eq!(previous.projects.len(), 309);
        assert_eq!(current.projects.len(), 316);
        validate_plan_extension(&previous, &current).unwrap();
        let mut wrong = current;
        wrong.projects.iter_mut().find(|p| p.path == Path::new("prebuilts/sdk"))
            .unwrap().commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_plan_extension(&previous, &wrong).is_err());
    }

    #[test]
    fn project_bound_admits_superproject_gitlink_extensions_but_not_unbounded_sync() {
        let mut lock = valid_lock();
        for index in 1..MAX_PROJECTS {
            let mut project = lock.projects[0].clone();
            project.path = format!("tools/verified_extra_{index:03}").into();
            project.name = format!("platform/tools/verified_extra_{index:03}");
            lock.projects.push(project);
            if index + 1 == AUDIO_SOURCE_PROJECT_COUNT {
                assert!(build_plan(&lock).is_ok(), "the exact locked audio project count remains permitted");
            }
            if index == 224 {
                assert!(build_plan(&lock).is_ok(), "225 pinned projects must remain permitted");
            }
        }
        assert!(build_plan(&lock).is_ok(), "the bounded maximum must be accepted");
        let mut forbidden = lock.projects[0].clone();
        forbidden.path = format!("tools/verified_extra_{}", MAX_PROJECTS + 1).into();
        forbidden.name = format!("platform/tools/verified_extra_{}", MAX_PROJECTS + 1);
        lock.projects.push(forbidden);
        let SourceError::Invalid(problems) = build_plan(&lock).unwrap_err() else {
            panic!("expected strict project-count validation");
        };
        assert!(problems.iter().any(|line| line.contains(&format!("1 through {MAX_PROJECTS}"))));
    }

    #[test]
    fn source_lock_preserves_exact_sparse_paths_through_the_368_bound() {
        let mut lock = valid_lock();
        assert_eq!(MAX_SPARSE_PATHS, 368);
        assert_eq!(355_usize.div_ceil(16) * 16, MAX_SPARSE_PATHS);
        for count in [133, 256, 257, 279, 288, 289, 355, 368] {
            let paths: Vec<PathBuf> = (0..count)
                .map(|i| format!("tests/pinned_{i:03}").into())
                .collect();
            lock.projects[0].sparse_paths = paths.clone();
            let plan = build_plan(&lock).unwrap();
            assert_eq!(plan.projects[0].sparse_paths, paths);
            assert_eq!(lock.projects[0].sparse_paths, paths);
            assert_eq!(plan.projects[0].commit, lock.projects[0].commit);
            assert!(!plan.unrestricted_repo_sync);
        }
    }

    #[test]
    fn source_lock_rejects_369_sparse_paths_without_truncating_them() {
        let mut lock = valid_lock();
        let paths: Vec<PathBuf> = (0..369)
            .map(|i| format!("tests/pinned_{i:03}").into())
            .collect();
        lock.projects[0].sparse_paths = paths.clone();
        let SourceError::Invalid(problems) = build_plan(&lock).unwrap_err() else {
            panic!("expected the finite sparse-path bound");
        };
        assert!(problems.iter().any(|line| line.contains("more than 368 sparse paths")));
        assert_eq!(lock.projects[0].sparse_paths, paths);
    }

    #[test]
    fn bounded_sparse_paths_reject_duplicates_and_escapes_at_the_new_boundary() {
        let mut lock = valid_lock();
        lock.projects[0].sparse_paths = (0..368)
            .map(|i| format!("tests/pinned_{i:03}").into())
            .collect();
        let mut duplicate = lock.clone();
        duplicate.projects[0].sparse_paths[367] = duplicate.projects[0].sparse_paths[0].clone();
        assert!(build_plan(&duplicate).unwrap_err().to_string().contains("repeats sparse path"));
        for escape in ["", ".", "../outside", "/outside", "tests/../outside"] {
            let mut bad = lock.clone();
            bad.projects[0].sparse_paths[367] = escape.into();
            assert!(build_plan(&bad).unwrap_err().to_string().contains("not normalized and relative"),
                "sparse escape must remain rejected: {escape:?}");
        }
        lock.policy.allow_unrestricted_repo_sync = true;
        assert!(build_plan(&lock).is_err());
    }

    #[test]
    fn actual_git_checkout_preserves_355_cones_and_hidden_blueprints() {
        let sandbox = tempfile::tempdir().unwrap();
        let origin = sandbox.path().join("origin");
        run("git", &[OsStr::new("init"), OsStr::new("--quiet"),
            OsStr::new("--initial-branch=main"), origin.as_os_str()]).unwrap();
        let paths: Vec<PathBuf> = (0..355)
            .map(|i| format!("inputs/pinned_{i:03}").into()).collect();
        let root_bp = b"filegroup { name: \"original_root\", srcs: [] }\n";
        fs::write(origin.join("Android.bp"), root_bp).unwrap();
        for (index, path) in paths.iter().enumerate() {
            fs::create_dir_all(origin.join(path)).unwrap();
            fs::write(origin.join(path).join("source.cc"), format!("// original {index}\n")).unwrap();
            fs::write(origin.join(path).join("Android.bp"),
                format!("filegroup {{ name: \"original_{index}\", srcs: [\"source.cc\"] }}\n")).unwrap();
        }
        fs::create_dir_all(origin.join("inputs/unselected")).unwrap();
        fs::write(origin.join("inputs/unselected/Android.bp"),
            b"filegroup { name: \"must_stay_hidden\", srcs: [] }\n").unwrap();
        run_git(&origin, &[OsStr::new("add"), OsStr::new(".")]).unwrap();
        run_git(&origin, &[OsStr::new("-c"), OsStr::new("user.name=Droidloom Test"),
            OsStr::new("-c"), OsStr::new("user.email=test@droidloom.invalid"),
            OsStr::new("commit"), OsStr::new("--quiet"), OsStr::new("-m"),
            OsStr::new("current 355-cone fixture")]).unwrap();
        let head = run_git_output(&origin,
            &[OsStr::new("rev-parse"), OsStr::new("HEAD")]).unwrap();
        let mut lock = valid_lock();
        lock.links.clear();
        lock.projects[0].commit = String::from_utf8(head.stdout).unwrap().trim().to_owned();
        lock.projects[0].sparse_paths = paths.clone();
        let mut project = build_plan(&lock).unwrap().projects.remove(0);
        project.url = origin.to_string_lossy().into_owned();
        let root = sandbox.path().join("checkout");
        fs::create_dir(&root).unwrap();
        materialize_project(&root, &project).unwrap();
        let checkout = root.join(&project.path);
        assert_eq!(fs::read(checkout.join("Android.bp")).unwrap(), root_bp);
        for path in &paths {
            for filename in ["source.cc", "Android.bp"] {
                assert_eq!(fs::read(checkout.join(path).join(filename)).unwrap(),
                    fs::read(origin.join(path).join(filename)).unwrap());
            }
        }
        assert!(!checkout.join("inputs/unselected/Android.bp").exists());
        let selected = run_git_output(&checkout,
            &[OsStr::new("sparse-checkout"), OsStr::new("list")]).unwrap();
        let observed: Vec<PathBuf> = String::from_utf8(selected.stdout).unwrap()
            .lines().map(PathBuf::from).collect();
        assert_eq!(observed, paths);
    }

    #[test]
    fn plan_uses_only_exact_official_projects() {
        let plan = build_plan(&valid_lock()).unwrap();
        assert!(!plan.unrestricted_repo_sync);
        assert_eq!(plan.projects.len(), 1);
        assert_eq!(
            plan.projects[0].url,
            "https://android.googlesource.com/platform/build"
        );
        assert_eq!(
            plan.projects[0].commit,
            "5ce6f787337d0223710bf7d4a16dbe6d2a35f777"
        );
    }

    #[test]
    fn platform_compat_uses_its_official_tools_namespace() {
        let mut lock = valid_lock();
        lock.projects[0].name = "tools/platform-compat".into();
        assert_eq!(
            build_plan(&lock).unwrap().projects[0].url,
            "https://android.googlesource.com/tools/platform-compat"
        );
        for invalid in ["tools/other", "tools/platform-compat/../other"] {
            lock.projects[0].name = invalid.into();
            assert!(build_plan(&lock).is_err());
        }
    }

    #[test]
    fn traversal_and_full_sync_policy_are_rejected_together() {
        let mut lock = valid_lock();
        lock.projects[0].path = "../outside".into();
        lock.policy.allow_unrestricted_repo_sync = true;
        let SourceError::Invalid(problems) = build_plan(&lock).unwrap_err() else {
            panic!("expected validation failures");
        };
        assert!(
            problems
                .iter()
                .any(|problem| problem.contains("normalized"))
        );
        assert!(problems.iter().any(|problem| problem.contains("repo sync")));
    }

    #[test]
    fn duplicate_projects_and_moving_refs_are_rejected() {
        let mut lock = valid_lock();
        let mut duplicate = lock.projects[0].clone();
        duplicate.commit = "refs/heads/main".into();
        lock.projects.push(duplicate);
        let SourceError::Invalid(problems) = build_plan(&lock).unwrap_err() else {
            panic!("expected validation failures");
        };
        assert!(problems.iter().any(|problem| problem.contains("duplicate")));
        assert!(problems.iter().any(|problem| problem.contains("exact")));
    }

    #[test]
    fn root_links_are_relative_to_their_parent() {
        assert_eq!(
            relative_path(Path::new("build"), Path::new("build/make/core")),
            Path::new("make/core")
        );
        assert_eq!(
            relative_path(Path::new(""), Path::new("build/soong/root.bp")),
            Path::new("build/soong/root.bp")
        );
    }

    #[test]
    fn exact_local_git_fetch_and_manifest_link_are_verified() {
        let sandbox = tempfile::tempdir().unwrap();
        let origin = sandbox.path().join("origin");
        run(
            "git",
            &[
                OsStr::new("init"),
                OsStr::new("--quiet"),
                OsStr::new("--initial-branch=main"),
                origin.as_os_str(),
            ],
        )
        .unwrap();
        run_git(
            &origin,
            &[
                OsStr::new("config"),
                OsStr::new("user.email"),
                OsStr::new("test@droidloom.invalid"),
            ],
        )
        .unwrap();
        run_git(
            &origin,
            &[
                OsStr::new("config"),
                OsStr::new("user.name"),
                OsStr::new("Droidloom Test"),
            ],
        )
        .unwrap();
        fs::create_dir(origin.join("core")).unwrap();
        fs::write(origin.join("core/marker"), b"exact commit").unwrap();
        run_git(&origin, &[OsStr::new("add"), OsStr::new("core/marker")]).unwrap();
        run_git(
            &origin,
            &[
                OsStr::new("commit"),
                OsStr::new("--quiet"),
                OsStr::new("-m"),
                OsStr::new("fixture"),
            ],
        )
        .unwrap();
        let output =
            run_git_output(&origin, &[OsStr::new("rev-parse"), OsStr::new("HEAD")]).unwrap();
        let commit = String::from_utf8(output.stdout).unwrap().trim().to_owned();

        let root = sandbox.path().join("checkout");
        fs::create_dir(&root).unwrap();
        materialize_project(
            &root,
            &PlannedProject {
                path: "build/make".into(),
                url: origin.to_string_lossy().into_owned(),
                commit,
                purpose: "test fixture".into(),
                sparse_paths: vec!["core".into()],
            },
        )
        .unwrap();
        create_root_link(
            &root,
            &RootLink {
                source: "build/make/core".into(),
                target: "build/core".into(),
            },
        )
        .unwrap();
        assert_eq!(
            fs::read(root.join("build/core/marker")).unwrap(),
            b"exact commit"
        );
        assert!(
            fs::symlink_metadata(root.join("build/core"))
                .unwrap()
                .file_type()
                .is_symlink()
        );
    }

    #[test]
    fn reconciliation_accepts_only_monotonic_plan_expansion() {
        let initial = build_plan(&valid_lock()).unwrap();
        let mut expanded = initial.clone();
        expanded.projects.push(PlannedProject {
            path: "external/rust/android-crates-io".into(),
            url: "https://android.googlesource.com/platform/external/rust/android-crates-io".into(),
            commit: "1f5e95cd6e996995023c9c0f7df0f15a8a43269e".into(),
            purpose: "Rust crates".into(),
            sparse_paths: Vec::new(),
        });
        validate_plan_extension(&initial, &expanded).unwrap();

        let mut changed = expanded;
        changed.projects[0].commit = "0000000000000000000000000000000000000000".into();
        assert!(validate_plan_extension(&initial, &changed).is_err());
    }

    #[test]
    fn reconciliation_accepts_bounded_sparse_path_expansion() {
        let mut initial = build_plan(&valid_lock()).unwrap();
        initial.projects[0].sparse_paths = vec!["core".into()];

        let mut expanded = initial.clone();
        expanded.projects[0].sparse_paths.push("tools".into());
        validate_plan_extension(&initial, &expanded).unwrap();

        let mut contracted = expanded;
        contracted.projects[0].sparse_paths = vec!["tools".into()];
        assert!(validate_plan_extension(&initial, &contracted).is_err());
    }

    #[test]
    fn materialized_verification_rejects_dirty_projects() {
        let sandbox = tempfile::tempdir().unwrap();
        let root = sandbox.path().join("checkout");
        let checkout = root.join("build/make");
        fs::create_dir_all(checkout.join("core")).unwrap();
        run(
            "git",
            &[
                OsStr::new("init"),
                OsStr::new("--quiet"),
                OsStr::new("--initial-branch=main"),
                checkout.as_os_str(),
            ],
        )
        .unwrap();
        run_git(
            &checkout,
            &[
                OsStr::new("config"),
                OsStr::new("user.email"),
                OsStr::new("test@droidloom.invalid"),
            ],
        )
        .unwrap();
        run_git(
            &checkout,
            &[
                OsStr::new("config"),
                OsStr::new("user.name"),
                OsStr::new("Droidloom Test"),
            ],
        )
        .unwrap();
        run_git(
            &checkout,
            &[
                OsStr::new("remote"),
                OsStr::new("add"),
                OsStr::new("origin"),
                OsStr::new("https://android.googlesource.com/platform/build"),
            ],
        )
        .unwrap();
        fs::write(checkout.join("core/marker"), b"clean").unwrap();
        run_git(&checkout, &[OsStr::new("add"), OsStr::new("core/marker")]).unwrap();
        run_git(
            &checkout,
            &[
                OsStr::new("commit"),
                OsStr::new("--quiet"),
                OsStr::new("-m"),
                OsStr::new("fixture"),
            ],
        )
        .unwrap();

        let output =
            run_git_output(&checkout, &[OsStr::new("rev-parse"), OsStr::new("HEAD")]).unwrap();
        let mut lock = valid_lock();
        lock.projects[0].commit = String::from_utf8(output.stdout).unwrap().trim().to_owned();
        let lock_path = sandbox.path().join("lock.json");
        fs::write(&lock_path, b"exact test lock").unwrap();
        create_root_link(&root, &lock.links[0]).unwrap();
        let manifest = MaterializedManifest {
            schema_version: 1,
            source_lock_sha256: sha256_file(&lock_path).unwrap(),
            plan: build_plan(&lock).unwrap(),
        };
        fs::write(
            root.join(".droidloom-source-manifest.json"),
            serde_json::to_vec_pretty(&manifest).unwrap(),
        )
        .unwrap();

        verify_materialized(&lock_path, &lock, &root).unwrap();
        fs::write(checkout.join("core/marker"), b"dirty").unwrap();
        let error = verify_materialized(&lock_path, &lock, &root).unwrap_err();
        assert!(error.to_string().contains("local changes"));
    }
}
