#!/usr/bin/env python3
"""One original recorder cleanup, with its original owned-child lifetime gate.

The recorder, cleanup implementation, task parser, R5 transport and guards are
not patched. No launch, input, focus transfer, install or reconciliation occurs.
Only the already owned task 876 may be removed by the original cleanup path.
"""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

ROOT = '/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1'
FLOW = '/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb'
STEP = 'cleanup-owned-task-876-01'
TASK = 876
PACKAGE = 'com.lianjia.beike'
EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
MANIFEST_SHA = '646f6e4c7d931bf005ada01a84202a891c95e99e93bbde7a561f3307527008a4'
RECORDER = {'path': '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder/recorder.py',
    'bytes': 39563, 'sha256': '0e50c67b1d5d251766fb58a69d9e62e119f0663ff2c4115ae326874cf95d6c09'}
CORE = {'path': '/home/alex/work/pocket4-beike-owned-postcondition-20261106-baaf68ac0d617dbe3894f714b18f099b/owned_postcondition_core.py',
    'bytes': 28714, 'sha256': '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41'}
SUPPORT = {'path': '/home/alex/work/pocket4-beike-owned-generation-20261106-b34f158f88bbebf112840fd88df25d03/prepare_beike_owned_lifetime.py',
    'bytes': 20132, 'sha256': '76b858b83c7304287fedb13f80c889e3fa7a8d6d32d4183409a5ad6fce269baf'}
BUNDLE = {'path': '/home/alex/work/pocket4-beike-postcondition-evidence-20261106-r1/bundle.private.json',
    'bytes': 1218042, 'sha256': '3c72bc43b2a32950a576405049b12cf6984ef790978638122ef2a7d4602941c8'}
ARGV = [RECORDER['path'], 'cleanup', '--adapter-manifest-sha256', MANIFEST_SHA,
        '--flow-dir', FLOW, '--step', STEP]
STAT = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_rdev',
        'st_size', 'st_mtime_ns', 'st_ctime_ns')
MAX_FILE = 2 * 1024 * 1024
SELF_PIN = None


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def read(path, maximum=MAX_FILE):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts and str(path) == path.as_posix(), 'CANONICAL_ABSOLUTE_PATH')
    owned = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); owned.append(parent)
        for name in path.parts[1:-1]:
            parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            owned.append(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        owned.append(fd); first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == 0 and first.st_nlink == 1 and
             not first.st_mode & 0o022 and 0 <= first.st_size <= maximum, 'BOUNDED_ROOT_REGULAR_FILE')
        body = bytearray(); deadline = time.monotonic() + 10
        while len(body) <= first.st_size:
            need(time.monotonic() < deadline, 'HOST_FILE_READ_BOUND')
            part = os.read(fd, min(65536, first.st_size + 1 - len(body)))
            if not part:
                break
            body.extend(part)
        last, named = os.fstat(fd), os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        need(len(body) == first.st_size and all(getattr(first, key) == getattr(last, key) == getattr(named, key)
                                               for key in STAT), 'HOST_FILE_CHANGED_OR_REPLACED')
        return bytes(body), {key: getattr(first, key) for key in STAT}
    finally:
        for fd in reversed(owned):
            os.close(fd)


def pinned(pin):
    need(set(pin) == {'path', 'bytes', 'sha256'} and type(pin['bytes']) is int and
         0 < pin['bytes'] <= MAX_FILE and re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'EXACT_PIN')
    raw, _ = read(pin['path'])
    need(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'PINNED_BYTES_CHANGED')
    return raw


def load(pin, name):
    module = types.ModuleType(name); module.__file__ = pin['path']
    exec(compile(pinned(pin), pin['path'], 'exec'), module.__dict__)
    return module


def entry(mode):
    global SELF_PIN
    need(os.getuid() == os.geteuid() == 0 and len(sys.argv) == 6 and sys.argv[1] == mode and
         sys.argv[2] == '--source-sha256' and sys.argv[4] == '--source-bytes' and
         re.fullmatch('[0-9a-f]{64}', sys.argv[3]) and sys.argv[5].isdigit(), 'EXACT_ROOT_ONCE_ENTRY')
    need(str(Path(__file__).resolve()) == ROOT + '/cleanup_owned_task_once.py', 'REAL_NEW_SOURCE_LOCATION')
    SELF_PIN = {'path': str(Path(__file__).resolve()), 'bytes': int(sys.argv[5]), 'sha256': sys.argv[3]}
    pinned(SELF_PIN)
    os.umask(0o077)


def originals(core):
    bundle = core.document(pinned(BUNDLE))
    need(bundle.get('schema') == 'pocket4-beike-two-step-private-original-byte-bundle-v1' and
         bundle.get('flow') == FLOW and bundle.get('full_original_bytes') is True and
         bundle.get('contains_private_UI_evidence') is True and bundle.get('approved_for_Git') is False and
         type(bundle.get('files')) is dict and len(bundle['files']) == 177, 'ACTUAL_PRIVATE_ORIGINAL_BUNDLE')
    rows = bundle['files']; bodies = {}; identities = {}; total = 0
    for relative, row in rows.items():
        need(type(relative) is str and not relative.startswith('/') and
             all(x not in ('', '.', '..') for x in relative.split('/')) and '\\' not in relative and
             type(row) is dict and set(row) == {'bytes', 'sha256', 'base64'}, 'CLOSED_ORIGINAL_ROW')
        body = base64.b64decode(row['base64'], validate=True)
        need(type(row['bytes']) is int and 0 <= row['bytes'] <= MAX_FILE and len(body) == row['bytes'] and
             sha(body) == row['sha256'], 'ORIGINAL_BUNDLE_MEMBER_PIN')
        current, identity = read(Path(FLOW) / relative)
        need(current == body, 'ORIGINAL_EVIDENCE_CHANGED_BEFORE_CLEANUP')
        bodies[relative], identities[relative] = body, identity
        total += len(body)
    need(total == 888207, 'EXACT_177_ORIGINAL_BYTE_TOTAL')
    scope = core.fixed_scope(core.document(bodies['scope.json']))
    launch = core.fixed_launch(core.document(bodies['launch-scope.json']))
    need(launch['launch_step'] == 'native-launch-01' and launch['task'] == TASK and
         launch['prelaunch_absent'] is True and launch['cleanup_allowed'] is True, 'ORIGINAL_NATIVE_OWNED_NEW_TASK')
    old = core.document(bodies['steps/close-entry-popup-01/result.json'])
    need(old.get('ok') is True and old.get('action_attempted') is True and old.get('outcome_unknown') is True and
         old.get('epoch_sha256') == EPOCH, 'ORIGINAL_CLOSE_UNKNOWN_MUST_REMAIN')
    need(not os.path.lexists(Path(FLOW) / 'cleanup-attempted.json') and
         not os.path.lexists(Path(FLOW) / 'steps' / STEP), 'NO_CLEANUP_REPLAY_OR_STEP_REUSE')
    need(not os.path.lexists(Path(FLOW) / 'reconciliations/close-entry-popup-01.json'), 'NO_RECONCILIATION_CREATED')
    return bodies, identities, scope, launch


def preserved(bodies, identities):
    for relative, original in bodies.items():
        current, identity = read(Path(FLOW) / relative)
        need(current == original and identity == identities[relative], 'ORIGINAL_EVIDENCE_OR_IDENTITY_CHANGED')
    need(not os.path.lexists(Path(FLOW) / 'reconciliations/close-entry-popup-01.json'), 'NO_RECONCILIATION_CREATED')


def verify_cleanup(core, recorder, tasks_source, original_stdout):
    need(original_stdout.endswith(b'\n') and len(original_stdout.splitlines()) == 1, 'ONE_ORIGINAL_RECORDER_RESULT')
    value = core.document(original_stdout)
    need(value.get('ok') is True and value.get('outcome_unknown') is False and
         value.get('epoch_sha256') == EPOCH and value.get('automatic_retry') is False and
         value.get('business_success_verified') is False, 'ORIGINAL_CLEANUP_NOT_SUCCESSFUL')
    folder = Path(FLOW) / 'steps' / STEP
    result_raw, _ = read(folder / 'result.json')
    need(core.document(result_raw) == value, 'ORIGINAL_RESULT_FILE_DIFFERS_FROM_STDOUT')
    intent_raw, _ = read(folder / 'intent.json'); intent = core.document(intent_raw)
    need(intent.get('operation') == 'cleanup' and intent.get('mutation') is True and
         intent.get('request') is None and intent.get('unknown_step') is None and
         intent.get('observation_step') is None and intent.get('postcondition') is None and
         intent.get('automatic_retry') is False, 'ORIGINAL_CLEANUP_OPERATION_ONLY')
    core.fixed_scope(intent['scope'])
    binding_raw, _ = read(folder / 'held-main-binding.json'); binding = core.document(binding_raw)
    core.held_binding_identity(binding)
    contract = recorder.source_contract(MANIFEST_SHA)[1]
    transport = contract.load('bound_android_transport.py', 'cleanup_exact_frozen_transport')
    removed = value.get('new_leaf_removed_and_verified') is True
    if removed:
        count = value.get('observations')
        need(type(count) is int and 1 <= count <= 32 and value.get('other_tasks_preserved') is True and
             value.get('action_attempted') is True and TASK not in value.get('task_ids_after', [TASK]),
             'OWNED_REMOVAL_AND_OTHER_TASK_SET_REQUIRED')
        attempt_raw, _ = read(Path(FLOW) / 'cleanup-attempted.json'); attempt = core.document(attempt_raw)
        core.fixed_launch(attempt.get('selected'))
        need(attempt.get('step') == STEP and attempt.get('automatic_retry') is False, 'ONCE_ONLY_ORIGINAL_CLEANUP_ATTEMPT')
        expected = [(['list'], False, 20), (['remove', str(TASK)], True, 20)] + [(['list'], False, None)] * count
    else:
        need(value.get('new_task_already_absent') is True and value.get('removal_attempted') is False and
             value.get('action_attempted') is False and not os.path.lexists(Path(FLOW) / 'cleanup-attempted.json'),
             'ONLY_ACTUAL_ALREADY_ABSENT_NOOP_CAN_QUALIFY')
        count = 0; expected = [(['list'], False, 20)]
    seen = sorted(path.name for path in folder.glob('command-*.intent.json'))
    need(seen == ['command-%03d.intent.json' % i for i in range(1, len(expected) + 1)], 'EXACT_ORIGINAL_COMMAND_COUNT')
    evidence = []; before_tasks = None; last_roots = last_tasks = None; authority = None
    for index, (tail, mutation, fixed_timeout) in enumerate(expected, 1):
        stem = 'command-%03d' % index
        ci_raw, _ = read(folder / (stem + '.intent.json')); cr_raw, _ = read(folder / (stem + '.result.json'))
        out, _ = read(folder / (stem + '.stdout')); err, _ = read(folder / (stem + '.stderr'))
        ci, cr = core.document(ci_raw), core.document(cr_raw)
        timeout = ci.get('timeout_seconds')
        need(timeout == fixed_timeout if fixed_timeout is not None else type(timeout) in (int, float) and 0 < timeout <= 3,
             'UNCHANGED_ORIGINAL_REMOVAL_TIMEOUT')
        argv = ['/system/bin/cmd', 'activity', 'stack', *tail]
        core.command_success(ci, cr, out, err, mutation, timeout)
        route = core.command_argv(ci, argv, timeout,
            '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry', binding['classpath']['values'], transport)
        need(route['parent_pid'] == os.getpid() and (authority is None or authority == route), 'ONE_ACTUAL_CLEANUP_AUTHORITY')
        authority = route
        ti = core.document(read(folder / ('transport-%03d.intent.json' % index))[0])
        tc = core.document(read(folder / ('transport-%03d.command-result.json' % index))[0])
        tv = core.document(read(folder / ('transport-%03d.verified-result.json' % index))[0])
        identity = {'sequence': index, 'epoch_sha256': EPOCH, 'package': PACKAGE, 'uid': 10143,
            'command_sha256': sha(json.dumps(argv, ensure_ascii=False, separators=(',', ':')).encode()),
            'timeout_seconds': timeout, 'inner_timeout_seconds': max(1, timeout - 5),
            'automatic_retry': False, 'numeric_pid_target_used': False}
        need(ti == identity and tc == tv and all(tc.get(k) == v for k, v in identity.items()) and
             tc.get('returncode') == 0 and tc.get('action_attempted') is True and tc.get('outcome_unknown') is False and
             tc.get('stdout_bytes') == len(out) and tc.get('stderr_bytes') == 0 and
             tc.get('stdout_sha256') == sha(out) and tc.get('stderr_sha256') == sha(err), 'COMPLETE_LEASE_RELEASE_AND_POST_GUARD')
        if tail == ['list']:
            roots, tasks = tasks_source.parse_stacks(out.decode('utf-8', 'strict'))
            if before_tasks is None:
                before_tasks = tasks
                if removed:
                    need(tasks_source.exact_leaf(roots, TASK, PACKAGE), 'ACTUAL_PRE_REMOVE_EXACT_LEAF')
            else:
                need(tasks - {TASK} == before_tasks - {TASK}, 'ORIGINAL_OTHER_TASK_SET_CHANGED')
            last_roots, last_tasks = roots, tasks
        if index >= 3:
            observation = core.document(read(folder / ('cleanup-observation-%02d.json' % (index - 2)))[0])
            need(observation.get('observation') == index - 2 and observation.get('raw_stacks') == out.decode('utf-8', 'strict') and
                 observation.get('root_ids') == sorted(last_roots) and observation.get('task_ids') == sorted(last_tasks) and
                 observation.get('target_absent') is (TASK not in last_roots and TASK not in last_tasks), 'ACTUAL_CLEANUP_READBACK_RECEIPT')
        evidence.append({'index': index, 'argv': argv, 'mutation': mutation, 'joined': True, 'returncode': 0,
            'command_result_sha256': sha(cr_raw), 'stdout_bytes': len(out), 'stdout_sha256': sha(out),
            'transport_verified_result_sha256': sha(read(folder / ('transport-%03d.verified-result.json' % index))[0])})
    need(last_roots is not None and TASK not in last_roots and TASK not in last_tasks, 'TARGET_MUST_ACTUALLY_BE_ABSENT')
    return {'original_result': value, 'original_result_sha256': sha(result_raw), 'command_evidence': evidence,
            'task_absence_observed': True, 'target_task': TASK, 'removal_sent_once': removed,
            'already_absent_no_removal': not removed, 'task_ids_after': sorted(last_tasks),
            'readback_observations': count, 'raw_stacks_exported': False}


def child():
    entry('--child')
    need(sys.stdin.buffer.read(1) == b'R', 'ORIGINAL_PARENT_PIDFD_RELEASE_REQUIRED')
    result = {'schema': 'pocket4-original-owned-task-cleanup-child-v1', 'ok': False, 'errors': [],
        'original_recorder_invoked': False, 'original_recorder_modified': False, 'old_unknown_rewritten': False,
        'new_launches': 0, 'UI_input_actions': 0, 'instrumentation_calls': 0, 'permission_changes': 0,
        'App_installs': 0, 'reconciliation_published': False, 'production_ready': False, 'automatic_retry': False,
        'requires_parent_pidfd_retirement_and_durable_terminal': True}
    output = io.StringIO(); probe = frozen = None
    try:
        support = load(SUPPORT, 'original_exact_library_bootstrap')
        probe = support.load_module(support.PROBE_SOURCE, 'original_exact_owned_child_probe')
        observed = support.probe_proof()
        initial, frozen, library_fd, library = support.initialize_library(probe, observed)
        core = load(CORE, 'unchanged_offline_command_validation_only')
        recorder = load(RECORDER, 'unchanged_actual_recorder')
        task_path = Path(RECORDER['path']).parent / 'references/task_scope_baseline.py'
        tasks_source = recorder.task_functions(task_path)
        bodies, identities, scope, launch = originals(core)
        _, lock_metadata = read(Path(FLOW) / 'flow.lock', 65536)
        need(stat.S_IMODE(lock_metadata['st_mode']) == 0o600, 'ORIGINAL_FLOW_LOCK_METADATA')
        need(probe.same_descriptors(frozen, probe.census()), 'NO_PRE_CLEANUP_UNKNOWN_DESCRIPTOR')
        arguments = sys.argv
        returned = None
        try:
            sys.argv = ARGV
            result['original_recorder_invoked'] = True
            with contextlib.redirect_stdout(output):
                try:
                    recorder.main()
                    returned = 0
                except SystemExit as error:
                    returned = error.code
        finally:
            sys.argv = arguments
            raw = output.getvalue().encode('utf-8')
            result.update(original_recorder_returncode=returned, original_recorder_stdout=raw.decode('utf-8'),
                original_recorder_stdout_bytes=len(raw), original_recorder_stdout_sha256=sha(raw))
        need(returned == 0, 'ORIGINAL_RECORDER_FAILED_NO_RETRY')
        result['cleanup'] = verify_cleanup(core, recorder, tasks_source, raw)
        preserved(bodies, identities)
        result['old_original_evidence_preserved'] = {'files': 177, 'bytes': 888207, 'private_bundle_sha256': BUNDLE['sha256'],
            'original_close_outcome': 'unknown_retained', 'raw_private_data_exported': False}
        for pin in (SELF_PIN, SUPPORT, CORE, RECORDER, support.PROBE_SOURCE):
            pinned(pin)
        support.pin_runtime_files(probe, observed)
        final = probe.census()
        extra = set(final) - set(frozen)
        need(len(extra) == 1 and probe.same_descriptors(frozen, {k: v for k, v in final.items() if k in frozen}),
             'ONLY_ORIGINAL_DECLARED_FLOW_LOCK_MAY_REMAIN')
        held_lock = final[next(iter(extra))]
        need(held_lock['link'] == FLOW + '/flow.lock' and held_lock['fstat'] == lock_metadata and
             held_lock['descriptor_flags'] == 1 and held_lock['status_flags'] & os.O_ACCMODE == os.O_RDWR,
             'EXACT_ORIGINAL_FLOW_LOCK_UNTIL_PROCESS_EXIT')
        need(support.stable_library(probe.library_binding(library_fd, final[str(library_fd)])) == support.stable_library(library),
             'EXPLICIT_LIBRARY_RESOURCE_CHANGED')
        result.update(ok=True, final_descriptors=final, original_flow_lock_retired_at_process_exit=True,
            original_namespace_authority_released=True, library_retired_at_process_exit=True,
            manual_library_close=False, unknown_descriptors_closed=0)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    result['outcome_unknown'] = result['original_recorder_invoked'] and not result['ok']
    raw = canonical(result)
    need(len(raw) <= 131072, 'CHILD_RESULT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


def require_owned_exit(life, stderr):
    need(life.get('returncode') == 0 and life.get('pidfd_acquired') is True and
         life.get('pidfd_exit_observed') is True and life.get('pidfd_closed') is True and
         life.get('parent_descriptors_restored') is True and life.get('owned_child_sigkill_count') == 0 and
         life.get('timeout') is False and life.get('errors') == [] and not stderr,
         'NORMAL_ORIGINAL_CHILD_LIFETIME_REQUIRED')


def parent():
    entry('--execute-cleanup-once')
    result = {'schema': 'pocket4-original-owned-task-cleanup-result-v1', 'ok': False, 'errors': [],
        'automatic_retry': False, 'old_unknown_rewritten': False, 'new_launches': 0,
        'reconciliation_published': False, 'production_ready': False,
        'old_build_or_App_data_deleted': False, 'target_task': TASK,
        'acceptance_requires_original_stdout_and_authoritative_durable_terminal': True}
    try:
        support = load(SUPPORT, 'original_owned_library_functions')
        probe = support.load_module(support.PROBE_SOURCE, 'original_pidfd_lifetime_functions')
        observed = support.probe_proof(); support.pin_runtime_files(probe, observed)
        before = probe.census()
        need(set(before) == {'0', '1', '2'}, 'PARENT_INITIAL_STDIO_ONLY')
        argv = [sys.executable, '-I', '-B', SELF_PIN['path'], '--child', '--source-sha256', SELF_PIN['sha256'],
                '--source-bytes', str(SELF_PIN['bytes'])]
        life, raw, stderr = probe.run_owned_child(argv, seconds=240)
        result.update(child_lifecycle=life, child_stdout_original=raw.decode('utf-8', 'strict'),
            child_stdout_bytes=len(raw), child_stdout_sha256=sha(raw), child_stderr_original=stderr.decode('utf-8', 'replace'),
            child_stderr_bytes=len(stderr), child_stderr_sha256=sha(stderr))
        value = json.loads(raw)
        require_owned_exit(life, stderr)
        need(value.get('schema') == 'pocket4-original-owned-task-cleanup-child-v1' and value.get('ok') is True and
             value.get('errors') == [] and value.get('outcome_unknown') is False, 'NORMAL_ORIGINAL_CHILD_AND_CLEANUP_JOINT_GATE')
        need(value.get('cleanup', {}).get('task_absence_observed') is True and
             value.get('old_original_evidence_preserved', {}).get('original_close_outcome') == 'unknown_retained',
             'TASK_ABSENCE_AND_ORIGINAL_UNKNOWN_REQUIRED')
        for pin in (SELF_PIN, SUPPORT, CORE, RECORDER, support.PROBE_SOURCE):
            pinned(pin)
        support.pin_runtime_files(probe, observed)
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_MUST_RESTORE')
        result.update(ok=True, cleanup=value['cleanup'], old_close_outcome='unknown_retained',
            all_owned_child_resources_retired_by_normal_pidfd_exit=True,
            new_session_not_created=True, next_launch_requires_separate_reviewed_request=True)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    result['outcome_unknown'] = not result['ok'] and 'child_lifecycle' in result
    result['status'] = 'ORIGINAL_OWNED_TASK_ABSENT_AND_CHILD_RETIRED' if result['ok'] else 'CLEANUP_INCOMPLETE_NO_RETRY'
    raw = canonical(result)
    need(len(raw) <= 262144, 'PARENT_RESULT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(child() if sys.argv[1:2] == ['--child'] else parent())
