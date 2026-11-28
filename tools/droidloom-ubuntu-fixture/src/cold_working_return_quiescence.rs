//! A fresh, finite original-kernel return window. This factory owns actual
//! source, PID1-selected cgroups and a separate same-source thaw process; an old
//! forward window or serialized "frozen" flag cannot construct it.
use super::{
    FreezeIntent, FreezePurpose, Group, MAX_SECONDS, SealedInput, ThawCleanup, bounded, clock_ms,
    inventory_groups_for_units, starttime,
};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_qualification::{
        WorkingBootRetirement, WorkingRecoverySources, commands, materials::Guard, owner,
    },
    ensure, fs,
    model::Identity,
};
use rustix::fs::{Mode, OFlags};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs::File,
    io::Seek,
    os::fd::{AsRawFd, OwnedFd},
    path::{Path, PathBuf},
    rc::Rc,
    time::{Duration, Instant},
};

const REQUEST: &str = "droidloom.working-return-window-command.v1";
const RESPONSE: &str = "droidloom.working-return-window-command-result.v1";
const INTENT_SCHEMA: &str = "droidloom.working-return-freeze-source.v1";
const FREEZE_SCHEMA: &str = "droidloom.working-return-freeze-intent.v1";
const READY_SCHEMA: &str = "droidloom.working-return-thaw-ready.v1";
const RELEASE_SCHEMA: &str = "droidloom.working-return-freeze-released.v1";
const THAW_SCHEMA: &str = "droidloom.working-return-thaw-result.v1";
const MODE: &str = "__working-return-thaw";
const PYTHON_BYTES: u64 = 7_477_160;
const PYTHON_SHA: &str = "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41";
const NS: [&str; 7] = ["user", "pid", "mnt", "net", "ipc", "uts", "cgroup"];

fn equal_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
fn save(path: &Path, value: &impl Serialize) -> Result<SealedInput> {
    let mut bytes = serde_json::to_vec(value)?;
    bytes.push(b'\n');
    files::write_new(path, &bytes, 0o400)?;
    File::open(path.parent().ok_or("return window record parent")?)?.sync_all()?;
    SealedInput::open(&files::pin_file(path)?)
}
fn unique_directory(parent: &Path, name: &str) -> Result<PathBuf> {
    ensure(
        !name.is_empty() && !name.contains('/') && name != "." && name != "..",
        "return window directory component",
    )?;
    let held = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(parent)?)?;
    rustix::fs::mkdirat(&held, name, Mode::from_raw_mode(0o700))?;
    held.sync_all()?;
    let path = parent.join(name);
    let made = fs::Tree::open("/", 0)?.dir(&fs::absolute_string(&path)?)?;
    let state = fs::stat(&made)?;
    ensure(
        state.uid == 0 && state.gid == 0 && state.mode & 0o7777 == 0o700,
        "return window create-only directory protection",
    )?;
    Ok(path)
}
fn owner_prefix(group: &str, candidate: &str) -> Result<&'static str> {
    ensure(fs::valid_digest(candidate), "return window candidate")?;
    for prefix in ["droidloom-working-recovery@", "droidloom-working-cold@"] {
        if group == format!("/system.slice/{prefix}{candidate}.service") {
            return Ok(prefix);
        }
    }
    Err("return window is not the fresh recovery or same-process original unit".into())
}
fn inventory_groups(
    value: &Value,
    candidate: &str,
    prefix: &str,
) -> Result<(Vec<(String, String)>, Vec<String>)> {
    ensure(
        matches!(
            prefix,
            "droidloom-working-recovery@" | "droidloom-working-cold@"
        ),
        "return inventory owner is not a fixed normal unit",
    )?;
    inventory_groups_for_units(
        value,
        &format!("{prefix}{candidate}.service"),
        &format!("droidloom-working-return-thaw@{candidate}.service"),
        "no",
    )
}

/// Only an actual fresh source/retirement factory constructs this envelope.
/// The reaper consumes it solely to undo this fixed, originally-zero group set.
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ReturnFreezeIntent {
    schema: String,
    freeze: FreezeIntent,
    material_input: FilePin,
    normal_sources: FilePin,
    retirement: FilePin,
}
fn normal_driver(prefix: &str) -> Result<String> {
    ensure(
        matches!(
            prefix,
            "droidloom-working-recovery@" | "droidloom-working-cold@"
        ),
        "fixed return window normal owner prefix",
    )?;
    let source = commands::historical_driver_source();
    let (head, _) = source
        .split_once("\ndef preservation(")
        .ok_or("normal return window source prefix changed")?;
    let (_, part) = source
        .split_once("elif op=='quiescence-inventory':")
        .ok_or("normal writer inventory boundary changed")?;
    let (part, _) = part
        .split_once("elif op=='systemctl':")
        .ok_or("normal fixed thaw boundary changed")?;
    let part = format!("if op=='return-writer-inventory':\n need(arg=={{}},'fixed return inventory has no caller argv')\n{part}")
        .replace("quiescence-reaper", "return-thaw-start")
        .replace("droidloom-original-qualification@", prefix)
        .replace("droidloom-original-thaw@", "droidloom-working-return-thaw@")
        .replace("__original-once-thaw", MODE)
        .replace(" producer=arg['producer'];", " need(set(arg)=={'producer','freeze_intent'},'fixed return thaw fields')\n producer=arg['producer'];");
    let (_, tail) = source
        .split_once("check_tool_sources(full=True)")
        .ok_or("normal return window final source readback changed")?;
    let output = format!("{head}\n{part}else:raise RuntimeError('unsupported fixed return-window operation')\ncheck_tool_sources(full=True){tail}")
        .replace("droidloom.original-once-fixed-command-result.v1", RESPONSE)
        .replace("droidloom.original-once-fixed-command.v1", REQUEST);
    ensure(
        !output.contains("elif op=='systemctl':")
            && !output.contains("grub-arm")
            && !output.contains("public-apply")
            && !output.contains("native-apply"),
        "return freezer acquired an unrelated package, boot or freeform operation",
    )?;
    Ok(output)
}
#[derive(Clone, Copy)]
enum Operation {
    Inventory,
    Start,
}
impl Operation {
    fn name(self) -> &'static str {
        match self {
            Self::Inventory => "return-writer-inventory",
            Self::Start => "return-thaw-start",
        }
    }
}

/// Held normal modules and records are entirely in the private qualification
/// exclusion. Actual installed tools are fully source-bound per invocation;
/// no installed inode is silently refreshed across returned-label writes.
struct NormalControl {
    sources: PathBuf,
    driver: String,
    modules: Vec<Guard>,
    records: Vec<SealedInput>,
    work: PathBuf,
}
impl NormalControl {
    fn prepare(directory: &Path, prefix: &str) -> Result<Self> {
        let sources = unique_directory(directory, "normal-source")?;
        let mut modules = Vec::new();
        for (name, bytes) in crate::boot_host::cold_modules::FILES {
            let path = sources.join(Path::new(name).file_name().ok_or("normal module name")?);
            files::write_new(&path, bytes, 0o400)?;
            modules.push(Guard::open(&FilePin {
                path,
                bytes: bytes.len() as u64,
                sha256: fs::digest(bytes),
            })?);
        }
        File::open(&sources)?.sync_all()?;
        Ok(Self {
            sources,
            driver: normal_driver(prefix)?,
            modules,
            records: Vec::new(),
            work: directory.into(),
        })
    }
    fn custody(&self) -> Result<()> {
        for module in &self.modules {
            module.revalidate_custody()?;
        }
        for record in &self.records {
            record.revalidate_custody()?;
        }
        Ok(())
    }
    fn revalidate(&self) -> Result<()> {
        self.custody()?;
        for module in &self.modules {
            module.revalidate()?;
        }
        for record in &self.records {
            record.revalidate()?;
        }
        Ok(())
    }
    fn call(
        &mut self,
        sources: &WorkingRecoverySources,
        operation: Operation,
        arguments: Value,
    ) -> Result<(Value, FilePin)> {
        sources.revalidate()?;
        self.revalidate()?;
        let directory = unique_directory(&self.work, operation.name())?;
        let input = save(
            &directory.join("INPUTS.json"),
            &json!({
                "schema":REQUEST,"candidate_id":sources.candidate(),"intent":sources.boot_intent(),
                "operation":operation.name(),"arguments":arguments,"materials":sources.normal_materials(),
            }),
        )?;
        let python_pin = FilePin {
            path: "/usr/bin/python3.14".into(),
            bytes: PYTHON_BYTES,
            sha256: PYTHON_SHA.into(),
        };
        let (python, identity) = files::open_pin(&python_pin)?;
        let attributes = fs::xattrs(&python)?;
        ensure(
            identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.mode == 0o100755
                && attributes.keys().all(|v| v == "security.selinux"),
            "normal return interpreter is outside its exact protected source",
        )?;
        let command = files::run_logged(
            &directory,
            "normal-return-window",
            &format!("/proc/{}/fd/{}", std::process::id(), python.as_raw_fd()),
            &[
                "-I".into(),
                "-B".into(),
                "-c".into(),
                self.driver.clone(),
                fs::absolute_string(&self.sources)?,
                fs::absolute_string(&input.pin().path)?,
            ],
            180,
        )?;
        (&python).rewind()?;
        let named = fs::Tree::open("/", 0)?.file("/usr/bin/python3.14")?;
        ensure(
            fs::stat(&python)? == identity
                && fs::stat(&named)? == identity
                && fs::xattrs(&python)? == attributes
                && fs::xattrs(&named)? == attributes
                && fs::hash(&python)? == PYTHON_SHA
                && fs::stat(&python)? == identity,
            "normal return interpreter changed during the actual invocation",
        )?;
        ensure(
            command.exit_code == Some(0) && !command.timed_out,
            "normal return window command failed or has unknown outcome; it is not replayed",
        )?;
        input.revalidate()?;
        sources.revalidate()?;
        self.revalidate()?;
        let actual: Value =
            serde_json::from_slice(&files::read_pin(&command.log, 32 * 1024 * 1024)?)?;
        ensure(
            actual["schema"] == RESPONSE
                && actual["operation"] == operation.name()
                && actual["candidate_id"] == sources.candidate()
                && actual["intent"] == serde_json::to_value(sources.boot_intent())?
                && actual["original"]["boot_id"] == sources.owner().boot_id()
                && actual["original"]["kernel"] == "7.0.14-p4cred1",
            "normal return window result has another actual source or boot",
        )?;
        let record = save(
            &directory.join("RESULT.json"),
            &json!({
                "schema":"droidloom.working-return-window-normal-command.v1",
                "input":input.pin(),"command":command,"actual":actual,
                "driver_sha256":fs::digest(self.driver.as_bytes()),
            }),
        )?;
        let pin = record.pin().clone();
        let result = actual["result"].clone();
        self.records.extend([input, record]);
        self.revalidate()?;
        sources.revalidate()?;
        Ok((result, pin))
    }
}

struct Reaper {
    pid: u32,
    birth: u64,
    pidfd: OwnedFd,
    executable: File,
    identity: Identity,
    namespaces: BTreeMap<String, String>,
    ready: SealedInput,
    group: String,
}
fn pidfd_pid(fd: &OwnedFd) -> Result<Option<u32>> {
    let text = bounded(
        &File::open(format!("/proc/self/fdinfo/{}", fd.as_raw_fd()))?,
        8192,
    )?;
    let rows = text
        .lines()
        .filter_map(|v| v.strip_prefix("Pid:"))
        .map(str::trim)
        .collect::<Vec<_>>();
    ensure(
        rows.len() == 1,
        "held pidfd has no unique kernel PID record",
    )?;
    if rows[0] == "-1" {
        return Ok(None);
    }
    let pid: u32 = rows[0].parse()?;
    ensure(pid > 1, "held return pidfd may not refer to PID1")?;
    Ok(Some(pid))
}
pub(super) fn process_retired(fd: &OwnedFd, pid: u32, birth: u64) -> Result<bool> {
    match pidfd_pid(fd)? {
        None => Ok(true),
        Some(actual) => {
            ensure(actual == pid, "held pidfd belongs to another process")?;
            let file = match File::open(format!("/proc/{pid}/stat")) {
                Ok(file) => file,
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                    ensure(pidfd_pid(fd)?.is_none(), "live pidfd lost its proc process")?;
                    return Ok(true);
                }
                Err(e) => return Err(e.into()),
            };
            let text = bounded(&file, 8192)?;
            let end = text.rfind(')').ok_or("return process stat")?;
            let fields = text[end + 1..].split_whitespace().collect::<Vec<_>>();
            ensure(
                fields.len() >= 20 && fields[19].parse::<u64>()? == birth,
                "held return process birth changed",
            )?;
            Ok(matches!(fields[0], "Z" | "X"))
        }
    }
}
impl Reaper {
    fn capture(
        ready: SealedInput,
        intent: &FilePin,
        sources: &WorkingRecoverySources,
        deadline: u64,
    ) -> Result<Self> {
        let v: Value = serde_json::from_slice(&ready.read()?)?;
        ensure(
            v["schema"] == READY_SCHEMA
                && v["freeze_intent"] == serde_json::to_value(intent)?
                && v["candidate_id"] == sources.candidate()
                && v["deadline_boot_ms"] == deadline,
            "return reaper readiness belongs to another fresh window",
        )?;
        let pid: u32 = v["pid"].as_u64().ok_or("return reaper PID")?.try_into()?;
        let birth = v["starttime"].as_u64().ok_or("return reaper birth")?;
        let pidfd = rustix::process::pidfd_open(
            rustix::process::Pid::from_raw(i32::try_from(pid)?).ok_or("return reaper PID range")?,
            rustix::process::PidfdFlags::empty(),
        )?;
        let executable = File::open(format!("/proc/{pid}/exe"))?;
        let identity: Identity = serde_json::from_value(v["executable"].clone())?;
        let (named, source) = files::open_pin(sources.owner().program_pin())?;
        ensure(
            identity == source
                && fs::stat(&executable)? == identity
                && fs::hash(&executable)? == sources.owner().program_pin().sha256
                && fs::stat(&named)? == identity,
            "return reaper is not the actual same normal producer",
        )?;
        let value = Self {
            pid,
            birth,
            pidfd,
            executable,
            identity,
            namespaces: serde_json::from_value(v["namespaces"].clone())?,
            ready,
            group: format!(
                "/system.slice/droidloom-working-return-thaw@{}.service",
                sources.candidate()
            ),
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        self.ready.revalidate_custody()?;
        ensure(
            !process_retired(&self.pidfd, self.pid, self.birth)?
                && fs::stat(&self.executable)? == self.identity
                && fs::stat(&File::open(format!("/proc/{}/exe", self.pid))?)? == self.identity
                && bounded(&File::open(format!("/proc/{}/cgroup", self.pid))?, 4096)?
                    == format!("0::{}\n", self.group),
            "actual independent return reaper changed",
        )?;
        ensure(
            self.namespaces.len() == 7,
            "return reaper lacks all original namespaces",
        )?;
        for kind in NS {
            let actual = std::fs::read_link(format!("/proc/{}/ns/{kind}", self.pid))?;
            let original = std::fs::read_link(format!("/proc/1/ns/{kind}"))?;
            ensure(
                actual == original
                    && actual.to_str() == self.namespaces.get(kind).map(String::as_str),
                "return reaper left its held initial namespace",
            )?;
        }
        Ok(())
    }
}

pub(crate) struct WorkingReturnQuiescence {
    sources: Rc<WorkingRecoverySources>,
    retirement: Rc<WorkingBootRetirement>,
    normal: NormalControl,
    intent: SealedInput,
    groups: Vec<Group>,
    deadline: u64,
    reaper: Option<Reaper>,
    directory: PathBuf,
    released: bool,
    closed: bool,
}
impl WorkingReturnQuiescence {
    pub(crate) fn acquire(
        sources: Rc<WorkingRecoverySources>,
        retirement: Rc<WorkingBootRetirement>,
    ) -> Result<Self> {
        sources.revalidate()?;
        retirement.require_owner(sources.owner())?;
        ensure(
            equal_pin(
                retirement.normal_sources().source_pin(),
                sources.normal_sources().source_pin(),
            ),
            "return window normal source differs from actual retirement",
        )?;
        let observed = sources.owner().evidence();
        let actual = &observed["actual_original"];
        let invocation = actual["invocation_id"]
            .as_str()
            .ok_or("fresh recovery invocation")?;
        let group = actual["control_group"]
            .as_str()
            .ok_or("fresh recovery group")?;
        let prefix = owner_prefix(group, sources.candidate())?;
        ensure(
            invocation.len() == 32
                && invocation
                    .bytes()
                    .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v)),
            "fresh recovery invocation is not its actual fixed identifier",
        )?;
        // mkdirat(EXCL semantics) prevents a second deadline from being
        // manufactured by reconstructing this factory in the same invocation.
        let directory = unique_directory(
            sources.work(),
            &format!("working-return-quiescence-{invocation}"),
        )?;
        let mut normal = NormalControl::prepare(&directory, prefix)?;
        let (inventory, inventory_pin) = normal.call(&sources, Operation::Inventory, json!({}))?;
        let unit = format!("{prefix}{}.service", sources.candidate());
        let rows = inventory["units"]
            .as_array()
            .ok_or("actual return writer units")?
            .iter()
            .filter(|r| r["RequestedId"] == unit)
            .collect::<Vec<_>>();
        ensure(
            rows.len() == 1
                && rows[0]["MainPID"] == std::process::id().to_string()
                && rows[0]["InvocationID"] == invocation
                && rows[0]["DropInPaths"] == "",
            "actual PID1 return inventory differs from this fresh owner",
        )?;
        let (paths, remote) = inventory_groups(&inventory, sources.candidate(), prefix)?;
        let groups = paths
            .iter()
            .map(|(p, u)| Group::open(p, u))
            .collect::<Result<Vec<_>>>()?;
        for group in &groups {
            ensure(
                !group.is_frozen()? && bounded(&group.freeze, 16)?.trim() == "0",
                "return freezer cannot claim a pre-existing requested freeze",
            )?;
        }
        let deadline = clock_ms()?
            .checked_add(MAX_SECONDS * 1000)
            .ok_or("new return deadline overflow")?;
        let freeze = FreezeIntent {
            schema: FREEZE_SCHEMA.into(),
            candidate_id: sources.candidate().into(),
            original_boot_id: sources.owner().boot_id().into(),
            admitted_original_boot_id: sources.original_boot_id().into(),
            owner_invocation: invocation.into(),
            purpose: FreezePurpose::Restore,
            base_intent: sources.boot_intent().clone(),
            producer: sources.owner().program_pin().clone(),
            owner_pid: std::process::id(),
            owner_starttime: starttime(std::process::id())?,
            owner_control_group: group.into(),
            deadline_boot_ms: deadline,
            inventory: inventory_pin,
            groups: groups
                .iter()
                .map(|g| {
                    serde_json::from_value(serde_json::to_value(&g.record)?).map_err(Into::into)
                })
                .collect::<Result<_>>()?,
            excluded_remote_scopes: remote,
            critical_excluded: serde_json::from_value(inventory["critical_excluded"].clone())?,
        };
        let envelope = ReturnFreezeIntent {
            schema: INTENT_SCHEMA.into(),
            freeze,
            material_input: sources.owner().input_pin().clone(),
            normal_sources: sources.normal_sources().source_pin().clone(),
            retirement: retirement.report_pin().clone(),
        };
        let intent = save(&directory.join("FREEZE-INTENT.json"), &envelope)?;
        // Own the original-zero undo set before starting a helper. If normal
        // start has an unknown result, Drop publishes release without replay;
        // an actually started helper then exits instead of killing this owner.
        let mut value = Self {
            sources,
            retirement,
            normal,
            intent,
            groups,
            deadline,
            reaper: None,
            directory,
            released: false,
            closed: false,
        };
        let (started, _) = value.normal.call(
            &value.sources,
            Operation::Start,
            json!({
                "producer":value.sources.owner().program_pin(),"freeze_intent":value.intent.pin(),
            }),
        )?;
        ensure(started["exit"] == 0, "normal return thaw start failed")?;
        let ready = value.directory.join("READY.json");
        let until = Instant::now() + Duration::from_secs(15);
        while !ready.exists() {
            ensure(
                Instant::now() < until && clock_ms()? < deadline,
                "independent fresh return thaw did not become ready",
            )?;
            std::thread::sleep(Duration::from_millis(50));
        }
        value.reaper = Some(Reaper::capture(
            SealedInput::open(&files::pin_file(&ready)?)?,
            value.intent.pin(),
            &value.sources,
            deadline,
        )?);
        value.verify_guard_custody()?;
        for group in &value.groups {
            group.set(true)?;
            value.verify_guard_custody()?;
        }
        value.revalidate()?;
        let _frozen = save(
            &value.directory.join("FROZEN.json"),
            &json!({
                "schema":"droidloom.working-return-frozen.v1","freeze_intent":value.intent.pin(),
                "retirement":value.retirement.report_pin(),"deadline_boot_ms":deadline,
                "actual_frozen":value.groups.iter().map(|g|&g.record.path).collect::<Vec<_>>(),
                "old_forward_window_reused":false,"deadline_renewed":false,
            }),
        )?;
        Ok(value)
    }
    fn verify_guard_custody(&self) -> Result<()> {
        ensure(
            !self.released && !self.closed && clock_ms()? < self.deadline,
            "fresh return window ended; its deadline cannot be renewed",
        )?;
        self.intent.revalidate_custody()?;
        self.normal.custody()?;
        self.sources.revalidate_normal_source_custody()?;
        self.reaper
            .as_ref()
            .ok_or("return freeze has no ready independent reaper")?
            .revalidate()
    }
    /// Post-syscall fence before typed label checkpoint adoption. It checks
    /// actual frozen groups and immutable source custody without recursively
    /// checking the one owner/retirement inode whose ctime just changed.
    pub(crate) fn verify_window_custody(&self) -> Result<()> {
        self.verify_guard_custody()?;
        for group in &self.groups {
            ensure(
                group.is_frozen()?,
                "an actual returned writer is no longer frozen",
            )?;
        }
        self.verify_guard_custody()
    }
    pub(crate) fn require_sources(&self, sources: &WorkingRecoverySources) -> Result<()> {
        ensure(
            std::ptr::eq(self.sources.as_ref(), sources),
            "return window belongs to another fresh source factory",
        )?;
        self.revalidate()
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.sources.revalidate()?;
        self.retirement.require_owner(self.sources.owner())?;
        self.verify_window_custody()?;
        self.normal.revalidate()?;
        self.sources.revalidate()
    }
    pub(crate) fn deadline_boot_ms(&self) -> u64 {
        self.deadline
    }
    pub(crate) fn intent_pin(&self) -> &FilePin {
        self.intent.pin()
    }
    fn release(&mut self) -> Result<()> {
        if self.closed {
            return Ok(());
        }
        self.intent.revalidate_custody()?;
        let mut failed = Vec::new();
        for group in self.groups.iter().rev() {
            if let Err(e) = group.set(false) {
                failed.push(format!("{}: {e}", group.record.path));
            }
        }
        ensure(
            failed.is_empty(),
            &format!("fresh return thaw remains incomplete: {failed:?}"),
        )?;
        let body = json!({"schema":RELEASE_SCHEMA,"freeze_intent":self.intent.pin(),
            "actual_thawed":self.groups.iter().map(|g|&g.record.path).collect::<Vec<_>>()});
        let path = self.directory.join("RELEASED.json");
        match std::fs::symlink_metadata(&path) {
            Ok(_) => {
                let record = SealedInput::open(&files::pin_file(&path)?)?;
                ensure(
                    serde_json::from_slice::<Value>(&record.read()?)? == body,
                    "fresh return release belongs to another window",
                )?;
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                let _record = save(&path, &body)?;
            }
            Err(e) => return Err(e.into()),
        }
        self.released = true;
        Ok(())
    }
    pub(crate) fn finish(&mut self) -> Result<()> {
        self.release()?;
        let reaper = self
            .reaper
            .as_ref()
            .ok_or("no actual return thaw process was admitted")?;
        let until = Instant::now() + Duration::from_secs(15);
        let path = self.directory.join("THAWED.json");
        while !path.exists() {
            ensure(
                Instant::now() < until,
                "actual independent return thaw result remains unconfirmed",
            )?;
            std::thread::sleep(Duration::from_millis(50));
        }
        let result = SealedInput::open(&files::pin_file(&path)?)?;
        let v: Value = serde_json::from_slice(&result.read()?)?;
        ensure(
            v["schema"] == THAW_SCHEMA
                && v["freeze_intent"] == serde_json::to_value(self.intent.pin())?
                && v["reason"] == "released"
                && v["failures"] == json!([])
                && v["actual_thawed"]
                    == serde_json::to_value(
                        self.groups
                            .iter()
                            .rev()
                            .map(|g| &g.record.path)
                            .collect::<Vec<_>>(),
                    )?,
            "independent return thaw did not report exact actual released groups",
        )?;
        while !process_retired(&reaper.pidfd, reaper.pid, reaper.birth)? {
            ensure(
                Instant::now() < until,
                "actual return thaw process did not retire",
            )?;
            std::thread::sleep(Duration::from_millis(50));
        }
        for group in &self.groups {
            ensure(
                !group.is_frozen()?,
                "returned writer refroze during release",
            )?;
        }
        result.revalidate()?;
        self.normal.revalidate()?;
        self.sources.revalidate()?;
        self.retirement.revalidate()?;
        self.closed = true;
        Ok(())
    }
}
impl Drop for WorkingReturnQuiescence {
    fn drop(&mut self) {
        if !self.closed {
            if let Err(e) = self.release() {
                eprintln!("fresh returned writer release remains unconfirmed: {e}");
            }
        }
    }
}

pub(super) fn stop_live_owner(fd: &OwnedFd, pid: u32, birth: u64) -> Result<()> {
    if process_retired(fd, pid, birth)? {
        return Ok(());
    }
    // This descriptor was opened on the exact original owner before READY.
    // Refuse a mismatched process before sending any signal.
    ensure(
        pidfd_pid(fd)? == Some(pid) && starttime(pid)? == birth,
        "return guard may only terminate its actually held original owner",
    )?;
    rustix::process::pidfd_send_signal(fd, rustix::process::Signal::KILL)?;
    let until = Instant::now() + Duration::from_secs(10);
    loop {
        if process_retired(fd, pid, birth)? {
            return Ok(());
        }
        ensure(
            Instant::now() < until,
            "held return owner retirement remains unconfirmed; writers stay frozen",
        )?;
        std::thread::sleep(Duration::from_millis(25));
    }
}
fn validate_envelope(v: &ReturnFreezeIntent, config: &Path) -> Result<&'static str> {
    let f = &v.freeze;
    ensure(
        v.schema == INTENT_SCHEMA
            && f.schema == FREEZE_SCHEMA
            && f.purpose == FreezePurpose::Restore
            && fs::valid_digest(&f.candidate_id)
            && crate::cold_working_recovery::contract::uuid(&f.original_boot_id)
            && crate::cold_working_recovery::contract::uuid(&f.admitted_original_boot_id)
            && f.owner_invocation.len() == 32
            && f.owner_invocation
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            && f.owner_pid > 1
            && f.groups.len() <= 64
            && !f.groups.is_empty(),
        "fresh return thaw intent identity or finite scope differs",
    )?;
    let prefix = owner_prefix(&f.owner_control_group, &f.candidate_id)?;
    let work = Path::new("/var/lib/droidloom-qualification")
        .join(format!("working-qualification-{}", f.candidate_id));
    ensure(
        config
            == work.join(format!(
                "working-return-quiescence-{}/FREEZE-INTENT.json",
                f.owner_invocation
            ))
            && f.base_intent.path == work.join("BOOT-INTENT.json")
            && f.inventory.path
                == config
                    .parent()
                    .ok_or("return thaw parent")?
                    .join("return-writer-inventory/RESULT.json")
            && v.retirement.path.starts_with(&work)
            && v.retirement.path.file_name() == Some(std::ffi::OsStr::new("BOOT-RETIREMENT.json"))
            && f.producer
                .path
                .starts_with("/var/lib/droidloom-qualification")
            && v.material_input
                .path
                .starts_with("/var/lib/droidloom-qualification"),
        "fresh return thaw left its exact private source layout",
    )?;
    for pin in [
        &f.producer,
        &f.base_intent,
        &f.inventory,
        &v.material_input,
        &v.normal_sources,
        &v.retirement,
    ] {
        let path = fs::absolute_string(&pin.path)?;
        ensure(
            pin.bytes > 0
                && fs::valid_digest(&pin.sha256)
                && path
                    .split('/')
                    .skip(1)
                    .all(|p| !p.is_empty() && p != "." && p != "..")
                && !path.contains(['\0', '\n', '\r']),
            "fresh return thaw source pin or path is not canonical",
        )?;
    }
    Ok(prefix)
}

pub(in crate::cold_original_qualification) fn run_thaw_guard(
    config: &Path,
    expected: &str,
) -> Result<()> {
    let pin = files::pin_file(config)?;
    ensure(
        pin.sha256 == expected,
        "fresh return thaw config hash differs",
    )?;
    let sealed = SealedInput::open(&pin)?;
    let envelope: ReturnFreezeIntent = serde_json::from_slice(&sealed.read()?)?;
    let prefix = validate_envelope(&envelope, config)?;
    let v = &envelope.freeze;
    let thaw_owner = owner::verify_working_return_thaw_owner(&v.candidate_id, &v.original_boot_id)?;
    let initial = clock_ms()?;
    ensure(
        v.deadline_boot_ms > initial && v.deadline_boot_ms - initial <= MAX_SECONDS * 1000,
        "fresh return thaw cannot renew an expired or unbounded deadline",
    )?;
    let exe = File::open("/proc/self/exe")?;
    let (_, source) = files::open_pin(&v.producer)?;
    ensure(
        fs::stat(&exe)? == source
            && fs::hash(&exe)? == v.producer.sha256
            && fs::stat(&exe)? == source,
        "fresh return thaw is not its actual normal producer",
    )?;
    let own_args = [
        fs::absolute_string(&v.producer.path)?,
        MODE.into(),
        "--config".into(),
        fs::absolute_string(config)?,
        "--config-sha256".into(),
        expected.into(),
    ]
    .join("\0")
        + "\0";
    ensure(
        bounded(&File::open("/proc/self/cmdline")?, 32768)? == own_args,
        "fresh return thaw actual complete argv differs",
    )?;
    let base = SealedInput::open(&v.base_intent)?;
    let base_value: Value = serde_json::from_slice(&base.read()?)?;
    let material = SealedInput::open(&envelope.material_input)?;
    let material_value: Value = serde_json::from_slice(&material.read()?)?;
    let retirement = SealedInput::open(&envelope.retirement)?;
    let retirement_value: Value = serde_json::from_slice(&retirement.read()?)?;
    let normal = SealedInput::open(&envelope.normal_sources)?;
    ensure(
        base_value["schema"] == "droidloom.working-qualification-boot-intent.v1"
            && base_value["candidate_id"] == v.candidate_id
            && base_value["original_boot_id"] == v.admitted_original_boot_id
            && base_value["normal_producer"] == serde_json::to_value(&v.producer)?
            && base_value["normal_sources"] == serde_json::to_value(&envelope.normal_sources)?
            && material_value["candidate_id"] == v.candidate_id
            && material_value["normal_producer"] == base_value["normal_producer"]
            && material_value["normal_sources"] == base_value["normal_sources"]
            && retirement_value["schema"] == "droidloom.working-boot-retirement.v1"
            && retirement_value["candidate_id"] == v.candidate_id
            && retirement_value["current_original_boot_id"] == v.original_boot_id
            && retirement_value["prepared_original_boot_id"] == v.admitted_original_boot_id
            && retirement_value["intent"] == serde_json::to_value(&v.base_intent)?
            && retirement_value["normal_sources"] == base_value["normal_sources"],
        "fresh return thaw source chain differs from its actual original owner",
    )?;
    let inventory = SealedInput::open(&v.inventory)?;
    let iv: Value = serde_json::from_slice(&inventory.read()?)?;
    ensure(
        iv["schema"] == "droidloom.working-return-window-normal-command.v1"
            && iv["actual"]["schema"] == RESPONSE
            && iv["actual"]["operation"] == "return-writer-inventory"
            && iv["actual"]["candidate_id"] == v.candidate_id
            && iv["actual"]["intent"] == serde_json::to_value(&v.base_intent)?
            && iv["actual"]["original"]["boot_id"] == v.original_boot_id,
        "fresh return thaw inventory has another actual original command",
    )?;
    let (allowed, remote) = inventory_groups(&iv["actual"]["result"], &v.candidate_id, prefix)?;
    ensure(
        allowed
            .iter()
            .map(|p| (&p.0, &p.1))
            .eq(v.groups.iter().map(|g| (&g.path, &g.unit)))
            && remote == v.excluded_remote_scopes
            && iv["actual"]["result"]["critical_excluded"]
                == serde_json::to_value(&v.critical_excluded)?,
        "return thaw groups differ from normal PID1 and remote-session inventory",
    )?;
    let groups = v
        .groups
        .iter()
        .map(Group::from_record)
        .collect::<Result<Vec<_>>>()?;
    let owner_fd = rustix::process::pidfd_open(
        rustix::process::Pid::from_raw(i32::try_from(v.owner_pid)?)
            .ok_or("return owner PID range")?,
        rustix::process::PidfdFlags::empty(),
    )?;
    let owner_mode = if prefix == "droidloom-working-cold@" {
        "run-working-qualification"
    } else {
        "recover-working-qualification"
    };
    let expected_owner = [
        fs::absolute_string(&v.producer.path)?,
        owner_mode.into(),
        "--config".into(),
        fs::absolute_string(&envelope.material_input.path)?,
        "--config-sha256".into(),
        envelope.material_input.sha256.clone(),
    ]
    .join("\0")
        + "\0";
    ensure(
        !process_retired(&owner_fd, v.owner_pid, v.owner_starttime)?
            && bounded(&File::open(format!("/proc/{}/cgroup", v.owner_pid))?, 4096)?
                == format!("0::{}\n", v.owner_control_group)
            && bounded(
                &File::open(format!("/proc/{}/cmdline", v.owner_pid))?,
                32768,
            )? == expected_owner
            && fs::stat(&File::open(format!("/proc/{}/exe", v.owner_pid))?)? == source,
        "fresh return thaw owner is not the exact live source process",
    )?;
    let directory = config.parent().ok_or("fresh return thaw directory")?;
    let mut cleanup = ThawCleanup::new(groups, directory, &pin)?;
    cleanup.schema = THAW_SCHEMA;
    let monitored = (|| -> Result<&'static str> {
        let _ready = save(
            &directory.join("READY.json"),
            &json!({
                "schema":READY_SCHEMA,"candidate_id":v.candidate_id,"freeze_intent":pin,
                "pid":std::process::id(),"starttime":starttime(std::process::id())?,
                "deadline_boot_ms":v.deadline_boot_ms,"executable":source,
                "namespaces":thaw_owner["namespaces"],
            }),
        )?;
        let reason = loop {
            for record in [&sealed, &base, &material, &retirement, &normal, &inventory] {
                record.revalidate_custody()?;
            }
            owner::verify_working_return_thaw_owner(&v.candidate_id, &v.original_boot_id)?;
            ensure(
                fs::stat(&exe)? == source,
                "fresh return guard executable changed",
            )?;
            if directory.join("RELEASED.json").exists() {
                let released =
                    SealedInput::open(&files::pin_file(&directory.join("RELEASED.json"))?)?;
                let actual: Value = serde_json::from_slice(&released.read()?)?;
                ensure(
                    actual
                        == json!({"schema":RELEASE_SCHEMA,"freeze_intent":pin,
                    "actual_thawed":cleanup.groups.iter().map(|g|&g.record.path).collect::<Vec<_>>()})
                        && cleanup
                            .groups
                            .iter()
                            .all(|g| g.is_frozen().is_ok_and(|f| !f)),
                    "fresh return release did not actually thaw its exact groups",
                )?;
                break "released";
            }
            if process_retired(&owner_fd, v.owner_pid, v.owner_starttime)? {
                break "owner-retired";
            }
            if clock_ms()? >= v.deadline_boot_ms {
                break "deadline";
            }
            std::thread::sleep(Duration::from_millis(200));
        };
        for record in [&sealed, &base, &material, &retirement, &normal, &inventory] {
            record.revalidate()?;
        }
        (&exe).rewind()?;
        ensure(
            fs::stat(&exe)? == source
                && fs::hash(&exe)? == v.producer.sha256
                && fs::stat(&exe)? == source,
            "fresh return guard whole source changed",
        )?;
        Ok(reason)
    })();
    let reason = monitored
        .as_ref()
        .copied()
        .unwrap_or("guard-validation-failed");
    let cause = monitored.as_ref().err().map(ToString::to_string);
    // Never release frozen writers while a timed-out or failed transaction
    // may still be writing. This reaper can signal only its original pidfd.
    if matches!(reason, "deadline" | "guard-validation-failed") {
        if let Err(error) = stop_live_owner(&owner_fd, v.owner_pid, v.owner_starttime) {
            let failure = json!({"schema":"droidloom.working-return-thaw-blocked.v1",
                "freeze_intent":pin,"reason":reason,"observed_error":cause,
                "owner_retirement_error":error.to_string(),"writers_released":false,
                "qualification_pass":false});
            let written = save(
                &directory.join("OWNER-RETIREMENT-UNCONFIRMED.json"),
                &failure,
            );
            // Suppress the generic Drop auto-thaw on this one unresolved
            // lifetime boundary. Fixed cgroups remain frozen; PID1, SSH and
            // networking stay outside them. No THAWED success is emitted.
            std::mem::forget(cleanup);
            written?;
            return Err(error);
        }
    }
    let thaw = cleanup.finish(reason, cause.as_deref());
    if let Err(error) = monitored {
        if let Err(other) = &thaw {
            eprintln!("fresh return thaw also failed: {other}");
        }
        return Err(error);
    }
    thaw
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::Write,
        process::{Command, Stdio},
    };
    #[test]
    fn returned_freezer_driver_is_closed_and_both_actual_python_variants_parse() -> Result<()> {
        for prefix in ["droidloom-working-recovery@", "droidloom-working-cold@"] {
            let driver = normal_driver(prefix)?;
            for forbidden in [
                "elif op=='systemctl':",
                "grub-arm",
                "grub-disarm",
                "public-apply",
                "native-apply",
                "__original-once-thaw",
                "__working-cold-thaw",
            ] {
                assert!(!driver.contains(forbidden), "{forbidden}");
            }
            assert!(
                driver.contains("return-writer-inventory") && driver.contains("return-thaw-start")
            );
            assert!(driver.contains("droidloom-working-return-thaw@") && driver.contains(MODE));
            let mut child = Command::new("/usr/bin/python3.14")
                .args([
                    "-I",
                    "-B",
                    "-c",
                    "import ast,sys; ast.parse(sys.stdin.read())",
                ])
                .stdin(Stdio::piped())
                .stdout(Stdio::null())
                .stderr(Stdio::piped())
                .spawn()?;
            child
                .stdin
                .take()
                .ok_or("test child stdin")?
                .write_all(driver.as_bytes())?;
            let output = child.wait_with_output()?;
            ensure(
                output.status.success(),
                &String::from_utf8_lossy(&output.stderr),
            )?;
        }
        assert!(normal_driver("arbitrary@").is_err());
        Ok(())
    }
    #[test]
    fn returned_freezer_owner_prefix_excludes_old_and_foreign_units() -> Result<()> {
        let candidate = "a".repeat(64);
        for prefix in ["droidloom-working-cold@", "droidloom-working-recovery@"] {
            assert_eq!(
                owner_prefix(
                    &format!("/system.slice/{prefix}{candidate}.service"),
                    &candidate
                )?,
                prefix
            );
        }
        for group in [
            format!("/system.slice/droidloom-original-qualification@{candidate}.service"),
            format!("/system.slice/droidloom-working-return-thaw@{candidate}.service"),
            format!(
                "/system.slice/droidloom-working-recovery@{}.service",
                "b".repeat(64)
            ),
            format!("/user.slice/droidloom-working-recovery@{candidate}.service"),
        ] {
            assert!(owner_prefix(&group, &candidate).is_err());
        }
        Ok(())
    }
    #[test]
    fn returned_thaw_reaper_uses_actual_pidfd_birth_and_confirms_exit_before_release() -> Result<()>
    {
        let mut child = Command::new("/usr/bin/sleep")
            .arg("30")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;
        let pid = child.id();
        let fd = rustix::process::pidfd_open(
            rustix::process::Pid::from_raw(i32::try_from(pid)?).ok_or("test PID")?,
            rustix::process::PidfdFlags::empty(),
        )?;
        let birth = starttime(pid)?;
        let tested = (|| -> Result<()> {
            ensure(
                !process_retired(&fd, pid, birth)?,
                "actual child unexpectedly exited",
            )?;
            ensure(
                stop_live_owner(&fd, pid, birth + 1).is_err(),
                "foreign birth was signalled",
            )?;
            ensure(
                child.try_wait()?.is_none(),
                "wrong-birth refusal killed the actual child",
            )?;
            stop_live_owner(&fd, pid, birth)?;
            ensure(
                process_retired(&fd, pid, birth)?,
                "actual held child did not retire",
            )?;
            let status = child.wait()?;
            use std::os::unix::process::ExitStatusExt;
            ensure(
                status.signal() == Some(9),
                "actual held child did not receive fixed KILL",
            )?;
            Ok(())
        })();
        if tested.is_err() {
            let _ = child.kill();
            let _ = child.wait();
        }
        tested
    }
}
