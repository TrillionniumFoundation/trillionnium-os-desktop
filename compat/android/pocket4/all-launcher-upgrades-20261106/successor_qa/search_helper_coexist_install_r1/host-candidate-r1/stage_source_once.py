#!/usr/bin/env python3
"""Publish only the fixed coexistence owner and completed build/B receipts. No Android entry."""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path('/home/alex/work/pocket4-beike-search-helper-coexist-install-20261106-r1')
PINS = {'owned_install_once.py': {'bytes': 39677, 'sha256': '0288098834b039fad646331dce2caa2c4bde7166224a1b770866c7c09b5cae41'}, 'install_search_helper_full_scope.py': {'bytes': 24933, 'sha256': 'a15d1322c1bbf6001d0870307243bf4509e00111484b042038ad583871f101c6'}, 'request.json': {'bytes': 2066, 'sha256': 'b2ed2b01358ff4e15fcc997554042cdf1edf7bfdf6da1d4af73bc58ad70d7324'}, 'build.stdout.original.json': {'bytes': 263, 'sha256': '608d7dec90de0bba10dd8e5e7daf3999a22f984dcd289edb18e7547e4babbc57'}, 'build.terminal.original.json': {'bytes': 729, 'sha256': '121ac5733395c1e66d280ff8cb69df38fe7a163f07ff6c99df18aee73ac4ae7b'}, 'stage-b.stdout.original.jsonl': {'bytes': 19805, 'sha256': '3a046f40503768c5e0411daee65c5b233e6245b32c0098c8fd4493a8915a9cbf'}, 'stage-b.terminal.original.json': {'bytes': 733, 'sha256': '29f4241e351442586e8080fa0d252c883075df864934add9657216cecde72ece'}}
PAYLOAD_SHA = '44860460305c1d3bfb4e6a35ecb1a920755b9660e4147476a552807c63f0beb8'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def need(value, code):
    if not value:
        raise RuntimeError(code)



def sha(raw):
    return hashlib.sha256(raw).hexdigest()



def census():
    found = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name); row = os.fstat(fd)
            found[name] = (os.readlink('/proc/self/fd/' + name), row.st_dev, row.st_ino,
                           row.st_mode, row.st_uid, row.st_gid)
        except OSError as failure:
            if failure.errno not in (errno.EBADF, errno.ENOENT):
                raise
    return found



def main():
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_ROOT_HOST_STAGE')
    need(sys.argv[1:] == ['--payload-sha256', PAYLOAD_SHA], 'EXACT_STAGE_ARGUMENTS')
    before = census()
    raw = sys.stdin.buffer.read(524289)
    need(len(raw) <= 524288 and sha(raw) == PAYLOAD_SHA, 'EXACT_BOUNDED_PAYLOAD')
    payload = json.loads(raw)
    need(set(payload) == {'schema', 'root', 'files'} and
         payload['schema'] == 'pocket4-search-helper-coexist-source-stage-payload-v1' and
         payload['root'] == str(ROOT) and set(payload['files']) == set(PINS), 'CLOSED_FIXED_STAGE_PAYLOAD')
    bodies = {}
    for name, pin in PINS.items():
        need('/' not in name and name not in ('', '.', '..'), 'FLAT_FIXED_STAGE_PATH')
        row = payload['files'][name]
        need(set(row) == {'bytes', 'sha256', 'base64'} and row['bytes'] == pin['bytes'] and
             row['sha256'] == pin['sha256'], 'EXTERNAL_MEMBER_PIN')
        body = base64.b64decode(row['base64'], validate=True)
        need(len(body) == pin['bytes'] and sha(body) == pin['sha256'], 'EXACT_MEMBER_BYTES')
        if name.endswith('.py'):
            compile(body, str(ROOT / name), 'exec')
        bodies[name] = body
    need(ROOT.parent.resolve() == ROOT.parent and ROOT.name == 'pocket4-beike-search-helper-coexist-install-20261106-r1',
         'EXACT_NEW_HOST_PRIVATE_ROOT')
    os.umask(0o077)
    ROOT.mkdir(mode=0o700)
    directory = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(directory)
        need(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700, 'ACTUAL_ROOT_PRIVATE_STAGE')
        for name, body in bodies.items():
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o400, dir_fd=directory)
            try:
                offset = 0
                while offset < len(body):
                    count = os.write(fd, body[offset:]); need(count > 0, 'MEMBER_WRITE_PROGRESS'); offset += count
                os.fsync(fd)
            finally:
                os.close(fd)
        os.fsync(directory)
        need(set(os.listdir(directory)) == set(PINS), 'EXACT_STAGED_FILE_SET')
        for name, pin in PINS.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            try:
                first = os.fstat(fd)
                need(stat.S_ISREG(first.st_mode) and first.st_uid == 0 and first.st_nlink == 1 and
                     stat.S_IMODE(first.st_mode) == 0o400 and first.st_size == pin['bytes'], 'STAGED_FILE_METADATA')
                data = bytearray()
                while len(data) <= first.st_size:
                    part = os.read(fd, min(65536, first.st_size + 1 - len(data)))
                    if not part:
                        break
                    data.extend(part)
                last = os.fstat(fd); current = os.stat(name, dir_fd=directory, follow_symlinks=False)
                need(bytes(data) == bodies[name] and len(data) == pin['bytes'] and sha(data) == pin['sha256'] and
                     all(getattr(first, k) == getattr(last, k) == getattr(current, k) for k in FIELDS),
                     'STAGED_SOURCE_READBACK_CHANGED')
            finally:
                os.close(fd)
    finally:
        os.close(directory)
    need(census() == before, 'STAGE_WHOLE_PROCESS_FD_IDENTITIES_CHANGED')
    print(json.dumps({'schema': 'pocket4-search-helper-coexist-source-stage-v1', 'root': str(ROOT),
        'files': PINS, 'whole_process_fd_identities_unchanged': True, 'mode': 'source-only-normal-coexist-installer-not-invoked',
        'Main_commands': 0, 'namespace_entries': 0, 'Main_locks_or_guards': 0,
        'private_bundle_copied': False, 'reconciliation_published': False}, sort_keys=True), flush=True)



if __name__ == "__main__":
    main()
