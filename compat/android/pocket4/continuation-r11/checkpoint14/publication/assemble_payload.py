#!/usr/bin/env python3
"""One-off publication assembler: read fixed UTF-8 artifacts, never run a probe."""
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path('/workspace/scratch/94990735b266')
OUT = ROOT/'root-recovery-20261104-02/checkpoint14-publication'
CATALOGS = [
    ('lmkd-recovery-20261105-01/cp14-source-allowlist-01/allowlist.json', '0ebcbbe6916ff183bd01ead64f1def9be9f76f759fabd02350c75b9fa9e169a1', 'owner'),
    ('android-cp14-source-index-02/SOURCE_FILE_ALLOWLIST.json', '58abedabb2ce919e3a78dfb56e9e30433aa3d3afa31940940cc0757612296dce', 'android'),
    ('android-cp14-source-addendum-03/SOURCE_ADDITIONS.json', '7c9fd768daba28d4ac0a6d0c3338dd1d96050be976c44b33d5b1a3967f01a33b', 'android'),
    ('native-recovery-20261105-02/cp14-native-source-index01/SOURCE_FILE_ALLOWLIST.json', '01396fde7f9a5089102ab76f85fe4f3bb6ac1bc1d8a70efa185fc1c6829e74cd', 'native'),
    ('lmkd-recovery-20261105-01/cp14-source-addendum-01/allowlist.json', '4c46f8e958be779e3772ee5c74b20de274b73836bb9dddff572e418cf666b479', 'owner'),
    ('native-recovery-20261105-02/cp14-native-addendum01/SOURCE_FILE_ALLOWLIST.json', 'db37226bca844d8b7ec42efa0db3b66134472e72fbb21eece4dfe7bd10016340', 'native'),
]
EVIDENCE = [
    'candidate07-android-result-read01', 'candidate07-android-cases-read02',
    'producer10-broker-compile01', 'producer10-broker-ordinary01',
    'owner10-normal01-prepared-read01', 'owner10-normal01-runtime-read01', 'owner10-normal01-logs01',
    'qa-r5-install-state02-failure-read01', 'qa-r5-install-state03-read01',
    'bili-r5-buffer-viewport01-read01', 'bili-r5-player-structure-read01', 'bili-r5-player-structure-read02',
    'paired-art-apex-definitions-read01', 'paired-art-apex-manifests-read02',
    'art-role-java-callers-read01', 'art-role-seccomp-source-read01', 'fs-identity-query-abi-read01',
    'paired-builder462-compile01-transport02', 'producer11-retirement-compile01',
    'producer11-retirement-ordinary01', 'art-role-ingress-exit-read01', 'amazon-artifact-readonly01',
]
INDEXES = {
    'lmkd-recovery-20261105-01/cp14-source-allowlist-01': ['summary.json', 'allowlist.json', 'frozen-tree-readback.json'],
    'android-cp14-source-index-02': ['README.md', 'SOURCE_FILE_ALLOWLIST.json', 'validation-result.json'],
    'android-cp14-source-addendum-03': ['SOURCE_ADDITIONS.json'],
    'native-recovery-20261105-02/cp14-native-source-index01': ['SOURCE_TREE_INDEX.json', 'README.md', 'SOURCE_FILE_ALLOWLIST.json', 'SOURCE_PINS.json'],
    'lmkd-recovery-20261105-01/cp14-source-addendum-01': ['verification.json', 'allowlist.json'],
    'native-recovery-20261105-02/cp14-native-addendum01': ['SOURCE_TREE_INDEX.json', 'SOURCE_FILE_ALLOWLIST.json', 'SOURCE_PINS.json'],
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def read(path):
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode), str(path)
    data = path.read_bytes()
    data.decode('utf-8', errors='strict')
    assert len(data) == info.st_size
    assert '\x00' not in data.decode('utf-8'), str(path)
    return data


def main():
    rows = {}
    def add(target, local, expected=None, catalog=None, existing_blob=False):
        target_path = Path(target)
        assert not target_path.is_absolute() and '..' not in target_path.parts
        assert not any(x.endswith('.transport-parts') or x == '__pycache__' for x in target_path.parts)
        assert target not in rows, target
        raw = read(local)
        row = {'path': target, 'local_path': str(local), 'bytes': len(raw), 'sha256': sha(raw),
               'git_blob_sha1': blob(raw), 'mode': '100644', 'encoding': 'utf-8',
               'existing_git_blob': existing_blob}
        if expected:
            assert row['bytes'] == expected['bytes'] and row['sha256'] == expected['sha256'], target
            prior_blob = expected.get('git_sha') or expected.get('git_blob_sha1') or expected.get('git_blob')
            assert prior_blob == row['git_blob_sha1'], target
            row['origin_tree'] = expected.get('origin_tree')
            row['origin_path'] = expected.get('origin_path') or expected.get('path')
        if catalog:
            row['input_catalog'] = catalog
        rows[target] = row

    for relative, expected_sha, kind in CATALOGS:
        raw = read(ROOT/relative)
        assert sha(raw) == expected_sha, relative
        value = json.loads(raw)
        for row in value['files']:
            target = row.get('target_path') or row.get('target')
            if target is None:
                target = ('source/native/'+row['package']+'/'+row['relative']) if kind == 'native' else row['path']
            assert target.startswith('source/'+kind+'/')
            local = Path(row.get('local_path') or row.get('localpath'))
            assert local.is_relative_to(ROOT)
            add(target, local, row, relative, True)

    for directory, names in INDEXES.items():
        for name in names:
            add('source/indexes/'+Path(directory).name+'/'+name, ROOT/directory/name)

    evidence_root = ROOT/'root-recovery-20261104-02/evidence'
    for name in EVIDENCE:
        folder = evidence_root/name
        assert folder.is_dir(), str(folder)
        for local in sorted(folder.rglob('*')):
            if local.is_file() and not any(x.endswith('.transport-parts') or x == '__pycache__' for x in local.parts):
                add('evidence/'+name+'/'+str(local.relative_to(folder)), local)
    metadata_root = ROOT/'root-recovery-20261104-02/checkpoint14-evidence'
    for local in sorted(metadata_root.rglob('*')):
        if local.is_file() and not any(x.endswith('.transport-parts') for x in local.parts):
            add('evidence/exact-transport/'+str(local.relative_to(metadata_root)), local)

    add('publication/assemble_payload.py', Path(__file__))
    result = {'schema': 1, 'checkpoint': 14, 'scope': 'immutable source/evidence candidate; no runtime qualification implied',
              'files': [rows[name] for name in sorted(rows)], 'count': len(rows),
              'bytes': sum(row['bytes'] for row in rows.values()), 'raw_private_UI_or_APK_ELF_included': False}
    body = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()
    output = OUT/'payload-base-index.json'
    if output.exists():
        assert output.read_bytes() == body, 'base index already frozen with other bytes'
    else:
        with output.open('xb') as stream:
            stream.write(body)
    print(json.dumps({'path': str(output), 'bytes': len(body), 'sha256': sha(body), 'payload_files': len(rows),
                      'payload_bytes': result['bytes'], 'existing_blobs': sum(row['existing_git_blob'] for row in rows.values())}))


if __name__ == '__main__':
    main()
