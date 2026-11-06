#!/usr/bin/env python3
"""Return only one pinned private bundle as bounded zlib-base64; no Main API."""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import zlib

BUNDLE = Path('/home/alex/work/pocket4-beike-search-click-failure-evidence-20261106-r1/bundle.private.json')
BUNDLE_BYTES = 1102634
BUNDLE_SHA = '85b3b9801685a427a484cc81b80de64e66df49ceb477efa99901ac2dfb01cee4'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
CAPTURE_BINDING = {'diagnostic_job': '1a1b30c6205-fc05-8083', 'diagnostic_stdout_bytes': 15496, 'diagnostic_stdout_sha256': 'c6b1396ac512fe5730497a2de75642cce3d6c0c24bccbc5a9a83a41b37002e9b', 'diagnostic_terminal_bytes': 733, 'diagnostic_terminal_sha256': 'f3b1a5e3a34df13bcfcf906c3eb3da63c90e28c174385dcc0578691a14c34d5a', 'original_failed_job': '1a1b30305de-fc05-8072', 'original_failed_step': 'search-click-after-partial-commit-01', 'original_failed_case_reclassified': False, 'files': 101, 'original_bytes': 782840}
MAX_COMPRESSED_BYTES = BUNDLE_BYTES + 65536
MAX_STDOUT_BYTES = 2097152


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def census():
    result = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name); row = os.fstat(fd)
            result[name] = (os.readlink('/proc/self/fd/' + name), row.st_dev, row.st_ino,
                            row.st_mode, row.st_uid, row.st_gid)
        except OSError as failure:
            if failure.errno not in (errno.EBADF, errno.ENOENT):
                raise
    return result


def pinned_bundle():
    owned = []; deadline = time.monotonic() + 30
    try:
        current = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); owned.append(current)
        for part in BUNDLE.parts[1:-1]:
            current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
            owned.append(current)
        fd = os.open(BUNDLE.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=current)
        owned.append(fd); first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == 0 and first.st_nlink == 1 and
             not first.st_mode & 0o077 and first.st_size == BUNDLE_BYTES, 'FIXED_ROOT_PRIVATE_BUNDLE')
        data = bytearray()
        while len(data) <= BUNDLE_BYTES:
            need(time.monotonic() < deadline, 'BOUNDED_BUNDLE_READ')
            part = os.read(fd, min(65536, BUNDLE_BYTES + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        again = os.open(BUNDLE.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
        owned.append(again)
        need(len(data) == BUNDLE_BYTES and sha(data) == BUNDLE_SHA and
             all(getattr(first, key) == getattr(os.fstat(fd), key) == getattr(os.fstat(again), key)
                 for key in FIELDS), 'EXACT_BUNDLE_BYTES_AND_UNCHANGED_IDENTITY')
        return bytes(data), tuple(getattr(first, key) for key in FIELDS)
    finally:
        for fd in reversed(owned):
            os.close(fd)


def main():
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_ROOT_REQUIRED')
    before = census()
    raw, identity = pinned_bundle()
    compressed = zlib.compress(raw, 9)
    need(0 < len(compressed) <= MAX_COMPRESSED_BYTES, 'FIXED_COMPRESSED_BYTE_BOUND')
    again, again_identity = pinned_bundle()
    need(again == raw and again_identity == identity, 'BUNDLE_UNCHANGED_AFTER_COMPRESSION')
    after = census()
    need(after == before, 'WHOLE_PROCESS_FD_IDENTITIES_CHANGED')
    result = {
        'schema': 'pocket4-one-fixed-private-bundle-zlib-readback-v1', 'ok': True,
        'encoding': 'zlib-base64', 'capture_binding': CAPTURE_BINDING,
        'bundle': {'path': str(BUNDLE), 'bytes': BUNDLE_BYTES, 'sha256': BUNDLE_SHA},
        'bundle_stat': dict(zip(FIELDS, identity)),
        'compressed_bytes': len(compressed), 'compressed_sha256': sha(compressed),
        'data': base64.b64encode(compressed).decode('ascii'),
        'process_fds_before': before, 'process_fds_after': after,
        'whole_process_fd_identities_unchanged': True, 'original_file_bytes_and_stat_unchanged': True,
        'raw_output_may_contain_private_state': True, 'raw_output_repository_publication_admitted': False,
        'Main_reads': 0, 'Main_commands': 0, 'namespace_entries': 0, 'Main_locks_or_guards': 0,
        'UI_actions': 0, 'installs': 0, 'permission_changes': 0, 'signals': 0,
        'originals_modified': False, 'automatic_retry': False, 'reconciliation_published': False,
        'old_UNKNOWN_modified': False, 'production_ready': False
    }
    output = (json.dumps(result, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False) + '\n').encode('ascii')
    need(len(output) <= MAX_STDOUT_BYTES, 'COMPLETE_PRIVATE_STDOUT_BYTE_BOUND')
    need(census() == before, 'FINAL_FD_IDENTITIES_CHANGED')
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
