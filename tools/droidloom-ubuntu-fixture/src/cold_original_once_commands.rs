//! Fixed calls to the existing normal cold engines. Only the Rust once owner
//! can select these operations; there is no public argv or acceptance flag.
use super::{OriginalQualificationAuthority, owner::SealedInput};
use crate::{
    Result,
    boot_files::{self as files, FilePin},
    ensure, fs,
};
use serde_json::{Value, json};
use std::{
    fs::File,
    io::Seek,
    os::fd::AsRawFd,
    path::{Path, PathBuf},
};

const PYTHON_BYTES: u64 = 7_477_160;
const PYTHON_SHA: &str = "52e0a13e60a981d8c4b6478be2ba5176f69da07948a056bf49cf6f077e30cb41";

// This is an internal adapter to the already source-bound engines, not a new
// Python CLI. All source files are exact embedded normal-producer bytes. In
// particular package rollback uses the original durable engine snapshots.
const DRIVER: &str = r#"import sys,json,os,stat,hashlib,contextlib,re
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from release import need,held,hash_fd,file_pin,read_pin,read_json_file,canonical,f9,TOOLS,_fixed_command,verify_original_grub_entry,original_grub_entry,ORIGINAL_ROOT_UUID,ORIGINAL_KERNEL,new_file
from cold_apply import PublicTransaction,original_cold_context,COLD_OWNER_UNITS
from cold_native import NativeTransaction
from native_release import verify_bundle,ORIGINAL_SCHEMA
request=json.loads(Path(sys.argv[2]).read_text())
need(set(request)=={'schema','candidate_id','intent','operation','arguments','materials'},'fixed Rust command field set')
need(request['schema']=='droidloom.original-once-fixed-command.v1','fixed command schema')
m=request['materials'];op=request['operation'];arg=request['arguments']
context=original_cold_context()
need(m['deployment_id']==request['candidate_id'],'normal candidate identity')
public=Path(m['public_release']['path']).parent;native=Path(m['native_release']['path']).parent
need(file_pin(public/'RELEASE.json')==m['public_release'] and file_pin(native/'NATIVE-RELEASE.json')==m['native_release'],'same complete normal manifests')

def serialize(v):
 if isinstance(v,bytes):return v.decode('utf-8','strict')
 if isinstance(v,Path):return str(v)
 if isinstance(v,dict):return {k:serialize(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)):return [serialize(x) for x in v]
 return v

_tool_sources=contextlib.ExitStack()
_tool_custody=[]
_tool_payloads=None

def source_attrs(fd):
 names=os.listxattr(fd)
 need(len(names)==len(set(names)) and len(names)<=16,'normal tool source xattr inventory')
 return {n:os.getxattr(fd,n) for n in names}

def check_tool_sources(full=False):
 for path,fd,before,attrs,pin in _tool_custody:
  with held(path,root=True,maximum=16*1024**3) as (named,now):
   need(f9(os.fstat(fd))==f9(before)==f9(now),'normal tool archive custody changed')
   need(source_attrs(fd)==attrs==source_attrs(named),'normal tool archive xattrs changed')
   if full:need(hash_fd(fd)==pin['sha256'],'normal tool archive full source bytes changed')
   need(f9(os.fstat(fd))==f9(before)==f9(os.fstat(named)),'normal tool archive changed during readback')

def normal_tool_payloads():
 global _tool_payloads
 if _tool_payloads is None:
  descriptor=json.loads(read_pin(m['native_release']))
  need(descriptor['schema']==ORIGINAL_SCHEMA and isinstance(descriptor['files'],list) and len(descriptor['files'])<=512,'bounded exact original native source')
  rows=[{'path':'NATIVE-RELEASE.json','bytes':m['native_release']['bytes'],'sha256':m['native_release']['sha256']}]+descriptor['files']
  seen=set()
  for pin in rows:
   relative=pin['path'];parts=Path(relative).parts
   need(not Path(relative).is_absolute() and parts and all(p not in ('','.','..') for p in parts) and relative not in seen,'normal native relative source')
   seen.add(relative);path=native/relative
   fd,st=_tool_sources.enter_context(held(path,root=True,maximum=16*1024**3))
   need(st.st_size==pin['bytes'] and hash_fd(fd)==pin['sha256'],'normal tool initial source bytes')
   _tool_custody.append((path,fd,st,source_attrs(fd),pin))
  actual,closure,packages,payloads=verify_bundle(native,m['native_release_id'],True)
  need(actual==descriptor and len(packages)==22,'exact physical native22 source')
  check_tool_sources();_tool_payloads=payloads
 else:check_tool_sources()
 return _tool_payloads

def normal_tool(name,args,seconds=60,maximum=8*1024*1024,borrowed=()):
 # The original kernel may already have its normally upgraded systemd. Select
 # only the actual old/new member of this complete native22 source closure.
 if name in ('systemctl','journalctl','loginctl','systemd-run'):
  payloads=normal_tool_payloads()
  path='/usr/bin/'+name;rows=[]
  for kind in ('old','new'):
   row=payloads['systemd'][kind]['payload']['usr/bin/'+name]
   need(row['type']=='0' and row['mode']==0o755 and row['uid']==row['gid']==0,'normal fixed tool member')
   rows.append((kind,row))
  with held(path,root=True,modes={0o755},maximum=16*1024*1024) as (fd,st):actual=(st.st_size,hash_fd(fd))
  matches=[(k,r) for k,r in rows if actual==(r['bytes'],r['sha256'])]
  need(len(matches)==1,'fixed tool must uniquely match the actual old/new normal package member')
  kind,row=matches[0]
  result=_fixed_command(path,row['bytes'],row['sha256'],args,uid=None,seconds=seconds,maximum=maximum,borrowed=borrowed)
  check_tool_sources()
  result['normal_package_kind']=kind
  result['normal_native_release']=m['native_release']
  return result
 need(name=='grub-editenv','closed normal tool name')
 path,size,sha=TOOLS[name]
 return _fixed_command(path,size,sha,args,uid=None,seconds=seconds,maximum=maximum,borrowed=borrowed)

def preservation(kind,snapshot,current):
 proof=arg.get('restored_metadata')
 if proof is None:
  need(current==snapshot,'original complete preserved metadata changed');return None
 v=json.loads(read_pin(proof,16*1024*1024,True))
 label=v['actual_label_restoration']
 need(re.fullmatch('[0-9a-f]{64}',label['sha256']) and Path(proof['path'])==Path(request['intent']['path']).parent/('NORMAL-PACKAGE-PRESERVATION-'+label['sha256']+'.json'),'fixed actual restoration preservation source')
 need(v['schema']=='droidloom.original-once-package-preservation.v1' and v['candidate_id']==request['candidate_id'] and v['intent']==request['intent'],'same actual original-return metadata source')
 source=v['snapshots'][kind]
 need(source['snapshot']==arg['snapshot'] and source['original']==snapshot,'original normal package snapshot was not rewritten')
 need(set(current)==set(snapshot),'fixed preserved metadata roster differs')
 for name,old in snapshot.items():
  now=current[name]
  if kind=='native' and old.get('absent'):
   need(now==old,'an absent preserved inode appeared');continue
  path=name if name.startswith('/') else '/'+name
  row=v['metadata']['paths'][path]
  def ident(i):return [i['dev'],i['ino'],i['mode'],i['uid'],i['gid'],i['nlink'],i['size'],i['mtime_sec']*10**9+i['mtime_nsec'],i['ctime_sec']*10**9+i['ctime_nsec']]
  old_id=old if kind=='public' else old['f9'];now_id=now if kind=='public' else now['f9']
  need(ident(row['prelabel']['identity'])==old_id and ident(row['restored']['identity'])==now_id,'actual preserved metadata is not its observed source-to-restored derivation')
  if kind=='native':
   need(old.get('type')==now.get('type') and old.get('target')==now.get('target') and all(old['node'][k]==now['node'][k] for k in ('device','inode','mode','uid','gid')),'normal preserved node type/owner/link contract changed')
  need({n:list(os.getxattr(path,n,follow_symlinks=False)) for n in os.listxattr(path,follow_symlinks=False)}==row['restored']['attributes'],'actual restored preservation xattrs changed')
 return proof

class OncePublicTransaction(PublicTransaction):
 def preserved(self):
  actual={path:list(f9((self.root/path.lstrip('/')).lstat())) for path in self.snapshot['preserved_metadata_only']}
  preservation('public',self.snapshot['preserved_metadata_only'],actual)
class OnceNativeTransaction(NativeTransaction):
 def verify_private_preservation(self):
  return preservation('native',self.snapshot['private_metadata'],self.private_metadata())

def public_transaction(existing):
 t=OncePublicTransaction(Path('/'),public,m['public_release_id'],existing=existing)
 if existing:need(t.expected_snapshot==arg['snapshot'],'exact source-owned public snapshot')
 return t

def native_transaction(existing):
 t=OnceNativeTransaction(Path('/'),native,m['native_release_id'],existing=existing)
 if existing:need(file_pin(t.attempt/'SNAPSHOT.json')==arg['snapshot'],'exact source-owned native snapshot')
 return t

def transaction_result(t,kind):
 directory=t.path if kind=='public' else t.attempt
 result={'kind':kind,'directory':str(directory),'snapshot':file_pin(directory/'SNAPSHOT.json')}
 if kind=='native':result['attempt']=t.attempt.name;result['events']=t.history
 else:
  result['pointer']=file_pin(t.pointer)
  result['journal']=file_pin(t.journal)
 return result

if op=='public-snapshot':
 t=public_transaction(False)
 try:t.capture();result=transaction_result(t,'public')
 finally:t.close()
elif op in ('public-apply','public-verify','public-rollback'):
 t=public_transaction(True)
 try:
  if op=='public-apply':
   t.claim_public_namespaces();t.dpkg('unpack');t.dpkg('configure');t.restore_directory_metadata();t.verify_installed();t.event('public-phase-completed',activated=False)
  elif op=='public-verify':t.verify_installed()
  else:t.rollback()
  result=transaction_result(t,'public')
 finally:t.close()
elif op=='native-snapshot':
 t=native_transaction(None)
 try:t.begin();result=transaction_result(t,'native')
 finally:t.close()
elif op in ('native-apply','native-verify','native-rollback'):
 t=native_transaction(arg['attempt'])
 try:
  if op=='native-apply':t.apply()
  elif op=='native-verify':t.verify_installed('new')
  else:t.rollback()
  result=transaction_result(t,'native')
 finally:t.close()
elif op in ('package-writers-stop','package-writers-restore'):
 units=arg['units'];expected=['apt-daily.service','apt-daily.timer','apt-daily-upgrade.service','apt-daily-upgrade.timer','unattended-upgrades.service','packagekit.service','packagekit-offline-update.service','snapd.service','snapd.socket','snapd.snap-repair.service','snapd.snap-repair.timer']
 need(units==expected,'exact source package writer set')
 def inventory(names):
  rows=[]
  for name in names:
   q=normal_tool('systemctl',['show',name,'--no-pager','--property=Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,FragmentPath,DropInPaths,Transient'])
   row=dict(line.split('=',1) for line in q['stdout'].decode('utf-8','strict').splitlines() if '=' in line)
   need(q['exit']==0 or row.get('LoadState')=='not-found' and row.get('ActiveState')=='inactive','actual package writer observation failed')
   need(row.get('Id')==name and row.get('ActiveState') in ('active','inactive','failed'),'package writer is in an unknown/transitional state')
   rows.append(row)
  return rows
 before=inventory(units)
 if op=='package-writers-stop':
  cold=inventory(COLD_OWNER_UNITS)
  intent={'schema':'droidloom.original-once-package-writers.v1','candidate_id':request['candidate_id'],'intent':request['intent'],'source':m['native_release'],'units':units,'actual_before':before,'actual_cold_before':cold}
  saved=Path(sys.argv[2]).parent/'WRITERS-INTENT.json';new_file(saved,canonical(intent),0o400)
  d=os.open(saved.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);os.fsync(d);os.close(d)
  active=[r['Id'] for r in before+cold if r['ActiveState']=='active']
  change=normal_tool('systemctl',['stop',*active],seconds=90) if active else None
  need(change is None or change['exit']==0,'normal package writer stop failed')
  after=inventory(units);cold_after=inventory(COLD_OWNER_UNITS);need(all(r['ActiveState'] in ('inactive','failed') and r.get('MainPID','0')=='0' for r in after+cold_after),'a real package writer did not retire')
  result={'original':file_pin(saved),'before':before,'after':after,'actual_cold_before':cold,'actual_cold_after':cold_after,'command':change}
 else:
  original=arg['original'];v=json.loads(read_pin(original,1024*1024,True))
  need(v['schema']=='droidloom.original-once-package-writers.v1' and v['candidate_id']==request['candidate_id'] and v['intent']==request['intent'] and v['units']==units,'writer restoration uses another actual original inventory')
  active=[r['Id'] for r in v['actual_before'] if r['ActiveState']=='active']
  change=normal_tool('systemctl',['start',*active],seconds=90) if active else None
  need(change is None or change['exit']==0,'normal original writer restart failed')
  after=inventory(units);need(all(r['ActiveState']=='active' for r in after if r['Id'] in active),'normal original writer restart was not observed')
  need(all(r['ActiveState'] in ('inactive','failed') for r in after if r['Id'] not in active),'restoration started an originally inactive writer')
  cold_active=[r['Id'] for r in v['actual_cold_before'] if r['ActiveState']=='active']
  cold_request=normal_tool('systemctl',['--no-block','start',*cold_active],seconds=30) if cold_active else None
  need(cold_request is None or cold_request['exit']==0,'normal original graphical restore request failed')
  result={'original':original,'before':before,'after':after,'command':change,'cold_original_request':cold_request,'cold_activation_observed':False}
elif op=='quiescence-inventory':
 fixed=['gdm.service','gdm3.service','systemd-journald.service','rsyslog.service','accounts-daemon.service','user@1000.service','user@120.service','user@981.service','user@997.service','hepta-runtime.service']
 props=['Id','LoadState','ActiveState','SubState','ControlGroup','MainPID','InvocationID','FragmentPath','DropInPaths','Transient','Restart']
 sessions=normal_tool('loginctl',['list-sessions','--no-legend','--no-pager']);need(sessions['exit']==0,'normal session inventory failed')
 session_ids=[]
 for line in sessions['stdout'].decode('utf-8','strict').splitlines():
  words=line.split();need(words and len(words[0])<=32 and words[0].isalnum(),'bounded actual session ID')
  session_ids.append(words[0])
 need(len(session_ids)<=128,'bounded original sessions')
 observed=[]
 for sid in session_ids:
  q=normal_tool('loginctl',['show-session',sid,'--no-pager','--property=Id,User,Remote,Type,Class,Scope,Leader,State'])
  need(q['exit']==0,'actual original session readback failed')
  row=dict(line.split('=',1) for line in q['stdout'].decode().splitlines() if '=' in line)
  observed.append(row)
  if row.get('User') in ('1000','120','981') and row.get('Remote')=='no' and row.get('Class')=='user' and row.get('Type') in ('wayland','x11'):
   scope=row.get('Scope','');need(scope=='session-'+sid+'.scope','actual graphical scope identity');fixed.append(scope)
 units=[]
 for name in fixed+['droidloom-original-qualification@'+request['candidate_id']+'.service']:
  q=normal_tool('systemctl',['show',name,'--no-pager','--property='+','.join(props)])
  need(q['exit']==0,'normal unit observation failed')
  row=dict(line.split('=',1) for line in q['stdout'].decode().splitlines() if '=' in line);row['RequestedId']=name;units.append(row)
 result={'units':units,'sessions':observed,'critical_excluded':['init.scope','ssh.service','ssh.socket','sshd.service','systemd-networkd.service','NetworkManager.service','dbus.service','systemd-logind.service','polkit.service'],'source':m['native_release']}
elif op=='quiescence-reaper':
 producer=arg['producer'];freeze=arg['freeze_intent'];unit='droidloom-original-thaw@'+request['candidate_id']+'.service'
 need(file_pin(Path(producer['path']))==producer,'normal reaper producer bytes')
 need(Path(freeze['path']).name=='FREEZE-INTENT.json' and file_pin(Path(freeze['path']))==freeze,'exact immutable freeze intent')
 log=str(Path(freeze['path']).parent/'thaw-reaper.log')
 result=normal_tool('systemd-run',['--unit='+unit,'--property=Type=exec','--property=Restart=no','--property=KillMode=control-group','--property=StandardInput=null','--property=StandardOutput=file:'+log,'--property=StandardError=inherit','--property=UMask=0077','--property=AmbientCapabilities=','--property=NoNewPrivileges=no','--collect','--',producer['path'],'__original-once-thaw','--config',freeze['path'],'--config-sha256',freeze['sha256']],seconds=30)
 need(result['exit']==0,'independent normal thaw guard failed to start')
elif op=='systemctl':
 args=arg['argv'];need(isinstance(args,list) and 1<=len(args)<=64 and all(isinstance(s,str) and len(s)<=512 and '\x00' not in s for s in args),'bounded source systemctl argv')
 need(args[0] in ('show','stop','start','daemon-reload','is-active','--no-block'),'closed systemctl operation')
 result=normal_tool('systemctl',args,seconds=90)
elif op in ('grub-read','grub-arm','grub-disarm'):
 with held('/boot/grub/grub.cfg',root=True,maximum=16*1024*1024) as (fd,st):
  body=os.pread(fd,st.st_size+1,0)
  original=verify_original_grub_entry(body,ORIGINAL_ROOT_UUID,original_grub_entry(ORIGINAL_ROOT_UUID),ORIGINAL_KERNEL)
  need(hashlib.sha256(body).hexdigest()==arg['original_cfg_sha256'],'original GRUB body changed')
 with held('/boot/grub/grubenv',root=True,modes={0o644},maximum=1024) as (fd,st):
  need(st.st_size==1024 and st.st_nlink==1,'normal GRUB environment identity')
  before=os.pread(fd,1024,0);listed=normal_tool('grub-editenv',[f'/proc/self/fd/{fd}','list'],maximum=65536,borrowed=(fd,))
  need(listed['exit']==0,'normal GRUB environment read failed')
  fields={}
  for line in listed['stdout'].decode('utf-8','strict').splitlines():
   name,value=line.split('=',1);need(name not in fields,'duplicate GRUB environment key');fields[name]=value
  candidate='droidloom-original-once-'+request['candidate_id']
  oldnext=fields.get('next_entry','')
  need(oldnext in ('',candidate,original_grub_entry(ORIGINAL_ROOT_UUID)),'foreign one-shot boot selection')
  changed=None
  if op=='grub-arm':
   need(oldnext=='','a one-shot boot is already selected')
   changed=normal_tool('grub-editenv',[f'/proc/self/fd/{fd}','set','next_entry='+candidate],maximum=65536,borrowed=(fd,))
  elif op=='grub-disarm' and oldnext:
   changed=normal_tool('grub-editenv',[f'/proc/self/fd/{fd}','unset','next_entry'],maximum=65536,borrowed=(fd,))
  need(changed is None or changed['exit']==0,'normal GRUB mutation failed')
  again=normal_tool('grub-editenv',[f'/proc/self/fd/{fd}','list'],maximum=65536,borrowed=(fd,));need(again['exit']==0,'normal GRUB final read failed')
  after=os.pread(fd,1024,0);now=os.fstat(fd);named=os.stat('/boot/grub/grubenv',follow_symlinks=False)
  need(f9(now)==f9(named) and f9(st)[:7]==f9(now)[:7],'GRUB mutation replaced or resized its held inode')
  final={}
  for line in again['stdout'].decode('utf-8','strict').splitlines():
   name,value=line.split('=',1);need(name not in final,'duplicate final GRUB key');final[name]=value
  expected=candidate if op=='grub-arm' else ('' if op=='grub-disarm' else oldnext)
  need(final.get('next_entry','')==expected and {k:v for k,v in final.items() if k!='next_entry'}=={k:v for k,v in fields.items() if k!='next_entry'},'only the owned one-shot field may change')
  result={'original':original,'before':{'identity':f9(st),'body_hex':before.hex(),'sha256':hashlib.sha256(before).hexdigest()},'after':{'identity':f9(now),'body_hex':after.hex(),'sha256':hashlib.sha256(after).hexdigest()},'before_fields':fields,'after_fields':final,'command':changed,'readback':again,'default_changed':False}
elif op=='retirement-journal':
 boot=arg['boot'];need(isinstance(boot,str) and len(boot)==36,'bounded candidate boot')
 fields='_BOOT_ID,_PID,_UID,_EXE,_COMM,_SYSTEMD_UNIT,_SYSTEMD_USER_UNIT,_SYSTEMD_INVOCATION_ID,__MONOTONIC_TIMESTAMP,__REALTIME_TIMESTAMP,MESSAGE_ID,MESSAGE,UNIT,USER_UNIT,UNIT_RESULT,JOB_RESULT,INVOCATION_ID'
 verified=normal_tool('journalctl',['--directory=/var/log/journal','--verify'],seconds=60)
 rows=normal_tool('journalctl',['--directory=/var/log/journal','--boot='+boot,'--no-pager','--all','--output=json','--output-fields='+fields,'_PID=1','+','_SYSTEMD_UNIT=systemd-journald.service'],seconds=60,maximum=16*1024*1024)
 result={'verify_exit':verified['exit'],'verify_stdout':verified['stdout'].decode('utf-8','strict'),'verify_stderr':verified['stderr'].decode('utf-8','strict'),'exit':rows['exit'],'stderr':rows['stderr'].decode('utf-8','strict'),'rows':[json.loads(line) for line in rows['stdout'].splitlines()],'normal_journalctl_package_kind':rows['normal_package_kind']}
else:raise RuntimeError('unsupported source-owned once operation')
check_tool_sources(full=True)
_tool_sources.close()
need(original_cold_context()==context,'original kernel/root/boot changed during the normal command')
print(json.dumps(serialize({'schema':'droidloom.original-once-fixed-command-result.v1','operation':op,'candidate_id':request['candidate_id'],'intent':request['intent'],'original':context,'result':result}),sort_keys=True))
"#;

pub(super) struct CommandEvidence {
    pub(super) report: Value,
    pub(super) pin: FilePin,
}

pub(super) fn call(
    a: &OriginalQualificationAuthority,
    name: &str,
    operation: &str,
    arguments: Value,
    seconds: u64,
) -> Result<CommandEvidence> {
    ensure(
        name.len() <= 96
            && !name.is_empty()
            && name
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-'),
        "fixed command log name required",
    )?;
    a.verify_current_owner()?;
    let report: Value =
        serde_json::from_slice(&files::read_pin(a.materials.report(), 128 * 1024 * 1024)?)?;
    let materials = &report["normal_initramfs"]["normal_materials"];
    let dir = a.work().join("commands");
    if !dir.exists() {
        files::private_dir(&dir)?;
        File::open(a.work())?.sync_all()?;
    }
    let work = dir.join(name);
    files::private_dir(&work)?;
    let input = json!({"schema":"droidloom.original-once-fixed-command.v1","candidate_id":a.candidate_id(),"intent":a.intent.pin(),"operation":operation,"arguments":arguments,"materials":materials});
    let input_path = work.join("INPUTS.json");
    let mut body = serde_json::to_vec(&input)?;
    body.push(b'\n');
    files::write_new(&input_path, &body, 0o400)?;
    File::open(&work)?.sync_all()?;
    let input_pin = files::pin_file(&input_path)?;
    let seal = SealedInput::open(&input_pin)?;
    let source = a.work().join("cold-source");
    for (name, bytes) in crate::boot_host::cold_modules::FILES {
        let pin = FilePin {
            path: source.join(Path::new(name).file_name().ok_or("cold module basename")?),
            bytes: bytes.len() as u64,
            sha256: fs::digest(bytes),
        };
        ensure(
            files::read_pin(&pin, 1024 * 1024)? == *bytes,
            "normal command source changed",
        )?;
    }
    let python_pin = FilePin {
        path: PathBuf::from("/usr/bin/python3.14"),
        bytes: PYTHON_BYTES,
        sha256: PYTHON_SHA.into(),
    };
    let (python, id) = files::open_pin(&python_pin)?;
    ensure(
        id.uid == 0 && id.gid == 0 && id.mode & 0o7777 == 0o755 && id.nlink == 1,
        "normal interpreter custody differs",
    )?;
    ensure(
        fs::hash(&python)? == python_pin.sha256
            && fs::stat(&python)? == id
            && fs::Tree::open("/", 0)?.identity("/usr/bin/python3.14")? == id
            && fs::xattrs(&python)?.keys().all(|k| k == "security.selinux"),
        "normal interpreter complete bytes or privilege attributes differ before exec",
    )?;
    let preservation = if matches!(operation, "public-rollback" | "native-rollback") {
        arguments
            .get("restored_metadata")
            .filter(|v| !v.is_null())
            .map(|v| {
                let p: FilePin = serde_json::from_value(v.clone())?;
                super::configurations::PackagePreservation::open(a, &p)
            })
            .transpose()?
    } else {
        None
    };
    let result = files::run_logged(
        &work,
        "normal-command",
        &format!("/proc/{}/fd/{}", std::process::id(), python.as_raw_fd()),
        &[
            "-I".into(),
            "-B".into(),
            "-c".into(),
            DRIVER.into(),
            fs::absolute_string(&source)?,
            fs::absolute_string(&input_path)?,
        ],
        seconds,
    )?;
    ensure(
        result.exit_code == Some(0) && !result.timed_out,
        "normal source-owned command failed or timed out",
    )?;
    (&python).rewind()?;
    ensure(
        fs::stat(&python)? == id
            && fs::hash(&python)? == python_pin.sha256
            && fs::Tree::open("/", 0)?.identity("/usr/bin/python3.14")? == id,
        "normal interpreter changed across command",
    )?;
    seal.revalidate()?;
    if let Some(held) = &preservation {
        held.revalidate()?;
    }
    a.verify_current_owner()?;
    let actual: Value = serde_json::from_slice(&files::read_pin(&result.log, 64 * 1024 * 1024)?)?;
    ensure(
        actual["schema"] == "droidloom.original-once-fixed-command-result.v1"
            && actual["operation"] == operation
            && actual["candidate_id"] == a.candidate_id()
            && actual["intent"] == serde_json::to_value(a.intent.pin())?,
        "normal command result belongs to another source or transaction",
    )?;
    let evidence = json!({"schema":"droidloom.original-once-command-evidence.v1","input":input_pin,"command":result,"actual":actual});
    let path = work.join("RESULT.json");
    let mut bytes = serde_json::to_vec(&evidence)?;
    bytes.push(b'\n');
    files::write_new(&path, &bytes, 0o400)?;
    File::open(&work)?.sync_all()?;
    Ok(CommandEvidence {
        report: actual["result"].clone(),
        pin: files::pin_file(&path)?,
    })
}
