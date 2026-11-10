#!/usr/bin/python3
"""Ordinary no-load compilation of one finite diskless guest control."""
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import time

B = Path('/home/alex/work/p4-context-provider-runtime-8764-r1')
C = B / 'control'
D = B / 'build-r5'
OLD = Path('/home/alex/work/pocket4-production-namespace-broker-20261109-8b88-r1/qualification')
TOOLS = OLD / 'selinux-storage-probe-normal-launch-r5/input-tools'
ORIGINAL = OLD / 'normal-selinux-storage-probe-r5'
assert os.getuid() == os.geteuid() == 1000 and sorted(os.sched_getaffinity(0)) == [20, 21]
os.umask(0o077)
D.mkdir(mode=0o700)
CG = Path('/sys/fs/cgroup' + Path('/proc/self/cgroup').read_text().strip().split('::', 1)[1])
R = {'schema': 'p4ctx1-scm-ordinary-runtime-build-v5', 'started_ns': time.time_ns(),
     'commands': [], 'errors': [], 'host_policy_loads': 0, 'host_module_loads': 0,
     'guest_runs': 0, 'Android_starts': 0, 'source_reads_from_Android_data': 0,
     'cgroup': str(CG), 'inputs': []}
CHILD = None


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def pin(path, expected=None):
    path = Path(path)
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= 8 * 1024**2,
         'bounded regular public input required: ' + str(path))
    data = path.read_bytes()
    after = path.lstat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(all(getattr(before, k) == getattr(after, k) for k in fields), 'input changed: ' + str(path))
    record = {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
              'dev': before.st_dev, 'inode': before.st_ino}
    if expected:
        need(record['sha256'] == expected, 'input hash differs: ' + str(path))
    return record


def track(path, expected=None):
    value = pin(path, expected)
    R['inputs'].append(value)
    return value


def create(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
    return pin(path)


def run(name, argv, expected=0, env=None, timeout=90):
    global CHILD
    stdout, stderr = D / (name + '.stdout'), D / (name + '.stderr')
    started = time.monotonic()
    with stdout.open('xb') as out, stderr.open('xb') as err:
        CHILD = subprocess.Popen(argv, cwd=D, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        pid = CHILD.pid
        fd = os.pidfd_open(pid)
        try:
            code = CHILD.wait(timeout=timeout)
        except BaseException:
            CHILD.terminate()
            try:
                CHILD.wait(timeout=10)
            except subprocess.TimeoutExpired:
                CHILD.kill(); CHILD.wait(timeout=10)
            raise
        finally:
            exited = bool(select.select([fd], [], [], 0)[0]); os.close(fd)
    R['commands'].append({'name': name, 'argv': argv, 'exit_code': code,
                          'pid': pid, 'pidfd_exit': exited, 'seconds': time.monotonic() - started,
                          'stdout': pin(stdout), 'stderr': pin(stderr)})
    CHILD = None
    print(json.dumps({'command': name, 'exit_code': code, 'pidfd_exit': exited}), flush=True)
    need(code == expected and exited, 'ordinary command failed: ' + name)
    return stdout.read_text(errors='replace')


def interrupted(signum, _frame):
    raise RuntimeError('owned probe builder signal ' + str(signum))


for number in (signal.SIGTERM, signal.SIGINT):
    signal.signal(number, interrupted)

try:
    actual = {name: (CG / name).read_text().strip() for name in ('memory.max', 'memory.swap.max', 'cpu.max', 'pids.max')}
    need(actual == {'memory.max': '1073741824', 'memory.swap.max': '0', 'cpu.max': '100000 100000', 'pids.max': '32'},
         'ordinary probe resource profile differs')
    R['resources_before'] = actual
    state=subprocess.run(['/usr/bin/systemctl','--user','show','p4-context-probe-8764-r5-build.service','--property=MainPID,InvocationID,KillMode,OOMPolicy'],capture_output=True,text=True,check=True,timeout=10)
    owner=dict(line.split('=',1) for line in state.stdout.splitlines() if '=' in line)
    need(owner.get('MainPID')==str(os.getpid()) and owner.get('InvocationID')==os.environ.get('INVOCATION_ID') and owner.get('KillMode')=='control-group' and owner.get('OOMPolicy')=='stop','ordinary build owned unit identity differs')
    R['owned_unit']=owner
    track(__file__)
    track(C / 'build-inputs-r5.json', '5de24cacc89838d5bbf2446a7b2f6d1bbe3ad3039dbca452788cae14e4fb4d9d')
    packet = json.loads((C / 'build-inputs-r5.json').read_bytes())
    names = ['context_probe.c', 'context_binder.h', 'context_credentials.h', 'context_ip.h', 'context_stream.h', 'p4_lsm_context.h',
             'include/linux/android/binder.h', 'include/linux/android/binderfs.h', 'vocabulary.cil',
             'context-diagnostic.cil', 'context-apparmor.profile', 'diagnostic-policy-r4c-delta.json', 'diagnostic-stream-r5-delta.json']
    need(packet['schema'] == 'p4ctx1-scm-runtime-source-v1' and [r['path'] for r in packet['files']] == names,
         'source packet has unexpected files')
    for row in packet['files']:
        data = row['text'].encode()
        need(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'source packet content mismatch')
        create(D / row['path'], data)
        track(D / row['path'], row['sha256'])
    track(ORIGINAL / 'vocabulary.cil', 'b66bf45186d7bf801b645510504fca6cd33fe07daa6acef48fef9ac52890421e')
    track(ORIGINAL / 'compiler-build-origin.json', '13ef6216dd8ba9392ee3854a3b787159baa3b49e04b8ff20f41cda92a1e9dd0f')
    track(TOOLS / 'secilc', 'bcd13a3d2abcefc03a999448e191edf30cd2b19d192b9a70d42bca8f7219b190')
    track(TOOLS / 'libsepol.so.2', '0301e315bae5890d17b3160462c63fb00119b98456aebbae44745e6c1208b85c')
    features = track(ORIGINAL / 'apparmor.features', 'e510bb8f6788b45e48de2f859a6f94a7b8416cbac5a1051814cfce925fa911bd')
    create(D / 'apparmor.features', Path(features['path']).read_bytes())
    create(D / 'apparmor-parser.conf', b'')
    for executable in ('/usr/bin/gcc', '/usr/bin/readelf', '/usr/sbin/apparmor_parser'):
        track(Path(executable).resolve(strict=True))
    run('compiler-version', ['/usr/bin/gcc', '--version'])
    command = ['/usr/bin/gcc', '-std=c11', '-O2', '-static', '-Wall', '-Wextra', '-Werror',
               '-Wno-misleading-indentation', '-Wl,-z,noexecstack', '-I', str(D / 'include')]
    for suffix, release in (('candidate', '7.0.14-p4ctx3'), ('previous', '7.0.14-p4ctx2'), ('baseline', '7.0.14-p4ctx1')):
        executable = D / ('context-probe-' + suffix)
        run('compile-' + suffix, command + ['-DEXPECTED_RELEASE="' + release + '"', '-o', str(executable), str(D / 'context_probe.c')])
        program = run('elf-' + suffix, ['/usr/bin/readelf', '-lW', str(executable)])
        stack = [line for line in program.splitlines() if 'GNU_STACK' in line]
        need('INTERP' not in program and len(stack) == 1 and ' RWE ' not in stack[0] and ' RW ' in stack[0],
             'static nonexecuting-stack guest binary required')
        run('outside-vm-' + suffix, [str(executable)], expected=64, timeout=5)
    env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8', 'LD_LIBRARY_PATH': str(TOOLS)}
    run('normal-selinux-policy', [str(TOOLS / 'secilc'), '-M', 'true', '-U', 'deny', '-c', '30',
        '-o', str(D / 'context-selinux.bin'), '-f', str(D / 'file_contexts'),
        str(D / 'vocabulary.cil'), str(D / 'context-diagnostic.cil')], env=env)
    run('normal-apparmor-no-load', ['/usr/sbin/apparmor_parser', '--config-file', str(D / 'apparmor-parser.conf'),
        '--skip-kernel-load', '--skip-cache', '--features-file', str(D / 'apparmor.features'), '--jobs', '1', '--max-jobs', '1',
        '--ofile', str(D / 'context-apparmor.bin'), str(D / 'context-apparmor.profile')])
    R['artifacts'] = [pin(D / name) for name in ('context-probe-candidate', 'context-probe-previous', 'context-probe-baseline', 'context-selinux.bin', 'context-apparmor.bin')]
    R['passed'] = True
except BaseException as error:
    R['passed'] = False
    R['errors'].append({'type': type(error).__name__, 'message': str(error)})
finally:
    if CHILD is not None and CHILD.poll() is None:
        CHILD.terminate()
        try:
            CHILD.wait(timeout=10)
        except subprocess.TimeoutExpired:
            CHILD.kill(); CHILD.wait(timeout=10)
    R['inputs_unchanged'] = all(pin(row['path']) == row for row in R['inputs'])
    R['resources_final'] = {name: (CG / name).read_text().strip() for name in ('memory.events', 'memory.peak', 'memory.max', 'memory.swap.max', 'cpu.max')}
    events = dict(line.split() for line in R['resources_final']['memory.events'].splitlines())
    if not R['inputs_unchanged'] or any(events.get(key) != '0' for key in ('oom', 'oom_kill', 'oom_group_kill')):
        R['passed'] = False
    R['finished_ns'] = time.time_ns()
    create(D / 'result.json', (json.dumps(R, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps({'result': pin(D / 'result.json'), 'passed': R['passed'], 'errors': R['errors']}), flush=True)
raise SystemExit(0 if R['passed'] else 1)
