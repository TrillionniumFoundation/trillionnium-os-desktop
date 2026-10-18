"""Read existing generated evidence; write only disposable review destinations."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('candidate', root / 'archive.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
base = Path('/workspace/scratch/ae1a8cf05419/trillionnium-os-desktop/support/build/out')
rows = []
for name in ('osdk-integration-native-07', 'osdk-capture-v2-02'):
    source = base / name
    destination = root / 'compatibility-final' / name
    count = module.archive(source, destination)
    manifest = json.loads((destination / 'archive.json').read_text())
    selected = manifest['files']
    if count != len(selected):
        raise RuntimeError('record count mismatch')
    for record in selected:
        original = source / record['source']
        data = original.read_bytes()
        payload = destination / record['archived']
        copied = payload.read_bytes()
        if record['archived'].endswith('.gz'):
            copied = gzip.decompress(copied)
        if (copied != data or len(data) != record['source_size']
                or hashlib.sha256(data).hexdigest() != record['source_sha256']):
            raise RuntimeError(f'evidence byte/hash mismatch: {original}')
    for line in (destination / 'evidence.sha256').read_text().splitlines():
        expected, path = line.split('  ', 1)
        if hashlib.sha256((destination / path).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'archive checksum mismatch: {path}')
    rows.append({'run': name, 'source': str(source), 'destination': str(destination),
                 'records': count, 'total_source_bytes': sum(r['source_size'] for r in selected),
                 'max_source_bytes': max(r['source_size'] for r in selected),
                 'largest_10': sorted(selected, key=lambda r:r['source_size'], reverse=True)[:10],
                 'all_source_payloads_and_manifest_checksums_verified': True,
                 'max_file_bytes': module.MAX_FILE_BYTES, 'max_total_bytes': module.MAX_TOTAL_BYTES})
(root / 'compatibility.json').write_text(json.dumps(rows, indent=2) + '\n')
print(json.dumps(rows, indent=2))
