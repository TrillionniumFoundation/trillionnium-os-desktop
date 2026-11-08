"""Six once-only acoustic requests between a root worker and its actual parent.

All messages carry kernel credentials. No message is retried after send or an
unknown response, and no audio descriptor or arbitrary command crosses here.
"""
import os
from pathlib import Path
import select
import socket
import stat
import struct
import time

SCHEMA = 'pocket4-current-camera-acoustic-channel-v1'
MAX_PACKET = 65536
ORDER = ('emit_prepare', 'emit_go', 'emit_finish', 'listen_prepare', 'listen_go', 'listen_finish')
REQUEST_KEYS = {'schema', 'sequence', 'kind', 'parent', 'plan', 'value'}
RESPONSE_KEYS = {'schema', 'sequence', 'kind', 'ok', 'value', 'error'}

def need(ok, why):
    if not ok: raise RuntimeError(why)

def socket_identity(fd):
    s = os.fstat(fd); need(stat.S_ISSOCK(s.st_mode), 'ACTUAL_ACOUSTIC_CHANNEL_SOCKET')
    return {'device': s.st_dev, 'inode': s.st_ino, 'mode': s.st_mode, 'uid': s.st_uid, 'gid': s.st_gid}

def receive(sock, credentials, parse):
    raw, ancillary, flags, _ = sock.recvmsg(MAX_PACKET + 1, socket.CMSG_SPACE(struct.calcsize('3i')))
    need(raw and len(raw) <= MAX_PACKET and flags == 0, 'ACOUSTIC_CHANNEL_EOF_OVERFLOW_OR_TRUNCATION')
    need(len(ancillary) == 1 and ancillary[0][:2] == (socket.SOL_SOCKET, socket.SCM_CREDENTIALS)
        and len(ancillary[0][2]) == struct.calcsize('3i')
        and struct.unpack('3i', ancillary[0][2]) == credentials, 'ACTUAL_ACOUSTIC_CHANNEL_SENDER')
    return parse(raw)

def exited(pidfd):
    p = select.poll(); p.register(pidfd, select.POLLIN); return bool(p.poll(0))

def child_identity(pid):
    need(type(pid) is int and pid > 1, 'EXACT_ACOUSTIC_CHILD_PID')
    directory = os.open('/proc/' + str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        def read(name, maximum):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            try:
                chunks = []; total = 0
                while total <= maximum:
                    part = os.read(fd, min(16384, maximum + 1 - total))
                    if not part: break
                    total += len(part); chunks.append(part)
                need(total <= maximum, 'BOUNDED_ACOUSTIC_PROC_FIELD')
                return b''.join(chunks).decode('ascii', 'strict')
            finally: os.close(fd)
        def generation():
            raw = read('stat', 65536); fields = raw.rsplit(')', 1)[1].split()
            need(int(raw.split(' ', 1)[0]) == pid and len(fields) >= 20, 'ACTUAL_ACOUSTIC_PROC_STAT')
            return {'pid': pid, 'parent': int(fields[1]), 'start_ticks': int(fields[19])}
        before = generation()
        selected = {line.split(':', 1)[0]: line.split(':', 1)[1].split()
            for line in read('status', 131072).splitlines()
            if line.split(':', 1)[0] in ('Uid', 'Gid', 'Groups', 'CapEff', 'CapPrm', 'CapAmb', 'NoNewPrivs')}
        need(set(selected) == {'Uid', 'Gid', 'Groups', 'CapEff', 'CapPrm', 'CapAmb', 'NoNewPrivs'},
            'COMPLETE_ACTUAL_ACOUSTIC_CHILD_STATUS')
        exe = os.open('exe', os.O_PATH | os.O_CLOEXEC, dir_fd=directory)
        try: info = os.fstat(exe)
        finally: os.close(exe)
        value = {**before, 'uids': [int(x) for x in selected['Uid']], 'gids': [int(x) for x in selected['Gid']],
            'groups': [int(x) for x in selected['Groups']],
            **{key: selected[key][0] for key in ('CapEff', 'CapPrm', 'CapAmb', 'NoNewPrivs')},
            'executable_inode': {'device': info.st_dev, 'inode': info.st_ino},
            'namespaces': {n: os.readlink('ns/' + n, dir_fd=directory) for n in ('mnt', 'pid', 'uts', 'ipc', 'net', 'cgroup', 'user')},
            'cgroup': read('cgroup', 65536).splitlines()}
        need(generation() == before, 'SAME_ACOUSTIC_CHILD_GENERATION')
        return value
    finally: os.close(directory)

class AcousticClient:
    def __init__(self, c, runtime, fd, parent_ref, plan_ref, prep_ref, base):
        self.c, self.runtime, self.parent_ref, self.plan_ref, self.base = c, runtime, parent_ref, plan_ref, base
        self.sock = self.pidfd = None; self.session = None; self.closed = False
        self.sequence = 0; self.pending = None; self.results = {}
        value = c.parse(c.read_ref(parent_ref, 131072)); self.parent = value
        try:
            need(set(value) == {'schema', 'plan', 'preparation', 'case_root', 'parent', 'boot_id',
                'client_socket', 'limits', 'nonce', 'automatic_retry'}
                and value['schema'] == 'pocket4-current-camera-acoustic-parent-v1'
                and value['plan'] == plan_ref and value['preparation'] == prep_ref
                and value['case_root'] == base['case_root'] and value['limits'] == base['limits']
                and value['nonce'] == base['audio_nonce'] and value['automatic_retry'] is False
                and Path(parent_ref['path']) == Path(base['case_root']) / 'acoustic-supervisor/parent.json',
                'EXACT_CURRENT_CAMERA_ACOUSTIC_PARENT')
            need(type(fd) is int and fd > 2 and socket_identity(fd) == value['client_socket'], 'EXACT_INHERITED_ACOUSTIC_FD')
            self.sock = socket.socket(fileno=fd); self.sock.setblocking(False); os.set_inheritable(fd, False)
            need(self.sock.family == socket.AF_UNIX and self.sock.type == socket.SOCK_SEQPACKET,
                'EXACT_PRIVATE_ACOUSTIC_PROTOCOL')
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
            self.pid = value['parent']['pid']; self.pidfd = os.pidfd_open(self.pid, 0)
            need(struct.unpack('3i', self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)) == (self.pid, 0, 0),
                'ACTUAL_ROOT_ACOUSTIC_PARENT_PEER')
            self.verify()
        except BaseException:
            self.close(); raise

    def verify(self):
        need(not self.closed and self.sock is not None and self.pidfd is not None,
            'ACOUSTIC_PARENT_AUTHORITY_CLOSED')
        self.c.read_ref(self.parent_ref)
        need(not exited(self.pidfd) and os.getppid() == self.pid
            and self.runtime.boot() == self.parent['boot_id']
            and self.runtime.process(self.c, self.pid) == self.parent['parent'], 'SAME_LIVE_ACOUSTIC_PARENT_GENERATION')
        need(socket_identity(self.sock.fileno()) == self.parent['client_socket']
            and not os.get_inheritable(self.sock.fileno()), 'UNCHANGED_PRIVATE_ACOUSTIC_CHANNEL')

    def attach(self, session):
        need(self.session is None and session.active['base_plan'] == self.plan_ref
            and session.kind == 'camera_video' and session.root == Path(self.base['case_root']),
            'ONE_CURRENT_CAMERA_VIDEO_SESSION')
        self.session = session; self.verify()

    def request(self, kind, extra=None):
        need(self.session is not None and self.pending is None and self.sequence < len(ORDER)
            and kind == ORDER[self.sequence], 'ONCE_ORDERED_CAMERA_ACOUSTIC_REQUEST')
        self.verify(); self.session.guard()
        value = {'active_plan': self.session.active_ref, 'phase': self.session.phase_ref}
        if extra is not None:
            need(kind == 'listen_finish' and set(extra) == {'playback_binding'}, 'ONLY_EXACT_PLAYBACK_BINDING')
            value.update(extra)
        deadline = min(time.monotonic() + (12 if kind.endswith('finish') else 10), self.session.deadline)
        need(time.monotonic() < deadline, 'NO_ACOUSTIC_DISPATCH_AFTER_CURRENT_PHASE')
        self.sequence += 1
        row = {'schema': SCHEMA, 'sequence': self.sequence, 'kind': kind,
            'parent': self.parent_ref, 'plan': self.plan_ref, 'value': value}
        raw = self.c.canonical(row); need(len(raw) <= MAX_PACKET, 'BOUNDED_CURRENT_ACOUSTIC_REQUEST')
        self.pending = {'kind': kind, 'sequence': self.sequence, 'sent': False, 'automatic_retry': False}
        poller = select.poll(); poller.register(self.pidfd, select.POLLIN)
        poller.register(self.sock, select.POLLIN | select.POLLOUT | select.POLLERR | select.POLLHUP)
        while time.monotonic() < deadline:
            self.verify()
            if not self.pending['sent']:
                try:
                    need(self.sock.send(raw, socket.MSG_NOSIGNAL) == len(raw), 'ATOMIC_ACOUSTIC_REQUEST')
                    self.pending['sent'] = True
                    poller.modify(self.sock, select.POLLIN | select.POLLERR | select.POLLHUP)
                except BlockingIOError: pass
            if self.pending['sent']:
                try:
                    reply = receive(self.sock, (self.pid, 0, 0), self.c.parse)
                    need(type(reply) is dict and set(reply) == RESPONSE_KEYS and reply['schema'] == SCHEMA
                        and reply['sequence'] == self.sequence and reply['kind'] == kind
                        and reply['ok'] is True and reply['error'] is None, 'EXACT_CURRENT_ACOUSTIC_REPLY')
                    self.verify(); self.session.guard()
                    self.results[kind] = reply['value']; self.pending = None
                    return reply['value']
                except BlockingIOError: pass
            poller.poll(max(1, min(100, int((deadline - time.monotonic()) * 1000))))
        raise TimeoutError('ACOUSTIC_REQUEST_OUTCOME_UNKNOWN_NO_REPLAY')

    def close(self):
        first = None
        for key in ('sock', 'pidfd'):
            value = getattr(self, key, None); setattr(self, key, None)
            if value is not None:
                try: value.close() if key == 'sock' else os.close(value)
                except BaseException as error:
                    if first is None: first = error
                    else: first.add_note('OTHER_ACOUSTIC_DESCRIPTOR_CLOSE:' + str(error))
        self.closed = True
        if first is not None: raise first
