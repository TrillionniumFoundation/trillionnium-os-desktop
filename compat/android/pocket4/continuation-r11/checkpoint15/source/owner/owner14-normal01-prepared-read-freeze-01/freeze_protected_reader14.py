#!/usr/bin/env python3
"""Freeze one exact Owner14 protected read only after observed bytes and SHA."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent.parent
OLD = BASE / 'owner11-normal01-prepared-read-freeze-01'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=('prepared', 'runtime'), required=True)
    parser.add_argument('--bytes', type=int, required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    assert 0 < args.bytes <= 1048576 and re.fullmatch('[0-9a-f]{64}', args.sha256)
    out = BASE / ('owner14-normal01-' + args.kind + '-read-freeze-01')
    assert not out.exists()
    manifest = (OLD / 'manifest.json').read_bytes()
    assert sha(manifest) == '6644011c7d0d06b819fca6b0ae4981cbbd0850c3c49bf85dcdcab0c7ac35dc92'
    for row in json.loads(manifest)['files']:
        raw = (OLD / row['path']).read_bytes()
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    source = (OLD / 'read.py').read_text()
    assert sha(source.encode()) == 'fd87aa8d233eee659986184a338aa74c8871a6f39206865b019a1b545d68f5e2'
    substitutions = [
        ('p4-owner11-normal-20261105-01-state', 'p4-owner14-normal-20261105-01-state', 1),
        ('EXPECTED_REPORT_BYTES = 55139', 'EXPECTED_REPORT_BYTES = ' + str(args.bytes), 1),
        ('d48a503751555736dd85b54211a89c4a2b51371adf41c860f44cd3887b8c5bf5', args.sha256, 1),
        ('fixed-owner11-normal01-prepared-read', 'fixed-owner14-normal01-' + args.kind + '-read', 1),
    ]
    member = 'prepared.json'
    if args.kind == 'runtime':
        member = 'runtime-result.json'
        substitutions += [
            ('prepared.json', member, 4),
            ('externally pinned actual prepared report differs', 'externally pinned actual runtime report differs', 1),
            ('held prepared directory changed', 'held runtime directory changed', 1),
        ]
    text = source
    for old, new, count in substitutions:
        assert text.count(old) == count
        text = text.replace(old, new)
    inverse = text
    for old, new, count in reversed(substitutions):
        assert inverse.count(new) == count
        inverse = inverse.replace(new, old)
    assert inverse == source
    ast.parse(text)
    compile(text, '<fixed protected Owner14 report reader>', 'exec')
    request = json.loads((OLD / 'request.json').read_bytes())
    assert request['stdin'] == source
    request['stdin'] = text
    request['idempotency_key'] = 'p4-owner14-normal01-' + args.kind + '-read01-' + sha(text.encode())[:16]
    validation = {
        'kind': 'owner14_' + args.kind + '_fixed_reader_binding',
        'fixed_path': '/opt/p4-owner14-normal-20261105-01-state/' + member,
        'expected_bytes': args.bytes, 'expected_sha256': args.sha256,
        'preimage_reader_sha256': sha(source.encode()), 'reader_sha256': sha(text.encode()),
        'only_exact_fixed_root_member_length_digest_and_inert_scope_literals_changed': True,
        'inverse_literal_transform_exact': True,
        'held_root_owned_FD_identity_and_double_read_gates_unchanged': True,
        'request_sha256': sha(pretty(request)), 'reader_executed': False,
        'mutations': False, 'runtime_qualification': False,
    }
    members = {
        'read.py': text.encode(), 'request.json': pretty(request),
        'validation.json': pretty(validation),
        'source.diff': ''.join(difflib.unified_diff(source.splitlines(True), text.splitlines(True),
            fromfile='owner11-prepared/read.py', tofile='owner14-' + args.kind + '/read.py')).encode(),
        'freeze_protected_reader14.py': Path(__file__).read_bytes(),
    }
    out.mkdir()
    rows = []
    for name, raw in members.items():
        raw.decode('utf-8')
        with (out / name).open('xb') as stream:
            stream.write(raw)
        rows.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw)})
    raw_manifest = pretty({'kind': 'owner14_' + args.kind + '_fixed_reader', 'files': rows, 'executed': False})
    with (out / 'manifest.json').open('xb') as stream:
        stream.write(raw_manifest)
    print(json.dumps({'root': str(out), 'manifest_sha256': sha(raw_manifest),
                      'request_bytes': len(pretty(request)), 'key': request['idempotency_key'], **validation}, indent=2))


if __name__ == '__main__':
    main()
