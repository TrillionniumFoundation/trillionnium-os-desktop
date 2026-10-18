#!/usr/bin/env python3
"""Count actual function-entry records from the retained final LLVM report."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def analyze(phase):
    manifest_path = phase / 'raw/manifest.json'
    data = manifest_path.read_bytes()
    manifest = json.loads(data)
    payload = []
    for part in manifest['ordered_parts']:
        name = part['path']
        require(Path(name).name == name and name not in ('.', '..'), 'unsafe part name')
        blob = (phase / 'raw' / name).read_bytes()
        require(len(blob) == part['bytes'] and sha(blob) == part['sha256'], 'part identity mismatch')
        payload.append(blob)
    compressed = b''.join(payload)
    require(len(compressed) == manifest['gzip_bytes'] and sha(compressed) == manifest['gzip_sha256'], 'archive identity mismatch')
    member = 'final-matrix/case-15/coverage/llvm-profdata-1.log'
    with tarfile.open(fileobj=io.BytesIO(compressed), mode='r:gz') as archive:
        found = [entry for entry in archive.getmembers() if entry.name == member]
        require(len(found) == 1 and found[0].isreg(), 'missing/ambiguous/nonregular LLVM report')
        stream = archive.extractfile(found[0])
        require(stream is not None, 'missing report stream')
        text_bytes = stream.read()
    expected = manifest['members'][member]
    require(len(text_bytes) == expected['bytes'] and sha(text_bytes) == expected['sha256'], 'member identity mismatch')
    text = text_bytes.decode('utf-8')
    counts = [int(value) for value in re.findall(r'^\s+Function count:\s*(\d+)\s*$', text, re.M)]
    total = re.search(r'^Total functions:\s*(\d+)\s*$', text, re.M)
    require(total is not None and len(counts) == int(total.group(1)), 'function denominator mismatch')
    require(counts and all(value > 0 for value in counts), 'not every recorded function has a positive entry count')
    return {'passed': True, 'scope': 'offline analysis of exact retained LLVM report; no new guest or coverage run',
        'manifest_sha256': sha(data), 'archive_sha256': sha(compressed), 'member': member,
        'member_bytes': len(text_bytes), 'member_sha256': sha(text_bytes),
        'function_records': len(counts), 'positive_function_entry_counts': sum(value > 0 for value in counts),
        'zero_function_entry_counts': sum(value == 0 for value in counts), 'maximum_function_entry_count': max(counts)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-phase', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.native_phase)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
