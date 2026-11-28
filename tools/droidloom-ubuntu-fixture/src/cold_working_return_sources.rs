//! Fresh read-only comparison inputs for returned working qualification.
//! The fresh original-kernel owner is acquired independently. Historical files
//! bind the fixed candidate and normal software; none reconstructs an old lease.
use super::{WorkingReturnOwner, materials::Guard, owner::SealedInput};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::labels::OriginalLabelRestoreSources,
    cold_working_recovery::contract::{self as c, WorkingReturnConfiguration},
    ensure, fs,
    model::Identity,
};
use serde_json::Value;
use std::{
    collections::BTreeMap,
    fs::File,
    path::{Path, PathBuf},
    rc::Rc,
};
#[path = "cold_working_retained_contract.rs"]
mod retained;
pub(crate) use retained::RETAINED_PAIR_HASH_SECONDS as RETAINED_ORIGINAL_HASH_SECONDS;
pub(crate) use retained::RetainedOriginalsSpec;

fn same_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
fn pin(value: &Value) -> Result<FilePin> {
    Ok(serde_json::from_value(value.clone())?)
}
fn text<'a>(value: &'a Value, name: &str) -> Result<&'a str> {
    value[name]
        .as_str()
        .ok_or_else(|| format!("returned source lacks {name}").into())
}
fn read(value: &SealedInput, limit: u64) -> Result<Value> {
    ensure(
        value.pin().bytes <= limit,
        "returned source exceeds its fixed bound",
    )?;
    Ok(serde_json::from_slice(&value.read()?)?)
}
fn bind_pin(value: &Value, wanted: &FilePin) -> Result<()> {
    ensure(
        same_pin(&pin(value)?, wanted),
        "returned source pin differs from its actual preserved member",
    )
}
fn fixed(work: &Path, name: &str, limit: u64) -> Result<SealedInput> {
    ensure(
        !name.contains('/') && !name.is_empty(),
        "fixed returned source name required",
    )?;
    let path = work.join(name);
    let tree = fs::Tree::open("/", 0)?;
    let held = tree.file(&fs::absolute_string(&path)?)?;
    let before = fs::stat(&held)?;
    ensure(
        before.uid == 0
            && before.gid == 0
            && before.nlink == 1
            && before.mode & 0o7777 == 0o400
            && before.size > 0
            && before.size <= limit,
        "returned source lost its actual protected bounded inode",
    )?;
    let input = files::pin_file(&path)?;
    ensure(
        fs::stat(&held)? == before
            && input.bytes == before.size
            && tree.identity(&fs::absolute_string(&path)?)? == before,
        "returned source changed during complete source pinning",
    )?;
    SealedInput::open(&input)
}
pub(crate) struct ReturnedRuntimeFile {
    pub(crate) destination: PathBuf,
    pub(crate) source: FilePin,
    pub(crate) mode: u32,
}
pub(crate) struct WorkingRecoverySources {
    owner: Rc<WorkingReturnOwner>,
    work: PathBuf,
    directory: File,
    directory_identity: Identity,
    records: BTreeMap<&'static str, SealedInput>,
    guards: Vec<Guard>,
    normal: OriginalLabelRestoreSources,
    configuration: WorkingReturnConfiguration,
    original_boot_id: String,
    first_once: String,
    runtime_files: Vec<ReturnedRuntimeFile>,
    retained: RetainedOriginalsSpec,
    cold_clone: FilePin,
    data_intent: FilePin,
    selection: FilePin,
    original_cell: FilePin,
}
impl WorkingRecoverySources {
    pub(crate) fn open(owner: Rc<WorkingReturnOwner>) -> Result<Self> {
        owner.revalidate()?;
        let input = SealedInput::open(owner.input_pin())?;
        let plan = read(&input, 16 * 1024 * 1024)?;
        ensure(
            plan["schema"] == "droidloom.working-qualification-material-plan.v1"
                && plan["candidate_id"] == owner.candidate()
                && fs::valid_digest(text(&plan, "first_once_candidate")?)
                && plan["first_once_candidate"] != plan["candidate_id"]
                && c::uuid(text(&plan, "original_boot_id")?),
            "returned owner input is not one exact distinct working material plan",
        )?;
        bind_pin(&plan["normal_producer"], owner.program_pin())?;
        let work = Path::new("/var/lib/droidloom-qualification")
            .join(format!("working-qualification-{}", owner.candidate()));
        let directory = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(&work)?)?;
        let directory_identity = fs::stat(&directory)?;
        ensure(
            directory_identity.uid == 0
                && directory_identity.gid == 0
                && directory_identity.mode & 0o7777 == 0o700,
            "returned working source directory lost its fixed root protection",
        )?;
        let mut records = BTreeMap::new();
        for name in [
            "MATERIALS-INTENT.json",
            "ADMITTED-MATERIALS.json",
            "BOOT-INTENT.json",
            "WORKING-RUNTIME-PREPARED.json",
            "WORKING-RETURN.json",
            "WORKING-RETAINED-ORIGINALS.json",
            "DATA-EXCHANGE-INTENT.json",
        ] {
            records.insert(name, fixed(&work, name, 16 * 1024 * 1024)?);
        }
        let material = read(&records["MATERIALS-INTENT.json"], 16 * 1024 * 1024)?;
        let admitted = read(&records["ADMITTED-MATERIALS.json"], 16 * 1024 * 1024)?;
        let boot = read(&records["BOOT-INTENT.json"], 16 * 1024 * 1024)?;
        let runtime = read(&records["WORKING-RUNTIME-PREPARED.json"], 16 * 1024 * 1024)?;
        for (value, schema) in [
            (
                &material,
                "droidloom.working-qualification-material-intent.v1",
            ),
            (
                &admitted,
                "droidloom.working-qualification-admitted-materials.v1",
            ),
            (&boot, "droidloom.working-qualification-boot-intent.v1"),
            (
                &runtime,
                "droidloom.working-qualification-runtime-prepared.v1",
            ),
        ] {
            ensure(
                value["schema"] == schema && value["candidate_id"] == owner.candidate(),
                "returned historical source has another schema or candidate",
            )?;
        }
        bind_pin(&admitted["input"], owner.input_pin())?;
        bind_pin(
            &material["admitted_materials"],
            records["ADMITTED-MATERIALS.json"].pin(),
        )?;
        bind_pin(
            &boot["material_intent"],
            records["MATERIALS-INTENT.json"].pin(),
        )?;
        bind_pin(
            &boot["admitted_materials"],
            records["ADMITTED-MATERIALS.json"].pin(),
        )?;
        bind_pin(&material["normal_producer"], owner.program_pin())?;
        bind_pin(&boot["normal_producer"], owner.program_pin())?;
        bind_pin(&runtime["boot_intent"], records["BOOT-INTENT.json"].pin())?;
        bind_pin(
            &runtime["return_configuration"],
            records["WORKING-RETURN.json"].pin(),
        )?;
        ensure(
            material["work_directory"] == fs::absolute_string(&work)?
                && material["original_boot_id"] == plan["original_boot_id"]
                && boot["original_boot_id"] == plan["original_boot_id"]
                && material["first_once_candidate"] == plan["first_once_candidate"]
                && admitted["first_once_candidate"] == plan["first_once_candidate"]
                && boot["first_once_candidate"] == plan["first_once_candidate"]
                && material["root_uuid"] == c::ROOT_UUID
                && boot["root_uuid"] == c::ROOT_UUID
                && material["original_kernel"] == c::ORIGINAL_KERNEL
                && boot["original_kernel"] == c::ORIGINAL_KERNEL
                && material["original_entry"] == c::ORIGINAL_ENTRY
                && boot["original_entry"] == c::ORIGINAL_ENTRY,
            "returned source changed its original machine, boot or first-once provenance",
        )?;
        let normal_pin = pin(&material["normal_sources"])?;
        bind_pin(&admitted["normal_sources"], &normal_pin)?;
        bind_pin(&boot["normal_sources"], &normal_pin)?;
        let normal = OriginalLabelRestoreSources::reopen(&normal_pin)?;
        let historical = normal.historical_initramfs_readback();
        ensure(
            historical["host_source_commit"] == material["host_source_commit"]
                && historical["host_source_tree"] == material["host_source_tree"]
                && boot["host_source_commit"] == material["host_source_commit"]
                && boot["host_source_tree"] == material["host_source_tree"]
                && historical["normal_materials"]["deployment_id"] == owner.candidate()
                && historical["normal_materials"]["public_release_id"]
                    == material["normal_public_release_id"]
                && historical["normal_materials"]["native_release_id"]
                    == material["normal_native_release_id"],
            "returned source does not identify its actual archived normal release",
        )?;
        let configuration: WorkingReturnConfiguration =
            serde_json::from_slice(&records["WORKING-RETURN.json"].read()?)?;
        configuration.validate()?;
        ensure(
            configuration.candidate_id == owner.candidate()
                && configuration.first_once_candidate == text(&plan, "first_once_candidate")?
                && configuration.original_boot_id == text(&plan, "original_boot_id")?
                && configuration.intent_sha256 == records["BOOT-INTENT.json"].pin().sha256,
            "returned runtime configuration differs from the exact material/boot sources",
        )?;
        let retained: RetainedOriginalsSpec =
            serde_json::from_slice(&records["WORKING-RETAINED-ORIGINALS.json"].read()?)?;
        retained.validate()?;
        ensure(
            retained.candidate_id == owner.candidate(),
            "retained original images belong to another candidate",
        )?;
        bind_pin(
            &admitted["retained_originals"],
            records["WORKING-RETAINED-ORIGINALS.json"].pin(),
        )?;
        let cold_clone = pin(&admitted["historical_cold_clone"])?;
        ensure(
            cold_clone.bytes == 2843
                && cold_clone.sha256
                    == "3eda27b424c264102e609fbb87392b4d34e14ce8440d1ab40ab250131fc92ca0",
            "returned source lost the exact original cold-copy provenance",
        )?;
        let cold_guard = Guard::open(&cold_clone)?;
        let cold: Value = serde_json::from_slice(&files::read_pin(&cold_clone, 65536)?)?;
        let rows = cold["rows"]
            .as_array()
            .ok_or("retained original hash source lacks rows")?;
        ensure(
            cold["schema"] == "pocket4-original-data-cold-compatibility-clone-v1"
                && rows.len() == 2,
            "retained original hash source changed schema or role count",
        )?;
        for (i, (entry, name)) in retained
            .files
            .iter()
            .zip(["data.img", "metadata.img"])
            .enumerate()
        {
            ensure(
                entry.name == name
                    && rows[i]["sha256"] == entry.sha256
                    && rows[i]["bytes"] == entry.snapshot.identity.size
                    && rows[i]["source_path"]
                        == format!("/var/lib/droidloom/users/1000/data/{name}"),
                "retained original complete hash is not the admitted original-image source",
            )?;
        }
        let data = read(&records["DATA-EXCHANGE-INTENT.json"], 128 * 1024)?;
        ensure(
            data["schema"] == "droidloom.working-qualification-data-intent.v1"
                && data["first_once_candidate"] == plan["first_once_candidate"]
                && data["data"]["schema"] == "droidloom.working-data-exchange-intent.v1"
                && data["data"]["candidate_id"] == owner.candidate()
                && data["data"]["original_boot_id"] == plan["original_boot_id"]
                && data["data"]["work"] == fs::absolute_string(&work)?
                && data["normal_return_configuration"] == serde_json::to_value(&configuration)?,
            "returned data intent is not this actual current working source",
        )?;
        bind_pin(&data["boot_intent"], records["BOOT-INTENT.json"].pin())?;
        bind_pin(&data["data"]["cold_clone"], &cold_clone)?;
        let selection = pin(&material["selection"])?;
        bind_pin(&boot["selection"], &selection)?;
        bind_pin(&runtime["selection"], &selection)?;
        bind_pin(&data["data"]["selection"], &selection)?;
        ensure(
            configuration.selection.bytes == selection.bytes
                && configuration.selection.sha256 == selection.sha256,
            "returned selection differs from the source-bound runtime configuration",
        )?;
        let original_cell = pin(&material["original_cell"])?;
        bind_pin(&admitted["original_cell"], &original_cell)?;
        bind_pin(&boot["original_cell"], &original_cell)?;
        let mut guards = vec![
            cold_guard,
            Guard::open(&selection)?,
            Guard::open(&original_cell)?,
        ];
        let expected = super::working_runtime_roster();
        let rows = runtime["runtime_files"]
            .as_array()
            .ok_or("returned fixed runtime roster absent")?;
        ensure(
            rows.len() == expected.len(),
            "returned runtime roster length changed",
        )?;
        let mut seen = BTreeMap::new();
        let mut runtime_files = Vec::new();
        for row in rows {
            let destination: PathBuf = serde_json::from_value(row["destination"].clone())?;
            let source = pin(&row["source"])?;
            let mode = row["mode"].as_u64().ok_or("returned runtime mode absent")?;
            ensure(
                mode <= 0o777
                    && expected.get(&destination) == Some(&(mode as u32))
                    && seen.insert(destination.clone(), ()).is_none(),
                "returned runtime entry is outside the fixed source roster",
            )?;
            guards.push(Guard::open(&source)?);
            runtime_files.push(ReturnedRuntimeFile {
                destination,
                source,
                mode: mode as u32,
            });
        }
        ensure(
            runtime_files
                .iter()
                .filter(|f| {
                    f.destination == Path::new("/etc/droidloom/cell.json")
                        && f.source.bytes == configuration.cell.bytes
                        && f.source.sha256 == configuration.cell.sha256
                })
                .count()
                == 1,
            "returned cell source is not the one actual runtime member",
        )?;
        let data_intent = records["DATA-EXCHANGE-INTENT.json"].pin().clone();
        let original_boot_id = text(&plan, "original_boot_id")?.to_owned();
        let first_once = text(&plan, "first_once_candidate")?.to_owned();
        records.insert("INPUT", input);
        let result = Self {
            owner,
            work,
            directory,
            directory_identity,
            records,
            guards,
            normal,
            configuration,
            original_boot_id,
            first_once,
            runtime_files,
            retained,
            cold_clone,
            data_intent,
            selection,
            original_cell,
        };
        result.revalidate()?;
        Ok(result)
    }
    pub(crate) fn revalidate_normal_source_custody(&self) -> Result<()> {
        let actual = fs::stat(&self.directory)?;
        let named = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(&self.work)?)?;
        let same = |id: &Identity| {
            (id.dev, id.ino, id.mode, id.uid, id.gid)
                == (
                    self.directory_identity.dev,
                    self.directory_identity.ino,
                    self.directory_identity.mode,
                    self.directory_identity.uid,
                    self.directory_identity.gid,
                )
        };
        ensure(
            same(&actual) && same(&fs::stat(&named)?),
            "returned source workspace changed its actual retained directory",
        )?;
        for record in self.records.values() {
            record.revalidate_custody()?;
        }
        for guard in &self.guards {
            guard.revalidate_custody()?;
        }
        self.normal.revalidate_custody()
    }
    pub(crate) fn revalidate_custody(&self) -> Result<()> {
        self.owner.revalidate()?;
        self.revalidate_normal_source_custody()?;
        self.owner.revalidate()
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.revalidate_custody()?;
        for record in self.records.values() {
            record.revalidate()?;
        }
        for guard in &self.guards {
            guard.revalidate()?;
        }
        self.normal.revalidate()?;
        self.revalidate_custody()
    }
    pub(crate) fn owner(&self) -> &Rc<WorkingReturnOwner> {
        &self.owner
    }
    pub(crate) fn candidate(&self) -> &str {
        self.owner.candidate()
    }
    pub(crate) fn work(&self) -> &Path {
        &self.work
    }
    pub(crate) fn original_boot_id(&self) -> &str {
        &self.original_boot_id
    }
    pub(crate) fn first_once(&self) -> &str {
        &self.first_once
    }
    pub(crate) fn normal_sources(&self) -> &OriginalLabelRestoreSources {
        &self.normal
    }
    pub(crate) fn normal_materials(&self) -> &Value {
        &self.normal.historical_initramfs_readback()["normal_materials"]
    }
    pub(crate) fn boot_intent(&self) -> &FilePin {
        self.records["BOOT-INTENT.json"].pin()
    }
    pub(crate) fn return_configuration_pin(&self) -> &FilePin {
        self.records["WORKING-RETURN.json"].pin()
    }
    pub(crate) fn configuration(&self) -> &WorkingReturnConfiguration {
        &self.configuration
    }
    pub(crate) fn retained(&self) -> &RetainedOriginalsSpec {
        &self.retained
    }
    pub(crate) fn cold_clone(&self) -> &FilePin {
        &self.cold_clone
    }
    pub(crate) fn data_intent(&self) -> &FilePin {
        &self.data_intent
    }
    pub(crate) fn selection(&self) -> &FilePin {
        &self.selection
    }
    pub(crate) fn original_cell(&self) -> &FilePin {
        &self.original_cell
    }
    pub(crate) fn runtime_files(&self) -> &[ReturnedRuntimeFile] {
        &self.runtime_files
    }
}
