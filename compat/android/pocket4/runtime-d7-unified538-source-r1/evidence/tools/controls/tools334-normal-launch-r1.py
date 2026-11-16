import os,json,hashlib,subprocess,select
from pathlib import Path
R=Path('/data/pocket4-runtime-d7-unified538-20261113-e2a3-r1')
os.umask(0o077)
assert os.getuid()==1000 and {8,9}.issubset(os.sched_getaffinity(0))
for name,digest in [('tools334-normal-worker-r1.py','c3904dad7236043ac9b0ca05de5588661ab25ecb13836064e72447e3a404b50c'),('tools334-catalog.json','f0cef31c0597ddb9c1f0f42361b8b7014df76a4284412a744136e02e71e02abb'),('tools334-test-terminal.py','5839760e1804f5d4c8f345da8b71b9fc2d48a02e6efd9205535ed3f36787a69b')]:
 assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest
unit='p4-runtime-d7-tools334-normal-e2a3-r1.service'
cgroup=Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice')/unit
assert not cgroup.exists() and not (R/'tools-normal334-r1').exists()
argv=['/usr/bin/systemd-run','--user','--wait','--collect','--pipe','--unit='+unit,'--property=MemoryMax=4G','--property=MemorySwapMax=0','--property=CPUQuota=200%','--property=CPUAffinity=8 9','--property=TasksMax=128','--property=RuntimeMaxSec=2400','--property=TimeoutStopSec=5','--property=KillMode=control-group','--property=NoNewPrivileges=yes','--property=Nice=10','--property=UMask=0077','/usr/bin/python3','-B',str(R/'tools334-normal-worker-r1.py')]
p=subprocess.Popen(argv);fd=os.pidfd_open(p.pid)
code=p.wait();poll=select.poll();poll.register(fd,select.POLLIN);retired=bool(poll.poll(0));os.close(fd);assert retired
s=subprocess.run(['/usr/bin/systemctl','--user','show',unit,'-p','LoadState','-p','ActiveState','-p','MainPID','-p','ControlGroup'],capture_output=True,text=True)
r={'state':'D7_TOOLS334_NORMAL_UNIT_RETIRED','reader_pid':os.getpid(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'exit_code':code,'systemd_run_pid':p.pid,'original_pidfd_retired':retired,'cgroup_absent':not cgroup.exists(),'unit_show':s.stdout,'runtime_qualified':False,'production_ready':False}
q=R/'TOOLS334-NORMAL-r1-RETIREMENT.json'
with q.open('x') as f:json.dump(r,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
print(json.dumps(r),flush=True)
raise SystemExit(code)

