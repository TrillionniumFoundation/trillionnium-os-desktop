#!/usr/bin/env python3
"""Verify a frozen closure index; never execute archived checks, builds or VMs."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

MAX_FILE_BYTES = 2 * 1024 * 1024
EVIDENCE_PREFIX = ('support', 'build', 'evidence')
FIXED_PINS = {
    'repository': 'asterinas/asterinas', 'tag': 'v0.19.0',
    'commit': 'c4b7ed575b7b32773475b194d2ad41fb6d03765b',
    'tree': '96605cf64aeae2d34f29b97e85eff9315fe10a8e',
    'toolchain': 'nightly-2026-07-21', 'reuse': 'full_kernel_derived',
    'source_directory': 'kernel/asterinas',
}
FALSE_SCOPES = ('all_project_blockers_closed',
                'cross_host_reproducibility_accepted',
                'immutable_environment_accepted')
IDENTITY_FIELDS = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode')
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative(name):
    require(type(name) is str and name and not any(ord(c) < 32 or ord(c) == 127 for c in name),
            'invalid relative path')
    path = PurePosixPath(name)
    require(bool(path.parts) and path.name not in ('.', '..') and
            not path.is_absolute() and str(path) == name and
            not any(part in ('.', '..') for part in path.parts) and '\\' not in name,
            'unsafe relative path: ' + name)
    return path.parts


def digest(value):
    return hashlib.sha256(value).hexdigest()


def identity(info):
    return tuple(getattr(info, field) for field in IDENTITY_FIELDS)


def open_root(path):
    absolute = Path(path).absolute()
    require(not any(p in ('.', '..') for p in absolute.parts), 'noncanonical repository root')
    fd = os.open('/', DIR_FLAGS)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd, absolute
    except BaseException:
        os.close(fd)
        raise


def open_directory(anchor, parts):
    fd = os.dup(anchor)
    try:
        for part in parts:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def stable_file(directory, name):
    before_path = os.stat(name, dir_fd=directory, follow_symlinks=False)
    require(stat.S_ISREG(before_path.st_mode), 'non-regular file: ' + name)
    require(before_path.st_size <= MAX_FILE_BYTES, 'file exceeds 2 MiB: ' + name)
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(fd)
        require(identity(before) == identity(before_path), 'file changed before read: ' + name)
        parts, size = [], 0
        while True:
            block = os.read(fd, 128 * 1024)
            if not block:
                break
            size += len(block)
            require(size <= MAX_FILE_BYTES, 'file grew beyond 2 MiB: ' + name)
            parts.append(block)
        after = os.fstat(fd)
        after_path = os.stat(name, dir_fd=directory, follow_symlinks=False)
        require(identity(before) == identity(after) == identity(after_path), 'file changed during read: ' + name)
        data = b''.join(parts)
        require(len(data) == before.st_size, 'short file read: ' + name)
        return data
    finally:
        os.close(fd)


def read_relative(anchor, name):
    parts = relative(name)
    parent = open_directory(anchor, parts[:-1])
    try:
        return stable_file(parent, parts[-1])
    finally:
        os.close(parent)


def inventory(directory):
    records = {}

    def visit(fd, prefix):
        before = os.fstat(fd)
        for name in sorted(os.listdir(fd)):
            relative(name)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            path = '/'.join(prefix + (name,))
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIR_FLAGS, dir_fd=fd)
                try:
                    require(identity(os.fstat(child)) == identity(info), 'directory changed before read: ' + path)
                    visit(child, prefix + (name,))
                    require(identity(os.fstat(child)) == identity(os.stat(name, dir_fd=fd, follow_symlinks=False)),
                            'directory path changed: ' + path)
                finally:
                    os.close(child)
            else:
                data = stable_file(fd, name)
                records[path] = {'bytes': len(data), 'sha256': digest(data)}
        require(identity(before) == identity(os.fstat(fd)), 'directory changed during inventory')

    visit(directory, ())
    return records


def checksum_entries(data):
    entries = {}
    for line in data.decode('utf-8').splitlines():
        require(len(line) > 66 and line[64:66] == '  ', 'invalid checksum line')
        sha, name = line[:64], line[66:]
        relative(name)
        require(re.fullmatch('[0-9a-f]{64}', sha) is not None and
                name not in entries and name != 'SHA256SUMS', 'invalid/duplicate/self checksum entry')
        entries[name] = sha
    return entries


def verify_phase(repository, path, expected=None):
    parts = relative(path)
    require(parts[:3] == EVIDENCE_PREFIX and len(parts) >= 4, 'phase is outside evidence directory')
    phase = open_directory(repository, parts)
    try:
        anchor = os.fstat(phase)
        manifest = stable_file(phase, 'SHA256SUMS')
        entries = checksum_entries(manifest)
        files = inventory(phase)
        require(files['SHA256SUMS']['sha256'] == digest(manifest), 'manifest changed during inventory: ' + path)
        require(set(files) == set(entries) | {'SHA256SUMS'}, 'unlisted/missing phase files: ' + path)
        for name, sha in entries.items():
            require(files[name]['sha256'] == sha, 'phase checksum mismatch: ' + path + '/' + name)
        result = {'path': path, 'sha256sums_sha256': digest(manifest),
                  'file_count': len(files), 'total_bytes': sum(r['bytes'] for r in files.values()),
                  'checksum_entries': len(entries),
                  'maximum_file_bytes': max(r['bytes'] for r in files.values())}
        if expected is not None:
            for key in ('file_count', 'total_bytes'):
                require(type(expected[key]) is int and expected[key] >= 0 and result[key] == expected[key],
                        'phase count/size mismatch: ' + path + ':' + key)
            require(re.fullmatch('[0-9a-f]{64}', expected['sha256sums_sha256']) is not None and
                    result['sha256sums_sha256'] == expected['sha256sums_sha256'], 'phase manifest identity mismatch: ' + path)
        reopened = open_directory(repository, parts)
        try:
            require((anchor.st_dev, anchor.st_ino) == (os.fstat(reopened).st_dev, os.fstat(reopened).st_ino),
                    'phase pathname was replaced: ' + path)
        finally:
            os.close(reopened)
        return result
    finally:
        os.close(phase)


def verify(repository_path, index_name='phase-index.json', report_name='report.json'):
    repository, repo = open_root(repository_path)
    try:
        final_directory = Path(__file__).absolute().parent
        final_path = str(final_directory.relative_to(repo))
        relative(index_name); relative(report_name)
        require(index_name != report_name and 'SHA256SUMS' not in (index_name, report_name), 'index/report names overlap')
        own = verify_phase(repository, final_path)
        final_fd = open_directory(repository, relative(final_path))
        try:
            own_manifest = read_relative(final_fd, 'SHA256SUMS')
            require(digest(own_manifest) == own['sha256sums_sha256'], 'final manifest changed before index read')
            own_entries = checksum_entries(own_manifest)
            index_bytes = read_relative(final_fd, index_name)
            report_bytes = read_relative(final_fd, report_name)
            require(digest(index_bytes) == own_entries[index_name] and digest(report_bytes) == own_entries[report_name],
                    'index/report do not match verified final manifest')
            index = json.loads(index_bytes)
            report = json.loads(report_bytes)
        finally:
            os.close(final_fd)
        require(index['schema'] == 'a01-cloud-closure-index/1', 'wrong index schema')
        require(type(index['phases']) is list and index['phases'], 'empty or invalid phase index')
        paths = []
        for row in index['phases']:
            parts = relative(row['path'])
            require(parts[:3] == EVIDENCE_PREFIX and len(parts) >= 4, 'indexed path outside evidence')
            final_parts = relative(final_path)
            require(not (parts[:len(final_parts)] == final_parts or final_parts[:len(parts)] == parts),
                    'index must exclude its own phase and ancestors/descendants: circular manifest identity')
            require(all(not (parts[:len(old)] == old or old[:len(parts)] == parts) for old in paths),
                    'duplicate/overlapping indexed phases')
            paths.append(parts)
        results = [verify_phase(repository, row['path'], row) for row in index['phases']]
        require(read_relative(repository, 'README.md') == b'', 'root README must be exactly zero bytes')
        lock = json.loads(read_relative(repository, 'support/upstream-lock.json'))
        require(all(lock['kernel'][key] == value for key, value in FIXED_PINS.items()), 'fixed upstream pins changed')
        require(all(report['scopes'][key] is False for key in FALSE_SCOPES), 'final acceptance scope widened')
        # Recheck the final phase after all other reads, so changes during verification fail closed.
        require(verify_phase(repository, final_path) == own, 'final phase changed during verification')
        return {'passed': True, 'scope': 'Offline phase inventory/hash/size and fixed-pin verification only; indexed validation claims are not rerun.',
                'final_phase': own, 'indexed_phases': results,
                'fixed_pins_checked': FIXED_PINS, 'root_readme_bytes': 0,
                'scopes': {key: False for key in FALSE_SCOPES},
                'nested_manifest_policy': 'Nested checksum receipts are ordinary files covered by the phase root manifest. They are never recursively interpreted or executed.'}
    finally:
        os.close(repository)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--index', default='phase-index.json', help='relative to this verifier phase')
    parser.add_argument('--report', default='report.json', help='relative to this verifier phase')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.repo_root, args.index, args.report), indent=2))
    except (ValueError, KeyError, TypeError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print('verification failed: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
