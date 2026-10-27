"""Linux x86_64 identity selection for one ORIGINAL named issuer channel.

No thread-name heuristics, process-wide stop, syscall edits or replacement peer.
The only paused thread starts at read-one or the socket+owner-pidfd idle poll.
"""
import ctypes
import errno
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import time

from notes_fault_contract import Refused, require
from notes_fault_linux import (LIBC, Iovec, TraceThread, Registers, READS, SEIZE,
                               INTERRUPT, GETREGS, EVENT_STOP, proc_identity)

POLLS = {7, 271}  # x86_64 poll and ppoll; ppoll_time64 is unnecessary on x86_64.


def read_memory(pid, address, length):
    require(0 < length <= 8192, "issuer_memory_bound")
    buffer = ctypes.create_string_buffer(length)
    local = Iovec(ctypes.cast(buffer, ctypes.c_void_p), length)
    remote = Iovec(ctypes.c_void_p(address), length)
    count = LIBC.process_vm_readv(pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0)
    if count != length:
        raise OSError(ctypes.get_errno() or errno.EIO, "bounded issuer memory read incomplete")
    return bytes(buffer.raw)


def snapshot(root, tid):
    line = Path(f"/proc/{root.pid}/task/{tid}/syscall").read_text().split()
    if len(line) != 9 or line[0] in ("running", "-1"):
        return None
    nr, args = int(line[0]), [int(item, 16) for item in line[1:7]]
    return (nr, args) if (nr in READS and args[2] == 1) or (nr in POLLS and args[1] == 2) else None


def poll_descriptors(root, value, *, idle=True):
    nr, args = value
    require(nr in POLLS and args[1] == 2, "issuer_not_two_fd_poll")
    entries = struct.unpack("ihhihh", read_memory(root.pid, args[0], 16))
    require(entries[1] in ((1,) if idle else (1, 4)) and entries[4] == 1 and entries[0] >= 0 and entries[3] >= 0,
            "issuer_idle_poll_events")
    return entries[0], entries[3]


def pidfd_target(pid, fd):
    require(os.readlink(f"/proc/{pid}/fd/{fd}") == "anon_inode:[pidfd]", "issuer_owner_not_pidfd")
    values = [line.split(":", 1)[1].strip() for line in
              Path(f"/proc/{pid}/fdinfo/{fd}").read_text().splitlines() if line.startswith("Pid:")]
    require(len(values) == 1 and values[0].isdecimal(), "issuer_owner_pidfd_identity")
    return int(values[0])


def path_identity(path, peer_gid):
    require(path.is_absolute() and path.resolve(strict=True) == path, "issuer_canonical_path")
    info = path.lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid == 0 and info.st_gid == peer_gid
            and stat.S_IMODE(info.st_mode) == 0o660, "issuer_node_custody")
    parent = path.parent.stat()
    require(parent.st_uid == 0 and parent.st_gid == peer_gid
            and stat.S_IMODE(parent.st_mode) == 0o2710, "issuer_runtime_custody")
    for ancestor in path.parent.parents:
        item = ancestor.stat()
        require(stat.S_ISDIR(item.st_mode) and item.st_uid == 0 and not item.st_mode & 0o022,
                "issuer_ancestor_custody")
    return info.st_dev, info.st_ino


class HeldIssuerSocket:
    def __init__(self, root, fd, agentd, path, owner_fd=None):
        self.root, self.fd, self.agentd = root, fd, agentd
        self.path, self.owner_fd = Path(path), owner_fd
        self.node = path_identity(self.path, agentd.identity["gid"][0])
        result = LIBC.syscall(ctypes.c_long(438), ctypes.c_int(root.pidfd), ctypes.c_int(fd), ctypes.c_uint(0))
        if result < 0:
            raise OSError(ctypes.get_errno(), "issuer pidfd_getfd unavailable")
        self.socket = socket.socket(fileno=result)
        try:
            self.identity = os.fstat(result)
            require(self.socket.family == socket.AF_UNIX
                    and self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM
                    and self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 0,
                    "issuer_not_accepted_stream")
            require(self.socket.getsockname() == str(self.path)
                    and self.socket.getpeername() in ("", b""), "issuer_original_named_socket")
            peer = struct.unpack("iII", self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            require(peer == (agentd.pid, agentd.identity["uid"][0], agentd.identity["gid"][0]),
                    "issuer_original_agentd_peer")
            self.verify()
        except BaseException:
            self.socket.close()
            raise

    def observe_owner(self, owner_fd):
        require(self.owner_fd is None or self.owner_fd == owner_fd, "issuer_owner_fd_changed")
        require(pidfd_target(self.root.pid, owner_fd) == self.agentd.pid, "issuer_original_owner_pidfd")
        self.owner_fd = owner_fd

    def verify(self):
        self.root.verify(tracer=os.getpid())
        self.agentd.verify()
        current = os.stat(f"/proc/{self.root.pid}/fd/{self.fd}")
        require(stat.S_ISSOCK(current.st_mode)
                and (current.st_dev, current.st_ino) == (self.identity.st_dev, self.identity.st_ino),
                "issuer_socket_replaced")
        require(path_identity(self.path, self.agentd.identity["gid"][0]) == self.node,
                "issuer_named_node_replaced")
        if self.owner_fd is not None:
            require(pidfd_target(self.root.pid, self.owner_fd) == self.agentd.pid, "issuer_owner_pidfd_mismatch")

    def close(self):
        self.socket.close()


def select_issuer(root, agentd, path):
    candidates, blocked = [], False
    try:
        for entry in Path(f"/proc/{root.pid}/task").iterdir():
            if not entry.name.isdecimal():
                continue
            tid = int(entry.name)
            birth = proc_identity(root.pid, tid)["start_ticks"]
            value = snapshot(root, tid)
            if value is None:
                continue
            try:
                nr, args = value
                fd, owner = poll_descriptors(root, value) if nr in POLLS else (args[0], None)
                if not os.readlink(f"/proc/{root.pid}/fd/{fd}").startswith("socket:["):
                    continue
                if owner is not None and pidfd_target(root.pid, owner) != agentd.pid:
                    continue
                channel = HeldIssuerSocket(root, fd, agentd, path, owner)
            except Refused:
                continue
            except OSError as error:
                if error.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS):
                    blocked = True
                continue
            try:
                require(snapshot(root, tid) == value and proc_identity(root.pid, tid)["start_ticks"] == birth,
                        "issuer_idle_snapshot_changed")
                candidates.append((tid, value, channel, birth))
            except BaseException:
                channel.close()
                raise
        require(len(candidates) == 1, "issuer_thread_not_unique" if candidates else
                "issuer_inspection_not_permitted" if blocked else "no_original_idle_issuer_thread")
        return candidates.pop()
    finally:
        for _, _, channel, _ in candidates:
            channel.close()


class IssuerTrace(TraceThread):
    def attach(self, deadline):
        self.ptrace(SEIZE, data=ctypes.c_void_p(1 | 0x10))
        self.attached = True
        self.record({"attached_monotonic": time.monotonic(), "tid": self.tid, "start_ticks": self.birth})
        self.ptrace(INTERRUPT)
        status = self.wait(deadline)
        require(status >> 16 == EVENT_STOP and os.WSTOPSIG(status) == signal.SIGTRAP,
                "real_signal_during_issuer_attachment")
        regs = Registers()
        self.ptrace(GETREGS, data=ctypes.byref(regs))
        nr, args = self.snapshot
        require(regs.orig_rax == nr and (regs.rdi, regs.rsi, regs.rdx) == tuple(args[:3]),
                "issuer_not_at_original_idle_syscall")
        require((nr in READS and args[2] == 1) or (nr in POLLS and args[1] == 2),
                "issuer_partial_start_unsupported")
        return {"nr": nr, "args": args}

    def read_frame(self, address, length):
        require(self.stopped and 0 < length <= 65536, "issuer_frame_memory_bound")
        return b"".join(self.read_memory(address + offset, min(8192, length - offset))
                        for offset in range(0, length, 8192))

    def poll_deadline(self, args, nr, now):
        if nr == 7:
            milliseconds = ctypes.c_int(args[2]).value
            require(milliseconds >= 0, "issuer_poll_not_bounded")
            return now + milliseconds / 1000
        require(args[2] != 0, "issuer_ppoll_not_bounded")
        seconds, nanos = struct.unpack("qq", self.read_memory(args[2], 16))
        require(seconds >= 0 and 0 <= nanos < 1000000000, "issuer_ppoll_timeout")
        return now + seconds + nanos / 1000000000
