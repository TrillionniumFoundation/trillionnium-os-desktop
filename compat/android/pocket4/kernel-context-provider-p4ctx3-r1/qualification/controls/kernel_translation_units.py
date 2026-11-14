#!/usr/bin/python3
"""Ordinary isolated Kbuild for fixed context providers; never installs anything."""
import fcntl
import hashlib
import json
import os
import pathlib
import select
import signal
import stat
import subprocess
import sys
import time

B = pathlib.Path('/home/qq/work/p4-kernel-p4ctx1-scm-8764-r3')
C = B / 'control'
S = B / 'source'
O = B / 'out'
ORIG = pathlib.Path('/home/qq/work/pocket4-kernel-lsm-context-full-20261110-8b88-r1')
MODE = sys.argv[1]
assert MODE == 'tus' and len(sys.argv) == 2
assert os.getuid() == os.geteuid() == 1000
assert sorted(os.sched_getaffinity(0)) == list(range(6))
os.umask(0o077)
D = C / MODE
D.mkdir(mode=0o700)
LOCK = os.open(C / 'materialize.lock', os.O_RDWR | os.O_NOFOLLOW |
               (os.O_CREAT | os.O_EXCL if MODE == 'tus' else 0), 0o600)
LS = os.fstat(LOCK)
assert stat.S_ISREG(LS.st_mode) and LS.st_uid == 1000 and LS.st_size == 0 and LS.st_nlink == 1
fcntl.flock(LOCK, fcntl.LOCK_EX | fcntl.LOCK_NB)
CG = pathlib.Path('/sys/fs/cgroup' + pathlib.Path('/proc/self/cgroup').read_text().strip().split('::', 1)[1])
R = {'schema': 'p4ctx1-typed-scm-extension-tus-v3b', 'mode': MODE,
     'started_ns': time.time_ns(), 'commands': [], 'errors': [],
     'host_kernel_installations': 0, 'host_reboots': 0, 'host_module_loads': 0,
     'host_policy_loads': 0, 'Android_starts': 0, 'VM_runs': 0,
     'source_generation': str(B), 'cgroup': str(CG),
     'owner': {'pid': os.getpid(), 'stat': pathlib.Path('/proc/self/stat').read_text(),
               'boot_id': pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
               'invocation_id': os.environ.get('INVOCATION_ID')}}
TRACKED = {}
CHILD = None


def need(value, message):
    if not value:
        raise RuntimeError(message)


def pin(path, expected=None):
    path = pathlib.Path(path)
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode), 'regular input required: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    after = path.lstat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(all(getattr(before, field) == getattr(after, field) for field in fields), 'input changed: ' + str(path))
    result = {'path': str(path), 'bytes': before.st_size, 'sha256': digest.hexdigest(),
              'dev': before.st_dev, 'inode': before.st_ino}
    if expected:
        need((result['bytes'], result['sha256']) == expected, 'pin mismatch: ' + str(path))
    return result


def track(path, expected=None):
    value = pin(path, expected)
    TRACKED[value['path']] = value
    return value


def run(name, argv, env=None, limit=600, expected=0):
    global CHILD
    started = time.monotonic()
    out, err = D / (name + '.stdout'), D / (name + '.stderr')
    with out.open('xb') as stdout, err.open('xb') as stderr:
        CHILD = subprocess.Popen(argv, cwd=B, env=env, stdin=subprocess.DEVNULL,
                                 stdout=stdout, stderr=stderr)
        pid = CHILD.pid
        pidfd = os.pidfd_open(pid)
        ticks = pathlib.Path('/proc/%d/stat' % pid).read_text().rsplit(') ', 1)[1].split()[19]
        timed_out = False
        try:
            code = CHILD.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            CHILD.terminate()
            try:
                code = CHILD.wait(timeout=15)
            except subprocess.TimeoutExpired:
                CHILD.kill()
                code = CHILD.wait(timeout=15)
        finally:
            exited = bool(select.select([pidfd], [], [], 0)[0])
            os.close(pidfd)
    record = {'name': name, 'argv': argv, 'exit_code': code, 'pid': pid,
              'start_ticks': ticks, 'pidfd_exit': exited, 'child_reaped': CHILD.returncode is not None,
              'timed_out': timed_out, 'seconds': time.monotonic() - started,
              'stdout': pin(out), 'stderr': pin(err)}
    CHILD = None
    R['commands'].append(record)
    print(json.dumps({k: record[k] for k in ('name', 'exit_code', 'pidfd_exit', 'seconds')}), flush=True)
    need(code == expected and exited and not timed_out, 'command failed: ' + name)
    return out.read_text(errors='replace')


def values(raw):
    result = {}
    for line in raw.splitlines():
        if line.startswith('CONFIG_'):
            key, value = line.split('=', 1)
            result[key] = value
        elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
            result[line[2:-11]] = 'n'
    return result


def interrupted(number, _frame):
    if CHILD is not None and CHILD.poll() is None:
        CHILD.terminate()
    raise RuntimeError('owned controller signal: ' + str(number))


for _sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(_sig, interrupted)

try:
    resources = {name: (CG / name).read_text().strip() for name in
                 ('memory.max', 'memory.swap.max', 'cpu.max', 'pids.max')}
    need(resources == {'memory.max': '8589934592', 'memory.swap.max': '0',
                       'cpu.max': '600000 100000', 'pids.max': '256'}, 'resource profile differs')
    R['resources_before'] = resources
    mem = int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines()
                   if line.startswith('MemAvailable:'))) * 1024
    fs = os.statvfs(B)
    need(mem >= 16 * 1024**3 and fs.f_bavail * fs.f_frsize >= 80 * 1024**3, 'resource reserve unavailable')
    R['admission'] = {'MemAvailable': mem, 'disk_free_bytes': fs.f_bavail * fs.f_frsize,
                      'affinity': sorted(os.sched_getaffinity(0)), 'lock_inode': LS.st_ino}
    R['controller'] = track(__file__)
    actual = subprocess.run(['/usr/bin/systemctl','--user','show','p4ctx1-scm-8764-r3-tus.service',
                             '--property=MainPID,InvocationID,KillMode,OOMPolicy'],capture_output=True,text=True,check=True,timeout=15)
    unit_state=dict(line.split('=',1) for line in actual.stdout.splitlines() if '=' in line)
    need(unit_state.get('MainPID')==str(os.getpid()) and unit_state.get('InvocationID')==os.environ.get('INVOCATION_ID') and
         unit_state.get('KillMode')=='control-group' and unit_state.get('OOMPolicy')=='stop','owned unit lifetime differs')
    R['owned_unit']=unit_state
    previous=pathlib.Path('/home/qq/work/p4-kernel-p4ctx1-scm-8764-r2')
    R['previous_image_result']=track(previous/'control/image/result.json',(14978,'d88e0a48038de325bb0e5f0987298ff411defb34db3c64e18abc0091244d2468'))
    R['previous_image_retirement']=track(previous/'control/image/independent-retirement.json',(3244,'4b57968c0f990b88edc3f3a35a7c006fdeb6f825f057b7fcb3e033408fd7d119'))
    previous_result=json.loads((previous/'control/image/result.json').read_bytes())
    previous_retirement=json.loads((previous/'control/image/independent-retirement.json').read_bytes())
    need(previous_result['passed'] and previous_retirement['passed'] and previous_retirement['cgroup_absent'] and not previous_retirement['remaining_pids'] and not pathlib.Path(previous_result['cgroup']).exists(), 'previous complete image generation not retired')
    previous_lock=os.open(previous/'control/materialize.lock',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    need(os.fstat(previous_lock).st_ino==55595812,'previous generation lock changed')
    fcntl.flock(previous_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    R['previous_generation_lock_inode']=os.fstat(previous_lock).st_ino
    fcntl.flock(previous_lock,fcntl.LOCK_UN);os.close(previous_lock)
    R['patch'] = track(C / 'context-providers-v3b.patch',
                       (15935, '58b33c63587b7adf4846a354fdcf6d80a124d3fcac6144a85649ab0ee566c827'))
    R['pins'] = track(C / 'input-pins-v3b.json',
                      (2356, '530b92bd948a0b13a2e6a736b5ecc1af3feacd8e9e6fbccd1821ec6ae7875bf1'))
    rows = json.loads((C / 'input-pins-v3b.json').read_bytes())
    need(len(rows) == 9 and len({row['path'] for row in rows}) == 9, 'source delta differs')
    for row in rows:
        need(not pathlib.PurePath(row['path']).is_absolute() and '..' not in pathlib.PurePath(row['path']).parts,
             'source path must be bounded')
        track(ORIG / 'source' / row['path'], (row['before_bytes'], row['before']))
    track(ORIG / 'out/.config',
          (308714, '561f347708186f01e77e97b1f394a8c06733a9040340659ce21e0e538f849940'))
    track(ORIG / 'qualification/result.json',
          (434917, '1b6e1318226b5ea403001632574235a1901330c8b923b3dd7563bad1f653f579'))
    original = json.loads((ORIG / 'qualification/result.json').read_bytes())
    env = dict(original['build_environment'])
    R['tool_input_snapshot'] = track(C / 'tool-inputs.json',
                                    (6665, '3657f30e2db081a6e74509560f6527add2a9a0965624d0eb111f5a633c5311ae'))
    tool = json.loads((C / 'tool-inputs.json').read_bytes())
    roles = ('RUSTC', 'HOSTRUSTC', 'BINDGEN', 'CLANG', 'PAHOLE', 'HOSTCFLAGS', 'HOSTLDFLAGS')
    need(tool['private_make_arguments'] == [role + '=' + env[role] for role in roles], 'qualified tool roles changed')
    for row in tool['public_tool_inputs'] + tool['public_runtime_inputs']:
        track(row['path'], (row['bytes'], row['sha256']))
    for row in tool['tool_aliases']:
        need(str(pathlib.Path(row['path']).resolve(strict=True)) == row['target'], 'qualified tool alias changed')
    (B / 'tmp').mkdir(mode=0o700, exist_ok=True)
    env['TMPDIR'] = str(B / 'tmp')
    R['build_environment'] = env
    if MODE == 'tus':
        R['prior_units'] = {}
        for unit in ('p4-kernel-context-provider-tus-8764-r1.service',
                     'p4-kernel-context-provider-tus-8764-r2.service',
                     'p4-context-provider-8764-r2-image.service',
                     'p4ctx1-scm-8764-r1-tus.service',
                     'p4ctx1-scm-8764-r2-tus.service',
                     'p4ctx1-scm-8764-r2-image.service'):
            process = subprocess.run(['/usr/bin/systemctl', '--user', 'show', unit,
                                      '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],
                                     capture_output=True, text=True, timeout=15)
            state = dict(line.split('=', 1) for line in process.stdout.splitlines() if '=' in line)
            R['prior_units'][unit] = state
            need(state.get('ActiveState') in ('inactive', 'failed') and state.get('MainPID') == '0'
                 and state.get('ControlGroup') == '', 'prior owned compiler unit not retired')
        prior_root = pathlib.Path('/home/qq/work/p4-kernel-p4ctx1-scm-8764-r1')
        R['prior_scm_tus'] = track(prior_root / 'control/tus/result.json',
                                   (19467, '4e9f88ab51089468de509f734f1718345d2ede56c68911c150950976edf254e4'))
        prior = json.loads((prior_root / 'control/tus/result.json').read_bytes())
        need(prior['passed'] and prior['inputs_unchanged'], 'prior SCM TU input failure')
        prior_cgroup = '/user.slice/user-1000.slice/user@1000.service/app.slice/p4ctx1-scm-8764-r1-tus.service'
        need(prior['cgroup'] == '/sys/fs/cgroup' + prior_cgroup and
             not pathlib.Path(prior['cgroup']).exists(), 'prior SCM cgroup still exists')
        leftovers = []
        for process_dir in pathlib.Path('/proc').glob('[0-9]*'):
            try:
                if process_dir.stat().st_uid != 1000:
                    continue
                groups = (process_dir / 'cgroup').read_text().splitlines()
                if any(group.split('::', 1)[-1] == prior_cgroup or
                       group.split('::', 1)[-1].startswith(prior_cgroup + '/') for group in groups):
                    leftovers.append(int(process_dir.name))
            except FileNotFoundError:
                continue
        need(not leftovers, 'prior SCM compiler processes remain')
        prior_lock = os.open(prior_root / 'control/materialize.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        fcntl.flock(prior_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        R['prior_scm_retirement'] = {'cgroup_absent': True, 'matching_processes': leftovers,
                                     'lock_inode_reacquired': os.fstat(prior_lock).st_ino}
        fcntl.flock(prior_lock, fcntl.LOCK_UN)
        os.close(prior_lock)
        oldlock = os.open('/home/qq/work/p4-kernel-context-provider-8764-r1/control/materialize.lock',
                          os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        fcntl.flock(oldlock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        R['prior_lock_free_inode'] = os.fstat(oldlock).st_ino
        fcntl.flock(oldlock, fcntl.LOCK_UN)
        os.close(oldlock)
        need(not S.exists() and not O.exists(), 'new generation already contains source/output')
        need(not (ORIG / 'source/certs/signing_key.pem').exists(), 'source contains a private generated key')
        run('copy-source', ['/usr/bin/cp', '-a', '--reflink=auto', str(ORIG / 'source'), str(S)])
        run('whole-copy-compare', ['/usr/bin/diff', '-q', '-r', '--no-dereference', str(ORIG / 'source'), str(S)])
        for row in rows:
            target = S / row['path']
            need(target.stat().st_ino != (ORIG / 'source' / row['path']).stat().st_ino, 'hardlinked input forbidden')
            target.chmod(target.stat().st_mode | stat.S_IWUSR)
        patch = ['/usr/bin/patch', '--batch', '--fuzz=0', '-p1', '-d', str(S), '-i', str(C / 'context-providers-v3b.patch')]
        run('patch-check', patch + ['--dry-run'])
        run('patch-apply', patch)
        O.mkdir(mode=0o700)
        config = (ORIG / 'out/.config').read_text()
        need(config.count('CONFIG_LOCALVERSION="-p4ctx1"') == 1, 'original release differs')
        (O / '.config').write_text(config.replace('CONFIG_LOCALVERSION="-p4ctx1"', 'CONFIG_LOCALVERSION="-p4ctx3"'))
    else:
        R['prior_tus_result'] = track(C / 'tus/result.json')
        prior = json.loads((C / 'tus/result.json').read_bytes())
        need(prior.get('passed') is True and prior.get('inputs_unchanged') is True and prior.get('mode') == 'tus',
             'qualified TU result required')
        need(prior['patch'] == R['patch'] and prior['pins'] == R['pins'], 'TU delta differs')
        need(all(row['pidfd_exit'] and row['child_reaped'] and not row['timed_out']
                 for row in prior['commands']), 'TU children not retired')
    for row in rows:
        track(S / row['path'], (row['after_bytes'], row['after']))
    unchanged = ('security/p4_lsm_context.c', 'include/linux/p4_lsm_context.h',
                 'include/uapi/linux/p4_lsm_context.h', 'drivers/android/binder.c',
                 'drivers/android/binderfs.c', 'drivers/android/binder_internal.h',
                 'fs/proc/base.c', 'fs/proc/root.c', 'fs/proc/inode.c', 'net/socket.c',
                 'net/core/net_namespace.c')
    R['unchanged_original_framework'] = []
    for name in unchanged:
        original_pin = track(ORIG / 'source' / name)
        copied_pin = track(S / name, (original_pin['bytes'], original_pin['sha256']))
        R['unchanged_original_framework'].append({'path': name, 'sha256': copied_pin['sha256']})
    make = ['/usr/bin/make', '--no-print-directory', '-C', str(S), 'O=' + str(O), '-j6',
            *tool['private_make_arguments']]
    if MODE == 'tus':
        run('olddefconfig', make + ['olddefconfig'], env, 300)
    before, after = values((ORIG / 'out/.config').read_text()), values((O / '.config').read_text())
    delta = {key: {'before': before.get(key), 'after': after.get(key)} for key in set(before) | set(after)
             if before.get(key) != after.get(key)}
    R['config_delta'] = delta
    need(delta == {'CONFIG_LOCALVERSION': {'before': '"-p4ctx1"', 'after': '"-p4ctx3"'}},
         'unexpected configuration or toolchain change')
    if MODE == 'tus':
        run('prepare-scripts', make + ['prepare', 'scripts'], env, 600)
        targets = ['security/security.o', 'net/core/scm.o', 'net/ipv4/ip_sockglue.o',
                   'net/unix/af_unix.o', 'net/unix/garbage.o', 'net/unix/unix_bpf.o',
                   'net/unix/diag.o', 'net/unix/sysctl_net_unix.o']
        run('changed-translation-units', make + targets, env, 1800)
        R['objects'] = [pin(O / target) for target in targets]
    else:
        run('kernel-and-modules', make + ['bzImage', 'modules'], env, 18000)
        R['artifacts'] = [pin(O / name) for name in ('arch/x86/boot/bzImage', 'drivers/android/binder_linux.ko',
                                                    'vmlinux', 'Module.symvers', 'modules.order', 'include/config/kernel.release')]
        need((O / 'include/config/kernel.release').read_text().strip() == '7.0.14-p4ctx3', 'built kernel release differs')
    R['config_after'] = pin(O / '.config')
    R['passed'] = True
except BaseException as error:
    R['passed'] = False
    R['errors'].append({'type': type(error).__name__, 'message': str(error)})
finally:
    if CHILD is not None and CHILD.poll() is None:
        CHILD.terminate()
        try:
            CHILD.wait(timeout=15)
        except subprocess.TimeoutExpired:
            CHILD.kill()
            CHILD.wait(timeout=15)
    R['inputs_unchanged'] = all(pin(path) == value for path, value in TRACKED.items())
    R['finished_ns'] = time.time_ns()
    R['resources_final'] = {name: (CG / name).read_text().strip() for name in
                            ('memory.events', 'memory.peak', 'memory.max', 'memory.swap.max', 'cpu.max', 'pids.max')}
    events = dict(line.split() for line in R['resources_final']['memory.events'].splitlines())
    if not R['inputs_unchanged'] or any(events.get(key) != '0' for key in ('oom', 'oom_kill', 'oom_group_kill')):
        R['passed'] = False
    with (D / 'result.json').open('x') as stream:
        json.dump(R, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'result': pin(D / 'result.json'), 'passed': R['passed'],
                      'errors': R['errors'], 'inputs_unchanged': R['inputs_unchanged']}), flush=True)
    os.close(LOCK)
raise SystemExit(0 if R['passed'] else 1)
