import os,json,hashlib,subprocess,select
from pathlib import Path
R=Path('/data/pocket4-runtime-d7-unified538-20261113-e2a3-r1')
os.umask(0o077)
assert os.getuid()==1000 and {8,9}.issubset(os.sched_getaffinity(0))
assert hashlib.sha256((R/'tools334-dma-worker-r1.py').read_bytes()).hexdigest()=='b35050fbfafb1dd83a30463b9013c8e68cd8fdf600274771f63aff561ef0922d'
unit='p4-runtime-d7-tools334-dma-layout-e2a3-r1.service'
cg=Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice')/unit
assert not cg.exists() and not (R/'tools-dma334-r1').exists()
argv=['/usr/bin/systemd-run','--user','--wait','--collect','--pipe','--unit='+unit,'--property=MemoryMax=4G','--property=MemorySwapMax=0','--property=CPUQuota=200%','--property=CPUAffinity=8 9','--property=TasksMax=64','--property=RuntimeMaxSec=600','--property=TimeoutStopSec=5','--property=KillMode=control-group','--property=NoNewPrivileges=yes','--property=Nice=10','--property=UMask=0077','/usr/bin/python3','-I','-B',str(R/'tools334-dma-worker-r1.py')]
p=subprocess.Popen(argv);fd=os.pidfd_open(p.pid);code=p.wait();poll=select.poll();poll.register(fd,select.POLLIN);retired=bool(poll.poll(0));os.close(fd);assert retired
q=subprocess.run(['/usr/bin/systemctl','--user','show',unit,'-p','LoadState','-p','ActiveState','-p','MainPID','-p','ControlGroup'],capture_output=True,text=True)
r={'state':'D7_TOOLS334_DMA_UNIT_RETIRED','reader_pid':os.getpid(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'exit_code':code,'systemd_run_pid':p.pid,'original_pidfd_retired':retired,'cgroup_absent':not cg.exists(),'unit_show':q.stdout,'Android_builds':0,'runtime_qualified':False,'production_ready':False}
with (R/'TOOLS334-DMA-RETIREMENT.json').open('x') as f:json.dump(r,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
print(json.dumps(r),flush=True)
raise SystemExit(code)
