#!/usr/bin/env python3
"""Archive already-frozen Bazel follow-up evidence; no CI or product execution."""
import datetime
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile

ROOT = Path('/workspace/scratch/499c7902de8e/r10-evidence/owner-ci')
SOURCE = ROOT / 'bazel-followup'
DEST = ROOT / 'bazel-followup-package'
PRIMARY = ['README.md', 'BAZEL_FAILURE_DIAGNOSIS.md', 'log-preservation.json',
           'source-comparison.json', 'source-and-jobs.json', 'failure-excerpts.json',
           'windows-test-blocks.json', 'final-status.json', 'final-snapshot.json',
           'freeze-state.json', 'excluded-raw-copies.json']


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def record(path, name=None):
    data = path.read_bytes()
    return {'path': name or path.name, 'bytes': len(data), 'sha256': sha(data)}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    assert not DEST.exists(), 'Refusing to overwrite completed package'
    started = now()
    omissions = json.loads((SOURCE / 'excluded-raw-copies.json').read_text())['copies']
    omit = {x['excluded_raw_path'] for x in omissions}
    assert omit == {'117846024935.log', '117846024963.log', '117846025117.log', 'job-log-responses.json'}
    for x in omissions:
        raw = (SOURCE / x['excluded_raw_path']).read_bytes()
        compressed = (SOURCE / x['replacement_path']).read_bytes()
        assert len(raw) == x['raw_bytes'] and sha(raw) == x['raw_sha256']
        assert len(compressed) == x['compressed_bytes'] and sha(compressed) == x['compressed_sha256']
        assert lzma.decompress(compressed) == raw
    names = []
    for p in SOURCE.rglob('*'):
        assert not p.is_symlink(), p
        if not p.is_file():
            continue
        n = p.relative_to(SOURCE).as_posix()
        pp = PurePosixPath(n)
        assert not pp.is_absolute() and '..' not in pp.parts
        assert not set(pp.parts).intersection({'.git', 'target', 'home', 'Fleet', 'cargo-home', 'rustup-home', '__pycache__', '.ssh', '.aws'})
        assert pp.suffix not in {'.rlib', '.rmeta', '.o', '.pyc', '.pyo'}
        if n not in omit:
            names.append(n)
    names.sort()
    assert set(PRIMARY).issubset(names)
    files = [record(SOURCE / n, n) for n in names]
    index = {x['path']: x for x in files}
    manifest = {'schema_version': 1, 'created_at': started,
                'check_head': 'd32e795f0d24df89fc57745f6fae70fbd0642eba',
                'ci_checkout_commit': '60a3376902982d79e85173d6aaf6bd631b4c4cf3',
                'source_tree': 'a3e718280a7e17b8c4a226a0232bf18c23fd3586',
                'entry_count': len(files), 'total_file_bytes': sum(x['bytes'] for x in files),
                'files': files, 'archive_order': ['files-manifest.json', *names],
                'self_reference': 'The manifest is the first archive member and is externally hashed by artifact-manifest.json; it does not hash itself.',
                'omissions': omissions, 'failed_evidence_omitted': False,
                'external_roots_excluded': 'All checkouts, credentials, tool/cache roots and compiled products are outside SOURCE and not included.'}
    mbytes = encoded(manifest)
    stage = Path(tempfile.mkdtemp(prefix='bazel-followup-package.partial-', dir=ROOT))
    try:
        (stage / 'files-manifest.json').write_bytes(mbytes)
        archive = stage / 'raw-evidence.tar.xz'
        with tarfile.open(archive, 'w:xz', preset=6, format=tarfile.PAX_FORMAT) as tf:
            for n in manifest['archive_order']:
                data = mbytes if n == 'files-manifest.json' else (SOURCE / n).read_bytes()
                if n != 'files-manifest.json':
                    assert len(data) == index[n]['bytes'] and sha(data) == index[n]['sha256']
                info = tarfile.TarInfo(n)
                info.size = len(data)
                info.mode = 0o644
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                tf.addfile(info, io.BytesIO(data))
        with tarfile.open(archive, 'r:xz') as tf:
            members = tf.getmembers()
            assert [x.name for x in members] == manifest['archive_order']
            for member in members:
                assert member.isfile() and not member.issym() and not member.islnk()
                data = tf.extractfile(member).read()
                expected = {'bytes': len(mbytes), 'sha256': sha(mbytes)} if member.name == 'files-manifest.json' else index[member.name]
                assert len(data) == member.size == expected['bytes']
                assert sha(data) == expected['sha256']
        primary = []
        for n in PRIMARY:
            out = stage / n
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / n, out)
            actual = record(out, n)
            assert actual == index[n]
            primary.append({**actual, 'archive_entry': n})
        helper = stage / 'package-bazel-followup.py'
        shutil.copyfile(__file__, helper)
        assert files == [record(SOURCE / n, n) for n in names]
        receipt = {'schema_version': 1, 'status': 'verified', 'started_at': started,
                   'completed_at': now(), 'archive': record(archive),
                   'files_manifest': record(stage / 'files-manifest.json'),
                   'packaging_helper': record(helper), 'primary_copies': primary,
                   'verified_regular_member_count': len(files) + 1,
                   'ordered_members_sizes_sha256_verified': True,
                   'primary_equals_archive_entries': True, 'raw_xz_roundtrip_verified': True,
                   'all_frozen_source_inputs_unchanged': True,
                   'atomic_publication': 'Same-filesystem directory rename after all checks; destination must not exist.',
                   'ci_operations': 0, 'compile_or_test_runs': 0}
        (stage / 'artifact-manifest.json').write_bytes(encoded(receipt))
        os.rename(stage, DEST)
        print(json.dumps({'destination': str(DEST), 'entry_count': len(files),
                          'primary_count': len(primary), 'archive': receipt['archive'],
                          'files_manifest': receipt['files_manifest'],
                          'artifact_manifest': record(DEST / 'artifact-manifest.json')}, indent=2))
    except BaseException as error:
        (ROOT / 'bazel-followup-package-failure.json').write_bytes(encoded({
            'status': 'failed', 'at': now(), 'staging_path': str(stage),
            'published': False, 'error_type': type(error).__name__, 'error': str(error)}))
        raise


if __name__ == '__main__':
    main()
