//! Evidence for the fixed exec/keycreate/fscreate Debian candidate.
//! Consume the producer's actual receipt formats without rewriting them.
use super::{
    CANDIDATE_VERSION, LibselinuxCandidate, MEMBER, ORIGINAL_SHA, ORIGINAL_VERSION, artifact,
    equal_pin,
};
use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

const SOURCE_FILES: [(&str, &[u8]); 5] = [
    (
        "README.md",
        include_bytes!("../../../packaging/ubuntu/libselinux/README.md"),
    ),
    (
        "changelog-entry",
        include_bytes!("../../../packaging/ubuntu/libselinux/changelog-entry"),
    ),
    (
        "native-exec-api-test.c",
        include_bytes!("../../../packaging/ubuntu/libselinux/native-exec-api-test.c"),
    ),
    (
        "p4-native-lsm-exec-attribute.patch",
        include_bytes!("../../../packaging/ubuntu/libselinux/p4-native-lsm-exec-attribute.patch"),
    ),
    (
        "source.lock.json",
        include_bytes!("../../../packaging/ubuntu/libselinux/source.lock.json"),
    ),
];

fn source_lock() -> Result<Value> {
    let lock: Value = serde_json::from_slice(SOURCE_FILES[4].1)?;
    ensure(
        lock["schema"] == "droidloom-ubuntu-libselinux-source-v1"
            && lock["original_version"] == ORIGINAL_VERSION
            && lock["candidate_version"] == CANDIDATE_VERSION,
        "compiled libselinux source lock differs",
    )?;
    Ok(lock)
}

pub(super) fn maintained_source(
    source: &Value,
    declaration: &Value,
    input: &LibselinuxCandidate,
) -> Result<()> {
    let lock = source_lock()?;
    let candidate = artifact(&source["candidate"])?;
    let readback = &source["source_commit_readback"];
    ensure(
        source["association_kind"] == "post_build_exact_source_bytes_matched_to_committed_tree"
            && source["original_build_receipt_preserved"] == true
            && candidate.bytes == input.declaration.bytes
            && candidate.sha256 == input.declaration.sha256
            && readback["schema"] == "p4-native-lsm-source-commit-readback-v1"
            && readback["commit"] == source["commit"]
            && readback["observed_head"] == source["commit"]
            && readback["tree"] == source["tree"]
            && readback["source"] == source["source"]
            && readback["working_tree_status"] == ""
            && readback["files"] == source["files"],
        "candidate source association is not the preserved exact-byte Git readback",
    )?;
    let files = source["files"]
        .as_array()
        .ok_or("source file proofs absent")?;
    ensure(
        files.len() == SOURCE_FILES.len(),
        "source proof file set differs",
    )?;
    let source_input = Path::new(
        declaration["source"]["source_input_directory"]
            .as_str()
            .ok_or("normal source input directory absent")?,
    );
    ensure(
        source_input.is_absolute(),
        "normal source input path is not absolute",
    )?;
    for (name, bytes) in SOURCE_FILES {
        let relative = format!("packaging/ubuntu/libselinux/{name}");
        let matches: Vec<_> = files.iter().filter(|f| f["path"] == relative).collect();
        ensure(
            matches.len() == 1,
            "missing or repeated maintained source file",
        )?;
        let proof = matches[0];
        let expected = FilePin {
            path: source_input.join(name),
            bytes: bytes.len() as u64,
            sha256: fs::digest(bytes),
        };
        ensure(
            proof["bytes"] == expected.bytes
                && proof["sha256"] == expected.sha256
                && proof["working_file_matches"] == true
                && proof["built_source_input_matches_committed_bytes"] == true
                && proof["built_source_input_path"] == expected.path.to_string_lossy().as_ref(),
            "normal build input differs from the compiled maintained source",
        )?;
        boot_files::checked_file(&expected)?;
    }
    ensure(
        source["patch_sha256"] == fs::digest(SOURCE_FILES[3].1)
            && source["test_sha256"] == fs::digest(SOURCE_FILES[2].1)
            && declaration["source"]["patch_sha256"] == lock["patch"]["sha256"]
            && declaration["source"]["procattr_sha256"] == lock["source_file"]["patched_sha256"]
            && declaration["source"]["source_date_epoch"] == lock["source_date_epoch"]
            && declaration["source"]["before_build_exit"] == 0,
        "candidate maintained patch, test or normal source identity differs",
    )?;
    let archives = declaration["source"]["official_archives_verified"]
        .as_array()
        .ok_or("official source archive proofs absent")?;
    let expected = lock["source_archives"]
        .as_array()
        .ok_or("compiled archive pins absent")?;
    ensure(
        archives.len() == expected.len(),
        "official source archive set differs",
    )?;
    ensure(
        archives == expected,
        "original Ubuntu source pin declarations differ",
    )?;
    let package = artifact(&declaration["package"])?;
    let archive_root = package
        .path
        .parent()
        .ok_or("normal package parent absent")?;
    for pin in expected {
        let name = pin["name"].as_str().ok_or("source archive name absent")?;
        let original = FilePin {
            path: archive_root.join(name),
            bytes: pin["bytes"].as_u64().ok_or("source archive size absent")?,
            sha256: pin["sha256"]
                .as_str()
                .ok_or("source archive digest absent")?
                .into(),
        };
        boot_files::checked_file(&original)?;
    }
    for pin in [&input.source_orig_archive, &input.source_orig_signature] {
        ensure(
            expected
                .iter()
                .filter(|p| {
                    pin.path.file_name().and_then(|x| x.to_str()) == p["name"].as_str()
                        && pin.bytes == p["bytes"]
                        && pin.sha256 == p["sha256"]
                })
                .count()
                == 1,
            "candidate original source is not the locked Ubuntu archive",
        )?;
    }
    let readback_root = Path::new(
        declaration["source"]["source"]
            .as_str()
            .ok_or("normal source package readback path absent")?,
    );
    let procattr = boot_files::pin_file(&readback_root.join("src/procattr.c"))?;
    ensure(
        procattr.sha256 == lock["source_file"]["patched_sha256"],
        "normal source package procattr differs from its maintained patch",
    )?;
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BuildCommand {
    name: String,
    argv: Vec<String>,
    cwd: PathBuf,
    exit_code: i32,
    seconds: f64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct NormalBuild {
    success: bool,
    candidate_version: String,
    deb: FilePin,
    library: FilePin,
    commands: Vec<BuildCommand>,
    seconds: f64,
    installed: bool,
    runtime_qualified: bool,
}

pub(super) fn normal_build(value: &Value, declaration: &Value) -> Result<()> {
    let build: NormalBuild = serde_json::from_value(value.clone())?;
    let package = artifact(&declaration["package"])?;
    let library = artifact(&declaration["candidate_library"])?;
    let parent = package.path.parent().ok_or("package parent absent")?;
    let source = parent.join("libselinux-3.9");
    let input = Path::new(
        declaration["source"]["source_input_directory"]
            .as_str()
            .ok_or("normal source input directory absent")?,
    );
    let test_output = input
        .parent()
        .ok_or("test source parent absent")?
        .join("native-exec-api-test-r3");
    let lock = source_lock()?;
    ensure(
        build.success
            && !build.installed
            && !build.runtime_qualified
            && build.candidate_version == CANDIDATE_VERSION
            && equal_pin(&build.deb, &package)
            && equal_pin(&build.library, &library)
            && build.seconds.is_finite()
            && build.seconds >= 0.0
            && build.seconds < 3600.0,
        "candidate did not come from its actual successful normal Debian build",
    )?;
    let expected = [
        (
            "source-extract",
            json!([
                "dpkg-source",
                "-x",
                parent.join("libselinux_3.9-4build1.dsc"),
                source
            ]),
            parent,
        ),
        (
            "source-before-build",
            json!(["dpkg-source", "--before-build", source]),
            parent,
        ),
        (
            "dependency-check",
            json!(["dpkg-checkbuilddeps", "-P", "nopython,noruby,noudeb"]),
            source.as_path(),
        ),
        (
            "test-compile",
            json!([
                "cc",
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-rdynamic",
                "-pthread",
                input.join("native-exec-api-test.c"),
                "-ldl",
                "-o",
                test_output
            ]),
            parent,
        ),
        ("build", lock["build_argv"].clone(), source.as_path()),
        (
            "extract-library",
            json!([
                "dpkg-deb",
                "-x",
                package.path,
                parent.join("unpacked-libselinux1")
            ]),
            parent,
        ),
    ];
    ensure(
        build.commands.len() == expected.len(),
        "normal build command set differs",
    )?;
    for (actual, (name, argv, cwd)) in build.commands.iter().zip(expected) {
        ensure(
            actual.name == name
                && serde_json::to_value(&actual.argv)? == argv
                && actual.cwd == cwd
                && actual.exit_code == 0
                && actual.seconds.is_finite()
                && actual.seconds >= 0.0
                && actual.seconds < 3600.0,
            "normal source, build, test compile or package extraction command differs",
        )?;
    }
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct OriginalLibrary {
    path: PathBuf,
    sha256: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ApiCase {
    attribute: String,
    case: String,
    exit: i32,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Dynamic {
    original: Vec<String>,
    candidate: Vec<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ApiReport {
    schema: String,
    candidate_version: String,
    test_sha256: String,
    tested_library: FilePin,
    original_library: OriginalLibrary,
    tests: Vec<ApiCase>,
    passed: u64,
    total: u64,
    exports_equal: bool,
    exports_count: u64,
    missing_exports: Vec<String>,
    extra_exports: Vec<String>,
    dynamic: Dynamic,
    dependencies_and_soname_equal: bool,
    installed: bool,
    real_kernel_qualified: bool,
}

pub(super) fn public_api(value: &Value, source: &Value, declaration: &Value) -> Result<usize> {
    let api: ApiReport = serde_json::from_value(value.clone())?;
    let dynamic = [
        "libpcre2-8.so.0",
        "libc.so.6",
        "ld-linux-x86-64.so.2",
        "libselinux.so.1",
    ];
    ensure(
        api.schema == "droidloom-native-fscreate-packaged-abi-test-v1"
            && api.candidate_version == CANDIDATE_VERSION
            && source["test_sha256"] == api.test_sha256
            && api.test_sha256 == fs::digest(SOURCE_FILES[2].1)
            && equal_pin(
                &api.tested_library,
                &artifact(&declaration["candidate_library"])?,
            )
            && api.original_library.path == Path::new("/").join(MEMBER)
            && api.original_library.sha256 == ORIGINAL_SHA
            && api.passed == 86
            && api.total == 86
            && api.tests.len() == 86
            && api.exports_equal
            && api.exports_count == 247
            && api.missing_exports.is_empty()
            && api.extra_exports.is_empty()
            && api.dependencies_and_soname_equal
            && api.dynamic.original == dynamic
            && api.dynamic.candidate == dynamic
            && !api.installed
            && !api.real_kernel_qualified,
        "actual stripped package ABI proof or original library binding differs",
    )?;
    let mut cases = BTreeSet::new();
    for test in api.tests {
        ensure(
            test.exit == 0 && cases.insert((test.attribute, test.case)),
            "failed or repeated actual package API case",
        )?;
    }
    let mut expected = BTreeSet::new();
    for attribute in ["exec", "keycreate", "fscreate"] {
        for case in [
            "cache-and-clear",
            "eintr",
            "enosys",
            "eopnotsupp",
            "eacces",
            "eperm",
            "einval",
            "e2big",
            "efault",
            "enomem",
            "null-first",
            "enosys-null",
            "eopnotsupp-null",
            "fallback-failure",
            "failure-retains-cache",
            "thread-local",
            "public-wrapper",
            "positive-result",
            "positive-result-null",
        ] {
            expected.insert((attribute.to_owned(), case.to_owned()));
        }
    }
    for case in [
        "get-value",
        "get-unset",
        "get-cleared",
        "get-public-wrapper",
        "get-eintr",
        "get-enosys",
        "get-eopnotsupp",
        "get-enosys-unset",
        "get-eopnotsupp-unset",
        "get-eacces",
        "get-eperm",
        "get-einval",
        "get-e2big",
        "get-efault",
        "get-enomem",
        "get-bad-count",
        "get-bad-id",
        "get-bad-flags",
        "get-bad-short",
        "get-bad-size",
        "get-bad-length",
        "get-bad-context-length",
        "get-bad-nul",
        "get-bad-embedded-nul",
        "get-bad-unset-alignment",
        "get-bad-padding",
    ] {
        expected.insert(("fscreate".into(), case.into()));
    }
    expected.insert(("exec".into(), "independent-cache".into()));
    for attribute in ["current", "sockcreate"] {
        expected.insert((attribute.into(), "other-attribute".into()));
    }
    ensure(
        cases == expected && expected.len() == 86,
        "actual package API case set differs",
    )?;
    Ok(cases.len())
}
