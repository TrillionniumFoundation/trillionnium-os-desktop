//! Exact normal source extension for HealthFitness's retained lint dependency.
//! Existing Audio, NativePair, Production651 and CMake contracts stay separate.
use super::*;

/// Read the bounded lock; this profile validates its complete fixed scope next.
pub use super::load_lock;

const BASE_SHA: &str = "2e9877a58ebbc3625c7411d3573951afa409d9b13692468b825b4c25961ffffb";
const BASE_LOCK: &[u8] =
    include_bytes!("../../../android/manifest/production-full-cmake-source-lock.json");
/// Original project whose retained tests use its separately located lint module.
pub const HEALTH_PATH: &str = "packages/modules/HealthFitness";
/// The unchanged Gitlink from the original Android superproject.
pub const HEALTH_COMMIT: &str = "a292a16a8ac82667b65d763c00fa935cc44e9925";
/// Whole original module directory, including its checker source and unit test.
pub const LINT_PATH: &str = "lint";

fn invalid(message: &str) -> SourceError {
    SourceError::Invalid(vec![message.to_owned()])
}

fn original() -> Result<SparseSourceLock, SourceError> {
    if format!("{:x}", Sha256::digest(BASE_LOCK)) != BASE_SHA {
        return Err(invalid("original Production652 CMake lock bytes changed"));
    }
    serde_json::from_slice(BASE_LOCK)
        .map_err(|_| invalid("original Production652 CMake lock is malformed"))
}

/// Validate the original 652 projects plus the complete original lint directory.
/// No project, commit, root link, build dependency or test is removed.
///
/// # Errors
/// Rejects a partial lint module, changed original entries, policy drift and
/// every existing URL, path, duplicate and finite-profile validation failure.
pub fn build_plan(lock: &SparseSourceLock) -> Result<MaterializationPlan, SourceError> {
    // Reuse the existing finite 652/534 bounds. The exact equality below adds
    // this one independently selected profile without broadening the old one.
    let plan = super::build_plan_with_profile(lock, SourceProfile::Production652)?;
    let base = original()?;
    let mut expected = super::production_cmake::build_plan(&base)?;
    let health = expected
        .projects
        .iter_mut()
        .find(|project| project.path == Path::new(HEALTH_PATH))
        .ok_or_else(|| invalid("original HealthFitness project is absent"))?;
    if health.commit != HEALTH_COMMIT
        || health.url != format!("{OFFICIAL_REMOTE}platform/packages/modules/HealthFitness")
        || health.sparse_paths.is_empty()
        || health
            .sparse_paths
            .iter()
            .any(|path| path == Path::new(LINT_PATH))
    {
        return Err(invalid("original HealthFitness identity or sparse scope changed"));
    }
    // Keep every original cone and append the complete six-file module.
    // Other omitted test-provider directories are not silently introduced.
    health.sparse_paths.push(LINT_PATH.into());
    if plan != expected
        || lock.selected_at != base.selected_at
        || lock.status != base.status
        || lock.superproject.source_ref != base.superproject.source_ref
    {
        return Err(invalid(
            "production-full-lint requires unchanged Production652 and the complete original HealthFitness lint directory",
        ));
    }
    Ok(plan)
}

/// Materialize the explicit fixed profile through the original atomic writer.
///
/// # Errors
/// Preserves every original validation, Git provenance and writer failure.
pub fn materialize(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::materialize_with_profile(lock_path, lock, destination, SourceProfile::Production652)
}

/// Add only the complete lint directory through normal monotonic reconciliation.
///
/// # Errors
/// Rejects removed or changed projects, dirty Git trees and aliased root links.
pub fn reconcile(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::reconcile_with_profile(lock_path, lock, destination, SourceProfile::Production652)
}

/// Verify the exact new manifest and every original materialized Git checkout.
///
/// # Errors
/// Rejects a stale CMake manifest, omitted inputs, wrong Git identity or dirt.
pub fn verify_materialized(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::verify_materialized_with_profile(
        lock_path,
        lock,
        destination,
        SourceProfile::Production652,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lock() -> SparseSourceLock {
        serde_json::from_slice(include_bytes!(
            "../../../android/manifest/production-full-lint-source-lock.json"
        ))
        .unwrap()
    }

    fn health(lock: &mut SparseSourceLock) -> &mut SparseProject {
        lock.projects
            .iter_mut()
            .find(|project| project.path == Path::new(HEALTH_PATH))
            .unwrap()
    }

    #[test]
    fn lint_profile_extends_only_the_complete_original_lint_directory() {
        let base = original().unwrap();
        let prior = crate::production_cmake::build_plan(&base).unwrap();
        let current = lock();
        let plan = build_plan(&current).unwrap();
        assert_eq!(plan.projects.len(), 652);
        assert_eq!(plan.links, prior.links);
        assert_eq!(plan.superproject_commit, prior.superproject_commit);
        let mut changed = Vec::new();
        for (old, new) in prior.projects.iter().zip(&plan.projects) {
            if old != new {
                changed.push(old.path.as_path());
                let mut complete = old.clone();
                complete.sparse_paths.push(LINT_PATH.into());
                assert_eq!(&complete, new);
                assert_eq!(new.commit, HEALTH_COMMIT);
            }
        }
        assert_eq!(changed, vec![Path::new(HEALTH_PATH)]);
        assert!(!plan.unrestricted_repo_sync);
        super::super::validate_plan_extension(&prior, &plan).unwrap();
        assert!(super::super::validate_plan_extension(&plan, &prior).is_err());
        assert!(crate::production_cmake::build_plan(&current).is_err());
        assert!(crate::production_full::build_plan(&current).is_err());
        assert!(crate::native_pair::build_plan(&current).is_err());
        assert!(crate::build_plan(&current).is_err());
        assert!(build_plan(&base).is_err());
    }

    #[test]
    fn lint_profile_rejects_partial_provider_repin_and_wrong_project() {
        for mutation in 0..8 {
            let mut bad = lock();
            let project = health(&mut bad);
            match mutation {
                0 => {
                    project.sparse_paths.pop();
                    project.sparse_paths.push("lint/Android.bp".into());
                }
                1 => {
                    project.sparse_paths.pop();
                    project.sparse_paths.push("lint/src".into());
                }
                2 => project.sparse_paths.clear(),
                3 => project.commit = "0".repeat(40),
                4 => project.name = "platform/packages/apps/HealthFitness".into(),
                5 => project.path = "packages/apps/HealthFitness".into(),
                6 => project.purpose = "unreviewed source".into(),
                7 => project.path = "../outside".into(),
                _ => unreachable!(),
            }
            assert!(build_plan(&bad).is_err(), "mutation {mutation}");
        }
    }

    #[test]
    fn lint_profile_rejects_unrelated_projects_metadata_and_policy_changes() {
        for mutation in 0..11 {
            let mut bad = lock();
            match mutation {
                0 => bad.projects[0].commit = "0".repeat(40),
                1 => bad.projects.swap(0, 1),
                2 => bad.projects[0].sparse_paths = vec!["unreviewed".into()],
                3 => bad.superproject.commit = "0".repeat(40),
                4 => bad.superproject.source_ref = "refs/heads/android-other".into(),
                5 => bad.selected_at = "unreviewed".into(),
                6 => bad.status = "build_proven".into(),
                7 => bad.policy.allow_unrestricted_repo_sync = true,
                8 => bad.links.pop().map(drop).unwrap(),
                9 => bad.projects.push(bad.projects[0].clone()),
                10 => {
                    bad.projects.remove(0);
                }
                _ => unreachable!(),
            }
            assert!(build_plan(&bad).is_err(), "mutation {mutation}");
        }
    }

    #[test]
    fn lint_operations_reject_incomplete_scope_before_any_source_io() {
        let directory = tempfile::tempdir().unwrap();
        let absent = directory.path().join("must-not-exist");
        let missing_lock = directory.path().join("missing-lock.json");
        let old = original().unwrap();
        let mut incomplete = lock();
        health(&mut incomplete).sparse_paths = vec!["lint".into()];
        for bad in [&old, &incomplete] {
            assert!(materialize(&missing_lock, bad, &absent).is_err());
            assert!(reconcile(&missing_lock, bad, &absent).is_err());
            assert!(verify_materialized(&missing_lock, bad, &absent).is_err());
        }
        assert_eq!(fs::read_dir(directory.path()).unwrap().count(), 0);
    }

    #[test]
    fn lint_verification_never_rewrites_the_original_cmake_manifest() {
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("source");
        fs::create_dir(&source).unwrap();
        let base = original().unwrap();
        let prior = MaterializedManifest {
            schema_version: 1,
            source_lock_sha256: BASE_SHA.into(),
            plan: crate::production_cmake::build_plan(&base).unwrap(),
        };
        let bytes = serde_json::to_vec_pretty(&prior).unwrap();
        let manifest = source.join(".droidloom-source-manifest.json");
        fs::write(&manifest, &bytes).unwrap();
        let repo = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap();
        let new_path = repo.join("android/manifest/production-full-lint-source-lock.json");
        assert!(verify_materialized(&new_path, &lock(), &source).is_err());
        assert_eq!(fs::read(manifest).unwrap(), bytes);
        assert_eq!(fs::read_dir(source).unwrap().count(), 1);
    }
}
