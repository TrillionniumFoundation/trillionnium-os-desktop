#!/usr/bin/env python3
"""Exercise the production Stage using only real, fresh host fixture files.

The bounded Target maps its two permitted APIs to one new temporary host
directory. It does not supply a fake stat, open /data, import the transport,
enter a namespace, run an Android command, or create an actual APK install.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import types
from unittest.mock import patch


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


class HostFileTarget:
    def __init__(self, directory, fail_readback=False):
        self.directory = Path(directory)
        self.fail_readback = fail_readback
        self.calls = []

    def open_root(self, path, flags):
        need(path == '/data/local/tmp' and flags == os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
             'ONLY_FIXTURE_PARENT_OPEN_ALLOWED')
        self.calls.append('open_fixture_parent')
        return os.open(self.directory, flags | os.O_CLOEXEC)

    def read_file(self, path, maximum, single_link):
        prefix = '/data/local/tmp/'
        need(path.startswith(prefix) and single_link is True, 'ONLY_OWNED_FIXTURE_READ_ALLOWED')
        relative = Path(path[len(prefix):])
        need(len(relative.parts) == 2 and relative.parts[0].startswith('pocket4-successor-owned-qa-') and
             relative.parts[1] == 'owned-qa.apk' and not any(x in ('', '.', '..') for x in relative.parts),
             'CLOSED_FIXTURE_PATH')
        self.calls.append('read_real_fixture_file')
        pfd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        dfd = fd = None
        try:
            dfd = os.open(relative.parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=pfd)
            fd = os.open(relative.parts[1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=dfd)
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= maximum, 'REAL_FIXTURE_FILE_SHAPE')
            data = os.read(fd, maximum + 1)
            need(len(data) == info.st_size and os.read(fd, 1) == b'', 'REAL_FIXTURE_READ_BOUND')
            if self.fail_readback:
                raise OSError(errno.EIO, 'explicit host-fixture readback failure')
            return data, {'device':info.st_dev,'inode':info.st_ino,'bytes':info.st_size}
        finally:
            for selected in (fd, dfd, pfd):
                if selected is not None:
                    os.close(selected)


def closed(fds):
    for fd in fds:
        try:
            os.fstat(fd)
        except OSError as error:
            need(error.errno == errno.EBADF, 'WRONG_FD_CLOSE_ERROR')
        else:
            raise RuntimeError('STAGE_FD_STILL_OPEN')


def run(template, expected, directory, require_root_positive=False):
    raw = Path(template).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected, 'EXACT_PRODUCTION_STAGE_TEMPLATE')
    text = raw.decode().replace('__HELPER_PACKAGE_LITERAL__',repr('org.example.hoststagefixture'))
    text = text.replace('__RECORDER_MANIFEST_LITERAL__',repr('0'*64))
    m = types.ModuleType('actual_stage_class_host_file_controls')
    m.__file__ = str(template)
    exec(compile(text,str(template),'exec'),m.__dict__)
    caller = os.geteuid()
    need(not require_root_positive or caller == 0, 'ACTUAL_ROOT_POSITIVE_CONTROL_REQUIRES_ROOT')
    data = b'Host-only production Stage fixture; never an Android APK.\n' * 64
    digest = hashlib.sha256(data).hexdigest()
    rows = []
    initial_fd_count = len(os.listdir('/proc/self/fd'))
    with tempfile.TemporaryDirectory(prefix='host-stage-controls-',dir=directory) as root:
        root = Path(root)
        success = root/'complete'
        success.mkdir(mode=0o700)
        target = HostFileTarget(success)
        stage = m.Stage(target,'1'*32)
        try:
            if caller == 0:
                stage.stage(data,digest)
                need(stage.record['sha256'] == digest and stage.record['bytes'] == len(data), 'ACTUAL_STAGE_RECORD')
                name = success/stage.name/'owned-qa.apk'
                info = name.stat()
                need(name.read_bytes() == data and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o444,
                     'REAL_ROOT_OWNED_STAGE_BYTES')
                rows.append({'name':'root_positive_real_write_readback','passed':True,'skipped':False})
            else:
                try:
                    stage.stage(data,digest)
                except RuntimeError as error:
                    need(str(error) == 'OWNED_GUEST_APK_IDENTITY', 'NONROOT_MUST_REACH_REAL_OWNER_REJECTION')
                else:
                    raise RuntimeError('NONROOT_FILE_WAS_ACCEPTED_AS_ROOT')
                rows.append({'name':'nonroot_real_owner_rejected','passed':True,'skipped':False})
                rows.append({'name':'root_positive_real_write_readback','passed':False,'skipped':True,
                             'reason':'actual caller UID is not root; no stat or UID substitution'})
        finally:
            held = list(stage.fds)
            stage.close()
            closed(held)
        need(len(held) == 3 and stage.fds == [] and target.calls == ['open_fixture_parent','read_real_fixture_file'],
             'COMPLETE_STAGE_FD_OR_IO_CONTRACT')
        rows.append({'name':'complete_or_owner_rejected_stage_all_three_fds_closed','passed':True,'skipped':False})
        for failure in ('partial_write','readback'):
            location = root/failure
            location.mkdir(mode=0o700)
            stage = m.Stage(HostFileTarget(location,fail_readback=failure=='readback'),'2'*32)
            original_write = os.write
            writes = [0]
            def failed_write(fd,value):
                writes[0] += 1
                if writes[0] == 1:
                    return original_write(fd,value[:7])
                raise OSError(errno.ENOSPC,'explicit host-fixture mid-write failure')
            try:
                try:
                    if failure == 'partial_write':
                        with patch.object(m.os,'write',failed_write):
                            stage.stage(data,digest)
                    else:
                        stage.stage(data,digest)
                except OSError as error:
                    need(error.errno == (errno.ENOSPC if failure=='partial_write' else errno.EIO), 'REAL_FAILURE_NOT_OBSERVED')
                else:
                    raise RuntimeError('INJECTED_FAILURE_NOT_OBSERVED')
            finally:
                held = list(stage.fds)
                stage.close()
                closed(held)
            need(len(held) == 3 and stage.fds == [],'FAILED_STAGE_FDS_NOT_CLOSED')
            content = (location/stage.name/'owned-qa.apk').read_bytes()
            need(content == (data[:7] if failure=='partial_write' else data),'ACTUAL_FAILED_WRITE_CONTENT_DIFFERS')
            rows.append({'name':failure+'_real_files_all_three_fds_closed','passed':True,'skipped':False})
    need(len(os.listdir('/proc/self/fd')) == initial_fd_count,'CONTROL_PROCESS_FD_LEAK')
    return {'schema':'pocket4-production-Stage-host-file-controls-v1','caller_uid':caller,
        'production_template_sha256':expected,'cases':rows,
        'all_required_passed':all(r['passed'] for r in rows if not r['skipped']),
        'root_positive_completed':caller==0,'total_fd_count_unchanged':True,
        'actual_android_paths_opened':0,'Android_commands':0,'namespace_entries':0,'helper_installs':0,
        'generated_successor_bindings':0,'production_ready':False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--template',required=True)
    p.add_argument('--template-sha256',required=True)
    p.add_argument('--temporary-parent',required=True)
    p.add_argument('--require-root-positive',action='store_true')
    a = p.parse_args()
    result = run(a.template,a.template_sha256,a.temporary_parent,a.require_root_positive)
    print(json.dumps(result,sort_keys=True,ensure_ascii=True),flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
