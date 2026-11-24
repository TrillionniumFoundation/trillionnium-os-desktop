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
const MEMBER: &str = "usr/sbin/gdm3";
const PATCH: &str = "debian/patches/p4-dynamic-environment-credentials.patch";
const PATCH_NAME: &str = "p4-dynamic-environment-credentials.patch";
const ORIGINAL_VERSION: &str = "50.1-0ubuntu0.1";
const VERSION: &str = "50.1-0ubuntu0.1+p4fsuser1";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GdmCandidate {
    /// Exactly the fifteen names and content pins in the compiled source.lock.
    pub artifacts: BTreeMap<String, FilePin>,
}

fn source_lock() -> Result<Value> {
    let lock: Value = serde_json::from_slice(SOURCE_LOCK)?;
    ensure(
        lock["schema"] == "p4-gdm-fs-user-source-lock-v1"
            && lock["original_version"] == ORIGINAL_VERSION
            && lock["candidate_version"] == VERSION
            && lock["source_files"][PATCH]["sha256"] == fs::digest(SOURCE_PATCH)
            && lock["source_files"]["common/test-environment-file.c"]["sha256"]
                == fs::digest(TEST_SOURCE),
        "compiled GDM source contract differs",
    )?;
    Ok(lock)
}

fn validate_pins(input: &GdmCandidate, lock: &Value) -> Result<()> {
    let expected = lock["artifacts"]
        .as_object()
        .ok_or("GDM artifact set absent")?;
    ensure(
        expected.len() == 15
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

fn verify_tests(tests: &Value, log: &str, lock: &Value) -> Result<()> {
    ensure(
        tests["schema"] == 1
            && tests["source_commit"] == lock["source_commit"]
            && tests["exit_code"] == 0
            && tests["actual_root_subprocess_tests"] == true
            && tests["enforcing_target_gdm_runtime_qualified"] == false
            && tests["test_elf"]["bytes"] == lock["artifacts"]["root_test_executable"]["bytes"]
            && tests["test_elf"]["sha256"] == lock["artifacts"]["root_test_executable"]["sha256"]
            && tests["test_log"]["bytes"] == lock["artifacts"]["root_test_log"]["bytes"]
            && tests["test_log"]["sha256"] == lock["artifacts"]["root_test_log"]["sha256"],
        "GDM actual root regression binding differs",
    )?;
    let cases: Vec<_> = log.lines().filter(|l| l.starts_with("ok ")).collect();
    ensure(
        log.lines().filter(|l| *l == "1..3").count() == 1
            && !log.contains("not ok ")
            && !log.contains("# SKIP")
            && cases
                == [
                    "ok 1 /environment/private-write-replace-and-thread-scope",
                    "ok 2 /environment/io-failure-restores-identity",
                    "ok 3 /environment/restoration-denial-is-fatal",
                ],
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
    let updated = unpack_source(work, "updated-source", &pins["source_debian_archive"], 101)?;
    let mut keys: BTreeSet<_> = original.keys().map(String::as_str).collect();
    keys.insert(PATCH);
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
            && fs::digest(archive::regular(&updated, "debian/rules", None)?)
                == lock["debian_rules_sha256"],
        "GDM quilt patch/rules differ from maintained source",
    )?;
    let old_series =
        std::str::from_utf8(archive::regular(&original, "debian/patches/series", None)?)?;
    let series = std::str::from_utf8(archive::regular(&updated, "debian/patches/series", None)?)?;
    ensure(
        series.lines().collect::<Vec<_>>()
            == old_series.lines().chain([PATCH_NAME]).collect::<Vec<_>>(),
        "GDM quilt series did not append only the maintained patch",
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
            && build["source_commit"] == lock["source_commit"]
            && build["installed_candidate"] == false,
        "GDM candidate lacks the successful complete normal Debian build",
    )?;
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
    verify_tests(&tests, &log, lock)?;
    Ok(
        json!({"source_commit":lock["source_commit"], "source_tree":lock["source_tree"],
        "source_lock_sha256":fs::digest(SOURCE_LOCK), "normal_debian_build_exit_code":0,
        "unchanged_original_debian_rules":true,"only_quilt_patch_series_and_changelog_changed":true,
        "actual_root_tests":3,"unprivileged_meson_root_tests_skipped":3,
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
    let original_file = boot_files::checked_file(&original_pin)?;
    let status_before =
        crate::boot_candidate::dpkg_status(root)?.ok_or("normal fixture dpkg status absent")?;
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
    let status_after =
        crate::boot_candidate::dpkg_status(root)?.ok_or("fixture dpkg status disappeared")?;
    ensure(
        crate::boot_candidate::equal_pin(&status_before, &status_after),
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
            "test_elf":lock["artifacts"]["root_test_executable"],"test_log":lock["artifacts"]["root_test_log"]});
        let log = "1..3\nok 1 /environment/private-write-replace-and-thread-scope\nok 2 /environment/io-failure-restores-identity\nok 3 /environment/restoration-denial-is-fatal\n";
        verify_tests(&report, log, &lock)?;
        assert!(verify_tests(&report, &(log.to_owned() + "# SKIP needs root\n"), &lock).is_err());
        assert!(verify_tests(&report, &log.replace("ok 2 ", "not ok 2 "), &lock).is_err());
        report["test_elf"]["sha256"] = json!("0".repeat(64));
        assert!(verify_tests(&report, log, &lock).is_err());
        Ok(())
    }
}
