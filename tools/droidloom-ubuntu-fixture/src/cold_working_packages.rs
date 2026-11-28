//! Actual H2 normal package installation and rollback under the working owner.
//! The normal public/native engines remain the source of package semantics.
//! This Rust owner selects a closed operation set, retains their immutable
//! snapshots, and records an effect attempt before invoking either mutator.
//! No OriginalQualificationAuthority is created or borrowed.
use super::{
    commands, configurations::working_package_masks::WorkingPackageMasks, materials::Guard,
    owner::SealedInput, working_custody::WorkingColdCustody,
    working_runtime::WorkingRuntimeSources,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_working_recovery::contract as c,
    ensure, fs,
};
use serde_json::{Value, json};
use std::{
    fs::File,
    io::Seek,
    os::fd::AsRawFd,
    path::{Path, PathBuf},
    rc::Rc,
};

const PYTHON_BYTES: u64 = 7_477_160;
const PYTHON_SHA: &str = "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41";
const REQUEST: &str = "droidloom.working-fixed-command.v1";
const RESPONSE: &str = "droidloom.working-fixed-command-result.v1";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum WorkingGrubOperation {
    Read,
    Arm,
    Disarm,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Operation {
    Reload,
    VerifyMasks,
    FreezeInventory,
    StartThawGuard,
    StopWriters,
    RestoreWriters,
    PublicSnapshot,
    PublicApply,
    PublicVerify,
    PublicRollback,
    NativeSnapshot,
    NativeApply,
    NativeVerify,
    NativeRollback,
    GrubRead,
    GrubArm,
    GrubDisarm,
    RequestReboot,
    ShutdownState,
}
impl Operation {
    fn name(self) -> &'static str {
        match self {
            Self::Reload => "systemctl",
            Self::VerifyMasks => "package-masks-read",
            Self::FreezeInventory => "working-writer-inventory",
            Self::StartThawGuard => "working-thaw-start",
            Self::StopWriters => "package-writers-stop",
            Self::RestoreWriters => "package-writers-restore",
            Self::PublicSnapshot => "public-snapshot",
            Self::PublicApply => "public-apply",
            Self::PublicVerify => "public-verify",
            Self::PublicRollback => "public-rollback",
            Self::NativeSnapshot => "native-snapshot",
            Self::NativeApply => "native-apply",
            Self::NativeVerify => "native-verify",
            Self::NativeRollback => "native-rollback",
            Self::GrubRead => "grub-read",
            Self::GrubArm => "grub-arm",
            Self::GrubDisarm => "grub-disarm",
            Self::RequestReboot => "working-reboot",
            Self::ShutdownState => "working-shutdown-state",
        }
    }
    fn seconds(self) -> u64 {
        match self {
            Self::PublicApply | Self::NativeApply | Self::PublicRollback | Self::NativeRollback => {
                600
            }
            _ => 180,
        }
    }
}

/// Reuse the normal backend implementation while keeping the H2 protocol and
/// operation roster separate. The unused once GRUB, reaper and journal adapters
/// are not included. PID1 must actually resolve every fixed package/sleep unit
/// to the retained runtime mask; an /etc or transient override is rejected.
pub(super) fn driver() -> Result<String> {
    let (engines, _) = commands::historical_driver_source()
        .split_once("elif op=='quiescence-inventory':")
        .ok_or("normal package worker boundary changed")?;
    let (_, ending) = commands::historical_driver_source()
        .split_once("check_tool_sources(full=True)")
        .ok_or("normal package worker terminal boundary changed")?;
    let (_, freeze_and_tail) = commands::historical_driver_source()
        .split_once("elif op=='quiescence-inventory':")
        .ok_or("normal writer inventory boundary changed")?;
    let (freeze, _) = freeze_and_tail
        .split_once("elif op=='systemctl':")
        .ok_or("normal thaw start boundary changed")?;
    let freeze = format!("elif op=='working-writer-inventory':{freeze}")
        .replace("quiescence-reaper", "working-thaw-start")
        .replace(
            "droidloom-original-qualification@",
            "droidloom-working-cold@",
        )
        .replace("droidloom-original-thaw@", "droidloom-working-thaw@")
        .replace("__original-once-thaw", "__working-cold-thaw");
    let units = c::PACKAGE_WRITERS
        .iter()
        .chain(c::SUSPEND_TARGETS.iter())
        .copied()
        .collect::<Vec<_>>();
    let mask_branch = r#"elif op=='package-masks-read':
 units=__WORKING_MASK_UNITS__
 need(arg=={'units':units},'fixed working runtime mask roster')
 result=[]
 for name in units:
  observed=normal_tool('systemctl',['show',name,'--no-pager','--property=Id,LoadState,FragmentPath,DropInPaths,Transient'],seconds=10,maximum=65536)
  need(observed['exit']==0,'actual PID1 mask query failed')
  lines=observed['stdout'].decode('utf-8','strict').splitlines()
  need(len(lines)==5 and all('=' in line for line in lines),'complete actual PID1 mask properties')
  values=dict(line.split('=',1) for line in lines)
  need(set(values)=={'Id','LoadState','FragmentPath','DropInPaths','Transient'},'exact actual PID1 mask property set')
  need(values=={'Id':name,'LoadState':'masked','FragmentPath':'/dev/null','DropInPaths':'','Transient':'no'},'runtime mask is overridden or not effective in PID1')
  result.append({'unit':name,'actual':values,'command':observed})
"#
    .replace("__WORKING_MASK_UNITS__", &serde_json::to_string(&units)?);
    let (_, grub_and_tail) = commands::historical_driver_source()
        .split_once("elif op in ('grub-read','grub-arm','grub-disarm'):")
        .ok_or("normal GRUB branch changed")?;
    let (grub, _) = grub_and_tail
        .split_once("elif op=='retirement-journal':")
        .ok_or("normal GRUB branch end changed")?;
    let grub = format!("elif op in ('grub-read','grub-arm','grub-disarm'):{grub}").replace(
        "droidloom-original-once-",
        "droidloom-working-qualification-",
    );
    let reboot = "elif op=='working-reboot':\n need(arg=={},'fixed working reboot has no caller argv')\n result=normal_tool('systemctl',['--no-block','reboot'],seconds=90)\n";
    let shutdown = r#"elif op=='working-shutdown-state':
 need(arg=={},'fixed read-only PID1 state has no caller selectors')
 state=normal_tool('systemctl',['show','--property=SystemState','--value'],seconds=10,maximum=4096)
 jobs=normal_tool('systemctl',['list-jobs','--no-legend','--no-pager','--plain'],seconds=10,maximum=262144)
 need(state['exit']==0 and jobs['exit']==0,'actual PID1 shutdown observation failed')
 current=state['stdout'].decode('utf-8','strict').strip()
 need(current in ('initializing','starting','running','degraded','maintenance','stopping','offline','unknown'),'unknown actual manager state')
 rows=[]
 for line in jobs['stdout'].decode('utf-8','strict').splitlines():
  fields=line.split();need(len(fields)==4 and fields[0].isdigit(),'bounded actual PID1 job row')
  need(len(rows)<256 and all(len(x)<=512 for x in fields),'actual PID1 job inventory bound')
  rows.append({'id':fields[0],'unit':fields[1],'type':fields[2],'state':fields[3]})
 shutdown_units={'reboot.target','shutdown.target','final.target','umount.target','systemd-reboot.service','systemd-soft-reboot.service','systemd-poweroff.service','poweroff.target','halt.target','systemd-halt.service','kexec.target','systemd-kexec.service'}
 result={'system_state':current,'jobs':rows,'shutdown_pending':current=='stopping' or any(row['unit'] in shutdown_units for row in rows),'idle':current in ('running','degraded') and rows==[],'commands':[state,jobs]}
"#;
    let body = format!(
        "{engines}{freeze}elif op=='systemctl':\n need(arg=={{'argv':['daemon-reload']}},'fixed working package daemon reload')\n result=normal_tool('systemctl',['daemon-reload'],seconds=90)\n{mask_branch}{grub}{reboot}{shutdown}else:raise RuntimeError('unsupported source-owned working package operation')\ncheck_tool_sources(full=True){ending}"
    );
    let body = body.replace("droidloom.original-once-", "droidloom.working-");
    ensure(
        !body.contains("droidloom-original-once-")
            && !body.contains("quiescence-reaper")
            && !body.contains("droidloom.original-once-"),
        "working package worker acquired another owner's operation",
    )?;
    Ok(body)
}
fn save(path: &Path, value: &Value) -> Result<SealedInput> {
    let mut bytes = serde_json::to_vec(value)?;
    bytes.push(b'\n');
    files::write_new(path, &bytes, 0o400)?;
    File::open(
        path.parent()
            .ok_or("working package record parent absent")?,
    )?
    .sync_all()?;
    SealedInput::open(&files::pin_file(path)?)
}
fn field_pin(value: &Value, field: &str) -> Result<FilePin> {
    Ok(serde_json::from_value(value[field].clone())?)
}
fn exact_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
struct Snapshot {
    result: Value,
    guard: Guard,
}
impl Snapshot {
    fn open(value: Value) -> Result<Self> {
        let guard = Guard::open(&field_pin(&value, "snapshot")?)?;
        guard.revalidate()?;
        Ok(Self {
            result: value,
            guard,
        })
    }
    fn arguments(&self, native: bool) -> Result<Value> {
        self.guard.revalidate()?;
        if native {
            let attempt = self.result["attempt"]
                .as_str()
                .ok_or("actual normal native attempt absent")?;
            ensure(
                self.guard
                    .pin()
                    .path
                    .parent()
                    .and_then(Path::file_name)
                    .and_then(|p| p.to_str())
                    == Some(attempt),
                "normal native snapshot is outside its actual attempt",
            )?;
            Ok(json!({"snapshot":self.guard.pin(),"attempt":attempt}))
        } else {
            Ok(json!({"snapshot":self.guard.pin()}))
        }
    }
}

/// Remains live on every error. Source custody, interpreter, normal modules,
/// snapshots and runtime mask inodes are not replaced by a JSON success field.
pub(crate) struct WorkingPackages {
    custody: Rc<WorkingColdCustody>,
    label_source: super::WorkingLabelSourceIdentity,
    candidate: String,
    intent: FilePin,
    materials: Value,
    work: PathBuf,
    modules: Vec<Guard>,
    python: File,
    python_identity: crate::model::Identity,
    driver: String,
    serial: u32,
    results: Vec<SealedInput>,
    masks: Option<WorkingPackageMasks>,
    mask_intent: Option<SealedInput>,
    preservation: Option<SealedInput>,
    stop_directory: Option<PathBuf>,
    writers: Option<Guard>,
    stop_attempted: bool,
    public: Option<Snapshot>,
    native: Option<Snapshot>,
    public_attempted: bool,
    native_attempted: bool,
    installed: bool,
    restored: bool,
}
impl WorkingPackages {
    pub(super) fn prepare(source: &WorkingRuntimeSources) -> Result<Self> {
        source.revalidate()?;
        let custody = source.package_custody()?;
        let candidate = source.candidate().to_owned();
        let intent = source.boot_intent().clone();
        let materials = source.label_sources().fresh_initramfs_report()["normal_materials"].clone();
        ensure(
            materials["deployment_id"] == candidate
                && fs::valid_digest(
                    materials["public_release_id"]
                        .as_str()
                        .ok_or("normal public ID absent")?,
                )
                && fs::valid_digest(
                    materials["native_release_id"]
                        .as_str()
                        .ok_or("normal native ID absent")?,
                ),
            "working package sources belong to another actual normal candidate",
        )?;
        let work = source.work().join("working-packages");
        files::private_dir(&work)?;
        let modules_path = work.join("normal-source");
        files::private_dir(&modules_path)?;
        files::private_dir(&work.join("commands"))?;
        let mut modules = Vec::new();
        for (name, bytes) in crate::boot_host::cold_modules::FILES {
            let path = modules_path.join(
                Path::new(name)
                    .file_name()
                    .ok_or("normal package module basename")?,
            );
            files::write_new(&path, bytes, 0o400)?;
            let expected = FilePin {
                path,
                bytes: bytes.len() as u64,
                sha256: fs::digest(bytes),
            };
            modules.push(Guard::open(&expected)?);
        }
        File::open(&modules_path)?.sync_all()?;
        File::open(&work)?.sync_all()?;
        let python_pin = FilePin {
            path: "/usr/bin/python3.14".into(),
            bytes: PYTHON_BYTES,
            sha256: PYTHON_SHA.into(),
        };
        let (python, python_identity) = files::open_pin(&python_pin)?;
        ensure(
            python_identity.uid == 0
                && python_identity.gid == 0
                && python_identity.mode == 0o100755
                && python_identity.nlink == 1,
            "working package interpreter is not its actual normal root executable",
        )?;
        let value = Self {
            custody,
            label_source: source.label_source_identity()?,
            candidate,
            intent,
            materials,
            work,
            modules,
            python,
            python_identity,
            driver: driver()?,
            serial: 0,
            results: Vec::new(),
            masks: None,
            mask_intent: None,
            preservation: None,
            stop_directory: None,
            writers: None,
            stop_attempted: false,
            public: None,
            native: None,
            public_attempted: false,
            native_attempted: false,
            installed: false,
            restored: false,
        };
        value.guard_source()?;
        Ok(value)
    }
    fn guard_source(&self) -> Result<()> {
        self.custody.revalidate()?;
        for module in &self.modules {
            module.revalidate()?;
        }
        if let Some(record) = &self.mask_intent {
            record.revalidate()?;
        }
        if let Some(record) = &self.preservation {
            record.revalidate()?;
        }
        for record in &self.results {
            record.revalidate()?;
        }
        if let Some(original) = &self.writers {
            original.revalidate()?;
        }
        for snapshot in [self.public.as_ref(), self.native.as_ref()]
            .into_iter()
            .flatten()
        {
            snapshot.guard.revalidate()?;
        }
        (&self.python).rewind()?;
        ensure(
            fs::stat(&self.python)? == self.python_identity
                && fs::hash(&self.python)? == PYTHON_SHA
                && fs::Tree::open("/", 0)?.identity("/usr/bin/python3.14")? == self.python_identity
                && fs::xattrs(&self.python)?.is_empty(),
            "working package interpreter lost its complete held/named source",
        )?;
        self.custody.revalidate()
    }
    pub(crate) fn guard_label_custody(&self) -> Result<()> {
        self.custody.revalidate_label_custody()?;
        ensure(
            self.installed && !self.restored,
            "working label window lost actual normal installation",
        )?;
        for module in &self.modules {
            module.revalidate_custody()?;
        }
        for record in &self.results {
            record.revalidate_custody()?;
        }
        if let Some(record) = &self.mask_intent {
            record.revalidate_custody()?;
        }
        if let Some(writers) = &self.writers {
            writers.revalidate_custody()?;
        }
        for snapshot in [self.public.as_ref(), self.native.as_ref()]
            .into_iter()
            .flatten()
        {
            snapshot.guard.revalidate_custody()?;
        }
        self.masks
            .as_ref()
            .ok_or("working label window lost actual masks")?
            .guard()?;
        ensure(
            fs::stat(&self.python)? == self.python_identity
                && fs::Tree::open("/", 0)?.identity("/usr/bin/python3.14")? == self.python_identity
                && fs::xattrs(&self.python)?.is_empty(),
            "working label window interpreter custody changed",
        )?;
        self.custody.revalidate_label_custody()
    }
    pub(crate) fn accept_working_label_batch(
        &mut self,
        batch: &crate::cold_original_data::labels::WorkingLabelBatch,
    ) -> Result<()> {
        batch.require_identity(&self.label_source)?;
        let actual = fs::stat(&self.python)?;
        if actual != self.python_identity {
            let path = Path::new("/usr/bin/python3.14");
            let proof = batch
                .records()
                .iter()
                .find(|proof| proof.paths().iter().any(|known| known == path))
                .ok_or("working package interpreter changed outside the same label batch")?;
            self.python_identity =
                proof.require_held_transition(path, &self.python, &self.python_identity)?;
        }
        // Other source, boot and pair checkpoints are advanced by this same
        // batch before the caller performs the complete bounded-window fence.
        batch.revalidate()
    }
    fn call(&mut self, operation: Operation, mut arguments: Value) -> Result<Value> {
        self.guard_source()?;
        if matches!(
            operation,
            Operation::PublicRollback
                | Operation::NativeRollback
                | Operation::PublicVerify
                | Operation::NativeVerify
        ) {
            if let Some(proof) = &self.preservation {
                proof.revalidate()?;
                arguments
                    .as_object_mut()
                    .ok_or("working normal arguments are not an object")?
                    .insert(
                        "restored_metadata".into(),
                        serde_json::to_value(proof.pin())?,
                    );
            }
        }
        ensure(
            self.serial < 64,
            "working package command bound exhausted; retain recovery owner",
        )?;
        self.serial += 1;
        let directory =
            self.work
                .join("commands")
                .join(format!("{:04}-{}", self.serial, operation.name()));
        files::private_dir(&directory)?;
        if operation == Operation::StopWriters {
            self.stop_directory = Some(directory.clone());
        }
        let input = save(
            &directory.join("INPUTS.json"),
            &json!({
                "schema":REQUEST,"candidate_id":self.candidate,"intent":self.intent,
                "operation":operation.name(),"arguments":arguments,"materials":self.materials
            }),
        )?;
        let result = files::run_logged(
            &directory,
            "normal-package-command",
            &format!(
                "/proc/{}/fd/{}",
                std::process::id(),
                self.python.as_raw_fd()
            ),
            &[
                "-I".into(),
                "-B".into(),
                "-c".into(),
                self.driver.clone(),
                fs::absolute_string(&self.work.join("normal-source"))?,
                fs::absolute_string(&input.pin().path)?,
            ],
            operation.seconds(),
        )?;
        // A failed command may have changed package state. The phase flags are
        // already set by the caller and stay set until actual reverse succeeds.
        ensure(
            result.exit_code == Some(0) && !result.timed_out,
            "actual normal working package command failed or timed out",
        )?;
        input.revalidate()?;
        self.guard_source()?;
        let actual: Value =
            serde_json::from_slice(&files::read_pin(&result.log, 64 * 1024 * 1024)?)?;
        ensure(
            actual["schema"] == RESPONSE
                && actual["operation"] == operation.name()
                && actual["candidate_id"] == self.candidate
                && actual["intent"] == serde_json::to_value(&self.intent)?,
            "actual normal package result belongs to another working owner",
        )?;
        let evidence = save(
            &directory.join("RESULT.json"),
            &json!({
                "schema":"droidloom.working-normal-package-command.v1",
                "input":input.pin(),"driver_sha256":fs::digest(self.driver.as_bytes()),
                "command":result,"actual":actual
            }),
        )?;
        let output = actual["result"].clone();
        self.results.push(evidence);
        self.guard_source()?;
        Ok(output)
    }
    pub(crate) fn working_grub_command(
        &mut self,
        operation: WorkingGrubOperation,
        cfg: &FilePin,
    ) -> Result<Value> {
        ensure(
            self.installed
                && !self.restored
                && cfg.path == Path::new("/boot/grub/grub.cfg")
                && fs::valid_digest(&cfg.sha256),
            "working GRUB requires installed normal packages",
        )?;
        let op = match operation {
            WorkingGrubOperation::Read => Operation::GrubRead,
            WorkingGrubOperation::Arm => Operation::GrubArm,
            WorkingGrubOperation::Disarm => Operation::GrubDisarm,
        };
        self.call(op, json!({"original_cfg_sha256": cfg.sha256}))
    }
    pub(crate) fn reload_manager(&mut self) -> Result<Value> {
        self.call(Operation::Reload, json!({"argv":["daemon-reload"]}))
    }
    pub(crate) fn working_shutdown_state(&mut self) -> Result<Value> {
        self.call(Operation::ShutdownState, json!({}))
    }
    pub(crate) fn working_request_reboot(&mut self) -> Result<Value> {
        ensure(
            self.installed && !self.restored,
            "working reboot requires installed normal packages",
        )?;
        self.call(Operation::RequestReboot, json!({}))
    }
    fn capture_writers(&mut self) -> Result<()> {
        if self.writers.is_some() {
            return Ok(());
        }
        let directory = self
            .stop_directory
            .as_ref()
            .ok_or("working writer stop was not invoked")?;
        let path = directory.join("WRITERS-INTENT.json");
        if let Err(error) = std::fs::symlink_metadata(&path) {
            if error.kind() == std::io::ErrorKind::NotFound {
                // The fixed source writes this immutable intent before its
                // first stop request. An absent intent cannot have stopped a unit.
                self.stop_attempted = false;
                return Ok(());
            }
            return Err(error.into());
        }
        let pin = files::pin_file(&path)?;
        let held = Guard::open(&pin)?;
        let value: Value = serde_json::from_slice(&files::read_pin(&pin, 1024 * 1024)?)?;
        let native = field_pin(&self.materials, "native_release")?;
        ensure(
            value["schema"] == "droidloom.working-package-writers.v1"
                && value["candidate_id"] == self.candidate
                && value["intent"] == serde_json::to_value(&self.intent)?
                && value["units"] == serde_json::to_value(c::PACKAGE_WRITERS)?
                && exact_pin(&field_pin(&value, "source")?, &native),
            "working writer restoration lost its actual immutable pre-stop inventory",
        )?;
        held.revalidate()?;
        self.writers = Some(held);
        Ok(())
    }
    pub(super) fn freeze_inventory(&mut self) -> Result<(Value, FilePin)> {
        ensure(
            self.installed && !self.restored,
            "working freeze requires actual normal packages",
        )?;
        let observed = self.call(Operation::FreezeInventory, json!({}))?;
        let record = self
            .results
            .last()
            .ok_or("actual writer inventory record absent")?;
        record.revalidate()?;
        Ok((observed, record.pin().clone()))
    }
    pub(super) fn start_thaw_guard(&mut self, producer: &FilePin, intent: &FilePin) -> Result<()> {
        ensure(
            self.installed && !self.restored,
            "working thaw requires actual normal packages",
        )?;
        let actual = self.call(
            Operation::StartThawGuard,
            json!({
                "producer":producer,"freeze_intent":intent
            }),
        )?;
        ensure(
            actual["exit"] == 0,
            "normal working thaw process failed to start",
        )
    }
    pub(super) fn install(&mut self) -> Result<()> {
        self.guard_source()?;
        ensure(
            self.masks.is_none() && !self.stop_attempted && !self.installed && !self.restored,
            "working package forward is create-only",
        )?;
        let units = c::PACKAGE_WRITERS
            .iter()
            .chain(c::SUSPEND_TARGETS.iter())
            .copied()
            .collect::<Vec<_>>();
        let masks = WorkingPackageMasks::prepare(&self.candidate, &units)?;
        self.mask_intent = Some(save(
            &self.work.join("MASKS-INTENT.json"),
            &masks.comparison(),
        )?);
        self.masks = Some(masks);
        self.masks.as_mut().unwrap().publish()?;
        let reload = self.call(Operation::Reload, json!({"argv":["daemon-reload"]}))?;
        ensure(
            reload["exit"] == 0,
            "normal working package masks were not reloaded",
        )?;
        self.verify_masks()?;
        self.stop_attempted = true;
        let stopped = self.call(Operation::StopWriters, json!({"units":c::PACKAGE_WRITERS}));
        // Capture the same before-effect intent even when stop failed after
        // affecting only a prefix of the fixed unit roster.
        let captured = self.capture_writers();
        let stopped = stopped?;
        captured?;
        ensure(
            self.stop_attempted
                && self.writers.as_ref().is_some_and(|guard| {
                    serde_json::to_value(guard.pin()).ok().as_ref() == Some(&stopped["original"])
                }),
            "normal writer stop did not retain its actual original inventory",
        )?;
        self.public = Some(Snapshot::open(
            self.call(Operation::PublicSnapshot, json!({}))?,
        )?);
        self.public_attempted = true;
        let arguments = self.public.as_ref().unwrap().arguments(false)?;
        self.call(Operation::PublicApply, arguments)?;
        self.native = Some(Snapshot::open(
            self.call(Operation::NativeSnapshot, json!({}))?,
        )?);
        self.native_attempted = true;
        let arguments = self.native.as_ref().unwrap().arguments(true)?;
        self.call(Operation::NativeApply, arguments)?;
        self.masks.as_ref().unwrap().guard()?;
        self.installed = true;
        self.verify_installed()
    }
    fn verify_masks(&mut self) -> Result<()> {
        self.masks
            .as_ref()
            .ok_or("working package masks missing")?
            .guard()?;
        let units = c::PACKAGE_WRITERS
            .iter()
            .chain(c::SUSPEND_TARGETS.iter())
            .copied()
            .collect::<Vec<_>>();
        self.call(Operation::VerifyMasks, json!({"units":units}))?;
        self.masks.as_ref().unwrap().guard()
    }
    pub(super) fn verify_installed(&mut self) -> Result<()> {
        self.guard_source()?;
        ensure(
            self.installed && self.public_attempted && self.native_attempted && !self.restored,
            "working runtime requires actual complete normal public/native installation",
        )?;
        self.verify_masks()?;
        let public = self
            .public
            .as_ref()
            .ok_or("actual public snapshot missing")?
            .arguments(false)?;
        self.call(Operation::PublicVerify, public)?;
        let native = self
            .native
            .as_ref()
            .ok_or("actual native snapshot missing")?
            .arguments(true)?;
        self.call(Operation::NativeVerify, native)?;
        self.guard_source()
    }
    pub(super) fn bind_label_restoration(
        &mut self,
        restored: &crate::cold_original_data::labels::WorkingLabelsRestored,
    ) -> Result<()> {
        restored.require_identity(&self.label_source)?;
        let mut snapshots = serde_json::Map::new();
        let mut paths = std::collections::BTreeSet::new();
        for (kind, snapshot, field) in [
            ("public", self.public.as_ref(), "preserved_metadata_only"),
            ("native", self.native.as_ref(), "private_metadata"),
        ] {
            let snapshot =
                snapshot.ok_or("actual working normal snapshot lost before label reverse")?;
            snapshot.guard.revalidate()?;
            let body: Value =
                serde_json::from_slice(&files::read_pin(snapshot.guard.pin(), 16 * 1024 * 1024)?)?;
            let original = body[field]
                .as_object()
                .ok_or("normal original metadata roster absent")?;
            ensure(
                !original.is_empty() && original.len() <= 32,
                "bounded actual normal preservation roster required",
            )?;
            for (name, old) in original {
                if kind == "native" && old["absent"] == true {
                    continue;
                }
                let path = if name.starts_with('/') {
                    PathBuf::from(name)
                } else {
                    PathBuf::from(format!("/{name}"))
                };
                ensure(
                    path.components().all(|c| {
                        matches!(
                            c,
                            std::path::Component::RootDir | std::path::Component::Normal(_)
                        )
                    }),
                    "normal preserved metadata path is not canonical",
                )?;
                paths.insert(path);
            }
            snapshots.insert(
                kind.into(),
                json!({"snapshot":snapshot.guard.pin(),"original":original}),
            );
        }
        let value = json!({
            "schema":"droidloom.working-package-preservation.v1",
            "candidate_id":self.candidate,"intent":self.intent,
            "actual_label_restoration":restored.report(),
            "snapshots":snapshots,"metadata":restored.metadata(&paths)?,
        });
        let pin = restored.publish_package_preservation(&value)?;
        let held = SealedInput::open(&pin)?;
        held.revalidate()?;
        if let Some(existing) = &self.preservation {
            ensure(
                serde_json::to_value(existing.pin())? == serde_json::to_value(&pin)?,
                "working package restoration proof changed",
            )?;
        } else {
            self.preservation = Some(held);
        }
        restored.require_identity(&self.label_source)?;
        self.guard_source()
    }
    pub(super) fn restore(&mut self) -> Result<()> {
        if self.restored {
            return self.guard_restored();
        }
        self.guard_source()?;
        if self.native_attempted {
            let arguments = self
                .native
                .as_ref()
                .ok_or("attempted native install lost its snapshot")?
                .arguments(true)?;
            self.call(Operation::NativeRollback, arguments)?;
            self.native_attempted = false;
        }
        if self.public_attempted {
            let arguments = self
                .public
                .as_ref()
                .ok_or("attempted public install lost its snapshot")?
                .arguments(false)?;
            self.call(Operation::PublicRollback, arguments)?;
            self.public_attempted = false;
        }
        if let Some(masks) = &mut self.masks {
            masks.restore()?;
        }
        if self.masks.is_some() {
            let reload = self.call(Operation::Reload, json!({"argv":["daemon-reload"]}))?;
            ensure(
                reload["exit"] == 0,
                "normal original package masks were not reloaded",
            )?;
        }
        if self.stop_attempted {
            self.capture_writers()?;
            if self.stop_attempted {
                let original = self
                    .writers
                    .as_ref()
                    .ok_or("actual original writer inventory missing")?
                    .pin()
                    .clone();
                self.call(
                    Operation::RestoreWriters,
                    json!({"units":c::PACKAGE_WRITERS,"original":original}),
                )?;
                self.stop_attempted = false;
            }
        }
        self.installed = false;
        self.restored = true;
        self.guard_restored()
    }
    pub(super) fn guard_restored(&self) -> Result<()> {
        ensure(
            self.restored
                && !self.public_attempted
                && !self.native_attempted
                && !self.stop_attempted,
            "normal working package restoration remains incomplete",
        )?;
        if let Some(masks) = &self.masks {
            masks.guard()?;
        }
        self.guard_source()
    }
    pub(super) fn evidence(&self) -> Result<Value> {
        self.guard_restored()?;
        Ok(
            json!({"schema":"droidloom.working-normal-packages-restored.v1",
            "candidate_id":self.candidate,"intent":self.intent,
            "public_snapshot":self.public.as_ref().map(|v|v.guard.pin()),
            "native_snapshot":self.native.as_ref().map(|v|v.guard.pin()),
            "commands":self.results.iter().map(|v|v.pin()).collect::<Vec<_>>(),
            "runtime_mask_intent":self.mask_intent.as_ref().map(|v|v.pin()),
            "normal_packages_restored":true,"runtime_masks_restored":true,
            "original_writer_requests_restored":true,"boot_armed":false,"production_ready":false}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_normal_package_worker_retains_only_fixed_backend_operations() {
        let source = driver().unwrap();
        assert!(source.contains(REQUEST));
        assert!(source.contains(RESPONSE));
        for forbidden in [
            "droidloom-original-once-",
            "quiescence-reaper",
            "retirement-journal",
            "droidloom.original-once-",
        ] {
            assert!(!source.contains(forbidden), "{forbidden}");
        }
        assert!(source.contains("arg=={'argv':['daemon-reload']}"));
        for operation in [
            Operation::GrubRead,
            Operation::GrubArm,
            Operation::GrubDisarm,
            Operation::RequestReboot,
            Operation::VerifyMasks,
            Operation::FreezeInventory,
            Operation::StartThawGuard,
            Operation::PublicSnapshot,
            Operation::PublicApply,
            Operation::PublicVerify,
            Operation::PublicRollback,
            Operation::NativeSnapshot,
            Operation::NativeApply,
            Operation::NativeVerify,
            Operation::NativeRollback,
            Operation::StopWriters,
            Operation::RestoreWriters,
        ] {
            assert!(source.contains(operation.name()));
        }
    }
    #[test]
    fn working_normal_package_worker_is_accepted_by_the_actual_python_parser() {
        use std::{
            io::Write,
            process::{Command, Stdio},
        };
        let mut child = Command::new("/usr/bin/python3.14")
            .args([
                "-I",
                "-B",
                "-c",
                "import ast,sys; ast.parse(sys.stdin.read(), filename='working-package-worker')",
            ])
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(driver().unwrap().as_bytes())
            .unwrap();
        let result = child.wait_with_output().unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
    }
}
