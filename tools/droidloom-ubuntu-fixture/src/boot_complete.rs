//! Prepare a complete, normally configured distribution root for an owned VM.
//! The historical public-file fixture remains a separate source authority.
use crate::boot_files::{self, FilePin};
use crate::complete_native::{self, CompleteManifest, Package};
use crate::complete_snapshot::{self, Snapshot};
use crate::{Result, ensure, fs};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

pub const PREPARED_SCHEMA: &str = "droidloom.complete-ubuntu-native-prepared.v1";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CompleteNativePlan {
    pub schema: String,
    pub work_directory: PathBuf,
    pub fixture_manifest: FilePin,
    pub fixture_root: PathBuf,
    pub native: crate::boot_native::CompleteNativeInputs,
}

/// This is an additional cohort check after the actual installed-source proof,
/// not an admission based on package names or version suffixes alone.
pub(super) fn normal_families(packages: &[Package]) -> Result<Value> {
    let mut by_name = BTreeMap::new();
    for package in packages {
        let name = package
            .package
            .split(':')
            .next()
            .ok_or("package name absent")?;
        ensure(
            by_name.insert(name, package).is_none(),
            "duplicate native package name",
        )?;
    }
    let systemd = [
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
    let families: [(&str, &[&str], &str); 4] = [
        ("systemd", &systemd, "+p4gentmp1"),
        ("libselinux", &["libselinux1"], "+p4lsmexec4"),
        ("apparmor", &["apparmor", "libapparmor1"], "+p4peer1"),
        ("gdm", &["gdm3", "libgdm1", "gir1.2-gdm-1.0"], "+p4fsuser3"),
    ];
    let mut result = BTreeMap::new();
    for (family, names, suffix) in families {
        let mut version: Option<&str> = None;
        let mut rows = Vec::new();
        for name in names {
            let p = by_name
                .get(name)
                .ok_or("complete native candidate family is incomplete")?;
            ensure(
                p.status == "ii " && p.architecture == "amd64" && p.version.ends_with(suffix),
                "complete native candidate version or configured state differs",
            )?;
            if let Some(prior) = version {
                ensure(
                    prior == p.version,
                    "complete native candidate family mixes versions",
                )?;
            } else {
                version = Some(&p.version);
            }
            rows.push(json!({"package":name,"version":p.version,"architecture":p.architecture}));
        }
        result.insert(family, rows);
    }
    Ok(json!({"families":result,"normal_package_count":packages.len()}))
}

pub(super) fn admitted_manifest(pin: &FilePin) -> Result<CompleteManifest> {
    let manifest: CompleteManifest =
        serde_json::from_slice(&boot_files::read_pin(pin, 128 * 1024 * 1024)?)?;
    let source = complete_native::validate(&manifest)?;
    ensure(
        source.stage == "installed"
            && source.native_release.is_some()
            && source.native_transaction.is_some()
            && !manifest.kernel_present
            && manifest.target_kernel_release
                == crate::boot_apparmor_candidate::REQUIRED_KERNEL_RELEASE,
        "complete boot requires the actually installed complete native release and shared kernel",
    )?;
    normal_families(&manifest.packages)?;
    Ok(manifest)
}

pub fn prepare(config: &Path, expected: &str) -> Result<()> {
    let plan: CompleteNativePlan = fs::read_json(&fs::absolute_string(config)?, expected)?;
    ensure(
        plan.schema == "droidloom.complete-ubuntu-native-boot-plan.v1"
            && plan.fixture_root != Path::new("/")
            && plan.fixture_root != plan.work_directory.join("root"),
        "complete native plan has an invalid authority or source root",
    )?;
    let manifest = admitted_manifest(&plan.fixture_manifest)?;
    let source_verification =
        complete_native::verify(&manifest, &plan.fixture_manifest.sha256, &plan.fixture_root)?;
    let source = Snapshot::open(&plan.fixture_root)?;
    let before = source.inventory()?;
    let source_identity = fs::stat(&source.root)?;
    crate::boot::create_work(&plan.work_directory)?;
    fs::write_json(
        &fs::absolute_string(&plan.work_directory.join("INPUTS.json"))?,
        &plan,
        0,
    )?;
    let root = plan.work_directory.join("root");
    let copy =
        complete_snapshot::copy(&source, &root, &manifest.entries, &manifest.static_devices)?;
    let (regular, bytes) =
        complete_snapshot::verify(&copy, &manifest.entries, &manifest.static_devices)?;
    ensure(
        source.inventory()? == before && fs::stat(&source.root)? == source_identity,
        "complete source changed during the owned native clone",
    )?;
    let database_before = boot_files::pin_file(&root.join("var/lib/dpkg/status"))?;
    let database_identity_before = copy.identity("/var/lib/dpkg/status")?;
    let clone = json!({
        "schema":"droidloom.complete-native-owned-clone.v1",
        "source_verification":source_verification,"source_root":plan.fixture_root,
        "source_identity":source_identity,"destination":root,
        "destination_identity":fs::stat(&copy.root)?,
        "manifest":plan.fixture_manifest,
        "entries_verified":manifest.entries.len()+manifest.static_devices.len(),
        "regular_paths_verified":regular,"unique_regular_bytes":bytes,
        "whole_package_database":database_before,
        "guest_qualified":false,"production_ready":false
    });
    fs::write_json(
        &fs::absolute_string(&plan.work_directory.join("COMPLETE-CLONE.json"))?,
        &clone,
        0,
    )?;
    let initialized = crate::boot_native::initialize_complete(
        &root,
        &plan.work_directory,
        &plan.native,
        &manifest,
    )?;
    let database_after = boot_files::pin_file(&root.join("var/lib/dpkg/status"))?;
    ensure(
        copy.identity("/var/lib/dpkg/status")? == database_identity_before
            && database_before.path == database_after.path
            && database_before.bytes == database_after.bytes
            && database_before.sha256 == database_after.sha256,
        "fresh native initialization changed the configured package database",
    )?;
    ensure(
        initialized["native_initialization_complete"] == true,
        "complete native initializer did not complete",
    )?;
    let receipt = json!({
        "schema":PREPARED_SCHEMA,"input_sha256":expected,
        "work_directory":plan.work_directory,"root":root,
        "root_identity":fs::stat(&copy.root)?,
        "complete_fixture_manifest":plan.fixture_manifest,
        "complete_clone":boot_files::pin_file(&plan.work_directory.join("COMPLETE-CLONE.json"))?,
        "normal_native_packages":normal_families(&manifest.packages)?,
        "root_filesystem_uuid":plan.native.root_filesystem_uuid,
        "network_connection_uuid":plan.native.network_connection_uuid,
        "native_initialization":initialized,
        "dpkg_status_preserved":database_after,
        "guest_qualified":false,"production_ready":false,
        "next_required":"Import the matching normal host, Android, shared kernel and complete modules, then perform the real enforcing owned boot."
    });
    let path = plan.work_directory.join("NATIVE-PREPARED.json");
    let sha = fs::write_json(&fs::absolute_string(&path)?, &receipt, 0)?;
    println!(
        "{}",
        json!({"receipt":path,"sha256":sha,
        "guest_qualified":false,"production_ready":false})
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn packages() -> Vec<Package> {
        let mut rows = Vec::new();
        for (names, version) in [
            (
                vec![
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
                ],
                "259.9-0ubuntu0.1+p4gentmp1",
            ),
            (vec!["libselinux1"], "3.9-1+p4lsmexec4"),
            (vec!["apparmor", "libapparmor1"], "5.0.2-1+p4peer1"),
            (
                vec!["gdm3", "libgdm1", "gir1.2-gdm-1.0"],
                "50.1-1+p4fsuser3",
            ),
        ] {
            for name in names {
                rows.push(Package {
                    package: name.into(),
                    version: version.into(),
                    architecture: "amd64".into(),
                    status: "ii ".into(),
                });
            }
        }
        rows
    }
    #[test]
    fn complete_boot_rejects_missing_mixed_or_unconfigured_native_family() {
        let complete = packages();
        normal_families(&complete).unwrap();
        let mut missing = complete.clone();
        missing.pop();
        assert!(normal_families(&missing).is_err());
        let mut mixed = complete.clone();
        mixed[0].version = "260-1+p4gentmp1".into();
        assert!(normal_families(&mixed).is_err());
        let mut stale = complete.clone();
        stale[10].version = "3.9-1".into();
        assert!(normal_families(&stale).is_err());
        let mut pending = complete.clone();
        pending[12].status = "iU ".into();
        assert!(normal_families(&pending).is_err());
        let mut duplicate = complete.clone();
        duplicate.push(complete[0].clone());
        assert!(normal_families(&duplicate).is_err());
    }
}
