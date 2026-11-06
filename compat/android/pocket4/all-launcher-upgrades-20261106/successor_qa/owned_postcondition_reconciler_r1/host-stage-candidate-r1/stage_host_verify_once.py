#!/usr/bin/env python3
"""Stage a fixed new host source closure, then only verify original evidence."""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path('/home/alex/work/pocket4-beike-owned-postcondition-20261106-25bd347fa5b74ba0bbf1a0cc29aa96fb')
PINS = {'action.plan.json': {'bytes': 319, 'sha256': 'ce1b63519bc77494612be3dee12867c9f02493e6d9a58afa2d745aaaddfc9a0a'}, 'action.process-request.json': {'bytes': 5162, 'sha256': '1cd983df6ea2970e6a8e36fb02e1f9baaa107007c9495f5392e19e1d521d0f19'}, 'action.process-start.json': {'bytes': 5859, 'sha256': '1293ea865303c1c26774937b5fd90720f12413420773f949765d9dfabb77fb2a'}, 'action.stderr.bin': {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}, 'action.stdout.jsonl': {'bytes': 6099, 'sha256': '4bbeced66e30ab83d35ff5def9a506f1da6e3488cd906515eb0ed1d1072c36c1'}, 'action.terminal.json': {'bytes': 731, 'sha256': '61c5940334cc25c8ecdf70e6a18a070a734dc6d4a4c1fd43c9bb778600bdb1bd'}, 'observation.plan.json': {'bytes': 178, 'sha256': 'cc933685490468cc98b2a6f585d9067c33ee616144dab96603f66e34842bf085'}, 'observation.process-request.json': {'bytes': 4831, 'sha256': 'afe1a331ab004344be9b934e1f9d0cccb81569189c017271dc455c1527a354d2'}, 'observation.process-start.json': {'bytes': 5529, 'sha256': 'a4d0a8aea7189bdd8944daef150267ae507f6472b0ae3f62f80ef62c8dfcb1b5'}, 'observation.stderr.bin': {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}, 'observation.stdout.jsonl': {'bytes': 6075, 'sha256': '6d063bbabc3bb7cedaa1f1662629ec2b5fd93015979ac2b6aeecef612b48d9e6'}, 'observation.terminal.json': {'bytes': 731, 'sha256': 'd1c9e26b0d766ac25c24fd8b579b37674b70fc5ad48572fc744ac80af45413f0'}, 'owned_postcondition_core.py': {'bytes': 23654, 'sha256': '4653c827e236680a227e50d739eaa45b4432126d5326c5bc38d184a58a31f3dc'}, 'publish_owned_reconciliation.py': {'bytes': 41581, 'sha256': 'b9944bfd05f3ed216e9a55c9933a51c00380f8b9b02f16d449104a5496a8484e'}, 'request.json': {'bytes': 2565, 'sha256': '57be31604c416476f8e0e4cd92bc7bf6d716fc36ebc5bf88e893190e6e69d654'}}
ENTRY_SHA = 'b9944bfd05f3ed216e9a55c9933a51c00380f8b9b02f16d449104a5496a8484e'
REQUEST_SHA = '57be31604c416476f8e0e4cd92bc7bf6d716fc36ebc5bf88e893190e6e69d654'
PAYLOAD_SHA = '5c971c815963c14633c552df7b6e1d46ba3af3b87cf6bd31e7dcf6dab854adb9'
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
         payload['schema'] == 'pocket4-owned-postcondition-host-stage-payload-v1' and
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
    need(ROOT.parent.resolve() == ROOT.parent and ROOT.name.startswith('pocket4-beike-owned-postcondition-20261106-'),
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
    print(json.dumps({'schema': 'pocket4-owned-postcondition-host-stage-v1', 'root': str(ROOT),
        'files': PINS, 'whole_process_fd_identities_unchanged': True, 'mode': 'verify-host-only',
        'Main_commands': 0, 'namespace_entries': 0, 'Main_locks_or_guards': 0,
        'private_bundle_copied': False, 'reconciliation_published': False}, sort_keys=True), flush=True)
    entry = ROOT / 'publish_owned_reconciliation.py'
    sys.argv = [str(entry), '--verify-host-only', '--source-sha256', ENTRY_SHA, '--request-sha256', REQUEST_SHA]
    exec(compile(bodies['publish_owned_reconciliation.py'], str(entry), 'exec'),
         {'__name__': '__main__', '__file__': str(entry)})


if __name__ == '__main__':
    main()
