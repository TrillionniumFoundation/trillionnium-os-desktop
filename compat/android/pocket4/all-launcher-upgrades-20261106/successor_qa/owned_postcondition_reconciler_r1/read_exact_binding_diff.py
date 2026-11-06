#!/usr/bin/env python3
"""Read two metadata records from one exact private bundle; no Main API."""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

BUNDLE = Path('/home/alex/work/pocket4-beike-postcondition-evidence-20261106-r1/bundle.private.json')
BUNDLE_BYTES = 1218042
BUNDLE_SHA = '3c72bc43b2a32950a576405049b12cf6984ef790978638122ef2a7d4602941c8'
OUTPUT = Path('/home/alex/work/pocket4-beike-held-binding-diff-20261106-r1')
SELECTED = ('steps/close-entry-popup-01/held-main-binding.json',
            'steps/inspect-after-close-02/held-main-binding.json')
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


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


def differences(left, right):
    result = []
    missing = object()
    def walk(a, b, path, depth):
        need(depth <= 64 and len(result) <= 512, 'BOUNDED_METADATA_DIFF')
        if type(a) is type(b) and a == b:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                walk(a.get(key, missing), b.get(key, missing), path + '/' + key.replace('~', '~0').replace('/', '~1'), depth + 1)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                result.append({'path': path, 'list_lengths': [len(a), len(b)]})
            for index in range(max(len(a), len(b))):
                walk(a[index] if index < len(a) else missing, b[index] if index < len(b) else missing,
                     path + '/' + str(index), depth + 1)
        else:
            row = {'path': path, 'before_present': a is not missing, 'after_present': b is not missing}
            if a is not missing:
                row['before'] = a
            if b is not missing:
                row['after'] = b
            need(len(json.dumps(row, ensure_ascii=True).encode()) <= 65536, 'DIFF_VALUE_BOUND')
            result.append(row)
    walk(left, right, '', 0)
    return result


def save(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            wrote = os.write(fd, raw[offset:]); need(wrote > 0, 'OWNED_RAW_WRITE_PROGRESS'); offset += wrote
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        readback = bytearray()
        while len(readback) <= len(raw):
            part = os.read(fd, min(65536, len(raw) + 1 - len(readback)))
            if not part:
                break
            readback.extend(part)
        need(bytes(readback) == raw, 'ORIGINAL_RAW_READBACK')
    finally:
        os.close(fd)
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def main():
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_ROOT_REQUIRED')
    os.umask(0o077); before = census()
    raw, identity = pinned_bundle(); bundle = json.loads(raw)
    need(bundle.get('schema') == 'pocket4-beike-two-step-private-original-byte-bundle-v1', 'FIXED_BUNDLE_SCHEMA')
    records = []
    for name in SELECTED:
        row = bundle['files'][name]
        need(set(row) == {'bytes', 'sha256', 'base64'} and type(row['bytes']) is int and 0 < row['bytes'] <= 1048576,
             'TWO_BOUNDED_BINDING_RECORDS_ONLY')
        body = base64.b64decode(row['base64'], validate=True)
        need(len(body) == row['bytes'] and sha(body) == row['sha256'], 'ORIGINAL_BINDING_BYTE_PIN')
        decoded = json.loads(body)
        need(decoded.get('schema') == 'pocket4-successor-held-binding-r5-v1' and
             decoded.get('package') == 'com.lianjia.beike' and decoded.get('uid') == 10143,
             'FIXED_NON_UI_BINDING_METADATA_ONLY')
        records.append((name, body, decoded))
    # No other row is base64-decoded or interpreted as UI content.
    del bundle
    diff = differences(records[0][2], records[1][2])
    OUTPUT.mkdir(mode=0o700)
    saved = []
    for index, (name, body, value) in enumerate(records):
        saved.append({'original_relative_path': name, **save(OUTPUT / ('binding-%02d.original.json' % index), body)})
    again, again_identity = pinned_bundle()
    need(again == raw and again_identity == identity, 'BUNDLE_UNCHANGED_AFTER_DIFF')
    parent = os.open(OUTPUT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    need(census() == before, 'WHOLE_PROCESS_FD_IDENTITIES_CHANGED')
    result = {'schema': 'pocket4-exact-two-held-binding-difference-v1', 'ok': True,
              'bundle': {'path': str(BUNDLE), 'bytes': BUNDLE_BYTES, 'sha256': BUNDLE_SHA},
              'saved_originals': saved, 'differences': diff, 'difference_count': len(diff),
              'raw_original_bytes_preserved': True, 'Python_integer_precision_preserved': True,
              'whole_process_fd_identities_unchanged': True, 'other_UI_rows_decoded': 0,
              'Main_reads': 0, 'Main_commands': 0, 'namespace_entries': 0,
              'Main_locks_or_guards': 0, 'old_evidence_changed': False, 'reconciliation_written': False}
    result_raw = (json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()
    save(OUTPUT / 'result.json', result_raw)
    parent = os.open(OUTPUT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    need(census() == before, 'FINAL_FD_IDENTITY_CHECK')
    sys.stdout.buffer.write(result_raw); sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
