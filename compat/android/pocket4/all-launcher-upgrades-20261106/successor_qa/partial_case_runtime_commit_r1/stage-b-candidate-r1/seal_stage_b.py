#!/usr/bin/env python3
"""Seal the reviewed Stage B bytes locally; never dispatch a target operation."""
import ast
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
STAGE_A = HERE.parent / 'stage-a-candidate-r1'
ROOT = '/home/alex/work/pocket4-beike-partial-case-commit-20261106-r1'
KEY = 'pocket4-beike-task878-partial-case-commit-stage-b-r1-20261106'
SOURCE_PIN = {'bytes': 70203, 'sha256': '28673ff6509c51dd818140107acfdd5d5847b7baeee366527735ff164e337a63'}
REQUEST_PIN = {'bytes': 2596, 'sha256': 'ca6d11780cc7f6d6a3adf58f5f2bcbe10eefc07fde9c636398b55f2a11d7d82c'}
A_STAGE_PIN = {'bytes': 5925, 'sha256': 'ce819668e952f049ec909ff8d569f0896a3a0b423be1c81e185385b4234f951a'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def assignment_replace(text, key, value):
    rows = [node for node in ast.parse(text).body if isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and target.id == key for target in node.targets)]
    assert len(rows) == 1 and rows[0].lineno == rows[0].end_lineno, key
    lines = text.splitlines(True)
    lines[rows[0].lineno - 1] = key + ' = ' + repr(value) + '\n'
    return ''.join(lines)


def literal(text, key):
    rows = [node for node in ast.parse(text).body if isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and target.id == key for target in node.targets)]
    assert len(rows) == 1, key
    return ast.literal_eval(rows[0].value)


def definition(text, path):
    nodes = ast.parse(text).body
    for name in path.split('.'):
        rows = [node for node in nodes if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
        assert len(rows) == 1, path
        found = rows[0]; nodes = found.body
    return ''.join(text.splitlines(True)[found.lineno - 1:found.end_lineno])


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def write_new(name, raw):
    fd = os.open(HERE / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            assert count > 0
            offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    assert (HERE / name).read_bytes() == raw


def main():
    worker = (HERE / 'commit_stage_b_once.py').read_bytes()
    request = (HERE / 'request.json').read_bytes()
    assert pin(worker) == SOURCE_PIN and pin(request) == REQUEST_PIN
    compile(worker, str(HERE / 'commit_stage_b_once.py'), 'exec')
    fixed = literal(worker.decode(), 'FIXED_REQUEST')
    assert request == canonical(fixed) + b'\n'
    assert fixed['operation'] == 'owned-qa-partial-case-commit'
    assert fixed['completed_stage_A_job'] == '1a1b2d13973-fc05-7fe2'
    assert fixed['original_UNKNOWN_retained'] is True and fixed['automatic_retry'] is False
    assert fixed['next_UI_decision_requires_actual_stage_B_durable_terminal_and_fresh_original_checks'] is True
    assert all(type(fixed[name]) is int and fixed[name] == 0 for name in
               ('UI_actions', 'instrumentation_calls', 'permission_changes', 'installs'))
    controls_raw = (HERE / 'local-controls.stdout.original.jsonl').read_bytes()
    controls = json.loads(controls_raw)
    assert controls['ok'] is True and controls['case_count'] == 5 and len(controls['cases']) == 5
    assert all(row['passed'] is True for row in controls['cases'])
    assert controls['source_sha256'] == SOURCE_PIN['sha256']
    assert controls['actual_uid'] == controls['actual_euid'] == 1000
    assert controls['whole_process_fd_identities_unchanged'] is True
    assert controls['Main_or_remote_actions'] == 0 and controls['real_runtime_commit_executed'] is False
    assert (HERE / 'local-controls.stderr.original.txt').read_bytes() == b''

    names = ('commit_stage_b_once.py', 'request.json', 'stage-a.stdout.original.jsonl', 'stage-a.terminal.original.json')
    bodies = {name: (HERE / name).read_bytes() for name in names}
    pins = {name: pin(raw) for name, raw in bodies.items()}
    assert bodies[names[2]] == (STAGE_A / 'actual/stdout.original.jsonl').read_bytes()
    assert bodies[names[3]] == (STAGE_A / 'actual/terminal.original.json').read_bytes()
    for name, key in ((names[2], 'completed_stage_A_stdout'), (names[3], 'completed_stage_A_terminal')):
        assert pins[name] == {field: fixed[key][field] for field in ('bytes', 'sha256')}
    payload = {'schema': 'pocket4-stage-b-partial-case-commit-stage-payload-v1', 'root': ROOT,
        'files': {name: {**pins[name], 'base64': base64.b64encode(raw).decode('ascii')} for name, raw in bodies.items()}}
    payload_raw = canonical(payload) + b'\n'
    assert len(payload_raw) < 524288

    old = (STAGE_A / 'stage_runtime_once.py').read_bytes()
    assert pin(old) == A_STAGE_PIN
    text = replace_once(old.decode(),
        'Stage only the new readonly runtime proof owner and actual host prerequisites.',
        'Stage the fixed Stage B owner and already completed Stage A receipts.')
    text = text.replace('pocket4-beike-partial-case-runtime-20261106-r1', Path(ROOT).name)
    text = assignment_replace(text, 'PINS', pins)
    text = assignment_replace(text, 'ENTRY_SHA', sha(worker))
    text = assignment_replace(text, 'PAYLOAD_SHA', sha(payload_raw))
    text = replace_once(text, 'pocket4-stage-a-runtime-proof-stage-payload-v1',
                        'pocket4-stage-b-partial-case-commit-stage-payload-v1')
    text = replace_once(text, 'pocket4-stage-a-runtime-proof-stage-v1',
                        'pocket4-stage-b-partial-case-commit-stage-v1')
    text = replace_once(text, 'readonly-runtime-candidate-not-yet-invoked',
                        'single-partial-case-commit-owner-not-yet-invoked')
    text = text.replace('runtime_stage_a_once.py', 'commit_stage_b_once.py')
    text = replace_once(text, "'--execute-runtime-once'", "'--publish-once'")
    text = replace_once(text, "'e21cf095aa8a72d95f04a7a3acea477675daeb0882d0919dcad27eb01daa1d9d'", repr(sha(request)))
    text = replace_once(text, "'--request-bytes', '838'", "'--request-bytes', " + repr(str(len(request))))
    stage = text.encode('utf-8')
    compile(stage, str(HERE / 'stage_commit_once.py'), 'exec')
    assert literal(text, 'PINS') == pins and literal(text, 'ENTRY_SHA') == sha(worker)
    assert literal(text, 'PAYLOAD_SHA') == sha(payload_raw)
    stage_diff = ''.join(difflib.unified_diff(old.decode().splitlines(True), text.splitlines(True),
        fromfile='actual-stage-a/stage_runtime_once.py', tofile='stage-b/stage_commit_once.py', n=3)).encode()
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', text, '--payload-sha256', sha(payload_raw)],
        'cwd': '/home/alex/work', 'stdin': payload_raw.decode('ascii'),
        'timeout_seconds': 900, 'cpu_quota_percent': 100, 'memory_max_bytes': 1073741824, 'nice': 10,
        'idempotency_key': KEY}
    packet_raw = canonical(packet) + b'\n'
    old_packet = json.loads((STAGE_A / 'process-request.review-only.json').read_bytes())
    for field in ('host', 'executable', 'cwd', 'timeout_seconds', 'cpu_quota_percent', 'memory_max_bytes', 'nice'):
        assert packet[field] == old_packet[field]
    assert packet['args'][:5] == old_packet['args'][:5]

    inherited = json.loads((HERE / 'SOURCE_INHERITANCE.json').read_bytes())
    assert inherited['source'] == SOURCE_PIN and inherited['request'] == REQUEST_PIN
    assert len(inherited['exact_inherited_definitions']) == 15
    for name, expected in inherited['exact_inherited_definitions'].items():
        original = definition((STAGE_A / 'runtime_stage_a_once.py').read_text(), name).encode()
        actual = definition(worker.decode(), name).encode()
        assert original == actual and pin(actual) == {key: expected[key] for key in ('bytes', 'sha256')}
    source_rows = json.loads((STAGE_A / 'SOURCE_INHERITANCE.json').read_bytes())['unchanged_exact_source_and_predicate_definitions']
    assert len(source_rows) == 8 and sum(len(row['method_definition_sha256']) for row in source_rows) == 39
    for row in source_rows:
        raw = (PROJECT / row['path']).read_bytes()
        assert pin(raw) == {key: row[key] for key in ('bytes', 'sha256')}
        for name, expected in row['method_definition_sha256'].items():
            assert sha(definition(raw.decode(), name).encode()) == expected
    old_publisher = PROJECT / inherited['same_original_no_replace_commit']['source']
    publisher = old_publisher.read_bytes()
    assert sha(publisher) == inherited['same_original_no_replace_commit']['file_sha256']
    assert definition(publisher.decode(), 'commit_envelope') == definition(worker.decode(), 'commit_envelope')
    stage_inheritance = {
        'schema': 'pocket4-stage-b-transport-and-predicate-inheritance-v1',
        'source': SOURCE_PIN, 'request': REQUEST_PIN,
        'stage_A_actual_source_stage': A_STAGE_PIN,
        'original_stage_IO_algorithm_modified': False,
        'stage_difference': 'Only fixed source/root/schema/argv/pins and descriptive mode changed. Original mkdir/O_EXCL/root0400/fsync/fullstat/readback/whole-FD gate preserved.',
        'same_stage_functions': {name: {'same_bytes': definition(old.decode(), name) == definition(text, name),
            'sha256': sha(definition(text, name).encode())} for name in ('need', 'sha', 'census')},
        'unchanged_exact_source_and_predicate_definitions': source_rows,
        'same_original_no_replace_commit': inherited['same_original_no_replace_commit'],
        'new_process_request_not_executed': True,
    }
    assert all(row['same_bytes'] for row in stage_inheritance['same_stage_functions'].values())
    review = {
        'schema': 'pocket4-stage-b-partial-case-commit-packet-review-v1',
        'state': 'PREPARED_NOT_SUBMITTED', 'source_root': ROOT, 'source': SOURCE_PIN, 'request': REQUEST_PIN,
        'stager': pin(stage), 'stage_input': pin(payload_raw), 'process_request': pin(packet_raw),
        'staged_files': pins, 'idempotency_key': KEY,
        'resource_bounds': {key: packet[key] for key in ('timeout_seconds', 'cpu_quota_percent', 'memory_max_bytes', 'nice')},
        'completed_stage_A_job': fixed['completed_stage_A_job'],
        'actual_stage_A_stdout': pins[names[2]], 'actual_stage_A_terminal': pins[names[3]],
        'stage_A_source_candidate_and_joint_pins_are_historical_actual_inputs': True,
        'worker_recorded_readonly_commands': 6, 'worker_total_transport_receipts': 8,
        'worker_private_foreground_transports': 2,
        'worker_UI_or_instrumentation_actions': 0,
        'private_UI_or_bundle_in_packet': False, 'stage_Main_commands_or_locks': 0,
        'compatibility_publication': 'one O_EXCL temporary + no-replace link + owned temporary unlink + directory fsync',
        'new_proof_is_explicit_owned_qa_partial_case_protocol': True,
        'original_Flow_consumer_Session_foreground_helper_guard_modified': False,
        'original_failed_unknown_preserved': True, 'old_action_replayed': False,
        'no_current_tree_or_UI_action_authority_claimed': True,
        'frozen_consumer_validates_controller_terminal': False,
        'root_must_maintain_action_freeze_until_actual_B_owned_exit_and_durable_terminal': True,
        'publication_or_exit_unknown_requires_original_job_reconciliation_not_retry': True,
        'local_boundary_control_count': 5, 'local_controls_are_not_Main_qualification': True,
        'root_review_and_coordinated_dispatch_required': True,
    }
    outputs = {
        'stage-input.json': payload_raw,
        'stage_commit_once.py': stage,
        'stage-against-actual-stage-a.diff': stage_diff,
        'process-request.review-only.json': packet_raw,
        'STAGE_INHERITANCE.json': json.dumps(stage_inheritance, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n',
        'PACKET_REVIEW.json': json.dumps(review, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n',
    }
    assert not any((HERE / name).exists() for name in (*outputs, 'SOURCE_PINS.json'))
    for name, raw in outputs.items():
        write_new(name, raw)
    rows = []
    for path in sorted(HERE.iterdir()):
        if path.name == '__pycache__':
            continue
        assert path.is_file() and not path.is_symlink(), str(path)
        rows.append({'path': path.name, **pin(path.read_bytes())})
    manifest = {
        'schema': 'pocket4-stage-b-frozen-source-closure-v1', 'state_at_seal': 'PREPARED_NOT_SUBMITTED',
        'source': SOURCE_PIN, 'request': REQUEST_PIN, 'process_request': pin(packet_raw),
        'completed_stage_A_job': fixed['completed_stage_A_job'], 'files': rows,
        'private_UI_nodes_window_raw_business_content_or_bundle_included': False,
        'Main_device_or_Git_actions_during_preparation': 0,
        'local_controls': pin(controls_raw), 'local_controls_not_runtime_or_publication_success': True,
        'original_unknown_retained': True, 'production_ready_apps': 0, 'cleanup_actions': 0,
    }
    manifest_raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
    write_new('SOURCE_PINS.json', manifest_raw)
    for row in rows:
        assert pin((HERE / row['path']).read_bytes()) == {key: row[key] for key in ('bytes', 'sha256')}
    directory = os.open(HERE, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    print(json.dumps({'state': 'SEALED_STAGE_B_NOT_SUBMITTED', 'source': SOURCE_PIN, 'request': REQUEST_PIN,
        'stager': pin(stage), 'stage_input': pin(payload_raw), 'process_request': pin(packet_raw),
        'source_manifest': pin(manifest_raw), 'manifest_members': len(rows),
        'actual_stage_A_job': fixed['completed_stage_A_job'], 'remote_or_Main_actions': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
