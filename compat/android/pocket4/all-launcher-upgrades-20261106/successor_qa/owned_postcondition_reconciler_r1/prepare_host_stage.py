#!/usr/bin/env python3
"""Create a local, fixed host-only stage request. Never contacts Pocket4."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import secrets

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_once(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def main():
    output = HERE / 'host-stage-candidate-r1'
    output.mkdir(mode=0o700)
    files = {}
    for filename in ('owned_postcondition_core.py', 'publish_owned_reconciliation.py'):
        raw = (HERE / filename).read_bytes(); compile(raw, filename, 'exec'); files[filename] = raw
    constants = {}
    for node in ast.parse(files['publish_owned_reconciliation.py']).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('CORE_BYTES', 'CORE_SHA', 'PRIVATE_BUNDLE', 'HOME_POSTCONDITION'):
                    constants[target.id] = ast.literal_eval(node.value)
    assert len(files['owned_postcondition_core.py']) == constants['CORE_BYTES']
    assert sha(files['owned_postcondition_core.py']) == constants['CORE_SHA']
    for role, directory, plan in (
            ('action', 'close-entry-popup-r1', 'close-entry-popup-01.plan.json'),
            ('observation', 'inspect-after-close-r2', 'inspect-after-close-02.plan.json')):
        actual = HERE.parent / 'actual' / directory
        for suffix, filename in (('process-request.json', 'process-request.json'),
                                 ('process-start.json', 'process-start.raw.json'),
                                 ('terminal.json', 'terminal.raw.json'), ('stdout.jsonl', 'stdout.raw.jsonl')):
            files[role + '.' + suffix] = (actual / filename).read_bytes()
        observed = json.loads((actual / 'process-read-0.raw.json').read_bytes())['stderr']
        terminal = json.loads(files[role + '.terminal.json'])
        assert observed == {'bytes_hex': '', 'eof': True, 'next_offset': 0, 'offset': 0, 'size': 0, 'text': ''}
        assert terminal['log_bytes']['stderr'] == {'seen': 0, 'stored': 0}
        files[role + '.stderr.bin'] = bytes.fromhex(observed['bytes_hex'])
        files[role + '.plan.json'] = (HERE.parent / 'owned_flow_r1' / plan).read_bytes()
    nonce = secrets.token_hex(16)
    root = '/home/alex/work/pocket4-beike-owned-postcondition-20261106-' + nonce
    request = {'schema': 'pocket4-beike-owned-postcondition-request-v1', 'stage_nonce': nonce,
               'flow_dir': '/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb',
               'unknown_step': 'close-entry-popup-01', 'observation_step': 'inspect-after-close-02',
               'proof_step': 'owned-postcondition-close-01', 'postcondition': constants['HOME_POSTCONDITION'],
               'private_bundle': constants['PRIVATE_BUNDLE'], 'publish_new_owned_qa_producer': True,
               'execution_pins': {key: {'bytes': len(raw), 'sha256': sha(raw)} for key, raw in files.items()
                                  if key.startswith(('action.', 'observation.'))}}
    files['request.json'] = (json.dumps(request, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    pins = {key: {'bytes': len(raw), 'sha256': sha(raw)} for key, raw in sorted(files.items())}
    payload = {'schema': 'pocket4-owned-postcondition-host-stage-payload-v1', 'root': root,
               'files': {key: {**pins[key], 'base64': base64.b64encode(raw).decode('ascii')} for key, raw in sorted(files.items())}}
    payload_raw = (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert len(payload_raw) <= 524288
    template = (HERE / 'stage_host_verify_once.py.in').read_text()
    stage = template.replace('@@ROOT@@', repr(root)).replace('@@PINS@@', repr(pins))
    stage = stage.replace('@@ENTRY_SHA@@', repr(pins['publish_owned_reconciliation.py']['sha256']))
    stage = stage.replace('@@REQUEST_SHA@@', repr(pins['request.json']['sha256']))
    stage = stage.replace('@@PAYLOAD_SHA@@', repr(sha(payload_raw)))
    assert '@@' not in stage
    compile(stage, 'stage_host_verify_once.py', 'exec')
    stage_raw = stage.encode()
    process = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
               'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', stage,
                        '--payload-sha256', sha(payload_raw)],
               'stdin': payload_raw.decode('ascii'), 'cwd': '/home/alex/work',
               'idempotency_key': 'pocket4-beike-postcondition-host-verify-20261106-' + nonce,
               'timeout_seconds': 180, 'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10}
    process_raw = (json.dumps(process, ensure_ascii=True, indent=2) + '\n').encode()
    for filename, raw in files.items():
        write_once(output / filename, raw)
    for filename, raw in (('stage_host_verify_once.py', stage_raw), ('stage-input.json', payload_raw),
                          ('process-request.json', process_raw)):
        write_once(output / filename, raw)
    manifest = {'schema': 'pocket4-owned-postcondition-host-stage-source-pins-v1',
                'root': root, 'idempotency_key': process['idempotency_key'], 'mode': 'verify-host-only',
                'Main_execution_authorized_by_this_packet': False, 'private_bundle_copied': False,
                'actual_source_validation_run': False, 'reconciliation_published': False,
                'files': {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
                          for p in sorted(output.iterdir()) if p.is_file()}}
    raw = (json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    write_once(output / 'SOURCE_PINS.json', raw)
    print(json.dumps({'root': root, 'files': len(manifest['files']), 'source_manifest_sha256': sha(raw),
                     'source_manifest_bytes': len(raw), 'process_request': manifest['files']['process-request.json'],
                     'publisher': pins['publish_owned_reconciliation.py'], 'core': pins['owned_postcondition_core.py'],
                     'packet_executed': False}, sort_keys=True))


if __name__ == '__main__':
    main()
