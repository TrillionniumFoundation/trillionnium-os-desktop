#!/usr/bin/env python3
"""Seal one cleanup transport from local reviewed bytes; never execute it."""
import ast
import base64
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'owned_postcondition_reconciler_r1/foreground-diagnostic-candidate-r1/stage_current_foreground_once.py'


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + '\n').encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def once(name, raw):
    path = HERE / name
    with path.open('xb') as output:
        output.write(raw)
    assert path.read_bytes() == raw


def main():
    source = (HERE / 'cleanup_owned_task_once.py').read_bytes()
    compile(source, 'cleanup_owned_task_once.py', 'exec')
    constants = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    root = constants['ROOT']
    pins = {'cleanup_owned_task_once.py': {'bytes': len(source), 'sha256': sha(source)}}
    payload = encoded({'schema': 'pocket4-original-owned-cleanup-stage-payload-v1', 'root': root,
                       'files': {'cleanup_owned_task_once.py': {**pins['cleanup_owned_task_once.py'],
                           'base64': base64.b64encode(source).decode('ascii')}}})
    before = PRIOR.read_bytes()
    assert len(before) == 5789 and sha(before) == 'e9e295730d56aaadd3ec3b6b916f4a624b0cade8072c4550463facb27df4c842'
    stage = before.decode('utf-8')
    replacements = {
        '"""Stage a fixed current-foreground readonly diagnostic, then invoke it once."""':
            '"""Stage one fixed original-recorder cleanup wrapper, then invoke it once."""',
        "ROOT = Path('/home/alex/work/pocket4-beike-foreground-diagnostic-20261106-b1510395d16c9c3e1bf9992eee8a78da')":
            'ROOT = Path(' + repr(root) + ')',
        "PINS = {'observe_current_foreground_r1.py': {'bytes': 13787, 'sha256': '89aab3853d29a1400b45eb8495cc1b35aa8527088ccf0443975971191a98ce37'}, 'request.json': {'bytes': 827, 'sha256': 'a767827fb2f58ae2334699642bf22d470d4064b1663a3b2e76e60d54ac99810e'}}":
            'PINS = ' + repr(pins),
        "ENTRY_SHA = '89aab3853d29a1400b45eb8495cc1b35aa8527088ccf0443975971191a98ce37'":
            'ENTRY_SHA = ' + repr(sha(source)),
        "REQUEST_SHA = 'a767827fb2f58ae2334699642bf22d470d4064b1663a3b2e76e60d54ac99810e'\n": '',
        "PAYLOAD_SHA = 'd794e4f651c67168964f76e0830bb440153b1b6dcf168ff22c379e32e5e2a898'":
            'PAYLOAD_SHA = ' + repr(sha(payload)),
        "'pocket4-owned-postcondition-host-stage-payload-v1'": "'pocket4-original-owned-cleanup-stage-payload-v1'",
        "ROOT.name.startswith('pocket4-beike-foreground-diagnostic-20261106-')":
            "ROOT.name == 'pocket4-beike-owned-cleanup-20261106-r1'",
        "'pocket4-current-foreground-diagnostic-stage-v1'": "'pocket4-original-owned-cleanup-stage-v1'",
        "'mode': 'readonly-current-foreground'": "'mode': 'original-owned-task-cleanup-not-yet-invoked'",
        "entry = ROOT / 'observe_current_foreground_r1.py'": "entry = ROOT / 'cleanup_owned_task_once.py'",
        "sys.argv = [str(entry), '--observe-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['observe_current_foreground_r1.py']['bytes']), '--request-sha256', REQUEST_SHA, '--request-bytes', str(PINS['request.json']['bytes'])]":
            "sys.argv = [str(entry), '--execute-cleanup-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['cleanup_owned_task_once.py']['bytes'])]",
        "exec(compile(bodies['observe_current_foreground_r1.py'], str(entry), 'exec'),":
            "exec(compile(bodies['cleanup_owned_task_once.py'], str(entry), 'exec'),"
    }
    for old, new in replacements.items():
        assert stage.count(old) == 1, old
        stage = stage.replace(old, new)
    stage_raw = stage.encode('utf-8')
    compile(stage_raw, 'stage_cleanup_once.py', 'exec')
    packet = encoded({'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', stage, '--payload-sha256', sha(payload)],
        'stdin': payload.decode('ascii'), 'cwd': '/home/alex/work',
        'idempotency_key': 'pocket4-beike-owned-task876-cleanup-r1-20261106-86d1a0aa167743a1842dc30487245feb',
        'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10, 'timeout_seconds': 300})
    delta = ''.join(difflib.unified_diff(before.decode().splitlines(True), stage.splitlines(True),
        fromfile='actual-successful-foreground-stage-e9e29573', tofile='new-original-cleanup-stage-r1')).encode()
    once('stage_cleanup_once.py', stage_raw)
    once('stage-input.json', payload)
    once('process-request.review-only.json', packet)
    once('stage-against-actual-foreground.diff', delta)
    names = ('cleanup_owned_task_once.py', 'check_owned_exit.py', 'prepare_packet.py', 'stage_cleanup_once.py',
             'stage-input.json', 'process-request.review-only.json', 'stage-against-actual-foreground.diff',
             'local-controls.stdout.original.jsonl', 'local-controls.stderr.original.txt')
    manifest = {'schema': 'pocket4-original-owned-cleanup-source-pins-v1', 'state': 'PREPARED_NOT_SUBMITTED',
        'files': {name: {'bytes': len((HERE / name).read_bytes()), 'sha256': sha((HERE / name).read_bytes())} for name in names},
        'original_source_pins': {key: constants[key] for key in ('RECORDER', 'CORE', 'SUPPORT', 'BUNDLE')},
        'only_Android_action': ['/system/bin/cmd', 'activity', 'stack', 'remove', '876'],
        'operation': 'cleanup', 'original_flow': constants['FLOW'], 'new_step': constants['STEP'],
        'original_recorder_or_helper_modified': False, 'old_unknown_rewritten': False,
        'new_launch_in_packet': False, 'historical_producer_implemented': False,
        'production_ready': False, 'old_build_or_App_data_deleted': False}
    once('SOURCE_PINS.json', encoded(manifest))
    print(json.dumps({'source': pins['cleanup_owned_task_once.py'],
        'stage': {'bytes': len(stage_raw), 'sha256': sha(stage_raw)},
        'payload': {'bytes': len(payload), 'sha256': sha(payload)},
        'request': {'bytes': len(packet), 'sha256': sha(packet)},
        'manifest': {'bytes': len(encoded(manifest)), 'sha256': sha(encoded(manifest))},
        'Main_actions': 0, 'remote_requests': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
