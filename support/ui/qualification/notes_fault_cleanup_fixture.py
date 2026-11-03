"""Actual UID0 own-process ptrace cleanup tests; no product, Notes or model."""
from pathlib import Path
import os,sys,json,time,threading,signal,hashlib,tempfile,shutil,ctypes,select
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
  from notes_fault_linux import HeldProcess,TraceThread,proc_identity,SEIZE,INTERRUPT,SYSGOOD,LIBC
  from notes_fault_controller import idle_snapshot
  from notes_fault_contract import Refused
 finally:
  sys.pycache_prefix=_old_cache

def wait_file(path,seconds=2):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if path.exists():return
  time.sleep(.002)
 raise RuntimeError('Fixture marker absent: '+str(path.name))

def child(scenario,inputfd,lifefd,root):
 root=Path(root);received=[0]
 def handler(*_):
  received[0]+=1
  (root/'signals.json').write_text(json.dumps({'count':received[0]}))
 signal.signal(signal.SIGUSR1,handler)
 def worker():
  (root/'ready.json').write_text(json.dumps({'tid':threading.get_native_id()}))
  command=os.read(inputfd,4)
  if scenario=='exec':
   os.execve(sys.executable,[sys.executable,'-B',str(Path(__file__).resolve()),'--after-exec',str(lifefd),str(root)],dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
  (root/'read-completed.json').write_text(json.dumps({'bytes':len(command)}))
  os.read(lifefd,1)
 thread=threading.Thread(target=worker);thread.start()
 while thread.is_alive():thread.join(.01)
 return 0

def binding(pid):
 info=proc_identity(pid);exe=Path(f'/proc/{pid}/exe').resolve(strict=True)
 return {'pid':pid,'start_ticks':info['start_ticks'],'uid':info['uid'][0],'gid':info['gid'][0],'executable':str(exe),'sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}

def tg_signal(app,tid):
 require=LIBC.syscall(ctypes.c_long(234),ctypes.c_int(app.pid),ctypes.c_int(tid),ctypes.c_int(signal.SIGUSR1))
 if require!=0:raise OSError(ctypes.get_errno(),'fixture tgkill')
 end=time.monotonic()+.25
 while time.monotonic()<end:
  if proc_identity(app.pid,tid)['state']=='t':return
  time.sleep(.001)
 raise RuntimeError('Actual signal-delivery stop did not arrive')

def one(scenario):
 root=Path(tempfile.mkdtemp(prefix='trill-own-cleanup-fixture-'));os.chmod(root,0o700);os.chown(root,FIXTURE_UID,FIXTURE_GID)
 inputr,inputw=os.pipe();lifer,lifew=os.pipe();pid=os.fork()
 if pid==0:
  os.close(inputw);os.close(lifew);os.setgroups([]);os.setresgid(FIXTURE_GID,FIXTURE_GID,FIXTURE_GID);os.setresuid(FIXTURE_UID,FIXTURE_UID,FIXTURE_UID)
  os.set_inheritable(inputr,True);os.set_inheritable(lifer,True)
  os.execve(sys.executable,[sys.executable,'-B',str(Path(__file__).resolve()),'--child',scenario,str(inputr),str(lifer),str(root)],dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
 os.close(inputr);os.close(lifer)
 held=trace=None;result={'scenario':scenario,'injected_signal_count':0,'product_qualified':False}
 try:
  wait_file(root/'ready.json');tid=json.loads((root/'ready.json').read_text())['tid'];held=HeldProcess(binding(pid))
  end=time.monotonic()+2;snapshot=None
  while time.monotonic()<end:
   snapshot=idle_snapshot(held,tid)
   if snapshot:break
   time.sleep(.002)
  if snapshot is None:raise RuntimeError('Own worker never idle read4')
  birth=proc_identity(pid,tid)['start_ticks'];trace=TraceThread(held,tid,snapshot,birth)
  if scenario=='attach-signal':
   original=trace.ptrace
   def wrapped(request,*args,**kwargs):
    value=original(request,*args,**kwargs)
    if request==SEIZE:
     tg_signal(held,tid);result['injected_signal_count']+=1
    return value
   trace.ptrace=wrapped
   try:
    trace.attach(time.monotonic()+2)
    trace.resume()
    trace.wait(time.monotonic()+2)
   except (Refused,OSError) as error:result['observed_refusal']=str(error)
   trace.close()
   wait_file(root/'signals.json');result['delivered_signal_count']=json.loads((root/'signals.json').read_text())['count']
   os.write(inputw,b'done');wait_file(root/'read-completed.json')
  else:
   trace.attach(time.monotonic()+2);trace.resume()
   if scenario=='exec':
    os.write(inputw,b'exec')
    try:
     end=time.monotonic()+3
     while time.monotonic()<end:
      trace.wait(end);trace.resume(trace.deliver)
    except Refused as error:result['observed_refusal']=str(error)
    trace.close();wait_file(root/'after-exec.json')
    result['after_exec']=json.loads((root/'after-exec.json').read_text())
    result['migration_proven']=any(event.get('from_tid')==tid and event.get('to_tid')==pid for event in trace.events)
   elif scenario=='cleanup-signal':
    original=trace.ptrace
    def wrapped(request,*args,**kwargs):
     if request==INTERRUPT:
      tg_signal(held,tid);result['injected_signal_count']+=1
     return original(request,*args,**kwargs)
    trace.ptrace=wrapped
    trace.close();wait_file(root/'signals.json')
    result['delivered_signal_count']=json.loads((root/'signals.json').read_text())['count']
    os.write(inputw,b'done');wait_file(root/'read-completed.json')
   elif scenario=='cancel-idle-wait':
    flag=threading.Event();timer=threading.Timer(.02,flag.set);timer.start();start=time.monotonic()
    try:
     while time.monotonic()<start+2:
      trace.wait(start+2,cancelled=flag.is_set);trace.resume(trace.deliver)
    except Refused as error:result['observed_refusal']=str(error)
    result['cancellation_seconds']=time.monotonic()-start;timer.join();trace.close()
    os.write(inputw,b'done');wait_file(root/'read-completed.json')
  identity=proc_identity(pid);result.update(app_tracer_after=identity['tracer'],app_state_after=identity['state'],original_tid=tid,app_pid=pid,trace_events=trace.events,trace_attached=trace.attached,trace_stopped=trace.stopped,cleanup_failed=trace.cleanup_failed)
  ok=not trace.attached and not trace.stopped and not trace.cleanup_failed and identity['tracer']==0 and identity['state'] not in ('Z','X')
  if scenario=='exec':ok=ok and result.get('migration_proven') and result['after_exec']['pid']==pid
  if scenario in ('attach-signal','cleanup-signal'):ok=ok and result['injected_signal_count']==result.get('delivered_signal_count')==1
  if scenario=='cancel-idle-wait':ok=ok and result.get('observed_refusal')=='controller_cancelled' and result['cancellation_seconds']<.5
  result['passed_before_reap']=bool(ok)
 except BaseException as e:result.update(passed_before_reap=False,error=repr(e))
 finally:
  if trace is not None and trace.attached:trace.close()
  os.close(inputw);os.close(lifew)
  if held is not None:held.close()
  got,status=os.waitpid(pid,0);result.update(reaped_pid=got,wait_status=status,passed=result.get('passed_before_reap',False) and status==0)
  shutil.rmtree(root)
 return result

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
 if len(sys.argv)>1 and sys.argv[1]=='--child':raise SystemExit(child(sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),sys.argv[5]))
 if len(sys.argv)>1 and sys.argv[1]=='--after-exec':
  Path(sys.argv[3],'after-exec.json').write_text(json.dumps({'pid':os.getpid(),'uid':os.getuid()}));os.read(int(sys.argv[2]),1);raise SystemExit(0)
 options=fixture_options();FIXTURE_UID,FIXTURE_GID=options.fixture_uid,options.fixture_gid
 if os.getuid()!=0 or os.geteuid()!=0:raise SystemExit('Actual UID/EUID zero required; no mocked UID')
 import subprocess
 git_env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')};git_env['GIT_NO_REPLACE_OBJECTS']='1'
 TOOL_COMMIT=subprocess.check_output(['git','-c','safe.directory='+str(BASE),'-C',str(BASE),'rev-parse','HEAD'],env=git_env,text=True).strip()
 HEPTA_COMMIT=json.loads((SOURCE/'HEPTA_SHARED_PRESENTER.json').read_text())['commit']
 out=options.output;out.mkdir(mode=0o700)
 before=source_snapshot()
 r={'scope':'Actual UID0 own fork/exec Python nonleader/signal/cancellation fixture only; no product Root, Notes, model or device','uid':os.getuid(),'cases':[],'product_qualified':False,'tool_commit':TOOL_COMMIT,'selected_hepta_commit':HEPTA_COMMIT}
 for scenario in ['exec','attach-signal','cleanup-signal','cancel-idle-wait']:
  r['cases'].append(one(scenario));(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 r['source_before']=before;r['source_after']=source_snapshot();r['source_unchanged']=r['source_before']==r['source_after']
 r['passed']=len(r['cases'])==4 and all(c['passed'] for c in r['cases']) and r['source_unchanged'];(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True);raise SystemExit(0 if r['passed'] else 1)
