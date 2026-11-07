#!/usr/bin/env python3
"""One-off CP14 append-only publication assembly; no device actions."""
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path('/workspace/scratch/94990735b266')
WORK = ROOT/'root-recovery-20261104-02'
OUT = WORK/'checkpoint14-publication'
BASE_SHA = '5f233370555e150065bad0273906ea20be17a3fbac6d653a39e0682c6db2d9d7'
CATALOGS = [
    ('lmkd-recovery-20261105-01/cp14-late-owner-catalog-01/allowlist.json',
     '772e9d033d0c81d04d459b3a430dd6a7f820df47c038fedc85a69cc04fda7ffc'),
    ('native-recovery-20261105-02/cp14-native-late-addendum01/SOURCE_FILE_ALLOWLIST.json',
     'c7e2a4dc727869fecce1bf0c6557803800d8641b3e0f23ab4351709da4053799'),
    ('android-cp14-late-source-index-04/SOURCE_ADDITIONS.json',
     '07c54253c684d6bf01a6e3a3806878fe402fe27d9c39bbd0f6041f6b8b1c9139'),
    ('android-cp14-late-source-addendum-05/SOURCE_ADDITIONS.json',
     'cb33d27d4d6afbc8eafbe2499b488508838fcca71607f975d63c0ad20c839cc1'),
]
INDEXES = {
    'lmkd-recovery-20261105-01/cp14-late-owner-catalog-01':
        ['verification.json', 'origin-recursive-readback-index.json', 'allowlist.json',
         'check_catalog.py', 'input-rows.json'],
    'native-recovery-20261105-02/cp14-native-late-addendum01':
        ['SOURCE_PINS', 'SOURCE_TREE_INDEX.json', 'SOURCE_FILE_ALLOWLIST.json'],
    'android-cp14-late-source-index-04': ['SOURCE_ADDITIONS.json'],
    'android-cp14-late-source-addendum-05': ['SOURCE_ADDITIONS.json'],
}
EVIDENCE = [
    'owner11-normal01-prepared-read01', 'owner11-normal01-runtime-read01',
    'owner11-normal01-logs01', 'bili-r5-player-geometry01-read01',
    'amazon-qa-r1-build01', 'amazon-qa-r1-install-state01-read01',
    'root-owner11-cause-review01', 'root-bili-r5-geometry-visual-review01',
    'root-amazon-install01-source-review',
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    before = path.lstat()
    assert stat.S_ISREG(before.st_mode), str(path)
    raw = path.read_bytes()
    text = raw.decode('utf-8', errors='strict')
    assert '\x00' not in text and len(raw) == before.st_size
    return raw


def main():
    raw = read(OUT/'payload-base-index.json')
    assert sha(raw) == BASE_SHA
    base = json.loads(raw)
    assert base['count'] == len(base['files']) == 756
    old = {r['path']: r for r in base['files']}
    rows = {}

    def add(target, local, expected=None, origin=None):
        rel = Path(target)
        assert not rel.is_absolute() and '..' not in rel.parts
        assert not any(x.endswith('.transport-parts') or x == '__pycache__' for x in rel.parts)
        assert not any(x in rel.parts for x in ['private-visual-inspection'])
        assert target not in old and target not in rows, target
        data = read(local)
        row = {'path': target, 'local_path': str(local), 'bytes': len(data),
               'sha256': sha(data), 'mode': '100644', 'encoding': 'utf-8',
               'git_blob_sha1': hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(),
               'existing_git_blob': bool(expected)}
        if expected:
            assert row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'], target
            assert row['git_blob_sha1'] == (expected.get('git_blob_sha1') or expected.get('git_sha')), target
            assert expected.get('mode', '100644') == '100644'
            row['origin_tree'] = expected['origin_tree']
            row['origin_path'] = expected['origin_path']
            row['input_catalog'] = origin
        rows[target] = row

    for rel, digest in CATALOGS:
        raw = read(ROOT/rel)
        assert sha(raw) == digest, rel
        for row in json.loads(raw)['files']:
            path = Path(row.get('local_path') or row.get('localpath'))
            assert path.is_relative_to(ROOT)
            add(row['path'], path, row, rel)
    assert len(rows) == 246
    for directory, names in INDEXES.items():
        for name in names:
            add('source/indexes/'+Path(directory).name+'/'+name, ROOT/directory/name)
    for name in EVIDENCE:
        directory = WORK/'evidence'/name
        assert directory.is_dir(), str(directory)
        for path in sorted(directory.rglob('*')):
            if path.is_file() and not any(x.endswith('.transport-parts') or x == '__pycache__' for x in path.parts):
                add('evidence/'+name+'/'+str(path.relative_to(directory)), path)
    for name in ['checkpoint14-late-evidence', 'checkpoint14-install-evidence']:
        directory = WORK/name
        assert directory.is_dir()
        for path in sorted(directory.rglob('*')):
            if path.is_file() and not any(x.endswith('.transport-parts') for x in path.parts):
                add('evidence/'+name+'/'+str(path.relative_to(directory)), path)
    for name in ['assemble_late_payload.py', 'payload-base-index.json', 'git-batches.json']:
        add('publication/'+name, OUT/name)
    add('evidence/previous-checkpoint13/publication-receipt.json',
        WORK/'checkpoint13-publication/publication-receipt.json')
    result = {'schema': 1, 'checkpoint': 14, 'base_tree': '339635402a41f8186701e6afe91bb727840641f9',
              'base_payload_index_sha256': BASE_SHA, 'base_files_unchanged': 756,
              'files': [rows[k] for k in sorted(rows)], 'count': len(rows),
              'bytes': sum(r['bytes'] for r in rows.values()),
              'private_pixels_APK_ELF_keys_caches_included': False}
    data = (json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2)+'\n').encode()
    path = OUT/'payload-late-index.json'
    if path.exists():
        assert path.read_bytes() == data, 'late index already frozen with other bytes'
    else:
        with path.open('xb') as stream:
            stream.write(data)
    print(json.dumps({'path': str(path), 'bytes': len(data), 'sha256': sha(data),
                      'payload_files': len(rows), 'payload_bytes': result['bytes'],
                      'existing_blobs': sum(r['existing_git_blob'] for r in rows.values())}))


if __name__ == '__main__':
    main()
