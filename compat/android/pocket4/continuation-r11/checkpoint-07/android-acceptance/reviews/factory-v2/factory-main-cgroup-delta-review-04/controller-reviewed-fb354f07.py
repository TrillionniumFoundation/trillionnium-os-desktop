#!/usr/bin/env python3
"""One-attempt owned host fixture. No default namespace or service action.

The factory and clients execute exact, sealed copies of the reviewed host ELFs.
All test actors live below a fresh PID-namespace init in a fresh network and
mount namespace. No Android entry, Main mutation, account, or ambient service.
"""
from __future__ import annotations

import argparse
import array
import ctypes
import errno
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import select
import signal
import socket
import stat
import struct
import sys
import time
import traceback
import types

BUILD = Path('/home/alex/work/pocket4-owned-factory-v2-host-build-01')
BUILD_SHA = 'adb1b0cb4bfa12d3d154c0538e931a7752046f8ab295e2bab77687615af6c81e'
AUDIT_SHA = 'bcef68b74b78a7b3e6b40354810fdf0a58c7ad3e5a89dde7f3487983cbf1ec3f'
ELFS = {
    'factory': ('factory-v2-host', '4be02a35826c0d5db7c8bee6ce60aebb0ec9c378ff2923785ee025ddb0eaf415', 134096),
    'client': ('factory-client-host', '2a3582edd0fbb1cec9cfb0d2dfdf602305d0c4a1e9b791682305fd66b7a6846c', 335168),
}
GUARD = Path('/home/alex/work/pocket4-framework-epoch-20261104-r10/framework_epoch.py')
GUARD_SHA = 'f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288'
ACTIVATION = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
MAIN_EPOCH = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
MAIN_INIT = 3588093
MAIN_CGROUP = Path('/sys/fs/cgroup/system.slice/droidloomd.service')
CELL_SHA = 'f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc'
ALLOW_UID, DENY_UID = 61171, 61172
CLONE_NEWNS, CLONE_NEWPID, CLONE_NEWNET = 0x00020000, 0x20000000, 0x40000000
NS_TYPES = {'pid': CLONE_NEWPID, 'mnt': CLONE_NEWNS, 'net': CLONE_NEWNET}
MS_REC, MS_PRIVATE = 16384, 1 << 18
PR_SET_PDEATHSIG = 1
SOCKET_NAME = b'\0droidloom.proc_maps.v2'
CLEAN_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
libc = ctypes.CDLL(None, use_errno=True)
libc.unshare.argtypes = [ctypes.c_int]
libc.setns.argtypes = [ctypes.c_int, ctypes.c_int]
libc.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_void_p]


def must(condition, message):
    if not condition:
        raise RuntimeError(message)


def checked(rc, operation):
    if rc != 0:
        raise OSError(ctypes.get_errno(), operation)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_pinned(path, expected, maximum=2 * 1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        must(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum, 'not bounded regular input')
        data = bytearray()
        while len(data) <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        after = os.fstat(fd)
        must((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'input changed during read')
        must(len(data) == before.st_size and sha(data) == expected, 'input pin mismatch: ' + str(path))
        return bytes(data)
    finally:
        os.close(fd)


def identity(fd):
    value = os.fstat(fd)
    return {'device': value.st_dev, 'inode': value.st_ino}


def ns_identity(path):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        return identity(fd)
    finally:
        os.close(fd)


def alive(pidfd):
    poller = select.poll()
    poller.register(pidfd, select.POLLIN)
    return not poller.poll(0)


def arm_parent(parent_pidfd):
    checked(libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0), 'PDEATHSIG')
    must(alive(parent_pidfd), 'actual parent already exited')


def close_except(keep):
    for entry in os.listdir('/proc/self/fd'):
        fd = int(entry)
        if fd not in keep:
            try:
                os.close(fd)
            except OSError as error:
                if error.errno != errno.EBADF:
                    raise


def fresh_proc():
    checked(libc.unshare(CLONE_NEWNS), 'unshare mount')
    checked(libc.mount(None, b'/', None, MS_PRIVATE | MS_REC, None), 'private mount propagation')
    checked(libc.mount(b'proc', b'/proc', b'proc', 2 | 4 | 8, None), 'fresh PID-namespace procfs')


def fd_table(pid):
    root = Path('/proc') / str(pid)
    result = {}
    for path in sorted((root / 'fd').iterdir(), key=lambda p: int(p.name)):
        fields = dict(line.split(':', 1) for line in (root / 'fdinfo' / path.name).read_text().splitlines() if ':' in line)
        result[path.name] = {'target': os.readlink(path),
                             **{k: fields[k].strip() for k in ('flags', 'mnt_id', 'ino', 'Pid', 'NSpid') if k in fields}}
    return result


def rights(ancillary):
    """Adopt every delivered fd before validating framing; caller closes all."""
    received, valid = [], True
    for level, kind, payload in ancillary:
        if level != socket.SOL_SOCKET or kind not in (socket.SCM_RIGHTS, 4):
            valid = False
            continue
        decoded = array.array('i')
        usable = len(payload) - len(payload) % decoded.itemsize
        decoded.frombytes(payload[:usable])
        received.extend(decoded)
        # Linux SCM_PIDFD (4) also installs an fd. Adopt it for closure, then
        # reject it; never interpret credentials or unknown payloads as fds.
        valid = valid and usable == len(payload) and kind == socket.SCM_RIGHTS
    return received, valid


def message_flags_valid(flags):
    # Linux returns this input flag in msg_flags. It is not truncation.
    return flags & ~socket.MSG_CMSG_CLOEXEC == 0


class Child:
    def __init__(self, pid, pidfd, stdout, stderr, label):
        self.pid, self.pidfd, self.stdout, self.stderr, self.label = pid, pidfd, stdout, stderr, label
        self.returncode = None
        self.result = None
        self.outputs = {stdout: bytearray(), stderr: bytearray()}
        self.hashes = {stdout: hashlib.sha256(), stderr: hashlib.sha256()}
        self.seen = {stdout: 0, stderr: 0}
        self.open_fds = {stdout, stderr}
        self.eof_fds = set()
        self.over_bound = set()
        self.join_errors = []
        self.forced_kill = False

    def observation(self):
        streams = {}
        for name, fd in (('stdout', self.stdout), ('stderr', self.stderr)):
            streams[name] = self.outputs[fd].decode('utf-8', 'replace')
            streams[name + '_observed_bytes'] = self.seen[fd]
            streams[name + '_observed_sha256'] = self.hashes[fd].hexdigest()
            streams[name + '_retained_bytes'] = len(self.outputs[fd])
            streams[name + '_truncated'] = fd in self.over_bound
            streams[name + '_eof'] = fd in self.eof_fds
        return {'label': self.label, 'pid_in_fixture': self.pid, 'returncode': self.returncode,
                'forced_kill': self.forced_kill, 'reaped': self.returncode is not None,
                'join_errors': list(self.join_errors), **streams}

    def join(self, seconds=6, kill_on_timeout=False):
        if self.result is not None:
            return self.result
        deadline = time.monotonic() + seconds
        timeout_kill_sent = False
        try:
            while self.returncode is None or self.open_fds:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if kill_on_timeout and self.returncode is None and not timeout_kill_sent:
                        signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
                        timeout_kill_sent = self.forced_kill = True
                        deadline = time.monotonic() + 2
                        continue
                    raise TimeoutError(self.label + ' wait/drain deadline')
                poller = select.poll()
                for fd in self.open_fds:
                    poller.register(fd, select.POLLIN | select.POLLHUP)
                if self.returncode is None:
                    poller.register(self.pidfd, select.POLLIN)
                for fd, event in poller.poll(min(100, max(1, int(remaining * 1000)))):
                    if fd == self.pidfd:
                        waited, status = os.waitpid(self.pid, 0)
                        must(waited == self.pid, 'wrong child reaped')
                        self.returncode = os.waitstatus_to_exitcode(status)
                    elif fd in self.open_fds:
                        block = os.read(fd, 8192)
                        if block:
                            self.hashes[fd].update(block)
                            self.seen[fd] += len(block)
                            self.outputs[fd].extend(block[:max(0, 65536 - len(self.outputs[fd]))])
                            if self.seen[fd] > 65536 and fd not in self.over_bound:
                                self.over_bound.add(fd)
                                raise RuntimeError('owned child output exceeded bound')
                        else:
                            os.close(fd)
                            self.open_fds.remove(fd)
                            self.eof_fds.add(fd)
            self.result = self.observation()
            return self.result
        except BaseException as error:
            self.join_errors.append({'type': type(error).__name__, 'message': str(error)})
            raise

    def retire(self):
        if self.returncode is None and alive(self.pidfd):
            signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
            self.forced_kill = True
        return self.join(3, kill_on_timeout=True)

    def close_streams(self):
        # Only descriptors still owned by this object are closed. A successful
        # EOF close removes the number, so a later reuse cannot be closed twice.
        errors = []
        for fd in list(self.open_fds):
            try:
                os.close(fd)
                self.open_fds.remove(fd)
            except BaseException as error:
                errors.append(repr(error))
        return errors


def spawn(label, function, keep=(), cross_pid=False, remount_proc=True):
    parent_fd = os.pidfd_open(os.getpid(), 0)
    out_r, out_w = os.pipe2(os.O_CLOEXEC)
    err_r, err_w = os.pipe2(os.O_CLOEXEC)
    original_ns = os.open('/proc/self/ns/pid', os.O_RDONLY | os.O_CLOEXEC) if cross_pid else None
    pid = None
    try:
        if cross_pid:
            checked(libc.unshare(CLONE_NEWPID), 'next child PID namespace')
        pid = os.fork()
        if pid == 0:
            try:
                os.dup2(out_w, 1)
                os.dup2(err_w, 2)
                close_except({0, 1, 2, parent_fd, *keep})
                arm_parent(parent_fd)
                if cross_pid and remount_proc:
                    fresh_proc()
                code = function(parent_fd)
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(0 if code is None else code)
            except BaseException:
                traceback.print_exc()
                sys.stderr.flush()
                os._exit(125)
        if cross_pid:
            checked(libc.setns(original_ns, CLONE_NEWPID), 'restore future child PID namespace')
        child = Child(pid, os.pidfd_open(pid, 0), out_r, err_r, label)
        return child
    except BaseException:
        if pid and pid > 0:
            failed = os.pidfd_open(pid, 0)
            try:
                if alive(failed):
                    signal.pidfd_send_signal(failed, signal.SIGKILL)
                os.waitpid(pid, 0)
            finally:
                os.close(failed)
        for fd in (out_r, err_r):
            os.close(fd)
        raise
    finally:
        if pid != 0:
            for fd in (parent_fd, out_w, err_w):
                os.close(fd)
            if original_ns is not None:
                os.close(original_ns)


def child_exec(elf_fd, argv, uid=None):
    def execute(parent_fd):
        if uid is not None:
            os.setgroups([])
            os.setresgid(uid, uid, uid)
            os.setresuid(uid, uid, uid)
            # Linux clears this setting during the credential transition.
            arm_parent(parent_fd)
        must(alive(parent_fd), 'parent lost before exact ELF exec')
        os.set_inheritable(elf_fd, False)
        os.execve(elf_fd, argv, CLEAN_ENV)
    return execute


class Fixture:
    def __init__(self, elfs):
        self.elfs, self.children, self.held_sockets, self.latches = elfs, [], [], []
        self.rows, self.retirement = [], []

    def add(self, child):
        self.children.append(child)
        return child

    def start_factory(self, label):
        transfer, child_transfer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
        transfer.settimeout(4)
        read_latch, write_latch = os.pipe2(os.O_CLOEXEC)
        self.latches.append(write_latch)
        def owner(parent_fd):
            endpoint = socket.socket(fileno=child_transfer.fileno())
            a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
            values = array.array('i', [a.fileno(), b.fileno()])
            must(endpoint.sendmsg([b'CONTROL_V2'], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, values)]) == 10, 'control transfer')
            a.close()
            b.close()
            must(endpoint.send(b'DROPPED') == 7, 'control endpoints closed acknowledgement')
            endpoint.close()
            must(os.read(read_latch, 1) == b'', 'unexpected owner latch command')
            must(alive(parent_fd), 'owner parent lost')
            return 0
        creator = self.add(spawn(label + '-owner', owner, [child_transfer.fileno(), read_latch]))
        child_transfer.close()
        os.close(read_latch)
        received = []
        try:
            message, ancillary, flags, _ = transfer.recvmsg(128, socket.CMSG_SPACE(8 * 4), socket.MSG_CMSG_CLOEXEC)
            received, valid = rights(ancillary)
            must(message == b'CONTROL_V2' and valid and len(received) == 2 and message_flags_valid(flags), 'control rights framing')
            must(transfer.recv(32) == b'DROPPED', 'owner control endpoints not closed')
            control = socket.socket(fileno=received.pop())
            factory_control = socket.socket(fileno=received.pop())
        finally:
            transfer.close()
            for fd in received:
                os.close(fd)
        self.held_sockets.extend([control, factory_control])
        creator_fd_table = fd_table(creator.pid)
        control_targets = {'socket:[' + str(os.fstat(s.fileno()).st_ino) + ']' for s in (control, factory_control)}
        must(not any(row['target'] in control_targets for row in creator_fd_table.values()), 'owner retained control endpoint')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC | socket.SOCK_NONBLOCK)
        self.held_sockets.append(listener)
        listener.bind(SOCKET_NAME)
        listener.listen(8)
        for endpoint in (listener, factory_control):
            endpoint.set_inheritable(True)
        factory = self.add(spawn(label + '-factory', child_exec(self.elfs['factory'],
            ['factory-v2-host', '--serve-inherited', str(listener.fileno()), str(factory_control.fileno()), str(ALLOW_UID), str(ALLOW_UID)]),
            [self.elfs['factory'], listener.fileno(), factory_control.fileno()]))
        listener.close()
        factory_control.close()
        control.settimeout(4)
        ready = control.recv(128)
        must(len(ready) == 40 and ready[:8] == b'DP4RDY02', 'factory READY length/magic')
        version, size, visible_pid, reserved, nsdev, nsino = struct.unpack('<IIIIQQ', ready[8:])
        must((version, size, visible_pid, reserved, nsdev, nsino) ==
             (2, 40, factory.pid, 0, 5, 4026531837), 'factory READY authority mismatch')
        must(alive(creator.pidfd) and alive(factory.pidfd), 'service owner/start terminal')
        table = fd_table(factory.pid)
        return {'creator': creator, 'factory': factory, 'control': control, 'latch': write_latch,
                'baseline': table, 'ready_hex': ready.hex(), 'creator_fd_table': creator_fd_table}

    def idle(self, service):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            must(alive(service['factory'].pidfd), 'factory exited during case')
            observed = fd_table(service['factory'].pid)
            if observed == service['baseline']:
                return observed
            time.sleep(0.01)
        raise RuntimeError('factory FD table did not return to baseline')

    def client(self, case, service=None, cross=False, remount=True, expected_rejection=False, label=None):
        uid = DENY_UID if case == 'wrong_uid' else ALLOW_UID
        name = label or (('cross-' if cross else 'same-') + case)
        child = self.add(spawn(name, child_exec(self.elfs['client'],
            ['factory-client-host', '--owned-client', case], uid), [self.elfs['client']], cross, remount))
        row = child.join(7)
        observed = json.loads(row['stdout'])
        row['observed'] = observed
        row['cross_pid_namespace'] = cross
        row['fresh_proc_view'] = remount if cross else True
        must(not row['stderr'] and not row['forced_kill'], name + ' stderr/forced cleanup')
        if expected_rejection:
            must(row['returncode'] == 1 and observed['pass'] is False and observed['stage'] == 14 and
                 observed['reply_errno'] == errno.EXDEV and observed['wire_valid'] is True and observed['rights'] == 0,
                 name + ' expected wrong-proc EXDEV')
            row['expected_rejection_qualified'] = True
        else:
            must(row['returncode'] == 0 and observed['pass'] is True, name + ' client failed')
        must(observed['fd_before'] == observed['fd_after'], name + ' client FD leak')
        if cross and remount:
            must(observed['visible_tgid'] == 1 and child.pid != 1, 'cross PID number must differ')
        if service is not None:
            row['factory_fd_table_after'] = self.idle(service)
        self.rows.append(row)
        return row

    def hup_stop(self, service):
        must(alive(service['creator'].pidfd), 'HUP owner was already dead')
        service['control'].close()
        result = service['factory'].join(3)
        must(result['returncode'] == 0 and alive(service['creator'].pidfd), 'HUP did not stop factory independently')
        self.rows.append({'case': 'control-HUP-owner-still-alive', 'pass': True, 'factory': result})
        os.close(service['latch'])
        self.latches.remove(service['latch'])
        owner = service['creator'].join(2)
        must(owner['returncode'] == 0, 'owner latch exit')

    def owner_death(self):
        service = self.start_factory('owner-death')
        pending = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
        self.held_sockets.append(pending)
        pending.settimeout(2)
        pending.connect(SOCKET_NAME)
        deadline = time.monotonic() + 0.6
        while time.monotonic() < deadline:
            if len(fd_table(service['factory'].pid)) == len(service['baseline']) + 1:
                break
            time.sleep(0.005)
        else:
            raise RuntimeError('owner-death pending connection was not accepted')
        must(alive(service['creator'].pidfd), 'owner was already terminal')
        started = time.monotonic()
        signal.pidfd_send_signal(service['creator'].pidfd, signal.SIGKILL)
        creator = service['creator'].join(1)
        must(creator['returncode'] == -signal.SIGKILL, 'owner exact pidfd kill result')
        must(service['control'].fileno() >= 0, 'control peer unexpectedly closed')
        result = service['factory'].join(1)
        elapsed = time.monotonic() - started
        must(result['returncode'] == 0 and elapsed < 1.5 and pending.recv(1) == b'', 'owner-death did not retire pending factory')
        self.rows.append({'case': 'owner-pidfd-death-control-peer-held-open', 'pass': True,
                          'seconds': elapsed, 'factory': result, 'creator': creator,
                          'control_peer_fd_open': fcntl.fcntl(service['control'], fcntl.F_GETFD) >= 0})
        pending.close()
        service['control'].close()
        os.close(service['latch'])
        self.latches.remove(service['latch'])

    def bad_reply(self, variant):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
        self.held_sockets.append(listener)
        listener.bind(SOCKET_NAME)
        listener.listen(1)
        listener.settimeout(4)
        def fake(parent_fd):
            connection, _ = listener.accept()
            received = []
            try:
                connection.settimeout(4)
                request, ancillary, flags, _ = connection.recvmsg(128, socket.CMSG_SPACE(32 * 4), socket.MSG_CMSG_CLOEXEC)
                received, valid = rights(ancillary)
                must(len(request) == 64 and valid and len(received) == 2 and message_flags_valid(flags), 'fake peer actual request malformed')
                for fd in received:
                    os.close(fd)
                received.clear()
                wire = bytearray(b'DP4REP02' + struct.pack('<II', 2, 0) + bytes(16))
                count = 0
                if variant == 'v1':
                    wire[:8] = b'DP4REP01'
                    wire[8:12] = struct.pack('<I', 1)
                elif variant == 'short':
                    wire = wire[:-1]
                elif variant == 'long':
                    wire += b'\0'
                elif variant == 'reserved':
                    wire[16] = 1
                elif variant == 'rights0':
                    pass
                elif variant == 'rights2':
                    count = 2
                elif variant == 'error-rights1':
                    wire[12:16] = struct.pack('<I', errno.EPERM)
                    count = 1
                elif variant == 'rights17':
                    count = 17
                else:
                    raise RuntimeError('unrecognized fake reply')
                fd = os.memfd_create('owned-malformed-reply', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
                try:
                    ancillary_out = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd] * count))] if count else []
                    must(connection.sendmsg([wire], ancillary_out, socket.MSG_NOSIGNAL) == len(wire), 'fake reply send')
                    must(connection.recv(1) == b'', 'actual client did not close malformed reply')
                finally:
                    os.close(fd)
                must(alive(parent_fd), 'fake owner parent lost')
                print(json.dumps({'variant': variant, 'actual_request_bytes': len(request), 'response_bytes': len(wire), 'response_rights': count}))
                return 0
            finally:
                for fd in received:
                    os.close(fd)
                connection.close()
                listener.close()
        fake_child = self.add(spawn('fake-' + variant, fake, [listener.fileno()]))
        listener.close()
        row = self.client('bad_reply', label='bad-reply-' + variant)
        row['fake_peer'] = fake_child.join(2)
        must(row['fake_peer']['returncode'] == 0 and not row['fake_peer']['stderr'], 'fake peer failed')

    def run(self):
        must(os.getpid() == 1, 'fixture must be private namespace init')
        service = self.start_factory('normal')
        self.rows.append({'case': 'factory-ready-owned-control', 'pass': True, 'ready_hex': service['ready_hex'],
                          'factory_fd_baseline': service['baseline'], 'creator_fd_table': service['creator_fd_table']})
        for case in ('wire_snapshot', 'create_snapshot'):
            self.client(case, service)
            self.client(case, service, cross=True)
        for case in ('short', 'long', 'v1', 'rights0', 'rights1', 'rights3', 'rights17',
                     'unsealed', 'wrong_source', 'wrong_uid', 'timeout', 'peer_death'):
            self.client(case, service)
        self.client('wire_snapshot', service, cross=True, remount=False, expected_rejection=True, label='wrong-proc-view')
        self.hup_stop(service)
        self.owner_death()
        for variant in ('v1', 'short', 'long', 'reserved', 'rights0', 'rights2', 'error-rights1', 'rights17'):
            self.bad_reply(variant)

    def finish(self):
        errors = []
        for endpoint in self.held_sockets:
            try:
                endpoint.close()
            except BaseException as error:
                errors.append({'stage': 'socket-close', 'error': repr(error)})
        for fd in self.latches:
            try:
                os.close(fd)
            except BaseException as error:
                errors.append({'stage': 'latch-close', 'error': repr(error)})
        for child in reversed(self.children):
            try:
                was_alive = child.returncode is None and alive(child.pidfd)
                result = child.retire()
                self.retirement.append({'label': child.label, 'was_alive_at_cleanup': was_alive,
                                        **child.observation()})
                if was_alive:
                    errors.append({'stage': 'unexpected-live-child', 'label': child.label})
            except BaseException as error:
                errors.append({'stage': 'child-retire', 'label': child.label, 'error': repr(error)})
                self.retirement.append({'label': child.label, 'retirement_error': repr(error), **child.observation()})
            finally:
                for error in child.close_streams():
                    errors.append({'stage': 'child-stream-close', 'label': child.label, 'error': error})
                try:
                    os.close(child.pidfd)
                except BaseException as error:
                    errors.append({'stage': 'pidfd-close', 'label': child.label, 'error': repr(error)})
        try:
            remaining = Path('/proc/1/task/1/children').read_text().strip()
            must(not remaining, 'unreaped or unexpected descendant remains: ' + remaining)
        except BaseException as error:
            errors.append({'stage': 'namespace-descendant-fence', 'error': repr(error)})
        return errors


def run_namespace(elfs, endpoint, parent_fd):
    result = {'schema': 1, 'success': False, 'Android_execution': False, 'production_ready': False,
              'limits': ['Host ELF execution only; no Bionic API or outer ARM64 execution.',
                         'No production factory bootstrap, ART APEX, signing, deployment or complete-App acceptance.',
                         'Peer-death case proves no hang/FD leak after that request; not a mid-copy abort timing claim.',
                         'No adversarial escaped-descendant qualification.']}
    fixture = None
    try:
        arm_parent(parent_fd)
        must(os.getpid() == 1, 'private init PID not one')
        checked(libc.unshare(CLONE_NEWNET), 'unshare private network')
        fresh_proc()
        arm_parent(parent_fd)
        namespace_fds = [os.open('/proc/self/ns/' + name, os.O_RDONLY | os.O_CLOEXEC) for name in NS_TYPES]
        try:
            message = json.dumps({'pid': os.getpid(), 'userns': ns_identity('/proc/self/ns/user'),
                                  'namespaces': {name: identity(fd) for name, fd in zip(NS_TYPES, namespace_fds)}}).encode()
            must(endpoint.sendmsg([message], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', namespace_fds))]) == len(message), 'namespace hello send')
        finally:
            for fd in namespace_fds:
                os.close(fd)
        endpoint.settimeout(10)
        must(endpoint.recv(32) == b'GO_OWNED_HOST_ONLY', 'outer admission missing')
        os.close(parent_fd)
        fixture = Fixture(elfs)
        fixture.run()
        result['success'] = True
    except BaseException as error:
        result['primary_error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        if fixture is not None:
            result['cleanup_errors'] = fixture.finish()
            result['rows'] = fixture.rows
            result['retirement'] = fixture.retirement
            result['success'] = result['success'] and not result['cleanup_errors']
        data = json.dumps(result, sort_keys=True).encode()
        must(len(data) < 200000, 'fixture result packet exceeds bound')
        endpoint.send(data)
        endpoint.close()
    return 0 if result['success'] else 1


def cgroup_path(pid):
    lines = Path('/proc/' + str(pid) + '/cgroup').read_text().splitlines()
    paths = [line[3:] for line in lines if line.startswith('0::')]
    must(len(paths) == 1 and paths[0].startswith('/') and paths[0] != '/', 'unbounded cgroup')
    return Path('/sys/fs/cgroup' + paths[0])


def cgroup_read(root):
    result = {'path': str(root), 'device': root.stat().st_dev, 'inode': root.stat().st_ino}
    for name in ('memory.max', 'memory.high', 'memory.swap.max', 'cpu.max', 'pids.max', 'memory.events', 'pids.current', 'cgroup.events'):
        result[name] = (root / name).read_text().strip()
    return result


def guard_main(guard, snapshot, activation):
    guard.require_unchanged(snapshot)
    read_pinned(ACTIVATION, ACTIVATION_SHA)
    read_pinned('/etc/droidloom/cell.json', CELL_SHA)
    for field in ('daemon_process', 'launcher_process', 'presenter_process'):
        expected = activation[field]
        must(guard.process_identity(expected['host_pid']) == expected, 'Main host process changed: ' + field)
    must({key: (MAIN_CGROUP / key).read_text().strip() for key in activation['limits']} == activation['limits'],
         'Main activation resource limits changed')
    guard.require_unchanged(snapshot)


def events(text):
    return {key: int(value) for key, value in (line.split() for line in text.splitlines())}


def preflight_uids():
    wanted = {ALLOW_UID, DENY_UID}
    must(not any(p.pw_uid in wanted for p in pwd.getpwall()), 'fixture UID account already exists')
    must(not any(g.gr_gid in wanted for g in grp.getgrall()), 'fixture GID group already exists')
    scanned = 0
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            status = dict(line.split(':', 1) for line in (path / 'status').read_text().splitlines() if ':' in line)
            values = set(map(int, (status['Uid'] + status['Gid'] + status.get('Groups', '')).split()))
            must(not (wanted & values), 'fixture UID/GID already used by live process ' + path.name)
            scanned += 1
        except (FileNotFoundError, ProcessLookupError):
            continue
    return {'uids': sorted(wanted), 'process_status_files_checked': scanned, 'accounts_created': False}


def make_elfs():
    report = json.loads(read_pinned(BUILD / 'build-result.json', BUILD_SHA))
    audit = json.loads(read_pinned(BUILD / 'worker-audit.json', AUDIT_SHA))
    must(report['success'] and report['inputs_unchanged'] and report['candidate_source_unchanged'] and
         report['fixture_sources_unchanged'] and report['worker_audit_pass'], 'build not qualified')
    must(audit['qualified_worker_closure'] and not audit['errors'], 'worker binary closure failed')
    result = {}
    try:
        for name, (filename, expected, size) in ELFS.items():
            data = read_pinned(BUILD / filename, expected)
            must(len(data) == size and data[:4] == b'\x7fELF', 'ELF size/magic')
            must(report['artifacts'][name]['sha256'] == expected, 'build artifact pin')
            fd = os.memfd_create('pocket4-owned-v2-' + name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            result[name] = fd
            written = 0
            while written < len(data):
                written += os.write(fd, data[written:])
            os.fchmod(fd, 0o555)
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, 15)
            must(fcntl.fcntl(fd, fcntl.F_GET_SEALS) == 15 and os.fstat(fd).st_uid == 0, 'sealed root ELF')
        return result
    except BaseException:
        for fd in result.values():
            os.close(fd)
        raise


def save(directory_fd, name, value):
    data = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o444, dir_fd=directory_fd)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory_fd)
    return {'name': name, 'bytes': len(data), 'sha256': sha(data)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--out')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'state': 'PLAN_ONLY', 'service_started': False, 'Android_execution': False}))
        return 0
    must(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0, 'owned fixture requires initial-root launch')
    out = Path(args.out or '')
    must(out.parent == Path('/home/alex/work') and out.name.startswith('pocket4-factory-v2-host-runtime-') and
         out.name.removeprefix('pocket4-factory-v2-host-runtime-').isdecimal(), 'exact owned output name required')
    out.mkdir(mode=0o700)
    directory_fd = os.open(out, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    result = {'schema': 1, 'success': False, 'Android_execution': False, 'production_ready': False,
              'automatic_retry': False, 'cleanup_errors': [], 'build_report_sha256': BUILD_SHA,
              'worker_audit_sha256': AUDIT_SHA, 'elf_pins': ELFS}
    guard = snapshot = activation = own_before = main_before = None
    own_root = main_root = None
    child_pid = child_pidfd = parent_fd = None
    parent_sock = child_sock = None
    held_namespaces, elfs = [], {}
    child_reaped = False
    start = time.monotonic()
    try:
        activation = json.loads(read_pinned(ACTIVATION, ACTIVATION_SHA))
        guard = types.ModuleType('owned_factory_main_epoch_guard')
        exec(compile(read_pinned(GUARD, GUARD_SHA), str(GUARD), 'exec'), guard.__dict__)
        snapshot = guard.capture_android(MAIN_INIT)
        must(snapshot['sha256'] == MAIN_EPOCH, 'Main epoch differs from frozen binding')
        main_root, own_root = MAIN_CGROUP, cgroup_path(os.getpid())
        init_cgroup = cgroup_path(MAIN_INIT)
        must(init_cgroup == main_root or main_root in init_cgroup.parents,
             'Main init is outside fixed service cgroup hierarchy')
        guard_main(guard, snapshot, activation)
        must(main_root != own_root and not str(own_root).startswith(str(main_root) + '/'), 'fixture shares Main cgroup')
        own_before, main_before = cgroup_read(own_root), cgroup_read(main_root)
        must(own_before['memory.max'].isdigit() and int(own_before['memory.max']) <= 512 * 1024 * 1024, 'fixture memory must be bounded')
        quota, period = own_before['cpu.max'].split()
        must(quota.isdecimal() and int(quota) <= int(period), 'fixture CPU quota must be <= one CPU')
        affinity = sorted(os.sched_getaffinity(0))
        must(len(affinity) >= 4, 'reserve at least two CPUs')
        os.sched_setaffinity(0, {affinity[-1]})
        must(ns_identity('/proc/self/ns/user') == {'device': 5, 'inode': 4026531837}, 'initial user namespace required')
        result['uid_admission'] = preflight_uids()
        result['Main_before'] = snapshot
        result['main_cgroup_before'] = main_before
        result['own_cgroup_before'] = own_before
        result['affinity_before'] = affinity
        result['affinity_selected'] = affinity[-1:]
        elfs = make_elfs()
        result['sealed_elfs'] = {name: {**identity(fd), 'seals': fcntl.fcntl(fd, fcntl.F_GET_SEALS)} for name, fd in elfs.items()}
        parent_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
        parent_sock.settimeout(12)
        parent_fd = os.pidfd_open(os.getpid(), 0)
        original_pidns = os.open('/proc/self/ns/pid', os.O_RDONLY | os.O_CLOEXEC)
        try:
            checked(libc.unshare(CLONE_NEWPID), 'outer future child PID namespace')
            child_pid = os.fork()
            if child_pid == 0:
                try:
                    close_except({0, 1, 2, parent_fd, child_sock.fileno(), *elfs.values()})
                    rc = run_namespace(elfs, child_sock, parent_fd)
                    os._exit(rc)
                except BaseException:
                    traceback.print_exc()
                    sys.stderr.flush()
                    os._exit(125)
            checked(libc.setns(original_pidns, CLONE_NEWPID), 'restore outer future children')
        finally:
            os.close(original_pidns)
        child_pidfd = os.pidfd_open(child_pid, 0)
        child_sock.close()
        os.close(parent_fd)
        parent_fd = None
        hello, ancillary, flags, _ = parent_sock.recvmsg(8192, socket.CMSG_SPACE(8 * 4), socket.MSG_CMSG_CLOEXEC)
        held_namespaces, valid = rights(ancillary)
        result['namespace_initial_packet_utf8'] = hello.decode('utf-8', 'replace')
        must(valid and len(held_namespaces) == 3 and message_flags_valid(flags), 'namespace attestation rights malformed')
        hello = json.loads(hello)
        must(hello['pid'] == 1 and hello['userns'] == {'device': 5, 'inode': 4026531837}, 'fixture init authority')
        for (name, kind), fd in zip(NS_TYPES.items(), held_namespaces):
            must(fcntl.ioctl(fd, 0xb703) == kind, 'namespace fd type mismatch')
            actual = identity(fd)
            must(actual == hello['namespaces'][name] == ns_identity('/proc/' + str(child_pid) + '/ns/' + name), 'namespace identity mismatch')
            must(actual != ns_identity('/proc/self/ns/' + name) and actual != ns_identity('/proc/' + str(MAIN_INIT) + '/ns/' + name), 'namespace was not isolated')
        result['namespace_admission'] = {'host_pid': child_pid, 'hello': hello,
                                         'held_ns': {name: identity(fd) for name, fd in zip(NS_TYPES, held_namespaces)}}
        guard_main(guard, snapshot, activation)
        must(alive(child_pidfd), 'fixture init died before admission')
        parent_sock.send(b'GO_OWNED_HOST_ONLY')
        parent_sock.settimeout(115)
        body, ancillary, flags, _ = parent_sock.recvmsg(262144, socket.CMSG_SPACE(8 * 4), socket.MSG_CMSG_CLOEXEC)
        unexpected, valid = rights(ancillary)
        for fd in unexpected:
            os.close(fd)
        must(valid and not unexpected and message_flags_valid(flags) and len(body) < 200000, 'fixture result framing')
        result['fixture'] = json.loads(body)
        deadline = time.monotonic() + 3
        while alive(child_pidfd) and time.monotonic() < deadline:
            time.sleep(0.01)
        must(not alive(child_pidfd), 'fixture init did not exit after result')
        waited, status = os.waitpid(child_pid, 0)
        child_reaped = True
        result['namespace_init_returncode'] = os.waitstatus_to_exitcode(status)
        must(waited == child_pid and result['namespace_init_returncode'] == 0 and result['fixture']['success'], 'owned fixture failed')
        result['success'] = True
    except BaseException as error:
        result['primary_error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        # Each cleanup/fence runs even if a prior operation failed.
        if child_pid and child_pid > 0 and not child_reaped:
            try:
                if child_pidfd is None:
                    child_pidfd = os.pidfd_open(child_pid, 0)
                if alive(child_pidfd):
                    signal.pidfd_send_signal(child_pidfd, signal.SIGKILL)
                    result['forced_namespace_retirement'] = True
                waited, status = os.waitpid(child_pid, 0)
                child_reaped = waited == child_pid
                result['namespace_init_returncode'] = os.waitstatus_to_exitcode(status)
            except BaseException as error:
                result['cleanup_errors'].append({'stage': 'namespace-init-retire', 'error': repr(error)})
        result['namespace_init_reaped'] = child_reaped
        for fd in [child_pidfd, parent_fd, *held_namespaces, *elfs.values()]:
            if fd is not None:
                try:
                    os.close(fd)
                except BaseException as error:
                    result['cleanup_errors'].append({'stage': 'held-fd-close', 'error': repr(error)})
        for endpoint in (parent_sock, child_sock):
            if endpoint is not None:
                try:
                    endpoint.close()
                except BaseException as error:
                    result['cleanup_errors'].append({'stage': 'outer-socket-close', 'error': repr(error)})
        if snapshot is not None:
            try:
                guard_main(guard, snapshot, activation)
                result['Main_unchanged'] = True
            except BaseException as error:
                result['cleanup_errors'].append({'stage': 'Main-epoch-after', 'error': repr(error)})
        for name, root, before in (('main', main_root, main_before), ('own', own_root, own_before)):
            if before is not None:
                try:
                    after = cgroup_read(root)
                    result[name + '_cgroup_after'] = after
                    for field in ('path', 'device', 'inode', 'memory.max', 'memory.high', 'memory.swap.max', 'cpu.max', 'pids.max'):
                        must(before[field] == after[field], name + ' cgroup identity/limit changed')
                    a, b = events(before['memory.events']), events(after['memory.events'])
                    deltas = {key: b[key] - a.get(key, 0) for key in b}
                    result[name + '_memory_event_delta'] = deltas
                    must(all(deltas.get(key, 0) == 0 for key in ('oom', 'oom_kill', 'oom_group_kill')), name + ' OOM event')
                except BaseException as error:
                    result['cleanup_errors'].append({'stage': name + '-cgroup-after', 'error': repr(error)})
        result['success'] = bool(result['success'] and child_reaped and not result['cleanup_errors'] and not result.get('forced_namespace_retirement'))
        result['seconds'] = time.monotonic() - start
        result['controller_sha256'] = sha(Path(__file__).read_bytes())
        receipt = save(directory_fd, 'runtime-result.json', result)
        os.fchmod(directory_fd, 0o755)
        os.close(directory_fd)
        print(json.dumps({'success': result['success'], 'output': str(out / 'runtime-result.json'),
                          **receipt, 'primary_error': result.get('primary_error'),
                          'Android_execution': False, 'production_ready': False}), flush=True)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
