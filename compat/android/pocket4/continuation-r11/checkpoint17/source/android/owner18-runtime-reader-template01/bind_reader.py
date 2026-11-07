#!/usr/bin/env python3
"""Fill only actual terminal size/hash in this one fixed Owner18 result reader."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'android-owner18-normal01-runtime-reader-01'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bytes', type=int, required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    assert 0 < args.bytes <= 5 * 1024 * 1024
    assert re.fullmatch('[0-9a-f]{64}', args.sha256)
    pins = json.loads((HERE / 'SOURCE_PINS.json').read_bytes())
    for name, row in pins['files'].items():
        body = (HERE / name).read_bytes()
        assert len(body) == row['bytes'] and sha(body) == row['sha256'], name
    template = (HERE / 'read-template.py').read_text()
    assert template.count('EXPECTED_REPORT_BYTES = None') == template.count('EXPECTED_REPORT_SHA256 = None') == 1
    source = template.replace('EXPECTED_REPORT_BYTES = None', 'EXPECTED_REPORT_BYTES = ' + str(args.bytes))
    source = source.replace('EXPECTED_REPORT_SHA256 = None', 'EXPECTED_REPORT_SHA256 = ' + repr(args.sha256))
    assert source.replace('EXPECTED_REPORT_BYTES = ' + str(args.bytes), 'EXPECTED_REPORT_BYTES = None').replace(
        'EXPECTED_REPORT_SHA256 = ' + repr(args.sha256), 'EXPECTED_REPORT_SHA256 = None') == template
    ast.parse(source); compile(source, '<fixed Owner18 runtime result reader>', 'exec')
    request = json.loads((HERE / 'request-template.json').read_bytes())
    assert request['stdin'] == template
    request.update(stdin=source, idempotency_key='p4-owner18-normal01-runtime-read01-' + sha(source.encode())[:16])
    members = {'read.py': source.encode(), 'request.json': pretty(request), 'binding.json': pretty({
        'schema': 1, 'expected_report_path': '/opt/p4-owner18-normal-20261105-01-state/runtime-result.json',
        'expected_report_bytes': args.bytes, 'expected_report_sha256': args.sha256,
        'template_manifest_sha256': sha((HERE / 'SOURCE_PINS.json').read_bytes()),
        'original_resources_and_protected_metadata_FD_gates_unchanged': True,
        'only_actual_size_hash_and_stable_key_filled': True, 'executed': False, 'qualification': False})}
    OUT.mkdir(exist_ok=False)
    for name, body in members.items():
        with (OUT / name).open('xb') as stream:
            stream.write(body)
    manifest = {'schema': 1, 'files': {n: {'bytes': len(b), 'sha256': sha(b)} for n, b in members.items()}}
    (OUT / 'SOURCE_PINS.json').write_bytes(pretty(manifest))
    print(json.dumps({'root': str(OUT), 'request_bytes': len(members['request.json']),
        'request_sha256': sha(members['request.json']), 'stdin_bytes': len(source.encode()),
        'stdin_sha256': sha(source.encode()), 'key': request['idempotency_key'], 'qualification': False}))


if __name__ == '__main__':
    main()
