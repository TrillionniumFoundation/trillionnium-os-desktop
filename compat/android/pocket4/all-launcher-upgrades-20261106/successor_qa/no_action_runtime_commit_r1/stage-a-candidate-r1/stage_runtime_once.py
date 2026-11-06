#!/usr/bin/env python3
"""Stage only the new no-action proof owner and exact historical prerequisites."""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path('/home/alex/work/pocket4-beike-no-action-runtime-20261106-r1')
PINS = {'runtime_stage_a_once.py': {'bytes': 49806, 'sha256': '2a6dfffa73fa7698e6d59039d992c78a17ddaf07f0a01eab0973c327870c5c1e'}, 'no_action_core.py': {'bytes': 38241, 'sha256': '92cbde977c018203f8206b47a178774bb9c408cfb9c4559be0a574751e01debd'}, 'read_failed_search_click.frozen.py': {'bytes': 42818, 'sha256': '4525a588639a695b9afcbee17d7dfc6d2a9f3445ad9a678c80e6cba3dd5e4b5b'}, 'request.json': {'bytes': 886, 'sha256': '25cc6f0283975904e6f0da6bd14ef6493ba87c5a6799d06a8435b20b2729ef17'}, 'reader.stdout.original.json': {'bytes': 15496, 'sha256': 'c6b1396ac512fe5730497a2de75642cce3d6c0c24bccbc5a9a83a41b37002e9b'}, 'reader.terminal.original.json': {'bytes': 733, 'sha256': 'f3b1a5e3a34df13bcfcf906c3eb3da63c90e28c174385dcc0578691a14c34d5a'}, 'prior-inspect.stdout.original.jsonl': {'bytes': 13947, 'sha256': '23639dfd1822118c1379e306ba45bf2a1e0d5c8b30ee660c6b50125e8b7cdf84'}, 'prior-inspect.terminal.original.json': {'bytes': 733, 'sha256': '8c1b239ea57641d497f59f8f417ec66c663d4290366bb4f2fa008f0460109037'}}
ENTRY_SHA = '2a6dfffa73fa7698e6d59039d992c78a17ddaf07f0a01eab0973c327870c5c1e'
PAYLOAD_SHA = 'd05965d0a9bebc1edb85c3b9c9a16c8c2877da9278cb52c556c5db2947cc1de4'
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
         payload['schema'] == 'pocket4-no-action-runtime-proof-stage-payload-v1' and
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
    need(ROOT.parent.resolve() == ROOT.parent and ROOT.name == 'pocket4-beike-no-action-runtime-20261106-r1',
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
    print(json.dumps({'schema': 'pocket4-no-action-runtime-proof-stage-v1', 'root': str(ROOT),
        'files': PINS, 'whole_process_fd_identities_unchanged': True, 'mode': 'readonly-runtime-candidate-not-yet-invoked',
        'Main_commands': 0, 'namespace_entries': 0, 'Main_locks_or_guards': 0,
        'private_bundle_copied': False, 'reconciliation_published': False}, sort_keys=True), flush=True)
    entry = ROOT / 'runtime_stage_a_once.py'
    sys.argv = [str(entry), '--execute-runtime-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['runtime_stage_a_once.py']['bytes']), '--request-sha256', '25cc6f0283975904e6f0da6bd14ef6493ba87c5a6799d06a8435b20b2729ef17', '--request-bytes', '886']
    exec(compile(bodies['runtime_stage_a_once.py'], str(entry), 'exec'),
         {'__name__': '__main__', '__file__': str(entry)})


if __name__ == '__main__':
    main()
