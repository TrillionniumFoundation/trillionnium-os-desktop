//! The fixed private preparation child of the installed working owner.
//! Wire values are comparisons. Actual Boot/parent/PID1, Main and held files
//! establish custody; a JSON document never restores a completed application.
use super::*;
use super::socket::{Packet, Socket};
use crate::control::{MainCustodyObservation, NativeApplicationInspector, DEFAULT_CONTROL_SOCKET};
use crate::working_qualification::{WorkingSourceOrigin, WorkingSourceWitness, WorkingSourceFilePin};
use serde_json::{Value, json};
use std::io::Write;
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};

pub(super) const PREPARATION_CASE: u8 = 254;
pub(super) const PREPARATION_SUMMARY_LIMIT: u64 = 64 * 1024;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct PreparationStart {
    pub schema: String,
    pub origin: WorkingSourceOrigin,
    pub publication: WorkingSourceFilePin,
    pub preparation_end_ns: u64,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct PreparationReady {
    pub schema: String,
    pub plan_bytes: u64,
    pub plan_sha256: String,
    pub summary_bytes: u64,
    pub summary_sha256: String,
    pub binding: RuntimeMainCustody,
}

/// Only the ordinary preparation producer can obtain this move-only held plan.
/// It is a source input, never Complete or application runtime acceptance.
pub struct PreparedWorkingPlan {
    plan: Plan,
    epoch: RuntimeEpoch,
}
impl PreparedWorkingPlan {
    pub fn observation(&self) -> Value {
        json!({"path":self.plan.path,"bytes":self.plan.pin[6],"sha256":self.plan.digest})
    }
}

/// Finite filenames owned by this normal preparation stage.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WorkingPreparationDocument {
    Main,
    Intent,
    Installation,
    RuntimeBindings,
    RuntimePlan,
    CaseInputs,
}
impl WorkingPreparationDocument {
    fn name(self) -> &'static str {
        match self {
            Self::Main => "MAIN.json",
            Self::Intent => "RUNTIME-INTENT.json",
            Self::Installation => "APK-INSTALLATION.json",
            Self::RuntimeBindings => "RUNTIME-BINDINGS.json",
            Self::RuntimePlan => "RUNTIME-PLAN.json",
            Self::CaseInputs => "CASE-INPUTS.json",
        }
    }
}
struct Document {
    path: PathBuf,
    file: File,
    pin: [u64; 9],
    digest: String,
}
impl Document {
    fn guard(&self) -> io::Result<()> {
        let named = OpenOptions::new().read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).open(&self.path)?;
        if f9(&named)? != self.pin || f9(&self.file)? != self.pin {
            return Err(error("working preparation document inode changed"));
        }
        let mut body = vec![0; self.pin[6] as usize];
        self.file.read_exact_at(&mut body, 0)?;
        if sha(&body) != self.digest || self.file.read_at(&mut [0], self.pin[6])? != 0
            || f9(&self.file)? != self.pin || f9(&named)? != self.pin {
            return Err(error("working preparation document body changed"));
        }
        Ok(())
    }
    fn reference(&self) -> Value {
        json!({"path":self.path,"bytes":self.pin[6],"sha256":self.digest})
    }
}
fn parent_directory(path: &Path) -> io::Result<File> {
    if !path.is_absolute() || path.canonicalize()? != path {
        return Err(error("working preparation directory is not canonical"));
    }
    for p in path.ancestors() {
        let m = fs::symlink_metadata(p)?;
        if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {
            return Err(error("working preparation requires protected root parents"));
        }
    }
    OpenOptions::new().read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_DIRECTORY | libc::O_CLOEXEC).open(path)
}
fn new_document(root: &Path, name: &str, raw: &[u8]) -> io::Result<Document> {
    if raw.is_empty() || raw.len() > 4 * 1024 * 1024 {
        return Err(error("working preparation document exceeds source bound"));
    }
    let directory = parent_directory(root)?;
    let path = root.join(name);
    let mut file = OpenOptions::new().read(true).write(true).create_new(true)
        .mode(0o600).custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC).open(&path)?;
    let born = f9(&file)?;
    if born[2] != u64::from(libc::S_IFREG | 0o600) || born[3..6] != [0,0,1] {
        return Err(error("working preparation output is not a new root inode"));
    }
    file.write_all(raw)?;
    file.sync_all()?;
    file.set_permissions(fs::Permissions::from_mode(0o400))?;
    file.sync_all()?;
    directory.sync_all()?;
    let pin = f9(&file)?;
    if pin[2] != u64::from(libc::S_IFREG | 0o400) || pin[3..6] != [0,0,1]
        || pin[6] != raw.len() as u64 {
        return Err(error("working preparation immutable output metadata differs"));
    }
    let value = Document {path,file,pin,digest:sha(raw)};
    value.guard()?;
    Ok(value)
}

/// One fixed FD3 exchange in the actual installed preparation child.
/// No arbitrary parent, PID, path, UID, command, epoch or deadline is accepted.
pub struct WorkingPreparationChannel {
    socket: Option<Socket>,
    peer: ChildPeer,
    witness: WorkingSourceWitness,
    origin: WorkingSourceOrigin,
    publication: WorkingSourceFilePin,
    inspector: NativeApplicationInspector,
    main: MainCustodyObservation,
    end: Instant,
    wire_end: u64,
    root: PathBuf,
    root_file: File,
    root_identity: [u64; 5],
    documents: Vec<Document>,
}
impl WorkingPreparationChannel {
    pub fn acquire() -> Result<Self, String> {
        crate::working_qualification::seal_initial_child_entry()?;
        let peer = ChildPeer::capture_preparation().map_err(|e| e.to_string())?;
        let socket = Socket::inherited().map_err(|e| e.to_string())?;
        let hello_end = Instant::now() + Duration::from_secs(
            crate::native_working_contract::budget::SOURCE_AND_CAPTURE_SECONDS);
        peer.guard().map_err(|e| e.to_string())?;
        socket.send(&Packet {sequence:0,kind:1,case:PREPARATION_CASE,end_ns:0,
            payload:Vec::new()}, hello_end).map_err(|e|e.to_string())?;
        let ack = socket.receive(peer.parent_pid(), hello_end).map_err(|e|e.to_string())?;
        ack.require_sequence(0).map_err(|e|e.to_string())?;
        if ack.kind != 5 || ack.case != PREPARATION_CASE || ack.end_ns == 0 {
            return Err("working preparation initial acknowledgement differs".into());
        }
        let start: PreparationStart = serde_json::from_slice(&ack.payload).map_err(|e|e.to_string())?;
        if start.schema != "droidloom.working-preparation-start.v1"
            || start.preparation_end_ns != ack.end_ns
            || ack.end_ns >= start.origin.original_end_monotonic_ns {
            return Err("working preparation did not retain its original two phase ends".into());
        }
        let expected = start.origin.unit.owner_start_monotonic_ns.checked_add(
            crate::native_working_contract::PREPARATION_WORK_SECONDS.checked_mul(1_000_000_000)
                .ok_or("working preparation duration overflow")?)
            .ok_or("working preparation end overflow")?;
        if ack.end_ns != expected {
            return Err("working preparation end differs from the fixed original owner start".into());
        }
        let end = instant_until(ack.end_ns,
            Instant::now() + Duration::from_secs(crate::native_working_contract::PREPARATION_SECONDS))
            .map_err(|e|e.to_string())?;
        let witness = WorkingSourceWitness::capture(&start.origin)?;
        peer.guard().map_err(|e|e.to_string())?;
        let mut inspector = NativeApplicationInspector::acquire_until(
            Path::new(DEFAULT_CONTROL_SOCKET),end).map_err(|e|e.to_string())?;
        let main = inspector.observe_current_main_until(end).map_err(|e|e.to_string())?;
        witness.compare_main(&main)?;
        let base=Path::new("/var/lib/droidloom-qualification");
        parent_directory(base).map_err(|e|e.to_string())?;
        let root=base.join(format!("working-preparation-{}",start.origin.unit.invocation));
        fs::DirBuilder::new().mode(0o700).create(&root).map_err(|e|e.to_string())?;
        let root_file=parent_directory(&root).map_err(|e|e.to_string())?;
        let root_identity=f9(&root_file).map_err(|e|e.to_string())?[..5].try_into()
            .map_err(|_|"working preparation root identity")?;
        let value=Self{socket:Some(socket),peer,witness,origin:start.origin,
            publication:start.publication,inspector,main,end,wire_end:ack.end_ns,
            root,root_file,root_identity,documents:Vec::new()};
        value.guard()?;
        Ok(value)
    }
    pub fn deadline(&self)->Instant {self.end}
    pub fn main(&self)->&MainCustodyObservation {&self.main}
    pub fn observations(&mut self)->(&mut NativeApplicationInspector,&MainCustodyObservation) {
        (&mut self.inspector,&self.main)
    }
    pub fn source_publication(&self)->&WorkingSourceFilePin {&self.publication}
    pub fn cell_specification(&self)->Result<Value,String> {
        self.guard()?;
        Ok(json!({"path":"/etc/droidloom/cell.json",
            "bytes":self.origin.cell_configuration.bytes,
            "sha256":self.origin.cell_configuration.sha256}))
    }
    pub fn feishu_readonly_fixture(
        &self,
    ) -> Result<Option<crate::working_qualification::FeishuReadonlyFixture>, String> {
        self.guard()?;
        Ok(self.witness.feishu_readonly_fixture()?.cloned())
    }
    pub fn stage_directory(&self)->&Path {&self.root}
    pub fn guard(&self)->Result<(),String> {
        if self.socket.is_none() || Instant::now()>=self.end {
            return Err("working preparation channel ended".into());
        }
        self.peer.guard().map_err(|e|e.to_string())?;
        self.witness.compare_main(&self.main)?;
        self.inspector.revalidate().map_err(|e|e.to_string())?;
        let named=parent_directory(&self.root).map_err(|e|e.to_string())?;
        if f9(&self.root_file).map_err(|e|e.to_string())?[..5]!=self.root_identity
            || f9(&named).map_err(|e|e.to_string())?[..5]!=self.root_identity {
            return Err("working preparation root was replaced".into());
        }
        for document in &self.documents {document.guard().map_err(|e|e.to_string())?;}
        if Instant::now()>=self.end {return Err("preparation source checks exhausted original end".into());}
        Ok(())
    }
    pub fn write_document(&mut self,name:WorkingPreparationDocument,raw:&[u8])->Result<Value,String> {
        self.guard()?;
        let document=new_document(&self.root,name.name(),raw).map_err(|e|e.to_string())?;
        let reference=document.reference();
        self.documents.push(document);
        self.guard()?;
        Ok(reference)
    }
    /// The normal application producer calls this only after its strict complete
    /// source roster and per-case preparation documents have been validated.
    pub fn retain_plan(&mut self,raw:&[u8])->Result<PreparedWorkingPlan,String> {
        self.guard()?;
        if raw.is_empty() || raw.len()>4*1024*1024 {return Err("whole PLAN exceeds bound".into());}
        let digest=sha(raw);
        let path=plan_path(&digest).map_err(|e|e.to_string())?;
        let root=path.parent().ok_or("physical PLAN parent absent")?;
        parent_directory(root.parent().ok_or("physical stage base absent")?)
            .map_err(|e|e.to_string())?;
        fs::DirBuilder::new().mode(0o700).create(root).map_err(|e|e.to_string())?;
        let document=new_document(root,"PLAN.json",raw).map_err(|e|e.to_string())?;
        let plan=Plan::open(&digest).map_err(|e|e.to_string())?;
        if plan.pin!=document.pin {return Err("new whole PLAN inode differs on readback".into());}
        self.documents.push(document);
        self.guard()?;
        Ok(PreparedWorkingPlan{plan,epoch:self.main.facts().epoch.clone()})
    }
    /// Flush complete stdout before the private frame. The parent drains that
    /// pipe while waiting, then acknowledges only its whole-byte comparison.
    pub fn complete(mut self,plan:PreparedWorkingPlan)->Result<(),String> {
        self.guard()?;
        plan.plan.guard().map_err(|e|e.to_string())?;
        if plan.epoch!=self.main.facts().epoch {return Err("PLAN belongs to another actual Main".into());}
        let refreshed=self.inspector.refresh_main_until(&self.main,self.end).map_err(|e|e.to_string())?;
        self.witness.compare_main(&refreshed)?;
        if refreshed.facts()!=self.main.facts() {return Err("preparation actual Main changed".into());}
        self.main=refreshed;
        self.guard()?;
        let summary=json!({"schema":"droidloom.working-preparation-produced.v1",
            "plan":plan.observation(),"source_publication":self.publication,
            "actual_epoch":self.main.facts().epoch,
            "original_end_monotonic_ns":self.origin.original_end_monotonic_ns,
            "preparation_end_monotonic_ns":self.wire_end,"stage_directory":self.root,
            "application_gate_credit":false,"production_ready":false});
        let mut bytes=serde_json::to_vec_pretty(&summary).map_err(|e|e.to_string())?;
        bytes.push(b'\n');
        if bytes.len() as u64>PREPARATION_SUMMARY_LIMIT {return Err("preparation summary exceeds bound".into());}
        let mut out=std::io::stdout().lock();
        out.write_all(&bytes).and_then(|()|out.flush()).map_err(|e|e.to_string())?;
        drop(out);
        let ready=PreparationReady{schema:"droidloom.working-preparation-ready.v1".into(),
            plan_bytes:plan.plan.pin[6],plan_sha256:plan.plan.digest.clone(),
            summary_bytes:bytes.len() as u64,summary_sha256:sha(&bytes),
            binding:self.main.facts().clone()};
        let payload=serde_json::to_vec(&ready).map_err(|e|e.to_string())?;
        self.guard()?;
        let socket=self.socket.as_ref().ok_or("preparation channel absent")?;
        socket.send(&Packet{sequence:1,kind:4,case:PREPARATION_CASE,end_ns:self.wire_end,payload},
            self.end).map_err(|e|e.to_string())?;
        let ack=socket.receive(self.peer.parent_pid(),self.end).map_err(|e|e.to_string())?;
        ack.require_sequence(1).map_err(|e|e.to_string())?;
        if ack.kind!=5 || ack.case!=PREPARATION_CASE || ack.end_ns!=self.wire_end || !ack.payload.is_empty() {
            return Err("preparation completion acknowledgement differs".into());
        }
        self.guard()?;
        plan.plan.guard().map_err(|e|e.to_string())?;
        self.socket.take();
        Ok(())
    }
}
