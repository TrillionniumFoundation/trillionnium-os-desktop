#!/usr/bin/env python3
"""Local packet assembly only. The caller, not this file, dispatches anything."""
import ast
import base64
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
ROOT = '/home/alex/work/pocket4-beike-partial-case-runtime-20261106-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def file_pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def assignment_replace(text, key, value):
    tree = ast.parse(text)
    rows = [node for node in tree.body if isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and target.id == key for target in node.targets)]
    assert len(rows) == 1 and rows[0].lineno == rows[0].end_lineno, key
    lines = text.splitlines(True); lines[rows[0].lineno - 1] = key + ' = ' + repr(value) + '\n'
    return ''.join(lines)


def definition(text, path):
    nodes = ast.parse(text).body
    for name in path.split('.'):
        selected = [node for node in nodes if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
        assert len(selected) == 1, path
        found = selected[0]; nodes = found.body
    return ''.join(text.splitlines(True)[found.lineno - 1:found.end_lineno])


def main():
    worker = (HERE / 'runtime_stage_a_once.py').read_bytes(); compile(worker, str(HERE / 'runtime_stage_a_once.py'), 'exec')
    report = json.loads((HERE / 'local-controls.stdout.original.jsonl').read_bytes())
    assert report['ok'] is True and report['case_count'] == 6 and report['source_sha256'] == sha(worker)
    assert (HERE / 'local-controls.stderr.original.txt').read_bytes() == b''
    request = (HERE / 'request.json').read_bytes(); value = json.loads(request)
    assert value['reconciliation_published'] is False and value['stage_B_unsealed'] is True
    originals = PROJECT / 'successor_qa/partial_case_proof_r1/candidate-r1'
    old = (originals / 'stage_verify_host_once.py').read_bytes()
    assert len(old) == 6215 and sha(old) == '9819ce596773c1b66bb45335d07e2c4a6d777c0e9566cb9939fc40fc12ff35ed'
    names = ('runtime_stage_a_once.py', 'request.json', 'host.stdout.original.jsonl', 'host.terminal.original.json')
    bodies = {name: (HERE / name).read_bytes() for name in names}
    pins = {name: file_pin(body) for name, body in bodies.items()}
    payload = {'schema': 'pocket4-stage-a-runtime-proof-stage-payload-v1', 'root': ROOT,
        'files': {name: {**pins[name], 'base64': base64.b64encode(raw).decode('ascii')} for name, raw in bodies.items()}}
    payload_raw = canonical(payload) + b'\n'; assert len(payload_raw) < 524288
    text = old.decode()
    text = text.replace('Stage one fixed host-only partial-case verifier and exact historical inputs.',
                        'Stage only the new readonly runtime proof owner and actual host prerequisites.')
    text = text.replace('pocket4-beike-partial-case-proof-20261106-r1', Path(ROOT).name)
    text = assignment_replace(text, 'PINS', pins)
    text = assignment_replace(text, 'ENTRY_SHA', sha(worker))
    text = assignment_replace(text, 'PAYLOAD_SHA', sha(payload_raw))
    text = text.replace('pocket4-fixed-partial-case-host-stage-payload-v1', 'pocket4-stage-a-runtime-proof-stage-payload-v1')
    text = text.replace('pocket4-partial-case-historical-host-stage-v1', 'pocket4-stage-a-runtime-proof-stage-v1')
    text = text.replace('host-only-verification-not-yet-invoked', 'readonly-runtime-candidate-not-yet-invoked')
    text = text.replace('verify_partial_case_host.py', 'runtime_stage_a_once.py')
    text = text.replace("'--verify-host-once'", "'--execute-runtime-once'")
    old_argv = "sys.argv = [str(entry), '--execute-runtime-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['runtime_stage_a_once.py']['bytes'])]"
    new_argv = old_argv[:-1] + ", '--request-sha256', " + repr(sha(request)) + ", '--request-bytes', " + repr(str(len(request))) + "]"
    assert text.count(old_argv) == 1; text = text.replace(old_argv, new_argv)
    stage = text.encode(); compile(stage, str(HERE / 'stage_runtime_once.py'), 'exec')
    stage_diff = ''.join(difflib.unified_diff(old.decode().splitlines(True), text.splitlines(True),
        fromfile='actual-host-verifier/stage_verify_host_once.py', tofile='stage-a/stage_runtime_once.py', n=3)).encode()
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', text, '--payload-sha256', sha(payload_raw)],
        'cwd': '/home/alex/work', 'stdin': payload_raw.decode('ascii'),
        'timeout_seconds': 900, 'cpu_quota_percent': 100, 'memory_max_bytes': 1073741824, 'nice': 10,
        'idempotency_key': 'pocket4-beike-task878-partial-case-runtime-stage-a-r1-20261106'}
    packet_raw = canonical(packet) + b'\n'
    (HERE / 'stage-input.json').write_bytes(payload_raw)
    (HERE / 'stage_runtime_once.py').write_bytes(stage)
    (HERE / 'stage-against-actual-host.diff').write_bytes(stage_diff)
    (HERE / 'process-request.review-only.json').write_bytes(packet_raw)

    source_rows = []
    exact_methods = [
        ('successor_qa/reconstructed/source-generation-r2/helper/qa_adapter.py', 29378,
         'ad54e8583ffb8b4ff186accde10199aee1ab063bd5dbbb5b9586c908ebebb10c',
         ['own_source', 'qualified_build', 'Session.__init__', 'Session.installed', 'Session.task', 'Session.foreground']),
        ('successor_qa/reconstructed/source-generation-r2/recorder/recorder.py', 39563,
         '0e50c67b1d5d251766fb58a69d9e62e119f0663ff2c4115ae326874cf95d6c09',
         ['Flow.__init__', 'Flow.begin', 'Flow.bind', 'Flow.guard', 'Flow.close', 'Flow.reconciled', 'Flow.reconcile', 'lock_file', 'write_new']),
        ('successor_qa/partial_case_proof_r1/candidate-r1/partial_case_core.py', 34105,
         '13ff07c305afcd2894b240fae52b436567784cf605623361723a86253d33fb96',
         ['binding_identity', 'OriginalSequence.command', 'OriginalSequence.packages', 'OriginalSequence.task',
          'OriginalSequence.foreground', 'OriginalSequence.complete']),
        ('successor_qa/owned_postcondition_reconciler_r1/candidate-r2/owned_postcondition_core.py', 28714,
         '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41',
         ['held_binding_identity', 'compare_held_bindings', 'command_success', 'command_argv', 'installed_identity']),
        ('successor_qa/partial_case_proof_r1/candidate-r1/verify_partial_case_host.py', 27116,
         'afd9a9410051a4e72e4f5c7e9434bfa60b592fdb02672e7d1df1b3bd8d1ecd34',
         ['collect_and_verify', 'original_terminal']),
        ('successor_qa/owned_cleanup_r1/cleanup_owned_task_once.py', 22233,
         '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf',
         ['read', 'pinned', 'load', 'require_owned_exit']),
        ('successor_qa/ffi_owned_generation_r2/candidate-r1/prepare_beike_owned_lifetime.py', 20132,
         '76b858b83c7304287fedb13f80c889e3fa7a8d6d32d4183409a5ad6fce269baf',
         ['probe_proof', 'initialize_library', 'stable_library', 'pin_runtime_files']),
        ('successor_qa/ffi_bootstrap_probe_r1/probe_ffi_bootstrap.py', 18199,
         'c7fc2c4a9397d861e27f257e3e0788cd76f7867f006d1b873b2916303b35ce82',
         ['run_owned_child', 'census', 'same_descriptors']),
    ]
    for path, length, digest, methods in exact_methods:
        raw = (PROJECT / path).read_bytes(); assert len(raw) == length and sha(raw) == digest
        source_rows.append({'path': path, 'bytes': length, 'sha256': digest,
            'method_definition_sha256': {name: sha(definition(raw.decode(), name).encode()) for name in methods},
            'modified': False})
    inherited = json.loads((HERE / 'SOURCE_INHERITANCE.json').read_bytes())
    inherited['unchanged_exact_source_and_predicate_definitions'] = source_rows
    inherited['stage_exact_inherited_definitions'] = {name: {
        'same_bytes': definition(old.decode(), name) == definition(text, name),
        'definition_sha256': sha(definition(text, name).encode())} for name in ('need', 'sha', 'census')}
    inherited['stage_IO_logic_difference'] = 'Only fixed source/root/schema/argv/pins changed; mkdir/O_EXCL/root0400/fsync/fullstat/readback/FD gate unchanged.'
    (HERE / 'SOURCE_INHERITANCE.json').write_bytes(json.dumps(inherited, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n')
    (HERE / 'PACKET_REVIEW.json').write_bytes(json.dumps({
        'schema': 'pocket4-stage-a-runtime-packet-review-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'source': pins[names[0]], 'request': pins['request.json'], 'source_root': ROOT,
        'stager': file_pin(stage), 'stage_input': file_pin(payload_raw), 'process_request': file_pin(packet_raw),
        'staged_files': pins, 'idempotency_key': packet['idempotency_key'],
        'resource_bounds': {key: packet[key] for key in ('timeout_seconds', 'cpu_quota_percent', 'memory_max_bytes', 'nice')},
        'private_UI_or_bundle_in_packet': False, 'Main_commands_in_stage': 0,
        'worker_readonly_commands': 6, 'worker_private_foreground_transports': 2,
        'worker_UI_or_instrumentation_actions': 0, 'compatibility_publication_implemented': False,
        'stage_B_request_created': False, 'original_failed_unknown_preserved': True,
        'local_boundary_control_count': 6, 'local_controls_are_not_Main_qualification': True,
        'root_review_and_coordinated_dispatch_required': True,
    }, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps({'state': 'SEALED_STAGE_A_ONLY_NOT_SUBMITTED', 'source': pins[names[0]],
        'stager': file_pin(stage), 'process_request': file_pin(packet_raw), 'stage_B_created': False}))


if __name__ == '__main__':
    main()
