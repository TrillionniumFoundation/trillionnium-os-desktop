#!/usr/bin/env python3
"""Index retained new source/evidence through build07 preparation, without a run."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ARCHIVES = BASE.parents[2] / 'official_versions_restore_20261106_env2'
DEST = BASE / 'checkpoint06-delta'
OUTPUT = 'post-checkpoint06-through-source-r4-added-or-changed.json'
PREFIX = 'compat/android/pocket4/all-launcher-upgrades-20261106/framework_provider_repair/normal06/'
BASELINE_ARCHIVES = [
    'normal06_full_source_archive', 'normal06_upstream_go_and_recursive_archive',
    'normal06_graph_and_matrix_archive', 'normal06_provider_round12_archive',
    'normal06_postcp04_r3_delta_archive', 'normal06_postcp04_r4_delta_archive',
    'normal06_postcp04_r5_delta_archive', 'normal06_postcp04_r6_delta_archive',
]
LATER_ARCHIVES = ['normal06_postcp04_r7_delta_archive', 'normal06_postcp04_r8_delta_archive']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


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
    baseline_known, archive_latest, archive_pins = {}, {}, {}
    for name in BASELINE_ARCHIVES + LATER_ARCHIVES:
        raw = (ARCHIVES / (name + '.json')).read_bytes()
        archive_pins[name] = {'bytes': len(raw), 'sha256': sha(raw)}
        for row in json.loads(raw)['files']:
            path = row['path']
            if name in BASELINE_ARCHIVES[1:3]:
                if not path.startswith('framework_provider_repair/normal06/'):
                    continue
                path = path[len('framework_provider_repair/normal06/'):]
            body = row['text'].encode('utf-8')
            assert len(body) == row['bytes'] and sha(body) == row['sha256']
            archive_latest[path] = {'archive': name, 'sha256': row['sha256']}
            if name in BASELINE_ARCHIVES:
                baseline_known[path] = row['sha256']
    files = []
    for path in sorted(BASE.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        rel = path.relative_to(BASE).as_posix()
        if rel == 'checkpoint06-delta/' + OUTPUT:
            continue  # Its own digest is returned out of band, avoiding recursion.
        raw = path.read_bytes()
        digest = sha(raw)
        if baseline_known.get(rel) == digest:
            continue
        first = rel.split('/')[0]
        assert first not in top or first in evidence['subtrees'], 'unresolved baseline subtree: ' + first
        old = before.get(rel)
        git_sha = blob(raw)
        if old and old['sha'] == git_sha:
            continue
        assert not rel.lower().endswith(('.apk', '.png', '.jpg', '.jpeg', '.webp', '.mp4'))
        archive = archive_latest.get(rel)
        match = archive and archive['sha256'] == digest
        files.append({'relative_path': rel, 'repository_path': PREFIX + rel,
            'change': 'modified' if old else 'added',
            'checkpoint06_blob_sha1': old['sha'] if old else None,
            'checkpoint06_bytes': old.get('size') if old else None,
            'bytes': len(raw), 'sha256': digest, 'git_blob_sha1': git_sha,
            'raw_source': archive['archive'] if match else 'current_local_original_or_derived_file',
            'raw_archive_match': bool(match)})
    actual06 = [x['relative_path'] for x in files if x['relative_path'].startswith('actual-build06-fence-failure/')]
    assert len(actual06) >= 11
    source04 = [x['relative_path'] for x in files if x['relative_path'].startswith('source-r4/')]
    assert len(source04) >= 40
    document = {'schema': 'pocket4-checkpoint06-exact-source-evidence-delta-v1',
        'scope': 'This agent normal06 subtree through source-r4 build07 preparation and actual settled build06 fence failure; no run is implied.',
        'baseline_commit': evidence['checkpoint'],
        'baseline_git_tree_evidence': {'bytes': len(evidence_raw), 'sha256': sha(evidence_raw)},
        'archive_pins_used_for_unchanged_filter': archive_pins,
        'added_count': sum(row['change'] == 'added' for row in files),
        'modified_count': sum(row['change'] == 'modified' for row in files),
        'deletions_requested': 0, 'old_actual_failures_rewritten': False,
        'binary_APKs_or_private_UI_captures_copied': False, 'index_only': True,
        'self_excluded_for_nonrecursive_digest': 'checkpoint06-delta/' + OUTPUT,
        'actual_build06_failure_original_paths': actual06,
        'source_r4_paths': source04,
        'files': files}
    raw = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode()
    output = DEST / OUTPUT
    if output.exists():
        assert output.read_bytes() == raw, 'Frozen index differs; use a new revision.'
    else:
        output.write_bytes(raw)
    print(json.dumps({'path': str(output), 'bytes': len(raw), 'sha256': sha(raw),
        'added': document['added_count'], 'modified': document['modified_count'],
        'actual06_files': len(actual06), 'source_r4_files': len(source04)}))


if __name__ == '__main__':
    main()
