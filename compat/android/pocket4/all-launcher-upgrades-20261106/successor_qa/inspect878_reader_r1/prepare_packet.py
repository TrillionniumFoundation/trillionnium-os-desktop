#!/usr/bin/env python3
"""Local-only one-time binding of the reviewed reader to actual public evidence."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def exact(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    return raw


def main():
    source_path = HERE / 'read_completed_inspect878.py'
    template = source_path.read_text()
    assert template.count('CONFIGURATION_PLACEHOLDER = True') == 1
    assert template.count('LOAD_BASE_PLACEHOLDER = True') == 1
    prefix = PROJECT / 'successor_qa'
    ui = exact(prefix / 'reusable_owned_ui_r1/owned_ui_request_once.py', 25377,
               'c394598e477f1912378c6c3d582850a196e64f77791d0b7f5c4d498ec9b61e38').decode()
    tree = ast.parse(ui)
    load_base = next(ast.get_source_segment(ui, node) for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name == 'load_base')
    constants = {}
    wanted = {'BASE', 'SCOPE', 'FLOW', 'ROOT', 'LAUNCH_SCOPE_SHA'}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('BASE', 'FLOW', 'ROOT', 'LAUNCH_SCOPE_SHA'):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    actual = prefix / 'reusable_owned_ui_r1/actual-inspect-01'
    stdout = exact(actual / 'stdout.original.jsonl', 14794,
        '11a958010bb7dbaa4865385018a72fef9d6abe12b378805da84f3006fd4f25c3')
    terminal = exact(actual / 'status-1.original.txt', 733,
        '9333a1e8b841f253216b6d2ef48f393eba418a90f0283ae2ec35a9fe67dd697c')
    lines = stdout.splitlines(keepends=True)
    assert len(lines) == 2
    value = json.loads(lines[1]); child = json.loads(value['child_stdout_original'])
    raw_adapter = child['original_stdout'].encode(); adapter = json.loads(raw_adapter)
    assert len(raw_adapter) == 5752 and sha(raw_adapter) == 'fa0d8966f92122fc32b161b3e19f88ba86bc6cf4a5971e9359c13bc82af8b302'
    result = dict(value); joint = result.pop('joint_artifact')
    assert len(canonical(result) + b'\n') == joint['bytes'] == 13629
    assert sha(canonical(result) + b'\n') == joint['sha256'] == '7ad76e72aa20919fa8695899c27233b89a9794e0446379db9f282553b671f9dc'
    flow = constants['FLOW']; step = 'inspect-new-session-01'; folder = flow + '/steps/' + step
    pins = {
        'BASE': constants['BASE'],
        'CORE': {'path': '/home/alex/work/pocket4-beike-owned-postcondition-20261106-baaf68ac0d617dbe3894f714b18f099b/owned_postcondition_core.py', 'bytes': 28714,
                 'sha256': '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41'},
        'QA': {'path': '/home/alex/work/pocket4-successor-qa-build-source-b34f158f88bbebf112840fd88df25d03/qa_contract.py', 'bytes': 52359,
               'sha256': 'bfe1e781e254033ab5c5b7616a928d309998bde4cbc243bd542c3eb4805eda6e'},
        'TRANSPORT': {'path': '/home/alex/work/pocket4-successor-qa-source-b34f158f88bbebf112840fd88df25d03/recorder/bound_android_transport.py', 'bytes': 15603,
                      'sha256': '069d003809d95b33e0d727fdec3ca6e8488e214180449cacbad07e66a302652f'},
        'UI_SOURCE': value['source'], 'JOINT': joint, 'STEP_RESULT': child['original_result'],
        'SCOPE': {'path': flow + '/scope.json', 'bytes': 1002,
                  'sha256': '08c014646be1d32ef9eacc119f7930b941fc696333bd4cff9d74106f19dba516'},
        'PLAN': child['input_artifact'],
    }
    config = {**pins, 'FLOW': flow, 'STEP': step, 'FOLDER': folder,
        'JOB': '1a1b2537fa5-fc05-7d8c', 'EPOCH': adapter['epoch_sha256'],
        'NONCE': '8f3efa4249d24d303984ec1887d5914b', 'WIRE': adapter['inspection_wire_sha256'],
        'ACTUAL_STDOUT_SHA': sha(stdout), 'TERMINAL_SHA': sha(terminal),
        'CHILD_SHA': value['child_stdout_sha256'], 'ADAPTER_STDOUT_SHA': sha(raw_adapter),
        'LAUNCH_SCOPE_SHA': constants['LAUNCH_SCOPE_SHA'],
        'NATIVE_RECEIPT_SHA': adapter['owned_task']['native_receipt_sha256'],
        'HELD_HELPER': '/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry',
        'EXPECTED_PLAN': json.loads(exact(prefix / 'reusable_owned_ui_r1/inspect-new-session-01.plan.json',
            178, 'd8d1e4b0202d25d9fe824b54e8d480d26d5edec3eabbd70f61a342034f3468e7')),
        'STAGE_STDOUT': lines[0], 'TERMINAL_RAW': terminal}
    nonce = config['NONCE']
    selected = {'intent.json', 'held-main-binding.json', nonce + '.request.json', nonce + '.assessment.json',
                'command-005.intent.json', 'command-005.result.json', 'command-005.stdout', 'command-005.stderr',
                'transport-006.intent.json', 'transport-006.command-result.json', 'transport-006.verified-result.json'}
    allowed = {pin['path'] for pin in pins.values()} | {flow + '/launch-scope.json'} | {folder + '/' + name for name in selected}
    assert len(allowed) == 21
    config_text = '\n'.join(key + ' = ' + repr(item) for key, item in config.items())
    config_text += '\nALLOWED_PATHS = frozenset(' + repr(sorted(allowed)) + ')'
    source = template.replace('CONFIGURATION_PLACEHOLDER = True', config_text).replace('LOAD_BASE_PLACEHOLDER = True', load_base)
    compile(source, str(source_path), 'exec')
    source_path.write_bytes(source.encode('utf-8'))
    source_sha = sha(source.encode())
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', source],
        'cwd': '/home/alex/work', 'timeout_seconds': 120, 'cpu_quota_percent': 100,
        'memory_max_bytes': 268435456, 'nice': 10,
        'idempotency_key': 'pocket4-beike-completed-inspect878-reader-r1-20261106'}
    packet_raw = json.dumps(packet, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n'
    with (HERE / 'process-request.review-only.json').open('xb') as output:
        output.write(packet_raw)
    proof = {'schema': 'pocket4-inspect878-local-reader-packet-proof-v1', 'ok': True,
        'source': {'path': source_path.name, 'bytes': len(source.encode()), 'sha256': source_sha},
        'packet': {'path': 'process-request.review-only.json', 'bytes': len(packet_raw), 'sha256': sha(packet_raw)},
        'historical_stdout': {'bytes': len(stdout), 'sha256': sha(stdout)},
        'historical_terminal': {'bytes': len(terminal), 'sha256': sha(terminal)},
        'historical_joint': joint, 'historical_step_result': child['original_result'],
        'exact_allowed_file_count': len(allowed), 'exact_allowed_paths': sorted(allowed),
        'load_base_exact_frozen_original': True, 'remote_submitted': False, 'Main_commands': 0,
        'private_UI_read_or_saved_locally': False, 'no_integer_conversion_through_JavaScript': True}
    with (HERE / 'LOCAL_PACKET_PROOF.json').open('xb') as output:
        output.write(json.dumps(proof, ensure_ascii=True, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps(proof, ensure_ascii=True, sort_keys=True))


if __name__ == '__main__':
    main()
