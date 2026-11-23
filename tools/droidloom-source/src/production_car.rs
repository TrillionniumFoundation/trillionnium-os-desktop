//! Exact original Car APEX source closure for the strict normal vendor graph.
//! Historical 652-project profiles remain independent recovery contracts.
use super::*;

/// Read a bounded lock; this profile validates its complete exact scope next.
pub use super::load_lock;

pub(super) const MAX_PROJECTS: usize = 653;
pub(super) const MAX_SPARSE_PATHS: usize = 534;
const BASE_SHA: &str = "14fd227541b01876c7e34d7e6a1ffcb2a202d97d94c6a8f6e14be369e4b79505";
const BASE_LOCK: &[u8] =
    include_bytes!("../../../android/manifest/production-full-apex-tests-source-lock.json");

/// Original project, unchanged superproject Gitlink and complete required cone.
/// Ancestor Android.bp files are retained by the normal Git cone materializer.
pub const PROVIDERS: &[(&str, &str, &str)] = &[
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "apex_car_framework"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "car-lib-module"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "car-lib/generated-prop-config"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "service/proto"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "service/res"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "service/src"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "packages/ScriptExecutor/res"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "packages/ScriptExecutor/src"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/power/aidl"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/telemetry/cartelemetryd/aidl"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/telemetry/cartelemetryd/src"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/telemetry/cartelemetryd/tests"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "cpp/telemetry/proto"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "libs/car-watchdog-lib"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "libs/procfs-inspector/client"),
    ("packages/services/Car", "9f04df65daa8b9a65ee05fd4039fe95446874d76", "data/etc"),
    ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "automotive/telemetry/aidl/aidl_api"),
    ("frameworks/hardware/interfaces", "9de6d032a248523c22d0bd86e224d1762355c41e", "automotive/telemetry/aidl/android"),
];

/// Actual provider path and name in the same original AOSP superproject.
pub const SERVICES_PATH: &str = "frameworks/opt/car/services";
/// Official repository name of the original system-server provider.
pub const SERVICES_NAME: &str = "platform/frameworks/opt/car/services";
/// Exact original 28f0bbdd superproject Gitlink, not a moving release ref.
pub const SERVICES_COMMIT: &str = "2bb3349c1a84b9b15c5ef05ef9c2e3dc6dde427a";
/// Inclusion reason shared by the exact new lock and compiled validator.
pub const SERVICES_PURPOSE: &str = "Original superproject Car framework system-server module, builtin API and protobuf source required by com.android.car.framework";
/// Complete original Java, API and protobuf providers; no unrelated test tree.
pub const SERVICES_CONES: &[&str] = &[
    "builtInServices/api",
    "builtInServices/proto",
    "builtInServices/src",
    "updatableServices/src",
];

fn invalid(message: &str) -> SourceError {
    SourceError::Invalid(vec![message.to_owned()])
}

fn original() -> Result<SparseSourceLock, SourceError> {
    if format!("{:x}", Sha256::digest(BASE_LOCK)) != BASE_SHA {
        return Err(invalid("original Production652 APEX-test lock bytes changed"));
    }
    serde_json::from_slice(BASE_LOCK)
        .map_err(|_| invalid("original Production652 APEX-test lock is malformed"))
}

/// Retain all original projects and add only the authenticated Car dependency closure.
///
/// # Errors
/// Rejects every changed old identity, missing source cone, unrelated extension,
/// altered policy and existing path, URL or duplicate validation failure.
pub fn build_plan(lock: &SparseSourceLock) -> Result<MaterializationPlan, SourceError> {
    let plan = super::build_plan_with_profile(lock, SourceProfile::Production653)?;
    let base = original()?;
    let mut expected = super::production_apex_tests::build_plan(&base)?;
    for &(path, commit, cone) in PROVIDERS {
        let project = expected.projects.iter_mut()
            .find(|project| project.path == Path::new(path))
            .ok_or_else(|| invalid("original Car dependency project is absent"))?;
        if project.commit != commit
            || project.url != format!("{OFFICIAL_REMOTE}platform/{path}")
            || project.sparse_paths.is_empty()
            || project.sparse_paths.iter().any(|item| item == Path::new(cone))
        {
            return Err(invalid("original Car dependency identity or scope changed"));
        }
        project.sparse_paths.push(cone.into());
    }
    expected.projects.push(PlannedProject {
        path: SERVICES_PATH.into(),
        url: format!("{OFFICIAL_REMOTE}{SERVICES_NAME}"),
        commit: SERVICES_COMMIT.to_owned(),
        purpose: SERVICES_PURPOSE.to_owned(),
        sparse_paths: SERVICES_CONES.iter().map(PathBuf::from).collect(),
    });
    if plan != expected
        || lock.selected_at != base.selected_at
        || lock.status != base.status
        || lock.superproject.source_ref != base.superproject.source_ref
    {
        return Err(invalid(
            "production-full-car requires unchanged Production652 plus exactly the original Car APEX dependency closure",
        ));
    }
    Ok(plan)
}

/// Materialize the named profile through the unchanged normal atomic writer.
///
/// # Errors
/// Preserves the original exact Git provenance, path validation and writer failures.
pub fn materialize(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::materialize_with_profile(lock_path, lock, destination, SourceProfile::Production653)
}

/// Add only this fixed closure using the unchanged monotonic source reconciler.
///
/// # Errors
/// Rejects dirty trees, missing old inputs, changed Gitlinks and root-link aliases.
pub fn reconcile(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::reconcile_with_profile(lock_path, lock, destination, SourceProfile::Production653)
}

/// Verify the exact new manifest and every real original materialized Git input.
///
/// # Errors
/// Rejects an unreconciled 652 manifest, partial source, wrong Git identity or dirt.
pub fn verify_materialized(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::verify_materialized_with_profile(
        lock_path, lock, destination, SourceProfile::Production653,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lock() -> SparseSourceLock {
        serde_json::from_slice(include_bytes!(
            "../../../android/manifest/production-full-car-source-lock.json"
        )).unwrap()
    }

    fn project<'a>(lock: &'a mut SparseSourceLock, path: &str) -> &'a mut SparseProject {
        lock.projects.iter_mut().find(|project| project.path == Path::new(path)).unwrap()
    }

    #[test]
    fn car_profile_retains_original_652_and_adds_only_authenticated_provider_sources() {
        let base = original().unwrap();
        let prior = crate::production_apex_tests::build_plan(&base).unwrap();
        let current = lock();
        let plan = build_plan(&current).unwrap();
        assert_eq!(prior.projects.len(), 652);
        assert_eq!(plan.projects.len(), 653);
        for (old, new) in prior.projects.iter().zip(&plan.projects) {
            let mut expected = old.clone();
            for &(path, commit, cone) in PROVIDERS {
                if old.path == Path::new(path) {
                    assert_eq!(old.commit, commit);
                    expected.sparse_paths.push(cone.into());
                }
            }
            assert_eq!(&expected, new);
        }
        let service = plan.projects.last().unwrap();
        assert_eq!(service.path, Path::new(SERVICES_PATH));
        assert_eq!(service.url, format!("{OFFICIAL_REMOTE}{SERVICES_NAME}"));
        assert_eq!(service.commit, SERVICES_COMMIT);
        assert_eq!(service.purpose, SERVICES_PURPOSE);
        assert_eq!(service.sparse_paths, SERVICES_CONES.iter().map(PathBuf::from).collect::<Vec<_>>());
        assert_eq!(plan.links, prior.links);
        assert_eq!(plan.superproject_commit, prior.superproject_commit);
        assert!(!plan.unrestricted_repo_sync);
        super::super::validate_plan_extension(&prior, &plan).unwrap();
        assert!(super::super::validate_plan_extension(&plan, &prior).is_err());
        assert!(crate::production_apex_tests::build_plan(&current).is_err());
        assert!(crate::production_lint::build_plan(&current).is_err());
        assert!(crate::production_cmake::build_plan(&current).is_err());
        assert!(crate::production_full::build_plan(&current).is_err());
        assert!(crate::native_pair::build_plan(&current).is_err());
        assert!(crate::build_plan(&current).is_err());
        assert!(build_plan(&base).is_err());
    }

    #[test]
    fn car_profile_rejects_each_missing_partial_duplicate_or_repinned_source_cone() {
        for &(path, _, cone) in PROVIDERS {
            for mutation in 0..7 {
                let mut bad = lock();
                let selected = project(&mut bad, path);
                let index = selected.sparse_paths.iter().position(|p| p == Path::new(cone)).unwrap();
                match mutation {
                    0 => { selected.sparse_paths.remove(index); }
                    1 => selected.sparse_paths[index] = format!("{cone}/Android.bp").into(),
                    2 => selected.sparse_paths.clear(),
                    3 => selected.commit = "0".repeat(40),
                    4 => selected.sparse_paths.push(cone.into()),
                    5 => selected.purpose = "unreviewed source".into(),
                    6 => selected.sparse_paths[index] = "../outside".into(),
                    _ => unreachable!(),
                }
                assert!(build_plan(&bad).is_err(), "{path}/{cone} mutation {mutation}");
            }
        }
    }

    #[test]
    fn car_profile_rejects_foreign_service_gitlink_and_incomplete_api_or_proto() {
        for mutation in 0..10 {
            let mut bad = lock();
            let service = project(&mut bad, SERVICES_PATH);
            match mutation {
                0 => service.commit = "0".repeat(40),
                1 => service.name = "platform/frameworks/opt/other".into(),
                2 => service.path = "frameworks/opt/other".into(),
                3 => service.purpose = "unreviewed service".into(),
                4 => service.sparse_paths.clear(),
                5 => service.sparse_paths = vec!["updatableServices/Android.bp".into()],
                6 => { service.sparse_paths.remove(0); }
                7 => { service.sparse_paths.remove(1); }
                8 => service.sparse_paths.push("unreviewed".into()),
                9 => service.sparse_paths.swap(0, 1),
                _ => unreachable!(),
            }
            assert!(build_plan(&bad).is_err(), "service mutation {mutation}");
        }
    }

    #[test]
    fn car_profile_rejects_unrelated_metadata_scope_and_source_policy_changes() {
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
    fn car_operations_reject_old_or_partial_scope_before_source_io() {
        let directory = tempfile::tempdir().unwrap();
        let absent = directory.path().join("must-not-exist");
        let missing_lock = directory.path().join("missing-lock.json");
        let old = original().unwrap();
        let mut partial = lock();
        partial.projects.pop();
        for bad in [&old, &partial] {
            assert!(materialize(&missing_lock, bad, &absent).is_err());
            assert!(reconcile(&missing_lock, bad, &absent).is_err());
            assert!(verify_materialized(&missing_lock, bad, &absent).is_err());
        }
        assert_eq!(fs::read_dir(directory.path()).unwrap().count(), 0);
    }

    #[test]
    fn car_verification_never_rewrites_original_652_manifest() {
        let directory = tempfile::tempdir().unwrap();
        let source = directory.path().join("source");
        fs::create_dir(&source).unwrap();
        let prior = MaterializedManifest {
            schema_version: 1,
            source_lock_sha256: BASE_SHA.into(),
            plan: crate::production_apex_tests::build_plan(&original().unwrap()).unwrap(),
        };
        let bytes = serde_json::to_vec_pretty(&prior).unwrap();
        let manifest = source.join(".droidloom-source-manifest.json");
        fs::write(&manifest, &bytes).unwrap();
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let current = repo.join("android/manifest/production-full-car-source-lock.json");
        assert!(verify_materialized(&current, &lock(), &source).is_err());
        assert_eq!(fs::read(manifest).unwrap(), bytes);
        assert_eq!(fs::read_dir(source).unwrap().count(), 1);
    }
}


/// Resume verified disjoint source checkouts under the exact production lock.
pub fn materialize_resuming(
    lock_path: &Path, lock: &SparseSourceLock, destination: &Path,
    resume: Option<&Path>, progress: &Path,
) -> Result<MaterializedManifest, SourceError> {
    materialize_resuming_with_jobs(lock_path, lock, destination, resume, progress, 1)
}

/// Limit parallel official Git requests when restoring a verified source tree.
pub fn materialize_resuming_with_jobs(
    lock_path: &Path, lock: &SparseSourceLock, destination: &Path,
    resume: Option<&Path>, progress: &Path, jobs: usize,
) -> Result<MaterializedManifest, SourceError> {
    super::resume::materialize_for_profile(lock_path, lock, destination, resume, progress, true, jobs)
}
