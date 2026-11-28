//! Fresh original-kernel boot retirement observations for working qualification.
//! Normal read-only tools and retained actual records establish these facts.
//! A reboot request, a JSON receipt or an old live owner cannot establish return.
use super::{SealedInput, WorkingReturnOwner, returned_label_identity};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    cold_original_data::labels::{OriginalLabelRestoreSources, WorkingReturnedLabelRestoration},
    cold_original_qualification::{commands, materials::Guard},
    cold_working_recovery::contract::{self as c, WorkingReturnConfiguration},
    ensure, fs,
    model::Identity,
};
use rustix::fs::{FileType, FlockOperation, Mode};
use serde_json::{Value, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    fs::File,
    io::Seek,
    os::fd::AsRawFd,
    path::{Path, PathBuf},
    rc::Rc,
};

const BASE: &str = "/var/lib/droidloom-qualification";
const PYTHON_BYTES: u64 = 7_477_160;
const PYTHON_SHA: &str = "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41";
const REQUEST: &str = "droidloom.working-return-read-command.v1";
const RESPONSE: &str = "droidloom.working-return-read-command-result.v1";
const PARENT_NAMES: [&str; 6] = [
    "OWNER-START.json",
    "OWNER-FAILURE.json",
    "PREPARATION-OWNER-RESULT.json",
    "PREPARATION.stdout",
    "PREPARATION.stderr",
    "PHYSICAL-OWNER-RESULT.json",
];
const RETURN_NAMES: [&str; 5] = [
    "WORKING-RETURN-OBSERVED.json",
    "WORKING-COLLECTION-OBSERVED.json",
    "WORKING-COLLECTION-SKIPPED.json",
    "WORKING-RETURN-SELECTED.json",
    "WORKING-RETURN-REQUESTED.json",
];

/// Comparison inputs only. The factory still requires a fresh actual owner,
/// held source records, original-kernel observations and source-bound commands.
pub(crate) struct WorkingReturnExpectation {
    pub(crate) boot_intent: FilePin,
    pub(crate) normal_sources: FilePin,
    pub(crate) return_config: FilePin,
    pub(crate) original_boot_id: String,
}
fn same_pin(a: &FilePin, b: &FilePin) -> bool {
    a.path == b.path && a.bytes == b.bytes && a.sha256 == b.sha256
}
fn str_field<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    v[key]
        .as_str()
        .ok_or_else(|| format!("working return lacks bounded field {key}").into())
}
fn attrs(file: &File) -> Result<BTreeMap<String, String>> {
    let value = fs::xattrs(file)?;
    ensure(
        value.keys().all(|name| name == "security.selinux"),
        "working return record has an unrelated extended attribute",
    )?;
    Ok(value)
}
struct Readback {
    pin: FilePin,
    held: File,
    identity: Identity,
    attributes: BTreeMap<String, String>,
}
impl Readback {
    fn open(path: &Path, modes: &[u32], maximum: u64) -> Result<Self> {
        let held = fs::Tree::open("/", 0)?.file(&fs::absolute_string(path)?)?;
        let identity = fs::stat(&held)?;
        ensure(
            FileType::from_raw_mode(identity.mode) == FileType::RegularFile
                && identity.uid == 0
                && identity.gid == 0
                && identity.nlink == 1
                && modes.contains(&(identity.mode & 0o7777))
                && identity.size <= maximum,
            "working return record is outside its exact protected file bound",
        )?;
        let attributes = attrs(&held)?;
        let pin = FilePin {
            path: path.into(),
            bytes: identity.size,
            sha256: fs::hash(&held)?,
        };
        let value = Self {
            pin,
            held,
            identity,
            attributes,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        let named = fs::Tree::open("/", 0)?.file(&fs::absolute_string(&self.pin.path)?)?;
        ensure(
            fs::stat(&self.held)? == self.identity
                && fs::stat(&named)? == self.identity
                && attrs(&self.held)? == self.attributes
                && attrs(&named)? == self.attributes,
            "working return held/named inode or attributes changed",
        )?;
        (&self.held).rewind()?;
        ensure(
            fs::hash(&self.held)? == self.pin.sha256
                && fs::stat(&self.held)? == self.identity
                && fs::stat(&named)? == self.identity,
            "working return complete held bytes changed",
        )?;
        Ok(())
    }
    fn accept_label_restoration(&mut self, proof: &WorkingReturnedLabelRestoration) -> Result<()> {
        if !proof.paths().iter().any(|path| path == &self.pin.path) {
            return self.revalidate();
        }
        let after = proof.require_held_transition(&self.pin.path, &self.held, &self.identity)?;
        returned_label_identity(&self.identity, &after)?;
        let named = fs::Tree::open("/", 0)?.file(&fs::absolute_string(&self.pin.path)?)?;
        let attributes = attrs(&self.held)?;
        (&self.held).rewind()?;
        ensure(
            fs::stat(&self.held)? == after
                && fs::stat(&named)? == after
                && attrs(&named)? == attributes
                && fs::hash(&self.held)? == self.pin.sha256
                && fs::stat(&self.held)? == after
                && fs::stat(&named)? == after,
            "returned label adoption changed held retirement bytes or named inode",
        )?;
        proof.revalidate()?;
        self.identity = after;
        self.attributes = attributes;
        self.revalidate()
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
}
struct RuntimeEvidence {
    path: PathBuf,
    directory: File,
    identity: Identity,
    attributes: BTreeMap<String, String>,
    members: BTreeSet<String>,
    records: BTreeMap<String, Readback>,
    json: BTreeMap<String, Value>,
    incomplete: BTreeSet<String>,
}
impl RuntimeEvidence {
    fn allowed() -> BTreeSet<String> {
        let mut names = PARENT_NAMES
            .into_iter()
            .chain(RETURN_NAMES)
            .map(str::to_owned)
            .collect::<BTreeSet<_>>();
        names.insert("owner.lock".into());
        for verb in ["collect", "rollback", "reboot"] {
            for suffix in [
                ".stdout",
                ".stderr",
                "-INTENT.json",
                "-RESULT.json",
                "-TIMEOUT.json",
            ] {
                names.insert(format!("{verb}{suffix}"));
            }
        }
        names
    }
    fn capture(config: &WorkingReturnConfiguration) -> Result<Option<Self>> {
        let path = config.runtime_evidence_directory();
        let tree = match fs::Tree::open(&fs::absolute_string(&path)?, 0) {
            Ok(v) => v,
            Err(e) if e.downcast_ref::<rustix::io::Errno>() == Some(&rustix::io::Errno::NOENT) => {
                return Ok(None);
            }
            Err(e) => return Err(e),
        };
        let identity = fs::stat(&tree.root)?;
        ensure(
            identity.uid == 0 && identity.gid == 0 && identity.mode & 0o7777 == 0o700,
            "working evidence root is not the normal protected directory",
        )?;
        let attributes = attrs(&tree.root)?;
        let allowed = Self::allowed();
        let mut members = BTreeSet::new();
        let mut records = BTreeMap::new();
        let mut json = BTreeMap::new();
        let mut incomplete = BTreeSet::new();
        let mut total = 0u64;
        for entry in std::fs::read_dir(&path)? {
            let name = entry?
                .file_name()
                .into_string()
                .map_err(|_| "non-UTF8 working evidence name")?;
            ensure(
                members.len() < 32 && allowed.contains(&name) && members.insert(name.clone()),
                "working return evidence contains an unknown or duplicate direct member",
            )?;
            let record = Readback::open(&path.join(&name), &[0o400, 0o600], 64 * 1024 * 1024)?;
            total = total
                .checked_add(record.pin.bytes)
                .ok_or("working evidence size overflow")?;
            ensure(
                total <= 128 * 1024 * 1024,
                "bounded working return evidence aggregate exceeded",
            )?;
            if name == "owner.lock" {
                ensure(
                    record.identity.mode & 0o7777 == 0o400 && record.pin.bytes == 0,
                    "working return owner lock is not its fixed prepared inode",
                )?;
                rustix::fs::flock(&record.held, FlockOperation::NonBlockingLockExclusive)?;
            } else if name.ends_with(".json") {
                match serde_json::from_slice::<Value>(&record.bytes()?) {
                    Ok(value) => {
                        json.insert(name.clone(), value);
                    }
                    Err(_) if record.identity.mode & 0o7777 == 0o600 => {
                        incomplete.insert(name.clone());
                    }
                    Err(e) => return Err(e.into()),
                }
            }
            records.insert(name, record);
        }
        // An absent owner.lock can occur before candidate publication completed;
        // it is a failed/preboot observation, never normal return authority.
        let value = Self {
            path,
            directory: tree.root,
            identity,
            attributes,
            members,
            records,
            json,
            incomplete,
        };
        value.revalidate()?;
        Ok(Some(value))
    }
    fn revalidate(&self) -> Result<()> {
        let named = fs::Tree::open(&fs::absolute_string(&self.path)?, 0)?.root;
        ensure(
            fs::stat(&self.directory)? == self.identity
                && fs::stat(&named)? == self.identity
                && attrs(&self.directory)? == self.attributes
                && attrs(&named)? == self.attributes,
            "retired working evidence directory changed after complete capture",
        )?;
        let names = std::fs::read_dir(&self.path)?
            .map(|e| -> Result<String> {
                Ok(e?
                    .file_name()
                    .into_string()
                    .map_err(|_| "non-UTF8 retained runtime member")?)
            })
            .collect::<Result<BTreeSet<_>>>()?;
        ensure(
            names == self.members,
            "retired working evidence member inventory changed",
        )?;
        for (name, record) in &self.records {
            record.revalidate()?;
            if name == "owner.lock" {
                rustix::fs::flock(&record.held, FlockOperation::NonBlockingLockExclusive)?;
            }
        }
        ensure(
            fs::stat(&self.directory)? == self.identity
                && fs::stat(&named)? == self.identity
                && attrs(&self.directory)? == self.attributes
                && attrs(&named)? == self.attributes,
            "working evidence changed during readback",
        )?;
        Ok(())
    }
    fn accept_label_restoration(&mut self, proof: &WorkingReturnedLabelRestoration) -> Result<()> {
        // The returned writer handles these held objects one at a time. A
        // directory xattr never changes its names or any child's checkpoint.
        if proof.paths().iter().any(|path| path == &self.path) {
            let after =
                proof.require_held_transition(&self.path, &self.directory, &self.identity)?;
            returned_label_identity(&self.identity, &after)?;
            let named = fs::Tree::open(&fs::absolute_string(&self.path)?, 0)?.root;
            let attributes = attrs(&self.directory)?;
            ensure(
                fs::stat(&self.directory)? == after
                    && fs::stat(&named)? == after
                    && attrs(&named)? == attributes,
                "returned evidence directory lost its held/named exact restoration",
            )?;
            proof.revalidate()?;
            self.identity = after;
            self.attributes = attributes;
        }
        for record in self.records.values_mut() {
            record.accept_label_restoration(proof)?;
        }
        self.revalidate()
    }

    fn observed_boot(&self, config: &WorkingReturnConfiguration) -> Result<Option<String>> {
        let mut boots = BTreeSet::new();
        if let Some(owner) = self.json.get("OWNER-START.json") {
            ensure(
                owner["schema"] == "droidloom.live-working-qualification-owner.v1"
                    && owner["boot"]["schema"] == "droidloom.working-boot-source-custody.v1"
                    && owner["boot"]["candidate_id"] == config.candidate_id
                    && owner["boot"]["first_once_candidate"] == config.first_once_candidate
                    && owner["boot"]["host_source_commit"] == config.host_source_commit
                    && owner["boot"]["host_source_tree"] == config.host_source_tree
                    && owner["boot"]["admitted_materials_sha256"]
                        == config.admitted_materials_sha256
                    && owner["boot"]["joint_policy_sha256"] == config.joint_policy_sha256
                    && owner["boot"]["applications"] == serde_json::to_value(&config.applications)?
                    && owner["boot"]["selection"] == serde_json::to_value(&config.selection)?
                    && owner["boot"]["cell"] == serde_json::to_value(&config.cell)?,
                "working owner record belongs to another actual selected source",
            )?;
            boots.insert(str_field(&owner["boot"], "actual_boot_id")?.to_owned());
        }
        for (name, value) in &self.json {
            if PARENT_NAMES.contains(&name.as_str()) {
                continue;
            }
            if let Some(boot) = value.get("boot_id") {
                boots.insert(
                    boot.as_str()
                        .ok_or("runtime boot identity is not a string")?
                        .to_owned(),
                );
            }
            if let Some(intent) = value.get("intent_sha256") {
                ensure(
                    intent == &Value::String(config.intent_sha256.clone()),
                    "runtime maintenance record belongs to another boot intent",
                )?;
            }
        }
        if let Some(v) = self.json.get("WORKING-RETURN-OBSERVED.json") {
            ensure(
                v["schema"] == "droidloom.working-qualification-return-observed.v1"
                    && v["candidate_id"] == config.candidate_id
                    && v["first_once_candidate"] == config.first_once_candidate
                    && v["original_boot_id"] == config.original_boot_id
                    && v["actual_parent_tree_empty"] == true,
                "working return observation did not retire this exact parent tree",
            )?;
        }
        ensure(
            boots.len() <= 1
                && boots
                    .iter()
                    .all(|v| super::uuid(v) && v != &config.original_boot_id),
            "working runtime records have ambiguous or original-host boot identities",
        )?;
        Ok(boots.into_iter().next())
    }
    fn command(
        &self,
        verb: &str,
        config: &WorkingReturnConfiguration,
        boot: &str,
    ) -> Result<Option<Value>> {
        let name = format!("{verb}-RESULT.json");
        let Some(result) = self.json.get(&name) else {
            return Ok(None);
        };
        let Some(start) = self.json.get(&format!("{verb}-INTENT.json")) else {
            return Ok(None);
        };
        for value in [start, result] {
            ensure(
                value["schema"] == "droidloom.working-qualification-maintenance-command.v1"
                    && value["intent_sha256"] == config.intent_sha256
                    && value["boot_id"] == boot
                    && value["verb"] == verb,
                "normal working maintenance comparison identity differs",
            )?;
        }
        if result["completed"] != true
            || result["exit_code"] != 0
            || self.records.contains_key(&format!("{verb}-TIMEOUT.json"))
        {
            return Ok(None);
        }
        for name in [format!("{verb}-RESULT.json"), format!("{verb}-INTENT.json")] {
            if self.records[&name].identity.mode & 0o7777 != 0o400 {
                return Ok(None);
            }
        }
        for suffix in ["stdout", "stderr"] {
            let name = format!("{verb}.{suffix}");
            let Some(file) = self.records.get(&name) else {
                return Ok(None);
            };
            ensure(
                file.pin.bytes
                    == result[suffix]["bytes"]
                        .as_u64()
                        .ok_or("normal output size absent")?
                    && Value::String(file.pin.sha256.clone()) == result[suffix]["sha256"],
                "normal maintenance output differs from its full source-produced commitment",
            )?;
            if file.identity.mode & 0o7777 != 0o400 {
                return Ok(None);
            }
        }
        Ok(Some(self.records[&format!("{verb}.stdout")].json()?))
    }
    fn summary(&self) -> Value {
        json!({"directory":self.path,"identity":self.identity,
            "files":self.records.iter().map(|(name,r)|(name.clone(),
                json!({"pin":r.pin,"identity":r.identity,"attributes":r.attributes}))).collect::<BTreeMap<_,_>>(),
            "incomplete_json_records":self.incomplete,
            "parent_fixed_file_roster":PARENT_NAMES,"account_business_accepted":false})
    }
}
#[derive(Clone, Copy)]
enum ReadOperation {
    Grub,
    Units,
    Journal,
}
impl ReadOperation {
    fn name(self) -> &'static str {
        match self {
            Self::Grub => "grub-read",
            Self::Units => "owner-units-read",
            Self::Journal => "retirement-journal",
        }
    }
    fn seconds(self) -> u64 {
        match self {
            Self::Journal => 150,
            _ => 90,
        }
    }
}
fn normal_driver() -> Result<String> {
    // Preserve the maintained source-bound interpreter/tool admission and only
    // its read-only primitive prefix. None of the package/mutation dispatch
    // or unrestricted systemctl adapter is included.
    let (prefix, _) = commands::historical_driver_source()
        .split_once("\ndef preservation(")
        .ok_or("normal read-only tool prefix changed")?;
    let (_, ending) = commands::historical_driver_source()
        .split_once("check_tool_sources(full=True)\n")
        .ok_or("normal read-only tool final fence changed")?;
    let readonly = r#"if op=='grub-read':
 need(set(arg)=={'original_cfg_sha256'},'fixed read-only GRUB argument set')
 with held('/boot/grub/grub.cfg',root=True,maximum=16*1024*1024) as (fd,st):
  body=os.pread(fd,st.st_size+1,0)
  need(len(body)==st.st_size and f9(os.fstat(fd))==f9(st),'complete held original GRUB bytes')
  original=verify_original_grub_entry(body,ORIGINAL_ROOT_UUID,original_grub_entry(ORIGINAL_ROOT_UUID),ORIGINAL_KERNEL)
  need(hashlib.sha256(body).hexdigest()==arg['original_cfg_sha256'],'original GRUB source changed')
 with held('/boot/grub/grubenv',root=True,modes={0o644},maximum=1024) as (fd,st):
  need(st.st_size==1024 and st.st_nlink==1,'normal GRUB environment identity')
  before=os.pread(fd,1025,0);attrs=source_attrs(fd)
  observed=normal_tool('grub-editenv',[f'/proc/self/fd/{fd}','list'],maximum=65536,borrowed=(fd,))
  need(observed['exit']==0,'normal read-only GRUB list failed')
  fields={}
  for line in observed['stdout'].decode('utf-8','strict').splitlines():
   name,value=line.split('=',1);need(name not in fields,'duplicate actual GRUB field');fields[name]=value
  after=os.pread(fd,1025,0);now=os.fstat(fd);named=os.stat('/boot/grub/grubenv',follow_symlinks=False)
  need(len(before)==1024 and before==after and f9(st)==f9(now)==f9(named) and attrs==source_attrs(fd),'read-only GRUB inode or contents changed')
  need(fields.get('next_entry','')=='','actual original return has a one-shot selection still armed')
  result={'original':original,'identity':f9(now),'body_hex':after.hex(),'sha256':hashlib.sha256(after).hexdigest(),'fields':fields,'readback':observed,'mutation_performed':False,'default_changed':False}
elif op=='owner-units-read':
 need(arg=={},'fixed original owner unit read')
 units=list(COLD_OWNER_UNITS)+['droidloom-early-observer.service','droidloom-working-qualification.service','droidloom-working-qualification-return.service']
 rows=[]
 for name in units:
  props=['Id','LoadState','ActiveState','SubState','FragmentPath','DropInPaths','Transient']
  if not name.endswith('.target'):props+=['MainPID','ControlGroup']
  actual=normal_tool('systemctl',['show',name,'--no-pager','--property='+','.join(props)],seconds=10,maximum=65536)
  values={}
  for line in actual['stdout'].decode('utf-8','strict').splitlines():
   key,value=line.split('=',1);need(key not in values,'duplicate PID1 unit property');values[key]=value
  need(set(values)==set(props),'complete fixed actual unit property roster')
  ids={name,'gdm3.service'} if name=='gdm.service' else {name}
  need(values['Id'] in ids and values['ActiveState'] in ('inactive','failed') and values.get('MainPID','0')=='0','actual graphical/Android owner remains live')
  need(actual['exit']==0 or values['LoadState']=='not-found' and values['ActiveState']=='inactive','normal PID1 inactive observation failed')
  rows.append({'requested_unit':name,'actual':values,'normal_command':actual})
 result={'units':rows,'all_fixed_graphical_android_owners_inactive':True}
elif op=='retirement-journal':
 boot=arg['boot'];need(set(arg)=={'boot'} and isinstance(boot,str) and re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',boot),'exact actual candidate boot')
 fields='_BOOT_ID,_PID,_UID,_EXE,_COMM,_SYSTEMD_UNIT,_SYSTEMD_USER_UNIT,_SYSTEMD_INVOCATION_ID,__MONOTONIC_TIMESTAMP,__REALTIME_TIMESTAMP,MESSAGE_ID,MESSAGE,UNIT,USER_UNIT,UNIT_RESULT,JOB_RESULT,INVOCATION_ID'
 verified=normal_tool('journalctl',['--directory=/var/log/journal','--verify'],seconds=60)
 rows=normal_tool('journalctl',['--directory=/var/log/journal','--boot='+boot,'--no-pager','--all','--output=json','--output-fields='+fields,'_PID=1','+','_SYSTEMD_UNIT=systemd-journald.service'],seconds=60,maximum=16*1024*1024)
 result={'verify_exit':verified['exit'],'verify_stdout':verified['stdout'].decode('utf-8','strict'),'verify_stderr':verified['stderr'].decode('utf-8','strict'),'exit':rows['exit'],'stderr':rows['stderr'].decode('utf-8','strict'),'rows':[json.loads(line) for line in rows['stdout'].splitlines()],'normal_journalctl_package_kind':rows['normal_package_kind']}
else:raise RuntimeError('unsupported source-owned read-only working return operation')
check_tool_sources(full=True)
"#;
    Ok(format!("{prefix}\n{readonly}{ending}")
        .replace("droidloom.original-once-fixed-command.v1", REQUEST)
        .replace("droidloom.original-once-fixed-command-result.v1", RESPONSE))
}
fn save(path: &Path, value: &Value) -> Result<SealedInput> {
    let mut bytes = serde_json::to_vec(value)?;
    bytes.push(b'\n');
    ensure(
        bytes.len() <= 32 * 1024 * 1024,
        "working return report bound exceeded",
    )?;
    files::write_new(path, &bytes, 0o400)?;
    File::open(path.parent().ok_or("working return report parent absent")?)?.sync_all()?;
    SealedInput::open(&files::pin_file(path)?)
}
fn attempt_directory(owner: &WorkingReturnOwner, work: &Path) -> Result<PathBuf> {
    let root = fs::Tree::open(&fs::absolute_string(work)?, 0)?.root;
    let id = fs::stat(&root)?;
    ensure(
        id.mode & 0o7777 == 0o700 && id.uid == 0 && id.gid == 0,
        "working return observation work root differs",
    )?;
    for n in 1..=8 {
        let name = format!("working-return-observation-{}-{n:02}", owner.boot_id());
        match rustix::fs::mkdirat(&root, name.as_str(), Mode::from_raw_mode(0o700)) {
            Ok(()) => {
                root.sync_all()?;
                return Ok(work.join(name));
            }
            Err(rustix::io::Errno::EXIST) => continue,
            Err(e) => return Err(e.into()),
        }
    }
    Err("finite fresh read-only working return observations exhausted".into())
}
struct NormalReadbacks {
    modules: Vec<Guard>,
    sources: PathBuf,
    python: Readback,
    driver: String,
    records: Vec<SealedInput>,
    outputs: Vec<Readback>,
    work: PathBuf,
}
impl NormalReadbacks {
    fn prepare(work: &Path) -> Result<Self> {
        let sources = work.join("normal-source");
        files::private_dir(&sources)?;
        let mut modules = Vec::new();
        for (name, bytes) in crate::boot_host::cold_modules::FILES {
            let path = sources.join(
                Path::new(name)
                    .file_name()
                    .ok_or("normal module basename absent")?,
            );
            files::write_new(&path, bytes, 0o400)?;
            modules.push(Guard::open(&FilePin {
                path,
                bytes: bytes.len() as u64,
                sha256: fs::digest(bytes),
            })?);
        }
        File::open(&sources)?.sync_all()?;
        let python = Readback::open(Path::new("/usr/bin/python3.14"), &[0o755], 16 * 1024 * 1024)?;
        ensure(
            python.pin.bytes == PYTHON_BYTES && python.pin.sha256 == PYTHON_SHA,
            "normal read-only interpreter is not its actual source-bound member",
        )?;
        Ok(Self {
            modules,
            sources,
            python,
            driver: normal_driver()?,
            records: Vec::new(),
            outputs: Vec::new(),
            work: work.into(),
        })
    }
    fn revalidate(&self) -> Result<()> {
        for module in &self.modules {
            module.revalidate()?;
        }
        self.python.revalidate()?;
        for record in &self.records {
            record.revalidate()?;
        }
        for output in &self.outputs {
            output.revalidate()?;
        }
        Ok(())
    }
    fn accept_label_restoration(&mut self, proof: &WorkingReturnedLabelRestoration) -> Result<()> {
        // All generated modules and command records live in the private
        // original work exclusion. Only the actual fixed interpreter can
        // participate in the original-host label restoration.
        for module in &self.modules {
            module.revalidate()?;
        }
        for record in &self.records {
            record.revalidate()?;
        }
        for output in &self.outputs {
            output.revalidate()?;
        }
        self.python.accept_label_restoration(proof)?;
        self.revalidate()
    }
    fn read(
        &mut self,
        owner: &WorkingReturnOwner,
        sources: &OriginalLabelRestoreSources,
        intent: &FilePin,
        operation: ReadOperation,
        arguments: Value,
    ) -> Result<Value> {
        owner.revalidate()?;
        sources.revalidate()?;
        self.revalidate()?;
        let path = self.work.join(operation.name());
        files::private_dir(&path)?;
        let materials = sources.historical_initramfs_readback()["normal_materials"].clone();
        ensure(
            materials["deployment_id"] == owner.candidate(),
            "normal read-only source candidate differs",
        )?;
        let input = save(
            &path.join("INPUTS.json"),
            &json!({"schema":REQUEST,
            "candidate_id":owner.candidate(),"intent":intent,"operation":operation.name(),
            "arguments":arguments,"materials":materials}),
        )?;
        let result = files::run_logged(
            &path,
            "normal-read",
            &format!(
                "/proc/{}/fd/{}",
                std::process::id(),
                self.python.held.as_raw_fd()
            ),
            &[
                "-I".into(),
                "-B".into(),
                "-c".into(),
                self.driver.clone(),
                fs::absolute_string(&self.sources)?,
                fs::absolute_string(&input.pin().path)?,
            ],
            operation.seconds(),
        )?;
        ensure(
            result.exit_code == Some(0) && !result.timed_out,
            "actual normal read-only working return command failed",
        )?;
        let output = Readback::open(&result.log.path, &[0o400, 0o600], 32 * 1024 * 1024)?;
        ensure(
            same_pin(&output.pin, &result.log),
            "normal command log commitment changed",
        )?;
        let actual = output.json()?;
        ensure(
            actual["schema"] == RESPONSE
                && actual["operation"] == operation.name()
                && actual["candidate_id"] == owner.candidate()
                && actual["intent"] == serde_json::to_value(intent)?
                && actual["original"]["boot_id"] == owner.boot_id()
                && actual["original"]["kernel"] == c::ORIGINAL_KERNEL,
            "normal read-only result changed the actual owner, source or original boot",
        )?;
        let record = save(
            &path.join("RESULT.json"),
            &json!({"schema":"droidloom.working-return-normal-read.v1",
            "input":input.pin(),"driver_sha256":fs::digest(self.driver.as_bytes()),
            "actual":actual,"command":result}),
        )?;
        self.records.extend([input, record]);
        self.outputs.push(output);
        self.revalidate()?;
        sources.revalidate()?;
        owner.revalidate()?;
        Ok(actual["result"].clone())
    }
}
fn journal_retired(journal: &Value, boot: &str) -> bool {
    if journal["verify_exit"] != 0 || journal["exit"] != 0 {
        return false;
    }
    let Some(rows) = journal["rows"].as_array() else {
        return false;
    };
    let required = BTreeSet::from([
        "droidloom-production.service",
        "droidloom-instance-launcher.service",
        "droidloom-instance-factory.service",
        "droidloom-early-observer.service",
        "user@1000.service",
    ]);
    let mut stopped = BTreeSet::new();
    let mut reboot = false;
    let mut shutdown = false;
    let mut bad = false;
    for row in rows {
        if row["_BOOT_ID"] != boot.replace('-', "") {
            return false;
        }
        if row["_PID"] != "1" || row["_UID"] != "0" || row["_EXE"] != "/usr/lib/systemd/systemd" {
            continue;
        }
        let unit = row["UNIT"].as_str().unwrap_or("");
        if required.contains(unit)
            && row["MESSAGE_ID"] == "9d1aaa27d60140bd96365438aad20286"
            && row["JOB_RESULT"] == "done"
        {
            stopped.insert(unit);
        }
        if (required.contains(unit) || unit == "systemd-reboot.service" || unit == "reboot.target")
            && (row.get("UNIT_RESULT").is_some_and(|v| v != "success")
                || row.get("JOB_RESULT").is_some_and(|v| v != "done"))
        {
            bad = true;
        }
        if unit == "reboot.target"
            && row["MESSAGE_ID"] == "39f53479d3a045ac8e11786248231fbf"
            && row["JOB_RESULT"] == "done"
        {
            reboot = true;
        }
        if row["MESSAGE"] == "Shutting down." {
            shutdown = true;
        }
    }
    !bad && reboot && shutdown && stopped == required
}
fn normal_chain(
    evidence: &RuntimeEvidence,
    config: &WorkingReturnConfiguration,
    boot: &str,
    journal: &Value,
) -> Result<bool> {
    if !evidence.records.contains_key("owner.lock") || !evidence.incomplete.is_empty() {
        return Ok(false);
    }
    let (Some(collect), Some(rollback), Some(reboot)) = (
        evidence.command("collect", config, boot)?,
        evidence.command("rollback", config, boot)?,
        evidence.command("reboot", config, boot)?,
    ) else {
        return Ok(false);
    };
    let status = |v: &Value| {
        v["boot_id"] == boot
            && v["kernel"] == c::KERNEL
            && v["selinux_enforcing"] == true
            && v["selinux_context"] == "u:system_r:p4_linux_maintenance_t:s0"
            && v["system_units"]["exit"] == 0
            && v["user_units"]["exit"] == 0
            && v["system_units"]["observation_failed"] != true
            && v["user_units"]["observation_failed"] != true
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
            "WORKING-RETURN-OBSERVED.json",
            "droidloom.working-qualification-return-observed.v1",
        ),
        (
            "WORKING-RETURN-SELECTED.json",
            "droidloom.working-qualification-return-selected.v1",
        ),
        (
            "WORKING-RETURN-REQUESTED.json",
            "droidloom.working-qualification-return-requested.v1",
        ),
    ] {
        let Some(value) = evidence.json.get(name) else {
            return Ok(false);
        };
        ensure(
            value["schema"] == schema
                && value["intent_sha256"] == config.intent_sha256
                && value["boot_id"] == boot,
            "working normal return record is from another actual source boot",
        )?;
        if evidence.records[name].identity.mode & 0o7777 != 0o400 {
            return Ok(false);
        }
    }
    Ok(journal_retired(journal, boot))
}
/// Actual boot facts only. Four backing locks, reference scans and original
/// whole-data comparisons belong to the separate fresh data factory.
pub(crate) struct WorkingBootRetirement {
    owner: Rc<WorkingReturnOwner>,
    sources: OriginalLabelRestoreSources,
    inputs: Vec<SealedInput>,
    runtime: RefCell<Option<RuntimeEvidence>>,
    normal: RefCell<NormalReadbacks>,
    grub: RefCell<Readback>,
    grub_configuration: RefCell<Readback>,
    candidate_boot: Option<String>,
    normal_return: bool,
    report: SealedInput,
    value: Value,
}
impl WorkingBootRetirement {
    pub(crate) fn observe(
        owner: Rc<WorkingReturnOwner>,
        expected: &WorkingReturnExpectation,
    ) -> Result<Self> {
        owner.revalidate()?;
        let work = Path::new(BASE).join(format!("working-qualification-{}", owner.candidate()));
        ensure(
            expected.boot_intent.path == work.join("BOOT-INTENT.json")
                && expected.return_config.path == work.join("WORKING-RETURN.json")
                && super::uuid(&expected.original_boot_id),
            "working return comparison paths or original boot differ",
        )?;
        let intent = SealedInput::open(&expected.boot_intent)?;
        let config = SealedInput::open(&expected.return_config)?;
        let boot: Value = serde_json::from_slice(&intent.read()?)?;
        let config_value: WorkingReturnConfiguration = serde_json::from_slice(&config.read()?)?;
        config_value.validate()?;
        ensure(
            boot["schema"] == "droidloom.working-qualification-boot-intent.v1"
                && boot["kind"] == c::KIND
                && boot["candidate_id"] == owner.candidate()
                && boot["original_boot_id"] == expected.original_boot_id
                && boot["normal_sources"] == serde_json::to_value(&expected.normal_sources)?
                && boot["normal_producer"] == serde_json::to_value(owner.program_pin())?
                && config_value.candidate_id == owner.candidate()
                && config_value.intent_sha256 == expected.boot_intent.sha256
                && config_value.original_boot_id == expected.original_boot_id
                && Value::String(config_value.first_once_candidate.clone())
                    == boot["first_once_candidate"]
                && Value::String(config_value.host_source_commit.clone())
                    == boot["host_source_commit"]
                && Value::String(config_value.host_source_tree.clone()) == boot["host_source_tree"],
            "fresh boot retirement comparisons are outside this actual owned source",
        )?;
        let material_pin: FilePin = serde_json::from_value(boot["material_intent"].clone())?;
        ensure(
            material_pin.path == work.join("MATERIALS-INTENT.json"),
            "working boot material intent left the fixed original work",
        )?;
        let material = SealedInput::open(&material_pin)?;
        let material_value: Value = serde_json::from_slice(&material.read()?)?;
        let caller = SealedInput::open(owner.input_pin())?;
        let caller_value: Value = serde_json::from_slice(&caller.read()?)?;
        ensure(
            material_value["schema"] == "droidloom.working-qualification-material-intent.v1"
                && material_value["candidate_id"] == owner.candidate()
                && material_value["normal_sources"] == boot["normal_sources"]
                && material_value["normal_producer"] == boot["normal_producer"]
                && caller_value["candidate_id"] == owner.candidate()
                && caller_value["normal_producer"] == boot["normal_producer"]
                && caller_value["first_once_candidate"] == boot["first_once_candidate"],
            "fresh recovery's actual input differs from the retained normal source chain",
        )?;
        let sources = OriginalLabelRestoreSources::reopen(&expected.normal_sources)?;
        let source_value: Value =
            serde_json::from_slice(&files::read_pin(sources.source_pin(), 16 * 1024 * 1024)?)?;
        ensure(
            source_value["host_source_commit"] == boot["host_source_commit"]
                && source_value["host_source_tree"] == boot["host_source_tree"],
            "working return normal source cohort differs",
        )?;
        let grub_input: FilePin = serde_json::from_value(boot["current_original_grub"].clone())?;
        let original_grub = SealedInput::open(&grub_input)?;
        let original: Value = serde_json::from_slice(&original_grub.read()?)?;
        let cfg = original["preserved"]
            .as_array()
            .ok_or("preserved original GRUB roster absent")?
            .iter()
            .filter(|r| r["source"]["path"] == "/boot/grub/grub.cfg")
            .collect::<Vec<_>>();
        ensure(
            cfg.len() == 1,
            "original GRUB preimage lacks its unique fixed configuration",
        )?;
        let cfg_pin: FilePin = serde_json::from_value(cfg[0]["source"].clone())?;
        let grub_configuration = Readback::open(
            &cfg_pin.path,
            &[0o400, 0o444, 0o600, 0o644],
            16 * 1024 * 1024,
        )?;
        ensure(
            same_pin(&grub_configuration.pin, &cfg_pin),
            "held actual GRUB configuration differs from its original source",
        )?;
        let runtime = RuntimeEvidence::capture(&config_value)?;
        let candidate_boot = runtime
            .as_ref()
            .map(|r| r.observed_boot(&config_value))
            .transpose()?
            .flatten();
        ensure(
            candidate_boot.as_ref().is_none_or(|v| v != owner.boot_id())
                && (owner.boot_id() != expected.original_boot_id || candidate_boot.is_none()),
            "a requested or same original boot cannot become the candidate's actual return",
        )?;
        let path = attempt_directory(&owner, &work)?;
        let mut normal = NormalReadbacks::prepare(&path)?;
        let units = normal.read(
            &owner,
            &sources,
            intent.pin(),
            ReadOperation::Units,
            json!({}),
        )?;
        let grub_observation = normal.read(
            &owner,
            &sources,
            intent.pin(),
            ReadOperation::Grub,
            json!({"original_cfg_sha256":cfg_pin.sha256}),
        )?;
        ensure(
            grub_observation["original"]["original_entry"] == c::ORIGINAL_ENTRY
                && grub_observation["original"]["original_default"] == c::ORIGINAL_ENTRY
                && grub_observation["mutation_performed"] == false
                && grub_observation["default_changed"] == false,
            "normal original return changed the persistent original boot target",
        )?;
        let grub = Readback::open(Path::new("/boot/grub/grubenv"), &[0o644], 1024)?;
        ensure(
            grub.pin.bytes == 1024
                && Value::String(grub.pin.sha256.clone()) == grub_observation["sha256"]
                && hex::encode(grub.bytes()?) == str_field(&grub_observation, "body_hex")?,
            "held actual GRUB bytes disagree with normal read-only source",
        )?;
        let journal = match candidate_boot.as_deref() {
            Some(boot) => normal.read(
                &owner,
                &sources,
                intent.pin(),
                ReadOperation::Journal,
                json!({"boot":boot}),
            )?,
            None => Value::Null,
        };
        let normal_return = match (&runtime, candidate_boot.as_deref()) {
            (Some(records), Some(boot)) => normal_chain(records, &config_value, boot, &journal)?,
            _ => false,
        };
        let kind = if owner.boot_id() == expected.original_boot_id {
            "same-boot-abort"
        } else if normal_return {
            "verified-normal-return"
        } else {
            "observed-original-after-failed-or-unproven-candidate"
        };
        let value = json!({"schema":"droidloom.working-boot-retirement.v1","kind":kind,
            "candidate_id":owner.candidate(),"intent":intent.pin(),"normal_sources":sources.source_pin(),
            "return_configuration":config.pin(),"actual_owner":owner.evidence(),
            "prepared_original_boot_id":expected.original_boot_id,"current_original_boot_id":owner.boot_id(),
            "candidate_boot_id":candidate_boot,"normal_return_observed":normal_return,
            "runtime_evidence":runtime.as_ref().map(RuntimeEvidence::summary),
            "actual_original_units":units,"actual_grub":grub_observation,"actual_candidate_journal":journal,
            "grubenv":grub.pin,"grubenv_identity":grub.identity,
            "backing_locks_owned":false,"backing_reference_scan_performed":false,
            "original_data_restored":false,"application_business_accepted":false,"production_ready":false});
        let report = save(&path.join("BOOT-RETIREMENT.json"), &value)?;
        let result = Self {
            owner,
            sources,
            inputs: vec![intent, config, material, caller, original_grub],
            runtime: RefCell::new(runtime),
            normal: RefCell::new(normal),
            grub: RefCell::new(grub),
            grub_configuration: RefCell::new(grub_configuration),
            candidate_boot,
            normal_return,
            report,
            value,
        };
        result.revalidate()?;
        Ok(result)
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.owner.revalidate()?;
        self.sources.revalidate()?;
        for input in &self.inputs {
            input.revalidate()?;
        }
        if let Some(runtime) = self.runtime.borrow().as_ref() {
            runtime.revalidate()?;
        }
        self.normal.borrow().revalidate()?;
        self.grub.borrow().revalidate()?;
        self.grub_configuration.borrow().revalidate()?;
        self.report.revalidate()?;
        self.owner.revalidate()
    }
    pub(crate) fn label_sensitive_paths(&self) -> BTreeSet<PathBuf> {
        let mut paths = BTreeSet::from([
            self.normal.borrow().python.pin.path.clone(),
            self.grub.borrow().pin.path.clone(),
            self.grub_configuration.borrow().pin.path.clone(),
        ]);
        if let Some(runtime) = self.runtime.borrow().as_ref() {
            paths.insert(runtime.path.clone());
            paths.extend(
                runtime
                    .records
                    .values()
                    .map(|record| record.pin.path.clone()),
            );
        }
        paths
    }
    pub(crate) fn accept_label_restoration_custody(
        &self,
        proof: &WorkingReturnedLabelRestoration,
    ) -> Result<()> {
        proof.require_owner(self.owner.as_ref())?;
        ensure(
            proof.candidate_id() == self.owner.candidate(),
            "returned retirement label belongs to another actual candidate",
        )?;
        // Owner adoption is deliberately first at the call site. This fence
        // then rejects another owner, stale global lock or changed PID1 while
        // allowing only the actual target's pending retirement checkpoint.
        self.owner.revalidate()?;
        self.sources.revalidate()?;
        for input in &self.inputs {
            input.revalidate()?;
        }
        self.report.revalidate()?;
        if let Some(runtime) = self.runtime.borrow_mut().as_mut() {
            runtime.accept_label_restoration(proof)?;
        }
        self.normal.borrow_mut().accept_label_restoration(proof)?;
        self.grub.borrow_mut().accept_label_restoration(proof)?;
        self.grub_configuration
            .borrow_mut()
            .accept_label_restoration(proof)?;
        proof.revalidate()?;
        self.revalidate()
    }
    pub(crate) fn require_owner(&self, owner: &Rc<WorkingReturnOwner>) -> Result<()> {
        ensure(
            Rc::ptr_eq(&self.owner, owner),
            "working boot retirement belongs to another fresh owner",
        )?;
        self.revalidate()
    }
    pub(crate) fn evidence(&self) -> &Value {
        &self.value
    }
    pub(crate) fn report_pin(&self) -> &FilePin {
        self.report.pin()
    }
    pub(crate) fn normal_sources(&self) -> &OriginalLabelRestoreSources {
        &self.sources
    }
    pub(crate) fn candidate_boot_id(&self) -> Option<&str> {
        self.candidate_boot.as_deref()
    }
    pub(crate) fn normal_return_observed(&self) -> bool {
        self.normal_return
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_return_read_driver_contains_no_mutation_dispatch_and_actual_python_parses() {
        use std::{
            io::Write,
            process::{Command, Stdio},
        };
        let source = normal_driver().unwrap();
        for forbidden in [
            "if op=='public-snapshot'",
            "elif op=='systemctl'",
            "grub-arm",
            "grub-disarm",
            "public-apply",
            "native-apply",
            "working-reboot",
        ] {
            assert!(!source.contains(forbidden), "{forbidden}");
        }
        assert!(source.contains(REQUEST) && source.contains(RESPONSE));
        assert!(source.contains("actual original return has a one-shot selection still armed"));
        let mut child = Command::new("/usr/bin/python3.14")
            .args([
                "-I",
                "-B",
                "-c",
                "import ast,sys; ast.parse(sys.stdin.read(), filename='working-return-read')",
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
            .write_all(source.as_bytes())
            .unwrap();
        let output = child.wait_with_output().unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    #[test]
    fn working_return_requested_reboot_or_foreign_journal_cannot_prove_shutdown() {
        let boot = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
        assert!(!journal_retired(
            &json!({"requested":true,"completed":false}),
            boot
        ));
        let row = |unit: &str, message: &str| {
            json!({"_BOOT_ID":boot.replace('-',""),
            "_PID":"1","_UID":"0","_EXE":"/usr/lib/systemd/systemd",
            "UNIT":unit,"MESSAGE_ID":message,"JOB_RESULT":"done"})
        };
        let mut rows = vec![];
        for unit in [
            "droidloom-production.service",
            "droidloom-instance-launcher.service",
            "droidloom-instance-factory.service",
            "droidloom-early-observer.service",
            "user@1000.service",
        ] {
            rows.push(row(unit, "9d1aaa27d60140bd96365438aad20286"));
        }
        rows.push(row("reboot.target", "39f53479d3a045ac8e11786248231fbf"));
        let mut shutdown = row("", "");
        shutdown["MESSAGE"] = json!("Shutting down.");
        rows.push(shutdown);
        let value = json!({"verify_exit":0,"exit":0,"rows":rows});
        assert!(journal_retired(&value, boot));
        let mut wrong = value.clone();
        wrong["rows"][0]["_PID"] = json!("42");
        assert!(!journal_retired(&wrong, boot));
        let mut wrong = value.clone();
        wrong["rows"][0]["_BOOT_ID"] = json!("b".repeat(32));
        assert!(!journal_retired(&wrong, boot));
        let mut wrong = value.clone();
        wrong["rows"][0]["JOB_RESULT"] = json!("failed");
        assert!(!journal_retired(&wrong, boot));
        let mut wrong = value.clone();
        wrong["verify_exit"] = json!(1);
        assert!(!journal_retired(&wrong, boot));
        let mut wrong = value;
        wrong["rows"].as_array_mut().unwrap().pop();
        assert!(!journal_retired(&wrong, boot));
    }
    #[test]
    fn working_return_records_include_actual_parent_and_normal_maintenance_outputs_only() {
        let allowed = RuntimeEvidence::allowed();
        for name in PARENT_NAMES.into_iter().chain(RETURN_NAMES) {
            assert!(allowed.contains(name));
        }
        for name in [
            "collect.stdout",
            "rollback-RESULT.json",
            "reboot-TIMEOUT.json",
            "owner.lock",
        ] {
            assert!(allowed.contains(name));
        }
        for name in [
            "../BOOT-INTENT.json",
            "arbitrary.json",
            "RETURN-REQUESTED.json",
            "private-data.img",
            "native-leaves",
        ] {
            assert!(!allowed.contains(name));
        }
        assert_eq!(allowed.len(), 27);
    }
}
