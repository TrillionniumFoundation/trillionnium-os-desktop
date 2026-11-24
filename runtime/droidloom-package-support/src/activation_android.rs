//! The only first-generation selector writer. These records select inputs;
//! runtime admission still comes from the shared kernel's real boot witnesses.
use super::{
    Result,
    activation_files::{self as files, FilePin, HeldFile},
    activation_mac, activation_query,
    activation_userdata::OriginalData,
};
use droidloom_contracts::system_ext::{self, Declaration, ReadinessDeclaration};
use droidloom_supervisor::{AndroidImageLayout, CellSpec};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

const MIB: u64 = 1024 * 1024;
const ROLES: [&str; 4] = [
    "system",
    "vendor",
    "system_ext_lib64",
    "system_ext_readiness",
];
pub(super) const UNITS: [&str; 5] = [
    "droidloom-instance-factory.service",
    "droidloom-instance-launcher.service",
    "droidloom-manager-label.service",
    "droidloom-production.service",
    "droidloom-early-observer.service",
];
pub(super) const ENABLED: [&str; 2] = [
    "droidloom-production.service",
    "droidloom-early-observer.service",
];
const CONFIGURATION: [&str; 3] = [
    "etc/droidloom/cell.json",
    "etc/droidloom/production/selected.json",
    "etc/droidloom/container-launcher.json",
];
const TEMPLATE: &[u8] = include_bytes!("../../../packaging/cell-spec-x86_64-u1000.json");
fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct AndroidInputs {
    pub cohort: FilePin,
    pub runtime: FilePin,
    pub query_inputs: BTreeMap<String, FilePin>,
    pub device_manifest: FilePin,
    pub device_bank: FilePin,
    pub images: BTreeMap<String, FilePin>,
    pub cell_template: FilePin,
    pub mac_release: FilePin,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Image {
    file: String,
    bytes: u64,
    sha256: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Cohort {
    schema: u32,
    scope: String,
    layout: AndroidImageLayout,
    system: Image,
    vendor: Image,
    system_ext_lib64: Declaration,
    system_ext_readiness: ReadinessDeclaration,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Device {
    schema: u32,
    scope: String,
    base_cohort_sha256: String,
    runtime_manifest_sha256: String,
    source_system_sha256: String,
    file: String,
    bytes: u64,
    sha256: String,
    readback: Value,
}
struct Admitted {
    cohort: HeldFile,
    runtime: HeldFile,
    device: HeldFile,
    bank: HeldFile,
    template: HeldFile,
    images: [HeldFile; 4],
    query: activation_query::QueryPlan,
}
fn admit(input: &AndroidInputs) -> Result<Admitted> {
    require(
        input
            .images
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            == BTreeSet::from(ROLES),
        "first activation needs exactly the normal four-image cohort",
    )?;
    let cohort = HeldFile::open(&input.cohort, 16 * 1024)?;
    let row: Cohort = serde_json::from_slice(&cohort.read_all(16 * 1024)?)?;
    require(
        row.schema == 3
            && row.scope == "android_base_images_v3"
            && row.layout == AndroidImageLayout::GsiSystemAsRoot
            && row.system.file == "system.img"
            && row.vendor.file == "vendor.img"
            && system_ext::accepts_base(
                row.schema,
                &row.scope,
                Some(&row.system_ext_lib64),
                Some(&row.system_ext_readiness),
                &row.system.sha256,
                &row.vendor.sha256,
            ),
        "normal Android cohort is incomplete or crosses release generations",
    )?;
    let members = [
        (row.system.bytes, &row.system.sha256),
        (row.vendor.bytes, &row.vendor.sha256),
        (row.system_ext_lib64.bytes, &row.system_ext_lib64.sha256),
        (
            row.system_ext_readiness.bytes,
            &row.system_ext_readiness.sha256,
        ),
    ];
    let mut seen = BTreeSet::new();
    let mut images = Vec::new();
    for (role, (bytes, sha)) in ROLES.iter().zip(members) {
        let pin = &input.images[*role];
        require(
            (4096..=8 * 1024 * 1024 * 1024).contains(&bytes)
                && bytes % 512 == 0
                && files::valid_digest(sha)
                && pin.bytes == bytes
                && pin.sha256 == *sha,
            "Android image is not the selected complete raw member",
        )?;
        let held = HeldFile::open(pin, 8 * 1024 * 1024 * 1024)?;
        files::no_privilege_xattrs(held.file())?;
        require(
            seen.insert((held.identity().device, held.identity().inode)),
            "selected Android roles alias one backing inode",
        )?;
        images.push(held);
    }
    let runtime = HeldFile::open(&input.runtime, 256 * 1024)?;
    let query = activation_query::admit(
        &runtime.read_all(256 * 1024)?,
        &input.cohort.sha256,
        &input.runtime.sha256,
        &input.images["system"],
        Some(&input.query_inputs),
    )?
    .ok_or("production applications require the fixed kernel-first v2 query contract")?;
    let device = HeldFile::open(&input.device_manifest, MIB)?;
    let declaration: Device = serde_json::from_slice(&device.read_all(MIB)?)?;
    require(
        declaration.schema == 1
            && declaration.scope == "android_private_device_source_v1"
            && declaration.base_cohort_sha256 == input.cohort.sha256
            && declaration.runtime_manifest_sha256 == input.runtime.sha256
            && declaration.source_system_sha256 == input.images["system"].sha256
            && declaration.file == format!("{}.img", system_ext::DEVICE_SOURCE_SHA256)
            && declaration.bytes == system_ext::DEVICE_SOURCE_BYTES
            && declaration.sha256 == system_ext::DEVICE_SOURCE_SHA256
            && declaration.readback["bytes"] == declaration.bytes
            && declaration.readback["sha256"] == declaration.sha256
            && input.device_bank.bytes == declaration.bytes
            && input.device_bank.sha256 == declaration.sha256,
        "device source does not bind the exact fixed original template to this cohort",
    )?;
    let bank = HeldFile::open(&input.device_bank, system_ext::DEVICE_SOURCE_BYTES)?;
    let template = HeldFile::open(&input.cell_template, MIB)?;
    require(
        template.read_all(MIB)? == TEMPLATE,
        "first activation template differs from this normal source tree",
    )?;
    Ok(Admitted {
        cohort,
        runtime,
        device,
        bank,
        template,
        images: images
            .try_into()
            .map_err(|_| "Android role cardinality changed")?,
        query,
    })
}
fn destination(root: &Path, relative: &str) -> Result<PathBuf> {
    require(
        !relative.starts_with('/')
            && !relative
                .split('/')
                .any(|p| p.is_empty() || p == "." || p == ".."),
        "invalid fixed Android destination",
    )?;
    let path = root.join(relative);
    files::ensure_dir(
        root,
        Path::new(relative)
            .parent()
            .and_then(Path::to_str)
            .ok_or("Android destination has no parent")?,
    )?;
    Ok(path)
}
fn install(root: &Path, path: &str, input: &HeldFile, mode: u32) -> Result<FilePin> {
    input.copy_new(&destination(root, path)?, mode)
}
fn expected_configuration(
    root: &Path,
    input: &AndroidInputs,
    original: &OriginalData,
) -> Result<[Vec<u8>; 3]> {
    original.revalidate()?;
    let template = HeldFile::open(&input.cell_template, MIB)?;
    let raw = template.read_all(MIB)?;
    require(raw == TEMPLATE, "normal cell template changed")?;
    let (selected_uids, selected_gids) =
        super::activation_identity::production_ranges(original.cell_spec())?;
    let mut cell: Value = serde_json::from_slice(&raw)?;
    let map = cell
        .as_object_mut()
        .ok_or("normal cell template is not an object")?;
    let base = format!("/var/lib/droidloom/cohorts/{}", input.cohort.sha256);
    for (name, value) in [
        ("image_layout", json!("gsi_system_as_root")),
        ("image_dir", json!(format!("{base}/images"))),
        ("vendor_image", json!(format!("{base}/images/vendor.img"))),
        ("subordinate_uids", serde_json::to_value(&selected_uids)?),
        ("subordinate_gids", serde_json::to_value(&selected_gids)?),
        ("android_init", Value::Null),
        ("android_file_overrides", json!([])),
        ("android_runtime_directories", json!([])),
        ("shared_storage_directories", json!([])),
        ("gapps_dir", Value::Null),
    ] {
        map.insert(name.into(), value);
    }
    let bytes = serde_json::to_vec_pretty(&cell)?;
    let parsed: CellSpec = serde_json::from_slice(&bytes)?;
    parsed.validate()?;
    require(
        parsed.host_uid == 1000
            && parsed.data_dir == original.cell_spec().data_dir
            && parsed.subordinate_uids == selected_uids
            && parsed.subordinate_gids == selected_gids
            && parsed.android_init.is_none()
            && parsed.android_file_overrides.is_empty()
            && parsed.android_runtime_directories.is_empty()
            && parsed.shared_storage_directories.is_empty()
            && parsed.gapps_dir.is_none(),
        "first production cell lost original data or retained legacy overrides",
    )?;
    let selected = serde_json::to_vec_pretty(
        &json!({"schema":"droidloom-production-selection-v4",
        "launcher":"early_boot_shared_kernel_v1","host_uid":1000,"cell_spec_bytes":bytes.len(),
        "cell_spec_sha256":files::digest(&bytes),"base_cohort_sha256":input.cohort.sha256,
        "runtime_manifest_sha256":input.runtime.sha256,"persistent_data":original.persistent_policy()}),
    )?;
    let manager = files::pin_file(&root.join("usr/lib/droidloom/production/current/droidloomd"))?;
    let launcher =
        serde_json::to_vec_pretty(&json!({"schema":"droidloom-public-early-launcher-v1",
        "launcher":"early_boot_shared_kernel_v1","selection_sha256":files::digest(&selected),
        "manager_sha256":manager.sha256,"manager_bytes":manager.bytes}))?;
    Ok([bytes, selected, launcher])
}
fn immutable_files(input: &AndroidInputs) -> Vec<(String, FilePin, u32)> {
    let base = &input.cohort.sha256;
    let mut rows = vec![
        (
            format!("etc/droidloom/cohorts/{base}.json"),
            input.cohort.clone(),
            0o400,
        ),
        (
            format!(
                "etc/droidloom/runtime-cohorts/{}.json",
                input.runtime.sha256
            ),
            input.runtime.clone(),
            0o400,
        ),
        (
            format!(
                "etc/droidloom/board-devices/{}.json",
                input.device_manifest.sha256
            ),
            input.device_manifest.clone(),
            0o444,
        ),
        (
            format!(
                "var/lib/droidloom/cohorts/{base}/board/{}.img",
                input.device_bank.sha256
            ),
            input.device_bank.clone(),
            0o444,
        ),
    ];
    for role in ROLES {
        rows.push((
            format!("var/lib/droidloom/cohorts/{base}/images/{role}.img"),
            input.images[role].clone(),
            0o400,
        ));
    }
    for role in activation_query::fixed::INPUTS {
        rows.push((
            format!(
                "var/lib/droidloom/runtime-cohorts/{}/images/{}",
                input.runtime.sha256, role.output_name
            ),
            input.query_inputs[role.output_name].clone(),
            role.installed_mode(),
        ));
    }
    rows
}
pub(super) fn install_paths(input: &AndroidInputs) -> Result<BTreeSet<String>> {
    require(
        input
            .images
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            == BTreeSet::from(ROLES)
            && input
                .query_inputs
                .keys()
                .map(String::as_str)
                .collect::<BTreeSet<_>>()
                == activation_query::fixed::INPUTS
                    .iter()
                    .map(|r| r.output_name)
                    .collect(),
        "Android install inventory is incomplete",
    )?;
    let mut set: BTreeSet<_> = immutable_files(input)
        .into_iter()
        .map(|(path, _, _)| path)
        .collect();
    set.extend(CONFIGURATION.iter().map(|s| s.to_string()));
    set.extend(
        droidloom_contracts::mac_release::NAMES
            .iter()
            .map(|name| format!("etc/droidloom/host-mac/{name}")),
    );
    set.extend(
        UNITS
            .iter()
            .map(|unit| format!("etc/systemd/system/{unit}")),
    );
    Ok(set)
}
pub(super) struct StagedSelection {
    files: [FilePin; 3],
    expected: [Vec<u8>; 3],
}
pub(super) struct CommittedSelection {
    files: [HeldFile; 3],
}
impl StagedSelection {
    pub(super) fn files(&self) -> &[FilePin; 3] {
        &self.files
    }
    pub(super) fn observe_committed(&self, actual: &[HeldFile; 3]) -> Result<CommittedSelection> {
        let mut files = Vec::new();
        for ((held, expected), path) in actual.iter().zip(&self.expected).zip(CONFIGURATION) {
            require(
                held.pin().path == Path::new("/").join(path)
                    && held.identity().uid == 0
                    && held.identity().gid == 0
                    && held.read_all(MIB)? == *expected,
                "committed configuration is not the exact staged first selection",
            )?;
            let again = HeldFile::open(held.pin(), MIB)?;
            require(
                again.identity() == held.identity(),
                "committed configuration changed during proof transfer",
            )?;
            files.push(again);
        }
        Ok(CommittedSelection {
            files: files
                .try_into()
                .map_err(|_| "configuration cardinality changed")?,
        })
    }
}
impl CommittedSelection {
    pub(super) fn revalidate(&self) -> Result<()> {
        for file in &self.files {
            file.revalidate()?;
            file.read_all(MIB)?;
        }
        Ok(())
    }
    pub(super) fn receipt(&self) -> Value {
        json!({"configuration":self.files.iter().map(HeldFile::pin).collect::<Vec<_>>(),
            "selection_scope":"early_boot_shared_kernel_v1","original_userdata_preserved":true,
            "runtime_admission_observed":false,"production_ready":false})
    }
}
pub(super) fn stage(
    root: &Path,
    input: &AndroidInputs,
    original: &OriginalData,
) -> Result<(StagedSelection, Value)> {
    let admitted = admit(input)?;
    let base = &input.cohort.sha256;
    let sources = [
        &admitted.cohort,
        &admitted.runtime,
        &admitted.device,
        &admitted.bank,
    ];
    let locations = immutable_files(input);
    for ((path, _, mode), source) in locations[..4].iter().zip(sources) {
        install(root, path, source, *mode)?;
    }
    for (role, source) in ROLES.iter().zip(&admitted.images) {
        install(
            root,
            &format!("var/lib/droidloom/cohorts/{base}/images/{role}.img"),
            source,
            0o400,
        )?;
    }
    let query = activation_query::stage(root, &admitted.query)?;
    let mac = activation_mac::stage(root, &input.mac_release, base, &input.runtime.sha256)?;
    let expected = expected_configuration(root, input, original)?;
    let mut pins = Vec::new();
    for (index, (path, bytes)) in CONFIGURATION.iter().zip(&expected).enumerate() {
        pins.push(files::write_new(
            &destination(root, path)?,
            bytes,
            if index == 1 { 0o400 } else { 0o644 },
        )?);
    }
    for unit in UNITS {
        let pin = files::pin_file(&root.join(format!("usr/share/droidloom/production/{unit}")))?;
        let file = HeldFile::open(&pin, 64 * 1024)?;
        install(root, &format!("etc/systemd/system/{unit}"), &file, 0o644)?;
    }
    files::ensure_dir(root, "var/lib/droidloom")?;
    files::private_dir(&root.join("var/lib/droidloom/identity-reservations"))?;
    for file in sources {
        file.revalidate()?;
    }
    for file in &admitted.images {
        file.revalidate()?;
    }
    admitted.template.revalidate()?;
    original.revalidate()?;
    let selection = StagedSelection {
        files: pins
            .try_into()
            .map_err(|_| "configuration cardinality changed")?,
        expected,
    };
    let receipt = json!({"cohort":input.cohort,"runtime":input.runtime,"device_manifest":input.device_manifest,
        "configuration":selection.files,"query":query,"mac":mac,"userdata":original.receipt(),
        "ordinary_units":UNITS,"production_ready":false});
    Ok((selection, receipt))
}
pub(super) fn verify_staged(
    root: &Path,
    input: &AndroidInputs,
    original: &OriginalData,
) -> Result<StagedSelection> {
    // Parse the exact original declarations again; an inventory receipt alone
    // cannot turn a modified stage into an authorized new generation.
    let admitted = admit(input)?;
    for (path, source, mode) in immutable_files(input) {
        let pin = FilePin {
            path: root.join(path),
            bytes: source.bytes,
            sha256: source.sha256,
        };
        let held = HeldFile::open(&pin, 8 * 1024 * 1024 * 1024)?;
        require(
            held.identity().uid == 0
                && held.identity().gid == 0
                && held.identity().mode & 0o7777 == mode,
            "staged Android input lost its original sealed root custody",
        )?;
        files::no_privilege_xattrs(held.file())?;
    }
    activation_mac::verify_staged(
        root,
        &input.mac_release,
        &input.cohort.sha256,
        &input.runtime.sha256,
    )?;
    let expected = expected_configuration(root, input, original)?;
    let mut pins = Vec::new();
    for (index, (path, bytes)) in CONFIGURATION.iter().zip(&expected).enumerate() {
        let pin = FilePin {
            path: root.join(path),
            bytes: bytes.len() as u64,
            sha256: files::digest(bytes),
        };
        let file = HeldFile::open(&pin, MIB)?;
        require(
            file.identity().uid == 0
                && file.identity().gid == 0
                && file.identity().mode & 0o7777 == if index == 1 { 0o400 } else { 0o644 },
            "staged selection custody changed",
        )?;
        pins.push(pin);
    }
    for unit in UNITS {
        let source = files::pin_file(&root.join(format!("usr/share/droidloom/production/{unit}")))?;
        let target = files::pin_file(&root.join(format!("etc/systemd/system/{unit}")))?;
        require(
            source.bytes == target.bytes && source.sha256 == target.sha256,
            "staged native unit differs from normal host",
        )?;
    }
    admitted.cohort.revalidate()?;
    admitted.runtime.revalidate()?;
    original.revalidate()?;
    Ok(StagedSelection {
        files: pins
            .try_into()
            .map_err(|_| "configuration cardinality changed")?,
        expected,
    })
}
