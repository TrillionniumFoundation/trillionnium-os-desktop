#!/usr/bin/env python3
"""Read one completed private inspect. No live target API or file mutation.

Only the fixed historical task-878 step and its actual owned-lifetime artifact
are read. The original pure wire parser recomputes its assessment. Output may
contain private UI node text and MUST NOT be committed to Git. This is not a
current foreground observation or authority to perform a new action.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

# Filled once from exact local original source/evidence by prepare_packet.py.
BASE = {'path': '/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1/cleanup_owned_task_once.py', 'bytes': 22233, 'sha256': '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'}
CORE = {'path': '/home/alex/work/pocket4-beike-owned-postcondition-20261106-baaf68ac0d617dbe3894f714b18f099b/owned_postcondition_core.py', 'bytes': 28714, 'sha256': '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41'}
QA = {'path': '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/qa_contract.py', 'bytes': 52359, 'sha256': 'bfe1e781e254033ab5c5b7616a928d309998bde4cbc243bd542c3eb4805eda6e'}
TRANSPORT = {'path': '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder/bound_android_transport.py', 'bytes': 15603, 'sha256': '069d003809d95b33e0d727fdec3ca6e8488e214180449cacbad07e66a302652f'}
UI_SOURCE = {'bytes': 25377, 'path': '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/owned_ui_request_once.py', 'sha256': 'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38'}
JOINT = {'bytes': 13629, 'path': '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/result-92bd97c8f6b868168fc98520b4e4908103843bfdb689e7f80c06f51002abab73.json', 'sha256': '7ad76e72aa20919fa8695899c27233b89a9794e0446379db9f282553b671f9dc'}
STEP_RESULT = {'bytes': 6362, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/result.json', 'sha256': '4979b991b411d2d5f2eca82e5130faeef871a1796d0bd5502aeef18c468fd8b9'}
SCOPE = {'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/scope.json', 'bytes': 1002, 'sha256': '08c014646be1d32ef9eacc119f7930b941fc696333bd4cff9d74106f19dba516'}
PLAN = {'bytes': 178, 'path': '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/qa-inspect-new-session-01.plan.json', 'sha256': 'd8d1e4b0202d25d9fe824b54e8d480d26d5edec3eabbd70f61a342034f3468e7'}
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
STEP = 'inspect-new-session-01'
FOLDER = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01'
JOB = '1a1b2537fa5-fc05-7d8c'
EPOCH = '7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c'
NONCE = '8f3efa4249d24d303984ec1887d5914b'
WIRE = 'cb49f560bdc90f13fa5a314019e4f2948d4c9e63e3b62571c8f0a4cc37fe4647'
ACTUAL_STDOUT_SHA = '11a958010bb7dbaa4865385018a72fef9d6abe12b378805da84f3006fd4f25c3'
TERMINAL_SHA = '9333a1e8b841f253216b6d2ef48f393eba418a90f0283ae2ec35a9fe67dd697c'
CHILD_SHA = 'c2f1b0df1642c12051a42ef003513aa1637f4396e1e0f3cdc457d173151c2fc6'
ADAPTER_STDOUT_SHA = 'fa0d8966f92122fc32b161b3e19f88ba86bc6cf4a5971e9359c13bc82af8b302'
LAUNCH_SCOPE_SHA = '54a669eb54fa0dcf6df5afcd17848af7511c2122623192051eb6370e42bfbb06'
NATIVE_RECEIPT_SHA = 'e1b09112b1be1ec8095cd5b7049131e0e8bd13ad8b4e38803e3c19d02e5e65a3'
HELD_HELPER = '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry'
EXPECTED_PLAN = {'schema': 1, 'operation': 'inspect', 'nonces': {'before': '82180d7421b8885c91cc382bceb85cb1', 'inspect': '8f3efa4249d24d303984ec1887d5914b', 'after': '2c14c0876063e1296f439eb3445151e4'}}
STAGE_STDOUT = b'{"Main_commands": 0, "Main_locks_or_guards": 0, "files": {"launch.stdout.original.jsonl": {"bytes": 8339, "sha256": "8a9a32bb54dad115d49fdc814ba10337cba43a04144c621f3a4d0a405b8db211"}, "launch.terminal.original.json": {"bytes": 731, "sha256": "96292fcfeed27a538996f05b924feefc963d4f304759ea8423295e82c2380579"}, "owned_ui_request_once.py": {"bytes": 25377, "sha256": "c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38"}, "request-92bd97c8f6b868168fc98520b4e4908103843bfdb689e7f80c06f51002abab73.json": {"bytes": 400, "sha256": "92bd97c8f6b868168fc98520b4e4908103843bfdb689e7f80c06f51002abab73"}}, "mode": "readonly-inspect-not-yet-invoked", "namespace_entries": 0, "private_bundle_copied": false, "reconciliation_published": false, "root": "/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1", "schema": "pocket4-fixed-owned-ui-stage-v1", "whole_process_fd_identities_unchanged": true}\n'
TERMINAL_RAW = b'{\n  "at_unix_ms": 1793993194110,\n  "audit_recorded": true,\n  "automatic_retry": false,\n  "cancelled": false,\n  "exit_code": 0,\n  "job_id": "1a1b2537fa5-fc05-7d8c",\n  "launch_nonce": "4c6a5761fba59d1533e422c50d38f8d9",\n  "log_bytes": {\n    "stderr": {\n      "seen": 0,\n      "stored": 0\n    },\n    "stdout": {\n      "seen": 14794,\n      "stored": 14794\n    }\n  },\n  "log_errors": {\n    "stderr": null,\n    "stdout": null\n  },\n  "log_synced": {\n    "stderr": true,\n    "stdout": true\n  },\n  "log_truncated": {\n    "stderr": false,\n    "stdout": false\n  },\n  "output_complete": true,\n  "output_durable": true,\n  "state": "succeeded",\n  "terminal_publication_confirmed": true,\n  "terminal_publication_protocol": 1,\n  "timed_out": false\n}'
ALLOWED_PATHS = frozenset(['/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1/cleanup_owned_task_once.py', '/home/alex/work/pocket4-beike-owned-postcondition-20261106-baaf68ac0d617dbe3894f714b18f099b/owned_postcondition_core.py', '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/owned_ui_request_once.py', '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1/result-92bd97c8f6b868168fc98520b4e4908103843bfdb689e7f80c06f51002abab73.json', '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/qa_contract.py', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/launch-scope.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/qa-inspect-new-session-01.plan.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/scope.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/8f3efa4249d24d303984ec1887d5914b.assessment.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/8f3efa4249d24d303984ec1887d5914b.request.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/command-005.intent.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/command-005.result.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/command-005.stderr', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/command-005.stdout', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/held-main-binding.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/intent.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/result.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/transport-006.command-result.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/transport-006.intent.json', '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe/steps/inspect-new-session-01/transport-006.verified-result.json', '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder/bound_android_transport.py'])


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


# Exact previously executed no-follow bootstrap, inserted from frozen source.
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


def census():
    """Close listdir's transient directory FD before inspecting persistent FDs."""
    names = os.listdir('/proc/self/fd')
    rows = {}
    for name in sorted(names, key=int):
        need(name.isdigit(), 'PROC_FD_NAME')
        fd = int(name)
        try:
            first = os.fstat(fd)
        except OSError as error:
            # listdir's own already-closed descriptor is the sole allowed skip.
            need(error.errno == 9 and not os.path.lexists('/proc/self/fd/' + name),
                 'FD_CENSUS_UNSTABLE_OR_REUSED')
            continue
        link = os.readlink('/proc/self/fd/' + name)
        flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        after = os.fstat(fd)
        identity = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_rdev')
        need(all(getattr(first, key) == getattr(after, key) for key in identity) and
             link == os.readlink('/proc/self/fd/' + name) and
             flags == fcntl.fcntl(fd, fcntl.F_GETFD), 'FD_CHANGED_DURING_CENSUS')
        rows[name] = {'link': link, 'flags': flags,
                      **{key: getattr(first, key) for key in identity}}
    return rows


def project_nodes(inspection):
    """No additional truncation; redact neither by guessing nor by field names."""
    fields = ('path', 'node_sha256', 'package', 'resource_id', 'resource_id_sha256',
              'resource_id_truncated', 'class', 'class_sha256', 'class_truncated',
              'text', 'text_sha256', 'text_truncated', 'content_desc',
              'content_desc_sha256', 'content_desc_truncated', 'visible',
              'password', 'enabled', 'clickable', 'editable', 'supports_set_text',
              'focused', 'selected', 'checked', 'child_count', 'bounds')
    selected = []
    omitted = 0
    for node in inspection['nodes']:
        need(type(node.get('visible')) is bool and type(node.get('password')) is bool,
             'RECORDED_NODE_VISIBILITY_AND_PASSWORD_TYPES')
        if node['visible'] is not True or node['password'] is not False:
            omitted += 1
            continue
        need(node.get('content_redacted') is not True, 'VISIBLE_NODE_CONTENT_IS_REDACTED')
        for name in ('resource_id', 'class', 'text', 'content_desc'):
            need(type(node.get(name)) is str and type(node.get(name + '_truncated')) is bool,
                 'ORIGINAL_STRING_AND_TRUNCATION_FLAG_REQUIRED')
        row = {key: node[key] for key in fields if key in node}
        row['usable_exact_selector_fields'] = [key for key in ('resource_id', 'class', 'text', 'content_desc')
            if node[key] and node[key + '_truncated'] is False]
        row['all_four_string_fields_untruncated'] = all(
            node[key + '_truncated'] is False for key in ('resource_id', 'class', 'text', 'content_desc'))
        selected.append(row)
    need(len(selected) + omitted == len(inspection['nodes']) <= 512, 'COMPLETE_NODE_PROJECTION_BOUND')
    return selected, omitted


def run():
    need(os.getuid() == os.geteuid() == 0 and sys.argv == ['-c'], 'EXACT_ROOT_HOST_READER_ENTRY')
    before = census()
    end = time.monotonic() + 90
    base = load_base()
    observed = {}
    total = 0

    def read_path(path, pin=None):
        nonlocal total
        need(path in ALLOWED_PATHS and path not in observed and time.monotonic() < end,
             'FIXED_FINITE_READ_SET_AND_TOTAL_DEADLINE')
        raw, identity = base.read(path, maximum=2 * 1024 * 1024)
        need(time.monotonic() < end, 'HOST_TOTAL_DEADLINE')
        total += len(raw)
        need(total <= 4 * 1024 * 1024, 'ALL_SELECTED_FILES_TOTAL_BOUND')
        if pin is not None:
            need(pin['path'] == path and len(raw) == pin['bytes'] and sha(raw) == pin['sha256'],
                 'EXACT_HISTORICAL_FILE_PIN')
        observed[path] = (raw, identity)
        return raw

    def module(pin, name):
        raw = read_path(pin['path'], pin)
        value = types.ModuleType(name)
        value.__file__ = pin['path']
        exec(compile(raw, pin['path'], 'exec'), value.__dict__)
        return value

    read_path(BASE['path'], BASE)
    core = module(CORE, 'exact_offline_evidence_definitions')
    qa = module(QA, 'exact_offline_owned_wire_contract')
    transport = module(TRANSPORT, 'exact_transport_environment_validation_only')
    read_path(UI_SOURCE['path'], UI_SOURCE)
    joint_raw = read_path(JOINT['path'], JOINT)
    joint = core.document(joint_raw)
    need(joint_raw == canonical(joint) + b'\n', 'ACTUAL_JOINT_CANONICAL_ORIGINAL_BYTES')
    actual_stdout = STAGE_STDOUT + canonical({**joint, 'joint_artifact': JOINT}) + b'\n'
    need(len(actual_stdout) == 14794 and sha(actual_stdout) == ACTUAL_STDOUT_SHA,
         'EXACT_RECONSTRUCTED_ACTUAL_STDOUT_FROM_PINNED_JOINT_AND_STAGE')
    need(len(TERMINAL_RAW) == 733 and sha(TERMINAL_RAW) == TERMINAL_SHA,
         'EMBEDDED_ORIGINAL_TERMINAL_BYTES')
    terminal = core.document(TERMINAL_RAW)
    need(terminal.get('job_id') == JOB and terminal.get('state') == 'succeeded' and
         terminal.get('exit_code') == 0 and all(terminal.get(key) is True for key in
         ('audit_recorded', 'output_complete', 'output_durable', 'terminal_publication_confirmed')) and
         all(terminal.get(key) is False for key in ('timed_out', 'cancelled', 'automatic_retry')) and
         terminal.get('log_bytes') == {'stdout': {'seen': 14794, 'stored': 14794},
                                      'stderr': {'seen': 0, 'stored': 0}} and
         terminal.get('log_synced') == {'stdout': True, 'stderr': True} and
         terminal.get('log_truncated') == {'stdout': False, 'stderr': False} and
         terminal.get('log_errors') == {'stdout': None, 'stderr': None},
         'ACTUAL_COMPLETED_DURABLE_ZERO_WITH_ALL_ORIGINAL_STDOUT')
    need(joint.get('schema') == 'pocket4-fixed-reusable-owned-ui-result-v1' and
         joint.get('ok') is True and joint.get('errors') == [] and joint.get('flow') == FLOW and
         joint.get('step') == STEP and joint.get('task') == 878 and joint.get('kind') == 'plan' and
         joint.get('source') == UI_SOURCE and joint.get('original_result') == STEP_RESULT and
         joint.get('all_owned_child_resources_retired_by_normal_pidfd_exit') is True and
         joint.get('original_old_close_outcome') == 'unknown_retained' and
         all(joint.get(key) is False for key in ('outcome_unknown', 'original_UNKNOWN_rewritten',
         'original_action_attempted', 'original_action_outcome_unknown', 'automatic_retry',
         'reconciliation_published', 'production_ready', 'allows_new_mutation_without_original_Flow_checks')),
         'EXACT_ACTUAL_COMPLETED_READONLY_OWNED_SEQUENCE')
    need(joint['child_lifecycle']['child_pid'] == 1308652 and joint['child_stderr_original'] == '' and
         joint['child_stderr_bytes'] == 0 and joint['child_stderr_sha256'] == sha(b''),
         'ACTUAL_HISTORICAL_OWNED_CHILD_AND_EMPTY_STDERR')
    base.require_owned_exit(joint['child_lifecycle'], b'')
    child_raw = joint['child_stdout_original'].encode('utf-8')
    need(len(child_raw) == joint['child_stdout_bytes'] == 10622 and
         sha(child_raw) == joint['child_stdout_sha256'] == CHILD_SHA, 'EXACT_ACTUAL_CHILD_STDOUT')
    child = core.document(child_raw)
    need(child.get('schema') == 'pocket4-fixed-reusable-owned-ui-child-v1' and child.get('ok') is True and
         child.get('errors') == [] and child.get('original_returncode') == 0 and
         child.get('original_result') == STEP_RESULT and child.get('flow') == FLOW and
         child.get('step') == STEP and child.get('task') == 878 and child.get('declared_mutation') is False,
         'ORIGINAL_READONLY_CHILD_PROTOCOL')
    adapter_raw = child['original_stdout'].encode('utf-8')
    need(len(adapter_raw) == child['original_stdout_bytes'] == 5752 and
         sha(adapter_raw) == child['original_stdout_sha256'] == ADAPTER_STDOUT_SHA,
         'ORIGINAL_ADAPTER_STDOUT_BYTES')
    result = core.document(read_path(STEP_RESULT['path'], STEP_RESULT))
    need(result == core.document(adapter_raw) and result.get('ok') is True and
         result.get('error') is None and result.get('secondary_errors') == [] and
         result.get('epoch_sha256') == EPOCH and result.get('inspection_wire_sha256') == WIRE and
         all(result.get(key) is False for key in ('action_attempted', 'outcome_unknown',
         'automatic_retry', 'whole_app_production_ready', 'business_success_verified', 'old_v2_helper_called')) and
         all(result.get(key) is True for key in ('after_state_attempted', 'after_state_completed',
         'restoration_qualified', 'post_state_matches_before')), 'UNCHANGED_SUCCESSFUL_ORIGINAL_INSPECT_RESULT')
    build = core.fixed_build(result['build'])
    core.installed_identity(result['installed_before'], build)
    need(result['installed_before'] == result['installed_after'] and
         result['installed_before']['uid'] == 10157 and result['installed_before']['bytes'] == 37008,
         'HISTORICAL_HELPER_IDENTITY_AND_VERSION')
    scope = core.fixed_scope(core.document(read_path(SCOPE['path'], SCOPE)))
    launch_raw = read_path(FLOW + '/launch-scope.json')
    need(sha(launch_raw) == LAUNCH_SCOPE_SHA, 'EXACT_TASK878_LAUNCH_SCOPE_BYTES')
    launch = core.document(launch_raw)
    need(launch == result['owned_task'] and launch.get('task') == 878 and
         launch.get('package') == qa.PACKAGE and launch.get('epoch_sha256') == EPOCH and
         launch.get('native_receipt_sha256') == NATIVE_RECEIPT_SHA and
         launch.get('prelaunch_absent') is True and launch.get('cleanup_allowed') is True,
         'NO_OLD_TASK876_OR_OTHER_TASK_SUBSTITUTION')
    plan_raw = read_path(PLAN['path'], PLAN)
    plan = core.document(plan_raw)
    need(plan == EXPECTED_PLAN and child['input_artifact'] == PLAN and
         result['plan_sha256'] == PLAN['sha256'], 'ONLY_THIS_COMPLETED_READONLY_PLAN')

    def step_file(name):
        return read_path(FOLDER + '/' + name)

    intent = core.document(step_file('intent.json'))
    need(intent.get('operation') == 'owned-qa' and intent.get('mutation') is False and
         intent.get('scope') == scope and intent.get('automatic_retry') is False and
         all(intent.get(key) is None for key in ('unknown_step', 'observation_step', 'postcondition')) and
         intent.get('request') == {'plan': plan, 'plan_sha256': PLAN['sha256'], 'owned_build': build},
         'ORIGINAL_STEP_INTENT_PLAN_AND_SCOPE')
    binding = core.document(step_file('held-main-binding.json'))
    core.held_binding_identity(binding)
    need(binding.get('framework_epoch_sha256') == EPOCH and
         binding.get('runtime_epoch_sha256') == qa.RUNTIME_EPOCH and
         binding.get('app_scope_sha256') == qa.APP_SCOPE_SHA and
         binding.get('package') == qa.PACKAGE and binding.get('uid') == qa.UID and
         binding.get('ui_actions_performed_by_binding') is False and binding.get('production_ready') is False and
         binding['target'].get('pidfd_held') is True and
         binding['target'].get('numeric_target_used_for_entry') is False, 'HISTORICAL_RECORDED_HELD_R5_IDENTITY')
    front = qa.scope(result['foreground_before'])
    need(front == result['foreground_after'] and front['window_token'] == 'c1a867e' and
         front['activity'] == 'com.lianjia.beike/com.lianjia.activity.MainActivity',
         'EXACT_HISTORICAL_FOREGROUND_NOT_A_CURRENT_CHECK')
    expected_request = {'protocol': qa.PROTOCOL, 'nonce': NONCE, 'op': 'inspect', 'scope': front}
    request_raw = step_file(NONCE + '.request.json')
    request = core.document(request_raw)
    need(request == expected_request, 'EXACT_HISTORICAL_INSPECTION_NONCE_AND_SCOPE')
    argv = qa.instrumentation_argv(request)
    ci = core.document(step_file('command-005.intent.json'))
    command_raw = step_file('command-005.result.json')
    cr = core.document(command_raw)
    out, err = step_file('command-005.stdout'), step_file('command-005.stderr')
    core.command_success(ci, cr, out, err, False, 20)
    route = core.command_argv(ci, argv, 20, HELD_HELPER, binding['classpath']['values'], transport)
    need(route['parent_pid'] == 1308652, 'ONLY_THE_ACTUAL_ORIGINAL_OWNED_CHILD_AUTHORITY')
    ti = core.document(step_file('transport-006.intent.json'))
    tc = core.document(step_file('transport-006.command-result.json'))
    tv = core.document(step_file('transport-006.verified-result.json'))
    identity = {'sequence': 6, 'epoch_sha256': EPOCH, 'package': qa.PACKAGE, 'uid': qa.UID,
        'command_sha256': sha(json.dumps(argv, ensure_ascii=False, separators=(',', ':')).encode('utf-8')),
        'timeout_seconds': 20, 'inner_timeout_seconds': 15,
        'automatic_retry': False, 'numeric_pid_target_used': False}
    need(ti == identity and tc == tv and all(tc.get(key) == value for key, value in identity.items()) and
         set(tc) == set(identity) | {'returncode', 'stdout_bytes', 'stderr_bytes', 'stdout_sha256',
                                    'stderr_sha256', 'action_attempted', 'outcome_unknown'} and
         type(tc.get('returncode')) is int and tc['returncode'] == 0 and
         tc['action_attempted'] is True and tc['outcome_unknown'] is False and
         tc['stdout_bytes'] == len(out) and tc['stderr_bytes'] == 0 and
         tc['stdout_sha256'] == sha(out) and tc['stderr_sha256'] == sha(err),
         'ORIGINAL_COMMAND_RETURN_LEASE_RELEASE_AND_POST_GUARD_RECEIPT')
    assessment_raw = step_file(NONCE + '.assessment.json')
    assessment = qa.parse_completed(out, err, cr['returncode'], request, 10157)
    assessment['recorder_command_result_sha256'] = sha(command_raw)
    assessment['held_transport_returned_after_post_guard'] = True
    need(core.document(assessment_raw) == assessment and assessment['wire_sha256'] == WIRE and
         sha(qa.canonical(assessment['helper'])) == WIRE, 'ORIGINAL_ASSESSMENT_RECOMPUTED_FROM_ACTUAL_RAW')
    inspection = qa.inspect_record(assessment['helper']['inspection'])
    nodes, omitted = project_nodes(inspection)
    need(set(observed) == ALLOWED_PATHS, 'ALL_AND_ONLY_FIXED_HOST_FILES_READ')
    for path, (raw, identity) in observed.items():
        need(time.monotonic() < end, 'FINAL_RECHECK_TOTAL_DEADLINE')
        again, current = base.read(path, maximum=2 * 1024 * 1024)
        need(again == raw and current == identity and time.monotonic() < end,
             'ORIGINAL_FILE_BYTES_OR_IDENTITY_CHANGED_DURING_READ')
    after = census()
    need(after == before, 'WHOLE_PROCESS_FD_IDENTITIES_MUST_BE_RESTORED')
    result = {'schema': 'pocket4-completed-task878-inspection-private-selector-read-v1', 'ok': True,
        'historical_job': JOB, 'historical_stdout': {'bytes': 14794, 'sha256': ACTUAL_STDOUT_SHA},
        'terminal_original_sha256': TERMINAL_SHA, 'terminal_origin': 'embedded_exact_actual_controller_terminal',
        'actual_stdout_origin': 'deterministically_reconstructed_from_actual_pinned_joint_and_original_stage_line',
        'historical_joint': JOINT, 'historical_step_result': STEP_RESULT, 'flow': FLOW, 'step': STEP,
        'historical_task': 878, 'nonce': NONCE, 'wire_sha256': WIRE,
        'inspection_tree_sha256': inspection['tree_sha256'], 'inspection_window_sha256': inspection['window_sha256'],
        'inspection_observed_elapsed_ms': inspection['observed_elapsed_ms'],
        'complete_original_tree': True, 'all_original_node_count': len(inspection['nodes']),
        'omitted_invisible_or_password_nodes': omitted, 'selected_visible_nonpassword_nodes': nodes,
        'additional_string_truncation_applied': False, 'original_truncation_flags_preserved': True,
        'original_command_join_lease_release_and_postguard_receipts_rechecked': True,
        'actual_raw_reparsed_with_original_contract': QA, 'all_file_bytes_and_stat_rechecked': True,
        'files': {path: {'bytes': len(raw), 'sha256': sha(raw), 'stat': identity}
                  for path, (raw, identity) in sorted(observed.items())},
        'original_files_count': len(observed), 'original_files_bytes': total,
        'process_fds_before': before, 'process_fds_after': after,
        'whole_process_fd_identities_unchanged': True, 'new_live_target_observation': False,
        'fresh_inspection_and_original_guards_required_before_any_action': True,
        'current_action_authority': False, 'Main_commands': 0, 'namespace_entries': 0,
        'Main_locks_or_guards': 0, 'UI_actions': 0, 'native_commands': 0, 'installs': 0,
        'permission_changes': 0, 'signals': 0, 'existing_files_modified': False,
        'new_files_written': False, 'old_UNKNOWN_modified': False, 'reconciliation_published': False,
        'production_ready': False, 'automatic_retry': False,
        'private_UI_content_do_not_publish_to_Git': True}
    wire = canonical(result)
    need(len(wire) <= 1048576, 'COMPLETE_PRIVATE_RESULT_BOUND_NO_TRUNCATION')
    return wire


if __name__ == '__main__':
    try:
        output = run()
    except BaseException as error:
        print(canonical({'schema': 'pocket4-completed-task878-inspection-reader-error-v1',
            'ok': False, 'exception_type': type(error).__name__,
            'reason': str(error) if type(error) is RuntimeError and re.fullmatch('[A-Z0-9_]+', str(error)) else 'HOST_READER_REJECTED',
            'Main_commands': 0, 'UI_actions': 0, 'new_files_written': False,
            'no_current_action_authority': True}).decode('ascii'), flush=True)
        raise SystemExit(1)
    print(output.decode('ascii'), flush=True)
