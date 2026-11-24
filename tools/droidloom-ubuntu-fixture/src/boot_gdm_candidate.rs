//! Exact normal-package GDM replacement in a private, fresh fixture only.
//! The normal source, Debian build, and real root regression evidence are
//! source-owned inputs. This is not dpkg installation or runtime qualification.
use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
    model::{Content, Manifest},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::io::Seek;
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

#[path = "boot_gdm_archive.rs"]
mod archive;

const SOURCE_LOCK: &[u8] = include_bytes!("../../../packaging/ubuntu/gdm/source.lock");
const SOURCE_PATCH: &[u8] =
    include_bytes!("../../../packaging/ubuntu/gdm/p4-dynamic-environment-credentials.patch");
const TEST_SOURCE: &[u8] = include_bytes!("../../../packaging/ubuntu/gdm/tests/environment-file.c");
const LIFECYCLE_PATCH: &[u8] =
    include_bytes!("../../../packaging/ubuntu/gdm/p4-dynamic-directory-lifecycle.patch");
const LIFECYCLE_TEST_SOURCE: &[u8] =
    include_bytes!("../../../packaging/ubuntu/gdm/tests/dynamic-files.c");
const PUBLICATION_PATCH: &[u8] =
    include_bytes!("../../../packaging/ubuntu/gdm/p4-persistent-inode-publication.patch");
const PUBLICATION_PATCH_PATH: &str = "debian/patches/p4-persistent-inode-publication.patch";
const PUBLICATION_PATCH_NAME: &str = "p4-persistent-inode-publication.patch";
const MEMBER: &str = "usr/sbin/gdm3";
const PATCH: &str = "debian/patches/p4-dynamic-environment-credentials.patch";
const PATCH_NAME: &str = "p4-dynamic-environment-credentials.patch";
const LIFECYCLE_PATCH_PATH: &str = "debian/patches/p4-dynamic-directory-lifecycle.patch";
const LIFECYCLE_PATCH_NAME: &str = "p4-dynamic-directory-lifecycle.patch";
const ORIGINAL_VERSION: &str = "50.1-0ubuntu0.1";
const VERSION: &str = "50.1-0ubuntu0.1+p4fsuser3";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GdmCandidate {
    /// Exactly the eighteen names and content pins in the compiled source.lock.
    pub artifacts: BTreeMap<String, FilePin>,
}

fn source_lock() -> Result<Value> {
    let lock: Value = serde_json::from_slice(SOURCE_LOCK)?;
    ensure(
        lock["schema"] == "p4-gdm-fs-user-source-lock-v3"
            && lock["original_version"] == ORIGINAL_VERSION
            && lock["candidate_version"] == VERSION
            && lock["source_files"][PATCH]["sha256"] == fs::digest(SOURCE_PATCH)
            && lock["source_files"]["common/test-environment-file.c"]["sha256"]
                == fs::digest(TEST_SOURCE)
            && lock["source_files"][LIFECYCLE_PATCH_PATH]["sha256"] == fs::digest(LIFECYCLE_PATCH)
            && lock["source_files"][PUBLICATION_PATCH_PATH]["sha256"]
                == fs::digest(PUBLICATION_PATCH)
            && lock["source_files"]["common/test-dynamic-files.c"]["sha256"]
                == fs::digest(LIFECYCLE_TEST_SOURCE),
        "compiled GDM source contract differs",
    )?;
    Ok(lock)
}

fn validate_pins(input: &GdmCandidate, lock: &Value) -> Result<()> {
    let expected = lock["artifacts"]
        .as_object()
        .ok_or("GDM artifact set absent")?;
    ensure(
        expected.len() == 18
            && input.artifacts.keys().collect::<BTreeSet<_>>() == expected.keys().collect(),
        "GDM candidate artifact set differs",
    )?;
    for (key, pin) in &input.artifacts {
        let wanted = &expected[key];
        ensure(
            pin.path.is_absolute()
                && pin.path.file_name().and_then(|n| n.to_str()) == wanted["filename"].as_str()
                && Some(pin.bytes) == wanted["bytes"].as_u64()
                && pin.sha256 == wanted["sha256"]
                && pin.bytes > 0
                && pin.bytes <= 4 * 1024 * 1024
                && fs::valid_digest(&pin.sha256),
            "GDM candidate content pin differs from maintained normal build",
        )?;
    }
    Ok(())
}

fn json_input(pins: &BTreeMap<String, FilePin>, key: &str) -> Result<Value> {
    Ok(serde_json::from_slice(&boot_files::read_pin(
        pins.get(key).ok_or("GDM input absent")?,
        1024 * 1024,
    )?)?)
}

fn sha_sources(text: &str, version: &str) -> Result<BTreeMap<String, (u64, String)>> {
    ensure(
        text.lines().filter(|l| *l == "Source: gdm3").count() == 1
            && text
                .lines()
                .filter(|l| *l == format!("Version: {version}"))
                .count()
                == 1
            && text.lines().filter(|l| *l == "Format: 3.0 (quilt)").count() == 1,
        "GDM source package identity differs",
    )?;
    let mut found = false;
    let mut reading = false;
    let mut result = BTreeMap::new();
    for line in text.lines() {
        if line == "Checksums-Sha256:" {
            ensure(!found, "repeated GDM source checksum field")?;
            found = true;
            reading = true;
            continue;
        }
        if reading && !line.starts_with(' ') {
            reading = false;
        }
        if !reading {
            continue;
        }
        let p: Vec<_> = line.split_whitespace().collect();
        ensure(
            p.len() == 3
                && fs::valid_digest(p[0])
                && (p[2] == "gdm3_50.1.orig.tar.xz"
                    || p[2] == format!("gdm3_{version}.debian.tar.xz")),
            "GDM source checksum row differs",
        )?;
        ensure(
            result
                .insert(p[2].into(), (p[1].parse()?, p[0].into()))
                .is_none(),
            "duplicate GDM source archive",
        )?;
    }
    ensure(found && result.len() == 2, "GDM source archive pair absent")?;
    Ok(result)
}

fn unpack_source(
    work: &Path,
    stem: &str,
    pin: &FilePin,
    members: usize,
) -> Result<BTreeMap<String, archive::Member>> {
    let tar = crate::boot_runtime::redirected(
        work,
        stem,
        "/usr/bin/xz",
        &[
            "--decompress".into(),
            "--stdout".into(),
            pin.path.to_string_lossy().into(),
        ],
        None,
        None,
        &work.join(format!("{stem}.tar")),
        16 * 1024 * 1024,
        30,
    )?;
    archive::read(
        &boot_files::read_pin(&tar, 16 * 1024 * 1024)?,
        &BTreeMap::new(),
        members,
    )
}

fn verify_regression(tests: &Value, log: &str, lock: &Value, lifecycle: bool) -> Result<()> {
    let (prefix, wanted): (&str, &[&str]) = if lifecycle {
        (
            "lifecycle",
            &[
                "ok 1 /dynamic-files/private-000-copy-refused-unchanged",
                "ok 2 /dynamic-files/write-retire-exclusive-recreate",
                "ok 3 /dynamic-files/foreign-owner-fails-and-restores",
                "ok 4 /dynamic-files/hard-link-transfer-rejected",
                "ok 5 /dynamic-files/root-alias-rejected",
                "ok 6 /dynamic-files/original-gdm-data-owner",
                "ok 7 /dynamic-files/denied-fsuid-restores-without-dac",
                "ok 8 /dynamic-files/private-000-retirement-refused",
                "ok 9 /dynamic-files/retained-handoff-refused",
                "ok 10 /dynamic-files/old-writer-fd-cannot-change-new-inode",
                "ok 11 /dynamic-files/concurrent-hardlink-preserves-original-owner",
                "ok 12 /dynamic-files/concurrent-rename-preserves-original-owner",
                "ok 13 /dynamic-files/concurrent-write-refuses-publication",
                "ok 14 /dynamic-files/new-inodes-private-until-publication",
            ],
        )
    } else {
        (
            "root",
            &[
                "ok 1 /environment/private-write-replace-and-thread-scope",
                "ok 2 /environment/io-failure-restores-identity",
                "ok 3 /environment/restoration-denial-is-fatal",
            ],
        )
    };
    let executable = &lock["artifacts"][format!("{prefix}_test_executable")];
    let recorded_log = &lock["artifacts"][format!("{prefix}_test_log")];
    ensure(
        tests["schema"] == 1
            && tests["source_commit"] == lock["source_commit"]
            && tests["exit_code"] == 0
            && tests["actual_root_subprocess_tests"] == true
            && tests["enforcing_target_gdm_runtime_qualified"] == false
            && tests["normal_debian_build_test_artifact"] == true
            && tests["cases_passed"].as_u64() == Some(wanted.len() as u64)
            && tests["test_elf"]["bytes"] == executable["bytes"]
            && tests["test_elf"]["sha256"] == executable["sha256"]
            && tests["test_log"]["bytes"] == recorded_log["bytes"]
            && tests["test_log"]["sha256"] == recorded_log["sha256"],
        "GDM actual root regression binding differs",
    )?;
    let cases: Vec<_> = log.lines().filter(|l| l.starts_with("ok ")).collect();
    ensure(
        log.lines()
            .filter(|l| *l == format!("1..{}", wanted.len()))
            .count()
            == 1
            && !log.contains("not ok ")
            && !log.contains("# SKIP")
            && cases == wanted,
        "GDM actual root regression cases did not all pass",
    )
}

fn verify_sources(pins: &BTreeMap<String, FilePin>, lock: &Value, work: &Path) -> Result<Value> {
    let freeze = json_input(pins, "source_freeze")?;
    ensure(
        freeze["source_commit"] == lock["source_commit"]
            && freeze["source_tree"] == lock["source_tree"]
            && freeze["base_source_commit"] == lock["base_source_commit"]
            && freeze["normal_version"] == VERSION
            && freeze["files"] == lock["source_files"],
        "GDM maintained source freeze differs",
    )?;
    for (key, version, archive_key) in [
        ("source_dsc", VERSION, "source_debian_archive"),
        (
            "original_source_dsc",
            ORIGINAL_VERSION,
            "original_debian_archive",
        ),
    ] {
        let text = String::from_utf8(boot_files::read_pin(&pins[key], 65536)?)?;
        let rows = sha_sources(&text, version)?;
        for key in [archive_key, "source_orig_archive"] {
            let pin = &pins[key];
            let name = pin
                .path
                .file_name()
                .and_then(|p| p.to_str())
                .ok_or("GDM archive basename absent")?;
            ensure(
                rows.get(name) == Some(&(pin.bytes, pin.sha256.clone())),
                "GDM archive not bound by actual dsc",
            )?;
        }
    }
    let original = unpack_source(
        work,
        "original-source",
        &pins["original_debian_archive"],
        100,
    )?;
    let updated = unpack_source(work, "updated-source", &pins["source_debian_archive"], 103)?;
    let mut keys: BTreeSet<_> = original.keys().map(String::as_str).collect();
    keys.insert(PATCH);
    keys.insert(LIFECYCLE_PATCH_PATH);
    keys.insert(PUBLICATION_PATCH_PATH);
    ensure(
        keys == updated.keys().map(String::as_str).collect(),
        "GDM Debian source member set changed unexpectedly",
    )?;
    for (path, before) in &original {
        if ["debian/changelog", "debian/patches/series"].contains(&path.as_str()) {
            continue;
        }
        let after = &updated[path];
        ensure(
            before.kind == after.kind && before.body == after.body && before.link == after.link,
            "GDM normal Debian rules or unrelated source file changed",
        )?;
    }
    ensure(
        archive::regular(&updated, PATCH, None)? == SOURCE_PATCH
            && archive::regular(&updated, LIFECYCLE_PATCH_PATH, None)? == LIFECYCLE_PATCH
            && archive::regular(&updated, PUBLICATION_PATCH_PATH, None)? == PUBLICATION_PATCH
            && fs::digest(archive::regular(&updated, "debian/rules", None)?)
                == lock["debian_rules_sha256"],
        "GDM quilt patch/rules differ from maintained source",
    )?;
    let old_series =
        std::str::from_utf8(archive::regular(&original, "debian/patches/series", None)?)?;
    let series = std::str::from_utf8(archive::regular(&updated, "debian/patches/series", None)?)?;
    ensure(
        series.lines().collect::<Vec<_>>()
            == old_series
                .lines()
                .chain([PATCH_NAME, LIFECYCLE_PATCH_NAME, PUBLICATION_PATCH_NAME])
                .collect::<Vec<_>>(),
        "GDM quilt series did not append only the three maintained patches",
    )?;
    ensure(
        std::str::from_utf8(archive::regular(&updated, "debian/changelog", None)?)?
            .starts_with(&format!("gdm3 ({VERSION})")),
        "GDM Debian changelog version differs",
    )?;
    let intent = json_input(pins, "normal_build_intent")?;
    let build = json_input(pins, "normal_build_result")?;
    let argv = intent["argv"]
        .as_array()
        .ok_or("GDM normal build argv absent")?;
    ensure(
        intent["source_commit"] == lock["source_commit"]
            && intent["source_tree"] == lock["source_tree"]
            && intent["version"] == VERSION
            && intent["all_original_debian_rules_and_tests"] == true
            && intent["installed_candidate"] == false
            && argv.ends_with(&[
                json!("/usr/bin/dpkg-buildpackage"),
                json!("-F"),
                json!("-j2"),
                json!("-us"),
                json!("-uc"),
            ])
            && build["exit_code"] == 0
            && build["frozen_source_unchanged"] == true
            && build["canonical_source_unchanged"] == true
            && build["source_roundtrip_verified"] == true
            && build["source_commit"] == lock["source_commit"]
            && build["installed_candidate"] == false,
        "GDM candidate lacks the successful complete normal Debian build",
    )?;
    let files = lock["source_files"]
        .as_object()
        .ok_or("GDM source file set absent")?;
    let roundtrip = build["source_roundtrip"]
        .as_object()
        .ok_or("GDM normal source round-trip absent")?;
    ensure(
        files.len() == 15 && files.keys().collect::<BTreeSet<_>>() == roundtrip.keys().collect(),
        "GDM normal source round-trip file set differs",
    )?;
    for (path, wanted) in files {
        let actual = &roundtrip[path];
        ensure(
            actual["bytes"] == wanted["bytes"]
                && actual["sha256"] == wanted["sha256"]
                && actual["canonical_sha256"] == wanted["sha256"],
            "GDM new normal dsc did not reproduce its maintained source bytes",
        )?;
    }
    for key in [
        "package",
        "source_dsc",
        "source_debian_archive",
        "buildinfo",
        "changes",
    ] {
        let want = &lock["artifacts"][key];
        let name = want["filename"]
            .as_str()
            .ok_or("GDM build output name absent")?;
        ensure(
            build["outputs"][name]["bytes"] == want["bytes"]
                && build["outputs"][name]["sha256"] == want["sha256"],
            "GDM actual build output differs",
        )?;
    }
    let tests = json_input(pins, "root_test_result")?;
    let log = String::from_utf8(boot_files::read_pin(&pins["root_test_log"], 65536)?)?;
    verify_regression(&tests, &log, lock, false)?;
    let lifecycle = json_input(pins, "lifecycle_test_result")?;
    let lifecycle_log =
        String::from_utf8(boot_files::read_pin(&pins["lifecycle_test_log"], 65536)?)?;
    verify_regression(&lifecycle, &lifecycle_log, lock, true)?;
    Ok(
        json!({"source_commit":lock["source_commit"], "source_tree":lock["source_tree"],
        "source_lock_sha256":fs::digest(SOURCE_LOCK), "normal_debian_build_exit_code":0,
        "unchanged_original_debian_rules":true,"only_quilt_patch_series_and_changelog_changed":true,
        "actual_root_tests":17,"unprivileged_meson_root_tests_skipped":17,
        "normal_dsc_source_roundtrip_files_verified":15,
        "test_host_kernel":tests["host_kernel"],"target_gdm_runtime_qualified":false}),
    )
}

fn elf_report(
    path: &Path,
    work: &Path,
    stem: &str,
    candidate: bool,
    lock: &Value,
) -> Result<Value> {
    let pin = boot_files::pin_file(path)?;
    let bytes = boot_files::read_pin(&pin, 1024 * 1024)?;
    ensure(
        bytes.len() >= 64 && &bytes[..6] == b"\x7fELF\x02\x01" && bytes[16..20] == [3, 0, 62, 0],
        "GDM is not an x86_64 PIE ELF",
    )?;
    let elf = boot_files::run_logged(
        work,
        &format!("{stem}-elf"),
        "/usr/bin/readelf",
        &[
            "--wide".into(),
            "--dynamic".into(),
            "--program-headers".into(),
            "--dyn-syms".into(),
            path.to_string_lossy().into(),
        ],
        30,
    )?;
    let text = String::from_utf8(boot_files::read_pin(&elf.log, 1024 * 1024)?)?;
    let needed: Vec<_> = text
        .lines()
        .filter(|l| l.contains("(NEEDED)"))
        .map(|l| {
            l.split_once('[')
                .and_then(|(_, s)| s.strip_suffix(']'))
                .ok_or("invalid GDM NEEDED field")
        })
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let expected: Vec<_> = lock["needed"]
        .as_array()
        .ok_or("GDM dependency contract absent")?
        .iter()
        .map(|v| v.as_str().ok_or("invalid GDM dependency"))
        .collect::<std::result::Result<_, _>>()?;
    ensure(
        needed == expected
            && !text.contains("(RPATH)")
            && !text.contains("(RUNPATH)")
            && !text.contains("(TEXTREL)")
            && !text.contains("(SONAME)")
            && text
                .lines()
                .filter(|l| {
                    l.contains("[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]")
                })
                .count()
                == 1
            && text.lines().filter(|l| l.contains("GNU_STACK")).count() == 1
            && text
                .lines()
                .find(|l| l.contains("GNU_STACK"))
                .is_some_and(|l| {
                    l.split_whitespace().any(|p| p == "RW")
                        && !l.split_whitespace().any(|p| p == "RWE")
                }),
        "GDM loader/dependency/stack contract differs",
    )?;
    if candidate {
        for name in ["setfsuid@GLIBC_2.2.5", "setfsgid@GLIBC_2.2.5"] {
            ensure(
                text.lines()
                    .filter(|l| l.contains(" UND ") && l.split_whitespace().any(|p| p == name))
                    .count()
                    == 1,
                "GDM candidate lacks its actual filesystem-credential calls",
            )?;
        }
    }
    Ok(
        json!({"executable":pin,"needed":needed,"interpreter":"/lib64/ld-linux-x86-64.so.2","nonexecutable_stack":true,"readelf":elf.log}),
    )
}

fn prepare_candidate(
    input: &GdmCandidate,
    lock: &Value,
    layer: &Path,
) -> Result<(Value, PathBuf, Value)> {
    validate_pins(input, lock)?;
    let artifacts = layer.join("artifacts");
    boot_files::private_dir(&artifacts)?;
    let mut local = BTreeMap::new();
    for (key, pin) in &input.artifacts {
        let target = artifacts.join(pin.path.file_name().ok_or("GDM input filename absent")?);
        boot_files::copy_pin(pin, &target, 0o400)?;
        local.insert(key.clone(), boot_files::pin_file(&target)?);
    }
    let sources = verify_sources(&local, lock, layer)?;
    let package = &local["package"];
    for (field, want) in [
        ("Package", "gdm3"),
        ("Version", VERSION),
        ("Architecture", "amd64"),
    ] {
        let report = boot_files::run_logged(
            &layer,
            &format!("deb-{}", field.to_lowercase()),
            "/usr/bin/dpkg-deb",
            &[
                "--field".into(),
                package.path.to_string_lossy().into(),
                field.into(),
            ],
            30,
        )?;
        ensure(
            String::from_utf8(boot_files::read_pin(&report.log, 4096)?)?.trim() == want,
            "actual normal GDM package identity differs",
        )?;
    }
    let tar = crate::boot_runtime::redirected(
        &layer,
        "deb-data",
        "/usr/bin/dpkg-deb",
        &[
            "--fsys-tarfile".into(),
            package.path.to_string_lossy().into(),
        ],
        None,
        None,
        &layer.join("data.tar"),
        16 * 1024 * 1024,
        30,
    )?;
    let aliases = BTreeMap::from([
        ("usr/lib/systemd/system/gdm3.service", "gdm.service"),
        ("usr/share/dconf/profile/Debian-gdm", "gdm"),
        (
            "usr/share/gdm/dconf/90-debian-settings",
            "/etc/gdm3/greeter.dconf-defaults",
        ),
    ]);
    let entries = archive::read(
        &boot_files::read_pin(&tar, 16 * 1024 * 1024)?,
        &aliases,
        562,
    )?;
    let bytes = archive::regular(&entries, MEMBER, Some(0o755))?;
    ensure(
        Some(bytes.len() as u64) == lock["candidate_executable"]["bytes"].as_u64()
            && fs::digest(bytes) == lock["candidate_executable"]["sha256"],
        "actual package GDM ELF differs",
    )?;
    let selected = layer.join("gdm3");
    boot_files::write_new(&selected, bytes, 0o755)?;
    let candidate_elf = elf_report(&selected, layer, "candidate", true, lock)?;
    Ok((sources, selected, candidate_elf))
}

pub fn apply(root: &Path, boot: &Path, manifest: &Manifest, input: &GdmCandidate) -> Result<Value> {
    let work = boot.parent().ok_or("GDM candidate work parent absent")?;
    ensure(
        work.parent() == Some(Path::new("/var/lib/droidloom-qualification"))
            && root == work.join("root")
            && boot == work.join("boot"),
        "GDM candidate only accepts a fresh qualification clone",
    )?;
    let owner = fs::Tree::open(&fs::absolute_string(work)?, 0)?;
    ensure(
        fs::stat(&owner.root)?.mode & 0o7777 == 0o700,
        "GDM candidate work is not private",
    )?;
    let lock = source_lock()?;
    validate_pins(input, &lock)?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let guest = format!("/{MEMBER}");
    let original = tree.identity(&guest)?;
    let expected = manifest
        .entries
        .iter()
        .find(|e| e.path == guest)
        .ok_or("original GDM absent from fixture manifest")?;
    ensure(
        rustix::fs::FileType::from_raw_mode(original.mode) == rustix::fs::FileType::RegularFile
            && original.uid == 0
            && original.gid == 0
            && original.nlink == 1
            && original.mode & 0o7777 == 0o755
            && Some(original.size) == lock["original_executable"]["bytes"].as_u64()
            && matches!(&expected.content, Content::Regular{sha256} if sha256 == lock["original_executable"]["sha256"].as_str().unwrap_or("")),
        "GDM destination is not the original independent selected fixture ELF",
    )?;
    let original_pin = boot_files::pin_file(&root.join(MEMBER))?;
    ensure(
        original_pin.sha256 == lock["original_executable"]["sha256"],
        "original fixture GDM bytes differ",
    )?;
    let mut original_file = boot_files::checked_file(&original_pin)?;
    // A captured public fixture need not contain a dpkg database. Preserve its
    // presence as well as any existing file identity and bytes across this overlay.
    let status_before = crate::boot_candidate::dpkg_status(root)?;
    let status_identity_before = status_before
        .as_ref()
        .map(|_| tree.identity("/var/lib/dpkg/status"))
        .transpose()?;
    let layer = boot.join("gdm-candidate");
    boot_files::private_dir(&layer)?;
    let (sources, selected, candidate_elf) = prepare_candidate(input, &lock, &layer)?;
    let before = layer.join("original-gdm3");
    boot_files::copy_pin(&original_pin, &before, 0o400)?;
    let original_elf = elf_report(&before, &layer, "original", false, &lock)?;
    let mut dependencies = Vec::new();
    for name in lock["needed"].as_array().ok_or("GDM dependencies absent")? {
        let name = name.as_str().ok_or("invalid GDM dependency")?;
        let (pin, resolution) =
            boot_files::resolve_public_file(root, &format!("/usr/lib/x86_64-linux-gnu/{name}"))?;
        let guest_path = format!(
            "/{}",
            pin.path
                .strip_prefix(root)?
                .to_str()
                .ok_or("dependency path encoding differs")?
        );
        ensure(
            manifest.entries.iter().any(|e| {
                e.path == guest_path
                    && matches!(&e.content, Content::Regular{sha256} if sha256 == &pin.sha256)
            }),
            "GDM dependency is not from the selected original fixture",
        )?;
        dependencies.push(json!({"library":pin,"resolution":resolution}));
    }
    let temporary = root.join("usr/sbin/.gdm3-p4-candidate-new");
    boot_files::copy_pin(&boot_files::pin_file(&selected)?, &temporary, 0o755)?;
    ensure(
        tree.identity(&guest)? == original
            && fs::stat(&original_file)? == original
            && fs::hash(&original_file)? == original_pin.sha256,
        "original GDM changed before candidate replacement",
    )?;
    let parent = tree.dir("/usr/sbin")?;
    rustix::fs::renameat(&parent, ".gdm3-p4-candidate-new", &parent, "gdm3")?;
    rustix::fs::fsync(&parent)?;
    let installed = boot_files::pin_file(&root.join(MEMBER))?;
    let id = tree.identity(&guest)?;
    // hash() consumes the held descriptor offset; re-read the same original inode.
    original_file.rewind()?;
    ensure(
        installed.sha256 == lock["candidate_executable"]["sha256"]
            && Some(installed.bytes) == lock["candidate_executable"]["bytes"].as_u64()
            && id.uid == 0
            && id.gid == 0
            && id.nlink == 1
            && id.mode & 0o7777 == 0o755
            && fs::hash(&original_file)? == original_pin.sha256,
        "installed GDM or original-held ELF readback differs",
    )?;
    let status_after = crate::boot_candidate::dpkg_status(root)?;
    let status_identity_after = status_after
        .as_ref()
        .map(|_| tree.identity("/var/lib/dpkg/status"))
        .transpose()?;
    let status_unchanged = match (&status_before, &status_after) {
        (None, None) => true,
        (Some(before), Some(after)) => crate::boot_candidate::equal_pin(before, after),
        _ => false,
    };
    ensure(
        status_unchanged && status_identity_before == status_identity_after,
        "GDM overlay changed dpkg state",
    )?;
    let result = json!({"schema":"droidloom.fixture-gdm-candidate.v1", "input":input,
        "source_lock_sha256":fs::digest(SOURCE_LOCK),"sources":sources,"original":original_pin,
        "preserved_original":boot_files::pin_file(&before)?,"installed_candidate":installed,
        "original_elf":original_elf,"candidate_elf":candidate_elf,"dependencies":dependencies,
        "dpkg_status":status_after,"dpkg_database_updated":false,"maintainer_scripts_executed":false,
        "overlay_only":true,"guest_qualified":false,"production_ready":false});
    fs::write_json(
        &fs::absolute_string(&layer.join("OVERLAY.json"))?,
        &result,
        0,
    )?;
    Ok(result)
}

pub fn verify_image(root: &Path, work: &Path, image: &Path) -> Result<Value> {
    let lock = source_lock()?;
    let expected = boot_files::pin_file(&root.join(MEMBER))?;
    let candidate = expected.sha256 == lock["candidate_executable"]["sha256"]
        && Some(expected.bytes) == lock["candidate_executable"]["bytes"].as_u64();
    ensure(
        candidate
            || (expected.sha256 == lock["original_executable"]["sha256"]
                && Some(expected.bytes) == lock["original_executable"]["bytes"].as_u64()),
        "GDM image contains an unadmitted ELF",
    )?;
    if candidate {
        let overlay = boot_files::pin_file(&work.join("gdm-candidate/OVERLAY.json"))?;
        let record: Value = serde_json::from_slice(&boot_files::read_pin(&overlay, 1024 * 1024)?)?;
        ensure(
            record["schema"] == "droidloom.fixture-gdm-candidate.v1"
                && record["source_lock_sha256"] == fs::digest(SOURCE_LOCK)
                && record["installed_candidate"]["sha256"] == expected.sha256
                && record["dpkg_database_updated"] == false,
            "GDM image lost its actual source admission",
        )?;
    }
    let check = work.join("gdm-image-readback");
    boot_files::private_dir(&check)?;
    let extracted = check.join("gdm3");
    let command = format!(
        "dump -p /{MEMBER} {}",
        crate::boot_runtime::debugfs_command_path(&fs::absolute_string(&extracted)?)?
    );
    let dump = boot_files::run_logged(
        &check,
        "gdm3",
        "/usr/sbin/debugfs",
        &["-R".into(), command, image.to_string_lossy().into()],
        30,
    )?;
    let actual = boot_files::pin_file(&extracted)?;
    ensure(
        actual.bytes == expected.bytes && actual.sha256 == expected.sha256,
        "actual ext4 GDM bytes differ from the admitted root",
    )?;
    Ok(
        json!({"source":expected,"image_executable":actual,"dump":dump,
        "source_candidate_applied":candidate,"all_matched":true,"runtime_qualified":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "requires actual original public fixture files, root-protected candidate inputs, and fresh protected work"]
    fn actual_original_fixture_apply_preserves_optional_status_and_held_elf() -> Result<()> {
        ensure(
            rustix::process::geteuid().as_raw() == 0,
            "actual apply test requires root",
        )?;
        let value = |name| {
            std::env::var_os(name)
                .map(PathBuf::from)
                .ok_or("actual apply input absent")
        };
        let config = value("DROIDLOOM_GDM_ADMISSION_INPUTS")?;
        let source = value("DROIDLOOM_GDM_APPLY_SOURCE_ROOT")?;
        let manifest_path = value("DROIDLOOM_GDM_APPLY_MANIFEST")?;
        let work = value("DROIDLOOM_GDM_APPLY_WORK")?;
        let parent = Path::new("/var/lib/droidloom-qualification");
        ensure(
            work.parent() == Some(parent),
            "actual apply work outside qualification root",
        )?;
        boot_files::private_dir(&work)?;
        let config_pin = boot_files::pin_file(&config)?;
        let input: GdmCandidate =
            serde_json::from_slice(&boot_files::read_pin(&config_pin, 65536)?)?;
        let manifest_pin = FilePin {
            path: manifest_path,
            bytes: 31749096,
            sha256: "7cc2be80bdf94e30f8b0d73be13a04b45bb3165a4395c9d7653c26d1644d9965".into(),
        };
        let manifest: Manifest =
            serde_json::from_slice(&boot_files::read_pin(&manifest_pin, 64 * 1024 * 1024)?)?;
        ensure(
            manifest.schema == crate::model::MANIFEST_SCHEMA,
            "original public manifest schema differs",
        )?;
        let lock = source_lock()?;
        let original = boot_files::pin_file(&source.join(MEMBER))?;
        ensure(
            Some(original.bytes) == lock["original_executable"]["bytes"].as_u64()
                && original.sha256 == lock["original_executable"]["sha256"],
            "original fixture test ELF differs",
        )?;
        let mut held = boot_files::checked_file(&original)?;
        let original_identity = fs::stat(&held)?;
        let mut files = BTreeMap::from([(format!("/{MEMBER}"), original.clone())]);
        let mut aliases = BTreeMap::new();
        for name in lock["needed"]
            .as_array()
            .ok_or("test dependency contract absent")?
        {
            let name = name.as_str().ok_or("test dependency name invalid")?;
            let (pin, resolution) = boot_files::resolve_public_file(
                &source,
                &format!("/usr/lib/x86_64-linux-gnu/{name}"),
            )?;
            let guest = format!(
                "/{}",
                pin.path
                    .strip_prefix(&source)?
                    .to_str()
                    .ok_or("test path encoding differs")?
            );
            ensure(manifest.entries.iter().any(|entry| entry.path == guest
                && matches!(&entry.content, Content::Regular {sha256} if sha256 == &pin.sha256)),
                "test dependency differs from selected original public manifest")?;
            files.insert(guest, pin);
            for alias in resolution["aliases"]
                .as_array()
                .ok_or("dependency aliases absent")?
            {
                let path = alias["path"]
                    .as_str()
                    .ok_or("dependency alias path absent")?;
                let target = alias["target"]
                    .as_str()
                    .ok_or("dependency alias target absent")?;
                ensure(manifest.entries.iter().any(|entry| entry.path == path
                    && matches!(&entry.content, Content::Symlink {target: wanted} if wanted == target)),
                    "test dependency alias differs from original public manifest")?;
                aliases.insert(path.to_owned(), target.to_owned());
            }
        }
        let stem = work
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("apply test stem absent")?;
        let mut cases = Vec::new();
        for case in ["status-absent", "status-present", "changed-original"] {
            let destination = parent.join(format!("{stem}-{case}"));
            boot_files::private_dir(&destination)?;
            let root = destination.join("root");
            let boot = destination.join("boot");
            boot_files::private_dir(&root)?;
            boot_files::private_dir(&boot)?;
            for (guest, pin) in &files {
                let target = root.join(guest.trim_start_matches('/'));
                std::fs::create_dir_all(target.parent().ok_or("test file parent absent")?)?;
                let original_mode = fs::stat(&boot_files::checked_file(pin)?)?.mode & 0o777;
                boot_files::copy_pin(pin, &target, original_mode)?;
            }
            for (guest, target) in &aliases {
                let path = root.join(guest.trim_start_matches('/'));
                std::fs::create_dir_all(path.parent().ok_or("test alias parent absent")?)?;
                std::os::unix::fs::symlink(target, path)?;
            }
            let status = root.join("var/lib/dpkg/status");
            if case == "status-present" {
                std::fs::create_dir_all(status.parent().ok_or("test status parent absent")?)?;
                boot_files::write_new(&status, b"Package: fixture-apply-preservation-test\nStatus: install ok installed\nArchitecture: amd64\nVersion: 1\n\n", 0o644)?;
            }
            if case == "changed-original" {
                use std::os::unix::fs::FileExt;
                let f = std::fs::OpenOptions::new()
                    .write(true)
                    .open(root.join(MEMBER))?;
                f.write_all_at(b"X", 0)?;
                f.sync_all()?;
                let error = apply(&root, &boot, &manifest, &input)
                    .err()
                    .ok_or("altered original ELF accepted")?;
                ensure(
                    !boot.join("gdm-candidate").exists(),
                    "altered original progressed to replacement",
                )?;
                cases.push(json!({"case":case,"rejected":true,"error":error.to_string()}));
            } else {
                let tree = fs::Tree::open(&fs::absolute_string(&root)?, 0)?;
                let before_status = crate::boot_candidate::dpkg_status(&root)?;
                let before_identity = before_status
                    .as_ref()
                    .map(|_| tree.identity("/var/lib/dpkg/status"))
                    .transpose()?;
                let overlay = apply(&root, &boot, &manifest, &input)?;
                let after_status = crate::boot_candidate::dpkg_status(&root)?;
                let after_identity = after_status
                    .as_ref()
                    .map(|_| tree.identity("/var/lib/dpkg/status"))
                    .transpose()?;
                ensure(
                    before_identity == after_identity
                        && match (&before_status, &after_status) {
                            (None, None) => true,
                            (Some(a), Some(b)) => crate::boot_candidate::equal_pin(a, b),
                            _ => false,
                        },
                    "actual apply changed optional dpkg fixture state",
                )?;
                ensure(
                    overlay["preserved_original"]["sha256"] == original.sha256
                        && overlay["installed_candidate"]["sha256"]
                            == lock["candidate_executable"]["sha256"]
                        && overlay["dpkg_database_updated"] == false,
                    "actual apply omitted its original/candidate custody",
                )?;
                cases.push(json!({"case":case,"applied":true,"status_presence_identity_and_bytes_preserved":true,
                    "overlay":boot_files::pin_file(&boot.join("gdm-candidate/OVERLAY.json"))?}));
            }
        }
        held.rewind()?;
        ensure(
            fs::stat(&held)? == original_identity
                && fs::hash(&held)? == original.sha256
                && boot_files::pin_file(&source.join(MEMBER))?.sha256 == original.sha256,
            "original public fixture changed during apply tests",
        )?;
        fs::write_json(
            &fs::absolute_string(&work.join("RESULT.json"))?,
            &json!({"schema":"droidloom.gdm-real-apply-regression.v1","inputs":config_pin,
                "source_lock_sha256":fs::digest(SOURCE_LOCK),"original_manifest":manifest_pin,
                "original_elf":original,"copied_original_regular_files":files.len(),"cases":cases,
                "actual_full_apply_function":true,"full_native_fixture":false,
                "gdm_executed":false,"guest_runtime_qualified":false}),
            0,
        )?;
        Ok(())
    }
    #[test]
    #[ignore = "requires the root-protected normal GDM artifacts and a fresh qualification directory"]
    fn actual_normal_gdm_artifacts_admission() -> Result<()> {
        ensure(
            rustix::process::geteuid().as_raw() == 0,
            "actual admission test requires root",
        )?;
        let config = PathBuf::from(
            std::env::var_os("DROIDLOOM_GDM_ADMISSION_INPUTS").ok_or("actual GDM inputs absent")?,
        );
        let work = PathBuf::from(
            std::env::var_os("DROIDLOOM_GDM_ADMISSION_WORK").ok_or("actual GDM work absent")?,
        );
        ensure(
            work.parent() == Some(Path::new("/var/lib/droidloom-qualification")),
            "actual GDM admission work outside protected root",
        )?;
        boot_files::private_dir(&work)?;
        let config_pin = boot_files::pin_file(&config)?;
        let original = boot_files::read_pin(&config_pin, 65536)?;
        let input: GdmCandidate = serde_json::from_slice(&original)?;
        let lock = source_lock()?;
        let positive = work.join("positive");
        boot_files::private_dir(&positive)?;
        let (sources, selected, elf) = prepare_candidate(&input, &lock, &positive)?;
        let mut rejected = Vec::new();
        for case in [
            "missing-input",
            "extra-input",
            "truncated-package",
            "changed-package-byte",
            "changed-source-proof",
            "symlink-package",
        ] {
            let mut changed: GdmCandidate = serde_json::from_slice(&original)?;
            let case_root = work.join(case);
            boot_files::private_dir(&case_root)?;
            if case == "missing-input" {
                changed.artifacts.remove("source_freeze");
            } else if case == "extra-input" {
                changed
                    .artifacts
                    .insert("extra".into(), changed.artifacts["package"].clone());
            } else {
                let key = if case == "changed-source-proof" {
                    "source_freeze"
                } else {
                    "package"
                };
                let pin = &input.artifacts[key];
                let path =
                    case_root.join(pin.path.file_name().ok_or("actual input basename absent")?);
                if case == "symlink-package" {
                    std::os::unix::fs::symlink(&pin.path, &path)?;
                } else {
                    let mut bytes = boot_files::read_pin(pin, 4 * 1024 * 1024)?;
                    if case == "truncated-package" {
                        bytes.pop();
                    } else {
                        bytes[0] ^= 1;
                    }
                    boot_files::write_new(&path, &bytes, 0o400)?;
                }
                changed
                    .artifacts
                    .get_mut(key)
                    .ok_or("negative input absent")?
                    .path = path;
            }
            let attempt = case_root.join("attempt");
            boot_files::private_dir(&attempt)?;
            let error = prepare_candidate(&changed, &lock, &attempt)
                .err()
                .ok_or("actual malformed GDM input was accepted")?;
            rejected.push(json!({"case":case,"rejected":true,"error":error.to_string()}));
        }
        let result = json!({"schema":"droidloom.gdm-candidate-admission-test.v1", "source_lock_sha256":fs::digest(SOURCE_LOCK),
            "inputs":config_pin,"sources":sources,"selected":boot_files::pin_file(&selected)?,"elf":elf,
            "actual_positive_passed":true,"actual_negative_cases":rejected,"candidate_executed":false,
            "fixture_replaced":false,"guest_runtime_qualified":false});
        fs::write_json(&fs::absolute_string(&work.join("RESULT.json"))?, &result, 0)?;
        Ok(())
    }
    fn inputs(lock: &Value) -> GdmCandidate {
        GdmCandidate {
            artifacts: lock["artifacts"]
                .as_object()
                .unwrap()
                .iter()
                .map(|(k, v)| {
                    (
                        k.clone(),
                        FilePin {
                            path: PathBuf::from("/fixed").join(v["filename"].as_str().unwrap()),
                            bytes: v["bytes"].as_u64().unwrap(),
                            sha256: v["sha256"].as_str().unwrap().into(),
                        },
                    )
                })
                .collect(),
        }
    }
    #[test]
    fn pins_reject_missing_extra_changed_digest_size_and_basename() -> Result<()> {
        let lock = source_lock()?;
        validate_pins(&inputs(&lock), &lock)?;
        for kind in 0..5 {
            let mut input = inputs(&lock);
            match kind {
                0 => {
                    input.artifacts.remove("package");
                }
                1 => {
                    input
                        .artifacts
                        .insert("extra".into(), input.artifacts["package"].clone());
                }
                2 => input.artifacts.get_mut("package").unwrap().bytes += 1,
                3 => input.artifacts.get_mut("package").unwrap().sha256 = "0".repeat(64),
                _ => {
                    input.artifacts.get_mut("package").unwrap().path =
                        PathBuf::from("/fixed/substituted.deb")
                }
            }
            assert!(validate_pins(&input, &lock).is_err());
        }
        Ok(())
    }
    #[test]
    fn dsc_rejects_duplicate_extra_and_wrong_version() -> Result<()> {
        let lock = source_lock()?;
        let row = |key: &str| {
            format!(
                " {} {} {}\n",
                lock["artifacts"][key]["sha256"].as_str().unwrap(),
                lock["artifacts"][key]["bytes"],
                lock["artifacts"][key]["filename"].as_str().unwrap()
            )
        };
        let good = format!(
            "Format: 3.0 (quilt)\nSource: gdm3\nVersion: {VERSION}\nChecksums-Sha256:\n{}{}",
            row("source_orig_archive"),
            row("source_debian_archive")
        );
        assert_eq!(sha_sources(&good, VERSION)?.len(), 2);
        assert!(sha_sources(&(good.clone() + &row("source_orig_archive")), VERSION).is_err());
        assert!(sha_sources(&(good.clone() + "Checksums-Sha256:\n"), VERSION).is_err());
        assert!(sha_sources(&good, ORIGINAL_VERSION).is_err());
        Ok(())
    }
    #[test]
    fn root_regression_refuses_skips_failures_and_unbound_binary() -> Result<()> {
        let lock = source_lock()?;
        let mut report = json!({"schema":1,"source_commit":lock["source_commit"],"exit_code":0,
            "actual_root_subprocess_tests":true,"enforcing_target_gdm_runtime_qualified":false,
            "normal_debian_build_test_artifact":true,"cases_passed":3,
            "test_elf":lock["artifacts"]["root_test_executable"],"test_log":lock["artifacts"]["root_test_log"]});
        let log = "1..3\nok 1 /environment/private-write-replace-and-thread-scope\nok 2 /environment/io-failure-restores-identity\nok 3 /environment/restoration-denial-is-fatal\n";
        verify_regression(&report, log, &lock, false)?;
        assert!(
            verify_regression(
                &report,
                &(log.to_owned() + "# SKIP needs root\n"),
                &lock,
                false
            )
            .is_err()
        );
        assert!(
            verify_regression(&report, &log.replace("ok 2 ", "not ok 2 "), &lock, false).is_err()
        );
        report["test_elf"]["sha256"] = json!("0".repeat(64));
        assert!(verify_regression(&report, log, &lock, false).is_err());
        Ok(())
    }
    #[test]
    fn lifecycle_regression_requires_all_normal_artifact_cases() -> Result<()> {
        let lock = source_lock()?;
        let mut report = json!({"schema":1,"source_commit":lock["source_commit"],"exit_code":0,
            "actual_root_subprocess_tests":true,"enforcing_target_gdm_runtime_qualified":false,
            "normal_debian_build_test_artifact":true,"cases_passed":14,
            "test_elf":lock["artifacts"]["lifecycle_test_executable"],"test_log":lock["artifacts"]["lifecycle_test_log"]});
        let names = [
            "private-000-copy-refused-unchanged",
            "write-retire-exclusive-recreate",
            "foreign-owner-fails-and-restores",
            "hard-link-transfer-rejected",
            "root-alias-rejected",
            "original-gdm-data-owner",
            "denied-fsuid-restores-without-dac",
            "private-000-retirement-refused",
            "retained-handoff-refused",
            "old-writer-fd-cannot-change-new-inode",
            "concurrent-hardlink-preserves-original-owner",
            "concurrent-rename-preserves-original-owner",
            "concurrent-write-refuses-publication",
            "new-inodes-private-until-publication",
        ];
        let log = format!(
            "1..14\n{}",
            names
                .iter()
                .enumerate()
                .map(|(i, n)| format!("ok {} /dynamic-files/{n}\n", i + 1))
                .collect::<String>()
        );
        verify_regression(&report, &log, &lock, true)?;
        assert!(
            verify_regression(&report, &(log.clone() + "# SKIP needs root\n"), &lock, true)
                .is_err()
        );
        assert!(
            verify_regression(&report, &log.replace("ok 6 ", "not ok 6 "), &lock, true).is_err()
        );
        report["normal_debian_build_test_artifact"] = json!(false);
        assert!(verify_regression(&report, &log, &lock, true).is_err());
        Ok(())
    }
}
