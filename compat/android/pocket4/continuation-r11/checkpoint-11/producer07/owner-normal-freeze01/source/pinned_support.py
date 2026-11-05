#!/usr/bin/env python3
"""Pinned read-only Main and held-process helpers from actual prefix02, plus owned helpers."""
import ctypes, errno, hashlib, json, os, select, signal, socket, stat, struct, subprocess, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"}
PROPERTIES = ("LoadState", "ActiveState", "SubState", "Description", "InvocationID", "ControlGroup", "MainPID", "ExecMainPID", "ExecMainCode", "ExecMainStatus", "Result", "Transient", "ExecMainStartTimestampMonotonic", "ExecMainExitTimestampMonotonic", "MemoryPeak", "MemorySwapPeak")
NAMES = ("pid", "pid_for_children", "mnt", "cgroup", "user", "net", "ipc", "uts", "time", "time_for_children")
def need(value, message):
    if not value:
        raise RuntimeError(message)


def stamp(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)


def require_cgroup2(fd):
    need(os.uname().machine == "x86_64", "prefix control filesystem ABI is qualified only for x86_64")
    libc = ctypes.CDLL(None, use_errno=True)
    buffer = ctypes.create_string_buffer(512)
    libc.fstatfs.argtypes = (ctypes.c_int, ctypes.c_void_p)
    libc.fstatfs.restype = ctypes.c_int
    need(libc.fstatfs(fd, buffer) == 0 and ctypes.c_long.from_buffer(buffer).value == 0x63677270,
         "unit directory is not cgroup2")


def bounded(fd, name, limit=16384):
    current = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
    try:
        result = bytearray()
        while True:
            part = os.read(current, min(8192, limit + 1 - len(result)))
            if not part:
                break
            result.extend(part)
            need(len(result) <= limit, "bounded read exceeded: " + name)
        return bytes(result)
    finally:
        os.close(current)


def verify_fd(fd, digest, executable=False):
    need(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "invalid artifact digest")
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
         and before.st_mode & 0o6022 == 0 and 0 < before.st_size <= 128 * 1024 * 1024,
         "artifact ownership/type/size/privilege differs")
    if executable:
        need(before.st_mode & 0o111, "artifact is not executable")
        try:
            value = os.getxattr(fd, "security.capability")
        except OSError as error:
            need(error.errno in (errno.ENODATA, errno.ENOTSUP), "file capability inspection failed")
        else:
            need(not value, "privileged file capability can clear parent-death")
    h = hashlib.sha256()
    offset = 0
    while True:
        part = os.pread(fd, 65536, offset)
        if not part:
            break
        h.update(part)
        offset += len(part)
        need(offset <= 128 * 1024 * 1024, "artifact grew beyond limit")
    need(h.hexdigest() == digest and stamp(os.fstat(fd)) == stamp(before), "artifact content changed")
    return before


def pinned(path, digest, executable=False):
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts, "invalid artifact authority path")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        verify_fd(fd, digest, executable)
        return fd
    except BaseException:
        os.close(fd)
        raise


def current_interpreter(digest):
    # /usr/bin/python3 may be a packaging symlink. The current process's
    # kernel-owned exe link pins the actual interpreter rather than guessing
    # a versioned pathname or treating a symlink as a regular artifact.
    fd = os.open("/proc/self/exe", os.O_RDONLY | os.O_CLOEXEC)
    try:
        verify_fd(fd, digest, True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def dead(fd):
    poller = select.poll()
    poller.register(fd, select.POLLIN)
    result = poller.poll(0)
    need(not any(flags & (select.POLLERR | select.POLLNVAL) for _, flags in result), "pidfd poll fault")
    return bool(result)


def await_dead(fd, seconds=4):
    end = time.monotonic() + seconds
    while not dead(fd):
        need(time.monotonic() < end, "original pidfd remains alive")
        time.sleep(0.01)


def pidfd_pid(fd):
    data = Path(f"/proc/self/fdinfo/{fd}").read_text()
    fields = [line.split(":", 1)[1].strip() for line in data.splitlines() if line.startswith("Pid:")]
    need(len(fields) == 1 and fields[0].isdigit() and int(fields[0]) > 0, "pidfd has no live host PID")
    return int(fields[0])


def identity(fd):
    need(not dead(fd), "process dead before identity")
    pid = pidfd_pid(fd)
    proc = os.open(f"/proc/{pid}", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = bounded(proc, "stat").decode().rsplit(")", 1)[1].split()[19]
        fields = dict(line.split(":", 1) for line in bounded(proc, "status").decode().splitlines() if ":" in line)
        value = {"pid": pid, "birth": int(first), "parent": int(fields["PPid"]),
                 "uids": [int(x) for x in fields["Uid"].split()],
                 "gids": [int(x) for x in fields["Gid"].split()],
                 "nspid": [int(x) for x in fields["NSpid"].split()],
                 "cmdline": bounded(proc, "cmdline").decode().split("\0")[:-1],
                 "cgroup": bounded(proc, "cgroup").decode().splitlines()}
        second = bounded(proc, "stat").decode().rsplit(")", 1)[1].split()[19]
        need(first == second and not dead(fd) and pidfd_pid(fd) == pid, "process identity changed")
        return value, proc
    except BaseException:
        os.close(proc)
        raise


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def hex_value(value, length):
    return isinstance(value, str) and len(value) == length and set(value) <= set("0123456789abcdef") and set(value) != {"0"}


def counters(text):
    values = {}
    for line in text.splitlines():
        fields = line.split()
        need(len(fields) == 2 and fields[0] not in values and fields[1].isdigit(), "malformed/duplicate numeric counter")
        values[fields[0]] = fields[1]
    return values


def read_pinned(path, digest, maximum=65536):
    need(hex_value(digest, 64), "external file digest malformed")
    path = Path(path)
    need(path.is_absolute() and ".." not in path.parts, "external authority path malformed")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
             and before.st_mode & 0o6022 == 0 and 0 < before.st_size <= maximum,
             "external artifact owner/type/size/privilege differs")
        raw = bytearray()
        while True:
            part = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not part: break
            raw.extend(part); need(len(raw) <= maximum, "external file grew beyond bound")
        after = os.fstat(fd)
        fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mode, s.st_uid, s.st_gid, s.st_nlink, s.st_mtime_ns, s.st_ctime_ns)
        need(fields(before) == fields(after) and sha(raw) == digest, "external pinned bytes changed")
        return bytes(raw)
    finally:
        os.close(fd)


def read_json_at(directory, name, maximum=65536):
    need(name and "/" not in name and name not in (".", ".."), "not a single owned filename")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
             and info.st_mode & 0o6022 == 0 and 0 < info.st_size <= maximum,
             "owned record metadata differs")
        raw = os.read(fd, maximum + 1)
        need(len(raw) == info.st_size and len(raw) <= maximum, "owned record length changed")
        after = os.fstat(fd)
        need((info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
             (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "owned record changed while read")
        return json.loads(raw), sha(raw)
    finally:
        os.close(fd)


def atomic_json(directory, name, value):
    """Create-only atomic publication; never truncate an old claim or receipt."""
    need(os.uname().machine == "x86_64" and "/" not in name, "atomic record ABI/name differs")
    temporary = "." + name + ".pending"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=directory)
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    libc = ctypes.CDLL(None, use_errno=True)
    method = libc.renameat2
    method.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    method.restype = ctypes.c_int
    if method(directory, temporary.encode(), directory, name.encode(), 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), name)
    os.fsync(directory)
    return sha(raw)


def call(argv, timeout=5, allowed=(0,)):
    value = subprocess.run(argv, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    need(len(value.stdout) <= 65536 and len(value.stderr) <= 65536, "bounded owned command output exceeded")
    need(value.returncode in allowed, "owned command failed: " + repr(argv) + " : " + value.stderr.decode(errors="replace")[-1000:])
    return value


def props(unit):
    result = call(["/usr/bin/systemctl", "show", unit, *["--property=" + key for key in PROPERTIES]], allowed=(0, 1))
    value = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
    need(result.returncode == 0 or value.get("LoadState") == "not-found", "unit observation failed")
    return value


class MainFence:
    """Read-only original process/cgroup authorities; never signals or enters Main."""
    def __init__(self, plan, actor):
        self.expected = plan["main"]; self.actor = actor; self.processes = {}; self.group = None
        try:
            rows = dict(self.expected["framework_binding"]["processes"])
            rows.update(self.expected["retained_processes"])
            for role, value in rows.items():
                fd = os.pidfd_open(value["host_pid"])
                self.processes[role] = fd
            self.group = os.open("/sys/fs/cgroup/system.slice/droidloomd.service",
                                 os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            actor["require_cgroup2"](self.group)
            s = os.fstat(self.group); self.identity = (s.st_dev, s.st_ino)
            self.check()
        except BaseException:
            self.close(); raise

    def capture(self, fd):
        value, directory = self.actor["identity"](fd)
        try:
            return {"host_pid": value["pid"], "parent_host_pid": value["parent"], "start_ticks": value["birth"],
                    "uids": value["uids"], "namespace_pids": value["nspid"],
                    # Match the pinned framework epoch representation of argv padding
                    # only for this read-only Main view; actor/launch argv stays strict.
                    "cmdline": [argument for argument in value["cmdline"] if argument],
                    "cgroup": value["cgroup"], "executable": os.readlink("exe", dir_fd=directory),
                    "namespaces": {name: os.readlink("ns/" + name, dir_fd=directory) for name in ("mnt", "pid")}}
        finally:
            os.close(directory)

    def check(self):
        e = self.expected
        current = props("droidloomd.service")
        need(current.get("ActiveState") == "active" and all(current.get(k) == v for k, v in e["daemon"].items()),
             "original Main unit generation changed")
        need(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == e["framework_binding"]["boot_id"], "boot identity changed")
        expected = dict(e["framework_binding"]["processes"]); expected.update(e["retained_processes"])
        for role, value in expected.items():
            need(self.capture(self.processes[role]) == value, "Main original process changed: " + role)
        path = os.stat("/sys/fs/cgroup/system.slice/droidloomd.service", follow_symlinks=False)
        need((path.st_dev, path.st_ino) == self.identity, "Main cgroup generation changed")
        for key, value in e["resources"].items():
            need(self.actor["bounded"](self.group, key, 128).decode().strip() == value, "Main resource changed: " + key)
        for path, digest in e["artifacts"].items():
            os.close(self.actor["pinned"](path, digest, path.startswith("/usr/bin/")))
        return {"framework_sha256": e["framework_sha256"], "daemon": e["daemon"],
                "held_cgroup_identity": list(self.identity), "resources": e["resources"],
                "original_processes_alive_and_unchanged": True, "installed_contract_unchanged": True}

    def close(self):
        for fd in self.processes.values(): os.close(fd)
        self.processes.clear()
        if self.group is not None: os.close(self.group); self.group = None


