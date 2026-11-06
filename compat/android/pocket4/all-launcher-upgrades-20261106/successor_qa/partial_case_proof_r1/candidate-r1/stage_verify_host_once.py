#!/usr/bin/env python3
"""Stage one fixed host-only partial-case verifier and exact historical inputs."""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path('/home/alex/work/pocket4-beike-partial-case-proof-20261106-r1')
PINS = {'partial_case_core.py': {'bytes': 34105, 'sha256': '13ff07c305afcd2894b240fae52b436567784cf605623361723a86253d33fb96'}, 'read_failed_case.frozen.py': {'bytes': 44768, 'sha256': '0e0716b7237199f2fe377ba9f067c2d0327d54a8efb5f40813b1f3e5ebc0021d'}, 'actual-build-result.original.json': {'bytes': 33691, 'sha256': 'c0dd8117cdb7fa8b551e2a59b466c91d48ee2f2d9a98908f69b3d3fb8807bf3d'}, 'observation.stdout.original.json': {'bytes': 13961, 'sha256': '50890b7a1c8a591f493a1af26606da2279f5b3c0cc1e7a893b19b77d200c0401'}, 'observation.terminal.original.json': {'bytes': 733, 'sha256': 'b314bd6a3cc8304d5d00038ece8f811e88bacadf0df09798c87cb42e613a5ede'}, 'inputs.json': {'bytes': 3631, 'sha256': '2bb7778d62d614ccd4514a2d7a573879e0fd0e01dd5046afba8a59cc4386cfce'}, 'verify_partial_case_host.py': {'bytes': 27116, 'sha256': 'afd9a9410051a4e72e4f5c7e9434bfa60b592fdb02672e7d1df1b3bd8d1ecd34'}}
ENTRY_SHA = 'afd9a9410051a4e72e4f5c7e9434bfa60b592fdb02672e7d1df1b3bd8d1ecd34'
PAYLOAD_SHA = '5a07a11fcbe8bd4f382023ce1a7d78c4accc780ed96ffff68b907cbf7bac494c'
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
         payload['schema'] == 'pocket4-fixed-partial-case-host-stage-payload-v1' and
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
    need(ROOT.parent.resolve() == ROOT.parent and ROOT.name == 'pocket4-beike-partial-case-proof-20261106-r1',
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
    print(json.dumps({'schema': 'pocket4-partial-case-historical-host-stage-v1', 'root': str(ROOT),
        'files': PINS, 'whole_process_fd_identities_unchanged': True, 'mode': 'host-only-verification-not-yet-invoked',
        'Main_commands': 0, 'namespace_entries': 0, 'Main_locks_or_guards': 0,
        'private_bundle_copied': False, 'reconciliation_published': False}, sort_keys=True), flush=True)
    entry = ROOT / 'verify_partial_case_host.py'
    sys.argv = [str(entry), '--verify-host-once', '--source-sha256', ENTRY_SHA, '--source-bytes', str(PINS['verify_partial_case_host.py']['bytes'])]
    exec(compile(bodies['verify_partial_case_host.py'], str(entry), 'exec'),
         {'__name__': '__main__', '__file__': str(entry)})


if __name__ == '__main__':
    main()
