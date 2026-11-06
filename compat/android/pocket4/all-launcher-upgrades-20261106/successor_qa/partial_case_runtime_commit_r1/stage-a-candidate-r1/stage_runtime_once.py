#!/usr/bin/env python3
"""Stage only the new readonly runtime proof owner and actual host prerequisites."""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path('/home/alex/work/pocket4-beike-partial-case-runtime-20261106-r1')
PINS = {'runtime_stage_a_once.py': {'bytes': 44063, 'sha256': '52784825ed50fc6178468ca80d05af7c060d48ca1da4dc2d38094b2778df02f1'}, 'request.json': {'bytes': 838, 'sha256': 'e21cf095aa8a72d95f04a7a3acea477675daeb0882d0919dcad27eb01daa1d9d'}, 'host.stdout.original.jsonl': {'bytes': 3405, 'sha256': '0033cfad5c04b9ed1b5ff8691c59a983ae790ed35a91282fc916a0c197240c4e'}, 'host.terminal.original.json': {'bytes': 731, 'sha256': '4c755da48c16bdca5c577ab528ca21e43f60cd776f378a5fbba09e1fd866a351'}}
ENTRY_SHA = '52784825ed50fc6178468ca80d05af7c060d48ca1da4dc2d38094b2778df02f1'
PAYLOAD_SHA = '7914f01180c39a963d9cdc294f5323dc91ec620987d9a05e3ba8e581fc5c72e0'
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
         payload['schema'] == 'pocket4-stage-a-runtime-proof-stage-payload-v1' and
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
    need(ROOT.parent.resolve() == ROOT.parent and ROOT.name == 'pocket4-beike-partial-case-runtime-20261106-r1',
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
    print(json.dumps({'schema': 'pocket4-stage-a-runtime-proof-stage-v1', 'root': str(ROOT),
        'files': PINS, 'whole_process_fd_identities_unchanged': True, 'mode': 'readonly-runtime-candidate-not-yet-invoked',
        'Main_commands': 0, 'namespace_entries': 0, 'Main_locks_or_guards': 0,
        'private_bundle_copied': False, 'reconciliation_published': False}, sort_keys=True), flush=True)
    entry = ROOT / 'runtime_stage_a_once.py'
    sys.argv = [str(entry), '--execute-runtime-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['runtime_stage_a_once.py']['bytes']), '--request-sha256', 'e21cf095aa8a72d95f04a7a3acea477675daeb0882d0919dcad27eb01daa1d9d', '--request-bytes', '838']
    exec(compile(bodies['runtime_stage_a_once.py'], str(entry), 'exec'),
         {'__name__': '__main__', '__file__': str(entry)})


if __name__ == '__main__':
    main()
