#!/usr/bin/env python3
"""Native597 revision of attempts/full-build-11/bind_packet.py.

Freeze an already reviewed controller only after the real normal materializer
and its durable terminal are pinned below. This never starts Soong or Main.
Unresolved pins deliberately make the preparation file non-executable.
"""
import ast
import copy
import difflib
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
F = R / 'source-evidence/native-known-physical-lock-candidate-20261108-r2'
D = R / 'attempts/full-build-native597-8gib-hostreserve5-20261108-r1'
TEMPLATE = F / 'framework_build_native597_8gib_hostreserve5.template-r1.py'
TEMPLATE_SHA = '3b8a2e95e29afe318cc37ca0995a680634e0bd038f09a304bbdc1274fc64d6d4'
LAUNCHER_TEMPLATE = F / 'launch_build_native597_8gib_hostreserve5.parent-lease-r1.template.py'
LAUNCHER_TEMPLATE_SHA = '59620c6c640209929f9c3f7f2cbee870da52bee2c533f414af9065644a4c324d'
MATERIALIZATION_PIN = {'path': '/home/alex/work/pocket4-android-final/native/source-evidence/native-known-physical-lock-candidate-20261108-r2/normal-reconcile-r8-observed-admission-recovery-host/result.json', 'bytes': 68810, 'sha256': '1d89dcaa0267cebeb30989428802af8cd4117b4629cbebf985a6d0eb5519755b'}
MATERIALIZATION_TERMINAL_PIN = {'path': '/home/alex/work/pocket4-android-final/native/source-evidence/native-known-physical-lock-candidate-20261108-r2/normal-reconcile-r8-observed-admission-recovery-host/h-terminal.json', 'bytes': 731, 'sha256': '2e51c1181c22cfeb1e371c3e5c9a4d72ecd7e3a3acbf257d5e8c92b57b8c3b8a'}
MATERIALIZATION_JOB = '1a1bb6057d2-13c47-22d'
ACTIVE_BINDING = R / 'manifests/native597-8gib-hostreserve5-normal-active-work-binding-20261108-r1.json'
BUILD_BINDING = R / 'manifests/native597-8gib-hostreserve5-normal-builder-binding-20261108-r1.json'
RECORD = R / 'manifests/native597-8gib-hostreserve5-normal-execution-binding-20261108-r1.json'
PATCH = R / 'patches/native597-8gib-hostreserve5-normal-execution-binding-20261108-r1.patch'
OLD_PACKET = {
    'path': str(R / 'attempts/full-build-11/build-packet.json'),
    'bytes': 235791,
    'sha256': 'eef8edc84a6c9a35f515bfb3d62898759b6610148d158ba65deb292645247f2c',
}
OLD_FAILED = {
    'path': str(R / 'attempt-12/terminal.json'),
    'bytes': 2856,
    'sha256': 'bff159815936a80027948e6ae28aa7637f5d38e3c62d79bda49b931b5a875d68',
}
OLD_CHILD_ATTRIBUTION = {
    'path': str(R / 'attempt-12/observations/child255-independent-review-camera-framework.json'),
    'bytes': 13295,
    'sha256': '0f547356675aa1498cf9cb419ad7c8b1ccf0934f8f76f60ff2781a63c150247b',
}
EXPECTED_CHANGED_FUNCTIONS = ['build', 'builder_contract', 'builder_recovery_contract', 'completion_gate', 'memory_admission', 'observe_active_inputs', 'observe_prepared_inputs', 'pair_builder_identity', 'plan', 'prior_failure_contract', 'qualify_active_completed_manifest', 'record_resource_admission']
EXPECTED_ADDED_FUNCTIONS = [
    'final_source_builder_proof', 'historical_active_materialization',
    'historical_source_scope', 'partial_recovery_predecessor', 'source_resume_predecessor',
]


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def read(path, maximum=8 * 1024**2):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'absolute input required')
    for ancestor in path.parents:
        need(stat.S_ISDIR(ancestor.lstat().st_mode), 'real input ancestors required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum,
             'bounded regular input required: ' + str(path))
        raw = stream.read(maximum + 1)
        need(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
             == identity(path.lstat()), 'input identity changed: ' + str(path))
    return raw


def short(path, raw=None):
    raw = read(path) if raw is None else raw
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def pinned(ref):
    need(type(ref) is dict and set(ref) == {'path', 'bytes', 'sha256'}, 'exact input pin required')
    raw = read(ref['path'])
    need(short(ref['path'], raw) == ref, 'pinned input changed: ' + ref['path'])
    return json.loads(raw)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def save(path, value):
    raw = value if isinstance(value, bytes) else encoded(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    need(read(path) == raw, 'create-only publication mismatch')
    return short(path, raw)


def assign(source, name, value, expression=False):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    need(nodes, 'assignment missing: ' + name)
    node = nodes[-1]
    lines = source.splitlines(True)
    lines[node.lineno - 1:node.end_lineno] = [name + ' = ' + (value if expression else repr(value)) + '\n']
    return ''.join(lines)


def functions(source):
    return {n.name: ast.dump(n, include_attributes=False)
            for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}


def check_only_build_timeout_changed(before, after):
    """Retain every build action; extend only the normal compiler wait."""
    node = next(n for n in ast.parse(before).body
                if isinstance(n, ast.FunctionDef) and n.name == 'build')
    matches = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == 'wait':
            for keyword in child.keywords:
                if keyword.arg == 'timeout' and isinstance(keyword.value, ast.Constant) and keyword.value.value == 6100:
                    matches.append(keyword)
    need(len(matches) == 1, 'one original normal-build wait required')
    matches[0].value = ast.Constant(value=21600)
    observed = next(n for n in ast.parse(after).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'build')
    need(ast.dump(node, include_attributes=False) == ast.dump(observed, include_attributes=False),
         'build change extends beyond the fixed normal compiler timeout')


def scope(source, name):
    value = {'__name__': name}
    exec(compile(source, name + '.py', 'exec'), value, value)
    return value


def run():
    need(TEMPLATE_SHA is not None and LAUNCHER_TEMPLATE_SHA is not None and MATERIALIZATION_PIN is not None
         and MATERIALIZATION_TERMINAL_PIN is not None and MATERIALIZATION_JOB is not None,
         'ACTUAL_NATIVE597_MATERIALIZATION_AND_REVIEWED_TEMPLATE_PINS_PENDING')
    need(os.getuid() == os.geteuid() == 1000, 'original operator required')
    os.umask(0o077)
    raw_cgroup = Path('/proc/self/cgroup').read_text().strip()
    need(raw_cgroup.startswith('0::/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-'),
         'owned binder cgroup required')
    cgroup = Path('/sys/fs/cgroup') / raw_cgroup[3:].lstrip('/')
    subprocess.run(['/usr/bin/systemctl', '--user', 'set-property', '--runtime',
                    cgroup.name, 'MemorySwapMax=0'], check=True, capture_output=True, timeout=15)
    need((cgroup / 'memory.max').read_text().strip() == str(512 * 1024**2)
         and (cgroup / 'cpu.max').read_text().strip() == '50000 100000'
         and (cgroup / 'memory.swap.max').read_text().strip() == '0', 'bounded freeze resources required')
    affinity = sorted(os.sched_getaffinity(0))
    need(len(affinity) >= 4, 'two spare logical CPUs required')
    os.sched_setaffinity(0, [affinity[-3]])
    locks = []
    created = False
    try:
        for name in ('package-build.lock', 'aosp-source-update.lock'):
            fd = os.open(R / 'work' / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            locks.append(fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        need(not (R / 'work/source-projection.json').exists()
             and not (R / 'work/source-projection.json').is_symlink(), 'source projection remains active')
        old_packet = pinned(OLD_PACKET)
        old_controller, old_outer = old_packet['controller_source'], old_packet['outer_source']
        need(sha(old_controller.encode()) == '4da41b6640a04be63dfca302b0e52d0ad033842414416f8760e58c4ba1b9846c'
             and sha(old_outer.encode()) == '56c0ae64f5f241fe1828606c8c3ebc09c40774075853bc9f3b381097cc6f2d9d',
             'historical controller or outer changed')
        failed = pinned(OLD_FAILED)
        need(failed['state'] == 'FAILED' and failed['cleanup']['complete'] is True
             and failed['cleanup']['errors'] == [] and failed['input_after_qualified'] is True
             and failed['source_projection_journal_present'] is False,
             'prior failed attempt or source restoration changed')
        pinned(OLD_CHILD_ATTRIBUTION)  # Attribution remains exclusively attached to failed attempt12.
        template = read(TEMPLATE, 256 * 1024)
        need(sha(template) == TEMPLATE_SHA, 'reviewed Native597 template changed')
        launcher = read(LAUNCHER_TEMPLATE, 65536)
        need(sha(launcher) == LAUNCHER_TEMPLATE_SHA, 'reviewed Native597 launcher changed')
        controller = template.decode()
        native = scope(controller, 'native597_input_freeze')
        builder, builder_ref, source_map, source_ref, builder_elf = native['builder_contract']()
        historical, historical_ref, historical_mat, historical_mat_ref = native['historical_active_materialization']()
        materialization = pinned(MATERIALIZATION_PIN)
        terminal = pinned(MATERIALIZATION_TERMINAL_PIN)
        native['pair_terminal_contract'](terminal, MATERIALIZATION_JOB, True)
        need(materialization['state'] == 'NORMAL_EXACT_597_MATERIALIZATION_VERIFIED'
             and materialization['normal_materialization_qualified'] is True
             and materialization['owned_retirement_qualified'] is True
             and materialization['source_locks_released'] is True and materialization['errors'] == [],
             'actual completed normal597 materialization and retirement required')
        source_history = native['source_resume_predecessor'](
            materialization, historical, historical_mat)
        need(source_history['actual_source_job_id'] == MATERIALIZATION_JOB,
             'actual source runtime and completed durable H terminal belong to different jobs')
        lock_path = native['BUILD_SOURCE'] / 'android/native-generation-pair/source-lock.json'
        lock_raw = read(lock_path)
        need(len(lock_raw) == 348102 and sha(lock_raw) ==
             '2b699174977614e080cf99a991f3e648774b24581c4ecdc29f1bd53b7b01ef23', 'exact597 lock required')
        manifest_path = R / 'work/aosp-source/.droidloom-source-manifest.json'
        manifest_raw = read(manifest_path)
        manifest = json.loads(manifest_raw)
        expected = native['expected_published_manifest'](json.loads(lock_raw))
        expected['source_lock_sha256'] = sha(lock_raw)
        need(manifest == expected and len(manifest['plan']['projects']) == 597
             and len(manifest['plan']['links']) == 8
             and materialization['materialized_manifest'] == short(manifest_path, manifest_raw),
             'actual atomically published complete597 manifest required')
        active = copy.deepcopy(historical)
        active.update(schema='pocket4-native597-active-work-binding-v1',
                      source_lock=short(lock_path, lock_raw), source_manifest=short(manifest_path, manifest_raw),
                      materialization_lock=materialization['frozen_lock'], normal_materialization=MATERIALIZATION_PIN,
                      normal_materialization_terminal=MATERIALIZATION_TERMINAL_PIN,
                      historical_268_binding={k: historical_ref[k] for k in ('path', 'bytes', 'sha256')},
                      historical_268_materialization={k: historical_mat_ref[k] for k in ('path', 'bytes', 'sha256')})
        active_raw = encoded(active)
        build_binding = {'schema': 'pocket4-native597-normal-builder-binding-v1',
                         'normal_release_result': {k: builder_ref[k] for k in ('path', 'bytes', 'sha256')},
                         'source_manifest': {k: source_ref[k] for k in ('path', 'bytes', 'sha256')},
                         'source_files': len(source_map), 'builder': builder_elf,
                         'qualified_Soong_artifact': False, 'runtime_qualified': False}
        build_raw = encoded(build_binding)
        values = {
            'ACTIVE_LOCK_SHA': sha(lock_raw), 'ACTIVE_LOCK_BYTES': len(lock_raw),
            'ACTIVE_MANIFEST_SHA': sha(manifest_raw), 'ACTIVE_MANIFEST_BYTES': len(manifest_raw),
            'ACTIVE_PREPARATION_SHA': MATERIALIZATION_PIN['sha256'],
            'ACTIVE_PREPARATION_BYTES': MATERIALIZATION_PIN['bytes'],
            'ACTIVE_BINDING_SHA': sha(active_raw), 'ACTIVE_BINDING_BYTES': len(active_raw),
            'FINAL_BUILDER_BINDING_SHA': sha(build_raw), 'FINAL_BUILDER_BINDING_BYTES': len(build_raw),
        }
        for name, value in values.items():
            controller = assign(controller, name, value)
        for name, value in {
            'ACTIVE_PREPARATION': 'P(' + repr(MATERIALIZATION_PIN['path']) + ')',
            'ACTIVE_BINDING': 'P(' + repr(str(ACTIVE_BINDING)) + ')',
            'FINAL_BUILDER_BINDING': 'P(' + repr(str(BUILD_BINDING)) + ')',
        }.items():
            controller = assign(controller, name, value, True)
        before, after = functions(old_controller), functions(controller)
        changed = sorted(n for n in before if after.get(n) != before[n])
        added = sorted(set(after) - set(before))
        need(changed == EXPECTED_CHANGED_FUNCTIONS and added == EXPECTED_ADDED_FUNCTIONS
             and set(before) <= set(after), 'unexpected execution-function change')
        check_only_build_timeout_changed(old_controller, controller)
        controller_sha = sha(controller.encode())
        outer = assign(old_outer, 'CONTROLLER_SHA', controller_sha)
        outer = assign(outer, 'FENCE_ROOT', "ROOT/'build-fences-native597-8gib-hostreserve5-20261108-r1'", True)
        need(functions(outer) == functions(old_outer), 'outer lifecycle changed')
        final = scope(controller, 'native597_frozen')
        final_outer = scope(outer, 'native597_frozen_outer')
        plan = final['plan']()
        need(plan['resource_profile_id'] == 'native597-8gib-hostreserve5-20261108-r1'
             and plan['memory_max_bytes'] == 8589934592 and plan['memory_swap_max_bytes'] == 0
             and plan['fresh_MemAvailable_min_bytes'] == 13958643712 and plan['cpu_quota_percent'] == 200
             and plan['targets'] == ['libberberis_arm64', 'com.android.art']
             and plan['dependency_mode'] == 'Strict' and plan['ALLOW_MISSING_DEPENDENCIES'] is False
             and plan['jobs'] == 2 and plan['nice'] == 10 and plan['builder_source_files'] == 515
             and plan['complete_engine_snapshot_files'] == 926 and plan['automatic_retry'] is False
             and plan['normal_build_timeout_seconds'] == 21600
             and plan['builder_wait_seconds'] == 21600
             and plan['outer_runtime_timeout_seconds'] == 23000
             and plan['actual_outer_runtime_admission_required'] is True
             and plan['post_preflight_runtime_admission_required'] is True
             and plan['post_preflight_runtime_margin_seconds'] == 1200
             and plan['source_qualification_scope'] == 'exact_268_to_597_after_preserved_complete_promisor_timeout_and_earlier_failures'
             and plan['actual_source_job'] == MATERIALIZATION_JOB == '1a1bb6057d2-13c47-22d'
             and plan['source_resource_history_clear'] is False
             and plan['historical_partial_recovery_scope'] == 'exact_268_to_597_after_preserved_r2_partial_boundary_failure'
             and plan['historical_partial_recovery_failed_source_job'] == '1a1b9b64e12-12894-1641'
             and plan['Main_actions'] == plan['Android_actions'] == 0
             and plan['native_runtime_and_APEX_signatures_qualified'] is False,
             'original resource, complete-pair, or qualification boundary changed')
        need(final_outer['CONTROLLER_SHA'] == controller_sha
             and final_outer['FENCE_ROOT'] == R / 'build-fences-native597-8gib-hostreserve5-20261108-r1'
             and final['OUT'] == R / 'android-out-native597-8gib-hostreserve5-20261108-r1'
             and final['ATTEMPT'] == R / 'attempt-native597-8gib-hostreserve5-20261108-r1', 'actual execution path mismatch')
        fresh = [D, ACTIVE_BINDING, BUILD_BINDING, RECORD, PATCH, final['OUT'], final['ATTEMPT'],
                 final_outer['FENCE_ROOT'], R / 'resource-admission-native597-8gib-hostreserve5-20261108-r1.json',
                 R / 'runtime-admission-native597-8gib-hostreserve5-20261108-r1.json']
        need(all(not p.exists() and not p.is_symlink() for p in fresh), 'create-only fresh execution paths required')
        D.mkdir(mode=0o700)
        created = True
        refs = {'binder': save(D / 'bind_packet.py', read(Path(__file__), 128 * 1024)),
                'controller': save(D / 'framework_build.py', controller.encode()),
                'outer': save(D / 'fenced_build.py', outer.encode())}
        active_ref = save(ACTIVE_BINDING, active_raw)
        build_ref = save(BUILD_BINDING, build_raw)
        packet = dict(old_packet)
        packet.update(controller_source=controller, outer_source=outer)
        packet_ref = save(D / 'build-packet.json', packet)
        refs['launcher'] = save(D / 'launch_build.py', launcher)
        patch = ''.join(difflib.unified_diff(old_controller.splitlines(True), controller.splitlines(True),
                        fromfile='full-build-11/framework_build.py', tofile='native597/framework_build.py'))
        patch += ''.join(difflib.unified_diff(old_outer.splitlines(True), outer.splitlines(True),
                         fromfile='full-build-11/fenced_build.py', tofile='native597/fenced_build.py'))
        refs['patch'] = save(PATCH, patch.encode())
        event_rows = dict(line.split() for line in (cgroup / 'memory.events').read_text().splitlines())
        need(all(event_rows[k] == '0' for k in ('max', 'oom', 'oom_kill', 'oom_group_kill'))
             and (cgroup / 'memory.swap.current').read_text().strip() == '0', 'binder resource event observed')
        record = {'schema': 'pocket4-native597-normal-execution-binding-v1',
                  'state': 'FROZEN_INPUTS_NOT_ADMITTED_OR_BUILT', 'created_ns': time.time_ns(),
                  'prior_packet': OLD_PACKET, 'prior_failed_attempt': OLD_FAILED,
                  'prior_exact_child255_attribution': OLD_CHILD_ATTRIBUTION,
                  'prior_child_attribution_applies_to_new_attempt': False,
                  'normal_release_result': build_binding['normal_release_result'],
                  'materialization': MATERIALIZATION_PIN,
                  'materialization_terminal': MATERIALIZATION_TERMINAL_PIN,
                  'source_partial_recovery_history': source_history,
                  'active_binding': active_ref, 'builder_binding': build_ref,
                  'packet': packet_ref, 'sources': refs, 'changed_controller_functions': changed,
                  'added_controller_functions': added, 'outer_lifecycle_unchanged': True,
                  'plan': plan, 'full_six_lock_preflight_pending': True,
                  'fresh_resource_admission_pending': True, 'peer_heavy_window_wait_required': True,
                  'Soong_invocations': 0, 'production_actions': 0}
        receipt = save(RECORD, record)
        print(json.dumps({'state': record['state'], 'binding': receipt,
                          'packet': packet_ref, 'sources': refs, 'heavy_started': False}), flush=True)
    except BaseException as error:
        if created and not (D / 'binding-failure.json').exists():
            save(D / 'binding-failure.json', {'state': 'FAILED', 'error': repr(error),
                                             'created_ns': time.time_ns(), 'Soong_invocations': 0})
        traceback.print_exc()
        raise
    finally:
        for fd in reversed(locks):
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


if __name__ == '__main__':
    run()
