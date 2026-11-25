//! Read-only admission of a normal systemd Debian build and its installed source.
//! Installation belongs to the isolated normal dpkg producer. This command never
//! extracts archives into a root, runs maintainer scripts, or changes package state.
use crate::{
    Result,
    boot_files::{self, FilePin},
    boot_packages::{self, Member, Payload},
    ensure, fs,
    model::{Content, Manifest},
    paths,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

#[path = "boot_systemd_dependencies.rs"]
pub(super) mod dependencies;
use dependencies::{Fields, control, field};

const SOURCE_LOCK: &[u8] = include_bytes!("../../../packaging/ubuntu/systemd/source.lock.json");
const PATCH: &[u8] =
    include_bytes!("../../../packaging/ubuntu/systemd/p4-native-generator-tmpfs.patch");
const PATCH_PATH: &str = "/debian/patches/p4-native-generator-tmpfs.patch";
const PATCH_NAME: &str = "p4-native-generator-tmpfs.patch";
const ORIGINAL: &str = "259.9-0ubuntu0.1";
const CANDIDATE: &str = "259.9-0ubuntu0.1+p4gentmp1";
const FAMILY: [&str; 10] = [
    "libnss-systemd",
    "libpam-systemd",
    "libsystemd-shared",
    "libsystemd0",
    "libudev1",
    "systemd",
    "systemd-resolved",
    "systemd-sysv",
    "systemd-timesyncd",
    "udev",
];
const MAX_TAR: u64 = 512 * 1024 * 1024;
// Exact po/LINGUAS in the pinned systemd_259.9.orig.tar.gz (154 bytes,
// SHA256 0b6470cb64747cb5f138483ef349bf8620707476209d23a762ddc5491e1379d0).
const LOCALES: &str = "be be@latin bg ca cs da de el es et eu fi fr gl he hi hr hu ia id it ja ka kab ko lt nl pa pl pt pt_BR ro ru si sk sl sr sv tr uk zh_CN zh_TW kn ar km kw";

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct InstalledSource {
    /// A completed, private normal dpkg root. No host root or public fixture without a DB.
    pub(super) root: PathBuf,
    /// When supplied, also verify the existing capture manifest of this root.
    /// Its absence leaves capture_manifest_verified=false in the receipt.
    #[serde(default)]
    pub(super) manifest: Option<FilePin>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema: String,
    work_directory: PathBuf,
    /// Keys are exact artifact basenames. Include both source archive sets, all
    /// actual .changes/.buildinfo outputs, and the ten original package archives.
    artifacts: BTreeMap<String, FilePin>,
    original_status: FilePin,
    normal_build: FilePin,
    #[serde(default)]
    installed_source: Option<InstalledSource>,
}

fn basename(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 192
        && !name.starts_with('.')
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b".+_~-".contains(&b))
}

fn source_lock() -> Result<Value> {
    let lock: Value = serde_json::from_slice(SOURCE_LOCK)?;
    ensure(
        lock["schema"] == "droidloom.native-systemd-generator-tmp-source.v1"
            && lock["original_source_version"] == ORIGINAL
            && lock["candidate_source_version"] == CANDIDATE
            && lock["patch"]["sha256"] == fs::digest(PATCH)
            && lock["patch"]["bytes"].as_u64() == Some(PATCH.len() as u64),
        "compiled systemd source/patch contract differs",
    )?;
    Ok(lock)
}

fn armored_control(text: &str) -> Result<Fields> {
    let text = if text.starts_with("-----BEGIN PGP SIGNED MESSAGE-----\n") {
        let (_, body) = text
            .split_once("\n\n")
            .ok_or("armored source header incomplete")?;
        body.split_once("-----BEGIN PGP SIGNATURE-----")
            .ok_or("armored source signature absent")?
            .0
    } else {
        text
    };
    let rows = control(text)?;
    ensure(
        rows.len() == 1,
        "expected exactly one Debian source/output stanza",
    )?;
    Ok(rows.into_iter().next().ok_or("source stanza absent")?)
}

fn checksums(fields: &Fields) -> Result<BTreeMap<String, (u64, String)>> {
    let mut out = BTreeMap::new();
    for row in fields
        .get("Checksums-Sha256")
        .ok_or("missing SHA256 output list")?
        .lines()
        .filter(|l| !l.trim().is_empty())
    {
        let terms: Vec<_> = row.split_whitespace().collect();
        ensure(
            terms.len() == 3 && fs::valid_digest(terms[0]) && basename(terms[2]),
            "invalid SHA256 output row",
        )?;
        let bytes: u64 = terms[1].parse()?;
        ensure(
            bytes > 0
                && bytes <= MAX_TAR
                && out
                    .insert(terms[2].into(), (bytes, terms[0].into()))
                    .is_none(),
            "duplicate or excessive SHA256 output",
        )?;
    }
    ensure(
        !out.is_empty() && out.len() <= 256,
        "output checksum list outside bound",
    )?;
    Ok(out)
}

fn artifact<'a>(pins: &'a BTreeMap<String, FilePin>, name: &str) -> Result<&'a FilePin> {
    pins.get(name)
        .ok_or_else(|| format!("systemd artifact absent: {name}").into())
}

fn artifact_control(pins: &BTreeMap<String, FilePin>, name: &str) -> Result<Fields> {
    armored_control(std::str::from_utf8(&boot_files::read_pin(
        artifact(pins, name)?,
        1024 * 1024,
    )?)?)
}

fn verify_rows(
    rows: &BTreeMap<String, (u64, String)>,
    pins: &BTreeMap<String, FilePin>,
) -> Result<()> {
    for (name, (bytes, sha)) in rows {
        let pin = artifact(pins, name)?;
        ensure(
            pin.bytes == *bytes && pin.sha256 == *sha,
            "actual Debian output not bound by its SHA256 list",
        )?;
    }
    Ok(())
}

fn source_members(work: &Path, stem: &str, pin: &FilePin) -> Result<BTreeMap<String, Payload>> {
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
        32 * 1024 * 1024,
        30,
    )?;
    let parsed = boot_packages::parse_tar_with(
        &boot_files::read_pin(&tar, 32 * 1024 * 1024)?,
        "systemd-source",
        &pin.sha256,
        |m| {
            ensure(
                (m.path == "/debian" || m.path.starts_with("/debian/")) && m.uid == 0 && m.gid == 0,
                "source member outside the Debian packaging directory",
            )
        },
    )?;
    Ok(parsed
        .into_iter()
        .map(|p| (p.member.path.clone(), p))
        .collect())
}

fn source_file<'a>(members: &'a BTreeMap<String, Payload>, path: &str) -> Result<&'a [u8]> {
    let payload = members.get(path).ok_or("normal source member absent")?;
    ensure(
        matches!(payload.member.content, Content::Regular { .. }),
        "normal source member is not regular",
    )?;
    Ok(&payload.data)
}

fn verify_environment(environment: &str) -> Result<()> {
    let mut fields = BTreeMap::new();
    for row in environment.lines().filter(|l| !l.trim().is_empty()) {
        let (name, value) = row
            .trim()
            .split_once('=')
            .ok_or("invalid build environment row")?;
        let value = value
            .strip_prefix('"')
            .and_then(|v| v.strip_suffix('"'))
            .ok_or("unquoted build environment value")?;
        ensure(
            fields.insert(name, value).is_none(),
            "repeated build environment variable",
        )?;
    }
    ensure(
        matches!(
            fields.get("DEB_BUILD_OPTIONS").copied(),
            Some("parallel=1" | "parallel=2" | "parallel=4")
        ),
        "normal build contains additional stage-changing build options",
    )?;
    // Ubuntu's Dpkg::Vendor::Ubuntu update-buildprofiles hook enables precisely
    // these distribution profiles. Neither disables the normal package tests.
    ensure(
        fields.get("DEB_BUILD_PROFILES").copied() == Some("derivative.ubuntu noudeb"),
        "normal build profiles differ from the Ubuntu vendor defaults",
    )
}

fn verify_sources(work: &Path, pins: &BTreeMap<String, FilePin>, lock: &Value) -> Result<Value> {
    let original = lock["normal_source_archives"]
        .as_object()
        .ok_or("original source archive contract absent")?;
    ensure(
        original.len() == 3,
        "original normal source archive count differs",
    )?;
    for (name, wanted) in original {
        let actual = artifact(pins, name)?;
        ensure(
            Some(actual.bytes) == wanted["bytes"].as_u64() && actual.sha256 == wanted["sha256"],
            "normal Ubuntu source archive changed",
        )?;
    }
    for version in [ORIGINAL, CANDIDATE] {
        let dsc = artifact_control(pins, &format!("systemd_{version}.dsc"))?;
        ensure(
            field(&dsc, "Source")? == "systemd"
                && field(&dsc, "Version")? == version
                && field(&dsc, "Format")? == "3.0 (quilt)",
            "systemd source package identity differs",
        )?;
        let rows = checksums(&dsc)?;
        let names = BTreeSet::from([
            "systemd_259.9.orig.tar.gz".to_owned(),
            format!("systemd_{version}.debian.tar.xz"),
        ]);
        ensure(
            rows.keys().cloned().collect::<BTreeSet<_>>() == names,
            "systemd dsc source pair differs",
        )?;
        verify_rows(&rows, pins)?;
    }
    let original = source_members(
        work,
        "original-source",
        artifact(pins, &format!("systemd_{ORIGINAL}.debian.tar.xz"))?,
    )?;
    let candidate = source_members(
        work,
        "candidate-source",
        artifact(pins, &format!("systemd_{CANDIDATE}.debian.tar.xz"))?,
    )?;
    let mut wanted: BTreeSet<_> = original.keys().cloned().collect();
    wanted.insert(PATCH_PATH.into());
    ensure(
        candidate.keys().cloned().collect::<BTreeSet<_>>() == wanted,
        "unreviewed Debian source member changes",
    )?;
    let mut restricted_modes = 0;
    for (path, before) in &original {
        let after = &candidate[path];
        let equal_mode = before.member.mode == after.member.mode;
        let tightened = after.member.mode == before.member.mode & !0o077;
        ensure(
            equal_mode || tightened,
            "Debian source archive permissions changed beyond the producer's private umask",
        )?;
        restricted_modes += usize::from(!equal_mode);
        ensure(
            before.member.uid == after.member.uid && before.member.gid == after.member.gid,
            "Debian source member ownership changed",
        )?;
        if ["/debian/changelog", "/debian/patches/series"].contains(&path.as_str()) {
            continue;
        }
        ensure(
            before.member.content == after.member.content && before.data == after.data,
            &format!("unrelated Debian source/rules changed: {path}"),
        )?;
    }
    ensure(
        source_file(&candidate, PATCH_PATH)? == PATCH,
        "normal source lacks the maintained exact quilt patch",
    )?;
    let old_series = std::str::from_utf8(source_file(&original, "/debian/patches/series")?)?;
    let new_series = std::str::from_utf8(source_file(&candidate, "/debian/patches/series")?)?;
    ensure(
        new_series.lines().collect::<Vec<_>>()
            == old_series.lines().chain([PATCH_NAME]).collect::<Vec<_>>(),
        "normal quilt series did not append only the maintained patch",
    )?;
    let old_changelog = std::str::from_utf8(source_file(&original, "/debian/changelog")?)?;
    let new_changelog = std::str::from_utf8(source_file(&candidate, "/debian/changelog")?)?;
    ensure(
        new_changelog.starts_with(&format!("systemd ({CANDIDATE})"))
            && new_changelog.ends_with(old_changelog),
        "normal changelog did not preserve the original history",
    )?;
    let changes = artifact_control(pins, &format!("systemd_{CANDIDATE}_amd64.changes"))?;
    let buildinfo = artifact_control(pins, &format!("systemd_{CANDIDATE}_amd64.buildinfo"))?;
    for fields in [&changes, &buildinfo] {
        ensure(
            field(fields, "Source")? == "systemd" && field(fields, "Version")? == CANDIDATE,
            "normal build output source identity differs",
        )?;
        verify_rows(&checksums(fields)?, pins)?;
    }
    ensure(
        field(&buildinfo, "Build-Architecture")? == "amd64",
        "normal build architecture differs",
    )?;
    let environment = buildinfo
        .get("Environment")
        .ok_or("normal build environment absent")?;
    verify_environment(environment)?;
    let changed = checksums(&changes)?;
    let built = checksums(&buildinfo)?;
    for package in FAMILY {
        let name = format!("{package}_{CANDIDATE}_amd64.deb");
        ensure(
            changed.get(&name) == built.get(&name) && changed.contains_key(&name),
            "selected package is absent from the normal changes/buildinfo pair",
        )?;
    }
    Ok(
        json!({"source_lock_sha256":fs::digest(SOURCE_LOCK),"patch_sha256":fs::digest(PATCH),
        "debian_rules_sha256":fs::digest(source_file(&candidate,"/debian/rules")?),
        "source_members_verified":candidate.len(),"source_archive_modes_restricted_only":restricted_modes,
        "normal_changes":artifact(pins,&format!("systemd_{CANDIDATE}_amd64.changes"))?,
        "normal_buildinfo":artifact(pins,&format!("systemd_{CANDIDATE}_amd64.buildinfo"))?,
        "source_signature_reverified":false}),
    )
}

fn verify_build(pin: &FilePin, pins: &BTreeMap<String, FilePin>, lock: &Value) -> Result<Value> {
    let record: Value = serde_json::from_slice(&boot_files::read_pin(pin, 4 * 1024 * 1024)?)?;
    ensure(
        record["schema"] == "droidloom.systemd-normal-build.v1"
            && record["exit_code"] == 0
            && record["source_lock_sha256"] == fs::digest(SOURCE_LOCK),
        "successful normal producer/source binding absent",
    )?;
    let argv = record["argv"]
        .as_array()
        .ok_or("normal build argv absent")?;
    ensure(
        argv.first()
            .and_then(Value::as_str)
            .is_some_and(|s| s == "/usr/bin/dpkg-buildpackage" || s == "dpkg-buildpackage")
            && argv.len() >= 3
            && argv.len() <= 5,
        "normal producer is not full dpkg-buildpackage",
    )?;
    let mut flags = BTreeSet::new();
    for flag in &argv[1..] {
        let flag = flag.as_str().ok_or("invalid normal producer argv")?;
        ensure(
            ["-us", "-uc", "-F", "-j1", "-j2", "-j4"].contains(&flag) && flags.insert(flag),
            "normal producer contains an unsupported/duplicate option",
        )?;
    }
    ensure(
        flags.contains("-us")
            && flags.contains("-uc")
            && flags.iter().filter(|f| f.starts_with("-j")).count() == 1,
        "normal producer options incomplete",
    )?;
    let outputs = record["outputs"]
        .as_object()
        .ok_or("normal producer output hashes absent")?;
    let changes = artifact_control(pins, &format!("systemd_{CANDIDATE}_amd64.changes"))?;
    for (name, (bytes, sha)) in checksums(&changes)? {
        ensure(
            outputs[&name]["bytes"].as_u64() == Some(bytes) && outputs[&name]["sha256"] == sha,
            "normal producer exit record does not bind the complete output set",
        )?;
    }
    let roundtrip = record["source_roundtrip"]
        .as_object()
        .ok_or("normal source roundtrip absent")?;
    let expected = lock["patched_files"]
        .as_object()
        .ok_or("maintained source file hashes absent")?;
    ensure(
        roundtrip.len() == expected.len(),
        "source roundtrip file set differs",
    )?;
    for (path, wanted) in expected {
        ensure(
            roundtrip[path]["bytes"] == wanted["bytes"]
                && roundtrip[path]["sha256"] == wanted["sha256"],
            "normal source package did not roundtrip the maintained patched bytes",
        )?;
    }
    Ok(record)
}

fn source_name(fields: &Fields) -> Result<&str> {
    Ok(fields
        .get("Source")
        .map(String::as_str)
        .unwrap_or(field(fields, "Package")?)
        .split_whitespace()
        .next()
        .ok_or("empty package source")?)
}

fn family(status: &[Fields], version: &str) -> Result<()> {
    let mut actual = BTreeSet::new();
    for package in status {
        if source_name(package)? != "systemd"
            || package
                .get("Status")
                .is_none_or(|s| s != "install ok installed")
        {
            continue;
        }
        ensure(
            field(package, "Architecture")? == "amd64" && field(package, "Version")? == version,
            "installed systemd family version/architecture is mixed",
        )?;
        ensure(
            actual.insert(field(package, "Package")?),
            "duplicate systemd family member",
        )?;
    }
    ensure(
        actual == BTreeSet::from(FAMILY),
        "installed systemd source family is incomplete or contains unselected packages",
    )
}

fn payload_allowed(m: &Member) -> Result<()> {
    ensure(
        m.uid == 0
            && m.gid == 0
            && m.path.bytes().all(|b| !b.is_ascii_control())
            && (m.path == "/usr"
                || m.path.starts_with("/usr/")
                || m.path == "/etc"
                || m.path.starts_with("/etc/")
                || m.path == "/var"
                || m.path.starts_with("/var/")),
        "systemd payload outside original public package roots",
    )?;
    if let Content::Symlink { target } = &m.content {
        ensure(
            m.mode == 0o777 && !target.is_empty() && !target.bytes().any(|b| b.is_ascii_control()),
            "systemd package symlink differs",
        )?;
        // Readback never follows it. The original/candidate comparison below also
        // requires an unchanged exact symlink and hardlink graph.
    } else {
        ensure(
            m.mode & !0o777 == 0 && m.mode & 0o022 == 0,
            "unreviewed systemd privilege/writable mode",
        )?;
    }
    Ok(())
}

fn package(
    work: &Path,
    pins: &BTreeMap<String, FilePin>,
    name: &str,
    version: &str,
) -> Result<(Fields, BTreeMap<String, Payload>)> {
    let pin = artifact(pins, &format!("{name}_{version}_amd64.deb"))?;
    let area = work.join(format!(
        "{name}-{}",
        if version == ORIGINAL {
            "original"
        } else {
            "candidate"
        }
    ));
    boot_files::private_dir(&area)?;
    let metadata = boot_files::run_logged(
        &area,
        "control",
        "/usr/bin/dpkg-deb",
        &["--field".into(), pin.path.to_string_lossy().into()],
        30,
    )?;
    let mut fields = control(std::str::from_utf8(&boot_files::read_pin(
        &metadata.log,
        128 * 1024,
    )?)?)?;
    ensure(fields.len() == 1, "binary package control count differs")?;
    let fields = fields.remove(0);
    ensure(
        field(&fields, "Package")? == name
            && field(&fields, "Version")? == version
            && field(&fields, "Architecture")? == "amd64"
            && source_name(&fields)? == "systemd",
        "binary package actual source/version/architecture differs",
    )?;
    let tar = crate::boot_runtime::redirected(
        &area,
        "data",
        "/usr/bin/dpkg-deb",
        &["--fsys-tarfile".into(), pin.path.to_string_lossy().into()],
        None,
        None,
        &area.join("data.tar"),
        MAX_TAR,
        60,
    )?;
    let members = boot_packages::parse_tar_with_long_names(
        &boot_files::read_pin(&tar, MAX_TAR)?,
        name,
        &pin.sha256,
        payload_allowed,
    )?;
    Ok((
        fields,
        members
            .into_iter()
            .map(|p| (p.member.path.clone(), p))
            .collect(),
    ))
}

fn same_layout(before: &Member, after: &Member) -> bool {
    before.path == after.path
        && before.mode == after.mode
        && before.uid == after.uid
        && before.gid == after.gid
        && match (&before.content, &after.content) {
            (Content::Regular { .. }, Content::Regular { .. }) => true,
            (Content::Hardlink { target: a, .. }, Content::Hardlink { target: b, .. }) => a == b,
            (a, b) => a == b,
        }
}

fn same_payload(a: &Member, b: &Member) -> bool {
    same_layout(a, b) && a.content == b.content && a.bytes == b.bytes
}

fn documentation_expansion(before: &Member, after: &Member) -> Option<String> {
    let prefix = format!("/usr/share/doc/{}/", before.package);
    let leaf = before.path.strip_prefix(&prefix)?;
    if !["NEWS.Debian.gz", "changelog.Debian.gz"].contains(&leaf)
        || ![
            "libpam-systemd",
            "systemd",
            "systemd-resolved",
            "systemd-sysv",
            "systemd-timesyncd",
            "udev",
        ]
        .contains(&before.package.as_str())
        || before.path != after.path
        || before.mode != 0o777
        || after.mode != 0o644
        || before.uid != 0
        || before.gid != 0
        || after.uid != 0
        || after.gid != 0
        || !matches!(after.content, Content::Regular { .. })
    {
        return None;
    }
    let Content::Symlink { target } = &before.content else {
        return None;
    };
    (target == &format!("../libsystemd-shared/{leaf}"))
        .then(|| format!("/usr/share/doc/libsystemd-shared/{leaf}"))
}

fn translation_paths() -> BTreeSet<String> {
    let mut out = BTreeSet::from(["/usr/share/locale".into()]);
    for locale in LOCALES.split_whitespace() {
        for tail in ["", "/LC_MESSAGES", "/LC_MESSAGES/systemd.mo"] {
            out.insert(format!("/usr/share/locale/{locale}{tail}"));
        }
    }
    out
}

fn verify_translation(payload: &Payload) -> Result<()> {
    let m = &payload.member;
    ensure(
        m.package == "systemd" && m.uid == 0 && m.gid == 0 && translation_paths().contains(&m.path),
        "translation addition is outside the original upstream language set",
    )?;
    if m.path.ends_with("/systemd.mo") {
        ensure(
            m.mode == 0o644
                && matches!(m.content, Content::Regular { .. })
                && (28..=1024 * 1024).contains(&payload.data.len()),
            "translation is not a bounded read-only catalog",
        )?;
        let data = &payload.data;
        let little = data[..4] == [0xde, 0x12, 0x04, 0x95];
        ensure(
            little || data[..4] == [0x95, 0x04, 0x12, 0xde],
            "translation lacks GNU message-catalog magic",
        )?;
        let integer = |offset: usize| -> u32 {
            let bytes: [u8; 4] = data[offset..offset + 4]
                .try_into()
                .expect("checked catalog header");
            if little {
                u32::from_le_bytes(bytes)
            } else {
                u32::from_be_bytes(bytes)
            }
        };
        let count = integer(8) as usize;
        ensure(
            integer(4) == 0 && (1..=8192).contains(&count),
            "unsupported message catalog revision/count",
        )?;
        for start in [integer(12) as usize, integer(16) as usize] {
            ensure(
                start
                    .checked_add(count * 8)
                    .is_some_and(|end| end <= data.len()),
                "catalog string table escapes payload",
            )?;
            for entry in 0..count {
                let length = integer(start + entry * 8) as usize;
                let offset = integer(start + entry * 8 + 4) as usize;
                ensure(
                    offset
                        .checked_add(length)
                        .is_some_and(|end| end < data.len() && data[end] == 0),
                    "catalog string escapes payload or lacks termination",
                )?;
            }
        }
    } else {
        ensure(
            m.mode == 0o755 && m.content == Content::Directory,
            "translation ancestor is not an ordinary directory",
        )?;
    }
    Ok(())
}

fn verify_expansions(
    work: &Path,
    members: &BTreeMap<String, Member>,
    expansions: &BTreeMap<String, String>,
    documents: &BTreeMap<String, Vec<u8>>,
) -> Result<()> {
    for (index, (path, target)) in expansions.iter().enumerate() {
        let value = members.get(path).ok_or("expanded documentation absent")?;
        let shared = members
            .get(target)
            .ok_or("shared documentation target absent")?;
        ensure(
            matches!(value.content, Content::Regular { .. })
                && matches!(shared.content, Content::Regular { .. })
                && shared.mode == 0o644
                && shared.uid == 0
                && shared.gid == 0,
            "expanded documentation is not bound to a normal shared-package document",
        )?;
        if value.bytes == shared.bytes && value.content == shared.content {
            continue;
        }
        ensure(
            path.ends_with("/changelog.Debian.gz"),
            "expanded NEWS differs from the normal shared-package target",
        )?;
        let mut texts = Vec::new();
        for (which, member) in [("shared", shared), ("expanded", value)] {
            let bytes = documents
                .get(&member.path)
                .ok_or("compressed document payload absent")?;
            ensure(
                member.bytes == bytes.len() as u64
                    && member.content
                        == (Content::Regular {
                            sha256: fs::digest(bytes),
                        }),
                "compressed document bytes changed",
            )?;
            let area = work.join(format!("document-{index:02}-{which}"));
            boot_files::private_dir(&area)?;
            let compressed = area.join("changelog.gz");
            boot_files::write_new(&compressed, bytes, 0o400)?;
            let decoded = crate::boot_runtime::redirected(
                &area,
                "decode",
                "/usr/bin/gzip",
                &[
                    "--decompress".into(),
                    "--stdout".into(),
                    compressed.to_string_lossy().into(),
                ],
                None,
                None,
                &area.join("changelog.txt"),
                4 * 1024 * 1024,
                30,
            )?;
            texts.push(boot_files::read_pin(&decoded, 4 * 1024 * 1024)?);
        }
        verify_changelog_footer(&texts[0], &texts[1], &value.package)?;
    }
    Ok(())
}

fn verify_changelog_footer(shared: &[u8], expanded: &[u8], package: &str) -> Result<()> {
    let shared = std::str::from_utf8(shared)?;
    let prefix = shared
        .strip_suffix("# To read the complete changelog use `apt changelog libsystemd-shared`.\n")
        .ok_or("normal Debhelper changelog footer absent")?;
    let expected =
        format!("{prefix}# To read the complete changelog use `apt changelog {package}`.\n");
    ensure(
        expanded == expected.as_bytes(),
        "expanded changelog changed more than its exact per-package Debhelper footer",
    )
}

fn capture_member(manifest: &Manifest, m: &Member) -> Result<()> {
    let entry = manifest
        .entries
        .iter()
        .find(|e| e.path == m.path)
        .ok_or_else(|| format!("captured package payload absent: {}", m.path))?;
    ensure(
        entry.source.mode & 0o7777 == m.mode
            && entry.source.uid == m.uid
            && entry.source.gid == m.gid
            && fs::content_type_matches(&entry.source, &m.content)
            && entry.xattrs.is_empty(),
        "captured systemd payload metadata differs",
    )?;
    match (&entry.content, &m.content) {
        (
            Content::Regular { sha256: a } | Content::Hardlink { sha256: a, .. },
            Content::Regular { sha256: b } | Content::Hardlink { sha256: b, .. },
        ) => ensure(
            a == b && entry.source.size == m.bytes,
            "captured systemd payload bytes differ",
        )?,
        (a, b) => ensure(a == b, "captured systemd alias/type differs")?,
    }
    Ok(())
}

pub(super) fn installed(
    source: &InstalledSource,
    members: &BTreeMap<String, Member>,
    controls: &[Fields],
) -> Result<Value> {
    let parent = source
        .root
        .parent()
        .ok_or("installed source has no private parent")?;
    ensure(
        parent.parent() == Some(Path::new("/var/lib/droidloom-qualification"))
            && source.root == parent.join("root"),
        "installed candidate source must be a private qualification root",
    )?;
    let private = fs::Tree::open(&fs::absolute_string(parent)?, 0)?;
    ensure(
        fs::stat(&private.root)?.mode & 0o7777 == 0o700,
        "installed candidate parent is not private",
    )?;
    let tree = fs::Tree::open(&fs::absolute_string(&source.root)?, 0)?;
    let manifest: Option<Manifest> = source
        .manifest
        .as_ref()
        .map(|pin| -> Result<Manifest> {
            Ok(serde_json::from_slice(&boot_files::read_pin(
                pin,
                128 * 1024 * 1024,
            )?)?)
        })
        .transpose()?;
    if let Some(manifest) = &manifest {
        ensure(
            manifest.schema == crate::model::MANIFEST_SCHEMA
                && manifest.source_root == fs::absolute_string(&source.root)?
                && manifest.source_root_identity == fs::stat(&tree.root)?
                && !manifest.guest_qualified,
            "capture is not of this installed private source",
        )?;
    }
    let status = boot_files::pin_file(&source.root.join("var/lib/dpkg/status"))?;
    let status_fields = control(std::str::from_utf8(&boot_files::read_pin(
        &status,
        32 * 1024 * 1024,
    )?)?)?;
    family(&status_fields, CANDIDATE)?;
    let dependencies = dependencies::closure(&status_fields, controls)?;
    let mut captured = 0;
    let mut source_only = Vec::new();
    let mut directory_transforms = Vec::new();
    let mut installed_payload = Vec::new();
    for m in members.values() {
        let mut expected = m.clone();
        if ["/etc/credstore", "/etc/credstore.encrypted"].contains(&m.path.as_str()) {
            ensure(
                m.content == Content::Directory && m.mode == 0o755 && m.uid == 0 && m.gid == 0,
                "credential-directory archive metadata differs",
            )?;
            let rules = members
                .get("/usr/lib/tmpfiles.d/credstore.conf")
                .ok_or("normal credential tmpfiles rule absent")?;
            boot_packages::readback(&tree, rules)?;
            let Content::Regular { sha256 } = &rules.content else {
                return Err("credential tmpfiles rule is not regular".into());
            };
            let pin = FilePin {
                path: source.root.join(rules.path.trim_start_matches('/')),
                bytes: rules.bytes,
                sha256: sha256.clone(),
            };
            let bytes = boot_files::read_pin(&pin, 65536)?;
            let rule = format!("d {} 0700 root root", m.path);
            ensure(
                std::str::from_utf8(&bytes)?
                    .lines()
                    .filter(|l| l.trim() == rule)
                    .count()
                    == 1,
                "normal credential directory permission is not bound to the actual package rule",
            )?;
            expected.mode = 0o700;
            directory_transforms.push(
                json!({"path":m.path,"archive_mode":m.mode,"installed_mode":expected.mode,
                "uid":0,"gid":0,"normal_package_rule":pin,"rule":rule}),
            );
        }
        boot_packages::readback(&tree, &expected)?;
        installed_payload.push(expected.clone());
        if m.path == "/usr" || m.path.starts_with("/usr/") || paths::public_config(&m.path) {
            if let Some(manifest) = &manifest {
                capture_member(manifest, &expected)?;
                captured += 1;
            }
        } else {
            source_only.push(m.path.clone());
        }
    }
    ensure(
        boot_files::pin_file(&status.path)?.sha256 == status.sha256,
        "installed source package state changed during readback",
    )?;
    fs::assert_root_namespace(&fs::absolute_string(&source.root)?, &tree)?;
    Ok(
        json!({"root":source.root,"root_identity":fs::stat(&tree.root)?,"manifest":source.manifest,"dpkg_status":status,
        "complete_installed_payload":installed_payload,
        "installed_packages":FAMILY,"candidate_package_payload_members_verified":members.len(),
        "capture_manifest_verified":manifest.is_some(),
        "captured_public_members_verified":manifest.as_ref().map(|_|captured),"source_only_configuration_or_state_members":source_only,
        "normal_tmpfiles_directory_transforms_verified":directory_transforms,
        "actual_dependencies_verified":dependencies,"dpkg_database_candidate_versions_verified":true,
        "guest_qualified":false,"production_ready":false}),
    )
}

fn admit_plan(plan: Plan, input: &FilePin, source_admission: Option<&FilePin>) -> Result<Value> {
    ensure(
        plan.schema == "droidloom.systemd-candidate-admission-plan.v1"
            && (25..=256).contains(&plan.artifacts.len()),
        "unsupported systemd admission plan",
    )?;
    let lock = source_lock()?;
    admission_work(&plan.work_directory)?;
    let input_copy = plan.work_directory.join("SOURCE-INPUTS.json");
    boot_files::copy_pin(input, &input_copy, 0o400)?;
    let source_input = boot_files::pin_file(&input_copy)?;
    let receipt_input = if source_admission.is_some() {
        input.clone()
    } else {
        source_input.clone()
    };
    fs::write_json(
        &fs::absolute_string(&plan.work_directory.join("INPUTS.json"))?,
        &plan,
        0,
    )?;
    let area = plan.work_directory.join("artifacts");
    boot_files::private_dir(&area)?;
    let mut pins = BTreeMap::new();
    let mut total = 0u64;
    for (name, pin) in &plan.artifacts {
        ensure(
            basename(name)
                && pin.path.file_name().and_then(|v| v.to_str()) == Some(name)
                && pin.bytes > 0
                && pin.bytes <= MAX_TAR,
            "invalid normal systemd artifact pin",
        )?;
        total = total
            .checked_add(pin.bytes)
            .ok_or("artifact size overflow")?;
        ensure(
            total <= 8 * 1024 * 1024 * 1024,
            "normal systemd artifact set exceeds bound",
        )?;
        let dest = area.join(name);
        boot_files::copy_pin(pin, &dest, 0o400)?;
        pins.insert(name.clone(), boot_files::pin_file(&dest)?);
    }
    let original_status = area.join("original-status");
    boot_files::copy_pin(&plan.original_status, &original_status, 0o400)?;
    let status = control(std::str::from_utf8(&boot_files::read_pin(
        &boot_files::pin_file(&original_status)?,
        32 * 1024 * 1024,
    )?)?)?;
    family(&status, ORIGINAL)?;
    let normal = area.join("normal-build.json");
    boot_files::copy_pin(&plan.normal_build, &normal, 0o400)?;
    let sources = verify_sources(&plan.work_directory, &pins, &lock)?;
    let build = verify_build(&boot_files::pin_file(&normal)?, &pins, &lock)?;
    let mut members = BTreeMap::<String, Member>::new();
    let mut controls = Vec::new();
    let mut reports = Vec::new();
    let mut expansions = BTreeMap::new();
    let mut documents = BTreeMap::new();
    for name in FAMILY {
        let (_, before) = package(&plan.work_directory, &pins, name, ORIGINAL)?;
        let (metadata, after) = package(&plan.work_directory, &pins, name, CANDIDATE)?;
        let old_paths: BTreeSet<_> = before.keys().cloned().collect();
        let new_paths: BTreeSet<_> = after.keys().cloned().collect();
        ensure(
            old_paths.is_subset(&new_paths),
            "candidate package removed an original payload path",
        )?;
        let additions: BTreeSet<_> = new_paths.difference(&old_paths).cloned().collect();
        ensure(
            additions
                == if name == "systemd" {
                    translation_paths()
                } else {
                    BTreeSet::new()
                },
            "candidate package added a path outside its original upstream translations",
        )?;
        let mut changed = Vec::new();
        for (path, payload) in &after {
            if path.starts_with("/usr/share/doc/")
                && path.ends_with("/changelog.Debian.gz")
                && matches!(payload.member.content, Content::Regular { .. })
            {
                documents.insert(path.clone(), payload.data.clone());
            }
            if let Some(original) = before.get(path) {
                if !same_layout(&original.member, &payload.member) {
                    let target = documentation_expansion(&original.member, &payload.member)
                        .ok_or_else(|| {
                            format!("candidate changed payload ownership/mode/alias graph: {path}")
                        })?;
                    expansions.insert(path.clone(), target);
                }
                if !same_payload(&original.member, &payload.member) {
                    changed.push(path.clone());
                }
            } else {
                verify_translation(payload)?;
                changed.push(path.clone());
            }
            if let Some(old) = members.get(path) {
                ensure(
                    same_payload(old, &payload.member),
                    "systemd family has conflicting cross-package payloads",
                )?;
            } else {
                members.insert(path.clone(), payload.member.clone());
            }
        }
        reports.push(json!({"package":name,"version":CANDIDATE,"architecture":"amd64","members_verified":after.len(),
            "changed_payload_members":changed,"upstream_translation_additions":additions,"control":metadata}));
        controls.push(metadata);
    }
    verify_expansions(&plan.work_directory, &members, &expansions, &documents)?;
    let dependency = dependencies::closure(&status, &controls)?;
    let source = plan
        .installed_source
        .as_ref()
        .map(|s| installed(s, &members, &controls))
        .transpose()?;
    let receipt = json!({"schema":"droidloom.systemd-candidate-admitted.v1","input_sha256":source_input.sha256,"input":receipt_input,"preserved_input":source_input,"source_admission":source_admission,
        "source":sources,"normal_build":build,"artifacts":pins,"original_status":plan.original_status,
        "packages":reports,"documentation_expansions_verified":expansions,"actual_dependencies_verified":dependency,"complete_selected_payload":members.values().collect::<Vec<_>>(),
        "installed_source":source,"source_files_modified_by_admission":false,"maintainer_scripts_executed_by_admission":false,
        "package_installation_performed_by_admission":false,"guest_qualified":false,"production_ready":false});
    let path = plan.work_directory.join("SYSTEMD-CANDIDATE-VERIFIED.json");
    let sha = fs::write_json(&fs::absolute_string(&path)?, &receipt, 0)?;
    let _ = sha;
    Ok(receipt)
}

/// Create only a new root-owned qualification evidence area. Installed-source
/// capture may place each verifier one level below its own private admission area.
pub(super) fn admission_work(work: &Path) -> Result<()> {
    let base = Path::new("/var/lib/droidloom-qualification");
    let parent = work.parent().ok_or("admission work parent absent")?;
    if parent == base {
        crate::boot::create_work(work)
    } else {
        ensure(
            parent.parent() == Some(base),
            "admission work is outside qualification custody",
        )?;
        let tree = fs::Tree::open(&fs::absolute_string(parent)?, 0)?;
        ensure(
            fs::stat(&tree.root)?.mode & 0o7777 == 0o700,
            "admission work parent is not private",
        )?;
        boot_files::private_dir(work)
    }
}

pub(super) fn verify_installed_systemd(
    root: &Path,
    admission_receipt: &FilePin,
    work: &Path,
) -> Result<Value> {
    let receipt: Value =
        serde_json::from_slice(&boot_files::read_pin(admission_receipt, 16 * 1024 * 1024)?)?;
    ensure(
        receipt["schema"] == "droidloom.systemd-candidate-admitted.v1",
        "systemd admission receipt schema differs",
    )?;
    let input: FilePin = serde_json::from_value(receipt["input"].clone())?;
    ensure(
        receipt["input_sha256"] == input.sha256,
        "systemd admission input binding differs",
    )?;
    let mut plan: Plan = serde_json::from_slice(&boot_files::read_pin(&input, 1024 * 1024)?)?;
    plan.work_directory = work.into();
    plan.installed_source = Some(InstalledSource {
        root: root.into(),
        manifest: None,
    });
    // Every source/build pin and every package is decoded again against the
    // current root. Previous pass flags and old dpkg metadata are not consumed.
    admit_plan(plan, &input, Some(admission_receipt))
}

pub fn run(config: &Path, expected: &str) -> Result<()> {
    let plan: Plan = fs::read_json(&fs::absolute_string(config)?, expected)?;
    let input = boot_files::pin_file(config)?;
    ensure(
        input.sha256 == expected,
        "systemd admission plan changed before snapshot",
    )?;
    let path = plan.work_directory.join("SYSTEMD-CANDIDATE-VERIFIED.json");
    let installed = plan.installed_source.is_some();
    admit_plan(plan, &input, None)?;
    let pin = boot_files::pin_file(&path)?;
    println!(
        "{}",
        json!({"receipt":path,"sha256":pin.sha256,"installed_source_verified":installed,
        "guest_qualified":false,"production_ready":false})
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn documentation_expansion_requires_the_exact_shared_document_bytes() -> Result<()> {
        let mut before = Member {
            path: "/usr/share/doc/libpam-systemd/NEWS.Debian.gz".into(),
            package: "libpam-systemd".into(),
            archive_sha256: "a".repeat(64),
            mode: 0o777,
            uid: 0,
            gid: 0,
            bytes: 0,
            content: Content::Symlink {
                target: "../libsystemd-shared/NEWS.Debian.gz".into(),
            },
        };
        let mut after = before.clone();
        after.mode = 0o644;
        after.bytes = 3;
        after.content = Content::Regular {
            sha256: fs::digest(b"abc"),
        };
        let target = documentation_expansion(&before, &after)
            .ok_or("valid documentation expansion refused")?;
        let mut shared = after.clone();
        shared.path = target.clone();
        shared.package = "libsystemd-shared".into();
        let expansions = BTreeMap::from([(after.path.clone(), target.clone())]);
        let mut members = BTreeMap::from([
            (after.path.clone(), after.clone()),
            (target.clone(), shared),
        ]);
        let work = tempfile::tempdir()?;
        verify_expansions(work.path(), &members, &expansions, &BTreeMap::new())?;
        members.get_mut(&target).unwrap().content = Content::Regular {
            sha256: fs::digest(b"bad"),
        };
        assert!(verify_expansions(work.path(), &members, &expansions, &BTreeMap::new()).is_err());
        before.content = Content::Symlink {
            target: "../../../etc/shadow".into(),
        };
        assert!(documentation_expansion(&before, &after).is_none());
        before.path = "/usr/lib/systemd/systemd".into();
        after.path = before.path.clone();
        assert!(documentation_expansion(&before, &after).is_none());
        Ok(())
    }
    #[test]
    fn changelog_expansion_only_changes_the_exact_final_binary_package_hint() -> Result<()> {
        let shared=b"normal source history\n# To read the complete changelog use `apt changelog libsystemd-shared`.\n";
        let expanded=b"normal source history\n# To read the complete changelog use `apt changelog systemd`.\n";
        verify_changelog_footer(shared, expanded, "systemd")?;
        assert!(verify_changelog_footer(shared, expanded, "udev").is_err());
        assert!(
            verify_changelog_footer(
                shared,
                b"changed history\n# To read the complete changelog use `apt changelog systemd`.\n",
                "systemd"
            )
            .is_err()
        );
        Ok(())
    }
    #[test]
    fn added_translations_are_fixed_data_paths_with_bounded_catalog_tables() -> Result<()> {
        assert_eq!(translation_paths().len(), 139);
        let mut data = Vec::new();
        for n in [0x950412deu32, 0, 1, 28, 36, 0, 0, 0, 44, 0, 45] {
            data.extend(n.to_le_bytes());
        }
        data.extend([0, 0]);
        let member = Member {
            path: "/usr/share/locale/zh_CN/LC_MESSAGES/systemd.mo".into(),
            package: "systemd".into(),
            archive_sha256: "a".repeat(64),
            mode: 0o644,
            uid: 0,
            gid: 0,
            bytes: data.len() as u64,
            content: Content::Regular {
                sha256: fs::digest(&data),
            },
        };
        let mut payload = Payload { member, data };
        verify_translation(&payload)?;
        payload.data[32..36].copy_from_slice(&u32::MAX.to_le_bytes());
        assert!(verify_translation(&payload).is_err());
        payload.member.path = "/usr/share/locale/zh_CN/LC_MESSAGES/helper.so".into();
        assert!(verify_translation(&payload).is_err());
        Ok(())
    }
    #[test]
    fn normal_ubuntu_profiles_do_not_admit_disabled_tests_or_docs() -> Result<()> {
        verify_environment(
            "\n DEB_BUILD_OPTIONS=\"parallel=4\"\n DEB_BUILD_PROFILES=\"derivative.ubuntu noudeb\"\n",
        )?;
        for profile in [
            "derivative.ubuntu noudeb nocheck",
            "nodoc",
            "noinsttest",
            "stage1",
            "",
        ] {
            assert!(
                verify_environment(&format!(
                    "DEB_BUILD_OPTIONS=\"parallel=4\"\nDEB_BUILD_PROFILES=\"{profile}\"\n"
                ))
                .is_err()
            );
        }
        assert!(verify_environment("DEB_BUILD_OPTIONS=\"parallel=4 nocheck\"\nDEB_BUILD_PROFILES=\"derivative.ubuntu noudeb\"\n").is_err());
        Ok(())
    }
    #[test]
    fn checksums_reject_duplicates_paths_and_missing_actual_outputs() -> Result<()> {
        let sha = "a".repeat(64);
        let valid = armored_control(&format!(
            "Source: systemd\nChecksums-Sha256:\n {sha} 2 example.deb\n"
        ))?;
        assert_eq!(checksums(&valid)?.len(), 1);
        assert!(verify_rows(&checksums(&valid)?, &BTreeMap::new()).is_err());
        for rows in [
            format!(" {sha} 2 ../example.deb\n"),
            format!(" {sha} 2 example.deb\n {sha} 2 example.deb\n"),
        ] {
            assert!(checksums(&armored_control(&format!("Checksums-Sha256:\n{rows}"))?).is_err());
        }
        Ok(())
    }
    #[test]
    fn exact_family_does_not_accept_pid1_only_or_mixed_versions() -> Result<()> {
        let text = FAMILY.iter().map(|name|format!("Package: {name}\nSource: systemd\nVersion: {ORIGINAL}\nArchitecture: amd64\nStatus: install ok installed\n\n")).collect::<String>();
        let mut packages = control(&text)?;
        family(&packages, ORIGINAL)?;
        assert!(family(&packages[..1], ORIGINAL).is_err());
        packages[0].insert("Version".into(), CANDIDATE.into());
        assert!(family(&packages, ORIGINAL).is_err());
        Ok(())
    }
    #[test]
    fn payload_change_cannot_add_privilege_or_change_aliases() {
        let before = Member {
            path: "/usr/lib/libsystemd-shared-259.so".into(),
            package: "libsystemd-shared".into(),
            archive_sha256: "a".repeat(64),
            mode: 0o644,
            uid: 0,
            gid: 0,
            bytes: 3,
            content: Content::Regular {
                sha256: "b".repeat(64),
            },
        };
        let mut after = before.clone();
        after.content = Content::Regular {
            sha256: "c".repeat(64),
        };
        assert!(same_layout(&before, &after));
        assert!(!same_payload(&before, &after));
        after.mode = 0o4644;
        assert!(!same_layout(&before, &after));
        assert!(payload_allowed(&after).is_err());
        after = before.clone();
        after.content = Content::Symlink {
            target: "/etc/shadow".into(),
        };
        assert!(!same_layout(&before, &after));
    }
}
