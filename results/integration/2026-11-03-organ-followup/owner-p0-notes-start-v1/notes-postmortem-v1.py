import hashlib,json,os,stat,subprocess,time
from pathlib import Path
assert os.getuid()==0
prefix=Path('/var/lib/trill/o1103n1');out=Path('/data/trill-organ-owner-20261103/root-fd-v5-tests-package-01/notes-live-fd-a39-v1/postmortem-v1.json')
assert not out.exists()
result={'scope':'Read-only observations of this failed fresh deployment; no authority reopen, state repair, process adoption or signal',
        'observed_unix_ms':int(time.time()*1000),'root_pid_exists':Path('/proc/2017019').exists(),'files':{}}
admin=prefix/'admin'
result['admin_entries']=[{'name':p.name,'mode':oct(stat.S_IMODE(p.lstat().st_mode)),'bytes':p.lstat().st_size} for p in sorted(admin.iterdir())]
for name in ('seed.stdout','seed.stderr','original-thread-seed.json','session.stdout','session.stderr','actual-composition.json','actual-human-provider-receipt.json','actual-artifacts.json'):
 p=admin/name
 if not p.exists():result['files'][name]={'exists':False};continue
 s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=65536
 raw=p.read_bytes();result['files'][name]={'exists':True,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'text':raw.decode()}
result['authority_state_directory_exists']=(prefix/'a/state').exists()
result['session_socket_exists']=Path('/run/user/1000/trillionnium-ui/session.sock').exists()
result['observer_namespace']=os.readlink('/proc/self/ns/mnt')
result['observer_namespace_prefix_mounts']=[line for line in Path('/proc/self/mountinfo').read_text().splitlines() if str(prefix) in line]
env={'PATH':'/usr/bin:/bin','XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'}
args=['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','/usr/bin/systemctl','--user','show','hepta-runtime-job-1a1a3519eb3-96a-766e.service','-p','ActiveState','-p','SubState','-p','MainPID','-p','ControlGroup','-p','ExecMainStatus']
try:
 r=subprocess.run(args,env=env,capture_output=True,text=True,timeout=8)
 result['original_job_unit']={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
 fields=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
 cg=fields.get('ControlGroup')
 if cg:
  p=Path('/sys/fs/cgroup')/cg.lstrip('/')/'cgroup.procs'
  result['original_cgroup_processes']=p.read_text() if p.exists() else None
except Exception as e:result['original_job_unit_error']=repr(e)
raw=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
os.chmod(out,0o644)
print(json.dumps({'path':str(out),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'result':result},ensure_ascii=False))
