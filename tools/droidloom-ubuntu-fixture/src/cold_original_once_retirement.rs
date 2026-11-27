//! Restoration authority produced by observations in the returned original
//! kernel, or by a separately bounded abort before a boot was ever armed.
//! Serialized command results and a requested reboot cannot construct this type.
use super::{OriginalQualificationAuthority, RetirementSource, owner::SealedInput, state::Phase};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::{
        OriginalDataTransaction, WorkingDataRetired,
        labels::{OriginalLabelRestoration, OriginalLabelRestoreSources},
    },
    cold_original_once_recovery::contract as c,
    ensure, fs,
    model::Identity,
};
use rustix::fs::{FileType, FlockOperation};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::Seek,
    path::{Path, PathBuf},
    rc::Rc,
};

const PID1_STOPPED: &str = "9d1aaa27d60140bd96365438aad20286";
const PID1_STARTED: &str = "39f53479d3a045ac8e11786248231fbf";
const REQUIRED_STOPPED: [&str; 5] = [
    "droidloom-production.service",
    "droidloom-instance-launcher.service",
    "droidloom-instance-factory.service",
    "droidloom-early-observer.service",
    "user@1000.service",
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    NormalReturn,
    FailedReturn,
    UnbootedAbort,
    PreparationInterrupted,
}
impl Kind {
    fn name(self) -> &'static str {
        match self {
            Self::NormalReturn => "verified-normal-return",
            Self::FailedReturn => "verified-failed-return",
            Self::UnbootedAbort => "verified-unbooted-abort",
            Self::PreparationInterrupted => "verified-preparation-interrupted-return",
        }
    }
}

fn attributes(file: &File) -> Result<BTreeMap<String, String>> {
    let mut names = vec![0u8; 65536];
    let count = rustix::fs::flistxattr(file, names.as_mut_slice())?;
    ensure(
        count <= names.len(),
        "return xattr inventory exceeded its bound",
    )?;
    names.truncate(count);
    ensure(
        names.is_empty() || names.last() == Some(&0),
        "return xattr inventory is unterminated",
    )?;
    let mut out = BTreeMap::new();
    for n in names.split(|b| *b == 0).filter(|n| !n.is_empty()) {
        let name = std::str::from_utf8(n)?;
        ensure(
            name == "security.selinux",
            "return input has an unexpected non-label xattr",
        )?;
        let mut bytes = vec![0u8; 65536];
        let len = rustix::fs::fgetxattr(file, name, bytes.as_mut_slice())?;
        ensure(
            out.insert(name.to_owned(), hex::encode(&bytes[..len]))
                .is_none(),
            "duplicate return xattr",
        )?;
    }
    Ok(out)
}
fn only_label_clock(before: &Identity, after: &Identity) -> Result<()> {
    let mut changed = after.clone();
    changed.ctime_sec = before.ctime_sec;
    changed.ctime_nsec = before.ctime_nsec;
    ensure(
        changed == *before,
        "label restoration changed an unrelated identity field",
    )
}
struct Readback {
    pin: FilePin,
    held: File,
    identity: Identity,
    attributes: BTreeMap<String, String>,
}
impl Readback {
    fn open(path: &Path, mode: u32, limit: u64) -> Result<Self> {
        let p = fs::absolute_string(path)?;
        let tree = fs::Tree::open("/", 0)?;
        let held = tree.file(&p)?;
        let identity = fs::stat(&held)?;
        ensure(
            FileType::from_raw_mode(identity.mode) == FileType::RegularFile
                && identity.mode & 0o7777 == mode
                && identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && identity.size <= limit,
            "original return input has an unexpected owner, mode, link or size",
        )?;
        let attributes = attributes(&held)?;
        let digest = fs::hash(&held)?;
        let v = Self {
            pin: FilePin {
                path: path.into(),
                bytes: identity.size,
                sha256: digest,
            },
            held,
            identity,
            attributes,
        };
        v.revalidate()?;
        Ok(v)
    }
    fn revalidate_custody(&self) -> Result<()> {
        let (named, id) = files::open_pin(&self.pin)?;
        ensure(
            id == self.identity
                && fs::stat(&self.held)? == id
                && attributes(&self.held)? == self.attributes
                && attributes(&named)? == self.attributes
                && fs::stat(&named)? == id
                && fs::stat(&self.held)? == id,
            "held return evidence was changed or replaced",
        )
    }
    fn revalidate(&self) -> Result<()> {
        self.revalidate_custody()?;
        (&self.held).rewind()?;
        ensure(
            fs::hash(&self.held)? == self.pin.sha256,
            "return evidence body changed",
        )?;
        self.revalidate_custody()
    }
    fn bytes(&self) -> Result<Vec<u8>> {
        self.revalidate()?;
        let b = files::read_pin(&self.pin, self.pin.bytes)?;
        self.revalidate()?;
        Ok(b)
    }
    fn json(&self) -> Result<Value> {
        Ok(serde_json::from_slice(&self.bytes()?)?)
    }
    fn accept_custody(&mut self, restoration: &OriginalLabelRestoration) -> Result<()> {
        if self.pin.path != restoration.path() {
            return Ok(());
        }
        ensure(
            (self.identity == *restoration.before_identity()
                || self.identity == *restoration.after_identity())
                && fs::stat(&self.held)? == *restoration.after_identity(),
            "opaque restoration is not this actual held return input",
        )?;
        only_label_clock(restoration.before_identity(), restoration.after_identity())?;
        self.identity = restoration.after_identity().clone();
        self.attributes = attributes(&self.held)?;
        self.revalidate_custody()
    }
}

fn save(path: &Path, value: &Value) -> Result<SealedInput> {
    let mut bytes = serde_json::to_vec(value)?;
    bytes.push(b'\n');
    ensure(
        bytes.len() <= 32 * 1024 * 1024,
        "bounded actual retirement report required",
    )?;
    files::write_new(path, &bytes, 0o400)?;
    File::open(path.parent().ok_or("return proof parent absent")?)?.sync_all()?;
    SealedInput::open(&files::pin_file(path)?)
}
fn field<'a>(v: &'a Value, k: &str) -> Result<&'a str> {
    v[k].as_str()
        .ok_or_else(|| format!("actual return evidence lacks {k}").into())
}
fn body_pin(v: &Value, path: &Path) -> Result<FilePin> {
    let bytes = v["bytes"].as_u64().ok_or("actual output size missing")?;
    let sha = field(v, "sha256")?;
    ensure(
        bytes <= 64 * 1024 * 1024 && fs::valid_digest(sha),
        "bounded normal output digest required",
    )?;
    Ok(FilePin {
        path: path.into(),
        bytes,
        sha256: sha.into(),
    })
}

struct RuntimeEvidence {
    directory: PathBuf,
    held_directory: File,
    identity: RefCell<Identity>,
    lock: File,
    lock_identity: RefCell<Identity>,
    files: RefCell<BTreeMap<String, Readback>>,
    json: BTreeMap<String, Value>,
}
impl RuntimeEvidence {
    fn read(authority: &OriginalQualificationAuthority) -> Result<Option<Self>> {
        let directory = Path::new("/var/lib/droidloom/qualification")
            .join(format!("original-once-{}", authority.candidate_id()))
            .join("runtime-evidence");
        let tree = match fs::Tree::open(&fs::absolute_string(&directory)?, 0) {
            Ok(v) => v,
            Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
                return Ok(None);
            }
            Err(e) => return Err(e),
        };
        let identity = fs::stat(&tree.root)?;
        ensure(
            identity.mode & 0o7777 == 0o700 && identity.uid == 0 && identity.gid == 0,
            "runtime evidence directory custody differs",
        )?;
        let lock = tree.file("/owner.lock")?;
        let lock_identity = fs::stat(&lock)?;
        ensure(
            lock_identity.mode & 0o7777 == 0o400
                && lock_identity.uid == 0
                && lock_identity.gid == 0
                && lock_identity.size == 0
                && lock_identity.nlink == 1,
            "runtime owner lock differs",
        )?;
        rustix::fs::flock(&lock, FlockOperation::NonBlockingLockExclusive)?;
        let mut allowed = BTreeSet::from([
            "owner.lock".to_owned(),
            "CANDIDATE-OBSERVED.json".into(),
            "COLLECTION-OBSERVED.json".into(),
            "COLLECTION-SKIPPED.json".into(),
            "RETURN-SELECTED.json".into(),
            "RETURN-REQUESTED.json".into(),
        ]);
        for verb in ["collect", "rollback", "reboot"] {
            for suffix in [
                ".stdout",
                ".stderr",
                "-INTENT.json",
                "-RESULT.json",
                "-TIMEOUT.json",
            ] {
                allowed.insert(format!("{verb}{suffix}"));
            }
        }
        let mut files = BTreeMap::new();
        let mut json = BTreeMap::new();
        let mut names = BTreeSet::new();
        for e in std::fs::read_dir(&directory)? {
            let name = e?
                .file_name()
                .into_string()
                .map_err(|_| "invalid runtime evidence member")?;
            ensure(
                names.len() < 32 && allowed.contains(&name) && names.insert(name.clone()),
                "unexpected runtime evidence member",
            )?;
            if name == "owner.lock" {
                continue;
            }
            // A killed writer may have left mode0600 output. Preserve that
            // failed fact; it is never accepted as a completed sealed record.
            let actual = std::fs::symlink_metadata(directory.join(&name))?;
            use std::os::unix::fs::PermissionsExt;
            let mode = actual.permissions().mode() & 0o7777;
            ensure(
                mode == 0o400 || mode == 0o600,
                "runtime evidence is neither sealed nor an interrupted source write",
            )?;
            let file = Readback::open(&directory.join(&name), mode, 64 * 1024 * 1024)?;
            if mode == 0o400 && name.ends_with(".json") {
                json.insert(name.clone(), file.json()?);
            }
            files.insert(name, file);
        }
        let result = Self {
            directory,
            held_directory: tree.root,
            identity: RefCell::new(identity),
            lock,
            lock_identity: RefCell::new(lock_identity),
            files: RefCell::new(files),
            json,
        };
        result.revalidate()?;
        Ok(Some(result))
    }
    fn revalidate_custody(&self) -> Result<()> {
        let tree = fs::Tree::open(&fs::absolute_string(&self.directory)?, 0)?;
        let now = fs::stat(&tree.root)?;
        ensure(
            now == *self.identity.borrow()
                && fs::stat(&self.held_directory)? == now
                && fs::stat(&self.lock)? == *self.lock_identity.borrow()
                && tree.identity("/owner.lock")? == *self.lock_identity.borrow(),
            "runtime evidence tree changed after original return",
        )?;
        rustix::fs::flock(&self.lock, FlockOperation::NonBlockingLockExclusive)?;
        for f in self.files.borrow().values() {
            f.revalidate_custody()?;
        }
        Ok(())
    }
    fn accept_custody(&self, restoration: &OriginalLabelRestoration) -> Result<()> {
        for (path, held, identity) in [
            (&self.directory, &self.held_directory, &self.identity),
            (
                &self.directory.join("owner.lock"),
                &self.lock,
                &self.lock_identity,
            ),
        ] {
            if path == restoration.path() {
                let mut old = identity.borrow_mut();
                ensure(
                    (*old == *restoration.before_identity()
                        || *old == *restoration.after_identity())
                        && fs::stat(held)? == *restoration.after_identity(),
                    "runtime witness restoration is not its held original inode",
                )?;
                only_label_clock(restoration.before_identity(), restoration.after_identity())?;
                *old = restoration.after_identity().clone();
            }
        }
        for f in self.files.borrow_mut().values_mut() {
            f.accept_custody(restoration)?;
        }
        self.revalidate_custody()
    }
    fn revalidate(&self) -> Result<()> {
        self.revalidate_custody()?;
        for f in self.files.borrow().values() {
            f.revalidate()?;
        }
        self.revalidate_custody()
    }
    fn command(&self, verb: &str, intent: &str, boot: &str) -> Result<Option<Value>> {
        let Some(result) = self.json.get(&format!("{verb}-RESULT.json")) else {
            return Ok(None);
        };
        ensure(
            result["schema"] == "droidloom.original-once-maintenance-command.v1"
                && result["intent_sha256"] == intent
                && result["boot_id"] == boot
                && result["verb"] == verb,
            "maintenance result belongs to a different actual intent or boot",
        )?;
        let Some(start) = self.json.get(&format!("{verb}-INTENT.json")) else {
            return Err("completed command lacks its durable source intent".into());
        };
        ensure(
            start["intent_sha256"] == intent && start["boot_id"] == boot && start["verb"] == verb,
            "maintenance command's start identity differs",
        )?;
        if result["completed"] != true || result["exit_code"] != 0 {
            return Ok(None);
        }
        ensure(
            !self.json.contains_key(&format!("{verb}-TIMEOUT.json")),
            "timed out command cannot become completed authority",
        )?;
        let files = self.files.borrow();
        for suffix in ["stdout", "stderr"] {
            let name = format!("{verb}.{suffix}");
            let file = files.get(&name).ok_or("sealed maintenance stream absent")?;
            ensure(
                file.identity.mode & 0o7777 == 0o400
                    && super::same_pin(&file.pin, &body_pin(&result[suffix], &file.pin.path)?),
                "normal maintenance output no longer matches its source-produced digest",
            )?;
        }
        Ok(Some(files[&format!("{verb}.stdout")].json()?))
    }
}

fn original_readback(
    authority: &OriginalQualificationAuthority,
    work: &Path,
    boot: Option<&str>,
) -> Result<(Value, SealedInput)> {
    authority.verify_current_owner()?;
    let source: Value = serde_json::from_slice(&authority.intent.read()?)?;
    let grub_pin: FilePin = serde_json::from_value(source["original_grub"].clone())?;
    let original: Value = serde_json::from_slice(&files::read_pin(&grub_pin, 1024 * 1024)?)?;
    let cfg = original["preserved"]
        .as_array()
        .ok_or("original GRUB preimage inventory")?
        .iter()
        .find(|v| v["source"]["path"] == "/boot/grub/grub.cfg")
        .ok_or("original grub.cfg source")?["source"]
        .clone();
    let suffix = work
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or("retirement work name")?;
    let read = super::commands::call(
        authority,
        &format!("{suffix}-grub"),
        "grub-read",
        json!({"original_cfg_sha256":cfg["sha256"]}),
        45,
    )?;
    ensure(
        read.report["after_fields"]
            .as_object()
            .ok_or("actual GRUB fields")?
            .get("next_entry")
            .is_none_or(|v| v == ""),
        "original return still has an armed one-shot selection",
    )?;
    let journal = if let Some(boot) = boot {
        ensure(c::uuid(boot), "actual candidate boot identity")?;
        Some(super::commands::call(
            authority,
            &format!("{suffix}-journal"),
            "retirement-journal",
            json!({"boot":boot}),
            150,
        )?)
    } else {
        None
    };
    let actual = json!({"schema":"droidloom.actual-original-return-observation.v1",
        "original_kernel":c::ORIGINAL_KERNEL,"original_boot_id":authority.owner.borrow().boot_id(),
        "grub":read.report["original"],"grub_cfg":cfg,
        "grubenv":{"path":"/boot/grub/grubenv","bytes":1024,"sha256":read.report["after"]["sha256"]},
        "grubenv_list_exit":read.report["readback"]["exit"],"grubenv_fields":read.report["after_fields"],
        "journal":journal.as_ref().map(|v|&v.report)});
    ensure(
        actual["grub"]["original_entry"] == c::ORIGINAL_ENTRY
            && actual["grub"]["original_default"] == c::ORIGINAL_ENTRY
            && actual["grubenv_list_exit"] == 0,
        "actual normal original boot target differs",
    )?;
    let proof = save(
        &work.join("ORIGINAL-RETURN-OBSERVATION.json"),
        &json!({"schema":"droidloom.original-once-original-readback.v1",
        "intent":authority.intent.pin(),"normal_grub_command":read.pin,"normal_journal_command":journal.as_ref().map(|v|&v.pin),"actual":actual}),
    )?;
    authority.verify_current_owner()?;
    Ok((actual, proof))
}

fn normal_chain(
    runtime: &RuntimeEvidence,
    intent: &str,
    boot: &str,
    actual: &Value,
) -> Result<bool> {
    let Some(collect) = runtime.command("collect", intent, boot)? else {
        return Ok(false);
    };
    let Some(rollback) = runtime.command("rollback", intent, boot)? else {
        return Ok(false);
    };
    let Some(reboot) = runtime.command("reboot", intent, boot)? else {
        return Ok(false);
    };
    normal_chain_outputs(
        &collect,
        &rollback,
        &reboot,
        &runtime.json,
        intent,
        boot,
        actual,
    )
}

/// Pure historical comparison shared by the live return factory and the
/// separate read-only archive observer. It cannot construct either authority.
pub(super) fn normal_chain_outputs(
    collect: &Value,
    rollback: &Value,
    reboot: &Value,
    runtime_json: &BTreeMap<String, Value>,
    intent: &str,
    boot: &str,
    actual: &Value,
) -> Result<bool> {
    let status = |s: &Value| {
        s["boot_id"] == boot
            && s["kernel"] == c::KERNEL
            && s["selinux_enforcing"] == true
            && s["selinux_context"] == "u:system_r:p4_linux_maintenance_t:s0"
            && s["system_units"]["exit"] == 0
            && s["user_units"]["exit"] == 0
            && s["system_units"]["observation_failed"] != true
            && s["user_units"]["observation_failed"] != true
    };
    if collect["schema"] != "droidloom-maintenance-evidence-v1"
        || collect["same_boot"] != true
        || collect["journal_exit"] != 0
        || !status(&collect)
        || !status(&collect["status_after"])
        || rollback["schema"] != "droidloom-maintenance-rollback-v1"
        || rollback["original_entry"] != c::ORIGINAL_ENTRY
        || rollback["reboot_requested"] != false
        || reboot["schema"] != "droidloom-maintenance-reboot-v1"
        || reboot["target"] != c::ORIGINAL_ENTRY
        || reboot["requested"] != true
        || reboot["completed"] != false
    {
        return Ok(false);
    }
    for (name, schema) in [
        (
            "RETURN-SELECTED.json",
            "droidloom.original-once-return-selected.v1",
        ),
        (
            "RETURN-REQUESTED.json",
            "droidloom.original-once-return-requested.v1",
        ),
    ] {
        let Some(v) = runtime_json.get(name) else {
            return Ok(false);
        };
        ensure(
            v["schema"] == schema && v["intent_sha256"] == intent && v["boot_id"] == boot,
            "return record belongs to another actual intent or boot",
        )?;
    }
    Ok(journal_retirement(&actual["journal"], boot))
}
fn journal_retirement(journal: &Value, boot: &str) -> bool {
    if journal["verify_exit"] != 0 || journal["exit"] != 0 {
        return false;
    }
    let Some(rows) = journal["rows"].as_array() else {
        return false;
    };
    let expected = boot.replace('-', "");
    let mut stopped = BTreeSet::new();
    let mut reboot = false;
    let mut shutdown = false;
    let mut bad = false;
    for row in rows {
        if row["_BOOT_ID"] != expected {
            return false;
        }
        if row["_PID"] != "1" || row["_UID"] != "0" || row["_EXE"] != "/usr/lib/systemd/systemd" {
            continue;
        }
        let unit = row["UNIT"].as_str().unwrap_or("");
        if REQUIRED_STOPPED.contains(&unit)
            && row["MESSAGE_ID"] == PID1_STOPPED
            && row["JOB_RESULT"] == "done"
        {
            stopped.insert(unit);
        }
        if (REQUIRED_STOPPED.contains(&unit)
            || unit == "systemd-reboot.service"
            || unit == "reboot.target")
            && (row.get("UNIT_RESULT").is_some_and(|v| v != "success")
                || row.get("JOB_RESULT").is_some_and(|v| v != "done"))
        {
            bad = true;
        }
        if unit == "reboot.target"
            && row["MESSAGE_ID"] == PID1_STARTED
            && row["JOB_RESULT"] == "done"
        {
            reboot = true;
        }
        if row["MESSAGE"] == "Shutting down." {
            shutdown = true;
        }
    }
    !bad && reboot && shutdown && stopped == REQUIRED_STOPPED.into_iter().collect()
}

/// Actual restoration custody. The current owner, source archive-only factory,
/// synchronized working OFDs and all observed evidence remain held together.
pub(crate) struct OriginalRetirement {
    authority: Rc<OriginalQualificationAuthority>,
    sources: OriginalLabelRestoreSources,
    working: WorkingDataRetired,
    kind: Kind,
    report: Value,
    sealed: SealedInput,
    observation: SealedInput,
    runtime: Option<RuntimeEvidence>,
    grubenv: RefCell<Readback>,
    pid: u32,
}
impl OriginalRetirement {
    /// The complete currently held runtime inventory, obtained only after real
    /// original return and retirement. New runtime files never become original
    /// label preimages. The dispatcher may archive exactly these members only
    /// after the full label transaction has finished.
    pub(super) fn runtime_inventory(&self) -> Result<Value> {
        self.revalidate()?;
        let value = if let Some(runtime) = &self.runtime {
            runtime.revalidate()?;
            let rows = runtime
                .files
                .borrow()
                .iter()
                .map(|(name, f)| {
                    json!({
                        "name":name,"pin":f.pin,"identity":f.identity,"attributes":f.attributes
                    })
                })
                .collect::<Vec<_>>();
            json!({"directory":runtime.directory,"directory_identity":runtime.identity.borrow().clone(),
                "owner_lock_identity":runtime.lock_identity.borrow().clone(),"files":rows})
        } else {
            Value::Null
        };
        self.revalidate()?;
        Ok(
            json!({"schema":"droidloom.original-once-held-runtime-inventory.v1","candidate_id":self.candidate_id(),"actual_retirement":self.report_pin(),"actual":value}),
        )
    }
    pub(crate) fn authority(&self) -> &OriginalQualificationAuthority {
        &self.authority
    }
    pub(crate) fn candidate_id(&self) -> &str {
        self.authority.candidate_id()
    }
    pub(crate) fn source_pin(&self) -> &FilePin {
        self.sources.source_pin()
    }
    pub(crate) fn sources(&self) -> &OriginalLabelRestoreSources {
        &self.sources
    }
    pub(crate) fn report(&self) -> &Value {
        &self.report
    }
    pub(crate) fn report_pin(&self) -> &FilePin {
        self.sealed.pin()
    }
    pub(super) fn synchronous_paths(&self) -> BTreeSet<PathBuf> {
        let mut paths = BTreeSet::from([self.grubenv.borrow().pin.path.clone()]);
        if let Some(runtime) = &self.runtime {
            paths.insert(runtime.directory.clone());
            paths.insert(runtime.directory.join("owner.lock"));
            paths.extend(runtime.files.borrow().values().map(|v| v.pin.path.clone()));
        }
        paths
    }

    pub(crate) fn pair_intent(&self) -> &FilePin {
        self.working.pair_intent()
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        ensure(
            self.pid == std::process::id(),
            "retirement authority crossed its actual process",
        )?;
        self.authority.verify_current_owner()?;
        self.sources.revalidate()?;
        self.working.revalidate()?;
        self.sealed.revalidate()?;
        self.observation.revalidate()?;
        self.grubenv.borrow().revalidate()?;
        if let Some(r) = &self.runtime {
            r.revalidate()?;
        }
        ensure(
            self.report["scope"] == self.kind.name()
                && self.report["original_boot_id"] == self.authority.owner.borrow().boot_id(),
            "retirement proof lost its actual original owner or scope",
        )?;
        Ok(())
    }
    pub(crate) fn verify_working_identity(&self, id: &Identity) -> Result<()> {
        self.revalidate()?;
        self.working.verify_working_identity(id)
    }
    pub(crate) fn verify_grubenv_identity(&self, id: &Identity) -> Result<()> {
        self.revalidate()?;
        ensure(
            self.grubenv.borrow().identity == *id,
            "GRUB evolution is not the actually read returned inode",
        )
    }
    pub(super) fn accept_label_restoration_custody(
        &self,
        restoration: &OriginalLabelRestoration,
    ) -> Result<()> {
        // The just-restored lock/backing's ctime necessarily differs from the
        // old expectation, so use the opaque per-inode proof before the full
        // fence. No unrelated metadata or timestamp is exempted.
        restoration.revalidate()?;
        ensure(
            restoration.candidate_id() == self.candidate_id(),
            "restoration belongs to another retired candidate",
        )?;
        self.authority
            .label_plan
            .borrow()
            .as_ref()
            .ok_or("held restore plan absent")?
            .verify_pin(restoration.source_plan())?;
        self.working.accept_label_restoration_custody(restoration)?;
        self.authority.owner.borrow_mut().accept_lock_label(
            restoration.path(),
            restoration.before_identity(),
            restoration.after_identity(),
        )?;
        self.grubenv.borrow_mut().accept_custody(restoration)?;
        if let Some(runtime) = &self.runtime {
            runtime.accept_custody(restoration)?;
        }
        self.revalidate_custody()
    }
    pub(crate) fn accept_label_restoration(
        &self,
        restoration: &OriginalLabelRestoration,
    ) -> Result<()> {
        self.authority
            .verify_label_plan(restoration.source_plan())?;
        self.accept_label_restoration_custody(restoration)?;
        self.revalidate()
    }
    pub(super) fn revalidate_custody(&self) -> Result<()> {
        ensure(
            self.pid == std::process::id(),
            "retirement custody crossed its original process",
        )?;
        super::window::verify_authority_custody(&self.authority)?;
        self.sources.revalidate_custody()?;
        self.working.revalidate_custody()?;
        self.sealed.revalidate_custody()?;
        self.observation.revalidate_custody()?;
        self.grubenv.borrow().revalidate_custody()?;
        if let Some(r) = &self.runtime {
            r.revalidate_custody()?;
        }
        ensure(
            self.report["scope"] == self.kind.name()
                && self.report["original_boot_id"] == self.authority.owner.borrow().boot_id(),
            "retirement original boot/scope changed",
        )
    }
    pub(super) fn verify_working_identity_custody(&self, id: &Identity) -> Result<()> {
        self.revalidate_custody()?;
        self.working.verify_working_identity_custody(id)
    }
    pub(super) fn verify_grubenv_identity_custody(&self, id: &Identity) -> Result<()> {
        self.revalidate_custody()?;
        ensure(
            self.grubenv.borrow().identity == *id,
            "returned GRUB inode differs from actual readback",
        )
    }
}

/// Called only by the owned dispatcher after actual selected.json withdrawal.
/// It performs the observation and data synchronization itself. There is no
/// `passed`, `returned`, mode, or externally supplied receipt parameter.
pub(super) fn prove(
    authority: Rc<OriginalQualificationAuthority>,
    data: &OriginalDataTransaction,
) -> Result<OriginalRetirement> {
    authority.verify_current_owner()?;
    let phase = authority
        .journal
        .borrow()
        .phase()
        .ok_or("retirement has no durable state")?;
    ensure(
        matches!(
            phase,
            Phase::SelectionWithdrawn | Phase::PairRestored | Phase::Aborting
        ),
        "selection must be actually withdrawn before retirement",
    )?;
    let intent: Value = serde_json::from_slice(&authority.intent.read()?)?;
    let original = field(&intent, "original_boot_id")?;
    let now = authority.owner.borrow().boot_id().to_owned();
    let armed = authority.journal.borrow().observation(Phase::Armed)?;
    let arm_intent = authority.journal.borrow().observation(Phase::ArmIntent)?;
    let initial_abort = now == original;
    let runtime = RuntimeEvidence::read(&authority)?;
    let observed = runtime
        .as_ref()
        .and_then(|r| r.json.get("CANDIDATE-OBSERVED.json"));
    let boot = if let Some(v) = observed {
        ensure(
            !initial_abort
                && v["schema"] == "droidloom.original-once-candidate-observed.v1"
                && v["candidate_id"] == authority.candidate_id()
                && v["intent_sha256"] == authority.intent.pin().sha256
                && v["original_boot_id"] == original,
            "candidate runtime belongs to a different original attempt",
        )?;
        let b = field(v, "boot_id")?;
        ensure(
            c::uuid(b) && b != original && b != now,
            "candidate and original boots were not independently observed",
        )?;
        Some(b.to_owned())
    } else {
        None
    };
    let invocation = authority.owner.borrow().evidence()["actual_original"]["invocation_id"]
        .as_str()
        .ok_or("actual owner invocation absent")?
        .to_owned();
    ensure(
        invocation.len() == 32 && invocation.bytes().all(|b| b.is_ascii_hexdigit()),
        "actual retirement owner invocation differs",
    )?;
    let work = authority
        .work()
        .join(format!("retirement-{now}-{invocation}"));
    files::private_dir(&work)?;
    let (actual, observation) = original_readback(&authority, &work, boot.as_deref())?;
    let kind = if initial_abort {
        Kind::UnbootedAbort
    } else if arm_intent.is_none() {
        ensure(
            observed.is_none() && armed.is_none(),
            "interrupted preparation cannot contain candidate/armed evidence",
        )?;
        Kind::PreparationInterrupted
    } else if let (Some(r), Some(b)) = (&runtime, &boot) {
        if armed.is_some() && normal_chain(r, &authority.intent.pin().sha256, b, &actual)? {
            Kind::NormalReturn
        } else {
            Kind::FailedReturn
        }
    } else {
        Kind::FailedReturn
    };
    let grubenv = Readback::open(Path::new("/boot/grub/grubenv"), 0o644, 1024)?;
    let reported: FilePin = serde_json::from_value(actual["grubenv"].clone())?;
    ensure(
        super::same_pin(&reported, &grubenv.pin),
        "actual returned GRUB environment changed after normal readback",
    )?;
    let sources = OriginalLabelRestoreSources::reopen(authority.materials.source_pin())?;
    let working = data.retire_working(&authority)?;
    ensure(
        working.candidate_id() == authority.candidate_id(),
        "synchronized data belongs to another candidate",
    )?;
    match &*authority.retirement.borrow() {
        RetirementSource::Prepared(pin) => ensure(
            super::same_pin(pin.pin(), working.pair_intent()),
            "data synchronization used another immutable pair intent",
        )?,
        RetirementSource::Initial => {
            return Err(
                "no pair was prepared; zero-effect early recovery must not invent a pair intent"
                    .into(),
            );
        }
    }
    let proof = json!({"schema":"droidloom.original-once-retirement.v1","scope":kind.name(),
        "candidate_id":authority.candidate_id(),"intent":authority.intent.pin(),"normal_sources":sources.source_pin(),
        "original_boot_id":now,"admitted_original_boot_id":original,"candidate_boot_id":boot,
        "original_kernel":c::ORIGINAL_KERNEL,"root_uuid":c::ROOT_UUID,"original_entry":c::ORIGINAL_ENTRY,
        "actual_original_return":!initial_abort,"normal_maintenance_and_pid1_shutdown_observed":kind==Kind::NormalReturn,
        "failed_return_preserved":kind==Kind::FailedReturn,"preparation_interrupted":kind==Kind::PreparationInterrupted,"unbooted_abort":initial_abort,"arm_was_observed":armed.is_some(),
        "actual_owner":authority.owner.borrow().evidence(),"original_observation":observation.pin(),
        "working_data":working.evidence(),"runtime_files":runtime.as_ref().map(|r|r.files.borrow().iter().map(|(name,f)|json!({"name":name,"pin":f.pin,"identity":f.identity})).collect::<Vec<_>>()),
        "grubenv":grubenv.pin,"grubenv_identity":grubenv.identity,"production_ready":false,"private_business_accepted":false});
    let sealed = save(&work.join("ORIGINAL-RETIREMENT.json"), &proof)?;
    let result = OriginalRetirement {
        authority,
        sources,
        working,
        kind,
        report: proof,
        sealed,
        observation,
        runtime,
        grubenv: RefCell::new(grubenv),
        pid: std::process::id(),
    };
    result.revalidate()?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn request_or_foreign_pid_cannot_prove_normal_retirement() {
        let boot = "11111111-1111-1111-1111-111111111111";
        assert!(!journal_retirement(
            &json!({"requested":true,"ordinary_shutdown_verified":true}),
            boot
        ));
        let mut rows=REQUIRED_STOPPED.iter().map(|unit|json!({"_BOOT_ID":boot.replace('-',""),"_PID":"1","_UID":"0","_EXE":"/usr/lib/systemd/systemd","UNIT":unit,"MESSAGE_ID":PID1_STOPPED,"JOB_RESULT":"done"})).collect::<Vec<_>>();
        rows.push(json!({"_BOOT_ID":boot.replace('-',""),"_PID":"1","_UID":"0","_EXE":"/usr/lib/systemd/systemd","UNIT":"reboot.target","MESSAGE_ID":PID1_STARTED,"JOB_RESULT":"done"}));
        rows.push(json!({"_BOOT_ID":boot.replace('-',""),"_PID":"1","_UID":"0","_EXE":"/usr/lib/systemd/systemd","MESSAGE":"Shutting down."}));
        let good = json!({"verify_exit":0,"exit":0,"rows":rows});
        assert!(journal_retirement(&good, boot));
        for (pointer, value) in [
            ("/rows/0/_PID", json!("22")),
            ("/rows/0/_BOOT_ID", json!("2".repeat(32))),
            ("/rows/0/JOB_RESULT", json!("timeout")),
            ("/verify_exit", json!(1)),
        ] {
            let mut bad = good.clone();
            *bad.pointer_mut(pointer).unwrap() = value;
            assert!(!journal_retirement(&bad, boot));
        }
    }
}
