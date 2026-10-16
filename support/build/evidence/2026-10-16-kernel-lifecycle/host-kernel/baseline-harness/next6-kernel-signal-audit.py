"""Exercise copied kernel.sh with TCP-lease host fixtures, never a VM."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time

repo = Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop')
output = Path('/workspace/scratch/ae1a8cf05419/next6-kernel-signal-audit')
output.mkdir(exist_ok=False)
fixture = output / 'fixture'
fixture.mkdir()
build = fixture / 'support/build'
kernel = fixture / 'kernel/asterinas/kernel'
tools = fixture / 'mock-bin'
vdso = fixture / 'vdso'
for path in (build/'minimal',kernel,tools,vdso):
    path.mkdir(parents=True,exist_ok=True)
for name in ('kernel.sh','check-boot.py'):
    shutil.copyfile(repo/'support/build'/name,build/name)
(build/'verify-source.py').write_text("print('{}')\n")
(build/'minimal/OSDK.toml').write_text('# owned host fixture manifest; not a project build\n')
(build/'minimal/Cargo.lock').write_text('# fixture lock\n')
(vdso/'vdso_x86_64.so').write_bytes(b'fixture vDSO')
(build/'minimal/prepare-initramfs.py').write_text('''import argparse
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--upstream');p.add_argument('--busybox');p.add_argument('--output');p.add_argument('--manifest')
a=p.parse_args();Path(a.output).write_bytes(b'fixture initramfs');Path(a.manifest).write_text('{}\\n')
''')
for name in ('cargo','rustc','rustup','gcc','qemu-system-x86_64','git'):
    tool=tools/name
    tool.write_text("#!/bin/sh\nprintf 'host fixture tool\\n'\n")
    tool.chmod(0o755)
child_code="""import json,os,signal,socket,time
from pathlib import Path
lease=socket.socket();lease.bind(('127.0.0.1',0));lease.listen(1)
signal.signal(signal.SIGTERM,signal.SIG_IGN)
Path('dummy-child.json').write_text(json.dumps({'pid':os.getpid(),'group':os.getpgrp(),'address':lease.getsockname()}))
time.sleep(60)
"""
make=tools/'make'
make.write_text('''#!/usr/bin/python3
import json,os,socket,subprocess,sys,time
from pathlib import Path
if '--version' in sys.argv: print('GNU Make host fixture');raise SystemExit(0)
root=Path(os.environ['MOCK_PROJECT']);os.chdir(root)
lease=socket.socket();lease.bind(('127.0.0.1',0));lease.listen(1)
child=subprocess.Popen([sys.executable,'-c',CHILD_CODE],pass_fds=(9,))
Path('dummy-make.json').write_text(json.dumps({'pid':os.getpid(),'group':os.getpgrp(),'child_pid':child.pid,'address':lease.getsockname(),'argv':sys.argv}))
time.sleep(60)
'''.replace('CHILD_CODE',repr(child_code)))
make.chmod(0o755)
env={key:value for key,value in os.environ.items()
     if not key.startswith(('A01_','CARGO_','RUSTUP_','MOCK_'))
     and key not in ('MAKEFLAGS','MFLAGS','VDSO_LIBRARY_DIR','INITRAMFS')}
env.update({'PATH':str(tools)+':/usr/bin:/bin','CARGO_HOME':str(fixture/'cargo-home'),
            'VDSO_LIBRARY_DIR':str(vdso),'MOCK_PROJECT':str(fixture),
            'A01_RUN_DIR':str(fixture/'evidence')})
command=['bash',str(build/'kernel.sh'),'kernel']
record={'kind':'copied_kernel_runner_signal_host_fixture_no_kernel_no_vm',
        'command':command,'selected_environment':{key:env[key] for key in ('PATH','CARGO_HOME','VDSO_LIBRARY_DIR','MOCK_PROJECT','A01_RUN_DIR')},
        'source_kernel_sh_sha256':hashlib.sha256((build/'kernel.sh').read_bytes()).hexdigest(),
        'original_source_sha256':hashlib.sha256((repo/'support/build/kernel.sh').read_bytes()).hexdigest(),
        'production_manifest_before':hashlib.sha256((repo/'kernel/asterinas/kernel/OSDK.toml').read_bytes()).hexdigest()}
descriptors={}
process=None

def wait_json(path):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        try:return json.loads(path.read_text())
        except (FileNotFoundError,json.JSONDecodeError):time.sleep(.01)
    raise RuntimeError('fixture did not become ready: '+str(path))

def exited(fd,timeout=0):
    return bool(select.select([fd],[],[],timeout)[0])

def busy(address):
    import socket
    with socket.socket() as probe:
        try:probe.bind(tuple(address));return False
        except OSError:return True

try:
    with (output/'runner.log').open('wb') as log:
        process=subprocess.Popen(command,env=env,cwd=fixture,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        descriptors['runner']=os.pidfd_open(process.pid)
        ready=wait_json(fixture/'dummy-make.json')
        child=wait_json(fixture/'dummy-child.json')
        descriptors['make']=os.pidfd_open(ready['pid'])
        descriptors['dummy_child']=os.pidfd_open(child['pid'])
        record.update({'leader_pid':process.pid,'make':ready,'dummy_child':child,
                       'manifest_present_before_signal':(kernel/'OSDK.toml').is_file(),
                       'all_pidfds_alive_before_signal':all(not exited(fd) for fd in descriptors.values())})
        if not all(not exited(fd) for fd in descriptors.values()):raise RuntimeError('fixture died before signal')
        if ready['group']!=process.pid or child['group']!=process.pid:raise RuntimeError('fixture escaped owned group')
        signal.pidfd_send_signal(descriptors['runner'],signal.SIGTERM)
        leader_exited=exited(descriptors['runner'],2)
        record['after_direct_runner_SIGTERM']={
            'runner_pidfd_exited':leader_exited,
            'make_pidfd_exited':exited(descriptors['make']),
            'dummy_child_pidfd_exited':exited(descriptors['dummy_child']),
            'manifest_present':(kernel/'OSDK.toml').exists(),
            'make_TCP_lease_busy':busy(ready['address']),
            'dummy_child_TCP_lease_busy':busy(child['address'])}
        with (build/'out-kernel.lock').open('a') as lock:
            try:
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                lock_busy=False
                fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
            except BlockingIOError:lock_busy=True
        record['after_direct_runner_SIGTERM']['workspace_lock_busy']=lock_busy
        record['owned_leader_waitid_WNOWAIT']=str(os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT))
        record['reproduced']=leader_exited and not exited(descriptors['make']) and not exited(descriptors['dummy_child']) and lock_busy
finally:
    if process is not None:
        # The direct session leader remains unreaped. Anchor group identity
        # before signaling only this disposable owned session.
        os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        time.sleep(.2)
        os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        record['runner_reaped_returncode']=process.wait(timeout=3)
        record['after_owned_group_cleanup_pidfd_exited']={name:exited(fd,3) for name,fd in descriptors.items()}
    for descriptor in descriptors.values():os.close(descriptor)
    record['production_manifest_after']=hashlib.sha256((repo/'kernel/asterinas/kernel/OSDK.toml').read_bytes()).hexdigest()
    (output/'observation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
