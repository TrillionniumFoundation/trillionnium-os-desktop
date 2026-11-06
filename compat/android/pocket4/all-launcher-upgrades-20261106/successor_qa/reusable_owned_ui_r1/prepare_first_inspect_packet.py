#!/usr/bin/env python3
"""Seal the first readonly request and reusable source; never submit remotely."""
import ast
import base64
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'owned_new_session_r1/stage_init_once.py'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode('ascii')


def once(name, raw):
    with (HERE / name).open('xb') as stream:
        stream.write(raw)
    assert (HERE / name).read_bytes() == raw


def main():
    source = (HERE / 'owned_ui_request_once.py').read_bytes(); compile(source, 'owned_ui_request_once.py', 'exec')
    constants = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    root = constants['ROOT']
    request = (HERE / 'inspect-new-session-01.request.json').read_bytes(); request_sha = sha(request)
    parsed = json.loads(request); plan = json.loads(parsed['payload_text'])
    assert parsed['kind'] == 'plan' and parsed['step'] == 'inspect-new-session-01' and plan['operation'] == 'inspect'
    assert set(plan) == {'schema', 'operation', 'nonces'} and parsed['payload_sha256'] == sha(parsed['payload_text'].encode())
    request_name = 'request-' + request_sha + '.json'
    inputs = {'owned_ui_request_once.py': source, request_name: request,
              'launch.stdout.original.jsonl': (HERE / 'launch.stdout.original.jsonl').read_bytes(),
              'launch.terminal.original.json': (HERE / 'launch.terminal.original.json').read_bytes()}
    pins = {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in inputs.items()}
    payload = encode({'schema': 'pocket4-fixed-owned-ui-stage-payload-v1', 'root': root,
        'files': {name: {**pins[name], 'base64': base64.b64encode(raw).decode('ascii')} for name, raw in inputs.items()}})
    before = PRIOR.read_bytes(); assert len(before) == 5678 and sha(before) == '1175c96b2340d0234613dd1e89a10c5ead281f322850272e03f2b910d877fe01'
    stage = before.decode()
    prior_tree = ast.parse(stage)
    def assignment(name):
        node = next(n for n in prior_tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and
                    isinstance(n.targets[0], ast.Name) and n.targets[0].id == name)
        return ast.get_source_segment(stage, node)
    replacements = {
        '"""Stage exact new-session sources and actual cleanup receipts; invoke only init."""':
            '"""Stage fixed reusable owned QA source and one readonly inspection request."""',
        assignment('ROOT'): 'ROOT = Path(' + repr(root) + ')', assignment('PINS'): 'PINS = ' + repr(pins),
        assignment('ENTRY_SHA'): 'ENTRY_SHA = ' + repr(sha(source)), assignment('PAYLOAD_SHA'): 'PAYLOAD_SHA = ' + repr(sha(payload)),
        "'pocket4-original-new-session-stage-payload-v1'": "'pocket4-fixed-owned-ui-stage-payload-v1'",
        "ROOT.name == 'pocket4-beike-owned-new-session-20261106-r1'": "ROOT.name == 'pocket4-beike-owned-ui-reusable-20261106-r1'",
        "'pocket4-original-new-session-stage-v1'": "'pocket4-fixed-owned-ui-stage-v1'",
        "'mode': 'original-init-not-yet-invoked-no-launch-in-stage'": "'mode': 'readonly-inspect-not-yet-invoked'",
        "entry = ROOT / 'new_session_once.py'": "entry = ROOT / 'owned_ui_request_once.py'",
        "sys.argv = [str(entry), '--init-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['new_session_once.py']['bytes'])]":
            "sys.argv = [str(entry), '--execute-request', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['owned_ui_request_once.py']['bytes']), '--request-sha256', " + repr(request_sha) + ", '--request-bytes', " + repr(str(len(request))) + "]",
        "exec(compile(bodies['new_session_once.py'], str(entry), 'exec'),":
            "exec(compile(bodies['owned_ui_request_once.py'], str(entry), 'exec'),"
    }
    for old, new in replacements.items():
        assert stage.count(old) == 1, old
        stage = stage.replace(old, new)
    stage_raw = stage.encode(); compile(stage_raw, 'stage_first_inspect_once.py', 'exec')
    packet = encode({'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-c', stage, '--payload-sha256', sha(payload)],
        'stdin': payload.decode('ascii'), 'cwd': '/home/alex/work',
        'idempotency_key': 'pocket4-beike-owned-ui-r1-20261106-' + request_sha,
        'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10, 'timeout_seconds': 480})
    patch = ''.join(difflib.unified_diff(before.decode().splitlines(True), stage.splitlines(True),
        fromfile='actual-successful-new-init-stage-1175c96b', tofile='first-readonly-owned-ui-stage')).encode()
    for name, raw in [('stage_first_inspect_once.py', stage_raw), ('stage-input.json', payload),
                      ('inspect-process-request.review-only.json', packet), ('stage-against-actual-init.diff', patch)]:
        once(name, raw)
    names = sorted(path.name for path in HERE.iterdir() if path.is_file() and path.name != 'SOURCE_PINS.json')
    manifest = {'schema': 'pocket4-reusable-fixed-owned-ui-source-pins-v1', 'state': 'FIRST_INSPECT_PREPARED_NOT_SUBMITTED',
        'files': {name: {'bytes': len((HERE / name).read_bytes()), 'sha256': sha((HERE / name).read_bytes())} for name in names},
        'remote_staged_files': pins, 'source_root': root, 'flow': constants['FLOW'], 'task': constants['TASK'],
        'initial_request': {'bytes': len(request), 'sha256': request_sha, 'step': parsed['step'], 'operation': 'inspect'},
        'original_sources': {key: constants[key] for key in ('BASE', 'SESSION', 'ADAPTER', 'CASE')},
        'original_guards_Flow_and_qa_implementations_modified': False,
        'every_subsequent_request_requires_separate_exact_review': True,
        'reconciliation_or_foreground_bypass_provided': False, 'original_UNKNOWN_rewritten': False,
        'production_ready_apps': 0, 'Main_or_remote_execution_by_sealer': False}
    m = encode(manifest); once('SOURCE_PINS.json', m)
    print(json.dumps({'source': pins['owned_ui_request_once.py'], 'stage': {'bytes': len(stage_raw), 'sha256': sha(stage_raw)},
        'payload': {'bytes': len(payload), 'sha256': sha(payload)}, 'process_request': {'bytes': len(packet), 'sha256': sha(packet)},
        'manifest': {'bytes': len(m), 'sha256': sha(m)}, 'operation': 'inspect', 'Main_or_remote_calls': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
