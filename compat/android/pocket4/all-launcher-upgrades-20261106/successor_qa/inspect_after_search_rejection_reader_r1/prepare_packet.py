#!/usr/bin/env python3
"""Local-only, one-time binding of the executed reader to one later observation.

No target API is called. Original source and actual evidence are read unchanged.
Every output is exclusive; Python preserves original integer values.
"""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
QA_ROOT = HERE.parent
OLD_SOURCE = QA_ROOT / 'inspect878_reader_r1/read_completed_inspect878.py'
ACTUAL = QA_ROOT / 'inspect_after_search_rejection_r1/actual'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def exact(path, count, digest):
    raw = path.read_bytes()
    assert len(raw) == count and sha(raw) == digest, str(path)
    return raw


def put(name, raw):
    path = HERE / name
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    assert path.read_bytes() == raw
    return {'path': name, 'bytes': len(raw), 'sha256': sha(raw)}


def functions(source):
    return {node.name: ast.get_source_segment(source, node)
            for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}


def main():
    old = exact(OLD_SOURCE, 27620,
        'f068d9907ba9fe4bc5f22ca76a273156c6f1e39d7e19927ddc157eada4122272').decode('utf-8')
    stdout = exact(ACTUAL / 'stdout.original.json', 13961,
        '50890b7a1c8a591f493a1af26606da2279f5b3c0cc1e7a893b19b77d200c0401')
    terminal_raw = exact(ACTUAL / 'status-01.original.txt', 733,
        'b314bd6a3cc8304d5d00038ece8f811e88bacadf0df09798c87cb42e613a5ede')
    child_raw = exact(ACTUAL / 'child.stdout.original.json', 10677,
        'e2ea488674a9a8512c28c6937fc9fc05824ae057b379ca8cd69c570327aff791')
    adapter_raw = exact(ACTUAL / 'adapter.stdout.original.json', 5752,
        'c4d26149b4e68b686dd84a5fe8c69c73a45b93f0e9ea2e37541b0ad8ab6f8162')
    plan_raw = exact(QA_ROOT / 'inspect_after_search_rejection_r1/inspect.review-only.json',
        178, '022d15ae8c0b31f1c9469a1a2a0f4a093d166d01d5ca25d496b159ab2879bcb4')
    value, terminal, child, adapter, plan = map(json.loads,
        (stdout, terminal_raw, child_raw, adapter_raw, plan_raw))
    assert stdout == canonical(value) + b'\n'
    assert value['child_stdout_original'].encode('utf-8') == child_raw
    assert child['original_stdout'].encode('utf-8') == adapter_raw
    assert value['child_stdout_bytes'] == len(child_raw)
    assert value['child_stdout_sha256'] == sha(child_raw)
    assert child['original_stdout_bytes'] == len(adapter_raw)
    assert child['original_stdout_sha256'] == sha(adapter_raw)
    assert value['child_lifecycle'] == {
        'child_pid': 2010422, 'errors': [], 'owned_child_sigkill_count': 0,
        'parent_descriptors_restored': True, 'pidfd_acquired': True,
        'pidfd_closed': True, 'pidfd_exit_observed': True, 'returncode': 0, 'timeout': False}
    assert terminal['job_id'] == '1a1b285c279-fc05-7e67'
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
    assert adapter['installed_before']['apk_sha256'] == '006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9'
    assert plan['operation'] == 'inspect' and len(set(plan['nonces'].values())) == 3
    assert plan['nonces']['inspect'] == 'd4be175e3d9f09f49cac2f7ac9dd7fc2'
    assert adapter['inspection_wire_sha256'] == '36174e091c45db20baf2c192ecc677abc52b6565d7c68b25ff50b5b8ec0f0aaa'
    assert adapter['plan_sha256'] == sha(plan_raw) == child['input_artifact']['sha256']
    flow = value['flow']; step = value['step']; folder = flow + '/steps/' + step
    assert flow == '/home/alex/work/pocket4-successor-qa-flow-b6de2bd4f04bcd572a074ef984ba7dbe'
    assert step == child['step'] == 'inspect-after-search-rejection-01'
    assert value['task'] == child['task'] == adapter['owned_task']['task'] == 878
    assert child['original_result'] == value['original_result'] == {
        'bytes': 6362, 'path': folder + '/result.json',
        'sha256': '8abc17cc8fb4983792f1ec09270abd8eaeb29d56f80ea3a1fe2c76dcba523b4d'}
    joint_value = dict(value)
    joint = joint_value.pop('joint_artifact')
    joint_raw = canonical(joint_value) + b'\n'
    assert joint['bytes'] == len(joint_raw) == 13706
    assert joint['sha256'] == sha(joint_raw) == '9eab29efce2bf0506e9b5c3dfb7282859e8310a4235f9885c108ecc546f93665'

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
    # Only actual evidence literals and the truthful no-stage origin change in run().
    replacements = (
        ('14794', '13961', 4),
        ('10622', '10677', 1),
        ('1308652', '2010422', 2),
        ("front['window_token'] == 'c1a867e'", "front['window_token'] == '2dfbb60'", 1),
        ('EXACT_RECONSTRUCTED_ACTUAL_STDOUT_FROM_PINNED_JOINT_AND_STAGE',
         'EXACT_RECONSTRUCTED_ACTUAL_STDOUT_FROM_PINNED_JOINT', 1),
        ('deterministically_reconstructed_from_actual_pinned_joint_and_original_stage_line',
         'deterministically_reconstructed_from_actual_pinned_joint', 1))
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
    source_pin = put('read_completed_inspect.py', source.encode('utf-8'))
    diff = ''.join(difflib.unified_diff(old.splitlines(keepends=True), source.splitlines(keepends=True),
        fromfile='executed-inspect878-reader-r1/read_completed_inspect878.py',
        tofile='inspect-after-search-rejection-reader-r1/read_completed_inspect.py'))
    diff_pin = put('SOURCE_DIFF.patch', diff.encode('utf-8'))
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', source],
        'cwd': '/home/alex/work', 'timeout_seconds': 120, 'cpu_quota_percent': 100,
        'memory_max_bytes': 268435456, 'nice': 10,
        'idempotency_key': 'pocket4-beike-inspect-after-search-rejection-fixed-reader-r1-20261106'}
    packet_pin = put('process-request.review-only.json',
        json.dumps(packet, ensure_ascii=True, sort_keys=True, indent=2).encode('ascii') + b'\n')
    proof = {'schema': 'pocket4-completed-inspect-fixed-reader-local-preparation-v1', 'ok': True,
        'original_executed_reader': {'path': str(OLD_SOURCE.relative_to(QA_ROOT)),
            'bytes': len(old.encode()), 'sha256': sha(old.encode())},
        'source': source_pin, 'diff': diff_pin, 'packet': packet_pin,
        'historical_job': terminal['job_id'], 'historical_stdout': {'bytes': len(stdout), 'sha256': sha(stdout)},
        'historical_terminal': {'bytes': len(terminal_raw), 'sha256': sha(terminal_raw)},
        'historical_joint': joint, 'historical_step_result': child['original_result'],
        'historical_nonce': nonce, 'historical_wire_sha256': changes['WIRE'],
        'exact_allowed_file_count': len(allowed), 'exact_allowed_paths': sorted(allowed),
        'unchanged_functions': list(unchanged), 'run_diff_limited_to_explicit_actual_metadata': True,
        'actual_outer_child_adapter_byte_roundtrip': True, 'actual_joint_reconstruction_sha_matches': True,
        'compiled_without_executing_reader': True, 'actual_local_uid': os.getuid(), 'actual_local_euid': os.geteuid(),
        'remote_submitted': False, 'Main_commands': 0, 'private_UI_read_or_saved_locally': False,
        'no_integer_conversion_through_JavaScript': True,
        'new_reconciliation_producer_or_authority_created': False}
    put('LOCAL_PACKET_PROOF.json', json.dumps(proof, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps(proof, ensure_ascii=True, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
