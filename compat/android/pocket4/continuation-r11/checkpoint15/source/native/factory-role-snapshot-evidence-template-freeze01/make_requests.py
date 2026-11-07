#!/usr/bin/env python3
"""Bind fixed read-only evidence requests; never dispatch or run the fixture."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = '/run/pocket4-role-authorized-snapshot-host-run-01-20261105/run01'
RESULT_TEMPLATE_SHA = '12e4767d6bd536e78fd156ad4cf477112852f865f94e632faa9732df9f6d7929'
LOG_BODY_SHA = '9ca2625627b71927bf6d11ce679d27c6f9fd69d97a6832bf0499a82d2539182e'


def need(value, message):
    if not value:
        raise RuntimeError(message)


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def request(source, key):
    ast.parse(source)
    return {'host': 'pocket4', 'executable': '/usr/bin/sudo',
            'args': ['-n', '/usr/bin/python3', '-I', '-', '--collect'],
            'cwd': '/', 'cpu_quota_percent': 25, 'memory_max_bytes': 128 * 1024 * 1024,
            'nice': 15, 'timeout_seconds': 30, 'stdin': source, 'idempotency_key': key}


def result_source(size, digest):
    need(isinstance(size, int) and not isinstance(size, bool) and 0 < size <= 131072,
         'actual terminal result size exceeds the fixed bound')
    need(re.fullmatch('[0-9a-f]{64}', digest) is not None, 'actual terminal SHA256 required')
    raw = (HERE / 'read_result.template.py').read_bytes()
    need(pin(raw)['sha256'] == RESULT_TEMPLATE_SHA, 'reviewed result reader template changed')
    source = raw.decode()
    need(source.count('"PENDING_ACTUAL_RUNTIME_RESULT_BYTES"') == 1 and
         source.count('PENDING_ACTUAL_RUNTIME_RESULT_SHA256') == 1,
         'single actual result binding required')
    return source.replace('"PENDING_ACTUAL_RUNTIME_RESULT_BYTES"', str(size)).replace(
        'PENDING_ACTUAL_RUNTIME_RESULT_SHA256', digest)


def logs_source(path):
    raw = path.read_bytes()
    need(0 < len(raw) <= 131072, 'actual runtime receipt exceeds fixed authority bound')
    value = json.loads(raw)
    execution = value['execution']
    body = (HERE / 'read_logs.body.py').read_bytes()
    need(pin(body)['sha256'] == LOG_BODY_SHA, 'reviewed two-log reader changed')
    rows = {}
    for label, limit in [('stdout', 131072), ('stderr', 32768)]:
        expected = execution[label]
        need(set(expected) == {'path', 'bytes', 'sha256', 'identity'},
             'actual log metadata shape differs')
        need(expected['path'] == ROOT + '/snapshot.' + label,
             'actual log path is outside the two fixed owned original files')
        need(isinstance(expected['bytes'], int) and not isinstance(expected['bytes'], bool) and
             0 <= expected['bytes'] <= limit and
             re.fullmatch('[0-9a-f]{64}', expected['sha256']) is not None,
             'actual original log size or SHA differs')
        identity = expected['identity']
        need(isinstance(identity, list) and len(identity) == 6 and
             all(isinstance(x, int) and not isinstance(x, bool) for x in identity) and
             identity[3] == expected['bytes'], 'actual original log identity differs')
        rows[label] = {'path': expected['path'], 'maximum': limit, 'expected': expected}
    bindings = {'schema': 1,
                'authority': {'path': ROOT + '/result.json', 'maximum': 131072, **pin(raw)},
                'rows': rows}
    source = ('#!/usr/bin/env python3\n'
              '"""Read exact original snapshot logs; no fixture replay or writes."""\n'
              'import base64,gzip,hashlib,json,os,stat,sys\n'
              'BINDINGS = ' + repr(bindings) + '\n\n' + body.decode())
    return source, bindings, raw


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='mode', required=True)
    first = sub.add_parser('result')
    first.add_argument('--actual-result-bytes', required=True, type=int)
    first.add_argument('--actual-result-sha256', required=True)
    first.add_argument('--output', required=True, type=Path)
    second = sub.add_parser('logs')
    second.add_argument('--actual-runtime-result', required=True, type=Path)
    second.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    files = {}
    if args.mode == 'result':
        source = result_source(args.actual_result_bytes, args.actual_result_sha256)
        key = 'pocket4-role-authorized-snapshot-runtime-result-readonly-01-20261105'
        files['read_result.py'] = source.encode()
        bindings = {'path': ROOT + '/result.json', 'maximum': 131072,
                    'bytes': args.actual_result_bytes, 'sha256': args.actual_result_sha256,
                    'source': 'actual runtime terminal pin supplied by root',
                    'runtime_pass_asserted': False}
    else:
        source, bindings, raw = logs_source(args.actual_runtime_result)
        key = 'pocket4-role-authorized-snapshot-runtime-original-logs-readonly-01-20261105'
        files['read_logs.py'] = source.encode()
        files['actual-runtime-result.json'] = raw
    files['BINDINGS.json'] = (json.dumps(bindings, indent=2, sort_keys=True) + '\n').encode()
    files['exact-request.json'] = (json.dumps(request(source, key), indent=2, sort_keys=True) + '\n').encode()
    args.output.mkdir()
    for name, raw in files.items():
        with (args.output / name).open('xb') as stream:
            stream.write(raw)
    pins = {name: pin(raw) for name, raw in files.items()}
    with (args.output / 'SOURCE_PINS.json').open('x') as stream:
        json.dump({'schema': 1, 'files': pins, 'remote_dispatch': False,
                   'new_test_execution': False, 'Main_actions': 0}, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'request': pins['exact-request.json'],
                      'dispatched': False}, sort_keys=True))


if __name__ == '__main__':
    main()
