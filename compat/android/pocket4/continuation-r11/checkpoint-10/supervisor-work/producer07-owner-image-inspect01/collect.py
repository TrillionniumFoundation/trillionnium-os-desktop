#!/usr/bin/env python3
"""Observe one pinned-image header and root-owned filesystem tool help only."""
import errno
import hashlib
import json
import os
from pathlib import PurePosixPath
import stat
import subprocess
import sys
import traceback

IMAGE = {'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/images/system.img',
         'bytes': 742322176, 'sha256': '358a7f008bbfbcd09fb9655d4ed1ff5f07071f89349735aabf7dd381d738b2cf'}
TOOLS = (('/usr/bin/fsck.erofs', '--help'), ('/usr/sbin/fsck.erofs', '--help'),
         ('/usr/sbin/debugfs', '-V'))


def need(value, message):
    if not value:
        raise RuntimeError(message)


def stamp(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def open_plain(path):
    parts = PurePosixPath(path).parts
    need(parts[0] == '/' and all(x not in ('', '.', '..') for x in parts[1:]), 'bad fixed path')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
            st = os.fstat(parent)
            need(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022, 'unsafe fixed parent')
        return os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)


def identity(st):
    return dict(device=st.st_dev, inode=st.st_ino, bytes=st.st_size,
                mode=stat.S_IMODE(st.st_mode), uid=st.st_uid, gid=st.st_gid,
                mtime_ns=st.st_mtime_ns, ctime_ns=st.st_ctime_ns)


def image_header():
    fd = open_plain(IMAGE['path'])
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0 and
             stat.S_IMODE(before.st_mode) == 0o444 and before.st_size == IMAGE['bytes'], 'image metadata differs')
        raw = os.pread(fd, 4096, 0)
        need(len(raw) == 4096 and stamp(os.fstat(fd)) == stamp(before), 'image header short or changed')
        kind = ('erofs' if raw[1024:1028] == bytes.fromhex('e2e1f5e0') else
                'ext4' if raw[1080:1082] == bytes.fromhex('53ef') else 'UNKNOWN')
        return {'expected': IMAGE, 'observed': identity(before), 'first_4096_sha256': hashlib.sha256(raw).hexdigest(),
                'first_16_hex': raw[:16].hex(), 'superblock_magic_hex': raw[1024:1028].hex(),
                'ext4_magic_hex': raw[1080:1082].hex(), 'filesystem_hint': kind,
                'full_image_digest_verified': False, 'image_written_or_mounted': False}
    finally:
        os.close(fd)


def tool_help(path, option):
    try:
        fd = open_plain(path)
    except FileNotFoundError:
        return {'path': path, 'present': False, 'executed': False}
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == before.st_gid == 0 and
             not before.st_mode & 0o6022 and before.st_mode & 0o111 and
             0 < before.st_size <= 4 * 1024 * 1024, 'unsafe tool type/owner/mode/size')
        try:
            caps = os.getxattr(fd, 'security.capability')
        except OSError as error:
            need(error.errno in (errno.ENODATA, errno.EOPNOTSUPP), 'cannot establish tool capabilities')
            caps = b''
        need(not caps and os.pread(fd, 4, 0) == b'\x7fELF', 'tool is privileged or not native ELF')
        digest = hashlib.sha256()
        offset = 0
        while offset < before.st_size:
            data = os.pread(fd, min(65536, before.st_size - offset), offset)
            need(bool(data), 'short held tool')
            digest.update(data)
            offset += len(data)
        need(stamp(os.fstat(fd)) == stamp(before), 'tool changed during hash')
        result = {'path': path, 'present': True, 'identity': identity(before), 'sha256': digest.hexdigest(),
                  'file_capabilities': None, 'argv': [path, option], 'executed': False}
        command = subprocess.run(['/proc/self/fd/' + str(fd), option], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(fd,), close_fds=True,
            cwd='/', env={'LC_ALL': 'C', 'PATH': '/usr/bin:/usr/sbin'}, timeout=3)
        result.update(executed=True, returncode=command.returncode, child_reaped=True,
                      stdout=command.stdout.decode('utf-8', 'strict'), stderr=command.stderr.decode('utf-8', 'strict'))
        need(len(command.stdout) + len(command.stderr) <= 32768, 'tool help output exceeded bound')
        need(stamp(os.fstat(fd)) == stamp(before), 'tool changed during help')
        result['held_identity_unchanged'] = True
        return result
    finally:
        os.close(fd)


def main():
    report = {'schema': 1, 'kind': 'producer07-image-preimage-readonly-inspect01', 'success': False,
              'qualification': False, 'extract_or_mount_performed': False,
              'namespaces_or_network_changed': False, 'files_written': False, 'tools': []}
    code = 1
    try:
        report['image'] = image_header()
        for path, option in TOOLS:
            report['tools'].append(tool_help(path, option))
        report['success'] = True
        code = 0
    except BaseException as error:
        report.update(error=repr(error), traceback=traceback.format_exc())
    encoded = json.dumps(report, sort_keys=True, ensure_ascii=False) + '\n'
    need(len(encoded.encode('utf-8')) <= 128 * 1024, 'report exceeded bound')
    sys.stdout.write(encoded)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
