#!/usr/bin/python3
"""One ordinary-qq, bounded, read-only full-r3 binding job. No compiler or VM.

This is an independent SOURCE-READY runner, not an unhold of the VM package.
Root reviews/stages it and the exact 729-byte original durable response first.
Only the worker's verified library call may write HELD-BINDING.json.
"""
from pathlib import Path
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import select
import signal
import stat
import subprocess
import sys
import time

ROOT = Path('/home/qq/work/p4-native-exit-vm260-binding-evidence-11ea-20261119-r3')
INPUT = ROOT / 'inputs'
CONTROL = ROOT / 'control'
SELF = INPUT / 'run_binding.py'
BINDER = INPUT / 'bind_full.py'
KNOWN = INPUT / 'KNOWN-INPUTS.json'
CAPTURE = ROOT / 'full-durable-terminal.json'
OUTPUT = ROOT / 'HELD-BINDING.json'
UNIT = 'p4-kernel-native-exit-vm260-binding-11ea-20261119-r3.service'
CGROUP_PARENT = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice')
CGROUP = CGROUP_PARENT / UNIT
ORIGINAL = Path('/home/qq/work/p4-kernel-6.18.64-cp3a-20261118-r1')
BINDER_BYTES = 45685
BINDER_SHA = '45b7b7946f7935d2c7355303fc40d45b0bc80d7f28ff22182d815d62fc5e4f80'
KNOWN_BYTES = 15046
KNOWN_SHA = 'de0d4ab915bf6691283e4f0eb8090387cc446330ae9a385ff55339d5d17129b8'
STATUS_BYTES = 729
STATUS_SHA = 'f7daec1be6bdebd7f2c72aaaf385b8a8503474fde07403b5ff5194e5a04ac857'
BUILD_SERIAL = [66306,72394674,33152,1000,1000,1,0,1795009302688014291,1795009302688014291]
LIMIT = 64 * 1024**2
GIB = 1024**3
FIELDS = ('LoadState','ActiveState','SubState','MainPID','ControlGroup','InvocationID')
RETIRED = {'LoadState':'not-found','ActiveState':'inactive','SubState':'dead',
           'MainPID':'0','ControlGroup':'','InvocationID':''}
ENV = {}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def f9(st):
    return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,
            st.st_size,st.st_mtime_ns,st.st_ctime_ns]


def read_pin(path):
    path = Path(path)
    need(path.resolve() == path and path.name != 'signing_key.pem', 'canonical public input')
    before = f9(path.lstat())
    need(stat.S_ISREG(before[2]) and before[5] == 1 and 0 <= before[6] <= LIMIT,
         'bounded single-link input')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        need(f9(os.fstat(fd)) == before, 'input descriptor identity')
        chunks = []; count = 0
        while True:
            block = os.read(fd, 1024**2)
            if not block:
                break
            chunks.append(block); count += len(block)
            need(count <= before[6], 'input grew')
        need(count == before[6] and f9(os.fstat(fd)) == before, 'input descriptor bookend')
    finally:
        os.close(fd)
    need(f9(path.lstat()) == before, 'named input bookend')
    body = b''.join(chunks)
    return {'path':str(path),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),
            'identity':before}, body


def pin(path):
    return read_pin(path)[0]


def write_once(path, value):
    body = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    need(len(body) <= LIMIT, 'bounded public receipt')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        pending = memoryview(body)
        while pending:
            count = os.write(fd, pending)
            need(count > 0, 'receipt write failed'); pending = pending[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return pin(path)


def source_inputs(expected_self):
    need(os.getuid() == os.geteuid() == 1000, 'ordinary qq only')
    need(re.fullmatch('[0-9a-f]{64}', expected_self), 'fixed runner SHA required')
    for directory in (ROOT, INPUT):
        s = directory.lstat()
        need(directory.resolve() == directory and stat.S_ISDIR(s.st_mode)
             and s.st_uid == 1000 and stat.S_IMODE(s.st_mode) == 0o700,
             'private ordinary-qq input directory')
    need(Path(__file__).resolve() == SELF, 'exact isolated runner path')
    need({p.name for p in INPUT.iterdir()} == {'run_binding.py','bind_full.py','KNOWN-INPUTS.json'},
         'exact three staged source members; no transport mutexes')
    rows = [pin(p) for p in (SELF,BINDER,KNOWN,CAPTURE)]
    need(rows[0]['sha256'] == expected_self, 'reviewed runner bytes')
    need((rows[1]['bytes'],rows[1]['sha256']) == (BINDER_BYTES,BINDER_SHA), 'reviewed binder bytes')
    need((rows[2]['bytes'],rows[2]['sha256']) == (KNOWN_BYTES,KNOWN_SHA), 'reviewed known inputs')
    need((rows[3]['bytes'],rows[3]['sha256']) == (STATUS_BYTES,STATUS_SHA), 'exact original 729-byte tool response')
    need(all(r['identity'][3] == 1000 and not r['identity'][2] & 0o022 for r in rows),
         'ordinary owned private source/capture files')
    return rows


def bookend(rows):
    need([pin(r['path']) for r in rows] == rows, 'complete runner/binder/known/capture bookend')


def resources(admission=False):
    available = next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()
                     if x.startswith('MemAvailable:'))
    fs = os.statvfs(ROOT); disk = fs.f_bavail * fs.f_frsize
    need(available >= (15 if admission else 12)*GIB, 'original VM memory reserve')
    need(disk >= 32*GIB, 'original VM disk floor')
    return {'observed_ns':time.time_ns(),'memory_available':available,'disk_free':disk,
            'minimum_memory_GiB':15 if admission else 12,'minimum_disk_GiB':32}


def bus_environment():
    runtime = Path('/run/user/1000'); s = runtime.lstat(); b = (runtime/'bus').lstat()
    need(stat.S_ISDIR(s.st_mode) and s.st_uid == 1000 and stat.S_IMODE(s.st_mode) == 0o700,
         'original ordinary user runtime')
    need(stat.S_ISSOCK(b.st_mode) and b.st_uid == 1000, 'original ordinary user bus')
    return {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','HOME':'/home/qq','USER':'qq','LOGNAME':'qq',
            'LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1','XDG_RUNTIME_DIR':str(runtime),
            'DBUS_SESSION_BUS_ADDRESS':'unix:path='+str(runtime/'bus')}


def status(unit):
    need(re.fullmatch(r'p4-[a-z0-9-]+\.service',unit), 'fixed user service name')
    result = subprocess.run(['/usr/bin/systemctl','--user','show',unit,'--property='+','.join(FIELDS)],
                            env=ENV, stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
    need(result.returncode == 0 and len(result.stdout)+len(result.stderr) <= 16384,
         'bounded actual unit observation')
    return dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)


def retired(unit):
    fields = status(unit)
    need(fields == RETIRED and not os.path.lexists(CGROUP_PARENT/unit), 'unit/cgroup not retired: '+unit)
    return {'unit':unit,'fields':fields,'cgroup_absent':True}


def wait_retired(unit):
    until = time.monotonic()+20
    while True:
        try:
            return retired(unit)
        except RuntimeError:
            if time.monotonic() >= until:
                raise
            time.sleep(0.1)


def serial_probe():
    handles = []; result = {}
    try:
        for path, inode in [(ORIGINAL/'control/build.serial.lock',72394674),
                            (ORIGINAL/'control/vm.serial.lock',72404993)]:
            need(path.resolve() == path, 'original serial path')
            fd = os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC); handles.append(fd)
            s = f9(os.fstat(fd))
            need(stat.S_ISREG(s[2]) and s[:2] == [66306,inode] and s[3:7] == [1000,1000,1,0],
                 'original serial inode/owner/link/size')
            if inode == 72394674:
                need(s == BUILD_SERIAL, 'original full build-serial F9')
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            need(s == f9(path.lstat()), 'serial descriptor/named identity')
            result[str(path)] = s
        for path, row in result.items():
            need(f9(Path(path).lstat()) == row, 'serial named bookend')
        return result
    finally:
        for fd in reversed(handles):
            os.close(fd)


def stop_observed_invocation(invocation):
    fields = status(UNIT)
    if fields == RETIRED:
        return {'already_retired':True}
    need(re.fullmatch('[0-9a-f]{32}',invocation or '')
         and fields['InvocationID'] == invocation, 'refuse to stop unobserved/different invocation')
    result = subprocess.run(['/usr/bin/systemctl','--user','stop',UNIT], env=ENV,
                            stdin=subprocess.DEVNULL,capture_output=True,timeout=30)
    need(len(result.stdout)+len(result.stderr) <= 16384, 'bounded own-invocation retirement')
    return {'exit':result.returncode,'invocation_id':invocation,
            'stdout':result.stdout.decode(errors='replace'),'stderr':result.stderr.decode(errors='replace')}


def worker(expected_self, expected_capture_f9):
    rows = source_inputs(expected_self)
    need(rows[3]['identity'] == expected_capture_f9, 'same actually observed capture F9')
    report = {'schema':'p4-vm260-full-binding-worker-11ea-v1','state':'RUNNING','started_ns':time.time_ns(),
              'inputs_before':rows,'compiler_invocations':0,'VM_invocations':0,
              'native_exit_abi_qualified':False,'production_android_runtime_qualified':False}
    try:
        cgline = Path('/proc/self/cgroup').read_text().strip()
        need(cgline == '0::/'+str(CGROUP.relative_to('/sys/fs/cgroup')), 'exact normal binder cgroup')
        limits = {k:(CGROUP/k).read_text().strip() for k in
                  ('memory.max','memory.high','memory.swap.max','cpu.max','pids.max')}
        need(limits == {'memory.max':str(3*GIB),'memory.high':str(5*GIB//2),
             'memory.swap.max':'0','cpu.max':'200000 100000','pids.max':'128'}
             and sorted(os.sched_getaffinity(0)) == [22,23], 'original VM resource contract')
        report['resource_admission'] = resources(True)
        invocation = os.environ.get('INVOCATION_ID','')
        need(re.fullmatch('[0-9a-f]{32}',invocation), 'actual systemd invocation identity')
        report['invocation_id'] = invocation
        report['admission'] = {'pid':os.getpid(),'cgroup':cgline,'limits':limits,'affinity':[22,23],
                               'original_capture_F9':expected_capture_f9}
        write_once(CONTROL/'WORKER-STARTED.json',report)
        # Publish readiness only after the complete started receipt is closed
        # and whole-body/F9 checked. The manager never parses a partial write.
        ready = os.open(CONTROL/'WORKER-STARTED.complete',
                        os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        os.close(ready)
        spec = importlib.util.spec_from_file_location('p4_reviewed_full_binding',BINDER)
        binder = importlib.util.module_from_spec(spec);spec.loader.exec_module(binder)
        bookend(rows)
        began = time.monotonic()
        record = binder.bind_completed_full(binder.ACTUAL_FULL_PIN,binder.ACTUAL_TERMINAL_PIN,rows[3],OUTPUT)
        report['actual_binding_seconds'] = time.monotonic()-began
        output, body = read_pin(OUTPUT)
        need(json.loads(body) == record and record['state'] == binder.BOUND_HELD
             and record['actual_full_evidence_verified'] is True
             and record['binding_time_serials_released'] is True
             and record['VM_executed'] is False and record['launch_assessment_performed'] is False,
             'actual complete binding remains HELD')
        report['binding'] = output
        report['binding_serials'] = record['binding_time_original_serials']
        report['binding_whole_file_reads'] = record['whole_file_reads']
        report['binding_body_bytes_read'] = record['body_bytes_read']
        bookend(rows)
        report['inputs_after'] = [pin(r['path']) for r in rows]
        report['input_bookends_unchanged'] = report['inputs_after'] == rows
        report['resource_final'] = resources()
        report['cgroup_final'] = {k:(CGROUP/k).read_text().strip() for k in
                                 ('memory.peak','memory.events','memory.swap.current','cpu.stat','pids.peak')}
        events = dict(line.split() for line in report['cgroup_final']['memory.events'].splitlines())
        need(int(events['oom']) == int(events['oom_kill']) == 0
             and report['cgroup_final']['memory.swap.current'] == '0', 'actual resource result')
        report['state'] = 'PASS'
        report['finished_ns'] = time.time_ns()
        receipt = write_once(CONTROL/'BINDING-RESULT.json',report)
        print(json.dumps({'state':'PASS','receipt':receipt,'binding':output,'VM_executed':False},sort_keys=True),flush=True)
        return 0
    except BaseException as exc:
        report.update(state='FAILED',error=repr(exc),finished_ns=time.time_ns())
        if not os.path.lexists(CONTROL/'BINDING-RESULT.json'):
            write_once(CONTROL/'BINDING-RESULT.json',report)
        raise


def manager(expected_self):
    global ENV
    rows = source_inputs(expected_self)
    need({p.name for p in ROOT.iterdir()} == {'inputs','full-durable-terminal.json'}, 'fresh exact binding root')
    ENV = bus_environment()
    units = [UNIT,'p4-kernel-native-exit-full-11ea-20261119-r3.service',
             'p4-kernel-native-exit-tu-11ea-20261119-r3.service',
             'p4-kernel-native-exit-vm260-prepare-11ea-20261119-r3.service',
             'p4-kernel-native-exit-vm260-run-11ea-20261119-r3.service',
             'p4-kernel61864-vm-run-20261118-r5.service',
             'p4-cp3a-vendor-20261118-162b-r10.service',
             'p4-cp3a-vendor-20261118-162b-r10-outer.service',
             'p4-cp3a-vendor-20261119-162b-r11.service',
             'p4-cp3a-vendor-supervisor-20261119-162b-r11.service',
             'p4-cp3a-vendor-20261119-162b-r11-recovery.service',
             'p4-cp3a-vendor-supervisor-20261119-162b-r12.service',
             'p4-cp3a-vendor-20261119-162b-r12.service',
             'p4-cp3a-vendor-20261119-162b-r12-recovery.service']
    report = {'schema':'p4-vm260-full-binding-terminal-11ea-v1','passed':False,'started_ns':time.time_ns(),
              'inputs_before':rows,'preflight_units':[retired(u) for u in units],
              'resource_admission':resources(True),'serials_before':serial_probe(),
              'compiler_invocations':0,'VM_invocations':0,'native_exit_abi_qualified':False,
              'production_android_runtime_qualified':False}
    CONTROL.mkdir(mode=0o700,exist_ok=False)
    argv = ['/usr/bin/systemd-run','--user','--unit='+UNIT,'--wait','--collect','--pipe',
            '--service-type=exec','--property=MemoryMax=3221225472','--property=MemoryHigh=2684354560',
            '--property=MemorySwapMax=0','--property=CPUAffinity=22 23','--property=CPUQuota=200%',
            '--property=TasksMax=128','--property=RuntimeMaxSec=900','--property=TimeoutStopSec=10',
            '--property=KillMode=control-group','--property=Nice=10','--property=UMask=0077',
            '--property=WorkingDirectory='+str(ROOT),'/usr/bin/python3','-I','-B',str(SELF),
            'worker',expected_self,','.join(map(str,rows[3]['identity']))]
    report['argv'] = argv
    write_once(CONTROL/'LAUNCH.json',report)
    child = None; pidfd = None; failure = None; invocation = None
    stdout_path = CONTROL/'worker.stdout'; stderr_path = CONTROL/'worker.stderr'
    until = time.monotonic()+960
    try:
        with stdout_path.open('xb',buffering=0) as stdout, stderr_path.open('xb',buffering=0) as stderr:
            child = subprocess.Popen(argv,cwd=ROOT,env=ENV,stdin=subprocess.DEVNULL,
                                     stdout=stdout,stderr=stderr,close_fds=True,start_new_session=True)
            pidfd = os.pidfd_open(child.pid)
            report['systemd_run_pid'] = child.pid
            report['systemd_run_pidfd_identity'] = f9(os.fstat(pidfd))
            poll = select.poll();poll.register(pidfd,select.POLLIN)
            while not poll.poll(1000):
                need(time.monotonic() < until, 'fixed original manager deadline')
                need(stdout_path.stat().st_size+stderr_path.stat().st_size <= LIMIT, 'bounded raw logs')
                report['resources_latest'] = resources()
                if invocation is None and (CONTROL/'WORKER-STARTED.complete').exists():
                    ready_pin = pin(CONTROL/'WORKER-STARTED.complete')
                    need(ready_pin['bytes'] == 0 and ready_pin['identity'][3] == 1000,
                         'closed started-receipt marker')
                    start_pin, body = read_pin(CONTROL/'WORKER-STARTED.json'); start = json.loads(body)
                    current = status(UNIT)
                    need(start['inputs_before'] == rows and start['admission']['cgroup'] == '0::/'+str(CGROUP.relative_to('/sys/fs/cgroup')),
                         'actual started worker/source identity')
                    need(current['InvocationID'] == start['invocation_id']
                         and current['MainPID'] == str(start['admission']['pid']), 'actual worker invocation/PID')
                    invocation = start['invocation_id'];report['observed_invocation_id'] = invocation
                    report['worker_started'] = start_pin
                    report['worker_started_complete'] = ready_pin
            observed = os.waitid(os.P_PIDFD,pidfd,os.WEXITED|os.WNOWAIT)
            need(observed.si_pid == child.pid, 'original Popen PIDFD identity')
            report['waitid'] = {'pid':observed.si_pid,'code':observed.si_code,'status':observed.si_status}
            rc = child.wait(timeout=10)
            need(rc == (observed.si_status if observed.si_code == os.CLD_EXITED else -observed.si_status), 'actual wait result')
            report['systemd_run_exit'] = rc;report['systemd_run_actual_reaped'] = True
    except BaseException as exc:
        failure = repr(exc)
    finally:
        if failure is not None or (child is not None and child.returncode is None):
            try:
                report['stop_observed_invocation'] = stop_observed_invocation(invocation)
            except BaseException as exc:
                report['stop_refused_or_failed'] = repr(exc)
                failure = failure or repr(exc)
        try:
            if child is not None and child.returncode is None:
                if pidfd is not None:
                    try:signal.pidfd_send_signal(pidfd,signal.SIGKILL)
                    except ProcessLookupError:pass
                else:
                    child.kill()  # Original unreaped Popen only; never signal a reaped PID/group.
                report['systemd_run_exit_after_error'] = child.wait(timeout=10)
                report['systemd_run_actual_reaped'] = True
        finally:
            if pidfd is not None:os.close(pidfd)
    try:
        report['unit_retirement'] = wait_retired(UNIT)
        report['serials_after'] = serial_probe()
        need(report['serials_after'] == report['serials_before'], 'original serial F9 and actual reacquisition')
        report['original_serials_reacquired'] = True
        report['stdout'] = pin(stdout_path);report['stderr'] = pin(stderr_path)
        result_pin, body = read_pin(CONTROL/'BINDING-RESULT.json'); result = json.loads(body)
        need(failure is None and report['systemd_run_exit'] == 0
             and report['systemd_run_actual_reaped'] is True
             and result['state'] == 'PASS' and result['input_bookends_unchanged'] is True
             and result['inputs_before'] == result['inputs_after'] == rows,
             'actual worker success and complete source/capture bookends')
        need(result['binding_serials'] == report['serials_before'], 'same two original held serials')
        need(pin(OUTPUT) == result['binding'], 'same complete HELD binding output')
        need(result['compiler_invocations'] == result['VM_invocations'] == 0
             and result['native_exit_abi_qualified'] is False
             and result['production_android_runtime_qualified'] is False, 'no compile or runtime credit')
        bookend(rows)
        report['inputs_after'] = [pin(r['path']) for r in rows]
        report['input_bookends_unchanged'] = report['inputs_after'] == rows
        report['worker_result'] = result_pin;report['binding'] = result['binding']
        report['actual_binding_seconds'] = result['actual_binding_seconds']
        report['passed'] = True
    except BaseException as exc:
        failure = failure or repr(exc)
    if failure is not None:report['error'] = failure
    report['finished_ns'] = time.time_ns()
    terminal = write_once(CONTROL/'BINDING-TERMINAL.json',report)
    print(json.dumps({'terminal':terminal,'passed':report['passed'],'VM_executed':False},sort_keys=True),flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    os.umask(0o077)
    need(len(sys.argv) in (3,4), 'explicit reviewed mode and source pin')
    if sys.argv[1] == 'manager':
        need(len(sys.argv) == 3, 'manager arguments')
        sys.exit(manager(sys.argv[2]))
    need(sys.argv[1] == 'worker' and len(sys.argv) == 4
         and re.fullmatch(r'[0-9]+(?:,[0-9]+){8}',sys.argv[3]), 'worker exact actual F9 arguments')
    sys.exit(worker(sys.argv[2],[int(x) for x in sys.argv[3].split(',')]))
