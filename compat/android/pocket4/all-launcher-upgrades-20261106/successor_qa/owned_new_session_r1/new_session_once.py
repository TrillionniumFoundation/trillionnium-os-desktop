#!/usr/bin/env python3
"""Original recorder init or launch in two separately admitted owned processes.

No recorder, guard, transport, helper or task function is replaced. The old
UNKNOWN stays in its original flow. The launch entry additionally requires the
exact init joint-lifetime artifact, accepted externally with its real terminal.
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
import types

ROOT = '/home/alex/work/pocket4-beike-owned-new-session-20261106-r1'
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
STEP = 'native-launch-01'
BASE = {'path': '/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1/cleanup_owned_task_once.py',
        'bytes': 22233, 'sha256': '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'}
CLEANUP_STDOUT = {'path': ROOT + '/cleanup.stdout.original.jsonl', 'bytes': 8920,
                  'sha256': '14a32088291f748d2d894783d4a27566dbe2f5b4a41dba0ffe54dc42ecd22224'}
CLEANUP_TERMINAL = {'path': ROOT + '/cleanup.terminal.original.json', 'bytes': 731,
                    'sha256': 'aa9628474f8c699662266033eba62d27f53f2cdcb53b7c77cef62050fae0fd69'}
CLEANUP_RESULT_SHA = '506e577d7e17c62cbd3a8b1fbe39cdfb65565ba2fef20a5ccf5291b6e78162f9'
BASELINE = '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/baseline.private.json'
BASELINE_SHA = '7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8'
COMPONENT = 'com.lianjia.beike/com.lianjia.activity.MainActivity'
SELF = None
INIT = None


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def load_base():
    """Bootstrap only the already deployed exact root-owned utility module."""
    path = Path(BASE['path']); fds = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); fds.append(parent)
        for name in path.parts[1:-1]:
            parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            fds.append(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent); fds.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and
             not before.st_mode & 0o022 and before.st_size == BASE['bytes'], 'EXACT_ROOT_UTILITY_FILE')
        raw = bytearray()
        while len(raw) <= before.st_size:
            part = os.read(fd, before.st_size + 1 - len(raw))
            if not part:
                break
            raw.extend(part)
        after, named = os.fstat(fd), os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        keys = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        need(len(raw) == BASE['bytes'] and sha(raw) == BASE['sha256'] and
             all(getattr(before, key) == getattr(after, key) == getattr(named, key) for key in keys), 'UTILITY_SOURCE_CHANGED')
    finally:
        for fd in reversed(fds):
            os.close(fd)
    module = types.ModuleType('unchanged_cleanup_utilities_only'); module.__file__ = str(path)
    exec(compile(bytes(raw), str(path), 'exec'), module.__dict__)
    return module


def entry(mode):
    global SELF, INIT
    is_launch = mode in ('--launch-once', '--child-launch')
    need(os.getuid() == os.geteuid() == 0 and len(sys.argv) == (10 if is_launch else 6) and
         sys.argv[1] == mode and sys.argv[2] == '--source-sha256' and sys.argv[4] == '--source-bytes' and
         re.fullmatch('[0-9a-f]{64}', sys.argv[3]) and sys.argv[5].isdigit(), 'EXACT_NEW_SESSION_ENTRY')
    need(str(Path(__file__).resolve()) == ROOT + '/new_session_once.py', 'REAL_NEW_SESSION_SOURCE_LOCATION')
    SELF = {'path': str(Path(__file__).resolve()), 'bytes': int(sys.argv[5]), 'sha256': sys.argv[3]}
    if is_launch:
        need(sys.argv[6] == '--init-proof-sha256' and re.fullmatch('[0-9a-f]{64}', sys.argv[7]) and
             sys.argv[8] == '--init-proof-bytes' and sys.argv[9].isdigit(), 'ACTUAL_INIT_PROOF_PIN_REQUIRED')
        INIT = {'path': ROOT + '/init-owned-lifetime.json', 'bytes': int(sys.argv[9]), 'sha256': sys.argv[7]}
    os.umask(0o077)
    base = load_base(); base.pinned(SELF)
    return base


def cleanup_gate(stdout, terminal, base):
    """Validate actual copied public receipts; these are not a live task query."""
    need(type(stdout) is bytes and len(stdout) == CLEANUP_STDOUT['bytes'] and sha(stdout) == CLEANUP_STDOUT['sha256'] and
         type(terminal) is bytes and len(terminal) == CLEANUP_TERMINAL['bytes'] and sha(terminal) == CLEANUP_TERMINAL['sha256'],
         'ACTUAL_CLEANUP_ORIGINAL_BYTES_REQUIRED')
    rows = stdout.splitlines(); need(len(rows) == 2, 'TWO_ACTUAL_CLEANUP_OUTPUT_ROWS')
    value, status = json.loads(rows[1]), json.loads(terminal)
    need(status.get('job_id') == '1a1b2307f12-fc05-7cdd' and status.get('state') == 'succeeded' and
         type(status.get('exit_code')) is int and status['exit_code'] == 0 and
         all(status.get(k) is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed', 'audit_recorded')) and
         all(status.get(k) is False for k in ('timed_out', 'cancelled', 'automatic_retry')) and
         status.get('log_bytes') == {'stdout': {'seen': len(stdout), 'stored': len(stdout)}, 'stderr': {'seen': 0, 'stored': 0}} and
         status.get('log_errors') == {'stdout': None, 'stderr': None} and
         status.get('log_synced') == {'stdout': True, 'stderr': True} and
         status.get('log_truncated') == {'stdout': False, 'stderr': False}, 'ACTUAL_DURABLE_CLEANUP_TERMINAL')
    need(value.get('schema') == 'pocket4-original-owned-task-cleanup-result-v1' and
         value.get('status') == 'ORIGINAL_OWNED_TASK_ABSENT_AND_CHILD_RETIRED' and value.get('ok') is True and
         value.get('errors') == [] and value.get('outcome_unknown') is False and value.get('target_task') == 876 and
         value.get('old_close_outcome') == 'unknown_retained' and value.get('old_unknown_rewritten') is False and
         value.get('reconciliation_published') is False and value.get('new_launches') == 0 and
         value.get('all_owned_child_resources_retired_by_normal_pidfd_exit') is True, 'ACTUAL_CLEANUP_JOINT_RESULT')
    base.require_owned_exit(value['child_lifecycle'], b'')
    child_raw = value['child_stdout_original'].encode('utf-8')
    need(len(child_raw) == value['child_stdout_bytes'] == 4913 and sha(child_raw) == value['child_stdout_sha256'] ==
         '67150cc9bfe4c73155e8d48d5a959b4eabbeabaa1db7114b9602cdb3504cf1c1', 'ACTUAL_CLEANUP_CHILD_BYTES')
    child = json.loads(child_raw); evidence = value['cleanup']
    need(child.get('ok') is True and child.get('errors') == [] and child.get('outcome_unknown') is False and
         child.get('cleanup') == evidence and evidence.get('task_absence_observed') is True and
         evidence.get('removal_sent_once') is True and evidence.get('original_result_sha256') == CLEANUP_RESULT_SHA and
         evidence.get('task_ids_after') == [875, 877], 'ACTUAL_ONE_REMOVAL_AND_TASK_ABSENCE')
    return value


def predecessor(base, core):
    actual = cleanup_gate(base.pinned(CLEANUP_STDOUT), base.pinned(CLEANUP_TERMINAL), base)
    result_raw, _ = base.read(Path(base.FLOW) / 'steps' / base.STEP / 'result.json')
    need(sha(result_raw) == CLEANUP_RESULT_SHA and core.document(result_raw) == actual['cleanup']['original_result'],
         'ACTUAL_ORIGINAL_CLEANUP_RESULT_UNCHANGED')
    archive = core.document(base.pinned(base.BUNDLE))
    need(archive.get('schema') == 'pocket4-beike-two-step-private-original-byte-bundle-v1' and
         archive.get('flow') == base.FLOW and archive.get('full_original_bytes') is True and
         archive.get('approved_for_Git') is False and type(archive.get('files')) is dict and len(archive['files']) == 177,
         'EXACT_OLD_PRIVATE_EVIDENCE_ARCHIVE')
    bodies, identities = {}, {}
    for relative, row in archive['files'].items():
        need(type(relative) is str and not relative.startswith('/') and '\\' not in relative and
             all(x not in ('', '.', '..') for x in relative.split('/')) and set(row) == {'bytes', 'sha256', 'base64'},
             'CLOSED_OLD_ARCHIVE_MEMBER')
        raw = base64.b64decode(row['base64'], validate=True)
        need(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'OLD_ARCHIVE_MEMBER_HASH')
        current, identity = base.read(Path(base.FLOW) / relative)
        need(current == raw, 'OLD_ORIGINAL_EVIDENCE_CHANGED')
        bodies[relative], identities[relative] = raw, identity
    need(sum(map(len, bodies.values())) == 888207, 'EXACT_OLD_ARCHIVE_TOTAL')
    old_scope = core.fixed_scope(core.document(bodies['scope.json']))
    core.fixed_launch(core.document(bodies['launch-scope.json']))
    unknown = core.document(bodies['steps/close-entry-popup-01/result.json'])
    need(unknown.get('outcome_unknown') is True and unknown.get('action_attempted') is True,
         'OLD_CLOSE_UNKNOWN_RETAINED')
    base.preserved(bodies, identities)
    return bodies, identities, old_scope


def new_scope(base, core, old_scope):
    raw, _ = base.read(Path(FLOW) / 'scope.json'); scope = core.fixed_scope(core.document(raw))
    need(set(scope) == set(old_scope) and all(scope[k] == old_scope[k] for k in scope if k != 'created_utc') and
         core.timestamp(scope['created_utc']) > core.timestamp('2026-11-06T18:48:11.546832+00:00'),
         'SAME_EXACT_TYPED_SCOPE_ONLY_NEW_CREATION_TIME')
    return scope, {'path': FLOW + '/scope.json', 'bytes': len(raw), 'sha256': sha(raw)}


def accepted_init(base, core, old_scope):
    need(INIT is not None, 'NO_UNQUALIFIED_INIT_DEFAULT')
    value = core.document(base.pinned(INIT))
    need(value.get('schema') == 'pocket4-original-new-session-owned-result-v1' and value.get('operation') == 'init' and
         value.get('ok') is True and value.get('errors') == [] and value.get('outcome_unknown') is False and
         value.get('flow') == FLOW and value.get('source') == SELF and value.get('old_close_outcome') == 'unknown_retained' and
         value.get('all_owned_child_resources_retired_by_normal_pidfd_exit') is True,
         'EXACT_NEW_INIT_JOINT_PROOF')
    base.require_owned_exit(value['child_lifecycle'], b'')
    child_raw = value['child_stdout_original'].encode('utf-8')
    need(sha(child_raw) == value['child_stdout_sha256'] and len(child_raw) == value['child_stdout_bytes'],
         'INIT_CHILD_ORIGINAL_BYTES')
    child = core.document(child_raw)
    need(child.get('ok') is True and child.get('errors') == [] and child.get('operation') == 'init' and
         child.get('flow') == FLOW and child.get('source') == SELF and child.get('outcome_unknown') is False, 'SUCCESSFUL_EXACT_INIT_CHILD')
    scope, pin = new_scope(base, core, old_scope)
    need(child.get('new_scope') == pin and value.get('new_scope') == pin and base.pinned(pin), 'UNCHANGED_INITIALIZED_SCOPE_BYTES')
    need(set(os.listdir(Path(FLOW) / 'steps')) == set() and set(os.listdir(Path(FLOW) / 'reconciliations')) == set() and
         not os.path.lexists(Path(FLOW) / 'launch-attempted.json') and
         not os.path.lexists(Path(FLOW) / 'launch-scope.json'), 'NO_NEW_FLOW_STEP_OR_LAUNCH_REPLAY')
    return scope


def invoke_original(recorder, base, operation):
    argv = [base.RECORDER['path'], operation, '--adapter-manifest-sha256', base.MANIFEST_SHA, '--flow-dir', FLOW]
    if operation == 'init':
        argv += ['--current-baseline', BASELINE, '--baseline-sha256', BASELINE_SHA,
                 '--package', base.PACKAGE, '--component', COMPONENT]
    else:
        argv += ['--step', STEP]
    saved, output, code = sys.argv, io.StringIO(), None
    try:
        sys.argv = argv
        with contextlib.redirect_stdout(output):
            try:
                recorder.main(); code = 0
            except SystemExit as error:
                code = error.code
    finally:
        sys.argv = saved
    return code, output.getvalue().encode('utf-8'), argv


def verify_launch(base, core, recorder, original_stdout, scope):
    value = core.document(original_stdout)
    need(value.get('ok') is True and value.get('native_launch_acknowledged') is True and
         value.get('cleanup_allowed') is True and value.get('action_attempted') is True and
         value.get('outcome_unknown') is False and value.get('automatic_retry') is False and
         value.get('business_success_verified') is False and value.get('epoch_sha256') == base.EPOCH,
         'ORIGINAL_NATIVE_LAUNCH_ACKNOWLEDGED_EXACTLY')
    folder = Path(FLOW) / 'steps' / STEP
    saved_result, _ = base.read(folder / 'result.json')
    need(core.document(saved_result) == value, 'ORIGINAL_LAUNCH_STDOUT_AND_FILE')
    intent = core.document(base.read(folder / 'intent.json')[0])
    need(intent.get('operation') == 'launch' and intent.get('mutation') is True and intent.get('scope') == scope and
         all(intent.get(k) is None for k in ('request', 'unknown_step', 'observation_step', 'postcondition')) and
         intent.get('automatic_retry') is False, 'ONLY_ORIGINAL_NATIVE_LAUNCH_OPERATION')
    selected_raw, _ = base.read(Path(FLOW) / 'launch-scope.json'); selected = core.document(selected_raw)
    task = selected.get('task')
    need(type(task) is int and task > 0 and selected.get('package') == base.PACKAGE and
         selected.get('epoch_sha256') == base.EPOCH and selected.get('prelaunch_absent') is True and
         selected.get('cleanup_allowed') is True and selected.get('launch_step') == STEP,
         'ACTUAL_NEW_NATIVE_TASK_NOT_OLD_OWNERSHIP')
    tasks_source = recorder.task_functions(Path(base.RECORDER['path']).parent / 'references/task_scope_baseline.py')
    binding = core.document(base.read(folder / 'held-main-binding.json')[0]); core.held_binding_identity(binding)
    contract = recorder.source_contract(base.MANIFEST_SHA)[1]
    transport = contract.load('bound_android_transport.py', 'unchanged_new_launch_transport_checks')
    need(sorted(p.name for p in folder.glob('command-*.intent.json')) ==
         ['command-001.intent.json', 'command-002.intent.json', 'command-003.intent.json'], 'EXACT_THREE_ORIGINAL_LAUNCH_COMMANDS')
    command_rows, parsed, authority = [], {}, None
    native = ['/usr/bin/sudo', '-n', '-u', '#1000', '--', '/usr/bin/env', 'XDG_RUNTIME_DIR=/run/user/1000',
              'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus', '/usr/bin/droidloomctl', 'launch', base.PACKAGE,
              '--component', COMPONENT, '--json']
    for index in (1, 2, 3):
        stem = 'command-%03d' % index
        ci = core.document(base.read(folder / (stem + '.intent.json'))[0])
        cr_raw, _ = base.read(folder / (stem + '.result.json')); cr = core.document(cr_raw)
        out, _ = base.read(folder / (stem + '.stdout')); err, _ = base.read(folder / (stem + '.stderr'))
        if index == 2:
            need(ci.get('argv') == ci.get('execution_argv') == native and ci.get('authority_fds_passed') == [] and
                 ci.get('label') == 'One native launch' and ci.get('mutation') is True and ci.get('timeout_seconds') == 70 and
                 ci.get('automatic_retry') is False and cr.get('returncode') == 0 and cr.get('spawned') is True and
                 cr.get('owned_command_joined') is True and cr.get('timed_out') is False and cr.get('errors') == [] and
                 cr.get('error') is None and cr.get('action_attempted') is True and cr.get('automatic_retry') is False and
                 cr.get('stdout_sha256') == sha(out) and cr.get('stderr_sha256') == sha(err) and err == b'',
                 'ONE_EXACT_NATIVE_COMMAND_JOIN_AND_ORIGINAL_RAW')
            receipt = core.document(out)
            match = re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)', receipt.get('launch', ''))
            need(receipt.get('ok') is True and receipt.get('state') == 'running' and receipt.get('outcome_unknown') is not True and
                 match is not None and int(match[3]) == 0 and int(match[4]) == task and
                 selected.get('native_receipt_sha256') == sha(out), 'ACTUAL_NATIVE_RECEIPT_TASK_AND_HASH')
            native_identity = {'object': int(match[1]), 'composer_display': int(match[2]), 'android_display': int(match[3]),
                               'task': task, 'host_pid': receipt['host_pid'], 'receipt_sha256': sha(out)}
        else:
            argv = ['/system/bin/cmd', 'activity', 'stack', 'list']
            core.command_success(ci, cr, out, err, False, 20)
            route = core.command_argv(ci, argv, 20,
                '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry', binding['classpath']['values'], transport)
            need(route['parent_pid'] == os.getpid() and (authority is None or authority == route), 'ONE_NEW_LAUNCH_HELD_AUTHORITY')
            authority = route; sequence = 1 if index == 1 else 2
            ti = core.document(base.read(folder / ('transport-%03d.intent.json' % sequence))[0])
            tc = core.document(base.read(folder / ('transport-%03d.command-result.json' % sequence))[0])
            tv = core.document(base.read(folder / ('transport-%03d.verified-result.json' % sequence))[0])
            identity = {'sequence': sequence, 'epoch_sha256': base.EPOCH, 'package': base.PACKAGE, 'uid': 10143,
                'command_sha256': sha(json.dumps(argv, ensure_ascii=False, separators=(',', ':')).encode()),
                'timeout_seconds': 20, 'inner_timeout_seconds': 15, 'automatic_retry': False, 'numeric_pid_target_used': False}
            need(ti == identity and tc == tv and all(tc.get(k) == v for k, v in identity.items()) and tc.get('returncode') == 0 and
                 tc.get('outcome_unknown') is False and tc.get('stdout_sha256') == sha(out) and tc.get('stderr_sha256') == sha(err),
                 'NEW_LAUNCH_READ_LEASE_RELEASE_AND_POST_GUARD')
            parsed[index] = tasks_source.parse_stacks(out.decode('utf-8', 'strict'))
        command_rows.append({'index': index, 'mutation': index == 2, 'returncode': 0, 'joined': True,
                             'stdout_bytes': len(out), 'stdout_sha256': sha(out), 'command_result_sha256': sha(cr_raw)})
    before_roots, before_tasks = parsed[1]; after_roots, after_tasks = parsed[3]
    need(876 not in before_tasks and 876 not in before_roots and task not in before_tasks and task not in before_roots and
         not any(child['component'].split('/')[0] == base.PACKAGE for root in before_roots.values() for child in root['children']) and
         tasks_source.exact_leaf(after_roots, task, base.PACKAGE) and after_tasks == before_tasks | {task} and
         selected.get('prelaunch_task_ids') == sorted(before_tasks), 'CURRENT_NO_BEIKE_AND_REAL_NEW_TASK_OTHER_TASKS_PRESERVED')
    return {'task': task, 'native_identity': native_identity, 'launch_scope_sha256': sha(selected_raw),
            'result_sha256': sha(saved_result), 'prelaunch_task_ids': sorted(before_tasks), 'postlaunch_task_ids': sorted(after_tasks),
            'command_evidence': command_rows, 'raw_stacks_exported': False, 'old_task_ownership_transferred': False}


def child(operation):
    base = entry('--child-' + operation)
    need(sys.stdin.buffer.read(1) == b'R', 'PARENT_HELD_PIDFD_BEFORE_RELEASE')
    result = {'schema': 'pocket4-original-new-session-owned-child-v1', 'operation': operation, 'flow': FLOW, 'source': SELF,
        'ok': False, 'errors': [], 'original_recorder_invoked': False, 'original_recorder_modified': False,
        'UI_input_actions': 0, 'instrumentation_calls': 0, 'permission_changes': 0, 'App_installs': 0,
        'old_unknown_rewritten': False, 'old_click_replayed': False, 'reconciliation_published': False,
        'production_ready': False, 'automatic_retry': False, 'owned_QA_helper_runtime_revalidated': False,
        'requires_parent_pidfd_exit_and_durable_terminal': True}
    try:
        support = base.load(base.SUPPORT, 'unchanged_library_bootstrap')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_owned_child_probe')
        observed = support.probe_proof(); _, frozen, library_fd, library = support.initialize_library(probe, observed)
        core = base.load(base.CORE, 'unchanged_evidence_validation_only')
        recorder = base.load(base.RECORDER, 'unchanged_actual_recorder')
        bodies, identities, old_scope = predecessor(base, core)
        if operation == 'init':
            need(not os.path.lexists(FLOW) and not os.path.lexists(Path(ROOT) / 'init-owned-lifetime.json'), 'NEW_FLOW_AND_INIT_ONCE_ONLY')
        else:
            accepted_init(base, core, old_scope)
        need(probe.same_descriptors(frozen, probe.census()), 'NO_PRE_STEP_UNKNOWN_FD')
        result['original_recorder_invoked'] = True
        code, raw, argv = invoke_original(recorder, base, operation)
        result.update(original_recorder_returncode=code, original_recorder_stdout=raw.decode('utf-8'),
                      original_recorder_stdout_sha256=sha(raw), original_recorder_stdout_bytes=len(raw), original_argv=argv)
        need(code == 0 and raw.endswith(b'\n') and len(raw.splitlines()) == 1, 'ORIGINAL_RECORDER_ZERO_SINGLE_RESULT')
        scope, scope_pin = new_scope(base, core, old_scope)
        if operation == 'init':
            need(core.document(raw) == {'ok': True, 'scope_initialized': True, 'epoch_sha256': base.EPOCH}, 'ACTUAL_ORIGINAL_INIT_RESULT')
            need(set(os.listdir(FLOW)) == {'flow.lock', 'baseline.json', 'baseline-qualification.json', 'scope.json', 'steps', 'reconciliations'} and
                 not os.listdir(Path(FLOW) / 'steps') and not os.listdir(Path(FLOW) / 'reconciliations'), 'ONLY_ORIGINAL_NEW_FLOW_LAYOUT')
            source, _ = recorder.source_contract(base.MANIFEST_SHA); source.verify_saved_baseline(Path(FLOW))
        else:
            result['launch'] = verify_launch(base, core, recorder, raw, scope)
        base.preserved(bodies, identities)
        need(sha(base.read(Path(base.FLOW) / 'steps' / base.STEP / 'result.json')[0]) == CLEANUP_RESULT_SHA,
             'ORIGINAL_CLEANUP_RESULT_RETAINED')
        for pin in (SELF, BASE, CLEANUP_STDOUT, CLEANUP_TERMINAL, base.RECORDER, base.CORE, base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed)
        lock_raw, lock_metadata = base.read(Path(FLOW) / 'flow.lock', 65536)
        need(lock_raw == b'' and stat.S_IMODE(lock_metadata['st_mode']) == 0o600, 'NEW_ORIGINAL_FLOW_LOCK_IDENTITY')
        final = probe.census(); extra = set(final) - set(frozen)
        need(len(extra) == 1 and probe.same_descriptors(frozen, {k: v for k, v in final.items() if k in frozen}),
             'ONLY_ORIGINAL_EXPLICIT_NEW_FLOW_LOCK_MAY_REMAIN')
        held = final[next(iter(extra))]
        need(held['link'] == FLOW + '/flow.lock' and held['fstat'] == lock_metadata and held['descriptor_flags'] == 1 and
             held['status_flags'] & os.O_ACCMODE == os.O_RDWR and
             support.stable_library(probe.library_binding(library_fd, final[str(library_fd)])) == support.stable_library(library),
             'EXACT_NEW_FLOW_LOCK_AND_FROZEN_LIBRARY_RESOURCE')
        result.update(ok=True, new_scope=scope_pin, old_close_outcome='unknown_retained',
            old_original_files_preserved=177, old_original_bytes_preserved=888207, final_descriptors=final,
            original_namespace_authority_released=True, flow_lock_and_library_retire_at_normal_process_exit=True,
            unknown_descriptors_closed=0, manual_library_close=False)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    result['outcome_unknown'] = result['original_recorder_invoked'] and not result['ok']
    raw = canonical(result); need(len(raw) <= 131072, 'CHILD_RESULT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


def publish_once(base, path, raw):
    """An artifact is not accepted without this job's complete durable zero exit."""
    need(path == ROOT + '/init-owned-lifetime.json' or path == ROOT + '/launch-owned-lifetime.json', 'FIXED_JOINT_ARTIFACT_PATH')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view); need(count > 0, 'ARTIFACT_WRITE_PROGRESS'); view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    directory = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    need(base.read(path)[0] == raw, 'EXACT_JOINT_ARTIFACT_READBACK')
    return {'path': path, 'bytes': len(raw), 'sha256': sha(raw)}


def parent(operation):
    base = entry('--' + operation + '-once')
    result = {'schema': 'pocket4-original-new-session-owned-result-v1', 'operation': operation, 'flow': FLOW, 'source': SELF,
        'ok': False, 'errors': [], 'automatic_retry': False, 'old_unknown_rewritten': False,
        'reconciliation_published': False, 'production_ready': False, 'UI_input_actions': 0, 'permission_changes': 0,
        'old_build_or_App_data_deleted': False, 'acceptance_requires_original_stdout_and_authoritative_durable_terminal': True}
    invoked = False
    try:
        support = base.load(base.SUPPORT, 'unchanged_owned_library_functions')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_pidfd_lifetime_functions')
        observed = support.probe_proof(); support.pin_runtime_files(probe, observed)
        before = probe.census(); need(set(before) == {'0', '1', '2'}, 'PARENT_INITIAL_STDIO_ONLY')
        argv = [sys.executable, '-I', '-B', SELF['path'], '--child-' + operation, '--source-sha256', SELF['sha256'],
                '--source-bytes', str(SELF['bytes'])]
        if operation == 'launch':
            base.pinned(INIT)
            argv += ['--init-proof-sha256', INIT['sha256'], '--init-proof-bytes', str(INIT['bytes'])]
        invoked = True
        life, raw, stderr = probe.run_owned_child(argv, seconds=240)
        result.update(child_lifecycle=life, child_stdout_original=raw.decode('utf-8', 'strict'), child_stdout_bytes=len(raw),
            child_stdout_sha256=sha(raw), child_stderr_original=stderr.decode('utf-8', 'replace'),
            child_stderr_bytes=len(stderr), child_stderr_sha256=sha(stderr))
        value = json.loads(raw); base.require_owned_exit(life, stderr)
        need(value.get('schema') == 'pocket4-original-new-session-owned-child-v1' and value.get('operation') == operation and
             value.get('flow') == FLOW and value.get('source') == SELF and value.get('ok') is True and value.get('errors') == [] and
             value.get('outcome_unknown') is False and value.get('old_close_outcome') == 'unknown_retained',
             'SUCCESS_AND_NORMAL_CHILD_EXIT_JOINTLY_REQUIRED')
        for pin in (SELF, BASE, CLEANUP_STDOUT, CLEANUP_TERMINAL, base.RECORDER, base.CORE, base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed)
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_RESTORED')
        result.update(ok=True, outcome_unknown=False, new_scope=value['new_scope'], old_close_outcome='unknown_retained',
            all_owned_child_resources_retired_by_normal_pidfd_exit=True, source_or_old_result_modified=False)
        if operation == 'launch':
            result['launch'] = value['launch']
        else:
            result['native_launches'] = 0
        artifact = publish_once(base, ROOT + '/' + operation + '-owned-lifetime.json', canonical(result) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_AFTER_ARTIFACT')
        result['joint_artifact'] = artifact
    except BaseException as error:
        result['ok'] = False
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    result['outcome_unknown'] = invoked and not result['ok']
    raw = canonical(result); need(len(raw) <= 262144, 'PARENT_RESULT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    mode = sys.argv[1:2]
    if mode == ['--child-init']:
        raise SystemExit(child('init'))
    if mode == ['--child-launch']:
        raise SystemExit(child('launch'))
    need(mode in (['--init-once'], ['--launch-once']), 'CLOSED_NEW_SESSION_OPERATION')
    raise SystemExit(parent('init' if mode == ['--init-once'] else 'launch'))
