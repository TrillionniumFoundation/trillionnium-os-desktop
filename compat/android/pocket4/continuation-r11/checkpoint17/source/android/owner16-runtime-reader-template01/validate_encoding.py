#!/usr/bin/env python3
"""One pure encoding-bound check; never calls the collector or opens /opt."""
import ast
import base64
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    source = (HERE / 'read-template.py').read_bytes()
    tree = ast.parse(source)
    module = {}
    exec(compile(source, '<fixed unbound reader definitions>', 'exec'), {'__name__': 'reader_definitions'}, module)
    limit = module['LIMIT']
    # A valid ASCII JSON string with near-maximum escaping overhead. This is a
    # codec fixture, not an actual runtime receipt or permission to collect one.
    body = b'"' + b'\\"' * ((limit - 3) // 2) + b'"\n'
    assert body.isascii() and len(body) <= limit
    json.loads(body)
    value = {'schema': 1, 'kind': 'fixed-owner16-normal01-runtime-read', 'collection_complete': True,
             'files': {'runtime-result.json': {'path': '/opt/p4-owner16-normal-20261105-01-state/runtime-result.json',
                       **pin(body), 'identity': [30, 1, len(body), 1, 1, 33152, 0, 0, 1], 'content': body.decode()}},
             'errors': [], 'mutations': False, 'qualification': False}
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    assert len(raw) <= module['ENVELOPE_LIMIT']
    compressed = gzip.compress(raw, mtime=0)
    assert len(compressed) <= module['GZIP_LIMIT']
    restored = gzip.decompress(base64.b64decode(base64.b64encode(compressed), validate=True))
    assert restored == raw
    decoded = json.loads(restored)['files']['runtime-result.json']['content'].encode()
    assert decoded == body and pin(decoded) == pin(body)
    assert module['EXPECTED_REPORT_BYTES'] is None and module['EXPECTED_REPORT_SHA256'] is None
    original = json.loads((HERE.parent / 'android-owner15-normal01-runtime-reader-01/request.json').read_bytes())
    request = json.loads((HERE / 'request-template.json').read_bytes())
    assert {k: v for k, v in original.items() if k not in ('stdin', 'idempotency_key')} == {
        k: v for k, v in request.items() if k not in ('stdin', 'idempotency_key')}
    assert request['stdin'].encode() == source
    # No remote read, process, namespace, lifecycle, device or UI action occurs.
    report = {'schema': 1, 'scope': 'pure JSON/gzip/base64 maximum escaping fixture; no collector call',
        'passed': True, 'source': pin(source), 'fixture_body': pin(body), 'envelope': pin(raw),
        'gzip': pin(compressed), 'full_bytes_restored': True, 'file_limit': limit,
        'envelope_limit': module['ENVELOPE_LIMIT'], 'gzip_limit': module['GZIP_LIMIT'],
        'original_128MiB_1CPU_30s_resources_unchanged': True,
        'actual_runtime_size_or_hash_filled': False, 'collector_executed': False, 'runtime_qualified': False}
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
