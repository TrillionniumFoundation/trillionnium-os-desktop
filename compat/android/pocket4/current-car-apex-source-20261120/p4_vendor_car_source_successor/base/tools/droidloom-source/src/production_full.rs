//! Fixed bounded source API for the complete Audio541/Native645 production union.
//! Existing Audio and NativePair contracts remain independent.
use super::*;

pub(super) const MAX_PROJECTS: usize = 651;
pub(super) const MAX_SPARSE_PATHS: usize = 534;

/// Read a bounded source lock; the next operation validates the production profile.
pub use super::load_lock;

/// Validate the fixed-size same-superproject production plan without I/O.
/// # Errors
/// Rejects foreign dimensions and all existing source-policy violations.
pub fn build_plan(lock: &SparseSourceLock) -> Result<MaterializationPlan, SourceError> {
    let plan = super::build_plan_with_profile(lock, SourceProfile::Production651)?;
    if plan.projects.len() != MAX_PROJECTS
        || plan.links.len() != 8
        || plan.superproject_commit != "28f0bbddc24d56c8ec5a8df5342ac7a292184039"
    {
        return Err(SourceError::Invalid(vec![
            "production-full requires the fixed 651-project, eight-link Android17 superproject union".into(),
        ]));
    }
    Ok(plan)
}

/// Materialize the complete production profile with the original atomic writer.
/// # Errors
/// Preserves all validation, original Git provenance and writer failures.
pub fn materialize(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::materialize_with_profile(lock_path, lock, destination, SourceProfile::Production651)
}

/// Reconcile only a monotonic extension through the original normal writer.
/// # Errors
/// Rejects non-monotonic, dirty, repinned or aliased source as before.
pub fn reconcile(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    build_plan(lock)?;
    super::reconcile_with_profile(lock_path, lock, destination, SourceProfile::Production651)
}

/// Verify every materialized project, Git revision and root link.
/// # Errors
/// Requires the complete exact source-lock manifest and original clean projects.
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
        SourceProfile::Production651,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn locks() -> (
        PathBuf,
        SparseSourceLock,
        PathBuf,
        SparseSourceLock,
        PathBuf,
        SparseSourceLock,
    ) {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap();
        let audio_path = repo.join("android/manifest/audio-bridge-source-lock.json");
        let native_path = repo.join("android/native-generation-pair/source-lock.json");
        let full_path = repo.join("android/manifest/production-full-source-lock.json");
        let audio = load_lock(&audio_path).unwrap();
        let native = load_lock(&native_path).unwrap();
        let full = load_lock(&full_path).unwrap();
        (audio_path, audio, native_path, native, full_path, full)
    }

    #[test]
    fn production_union_preserves_both_original_plans_and_profile_limits() {
        let (_, audio, _, native, _, full) = locks();
        let audio_plan = crate::build_plan(&audio).unwrap();
        let native_plan = crate::native_pair::build_plan(&native).unwrap();
        let plan = build_plan(&full).unwrap();
        assert_eq!(audio_plan.projects.len(), 541);
        assert_eq!(native_plan.projects.len(), 645);
        assert_eq!(plan.projects.len(), 651);
        assert_eq!(plan.links.len(), 8);
        assert_eq!(
            plan.projects.iter().map(|p| p.sparse_paths.len()).max(),
            Some(534)
        );
        // The original profiles retain different descriptive purpose strings.
        // Preserve all Audio provider identities and cones without rewriting either lock.
        for old in &audio_plan.projects {
            let new = plan.projects.iter().find(|p| p.path == old.path).unwrap();
            assert_eq!(old.url, new.url);
            assert_eq!(old.commit, new.commit);
            assert!(
                new.sparse_paths.is_empty()
                    || (!old.sparse_paths.is_empty()
                        && old
                            .sparse_paths
                            .iter()
                            .all(|p| new.sparse_paths.contains(p)))
            );
        }
        super::super::validate_plan_extension(&native_plan, &plan).unwrap();
        assert!(crate::build_plan(&full).is_err());
        assert!(crate::native_pair::build_plan(&full).is_err());
        assert!(build_plan(&audio).is_err());
        assert!(build_plan(&native).is_err());
        assert!(!plan.unrestricted_repo_sync);
    }

    #[test]
    fn production_operations_reject_foreign_profiles_before_source_io() {
        let (audio_path, audio, native_path, native, _, full) = locks();
        let d = tempfile::tempdir().unwrap();
        let absent = d.path().join("uncreated");
        for (path, lock) in [(&audio_path, &audio), (&native_path, &native)] {
            assert!(materialize(path, lock, &absent).is_err());
            assert!(reconcile(path, lock, &absent).is_err());
            assert!(verify_materialized(path, lock, &absent).is_err());
            assert!(!absent.exists());
        }
        let mut bad = full.clone();
        bad.projects[0].sparse_paths = (0..535)
            .map(|i| PathBuf::from(format!("src/pinned_{i}")))
            .collect();
        assert!(build_plan(&bad).is_err());
        let mut bad = full.clone();
        bad.projects[0].path = "../outside".into();
        assert!(build_plan(&bad).is_err());
        let mut bad = full.clone();
        bad.projects[1] = bad.projects[0].clone();
        assert!(build_plan(&bad).is_err());
        let mut bad = full;
        bad.policy.allow_unrestricted_repo_sync = true;
        assert!(build_plan(&bad).is_err());
        assert_eq!(fs::read_dir(d.path()).unwrap().count(), 0);
    }
}
