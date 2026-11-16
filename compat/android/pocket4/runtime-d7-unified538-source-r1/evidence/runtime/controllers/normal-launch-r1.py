import os, json, hashlib, subprocess, select
from pathlib import Path

R = Path('/data/pocket4-runtime-d7-unified538-20261113-e2a3-r1')
worker = Path('/home/qian-qi/work/p4-runtime-d7-normal-worker-e2a3-r1.py')
os.umask(0o077)
assert os.getuid() == 1000 and {8, 9}.issubset(os.sched_getaffinity(0))
os.sched_setaffinity(0, {8, 9})
assert hashlib.sha256(worker.read_bytes()).hexdigest() == 'cba15eb1e2a7b0e18d7708c88c40c531bd3df24d306744b8be4fc3b95e0c0134'
unit = 'p4-runtime-d7-unified538-normal-e2a3-r1.service'
cgroup = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice') / unit
assert not cgroup.exists() and not R.exists()
argv = ['/usr/bin/systemd-run', '--user', '--wait', '--collect', '--pipe', '--unit=' + unit,
        '--property=MemoryMax=4G', '--property=MemorySwapMax=0', '--property=CPUQuota=200%',
        '--property=CPUAffinity=8 9', '--property=TasksMax=128', '--property=RuntimeMaxSec=3600',
        '--property=TimeoutStopSec=5', '--property=KillMode=control-group', '--property=NoNewPrivileges=yes',
        '--property=Nice=10', '--property=UMask=0077', '/usr/bin/python3', '-B', str(worker)]
child = subprocess.Popen(argv)
fd = os.pidfd_open(child.pid)
code = child.wait()
poll = select.poll(); poll.register(fd, select.POLLIN)
retired = bool(poll.poll(0)); os.close(fd); assert retired
show = subprocess.run(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'LoadState',
                       '-p', 'ActiveState', '-p', 'MainPID', '-p', 'ControlGroup'], capture_output=True, text=True)
result = {'schema': 'runtime-d7-normal-owned-unit-retirement-v1', 'exit_code': code,
          'systemd_run_pid': child.pid, 'original_pidfd_retired': retired,
          'cgroup_absent': not cgroup.exists(), 'unit_show': show.stdout,
          'runtime_qualified': False, 'production_ready': False}
out = R / 'NORMAL-r1-RETIREMENT.json'
with out.open('x') as f:
    json.dump(result, f, sort_keys=True, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
print(json.dumps(result), flush=True)
raise SystemExit(code)
