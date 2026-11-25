//! A declared libapparmor candidate overlay in the private qualification clone.
//! This is deliberately not a package installer and never rewrites dpkg state.
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
    path::Path,
};

const MEMBER: &str = "usr/lib/x86_64-linux-gnu/libapparmor.so.1.30.7";
const PATCH: &str = "debian/patches/p4/readonly-socket-peer-lsm.patch";
const ORIGINAL_VERSION: &str = "5.0.2-0ubuntu1~26.04.1";
const CANDIDATE_VERSION: &str = "5.0.2-0ubuntu1~26.04.1+p4peer1";
const ORIGINAL_SHA: &str = "fba87c63e1c716620ed844df5d2fcee7de06cbfb0895d109f9de9a9d6f0245cd";

const LEAF: &str = "libapparmor.so.1.30.7";
const SONAME_MEMBER: &str = "usr/lib/x86_64-linux-gnu/libapparmor.so.1";
const FIXTURE_PATCH: &str = "debian/patches/p4/notify-login-test-fixture.patch";
const ORIGINAL_ARCHIVE_SHA: &str =
    "c02ff05f1831a42940d8a20194ed05128b9535db44afec13088b5aae57863327";
const SOURCE_PATCH: &[u8] =
    include_bytes!("../../../packaging/ubuntu/libapparmor/p4-readonly-socket-peer-lsm.patch");
const TEST_FIXTURE_PATCH: &[u8] =
    include_bytes!("../../../packaging/ubuntu/libapparmor/notify-login-test-fixture.patch");
const API_TEST_SOURCE: &[u8] =
    include_bytes!("../../../packaging/ubuntu/libapparmor/tests/peer-abi.c");
const KERNEL_PATCH: &[u8] =
    include_bytes!("../../../packaging/ubuntu/linux/patches/0002-readonly-socket-peer-lsm.patch");
pub const REQUIRED_KERNEL_RELEASE: &str = "6.18.64-p4ctx6181-fusectl-aafs-peer-r1";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LibapparmorCandidate {
    pub declaration: FilePin,
    pub package: FilePin,
    pub source_commit: FilePin,
    pub source_dsc: FilePin,
    pub source_debian_archive: FilePin,
    pub source_orig_archive: FilePin,
}

use crate::boot_candidate::{
    SourceMap, artifact, dpkg_status, equal_pin, read_json, safe_member, source_pin,
};

/// Read one regular member, never extract an archive namespace. The reviewed
/// source archive contains ordinary files and directories; the binary archive
/// additionally contains the one fixed SONAME alias validated below.
fn pick_regular(
    tar: &[u8],
    wanted: &str,
    mode: Option<u32>,
    allow_soname: bool,
) -> Result<Vec<u8>> {
    ensure(
        tar.len() <= 16 * 1024 * 1024 && safe_member(wanted),
        "candidate tar outside bound",
    )?;
    let mut offset = 0usize;
    let mut seen = BTreeSet::new();
    let mut selected = None;
    let mut soname_seen = false;
    loop {
        let h = tar
            .get(offset..offset + 512)
            .ok_or("truncated candidate tar header")?;
        offset += 512;
        if h.iter().all(|b| *b == 0) {
            ensure(
                tar.len() >= offset + 512
                    && tar.len() - offset <= 10752
                    && tar[offset..].iter().all(|b| *b == 0),
                "candidate tar termination differs",
            )?;
            break;
        }
        let sum: u64 = h
            .iter()
            .enumerate()
            .map(|(i, b)| {
                if (148..156).contains(&i) {
                    32
                } else {
                    u64::from(*b)
                }
            })
            .sum();
        ensure(
            crate::boot_host::octal(&h[148..156])? == sum,
            "candidate tar checksum differs",
        )?;
        let gnu = &h[257..265] == b"ustar  \0";
        let posix = &h[257..263] == b"ustar\0" && &h[263..265] == b"00";
        ensure(
            gnu || posix,
            "candidate tar must be reviewed GNU or POSIX ustar",
        )?;
        if gnu {
            ensure(
                h[345..500].iter().all(|b| *b == 0),
                "GNU sparse/extended metadata refused",
            )?;
        }
        let kind = h[156];
        ensure(
            [0, b'0', b'5'].contains(&kind) || (allow_soname && kind == b'2'),
            "candidate tar links, extensions and special files refused",
        )?;
        ensure(
            crate::boot_host::octal(&h[108..116])? == 0
                && crate::boot_host::octal(&h[116..124])? == 0,
            "candidate archive owner/link differs",
        )?;
        let link = crate::boot_host::text_field(&h[157..257])?;
        let name = crate::boot_host::text_field(&h[..100])?;
        let prefix = if gnu {
            ""
        } else {
            crate::boot_host::text_field(&h[345..500])?
        };
        let combined = if prefix.is_empty() {
            name.into()
        } else {
            format!("{prefix}/{name}")
        };
        let path = combined
            .strip_prefix("./")
            .unwrap_or(&combined)
            .trim_end_matches('/');
        ensure(
            (path.is_empty() && kind == b'5') || safe_member(path),
            "candidate archive path is unsafe",
        )?;
        ensure(
            seen.len() < 256 && seen.insert(path.to_owned()),
            "duplicate/excessive candidate members",
        )?;
        if kind == b'2' {
            ensure(
                allow_soname && path == SONAME_MEMBER && link == LEAF && !soname_seen,
                "candidate archive contains an unexpected SONAME link",
            )?;
            soname_seen = true;
        } else {
            ensure(
                link.is_empty(),
                "ordinary candidate member contains a link target",
            )?;
        }
        let size = usize::try_from(crate::boot_host::octal(&h[124..136])?)?;
        let actual_mode = u32::try_from(crate::boot_host::octal(&h[100..108])?)?;
        ensure(
            actual_mode & !0o777 == 0
                && if kind == b'2' {
                    actual_mode == 0o777 && size == 0
                } else {
                    actual_mode & 0o022 == 0 && (kind != b'5' || size == 0)
                },
            "candidate member permission/size differs",
        )?;
        let body = tar
            .get(
                offset
                    ..offset
                        .checked_add(size)
                        .ok_or("candidate member size overflow")?,
            )
            .ok_or("truncated candidate member")?;
        if path == wanted {
            ensure(
                (kind == 0 || kind == b'0') && mode.is_none_or(|m| m == actual_mode),
                "selected candidate member is not the required regular file",
            )?;
            selected = Some(body.to_vec());
        }
        offset += size;
        let padding = (512 - size % 512) % 512;
        ensure(
            tar.get(offset..offset + padding)
                .is_some_and(|p| p.iter().all(|b| *b == 0)),
            "candidate member padding differs",
        )?;
        offset += padding;
    }
    ensure(
        !allow_soname || soname_seen,
        "normal package SONAME link absent",
    )?;
    selected.ok_or_else(|| "required candidate member absent".into())
}

fn dsc_sources(text: &str) -> Result<BTreeMap<String, (u64, String)>> {
    ensure(
        text.lines()
            .filter(|l| *l == format!("Version: {CANDIDATE_VERSION}"))
            .count()
            == 1
            && text.lines().filter(|l| *l == "Source: apparmor").count() == 1,
        "candidate source identity differs",
    )?;
    let mut in_sha = false;
    let mut found = false;
    let mut result = BTreeMap::new();
    for line in text.lines() {
        if line == "Checksums-Sha256:" {
            ensure(!found, "repeated source SHA256 field")?;
            found = true;
            in_sha = true;
            continue;
        }
        if in_sha && !line.starts_with(' ') {
            in_sha = false;
        }
        if !in_sha {
            continue;
        }
        let p: Vec<_> = line.split_whitespace().collect();
        ensure(
            p.len() == 3
                && fs::valid_digest(p[0])
                && (p[2] == "apparmor_5.0.2.orig.tar.gz"
                    || p[2] == format!("apparmor_{CANDIDATE_VERSION}.debian.tar.xz")),
            "invalid source archive checksum row",
        )?;
        ensure(
            result
                .insert(p[2].into(), (p[1].parse()?, p[0].into()))
                .is_none(),
            "duplicate source archive",
        )?;
    }
    ensure(found && result.len() == 2, "source archive pair incomplete")?;
    Ok(result)
}

fn verify_sources(
    input: &LibapparmorCandidate,
    declaration: &Value,
    work: &Path,
    imports: Option<&SourceMap>,
) -> Result<Value> {
    let source = read_json(&source_pin(&input.source_commit, imports)?)?;
    let git = |v: &Value| {
        v.as_str().is_some_and(|s| {
            s.len() == 40
                && s.bytes()
                    .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        })
    };
    ensure(
        source["schema"] == "p4-native-apparmor-peer-source-commit-v1"
            && source["clean"] == true
            && git(&source["commit"])
            && git(&source["tree"])
            && source["original_source_version"] == ORIGINAL_VERSION
            && source["candidate_version"] == CANDIDATE_VERSION
            && source["patch_sha256"] == declaration["source"]["patch_sha256"]
            && source["patch_sha256"] == fs::digest(SOURCE_PATCH)
            && source["test_sha256"] == fs::digest(API_TEST_SOURCE)
            && source["test_fixture_patch_sha256"] == fs::digest(TEST_FIXTURE_PATCH)
            && source["kernel_patch_sha256"] == fs::digest(KERNEL_PATCH),
        "candidate maintained-source proof differs",
    )?;
    let packages = declaration["source_and_binary_packages"]
        .as_array()
        .ok_or("source package pins absent")?;
    for pin in [
        &input.source_dsc,
        &input.source_debian_archive,
        &input.package,
    ] {
        ensure(
            packages
                .iter()
                .filter_map(|v| artifact(v).ok())
                .filter(|v| equal_pin(v, pin))
                .count()
                == 1,
            "candidate package is not bound by its build declaration",
        )?;
    }
    let dsc = String::from_utf8(boot_files::read_pin(
        &source_pin(&input.source_dsc, imports)?,
        65536,
    )?)?;
    let sources = dsc_sources(&dsc)?;
    for pin in [&input.source_debian_archive, &input.source_orig_archive] {
        let name = pin
            .path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("invalid source archive basename")?;
        ensure(
            sources.get(name) == Some(&(pin.bytes, pin.sha256.clone())),
            "source archive not bound by .dsc",
        )?;
        ensure(
            pin.bytes <= 16 * 1024 * 1024,
            "source archive exceeds reviewed bound",
        )?;
        source_pin(pin, imports)?;
    }
    ensure(
        input.source_orig_archive.sha256 == ORIGINAL_ARCHIVE_SHA
            && input.source_orig_archive.bytes == 7_613_576,
        "candidate upstream archive is not the original admitted Ubuntu source",
    )?;
    let source_archive = work.join("source.debian.tar.xz");
    boot_files::copy_pin(
        &source_pin(&input.source_debian_archive, imports)?,
        &source_archive,
        0o400,
    )?;
    let tar = crate::boot_runtime::redirected(
        work,
        "source-xz",
        "/usr/bin/xz",
        &[
            "--decompress".into(),
            "--stdout".into(),
            source_archive.to_string_lossy().into(),
        ],
        None,
        None,
        &work.join("source.debian.tar"),
        16 * 1024 * 1024,
        30,
    )?;
    let archive = boot_files::read_pin(&tar, 16 * 1024 * 1024)?;
    let patch = pick_regular(&archive, PATCH, None, false)?;
    let fixture_patch = pick_regular(&archive, FIXTURE_PATCH, None, false)?;
    ensure(
        fs::digest(&fixture_patch) == fs::digest(TEST_FIXTURE_PATCH)
            && declaration["source"]["test_fixture_patch_sha256"] == fs::digest(&fixture_patch),
        "normal source package test fixture patch differs",
    )?;
    ensure(
        source["patch_sha256"] == fs::digest(&patch),
        "normal source package patch differs from maintained Git patch",
    )?;
    let build_pin = artifact(&declaration["normal_build"])?;
    let build = read_json(&source_pin(&build_pin, imports)?)?;
    ensure(
        build["schema"] == "p4-libapparmor-readonly-peer-build-v1"
            && build["exit_code"] == 0
            && build["candidate_version"] == CANDIDATE_VERSION
            && build["production_qualified"] == false,
        "candidate did not come from its declared successful normal Debian build",
    )?;
    let api_pin = artifact(&declaration["public_api_unit_tests"])?;
    let api = read_json(&source_pin(&api_pin, imports)?)?;
    ensure(
        api["schema"] == "p4-libapparmor-readonly-peer-public-abi-tests-v1"
            && api["test_source_sha256"] == source["test_sha256"]
            && api["kernel_runtime_qualified"] == false,
        "public API test source binding differs",
    )?;
    let library = declaration["candidate_library"]["path"]
        .as_str()
        .ok_or("test library identity absent")?;
    ensure(
        api["libraries"]
            .as_array()
            .ok_or("tested libraries absent")?
            .iter()
            .filter(|v| {
                v["path"] == library && v["sha256"] == declaration["candidate_library"]["sha256"]
            })
            .count()
            == 1,
        "API tests did not use the actual stripped package library",
    )?;
    let mut cases = BTreeSet::new();
    for test in api["tests"]
        .as_array()
        .ok_or("API tests absent")?
        .iter()
        .filter(|v| v["library"] == library)
    {
        ensure(
            test["exit_code"] == 0
                && cases.insert(test["case"].as_str().ok_or("API test name absent")?),
            "failed or repeated actual package API test",
        )?;
    }
    ensure(
        cases
            == BTreeSet::from([
                "success",
                "legacy",
                "unconfined",
                "range",
                "grow",
                "overflow",
                "eacces",
                "eperm",
                "einval",
                "eopnotsupp",
                "eintr",
                "enosys",
                "bad-size",
                "bad-version",
                "bad-provider",
                "flags",
                "reserved",
                "reserved2",
                "short-header",
                "bad-length",
                "empty",
                "oversized",
                "range-within-capacity",
                "wrong-label",
            ]),
        "actual package API test set differs",
    )?;
    Ok(json!({"source_commit":input.source_commit,"source":source,
        "dsc":input.source_dsc,"debian_archive":input.source_debian_archive,
        "orig_archive":input.source_orig_archive,"patch_member":PATCH,"patch_sha256":fs::digest(&patch),
        "test_fixture_patch_member":FIXTURE_PATCH,"test_fixture_patch_sha256":fs::digest(&fixture_patch),
        "normal_build":build_pin,"api_tests":api_pin,"package_api_cases":cases.len()}))
}

fn exports(text: &str) -> Result<BTreeSet<String>> {
    let mut found = BTreeSet::new();
    for line in text.lines() {
        let p: Vec<_> = line.split_whitespace().collect();
        if p.len() < 8
            || !p[0].ends_with(':')
            || !["GLOBAL", "WEAK"].contains(&p[4])
            || p[6] == "UND"
        {
            continue;
        }
        ensure(
            found.insert(format!("{} {} {} {}", p[3], p[4], p[5], p[7])),
            "duplicate public ELF symbol",
        )?;
    }
    ensure(
        found.len() == 90,
        "libapparmor public versioned ABI count differs",
    )?;
    Ok(found)
}

fn elf_report(path: &Path, work: &Path, name: &str) -> Result<(BTreeSet<String>, Value)> {
    let pin = boot_files::pin_file(path)?;
    let bytes = boot_files::read_pin(&pin, 4 * 1024 * 1024)?;
    ensure(
        bytes.len() >= 64 && &bytes[..6] == b"\x7fELF\x02\x01" && &bytes[16..20] == [3, 0, 62, 0],
        "candidate is not an x86_64 shared ELF",
    )?;
    let symbols = boot_files::run_logged(
        work,
        &format!("{name}-symbols"),
        "/usr/bin/readelf",
        &[
            "--dyn-syms".into(),
            "--wide".into(),
            path.to_string_lossy().into(),
        ],
        30,
    )?;
    let ex = exports(&String::from_utf8(boot_files::read_pin(
        &symbols.log,
        1024 * 1024,
    )?)?)?;
    let dynamic = boot_files::run_logged(
        work,
        &format!("{name}-dynamic"),
        "/usr/bin/readelf",
        &[
            "--dynamic".into(),
            "--wide".into(),
            path.to_string_lossy().into(),
        ],
        30,
    )?;
    let text = String::from_utf8(boot_files::read_pin(&dynamic.log, 65536)?)?;
    let mut needed = BTreeSet::new();
    let mut sonames = Vec::new();
    for line in text.lines() {
        if line.contains("(NEEDED)") || line.contains("(SONAME)") {
            let name = line
                .split_once('[')
                .and_then(|(_, s)| s.strip_suffix(']'))
                .ok_or("invalid native ELF dynamic field")?;
            if line.contains("(NEEDED)") {
                ensure(needed.insert(name.to_owned()), "duplicate ELF dependency")?;
            } else {
                sonames.push(name.to_owned());
            }
        }
        ensure(
            !line.contains("(RPATH)") && !line.contains("(RUNPATH)"),
            "candidate private loader search path refused",
        )?;
    }
    ensure(
        sonames == ["libapparmor.so.1"] && needed == BTreeSet::from(["libc.so.6".to_owned()]),
        "candidate SONAME/dependency set differs",
    )?;
    Ok((
        ex,
        json!({"library":pin,"soname":sonames[0],"needed":needed,
        "public_symbols":symbols.log,"dynamic":dynamic.log,"versioned_exports":90}),
    ))
}

/// The existing source/API admission also serves normal dpkg installations.
/// All writes are bounded evidence files in the caller's new private work area.
pub(super) fn admit_sources(
    input: &LibapparmorCandidate,
    imports: &SourceMap,
    layer: &Path,
) -> Result<Value> {
    let declaration = read_json(&source_pin(&input.declaration, Some(imports))?)?;
    ensure(
        declaration["schema"] == "p4-libapparmor-readonly-peer-candidate-v1"
            && declaration["package_name"] == "libapparmor1"
            && declaration["architecture"] == "amd64"
            && declaration["version"] == CANDIDATE_VERSION
            && declaration["member"] == MEMBER
            && equal_pin(&artifact(&declaration["package"])?, &input.package)
            && declaration["original_library"]["sha256"] == ORIGINAL_SHA
            && declaration["original_library"]["bytes"] == 89056
            && declaration["public_versioned_exports_equal"] == true
            && declaration["public_versioned_exports_count"] == 90
            && declaration["target_kernel_systemd_qualified"] == false,
        "normal AppArmor candidate declaration differs",
    )?;
    let sources = verify_sources(input, &declaration, layer, Some(imports))?;
    let package = source_pin(&input.package, Some(imports))?;
    let tar = crate::boot_runtime::redirected(
        layer,
        "candidate-data",
        "/usr/bin/dpkg-deb",
        &[
            "--fsys-tarfile".into(),
            package.path.to_string_lossy().into(),
        ],
        None,
        None,
        &layer.join("candidate-data.tar"),
        16 * 1024 * 1024,
        30,
    )?;
    let body = pick_regular(
        &boot_files::read_pin(&tar, 16 * 1024 * 1024)?,
        MEMBER,
        Some(0o644),
        true,
    )?;
    let expected = artifact(&declaration["candidate_library"])?;
    ensure(
        body.len() as u64 == expected.bytes && fs::digest(&body) == expected.sha256,
        "actual normal AppArmor library differs from its source/API candidate",
    )?;
    let library = layer.join(LEAF);
    boot_files::write_new(&library, &body, 0o400)?;
    let (_, elf) = elf_report(&library, layer, "candidate")?;
    Ok(json!({"sources":sources,"candidate_elf":elf,
        "source_receipts_rewritten":false,"root_files_modified":false}))
}

pub fn apply(
    root: &Path,
    boot: &Path,
    manifest: &Manifest,
    input: &LibapparmorCandidate,
) -> Result<Value> {
    let work = boot.parent().ok_or("candidate work parent absent")?;
    ensure(
        work.parent() == Some(Path::new("/var/lib/droidloom-qualification"))
            && root == work.join("root")
            && boot == work.join("boot"),
        "candidate overlay is only accepted inside a fresh qualification clone",
    )?;
    let owner = fs::Tree::open(&fs::absolute_string(work)?, 0)?;
    ensure(
        fs::stat(&owner.root)?.mode & 0o7777 == 0o700,
        "candidate work is not private",
    )?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let guest = format!("/{MEMBER}");
    let soname_guest = format!("/{SONAME_MEMBER}");
    let original_link = tree.identity(&soname_guest)?;
    let link_expected = manifest
        .entries
        .iter()
        .find(|e| e.path == soname_guest)
        .ok_or("original AppArmor SONAME link missing from fixture manifest")?;
    ensure(
        matches!(&link_expected.content, Content::Symlink { target } if target == LEAF)
            && rustix::fs::FileType::from_raw_mode(original_link.mode)
                == rustix::fs::FileType::Symlink
            && original_link.uid == 0
            && original_link.gid == 0
            && original_link.nlink == 1
            && original_link.mode & 0o7777 == 0o777
            && std::fs::read_link(root.join(SONAME_MEMBER))? == Path::new(LEAF),
        "candidate SONAME link is not the independent original alias",
    )?;
    let original = tree.identity(&guest)?;
    ensure(
        rustix::fs::FileType::from_raw_mode(original.mode) == rustix::fs::FileType::RegularFile
            && original.uid == 0
            && original.gid == 0
            && original.nlink == 1
            && original.mode & 0o7777 == 0o644
            && original.size == 89056,
        "candidate destination is not the known independent original library",
    )?;
    let expected = manifest
        .entries
        .iter()
        .find(|e| e.path == guest)
        .ok_or("original library missing from public fixture manifest")?;
    ensure(
        matches!(&expected.content, Content::Regular{sha256} if sha256 == ORIGINAL_SHA),
        "candidate overlay original is not the reviewed public fixture version",
    )?;
    let original_pin = boot_files::pin_file(&root.join(MEMBER))?;
    ensure(
        original_pin.sha256 == ORIGINAL_SHA,
        "original fixture library bytes differ",
    )?;
    let declaration = read_json(&input.declaration)?;
    ensure(
        declaration["schema"] == "p4-libapparmor-readonly-peer-candidate-v1"
            && declaration["package_name"] == "libapparmor1"
            && declaration["architecture"] == "amd64"
            && declaration["version"] == CANDIDATE_VERSION
            && declaration["member"] == MEMBER
            && declaration["original_library"]["sha256"] == ORIGINAL_SHA
            && declaration["original_library"]["bytes"] == 89056
            && equal_pin(&artifact(&declaration["package"])?, &input.package)
            && declaration["target_kernel_systemd_qualified"] == false
            && declaration["public_versioned_exports_equal"] == true
            && declaration["public_versioned_exports_count"] == 90,
        "candidate declaration is outside the reviewed replacement contract",
    )?;
    let layer = boot.join("libapparmor-candidate");
    boot_files::private_dir(&layer)?;
    let sources = verify_sources(input, &declaration, &layer, None)?;
    let deb = layer.join("candidate.deb");
    boot_files::copy_pin(&input.package, &deb, 0o400)?;
    for (field, want) in [
        ("Package", "libapparmor1"),
        ("Version", CANDIDATE_VERSION),
        ("Architecture", "amd64"),
    ] {
        let actual = boot_files::run_logged(
            &layer,
            &format!("deb-{}", field.to_lowercase()),
            "/usr/bin/dpkg-deb",
            &["--field".into(), deb.to_string_lossy().into(), field.into()],
            30,
        )?;
        ensure(
            String::from_utf8(boot_files::read_pin(&actual.log, 4096)?)?.trim() == want,
            "actual Debian package metadata differs",
        )?;
    }
    let tar = crate::boot_runtime::redirected(
        &layer,
        "deb-data",
        "/usr/bin/dpkg-deb",
        &["--fsys-tarfile".into(), deb.to_string_lossy().into()],
        None,
        None,
        &layer.join("data.tar"),
        16 * 1024 * 1024,
        30,
    )?;
    let bytes = pick_regular(
        &boot_files::read_pin(&tar, 16 * 1024 * 1024)?,
        MEMBER,
        Some(0o644),
        true,
    )?;
    let wanted = artifact(&declaration["candidate_library"])?;
    ensure(
        bytes.len() as u64 == wanted.bytes && fs::digest(&bytes) == wanted.sha256,
        "actual Debian library differs from tested candidate",
    )?;
    let candidate = layer.join(LEAF);
    boot_files::write_new(&candidate, &bytes, 0o644)?;
    let before = layer.join("original-libapparmor.so.1");
    boot_files::copy_pin(&original_pin, &before, 0o400)?;
    let (original_exports, original_elf) = elf_report(&before, &layer, "original")?;
    let (candidate_exports, candidate_elf) = elf_report(&candidate, &layer, "candidate")?;
    ensure(
        original_exports == candidate_exports,
        "candidate public ABI differs from original fixture library",
    )?;
    let mut dependencies = Vec::new();
    for name in ["libc.so.6"] {
        let (pin, resolution) =
            boot_files::resolve_public_file(root, &format!("/usr/lib/x86_64-linux-gnu/{name}"))?;
        dependencies.push(json!({"library":pin,"resolution":resolution}));
    }
    // This also checks the real usrmerge path. No host canonicalize() is used.
    let (alias_before, alias_resolution) =
        boot_files::resolve_public_file(root, "/lib/x86_64-linux-gnu/libapparmor.so.1")?;
    ensure(
        alias_before.sha256 == original_pin.sha256,
        "original SONAME lookup differs",
    )?;
    let status_before = dpkg_status(root)?;
    let temporary = root.join("usr/lib/x86_64-linux-gnu/.libapparmor-p4-candidate-new");
    boot_files::copy_pin(&boot_files::pin_file(&candidate)?, &temporary, 0o644)?;
    ensure(
        tree.identity(&guest)? == original && tree.identity(&soname_guest)? == original_link,
        "original fixture library changed before candidate replacement",
    )?;
    let parent = tree.dir("/usr/lib/x86_64-linux-gnu")?;
    rustix::fs::renameat(&parent, ".libapparmor-p4-candidate-new", &parent, LEAF)?;
    rustix::fs::fsync(&parent)?;
    let installed = boot_files::pin_file(&root.join(MEMBER))?;
    let id = tree.identity(&guest)?;
    let (alias_after, _) =
        boot_files::resolve_public_file(root, "/lib/x86_64-linux-gnu/libapparmor.so.1")?;
    ensure(
        installed.sha256 == wanted.sha256
            && installed.bytes == wanted.bytes
            && alias_after.sha256 == wanted.sha256
            && id.nlink == 1
            && id.uid == 0
            && id.gid == 0
            && id.mode & 0o7777 == 0o644
            && tree.identity(&soname_guest)? == original_link
            && std::fs::read_link(root.join(SONAME_MEMBER))? == Path::new(LEAF),
        "installed candidate or SONAME alias readback differs",
    )?;
    let status_after = dpkg_status(root)?;
    ensure(
        serde_json::to_vec(&status_before)? == serde_json::to_vec(&status_after)?,
        "fixture dpkg state changed",
    )?;
    let result = json!({"schema":"droidloom.fixture-libapparmor-candidate.v1","input":input,
        "sources":sources,"original":original_pin,"preserved_original":boot_files::pin_file(&before)?,
        "installed_candidate":installed,"original_elf":original_elf,"candidate_elf":candidate_elf,
        "dependencies":dependencies,"soname_resolution":alias_resolution,"original_soname_identity":original_link,
        "soname_link_preserved":true,"required_kernel_release":REQUIRED_KERNEL_RELEASE,"dpkg_status":status_after,
        "dpkg_database_updated":false,"maintainer_scripts_executed":false,"host_library_opened_for_write":false,
        "overlay_only":true,"guest_qualified":false,"production_ready":false});
    fs::write_json(
        &fs::absolute_string(&layer.join("OVERLAY.json"))?,
        &result,
        0,
    )?;
    Ok(result)
}

/// Read back the actual ELF bytes and the preserved SONAME alias from the
/// finished ext4 image. This does not execute a candidate or install a package.
pub fn verify_image(root: &Path, work: &Path, image: &Path) -> Result<Value> {
    let check = work.join("apparmor-image-readback");
    boot_files::private_dir(&check)?;
    let expected = boot_files::pin_file(&root.join(MEMBER))?;
    let extracted = check.join(LEAF);
    let dump = format!(
        "dump -p {} {}",
        crate::boot_runtime::debugfs_command_path(&format!("/{MEMBER}"))?,
        crate::boot_runtime::debugfs_command_path(&fs::absolute_string(&extracted)?)?,
    );
    let dump_result = boot_files::run_logged(
        &check,
        "library",
        "/usr/sbin/debugfs",
        &["-R".into(), dump, image.to_string_lossy().into()],
        30,
    )?;
    let actual = boot_files::pin_file(&extracted)?;
    ensure(
        actual.bytes == expected.bytes && actual.sha256 == expected.sha256,
        "actual ext4 AppArmor library bytes differ from the admitted root",
    )?;
    let link_result = boot_files::run_logged(
        &check,
        "soname",
        "/usr/sbin/debugfs",
        &[
            "-R".into(),
            format!("stat /{SONAME_MEMBER}"),
            image.to_string_lossy().into(),
        ],
        30,
    )?;
    let link_text = String::from_utf8(boot_files::read_pin(&link_result.log, 65536)?)?;
    let targets: Vec<_> = link_text
        .lines()
        .map(str::trim)
        .filter_map(|line| line.strip_prefix("Fast link dest: "))
        .collect();
    ensure(
        targets == [format!("\"{LEAF}\"")],
        "actual ext4 AppArmor SONAME alias target differs",
    )?;
    Ok(
        json!({"source":expected,"image_library":actual,"library_dump":dump_result,
        "soname_readback":link_result,"soname_target":LEAF,"all_matched":true}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(name: &str, kind: u8, body: &[u8], mode: u32, target: &str) -> Vec<u8> {
        let mut h = [0u8; 512];
        h[..name.len()].copy_from_slice(name.as_bytes());
        h[100..108].copy_from_slice(format!("{mode:07o}\0").as_bytes());
        h[108..116].copy_from_slice(b"0000000\0");
        h[116..124].copy_from_slice(b"0000000\0");
        h[124..136].copy_from_slice(format!("{:011o}\0", body.len()).as_bytes());
        h[136..148].copy_from_slice(b"00000000000\0");
        h[148..156].fill(b' ');
        h[156] = kind;
        h[157..157 + target.len()].copy_from_slice(target.as_bytes());
        h[257..265].copy_from_slice(b"ustar  \0");
        let sum: u64 = h.iter().map(|b| u64::from(*b)).sum();
        h[148..156].copy_from_slice(format!("{sum:06o}\0 ").as_bytes());
        let mut out = h.to_vec();
        out.extend_from_slice(body);
        out.resize(out.len().div_ceil(512) * 512, 0);
        out
    }
    fn archive(rows: &[Vec<u8>]) -> Vec<u8> {
        let mut out = rows.concat();
        out.resize(out.len() + 1024, 0);
        out
    }
    fn library() -> Vec<u8> {
        entry(MEMBER, b'0', b"library", 0o644, "")
    }
    fn alias(target: &str) -> Vec<u8> {
        entry(SONAME_MEMBER, b'2', b"", 0o777, target)
    }

    #[test]
    fn package_requires_one_exact_regular_library_and_original_soname() -> Result<()> {
        let tar = archive(&[library(), alias(LEAF)]);
        assert_eq!(pick_regular(&tar, MEMBER, Some(0o644), true)?, b"library");
        assert!(pick_regular(&tar, MEMBER, Some(0o644), false).is_err());
        assert!(pick_regular(&archive(&[library()]), MEMBER, Some(0o644), true).is_err());
        assert!(pick_regular(&tar, MEMBER, Some(0o755), true).is_err());
        Ok(())
    }

    #[test]
    fn candidate_archive_rejects_alias_escape_duplication_and_special_entries() {
        for target in ["/etc/shadow", "../outside", "libapparmor.so.other"] {
            assert!(
                pick_regular(&archive(&[library(), alias(target)]), MEMBER, None, true).is_err()
            );
        }
        assert!(
            pick_regular(
                &archive(&[library(), alias(LEAF), alias(LEAF)]),
                MEMBER,
                None,
                true
            )
            .is_err()
        );
        for kind in [b'1', b'3', b'x', b'L'] {
            let bad = entry(MEMBER, kind, b"library", 0o644, "");
            assert!(pick_regular(&archive(&[bad, alias(LEAF)]), MEMBER, None, true).is_err());
        }
        let wrong = entry("usr/lib/other", b'2', b"", 0o777, LEAF);
        assert!(pick_regular(&archive(&[library(), wrong]), MEMBER, None, true).is_err());
    }

    #[test]
    fn candidate_archive_checks_checksum_tail_traversal_and_selected_kind() {
        let tar = archive(&[library(), alias(LEAF)]);
        let mut damaged = tar.clone();
        damaged[0] ^= 1;
        assert!(pick_regular(&damaged, MEMBER, None, true).is_err());
        assert!(pick_regular(&tar[..tar.len() - 512], MEMBER, None, true).is_err());
        assert!(
            pick_regular(
                &archive(&[entry("../escape", b'0', b"x", 0o644, ""), alias(LEAF)]),
                MEMBER,
                None,
                true
            )
            .is_err()
        );
        assert!(pick_regular(&tar, SONAME_MEMBER, None, true).is_err());
    }

    #[test]
    fn source_archive_rejects_undeclared_links_and_checks_identity() -> Result<()> {
        let tar = archive(&[entry(PATCH, b'0', b"patch", 0o644, "")]);
        assert_eq!(pick_regular(&tar, PATCH, None, false)?, b"patch");
        let row = format!(" {} 42 apparmor_5.0.2.orig.tar.gz\n", "a".repeat(64));
        let second = format!(
            " {} 17 apparmor_{CANDIDATE_VERSION}.debian.tar.xz\n",
            "b".repeat(64)
        );
        let text = format!(
            "Source: apparmor\nVersion: {CANDIDATE_VERSION}\nChecksums-Sha256:\n{row}{second}Files:\n"
        );
        assert_eq!(dsc_sources(&text)?.len(), 2);
        assert!(dsc_sources(&text.replace("Source: apparmor", "Source: other")).is_err());
        assert!(dsc_sources(&text.replace(CANDIDATE_VERSION, "5.0.2-other")).is_err());
        assert!(dsc_sources(&text.replace(&second, &row)).is_err());
        assert!(
            dsc_sources(&text.replace("apparmor_5.0.2.orig.tar.gz", "../archive.tar.gz")).is_err()
        );
        Ok(())
    }
}
