#!/usr/bin/env python3
"""Local owned-file controls; never call collect or touch Main/device paths."""
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE_SHA = 'c98c6031edf12b7984c06553e429afcb4430f6e2dce7a10b143691b39a8a8368'
raw = (HERE/'probe_lock.py').read_bytes()
assert len(raw) == 16466 and hashlib.sha256(raw).hexdigest() == SOURCE_SHA
spec = importlib.util.spec_from_file_location('local_once_lock_controls', HERE/'probe_lock.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert os.getuid() == os.geteuid() == os.getgid() == 0
real_flock, real_close = fcntl.flock, os.close


class Support:
    @staticmethod
    def check_time(deadline):
        assert time.monotonic() < deadline

    @staticmethod
    def metadata(fd):
        s = os.fstat(fd)
        return dict(device=s.st_dev, inode=s.st_ino, mode=s.st_mode, uid=s.st_uid,
                    gid=s.st_gid, nlink=s.st_nlink, size=s.st_size,
                    mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)


def observation():
    return dict(opened_existing=False, exclusive_calls=0, exclusive_errno=None,
                acquired=False, unlock_calls=0, unlock_errno=None, unlocked=False,
                close_attempted=False, close_confirmed=False)


results = []
with tempfile.TemporaryDirectory(prefix='lock-once-local-') as directory:
    path = Path(directory)/'owned.lock'
    path.write_bytes(b'')
    path.chmod(0o600)
    st = path.stat()
    assert stat.S_ISREG(st.st_mode) and st.st_nlink == 1
    module.LOCK, module.LOCK_DEV, module.LOCK_INO = str(path), st.st_dev, st.st_ino

    def run(label, *, busy=False, other_error=False, unlock_error=False,
            wrong_inode=False, close_error_after_busy=False):
        holder = None
        if busy:
            holder = os.open(path, os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
            real_flock(holder, fcntl.LOCK_EX|fcntl.LOCK_NB)
        fds = module.OwnedFDs()
        anchor = fds.take(os.open(path, os.O_PATH|os.O_CLOEXEC|os.O_NOFOLLOW))
        before = Support.metadata(anchor)
        seen = []
        rw = None
        close_fault_done = False
        value = observation()
        error = None
        old_inode = module.LOCK_INO
        if wrong_inode:
            module.LOCK_INO += 1

        def call(fd, flags):
            nonlocal rw
            seen.append(flags)
            rw = fd
            if other_error:
                raise OSError(errno.EPERM, 'local injected non-busy errno')
            if unlock_error and flags == fcntl.LOCK_UN:
                raise OSError(errno.EIO, 'local injected unlock failure')
            return real_flock(fd, flags)

        def close(fd):
            nonlocal close_fault_done
            real_close(fd)
            if close_error_after_busy and fd == rw and not close_fault_done:
                close_fault_done = True
                raise OSError(errno.EIO, 'local close completed then diagnostic failure')

        try:
            with mock.patch.object(module.fcntl, 'flock', call), mock.patch.object(module.os, 'close', close):
                try:
                    module.admit_once(fds, Support, anchor, before, value, time.monotonic()+2.0)
                except Exception as actual:
                    error = actual
            assert value['close_attempted']
            assert rw is None or rw not in fds.values
            assert fds.values == [anchor]
            if wrong_inode:
                assert isinstance(error, RuntimeError) and not seen
                assert value['exclusive_calls'] == 0 and not value['acquired']
            elif busy:
                assert isinstance(error, BlockingIOError) and error.errno == errno.EAGAIN
                assert seen == [fcntl.LOCK_EX|fcntl.LOCK_NB]
                assert value['exclusive_calls'] == 1 and value['exclusive_errno'] == errno.EAGAIN
                assert not value['acquired'] and value['unlock_calls'] == 0
                if close_error_after_busy:
                    assert not value['close_confirmed'] and len(fds.close_errors) == 1
                    assert error.errno == errno.EAGAIN and error._lock_close_notes
                else:
                    assert value['close_confirmed'] and not fds.close_errors
            elif other_error:
                assert isinstance(error, OSError) and error.errno == errno.EPERM
                assert seen == [fcntl.LOCK_EX|fcntl.LOCK_NB]
                assert value['exclusive_errno'] == errno.EPERM and not value['acquired']
                assert value['unlock_calls'] == 0 and value['close_confirmed']
            elif unlock_error:
                assert isinstance(error, OSError) and error.errno == errno.EIO
                assert seen == [fcntl.LOCK_EX|fcntl.LOCK_NB, fcntl.LOCK_UN]
                assert value['acquired'] and not value['unlocked'] and value['unlock_errno'] == errno.EIO
                assert value['close_confirmed']
            else:
                assert error is None and value['acquired'] and value['unlocked'] and value['close_confirmed']
                assert seen == [fcntl.LOCK_EX|fcntl.LOCK_NB, fcntl.LOCK_UN]
                assert value['held_before'] == value['named_before'] == value['held_after_unlock'] == before

            # A distinct owned OFD independently checks whether this control's
            # holder remains or our admitted OFD has been released by UN/close.
            check = os.open(path, os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                if busy:
                    try:
                        real_flock(check, fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError as retained:
                        assert retained.errno == errno.EAGAIN
                    else:
                        raise AssertionError('busy fixture holder was modified')
                else:
                    real_flock(check, fcntl.LOCK_EX|fcntl.LOCK_NB)
                    real_flock(check, fcntl.LOCK_UN)
            finally:
                real_close(check)
            results.append(dict(name=label, passed=True, actual_calls=seen,
                                primary_errno=getattr(error, 'errno', None),
                                close_errors=len(fds.close_errors)))
        finally:
            module.LOCK_INO = old_inode
            fds.finish()
            assert not fds.values
            if holder is not None:
                real_flock(holder, fcntl.LOCK_UN)
                real_close(holder)

    run('free_actual_once_unlock_close')
    run('busy_actual_once_no_unlock_or_retry', busy=True)
    run('non_EAGAIN_is_preserved_without_retry', other_error=True)
    run('exact_identity_rejected_before_flock', wrong_inode=True)
    run('unlock_failure_preserved_owned_close_releases', unlock_error=True)
    run('busy_first_error_survives_close_diagnostic', busy=True, close_error_after_busy=True)

print(json.dumps(dict(schema=1, scope='local owned temporary file plus explicit syscall failure seams',
    source_sha256=SOURCE_SHA, controls=results, passed=len(results),
    collect_called=False, Main_paths_read=False, Hepta_calls=0,
    device_lock_or_Android_qualification=False), sort_keys=True, indent=2))
