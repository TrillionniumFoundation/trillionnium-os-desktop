//! Read-only normal Debian admission for the selected libselinux, AppArmor and
//! GDM source families. Complete package bodies and current dpkg state are read
//! back; the legacy single-ELF overlays are never applied to a complete root.
use crate::{
    Result,
    boot_candidate::{self, SourceMap},
    boot_files::{self, FilePin},
    boot_packages::{self, Member},
    boot_systemd_candidate,
    boot_systemd_candidate::dependencies::{self, Fields, control, field},
    ensure, fs,
    model::Content,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

const MAX_TAR: u64 = 32 * 1024 * 1024;
const SCHEMA: &str = "droidloom.native-family-candidate-admission.v1";

struct Package {
    name: &'static str,
    source: &'static str,
    original: &'static str,
    version: &'static str,
    bytes: u64,
    sha: &'static str,
}
// These are the actual normal .changes/.buildinfo outputs, independently read
// from the existing producers. Extra development/debug packages are not installed.
const PACKAGES: [Package; 6] = [
    Package {
        name: "libselinux1",
        source: "libselinux",
        original: "3.9-4build1",
        version: "3.9-4build1+p4lsmexec4",
        bytes: 91320,
        sha: "187f07a0ad4576f7adfb2915da7054233107449b59a6e317d2d5cfb2c148002f",
    },
    Package {
        name: "apparmor",
        source: "apparmor",
        original: "5.0.2-0ubuntu1~26.04.1",
        version: "5.0.2-0ubuntu1~26.04.1+p4peer1",
        bytes: 502050,
        sha: "a586b91b09dfafc0ac0ea1c3511acb147f986bc332865c99eb0e3ba4cd97c31b",
    },
    Package {
        name: "libapparmor1",
        source: "apparmor",
        original: "5.0.2-0ubuntu1~26.04.1",
        version: "5.0.2-0ubuntu1~26.04.1+p4peer1",
        bytes: 51804,
        sha: "ccc039b1512c0b87975428b0c1d91fc2f74a028a844b79767341ec13d781528e",
    },
    Package {
        name: "gdm3",
        source: "gdm3",
        original: "50.1-0ubuntu0.1",
        version: "50.1-0ubuntu0.1+p4fsuser3",
        bytes: 873260,
        sha: "9e9cb4637fd55d2fc0d62835518da20abc2600418d2bd60441457ba61c52ee88",
    },
    Package {
        name: "gir1.2-gdm-1.0",
        source: "gdm3",
        original: "50.1-0ubuntu0.1",
        version: "50.1-0ubuntu0.1+p4fsuser3",
        bytes: 21786,
        sha: "c3a237b92b7ed401e68aea6bca7e8b680847b03b4393a04ab011a38d97fb9a52",
    },
    Package {
        name: "libgdm1",
        source: "gdm3",
        original: "50.1-0ubuntu0.1",
        version: "50.1-0ubuntu0.1+p4fsuser3",
        bytes: 61070,
        sha: "68693aaffd421765bd7dc6ceab2007fb2e8deab921552cbf870695eea909a160",
    },
];
const METADATA: [(&str, u64, &str); 6] = [
    (
        "libselinux_3.9-4build1+p4lsmexec4_amd64.changes",
        3678,
        "3caf0bf79ace153f683d2d5e1a0da7138ef03339859235179f7925d1918ee391",
    ),
    (
        "libselinux_3.9-4build1+p4lsmexec4_amd64.buildinfo",
        8432,
        "02464db3e40202a559d28947bfbfcd03d966e59f0dc4d3943641bdac5b35b861",
    ),
    (
        "apparmor_5.0.2-0ubuntu1~26.04.1+p4peer1_amd64.changes",
        8303,
        "fd1cb0b9958cb1ac0e79afe14ec800a005204e9299722bd3f613740a2d08278b",
    ),
    (
        "apparmor_5.0.2-0ubuntu1~26.04.1+p4peer1_amd64.buildinfo",
        16314,
        "5cc3b7d114a7ec6f209cf3bb345a1a1c77e1e44ed327e3e3133214fbdfb6cb74",
    ),
    (
        "gdm3_50.1-0ubuntu0.1+p4fsuser3_amd64.changes",
        4105,
        "5c4320cd62efc39fad518da439b6e373c280dca9143b019a79dbc8345c8385be",
    ),
    (
        "gdm3_50.1-0ubuntu0.1+p4fsuser3_amd64.buildinfo",
        21459,
        "4ebbeb70cd41d53e65fbb8a08bd9e17c0e2fdacb287a7b2e0f28079fd420d97e",
    ),
];

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema: String,
    work_directory: PathBuf,
    original_status: FilePin,
    /// Keys retain the original producer's absolute paths. Values are verified
    /// independent imported copies. No original receipt is edited or re-signed.
    artifacts: SourceMap,
    libselinux: crate::boot_candidate::LibselinuxCandidate,
    libapparmor: crate::boot_apparmor_candidate::LibapparmorCandidate,
    gdm: crate::boot_gdm_candidate::GdmCandidate,
    #[serde(default)]
    installed_root: Option<PathBuf>,
}

fn basename(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 192
        && !name.starts_with('.')
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._+~-".contains(&b))
}

fn named<'a>(pins: &'a SourceMap, name: &str) -> Result<&'a FilePin> {
    ensure(basename(name), "invalid native artifact basename")?;
    let matches: Vec<_> = pins
        .values()
        .filter(|p| p.path.file_name().and_then(|v| v.to_str()) == Some(name))
        .collect();
    let first = *matches
        .first()
        .ok_or_else(|| format!("normal native artifact absent: {name}"))?;
    ensure(
        matches
            .iter()
            .all(|p| p.bytes == first.bytes && p.sha256 == first.sha256),
        "ambiguous native artifact contents",
    )?;
    Ok(first)
}

fn source_name(fields: &Fields) -> Result<&str> {
    let name = fields
        .get("Source")
        .map(String::as_str)
        .unwrap_or(field(fields, "Package")?);
    name.split_whitespace()
        .next()
        .ok_or_else(|| "package source absent".into())
}

fn families(fields: &[Fields], installed: bool) -> Result<()> {
    let mut names = BTreeSet::new();
    for f in fields {
        if !["libselinux", "apparmor", "gdm3"].contains(&source_name(f)?) {
            continue;
        }
        let name = field(f, "Package")?;
        let package = PACKAGES
            .iter()
            .find(|p| p.name == name)
            .ok_or("unselected native source-family member")?;
        ensure(
            field(f, "Status")? == "install ok installed"
                && field(f, "Architecture")? == "amd64"
                && field(f, "Version")?
                    == if installed {
                        package.version
                    } else {
                        package.original
                    }
                && source_name(f)? == package.source
                && names.insert(name),
            "native source family has mixed versions, architecture or configuration state",
        )?;
    }
    ensure(
        names == PACKAGES.iter().map(|p| p.name).collect(),
        "normal native source family is incomplete",
    )
}

fn one_control(bytes: &[u8]) -> Result<Fields> {
    let mut values = control(std::str::from_utf8(bytes)?)?;
    ensure(
        values.len() == 1,
        "normal native control has multiple stanzas",
    )?;
    Ok(values.remove(0))
}

fn checked_metadata(pins: &SourceMap) -> Result<Value> {
    let mut reports = Vec::new();
    for (name, bytes, sha) in METADATA {
        let pin = named(pins, name)?;
        ensure(
            pin.bytes == bytes && pin.sha256 == sha,
            "native normal build metadata differs from actual admitted producer",
        )?;
        let fields = one_control(&boot_files::read_pin(pin, 65536)?)?;
        let package = PACKAGES
            .iter()
            .find(|p| name.starts_with(&format!("{}_", p.source)))
            .ok_or("native build source absent")?;
        ensure(
            field(&fields, "Source")? == package.source
                && field(&fields, "Version")? == package.version,
            "native normal build source/version differs",
        )?;
        let checks = fields
            .get("Checksums-Sha256")
            .ok_or("native build checksums absent")?;
        let mut seen = BTreeSet::new();
        for line in checks.lines().filter(|l| !l.trim().is_empty()) {
            let parts: Vec<_> = line.split_whitespace().collect();
            ensure(
                parts.len() == 3 && fs::valid_digest(parts[0]) && seen.insert(parts[2]),
                "malformed or duplicate native build checksum",
            )?;
            let artifact = named(pins, parts[2])?;
            ensure(
                artifact.bytes == parts[1].parse::<u64>()? && artifact.sha256 == parts[0],
                "native normal build output checksum differs",
            )?;
        }
        for p in PACKAGES.iter().filter(|p| p.source == package.source) {
            ensure(
                seen.contains(format!("{}_{}_amd64.deb", p.name, p.version).as_str()),
                "normal native build omits an installed source-family member",
            )?;
        }
        if name.ends_with(".buildinfo") {
            ensure(
                field(&fields, "Build-Architecture")? == "amd64",
                "native build architecture differs",
            )?;
            let environment = fields
                .get("Environment")
                .ok_or("native build environment absent")?;
            ensure(
                !["nocheck", "nodoc", "stage1"]
                    .iter()
                    .any(|v| environment.contains(v)),
                "native normal build disabled required tests or used bootstrap profiles",
            )?;
        }
        reports.push(json!({"artifact":pin,"checksummed_outputs":seen}));
    }
    Ok(json!(reports))
}

fn allowed_member(member: &Member) -> Result<()> {
    ensure(
        member.uid == 0
            && member.gid == 0
            && member.mode & 0o7000 == 0
            && ["/usr", "/etc", "/var"]
                .iter()
                .any(|p| member.path == *p || member.path.starts_with(&format!("{p}/"))),
        "native package contains an unreviewed owner, privilege or namespace",
    )?;
    ensure(
        matches!(
            member.content,
            Content::Regular { .. } | Content::Directory | Content::Symlink { .. }
        ),
        "native package special inode or hardlink refused",
    )?;
    ensure(
        match member.content {
            Content::Symlink { .. } => member.mode == 0o777,
            Content::Directory => member.mode == 0o755,
            _ => [0o644, 0o755].contains(&member.mode),
        },
        "native package mode differs",
    )
}

fn same_member(a: &Member, b: &Member) -> bool {
    a.path == b.path
        && a.mode == b.mode
        && a.uid == b.uid
        && a.gid == b.gid
        && a.bytes == b.bytes
        && a.content == b.content
}

fn package(
    work: &Path,
    pins: &SourceMap,
    package: &Package,
) -> Result<(FilePin, Fields, Vec<Member>)> {
    let name = format!("{}_{}_amd64.deb", package.name, package.version);
    let pin = named(pins, &name)?;
    ensure(
        pin.bytes == package.bytes && pin.sha256 == package.sha,
        "normal native package differs from the selected source build",
    )?;
    let area = work.join(format!("package-{}", package.name));
    boot_files::private_dir(&area)?;
    let metadata = boot_files::run_logged(
        &area,
        "control",
        "/usr/bin/dpkg-deb",
        &["--field".into(), pin.path.to_string_lossy().into()],
        30,
    )?;
    let fields = one_control(&boot_files::read_pin(&metadata.log, 65536)?)?;
    ensure(
        field(&fields, "Package")? == package.name
            && field(&fields, "Version")? == package.version
            && field(&fields, "Architecture")? == "amd64"
            && source_name(&fields)? == package.source,
        "actual native package control differs",
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
        30,
    )?;
    let data = boot_packages::parse_tar_with_long_names(
        &boot_files::read_pin(&tar, MAX_TAR)?,
        package.name,
        &pin.sha256,
        allowed_member,
    )?;
    ensure(
        !data.is_empty() && data.len() < 2000,
        "native package member count differs",
    )?;
    Ok((
        pin.clone(),
        fields,
        data.into_iter().map(|p| p.member).collect(),
    ))
}

fn installed(
    root: &Path,
    members: &BTreeMap<String, Member>,
    controls: &[Fields],
) -> Result<Value> {
    let parent = root.parent().ok_or("normal installed root parent absent")?;
    ensure(
        parent.parent() == Some(Path::new("/var/lib/droidloom-qualification"))
            && root == parent.join("root"),
        "normal native readback requires a private qualification root",
    )?;
    let owner = fs::Tree::open(&fs::absolute_string(parent)?, 0)?;
    ensure(
        fs::stat(&owner.root)?.mode & 0o7777 == 0o700,
        "normal native source parent is not private",
    )?;
    let tree = fs::Tree::open(&fs::absolute_string(root)?, 0)?;
    let identity = fs::stat(&tree.root)?;
    let status = boot_files::pin_file(&root.join("var/lib/dpkg/status"))?;
    let fields = control(std::str::from_utf8(&boot_files::read_pin(
        &status,
        32 * 1024 * 1024,
    )?)?)?;
    families(&fields, true)?;
    let dependencies = dependencies::closure(&fields, controls)?;
    for member in members.values() {
        boot_packages::readback(&tree, member)?;
    }
    ensure(
        boot_files::pin_file(&status.path)?.sha256 == status.sha256
            && fs::stat(&tree.root)? == identity,
        "installed native source changed during readback",
    )?;
    fs::assert_root_namespace(&fs::absolute_string(root)?, &tree)?;
    Ok(
        json!({"root":root,"root_identity":identity,"dpkg_status":status,
        "complete_installed_payload":members.values().collect::<Vec<_>>(),
        "candidate_package_payload_members_verified":members.len(),
        "actual_dependencies_verified":dependencies,"dpkg_database_candidate_versions_verified":true,
        "normal_package_transforms":[],"capture_manifest_verified":false,
        "guest_qualified":false,"production_ready":false}),
    )
}

fn admit(plan: Plan, input: &FilePin, source_admission: Option<&FilePin>) -> Result<Value> {
    ensure(
        plan.schema == "droidloom.native-family-candidate-admission-plan.v1"
            && (40..=128).contains(&plan.artifacts.len()),
        "native candidate plan scope differs",
    )?;
    boot_systemd_candidate::admission_work(&plan.work_directory)?;
    let input_copy = plan.work_directory.join("SOURCE-INPUTS.json");
    boot_files::copy_pin(input, &input_copy, 0o400)?;
    let input_pin = boot_files::pin_file(&input_copy)?;
    let receipt_input = if source_admission.is_some() {
        input.clone()
    } else {
        input_pin.clone()
    };
    fs::write_json(
        &fs::absolute_string(&plan.work_directory.join("INPUTS.json"))?,
        &plan,
        0,
    )?;
    let area = plan.work_directory.join("artifacts");
    boot_files::private_dir(&area)?;
    let mut imports = SourceMap::new();
    let mut total = 0u64;
    for (index, (original, pin)) in plan.artifacts.iter().enumerate() {
        let name = original
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or("native evidence basename absent")?;
        ensure(
            original.is_absolute()
                && basename(name)
                && pin.path.file_name() == original.file_name()
                && pin.bytes > 0
                && pin.bytes <= MAX_TAR,
            "native source custody pin differs",
        )?;
        total = total
            .checked_add(pin.bytes)
            .ok_or("native artifact size overflow")?;
        ensure(
            total <= 256 * 1024 * 1024,
            "native source artifact bound exceeded",
        )?;
        let directory = area.join(format!("{index:03}"));
        boot_files::private_dir(&directory)?;
        let output = directory.join(name);
        boot_files::copy_pin(pin, &output, 0o400)?;
        imports.insert(original.clone(), boot_files::pin_file(&output)?);
    }
    let baseline = area.join("original-status");
    boot_files::copy_pin(&plan.original_status, &baseline, 0o400)?;
    let original_fields = control(std::str::from_utf8(&boot_files::read_pin(
        &boot_files::pin_file(&baseline)?,
        32 * 1024 * 1024,
    )?)?)?;
    families(&original_fields, false)?;
    let metadata = checked_metadata(&imports)?;
    let lib_work = plan.work_directory.join("libselinux-source");
    boot_files::private_dir(&lib_work)?;
    let lib = crate::boot_candidate::admit_sources(&plan.libselinux, &imports, &lib_work)?;
    let aa_work = plan.work_directory.join("apparmor-source");
    boot_files::private_dir(&aa_work)?;
    let aa = crate::boot_apparmor_candidate::admit_sources(&plan.libapparmor, &imports, &aa_work)?;
    let gdm_work = plan.work_directory.join("gdm-source");
    boot_files::private_dir(&gdm_work)?;
    let gdm_input = crate::boot_gdm_candidate::GdmCandidate {
        artifacts: plan
            .gdm
            .artifacts
            .iter()
            .map(|(name, pin)| {
                Ok((
                    name.clone(),
                    boot_candidate::source_pin(pin, Some(&imports))?,
                ))
            })
            .collect::<Result<_>>()?,
    };
    let gdm = crate::boot_gdm_candidate::admit_sources(&gdm_input, &gdm_work)?;
    let mut members = BTreeMap::<String, Member>::new();
    let mut controls = Vec::new();
    let mut packages = Vec::new();
    for selected in &PACKAGES {
        let (pin, fields, payload) = package(&plan.work_directory, &imports, selected)?;
        for member in &payload {
            if let Some(old) = members.get(&member.path) {
                ensure(
                    same_member(old, member),
                    "native source families conflict at a shared payload path",
                )?;
            } else {
                members.insert(member.path.clone(), member.clone());
            }
        }
        packages.push(json!({"package":selected.name,"archive":pin,"control":fields,"members_verified":payload.len()}));
        controls.push(fields);
    }
    let dependencies = dependencies::closure(&original_fields, &controls)?;
    let actual = plan
        .installed_root
        .as_ref()
        .map(|root| installed(root, &members, &controls))
        .transpose()?;
    let report = json!({"schema":SCHEMA,"input":receipt_input,"preserved_input":input_pin,"source_admission":source_admission,"input_sha256":input_pin.sha256,
        "source":{"libselinux":lib,"apparmor":aa,"gdm":gdm},"normal_build_metadata":metadata,
        "artifacts":imports,"original_status":plan.original_status,"packages":packages,
        "complete_selected_payload":members.values().collect::<Vec<_>>(),"actual_dependencies_verified":dependencies,
        "installed_source":actual,"source_receipts_rewritten":false,"source_files_modified_by_admission":false,
        "maintainer_scripts_executed_by_admission":false,"package_installation_performed_by_admission":false,
        "guest_qualified":false,"production_ready":false});
    fs::write_json(
        &fs::absolute_string(&plan.work_directory.join("NATIVE-CANDIDATES-VERIFIED.json"))?,
        &report,
        0,
    )?;
    Ok(report)
}

/// Re-admit actual normal sources/builds and all six complete packages against
/// this root. The old receipt locates pinned inputs; its pass flags are unused.
pub(super) fn verify_installed_native(
    root: &Path,
    admission_receipt: &FilePin,
    work: &Path,
) -> Result<Value> {
    let receipt: Value =
        serde_json::from_slice(&boot_files::read_pin(admission_receipt, 16 * 1024 * 1024)?)?;
    ensure(
        receipt["schema"] == SCHEMA,
        "native candidate admission receipt differs",
    )?;
    let input: FilePin = serde_json::from_value(receipt["input"].clone())?;
    ensure(
        receipt["input_sha256"] == input.sha256,
        "native admission input binding differs",
    )?;
    let mut plan: Plan = serde_json::from_slice(&boot_files::read_pin(&input, 1024 * 1024)?)?;
    plan.work_directory = work.into();
    plan.installed_root = Some(root.into());
    admit(plan, &input, Some(admission_receipt))
}

pub fn run(config: &Path, expected: &str) -> Result<()> {
    let plan: Plan = fs::read_json(&fs::absolute_string(config)?, expected)?;
    let input = boot_files::pin_file(config)?;
    ensure(
        input.sha256 == expected,
        "native candidate input changed before snapshot",
    )?;
    let path = plan.work_directory.join("NATIVE-CANDIDATES-VERIFIED.json");
    let installed = plan.installed_root.is_some();
    admit(plan, &input, None)?;
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
    fn status(installed: bool) -> Vec<Fields> {
        PACKAGES
            .iter()
            .map(|p| {
                BTreeMap::from([
                    ("Package".into(), p.name.into()),
                    ("Source".into(), p.source.into()),
                    (
                        "Version".into(),
                        if installed { p.version } else { p.original }.into(),
                    ),
                    ("Architecture".into(), "amd64".into()),
                    ("Status".into(), "install ok installed".into()),
                ])
            })
            .collect()
    }
    #[test]
    fn exact_normal_families_require_all_six_and_real_configured_versions() -> Result<()> {
        families(&status(false), false)?;
        families(&status(true), true)?;
        let mut rows = status(true);
        rows.pop();
        assert!(families(&rows, true).is_err());
        let mut rows = status(true);
        rows[0].insert("Version".into(), PACKAGES[0].original.into());
        assert!(families(&rows, true).is_err());
        let mut rows = status(true);
        rows[0].insert("Status".into(), "install ok unpacked".into());
        assert!(families(&rows, true).is_err());
        let mut rows = status(true);
        rows.push(rows[0].clone());
        assert!(families(&rows, true).is_err());
        let mut rows = status(true);
        rows[0].insert("Package".into(), "libselinux-dev".into());
        assert!(families(&rows, true).is_err());
        Ok(())
    }
    #[test]
    fn unrelated_normal_additions_and_other_proven_upgrades_do_not_change_family() -> Result<()> {
        let mut rows = status(true);
        rows.push(BTreeMap::from([
            ("Package".into(), "systemd".into()),
            ("Version".into(), "259.9-0ubuntu0.1+p4gentmp1".into()),
        ]));
        families(&rows, true)
    }
    #[test]
    fn normal_payload_policy_rejects_privilege_alias_and_owner_expansion() -> Result<()> {
        let m = Member {
            path: "/usr/lib/example".into(),
            package: "libselinux1".into(),
            archive_sha256: "a".repeat(64),
            mode: 0o644,
            uid: 0,
            gid: 0,
            bytes: 3,
            content: Content::Regular {
                sha256: "b".repeat(64),
            },
        };
        allowed_member(&m)?;
        for changed in [
            Member {
                uid: 1000,
                ..m.clone()
            },
            Member {
                mode: 0o4755,
                ..m.clone()
            },
            Member {
                path: "/home/alex/file".into(),
                ..m.clone()
            },
            Member {
                content: Content::Hardlink {
                    sha256: "b".repeat(64),
                    target: "/etc/file".into(),
                },
                ..m.clone()
            },
        ] {
            assert!(allowed_member(&changed).is_err());
        }
        Ok(())
    }
    #[test]
    fn ambiguous_basename_never_selects_different_producer_bytes() -> Result<()> {
        let good = FilePin {
            path: "/work/a/file.deb".into(),
            bytes: 3,
            sha256: "a".repeat(64),
        };
        let mut pins = SourceMap::from([
            ("/original/a/file.deb".into(), good.clone()),
            (
                "/original/b/file.deb".into(),
                FilePin {
                    path: "/work/b/file.deb".into(),
                    ..good.clone()
                },
            ),
        ]);
        named(&pins, "file.deb")?;
        pins.get_mut(Path::new("/original/b/file.deb"))
            .unwrap()
            .sha256 = "b".repeat(64);
        assert!(named(&pins, "file.deb").is_err());
        assert!(named(&pins, "../file.deb").is_err());
        Ok(())
    }
}
