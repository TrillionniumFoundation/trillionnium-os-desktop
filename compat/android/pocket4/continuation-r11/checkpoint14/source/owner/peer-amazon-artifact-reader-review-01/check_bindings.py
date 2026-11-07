#!/usr/bin/env python3
"""Read-only local frozen-input verification; does not execute the collector."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path('/workspace/scratch/94990735b266')
SOURCE = ROOT / 'android-amazon-artifact-readonly-freeze-01'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def record(path):
    raw = path.read_bytes()
    raw.decode('utf-8')
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def main():
    pins_raw = (SOURCE / 'SOURCE_PINS.json').read_bytes()
    pins = json.loads(pins_raw)
    files = []
    for row in pins['files']:
        path = SOURCE / row['path']
        actual = record(path)
        assert actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256']
        raw = path.read_bytes()
        assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == row['git_sha']
        files.append(actual)
    files.append(record(SOURCE / 'SOURCE_PINS.json'))
    dependencies = json.loads((SOURCE / 'DEPENDENCIES.json').read_bytes())
    dependency_checks = []
    for row in dependencies['records']:
        actual = record(Path(row['local_reference_path']))
        assert actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256']
        dependency_checks.append(actual)
    source = (SOURCE / 'read_amazon.py').read_text()
    stage = (SOURCE / 'stage_execute.py').read_text()
    assert digest(source.encode()) == '22a6552111154156004aff344d6929db436d5c3fe084893abea931f1399b0588'
    assert digest(stage.encode()) == 'd1b4aef3a1a06db71424bde5467eea6b52d7954aa19ceab57b66df292c1bbb1d'
    source_tree = ast.parse(source)
    ast.parse(stage)
    request_raw = (SOURCE / 'exact-request.json').read_bytes()
    assert len(request_raw) == 25348 and digest(request_raw) == pins['exact_request_sha256']
    request = json.loads(request_raw)
    packet = (json.dumps({'schema': 1, 'nonce': pins['nonce'], 'source': source},
        ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert request['stdin'].encode() == packet and digest(packet) == pins['stdin_sha256']
    expected_wrapper = ('import hashlib,json,sys;raw=sys.stdin.buffer.read(32769);assert len(raw)==' + str(len(packet)) +
        ' and hashlib.sha256(raw).hexdigest()==' + repr(digest(packet)) +
        ';stage=' + repr(stage) +
        ';assert hashlib.sha256(stage.encode()).hexdigest()==' + repr(digest(stage.encode())) +
        ';scope={"__name__":"amazon_fixed_metadata_stage","__file__":"<verified-amazon-stage>"};' +
        'exec(compile(stage,"stage_execute.py","exec"),scope);' +
        'raise SystemExit(scope["main"](json.loads(raw),' + repr(digest(source.encode())) + '))')
    assert request['args'] == ['-n', '/usr/bin/python3', '-I', '-c', expected_wrapper]
    ast.parse(expected_wrapper)
    assert request == {
        'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-c', expected_wrapper],
        'cwd': '/home/alex/work', 'env': {'PYTHONDONTWRITEBYTECODE': '1'},
        'stdin': packet.decode(), 'idempotency_key': 'pocket4-amazon-installed-artifact-readonly-01-20261105',
        'timeout_seconds': 240, 'cpu_quota_percent': 100, 'memory_max_bytes': 536870912, 'nice': 10,
    }
    context = next(x for x in source_tree.body if isinstance(x, ast.ClassDef) and x.name == 'Context')
    commands = [x for x in ast.walk(context) if isinstance(x, ast.Call)
        and isinstance(x.func, ast.Attribute) and x.func.attr == 'command']
    assert len(commands) == 1 and ast.unparse(commands[0].func) == 'self.recorder.Flow.command'
    assert ast.unparse(commands[0].args[0]) == 'self' and ast.literal_eval(commands[0].args[2]) == 15
    keywords = {x.arg: ast.unparse(x.value) for x in commands[0].keywords}
    assert keywords['mutation'] == 'False' and keywords['check'] == 'False'
    assert keywords['label'] == "'Android command'" and keywords['pass_fds'] == 'tuple(descriptors)'
    observations = json.loads((SOURCE / 'local-control-result-summary.json').read_bytes())
    assert observations['passed'] == 8 and observations['exit_code'] == 0
    assert observations['production_source_sha256'] == digest(source.encode())
    assert observations['remote_execution'] is False and observations['real_metadata_or_APK_read'] is False
    return {'scope': 'local pins, AST and exact bounded request binding only',
        'passed': True, 'frozen_files': files, 'dependencies': dependency_checks,
        'source_request_wrapper_byte_exact': True, 'actual_Flow_command_method_call_bound': True,
        'collector_executed': False, 'controls_reexecuted': False, 'Hepta_called': False,
        'actual_Amazon_metadata_or_APK_checked': False, 'whole_app_qualified': False}


if __name__ == '__main__':
    print(json.dumps(main(), sort_keys=True, indent=2))
