"""Own child/socket tests, explicitly not a product Root or Notes acceptance."""
from pathlib import Path
import os,sys,json,socket,time,threading,hashlib,tempfile,shutil,errno
sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[3]
SOURCE=BASE/'support/ui'
FIXTURE_UID=FIXTURE_GID=None
TOOL_COMMIT=HEPTA_COMMIT=None
sys.path.insert(0,str(SOURCE))
with tempfile.TemporaryDirectory(prefix='trill-fault-fixture-source-') as _source_cache:
 _old_cache=sys.pycache_prefix
 try:
  sys.pycache_prefix=_source_cache
  from notes_fault_controller import run
  from notes_fault_linux import proc_identity
  from notes_fault_contract import digest
  TARGET={'session_instance':'a'*32,'task_id':3,'incarnation':'b'*32}
  TEXT='隔离故障控制器：只验证真实进程与字节边界'
  def encode(x):return json.dumps(x,ensure_ascii=False,separators=(',',':')).encode()
  def readexact(s,n):
   data=b''
   while len(data)<n:
    v=s.recv(n-len(data))
    if not v:break
    data+=v
   return data
 finally:
  sys.pycache_prefix=_old_cache

def app(fd,life,scenario,root):
 stream=socket.socket(fileno=fd)
 stream.settimeout(None)
 Path(root,'ready').write_text('ready')
 header=readexact(stream,4)
 if len(header)!=4:return 1
 raw=readexact(stream,int.from_bytes(header,'big'))
 request=json.loads(raw)
 applied=scenario!='not-applied'
 effect=encode({'revision':6,'text_sha256':digest(request['text'].encode())})
 if applied:
  file=os.open(Path(root,'effect.json'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  os.write(file,effect);os.fsync(file);os.close(file)
 result={'status':'applied','previous_revision':5,'revision':6,'text_sha256':digest(request['text'].encode())} if applied else {'status':'not_applied','reason':'revision_conflict','current_revision':6}
 reply=encode({'schema_version':1,'target':TARGET,'operation_id':request['operation_id'],'payload_sha256':digest(raw),'result':result})
 status={'effect_count':1 if applied else 0,'body_write_errno':None,'reply_sha256':digest(reply)}
 try:
  prefix=len(reply).to_bytes(4,'big')
  stream.sendall(prefix[:1]);stream.sendall(prefix[1:])
  if scenario=='short-body':
   stream.sendall(reply[:1]);stream.sendall(reply[1:])
  else:stream.sendall(reply)
 except OSError as e:status['body_write_errno']=e.errno
 Path(root,'app-result.json').write_text(json.dumps(status))
 os.read(life,1)
 return 0

def session(fd,scenario):
 control=socket.socket(fileno=fd)
 control.settimeout(15)
 reader=control.makefile('rb')
 root=None;child=None;life_write=None;parent=None
 try:
  os.setgroups([]);os.setresgid(FIXTURE_GID,FIXTURE_GID,FIXTURE_GID);os.setresuid(FIXTURE_UID,FIXTURE_UID,FIXTURE_UID)
  root=tempfile.mkdtemp(prefix='trill-private-fault-fixture-');os.chmod(root,0o700)
  parent,childsocket=socket.socketpair()
  life_read,life_write=os.pipe()
  child=os.fork()
  if child==0:
   parent.close();control.close();reader.close();os.close(life_write)
   os.set_inheritable(childsocket.fileno(),True);os.set_inheritable(life_read,True)
   env=dict(os.environ,TRILL_NOTES_STATE_DIR=root,PYTHONDONTWRITEBYTECODE='1')
   os.execve(sys.executable,[sys.executable,'-B',str(Path(__file__).resolve()),'--app',str(childsocket.fileno()),str(life_read),scenario,root],env)
  childsocket.close();os.close(life_read)
  expires=time.monotonic()+5
  while not Path(root,'ready').exists() and time.monotonic()<expires:time.sleep(.005)
  control.sendall(encode({'session_pid':os.getpid(),'app_pid':child,'state_dir':root})+b'\n')
  command=reader.readline()
  if command!=b'go\n':raise RuntimeError('No original fixture go')
  text=TEXT+' wrong' if scenario=='wrong-request' else TEXT
  request={'schema_version':1,'action':'replace_note','operation_id':'fixture:original-op','destination_id':'trill.notes:'+'a'*32+':3:'+'b'*32,'target':TARGET,'expected_revision':5,'text':text}
  raw=encode(request);parent.settimeout(6);parent.sendall(len(raw).to_bytes(4,'big'));parent.sendall(raw)
  header=readexact(parent,4)
  expected=int.from_bytes(header,'big') if len(header)==4 else None
  body=readexact(parent,expected) if expected is not None else b''
  expires=time.monotonic()+2
  while not Path(root,'app-result.json').exists() and time.monotonic()<expires:time.sleep(.005)
  child_result=json.loads(Path(root,'app-result.json').read_text())
  report={'peer_header_bytes':len(header),'peer_expected_body_bytes':expected,'peer_body_bytes':len(body),'peer_body_sha256':digest(body),'app':child_result,'app_state_before_owned_exit':proc_identity(child)['state']}
  control.sendall(encode(report)+b'\n')
  if reader.readline()!=b'quit\n':raise RuntimeError('No owned fixture quit')
 finally:
  if life_write is not None:os.close(life_write)
  if parent is not None:parent.close()
  if child is not None:
   got,status=os.waitpid(child,0)
   control.sendall(encode({'reaped_app':got,'app_wait_status':status})+b'\n')
  if root is not None:shutil.rmtree(root)
  reader.close();control.close()
 return 0

def binding_for(pid):
 p=proc_identity(pid);exe=Path(f'/proc/{pid}/exe').resolve(strict=True)
 return {'pid':pid,'start_ticks':p['start_ticks'],'uid':p['uid'][0],'gid':p['gid'][0],'executable':str(exe),'sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}

def one(scenario,mode):
 parent,childsocket=socket.socketpair();parent.settimeout(20)
 pid=os.fork()
 if pid==0:
  parent.close()
  try:code=session(childsocket.detach(),scenario)
  except BaseException as e:print('fixture session:',repr(e),file=sys.stderr,flush=True);code=1
  os._exit(code)
 childsocket.close();reader=parent.makefile('rb')
 info=json.loads(reader.readline())
 binding={'schema':'trill.notes.partial-reply-fault.v1','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'desktop_commit':TOOL_COMMIT,'hepta_commit':HEPTA_COMMIT,'root':binding_for(os.getpid()),'session':binding_for(pid),'app':binding_for(info['app_pid']),'target':TARGET,'expected_revision':5,'text_sha256':digest(TEXT.encode()),'notes_state_dir':info['state_dir']}
 initial=Path(f'/proc/{info["app_pid"]}/syscall').read_text().split()
 initial_syscall={'number':initial[0],'fd':initial[1] if len(initial)>1 else None,'count':initial[3] if len(initial)>3 else None}
 sent=threading.Event();producer_error=[]
 def go_when_traced():
  try:
   end=time.monotonic()+4
   while time.monotonic()<end:
    p=proc_identity(info['app_pid'])
    if p['tracer']==os.getpid():
     parent.sendall(b'go\n');sent.set();return
    time.sleep(.002)
  except Exception as e:producer_error.append(repr(e))
 producer=threading.Thread(target=go_when_traced);producer.start()
 result=run(binding,mode,8,lambda:False)
 producer.join()
 if not sent.is_set():parent.sendall(b'go\n')
 report=json.loads(reader.readline())
 parent.sendall(b'quit\n');reaped=json.loads(reader.readline())
 reader.close();parent.close();got,status=os.waitpid(pid,0)
 expected='boundary_observed_without_fault' if mode=='observe' else 'reply_body_shutdown_observed_epipe' if scenario=='applied' else 'unexecuted'
 ok=result['status']==expected and report['peer_header_bytes']==4 and report['app_state_before_owned_exit'] not in ('Z','X') and status==0 and reaped['app_wait_status']==0
 if scenario!='applied':
  expected_reason={'not-applied':'selected_reply_not_applied','wrong-request':'request_text_mismatch','short-body':'incomplete_applied_body_buffer'}[scenario]
  ok=ok and result.get('reason')==expected_reason and result.get('tracing',{}).get('stops',0)>0
 if scenario=='applied' and mode=='drop-reply-body':ok=ok and report['peer_body_bytes']==0 and report['app']['body_write_errno']==errno.EPIPE and result['action_taken']
 else:ok=ok and report['peer_body_bytes']==report['peer_expected_body_bytes'] and not result['action_taken'] and report['peer_body_sha256']==report['app']['reply_sha256']
 return {'initial_syscall':initial_syscall,'scenario':scenario,'mode':mode,'expected_status':expected,'passed':ok,'controller':result,'peer':report,'owned_reap':reaped,'session_reaped':got,'session_wait_status':status,'producer_error':producer_error}

def source_snapshot():
 paths=[SOURCE/name for name in ('notes_fault_contract.py','notes_fault_linux.py','notes_fault_controller.py')]+[Path(__file__).resolve()]
 return {str(path.relative_to(BASE)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

def fixture_options():
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--fixture-uid',type=int,default=int(os.environ.get('SUDO_UID','0')))
 parser.add_argument('--fixture-gid',type=int,default=int(os.environ.get('SUDO_GID','0')))
 args=parser.parse_args()
 if not (0<args.fixture_uid<2**32 and 0<=args.fixture_gid<2**32):parser.error('Provide the non-Root fixture UID/GID')
 if not args.output.is_absolute() or args.output.resolve()!=args.output or args.output.is_relative_to(BASE):parser.error('Output must be a new canonical directory outside the source checkout')
 return args

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='--app':raise SystemExit(app(int(sys.argv[2]),int(sys.argv[3]),sys.argv[4],sys.argv[5]))
 options=fixture_options();FIXTURE_UID,FIXTURE_GID=options.fixture_uid,options.fixture_gid
 if os.getuid()!=0 or os.geteuid()!=0:raise SystemExit('Actual UID/EUID zero required; no mocked UID')
 import subprocess
 git_env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')};git_env['GIT_NO_REPLACE_OBJECTS']='1'
 TOOL_COMMIT=subprocess.check_output(['git','-c','safe.directory='+str(BASE),'-C',str(BASE),'rev-parse','HEAD'],env=git_env,text=True).strip()
 HEPTA_COMMIT=json.loads((SOURCE/'HEPTA_SHARED_PRESENTER.json').read_text())['commit']
 out=options.output;out.mkdir(mode=0o700)
 before=source_snapshot()
 receipt={'scope':'Own fork/exec Python process/socket fixture only; not installed ELF, genuine Root authority, human, model, owner receipt or Notes product acceptance','uid':os.getuid(),'euid':os.geteuid(),'cases':[],'product_qualified':False,'tool_commit':TOOL_COMMIT,'selected_hepta_commit':HEPTA_COMMIT}
 for scenario,mode in [('applied','observe'),('applied','drop-reply-body'),('not-applied','drop-reply-body'),('wrong-request','drop-reply-body'),('short-body','drop-reply-body')]:
  try:receipt['cases'].append(one(scenario,mode))
  except BaseException as e:receipt['error']=repr(e);break
  (out/'result.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 receipt['source_before']=before;receipt['source_after']=source_snapshot();receipt['source_unchanged']=receipt['source_before']==receipt['source_after']
 receipt['passed']=len(receipt['cases'])==5 and all(c['passed'] for c in receipt['cases']) and receipt['source_unchanged'];(out/'result.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False),flush=True)
 raise SystemExit(0 if receipt['passed'] else 1)
