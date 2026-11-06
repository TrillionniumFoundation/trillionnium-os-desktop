#!/usr/bin/env python3
"""Local-only sealing of the fixed no-action Stage B. Never dispatches tools."""
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
ORIGINAL_B = PROJECT / 'successor_qa/partial_case_runtime_commit_r1/stage-b-candidate-r1'
ROOT = '/home/alex/work/pocket4-beike-no-action-commit-20261106-r1'
KEY = 'pocket4-beike-task878-no-action-commit-stage-b-r1-20261106'
SOURCE_PIN = {'bytes': 77716, 'sha256': 'f36e146221d43359690b2d73969244dce337a9ac36da038d2bae506a2de981b7'}
REQUEST_PIN = {'bytes': 2531, 'sha256': 'a2e6b26f52fc0874a5dddac3435df326124558765236e7a1d19d85c3584c6449'}
ORIGINAL_STAGE_PIN = {'bytes': 5929, 'sha256': '7c2120f00f95540a0a91d60b5692fb0a54db0ea5222e1c03767e5f9b0027e20e'}
A_SOURCE_PIN = {'bytes': 49806, 'sha256': '2a6dfffa73fa7698e6d59039d992c78a17ddaf07f0a01eab0973c327870c5c1e'}
A_STDOUT_PIN = {'bytes': 15528, 'sha256': '099a24caac0527f24a97417419cea432b57663cde227d7c844204b2896b08561'}
A_TERMINAL_PIN = {'bytes': 733, 'sha256': '8ca15446afb6c5a4623632071495abafb57c007459257fc463bac3001529abbe'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def literal(source, name):
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    assert len(nodes) == 1, name
    return ast.literal_eval(nodes[0].value)


def definition(source, name):
    nodes = [node for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
    assert len(nodes) == 1, name
    node = nodes[0]
    return ''.join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])


def replace_once(source, before, after):
    assert source.count(before) == 1, before
    return source.replace(before, after, 1)


def replace_assignment(source, name, value):
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    assert len(nodes) == 1, name
    lines = source.splitlines(keepends=True); node = nodes[0]
    lines[node.lineno - 1:node.end_lineno] = [name + ' = ' + repr(value) + '\n']
    return ''.join(lines)


def write_new(name, raw):
    path = HERE / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:]); assert count > 0
            offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    assert path.read_bytes() == raw


def main():
    worker = (HERE / 'commit_stage_b_once.py').read_bytes()
    request = (HERE / 'request.json').read_bytes()
    assert pin(worker) == SOURCE_PIN and pin(request) == REQUEST_PIN
    compile(worker, str(HERE / 'commit_stage_b_once.py'), 'exec')
    fixed = literal(worker.decode(), 'FIXED_REQUEST')
    assert request == canonical(fixed) + b'\n'
    assert fixed['schema'] == 'pocket4-fixed-no-action-commit-only-request-v1'
    assert fixed['operation'] == 'owned-qa-no-action-commit' and fixed['stage_A_job'] == '1a1b33331ac-fc05-8102'
    assert fixed['original_UNKNOWN_retained'] is True and fixed['automatic_retry'] is False
    assert fixed['coordinator_must_wait_for_actual_stage_B_durable_terminal'] is True
    assert fixed['independent_later_observer_available'] is False and fixed['business_postcondition_observed'] is False
    assert all(type(fixed[name]) is int and fixed[name] == 0 for name in
               ('UI_actions', 'instrumentation_calls', 'permission_changes', 'installs'))
    a_source = (STAGE_A / 'runtime_stage_a_once.py').read_bytes()
    assert pin(a_source) == A_SOURCE_PIN
    assert literal((STAGE_A / 'no_action_core.py').read_text(), 'POSTCONDITION') is None

    control_path = HERE.parent / 'stage-b-controls-attempt1.stdout.original.jsonl'
    controls_raw = control_path.read_bytes(); controls = json.loads(controls_raw)
    assert controls['ok'] is True and controls['case_count'] == 4 and len(controls['cases']) == 4
    assert all(row['passed'] is True for row in controls['cases'])
    assert controls['source_sha256'] == SOURCE_PIN['sha256']
    assert controls['uid'] == controls['euid'] == 1000
    assert controls['whole_process_fd_identities_unchanged'] is True
    assert controls['Main_or_remote_actions'] == 0 and controls['actual_runtime_or_actual_publication_executed'] is False
    assert (HERE.parent / 'stage-b-controls-attempt1.stderr.original.txt').read_bytes() == b''

    names = ('commit_stage_b_once.py', 'request.json', 'stage-a.stdout.original.jsonl', 'stage-a.terminal.original.json')
    bodies = {name: (HERE / name).read_bytes() for name in names}
    pins = {name: pin(raw) for name, raw in bodies.items()}
    assert pins[names[2]] == A_STDOUT_PIN and pins[names[3]] == A_TERMINAL_PIN
    assert bodies[names[2]] == (STAGE_A / 'actual/stdout.original.jsonl').read_bytes()
    assert bodies[names[3]] == (STAGE_A / 'actual/terminal.original.json').read_bytes()
    for name, key in ((names[2], 'stage_A_stdout'), (names[3], 'stage_A_terminal')):
        assert pins[name] == {field: fixed[key][field] for field in ('bytes', 'sha256')}
    payload = {'schema': 'pocket4-stage-b-no-action-commit-stage-payload-v1', 'root': ROOT,
        'files': {name: {**pins[name], 'base64': base64.b64encode(raw).decode('ascii')} for name, raw in bodies.items()}}
    payload_raw = canonical(payload) + b'\n'
    assert len(payload_raw) < 524288

    old = (ORIGINAL_B / 'stage_commit_once.py').read_bytes()
    assert pin(old) == ORIGINAL_STAGE_PIN
    text = old.decode()
    text = replace_once(text, '/home/alex/work/pocket4-beike-partial-case-commit-20261106-r1', ROOT)
    text = replace_assignment(text, 'PINS', pins)
    text = replace_assignment(text, 'ENTRY_SHA', sha(worker))
    text = replace_assignment(text, 'PAYLOAD_SHA', sha(payload_raw))
    text = replace_once(text, 'pocket4-beike-partial-case-commit-20261106-r1', Path(ROOT).name)
    text = replace_once(text, 'pocket4-stage-b-partial-case-commit-stage-payload-v1',
                        'pocket4-stage-b-no-action-commit-stage-payload-v1')
    text = replace_once(text, 'pocket4-stage-b-partial-case-commit-stage-v1',
                        'pocket4-stage-b-no-action-commit-stage-v1')
    text = replace_once(text, 'single-partial-case-commit-owner-not-yet-invoked',
                        'single-no-action-commit-owner-not-yet-invoked')
    text = replace_once(text, 'ca6d11780cc7f6d6a3adf58f5f2bcbe10eefc07fde9c636398b55f2a11d7d82c', sha(request))
    text = replace_once(text, "'--request-bytes', '2596'", "'--request-bytes', " + repr(str(len(request))))
    stage = text.encode('utf-8')
    compile(stage, str(HERE / 'stage_commit_once.py'), 'exec')
    assert literal(text, 'PINS') == pins and literal(text, 'ENTRY_SHA') == sha(worker)
    assert literal(text, 'PAYLOAD_SHA') == sha(payload_raw)
    stage_diff = ''.join(difflib.unified_diff(old.decode().splitlines(True), text.splitlines(True),
        fromfile='actual-partial-stage-b/stage_commit_once.py', tofile='no-action-stage-b/stage_commit_once.py', n=3)).encode()
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', text, '--payload-sha256', sha(payload_raw)],
        'cwd': '/home/alex/work', 'stdin': payload_raw.decode('ascii'),
        'timeout_seconds': 900, 'cpu_quota_percent': 100, 'memory_max_bytes': 1073741824, 'nice': 10,
        'idempotency_key': KEY}
    packet_raw = canonical(packet) + b'\n'
    old_packet = json.loads((ORIGINAL_B / 'process-request.review-only.json').read_bytes())
    for field in ('host', 'executable', 'cwd', 'timeout_seconds', 'cpu_quota_percent', 'memory_max_bytes', 'nice'):
        assert packet[field] == old_packet[field]
    assert packet['args'][:5] == old_packet['args'][:5]

    inherited = json.loads((HERE / 'SOURCE_INHERITANCE.json').read_bytes())
    assert {k: inherited['source'][k] for k in SOURCE_PIN} == SOURCE_PIN
    assert {k: inherited['request'][k] for k in REQUEST_PIN} == REQUEST_PIN
    assert len(inherited['exact_stage_A_functions']) == 16
    for name, expected in inherited['exact_stage_A_functions'].items():
        original = definition(a_source.decode(), name).encode()
        actual = definition(worker.decode(), name).encode()
        assert original == actual and sha(actual) == expected
    old_worker = (ORIGINAL_B / 'commit_stage_b_once.py').read_bytes()
    assert pin(old_worker) == inherited['actual_original_stage_B']
    assert definition(old_worker.decode(), 'commit_envelope') == definition(worker.decode(), 'commit_envelope')
    assert sha(definition(worker.decode(), 'commit_envelope').encode()) == inherited['commit_envelope_definition_sha256']
    assert inherited['exact_evidence_members'] == {'original_failed_step': 90, 'actual_stage_A_step': 57,
        'original_flow_inputs': 5, 'new_prepublication_step': 59, 'total': 211}
    assert definition(a_source.decode(), 'verify_six_commands').replace('stage_a_only', 'stage_b_only') == definition(worker.decode(), 'verify_six_commands')
    stage_inheritance = {
        'schema': 'pocket4-no-action-stage-b-transport-inheritance-v1', 'source': SOURCE_PIN, 'request': REQUEST_PIN,
        'original_actually_used_stage_b_stager': ORIGINAL_STAGE_PIN,
        'original_stage_IO_algorithm_modified': False,
        'stage_difference': 'Only fixed root, pins, schema strings, mode label and exact request argv changed.',
        'same_stage_functions': {name: {'same_bytes': definition(old.decode(), name) == definition(text, name),
            'sha256': sha(definition(text, name).encode())} for name in ('need', 'sha', 'census')},
        'same_original_no_replace_publisher': True,
        'same_actual_stage_A_definitions': inherited['exact_stage_A_functions'],
        'same_six_command_validator_except_request_stage_key': True,
        'original_SystemExit_entry_exact': inherited['original_SystemExit_entry_exact'],
        'new_process_request_not_executed': True,
    }
    assert all(row['same_bytes'] for row in stage_inheritance['same_stage_functions'].values())
    review = {
        'schema': 'pocket4-no-action-stage-b-packet-review-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'source_root': ROOT, 'source': SOURCE_PIN, 'request': REQUEST_PIN,
        'stager': pin(stage), 'stage_input': pin(payload_raw), 'process_request': pin(packet_raw),
        'staged_files': pins, 'idempotency_key': KEY,
        'resource_bounds': {key: packet[key] for key in ('timeout_seconds', 'cpu_quota_percent', 'memory_max_bytes', 'nice')},
        'actual_stage_A_job': fixed['stage_A_job'], 'actual_stage_A_stdout': A_STDOUT_PIN, 'actual_stage_A_terminal': A_TERMINAL_PIN,
        'worker_recorded_readonly_commands': 6, 'worker_total_transport_receipts': 8,
        'worker_private_foreground_transports': 2, 'worker_UI_or_instrumentation_actions': 0,
        'private_UI_or_bundle_in_packet': False, 'stage_Main_commands_or_locks': 0,
        'exact_evidence_members': inherited['exact_evidence_members'],
        'no_later_observer_or_business_postcondition_invented': True,
        'compatibility_publication': 'one original O_EXCL temporary + no-replace link + owned temporary unlink + directory fsync',
        'original_Flow_reconcile_called': False,
        'original_Flow_consumer_Session_foreground_helper_guard_modified': False,
        'original_failed_unknown_preserved': True, 'old_action_replayed': False,
        'no_current_tree_or_UI_action_authority_claimed': True,
        'frozen_consumer_validates_controller_terminal': False,
        'root_must_maintain_action_freeze_until_actual_B_owned_exit_and_durable_terminal': True,
        'publication_or_exit_unknown_requires_original_job_reconciliation_not_retry': True,
        'local_boundary_control_count': 4, 'local_controls_are_not_Main_qualification': True,
        'root_review_and_coordinated_dispatch_required': True,
    }
    outputs = {
        'stage-input.json': payload_raw, 'stage_commit_once.py': stage,
        'stage-against-actual-partial-stage-b.diff': stage_diff,
        'process-request.review-only.json': packet_raw,
        'STAGE_INHERITANCE.json': json.dumps(stage_inheritance, sort_keys=True, indent=2).encode() + b'\n',
        'PACKET_REVIEW.json': json.dumps(review, sort_keys=True, indent=2).encode() + b'\n',
        'local-controls.stdout.original.jsonl': controls_raw,
        'local-controls.stderr.original.txt': b'',
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
    external = []
    for name in ('assemble_stage_b.py', 'stage_b_evidence.fragment.py', 'check_stage_b_controls.py'):
        path = HERE.parent / name
        external.append({'path': str(path.relative_to(PROJECT)), **pin(path.read_bytes()), 'local_only': True})
    manifest = {
        'schema': 'pocket4-no-action-stage-b-frozen-source-closure-v1', 'state_at_seal': 'PREPARED_NOT_SUBMITTED',
        'source': SOURCE_PIN, 'request': REQUEST_PIN, 'process_request': pin(packet_raw),
        'actual_stage_A_job': fixed['stage_A_job'], 'files': rows, 'local_preparation_inputs': external,
        'private_UI_nodes_window_raw_business_content_or_bundle_included': False,
        'Main_device_or_Git_actions_during_preparation': 0, 'local_controls': pin(controls_raw),
        'local_controls_not_runtime_or_publication_success': True,
        'original_unknown_retained': True, 'production_ready_apps': 0, 'cleanup_actions': 0,
    }
    manifest_raw = json.dumps(manifest, sort_keys=True, indent=2).encode() + b'\n'
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
        'actual_stage_A_job': fixed['stage_A_job'], 'remote_or_Main_actions': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
