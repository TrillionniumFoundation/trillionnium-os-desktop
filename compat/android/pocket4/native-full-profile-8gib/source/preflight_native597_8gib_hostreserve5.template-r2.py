import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time
import traceback

R = Path('/home/alex/work/pocket4-android-final/native')
D = R / 'attempts/full-build-native597-8gib-hostreserve5-20261108-r1'
F = R.parent / 'framework'
AUDIO_WORK = Path('/home/alex/work/pocket4-audio-source-build-20261108-r1/work')
BINDING = R / 'manifests/native597-8gib-hostreserve5-normal-execution-binding-20261108-r1.json'
BINDING_BYTES = None
BINDING_SHA = None
PEERS = [
    ('build-attempt-20261107-r9/terminal.json', 134980,
     'b208970de6e0aa67cbf3798c2ec448c2543d46cb507c20831bb02f6b6dc5b753'),
    ('build-reconciliation-20261107-r9/result.json', 126784,
     '9ddd29813bd4237a53b3d6a69b2e82b949a2a78444b8c9e8aef18f67ba3314a9'),
    ('abi-verification-20261107-r9b/result.json', 19308,
     '4ba55c62471f54b9cc845b86285c9747b5f7b3c608a29d7b049502cdeb15f226'),
]


def need(value, message):
    if not value:
        raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(value):
    return tuple(getattr(value, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
                 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def read(path, size, wanted):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = identity(os.fstat(fd))
        need(stat.S_ISREG(before[2]) and before[6] == size, 'input size/type changed: ' + str(path))
        raw = os.pread(fd, size + 1, 0)
        need(len(raw) == size and digest(raw) == wanted, 'input SHA changed: ' + str(path))
        need(identity(os.fstat(fd)) == before == identity(path.lstat()), 'held input identity changed: ' + str(path))
        return raw, {'path': str(path), 'bytes': size, 'sha256': wanted, 'identity': before}
    finally:
        os.close(fd)


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def owners():
    found = []
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            comm = (path / 'comm').read_text().strip()
            if comm in ('soong_ui', 'soong_build', 'ninja', 'droidloom-updat', 'droidloom-update',
                        'droidloom-sourc', 'droidloom-source'):
                found.append({'pid': int(path.name), 'comm': comm})
        except OSError:
            pass
    return found


def available():
    line = next(line for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
    return int(line.split()[1]) * 1024


if BINDING_BYTES is None or BINDING_SHA is None:
    raise SystemExit('ACTUAL_NATIVE597_FROZEN_EXECUTION_BINDING_PENDING')
need(type(BINDING_BYTES) is int and 0 < BINDING_BYTES <= 131072 and
     type(BINDING_SHA) is str and len(BINDING_SHA) == 64 and
     all(c in '0123456789abcdef' for c in BINDING_SHA), 'fixed bounded binding pin required')
os.umask(0o077)
need(os.getuid() == os.geteuid() == 1000, 'original operator is required')
need(not (D / 'preflight.json').exists(), 'preserve prior preflight')
started = time.time_ns()
locks = []
report = {'schema': 'pocket4-native597-bound-input-preflight-v1', 'state': 'VERIFYING',
          'started_ns': str(started), 'Soong_invocations': 0, 'production_actions': 0,
          'peer_transfer_scope': 'resource window only; retained independently qualified ABI does not authorize runtime',
          'preflight_resource_profile': 'native597-preflight2g-20261108-r2',
          'preserved_previous_preflight_failure': {'path': str(D / 'preflight-failure-1794158597107069008.json'),
              'bytes': 13430, 'sha256': 'f7f9bf96af1cf60371f652d932698f6000904b219310b79308c11fc78b1dbe57'}}
try:
    cg = Path('/sys/fs/cgroup') / Path('/proc/self/cgroup').read_text().strip()[3:].lstrip('/')
    need(cg.name.startswith('hepta-runtime-job-') and cg.name.endswith('.service'), 'owned preflight unit required')
    need((cg / 'cpu.max').read_text().strip() == '100000 100000', 'wrong preflight CPU quota')
    need((cg / 'memory.max').read_text().strip() == '2147483648', 'wrong preflight hard memory')
    completed = subprocess.run(['/usr/bin/systemctl', '--user', 'set-property', '--runtime', cg.name,
                                'MemorySwapMax=0'], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    need(completed.returncode == 0 and len(completed.stdout) + len(completed.stderr) < 8192,
         'preflight zero-swap unit setup failed')
    need((cg / 'memory.swap.max').read_text().strip() == '0', 'preflight swap limit differs')
    mask = sorted(os.sched_getaffinity(0))
    need(len(mask) >= 4, 'preflight must leave actual two-core build placement available')
    os.sched_setaffinity(0, {mask[-4]})
    report['preflight_resources'] = {'cgroup': str(cg), 'cpu.max': '100000 100000',
        'memory.max': 2147483648, 'memory.swap.max': 0, 'affinity': sorted(os.sched_getaffinity(0))}
    report['preflight_memory_stat_before'] = (cg / 'memory.stat').read_text()
    prior = report['preserved_previous_preflight_failure']
    read(Path(prior['path']), prior['bytes'], prior['sha256'])
    binding_raw, binding_pin = read(BINDING, BINDING_BYTES, BINDING_SHA)
    binding = json.loads(binding_raw)
    need(binding['schema'] == 'pocket4-native597-normal-execution-binding-v1' and
         binding['state'] == 'FROZEN_INPUTS_NOT_ADMITTED_OR_BUILT' and
         binding['Soong_invocations'] == binding['production_actions'] == 0 and
         binding['prior_child_attribution_applies_to_new_attempt'] is False,
         'actual reviewed frozen Native597 execution binding required')
    refs = {'packet': binding['packet'], **{key: binding['sources'][key]
            for key in ('controller', 'outer', 'launcher')}}
    for key, name in [('packet', 'build-packet.json'), ('controller', 'framework_build.py'),
                      ('outer', 'fenced_build.py'), ('launcher', 'launch_build.py')]:
        ref = refs[key]
        need(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'} and
             ref['path'] == str(D / name) and type(ref['bytes']) is int and
             0 < ref['bytes'] <= 524288, 'fixed bounded frozen execution source required')
    PACKET_SHA, CONTROLLER_SHA, OUTER_SHA = [refs[key]['sha256'] for key in ('packet', 'controller', 'outer')]
    packet_raw, packet_pin = read(D / 'build-packet.json', refs['packet']['bytes'], PACKET_SHA)
    packet = json.loads(packet_raw)
    controller_raw, controller_pin = read(D / 'framework_build.py', refs['controller']['bytes'], CONTROLLER_SHA)
    outer_raw, outer_pin = read(D / 'fenced_build.py', refs['outer']['bytes'], OUTER_SHA)
    _, launcher_pin = read(D / 'launch_build.py', 17845, '59620c6c640209929f9c3f7f2cbee870da52bee2c533f414af9065644a4c324d')
    need(refs['launcher'] == {key: launcher_pin[key] for key in ('path', 'bytes', 'sha256')},
         'reviewed actual-runtime launcher differs')
    need(packet['controller_source'].encode() == controller_raw and packet['outer_source'].encode() == outer_raw,
         'frozen packet and independent source files differ')
    report.update(packet=packet_pin, controller=controller_pin, outer=outer_pin, launcher=launcher_pin)
    report['frozen_binding'] = binding_pin
    peers = []
    for relative, size, wanted in PEERS:
        raw, pin = read(F / relative, size, wanted)
        peers.append({'reference': pin, 'document': json.loads(raw)})
    terminal, reconciliation, abi = [item['document'] for item in peers]
    need(terminal['state'] == 'FAILED' and terminal['lifecycle']['child_reaped']
         and terminal['lifecycle']['returncode'] == 0
         and terminal['lifecycle']['owned_tree_cleanup_complete']
         and terminal['lifecycle']['remaining_owned_children'] == [], 'r9 original terminal retirement differs')
    need(reconciliation['state'] == 'RECONCILED_BUILT_PENDING_ABI', 'exact r9 reconciliation differs')
    need(abi['state'] == 'ABI_QUALIFIED_PENDING_RUNTIME' and abi['source_locks_released'] is True and abi['reaper']['final_children_empty'] is True
         and abi['reaper']['restored'] is True, 'retained ABI attempt not fully retired')
    old_raw, old_pin = read(R / 'attempt-12/terminal.json', 2856,
        'bff159815936a80027948e6ae28aa7637f5d38e3c62d79bda49b931b5a875d68')
    old = json.loads(old_raw)
    need(old['state'] == 'FAILED' and old['cleanup']['complete'] and not old['cleanup']['errors']
         and old['input_after_qualified'] and not old['source_projection_journal_present'],
         'previous native build was not fully restored and retired')
    _, attr_pin = read(R / 'attempt-12/observations/child255-independent-review-camera-framework.json', 13295,
        '0f547356675aa1498cf9cb419ad7c8b1ccf0934f8f76f60ff2781a63c150247b')
    report['prior_failed_native_preserved'] = old_pin
    report['prior_exact_child_attribution'] = attr_pin
    report['framework_retained_receipts'] = [{'reference': item['reference'],
        'state': item['document'].get('state')} for item in peers]
    scope = {'__name__': 'pinned_native597_readonly_preflight', '__file__': str(D / 'framework_build.py')}
    exec(compile(controller_raw, str(D / 'framework_build.py'), 'exec'), scope, scope)
    outer_scope = {'__name__': 'pinned_native597_outer_preflight', '__file__': str(D / 'fenced_build.py')}
    exec(compile(outer_raw, str(D / 'fenced_build.py'), 'exec'), outer_scope, outer_scope)
    need(outer_scope['ROOT'] == R and outer_scope['FENCE_ROOT'] == R / 'build-fences-native597-8gib-hostreserve5-20261108-r1'
         and outer_scope['CONTROLLER_SHA'] == CONTROLLER_SHA,
         'actual outer fence directory or controller binding differs')
    need(scope['ATTEMPT'] == R / 'attempt-native597-8gib-hostreserve5-20261108-r1' and scope['OUT'] == R / 'android-out-native597-8gib-hostreserve5-20261108-r1'
         and scope['plan']()['resource_admission_receipt'] == str(R / 'resource-admission-native597-8gib-hostreserve5-20261108-r1.json'),
         'actual inner attempt, output or admission path differs')
    _, prior_binding_pin = read(R / 'manifests/build-binding-native268-sdk-api-r2.json', 3011,
        '90bcb46b8603e4f5bbfdb39fd088803ffae0b08c9e719ee687c997e1073df91b')
    report['preserved_original_source_execution_binding'] = prior_binding_pin
    report['actual_execution_paths_verified'] = {'fence_root': str(outer_scope['FENCE_ROOT']),
        'attempt': str(scope['ATTEMPT']), 'out': str(scope['OUT']),
        'admission': scope['plan']()['resource_admission_receipt']}
    plan = scope['plan']()
    need(plan == binding['plan'] and plan['targets'] == ['libberberis_arm64', 'com.android.art'] and
         plan['dependency_mode'] == 'Strict' and plan['ALLOW_MISSING_DEPENDENCIES'] is False and
         plan['builder_source_files'] == 515 and plan['complete_engine_snapshot_files'] == 926 and
         plan['resource_profile_id'] == 'native597-8gib-hostreserve5-20261108-r1' and
         plan['memory_max_bytes'] == 8589934592 and plan['fresh_MemAvailable_min_bytes'] == 13958643712 and
         plan['memory_swap_max_bytes'] == 0 and plan['cpu_quota_percent'] == plan['jobs'] * 100 == 200 and
         plan['normal_build_timeout_seconds'] == plan['builder_wait_seconds'] == 21600 and
         plan['outer_runtime_timeout_seconds'] == 23000 and
         plan['actual_outer_runtime_admission_required'] is True and
         plan['post_preflight_runtime_admission_required'] is True and
         plan['post_preflight_runtime_margin_seconds'] == 1200,
         'reviewed frozen full-pair and actual-runtime plan differs')
    all_locks = plan['normal_lock_paths'] + [str(work / name) for work in (F / 'work', AUDIO_WORK)
                 for name in ('package-build.lock', 'aosp-source-update.lock')]
    need(len(all_locks) == len(set(all_locks)) == 6, 'exact Native, Framework and Audio resource locks required')
    deadline = time.monotonic() + 120
    while True:
        try:
            for name in all_locks:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BaseException:
                    os.close(fd)
                    raise
                locks.append(fd)
            break
        except BlockingIOError:
            for fd in reversed(locks):
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            locks.clear()
            need(time.monotonic() < deadline, 'peer still owns normal source/build locks')
            time.sleep(0.5)
    for work in (R / 'work', F / 'work', AUDIO_WORK):
        journal = work / 'source-projection.json'
        need(not journal.exists() and not journal.is_symlink(), 'source projection not restored: ' + str(work))
    for path in (R / 'attempt-native597-8gib-hostreserve5-20261108-r1', R / 'android-out-native597-8gib-hostreserve5-20261108-r1',
                 R / 'build-fences-native597-8gib-hostreserve5-20261108-r1', R / 'resource-admission-native597-8gib-hostreserve5-20261108-r1.json',
                 R / 'runtime-admission-native597-8gib-hostreserve5-20261108-r1.json'):
        need(not path.exists() and not path.is_symlink(), 'fresh native attempt resource exists: ' + str(path))
    before_owners = owners()
    need(not before_owners, 'existing actual build owners: ' + repr(before_owners))
    report['available_memory_before_bytes'] = available()
    need(report['available_memory_before_bytes'] >= 13 * 1024**3, 'fresh 8GiB plus 5GiB host-reserve admission not yet available')
    context = scope['verify_prepared'](scope['PREPARATION_SHA'])
    after = scope['verify_inputs_after'](context)
    after_owners = owners()
    need(not after_owners, 'actual build owner appeared during readonly preflight')
    _, binding_after = read(BINDING, BINDING_BYTES, BINDING_SHA)
    need(binding_after == binding_pin, 'actual frozen execution binding changed during preflight')
    report['available_memory_after_bytes'] = available()
    need(report['available_memory_after_bytes'] >= 13 * 1024**3, '8GiB plus 5GiB host-reserve floor no longer met')
    for item, (relative, size, wanted) in zip(peers, PEERS):
        _, after_pin = read(F / relative, size, wanted)
        need(after_pin == item['reference'], 'peer retirement authority changed')
    report.update(state='PASS', observed_ns=str(time.time_ns()),
        source_and_artifact_before_after_qualified=True, inventory_bytes_read_after=after.get('inventory_bytes_read'),
        source_files=len(context['builder_map']), normal_locks_observed_available=all_locks,
        framework_native_and_audio_projection_absent=True, existing_build_owners_before=before_owners,
        existing_build_owners_after=after_owners, normal_full_pair_plan=plan,
        fresh_build_resource_admission_still_required=True)
    report['preflight_resources_after'] = {name: (cg / name).read_text().strip() for name in
        ('memory.current', 'memory.peak', 'memory.events', 'memory.swap.current', 'memory.swap.max')}
    report['preflight_memory_stat_after'] = (cg / 'memory.stat').read_text()
    events = dict(line.split() for line in report['preflight_resources_after']['memory.events'].splitlines())
    need(all(events[name] == '0' for name in ('max', 'oom', 'oom_kill', 'oom_group_kill'))
         and report['preflight_resources_after']['memory.swap.current'] == '0', 'preflight resource fault')
    report['owned_children_after'] = Path('/proc/self/task/' + str(os.getpid()) + '/children').read_text().split()
    need(not report['owned_children_after'], 'preflight retained a child')
    saved = save(D / 'preflight.json', report)
    print(json.dumps({'state': 'PASS_BOUND_INPUT_PREFLIGHT', 'preflight': saved,
        'available_memory_after_bytes': report['available_memory_after_bytes'],
        'source_files': report['source_files'], 'owned_children_after': [], 'Soong_invocations': 0}), flush=True)
except BaseException as error:
    report.update(state='FAILED', error=repr(error), traceback=traceback.format_exc(), observed_ns=str(time.time_ns()))
    failure = save(D / ('preflight-failure-' + str(started) + '.json'), report)
    print(json.dumps({'state': 'FAILED_BOUND_INPUT_PREFLIGHT', 'error': repr(error), 'failure': failure}), flush=True)
    raise
finally:
    for fd in reversed(locks):
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
