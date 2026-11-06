#!/usr/bin/env python3
"""Local packet sealing only; no device, network, Git or process submission."""
import ast
import base64
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
OUT = HERE / 'stage-a-candidate-r1'
ROOT = '/home/alex/work/pocket4-beike-no-action-runtime-20261106-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def file_pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def put(name, raw):
    with (OUT / name).open('xb') as f:
        f.write(raw)


def assignment(text, name, expression):
    rows = [n for n in ast.parse(text).body if isinstance(n, ast.Assign) and
            any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    assert len(rows) == 1 and rows[0].lineno == rows[0].end_lineno
    lines = text.splitlines(True); lines[rows[0].lineno - 1] = name + ' = ' + expression + '\n'
    return ''.join(lines)


def definition(text, path):
    nodes = ast.parse(text).body
    for name in path.split('.'):
        selected = [n for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
        assert len(selected) == 1, path
        found = selected[0]; nodes = found.body
    return ''.join(text.splitlines(True)[found.lineno - 1:found.end_lineno])


def main():
    worker = (OUT / 'runtime_stage_a_once.py').read_bytes()
    core = (OUT / 'no_action_core.py').read_bytes()
    controls = (HERE / 'local-controls-attempt2.stdout.original.jsonl').read_bytes()
    result = json.loads(controls)
    assert result['ok'] is True and result['case_count'] == 6 and result['source_sha256'] == sha(worker)
    assert result['core_sha256'] == sha(core) and result['whole_process_fd_identities_unchanged'] is True
    assert result['process_fds_before'] == result['process_fds_after']
    stderr = (HERE / 'local-controls-attempt2.stderr.original.txt').read_bytes(); assert stderr == b''
    originals = PROJECT / 'successor_qa/partial_case_runtime_commit_r1/stage-a-candidate-r1'
    old = (originals / 'stage_runtime_once.py').read_bytes()
    assert len(old) == 5925 and sha(old) == 'ce819668e952f049ec909ff8d569f0896a3a0b423be1c81e185385b4234f951a'
    request = (OUT / 'request.json').read_bytes()
    assert json.loads(request)['stage_B_unsealed'] is True
    names = ('runtime_stage_a_once.py', 'no_action_core.py', 'read_failed_search_click.frozen.py', 'request.json',
             'reader.stdout.original.json', 'reader.terminal.original.json',
             'prior-inspect.stdout.original.jsonl', 'prior-inspect.terminal.original.json')
    bodies = {name: (OUT / name).read_bytes() for name in names}
    pins = {name: file_pin(raw) for name, raw in bodies.items()}
    payload = {'schema': 'pocket4-no-action-runtime-proof-stage-payload-v1', 'root': ROOT,
        'files': {name: {**pins[name], 'base64': base64.b64encode(raw).decode('ascii')}
                  for name, raw in bodies.items()}}
    payload_raw = canonical(payload) + b'\n'; assert len(payload_raw) < 524288
    stage = old.decode().replace('pocket4-beike-partial-case-runtime-20261106-r1', Path(ROOT).name)
    stage = stage.replace('pocket4-stage-a-runtime-proof-stage-payload-v1', 'pocket4-no-action-runtime-proof-stage-payload-v1')
    stage = stage.replace('pocket4-stage-a-runtime-proof-stage-v1', 'pocket4-no-action-runtime-proof-stage-v1')
    stage = stage.replace('new readonly runtime proof owner and actual host prerequisites',
                          'new no-action proof owner and exact historical prerequisites')
    for name, value in (('ROOT', 'Path(' + repr(ROOT) + ')'), ('PINS', repr(pins)),
                        ('ENTRY_SHA', repr(sha(worker))), ('PAYLOAD_SHA', repr(sha(payload_raw)))):
        stage = assignment(stage, name, value)
    old_sha = 'e21cf095aa8a72d95f04a7a3acea477675daeb0882d0919dcad27eb01daa1d9d'
    assert stage.count("'--request-sha256', '" + old_sha + "', '--request-bytes', '838'") == 1
    stage = stage.replace("'--request-sha256', '" + old_sha + "', '--request-bytes', '838'",
        "'--request-sha256', '" + sha(request) + "', '--request-bytes', '" + str(len(request)) + "'")
    compile(stage, ROOT + '/stage_runtime_once.py', 'exec')
    for name in names:
        if name.endswith('.py'):
            compile(bodies[name], ROOT + '/' + name, 'exec')
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', stage, '--payload-sha256', sha(payload_raw)],
        'cwd': '/home/alex/work', 'stdin': payload_raw.decode('ascii'), 'timeout_seconds': 900,
        'cpu_quota_percent': 100, 'memory_max_bytes': 1073741824, 'nice': 10,
        'idempotency_key': 'pocket4-beike-task878-no-action-runtime-stage-a-r1-20261106'}
    packet_raw = canonical(packet) + b'\n'
    for name, raw in {'stage_runtime_once.py': stage.encode(), 'stage-input.json': payload_raw,
        'process-request.review-only.json': packet_raw, 'local-controls.stdout.original.jsonl': controls,
        'local-controls.stderr.original.txt': stderr}.items():
        put(name, raw)
    put('stage-against-actual-partial-stage-a.diff', ''.join(difflib.unified_diff(
        old.decode().splitlines(True), stage.splitlines(True), fromfile='actual-partial-stage-a/stager',
        tofile='no-action-stage-a/stager', n=3)).encode())
    source_rows = json.loads((originals / 'SOURCE_INHERITANCE.json').read_bytes())['unchanged_exact_source_and_predicate_definitions']
    for row in source_rows:
        raw = (PROJECT / row['path']).read_bytes()
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
        for name, digest in row['method_definition_sha256'].items():
            assert sha(definition(raw.decode(), name).encode()) == digest
    stage_inheritance = {'schema': 'pocket4-no-action-stage-a-frozen-contract-inheritance-v1',
        'unchanged_source_and_method_rows': source_rows,
        'unchanged_source_count': len(source_rows),
        'unchanged_method_count': sum(len(r['method_definition_sha256']) for r in source_rows),
        'original_recorder_helper_guard_consumer_modified': False,
        'original_frozen_stage_main_only_changes': ['fixed new root', 'schema labels', 'eight closed members',
                                                  'exact request hash and length', 'descriptive docstring'],
        'original_stage_helpers_exact': {name: definition(old.decode(), name) == definition(stage, name)
                                         for name in ('need', 'sha', 'census')},
        'actual_local_controls_source_pin_matched': True}
    assert all(stage_inheritance['original_stage_helpers_exact'].values())
    put('STAGE_INHERITANCE.json', json.dumps(stage_inheritance, sort_keys=True, indent=2).encode() + b'\n')
    review = {'schema': 'pocket4-no-action-stage-a-exact-packet-review-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'source': pins[names[0]], 'core': pins[names[1]], 'request': pins['request.json'],
        'stage': file_pin(stage.encode()), 'stage_input': file_pin(payload_raw),
        'process_request': file_pin(packet_raw), 'staged_files': pins,
        'source_root': ROOT, 'idempotency_key': packet['idempotency_key'],
        'resource_bounds': {k: packet[k] for k in ('timeout_seconds', 'cpu_quota_percent', 'memory_max_bytes', 'nice')},
        'historic_original_files': 101, 'historic_step_files': 90, 'historic_recorded_commands': 10,
        'historic_transport_receipts': 13, 'new_recorded_readonly_commands': 6,
        'new_private_foreground_transports': 2, 'new_instrumentation_or_UI_actions': 0,
        'stage_B_source_or_request_sealed': False, 'publication_function_present': False,
        'original_FAILED_UNKNOWN_retained': True, 'private_UI_or_bundle_bytes_in_packet': False,
        'no_later_observer_or_postcondition_manufactured': True,
        'original_whole48_scope_borrowed': False, 'actual_live_gate_not_yet_run': True}
    put('PACKET_REVIEW.json', json.dumps(review, sort_keys=True, indent=2).encode() + b'\n')
    rows = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != 'SOURCE_PINS.json':
            raw = path.read_bytes(); rows.append({'path': path.name, **file_pin(raw)})
    put('SOURCE_PINS.json', json.dumps({'schema': 'pocket4-no-action-stage-a-source-pins-v1',
        'files': rows, 'private_UI_included': False, 'device_submissions': 0}, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps({'state': 'SEALED_NO_ACTION_STAGE_A_NOT_SUBMITTED', 'worker': review['source'],
        'core': review['core'], 'stage': review['stage'], 'process_request': review['process_request'],
        'staged_members': len(pins), 'inheritance_sources': len(source_rows),
        'stage_B_sealed': False}, sort_keys=True))


if __name__ == '__main__':
    main()
