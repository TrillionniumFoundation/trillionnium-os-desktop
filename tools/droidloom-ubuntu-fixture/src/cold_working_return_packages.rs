//! Normal package inverse under a fresh original-kernel owner. The existing
//! source-bound public/native engines retain their package semantics. Only a
//! real completed fixed native command can produce PID1 replacement evidence.
use super::{
    WorkingRecoverySources, configurations::working_package_masks::WorkingPackageMasks,
    materials::Guard, owner::SealedInput,
};
use crate::cold_original_data::WorkingReturnData;
use crate::cold_working_recovery::contract as c;
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    ensure, fs,
};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::Seek,
    os::fd::AsRawFd,
    path::{Path, PathBuf},
    rc::Rc,
};

#[path = "cold_working_return_package_identity.rs"]
mod package_identity;
pub(super) use package_identity::{PackageReplacementAttempt, WorkingPid1PackageReplacement};

const PYTHON_BYTES: u64 = 7_477_160;
const PYTHON_SHA: &str = "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41";
const REQUEST: &str = "droidloom.working-fixed-command.v1";
const RESPONSE: &str = "droidloom.working-fixed-command-result.v1";

#[derive(Clone, Copy, PartialEq, Eq)]
enum Operation {
    OriginalMember,
    NativeRollback,
    PublicRollback,
    Reload,
    StopWriters,
    RestoreWriters,
}
impl Operation {
    fn name(self) -> &'static str {
        match self {
            Self::OriginalMember => "working-original-systemd",
            Self::NativeRollback => "native-rollback",
            Self::PublicRollback => "public-rollback",
            Self::Reload => "systemctl",
            Self::StopWriters => "package-writers-stop",
            Self::RestoreWriters => "package-writers-restore",
        }
    }
    fn seconds(self) -> u64 {
        if matches!(self, Self::NativeRollback | Self::PublicRollback) {
            600
        } else {
            180
        }
    }
}
fn driver() -> Result<String> {
    let body = super::working_packages::driver()?;
    let marker = "if op=='public-snapshot':";
    ensure(
        body.matches(marker).count() == 1,
        "normal package source changed its fixed operation boundary",
    )?;
    let branch = r#"if op=='working-original-systemd':
 need(arg=={},'fixed original systemd probe has no caller path or package selector')
 payloads=normal_tool_payloads()
 row=payloads['systemd']['old']['payload']['usr/lib/systemd/systemd']
 need(row['type']=='0' and row['mode']==0o755 and row['uid']==row['gid']==0,'normal original systemd member authority')
 need(0<row['bytes']<=128*1024**2 and re.fullmatch('[0-9a-f]{64}',row['sha256']),'normal original systemd complete bytes')
 result={'path':'/usr/lib/systemd/systemd','bytes':row['bytes'],'sha256':row['sha256'],'mode':0o755,'uid':0,'gid':0,'native_release':m['native_release'],'native_release_id':m['native_release_id'],'package_kind':'old'}
elif op=='public-snapshot':"#;
    Ok(body.replacen(marker, branch, 1))
}
fn save(path: &Path, value: &Value) -> Result<SealedInput> {
    let bytes = serde_json::to_vec(value)?;
    files::write_new(path, &bytes, 0o400)?;
    File::open(path.parent().ok_or("returned package record parent")?)?.sync_all()?;
    SealedInput::open(&files::pin_file(path)?)
}

/// No public constructor or deserializer. invoke() below creates this only
/// after OwnedChild has actually exited/reaped and its full normal output has
/// been read back. A preserved command JSON cannot instantiate this type.
struct ActualPackageCommand {
    operation: Operation,
    request: SealedInput,
    evidence: SealedInput,
    log: Guard,
    actual: Value,
    command: files::CommandResult,
}
impl ActualPackageCommand {
    fn revalidate_custody(&self) -> Result<()> {
        self.request.revalidate()?;
        self.evidence.revalidate()?;
        self.log.revalidate()?;
        ensure(
            self.command.exit_code == Some(0)
                && !self.command.timed_out
                && self.actual["schema"] == RESPONSE
                && self.actual["operation"] == self.operation.name(),
            "actual returned normal command is not a completed successful fixed operation",
        )
    }
}

/// The sole producer is this fixed source function. It retains the actual
/// interpreter descriptor and lets run_logged own/reap its actual child.
/// It deliberately performs only source checks after the command: PID1's
/// old F9 must be adopted by the separate exact replacement proof first.
fn invoke(
    sources: &Rc<WorkingRecoverySources>,
    modules: &[Guard],
    directory: &Path,
    operation: Operation,
    arguments: Value,
) -> Result<ActualPackageCommand> {
    sources.revalidate_normal_source_custody()?;
    let module_root = sources.work().join("working-packages/normal-source");
    ensure(
        modules.len() == crate::boot_host::cold_modules::FILES.len(),
        "complete retained normal module roster required",
    )?;
    for (held, (name, bytes)) in modules.iter().zip(crate::boot_host::cold_modules::FILES) {
        ensure(
            held.pin().path
                == module_root.join(
                    Path::new(name)
                        .file_name()
                        .ok_or("normal module basename")?,
                )
                && held.pin().bytes == bytes.len() as u64
                && held.pin().sha256 == fs::digest(bytes),
            "returned normal package module differs from the compiled producer source",
        )?;
        held.revalidate()?;
    }
    ensure(
        directory.starts_with(sources.work())
            && directory.components().all(|c| {
                matches!(
                    c,
                    std::path::Component::RootDir | std::path::Component::Normal(_)
                )
            }),
        "returned command escaped its source-owned private work",
    )?;
    files::private_dir(directory)?;
    let request = save(
        &directory.join("INPUTS.json"),
        &json!({"schema":REQUEST,
        "candidate_id":sources.candidate(),"intent":sources.boot_intent(),"operation":operation.name(),
        "arguments":arguments,"materials":sources.normal_materials()}),
    )?;
    let body = driver()?;
    let pin = FilePin {
        path: "/usr/bin/python3.14".into(),
        bytes: PYTHON_BYTES,
        sha256: PYTHON_SHA.into(),
    };
    let (python, identity) = files::open_pin(&pin)?;
    ensure(
        identity.uid == 0 && identity.gid == 0 && identity.mode == 0o100755 && identity.nlink == 1,
        "returned normal interpreter is not the actual root executable",
    )?;
    let attributes = fs::xattrs(&python)?;
    let result = files::run_logged(
        directory,
        "normal-package-command",
        &format!("/proc/{}/fd/{}", std::process::id(), python.as_raw_fd()),
        &[
            "-I".into(),
            "-B".into(),
            "-c".into(),
            body.clone(),
            fs::absolute_string(&module_root)?,
            fs::absolute_string(&request.pin().path)?,
        ],
        operation.seconds(),
    )?;
    (&python).rewind()?;
    ensure(
        fs::stat(&python)? == identity
            && fs::hash(&python)? == PYTHON_SHA
            && fs::xattrs(&python)? == attributes
            && fs::Tree::open("/", 0)?.identity("/usr/bin/python3.14")? == identity,
        "normal package operation changed the held interpreter",
    )?;
    request.revalidate()?;
    sources.revalidate_normal_source_custody()?;
    for module in modules {
        module.revalidate()?;
    }
    let log = Guard::open(&result.log)?;
    let actual: Value = serde_json::from_slice(&files::read_pin(&result.log, 64 * 1024 * 1024)?)?;
    ensure(
        result.exit_code == Some(0)
            && !result.timed_out
            && actual["schema"] == RESPONSE
            && actual["operation"] == operation.name()
            && actual["candidate_id"] == sources.candidate()
            && actual["intent"] == serde_json::to_value(sources.boot_intent())?,
        "returned normal output has another actual operation or source",
    )?;
    let evidence = save(
        &directory.join("RESULT.json"),
        &json!({"schema":"droidloom.working-returned-package-command.v1",
        "input":request.pin(),"driver_sha256":fs::digest(body.as_bytes()),"command":result,"actual":actual}),
    )?;
    let value = ActualPackageCommand {
        operation,
        request,
        evidence,
        log,
        actual,
        command: result,
    };
    value.revalidate_custody()?;
    Ok(value)
}

struct OriginalSystemdMember {
    pin: FilePin,
    command: Rc<ActualPackageCommand>,
}
impl OriginalSystemdMember {
    fn from_actual(
        sources: &WorkingRecoverySources,
        command: ActualPackageCommand,
    ) -> Result<Self> {
        command.revalidate_custody()?;
        let value = &command.actual["result"];
        ensure(
            command.operation == Operation::OriginalMember
                && value["path"] == "/usr/lib/systemd/systemd"
                && value["mode"] == 0o755
                && value["uid"] == 0
                && value["gid"] == 0
                && value["package_kind"] == "old"
                && value["native_release"] == sources.normal_materials()["native_release"]
                && value["native_release_id"] == sources.normal_materials()["native_release_id"],
            "actual normal source probe did not identify its original systemd member",
        )?;
        let pin = FilePin {
            path: "/usr/lib/systemd/systemd".into(),
            bytes: value["bytes"]
                .as_u64()
                .ok_or("original systemd byte count")?,
            sha256: value["sha256"]
                .as_str()
                .ok_or("original systemd full hash")?
                .into(),
        };
        ensure(
            pin.bytes > 0 && pin.bytes <= 128 * 1024 * 1024 && fs::valid_digest(&pin.sha256),
            "original systemd member shape differs",
        )?;
        Ok(Self {
            pin,
            command: Rc::new(command),
        })
    }
}

/// Only the actual native rollback path below can create this success object.
/// The independent child proof also compares the same live attempt Rc.
pub(super) struct CompletedPackageCommand {
    attempt: Rc<PackageReplacementAttempt>,
    sources: Rc<WorkingRecoverySources>,
    native_snapshot: Guard,
    original_systemd: FilePin,
    original_probe: Rc<ActualPackageCommand>,
    actual: ActualPackageCommand,
}
impl CompletedPackageCommand {
    fn from_actual(
        attempt: Rc<PackageReplacementAttempt>,
        sources: Rc<WorkingRecoverySources>,
        snapshot: &FilePin,
        original: &OriginalSystemdMember,
        actual: ActualPackageCommand,
    ) -> Result<Self> {
        attempt.require_sources(&sources)?;
        ensure(
            actual.operation == Operation::NativeRollback,
            "only actual native inverse can construct a PID1 replacement result",
        )?;
        let value = Self {
            attempt,
            sources,
            native_snapshot: Guard::open(snapshot)?,
            original_systemd: original.pin.clone(),
            original_probe: original.command.clone(),
            actual,
        };
        value.require_native_rollback_success()?;
        Ok(value)
    }
    pub(super) fn require_attempt(&self, attempt: &Rc<PackageReplacementAttempt>) -> Result<()> {
        ensure(
            Rc::ptr_eq(&self.attempt, attempt),
            "package completion belongs to a different live replacement attempt",
        )?;
        self.revalidate_custody()
    }
    pub(super) fn revalidate_custody(&self) -> Result<()> {
        self.sources.revalidate_normal_source_custody()?;
        self.native_snapshot.revalidate()?;
        self.original_probe.revalidate_custody()?;
        self.actual.revalidate_custody()
    }
    pub(super) fn native_snapshot(&self) -> &FilePin {
        self.native_snapshot.pin()
    }
    pub(super) fn result_pin(&self) -> &FilePin {
        self.actual.evidence.pin()
    }
    pub(super) fn original_systemd_member(&self) -> &FilePin {
        &self.original_systemd
    }
    pub(super) fn require_native_rollback_success(&self) -> Result<()> {
        self.revalidate_custody()?;
        ensure(
            self.actual.operation == Operation::NativeRollback
                && self.actual.actual["candidate_id"] == self.sources.candidate()
                && self.actual.actual["intent"]
                    == serde_json::to_value(self.sources.boot_intent())?
                && self.actual.actual["result"]["kind"] == "native"
                && self.actual.actual["result"]["snapshot"]
                    == serde_json::to_value(self.native_snapshot.pin())?,
            "completed native rollback lost its actual exact snapshot/result binding",
        )
    }
}

struct SnapshotSource {
    result: Value,
    guard: Guard,
}
impl SnapshotSource {
    fn open(result: Value, native: bool) -> Result<Self> {
        ensure(
            result["kind"] == if native { "native" } else { "public" },
            "actual normal snapshot kind differs",
        )?;
        let pin: FilePin = serde_json::from_value(result["snapshot"].clone())?;
        ensure(
            pin.path.file_name() == Some(std::ffi::OsStr::new("SNAPSHOT.json"))
                && pin
                    .path
                    .parent()
                    .is_some_and(|p| p == Path::new(result["directory"].as_str().unwrap_or(""))),
            "normal package snapshot left its actual durable transaction directory",
        )?;
        let value = Self {
            result,
            guard: Guard::open(&pin)?,
        };
        value.arguments(native)?;
        Ok(value)
    }
    fn arguments(&self, native: bool) -> Result<Value> {
        self.guard.revalidate()?;
        if native {
            let name = self.result["attempt"]
                .as_str()
                .ok_or("actual native attempt missing")?;
            ensure(
                self.guard
                    .pin()
                    .path
                    .parent()
                    .and_then(Path::file_name)
                    .and_then(|p| p.to_str())
                    == Some(name),
                "native original snapshot differs from its actual attempt",
            )?;
            Ok(json!({"snapshot":self.guard.pin(),"attempt":name}))
        } else {
            Ok(json!({"snapshot":self.guard.pin()}))
        }
    }
}
struct ForwardSources {
    records: Vec<SealedInput>,
    public: SnapshotSource,
    native: SnapshotSource,
    writers: Guard,
    mask: SealedInput,
}
fn original_commands(sources: &WorkingRecoverySources) -> Result<ForwardSources> {
    sources.revalidate_custody()?;
    let root = sources.work().join("working-packages/commands");
    let tree = fs::Tree::open("/", 0)?;
    tree.dir(&fs::absolute_string(&root)?)?;
    let mut names = BTreeSet::new();
    for item in std::fs::read_dir(&root)? {
        let name = item?
            .file_name()
            .into_string()
            .map_err(|_| "normal command directory is not UTF8")?;
        ensure(
            names.len() < 64
                && name.len() > 5
                && name.as_bytes().get(4) == Some(&b'-')
                && name[..4].bytes().all(|b| b.is_ascii_digit())
                && names.insert(name),
            "normal original command roster is outside its fixed bounded source",
        )?;
    }
    let mut records = Vec::new();
    let mut snapshots = BTreeMap::new();
    let mut writers = None;
    let driver_sha = fs::digest(super::working_packages::driver()?.as_bytes());
    for name in names {
        let directory = root.join(&name);
        let input = SealedInput::open(&files::pin_file(&directory.join("INPUTS.json"))?)?;
        let value: Value = serde_json::from_slice(&input.read()?)?;
        let operation = value["operation"]
            .as_str()
            .ok_or("actual old normal operation missing")?;
        ensure(
            value["schema"] == REQUEST
                && value["candidate_id"] == sources.candidate()
                && value["intent"] == serde_json::to_value(sources.boot_intent())?
                && value["materials"] == *sources.normal_materials()
                && name[5..] == *operation,
            "old normal command belongs to another source or operation",
        )?;
        if operation == "package-writers-stop" {
            ensure(
                writers.is_none(),
                "normal forward has multiple writer authorities",
            )?;
            let pin = files::pin_file(&directory.join("WRITERS-INTENT.json"))?;
            let held = Guard::open(&pin)?;
            let old: Value = serde_json::from_slice(&files::read_pin(&pin, 1024 * 1024)?)?;
            ensure(
                old["schema"] == "droidloom.working-package-writers.v1"
                    && old["candidate_id"] == sources.candidate()
                    && old["intent"] == serde_json::to_value(sources.boot_intent())?
                    && old["source"] == sources.normal_materials()["native_release"]
                    && old["units"] == serde_json::to_value(c::PACKAGE_WRITERS)?,
                "original writer inventory changed its real normal source",
            )?;
            writers = Some(held);
        }
        if matches!(operation, "public-snapshot" | "native-snapshot") {
            let report = SealedInput::open(&files::pin_file(&directory.join("RESULT.json"))?)?;
            let result: Value = serde_json::from_slice(&report.read()?)?;
            ensure(
                result["schema"] == "droidloom.working-normal-package-command.v1"
                    && result["input"] == serde_json::to_value(input.pin())?
                    && result["driver_sha256"] == driver_sha
                    && result["command"]["exit_code"] == 0
                    && result["command"]["timed_out"] == false
                    && result["actual"]["schema"] == RESPONSE
                    && result["actual"]["operation"] == operation
                    && result["actual"]["candidate_id"] == sources.candidate()
                    && result["actual"]["intent"] == serde_json::to_value(sources.boot_intent())?,
                "returned snapshot has no exact successful normal source observation",
            )?;
            ensure(
                snapshots
                    .insert(
                        operation.to_owned(),
                        SnapshotSource::open(
                            result["actual"]["result"].clone(),
                            operation == "native-snapshot",
                        )?,
                    )
                    .is_none(),
                "returned normal source repeats an original package snapshot",
            )?;
            records.push(report);
        }
        records.push(input);
    }
    let mask = SealedInput::open(&files::pin_file(
        &sources.work().join("working-packages/MASKS-INTENT.json"),
    )?)?;
    Ok(ForwardSources {
        records,
        public: snapshots
            .remove("public-snapshot")
            .ok_or("actual public original snapshot absent")?,
        native: snapshots
            .remove("native-snapshot")
            .ok_or("actual native original snapshot absent")?,
        writers: writers.ok_or("actual original writer inventory absent")?,
        mask,
    })
}

pub(super) struct WorkingReturnedPackages {
    sources: Rc<WorkingRecoverySources>,
    forward: ForwardSources,
    modules: Vec<Guard>,
    epoch: PathBuf,
    serial: u32,
    commands: Vec<ActualPackageCommand>,
    masks: WorkingPackageMasks,
    mask_source: SealedInput,
    original_member: Option<OriginalSystemdMember>,
    preservation: Option<SealedInput>,
    native_attempted: bool,
    native_done: Option<WorkingPid1PackageReplacement>,
    public_attempted: bool,
    public_done: bool,
    packages_done: bool,
    report: Option<SealedInput>,
}
impl WorkingReturnedPackages {
    pub(super) fn prepare(data: &WorkingReturnData) -> Result<Self> {
        data.revalidate()?;
        let sources = data.sources().clone();
        let forward = original_commands(&sources)?;
        let mut modules = Vec::new();
        for (name, bytes) in crate::boot_host::cold_modules::FILES {
            let pin = FilePin {
                path: sources.work().join("working-packages/normal-source").join(
                    Path::new(name)
                        .file_name()
                        .ok_or("normal module basename")?,
                ),
                bytes: bytes.len() as u64,
                sha256: fs::digest(bytes),
            };
            modules.push(Guard::open(&pin)?);
        }
        let old_private = Path::new("/run").join(format!(
            "droidloom-working-packages-{}",
            sources.candidate()
        ));
        WorkingPackageMasks::retire_returned(
            &sources,
            forward.mask.pin(),
            sources.original_boot_id(),
            &old_private,
        )?;
        // Earlier failed return owners may have left their own exact current-
        // boot masks. Retire only source-bound plans at the finite data epochs.
        let mut prior = Vec::new();
        for entry in std::fs::read_dir(sources.work())? {
            let name = entry?
                .file_name()
                .into_string()
                .map_err(|_| "returned source work name")?;
            if let Some(rest) = name.strip_prefix("working-return-data-") {
                let (boot, number) = rest.rsplit_once('-').ok_or("returned data epoch shape")?;
                ensure(
                    c::uuid(boot)
                        && number.len() == 2
                        && number.bytes().all(|b| b.is_ascii_digit())
                        && number.parse::<usize>()? < 32
                        && prior.len() < 1024,
                    "returned data epoch exceeds its source bound",
                )?;
                let mask = sources
                    .work()
                    .join(&name)
                    .join("packages/MASKS-INTENT.json");
                match std::fs::symlink_metadata(&mask) {
                    Ok(_) => prior.push((boot.to_owned(), number.to_owned(), mask)),
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                    Err(e) => return Err(e.into()),
                }
            }
        }
        for (boot, number, path) in prior {
            let pin = files::pin_file(&path)?;
            let private = Path::new("/run").join(format!(
                "droidloom-working-return-packages-{}-{boot}-{number}",
                sources.candidate()
            ));
            WorkingPackageMasks::retire_returned(&sources, &pin, &boot, &private)?;
        }
        let data_epoch = data
            .report()
            .path
            .parent()
            .ok_or("fresh actual data epoch absent")?;
        let number = data_epoch
            .file_name()
            .and_then(|s| s.to_str())
            .and_then(|s| s.rsplit_once('-'))
            .ok_or("actual data epoch ordinal")?
            .1
            .parse::<usize>()?;
        let epoch = data_epoch.join("packages");
        files::private_dir(&epoch)?;
        files::private_dir(&epoch.join("commands"))?;
        let masks = WorkingPackageMasks::prepare_returned(&sources, number)?;
        let mask_source = save(&epoch.join("MASKS-INTENT.json"), &masks.comparison())?;
        let mut value = Self {
            sources,
            forward,
            modules,
            epoch,
            serial: 0,
            commands: Vec::new(),
            masks,
            mask_source,
            original_member: None,
            preservation: None,
            native_attempted: false,
            native_done: None,
            public_attempted: false,
            public_done: false,
            packages_done: false,
            report: None,
        };
        value.masks.publish()?;
        value.fence(data)?;
        let reload = value.call(data, Operation::Reload, json!({"argv":["daemon-reload"]}))?;
        ensure(
            reload["exit"] == 0,
            "returned package masks did not reach actual PID1",
        )?;
        value.call(
            data,
            Operation::StopWriters,
            json!({"units":c::PACKAGE_WRITERS}),
        )?;
        let directory = value.next_directory(Operation::OriginalMember)?;
        let observed = invoke(
            &value.sources,
            &value.modules,
            &directory,
            Operation::OriginalMember,
            json!({}),
        )?;
        value.original_member = Some(OriginalSystemdMember::from_actual(
            &value.sources,
            observed,
        )?);
        value.fence(data)?;
        Ok(value)
    }
    fn source_custody(&self) -> Result<()> {
        self.sources.revalidate_normal_source_custody()?;
        for source in &self.forward.records {
            source.revalidate()?;
        }
        self.forward.public.guard.revalidate()?;
        self.forward.native.guard.revalidate()?;
        self.forward.writers.revalidate()?;
        self.forward.mask.revalidate()?;
        for module in &self.modules {
            module.revalidate()?;
        }
        self.mask_source.revalidate()?;
        if let Some(value) = &self.preservation {
            value.revalidate()?;
        }
        for command in &self.commands {
            command.revalidate_custody()?;
        }
        if let Some(original) = &self.original_member {
            original.command.revalidate_custody()?;
        }
        if let Some(proof) = &self.native_done {
            proof.revalidate()?;
        }
        if let Some(report) = &self.report {
            report.revalidate()?;
        }
        Ok(())
    }
    fn fence(&self, data: &WorkingReturnData) -> Result<()> {
        data.require_sources(&self.sources)?;
        data.revalidate_custody()?;
        self.source_custody()?;
        self.masks.guard()?;
        self.sources.owner().revalidate()
    }
    fn next_directory(&mut self, operation: Operation) -> Result<PathBuf> {
        ensure(
            self.serial < 16,
            "returned normal package operation count exhausted",
        )?;
        self.serial += 1;
        Ok(self
            .epoch
            .join("commands")
            .join(format!("{:04}-{}", self.serial, operation.name())))
    }
    fn call(
        &mut self,
        data: &WorkingReturnData,
        operation: Operation,
        arguments: Value,
    ) -> Result<Value> {
        ensure(
            operation != Operation::NativeRollback,
            "native inverse requires its live PID1 replacement attempt",
        )?;
        self.fence(data)?;
        let directory = self.next_directory(operation)?;
        let result = invoke(
            &self.sources,
            &self.modules,
            &directory,
            operation,
            arguments,
        )?;
        let actual = result.actual["result"].clone();
        self.commands.push(result);
        self.fence(data)?;
        Ok(actual)
    }
    pub(super) fn bind_labels(&mut self, data: &WorkingReturnData) -> Result<()> {
        self.fence(data)?;
        let labels = data.returned_label_history()?;
        labels.revalidate()?;
        let mut snapshots = serde_json::Map::new();
        let mut paths = BTreeSet::new();
        for (kind, source, field) in [
            ("public", &self.forward.public, "preserved_metadata_only"),
            ("native", &self.forward.native, "private_metadata"),
        ] {
            let body: Value =
                serde_json::from_slice(&files::read_pin(source.guard.pin(), 16 * 1024 * 1024)?)?;
            let original = body[field]
                .as_object()
                .ok_or("actual normal preservation roster missing")?;
            ensure(
                !original.is_empty() && original.len() <= 32,
                "normal preservation roster exceeds source bound",
            )?;
            for (name, old) in original {
                if kind == "native" && old["absent"] == true {
                    continue;
                }
                let path = PathBuf::from(if name.starts_with('/') {
                    name.clone()
                } else {
                    format!("/{name}")
                });
                fs::absolute_string(&path)?;
                paths.insert(path);
            }
            snapshots.insert(
                kind.into(),
                json!({"snapshot":source.guard.pin(),"original":original}),
            );
        }
        let value = json!({"schema":"droidloom.working-package-preservation.v1","candidate_id":self.sources.candidate(),
            "intent":self.sources.boot_intent(),"actual_label_restoration":labels.report(),
            "snapshots":snapshots,"metadata":labels.preserved_metadata(&paths)?});
        let path = self.sources.work().join(format!(
            "NORMAL-PACKAGE-PRESERVATION-{}.json",
            labels.report().sha256
        ));
        let preservation = match std::fs::symlink_metadata(&path) {
            Ok(_) => {
                let held = SealedInput::open(&files::pin_file(&path)?)?;
                ensure(
                    serde_json::from_slice::<Value>(&held.read()?)? == value,
                    "normal preservation handoff was rewritten",
                )?;
                held
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => save(&path, &value)?,
            Err(e) => return Err(e.into()),
        };
        self.preservation = Some(preservation);
        self.fence(data)
    }
    fn arguments(&self, native: bool) -> Result<Value> {
        let mut value = if native {
            self.forward.native.arguments(true)?
        } else {
            self.forward.public.arguments(false)?
        };
        let proof = self
            .preservation
            .as_ref()
            .ok_or("actual completed label preservation missing")?;
        proof.revalidate()?;
        value.as_object_mut().unwrap().insert(
            "restored_metadata".into(),
            serde_json::to_value(proof.pin())?,
        );
        Ok(value)
    }
    pub(super) fn restore_packages(&mut self, data: &WorkingReturnData) -> Result<()> {
        data.verify_original_restored()?;
        self.fence(data)?;
        if self.packages_done {
            return Ok(());
        }
        if self.native_done.is_none() {
            ensure(
                !self.native_attempted,
                "unknown native inverse requires a newly acquired recovery owner",
            )?;
            let arguments = self.arguments(true)?;
            let attempt = PackageReplacementAttempt::begin(
                self.sources.clone(),
                self.forward.native.guard.pin(),
            )?;
            let directory = self.next_directory(Operation::NativeRollback)?;
            self.native_attempted = true;
            let actual = invoke(
                &self.sources,
                &self.modules,
                &directory,
                Operation::NativeRollback,
                arguments,
            )?;
            let completed = CompletedPackageCommand::from_actual(
                attempt.clone(),
                self.sources.clone(),
                self.forward.native.guard.pin(),
                self.original_member
                    .as_ref()
                    .ok_or("actual original systemd source member missing")?,
                actual,
            )?;
            let proof = attempt.complete(completed)?;
            self.sources
                .owner()
                .accept_package_replacement_custody(&proof)?;
            self.native_done = Some(proof);
            data.retirement().revalidate()?;
            self.fence(data)?;
        }
        if !self.public_done {
            ensure(
                !self.public_attempted,
                "unknown public inverse requires a newly acquired recovery owner",
            )?;
            let arguments = self.arguments(false)?;
            self.public_attempted = true;
            self.call(data, Operation::PublicRollback, arguments)?;
            self.public_done = true;
        }
        self.fence(data)?;
        self.packages_done = true;
        Ok(())
    }
    pub(super) fn finish(&mut self, data: &WorkingReturnData) -> Result<FilePin> {
        self.fence(data)?;
        data.verify_original_restored()?;
        ensure(
            self.packages_done && self.native_done.is_some() && self.public_done,
            "returned normal packages are not actually restored",
        )?;
        if let Some(report) = &self.report {
            return Ok(report.pin().clone());
        }
        self.masks.restore()?;
        let reload = self.call(data, Operation::Reload, json!({"argv":["daemon-reload"]}))?;
        ensure(
            reload["exit"] == 0,
            "normal returned masks were not reloaded",
        )?;
        let writers = self.forward.writers.pin().clone();
        let original_requests = self.call(
            data,
            Operation::RestoreWriters,
            json!({"units":c::PACKAGE_WRITERS,"original":writers}),
        )?;
        let value = json!({"schema":"droidloom.working-returned-normal-packages.v1","candidate_id":self.sources.candidate(),
            "actual_data_retirement":data.report(),"public_snapshot":self.forward.public.guard.pin(),
            "native_snapshot":self.forward.native.guard.pin(),"actual_pid1_replacement":self.native_done.as_ref().unwrap().report_pin(),
            "commands":self.commands.iter().map(|c|c.evidence.pin()).collect::<Vec<_>>(),
            "actual_preservation":self.preservation.as_ref().unwrap().pin(),"original_writer_requests":original_requests,
            "normal_packages_restored":true,"owned_runtime_masks_restored":true,"production_ready":false});
        self.report = Some(save(&self.epoch.join("RESTORED.json"), &value)?);
        self.fence(data)?;
        data.revalidate()?;
        Ok(self.report.as_ref().unwrap().pin().clone())
    }
}
