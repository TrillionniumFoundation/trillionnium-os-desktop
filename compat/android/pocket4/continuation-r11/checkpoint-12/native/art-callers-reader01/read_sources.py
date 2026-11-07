#!/usr/bin/env python3
"""Read only four fixed current AOSP sources, retaining every failed observation."""
import base64
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat

BASE = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
SOURCES = (
    ('art/runtime/runtime.cc', 524288),
    ('art/runtime/native/dalvik_system_ZygoteHooks.cc', 262144),
    ('frameworks/base/core/jni/com_android_internal_os_Zygote.cpp', 524288),
    ('art/runtime/Android.bp', 262144),
)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'uid': info.st_uid, 'gid': info.st_gid, 'bytes': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def observe(relative, limit):
    path = BASE / relative
    row = {'path': str(path), 'relative': relative, 'maximum_bytes': limit,
           'started_utc': utc(), 'complete': False}
    try:
        parents = {}
        for parent in path.parents:
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise RuntimeError('source ancestor is not a real directory: ' + str(parent))
            parents[str(parent)] = (info.st_dev, info.st_ino, info.st_mode)
        named_before = path.lstat()
        row['named_before'] = identity(named_before)
        if not stat.S_ISREG(named_before.st_mode) or named_before.st_size > limit:
            raise RuntimeError('source is not regular or exceeds its fixed bound')
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            row['held_before'] = identity(os.fstat(stream.fileno()))
            if row['held_before'] != row['named_before']:
                raise RuntimeError('named/held source identity differs before read')
            raw = stream.read(limit + 1)
            row['held_after'] = identity(os.fstat(stream.fileno()))
            row['named_after'] = identity(path.lstat())
            if not (row['held_before'] == row['held_after'] == row['named_after']):
                raise RuntimeError('source changed while held')
            if len(raw) != row['held_before']['bytes'] or len(raw) > limit:
                raise RuntimeError('source read is incomplete or exceeds its fixed bound')
            for name, expected in parents.items():
                info = Path(name).lstat()
                if (info.st_dev, info.st_ino, info.st_mode) != expected:
                    raise RuntimeError('source ancestor identity changed: ' + name)
            row['bytes'] = len(raw)
            row['sha256'] = digest(raw)
            row['text'] = raw.decode('utf-8', errors='strict')
            row['complete'] = True
    except Exception as error:
        row['error'] = {'type': type(error).__name__, 'message': str(error),
                        'errno': getattr(error, 'errno', None),
                        'filename': getattr(error, 'filename', None)}
    row['finished_utc'] = utc()
    return row


def main():
    started = utc()
    rows = [observe(relative, limit) for relative, limit in SOURCES]
    complete = all(row['complete'] for row in rows)
    result = {'schema': 1, 'scope': 'four fixed current AOSP source observations only',
              'source_sha256': SOURCE_SHA256, 'started_utc': started, 'finished_utc': utc(),
              'all_four_complete': complete, 'files': rows,
              'installed_ART_binary_bound': False, 'compiled450_source_bound': False,
              'source_execution': False, 'recursive_scan': False, 'Main_actions': 0,
              'files_written': 0, 'policy_or_resource_changes': 0,
              'remote_service_or_build_started': False}
    raw = (json.dumps(result, ensure_ascii=True, sort_keys=True) + '\n').encode()
    if len(raw) > 20000000:
        raise RuntimeError('bounded four-source result unexpectedly exceeds encoding bound')
    packed = gzip.compress(raw, compresslevel=6, mtime=0)
    envelope = {'schema': 1, 'encoding': 'gzip+base64', 'uncompressed_bytes': len(raw),
                'sha256': digest(raw), 'gzip_bytes': len(packed), 'gzip_sha256': digest(packed),
                'all_four_complete': complete, 'payload': base64.b64encode(packed).decode('ascii')}
    print(json.dumps(envelope, sort_keys=True), flush=True)
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
