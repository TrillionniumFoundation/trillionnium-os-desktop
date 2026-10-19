#!/usr/bin/env python3
"""Publish a frozen CI ZIP as byte-preserving parts, and actually restore it."""

import argparse
import hashlib
import json
import stat
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(argv):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert result.returncode == 0, result.stdout
    return {'argv': argv, 'exit_code': result.returncode, 'output': result.stdout}


def verify_zip(path, manifest_path):
    expected = json.loads(manifest_path.read_text())
    # The two frozen reviewer schema versions name the identical entry list
    # either "members" or "files". Preserve the original document unchanged.
    members = expected['members'] if 'members' in expected else expected['files']
    assert isinstance(members, list)
    mapping = {member['path']: member for member in members}
    assert len(mapping) == len(members)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        assert len(infos) == len(members)
        assert sorted(i.filename for i in infos) == sorted(mapping)
        assert archive.testzip() is None
        total = 0
        for info in infos:
            relative = PurePosixPath(info.filename)
            assert not relative.is_absolute() and '..' not in relative.parts
            assert '\\' not in info.filename and not info.is_dir()
            assert not stat.S_ISLNK(info.external_attr >> 16)
            data = archive.read(info)
            recorded = mapping[info.filename]
            assert len(data) == info.file_size == recorded['bytes']
            assert sha(data) == recorded['sha256']
            assert f'{info.CRC:08x}' == recorded['crc32']
            if 'compressed_bytes' in recorded:
                assert info.compress_size == recorded['compressed_bytes']
            total += len(data)
    return {'archive': path.name, 'member_manifest': manifest_path.name, 'member_manifest_sha256': sha(manifest_path.read_bytes()), 'regular_members': len(members), 'uncompressed_bytes': total, 'safe_paths_no_symlinks_no_duplicates': True, 'all_member_size_sha256_crc32_verified': True, 'zip_crc_test_passed': True, 'no_member_executed': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--member-manifest', required=True)
    parser.add_argument('--original-manifest', required=True)
    parser.add_argument('--preserved', type=Path, required=True)
    parser.add_argument('--restore-root', type=Path, required=True)
    parser.add_argument('--helper-root', type=Path, required=True)
    parser.add_argument('--reuse-verified-parts', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    original_manifest_path = root / args.original_manifest
    original_manifest_bytes = original_manifest_path.read_bytes()
    frozen = json.loads(original_manifest_bytes)
    archive_record = next(i for i in frozen['files'] if i['path'] == args.archive)
    archive_path = root / args.archive
    original_bytes = archive_path.read_bytes()
    assert len(original_bytes) == archive_record['bytes']
    assert sha(original_bytes) == archive_record['sha256']
    assert not args.preserved.exists() and not args.restore_root.exists()
    config_path = root / 'archive-parts-config.json'
    if args.reuse_verified_parts:
        parts = json.loads((root / 'archive-parts.json').read_text())
        assert len(parts['archives']) == 1
        recorded = parts['archives'][0]
        assert recorded['path'] == args.archive
        assert recorded['bytes'] == len(original_bytes) and recorded['sha256'] == sha(original_bytes)
        split = run(['python3', '-I', str(args.helper_root / 'restore-r10-archives.py'), '--manifest', str(root / 'archive-parts.json'), '--verify-only'])
        split['meaning'] = 'Revalidate already created parts; preserve their bytes and prior split receipt after a member-manifest schema mismatch in the delivery helper.'
    else:
        assert not config_path.exists()
        config_path.write_text(json.dumps({'archives': [{'path': args.archive, 'key': 'a06-original-zip'}]}, indent=2) + '\n')
        split = run(['python3', '-I', str(args.helper_root / 'split-r10-archives.py'), '--root', str(root), '--config', str(config_path), '--receipt', str(root / 'archive-parts-execution.json')])
    original_zip_review = verify_zip(archive_path, root / args.member_manifest)
    args.preserved.write_bytes(original_bytes)
    assert args.preserved.read_bytes() == original_bytes
    assert archive_path.read_bytes() == original_bytes
    archive_path.unlink()
    assert not archive_path.exists()
    restore = run(['python3', '-I', str(args.helper_root / 'restore-r10-archives.py'), '--manifest', str(root / 'archive-parts.json'), '--output-root', str(args.restore_root)])
    restored = args.restore_root / args.archive
    assert restored.read_bytes() == args.preserved.read_bytes() == original_bytes
    assert not archive_path.exists()
    restored_zip_review = verify_zip(restored, root / args.member_manifest)
    assert restored_zip_review == original_zip_review
    assert original_manifest_path.read_bytes() == original_manifest_bytes
    receipt = {
        'schema': 'r10.ci-original-archive-parts-publication.v1',
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'original_frozen_manifest': {'path': args.original_manifest, 'bytes': len(original_manifest_bytes), 'sha256': sha(original_manifest_bytes)},
        'original_archive': archive_record,
        'original_archive_body_in_git_delivery': False,
        'original_preserved_outside_git_delivery': str(args.preserved),
        'original_frozen_manifest_unchanged': True,
        'parts_manifest': {'path': 'archive-parts.json', 'bytes': (root / 'archive-parts.json').stat().st_size, 'sha256': sha((root / 'archive-parts.json').read_bytes())},
        'split_execution': split,
        'actual_empty_directory_restore': restore,
        'restored_archive': str(restored),
        'source_archive_absent_before_and_after_restore': True,
        'original_restored_bytes_equal': True,
        'archive_not_recompressed_or_modified': True,
        'all_zip_members_independently_verified_before_and_after_restore': original_zip_review,
        'no_product_execution_or_producer_worktree_access': True,
        'instructions': 'Run ../review/restore-r10-archives.py with this directory archive-parts.json and a new --output-root. The restored ZIP matches the original frozen manifest. Internal ZIP paths are read after restoration/extraction; the ZIP body is intentionally absent from the Git tree.',
    }
    (root / 'publication-transport.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'root': str(root), 'archive_bytes': len(original_bytes), 'archive_sha256': sha(original_bytes), 'parts': len(json.loads((root / 'archive-parts.json').read_text())['archives'][0]['parts']), 'verified_zip_members': original_zip_review['regular_members'], 'original_body_omitted': True, 'original_frozen_manifest_unchanged': True, 'actual_restore_passed': True}))


if __name__ == '__main__':
    main()
