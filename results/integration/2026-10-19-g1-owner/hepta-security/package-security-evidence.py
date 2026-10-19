#!/usr/bin/env python3
"""Package existing R10 evidence only; never run diagnostics or mutate source."""
from __future__ import annotations

import datetime
import hashlib
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

BASE = Path('/workspace/scratch/499c7902de8e')
EVIDENCE = BASE / 'r10-evidence/owner-ci/new-head'
SOURCE = BASE / 'r10-cargo-deny-repro'
DESTINATION = BASE / 'r10-evidence/owner-ci/security-debt-package'
REMOTE = 'd32e795f0d24df89fc57745f6fae70fbd0642eba'
LOCAL = '1b0fedb8c2b510106848f6feaf530c9b3698399d'
TREE = 'a3e718280a7e17b8c4a226a0232bf18c23fd3586'
PRIMARY = [
    'README.md', 'final-status.json', 'final-source-state.json', 'exclusions.json',
    'local-source-comparison.json', 'round-07-final.json',
    'deny-repro-01/SECURITY_DEBT_DIAGNOSIS.md',
    'deny-repro-01/SECURITY_DEBT_DIAGNOSIS.en.md',
    'deny-repro-01/execution.json', 'deny-repro-01/tools-installation.json',
    'deny-repro-01/error-summary.json', 'deny-repro-01/dependency-scope.json',
    'deny-repro-01/agentd-graph-execution.json',
    'deny-repro-01/agentd-reachability.json',
    'deny-repro-01/sqlite-upgrade-constraints.json',
    'deny-repro-01/preservation.json', 'deny-repro-01/preservation-supplement.json',
    'deny-repro-01/upstream-sources/manifest.json',
    'deny-repro-01/cargo-deny.log.xz',
]


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record(path: Path, relative: str | None = None) -> dict:
    data = path.read_bytes()
    return {'path': relative or path.name, 'bytes': len(data), 'sha256': digest(data)}


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def source_state() -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(['git', '-C', str(SOURCE), *args], text=True).strip()
    state = {
        'commit': git('rev-parse', 'HEAD'),
        'tree': git('rev-parse', 'HEAD^{tree}'),
        'status_porcelain': git('status', '--porcelain=v1', '--untracked-files=all'),
    }
    assert state == {'commit': LOCAL, 'tree': TREE, 'status_porcelain': ''}, state
    return state


def safe_name(name: str, policy: dict) -> None:
    path = PurePosixPath(name)
    assert name and not path.is_absolute() and str(path) == name
    assert '..' not in path.parts and '.' not in path.parts
    assert not set(path.parts).intersection(policy['forbidden_archive_components']), name
    assert path.suffix not in policy['forbidden_artifact_suffixes'], name


def main() -> None:
    started = now()
    if DESTINATION.exists():
        raise RuntimeError('Refusing to overwrite a completed package')
    before = source_state()
    policy = json.loads((EVIDENCE / 'exclusions.json').read_text())
    excluded = {x['file']['path']: x for x in policy['excluded_existing_evidence_files']}
    assert set(excluded) == {'deny-repro-01/cargo-deny.log'}
    paths = []
    for path in EVIDENCE.rglob('*'):
        assert not path.is_symlink(), path
        if not path.is_file():
            continue
        name = path.relative_to(EVIDENCE).as_posix()
        safe_name(name, policy)
        if name not in excluded:
            paths.append(name)
    paths.sort()
    assert len(paths) == len(set(paths)) and set(PRIMARY).issubset(paths)
    for name, item in excluded.items():
        assert record(EVIDENCE / name, name) == item['file']
        compressed = item['replacement']
        assert record(EVIDENCE / compressed['path'], compressed['path']) == compressed
        expanded = lzma.decompress((EVIDENCE / compressed['path']).read_bytes())
        assert len(expanded) == item['file']['bytes']
        assert digest(expanded) == item['file']['sha256']
        assert expanded == (EVIDENCE / name).read_bytes()
    entries = [record(EVIDENCE / name, name) for name in paths]
    index = {entry['path']: entry for entry in entries}
    manifest = {
        'schema_version': 1, 'created_at': started,
        'remote_source_commit': REMOTE, 'local_equivalent_commit': LOCAL, 'source_tree': TREE,
        'included_root': str(EVIDENCE), 'entry_count': len(entries),
        'total_uncompressed_file_bytes': sum(x['bytes'] for x in entries),
        'files': entries, 'exclusions_manifest': 'exclusions.json',
        'archive_order': ['files-manifest.json', *paths],
        'self_reference_rule': 'The manifest is the first archive entry; its hash is externally bound by artifact-manifest.json. It does not list itself as evidence.',
        'compressed_log_original_bytes_verified': True,
    }
    manifest_data = json_bytes(manifest)
    staging = Path(tempfile.mkdtemp(prefix='security-debt-package.partial-', dir=DESTINATION.parent))
    try:
        (staging / 'files-manifest.json').write_bytes(manifest_data)
        archive = staging / 'raw-evidence.tar.xz'
        with tarfile.open(archive, 'w:xz', preset=6, format=tarfile.PAX_FORMAT) as tf:
            for name in manifest['archive_order']:
                data = manifest_data if name == 'files-manifest.json' else (EVIDENCE / name).read_bytes()
                if name != 'files-manifest.json':
                    assert len(data) == index[name]['bytes'] and digest(data) == index[name]['sha256']
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                tf.addfile(info, io.BytesIO(data))
        verified = []
        with tarfile.open(archive, 'r:xz') as tf:
            members = tf.getmembers()
            assert [m.name for m in members] == manifest['archive_order']
            for member in members:
                safe_name(member.name, policy)
                assert member.isfile() and not member.issym() and not member.islnk()
                data = tf.extractfile(member).read()
                assert len(data) == member.size
                expected = ({'bytes': len(manifest_data), 'sha256': digest(manifest_data)}
                            if member.name == 'files-manifest.json' else index[member.name])
                assert len(data) == expected['bytes'] and digest(data) == expected['sha256']
                verified.append(member.name)
        primary = []
        for name in PRIMARY:
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(EVIDENCE / name, target)
            actual = record(target, name)
            assert actual == index[name]
            primary.append({**actual, 'archive_entry': name})
        helper = staging / 'package-security-evidence.py'
        shutil.copyfile(Path(__file__), helper)
        # Rehash every frozen input after compression; never publish a mixed snapshot.
        assert entries == [record(EVIDENCE / name, name) for name in paths]
        after = source_state()
        assert before == after
        artifact = {
            'schema_version': 1, 'status': 'verified', 'started_at': started, 'completed_at': now(),
            'source_before': before, 'source_after': after, 'source_unchanged': True,
            'remote_equivalent_commit': REMOTE,
            'archive': record(archive), 'files_manifest': record(staging / 'files-manifest.json'),
            'packaging_helper': record(helper), 'primary_copies': primary,
            'verified_archive_entries': len(verified), 'ordered_members_verified': True,
            'all_member_sizes_and_sha256_verified': True, 'primary_equals_archive_entries': True,
            'compressed_log_roundtrip_verified': True, 'frozen_inputs_unchanged': True,
            'atomic_publication': 'The completed staging directory is renamed to security-debt-package only after all verification; destination must not preexist.',
            'product_build_performed': False, 'diagnostic_reexecuted': False, 'remote_operations': False,
        }
        (staging / 'artifact-manifest.json').write_bytes(json_bytes(artifact))
        # Same-filesystem rename is the only publication point.
        os.rename(staging, DESTINATION)
        print(json.dumps({'destination': str(DESTINATION), 'archive': artifact['archive'],
                          'manifest': artifact['files_manifest'], 'entry_count': len(entries),
                          'primary_count': len(primary), 'source_unchanged': True}, indent=2))
    except BaseException as error:
        failure = {'schema_version': 1, 'status': 'packaging_failed', 'at': now(),
                   'staging_path': str(staging), 'published': False,
                   'error_type': type(error).__name__, 'error': str(error)}
        (DESTINATION.parent / 'security-debt-package-failure.json').write_bytes(json_bytes(failure))
        raise


if __name__ == '__main__':
    main()
