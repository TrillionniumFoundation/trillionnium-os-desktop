"""Local-only fixed report reader generator, requiring observed size and SHA."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

BASE = Path('/workspace/scratch/94990735b266/lmkd-recovery-20261105-01')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bytes', type=int, required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    assert 0 < args.bytes <= 1048576 and re.fullmatch('[0-9a-f]{64}', args.sha256)
    old = (BASE / 'init-project-build02-read-freeze-01/read_build02.py').read_bytes()
    assert hashlib.sha256(old).hexdigest() == 'c5c6fa396fa546d021d632eb3c300a2d2256f77b2c473f6d2ed939167e4d1039'
    source = old.decode()
    edits = [
        ('Fixed three-file root read', 'Fixed single-report root read'),
        ("ROOT_NAME = 'p4-init-project-diagnostic-20261105-build-02'", "ROOT_NAME = 'p4-init-project-diagnostic-20261105-build-03'"),
        ('EXPECTED_REPORT_BYTES = 122942', 'EXPECTED_REPORT_BYTES = ' + str(args.bytes)),
        ("EXPECTED_REPORT_SHA256 = 'f6d4cc449bd8f2a2dfb61d55cc67688941aa582a5d88759e712fcf67253413af'", "EXPECTED_REPORT_SHA256 = '" + args.sha256 + "'"),
        ("NAMES = ('build-result.json', 'preflight.d', 'barrier.d')", "NAMES = ('build-result.json',)"),
        ('LIMIT = 262144', 'LIMIT = 1048576'),
        ("'kind': 'fixed-init-diagnostic-build02-read'", "'kind': 'fixed-init-diagnostic-build03-read'"),
        ('<= 3 * LIMIT', '<= LIMIT'),
        ('len(raw) <= 1048576', 'len(raw) <= 2097152'),
        ('len(compressed) <= 524288', 'len(compressed) <= 1048576'),
    ]
    for before, after in edits:
        assert source.count(before) == 1
        source = source.replace(before, after)
    ast.parse(source)
    compile(source, 'read_build03.py', 'exec')
    data = source.encode()
    digest = hashlib.sha256(data).hexdigest()
    request = {'host': 'pocket4', 'executable': '/usr/bin/sudo', 'args': ['-n', '/usr/bin/python3', '-I', '-B', '-'],
        'cwd': '/', 'stdin': source, 'idempotency_key': 'p4-init-project-build03-read01-' + digest[:16],
        'cpu_quota_percent': 100, 'memory_max_bytes': 134217728, 'nice': 10, 'timeout_seconds': 30}
    raw = (json.dumps(request, sort_keys=True, indent=2) + '\n').encode()
    output = BASE / 'init-project-build03-read-freeze-01'
    output.mkdir(exist_ok=False)
    members = {'read_build03.py': data, 'request.json': raw, 'make_read03.py': Path(__file__).read_bytes()}
    rows = []
    for name, value in members.items():
        (output / name).write_bytes(value)
        rows.append({'path': name, 'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()})
    manifest = (json.dumps({'schema': 1, 'actual_execution': False, 'files': rows}, sort_keys=True, indent=2) + '\n').encode()
    (output / 'manifest.json').write_bytes(manifest)
    print(json.dumps({'freeze': str(output), 'source_bytes': len(data), 'source_sha256': digest,
        'request_bytes': len(raw), 'request_sha256': hashlib.sha256(raw).hexdigest(),
        'key': request['idempotency_key'], 'manifest_sha256': hashlib.sha256(manifest).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
