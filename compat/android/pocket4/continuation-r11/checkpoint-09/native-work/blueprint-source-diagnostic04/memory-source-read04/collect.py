#!/usr/bin/env python3
"""Fixed four-file source read. Writes only a new owned evidence directory."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path('/home/alex/work/pocket4-go6r2-blueprint-writer-controls-source-readonly-04-20261105')
BASE = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source')
FILES = (
    ('blueprint-context-test.go', 'build/blueprint/context_test.go', 262144),
    ('blueprint-module-ctx.go', 'build/blueprint/module_ctx.go', 262144),
    ('blueprint-ninja-defs.go', 'build/blueprint/ninja_defs.go', 262144),
    ('blueprint-go.mod', 'build/blueprint/go.mod', 16384),
)
def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def identity(value):
    return {'dev': value.st_dev, 'ino': value.st_ino, 'mode': value.st_mode,
            'size': value.st_size, 'mtime_ns': value.st_mtime_ns,
            'ctime_ns': value.st_ctime_ns}

def save(path, value):
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}

def collect():
    if os.getuid() != 1000 or os.geteuid() != 1000:
        raise RuntimeError('only the ordinary operator UID is admitted')
    os.umask(0o077)
    for directory in (ROOT.parent, *ROOT.parent.parents):
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise RuntimeError('evidence parent aliases a non-directory')
    if ROOT.exists() or ROOT.is_symlink():
        raise RuntimeError('create-only evidence directory already exists')
    ROOT.mkdir(mode=0o700)
    report = {'schema': 1, 'scope': 'four fixed source files; held read-only FDs',
              'started_utc': utc(), 'uid': os.getuid(), 'euid': os.geteuid(),
              'source_changes': 0, 'Main_actions': 0, 'builds_started': 0,
              'process_scan': False, 'network_actions': 0, 'files': []}
    texts = {}
    for name, relative, maximum in FILES:
        source = BASE / relative
        row = {'path': str(source), 'maximum_bytes': maximum, 'output': name}
        fd = -1
        try:
            fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            before = os.fstat(fd)
            row['held_before'] = identity(before)
            if not stat.S_ISREG(before.st_mode):
                raise RuntimeError('not a regular source file')
            if before.st_size > maximum:
                raise RuntimeError('source exceeds this exact read bound')
            pieces = []
            count = 0
            while count <= maximum:
                data = os.read(fd, min(32768, maximum + 1 - count))
                if not data:
                    break
                pieces.append(data)
                count += len(data)
            raw = b''.join(pieces)
            after = os.fstat(fd)
            row['held_after'] = identity(after)
            row['path_after'] = identity(source.lstat())
            if count > maximum or len(raw) != before.st_size:
                raise RuntimeError('size changed or read limit exceeded')
            if row['held_before'] != row['held_after'] or row['held_after'] != row['path_after']:
                raise RuntimeError('held source identity/version changed during read')
            text = raw.decode('utf-8', errors='strict')
            row['bytes'] = len(raw)
            row['sha256'] = digest(raw)
            row['saved'] = save(ROOT / name, raw)
            row['state'] = 'HELD_SOURCE_READ_VERIFIED'
            texts[name] = text
        except Exception as error:
            row['state'] = 'SOURCE_READ_FAILED'
            row['error'] = repr(error)
            row['errno'] = getattr(error, 'errno', None)
        finally:
            if fd >= 0:
                os.close(fd)
        report['files'].append(row)
    report['finished_utc'] = utc()
    report['all_four_verified'] = len(texts) == 4
    result = save(ROOT / 'result.json', report)
    bundle = save(ROOT / 'text-bundle.json', {'schema': 1, 'result': report, 'files': texts})
    print(json.dumps({'state': 'SOURCE_READ_COMPLETE' if len(texts) == 4 else 'SOURCE_READ_PARTIAL',
                      'root': str(ROOT), 'result': result, 'bundle': bundle,
                      'source_count': len(texts), 'Main_actions': 0, 'builds_started': 0}), flush=True)
    return 0 if len(texts) == 4 else 1

if __name__ == '__main__':
    raise SystemExit(collect())
