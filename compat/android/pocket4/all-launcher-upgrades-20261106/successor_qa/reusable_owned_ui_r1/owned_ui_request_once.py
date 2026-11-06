#!/usr/bin/env python3
"""One externally pinned plan/case over the unchanged owned QA entry points.

Fixed Beike flow, task, helper, build and runtime. A fresh immutable request and
original Flow step are required each time. No launch, cleanup, focus transfer,
reconciliation, permission operation or alternate Android command is provided.
"""
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

ROOT = '/home/alex/work/pocket4-beike-owned-ui-reusable-20261106-r1'
FLOW = '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
BASE = {'path': '/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1/cleanup_owned_task_once.py',
        'bytes': 22233, 'sha256': '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'}
SESSION = {'path': '/home/alex/work/pocket4-beike-owned-new-session-20261106-r1/new_session_once.py',
           'bytes': 28943, 'sha256': 'eb02cc1e7669be21ad7f741af2438b7442fbac767a83587a0b285f764f34c909'}
LAUNCH = {'path': '/home/alex/work/pocket4-beike-owned-new-session-20261106-r1/launch-owned-lifetime.json',
          'bytes': 8135, 'sha256': 'a9e3c77e8b179e7c7702296ab23d97188ee809f2632bfdbcc44969774def68d4'}
LAUNCH_STDOUT = {'path': ROOT + '/launch.stdout.original.jsonl', 'bytes': 8339,
                 'sha256': '8a9a32bb54dad115d49fdc814ba10337cba43a04144c621f3a4d0a405b8db211'}
LAUNCH_TERMINAL = {'path': ROOT + '/launch.terminal.original.json', 'bytes': 731,
                   'sha256': '96292fcfeed27a538996f05b924feefc963d4f304759ea8423295e82c2380579'}
SCOPE = {'path': FLOW + '/scope.json', 'bytes': 1002,
         'sha256': '08c014646be1d32ef9eacc119f7930b941fc696333bd4cff9d74106f19dba516'}
LAUNCH_SCOPE_SHA = '54a669eb54fa0dcf6df5afcd17848af7511c2122623192051eb6370e42bfbb06'
ADAPTER = {'path': '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/qa_adapter.py',
           'bytes': 29378, 'sha256': 'ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c'}
CASE = {'path': '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/run_case.py',
        'bytes': 9595, 'sha256': 'cea31bd9afd0ddc147224a441fab277e0b5d55e034008dc49295ff198a046f2b'}
HELPER_MANIFEST = 'dfb9b6a483f1069847433152b9b2e8b0f1b2cdd571a1dbde3068fc9393ad62c4'
BUILD = '/home/alex/work/pocket4-successor-qa-build-b34f158f88bbebf112840fd88df25d03/build-result.json'
BUILD_SHA = 'c0dd8117cdb7fa8b551e2a59b466c91d48ee2f2d9a98908f69b3d3fb8807bf3d'
RECORDER_ROOT = '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder'
APK_SHA = '006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9'
SIGNER_SHA = 'd48d103342b42791ae4e927d70258062d0de11f9acb9f32b4426aff583f27d6f'
TASK = 878
SELF = REQUEST = None


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
    global SELF, REQUEST
    need(os.getuid() == os.geteuid() == 0 and len(sys.argv) == 10 and sys.argv[1] == mode and
         sys.argv[2] == '--source-sha256' and re.fullmatch('[0-9a-f]{64}', sys.argv[3]) and
         sys.argv[4] == '--source-bytes' and sys.argv[5].isdigit() and
         sys.argv[6] == '--request-sha256' and re.fullmatch('[0-9a-f]{64}', sys.argv[7]) and
         sys.argv[8] == '--request-bytes' and sys.argv[9].isdigit() and 0 < int(sys.argv[9]) <= 65536,
         'EXACT_ROOT_FIXED_SOURCE_AND_PER_STEP_INPUT')
    need(str(Path(__file__).resolve()) == ROOT + '/owned_ui_request_once.py', 'REAL_REUSABLE_ENTRY_LOCATION')
    SELF = {'path': str(Path(__file__).resolve()), 'bytes': int(sys.argv[5]), 'sha256': sys.argv[3]}
    REQUEST = {'path': ROOT + '/request-' + sys.argv[7] + '.json', 'bytes': int(sys.argv[9]), 'sha256': sys.argv[7]}
    os.umask(0o077)
    base = load_base(); base.pinned(SELF)
    return base


def outer_request(raw, core):
    value = core.document(raw)
    need(set(value) == {'schema', 'kind', 'step', 'payload_text', 'payload_sha256'} and
         value['schema'] == 'pocket4-fixed-beike-owned-ui-request-v1' and value['kind'] in ('plan', 'case') and
         type(value['step']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value['step']) and
         type(value['payload_text']) is str and re.fullmatch('[0-9a-f]{64}', value['payload_sha256']),
         'CLOSED_FIXED_UI_REQUEST_NO_COMMAND_OR_PATH_PARAMETERS')
    body = value['payload_text'].encode('utf-8')
    need(0 < len(body) <= (16384 if value['kind'] == 'plan' else 49152) and sha(body) == value['payload_sha256'],
         'EXACT_BOUNDED_DECLARED_PLAN_OR_CASE_BYTES')
    payload = core.document(body)
    return value, body, payload


def declared_request(raw, core, adapter, qa, cases):
    request, body, payload = outer_request(raw, core)
    if request['kind'] == 'plan':
        adapter.validate_plan(payload, qa)
        plans = [payload]
    else:
        cases.validate_case(payload, adapter, qa)
        plans = [entry['plan'] for entry in payload['steps']]
    need(all(plan['operation'] in ('inspect', 'click', 'set_text') for plan in plans), 'ONLY_COMPILED_BEIKE_INSPECT_CLICK_PUBLIC_TEXT')
    mutation = any(plan['operation'] != 'inspect' for plan in plans)
    return request, body, payload, mutation


def write_once(base, path, raw):
    path = Path(path)
    need(path.parent.as_posix() in (ROOT, FLOW) and path.name not in ('', '.', '..'), 'FIXED_OWNED_OUTPUT_DIRECTORY')
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(directory)
        need(before.st_uid == 0 and stat.S_IMODE(before.st_mode) == 0o700 and path.parent.resolve() == path.parent,
             'ROOT_PRIVATE_FIXED_OUTPUT_PARENT')
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=directory)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); need(count > 0, 'WRITE_PROGRESS'); view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
        named = os.stat(path.parent, follow_symlinks=False)
        need(all(getattr(before, key) == getattr(named, key) for key in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')),
             'OUTPUT_PARENT_REPLACED')
    finally:
        os.close(directory)
    need(base.read(path)[0] == raw, 'EXACT_IMMUTABLE_OUTPUT_READBACK')
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def launch_gate(base, core):
    stdout = base.pinned(LAUNCH_STDOUT); terminal = core.document(base.pinned(LAUNCH_TERMINAL))
    need(terminal.get('job_id') == '1a1b240f7fd-fc05-7d2d' and terminal.get('state') == 'succeeded' and
         terminal.get('exit_code') == 0 and all(terminal.get(k) is True for k in
             ('output_complete', 'output_durable', 'terminal_publication_confirmed', 'audit_recorded')) and
         all(terminal.get(k) is False for k in ('timed_out', 'cancelled', 'automatic_retry')) and
         terminal.get('log_bytes') == {'stdout': {'seen': 8339, 'stored': 8339}, 'stderr': {'seen': 0, 'stored': 0}} and
         terminal.get('log_errors') == {'stdout': None, 'stderr': None} and
         terminal.get('log_synced') == {'stdout': True, 'stderr': True} and
         terminal.get('log_truncated') == {'stdout': False, 'stderr': False}, 'ACTUAL_NATIVE_LAUNCH_DURABLE_ZERO')
    value = core.document(stdout)
    need(value.get('schema') == 'pocket4-original-new-session-owned-result-v1' and value.get('operation') == 'launch' and
         value.get('ok') is True and value.get('errors') == [] and value.get('outcome_unknown') is False and
         value.get('flow') == FLOW and value.get('source') == SESSION and value.get('joint_artifact') == LAUNCH and
         value.get('new_scope') == SCOPE and value.get('old_close_outcome') == 'unknown_retained' and
         value.get('old_unknown_rewritten') is False and value.get('reconciliation_published') is False,
         'ACTUAL_FIXED_NEW_FLOW_LAUNCH_RESULT')
    base.require_owned_exit(value['child_lifecycle'], b'')
    artifact = dict(value); del artifact['joint_artifact']
    need(base.pinned(LAUNCH) == canonical(artifact) + b'\n', 'REAL_LAUNCH_JOINT_ARTIFACT_MATCHES_ACTUAL_STDOUT')
    scope = core.document(base.pinned(SCOPE)); core.fixed_scope(scope)
    selected_raw, _ = base.read(Path(FLOW) / 'launch-scope.json')
    need(sha(selected_raw) == LAUNCH_SCOPE_SHA, 'UNCHANGED_ACTUAL_NATIVE_LAUNCH_SCOPE')
    selected = core.document(selected_raw)
    need(selected.get('task') == TASK and selected.get('package') == core.PACKAGE and selected.get('epoch_sha256') == core.MAIN_EPOCH and
         selected.get('prelaunch_absent') is True and selected.get('cleanup_allowed') is True and
         selected.get('launch_step') == 'native-launch-01' and selected.get('prelaunch_task_ids') == [875, 877] and
         selected.get('native_receipt_sha256') == value['launch']['native_identity']['receipt_sha256'] and
         value['launch'].get('task') == TASK and value['launch'].get('launch_scope_sha256') == LAUNCH_SCOPE_SHA,
         'EXACT_FRESH_NATIVE_OWNERSHIP_NO_TASK_TRANSFER')
    return scope, selected


def original_argv(request, body_path):
    selected = ADAPTER if request['kind'] == 'plan' else CASE
    return [selected['path'], '--execute-once', '--interactive-production',
        '--source-manifest-sha256', HELPER_MANIFEST, '--build-receipt', BUILD,
        '--build-receipt-sha256', BUILD_SHA, '--apk-sha256', APK_SHA,
        '--signer-certificate-sha256', SIGNER_SHA,
        '--' + request['kind'], str(body_path), '--' + request['kind'] + '-sha256', request['payload_sha256'],
        '--step', request['step'], '--recorder-root', RECORDER_ROOT,
        '--flow-dir', FLOW, '--helper-uid', '10157']


def verify_original(base, core, request, payload, mutation, raw, scope, selected):
    need(raw.endswith(b'\n') and len(raw.splitlines()) == 1, 'ONE_ORIGINAL_ADAPTER_OR_CASE_RESULT')
    result = core.document(raw); folder = Path(FLOW) / 'steps' / request['step']
    saved_raw, _ = base.read(folder / 'result.json')
    need(core.document(saved_raw) == result, 'ORIGINAL_RESULT_FILE_EQUALS_ORIGINAL_STDOUT')
    need(result.get('ok') is True and result.get('automatic_retry') is False and
         result.get('action_attempted') is mutation and result.get('outcome_unknown') is mutation and
         result.get('business_success_verified') is False and result.get('epoch_sha256') == core.MAIN_EPOCH,
         'ORIGINAL_SUCCESS_AND_MUTATION_UNKNOWN_RETAINED')
    intent = core.document(base.read(folder / 'intent.json')[0])
    need(intent.get('scope') == scope and intent.get('mutation') is mutation and
         intent.get('operation') == ('owned-qa' if request['kind'] == 'plan' else 'owned-qa-case') and
         all(intent.get(k) is None for k in ('unknown_step', 'observation_step', 'postcondition')),
         'ORIGINAL_FLOW_BEGIN_AND_FIXED_NEW_SCOPE')
    if request['kind'] == 'plan':
        need(intent['request'].get('plan') == payload and intent['request'].get('plan_sha256') == request['payload_sha256'] and
             result.get('plan_sha256') == request['payload_sha256'] and result.get('source_manifest_sha256') == HELPER_MANIFEST and
             result.get('owned_task') == selected and result.get('error') is None and result.get('secondary_errors') == [] and
             result.get('after_state_completed') is True and result.get('restoration_qualified') is True and
             result.get('post_state_matches_before') is True and
             result.get('next_business_mutation_requires_explicit_postcondition_reconciliation') is mutation and
             result.get('installed_before') == result.get('installed_after') and
             result['installed_before'].get('uid') == 10157 and result['installed_before'].get('apk_sha256') == APK_SHA,
             'FULL_ORIGINAL_OWNED_PLAN_RESTORATION_AND_HELPER_IDENTITY')
    else:
        need(result.get('schema') == 'pocket4-owned-scoped-qa-case-result-v1' and result.get('errors') == [] and
             result.get('declared_scoped_sequence_completed') is True and result.get('original_action_outcomes_rewritten') is False and
             result.get('case_sha256') == request['payload_sha256'] and intent['request'].get('case') == payload and
             intent['request'].get('case_sha256') == request['payload_sha256'] and len(result.get('steps', [])) == len(payload['steps']),
             'ORIGINAL_DECLARED_CASE_COMPLETED_WITHOUT_UNKNOWN_REWRITE')
        for index, (declared, evidence) in enumerate(zip(payload['steps'], result['steps'])):
            post = core.document(base.read(folder / ('case-%02d-postcondition.json' % index))[0])
            need(post == evidence and evidence.get('index') == index and evidence.get('postcondition') == declared['postcondition'] and
                 evidence.get('post_nonce') == declared['post_inspection']['nonces']['inspect'] and
                 evidence.get('original_action_outcome') == ('readonly' if declared['plan']['operation'] == 'inspect' else 'unknown_retained') and
                 evidence.get('allows_next_declared_case_decision_only') is True and evidence.get('business_success_verified') is False,
                 'EACH_ORIGINAL_INDEPENDENT_POST_INSPECT_RECEIPT_RETAINED')
    return result, {'path': str(folder / 'result.json'), 'bytes': len(saved_raw), 'sha256': sha(saved_raw)}


def child():
    base = entry('--child')
    need(sys.stdin.buffer.read(1) == b'R', 'PARENT_HELD_PIDFD_RELEASE_REQUIRED')
    result = {'schema': 'pocket4-fixed-reusable-owned-ui-child-v1', 'ok': False, 'errors': [], 'source': SELF, 'request': REQUEST,
        'flow': FLOW, 'task': TASK, 'original_entry_invoked': False, 'original_sources_modified': False,
        'original_UNKNOWN_rewritten': False, 'reconciliation_published': False, 'permission_changes': 0,
        'installs': 0, 'native_launches': 0, 'cleanup_or_focus_actions': 0, 'production_ready': False,
        'automatic_retry': False, 'allows_new_mutation_without_original_Flow_checks': False}
    try:
        session = base.load(SESSION, 'unchanged_session_support_only')
        support = base.load(base.SUPPORT, 'unchanged_library_bootstrap')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_owned_child_probe')
        observed = support.probe_proof(); _, frozen, library_fd, library = support.initialize_library(probe, observed)
        core = base.load(base.CORE, 'unchanged_pure_evidence_core')
        bodies, identities, old_scope = session.predecessor(base, core)
        scope, selected = launch_gate(base, core)
        _, same_scope = session.new_scope(base, core, old_scope); need(same_scope == SCOPE, 'UNCHANGED_NEW_SCOPE')
        adapter = base.load(ADAPTER, 'unchanged_actual_owned_adapter')
        manifest = adapter.own_source(HELPER_MANIFEST)
        qa = adapter.load(Path(ADAPTER['path']).with_name('qa_contract.py'), manifest['files']['qa_contract.py']['sha256'], 'unchanged_actual_qa_contract')
        cases = base.load(CASE, 'unchanged_actual_bounded_case')
        request, body, payload, mutation = declared_request(base.pinned(REQUEST), core, adapter, qa, cases)
        result.update(kind=request['kind'], step=request['step'], declared_mutation=mutation)
        need(not os.path.lexists(Path(FLOW) / 'steps' / request['step']), 'ORIGINAL_STEP_MUST_BE_FRESH_NO_REPLAY')
        body_path = Path(FLOW) / ('qa-' + request['step'] + '.' + request['kind'] + '.json')
        result['input_artifact'] = write_once(base, body_path, body)
        _, lock_metadata = base.read(Path(FLOW) / 'flow.lock', 65536)
        need(stat.S_IMODE(lock_metadata['st_mode']) == 0o600, 'EXACT_EXISTING_NEW_FLOW_LOCK')
        need(probe.same_descriptors(frozen, probe.census()), 'NO_PRE_ENTRY_UNKNOWN_DESCRIPTOR')
        argv = original_argv(request, body_path)
        saved, output, returned = sys.argv, io.StringIO(), None
        result['original_entry_invoked'] = True
        try:
            sys.argv = argv
            with contextlib.redirect_stdout(output):
                try:
                    returned = (adapter if request['kind'] == 'plan' else cases).main()
                except SystemExit as error:
                    returned = error.code
        finally:
            sys.argv = saved
            raw = output.getvalue().encode('utf-8')
            result.update(original_returncode=returned, original_stdout=raw.decode('utf-8'), original_stdout_bytes=len(raw),
                          original_stdout_sha256=sha(raw), original_argv=argv)
        need(type(returned) is int and returned == 0, 'ORIGINAL_ENTRY_FAILED_NO_RETRY')
        original, result_pin = verify_original(base, core, request, payload, mutation, raw, scope, selected)
        base.preserved(bodies, identities)
        launch_gate(base, core)
        for pin in (SELF, REQUEST, BASE, SESSION, ADAPTER, CASE, LAUNCH_STDOUT, LAUNCH_TERMINAL, base.RECORDER, base.CORE, base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed)
        final = probe.census(); extra = set(final) - set(frozen)
        need(len(extra) == 1 and probe.same_descriptors(frozen, {k: v for k, v in final.items() if k in frozen}), 'ONLY_DECLARED_ORIGINAL_FLOW_LOCK_MAY_REMAIN')
        held = final[next(iter(extra))]
        need(held['link'] == FLOW + '/flow.lock' and held['fstat'] == lock_metadata and held['descriptor_flags'] == 1 and
             held['status_flags'] & os.O_ACCMODE == os.O_RDWR and
             support.stable_library(probe.library_binding(library_fd, final[str(library_fd)])) == support.stable_library(library),
             'ORIGINAL_FLOW_LOCK_AND_EXPLICIT_LIBRARY_UNCHANGED')
        result.update(ok=True, original_result=result_pin, original_action_attempted=original['action_attempted'],
            original_action_outcome_unknown=original['outcome_unknown'], original_old_close_outcome='unknown_retained',
            original_namespace_authority_released=True, normal_process_exit_required_for_lock_and_library=True,
            final_descriptors=final, unknown_descriptors_closed=0, manual_library_close=False,
            original_private_UI_nodes_exported=False)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    result['outcome_unknown'] = bool(result.get('original_action_outcome_unknown', result['original_entry_invoked'] and not result['ok']))
    raw = canonical(result); need(len(raw) <= 131072, 'CHILD_OUTPUT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


def parent(publish):
    base = entry('--publish-and-execute' if publish else '--execute-request')
    result = {'schema': 'pocket4-fixed-reusable-owned-ui-result-v1', 'ok': False, 'errors': [], 'source': SELF,
        'request': REQUEST, 'flow': FLOW, 'task': TASK, 'original_UNKNOWN_rewritten': False, 'reconciliation_published': False,
        'production_ready': False, 'automatic_retry': False, 'permission_changes': 0, 'installs': 0,
        'native_launches': 0, 'cleanup_or_focus_actions': 0, 'old_products_deleted': False,
        'acceptance_requires_original_stdout_and_authoritative_durable_terminal': True}
    invoked = False
    try:
        support = base.load(base.SUPPORT, 'unchanged_owned_library_functions')
        probe = support.load_module(support.PROBE_SOURCE, 'unchanged_pidfd_lifetime_functions')
        observed = support.probe_proof(); support.pin_runtime_files(probe, observed)
        before = probe.census(); need(set(before) == {'0', '1', '2'}, 'PARENT_INITIAL_STDIO_ONLY')
        core = base.load(base.CORE, 'unchanged_request_json_parser')
        if publish:
            raw = sys.stdin.buffer.read(65537)
            need(len(raw) == REQUEST['bytes'] and sha(raw) == REQUEST['sha256'], 'EXACT_NEW_REQUEST_STDIN')
            outer_request(raw, core)
            write_once(base, REQUEST['path'], raw)
        request, _, _ = outer_request(base.pinned(REQUEST), core)
        marker = Path(ROOT) / ('attempt-' + REQUEST['sha256'] + '.json')
        write_once(base, marker, canonical({'source': SELF, 'request': REQUEST, 'step': request['step'],
                   'automatic_retry': False, 'child_not_yet_started': True}) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_DESCRIPTORS_BEFORE_CHILD')
        argv = [sys.executable, '-I', '-B', SELF['path'], '--child', '--source-sha256', SELF['sha256'], '--source-bytes', str(SELF['bytes']),
                '--request-sha256', REQUEST['sha256'], '--request-bytes', str(REQUEST['bytes'])]
        invoked = True
        life, raw, stderr = probe.run_owned_child(argv, seconds=360 if request['kind'] == 'plan' else 600)
        result.update(child_lifecycle=life, child_stdout_original=raw.decode('utf-8', 'strict'), child_stdout_bytes=len(raw),
            child_stdout_sha256=sha(raw), child_stderr_original=stderr.decode('utf-8', 'replace'),
            child_stderr_bytes=len(stderr), child_stderr_sha256=sha(stderr))
        value = core.document(raw); base.require_owned_exit(life, stderr)
        need(value.get('schema') == 'pocket4-fixed-reusable-owned-ui-child-v1' and value.get('ok') is True and value.get('errors') == [] and
             value.get('source') == SELF and value.get('request') == REQUEST and value.get('flow') == FLOW and value.get('task') == TASK and
             value.get('step') == request['step'] and value.get('kind') == request['kind'] and
             value.get('original_action_outcome_unknown') is value.get('declared_mutation'),
             'ORIGINAL_QA_SUCCESS_AND_NORMAL_CHILD_EXIT_JOINTLY_REQUIRED')
        for pin in (SELF, REQUEST, BASE, SESSION, ADAPTER, CASE, LAUNCH_STDOUT, LAUNCH_TERMINAL, base.SUPPORT, support.PROBE_SOURCE):
            base.pinned(pin)
        support.pin_runtime_files(probe, observed)
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_RESTORED')
        result.update(ok=True, step=request['step'], kind=request['kind'], original_result=value['original_result'],
            original_action_attempted=value['original_action_attempted'], original_action_outcome_unknown=value['original_action_outcome_unknown'],
            outcome_unknown=value['original_action_outcome_unknown'], all_owned_child_resources_retired_by_normal_pidfd_exit=True,
            allows_new_mutation_without_original_Flow_checks=False, original_old_close_outcome='unknown_retained')
        artifact = write_once(base, Path(ROOT) / ('result-' + REQUEST['sha256'] + '.json'), canonical(result) + b'\n')
        need(probe.same_descriptors(before, probe.census()), 'PARENT_FD_IDENTITIES_AFTER_ARTIFACT')
        result['joint_artifact'] = artifact
    except BaseException as error:
        result['ok'] = False
        result['errors'].append({'type': type(error).__name__, 'reason': str(error)[:512]})
    if not result['ok']:
        result['outcome_unknown'] = invoked
    raw = canonical(result); need(len(raw) <= 262144, 'PARENT_OUTPUT_BOUND')
    print(raw.decode('ascii'), flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    mode = sys.argv[1:2]
    if mode == ['--child']:
        raise SystemExit(child())
    need(mode in (['--execute-request'], ['--publish-and-execute']), 'CLOSED_ONE_REQUEST_ENTRY')
    raise SystemExit(parent(mode == ['--publish-and-execute']))
