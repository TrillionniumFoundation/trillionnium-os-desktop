#!/usr/bin/env python3
"""Replay the frozen independent Audio input patch, never an owner deployment."""

import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess


def require(ok, message):
    if not ok:
        raise SystemExit(message)


def identity(raw, row):
    require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'Member identity differs: ' + row.get('path', row.get('relative', 'archive')))


def original_member(root, name):
    if name != 'evidence/preimages.json.gz':
        return (root / name).read_bytes()
    encoded = (root / (name + '.b64')).read_bytes()
    require(encoded.endswith(b'\n') and encoded.count(b'\n') == 1,
            'Expected strict base64 and one terminal LF')
    return base64.b64decode(encoded[:-1], validate=True)


def verify_original_inventory(root):
    require(not any(p.is_symlink() for p in root.rglob('*')), 'Symlink in Audio capsule')
    manifest_raw = (root / 'FILES.json').read_bytes()
    manifest = json.loads(manifest_raw)
    transport = json.loads((root / 'TEXT_TRANSPORT.json').read_bytes())
    require(transport['schema'] == 'pocket4-lossless-text-transport-v1'
            and transport['original_member'] == 'evidence/preimages.json.gz'
            and transport['transport_member'] == 'evidence/preimages.json.gz.b64'
            and transport['encoding'] == 'strict base64 followed by one LF'
            and transport['original_FILES_sha256'] == hashlib.sha256(manifest_raw).hexdigest(),
            'Text transport mapping or original inventory pin differs')
    identity((root / transport['transport_member']).read_bytes(),
             {'bytes': transport['transport_bytes'], 'sha256': transport['transport_sha256']})
    identity(original_member(root, transport['original_member']),
             {'bytes': transport['original_bytes'], 'sha256': transport['original_sha256']})
    require(len(manifest['files']) == 56, 'Frozen Audio inventory count differs')
    expected = {'FILES.json', 'TEXT_TRANSPORT.json'}
    for row in manifest['files']:
        name = row['path']
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts
                and relative.as_posix() == name, 'Unsafe original member')
        physical = name + '.b64' if name == 'evidence/preimages.json.gz' else name
        require(physical not in expected, 'Duplicate original member')
        expected.add(physical)
        identity(original_member(root, name), row)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    require(actual == expected, 'Unexpected or missing transported Audio member')


def new_location(path):
    path = path.absolute()
    require('..' not in path.parts, 'Parent traversal is forbidden in output paths')
    for node in (path, *path.parents):
        require(not node.is_symlink(), 'Symlink in output ancestry')
    path = path.resolve(strict=False)
    require(path.parent.is_dir() and not path.exists(), 'Output requires a new path in an existing directory')
    return path


def replay(root, output):
    root = root.resolve(strict=True)
    output = new_location(output)
    require(output != root and not output.is_relative_to(root), 'Replay must not mutate its capsule')
    verify_original_inventory(root)
    manifest = json.loads((root / 'source-manifest.json').read_bytes())
    compressed = original_member(root, manifest['preimages_archive']['path'])
    identity(compressed, manifest['preimages_archive'])
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(1024 * 1024 + 1)
    require(len(raw) <= 1024 * 1024, 'Preimages exceed the frozen size bound')
    archive = json.loads(raw)
    preimages = {row['relative']: row for row in manifest['preimages']}
    postimages = {row['relative']: row for row in manifest['postimages']}
    require(len(preimages) == 3 and len(postimages) == 6 and len(archive['files']) == 3,
            'Expected three complete preimages and six exact postimages')
    for name in set(preimages) | set(postimages):
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts
                and relative.as_posix() == name, 'Unsafe source replay path')
    require(archive['source_origin_commit'] == manifest['base_commit'], 'Preimage base differs')
    output.mkdir(mode=0o700)
    seen = set()
    for row in archive['files']:
        name = row['relative']
        require(name in preimages and name not in seen, 'Unexpected preimage')
        seen.add(name)
        data = row['text'].encode('utf-8')
        identity(data, preimages[name])
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    patch = root / manifest['patch']['path']
    identity(patch.read_bytes(), manifest['patch'])
    for options in (['--check'], []):
        result = subprocess.run(['/usr/bin/git', 'apply', *options, str(patch)],
                                cwd=output, capture_output=True, timeout=30, check=False)
        require(result.returncode == 0, 'Frozen Audio replay failed: ' + result.stderr.decode('utf-8', 'replace'))
    actual = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
    require(actual == set(postimages), 'Replay produced unexpected source paths')
    for name, row in postimages.items():
        identity((output / name).read_bytes(), row)
    return {'schema': 'pocket4-audio-api-independent-replay-v1', 'preimages': 3,
            'postimages': 6, 'exact_replay_passed': True, 'selected_owner_successor': False,
            'runtime_qualified': False, 'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capsule', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    root = args.capsule.resolve(strict=True)
    output = new_location(args.output)
    require(output != root and not output.is_relative_to(root), 'Replay must not mutate its capsule')
    report = new_location(args.report) if args.report else None
    if report:
        require(report != root and not report.is_relative_to(root)
                and report != output and not report.is_relative_to(output),
                'Report must be outside its capsule and replay tree')
    result = replay(root, output)
    raw = json.dumps(result, sort_keys=True, indent=2) + '\n'
    if report:
        with report.open('x', encoding='utf-8') as stream:
            stream.write(raw)
    print(raw, end='')


if __name__ == '__main__':
    main()
