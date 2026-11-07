#!/usr/bin/env python3
"""Extract exactly one original RC through held, pinned, read-only image/tool FDs."""
import errno
import hashlib
import json
import os
from pathlib import PurePosixPath
import resource
import stat
import subprocess
import sys
import time
import traceback

ROOT = '/home/alex/pocket4-owner07-original-lmkd-rc-read-02'
INODE_PATH = '/system/etc/init/lmkd.rc'
OUTPUT = 'original-lmkd.rc'
INSPECTOR_RECEIPT = {'bytes': 3887, 'sha256': '04b8c44dce6b42cb3d9a9675db037bdf0ef7d2e37d5289a1c6cbb8ce98843599'}
IMAGE = {'path': '/opt/p4-media-composer-diagnostic-20261102-chat2-r5/images/system.img',
         'bytes': 742322176, 'sha256': '358a7f008bbfbcd09fb9655d4ed1ff5f07071f89349735aabf7dd381d738b2cf',
         'device': 66306, 'inode': 39237163, 'mode': 0o444, 'uid': 0, 'gid': 0,
         'mtime_ns': 1793634278483432061, 'ctime_ns': 1793634278483432061}
TOOL = {'path': '/usr/bin/fsck.erofs', 'bytes': 101520,
        'sha256': '8bc2596495e8d832cd94008aed4b301b1ec3fe512e430b39e608d5122a609d20',
        'device': 66306, 'inode': 108010838, 'mode': 0o755, 'uid': 0, 'gid': 0,
        'mtime_ns': 1772553600000000000, 'ctime_ns': 1792397752047022011}
FILE_LIMIT = 65536
REPORT_LIMIT = 256 * 1024
CHILD_SECONDS = 10
WORK_SECONDS = 75


def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(st):
    return dict(device=st.st_dev, inode=st.st_ino, bytes=st.st_size,
                mode=stat.S_IMODE(st.st_mode), uid=st.st_uid, gid=st.st_gid,
                mtime_ns=st.st_mtime_ns, ctime_ns=st.st_ctime_ns)


def stamp(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def open_directory(path, owners):
    parts = PurePosixPath(path).parts
    need(parts and parts[0] == '/' and all(x not in ('', '.', '..') for x in parts[1:]), 'bad absolute path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        for part in parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            st = os.fstat(fd)
            need(stat.S_ISDIR(st.st_mode) and st.st_uid in owners and not st.st_mode & 0o022,
                 'unsafe parent directory')
        answer, fd = fd, -1
        return answer
    finally:
        if fd >= 0:
            os.close(fd)


def open_fixed(expected):
    p = PurePosixPath(expected['path'])
    parent = open_directory(str(p.parent), {0})
    try:
        fd = os.open(p.name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        st = os.fstat(fd)
        need(stat.S_ISREG(st.st_mode), 'fixed input is not a regular file')
        need(identity(st) == {k: expected[k] for k in identity(st)}, 'fixed input metadata no longer matches inspector')
        return fd, st
    except BaseException:
        os.close(fd)
        raise


def full_digest(fd, before, deadline):
    h = hashlib.sha256()
    offset = 0
    while offset < before.st_size:
        need(time.monotonic() < deadline, 'whole-file hash exceeded controller deadline')
        data = os.pread(fd, min(1024 * 1024, before.st_size - offset), offset)
        need(bool(data), 'short fixed input')
        h.update(data)
        offset += len(data)
    need(os.pread(fd, 1, offset) == b'' and stamp(os.fstat(fd)) == stamp(before), 'fixed input changed while hashing')
    return h.hexdigest()


def verify_held_and_named(expected, fd, before, deadline):
    digest = full_digest(fd, before, deadline)
    need(digest == expected['sha256'], 'fixed input SHA-256 mismatch')
    named, named_st = open_fixed(expected)
    try:
        need(stamp(named_st) == stamp(before), 'named input differs from held input')
    finally:
        os.close(named)
    return {'sha256': digest, 'bytes': before.st_size, 'held_and_named_unchanged': True}


def make_fresh_root():
    p = PurePosixPath(ROOT)
    parent = open_directory(str(p.parent), {0, os.geteuid()})
    try:
        os.mkdir(p.name, mode=0o700, dir_fd=parent)
        fd = os.open(p.name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
        try:
            st = os.fstat(fd)
            need(st.st_uid == os.geteuid() and stat.S_IMODE(st.st_mode) == 0o700, 'fresh output root has wrong owner/mode')
            need(os.listdir(fd) == [], 'fresh output root is not empty')
            return fd, (st.st_dev, st.st_ino)
        except BaseException:
            os.close(fd)
            raise
    finally:
        os.close(parent)


def open_new(root_fd, name):
    need('/' not in name and name not in ('', '.', '..'), 'invalid output leaf')
    return os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                   0o600, dir_fd=root_fd)


def write_new(root_fd, name, data):
    fd = open_new(root_fd, name)
    try:
        offset = 0
        while offset < len(data):
            n = os.write(fd, data[offset:])
            need(n > 0, 'short output write')
            offset += n
        os.fsync(fd)
    finally:
        os.close(fd)


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')


def read_small(root_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
    try:
        st = os.fstat(fd)
        need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.geteuid() and
             not st.st_mode & 0o6022 and 0 <= st.st_size <= FILE_LIMIT, 'unsafe or excessive extracted output')
        raw = os.pread(fd, FILE_LIMIT + 1, 0)
        need(len(raw) == st.st_size and stamp(os.fstat(fd)) == stamp(st), 'output changed while reading')
        return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'identity': identity(st), 'content': raw.decode('utf-8', 'strict')}
    finally:
        os.close(fd)


def child_limits():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_LIMIT, FILE_LIMIT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def extraction_argv(tool_fd, image_fd, root_fd):
    return ['/proc/self/fd/' + str(tool_fd), '--path=' + INODE_PATH,
            '--extract=/proc/self/fd/' + str(root_fd) + '/' + OUTPUT,
            '--no-preserve-owner', '--no-preserve-perms', '--no-xattrs',
            '/proc/self/fd/' + str(image_fd)]


def record_error(report, stage, error):
    entry = {'stage': stage, 'error': repr(error), 'traceback': traceback.format_exc()}
    report['errors'].append(entry)
    if 'first_error' not in report:
        report['first_error'] = entry


def main():
    report = {'schema': 1, 'kind': 'producer07-original-lmkd-rc-single-inode-extract02',
              'success': False, 'qualification': False, 'semantic_rc_admission': False,
              'owner_or_android_executed': False, 'namespaces_or_network_changed': False,
              'image_mounted_or_written': False, 'system_service_changed': False,
              'output_root': ROOT, 'image_inode_path': INODE_PATH,
              'inspector_receipt': INSPECTOR_RECEIPT, 'image_expected': IMAGE, 'tool_expected': TOOL,
              'request_limits': {'cpu_quota_percent': 100, 'memory_max_bytes': 536870912,
                                 'nice': 10, 'timeout_seconds': 90},
              'child_reaped': False, 'errors': []}
    root_fd = image_fd = tool_fd = stdout_fd = stderr_fd = -1
    image_st = tool_st = None
    root_identity = None
    child = None
    deadline = time.monotonic() + WORK_SECONDS
    try:
        need(os.getuid() == os.geteuid() != 0 and os.getgid() == os.getegid(), 'ordinary unprivileged caller required')
        os.umask(0o077)
        root_fd, root_identity = make_fresh_root()
        write_new(root_fd, 'claim.json', encode({'kind': report['kind'], 'pid': os.getpid(),
            'image': IMAGE, 'tool': TOOL, 'inspector_receipt': INSPECTOR_RECEIPT,
            'root_device_inode': root_identity, 'inode_path': INODE_PATH, 'replay_allowed': False}))
        image_fd, image_st = open_fixed(IMAGE)
        tool_fd, tool_st = open_fixed(TOOL)
        need(os.pread(image_fd, 4, 1024) == bytes.fromhex('e2e1f5e0'), 'fixed image is no longer EROFS')
        need(os.pread(tool_fd, 4, 0) == b'\x7fELF', 'fixed tool is not native ELF')
        try:
            caps = os.getxattr(tool_fd, 'security.capability')
        except OSError as error:
            need(error.errno in (errno.ENODATA, errno.EOPNOTSUPP), 'cannot establish tool capabilities')
            caps = b''
        need(not caps, 'fixed tool has file capabilities')
        report['image_before'] = verify_held_and_named(IMAGE, image_fd, image_st, deadline)
        report['tool_before'] = verify_held_and_named(TOOL, tool_fd, tool_st, deadline)
        need(set(os.listdir(root_fd)) == {'claim.json'}, 'output root changed before extraction')
        stdout_fd = open_new(root_fd, 'tool.stdout')
        stderr_fd = open_new(root_fd, 'tool.stderr')
        argv = extraction_argv(tool_fd, image_fd, root_fd)
        report['command'] = {'argv': argv, 'pass_fds': [tool_fd, image_fd, root_fd],
                             'timeout_seconds': CHILD_SECONDS, 'file_bytes_limit': FILE_LIMIT,
                             'started_monotonic_ns': time.monotonic_ns()}
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout_fd, stderr=stderr_fd,
            close_fds=True, pass_fds=(tool_fd, image_fd, root_fd), cwd='/',
            env={'LC_ALL': 'C', 'PATH': '/usr/bin:/usr/sbin'}, preexec_fn=child_limits)
        report['command']['pid'] = child.pid
        report['command']['returncode'] = child.wait(timeout=CHILD_SECONDS)
        report['command']['finished_monotonic_ns'] = time.monotonic_ns()
        report['child_reaped'] = True
        need(child.returncode == 0, 'single-inode extractor returned nonzero')
        report['original_lmkd_rc'] = read_small(root_fd, OUTPUT)
        need(report['original_lmkd_rc']['bytes'] > 0, 'extracted RC is empty')
        need(set(os.listdir(root_fd)) == {'claim.json', 'tool.stdout', 'tool.stderr', OUTPUT},
             'extractor produced unexpected output paths')
    except BaseException as error:
        record_error(report, 'extract', error)
    finally:
        if child is not None and child.returncode is None:
            try:
                child.kill()
                child.wait(timeout=3)
                report['child_reaped'] = True
                report['command']['returncode'] = child.returncode
                report['command']['cleanup_exact_child_killed'] = True
            except BaseException as error:
                record_error(report, 'exact_child_cleanup', error)
        for name, fd in (('tool.stdout', stdout_fd), ('tool.stderr', stderr_fd)):
            if fd >= 0:
                os.close(fd)
                try:
                    report[name] = read_small(root_fd, name)
                except BaseException as error:
                    record_error(report, 'read_' + name, error)
        for name, expected, fd, st in (('image_after', IMAGE, image_fd, image_st),
                                       ('tool_after', TOOL, tool_fd, tool_st)):
            if fd >= 0:
                try:
                    report[name] = verify_held_and_named(expected, fd, st, deadline)
                except BaseException as error:
                    record_error(report, name, error)
                finally:
                    os.close(fd)
        if root_fd >= 0:
            try:
                named = open_directory(ROOT, {0, os.geteuid()})
                try:
                    st = os.fstat(named)
                    need((st.st_dev, st.st_ino) == root_identity and os.fstat(root_fd).st_ino == st.st_ino,
                         'fresh output directory was replaced')
                finally:
                    os.close(named)
                report['root_identity_unchanged'] = True
            except BaseException as error:
                record_error(report, 'output_root_final', error)
        report['success'] = (not report['errors'] and report['child_reaped'] and
            all(key in report for key in ('original_lmkd_rc', 'image_before', 'image_after', 'tool_before', 'tool_after')))
        encoded = encode(report)
        if len(encoded) > REPORT_LIMIT:
            report['success'] = False
            report['first_error'] = report.get('first_error', {'stage': 'result', 'error': 'report size limit exceeded'})
            report['original_lmkd_rc'] = {'omitted': 'oversized report'}
            report.pop('tool.stdout', None)
            report.pop('tool.stderr', None)
            encoded = encode(report)
        if root_fd >= 0:
            try:
                write_new(root_fd, 'result.json', encoded)
                os.fsync(root_fd)
            except BaseException as error:
                record_error(report, 'persist_result', error)
                report['success'] = False
                encoded = encode(report)
            finally:
                os.close(root_fd)
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
