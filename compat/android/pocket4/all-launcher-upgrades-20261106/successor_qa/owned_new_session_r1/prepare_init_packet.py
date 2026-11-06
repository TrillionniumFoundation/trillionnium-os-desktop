#!/usr/bin/env python3
"""Seal only the new init request from local exact bytes. Never execute it."""
import ast
import base64
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'owned_cleanup_r1/stage_cleanup_once.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode('ascii')


def once(name, raw):
    path = HERE / name
    with path.open('xb') as stream:
        stream.write(raw)
    assert path.read_bytes() == raw


def main():
    source = (HERE / 'new_session_once.py').read_bytes()
    compile(source, 'new_session_once.py', 'exec')
    tree = ast.parse(source); constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    root, flow = constants['ROOT'], constants['FLOW']
    names = ('new_session_once.py', 'cleanup.stdout.original.jsonl', 'cleanup.terminal.original.json')
    inputs = {name: (HERE / name).read_bytes() for name in names}
    pins = {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in inputs.items()}
    payload = encode({'schema': 'pocket4-original-new-session-stage-payload-v1', 'root': root,
        'files': {name: {**pins[name], 'base64': base64.b64encode(raw).decode('ascii')} for name, raw in inputs.items()}})
    before = PRIOR.read_bytes()
    assert len(before) == 5445 and sha(before) == 'a9393e1e82d373ebbab0809b06798e4d340d1cd68416cd5c5ef483e59b25ed82'
    stage = before.decode()
    replacements = {
        '"""Stage one fixed original-recorder cleanup wrapper, then invoke it once."""':
            '"""Stage exact new-session sources and actual cleanup receipts; invoke only init."""',
        "ROOT = Path('/home/alex/work/pocket4-beike-owned-cleanup-20261106-r1')": 'ROOT = Path(' + repr(root) + ')',
        "PINS = {'cleanup_owned_task_once.py': {'bytes': 22233, 'sha256': '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'}}": 'PINS = ' + repr(pins),
        "ENTRY_SHA = '559ae3641a5f6e017914102af61c5f8e909605cb92be32d1a045ae7c66a935cf'": 'ENTRY_SHA = ' + repr(sha(source)),
        "PAYLOAD_SHA = '4cac0c38f7abd057929efc626ded4ddce25efc2a07c3e1100ee65196d97ffc80'": 'PAYLOAD_SHA = ' + repr(sha(payload)),
        "'pocket4-original-owned-cleanup-stage-payload-v1'": "'pocket4-original-new-session-stage-payload-v1'",
        "ROOT.name == 'pocket4-beike-owned-cleanup-20261106-r1'": "ROOT.name == 'pocket4-beike-owned-new-session-20261106-r1'",
        "'pocket4-original-owned-cleanup-stage-v1'": "'pocket4-original-new-session-stage-v1'",
        "'mode': 'original-owned-task-cleanup-not-yet-invoked'": "'mode': 'original-init-not-yet-invoked-no-launch-in-stage'",
        "entry = ROOT / 'cleanup_owned_task_once.py'": "entry = ROOT / 'new_session_once.py'",
        "sys.argv = [str(entry), '--execute-cleanup-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['cleanup_owned_task_once.py']['bytes'])]":
            "sys.argv = [str(entry), '--init-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['new_session_once.py']['bytes'])]",
        "exec(compile(bodies['cleanup_owned_task_once.py'], str(entry), 'exec'),":
            "exec(compile(bodies['new_session_once.py'], str(entry), 'exec'),"
    }
    for old, new in replacements.items():
        assert stage.count(old) == 1, old
        stage = stage.replace(old, new)
    stage_bytes = stage.encode(); compile(stage_bytes, 'stage_init_once.py', 'exec')
    packet = encode({'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', stage, '--payload-sha256', sha(payload)],
        'stdin': payload.decode('ascii'), 'cwd': '/home/alex/work',
        'idempotency_key': 'pocket4-beike-owned-new-flow-init-r1-20261106-' + flow.rsplit('-', 1)[1],
        'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10, 'timeout_seconds': 300})
    patch = ''.join(difflib.unified_diff(before.decode().splitlines(True), stage.splitlines(True),
        fromfile='actual-successful-cleanup-stage-a9393e1e', tofile='new-session-init-stage-r1')).encode()
    for name, raw in [('stage_init_once.py', stage_bytes), ('stage-input.json', payload),
                      ('init-process-request.review-only.json', packet), ('stage-against-actual-cleanup.diff', patch)]:
        once(name, raw)
    names = sorted(path.name for path in HERE.iterdir() if path.is_file() and path.name != 'SOURCE_PINS.json')
    manifest = {'schema': 'pocket4-original-new-session-source-pins-v1', 'state': 'INIT_PREPARED_NOT_SUBMITTED',
        'files': {name: {'bytes': len((HERE / name).read_bytes()), 'sha256': sha((HERE / name).read_bytes())} for name in names},
        'new_flow': flow, 'new_source_root': root, 'init_only_in_packet': True,
        'launch_request_not_sealed': True, 'launch_requires_actual_init_joint_artifact_and_durable_zero_exit': True,
        'frozen_cleanup_utility': constants['BASE'], 'original_recorder_and_guards_modified': False,
        'historical_reconciliation_implemented': False, 'original_UNKNOWN_rewritten': False,
        'production_ready_apps': 0, 'old_product_deleted_bytes': 0, 'Main_or_remote_execution_by_sealer': False}
    manifest_raw = encode(manifest); once('SOURCE_PINS.json', manifest_raw)
    print(json.dumps({'source': pins['new_session_once.py'], 'stage': {'bytes': len(stage_bytes), 'sha256': sha(stage_bytes)},
        'payload': {'bytes': len(payload), 'sha256': sha(payload)}, 'request': {'bytes': len(packet), 'sha256': sha(packet)},
        'manifest': {'bytes': len(manifest_raw), 'sha256': sha(manifest_raw)}, 'Main_actions': 0, 'remote_requests': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
