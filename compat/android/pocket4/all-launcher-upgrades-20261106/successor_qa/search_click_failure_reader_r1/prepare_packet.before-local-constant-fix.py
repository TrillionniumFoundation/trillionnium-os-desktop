#!/usr/bin/env python3
"""Bind the executed failure reader to one new failed single-entry case.

Local preparation only. No private step directory or live Android is read here.
"""
import ast
import base64
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import types

HERE = Path(__file__).resolve().parent
QA = HERE.parent
PROJECT = QA.parent
PARENT = QA / 'case_failure_reader_r1'
ACTUAL = QA / 'search_click_after_partial_commit_r1/actual'
STEP = 'search-click-after-partial-commit-01'
JOB = '1a1b30305de-fc05-8072'
OUTPUT = '/home/alex/work/pocket4-beike-search-click-failure-evidence-20261106-r1'


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(path, size, digest):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == digest, 'EXACT_LOCAL_INPUT_' + path.name)
    return raw


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': sha(raw)}


def put(name, raw):
    path = HERE / name
    with path.open('xb') as target:
        target.write(raw)
        target.flush()
        os.fsync(target.fileno())
    need(path.read_bytes() == raw, 'NEW_LOCAL_OUTPUT_READBACK')
    return pin(path)


def functions(source):
    return {node.name: ast.get_source_segment(source, node)
            for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}


def replace_exact(source, before, after, count=1):
    need(source.count(before) == count, 'EXPECTED_SINGLE_SOURCE_CHANGE')
    return source.replace(before, after)


def main():
    old_path = PARENT / 'read_failed_case.py'
    old_raw = exact(old_path, 44768,
        '0e0716b7237199f2fe377ba9f067c2d0327d54a8efb5f40813b1f3e5ebc0021d')
    old = old_raw.decode()
    stdout = exact(ACTUAL / 'stdout.original.jsonl', 5009,
        '7d54b3f4e082dd77e8d8ef127616cb92d6e10bfb98a1de3743d59bf177b04a26')
    terminal_raw = exact(ACTUAL / 'status-01.original.json', 728,
        'f16e08511caa59179b205cad357a3c3f91d7f76cb6e99e17af7cb52e2b8466e8')
    child_raw = exact(ACTUAL / 'child.stdout.original.json', 3247,
        '2404ff57811ce7422a2d0ba412fe79986144269bef747356c9ba213281ecde54')
    result_raw = exact(ACTUAL / 'case-result.original.json', 563,
        '69911dce3dc95f2e85cc6c2ef4e76a686e3c83bcd02d7e572acce15c91ca4e7b')
    case_path = QA / 'search_click_after_partial_commit_r1/case.review-only.json'
    case_raw = exact(case_path, 739,
        '15cff75541c2b1219a92ada5ed7c3e38cd736660f848b7c216335b039b0cb58e')
    request_path = QA / 'search_click_after_partial_commit_r1/request.review-only.json'
    request_raw = exact(request_path, 1043,
        'bdb0f6779e20a7df21ff74983c2dfd4b412faedfaf1951216f24b63c17cd7b7b')
    outer, terminal, child, result, case, request = map(json.loads,
        (stdout, terminal_raw, child_raw, result_raw, case_raw, request_raw))
    need(outer['child_stdout_original'].encode() == child_raw and child['original_stdout'].encode() == result_raw,
         'ALL_ORIGINAL_OUTPUT_LAYERS_BYTE_EXACT')
    need(outer['child_stdout_bytes'] == len(child_raw) and outer['child_stdout_sha256'] == sha(child_raw) and
         child['original_stdout_bytes'] == len(result_raw) and child['original_stdout_sha256'] == sha(result_raw),
         'ORIGINAL_OUTPUT_LAYERS_LENGTH_SHA')
    need(terminal['job_id'] == JOB and terminal['state'] == 'failed' and terminal['exit_code'] == 1 and
         terminal['output_complete'] is True and terminal['output_durable'] is True and
         terminal['terminal_publication_confirmed'] is True and terminal['timed_out'] is False and
         terminal['cancelled'] is False and terminal['automatic_retry'] is False,
         'ONLY_SETTLED_ORIGINAL_FAILURE')
    need(terminal['log_bytes'] == {'stdout': {'seen': len(stdout), 'stored': len(stdout)},
                                  'stderr': {'seen': 0, 'stored': 0}} and
         terminal['log_errors'] == {'stdout': None, 'stderr': None} and
         terminal['log_truncated'] == {'stdout': False, 'stderr': False} and
         terminal['log_synced'] == {'stdout': True, 'stderr': True}, 'COMPLETE_ORIGINAL_DURABLE_LOGS')
    need(outer['child_lifecycle'] == {'child_pid': 2441902, 'errors': [],
         'owned_child_sigkill_count': 0, 'parent_descriptors_restored': True,
         'pidfd_acquired': True, 'pidfd_closed': True, 'pidfd_exit_observed': True,
         'returncode': 1, 'timeout': False}, 'ACTUAL_FAILED_CHILD_ALREADY_RETIRED')
    need(result['steps'] == [] and result['ok'] is False and result['action_attempted'] is True and
         result['outcome_unknown'] is True and child['original_returncode'] == 2 and
         result['errors'] == [{'code': 'EXACT_SUCCESSFUL_FINISH_REQUIRED', 'type': 'ProtocolError'}],
         'ACTUAL_FIRST_ENTRY_UNCOMPLETED_NOT_SUCCESS')
    need(request['step'] == STEP and request['kind'] == 'case' and request['payload_text'].encode() == case_raw and
         request['payload_sha256'] == sha(case_raw) and child['input_artifact']['sha256'] == sha(case_raw) and
         outer['request']['sha256'] == sha(request_raw), 'EXACT_FAILED_CASE_AND_REQUEST')
    need(case['name'] == 'beike-search-click-observe-01' and len(case['steps']) == 1,
         'SINGLE_ACTUAL_DECLARED_ENTRY')
    assignments = {node.targets[0].id: node for node in ast.parse(old).body
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    constants = {name: ast.literal_eval(node.value) for name, node in assignments.items()}
    config = copy.deepcopy(constants['CONFIG'])
    need(outer['source'] == config['sources']['worker'] and outer['flow'] == constants['FLOW'] and
         outer['task'] == child['task'] == 878 and child['step'] == STEP, 'SAME_SOURCE_FLOW_TASK')
    config.update(case=child['input_artifact'], request=outer['request'],
        actual_stdout_base64=base64.b64encode(stdout).decode('ascii'), actual_stdout_sha256=sha(stdout),
        terminal_base64=base64.b64encode(terminal_raw).decode('ascii'),
        terminal_bytes=len(terminal_raw), terminal_sha256=sha(terminal_raw),
        child_stdout_sha256=sha(child_raw), original_case_stdout_sha256=sha(result_raw))
    source_paths = {
        'base': QA / 'owned_cleanup_r1/cleanup_owned_task_once.py',
        'core': QA / 'owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py',
        'qa': QA / 'reconstructed/source-generation-r2/helper/qa_contract.py',
        'transport': QA / 'reconstructed/source-generation-r2/recorder/bound_android_transport.py',
        'worker': QA / 'reusable_owned_ui_r1/owned_ui_request_once.py',
        'adapter': QA / 'reconstructed/source-generation-r2/helper/qa_adapter.py',
        'run_case': QA / 'reconstructed/source-generation-r2/helper/run_case.py',
    }
    for label, path in source_paths.items():
        expected = config['sources'][label]
        exact(path, expected['bytes'], expected['sha256'])

    before = functions(old)
    modified = {}
    modified['phases'] = replace_exact(before['phases'],
        "case['name'] == 'beike-close-and-observe-search-01' and len(case['steps']) == 2",
        "case['name'] == 'beike-search-click-observe-01' and len(case['steps']) == 1")
    modified['phases'] = modified['phases'].replace('ONLY_THE_ACTUAL_TWO_STEP_CASE', 'ONLY_THE_ACTUAL_SINGLE_ENTRY_CASE')
    modified['phases'] = replace_exact(modified['phases'], "== 14, 'ALL_FOURTEEN_DISTINCT_DECLARED_NONCES'",
        "== 7, 'ALL_SEVEN_DISTINCT_DECLARED_NONCES'")
    modified['allowed_name'] = replace_exact(before['allowed_name'], 'range(2)', 'range(1)')
    modified['allowed_name'] = replace_exact(modified['allowed_name'], 'int(match[1]) <= 38', 'int(match[1]) <= 19')
    modified['allowed_name'] = replace_exact(modified['allowed_name'], 'int(match[1]) <= 50', 'int(match[1]) <= 25')
    modified['names_checked'] = replace_exact(before['names_checked'], 'len(names) <= 400', 'len(names) <= 202')
    validated = before['validate_actual']
    for a, b, count in [('5920','5009',3), ('1a1b272ec9d-fc05-7e0d',JOB,1),
                        ('1596573','2441902',1), ('4046','3247',1), ('1340','563',1)]:
        validated = replace_exact(validated, a, b, count)
    validated = replace_exact(validated,
        "len(original['steps']) == 1 and original['steps'][0]['index'] == 0",
        "original['steps'] == []")
    validated = validated.replace('ACTUAL_PARTIAL_CASE_AND_STRICT_FINISH_REJECTION',
                                   'ACTUAL_SINGLE_ENTRY_FAILED_BEFORE_POSTCONDITION_FINISH')
    modified['validate_actual'] = validated
    analyzed = replace_exact(before['analyze'], '1596573', '2441902')
    start = analyzed.index("    post_name = 'case-00-postcondition.json'\n")
    analyzed = analyzed[:start] + '''    need(result['steps'] == [] and 'case-00-postcondition.json' not in files,
         'ORIGINAL_SINGLE_ENTRY_HAS_NO_COMPLETED_POSTCONDITION')
    return {'commands': commands, 'transports': transport_rows, 'phases': phase_results,
            'no_declared_postcondition_completed': True,
            'single_case_operation_file_present': 'case-00-operation.json' in files,
            'single_case_postcondition_file_present': False,
            'all_recorded_commands_normal_zero_joined': all(row['normal_zero_joined'] for row in commands),
            'all_recorded_transports_verified': all(row['verified_result_present'] for row in transport_rows),
            'failure_remains_unknown': True, 'new_action_authority': False}'''
    modified['analyze'] = analyzed
    modified['run'] = replace_exact(before['run'], '1a1b272ec9d-fc05-7e0d', JOB, 2)
    modified['run'] = replace_exact(modified['run'], "'bytes': 5920", "'bytes': 5009")
    nodes = {node.name: node for node in ast.parse(old).body if isinstance(node, ast.FunctionDef)}
    edits = [(assignments['CONFIG'], 'CONFIG = ' + repr(config) + '\n'),
             (assignments['STEP'], 'STEP = ' + repr(STEP) + '\n'),
             (assignments['OUTPUT'], 'OUTPUT = ' + repr(OUTPUT) + '\n')]
    edits += [(nodes[name], text + '\n') for name, text in modified.items()]
    lines = old.splitlines(keepends=True)
    for node, text in sorted(edits, key=lambda item: item[0].lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [text]
    source = ''.join(lines); compile(source, 'read_failed_search_click.py', 'exec')
    after = functions(source)
    need(set(before) == set(after), 'NO_NEW_RUNTIME_FUNCTIONS')
    unchanged = sorted(set(before) - set(modified))
    need(len(unchanged) == 8 and all(before[name] == after[name] for name in unchanged),
         'ALL_EIGHT_ORIGINAL_IO_AND_FD_HELPERS_BYTE_IDENTICAL')
    need(all(after[name] == body for name, body in modified.items()), 'ONLY_LISTED_FUNCTION_DELTAS')

    # Pure local checks only: original input failure qualification and the
    # narrowed filename policy. No run(), base.read(), directory or Android call.
    definitions = {'__name__': 'local_failure_reader_definitions_only', '__file__': str(HERE / 'read_failed_search_click.py')}
    exec(compile(source, 'read_failed_search_click.py', 'exec'), definitions)
    parsed, life = definitions['validate_actual'](types.SimpleNamespace(document=json.loads))
    need(parsed == result and life == outer['child_lifecycle'], 'ORIGINAL_FAILURE_REMAINS_FAILED')
    phase_rows = definitions['phases'](case)
    need(len(phase_rows) == 7 and len({row['nonce'] for row in phase_rows}) == 7, 'SEVEN_ACTUAL_PHASES')
    allowed = definitions['allowed_name']
    need(allowed('command-019.stderr', phase_rows) and allowed('transport-025.verified-result.json', phase_rows),
         'FINITE_ONE_ENTRY_BOUNDARY_ACCEPTS')
    for name in ['command-020.stdout', 'transport-026.intent.json', 'case-01-operation.json',
                 'other.json', '../result.json', 'd4be175e3d9f09f49cac2f7ac9dd7fc2.request.json']:
        need(not allowed(name, phase_rows), 'UNRELATED_PATH_OR_OLD_NONCE_REJECTED')
    source_pin = put('read_failed_search_click.py', source.encode())
    diff = ''.join(difflib.unified_diff(old.splitlines(keepends=True), source.splitlines(keepends=True),
        fromfile='executed-case-failure-reader-r1/read_failed_case.py',
        tofile='search-click-failure-reader-r1/read_failed_search_click.py'))
    diff_pin = put('SOURCE_DIFF.patch', diff.encode())
    packet_path = PARENT / 'process-request.review-only.json'
    packet = json.loads(exact(packet_path, 45729,
        '510e9e090d7a2559959b3326c484fc7f6bc3af0eec34f375a62a0dd904ce4e72'))
    need(packet['args'] == ['-n','/usr/bin/python3','-I','-B','-c',old,
                           '--collect-once','--source-sha256',sha(old_raw)], 'ORIGINAL_READER_PACKET')
    packet['args'][5] = source
    packet['args'][-1] = source_pin['sha256']
    packet['idempotency_key'] = 'pocket4-beike-task878-search-click-failure-host-reader-r1-20261106'
    packet_pin = put('process-request.review-only.json',
        (json.dumps(packet, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode())
    proof = {
        'schema': 'pocket4-single-search-click-failure-fixed-reader-preparation-v1',
        'state': 'PREPARED_NOT_SUBMITTED', 'source': source_pin, 'diff': diff_pin, 'packet': packet_pin,
        'parent_executed_source': pin(old_path), 'actual_failed_job': JOB,
        'actual_failed_stdout': {'bytes': len(stdout), 'sha256': sha(stdout)},
        'actual_failed_terminal': {'bytes': len(terminal_raw), 'sha256': sha(terminal_raw)},
        'actual_failed_child': {'bytes': len(child_raw), 'sha256': sha(child_raw)},
        'actual_failed_original_case': {'bytes': len(result_raw), 'sha256': sha(result_raw)},
        'actual_owned_child_already_retired': life,
        'fixed_step': constants['FLOW'] + '/steps/' + STEP,
        'allowed_phase_count': 7, 'command_index_max': 19, 'transport_index_max': 25,
        'step_filename_count_max': 202,
        'step_filenames_and_individual_hashes_before_collection': 'UNKNOWN_NOT_INVENTED; only exact bounded original protocol names are admitted, and all raw bytes/stat are recorded and rechecked.',
        'seven_source_pins_unchanged': config['sources'],
        'original_scope_and_launch_pins_unchanged': [config['scope'], config['launch']],
        'eight_original_IO_and_FD_helpers_unchanged': unchanged,
        'function_changes': {
            'phases': 'Exact current case name and one entry/seven nonces instead of two/fourteen.',
            'allowed_name': 'Only case-00; commands 1..19 and transports 1..25.',
            'names_checked': 'Closed upper bound narrowed to 202 names.',
            'validate_actual': 'Exact new failed controller/child/case bytes; original steps is empty, failure remains strict.',
            'analyze': 'Actual child authority PID; no completed postcondition expected. Original strict raw command/transport/helper failure reparse is unchanged.',
            'run': 'Only actual job ID and stdout byte count; original read/copy/recheck/FD logic unchanged.'},
        'private_bundle_new_root': OUTPUT,
        'copy_policy': 'Only a new root-private bundle; original files untouched. Full command stdout/stderr, finish wire and failed assessment are captured, not exported in public stdout or Git.',
        'result_ok_means_collection_only': True,
        'offline_semantic_diagnosis_may_separately_fail_and_must_be_reported': True,
        'no_second_metadata_stage_needed': True,
        'local_controls': ['Actual immutable failure is accepted as failed evidence, never success.',
                           'One-entry bounds accept 19/25 and reject 20/26, old nonce, other entry and traversal.'],
        'run_main_executed_locally': False, 'remote_submitted': False,
        'Main_commands': 0, 'UI_actions': 0, 'signals': 0, 'old_UNKNOWN_modified': False,
        'reconciliation_published': False, 'new_action_authority': False, 'production_ready': False,
        'original_strict_finish_gate_unchanged': True,
    }
    proof_pin = put('LOCAL_PACKET_PROOF.json', (json.dumps(proof, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode())
    inputs = [pin(path) for path in [old_path, packet_path,
        PARENT / 'actual-public/status-01.original.txt', PARENT / 'actual-public/stdout.original.json',
        ACTUAL / 'stdout.original.jsonl', ACTUAL / 'status-01.original.json',
        ACTUAL / 'child.stdout.original.json', ACTUAL / 'case-result.original.json',
        case_path, request_path, *source_paths.values()]]
    pins = {'schema': 'pocket4-single-search-failure-reader-source-pins-v1',
        'inputs': inputs, 'outputs': [source_pin, diff_pin, packet_pin, proof_pin, pin(Path(__file__))],
        'remote_submitted': False, 'Main_commands': 0, 'private_original_UI_body_included': False,
        'production_ready': False, 'original_failure_and_UNKNOWN_unchanged': True}
    pins_pin = put('SOURCE_PINS.json', (json.dumps(pins, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps({'source': source_pin, 'packet': packet_pin, 'diff': diff_pin,
                      'proof': proof_pin, 'pins': pins_pin, 'remote_submitted': False}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
