"""Linux-only held process/socket identity and one-thread syscall observation.

No process is spawned, signalled to exit, or granted a product authority here.
Only the selected effect thread is traced; its syscall results are never edited.
"""
import ctypes
import errno
import hashlib
import os
from pathlib import Path
import platform
import select
import signal
import socket
import stat
import struct
import time

from notes_fault_contract import Refused, require

LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.ptrace.restype = ctypes.c_long
LIBC.ptrace.argtypes = (ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
LIBC.syscall.restype = ctypes.c_long
LIBC.process_vm_readv.restype = ctypes.c_ssize_t
SEIZE, INTERRUPT, SYSCALL, DETACH, GETREGS = 0x4206, 0x4207, 24, 17, 12
GET_SYSCALL_INFO, SYSGOOD, WALL = 0x420E, 0x80, 0x40000000
GET_EVENT_MESSAGE, EVENT_EXEC, EVENT_STOP = 0x4201, 4, 128
ARCH_X86_64 = 0xC000003E
READS, WRITES = {0, 45}, {1, 44}


def supported():
    require(platform.system() == "Linux" and platform.machine() == "x86_64", "unsupported_architecture")


def proc_identity(pid, tid=None):
    prefix = Path(f"/proc/{pid}") if tid is None else Path(f"/proc/{pid}/task/{tid}")
    raw = (prefix / "stat").read_text()
    tail = raw[raw.rindex(")") + 2:].split()
    status = {}
    for line in (prefix / "status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("Uid", "Gid", "Tgid", "TracerPid"):
            status[key] = [int(item) for item in value.split()]
    return {"pid": pid if tid is None else tid, "ppid": int(tail[1]), "start_ticks": int(tail[19]),
            "uid": status["Uid"], "gid": status["Gid"], "tgid": status["Tgid"][0], "tracer": status["TracerPid"][0],
            "state": tail[0]}


class HeldProcess:
    def __init__(self, binding):
        supported()
        self.pid = binding["pid"]
        require(type(self.pid) is int and self.pid > 1, "process_pid")
        self.pidfd = os.pidfd_open(self.pid)
        self.exe_fd = None
        try:
            self.identity = proc_identity(self.pid)
            require(self.identity["start_ticks"] == binding["start_ticks"], "process_birth")
            require(self.identity["uid"] == [binding["uid"]] * 4, "process_uid")
            require(self.identity["gid"] == [binding["gid"]] * 4, "process_gid")
            require(self.identity["tracer"] == 0, "already_traced")
            path = Path(binding["executable"])
            require(path.is_absolute() and path.resolve(strict=True) == path, "executable_path")
            self.exe_fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            self.executable = os.fstat(self.exe_fd)
            require(stat.S_ISREG(self.executable.st_mode) and self.executable.st_size <= 128 * 1024 * 1024,
                    "executable_not_regular_or_bounded")
            require(self.executable.st_uid == 0 and not self.executable.st_mode & 0o022,
                    "executable_not_root_custodied")
            self.sha256 = binding["sha256"]
            require(self.file_digest() == self.sha256, "executable_digest")
            self.verify()
        except BaseException:
            self.close()
            raise

    def file_digest(self):
        value, offset = hashlib.sha256(), 0
        while offset < self.executable.st_size:
            data = os.pread(self.exe_fd, min(1024 * 1024, self.executable.st_size - offset), offset)
            require(data, "held_executable_truncated")
            value.update(data)
            offset += len(data)
        return value.hexdigest()

    def verify(self, *, tracer=None, rehash=False):
        require(not select.select([self.pidfd], [], [], 0)[0], "process_ended")
        current = proc_identity(self.pid)
        require(current["start_ticks"] == self.identity["start_ticks"]
                and current["uid"] == self.identity["uid"]
                and current["gid"] == self.identity["gid"]
                and current["ppid"] == self.identity["ppid"], "process_identity_changed")
        if tracer is not None:
            require(current["tracer"] in (0, tracer), "foreign_tracer")
        actual = os.stat(f"/proc/{self.pid}/exe")
        expected = self.executable
        require((actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns)
                == (expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns, expected.st_ctime_ns),
                "process_executable_changed")
        if rehash:
            require(self.file_digest() == self.sha256, "held_executable_changed")

    def close(self):
        if self.exe_fd is not None:
            os.close(self.exe_fd)
            self.exe_fd = None
        if self.pidfd is not None:
            os.close(self.pidfd)
            self.pidfd = None


class HeldEffectSocket:
    def __init__(self, app, fd, session):
        supported()
        self.app, self.fd = app, fd
        result = LIBC.syscall(ctypes.c_long(438), ctypes.c_int(app.pidfd), ctypes.c_int(fd), ctypes.c_uint(0))
        if result == -1:
            error = ctypes.get_errno()
            raise OSError(error, "pidfd_getfd unavailable for the selected App")
        try:
            self.socket = socket.socket(fileno=result)
        except BaseException:
            try:
                os.close(result)
            except OSError:
                pass
            raise
        try:
            require(self.socket.family == socket.AF_UNIX
                    and self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM,
                    "effect_socket_type")
            require(self.socket.getsockname() in ("", b"") and self.socket.getpeername() in ("", b""),
                    "effect_socket_not_inherited_pair")
            peer = struct.unpack("iII", self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            require(peer == (session.pid, session.identity["uid"][0], session.identity["gid"][0]),
                    "effect_pair_creator_mismatch")
            self.identity = os.fstat(self.socket.fileno())
            self.verify()
        except BaseException:
            self.socket.close()
            raise

    def verify(self):
        current = os.stat(f"/proc/{self.app.pid}/fd/{self.fd}")
        require(stat.S_ISSOCK(current.st_mode)
                and (current.st_dev, current.st_ino) == (self.identity.st_dev, self.identity.st_ino),
                "effect_socket_replaced")

    def close(self):
        self.socket.close()


class Entry(ctypes.Structure):
    _fields_ = [("nr", ctypes.c_uint64), ("args", ctypes.c_uint64 * 6)]


class Exit(ctypes.Structure):
    _fields_ = [("rval", ctypes.c_int64), ("is_error", ctypes.c_uint8)]


class Payload(ctypes.Union):
    _fields_ = [("entry", Entry), ("exit", Exit), ("padding", ctypes.c_uint64 * 8)]


class SyscallInfo(ctypes.Structure):
    _fields_ = [("op", ctypes.c_uint8), ("pad", ctypes.c_uint8 * 3), ("arch", ctypes.c_uint32),
                ("ip", ctypes.c_uint64), ("sp", ctypes.c_uint64), ("payload", Payload)]


class Registers(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                "r15 r14 r13 r12 rbp rbx r11 r10 r9 r8 rax rcx rdx rsi rdi orig_rax rip cs eflags rsp ss fs_base gs_base ds es fs gs".split()]


class Iovec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("length", ctypes.c_size_t)]


class TraceThread:
    def __init__(self, app, tid, snapshot, birth):
        self.app, self.tid, self.snapshot = app, tid, snapshot
        self.original_tid = tid
        self.birth = birth
        require(proc_identity(app.pid, tid)["start_ticks"] == birth, "effect_thread_birth_changed")
        self.attached, self.stopped, self.deliver = False, False, 0
        self.events = []
        self.omitted_events, self.cleanup_failed = 0, False
        self.stopped_tid = None
        self.paused_at, self.total_pause, self.max_pause, self.stops = None, 0.0, 0.0, 0

    def record(self, event):
        if len(self.events) < 64:
            self.events.append(event)
        else:
            self.omitted_events += 1

    def ptrace(self, request, addr=0, data=0, *, tid=None):
        selected = self.tid if tid is None else tid
        require(selected in (self.original_tid, self.app.pid), "ptrace_outside_held_app")
        result = LIBC.ptrace(request, selected, ctypes.c_void_p(addr), data)
        if result == -1:
            error = ctypes.get_errno()
            raise OSError(error, f"ptrace request {request}")
        return result

    def attach(self, deadline):
        self.ptrace(SEIZE, data=ctypes.c_void_p(1 | 0x10))
        self.attached = True
        self.record({"attached_monotonic": time.monotonic(), "tid": self.tid, "start_ticks": self.birth})
        self.ptrace(INTERRUPT)
        status = self.wait(deadline)
        require(status >> 16 == EVENT_STOP and os.WSTOPSIG(status) == signal.SIGTRAP,
                "real_signal_during_attachment")
        regs = Registers()
        self.ptrace(GETREGS, data=ctypes.byref(regs))
        nr, args = self.snapshot
        require(regs.orig_rax == nr and tuple((regs.rdi, regs.rsi, regs.rdx)) == tuple(args[:3]),
                "effect_thread_not_at_original_idle_read")
        require(nr in READS and args[2] == 4, "partial_start_not_supported")
        return {"nr": nr, "args": args}

    def verify(self):
        identity = proc_identity(self.app.pid, self.tid)
        require(identity["start_ticks"] == self.birth and identity["tgid"] == self.app.pid
                and identity["tracer"] == os.getpid(), "traced_thread_identity")

    def wait(self, deadline, *, cancelled=None):
        while time.monotonic() < deadline:
            require(cancelled is None or not cancelled(), "controller_cancelled")
            # A nonleader exec becomes the already-held TGID. Never wait for
            # arbitrary children, nor interpret ESRCH on the old TID as detach.
            for selected in dict.fromkeys((self.tid, self.app.pid)):
                try:
                    got, status = os.waitpid(selected, os.WNOHANG | WALL)
                except ChildProcessError:
                    continue
                if not got:
                    continue
                require(os.WIFSTOPPED(status), "effect_thread_ended")
                self.stopped, self.stopped_tid = True, got
                self.paused_at = time.monotonic()
                self.stops += 1
                identity = proc_identity(self.app.pid, got)
                require(identity["tgid"] == self.app.pid and identity["tracer"] == os.getpid(),
                        "waited_task_outside_owned_app")
                event, stop = status >> 16, os.WSTOPSIG(status)
                self.deliver = stop if event == 0 and stop != signal.SIGTRAP | SYSGOOD else 0
                if event == EVENT_STOP and stop in (signal.SIGSTOP, signal.SIGTSTP, signal.SIGTTIN, signal.SIGTTOU):
                    self.deliver = stop
                if event == EVENT_EXEC:
                    former = ctypes.c_ulong()
                    self.ptrace(GET_EVENT_MESSAGE, data=ctypes.byref(former), tid=got)
                    self.record({"exec_stop_monotonic": time.monotonic(), "from_tid": int(former.value), "to_tid": got})
                    require(int(former.value) == self.original_tid and got == self.app.pid,
                            "unproven_exec_thread_migration")
                    self.tid = got  # Cleanup only; this event always refuses a fault.
                    raise Refused("effect_thread_exec_invalidates_boundary")
                require(got == self.tid, "unexpected_app_group_stop")
                self.verify()
                return status
            time.sleep(0.001)
        raise Refused("controller_deadline")

    def resume(self, deliver=0):
        self.ptrace(SYSCALL, data=ctypes.c_void_p(deliver))
        if deliver:
            self.record({"forwarded_signal": deliver, "monotonic": time.monotonic()})
        self.finished_pause()
        self.stopped = False
        self.stopped_tid = None
        self.deliver = 0

    def finished_pause(self):
        if self.paused_at is not None:
            duration = time.monotonic() - self.paused_at
            self.total_pause += duration
            self.max_pause = max(duration, self.max_pause)
            self.paused_at = None

    def syscall_info(self):
        info = SyscallInfo()
        size = self.ptrace(GET_SYSCALL_INFO, ctypes.sizeof(info), ctypes.byref(info))
        require(size >= 24 and info.arch == ARCH_X86_64, "unsupported_syscall_info")
        if info.op == 1:
            require(size >= 80, "short_syscall_entry_info")
            return "entry", {"nr": int(info.payload.entry.nr), "args": list(info.payload.entry.args)}
        if info.op == 2:
            require(size >= 33, "short_syscall_exit_info")
            return "exit", int(info.payload.exit.rval)
        raise Refused("unexpected_syscall_stop")

    def read_memory(self, address, length):
        require(self.stopped and 0 < length <= 8192, "bounded_stopped_memory_read")
        self.verify()
        buffer = ctypes.create_string_buffer(length)
        local = Iovec(ctypes.cast(buffer, ctypes.c_void_p), length)
        remote = Iovec(ctypes.c_void_p(address), length)
        result = LIBC.process_vm_readv(self.app.pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0)
        if result != length:
            raise OSError(ctypes.get_errno() or errno.EIO, "incomplete bounded process memory read")
        return bytes(buffer.raw)

    def close(self):
        if not self.attached:
            return
        failures = []
        try:
            if not self.stopped:
                try:
                    self.ptrace(INTERRUPT)
                except OSError as error:
                    if error.errno != errno.ESRCH:
                        failures.append(str(error))
                try:
                    self.wait(time.monotonic() + 1)
                except (OSError, Refused, ChildProcessError) as error:
                    # EXEC may have moved the stopped tracee to the held TGID;
                    # wait records that exact stop before refusing the boundary.
                    if not self.stopped:
                        failures.append(str(error))
            if self.stopped:
                try:
                    self.ptrace(DETACH, data=ctypes.c_void_p(self.deliver), tid=self.stopped_tid)
                    self.finished_pause()
                    self.record({"detached_monotonic": time.monotonic(), "tid": self.stopped_tid,
                                 "forwarded_signal": self.deliver})
                    self.stopped, self.stopped_tid = False, None
                except OSError as error:
                    failures.append(str(error))
            owned = []
            for selected in dict.fromkeys((self.original_tid, self.app.pid)):
                try:
                    identity = proc_identity(self.app.pid, selected)
                    if identity["tracer"] == os.getpid():
                        owned.append(selected)
                except FileNotFoundError:
                    pass
            self.attached = bool(owned)
            if owned or self.stopped:
                failures.append("held App still has a traced/stopped task")
        except (OSError, Refused, ChildProcessError) as error:
            failures.append(str(error))
        self.cleanup_failed = bool(failures)
        for error in failures:
            self.record({"cleanup_error": error})
