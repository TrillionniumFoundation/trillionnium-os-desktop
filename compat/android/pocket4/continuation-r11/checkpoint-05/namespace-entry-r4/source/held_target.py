# SPDX-License-Identifier: Apache-2.0
"""Held namespace/root binding for the existing owned Android runner."""
from pathlib import PurePosixPath
import fcntl
import hashlib
import os
import re
import select
import stat

KINDS = {'mnt': 0x00020000, 'pid': 0x20000000, 'uts': 0x04000000,
         'ipc': 0x08000000, 'net': 0x40000000, 'cgroup': 0x02000000}

class HeldTarget:
    def __init__(self, pid, expected, identity, helper_path, helper_sha256,
                 namespaces=('mnt', 'pid', 'uts', 'ipc')):
        self.fds = []
        self.closed = False
        self.pid = pid
        self.expected = expected
        self.identity = identity
        self.helper_path = str(helper_path)
        self.helper_sha256 = helper_sha256
        self.names = tuple(namespaces)
        if not self.names or len(set(self.names)) != len(self.names):
            raise RuntimeError('duplicate or empty namespace selection')
        if any(name not in KINDS for name in self.names):
            raise RuntimeError('unrecognized namespace')
        if not {'mnt', 'pid', 'uts', 'ipc'}.issubset(self.names):
            raise RuntimeError('missing required namespace authority')
        try:
            if identity(pid) != expected or expected['host_pid'] != pid:
                raise RuntimeError('process identity changed before binding')
            self.proc_fd = self._keep(os.open('/proc/' + str(pid),
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW))
            self.pid_fd = self._keep(os.pidfd_open(pid, 0))
            self.poller = select.poll()
            self.poller.register(self.pid_fd, select.POLLIN | select.POLLHUP | select.POLLERR)
            self.ns_fds = {}
            self.ns_identity = {}
            self.ns_labels = {}
            for name in self.names:
                fd = self._keep(os.open('ns/' + name, os.O_RDONLY | os.O_CLOEXEC,
                                        dir_fd=self.proc_fd))
                if fcntl.ioctl(fd, 0xb703) != KINDS[name]:
                    raise RuntimeError('namespace type mismatch')
                label = os.readlink('ns/' + name, dir_fd=self.proc_fd)
                match = re.fullmatch(re.escape(name) + r':\[(\d+)\]', label)
                if not match or os.fstat(fd).st_ino != int(match[1]):
                    raise RuntimeError('namespace label/descriptor mismatch')
                if name in expected['namespaces'] and expected['namespaces'][name] != label:
                    raise RuntimeError('namespace differs from qualified process')
                self.ns_fds[name] = fd
                self.ns_labels[name] = label
                self.ns_identity[name] = self._inode(fd)
            self.root_fd = self._keep(os.open('root', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC,
                                             dir_fd=self.proc_fd))
            self.root_identity = self._inode(self.root_fd)
            self.check()
        except BaseException:
            self.close()
            raise

    def _keep(self, fd):
        self.fds.append(fd)
        return fd

    @staticmethod
    def _inode(fd):
        value = os.fstat(fd)
        return [value.st_dev, value.st_ino]

    def _start_ticks(self):
        fd = os.open('stat', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=self.proc_fd)
        try:
            raw = os.read(fd, 4097)
            if len(raw) > 4096:
                raise RuntimeError('proc stat exceeds bound')
            end = raw.rfind(b')')
            if end < 0 or int(raw.split(b' ', 1)[0]) != self.pid:
                raise RuntimeError('anchored proc identity is malformed')
            fields = raw[end + 2:].split()
            return int(fields[19])
        finally:
            os.close(fd)

    def check(self):
        if self.closed or self.poller.poll(0):
            raise RuntimeError('held process exited or binding is closed')
        if self._start_ticks() != self.expected['start_ticks']:
            raise RuntimeError('anchored process start differs')
        if self.identity(self.pid) != self.expected:
            raise RuntimeError('current process identity differs')
        for name, held in self.ns_fds.items():
            if os.readlink('ns/' + name, dir_fd=self.proc_fd) != self.ns_labels[name]:
                raise RuntimeError('process namespace changed')
            current = os.open('ns/' + name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.proc_fd)
            try:
                if self._inode(current) != self.ns_identity[name] or self._inode(held) != self.ns_identity[name]:
                    raise RuntimeError('namespace descriptor identity changed')
            finally:
                os.close(current)
        current = os.open('root', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.proc_fd)
        try:
            if self._inode(current) != self.root_identity or self._inode(self.root_fd) != self.root_identity:
                raise RuntimeError('process root changed')
        finally:
            os.close(current)
        if self.poller.poll(0):
            raise RuntimeError('held process exited during binding check')

    def command_prefix(self):
        self.check()
        with open(self.helper_path, 'rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != self.helper_sha256:
                raise RuntimeError('namespace helper binary changed')
        return [self.helper_path, '--parent-pid=' + str(os.getpid()),
                '--root-fd=' + str(self.root_fd)] + [
                '--' + name + '-fd=' + str(self.ns_fds[name]) for name in self.names] + ['--']

    def pass_fds(self):
        return tuple(self.ns_fds.values()) + (self.root_fd,)

    def snapshot(self):
        self.check()
        return {'host_pid': self.pid, 'start_ticks': self.expected['start_ticks'],
                'namespaces': self.ns_labels, 'namespace_inode_pairs': self.ns_identity,
                'root_inode_pair': self.root_identity, 'numeric_pid_used_for_namespace_entry': False,
                'descriptor_authorities_cloexec_before_command': True,
                'helper_sha256': self.helper_sha256}

    def read_regular(self, absolute_path, limit=8 * 1024 * 1024):
        self.check()
        path = PurePosixPath(absolute_path)
        if not path.is_absolute() or '..' in path.parts or len(path.parts) < 2:
            raise RuntimeError('invalid rooted artifact path')
        parts = path.parts[1:]
        current = os.dup(self.root_fd)
        file_fd = None
        try:
            for component in parts[:-1]:
                next_fd = os.open(component, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC |
                                  os.O_NOFOLLOW, dir_fd=current)
                os.close(current)
                current = next_fd
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                              dir_fd=current)
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size < 0 or before.st_size > limit:
                raise RuntimeError('artifact is not a bounded regular file')
            chunks = []
            total = 0
            while True:
                chunk = os.read(file_fd, min(65536, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > limit:
                    raise RuntimeError('artifact grew beyond bound')
            after = os.fstat(file_fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                       after.st_mtime_ns, after.st_ctime_ns) or total != before.st_size:
                raise RuntimeError('artifact changed while held')
            self.check()
            return b''.join(chunks)
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(current)

    def close(self):
        if self.closed:
            return
        self.closed = True
        while self.fds:
            os.close(self.fds.pop())
