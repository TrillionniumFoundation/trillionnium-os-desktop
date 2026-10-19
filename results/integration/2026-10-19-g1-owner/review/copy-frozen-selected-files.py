#!/usr/bin/env python3
"""Copy only manifest-selected, immutable evidence files; never run producers."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(value):
    relative = PurePosixPath(value)
    assert not relative.is_absolute() and '..' not in relative.parts
    assert relative.as_posix() not in {'', '.'}
    return relative


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    for item in config['packages']:
        source = Path(item['source'])
        destination = Path(item['destination'])
        assert not destination.exists()
        manifest_relative = safe_relative(item['manifest'])
        original_manifest = (source / manifest_relative).read_bytes()
        assert digest(original_manifest) == item['manifest_sha256']
        original = json.loads(original_manifest)
        entries = original['files']
        assert len(entries) == item['listed_file_count']
        names = [e['path'] for e in entries]
        assert len(names) == len(set(names))
        assert manifest_relative.as_posix() not in names
        snapshots = {}
        for entry in entries:
            relative = safe_relative(entry['path'])
            path = source / relative
            assert path.is_file() and not path.is_symlink()
            data = path.read_bytes()
            assert len(data) == entry['bytes'] and digest(data) == entry['sha256'], relative
            snapshots[relative.as_posix()] = data
        snapshots[manifest_relative.as_posix()] = original_manifest
        destination.mkdir(parents=True, exist_ok=False)
        copied = []
        for relative, data in sorted(snapshots.items()):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            assert target.read_bytes() == data
            assert (source / relative).read_bytes() == data
            copied.append({'path': relative, 'bytes': len(data), 'sha256': digest(data)})
        assert sorted(p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()) == sorted(snapshots)
        receipt = {
            'schema': 'r10.frozen-selected-files-copy.v1',
            'completed_at_utc': datetime.now(timezone.utc).isoformat(),
            'source': str(source),
            'destination': str(destination),
            'original_manifest': {'path': manifest_relative.as_posix(), 'bytes': len(original_manifest), 'sha256': digest(original_manifest)},
            'listed_files': len(entries),
            'copied_files_including_manifest': len(copied),
            'total_bytes_including_manifest': sum(e['bytes'] for e in copied),
            'all_source_before_after_and_destination_bytes_equal': True,
            'original_manifest_unchanged': True,
            'selected_files_only': True,
            'source_directory_not_recursively_copied': True,
            'no_product_execution_or_producer_worktree_access': True,
            'files': copied,
        }
        receipt_path = Path(item['receipt'])
        assert not receipt_path.exists()
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({k: v for k, v in receipt.items() if k != 'files'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
