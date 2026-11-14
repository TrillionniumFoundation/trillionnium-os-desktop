"""Keep Clock's original whole-case flock across typed backend processes.

SCM_RIGHTS duplicates the existing open file description. The original
backend still calls its actual flock and close. A new open would self-conflict;
unlocking between decisions would weaken the original case contract.
"""
import array
import fcntl
import os
from pathlib import Path
import secrets
import select
import socket
import stat
import struct
import time

ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'


def identity(info):
    return {name: getattr(info, name) for name in
            ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink')}


def held(common, fd, path, expected):
    value = os.fstat(fd); named = Path(path).lstat()
    common.need(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and value.st_uid == 0 and
        identity(value) == identity(named) == expected, 'SAME_ACTUAL_GLOBAL_ACTION_LOCK_INODE_REQUIRED')
    # This is a real flock on the received original OFD, not a synthetic lock
    # success or a replacement fcntl implementation.
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


class Owner:
    def __init__(self, common, runtime, root, lock_path):
        self.c, self.runtime, self.root = common, runtime, common.private_dir(root)
        self.path = str(lock_path); self.fd = None; self.server = None
        self.pending = {}; self.served = []; self.clients = []
        self.errors = []; self.closed = False
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            self.expected = identity(os.fstat(self.fd)); held(common, self.fd, self.path, self.expected)
            self.owner = runtime.process(common, os.getpid())
            self.address = '\0p4-clock-action-' + secrets.token_hex(16)
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
            self.server.bind(self.address); self.server.listen(4); self.server.setblocking(False)
            self.value = {'schema': 'pocket4-final-clock-action-lock-v1', 'path': self.path,
                'file': self.expected, 'owner': self.owner, 'boot_id': runtime.boot(),
                'socket': '@' + self.address[1:], 'same_open_file_description_required': True,
                'automatic_retry': False}
            self.ref = common.write_new(self.root / 'action-lock.json', self.value, 0o400)
            common.private_dir(self.root / 'lock-grants', create=True)
        except BaseException:
            self._close_resources()
            raise

    def verify(self):
        self.c.need(not self.closed and self.fd is not None and not self.errors, 'CLOCK_ACTION_LOCK_OWNER_NOT_LIVE')
        self.c.need(self.runtime.process(self.c, os.getpid()) == self.owner, 'CLOCK_CASE_OPERATOR_CHANGED')
        held(self.c, self.fd, self.path, self.expected)
        self.c.read_ref(self.ref)

    def authorize(self, scope_ref, step, phase_ref, backend_argv):
        self.verify()
        step = Path(step)
        self.c.need(type(backend_argv) is list and all(type(x) is str for x in backend_argv),
                    'EXACT_NEW_TYPED_BACKEND_ARGV_REQUIRED')
        value = {'schema': 'pocket4-final-clock-lock-grant-v1', 'action_lock': self.ref,
            'scope': scope_ref, 'step': str(step), 'phase_lease': phase_ref,
            'backend_argv': backend_argv, 'token': secrets.token_hex(32), 'automatic_retry': False}
        name = scope_ref['sha256'][:24] + '-' + step.name
        ref = self.c.write_new(self.root / 'lock-grants' / (name + '.json'), value, 0o400)
        self.c.need(len(self.pending) + len(self.served) < 256, 'BOUNDED_ORIGINAL_TIMER_OBSERVATION_CALLS')
        self.pending[value['token']] = (ref, value)
        return ref

    def pump(self, execution_deadline):
        """One nonblocking pass in the original capture's single-threaded wait.

        No worker thread or background child may weaken OwnChildReaper's
        single-thread ownership. Accepted sockets have a one-second handshake
        bound, additionally clipped to the current command's actual deadline.
        """
        if self.closed or self.errors:
            return
        self.verify()
        for _ in range(4 - len(self.clients)):
            try:
                client, _ = self.server.accept()
            except BlockingIOError:
                break
            client.setblocking(False)
            self.clients.append((client, min(time.monotonic() + 1, execution_deadline)))
        for client, deadline in list(self.clients):
            try:
                self.c.need(time.monotonic() < deadline, 'ACTION_LOCK_HANDSHAKE_DEADLINE')
                try:
                    raw = client.recv(65537)
                except BlockingIOError:
                    continue
                self._serve_request(client, raw, deadline)
            except BaseException as error:
                # Retain any possibly delivered pidfd/OFD. A failed grant is
                # never replayed; the caller's next full guard refuses errors.
                self.errors.append(type(error).__name__ + ':' + str(error))
                try:
                    client.send(b'REJECTED')
                except OSError:
                    pass
            client.close(); self.clients.remove((client, deadline))
            if self.errors:
                break

    def _serve_request(self, client, raw, deadline):
        pid, uid, gid = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        self.c.need(uid == gid == 0, 'ROOT_TYPED_BACKEND_PEER_REQUIRED')
        self.c.need(0 < len(raw) <= 65536, 'BOUNDED_LOCK_GRANT_REQUEST')
        requested = self.c.parse(raw)
        self.c.need(set(requested) == {'grant', 'token'}, 'EXACT_LOCK_GRANT_REQUEST')
        pair = self.pending.pop(requested['token'], None)
        self.c.need(pair is not None and pair[0] == requested['grant'], 'ONCE_ONLY_PRIVATE_LOCK_GRANT_REQUIRED')
        ref, grant = pair; self.c.read_ref(ref); self.verify()
        peer = self.runtime.process(self.c, pid)
        self.runtime.descendant_from(self.c, pid, self.owner)
        with open('/proc/' + str(pid) + '/cmdline', 'rb') as stream:
            raw_argv = stream.read(131073)
        self.c.need(len(raw_argv) <= 131072 and raw_argv.endswith(b'\0') and
            raw_argv[:-1].decode('utf-8', 'strict').split('\0') == grant['backend_argv'],
            'ONLY_THE_EXACT_FROZEN_TYPED_BACKEND_MAY_RECEIVE_LOCK')
        pidfd = os.pidfd_open(pid, 0)
        try:
            self.c.need(self.runtime.process(self.c, pid) == peer, 'TYPED_BACKEND_PEER_CHANGED')
            row = {'grant': ref, 'peer': peer, 'transfer_attempted': True,
                   'same_OFD_sent': False, 'recipient_pidfd_held': True}
            self.served.append((pidfd, row)); pidfd = None
            descriptors = array.array('i', [self.fd])
            self.c.need(time.monotonic() < deadline, 'NO_ACTION_LOCK_TRANSFER_AFTER_PHASE_DEADLINE')
            sent = client.sendmsg([b'CLOCK_ORIGINAL_OFD'], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, descriptors)])
            self.c.need(sent == len(b'CLOCK_ORIGINAL_OFD'), 'ACTION_LOCK_FD_TRANSFER_INCOMPLETE')
            row['same_OFD_sent'] = True
            self.c.write_new(self.root / 'lock-grants' / (ref['sha256'] + '.sent.json'), row)
        finally:
            if pidfd is not None:
                os.close(pidfd)

    def _close_resources(self):
        if self.server is not None:
            self.server.close(); self.server = None
        for client, _ in self.clients:
            client.close()
        self.clients = []
        if self.fd is not None:
            os.close(self.fd); self.fd = None

    def close(self):
        primary = None
        if self.server is not None:
            self.server.close(); self.server = None
        for client, _ in self.clients:
            client.close()
        self.clients = []
        self.closed = True
        # All receiving processes must really have exited before the owner
        # releases its original lock. A live unknown holder keeps the FD open.
        for pidfd, row in self.served:
            if not select.select([pidfd], [], [], 0)[0]:
                primary = RuntimeError('ACTION_LOCK_RECIPIENT_RETIREMENT_UNKNOWN')
                break
        if primary is not None:
            raise primary
        for pidfd, _ in self.served:
            os.close(pidfd)
        self.served = []
        if self.fd is not None:
            os.close(self.fd); self.fd = None
        self.c.need(not self.errors, 'ACTION_LOCK_SERVER_RECORDED_FAILURE')


def validate(common, runtime, ref, *, expected_path=ACTION_LOCK):
    value = common.parse(common.read_ref(ref))
    common.need(set(value) == {'schema', 'path', 'file', 'owner', 'boot_id', 'socket',
        'same_open_file_description_required', 'automatic_retry'}
        and value['schema'] == 'pocket4-final-clock-action-lock-v1' and value['path'] == expected_path
        and value['boot_id'] == runtime.boot() and value['same_open_file_description_required'] is True
        and value['automatic_retry'] is False and type(value['socket']) is str
        and value['socket'].startswith('@p4-clock-action-') and len(value['socket']) == 49,
        'EXACT_ORIGINAL_CLOCK_WHOLE_CASE_LOCK_REQUIRED')
    common.need(runtime.process(common, value['owner']['pid']) == value['owner'], 'ACTUAL_CLOCK_LOCK_OWNER_CHANGED')
    common.need(identity(Path(value['path']).lstat()) == value['file'], 'GLOBAL_ACTION_LOCK_NAMED_INODE_CHANGED')
    return value


def receive(common, runtime, ref, grant_ref, scope_ref, step, phase_ref):
    value = validate(common, runtime, ref)
    return receive_validated(common, runtime, ref, value, grant_ref, scope_ref, step, phase_ref)


def receive_validated(common, runtime, ref, value, grant_ref, scope_ref, step, phase_ref):
    grant = common.parse(common.read_ref(grant_ref))
    common.need(grant['schema'] == 'pocket4-final-clock-lock-grant-v1' and grant['action_lock'] == ref
        and grant['scope'] == scope_ref and grant['step'] == str(step) and grant['phase_lease'] == phase_ref
        and grant['automatic_retry'] is False, 'EXACT_THIS_TYPED_BACKEND_LOCK_GRANT_REQUIRED')
    fd = None
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC) as channel:
        channel.settimeout(2); channel.connect('\0' + value['socket'][1:])
        pid, uid, gid = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        common.need(pid == value['owner']['pid'] and uid == gid == 0, 'ACTUAL_PRIVATE_LOCK_OWNER_PEER_REQUIRED')
        channel.sendall(common.canonical({'grant': grant_ref, 'token': grant['token']}))
        message, control, flags, _ = channel.recvmsg(64, socket.CMSG_SPACE(array.array('i').itemsize), socket.MSG_CMSG_CLOEXEC)
        descriptors = []
        try:
            for level, kind, data in control:
                common.need(level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS, 'ONLY_ONE_ORIGINAL_LOCK_DESCRIPTOR')
                received = array.array('i'); received.frombytes(data[:len(data) - len(data) % received.itemsize])
                descriptors.extend(received)
            common.need(message == b'CLOCK_ORIGINAL_OFD' and flags & ~socket.MSG_CMSG_CLOEXEC == 0
                        and len(descriptors) == 1,
                        'EXACT_COMPLETE_ORIGINAL_LOCK_DESCRIPTOR_REQUIRED')
            fd = descriptors.pop()
            common.need(fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC,
                        'RECEIVED_LOCK_DESCRIPTOR_MUST_BE_CLOSE_ON_EXEC')
            held(common, fd, value['path'], value['file'])
            common.need(runtime.process(common, pid) == value['owner'], 'LOCK_OWNER_CHANGED_DURING_TRANSFER')
            return fd
        except BaseException:
            if fd is not None:
                os.close(fd)
            raise
        finally:
            for unwanted in descriptors:
                os.close(unwanted)
