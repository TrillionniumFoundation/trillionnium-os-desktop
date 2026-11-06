"""Fixed single-report root read; no child, write, scan, chmod or runtime action."""
import hashlib
import json
import os
import stat
import sys
import traceback

ROOT_NAME = 'p4-owner20-normal-20261106-02-state'
EXPECTED_REPORT_BYTES = 817470
EXPECTED_REPORT_SHA256 = '7f91108de0fbec45051dae9cb8ca8e43e6bb99986915d51f74bd2d4f6dfc843e'
NAMES = ('runtime-result.json',)
LIMIT = 5 * 1024 * 1024
ENVELOPE_LIMIT = 2 * LIMIT + 65536
WIRE_LIMIT = ENVELOPE_LIMIT + 65536


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def stamp(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns, value.st_mode, value.st_uid, value.st_gid, value.st_nlink]


def directory(name, parent=None):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                 **({} if parent is None else {'dir_fd': parent}))
    try:
        value = os.fstat(fd)
        need(stat.S_ISDIR(value.st_mode) and value.st_uid == 0 and value.st_gid == 0 and
             not value.st_mode & 0o22, 'protected directory ownership/mode differs')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_member(root, name):
    need(name in NAMES, 'outside fixed file allowlist')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_gid == 0 and
             before.st_nlink == 1 and not before.st_mode & 0o6022 and before.st_size <= LIMIT,
             'member type/ownership/mode/bound differs')
        data = bytearray()
        while True:
            chunk = os.read(fd, min(32768, LIMIT + 1 - len(data)))
            if not chunk:
                break
            data += chunk
            need(len(data) <= LIMIT, 'member grew past bound')
        after = os.fstat(fd)
        named = os.stat(name, dir_fd=root, follow_symlinks=False)
        need(stamp(before) == stamp(after) == stamp(named) and len(data) == after.st_size,
             'member changed while held')
        body = bytes(data)
        need(body.isascii(), 'fixed original JSON writer ASCII encoding differs')
        result = {'path': '/opt/' + ROOT_NAME + '/' + name, 'bytes': len(body),
                  'sha256': hashlib.sha256(body).hexdigest(), 'identity': stamp(after),
                  'content': body.decode('utf-8')}
        if name == 'runtime-result.json':
            need(result['bytes'] == EXPECTED_REPORT_BYTES and result['sha256'] == EXPECTED_REPORT_SHA256,
                 'externally pinned actual runtime report differs')
        return result
    finally:
        os.close(fd)


def main():
    result = {'schema': 1, 'kind': 'fixed-owner20-normal02-runtime-plain-read', 'collection_complete': False,
              'files': {}, 'errors': [], 'mutations': False, 'qualification': False}
    fds = []
    try:
        need(type(EXPECTED_REPORT_BYTES) is int and 0 < EXPECTED_REPORT_BYTES <= LIMIT and
             isinstance(EXPECTED_REPORT_SHA256, str) and len(EXPECTED_REPORT_SHA256) == 64 and
             all(c in '0123456789abcdef' for c in EXPECTED_REPORT_SHA256),
             'external actual report size and full SHA are required before opening any path')
        need(os.geteuid() == 0 and os.getegid() == 0, 'root read required')
        slash = directory('/'); fds.append(slash)
        opt = directory('opt', slash); fds.append(opt)
        root = directory(ROOT_NAME, opt); fds.append(root)
        identity = stamp(os.fstat(root))
        result['root_identity'] = identity
        for name in NAMES:
            result['files'][name] = read_member(root, name)
        need(sum(item['bytes'] for item in result['files'].values()) <= LIMIT,
             'aggregate member bound exceeded')
        need(stamp(os.fstat(root)) == identity and stamp(os.stat(ROOT_NAME, dir_fd=opt, follow_symlinks=False)) == identity,
             'held runtime directory changed')
        need(read_member(root, 'runtime-result.json') == result['files']['runtime-result.json'],
             'original report changed at end')
        result['collection_complete'] = True
    except BaseException as error:
        result['errors'].append({'error': repr(error), 'traceback': traceback.format_exc()})
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError as error:
                result['errors'].append({'close_error': repr(error)})
    result['collection_complete'] = result['collection_complete'] and not result['errors']
    raw = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode()
    need(len(raw) <= ENVELOPE_LIMIT, 'read envelope exceeds bound')
    need(len(raw) <= WIRE_LIMIT, 'plain wire envelope exceeds bound')
    need(sys.stdout.buffer.write(raw) == len(raw), 'plain envelope write was incomplete')
    sys.stdout.buffer.flush()
    return 0 if result['collection_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
