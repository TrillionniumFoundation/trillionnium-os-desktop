"""Private host-only batch; exact frozen sources, unchanged bounded capture."""
import argparse,hashlib,json,os,resource,signal,stat,time,types
from pathlib import Path
COMMANDS={'path':'/home/alex/work/pocket4-android-final/qualification/business-support-frozen-resume-20261107-r9/business_commands.py',
'bytes':12813,'sha256':'cfe92077ebb75db4f7f0fd577fcd7e6d664afd9338128a05435512549ceeb1f3'}
LIFECYCLE={'path':'/home/alex/work/pocket4-android-final/framework/runtime_support/capture_lifecycle.py',
'bytes':25312,'sha256':'6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877'}
CASES=('queued-go-old','queued-go-new','adoptee-old','adoptee-new',
       'three-leader-channel','pipe-register-failure','missing-worker-terminal')
SIGNALS=[];RETIRING=False
class Cancelled(BaseException):pass
def cancel(n,f):
 SIGNALS.append(n)
 if not RETIRING:raise Cancelled('HOST_CONTROL_BATCH_CANCELLED')
def need(v,s):
 if not v:raise RuntimeError(s)
def identity(s):
 return {k:str(getattr(s,k)) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
def read(ref):
 p=Path(ref['path']);need(p.is_absolute() and p.resolve()==p and set(ref)=={'path','bytes','sha256'},'EXACT_SOURCE_REF')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==ref['bytes']<=262144,'SOURCE_SHAPE')
  b=os.pread(fd,ref['bytes']+1,0);need(len(b)==ref['bytes'] and hashlib.sha256(b).hexdigest()==ref['sha256'] and identity(before)==identity(os.fstat(fd))==identity(p.lstat()),'SOURCE_BYTES_CHANGED')
  return b,identity(before)
 finally:os.close(fd)
def load(ref,name):
 raw,_=read(ref);m=types.ModuleType(name);m.__file__=ref['path'];exec(compile(raw,m.__file__,'exec'),m.__dict__);return m

def main():
 global RETIRING
 p=argparse.ArgumentParser();p.add_argument('--inputs',required=True);p.add_argument('--expect-inputs-sha256',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 need(os.getuid()==os.geteuid()==0,'ROOT_PRIVATE_HOST_FIXTURE');os.umask(0o077);os.sched_setaffinity(0,{19});os.setpriority(os.PRIO_PROCESS,0,10);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 cgtext=Path('/proc/self/cgroup').read_text().splitlines();need(len(cgtext)==1 and cgtext[0].startswith('0::/') and 'hepta-runtime-job-' in cgtext[0],'PRIVATE_HOST_OWNER_CGROUP')
 cg=Path('/sys/fs/cgroup')/cgtext[0][3:].lstrip('/');need(str(os.getpid()) in (cg/'cgroup.procs').read_text().split(),'ACTUAL_OWNER_MEMBERSHIP')
 (cg/'memory.swap.max').write_text('0');(cg/'pids.max').write_text('64')
 limits={n:(cg/n).read_text().strip() for n in ('cpu.max','memory.max','memory.swap.max','pids.max')}
 need(limits=={'cpu.max':'50000 100000','memory.max':'536870912','memory.swap.max':'0','pids.max':'64'},'PRIVATE_HOST_LIMITS')
 raw=Path(a.inputs).read_bytes();need(hashlib.sha256(raw).hexdigest()==a.expect_inputs_sha256,'EXACT_BATCH_INPUT');inputs=json.loads(raw)
 need(inputs['schema']=='pocket4-camera-video-supervisor-host-input-v1' and inputs['cases']==list(CASES),'EXACT_SEVEN_REMAINING_RISK_CASES')
 need(read(inputs['controller'])[0]==Path(__file__).read_bytes(),'EXACT_CONTROLLER')
 refs=[inputs['controller'],inputs['worker'],inputs['source_map'],inputs['old_supervisor'],*inputs['sources'],COMMANDS,LIFECYCLE]
 before={r['path']:read(r)[1] for r in refs}
 def guard(**kw):
  need(all(read(r)[1]==before[r['path']] for r in refs),'FROZEN_BATCH_SOURCE_CHANGED');return {'actual_private_host_sources_verified':True,'Main_or_audio_authority':False}
 commands=load(COMMANDS,'camera_host_batch_commands');fixture=load(inputs['worker'],'camera_host_batch_fixture')
 capture=commands.load_capture();cold=fixture.fd_table();warm=capture.OwnChildReaper(protected_pids=(os.getpid(),os.getppid()));warm.flag();fds_before=fixture.fd_table()
 root=Path(a.output);need(root.parent==Path(a.inputs).parent and not root.exists(),'CREATE_ONLY_PRIVATE_BATCH_OUTPUT');root.mkdir(mode=0o700)
 logs=root/'commands';logs.mkdir(mode=0o700);results=[];error=None;unknown=False
 for n in (signal.SIGINT,signal.SIGTERM):signal.signal(n,cancel)
 try:
  for i,name in enumerate(CASES):
   out=root/name;argv=['/usr/bin/python3','-I','-B',inputs['worker']['path'],'--case',name,'--packet',inputs['packet'],
    '--source-map',inputs['source_map']['path'],'--output',str(out),'--lifecycle',LIFECYCLE['path'],
    '--old-supervisor',inputs['old_supervisor']['path'],'--expect-old-sha256',inputs['old_supervisor']['sha256']]
   r=commands.run_recorded('%02d-%s'%(i+1,name),argv,35,logs,guard,protected_pids=(os.getpid(),os.getppid()),check=False,output_bound=1048576)
   o=r.command_observation;l=o.get('lifecycle',{});sr=o.get('subreaper',{})
   retired=o.get('host_retirement_proved') is True and o.get('evidence_complete') is True and all(l.get(k) is True for k in ('owned_tree_cleanup_complete','all_acquired_fds_closed','retirement_within_deadline')) and l.get('remaining_owned_children')==[] and sr.get('restored') is True and sr.get('final_children_empty') is True
   unknown=not retired;row={'case':name,'command':o,'returncode':r.returncode,'host_retirement_proved':retired};results.append(row)
   need(retired and not r.host_timed_out and not r.recorder_errors,'ACTUAL_WORKER_RETIREMENT_UNKNOWN_OR_FAILED')
   b=(out/'result.json').read_bytes();v=json.loads(b);row['result']={'path':str(out/'result.json'),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};row['passed']=v.get('passed') is True
   need(r.returncode==0 and row['passed'] and not r.stderr,'ACTUAL_PRIVATE_HOST_CONTROL_FAILED')
  guard()
 except BaseException as e:error={'type':type(e).__name__,'message':str(e)}
 finally:RETIRING=True
 after={r['path']:read(r)[1] for r in refs};fds_after=fixture.fd_table();children=warm.children()
 signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM});pending=sorted(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
 passed=len(results)==len(CASES) and all(r.get('passed') for r in results) and not error and not unknown and not SIGNALS and not pending and before==after and fds_before==fds_after and children==[]
 value={'schema':'pocket4-camera-video-supervisor-host-batch-v1','state':'HOST_ONLY_SEVEN_REMAINING_RISK_CASES_PASSED' if passed else 'FAILED','passed':passed,
  'inputs':{'path':a.inputs,'bytes':len(raw),'sha256':a.expect_inputs_sha256},'cases':results,'error':error,'host_retirement_unknown':unknown,
  'signals':SIGNALS,'pending_at_commit':pending,'cold_FD_before_actual_libffi_initialization':cold,'FD_before':fds_before,'FD_after':fds_after,
  'remaining_children':children,'sources_before':before,'sources_after':after,'limits':limits,
  'resource_after':{n:(cg/n).read_text().strip() for n in ('memory.peak','memory.events','memory.swap.current')},
  'explicit_fixture_boundaries':['fresh Main/plan qualification','acoustic Python protocol backend','zero PCM correlation fixture'],
  'actual_audio_stream_actions':0,'Main_actions':0,'Android_UI_actions':0,'runtime_qualified':False,'whole_app_business_accepted':False}
 out=commands.write_new(root/'result.json',value);print(json.dumps({'passed':passed,'result':out,'host_retirement_unknown':unknown}));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
