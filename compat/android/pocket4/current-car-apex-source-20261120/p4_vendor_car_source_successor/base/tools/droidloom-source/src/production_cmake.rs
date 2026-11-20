//! Exact production source extension for the original Binder SDK host tools.
//! The historical Production651, Audio541 and NativePair contracts stay separate.
use super::*;

/// Read the bounded source lock; the explicit CMake profile validates it next.
pub use super::load_lock;

pub(super) const MAX_PROJECTS: usize = 652;
pub(super) const MAX_SPARSE_PATHS: usize = 534;
const BASE_SHA: &str = "30dcc1b5b090530b3fc06aeb3e489a961b0fc7c6368ed9d19eb0a1b2054e3eb4";
const BASE_LOCK: &[u8] =
    include_bytes!("../../../android/manifest/production-full-source-lock.json");
/// Complete project path recorded by the selected original superproject.
pub const CMAKE_PATH: &str = "prebuilts/cmake/linux-x86";
/// Official project name recorded by the original .gitmodules.
pub const CMAKE_NAME: &str = "platform/prebuilts/cmake/linux-x86";
/// Exact original 28f0bbdd superproject Gitlink; this is not a moving branch.
pub const CMAKE_COMMIT: &str = "d3078fda401bc334507d7831e30fca9273630e8c";
/// Inclusion reason shared with the exact extended lock.
pub const CMAKE_PURPOSE: &str = "Complete original superproject CMake provider for retained Binder SDK cmake, ctest and cmake_root dependencies";

fn invalid(message: &str) -> SourceError {
    SourceError::Invalid(vec![message.to_owned()])
}

fn original() -> Result<SparseSourceLock, SourceError> {
    if format!("{:x}", Sha256::digest(BASE_LOCK)) != BASE_SHA {
        return Err(invalid("original Production651 lock bytes changed"));
    }
    serde_json::from_slice(BASE_LOCK)
        .map_err(|_| invalid("original Production651 lock is malformed"))
}

/// Validate only the original 651 projects plus the complete exact CMake project.
///
/// # Errors
/// Rejects changed original entries, different upstream pins, incomplete cones,
/// metadata drift and all existing URL/path/duplicate/source-policy failures.
pub fn build_plan(lock: &SparseSourceLock) -> Result<MaterializationPlan, SourceError> {
    let plan = super::build_plan_with_profile(lock, SourceProfile::Production652)?;
    let base = original()?;
    let mut expected = super::production_full::build_plan(&base)?;
    expected.projects.push(PlannedProject {
        path: CMAKE_PATH.into(),
        url: format!("{OFFICIAL_REMOTE}{CMAKE_NAME}"),
        commit: CMAKE_COMMIT.to_owned(),
        purpose: CMAKE_PURPOSE.to_owned(),
        sparse_paths: Vec::new(),
    });
    if plan != expected
        || lock.selected_at != base.selected_at
        || lock.status != base.status
        || lock.superproject.source_ref != base.superproject.source_ref
    {
        return Err(invalid(
            "production-full-cmake requires unchanged Production651 and exactly the complete original CMake Gitlink",
        ));
    }
    Ok(plan)
}

/// Materialize the explicit 652-project profile through the normal atomic writer.
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

/// Extend an existing verified manifest only through normal monotonic reconciliation.
///
/// # Errors
/// Rejects removed or changed old projects, dirty Git trees and aliased root links.
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
/// Rejects a stale 651 manifest, missing provider, wrong Git commit/origin or dirt.
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
            "../../../android/manifest/production-full-cmake-source-lock.json"
        ))
        .unwrap()
    }

    #[test]
    fn cmake_profile_extends_only_the_complete_original_651_plan() {
        let base = original().unwrap();
        let base_plan = crate::production_full::build_plan(&base).unwrap();
        let new = lock();
        let plan = build_plan(&new).unwrap();
        assert_eq!(base_plan.projects.len(), 651);
        assert_eq!(plan.projects.len(), 652);
        assert_eq!(&plan.projects[..651], base_plan.projects.as_slice());
        assert_eq!(plan.links, base_plan.links);
        assert_eq!(plan.superproject_commit, base_plan.superproject_commit);
        assert_eq!(plan.projects[651].path, Path::new(CMAKE_PATH));
        assert_eq!(plan.projects[651].commit, CMAKE_COMMIT);
        assert!(plan.projects[651].sparse_paths.is_empty());
        assert!(!plan.unrestricted_repo_sync);
        super::super::validate_plan_extension(&base_plan, &plan).unwrap();
        assert!(super::super::validate_plan_extension(&plan, &base_plan).is_err());
        assert!(crate::production_full::build_plan(&new).is_err());
        assert!(crate::build_plan(&new).is_err());
        assert!(crate::native_pair::build_plan(&new).is_err());
        assert!(build_plan(&base).is_err());
    }

    #[test]
    fn cmake_profile_rejects_repins_wrong_provider_and_incomplete_resources() {
        let full = lock();
        for mutation in 0..8 {
            let mut bad = full.clone();
            let last = bad.projects.last_mut().unwrap();
            match mutation {
                0 => last.commit = "0".repeat(40),
                1 => last.name = "platform/external/cmake".into(),
                2 => last.path = "external/cmake".into(),
                3 => last.sparse_paths = vec!["bin".into()],
                4 => last.sparse_paths = vec!["Android.bp".into()],
                5 => last.purpose = "Unreviewed provider".into(),
                6 => last.path = "../outside".into(),
                7 => last.name = "https://example.invalid/cmake".into(),
                _ => unreachable!(),
            }
            assert!(build_plan(&bad).is_err(), "mutation {mutation}");
        }
        let mut added = full.clone();
        added.projects.push(added.projects[0].clone());
        assert!(build_plan(&added).is_err());
        let mut removed = full;
        removed.projects.remove(0);
        assert!(build_plan(&removed).is_err());
    }

    #[test]
    fn cmake_profile_rejects_original_project_and_policy_drift() {
        let full = lock();
        for mutation in 0..9 {
            let mut bad = full.clone();
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
                _ => unreachable!(),
            }
            assert!(build_plan(&bad).is_err(), "mutation {mutation}");
        }
    }

    #[test]
    fn cmake_operations_reject_wrong_scope_before_any_source_io() {
        let directory = tempfile::tempdir().unwrap();
        let absent = directory.path().join("must-not-exist");
        let nonexistent_lock = directory.path().join("missing-lock.json");
        let old = original().unwrap();
        let mut incomplete = lock();
        incomplete.projects.last_mut().unwrap().sparse_paths = vec!["bin".into()];
        for bad in [&old, &incomplete] {
            assert!(materialize(&nonexistent_lock, bad, &absent).is_err());
            assert!(reconcile(&nonexistent_lock, bad, &absent).is_err());
            assert!(verify_materialized(&nonexistent_lock, bad, &absent).is_err());
        }
        assert_eq!(fs::read_dir(directory.path()).unwrap().count(), 0);
    }

    #[test]
    fn cmake_verification_does_not_rewrite_an_original_651_manifest() {
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("source");
        fs::create_dir(&source).unwrap();
        let base = original().unwrap();
        let prior = MaterializedManifest {
            schema_version: 1,
            source_lock_sha256: BASE_SHA.to_owned(),
            plan: crate::production_full::build_plan(&base).unwrap(),
        };
        let bytes = serde_json::to_vec_pretty(&prior).unwrap();
        let path = source.join(".droidloom-source-manifest.json");
        fs::write(&path, &bytes).unwrap();
        let repo = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap();
        let new_path = repo.join("android/manifest/production-full-cmake-source-lock.json");
        assert!(verify_materialized(&new_path, &lock(), &source).is_err());
        assert_eq!(fs::read(path).unwrap(), bytes);
        assert_eq!(fs::read_dir(source).unwrap().count(), 1);
    }
}
