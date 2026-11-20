//! Exact source extension for original IPsec and Permission APEX declarations.
//! These upstream test modules remain non-installable; production dependencies
//! still need their names while Soong validates the complete strict graph.
use super::*;

/// Read a bounded lock before this profile validates its exact scope.
pub use super::load_lock;

const BASE_SHA: &str = "aa14d968c14c2febcfacbb90e82598e2ba8e57f4bbb2cfc8f1f2a741555153ca";
const BASE_LOCK: &[u8] =
    include_bytes!("../../../android/manifest/production-full-lint-source-lock.json");

/// Original project path, unchanged superproject Gitlink and complete directory.
/// Each selected directory contains its original Android.bp and JSON manifest.
pub const PROVIDERS: &[(&str, &str, &str)] = &[
    (
        "packages/modules/IPsec",
        "5c58f82cc230a9a4e22c80d6eaec62dffaec4444",
        "apex/testing",
    ),
    (
        "packages/modules/Permission",
        "1093eca7407576c72e51b1a88550ee0667a6e5dc",
        "testing",
    ),
];

fn invalid(message: &str) -> SourceError {
    SourceError::Invalid(vec![message.to_owned()])
}

fn original() -> Result<SparseSourceLock, SourceError> {
    if format!("{:x}", Sha256::digest(BASE_LOCK)) != BASE_SHA {
        return Err(invalid("original Production652 lint lock bytes changed"));
    }
    serde_json::from_slice(BASE_LOCK)
        .map_err(|_| invalid("original Production652 lint lock is malformed"))
}

/// Retain all original projects and add only both complete APEX test directories.
///
/// # Errors
/// Rejects partial providers, changed Gitlinks, unrelated scope changes and every
/// existing URL, path, duplicate, policy and finite-profile validation failure.
pub fn build_plan(lock: &SparseSourceLock) -> Result<MaterializationPlan, SourceError> {
    let plan = super::build_plan_with_profile(lock, SourceProfile::Production652)?;
    let base = original()?;
    let mut expected = super::production_lint::build_plan(&base)?;
    for &(path, commit, cone) in PROVIDERS {
        let project = expected
            .projects
            .iter_mut()
            .find(|project| project.path == Path::new(path))
            .ok_or_else(|| invalid("original APEX provider project is absent"))?;
        if project.commit != commit
            || project.url != format!("{OFFICIAL_REMOTE}platform/{path}")
            || project.sparse_paths.is_empty()
            || project.sparse_paths.iter().any(|item| item == Path::new(cone))
        {
            return Err(invalid("original APEX provider identity or scope changed"));
        }
        project.sparse_paths.push(cone.into());
    }
    if plan != expected
        || lock.selected_at != base.selected_at
        || lock.status != base.status
        || lock.superproject.source_ref != base.superproject.source_ref
    {
        return Err(invalid(
            "production-full-apex-tests requires unchanged Production652 lint and both complete original APEX test directories",
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

/// Add both original provider directories using normal monotonic reconciliation.
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
/// Rejects the old lint manifest, missing inputs, wrong Git identity and dirt.
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
            "../../../android/manifest/production-full-apex-tests-source-lock.json"
        ))
        .unwrap()
    }

    fn project<'a>(lock: &'a mut SparseSourceLock, path: &str) -> &'a mut SparseProject {
        lock.projects
            .iter_mut()
            .find(|project| project.path == Path::new(path))
            .unwrap()
    }

    #[test]
    fn apex_test_profile_retains_all_original_projects_and_adds_only_two_whole_directories() {
        let base = original().unwrap();
        let prior = crate::production_lint::build_plan(&base).unwrap();
        let current = lock();
        let plan = build_plan(&current).unwrap();
        assert_eq!(plan.projects.len(), 652);
        assert_eq!(plan.links, prior.links);
        assert_eq!(plan.superproject_commit, prior.superproject_commit);
        let mut changed = Vec::new();
        for (old, new) in prior.projects.iter().zip(&plan.projects) {
            let mut expected = old.clone();
            if let Some(&(_, commit, cone)) = PROVIDERS
                .iter()
                .find(|(path, _, _)| old.path == Path::new(path))
            {
                expected.sparse_paths.push(cone.into());
                assert_eq!(new.commit, commit);
                changed.push(old.path.as_path());
            }
            assert_eq!(&expected, new);
        }
        assert_eq!(changed.len(), 2);
        assert!(PROVIDERS.iter().all(|(path, _, _)| changed.contains(&Path::new(path))));
        assert!(!plan.unrestricted_repo_sync);
        super::super::validate_plan_extension(&prior, &plan).unwrap();
        assert!(super::super::validate_plan_extension(&plan, &prior).is_err());
        assert!(crate::production_lint::build_plan(&current).is_err());
        assert!(crate::production_cmake::build_plan(&current).is_err());
        assert!(crate::production_full::build_plan(&current).is_err());
        assert!(crate::native_pair::build_plan(&current).is_err());
        assert!(crate::build_plan(&current).is_err());
        assert!(build_plan(&base).is_err());
    }

    #[test]
    fn apex_test_profile_rejects_each_partial_provider_repin_and_wrong_project() {
        for &(path, _, cone) in PROVIDERS {
            for mutation in 0..9 {
                let mut bad = lock();
                let selected = project(&mut bad, path);
                match mutation {
                    0 => { selected.sparse_paths.pop(); }
                    1 => {
                        selected.sparse_paths.pop();
                        selected.sparse_paths.push(format!("{cone}/Android.bp").into());
                    }
                    2 => selected.sparse_paths.clear(),
                    3 => selected.commit = "0".repeat(40),
                    4 => selected.name = "platform/packages/apps/Unreviewed".into(),
                    5 => selected.path = "packages/apps/Unreviewed".into(),
                    6 => selected.purpose = "unreviewed source".into(),
                    7 => selected.sparse_paths.push(cone.into()),
                    8 => selected.sparse_paths.push("../outside".into()),
                    _ => unreachable!(),
                }
                assert!(build_plan(&bad).is_err(), "{path} mutation {mutation}");
            }
        }
    }

    #[test]
    fn apex_test_profile_rejects_unrelated_scope_metadata_and_policy_changes() {
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
                10 => { bad.projects.remove(0); }
                _ => unreachable!(),
            }
            assert!(build_plan(&bad).is_err(), "mutation {mutation}");
        }
    }

    #[test]
    fn apex_test_operations_reject_incomplete_scope_before_any_source_io() {
        let directory = tempfile::tempdir().unwrap();
        let absent = directory.path().join("must-not-exist");
        let missing_lock = directory.path().join("missing-lock.json");
        let old = original().unwrap();
        let mut partial = lock();
        project(&mut partial, PROVIDERS[0].0).sparse_paths.pop();
        for bad in [&old, &partial] {
            assert!(materialize(&missing_lock, bad, &absent).is_err());
            assert!(reconcile(&missing_lock, bad, &absent).is_err());
            assert!(verify_materialized(&missing_lock, bad, &absent).is_err());
        }
        assert_eq!(fs::read_dir(directory.path()).unwrap().count(), 0);
    }

    #[test]
    fn apex_test_verification_never_rewrites_the_original_lint_manifest() {
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("source");
        fs::create_dir(&source).unwrap();
        let base = original().unwrap();
        let prior = MaterializedManifest {
            schema_version: 1,
            source_lock_sha256: BASE_SHA.into(),
            plan: crate::production_lint::build_plan(&base).unwrap(),
        };
        let bytes = serde_json::to_vec_pretty(&prior).unwrap();
        let manifest = source.join(".droidloom-source-manifest.json");
        fs::write(&manifest, &bytes).unwrap();
        let repo = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent().unwrap().parent().unwrap();
        let current = repo.join("android/manifest/production-full-apex-tests-source-lock.json");
        assert!(verify_materialized(&current, &lock(), &source).is_err());
        assert_eq!(fs::read(manifest).unwrap(), bytes);
        assert_eq!(fs::read_dir(source).unwrap().count(), 1);
    }
}
