#!/usr/bin/env python3
"""Locally bind the existing 21-file reader to one actually completed inspect.

No target operation, remote call, private node read or reader main is executed.
All old artifacts are read unchanged. Only new review files are created.
"""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
QA_ROOT = HERE.parent
PROJECT = QA_ROOT.parent
OLD_ROOT = QA_ROOT / 'inspect_after_search_rejection_reader_r1'
ACTUAL = QA_ROOT / 'inspect_after_partial_commit_r1/actual'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def exact(path, count, digest):
    raw = path.read_bytes()
    assert len(raw) == count and sha(raw) == digest, str(path)
    return raw


def file_pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': sha(raw)}


def put(name, raw):
    path = HERE / name
    with path.open('xb') as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    assert path.read_bytes() == raw
    return file_pin(path)


def functions(source):
    return {node.name: ast.get_source_segment(source, node)
            for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}


def main():
    old_path = OLD_ROOT / 'read_completed_inspect.py'
    old = exact(old_path, 26862,
        'cc4abb3935f4d044e048eb4d5b9e221043fb9f8b401656d0be782e0a3d775b83').decode()
    actual_read = exact(ACTUAL / 'read-0.original.txt', 44390,
        '1b76cc5cae993bb674e384aa8268a910da8e804b40ee98508d7f711067c5f7c7')
    terminal_raw = exact(ACTUAL / 'terminal.original.json', 733,
        '8c1b239ea57641d497f59f8f417ec66c663d4290366bb4f2fa008f0460109037')
    plan_path = QA_ROOT / 'inspect_after_partial_commit_r1/inspect.review-only.json'
    plan_raw = exact(plan_path, 178,
        '0e867579f9549549050b2184b8b98c34417475c275d22c7356523d5a0a64d073')
    old_actual_summary_path = OLD_ROOT / 'actual-public/ACTUAL_READER_SUMMARY.derived.json'
    old_actual_summary = json.loads(exact(old_actual_summary_path, 1678,
        'e225106fa433cbce62080e8e1684a7e6a320c84755aa11bbf2f827c5e564a4e1'))
    assert old_actual_summary['reader_job'] == '1a1b295db9e-fc05-7ec9'
    assert old_actual_summary['original_files_count'] == 21
    assert old_actual_summary['whole_process_fd_identities_unchanged'] is True

    # Parse original MCP bytes_hex using Python; no ns integer crosses JS.
    original_read = json.loads(actual_read)
    assert original_read['job_id'] == '1a1b2f182c1-fc05-803d' and original_read['audit_recorded'] is True
    stream = original_read['stdout']
    stdout = bytes.fromhex(stream['bytes_hex'])
    assert stream['text'].encode() == stdout and stream['offset'] == 0 and stream['eof'] is True
    assert stream['size'] == stream['next_offset'] == len(stdout) == 13947
    assert sha(stdout) == '23639dfd1822118c1379e306ba45bf2a1e0d5c8b30ee660c6b50125e8b7cdf84'
    assert original_read['stderr'] == {'bytes_hex': '', 'eof': True, 'next_offset': 0,
                                       'offset': 0, 'size': 0, 'text': ''}
    value, terminal, plan = map(json.loads, (stdout, terminal_raw, plan_raw))
    assert stdout == canonical(value) + b'\n'
    child_raw = value['child_stdout_original'].encode()
    assert len(child_raw) == value['child_stdout_bytes'] == 10667
    assert sha(child_raw) == value['child_stdout_sha256'] == '4b0ad68e70e8383c49c11634ac3229b66d438f5a17a9820c1c1ceb3dcad9bc53'
    child = json.loads(child_raw)
    adapter_raw = child['original_stdout'].encode()
    assert len(adapter_raw) == child['original_stdout_bytes'] == 5752
    assert sha(adapter_raw) == child['original_stdout_sha256'] == '612ed6e8b154843990feec5ad647727a747e46faa540896c1534f561bd8ebd7d'
    adapter = json.loads(adapter_raw)
    assert value['child_lifecycle'] == {
        'child_pid': 2414622, 'errors': [], 'owned_child_sigkill_count': 0,
        'parent_descriptors_restored': True, 'pidfd_acquired': True,
        'pidfd_closed': True, 'pidfd_exit_observed': True, 'returncode': 0, 'timeout': False}
    assert terminal['job_id'] == '1a1b2f182c1-fc05-803d'
    assert terminal['state'] == 'succeeded' and terminal['exit_code'] == 0
    assert all(terminal[key] is True for key in ('audit_recorded', 'output_complete',
        'output_durable', 'terminal_publication_confirmed'))
    assert all(terminal[key] is False for key in ('timed_out', 'cancelled', 'automatic_retry'))
    assert terminal['log_bytes'] == {'stdout': {'seen': len(stdout), 'stored': len(stdout)},
                                    'stderr': {'seen': 0, 'stored': 0}}
    assert terminal['log_errors'] == {'stdout': None, 'stderr': None}
    assert terminal['log_synced'] == {'stdout': True, 'stderr': True}
    assert terminal['log_truncated'] == {'stdout': False, 'stderr': False}
    assert value['ok'] is True and value['errors'] == [] and value['outcome_unknown'] is False
    assert child['ok'] is True and child['errors'] == [] and child['declared_mutation'] is False
    assert adapter['ok'] is True and adapter['error'] is None and adapter['secondary_errors'] == []
    assert adapter['action_attempted'] is False and adapter['outcome_unknown'] is False
    assert adapter['restoration_qualified'] is True and adapter['post_state_matches_before'] is True
    assert adapter['foreground_before'] == adapter['foreground_after']
    assert adapter['foreground_before']['window_token'] == '2dfbb60'
    assert adapter['foreground_before']['activity'] == 'com.lianjia.beike/com.lianjia.activity.MainActivity'
    assert adapter['installed_before'] == adapter['installed_after']
    assert adapter['installed_before']['uid'] == 10157
    assert adapter['installed_before']['package'] == 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1'
    assert adapter['installed_before']['apk_sha256'] == '006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9'
    assert plan['operation'] == 'inspect' and len(set(plan['nonces'].values())) == 3
    assert plan['nonces']['inspect'] == '9cd6bf0cba03a95b40b7197ba6df22af'
    assert adapter['inspection_wire_sha256'] == 'ee9a3d6b4e89147c4df2b6c8675f5cc35b01e79f5e9f0da6bd3a6273fd1bfee0'
    assert adapter['plan_sha256'] == sha(plan_raw) == child['input_artifact']['sha256']
    flow = value['flow']; step = value['step']; folder = flow + '/steps/' + step
    assert flow == '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
    assert step == child['step'] == 'inspect-after-partial-commit-01'
    assert value['task'] == child['task'] == adapter['owned_task']['task'] == 878
    assert child['original_result'] == value['original_result'] == {
        'bytes': 6362, 'path': folder + '/result.json',
        'sha256': '474eef79b7291adcedfef8e7d28415bf9fbe15fd90867e823da12045f0e8dd45'}
    joint_value = dict(value)
    joint = joint_value.pop('joint_artifact')
    joint_raw = canonical(joint_value) + b'\n'
    assert joint['bytes'] == len(joint_raw) == 13692
    assert joint['sha256'] == sha(joint_raw) == '994cc23b67db34ee50122a2034cb9c0d77c7d88eeca4ca68d7da7ce505c14bfc'

    assignments = {node.targets[0].id: node for node in ast.parse(old).body
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    old_constants = {name: ast.literal_eval(node.value) for name, node in assignments.items()
                     if name != 'ALLOWED_PATHS'}
    assert value['source'] == old_constants['UI_SOURCE']
    assert adapter['epoch_sha256'] == old_constants['EPOCH']
    assert adapter['owned_task']['native_receipt_sha256'] == old_constants['NATIVE_RECEIPT_SHA']
    changes = {
        'JOINT': joint, 'STEP_RESULT': value['original_result'], 'PLAN': child['input_artifact'],
        'STEP': step, 'FOLDER': folder, 'JOB': terminal['job_id'],
        'NONCE': plan['nonces']['inspect'], 'WIRE': adapter['inspection_wire_sha256'],
        'ACTUAL_STDOUT_SHA': sha(stdout), 'TERMINAL_SHA': sha(terminal_raw),
        'CHILD_SHA': sha(child_raw), 'ADAPTER_STDOUT_SHA': sha(adapter_raw),
        'EXPECTED_PLAN': plan, 'STAGE_STDOUT': b'', 'TERMINAL_RAW': terminal_raw}
    all_constants = {**old_constants, **changes}
    pin_names = ('BASE', 'CORE', 'QA', 'TRANSPORT', 'UI_SOURCE', 'JOINT', 'STEP_RESULT', 'SCOPE', 'PLAN')
    nonce = changes['NONCE']
    step_names = ('intent.json', 'held-main-binding.json', nonce + '.request.json', nonce + '.assessment.json',
        'command-005.intent.json', 'command-005.result.json', 'command-005.stdout', 'command-005.stderr',
        'transport-006.intent.json', 'transport-006.command-result.json', 'transport-006.verified-result.json')
    allowed = {all_constants[name]['path'] for name in pin_names}
    allowed |= {flow + '/launch-scope.json'} | {folder + '/' + name for name in step_names}
    assert len(allowed) == 21
    lines = old.splitlines(keepends=True)
    edits = [(assignments[name], name + ' = ' + repr(item) + '\n') for name, item in changes.items()]
    edits.append((assignments['ALLOWED_PATHS'], 'ALLOWED_PATHS = frozenset(' + repr(sorted(allowed)) + ')\n'))
    for node, text in sorted(edits, key=lambda entry: entry[0].lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [text]
    source = ''.join(lines)
    replacements = (('13961', '13947', 4), ('10677', '10667', 1), ('2010422', '2414622', 2))
    for old_text, new_text, count in replacements:
        assert source.count(old_text) == count, (old_text, source.count(old_text), count)
        source = source.replace(old_text, new_text)
    compile(source, 'read_completed_inspect.py', 'exec')
    before_functions, after_functions = functions(old), functions(source)
    unchanged = ('need', 'sha', 'canonical', 'load_base', 'census', 'project_nodes')
    assert set(before_functions) == set(after_functions)
    assert all(before_functions[name] == after_functions[name] for name in unchanged)
    expected_run = before_functions['run']
    for old_text, new_text, _ in replacements:
        expected_run = expected_run.replace(old_text, new_text)
    assert expected_run == after_functions['run']
    source_pin = put('read_completed_inspect.py', source.encode())
    diff = ''.join(difflib.unified_diff(old.splitlines(keepends=True), source.splitlines(keepends=True),
        fromfile='executed-inspect-after-search-rejection-reader-r1/read_completed_inspect.py',
        tofile='inspect-after-partial-commit-reader-r1/read_completed_inspect.py'))
    diff_pin = put('SOURCE_DIFF.patch', diff.encode())
    old_request_path = OLD_ROOT / 'process-request.review-only.json'
    old_request = json.loads(exact(old_request_path, 27719,
        '05edd577f953ef8ed8a00c8dafc3369bf079f4e84046d3e97da2b771ba08f1b8'))
    assert old_request['args'] == ['-n', '/usr/bin/python3', '-I', '-B', '-c', old]
    packet = dict(old_request)
    packet['args'] = ['-n', '/usr/bin/python3', '-I', '-B', '-c', source]
    packet['idempotency_key'] = 'pocket4-beike-inspect-after-partial-commit-fixed-reader-r1-20261106'
    assert {k: v for k, v in packet.items() if k not in ('args', 'idempotency_key')} == {
        k: v for k, v in old_request.items() if k not in ('args', 'idempotency_key')}
    packet_pin = put('process-request.review-only.json',
        json.dumps(packet, ensure_ascii=True, sort_keys=True, indent=2).encode('ascii') + b'\n')
    known_by_path = {all_constants[name]['path']: all_constants[name] for name in pin_names}
    expected_reads = [{'path': path,
        'expected_bytes': known_by_path[path]['bytes'] if path in known_by_path else None,
        'expected_sha256': known_by_path[path]['sha256'] if path in known_by_path else
                          old_constants['LAUNCH_SCOPE_SHA'] if path == flow + '/launch-scope.json' else None,
        'basis': 'original pinned source/result/plan/scope' if path in known_by_path else
                 'original pinned launch-scope SHA' if path == flow + '/launch-scope.json' else
                 'fixed original step protocol path; recorded command, request, transport and full wire validated on read; byte/stat recheck required'}
        for path in sorted(allowed)]
    proof = {
        'schema': 'pocket4-completed-inspect-fixed-reader-local-preparation-v1', 'ok': True,
        'original_executed_reader': file_pin(old_path),
        'original_reader_public_success_reference': file_pin(old_actual_summary_path),
        'source': source_pin, 'diff': diff_pin, 'packet': packet_pin,
        'historical_job': terminal['job_id'],
        'original_MCP_process_read': file_pin(ACTUAL / 'read-0.original.txt'),
        'historical_stdout': {'bytes': len(stdout), 'sha256': sha(stdout)},
        'historical_terminal': {'bytes': len(terminal_raw), 'sha256': sha(terminal_raw)},
        'historical_child': {'bytes': len(child_raw), 'sha256': sha(child_raw)},
        'historical_adapter': {'bytes': len(adapter_raw), 'sha256': sha(adapter_raw)},
        'historical_joint': joint, 'historical_step_result': child['original_result'],
        'historical_nonce': nonce, 'historical_wire_sha256': changes['WIRE'],
        'actual_task': 878, 'actual_helper_uid': 10157, 'actual_target_uid': 10143,
        'actual_window_token': '2dfbb60',
        'exact_allowed_file_count': len(allowed), 'exact_allowed_paths_and_known_pins': expected_reads,
        'unchanged_functions': list(unchanged),
        'run_diff_limited_to_3_actual_metadata_literal_replacements': True,
        'original_packet_contract_unchanged_except_source_and_key': True,
        'whole_original_outer_child_adapter_bytes_bound_not_summary_substituted': True,
        'actual_joint_reconstruction_sha_matches': True,
        'compiled_without_executing_reader': True,
        'remote_submitted': False, 'Main_commands': 0,
        'private_UI_read_or_saved_locally': False,
        'no_integer_conversion_through_JavaScript': True,
        'new_reconciliation_producer_or_authority_created': False,
        'current_foreground_or_future_action_authority': False,
        'original_9_command_12_transport_runtime_sequence_not_rerun_or_modified': True,
        'reader_only_rechecks_selected_inspection_command005_transport006_of_original_sequence': True,
        'other_commands_not_newly_claimed_revalidated_by_this_reader': True,
        'private_stdout_destination_policy': 'Root must save raw output outside the Git-backed tree; only explicitly derived summaries with no UI text/nodes may be committed.',
        'new_NDK_inventory_not_collected_or_resolved_here': True,
        'production_ready': False,
    }
    proof_pin = put('LOCAL_PACKET_PROOF.json', json.dumps(proof, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    inputs = [file_pin(path) for path in [old_path, old_request_path,
        OLD_ROOT / 'prepare_packet.py', old_actual_summary_path, ACTUAL / 'read-0.original.txt',
        ACTUAL / 'terminal.original.json', plan_path,
        QA_ROOT / 'inspect_after_partial_commit_r1/SOURCE_CONTRACT_INDEX.json']]
    source_pins = {
        'schema': 'pocket4-fixed-completed-inspect-reader-source-pins-v1',
        'inputs': inputs,
        'outputs': [source_pin, diff_pin, packet_pin, proof_pin, file_pin(Path(__file__))],
        'status': 'LOCAL_PREPARED_NOT_SUBMITTED', 'remote_submitted': False,
        'Main_commands': 0, 'private_UI_included': False, 'original_UNKNOWN_modified': False,
        'producer_implemented': False,
    }
    pins_pin = put('SOURCE_PINS.json', json.dumps(source_pins, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps({'source': source_pin, 'diff': diff_pin, 'packet': packet_pin,
                      'proof': proof_pin, 'pins': pins_pin,
                      'exact_allowed_file_count': len(allowed), 'remote_submitted': False,
                      'private_UI_read_or_saved_locally': False}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
