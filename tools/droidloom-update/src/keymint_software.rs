//! Exact-source, journaled software KeyMint compatibility projection.
//!
//! Only the nonsecure in-process provider opts in. The generic TA and hardware
//! implementations retain their existing defaults. System metadata is projected
//! only for a complete system build, never silently onto an official GSI.

use super::*;
use serde::Deserialize;
use sha2::{Digest, Sha256};

const RECIPE: &str = include_str!("../../../android/keymint-software-compat/SOURCE.json");
const LEGACY: &str = include_str!("../../../android/keymint-software-compat/legacy_nonsecure.rs");
const TESTS: &str = include_str!("../../../android/keymint-software-compat/compat_tests.rs");
const METADATA_BEFORE: &[u8] =
    include_bytes!("../../../android/keymint-software-compat/metadata/service.before.rs");
const METADATA_AFTER: &[u8] =
    include_bytes!("../../../android/keymint-software-compat/metadata/service.after.rs");
const DEFAULT_TA: &str = "hardware/interfaces/security/keymint/aidl/default/ta";
const SOURCE_PATHS: &[&str] = &[
    "system/keymint/common/src/keyblob.rs",
    "system/keymint/ta/src/lib.rs",
    "hardware/interfaces/security/keymint/aidl/default/ta/lib.rs",
    "hardware/interfaces/security/keymint/aidl/default/Android.bp",
    "system/sepolicy/vendor/file_contexts",
];

#[derive(Deserialize)]
struct Recipe {
    schema: String,
    patches: Vec<Patch>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Patch {
    path: String,
    before_sha256: String,
    after_sha256: String,
    replacements: Vec<Replacement>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Replacement {
    old: String,
    new: String,
}

fn checked_transform(patch: &Patch, before: &str) -> Result<String> {
    if format!("{:x}", Sha256::digest(before.as_bytes())) != patch.before_sha256 {
        return fail(format!("KeyMint original source digest mismatch: {}", patch.path));
    }
    let mut after = before.to_owned();
    for replacement in &patch.replacements {
        if replacement.old.is_empty() || after.matches(&replacement.old).count() != 1 {
            return fail(format!("KeyMint source fragment mismatch: {}", patch.path));
        }
        after = after.replace(&replacement.old, &replacement.new);
    }
    if format!("{:x}", Sha256::digest(after.as_bytes())) != patch.after_sha256 {
        return fail(format!("KeyMint projected source digest mismatch: {}", patch.path));
    }
    Ok(after)
}

/// Project the provider, its authenticated opt-in and exact executable label.
/// The label uses the existing HAL domain; it introduces no policy allow rules.
pub(super) fn project_vendor(source: &Path, projection: &mut Projection) -> Result<()> {
    let recipe: Recipe = serde_json::from_str(RECIPE)?;
    if recipe.schema != "droidloom-keymint-software-compat-v1"
        || recipe.patches.len() != SOURCE_PATHS.len()
        || !recipe.patches.iter().zip(SOURCE_PATHS).all(|(p, path)| p.path == *path)
    {
        return fail("unexpected software KeyMint projection recipe");
    }
    let mut plan = Vec::new();
    for patch in &recipe.patches {
        let path = source.join(&patch.path);
        if !fs::symlink_metadata(&path)?.file_type().is_file() {
            return fail(format!("KeyMint source is not an ordinary file: {}", path.display()));
        }
        let before = fs::read_to_string(&path)?;
        let after = checked_transform(patch, &before)?;
        plan.push((path, before, after));
    }
    let additions = [
        (source.join(DEFAULT_TA).join("legacy_nonsecure.rs"), LEGACY),
        (source.join(DEFAULT_TA).join("compat_tests.rs"), TESTS),
    ];
    for (path, _) in &additions {
        match fs::symlink_metadata(path) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            _ => return fail(format!("KeyMint addition already exists: {}", path.display())),
        }
    }
    // Check every exact input before any writes, then recheck immediately before
    // journaled mutation. Projection owns restoration on build success/failure.
    for (path, before, after) in plan {
        if fs::read_to_string(&path)? != before {
            return fail(format!("KeyMint source changed during projection: {}", path.display()));
        }
        projection.put(&path, after)?;
    }
    for (path, content) in additions {
        projection.put(&path, content)?;
    }
    Ok(())
}

/// Correct only the returned legacy authorization labels after GetInfo checks.
/// Database state, counters, certificates and the internal routing stay intact.
pub(super) fn project_system_metadata(source: &Path, projection: &mut Projection) -> Result<()> {
    let path = source.join("system/security/keystore2/src/service.rs");
    if !fs::symlink_metadata(&path)?.file_type().is_file() || fs::read(&path)? != METADATA_BEFORE {
        return fail("keystore2 software metadata projection requires its exact pinned source");
    }
    projection.put(&path, METADATA_AFTER)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_drift_is_rejected_before_replacement() {
        let patch = Patch {
            path: "synthetic.rs".to_owned(),
            before_sha256: format!("{:x}", Sha256::digest(b"original\n")),
            after_sha256: format!("{:x}", Sha256::digest(b"projected\n")),
            replacements: vec![Replacement {
                old: "original".to_owned(),
                new: "projected".to_owned(),
            }],
        };
        assert_eq!(checked_transform(&patch, "original\n").unwrap(), "projected\n");
        assert!(checked_transform(&patch, "unreviewed original\n").is_err());
    }

    #[test]
    fn projected_digest_mismatch_is_rejected() {
        let patch = Patch {
            path: "synthetic.rs".to_owned(),
            before_sha256: format!("{:x}", Sha256::digest(b"original\n")),
            after_sha256: "0".repeat(64),
            replacements: vec![Replacement {
                old: "original".to_owned(),
                new: "projected".to_owned(),
            }],
        };
        assert!(checked_transform(&patch, "original\n").is_err());
    }

    #[test]
    #[ignore = "requires exact pinned sources in DROIDLOOM_KEYMINT_PINNED_SOURCE"]
    fn pinned_source_projection_and_restore() {
        let fixture = PathBuf::from(
            std::env::var_os("DROIDLOOM_KEYMINT_PINNED_SOURCE")
                .expect("set the pinned-source fixture directory"),
        );
        let temp = tempfile::tempdir().unwrap();
        let source = temp.path().join("source");
        let mut originals = BTreeMap::new();
        for relative in SOURCE_PATHS {
            let bytes = fs::read(fixture.join(relative)).unwrap();
            let path = source.join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(&path, &bytes).unwrap();
            originals.insert(path, bytes);
        }
        let metadata = source.join("system/security/keystore2/src/service.rs");
        fs::create_dir_all(metadata.parent().unwrap()).unwrap();
        fs::write(&metadata, METADATA_BEFORE).unwrap();
        originals.insert(metadata.clone(), METADATA_BEFORE.to_vec());
        let journal = temp.path().join("projection.json");
        let mut projection = Projection::new(journal.clone()).unwrap();

        project_vendor(&source, &mut projection).unwrap();
        assert_eq!(
            fs::read(&metadata).unwrap(),
            METADATA_BEFORE,
            "vendor-only builds must not alter the official system"
        );
        let recipe: Recipe = serde_json::from_str(RECIPE).unwrap();
        for patch in &recipe.patches {
            assert_eq!(
                format!("{:x}", Sha256::digest(fs::read(source.join(&patch.path)).unwrap())),
                patch.after_sha256,
            );
        }
        project_system_metadata(&source, &mut projection).unwrap();
        assert_eq!(fs::read(&metadata).unwrap(), METADATA_AFTER);
        assert_eq!(
            fs::read_to_string(source.join(DEFAULT_TA).join("legacy_nonsecure.rs")).unwrap(),
            LEGACY
        );
        projection.restore().unwrap();
        for (path, bytes) in &originals {
            assert_eq!(&fs::read(path).unwrap(), bytes);
        }
        assert!(!source.join(DEFAULT_TA).join("legacy_nonsecure.rs").exists());
        assert!(!source.join(DEFAULT_TA).join("compat_tests.rs").exists());
        assert!(!journal.exists());

        // A later source drift must fail before any earlier source is changed.
        let last = source.join(SOURCE_PATHS.last().unwrap());
        fs::write(&last, b"unreviewed context file\n").unwrap();
        let mut projection = Projection::new(journal.clone()).unwrap();
        assert!(project_vendor(&source, &mut projection).is_err());
        for (path, bytes) in &originals {
            if *path != last {
                assert_eq!(&fs::read(path).unwrap(), bytes);
            }
        }
        assert!(!source.join(DEFAULT_TA).join("legacy_nonsecure.rs").exists());
        assert!(!journal.exists());
    }
}
