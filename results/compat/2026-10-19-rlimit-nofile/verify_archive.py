#!/usr/bin/env python3
"""Verify frozen byte evidence without extracting or executing archived inputs."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check(data, expected, label):
    require(len(data) == expected['bytes'], f'{label}: size differs')
    require(hashlib.sha256(data).hexdigest() == expected['sha256'], f'{label}: SHA256 differs')


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    require(manifest['schema'] == 'a04.rlimit-nofile-baseline-evidence.v1', 'unknown manifest')
    decoded, archives = {}, {}
    for name, expected in manifest['files'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, f'{name}: invalid path')
        path = root / name
        require(path.is_file() and not path.is_symlink(), f'{name}: not a regular file')
        data = path.read_bytes()
        check(data, expected, name)
        encoding = expected.get('encoding')
        if encoding in ('gzip', 'tar+gzip'):
            limit = expected['uncompressed_bytes']
            require(0 <= limit <= 64 * 1024 * 1024, f'{name}: invalid decoded size')
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
                data = compressed.read(limit + 1)
            check(data, {'bytes': limit, 'sha256': expected['uncompressed_sha256']}, name + ':decoded')
        decoded[name] = data
        if encoding == 'tar+gzip':
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
                members = archive.getmembers()
                names = [member.name for member in members]
                require(len(names) == len(set(names)) and set(names) == set(expected['members']),
                        f'{name}: member set differs')
                for member in members:
                    require(member.isfile(), f'{name}/{member.name}: not a regular member')
                    record = expected['members'][member.name]
                    require(oct(member.mode) == record['mode'], f'{name}/{member.name}: mode differs')
                    check(archive.extractfile(member).read(), record, name + '/' + member.name)
                archives[name] = set(names)
    shared_count = 0
    for name, members in manifest['shared_archive_members'].items():
        for member, expected in members.items():
            require(member not in archives[name], f'{name}/{member}: duplicate stored member')
            check(decoded[expected['content_from']], expected, name + '/' + member + ':shared')
            shared_count += 1
    for name, expected in manifest['identical_original_snapshots'].items():
        check(decoded[expected['content_from']], expected, name + ':shared')
    print(json.dumps({'archive_integrity_passed': True, 'payload_files': len(manifest['files']),
                      'stored_archive_members': sum(map(len, archives.values())),
                      'shared_elf_members': shared_count, 'original_source_snapshots': 3,
                      'new_guest_qualification': False}))


if __name__ == '__main__':
    main()
