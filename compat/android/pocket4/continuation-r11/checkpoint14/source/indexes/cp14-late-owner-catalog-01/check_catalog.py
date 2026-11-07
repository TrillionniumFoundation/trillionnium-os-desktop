"""Read local immutable files and actual origin-tree metadata; write new catalog."""
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266')
OWN = BASE / 'lmkd-recovery-20261105-01'
HERE = Path(__file__).resolve().parent
def sha(data):
    return hashlib.sha256(data).hexdigest()
def pinned(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, str(path)
    return json.loads(raw)
base = pinned(BASE / 'root-recovery-20261104-02/checkpoint14-publication/payload-base-index.json', 496723, '5f233370555e150065bad0273906ea20be17a3fbac6d653a39e0682c6db2d9d7')
old138 = pinned(OWN / 'cp14-source-allowlist-01/allowlist.json', 69796, '0ebcbbe6916ff183bd01ead64f1def9be9f76f759fabd02350c75b9fa9e169a1')
old47 = pinned(OWN / 'cp14-source-addendum-01/allowlist.json', 27430, '4c46f8e958be779e3772ee5c74b20de274b73836bb9dddff572e418cf666b479')
existing = {r['path']: r for r in base['files']}
assert len(existing) == 756
for origin in (old138, old47):
    for row in origin['files']:
        same = existing[row['target_path']]
        assert same['bytes'] == row['bytes'] and same['sha256'] == row['sha256']
        assert same['git_blob_sha1'] == row['git_sha'] and same['mode'] == row['mode']
trees = {r['sha']: r for r in json.loads((HERE / 'origin-recursive-readback-index.json').read_bytes())}
rows = json.loads((HERE / 'input-rows.json').read_bytes())
seen, added, skipped = {}, [], []
for row in rows:
    assert row['path'] == 'source/owner/' + row['origin_path']
    assert row['mode'] == '100644' and row['encoding'] == 'utf-8'
    path = Path(row['local_path'])
    assert path.is_relative_to(OWN) and path.is_file()
    assert path.suffix in ('.json', '.py', '.md', '.diff', '.txt')
    raw = path.read_bytes()
    raw.decode('utf-8', 'strict')
    assert b'\0' not in raw
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    git_sha = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    assert git_sha == row['git_blob_sha1']
    tree = trees[row['origin_tree']]
    assert tree['truncated'] is False
    remote = next(r for r in tree['tree'] if r['path'] == row['origin_path'])
    assert remote['type'] == 'blob' and remote['mode'] == row['mode'] and remote['sha'] == git_sha and remote['size'] == len(raw)
    if row['path'] in seen:
        assert all(row[k] == seen[row['path']][k] for k in ('bytes', 'sha256', 'git_blob_sha1', 'mode'))
        skipped.append({'path': row['path'], 'reason': 'duplicate identical late path'})
        continue
    seen[row['path']] = row
    if row['path'] in existing:
        assert all(row[k] == existing[row['path']][k] for k in ('bytes', 'sha256', 'git_blob_sha1', 'mode'))
        skipped.append({'path': row['path'], 'reason': 'already present exact in fixed base756'})
        continue
    added.append(row)
added.sort(key=lambda r: r['path'])
catalog = {'schema': 1, 'kind': 'CP14_LATE_OWNER_FIXED_TEXT_ADDENDUM',
    'base_tree': '339635402a41f8186701e6afe91bb727840641f9',
    'base_payload_index_sha256': '5f233370555e150065bad0273906ea20be17a3fbac6d653a39e0682c6db2d9d7',
    'prior_owner138_and47_verified_present_unchanged': True,
    'candidate_row_count': len(rows), 'files_count': len(added),
    'total_bytes': sum(r['bytes'] for r in added), 'skipped_exact_paths': skipped,
    'all_local_utf8_size_sha256_git_sha_verified': True,
    'all_origin_tree_recursive_entries_verified': True,
    'private_UI_images_or_APK_ELF_or_cache_files_included': False,
    'unobserved_15log_actual_results_included': False,
    'actual_Owner11_original_failure_preserved': True,
    'ref_commit_PR_or_frozen_base_changed': False,
    'files': added}
data = (json.dumps(catalog, sort_keys=True, indent=2) + '\n').encode()
with (HERE / 'allowlist.json').open('xb') as stream:
    stream.write(data)
summary = {'schema': 1, 'path': str(HERE / 'allowlist.json'), 'bytes': len(data), 'sha256': sha(data),
    'files_count': len(added), 'payload_bytes': catalog['total_bytes'], 'skipped_count': len(skipped),
    'origin_trees': sorted(trees), 'all_checks_passed': True}
with (HERE / 'verification.json').open('xb') as stream:
    stream.write((json.dumps(summary, sort_keys=True, indent=2) + '\n').encode())
print(json.dumps(summary, indent=2))
