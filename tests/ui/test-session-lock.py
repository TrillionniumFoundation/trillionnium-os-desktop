#!/usr/bin/env python3
"""Linux host-only flock / O_NOFOLLOW syscall gate, NOT a Rust binary test.

Spawns only temporary Python child processes owned by this test. The lock
protocol mirrors the A10 Session's Linux flock(LOCK_EX | LOCK_NB) contract.
"""
import errno
import fcntl
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile

OPEN_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
CHILD_CODE = r'''
import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(23)
print('LOCKED', flush=True)
if len(sys.argv) >= 3 and sys.argv[2] == 'hold':
    time.sleep(30)
os.close(fd)
'''


def attempt(lock_path, *, hold=False):
    args = [sys.executable, '-c', CHILD_CODE, str(lock_path)]
    if hold:
        args.append('hold')
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(args, capture_output=True, text=True, timeout=3)


def main():
    with tempfile.TemporaryDirectory(prefix='a10-flock-') as root:
        runtime = Path(root)
        os.chmod(runtime, 0o700)
        path = runtime / 'session.lock'
        fd = os.open(path, OPEN_FLAGS, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            second = attempt(path)
            assert second.returncode == 23, f'live owner was not exclusive: {second}'
        finally:
            os.close(fd)
        after_release = attempt(path)
        assert after_release.returncode == 0, f'released lock was not reusable: {after_release}'

        crashed_owner = attempt(path, hold=True)
        try:
            selector = selectors.DefaultSelector()
            try:
                selector.register(crashed_owner.stdout, selectors.EVENT_READ)
                assert selector.select(timeout=3), 'holder never reached kernel lock'
                assert crashed_owner.stdout.readline().strip() == 'LOCKED'
            finally:
                selector.close()
            denied = attempt(path)
            assert denied.returncode == 23, f'competing owner bypassed held flock: {denied}'
        finally:
            crashed_owner.kill()
            crashed_owner.communicate(timeout=3)
        post_crash = attempt(path)
        assert post_crash.returncode == 0, f'flock persisted after owner SIGKILL: {post_crash}'

        protected = runtime / 'protected.txt'
        protected.write_bytes(b'unchanged')
        malicious_link = runtime / 'redirect.lock'
        malicious_link.symlink_to(protected)
        try:
            opened = os.open(malicious_link, OPEN_FLAGS, 0o600)
        except OSError as e:
            assert e.errno == errno.ELOOP, f'wrong symlink rejection error: {e}'
        else:
            os.close(opened)
            raise AssertionError('O_NOFOLLOW followed an existing symlink')
        assert protected.read_bytes() == b'unchanged'
        assert path.stat().st_mode & 0o777 == 0o600
    print('A10 host flock: PASS (exclusive, crash-released, symlink refused)')


if __name__ == '__main__':
    main()
