use crate::{
    Result,
    boot_files::{self, FilePin},
    ensure, fs,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{Read, Seek, SeekFrom},
    path::Path,
};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AndroidInputs {
    pub cohort: FilePin,
    pub runtime: FilePin,
    pub query_inputs: Option<BTreeMap<String, FilePin>>,
    pub device_manifest: FilePin,
    pub images: BTreeMap<String, FilePin>,
    pub device_bank: FilePin,
    pub cell_template: FilePin,
    pub persistent_data: Option<WorkingDataInputs>,
    pub mac_release: Option<BTreeMap<String, FilePin>>,
    pub calibrate: bool,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkingDataInputs {
    pub receipt: FilePin,
    pub images: BTreeMap<String, FilePin>,
}
fn admit_working(input: &WorkingDataInputs) -> Result<()> {
    let receipt: Value =
        serde_json::from_slice(&boot_files::read_pin(&input.receipt, 1024 * 1024)?)?;
    ensure(
        receipt["schema"] == "p4-real-userdata-independent-working-copy-v1"
            && receipt["cold_original_kept"] == true
            && receipt["original_userdata_opened"] == false
            && receipt["mounted"] == false
            && receipt["runtime_qualified"] == false,
        "working-data custody receipt is not the admitted cold independent copy",
    )?;
    let rows = receipt["images"]
        .as_array()
        .ok_or("missing working image identities")?;
    ensure(
        rows.len() == 2
            && input
                .images
                .keys()
                .map(String::as_str)
                .collect::<BTreeSet<_>>()
                == BTreeSet::from(["data", "metadata"]),
        "working-data pair incomplete",
    )?;
    for name in ["data", "metadata"] {
        let matches: Vec<_> = rows
            .iter()
            .filter(|r| r["name"] == format!("{name}.img"))
            .collect();
        ensure(matches.len() == 1, "duplicate or absent working image")?;
        let row = matches[0];
        let pin = &input.images[name];
        ensure(
            !pin.path.starts_with("/var/lib/droidloom/users")
                && row["working_path"] == pin.path.to_string_lossy().as_ref()
                && row["sha256"] == pin.sha256
                && row["working_identity"]["size"] == pin.bytes
                && row["same_bytes"] == true
                && row["source_unchanged"] == true
                && row["original_userdata_opened"] == false,
            "working image is outside admitted custody",
        )?;
        let (_, id) = boot_files::open_pin(pin)?;
        let r = &row["working_identity"];
        ensure(
            r["device"] == id.dev
                && r["inode"] == id.ino
                && r["size"] == id.size
                && r["uid"] == id.uid
                && r["gid"] == id.gid
                && r["nlink"] == id.nlink
                && r["mtime_ns"] == id.mtime_sec * 1_000_000_000 + id.mtime_nsec
                && r["ctime_ns"] == id.ctime_sec * 1_000_000_000 + id.ctime_nsec
                && id.uid == 0
                && id.gid == 0
                && id.nlink == 1
                && id.mode & 0o7777 == 0o600,
            "working image actual inode identity changed",
        )?;
        ensure(
            row["source_identity"]["device"] != id.dev || row["source_identity"]["inode"] != id.ino,
            "working image aliases its preserved cold source",
        )?;
    }
    Ok(())
}
const ROLES: [&str; 4] = [
    "system",
    "vendor",
    "system_ext_lib64",
    "system_ext_readiness",
];
const MAC: [&str; 5] = [
    "contract.json",
    "manager-label.json",
    "policy.bin",
    "policy-export.bin",
    "derivation.json",
];
fn install(root: &Path, guest: &str, pin: &FilePin, mode: u32) -> Result<()> {
    let parent = Path::new(guest)
        .parent()
        .and_then(Path::to_str)
        .ok_or("invalid installation path")?;
    boot_files::ensure_dir(root, parent, 0o755)?;
    boot_files::copy_pin(pin, &boot_files::guest_path(root, guest)?, mode)
}
fn write(root: &Path, guest: &str, bytes: &[u8], mode: u32) -> Result<()> {
    let parent = Path::new(guest)
        .parent()
        .and_then(Path::to_str)
        .ok_or("invalid installation path")?;
    boot_files::ensure_dir(root, parent, 0o755)?;
    boot_files::write_new(&boot_files::guest_path(root, guest)?, bytes, mode)
}
fn emit(root: &Path, guest: &str, value: &Value, mode: u32) -> Result<String> {
    let bytes = serde_json::to_vec_pretty(value)?;
    write(root, guest, &bytes, mode)?;
    Ok(fs::digest(&bytes))
}
pub fn uuid(bytes: &[u8]) -> Result<String> {
    ensure(bytes.len() == 16, "invalid ext4 UUID length")?;
    let h = hex::encode(bytes);
    Ok(format!(
        "{}-{}-{}-{}-{}",
        &h[..8],
        &h[8..12],
        &h[12..16],
        &h[16..20],
        &h[20..]
    ))
}
fn ext4_record(work: &Path, name: &str, path: &Path) -> Result<Value> {
    let pin = boot_files::pin_file(path)?;
    let mut f = boot_files::checked_file(&pin)?;
    f.seek(SeekFrom::Start(1024))?;
    let mut sb = [0u8; 1024];
    f.read_exact(&mut sb)?;
    ensure(
        u16::from_le_bytes(sb[56..58].try_into()?) == 0xef53,
        "persistent image is not ext4",
    )?;
    let rec = boot_files::run_logged(
        work,
        &format!("{name}-root-inode"),
        "/usr/sbin/debugfs",
        &[
            "-R".into(),
            "stat <2>".into(),
            path.to_string_lossy().into(),
        ],
        30,
    )?;
    let log = String::from_utf8(boot_files::read_pin(&rec.log, 1024 * 1024)?)?;
    let tokens: Vec<_> = log.split_whitespace().collect();
    let after = |key: &str| {
        tokens
            .iter()
            .position(|x| *x == key)
            .and_then(|i| tokens.get(i + 1))
            .copied()
    };
    ensure(
        after("Type:") == Some("directory")
            && after("User:") == Some("0")
            && after("Group:") == Some("0")
            && after("Mode:").and_then(|s| u32::from_str_radix(s, 8).ok()) == Some(0o755),
        "persistent filesystem root ownership/mode differs from selected original-ext4 contract",
    )?;
    Ok(
        json!({"image_bytes":pin.bytes,"filesystem_uuid":uuid(&sb[104..120])?,
        "feature_compat":u32::from_le_bytes(sb[92..96].try_into()?),
        "feature_incompat":u32::from_le_bytes(sb[96..100].try_into()?),
        "feature_ro_compat":u32::from_le_bytes(sb[100..104].try_into()?),
        "guest_root_uid":0,"guest_root_gid":0,"guest_root_mode":493}),
    )
}

pub fn install_android(root: &Path, work: &Path, input: &AndroidInputs, host_manifest: &FilePin) -> Result<Value> {
    ensure(
        input.calibrate != input.mac_release.is_some(),
        "select exactly calibration or a normal five-file MAC release",
    )?;
    let cohort: Value =
        serde_json::from_slice(&boot_files::read_pin(&input.cohort, 8 * 1024 * 1024)?)?;
    let runtime_raw = boot_files::read_pin(&input.runtime, 256 * 1024)?;
    let device: Value =
        serde_json::from_slice(&boot_files::read_pin(&input.device_manifest, 1024 * 1024)?)?;
    let generation = &input.cohort.sha256;
    ensure(
        cohort["schema"] == 3 && cohort["scope"] == "android_base_images_v3",
        "normal published four-image Android cohort required",
    )?;
    ensure(
        input
            .images
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            == BTreeSet::from(ROLES),
        "selected Android image set differs",
    )?;
    for role in ROLES {
        let pin = &input.images[role];
        ensure(
            cohort[role]["sha256"] == pin.sha256 && cohort[role]["bytes"] == pin.bytes,
            "image is not the normal cohort member",
        )?;
    }
    let query_plan = crate::boot_query::admit(
        &runtime_raw,
        generation,
        &input.runtime.sha256,
        &input.images["system"],
        input.query_inputs.as_ref(),
    )?;
    ensure(
        device["schema"] == 1
            && device["scope"] == "android_private_device_source_v1"
            && device["base_cohort_sha256"] == *generation
            && device["runtime_manifest_sha256"] == input.runtime.sha256
            && device["source_system_sha256"] == input.images["system"].sha256
            && device["sha256"] == input.device_bank.sha256
            && device["bytes"] == input.device_bank.bytes
            && device["file"] == format!("{}.img", input.device_bank.sha256),
        "normal device template is from a different release",
    )?;
    ensure(
        input.device_bank.bytes == 8388608
            && input.device_bank.sha256
                == "b5b7ee1522f87c6fafb668d671ff028685db9e8e346564b1edda1f7ef867d5f7",
        "unexpected selected board device template",
    )?;
    let base = format!("/var/lib/droidloom/cohorts/{generation}");
    install(
        root,
        &format!("/etc/droidloom/cohorts/{generation}.json"),
        &input.cohort,
        0o400,
    )?;
    install(
        root,
        &format!(
            "/etc/droidloom/runtime-cohorts/{}.json",
            input.runtime.sha256
        ),
        &input.runtime,
        0o400,
    )?;
    install(
        root,
        &format!(
            "/etc/droidloom/board-devices/{}.json",
            input.device_manifest.sha256
        ),
        &input.device_manifest,
        0o444,
    )?;
    install(
        root,
        &format!("{base}/board/{}.img", input.device_bank.sha256),
        &input.device_bank,
        0o444,
    )?;
    for role in ROLES {
        install(
            root,
            &format!("{base}/images/{role}.img"),
            &input.images[role],
            0o400,
        )?;
    }
    let query_inputs = query_plan
        .as_ref()
        .map(|plan| crate::boot_query::install(root, plan))
        .transpose()?;
    if let Some(mac) = &input.mac_release {
        ensure(
            mac.keys().map(String::as_str).collect::<BTreeSet<_>>() == BTreeSet::from(MAC),
            "incomplete normal MAC release",
        )?;
        for name in MAC {
            install(
                root,
                &format!("/etc/droidloom/host-mac/{name}"),
                &mac[name],
                0o400,
            )?;
        }
    }
    let mut cell: Value =
        serde_json::from_slice(&boot_files::read_pin(&input.cell_template, 1024 * 1024)?)?;
    let object = cell
        .as_object_mut()
        .ok_or("cell template is not an object")?;
    for (k, v) in [
        ("image_layout", json!("gsi_system_as_root")),
        ("image_dir", json!(format!("{base}/images"))),
        ("vendor_image", json!(format!("{base}/images/vendor.img"))),
        ("subordinate_uids", json!({"start":200000,"count":100000})),
        ("subordinate_gids", json!({"start":200000,"count":100000})),
        ("android_init", Value::Null),
        ("android_file_overrides", json!([])),
        ("android_runtime_directories", json!([])),
        ("shared_storage_directories", json!([])),
        ("gapps_dir", Value::Null),
    ] {
        object.insert(k.into(), v);
    }
    let spec = serde_json::to_vec_pretty(&cell)?;
    write(root, "/etc/droidloom/cell.json", &spec, 0o644)?;
    let stores = "/var/lib/droidloom/users/1000/data";
    boot_files::ensure_dir(root, stores, 0o700)?;
    boot_files::ensure_dir(root, "/var/lib/droidloom/identity-reservations", 0o700)?;
    if let Some(pins) = &input.persistent_data {
        ensure(
            !input.calibrate,
            "real working data is not used in factory calibration",
        )?;
        admit_working(pins)?;
    }
    let mut persistent = serde_json::Map::new();
    persistent.insert("mode".into(), json!("original-ext4-v1"));
    for name in ["data", "metadata"] {
        let path = boot_files::guest_path(root, &format!("{stores}/{name}.img"))?;
        if let Some(pins) = &input.persistent_data {
            boot_files::copy_pin(&pins.images[name], &path, 0o600)?;
        } else {
            let f = boot_files::new_file(&path, 0o600)?;
            let size = if name == "data" {
                if input.calibrate {
                    8u64 * 1024 * 1024 * 1024
                } else {
                    32u64 * 1024 * 1024 * 1024
                }
            } else {
                128 * 1024 * 1024
            };
            f.set_len(size)?;
            f.sync_all()?;
            boot_files::run_logged(
                work,
                &format!("mkfs-{name}"),
                "/usr/sbin/mke2fs",
                &[
                    "-q".into(),
                    "-F".into(),
                    "-t".into(),
                    "ext4".into(),
                    "-b".into(),
                    "4096".into(),
                    "-I".into(),
                    "256".into(),
                    "-E".into(),
                    "root_owner=0:0".into(),
                    path.to_string_lossy().into(),
                ],
                120,
            )?;
        }
        persistent.insert(name.into(), ext4_record(work, name, &path)?);
    }
    let host: crate::boot_host::HostManifest = serde_json::from_slice(&boot_files::read_pin(host_manifest, 1024 * 1024)?)?;
    let normal_host_release = crate::boot_host::normal_host_release(root, &host)?;
    let selected = json!({"schema":"droidloom-production-selection-v4","launcher":"early_boot_shared_kernel_v1",
        "host_uid":1000,"cell_spec_bytes":spec.len(),"cell_spec_sha256":fs::digest(&spec),
        "base_cohort_sha256":generation,"runtime_manifest_sha256":input.runtime.sha256,
        "persistent_data":persistent,"normal_host_release":normal_host_release});
    let selection = emit(
        root,
        "/etc/droidloom/production/selected.json",
        &selected,
        0o400,
    )?;
    write(root, "/etc/droidloom/setup.lock", b"", 0o600)?;
    let manager = &normal_host_release.manager;
    let publication = json!({"schema":"droidloom-public-early-launcher-v1","launcher":"early_boot_shared_kernel_v1",
        "selection_sha256":selection,"manager_sha256":manager.sha256,"manager_bytes":manager.bytes});
    emit(
        root,
        "/etc/droidloom/container-launcher.json",
        &publication,
        0o644,
    )?;
    let units = [
        "droidloom-instance-factory.service",
        "droidloom-instance-launcher.service",
        "droidloom-manager-label.service",
        "droidloom-production.service",
        "droidloom-early-observer.service",
    ];
    let mut unit_rows = Vec::new();
    for name in units {
        let src = root.join(format!("usr/share/droidloom/production/{name}"));
        let pin = boot_files::pin_file(&src)?;
        install(root, &format!("/etc/systemd/system/{name}"), &pin, 0o644)?;
        unit_rows.push(json!({"name":name,"sha256":pin.sha256}));
    }
    for name in [
        "droidloom-production.service",
        "droidloom-early-observer.service",
    ] {
        boot_files::run_logged(
            work,
            &format!("enable-{}", name.trim_end_matches(".service")),
            "/usr/bin/systemctl",
            &[
                "--root".into(),
                root.to_string_lossy().into(),
                "enable".into(),
                name.into(),
            ],
            30,
        )?;
    }
    if input.calibrate {
        let template =
            root.join("usr/share/droidloom/production/droidloom-mac-calibration.service");
        let pin = boot_files::pin_file(&template)?;
        // The exported original unit already occupies /usr/lib/systemd/system.
        let installed = boot_files::pin_file(
            &root.join("usr/lib/systemd/system/droidloom-mac-calibration.service"),
        )?;
        ensure(
            installed.sha256 == pin.sha256,
            "calibration unit is not the original normal export",
        )?;
        write(root,"/etc/systemd/system/droidloom-calibration-qualification.target",
            b"[Unit]\nDescription=Qualify ordinary host MAC calibration\nRequires=droidloom-mac-calibration.service systemd-journal-flush.service systemd-logind.service\nWants=snapd.apparmor.service\nAfter=droidloom-mac-calibration.service systemd-journal-flush.service systemd-logind.service\n",0o644)?;
    }
    Ok(
        json!({"cohort":input.cohort,"runtime":input.runtime,"device_manifest":input.device_manifest,
        "selection_sha256":selection,"selected":selected,"ordinary_units":unit_rows,
        "fixed_query_inputs":query_inputs,
        "calibration_requested":input.calibrate,"working_data_supplied":input.persistent_data.is_some(),
        "guest_qualified":false,"production_ready":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ext4_uuid_preserves_on_disk_byte_order() {
        assert_eq!(
            uuid(&[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]).unwrap(),
            "00010203-0405-0607-0809-0a0b0c0d0e0f"
        );
    }
}
