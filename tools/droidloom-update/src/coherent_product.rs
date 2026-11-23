//! Journaled configuration of one complete normal product.
//!
//! The original files are exact inputs. These changes happen before Soong and
//! are restored by the existing projection journal. A missing CP3A source/ABI
//! mapping fails before any write; this module cannot create such a mapping.
use super::*;

pub(super) const RECEIPT: &str = "droidloom-coherent-product-configuration.json";
const LIMIT: u64 = 1024 * 1024;
const DEVICE: &str = "vendor/droidloom/android/device/droidloom_x86_64";
const BEFORE_PRODUCT: &[u8] =
    include_bytes!("../../../android/coherent-product/before/droidloom_x86_64.mk");
const AFTER_PRODUCT: &[u8] =
    include_bytes!("../../../android/coherent-product/after/droidloom_x86_64.mk");
const BEFORE_BOARD: &[u8] =
    include_bytes!("../../../android/coherent-product/before/BoardConfig.mk");
const AFTER_BOARD: &[u8] = include_bytes!("../../../android/coherent-product/after/BoardConfig.mk");
const BEFORE_BP: &[u8] = include_bytes!("../../../android/coherent-product/before/Android.bp");
const AFTER_BP: &[u8] = include_bytes!("../../../android/coherent-product/after/Android.bp");
const BEFORE_INIT: &[u8] = include_bytes!("../../../android/coherent-product/before/init.rc");
const AFTER_INIT: &[u8] = include_bytes!("../../../android/coherent-product/after/init.rc");
const BEFORE_LMKD: &[u8] = include_bytes!("../../../android/coherent-product/before/lmkd.rc");
const AFTER_LMKD: &[u8] = include_bytes!("../../../android/coherent-product/after/lmkd.rc");
const BEFORE_NETD: &[u8] = include_bytes!("../../../android/coherent-product/before/netd.rc");
const AFTER_NETD: &[u8] = include_bytes!("../../../android/coherent-product/after/netd.rc");
const DEVICE_MATRIX: &[u8] =
    include_bytes!("../../../android/coherent-product/after/compatibility_matrix.device.xml");

const FIXTURES: &[(&str, &[u8])] = &[
    ("before/droidloom_x86_64.mk", BEFORE_PRODUCT),
    ("after/droidloom_x86_64.mk", AFTER_PRODUCT),
    ("before/BoardConfig.mk", BEFORE_BOARD),
    ("after/BoardConfig.mk", AFTER_BOARD),
    ("before/Android.bp", BEFORE_BP),
    ("after/Android.bp", AFTER_BP),
    ("before/init.rc", BEFORE_INIT),
    ("after/init.rc", AFTER_INIT),
    ("before/lmkd.rc", BEFORE_LMKD),
    ("after/lmkd.rc", AFTER_LMKD),
    ("before/netd.rc", BEFORE_NETD),
    ("after/netd.rc", AFTER_NETD),
    ("after/compatibility_matrix.device.xml", DEVICE_MATRIX),
];

// Fixed, whole original provider reads. This does not assert that their CP2A
// source profile is CP3A: the separate mandatory release mapping still rejects it.
const PROVIDERS: &[(&str, &str)] = &[
    (
        "packages/modules/Connectivity/Tethering/apex/Android.bp",
        "76ca1759349dbd6c3cf359eacc9b4a4592f777c6220a61df28d8fabcff23dc19",
    ),
    (
        "build/make/target/product/core_64_bit.mk",
        "66435d94707e1e5958432373347218c14f6fec0ebbe7c45af5c8cdb013668c67",
    ),
    (
        "build/make/target/product/generic_system.mk",
        "dde2b17c455668de2f884e96df9bccabaac0233fd0d94c43f2412f0b1cecb179",
    ),
    (
        "build/make/target/product/handheld_system_ext.mk",
        "9e548dc57becae4dddea2ef93a6a3eaa831396de205fabc35b6a063adcb284c8",
    ),
    (
        "build/make/target/product/telephony_system_ext.mk",
        "e2cd87868b41ae4bef4fb212ab2654f687b4ba67f265866938b5a2a23b5b664f",
    ),
    (
        "build/make/target/product/aosp_product.mk",
        "7299651a28575223fba525d59caa007bc9f932ad71d50476ab860696027f87c2",
    ),
    (
        "build/make/tools/releasetools/build_image.py",
        "e8c387d9887b07219cbc8b30076195b56d4a3f304006367b562bea861075ef6a",
    ),
    (
        "system/memory/lmkd/Android.bp",
        "eda1259eea0ed0f80dce28dde2576bb00060a3a3d90b5174f63123fc7859ab8e",
    ),
    (
        "system/netd/server/Android.bp",
        "4177df88b02389011ab0a822821bc6f340d5511e982dd61e34e6de5669645d21",
    ),
    (
        "system/core/rootdir/Android.bp",
        "13a1827ef7386b5c321238e50bd2f0cb3b184c1a046aeb166db4d5d241112c57",
    ),
    (
        "hardware/interfaces/compatibility_matrices/Android.bp",
        "f70b9dfae474513e87cb0060f216598438b5f23be2951ee3db03390f45752f4b",
    ),
    (
        "hardware/interfaces/compatibility_matrices/build/vintf_compatibility_matrix.go",
        "70c159557c868a3c4dfab72073f7c279d86fce00a0d2c87fd35bd0ab6a40b66c",
    ),
];

struct Change {
    relative: PathBuf,
    before: Option<Vec<u8>>,
    after: Vec<u8>,
}

fn exact(path: &Path, expected: &[u8]) -> Result<FileRef> {
    let reference = pin(path, LIMIT)?;
    if bound_body(&reference, LIMIT)? != expected {
        return fail(format!(
            "complete product input differs from its exact reviewed bytes: {}",
            path.display()
        ));
    }
    Ok(reference)
}

fn mesa_suffix(work: &Path) -> Result<Vec<u8>> {
    ordinary_absolute(work, true)?;
    // This path is embedded in a Make assignment and then a Meson argument.
    // Reject every byte outside the reviewed ASCII path alphabet; escaping one
    // parser would not make the value safe for all later consumers.
    if !work
        .as_os_str()
        .as_bytes()
        .iter()
        .all(|b| b.is_ascii_alphanumeric() || matches!(*b, b'/' | b'_' | b'-' | b'.'))
    {
        return fail(
            "the normal Mesa make argument requires an ASCII letters/digits/_-./ private work path",
        );
    }
    Ok(format!(
        "\nBOARD_MESA3D_MESON_ARGS += -Dmesa-clc=system --native-file {}\n",
        work.join("mesa-native.ini").display()
    )
    .into_bytes())
}

fn changes(work: &Path) -> Result<Vec<Change>> {
    let suffix = mesa_suffix(work)?;
    let before_board = [BEFORE_BOARD, suffix.as_slice()].concat();
    let after_board = [AFTER_BOARD, suffix.as_slice()].concat();
    Ok(vec![
        Change {
            relative: format!("{DEVICE}/droidloom_x86_64.mk").into(),
            before: Some(BEFORE_PRODUCT.to_vec()),
            after: AFTER_PRODUCT.to_vec(),
        },
        Change {
            relative: format!("{DEVICE}/BoardConfig.mk").into(),
            before: Some(before_board),
            after: after_board,
        },
        Change {
            relative: "vendor/droidloom/Android.bp".into(),
            before: Some(BEFORE_BP.to_vec()),
            after: AFTER_BP.to_vec(),
        },
        Change {
            relative: "system/memory/lmkd/lmkd.rc".into(),
            before: Some(BEFORE_LMKD.to_vec()),
            after: AFTER_LMKD.to_vec(),
        },
        Change {
            relative: "system/netd/server/netd.rc".into(),
            before: Some(BEFORE_NETD.to_vec()),
            after: AFTER_NETD.to_vec(),
        },
        Change {
            relative: "system/core/rootdir/init.rc".into(),
            before: Some(BEFORE_INIT.to_vec()),
            after: AFTER_INIT.to_vec(),
        },
        Change {
            relative: format!("{DEVICE}/compatibility_matrix.device.xml").into(),
            before: None,
            after: DEVICE_MATRIX.to_vec(),
        },
    ])
}

fn recipe_inputs(repo: &Path) -> Result<BTreeMap<String, FileRef>> {
    let mut refs = BTreeMap::new();
    for (relative, expected) in FIXTURES {
        let relative = format!("android/coherent-product/{relative}");
        refs.insert(relative.clone(), exact(&repo.join(&relative), expected)?);
    }
    for (relative, expected) in [
        (
            "android/device/droidloom_x86_64/droidloom_x86_64.mk",
            BEFORE_PRODUCT,
        ),
        (
            "android/device/droidloom_x86_64/BoardConfig.mk",
            BEFORE_BOARD,
        ),
        ("Android.bp", BEFORE_BP),
        ("packaging/compat/lmkd.rc", AFTER_LMKD),
        ("packaging/compat/netd.rc", AFTER_NETD),
        (
            "android/vintf-compat/compatibility_matrix.device.xml",
            DEVICE_MATRIX,
        ),
    ] {
        refs.insert(relative.into(), exact(&repo.join(relative), expected)?);
    }
    let patch = pin(
        &repo.join("android/apex-compat/0001-droidloom-classpath-projection.patch"),
        LIMIT,
    )?;
    if patch.sha256 != "9d7ce7ee0ef69115e5d81f4307915853955b3c1a7960632350c311fda6c7dc63" {
        return fail("normal init source projection patch changed");
    }
    refs.insert(
        "android/apex-compat/0001-droidloom-classpath-projection.patch".into(),
        patch,
    );
    let spec = pin(&repo.join("packaging/cell-spec-x86_64-u1000.json"), LIMIT)?;
    if spec.sha256 != "f87679f7a092b2500d5f1b57a5190cdde77ba7662c6781a7cc411e24b1833d14" {
        return fail(
            "complete product runtime targets must match the reviewed normal module paths",
        );
    }
    refs.insert("packaging/cell-spec-x86_64-u1000.json".into(), spec);
    Ok(refs)
}

fn providers(source: &Path) -> Result<BTreeMap<String, FileRef>> {
    PROVIDERS
        .iter()
        .map(|(relative, sha)| {
            let reference = pin(&source.join(relative), LIMIT)?;
            if &reference.sha256 != sha {
                return fail(format!("normal product provider changed: {relative}"));
            }
            Ok(((*relative).into(), reference))
        })
        .collect()
}

fn originals(source: &Path, plan: &[Change]) -> Result<Vec<Option<FileRef>>> {
    plan.iter().map(|change| {
        let path = source.join(&change.relative);
        match &change.before {
            Some(body) => exact(&path, body).map(Some),
            None => {
                ordinary_absolute(path.parent().ok_or("configuration path has no parent")?, true)?;
                match fs::symlink_metadata(&path) {
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
                    _ => fail("new normal VINTF input must be absent, not an existing or aliased file"),
                }
            }
        }
    }).collect()
}

/// Call after the existing Mesa suffix and checked work/init.rc are prepared,
/// immediately before Projection::stabilize_all. Only complete delivery calls
/// this function; the vendor-only route retains its original configuration.
pub(crate) fn project(
    repo: &Path,
    source: &Path,
    work: &Path,
    projection: &mut crate::android::Projection,
) -> Result<()> {
    preflight_selection(repo)?;
    for path in [repo, source, work] {
        ordinary_absolute(path, true)?;
    }
    let inputs = recipe_inputs(repo)?;
    let provider_inputs = providers(source)?;
    let checked_init = exact(&work.join("init.rc"), AFTER_INIT)?;
    let plan = changes(work)?;
    let before = originals(source, &plan)?;
    // Every original and provider is validated before the first mutation.
    for (change, reference) in plan.iter().zip(&before) {
        if let Some(reference) = reference {
            recheck(reference, LIMIT)?;
        } else if source.join(&change.relative).symlink_metadata().is_ok() {
            return fail("new normal VINTF input appeared before journaled creation");
        }
        projection.put(&source.join(&change.relative), &change.after)?;
        exact(&source.join(&change.relative), &change.after)?;
    }
    for reference in inputs
        .values()
        .chain(provider_inputs.values())
        .chain([&checked_init])
    {
        recheck(reference, LIMIT)?;
    }
    Ok(())
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Configuration {
    schema: String,
    repo: PathBuf,
    source: PathBuf,
    out: PathBuf,
    work: PathBuf,
    recipe: BTreeMap<String, FileRef>,
    providers: BTreeMap<String, FileRef>,
    projected: BTreeMap<PathBuf, FileRef>,
    checked_init: FileRef,
    mesa_native: FileRef,
    original_projection: Value,
    normal_image_generation_requested: bool,
    source_release_equivalence_inferred: bool,
    avb_signing_qualified: bool,
    android_runtime_qualified: bool,
}

/// The producer invokes this from run_normal after the existing journal has
/// stabilized all source mtimes and emitted its actual full-source receipt.
pub(super) fn input_receipt(
    repo: &Path,
    source: &Path,
    out: &Path,
    work: &Path,
    actual_projection: &Value,
) -> Result<FileRef> {
    let mut projected = BTreeMap::new();
    for change in changes(work)? {
        let reference = exact(&source.join(&change.relative), &change.after)?;
        let relative = change
            .relative
            .to_str()
            .ok_or("configuration path is not UTF8")?;
        if actual_projection["files"].get(relative) != Some(&json!(reference.sha256)) {
            return fail("actual source projection omitted a normal image configuration member");
        }
        projected.insert(change.relative, reference);
    }
    let value = Configuration {
        schema: "droidloom-coherent-product-configuration-v1".into(),
        repo: repo.into(),
        source: source.into(),
        out: out.into(),
        work: work.into(),
        recipe: recipe_inputs(repo)?,
        providers: providers(source)?,
        projected,
        checked_init: exact(&work.join("init.rc"), AFTER_INIT)?,
        mesa_native: pin(&work.join("mesa-native.ini"), LIMIT)?,
        original_projection: actual_projection.clone(),
        normal_image_generation_requested: true,
        source_release_equivalence_inferred: false,
        avb_signing_qualified: false,
        android_runtime_qualified: false,
    };
    save_new(&out.join(RECEIPT), &value)
}

fn load_record(
    reference: &FileRef,
    repo: &Path,
    source: &Path,
    out: &Path,
) -> Result<Configuration> {
    recheck(reference, MAX_JSON)?;
    let value: Configuration = serde_json::from_slice(&bound_body(reference, MAX_JSON)?)?;
    if value.schema != "droidloom-coherent-product-configuration-v1"
        || value.repo != repo
        || value.source != source
        || value.out != out
        || reference.path != out.join(RECEIPT)
        || !value.normal_image_generation_requested
        || value.source_release_equivalence_inferred
        || value.avb_signing_qualified
        || value.android_runtime_qualified
        || value.checked_init.path != value.work.join("init.rc")
        || value.mesa_native.path != value.work.join("mesa-native.ini")
    {
        return fail(
            "complete product configuration record has a foreign path or unsupported claim",
        );
    }
    if value.recipe != recipe_inputs(repo)? {
        return fail("configuration recipe identity changed after projection");
    }
    let plan = changes(&value.work)?;
    if value.projected.keys().cloned().collect::<BTreeSet<_>>()
        != plan.iter().map(|c| c.relative.clone()).collect()
        || value
            .providers
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            != PROVIDERS.iter().map(|(p, _)| *p).collect()
    {
        return fail("normal configuration record does not contain its exact member sets");
    }
    for change in plan {
        let actual = &value.projected[&change.relative];
        if actual.path != source.join(&change.relative)
            || actual.bytes != change.after.len() as u64
            || actual.sha256 != hex::encode(Sha256::digest(&change.after))
            || value.original_projection["files"].get(change.relative.to_str().unwrap())
                != Some(&json!(actual.sha256))
        {
            return fail("normal configuration does not describe the compiled fixed projection");
        }
    }
    for (relative, sha) in PROVIDERS {
        if value.providers[*relative].path != source.join(relative)
            || value.providers[*relative].sha256 != *sha
        {
            return fail("configuration provider receipt differs from the actual pinned provider");
        }
    }
    Ok(value)
}

pub(super) fn verify_live(
    reference: &FileRef,
    repo: &Path,
    source: &Path,
    out: &Path,
) -> Result<()> {
    let value = load_record(reference, repo, source, out)?;
    for original in value
        .recipe
        .values()
        .chain(value.providers.values())
        .chain(value.projected.values())
        .chain([&value.checked_init, &value.mesa_native])
    {
        recheck(original, LIMIT)?;
    }
    Ok(())
}

pub(super) fn verify_restored_record(
    reference: &FileRef,
    repo: &Path,
    source: &Path,
    out: &Path,
) -> Result<()> {
    // The normal caller has already restored the journal. Do not pretend the
    // projected source F9 survives restoration; preserve it as original evidence.
    load_record(reference, repo, source, out).map(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    #[test]
    fn complete_product_enables_normal_images_without_avb_or_system_other_promotion() {
        let product = std::str::from_utf8(AFTER_PRODUCT).unwrap();
        for name in ["SYSTEM", "SYSTEM_EXT", "PRODUCT", "VENDOR"] {
            assert_eq!(
                product
                    .matches(&format!("PRODUCT_BUILD_{name}_IMAGE := true\n"))
                    .count(),
                1
            );
            assert!(!product.contains(&format!("PRODUCT_BUILD_{name}_IMAGE := false")));
        }
        assert!(product.contains("PRODUCT_BUILD_SYSTEM_OTHER_IMAGE := false"));
        assert!(product.contains("PRODUCT_BUILD_VBMETA_IMAGE := false"));
        assert!(product.contains("PRODUCT_ENFORCE_VINTF_MANIFEST := true"));
        let board = std::str::from_utf8(AFTER_BOARD).unwrap();
        assert_eq!(board.matches("BOARD_AVB_ENABLE := false").count(), 1);
        assert!(!board.contains("BOARD_AVB_ENABLE := true"));
        assert!(board.contains("BOARD_USES_SYSTEM_OTHER_ODEX := false"));
        assert!(!product.contains("BUILD_ID :="));
    }

    #[test]
    fn real_init_and_service_projection_keep_the_original_source_inputs() {
        assert!(
            std::str::from_utf8(BEFORE_INIT)
                .unwrap()
                .contains("    exec_start derive_classpath\n")
        );
        assert!(
            std::str::from_utf8(AFTER_INIT)
                .unwrap()
                .contains("    exec_start droidloom_derive_classpath\n")
        );
        assert!(
            std::str::from_utf8(AFTER_LMKD)
                .unwrap()
                .contains("service lmkd /vendor/bin/droidloom-lmkd-compat\n")
        );
        assert!(
            std::str::from_utf8(AFTER_NETD)
                .unwrap()
                .contains("service netd /system/bin/netd\n")
        );
        assert!(
            std::str::from_utf8(AFTER_BP)
                .unwrap()
                .contains("name: \"DroidloomSystemUI\",\n    overrides: [\"SystemUI\"]")
        );
        assert_ne!(BEFORE_INIT, AFTER_INIT);
        assert_ne!(BEFORE_LMKD, AFTER_LMKD);
        assert_ne!(BEFORE_NETD, AFTER_NETD);
        assert_ne!(BEFORE_BP, AFTER_BP);
    }

    #[test]
    fn normal_configuration_preflight_rejects_foreign_bytes_and_new_file_aliases() {
        let t = tempfile::tempdir().unwrap();
        let source = t.path().join("source");
        let work = t.path().join("work");
        fs::create_dir_all(&source).unwrap();
        fs::create_dir_all(&work).unwrap();
        let plan = changes(&work).unwrap();
        for c in &plan {
            let p = source.join(&c.relative);
            fs::create_dir_all(p.parent().unwrap()).unwrap();
            if let Some(b) = &c.before {
                fs::write(p, b).unwrap();
            }
        }
        let before = originals(&source, &plan).unwrap();
        assert_eq!(before.len(), 7);
        let changed = source.join(&plan[0].relative);
        fs::write(&changed, b"foreign product").unwrap();
        assert!(originals(&source, &plan).is_err());
        fs::write(&changed, plan[0].before.as_ref().unwrap()).unwrap();
        let new = source.join(&plan[6].relative);
        symlink(&changed, &new).unwrap();
        assert!(originals(&source, &plan).is_err());
        fs::remove_file(new).unwrap();
        assert!(originals(&source, &plan).is_ok());
    }

    #[test]
    fn mesa_configuration_suffix_cannot_admit_extra_make_assignments() {
        let t = tempfile::tempdir().unwrap();
        let p = t.path().join("board");
        let safe = t.path().join("safe_A-9.name");
        fs::create_dir(&safe).unwrap();
        let suffix = mesa_suffix(&safe).unwrap();
        assert_eq!(
            suffix,
            format!(
                "\nBOARD_MESA3D_MESON_ARGS += -Dmesa-clc=system --native-file {}\n",
                safe.join("mesa-native.ini").display()
            )
            .into_bytes()
        );
        // These are actual directories passed to the production input function.
        // No Make process is started and no generated assignment is evaluated.
        for name in [
            "dollar$literal",
            "hash#literal",
            "back\\slash",
            "colon:word",
            "percent%word",
            "paren(word)",
            "space word",
            "tab\tword",
            "line\nword",
            "quote'word",
            "double\"word",
            "semi;word",
            "nonascii-é",
        ] {
            let bad_work = t.path().join(name);
            fs::create_dir(&bad_work).unwrap();
            assert!(bad_work.is_dir());
            assert!(
                mesa_suffix(&bad_work).is_err(),
                "accepted unsafe work directory: {name:?}"
            );
            assert!(changes(&bad_work).is_err());
        }
        use std::os::unix::ffi::OsStringExt;
        let non_utf8 = t
            .path()
            .join(std::ffi::OsString::from_vec(vec![b'x', 0xff]));
        fs::create_dir(&non_utf8).unwrap();
        assert!(mesa_suffix(&non_utf8).is_err());
        let plan = changes(t.path()).unwrap();
        let expected = &plan[1].after;
        fs::write(&p, expected).unwrap();
        exact(&p, expected).unwrap();
        let mut bad = expected.clone();
        bad.extend_from_slice(b"BUILD_ID := CP3A.260905.010\n");
        fs::write(&p, bad).unwrap();
        assert!(exact(&p, expected).is_err());
    }
}
