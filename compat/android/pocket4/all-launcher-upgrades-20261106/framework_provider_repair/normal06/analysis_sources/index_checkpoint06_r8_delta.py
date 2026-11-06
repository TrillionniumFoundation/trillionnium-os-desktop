#!/usr/bin/env python3
"""Index immutable r8/r7 raw bytes against actual checkpoint06 Git trees."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ARCHIVES = BASE.parents[2] / 'official_versions_restore_20261106_env2'
DEST = BASE / 'checkpoint06-delta'
PREFIX = 'compat/android/pocket4/all-launcher-upgrades-20261106/framework_provider_repair/normal06/'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def put(path, value):
    raw = (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()
    if path.exists():
        assert path.read_bytes() == raw, str(path)
    else:
        path.write_bytes(raw)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def main():
    evidence_raw = (DEST / 'baseline-git-tree-evidence.json').read_bytes()
    evidence = json.loads(evidence_raw)
    assert evidence['checkpoint'] == 'f491498a8a7bad7795c293f0e3f63e3ecdcaa383'
    top = {row['name']: row for row in evidence['root_listing']}
    before = {row['name']: row for row in evidence['root_listing'] if row['type'] == 'file'}
    for prefix, tree in evidence['subtrees'].items():
        assert tree['truncated'] is False and tree['sha'] == top[prefix]['sha']
        for row in tree['tree']:
            if row['type'] == 'blob':
                before[prefix + '/' + row['path']] = row
    archives = {}
    for name in ['normal06_postcp04_r7_delta_archive', 'normal06_postcp04_r8_delta_archive']:
        raw = (ARCHIVES / (name + '.json')).read_bytes()
        archives[name] = {'sha256': sha(raw), 'bytes': len(raw), 'document': json.loads(raw)}
    assert archives['normal06_postcp04_r8_delta_archive']['sha256'] == 'cc1304d32491dd11d5ae2b861b87d6eac44f9de91bb07b066f631d3f6675c313'
    latest = {}
    for name, archive in archives.items():
        for row in archive['document']['files']:
            raw = row['text'].encode('utf-8')
            assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
            assert (BASE / row['path']).read_bytes() == raw, row['path']
            assert not row['path'].lower().endswith(('.apk', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.xml'))
            latest[row['path']] = {**row, 'archive': name}
    def index(rows, scope):
        changed, unchanged = [], []
        for row in sorted(rows, key=lambda x: x['path']):
            path = row['path']
            first = path.split('/')[0]
            assert first not in top or first in evidence['subtrees'], 'unresolved baseline subtree: ' + first
            raw = row['text'].encode('utf-8')
            old = before.get(path)
            blob = git_blob(raw)
            if old and old['sha'] == blob:
                unchanged.append(path)
                continue
            changed.append({'relative_path': path, 'repository_path': PREFIX + path,
                'change': 'modified' if old else 'added',
                'checkpoint06_blob_sha1': old['sha'] if old else None,
                'checkpoint06_bytes': old.get('size') if old else None,
                'bytes': len(raw), 'sha256': sha(raw), 'git_blob_sha1': blob,
                'archive': row['archive'], 'raw_bytes_match_local_and_archive': True})
        raw_receipts = [x['relative_path'] for x in changed if '/actual/' in x['relative_path'] or
                        '/root-readback-01/' in x['relative_path'] or
                        x['relative_path'].startswith('reference/normal05-actual-authority/')]
        return {'schema': 1, 'scope': scope, 'baseline_commit': evidence['checkpoint'],
            'baseline_git_tree_evidence': {'bytes': len(evidence_raw), 'sha256': sha(evidence_raw)},
            'archives': {k: {f: v[f] for f in ['bytes', 'sha256']} for k, v in archives.items()},
            'added_count': sum(x['change'] == 'added' for x in changed),
            'modified_count': sum(x['change'] == 'modified' for x in changed),
            'unchanged_omitted_count': len(unchanged), 'unchanged_omitted_paths': unchanged,
            'deletions_requested': 0, 'binary_APKs_or_private_UI_captures_copied': False,
            'index_only_no_raw_artifact_recopies': True,
            'exact_operational_receipt_and_original_reference_paths': raw_receipts,
            'files': changed}
    r8 = [row for row in latest.values() if row['archive'] == 'normal06_postcp04_r8_delta_archive']
    all_rows = list(latest.values())
    result = []
    for name, rows, scope in [
        ('r8-only-added-or-changed.json', r8, 'Only immutable r8 archive entries, compared against actual checkpoint06.'),
        ('post-checkpoint06-through-r8-added-or-changed.json', all_rows,
         'Union of r7 actual stage/pending receipts and r8; r7 was not included in checkpoint06.')]:
        document = index(rows, scope)
        result.append({**put(DEST / name, document),
                       'added': document['added_count'], 'modified': document['modified_count'],
                       'unchanged_omitted': document['unchanged_omitted_count']})
    print(json.dumps(result))


if __name__ == '__main__':
    main()
