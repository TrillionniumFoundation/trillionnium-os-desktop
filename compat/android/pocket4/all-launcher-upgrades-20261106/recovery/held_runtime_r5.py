"""Descriptor-bound namespace entry and private Android classpath admission.

No numeric PID is used by the command entry helper. The caller keeps the
original Main/private epoch guards and owns full cell/process-tree cleanup.
"""
from contextlib import contextmanager
import ctypes
import errno
import fcntl
import hashlib
import os
from pathlib import PurePosixPath
import re
import select
import stat
import threading
import time

NS_TYPES = {"mnt": 0x00020000, "pid": 0x20000000, "uts": 0x04000000,
            "ipc": 0x08000000, "net": 0x40000000, "cgroup": 0x02000000}
REQUIRED_CLASSPATHS = ("BOOTCLASSPATH", "DEX2OATBOOTCLASSPATH")
ENV_LIMIT = 256 * 1024
PATH_COUNT_LIMIT = 256
PATH_BYTES_LIMIT = 32768
FILE_LIMIT = 128 * 1024 * 1024
TOTAL_FILE_LIMIT = 768 * 1024 * 1024
CLASSPATH_SECONDS = 45
HELPER_SOURCE_SHA = "adf5b08f7854bec061ab8d2a208f3414339701c816218881e6550afde2e6c31c"
HELPER_BINARY_SHA = "21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689"

class BindingError(RuntimeError):
    pass

def require(value, message):
    if not value:
        raise BindingError(message)

def deadline_check(deadline):
    require(time.monotonic() <= deadline, "bounded read deadline exceeded")

def fd_record(fd):
    value = os.fstat(fd)
    return {"device": value.st_dev, "inode": value.st_ino, "mode": value.st_mode,
            "uid": value.st_uid, "gid": value.st_gid, "bytes": value.st_size,
            "mtime_ns": value.st_mtime_ns, "nlink": value.st_nlink}

def read_fd(fd, limit, deadline):
    chunks = []
    count = 0
    while True:
        deadline_check(deadline)
        part = os.read(fd, min(65536, limit + 1 - count))
        if not part:
            return b"".join(chunks)
        count += len(part)
        require(count <= limit, "bounded read byte limit exceeded")
        chunks.append(part)

def read_at(directory_fd, relative, limit, deadline):
    require(not relative.startswith("/") and ".." not in relative.split("/"),
            "proc relative path is invalid")
    fd = os.open(relative, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                 dir_fd=directory_fd)
    try:
        return read_fd(fd, limit, deadline)
    finally:
        os.close(fd)

def proc_identity_at(proc_fd, pid, deadline):
    raw = read_at(proc_fd, "stat", 8192, deadline).decode("utf-8", "strict")
    status_raw = read_at(proc_fd, "status", 65536, deadline).decode("utf-8", "strict")
    status = dict(line.split(":", 1) for line in status_raw.splitlines() if ":" in line)
    require(raw.split("(", 1)[0].strip() == str(pid), "held proc PID differs")
    fields = raw.rsplit(")", 1)[1].split()
    namespaces = {name: os.readlink("ns/" + name, dir_fd=proc_fd) for name in NS_TYPES}
    return {"pid": pid, "start": fields[19], "uid": status["Uid"].split(),
            "nspid": status.get("NSpid", "").split(), "ppid": int(status["PPid"]),
            "ns": namespaces, "exe": os.readlink("exe", dir_fd=proc_fd),
            "cgroup": read_at(proc_fd, "cgroup", 16384, deadline).decode("utf-8", "strict")}

def pidfd_alive(fd):
    poller = select.poll()
    poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
    return not poller.poll(0)

class OpenHow(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint64), ("mode", ctypes.c_uint64),
                ("resolve", ctypes.c_uint64)]

def guest_path(path):
    require(isinstance(path, str) and path.startswith("/") and not path.startswith("//")
            and "\x00" not in path and len(path.encode("utf-8")) <= 4096,
            "guest path is not a bounded absolute path")
    require(path == "/" or all(part not in ("", ".", "..") for part in path[1:].split("/")),
            "guest path contains an empty or dot component")
    return path

def open_in_root(root_fd, path, flags=os.O_RDONLY):
    path = guest_path(path)
    require(os.uname().machine == "x86_64", "qualified openat2 entry is x86_64 only")
    # IN_ROOT resolves absolute symlinks inside the held Android root.
    # NO_MAGICLINKS excludes proc magic-link escape. APEX mount crossings are
    # expected, so NO_XDEV and BENEATH are intentionally absent.
    how = OpenHow(flags | os.O_CLOEXEC, 0, 0x10 | 0x02)
    libc = ctypes.CDLL(None, use_errno=True)
    syscall = libc.syscall
    syscall.restype = ctypes.c_long
    result = syscall(ctypes.c_long(437), ctypes.c_int(root_fd),
                     ctypes.c_char_p(path.encode("utf-8")),
                     ctypes.byref(how), ctypes.c_size_t(ctypes.sizeof(how)))
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), path)
    return int(result)

class HeldTarget:
    """One immutable init generation; no rebind after acquisition or close."""
    def __init__(self, expected, helper_path, helper_sha256=HELPER_BINARY_SHA):
        self.expected = expected
        self.helper_path = str(helper_path)
        self.helper_sha256 = helper_sha256
        self._lock = threading.RLock()
        self._active = 0
        self._unjoined_command = False
        self._admission_closed = False
        self._closed = False
        self._fds = []
        self.proc_fd = self.pid_fd = self.root_fd = -1
        self.namespaces = {}
        try:
            require(set(expected["ns"]) == set(NS_TYPES), "complete six-namespace identity required")
            pid = expected["pid"]
            self.proc_fd = self._own(os.open("/proc/" + str(pid),
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW))
            self.pid_fd = self._own(os.pidfd_open(pid, 0))
            self._verify_proc()
            for name, kind in NS_TYPES.items():
                fd = self._own(os.open("ns/" + name, os.O_RDONLY | os.O_CLOEXEC,
                                       dir_fd=self.proc_fd))
                require(fcntl.ioctl(fd, 0xb703) == kind, "namespace FD has incorrect type: " + name)
                match = re.fullmatch(re.escape(name) + r":\[(\d+)\]", expected["ns"][name])
                require(match is not None and os.fstat(fd).st_ino == int(match[1]),
                        "namespace FD differs from held proc identity: " + name)
                self.namespaces[name] = fd
            self.root_fd = self._own(os.open("root", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC,
                                            dir_fd=self.proc_fd))
            require(os.readlink("cwd", dir_fd=self.proc_fd) == "/", "init cwd is not root")
            self.root_record = fd_record(self.root_fd)
            require(stat.S_ISDIR(self.root_record["mode"]), "held root is not a directory")
            self._verify_proc()
            self.record = {"init": expected, "proc": fd_record(self.proc_fd),
                           "root": self.root_record,
                           "namespaces": {name: fd_record(fd) for name, fd in self.namespaces.items()},
                           "pidfd_held": True, "numeric_target_used_for_entry": False,
                           "helper_sha256": helper_sha256}
        except BaseException:
            for fd in reversed(self._fds):
                os.close(fd)
            self._fds.clear()
            self._closed = True
            raise

    def _own(self, fd):
        if fd < 3:
            os.close(fd)
            raise BindingError("authority descriptor would alias a standard stream")
        self._fds.append(fd)
        return fd

    def _verify_proc(self):
        require(not self._closed and pidfd_alive(self.pid_fd), "original init pidfd is no longer alive")
        require(proc_identity_at(self.proc_fd, self.expected["pid"], time.monotonic() + 3)
                == self.expected, "held init identity changed")
        require(pidfd_alive(self.pid_fd), "original init exited during verification")
        if self.root_fd >= 0:
            current = os.open("root", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.proc_fd)
            try:
                a, b = os.fstat(current), os.fstat(self.root_fd)
                require((a.st_dev, a.st_ino) == (b.st_dev, b.st_ino), "init changed its root")
            finally:
                os.close(current)

    def verify(self):
        with self._lock:
            require(not self._admission_closed, "held entry admission is closed")
            self._verify_proc()
            root = os.fstat(self.root_fd)
            require((root.st_dev, root.st_ino) == (self.root_record["device"], self.root_record["inode"]),
                    "held root inode changed")

    @contextmanager
    def lease(self):
        with self._lock:
            require(not self._admission_closed, "held entry admission is closed")
            self._verify_proc()
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
                require(self._active >= 0, "held entry lease accounting failed")

    @contextmanager
    def entry(self, command):
        with self.lease():
            require(command and str(command[0]).startswith("/"), "entry command must be absolute")
            authority = (self.root_fd, *self.namespaces.values())
            require(len(set(authority)) == 7 and all(fd >= 3 for fd in authority),
                    "complete unique held authority set required")
            argv = [self.helper_path, "--parent-pid=" + str(os.getpid()),
                    "--root-fd=" + str(self.root_fd)]
            argv += ["--" + name + "-fd=" + str(fd) for name, fd in self.namespaces.items()]
            argv += ["--", *map(str, command)]
            # The procdir and init pidfd are not passed. The helper reasserts
            # CLOEXEC on precisely these authorities before the final exec.
            yield argv, authority

    def open_root(self, path, flags=os.O_RDONLY):
        with self.lease():
            return open_in_root(self.root_fd, path, flags)

    def read_file(self, path, limit, *, single_link=False, deadline=None):
        deadline = deadline or time.monotonic() + 5
        fd = self.open_root(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = fd_record(fd)
            require(stat.S_ISREG(before["mode"]) and before["bytes"] <= limit,
                    "owned file is not bounded and regular")
            require(not single_link or before["nlink"] == 1, "owned file has multiple hard links")
            value = read_fd(fd, limit, deadline)
            require(fd_record(fd) == before and len(value) == before["bytes"],
                    "owned file changed during read")
            return value, before
        finally:
            os.close(fd)

    def exists(self, path):
        try:
            fd = self.open_root(path, os.O_PATH | os.O_NOFOLLOW)
        except FileNotFoundError:
            return False
        else:
            os.close(fd)
            return True

    def poison_unjoined_command(self):
        with self._lock:
            self._admission_closed = True
            self._unjoined_command = True

    def seal_admission(self):
        with self._lock:
            self._admission_closed = True

    def close(self):
        with self._lock:
            self._admission_closed = True
            require(self._active == 0, "held entry still has active commands/readers")
            require(not self._unjoined_command, "unjoined diagnostic child; authority FDs retained until controller exit")
            if self._closed:
                return
            errors = []
            for fd in reversed(self._fds):
                try:
                    os.close(fd)
                except OSError as error:
                    errors.append(repr(error))
            self._fds.clear()
            self._closed = True
            require(not errors, "authority FD release failed: " + repr(errors))

def selected_classpaths(raw):
    require(len(raw) <= ENV_LIMIT and raw.endswith(b"\0"), "zygote environ is incomplete or oversized")
    result = {}
    for entry in raw.split(b"\0"):
        name, separator, value = entry.partition(b"=")
        if name.decode("ascii", "ignore") not in REQUIRED_CLASSPATHS:
            continue
        require(separator and name in (b"BOOTCLASSPATH", b"DEX2OATBOOTCLASSPATH"),
                "required classpath key is not exact ASCII")
        key = name.decode("ascii")
        require(key not in result, "duplicate required classpath key")
        require(value and len(value) <= PATH_BYTES_LIMIT, "required classpath is empty or oversized")
        text = value.decode("ascii", "strict")
        parts = text.split(":")
        require(0 < len(parts) <= PATH_COUNT_LIMIT, "classpath entry count exceeded")
        for path in parts:
            guest_path(path)
            require(path.endswith(".jar") and all(ord(c) >= 33 and ord(c) < 127 for c in path),
                    "classpath entry is not a plain absolute jar path")
        require(len(set(parts)) == len(parts), "duplicate path in one classpath")
        result[key] = text
    require(set(result) == set(REQUIRED_CLASSPATHS), "required private zygote classpath keys are missing")
    return result

def hash_classpaths(target, values, deadline):
    unique = list(dict.fromkeys(path for key in REQUIRED_CLASSPATHS for path in values[key].split(":")))
    require(len(unique) <= PATH_COUNT_LIMIT, "combined classpath count exceeded")
    files = []
    total = 0
    for path in unique:
        deadline_check(deadline)
        fd = target.open_root(path, os.O_RDONLY)
        try:
            before = fd_record(fd)
            require(stat.S_ISREG(before["mode"]) and 0 < before["bytes"] <= FILE_LIMIT,
                    "classpath file is absent, empty, non-regular or oversized")
            total += before["bytes"]
            require(total <= TOTAL_FILE_LIMIT, "combined classpath byte budget exceeded")
            digest = hashlib.sha256()
            count = 0
            while True:
                deadline_check(deadline)
                block = os.read(fd, min(131072, before["bytes"] + 1 - count))
                if not block:
                    break
                count += len(block)
                require(count <= before["bytes"], "classpath grew during hashing")
                digest.update(block)
            require(count == before["bytes"] and fd_record(fd) == before, "classpath changed during hashing")
            files.append({"path": path, **before, "sha256": digest.hexdigest()})
        finally:
            os.close(fd)
    return files, total

class HeldZygoteRoot:
    """Read one fixed zygote's actual mount/root view; never enter it."""
    def __init__(self, expected, deadline):
        self.expected = expected
        self.deadline = deadline
        self.fds = []
        self.proc_fd = self.pid_fd = self.mnt_fd = self.root_fd = -1
        try:
            pid = expected["host_pid"]
            self.proc_fd = self._own(os.open("/proc/" + str(pid),
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW))
            self.pid_fd = self._own(os.pidfd_open(pid, 0))
            require(pidfd_alive(self.pid_fd), "private zygote exited before root acquisition")
            self.identity = proc_identity_at(self.proc_fd, pid, deadline)
            actual = self.identity
            require(int(actual["start"]) == expected["start_ticks"] and
                    actual["uid"] == [str(value) for value in expected["uids"]] and
                    actual["ns"]["pid"] == expected["namespaces"]["pid"] and
                    actual["ns"]["mnt"] == expected["namespaces"]["mnt"] and
                    actual["exe"] == expected["executable"] and
                    actual["ppid"] == expected["parent_host_pid"] and
                    [int(value) for value in actual["nspid"]] == expected["namespace_pids"] and
                    actual["cgroup"].splitlines() == expected["cgroup"],
                    "held zygote procdir differs from the fixed epoch")
            self.mnt_fd = self._own(os.open("ns/mnt", os.O_RDONLY | os.O_CLOEXEC,
                                             dir_fd=self.proc_fd))
            match = re.fullmatch(r"mnt:\[(\d+)\]", expected["namespaces"]["mnt"])
            require(match is not None and fcntl.ioctl(self.mnt_fd, 0xb703) == NS_TYPES["mnt"]
                    and os.fstat(self.mnt_fd).st_ino == int(match[1]),
                    "held zygote mount namespace differs")
            self.root_fd = self._own(os.open("root", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC,
                                              dir_fd=self.proc_fd))
            self.root_record = fd_record(self.root_fd)
            require(stat.S_ISDIR(self.root_record["mode"]), "zygote root is not a directory")
            self.verify()
        except BaseException:
            self.close()
            raise

    def _own(self, fd):
        if fd < 3:
            os.close(fd)
            raise BindingError("zygote authority aliases a standard descriptor")
        self.fds.append(fd)
        return fd

    def verify(self):
        deadline_check(self.deadline)
        require(pidfd_alive(self.pid_fd) and
                proc_identity_at(self.proc_fd, self.expected["host_pid"], self.deadline) == self.identity,
                "fixed zygote generation or mount namespace changed")
        fd = os.open("root", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.proc_fd)
        try:
            current = os.fstat(fd)
            require((current.st_dev, current.st_ino) ==
                    (self.root_record["device"], self.root_record["inode"]),
                    "fixed zygote changed its root")
        finally:
            os.close(fd)
        require(pidfd_alive(self.pid_fd), "fixed zygote exited during root verification")

    def open_root(self, path, flags=os.O_RDONLY):
        return open_in_root(self.root_fd, path, flags)

    def close(self):
        failures = []
        for fd in reversed(self.fds):
            try:
                os.close(fd)
            except OSError as error:
                failures.append(repr(error))
        self.fds.clear()
        require(not failures, "zygote root FD release failed: " + repr(failures))

def hash_classpaths_paired(target, zygote_view, values, deadline):
    """Prove each jar resolves to the same held file in both actual roots."""
    unique = list(dict.fromkeys(path for key in REQUIRED_CLASSPATHS for path in values[key].split(":")))
    require(len(unique) <= PATH_COUNT_LIMIT, "combined classpath count exceeded")
    files = []
    total = 0
    for path in unique:
        deadline_check(deadline)
        init_fd = target.open_root(path, os.O_RDONLY)
        zygote_fd = -1
        try:
            zygote_fd = zygote_view.open_root(path, os.O_RDONLY)
            first, second = fd_record(init_fd), fd_record(zygote_fd)
            require(stat.S_ISREG(first["mode"]) and stat.S_ISREG(second["mode"]) and
                    0 < first["bytes"] <= FILE_LIMIT and 0 < second["bytes"] <= FILE_LIMIT,
                    "classpath file is absent, empty, non-regular or oversized")
            require((first["device"], first["inode"], first["bytes"]) ==
                    (second["device"], second["inode"], second["bytes"]),
                    "init and zygote resolve the classpath jar to different backing files")
            total += first["bytes"]
            require(total <= TOTAL_FILE_LIMIT, "combined classpath byte budget exceeded")
            digest = hashlib.sha256()
            count = 0
            while True:
                deadline_check(deadline)
                block = os.read(init_fd, min(131072, first["bytes"] + 1 - count))
                if not block:
                    break
                count += len(block)
                require(count <= first["bytes"], "classpath grew during hashing")
                digest.update(block)
            require(count == first["bytes"] and fd_record(init_fd) == first and
                    fd_record(zygote_fd) == second,
                    "classpath backing or metadata changed during dual-view admission")
            files.append({"path": path, **first, "sha256": digest.hexdigest(),
                          "init_view": first, "zygote_view": second,
                          "same_backing_verified_by_held_fds": True})
        finally:
            if zygote_fd >= 0:
                os.close(zygote_fd)
            os.close(init_fd)
    return files, total

def bind_classpaths(target, epoch, process_identity, guard_check):
    """Read selected keys and prove jar equivalence across the two held roots."""
    guard_check()
    expected = epoch["binding"]["processes"]["zygote64"]
    require(expected["namespaces"]["pid"] == target.expected["ns"]["pid"],
            "zygote is not in the private init PID namespace")
    require(process_identity(expected["host_pid"]) == expected,
            "private zygote changed before environment read")
    deadline = time.monotonic() + CLASSPATH_SECONDS
    view = HeldZygoteRoot(expected, deadline)
    try:
        raw = read_at(view.proc_fd, "environ", ENV_LIMIT, deadline)
        values = selected_classpaths(raw)
        # No unrelated environment value is retained.
        del raw
        files, total = hash_classpaths_paired(target, view, values, deadline)
        again = selected_classpaths(read_at(view.proc_fd, "environ", ENV_LIMIT, deadline))
        require(again == values, "private zygote classpath changed during admission")
        view.verify()
        require(process_identity(expected["host_pid"]) == expected,
                "private zygote generation changed after environment admission")
        target.verify()
        guard_check()
        return values, {"schema": 2, "source": "fixed private zygote held procdir only",
            "zygote": expected, "required_keys": list(REQUIRED_CLASSPATHS),
            "values": values, "files": files, "total_bytes": total,
            "limits": {"environ_bytes": ENV_LIMIT, "path_count": PATH_COUNT_LIMIT,
                       "per_file_bytes": FILE_LIMIT, "total_file_bytes": TOTAL_FILE_LIMIT,
                       "deadline_seconds": CLASSPATH_SECONDS},
            "root": target.root_record, "zygote_root": view.root_record,
            "zygote_mount_namespace": fd_record(view.mnt_fd),
            "command_mount_namespace": fd_record(target.namespaces["mnt"]),
            "resolution_contract": "same dev/inode/size from simultaneously held init-root and zygote-root file descriptors; metadata stable around streaming hash",
            "different_mount_namespaces_permitted": True,
            "different_backing_files_permitted": False,
            "main_classpath_read": False}
    finally:
        view.close()
