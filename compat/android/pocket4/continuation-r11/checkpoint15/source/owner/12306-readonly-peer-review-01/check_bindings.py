"""Local source/AST/request checks only; never import or execute the reader."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

ROOT = Path('/workspace/scratch/94990735b266')
NEW = ROOT / 'android-12306-artifact-launcher-readonly-01'
OLD = ROOT / 'android-amazon-artifact-readonly-freeze-01'
OUT = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    manifest_raw = (NEW / 'SOURCE_PINS.json').read_bytes()
    manifest = json.loads(manifest_raw)
    checked = []
    for name, row in manifest['files'].items():
        raw = (NEW / name).read_bytes()
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
        raw.decode('utf-8')
        checked.append({'path': name, **row})
    assert len(checked) == 15 and manifest['actual_device_run'] is False
    assert manifest['package'] == 'com.MobileTicket'
    deltas = []
    for old, new, patch, before_label, after_label in [
        ('read_amazon.py', 'read_12306.py', 'amazon-artifact-to-12306.patch', 'amazon-artifact/read_amazon.py', '12306-artifact-launcher/read_12306.py'),
        ('stage_execute.py', 'stage_execute.py', 'stage-to-12306.patch', 'amazon-artifact/stage_execute.py', '12306-artifact-launcher/stage_execute.py'),
        ('make_request.py', 'make_request.py', 'generator-to-12306.patch', 'amazon-artifact/make_request.py', '12306-artifact-launcher/make_request.py'),
    ]:
        a, b = (OLD / old).read_bytes(), (NEW / new).read_bytes()
        expected = ''.join(difflib.unified_diff(a.decode().splitlines(True), b.decode().splitlines(True),
            fromfile=before_label, tofile=after_label)).encode()
        assert expected == (NEW / patch).read_bytes()
        ast.parse(b)
        deltas.append({'patch': patch, 'preimage_sha256': sha(a), 'candidate_sha256': sha(b), 'patch_sha256': sha(expected)})
    old_tree, new_tree = ast.parse((OLD / 'read_amazon.py').read_bytes()), ast.parse((NEW / 'read_12306.py').read_bytes())
    old_functions = {n.name: ast.dump(n) for n in old_tree.body if isinstance(n, ast.FunctionDef)}
    new_functions = {n.name: ast.dump(n) for n in new_tree.body if isinstance(n, ast.FunctionDef)}
    same = ['need', 'sha', 'read', 'load', 'error_row', 'remember', 'identity']
    for name in same:
        assert old_functions[name] == new_functions[name]
    old_context = next(n for n in old_tree.body if isinstance(n, ast.ClassDef) and n.name == 'Context')
    new_context = next(n for n in new_tree.body if isinstance(n, ast.ClassDef) and n.name == 'Context')
    for name in ['__init__', 'guard']:
        assert ast.dump(next(n for n in old_context.body if isinstance(n, ast.FunctionDef) and n.name == name)) == ast.dump(next(n for n in new_context.body if isinstance(n, ast.FunctionDef) and n.name == name))
    request_raw = (NEW / 'exact-request.json').read_bytes()
    request = json.loads(request_raw)
    reader = (NEW / 'read_12306.py').read_bytes()
    stage = (NEW / 'stage_execute.py').read_bytes()
    packet = (json.dumps({'schema': 1, 'nonce': manifest['nonce'], 'source': reader.decode()},
        ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert request['stdin'].encode() == packet and len(packet) <= 32768
    wrapper = ('import hashlib,json,sys;raw=sys.stdin.buffer.read(32769);assert len(raw)==' + str(len(packet)) +
        ' and hashlib.sha256(raw).hexdigest()==' + repr(sha(packet)) +
        ';stage=' + repr(stage.decode()) +
        ';assert hashlib.sha256(stage.encode()).hexdigest()==' + repr(sha(stage)) +
        ';scope={"__name__":"ticket12306_fixed_metadata_stage","__file__":"<verified-ticket12306-stage>"};' +
        'exec(compile(stage,"stage_execute.py","exec"),scope);' +
        'raise SystemExit(scope["main"](json.loads(raw),' + repr(sha(reader)) + '))')
    assert request['args'] == ['-n', '/usr/bin/python3', '-I', '-c', wrapper]
    assert request['host'] == 'pocket4' and request['executable'] == '/usr/bin/sudo'
    assert request['timeout_seconds'] == 240 and request['cpu_quota_percent'] == 100
    assert request['memory_max_bytes'] == 536870912 and request['nice'] == 10
    assert request['idempotency_key'] == 'pocket4-12306-artifact-launcher-readonly-01-20261105'
    ast.parse(wrapper)
    result = {'schema': 1, 'scope': 'Local hashes, exact diffs and request AST only; no reader/control/device execution',
        'SOURCE_PINS_sha256': sha(manifest_raw), 'manifest_member_count': len(checked),
        'checked_files': checked, 'deltas_reconstructed': deltas,
        'unchanged_function_AST': same + ['Context.__init__', 'Context.guard'],
        'request_sha256': sha(request_raw), 'request_bytes': len(request_raw),
        'stdin_sha256': sha(packet), 'stdin_bytes': len(packet),
        'wrapper_reconstructed_exactly': True, 'runtime_executed': False,
        'synthetic_or_device_controls_executed': False, 'qualification': False}
    raw = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    with (OUT / 'checks.json').open('xb') as file:
        file.write(raw)
    print(json.dumps({'bytes': len(raw), 'sha256': sha(raw), 'manifest_sha256': sha(manifest_raw)}))


if __name__ == '__main__':
    main()
