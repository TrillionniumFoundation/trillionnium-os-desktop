//! Explicit bounded source API for the original Native generation pair.
//!
//! This scope does not alter the default Audio541 API. The pair producer also
//! authenticates the complete lock and every historical source extension.
use super::*;

const NATIVE_SOURCE_PROJECT_COUNT: usize = 645;
pub(super) const MAX_PROJECTS: usize = NATIVE_SOURCE_PROJECT_COUNT.div_ceil(16) * 16;
pub(super) const MAX_SPARSE_PATHS: usize = 336;

/// Read a bounded exact source lock; validation remains an explicit next step.
pub use super::load_lock;
/// Resume only an explicitly selected private Native staging directory.
pub use super::resume::materialize_resuming;

/// Validate the complete source policy with the Native656/336 scope.
///
/// # Errors
/// Rejects every malformed, duplicate, escaped or out-of-scope input.
pub fn build_plan(lock: &SparseSourceLock) -> Result<MaterializationPlan, SourceError> {
    super::build_plan_with_profile(lock, SourceProfile::NativePair656)
}

/// Materialize with the explicit Native source scope.
///
/// # Errors
/// Preserves the complete normal materializer's validation and I/O failures.
pub fn materialize(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    super::materialize_with_profile(lock_path, lock, destination, SourceProfile::NativePair656)
}

/// Reconcile with the explicit Native source scope.
///
/// # Errors
/// Preserves the complete normal materializer's validation and I/O failures.
pub fn reconcile(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    super::reconcile_with_profile(lock_path, lock, destination, SourceProfile::NativePair656)
}

/// Verify materialized with the explicit Native source scope.
///
/// # Errors
/// Preserves the complete normal materializer's validation and I/O failures.
pub fn verify_materialized(
    lock_path: &Path,
    lock: &SparseSourceLock,
    destination: &Path,
) -> Result<MaterializedManifest, SourceError> {
    super::verify_materialized_with_profile(lock_path, lock, destination, SourceProfile::NativePair656)
}

const NATIVE_FROZEN_EXTRA_PROJECT_NAMES: &[&str] = &[
    "device/generic/goldfish",
    "device/generic/trusty",
    "device/google/cuttlefish",
    "device/sample",
    "trusty/external/trusted-firmware-a",
    "trusty/external/trusty",
    "trusty/external/headers",
    "trusty/lk/common",
    "trusty/external/musl",
    "trusty/device/arm/generic-arm64",
    "trusty/device/common",
    "trusty/device/desktop",
    "trusty/device/x86/generic-x86_64",
    "trusty/host/common",
    "trusty/lk/trusty",
    "trusty/app/authmgr",
    "trusty/app/avb",
    "trusty/app/cast-auth",
    "trusty/app/confirmationui",
    "trusty/app/gatekeeper",
    "trusty/app/keymaster",
    "trusty/app/keymint",
    "trusty/app/sample",
    "trusty/app/secretkeeper",
    "trusty/app/storage",
    "trusty/lib",
    "trusty/user/desktop",
    "trusty/vendor/google/aosp",
];

pub(super) fn is_project_name(name: &str) -> bool {
    (name.starts_with("platform/")
        || name.starts_with("kernel/")
        || name.starts_with("toolchain/")
        || name == "tools/platform-compat"
        || NATIVE_FROZEN_EXTRA_PROJECT_NAMES.contains(&name))
        && name.len() <= 255
        && name
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unified_profiles_keep_both_exact_locks_and_reject_cross_scope() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio = load_lock(&repo.join("android/manifest/audio-bridge-source-lock.json")).unwrap();
        let native = load_lock(&repo.join("android/native-generation-pair/source-lock.json")).unwrap();
        assert_eq!(crate::build_plan(&audio).unwrap().projects.len(), 541);
        assert_eq!(build_plan(&native).unwrap().projects.len(), 645);
        assert!(crate::build_plan(&native).is_err());
        // The current Audio lock has 355 exact CTS cones. Native retains its
        // independently bounded 336-cone contract rather than adopting Audio's.
        assert!(build_plan(&audio).is_err());
    }

    #[test]
    fn unified_profiles_reject_foreign_plans_before_materialization_or_io() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap();
        let audio_path = repo.join("android/manifest/audio-bridge-source-lock.json");
        let native_path = repo.join("android/native-generation-pair/source-lock.json");
        let audio = load_lock(&audio_path).unwrap();
        let native = load_lock(&native_path).unwrap();
        let scratch = tempfile::tempdir().unwrap();
        let absent = scratch.path().join("must-not-be-created");
        for result in [
            crate::materialize(&native_path, &native, &absent),
            crate::reconcile(&native_path, &native, &absent),
            crate::verify_materialized(&native_path, &native, &absent),
            materialize(&audio_path, &audio, &absent),
            reconcile(&audio_path, &audio, &absent),
            verify_materialized(&audio_path, &audio, &absent),
        ] {
            assert!(matches!(result, Err(SourceError::Invalid(_))));
            assert!(!absent.exists());
            assert_eq!(fs::read_dir(scratch.path()).unwrap().count(), 0);
        }
    }

    #[test]
    fn unified_profiles_keep_audio_name_policy_separate_from_native_names() {
        for name in ["device/google/cuttlefish", "trusty/app/avb", "trusty/device/arm/generic-arm64"] {
            assert!(is_project_name(name));
            assert!(!crate::is_project_name(name));
        }
        for name in ["platform/build", "tools/platform-compat", "trusty/lib"] {
            assert!(is_project_name(name));
            assert!(crate::is_project_name(name));
        }
        for name in ["device/unknown", "trusty/unknown", "platform/../escape", "https://untrusted.invalid/p"] {
            assert!(!is_project_name(name));
            assert!(!crate::is_project_name(name));
        }
    }

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

    fn lock_at_project_bound() -> SparseSourceLock {
        let mut lock = valid_lock();
        for index in 1..MAX_PROJECTS {
            let mut project = lock.projects[0].clone();
            project.path = format!("tools/verified_extra_{index:03}").into();
            project.name = format!("platform/tools/verified_extra_{index:03}");
            lock.projects.push(project);
        }
        lock
    }

    #[test]
    fn project_bound_admits_superproject_gitlink_extensions_but_not_unbounded_sync() {
        let mut lock = lock_at_project_bound();
        assert_eq!(MAX_PROJECTS % 16, 0);
        assert!(MAX_PROJECTS >= NATIVE_SOURCE_PROJECT_COUNT);
        assert!(MAX_PROJECTS - NATIVE_SOURCE_PROJECT_COUNT < 16);
        assert_eq!(lock.projects.len(), MAX_PROJECTS);
        assert!(build_plan(&lock).is_ok(), "the bounded maximum must be accepted");
        let mut forbidden = lock.projects[0].clone();
        forbidden.path = format!("tools/verified_extra_{}", MAX_PROJECTS + 1).into();
        forbidden.name = format!("platform/tools/verified_extra_{}", MAX_PROJECTS + 1);
        lock.projects.push(forbidden);
        let SourceError::Invalid(problems) = build_plan(&lock).unwrap_err() else {
            panic!("expected strict project-count validation");
        };
        assert!(problems.iter().any(|line| line.contains(&format!("1 through {MAX_PROJECTS}"))));
        lock.projects.truncate(NATIVE_SOURCE_PROJECT_COUNT);
        assert!(build_plan(&lock).is_ok(), "the concrete ordinary pair count must fit");
        lock.policy.allow_unrestricted_repo_sync = true;
        assert!(build_plan(&lock).is_err(), "the count change never authorizes full sync");
    }

    #[test]
    fn bounded_native_source_plan_keeps_duplicate_and_escape_rejections() {
        let good = lock_at_project_bound();
        let mut duplicate = good.clone();
        duplicate.projects[MAX_PROJECTS - 1] = duplicate.projects[0].clone();
        let SourceError::Invalid(problems) = build_plan(&duplicate).unwrap_err() else {
            panic!("expected duplicate rejection below the project-count bound");
        };
        assert!(problems.iter().any(|line| line.contains("duplicate project path")));
        assert!(problems.iter().any(|line| line.contains("duplicate Android project")));
        for escape in ["../outside", "/outside", "tools/../outside"] {
            let mut bad = good.clone();
            bad.projects[MAX_PROJECTS - 1].path = escape.into();
            assert!(build_plan(&bad).is_err(), "project escape must remain rejected: {escape}");
        }
        let mut bad = good;
        bad.projects[MAX_PROJECTS - 1].sparse_paths = vec!["../outside".into()];
        assert!(build_plan(&bad).is_err(), "sparse escape must remain rejected");
    }

    #[test]
    fn source_lock_preserves_exact_sparse_paths_through_the_336_bound() {
        let mut lock = valid_lock();
        assert_eq!(MAX_SPARSE_PATHS, 336);
        assert_eq!(323_usize.div_ceil(16) * 16, MAX_SPARSE_PATHS);
        for count in [133, 256, 257, 279, 288, 289, 323, 336] {
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
    fn source_lock_rejects_337_sparse_paths_without_truncating_them() {
        let mut lock = valid_lock();
        let paths: Vec<PathBuf> = (0..337)
            .map(|i| format!("tests/pinned_{i:03}").into())
            .collect();
        lock.projects[0].sparse_paths = paths.clone();
        let SourceError::Invalid(problems) = build_plan(&lock).unwrap_err() else {
            panic!("expected the finite sparse-path bound");
        };
        assert!(problems.iter().any(|line| line.contains("more than 336 sparse paths")));
        assert_eq!(lock.projects[0].sparse_paths, paths);
    }

    #[test]
    fn bounded_sparse_paths_reject_duplicates_and_escapes_at_the_new_boundary() {
        let mut lock = valid_lock();
        lock.projects[0].sparse_paths = (0..336)
            .map(|i| format!("tests/pinned_{i:03}").into())
            .collect();
        let mut duplicate = lock.clone();
        duplicate.projects[0].sparse_paths[335] = duplicate.projects[0].sparse_paths[0].clone();
        assert!(build_plan(&duplicate).unwrap_err().to_string().contains("repeats sparse path"));
        for escape in ["", ".", "../outside", "/outside", "tests/../outside"] {
            let mut bad = lock.clone();
            bad.projects[0].sparse_paths[335] = escape.into();
            assert!(build_plan(&bad).unwrap_err().to_string().contains("not normalized and relative"),
                "sparse escape must remain rejected: {escape:?}");
        }
        lock.policy.allow_unrestricted_repo_sync = true;
        assert!(build_plan(&lock).is_err());
    }

    #[test]
    fn original_cts_279_cones_are_preserved_as_an_unmaterialized_plan() {
        let paths: Vec<PathBuf> = serde_json::from_str(include_str!(
            "../tests/fixtures/ordinary-pair-cts-279-cones.json")).unwrap();
        assert_eq!(paths.len(), 279);
        let mut lock = valid_lock();
        lock.links.clear();
        lock.projects[0].path = "cts".into();
        lock.projects[0].name = "platform/cts".into();
        lock.projects[0].sparse_paths = paths.clone();
        let plan = build_plan(&lock).unwrap();
        assert_eq!(plan.projects[0].sparse_paths, paths);
        assert!(!plan.unrestricted_repo_sync);
    }

    #[test]
    fn actual_git_checkout_preserves_323_cones_and_hidden_blueprints() {
        let sandbox = tempfile::tempdir().unwrap();
        let origin = sandbox.path().join("origin");
        run("git", &[OsStr::new("init"), OsStr::new("--quiet"),
            OsStr::new("--initial-branch=main"), origin.as_os_str()]).unwrap();
        let paths: Vec<PathBuf> = (0..323)
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
            OsStr::new("current 323-cone fixture")]).unwrap();
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
    fn exact_frozen_device_and_trusty_names_keep_other_names_rejected() {
        let mut lock = valid_lock();
        for name in NATIVE_FROZEN_EXTRA_PROJECT_NAMES {
            lock.projects[0].name = (*name).into();
            assert_eq!(build_plan(&lock).unwrap().projects[0].url,
                       format!("https://android.googlesource.com/{name}"));
        }
        for invalid in ["device/unlisted", "trusty/unlisted", "device/generic/goldfish/extra",
                        "trusty/user/base/../unlisted", "https://other.example/device/generic/goldfish"] {
            lock.projects[0].name = invalid.into();
            assert!(build_plan(&lock).is_err(), "unexpected namespace widening: {invalid}");
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

