//! A declared libselinux candidate overlay in the private qualification clone.
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
    path::{Path, PathBuf},
};

const MEMBER: &str = "usr/lib/x86_64-linux-gnu/libselinux.so.1";
const PATCH: &str = "debian/patches/p4-native-lsm-exec-attribute.patch";
const ORIGINAL_VERSION: &str = "3.9-4build1";
const CANDIDATE_VERSION: &str = "3.9-4build1+p4lsmexec3";
const ORIGINAL_SHA: &str = "7538ee77765a27966563c0d22437a3080dcdb346ff76cc16d71a3ce3379a716a";

#[path = "boot_candidate_evidence.rs"]
mod evidence;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LibselinuxCandidate {
    pub declaration: FilePin,
    pub package: FilePin,
    pub source_commit: FilePin,
    pub source_dsc: FilePin,
    pub source_debian_archive: FilePin,
    pub source_orig_archive: FilePin,
    pub source_orig_signature: FilePin,
}

pub(super) fn artifact(value: &Value) -> Result<FilePin> {
    Ok(FilePin {
        path: PathBuf::from(value["path"].as_str().ok_or("artifact path absent")?),
        bytes: value["bytes"].as_u64().ok_or("artifact size absent")?,
        sha256: value["sha256"]
            .as_str()
            .ok_or("artifact digest absent")?
            .into(),
    })
}
pub(super) fn equal_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
pub(super) fn read_json(pin: &FilePin) -> Result<Value> {
    Ok(serde_json::from_slice(&boot_files::read_pin(
        pin,
        1024 * 1024,
    )?)?)
}
pub(super) fn safe_member(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && path.split('/').all(|p| {
            !p.is_empty()
                && p != "."
                && p != ".."
                && p.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(&b))
        })
}

/// Read one regular member, never extract an archive namespace. The reviewed
/// binary and source archives contain only ordinary files and directories.
fn pick_regular(tar: &[u8], wanted: &str, mode: Option<u32>) -> Result<Vec<u8>> {
    ensure(
        tar.len() <= 16 * 1024 * 1024 && safe_member(wanted),
        "candidate tar outside bound",
    )?;
    let mut offset = 0usize;
    let mut seen = BTreeSet::new();
    let mut selected = None;
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
            [0, b'0', b'5'].contains(&kind),
            "candidate tar links, extensions and special files refused",
        )?;
        ensure(
            crate::boot_host::octal(&h[108..116])? == 0
                && crate::boot_host::octal(&h[116..124])? == 0
                && crate::boot_host::text_field(&h[157..257])?.is_empty(),
            "candidate archive owner/link differs",
        )?;
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
        let size = usize::try_from(crate::boot_host::octal(&h[124..136])?)?;
        let actual_mode = u32::try_from(crate::boot_host::octal(&h[100..108])?)?;
        ensure(
            actual_mode & !0o777 == 0 && actual_mode & 0o022 == 0 && (kind != b'5' || size == 0),
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
    selected.ok_or_else(|| "required candidate member absent".into())
}

fn dsc_sources(text: &str) -> Result<BTreeMap<String, (u64, String)>> {
    ensure(
        text.lines()
            .filter(|l| *l == format!("Version: {CANDIDATE_VERSION}"))
            .count()
            == 1
            && text.lines().filter(|l| *l == "Source: libselinux").count() == 1,
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
            p.len() == 3 && fs::valid_digest(p[0]) && safe_member(p[2]) && !p[2].contains('/'),
            "invalid source archive checksum row",
        )?;
        ensure(
            result
                .insert(p[2].into(), (p[1].parse()?, p[0].into()))
                .is_none(),
            "duplicate source archive",
        )?;
    }
    ensure(
        found && result.len() == 3,
        "source archives and signature set incomplete",
    )?;
    Ok(result)
}

fn verify_sources(input: &LibselinuxCandidate, declaration: &Value, work: &Path) -> Result<Value> {
    let source = read_json(&input.source_commit)?;
    let git = |v: &Value| {
        v.as_str().is_some_and(|s| {
            s.len() == 40
                && s.bytes()
                    .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        })
    };
    ensure(
        source["schema"] == "p4-native-lsm-source-commit-v1"
            && source["clean"] == true
            && git(&source["commit"])
            && git(&source["tree"])
            && source["original_source_version"] == ORIGINAL_VERSION
            && source["candidate_version"] == CANDIDATE_VERSION
            && source["patch_sha256"] == declaration["source"]["patch_sha256"],
        "candidate maintained-source proof differs",
    )?;
    evidence::maintained_source(&source, declaration, input)?;
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
    let dsc = String::from_utf8(boot_files::read_pin(&input.source_dsc, 65536)?)?;
    let sources = dsc_sources(&dsc)?;
    for (pin, expected_name, limit) in [
        (
            &input.source_debian_archive,
            format!("libselinux_{CANDIDATE_VERSION}.debian.tar.xz"),
            16 * 1024 * 1024,
        ),
        (
            &input.source_orig_archive,
            "libselinux_3.9.orig.tar.gz".to_owned(),
            16 * 1024 * 1024,
        ),
        (
            &input.source_orig_signature,
            "libselinux_3.9.orig.tar.gz.asc".to_owned(),
            16 * 1024,
        ),
    ] {
        let name = pin
            .path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("invalid source archive basename")?;
        ensure(
            name == expected_name && sources.get(name) == Some(&(pin.bytes, pin.sha256.clone())),
            "exact source archive or signature is not bound by .dsc",
        )?;
        ensure(
            pin.bytes > 0 && pin.bytes <= limit,
            "source archive or signature exceeds reviewed bound",
        )?;
        boot_files::checked_file(pin)?;
    }
    let source_archive = work.join("source.debian.tar.xz");
    boot_files::copy_pin(&input.source_debian_archive, &source_archive, 0o400)?;
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
    let patch = pick_regular(&boot_files::read_pin(&tar, 16 * 1024 * 1024)?, PATCH, None)?;
    ensure(
        source["patch_sha256"] == fs::digest(&patch),
        "normal source package patch differs from maintained Git patch",
    )?;
    let build_pin = artifact(&declaration["normal_build"])?;
    let build = read_json(&build_pin)?;
    evidence::normal_build(&build, declaration)?;
    let api_pin = artifact(&declaration["public_api_unit_tests"])?;
    let api = read_json(&api_pin)?;
    let case_count = evidence::public_api(&api, &source, declaration)?;
    Ok(json!({"source_commit":input.source_commit,"source":source,
        "dsc":input.source_dsc,"debian_archive":input.source_debian_archive,
        "orig_archive":input.source_orig_archive,"orig_signature":input.source_orig_signature,
        "patch_member":PATCH,"patch_sha256":fs::digest(&patch),
        "normal_build":build_pin,"api_tests":api_pin,"package_api_cases":case_count}))
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
        found.len() == 247,
        "libselinux public versioned ABI count differs",
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
        sonames == ["libselinux.so.1"]
            && needed
                == BTreeSet::from([
                    "libpcre2-8.so.0".to_owned(),
                    "libc.so.6".to_owned(),
                    "ld-linux-x86-64.so.2".to_owned(),
                ]),
        "candidate SONAME/dependency set differs",
    )?;
    Ok((
        ex,
        json!({"library":pin,"soname":sonames[0],"needed":needed,
        "public_symbols":symbols.log,"dynamic":dynamic.log,"versioned_exports":247}),
    ))
}

pub(super) fn dpkg_status(root: &Path) -> Result<Option<FilePin>> {
    let path = root.join("var/lib/dpkg/status");
    match std::fs::symlink_metadata(&path) {
        Ok(_) => Ok(Some(boot_files::pin_file(&path)?)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e.into()),
    }
}

fn verify_declaration(input: &LibselinuxCandidate, declaration: &Value) -> Result<()> {
    ensure(
        declaration["schema"] == "p4-libselinux-native-exec-candidate-v1"
            && declaration["package_name"] == "libselinux1"
            && declaration["architecture"] == "amd64"
            && declaration["version"] == CANDIDATE_VERSION
            && declaration["member"] == MEMBER
            && declaration["original_library"]["sha256"] == ORIGINAL_SHA
            && declaration["original_library"]["bytes"] == 199120
            && equal_pin(&artifact(&declaration["package"])?, &input.package)
            && declaration["target_kernel_systemd_qualified"] == false
            && declaration["public_versioned_exports_equal"] == true
            && declaration["public_versioned_exports_count"] == 247
            && declaration["tested_attributes"] == json!(["exec", "keycreate", "fscreate"]),
        "candidate declaration is outside the reviewed replacement contract",
    )?;
    Ok(())
}

fn stage_debian_library(
    input: &LibselinuxCandidate,
    declaration: &Value,
    layer: &Path,
) -> Result<FilePin> {
    let deb = layer.join("candidate.deb");
    boot_files::copy_pin(&input.package, &deb, 0o400)?;
    for (field, want) in [
        ("Package", "libselinux1"),
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
    )?;
    let wanted = artifact(&declaration["candidate_library"])?;
    ensure(
        bytes.len() as u64 == wanted.bytes && fs::digest(&bytes) == wanted.sha256,
        "actual Debian library differs from tested candidate",
    )?;
    let candidate = layer.join("libselinux.so.1");
    boot_files::write_new(&candidate, &bytes, 0o644)?;
    boot_files::pin_file(&candidate)
}

pub fn apply(
    root: &Path,
    boot: &Path,
    manifest: &Manifest,
    input: &LibselinuxCandidate,
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
    let original = tree.identity(&guest)?;
    ensure(
        rustix::fs::FileType::from_raw_mode(original.mode) == rustix::fs::FileType::RegularFile
            && original.uid == 0
            && original.gid == 0
            && original.nlink == 1
            && original.mode & 0o7777 == 0o644
            && original.size == 199120,
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
    verify_declaration(input, &declaration)?;
    let layer = boot.join("libselinux-candidate");
    boot_files::private_dir(&layer)?;
    let sources = verify_sources(input, &declaration, &layer)?;
    let candidate = stage_debian_library(input, &declaration, &layer)?.path;
    let wanted = artifact(&declaration["candidate_library"])?;
    let before = layer.join("original-libselinux.so.1");
    boot_files::copy_pin(&original_pin, &before, 0o400)?;
    let (original_exports, original_elf) = elf_report(&before, &layer, "original")?;
    let (candidate_exports, candidate_elf) = elf_report(&candidate, &layer, "candidate")?;
    ensure(
        original_exports == candidate_exports,
        "candidate public ABI differs from original fixture library",
    )?;
    let mut dependencies = Vec::new();
    for name in ["libpcre2-8.so.0", "libc.so.6", "ld-linux-x86-64.so.2"] {
        let (pin, resolution) =
            boot_files::resolve_public_file(root, &format!("/usr/lib/x86_64-linux-gnu/{name}"))?;
        dependencies.push(json!({"library":pin,"resolution":resolution}));
    }
    // This also checks the real usrmerge path. No host canonicalize() is used.
    let (alias_before, alias_resolution) =
        boot_files::resolve_public_file(root, "/lib/x86_64-linux-gnu/libselinux.so.1")?;
    ensure(
        alias_before.sha256 == original_pin.sha256,
        "original SONAME lookup differs",
    )?;
    let status_before = dpkg_status(root)?;
    let temporary = root.join("usr/lib/x86_64-linux-gnu/.libselinux-p4-candidate-new");
    boot_files::copy_pin(&boot_files::pin_file(&candidate)?, &temporary, 0o644)?;
    ensure(
        tree.identity(&guest)? == original,
        "original fixture library changed before candidate replacement",
    )?;
    let parent = tree.dir("/usr/lib/x86_64-linux-gnu")?;
    rustix::fs::renameat(
        &parent,
        ".libselinux-p4-candidate-new",
        &parent,
        "libselinux.so.1",
    )?;
    rustix::fs::fsync(&parent)?;
    let installed = boot_files::pin_file(&root.join(MEMBER))?;
    let id = tree.identity(&guest)?;
    let (alias_after, _) =
        boot_files::resolve_public_file(root, "/lib/x86_64-linux-gnu/libselinux.so.1")?;
    ensure(
        installed.sha256 == wanted.sha256
            && installed.bytes == wanted.bytes
            && alias_after.sha256 == wanted.sha256
            && id.nlink == 1
            && id.uid == 0
            && id.gid == 0
            && id.mode & 0o7777 == 0o644,
        "installed candidate or SONAME alias readback differs",
    )?;
    let status_after = dpkg_status(root)?;
    ensure(
        serde_json::to_vec(&status_before)? == serde_json::to_vec(&status_after)?,
        "fixture dpkg state changed",
    )?;
    let result = json!({"schema":"droidloom.fixture-libselinux-candidate.v1","input":input,
        "sources":sources,"original":original_pin,"preserved_original":boot_files::pin_file(&before)?,
        "installed_candidate":installed,"original_elf":original_elf,"candidate_elf":candidate_elf,
        "dependencies":dependencies,"soname_resolution":alias_resolution,"dpkg_status":status_after,
        "dpkg_database_updated":false,"maintainer_scripts_executed":false,"host_library_opened_for_write":false,
        "overlay_only":true,"guest_qualified":false,"production_ready":false});
    fs::write_json(
        &fs::absolute_string(&layer.join("OVERLAY.json"))?,
        &result,
        0,
    )?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn archive(name: &str, kind: u8, bytes: &[u8], mode: u32) -> Vec<u8> {
        let mut h = [0u8; 512];
        h[..name.len()].copy_from_slice(name.as_bytes());
        h[100..108].copy_from_slice(format!("{mode:07o}\0").as_bytes());
        h[108..116].copy_from_slice(b"0000000\0");
        h[116..124].copy_from_slice(b"0000000\0");
        h[124..136].copy_from_slice(format!("{:011o}\0", bytes.len()).as_bytes());
        h[136..148].copy_from_slice(b"00000000000\0");
        h[148..156].fill(b' ');
        h[156] = kind;
        h[257..265].copy_from_slice(b"ustar  \0");
        let sum: u64 = h.iter().map(|b| u64::from(*b)).sum();
        h[148..156].copy_from_slice(format!("{sum:06o}\0 ").as_bytes());
        let mut out = h.to_vec();
        out.extend_from_slice(bytes);
        out.resize(out.len().div_ceil(512) * 512 + 1024, 0);
        out
    }

    #[test]
    fn actual_gnu_member_shape_selects_only_exact_regular_path() -> Result<()> {
        let good = archive(&format!("./{MEMBER}"), b'0', b"library", 0o644);
        assert_eq!(pick_regular(&good, MEMBER, Some(0o644))?, b"library");
        assert!(pick_regular(&good, "usr/lib/other", Some(0o644)).is_err());
        assert!(pick_regular(&good, MEMBER, Some(0o755)).is_err());
        Ok(())
    }

    #[test]
    fn candidate_tar_rejects_corruption_aliases_traversal_duplicate_and_missing_tail() {
        let good = archive(&format!("./{MEMBER}"), b'0', b"library", 0o644);
        let mut damaged = good.clone();
        damaged[0] ^= 1;
        assert!(pick_regular(&damaged, MEMBER, Some(0o644)).is_err());
        for kind in [b'1', b'2', b'x', b'3'] {
            assert!(
                pick_regular(
                    &archive(MEMBER, kind, b"library", 0o644),
                    MEMBER,
                    Some(0o644)
                )
                .is_err()
            );
        }
        assert!(pick_regular(&archive("../escape", b'0', b"x", 0o644), MEMBER, None).is_err());
        let mut repeated = good[..good.len() - 1024].to_vec();
        repeated.extend_from_slice(&good);
        assert!(pick_regular(&repeated, MEMBER, Some(0o644)).is_err());
        assert!(pick_regular(&good[..good.len() - 512], MEMBER, Some(0o644)).is_err());
    }

    #[test]
    fn source_checksum_identity_and_duplicate_rows_are_closed() -> Result<()> {
        let row = format!(" {} 42 libselinux_3.9.orig.tar.gz\n", "a".repeat(64));
        let second = format!(
            " {} 17 libselinux_{CANDIDATE_VERSION}.debian.tar.xz\n",
            "b".repeat(64)
        );
        let signature = format!(" {} 833 libselinux_3.9.orig.tar.gz.asc\n", "c".repeat(64));
        let text = format!(
            "Source: libselinux\nVersion: {CANDIDATE_VERSION}\nChecksums-Sha256:\n{row}{signature}{second}Files:\n"
        );
        assert_eq!(dsc_sources(&text)?.len(), 3);
        assert!(dsc_sources(&text.replace(&signature, "")).is_err());
        assert!(dsc_sources(&text.replace(CANDIDATE_VERSION, "3.9-other")).is_err());
        assert!(dsc_sources(&text.replace(&second, &row)).is_err());
        Ok(())
    }
    #[test]
    #[ignore = "requires the explicitly pinned original exec3 Debian materials on pocket4"]
    fn actual_exec3_normal_package_evidence_and_negative_gates() -> Result<()> {
        ensure(
            rustix::process::geteuid().as_raw() == 0,
            "actual candidate proof requires root",
        )?;
        let path = PathBuf::from(std::env::var("DROIDLOOM_EXEC3_INPUTS")?);
        ensure(
            path.starts_with("/var/lib/droidloom-qualification")
                && path.file_name().and_then(|n| n.to_str()) == Some("INPUTS.json"),
            "actual candidate proof plan path differs",
        )?;
        let pin = boot_files::pin_file(&path)?;
        ensure(
            pin.bytes < 16384 && pin.sha256 == std::env::var("DROIDLOOM_EXEC3_INPUTS_SHA256")?,
            "actual candidate proof plan pin differs",
        )?;
        let held = boot_files::checked_file(&pin)?;
        let identity = fs::stat(&held)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.mode & 0o7777 == 0o400,
            "actual candidate proof plan is not protected",
        )?;
        let input: LibselinuxCandidate =
            serde_json::from_slice(&boot_files::read_pin(&pin, 16384)?)?;
        let layer = path
            .parent()
            .ok_or("proof plan parent absent")?
            .join("source-proof");
        boot_files::private_dir(&layer)?;
        let declaration = read_json(&input.declaration)?;
        verify_declaration(&input, &declaration)?;
        let sources = verify_sources(&input, &declaration, &layer)?;
        let library = stage_debian_library(&input, &declaration, &layer)?;
        let original =
            boot_files::pin_file(Path::new("/usr/lib/x86_64-linux-gnu/libselinux.so.1"))?;
        ensure(
            original.sha256 == ORIGINAL_SHA && original.bytes == 199120,
            "actual read-only original library differs",
        )?;
        let original_copy = layer.join("original-libselinux.so.1");
        boot_files::copy_pin(&original, &original_copy, 0o400)?;
        let (old_exports, old_elf) = elf_report(&original_copy, &layer, "original")?;
        let (new_exports, new_elf) = elf_report(&library.path, &layer, "candidate")?;
        ensure(
            old_exports == new_exports,
            "actual package versioned ABI differs",
        )?;
        let source = read_json(&input.source_commit)?;
        let api_pin = artifact(&declaration["public_api_unit_tests"])?;
        let api = read_json(&api_pin)?;
        for invalid in [
            {
                let mut x = api.clone();
                x["tests"][0]["exit"] = json!(1);
                x
            },
            {
                let mut x = api.clone();
                x["tests"].as_array_mut().unwrap().pop();
                x
            },
            {
                let mut x = api.clone();
                x["tests"][1] = x["tests"][0].clone();
                x
            },
            {
                let mut x = api.clone();
                x["tested_library"]["sha256"] = json!("0".repeat(64));
                x
            },
            {
                let mut x = api.clone();
                x["test_sha256"] = json!("0".repeat(64));
                x
            },
            {
                let mut x = api.clone();
                x["tests"][57]["case"] = json!("other-attribute");
                x
            },
            {
                let mut x = api.clone();
                x["exports_count"] = json!(246);
                x
            },
        ] {
            assert!(evidence::public_api(&invalid, &source, &declaration).is_err());
        }
        let build_pin = artifact(&declaration["normal_build"])?;
        let build = read_json(&build_pin)?;
        for invalid in [
            {
                let mut x = build.clone();
                x["success"] = json!(false);
                x
            },
            {
                let mut x = build.clone();
                x["commands"][4]["argv"][0] = json!("cc");
                x
            },
            {
                let mut x = build.clone();
                x["library"]["sha256"] = json!("0".repeat(64));
                x
            },
            {
                let mut x = build.clone();
                x["schema"] = json!("p4-libselinux-debian-normal-build-v1");
                x
            },
        ] {
            assert!(evidence::normal_build(&invalid, &declaration).is_err());
        }
        let result = json!({"schema":"droidloom.exec3-actual-source-and-package-admission.v1",
            "input":pin,"sources":sources,"candidate_library":library,"original_library":original,
            "original_elf":old_elf,"candidate_elf":new_elf,"actual_package_api_cases":86,
            "negative_gate_cases":11,"host_library_opened_for_write":false,
            "guest_qualified":false,"production_qualified":false});
        fs::write_json(
            &fs::absolute_string(&layer.join("ADMISSION.json"))?,
            &result,
            0,
        )?;
        println!("{}", serde_json::to_string(&result)?);
        Ok(())
    }
}
