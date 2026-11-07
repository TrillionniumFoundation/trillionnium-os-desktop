from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import time
import traceback

CONTROL_REVISION = 'producer16-bounded-init-log01'
BASE = Path('/home/alex/work/pocket4-supervisor-lmkd-child-exit-r11-build-15-01')
SOURCE = BASE / "candidate"
OUT = Path('/home/alex/work/pocket4-supervisor-lmkd-init-log-r11-build-16-02')
CANDIDATE = OUT / "candidate"
TARGET = OUT / "target"
CARGO = '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/cargo'
RUST_SYSROOT = '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu'
RUSTC = RUST_SYSROOT + '/bin/rustc'
RUSTDOC = RUST_SYSROOT + '/bin/rustdoc'
DIRECT_TOOL_PINS = {'/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/cargo': {'bytes': 40753664, 'sha256': '9548937d530bf439ff1ba47a3b2bd26eeb9c3aff1961c20c01798613de922578'}, '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/rustc': {'bytes': 656704, 'sha256': 'd32249a7c3bfcfc67b471460386e46323accae7125e344567a12d5664d99bb57'}, '/home/alex/.rustup/toolchains/1.93.0-x86_64-unknown-linux-gnu/bin/rustdoc': {'bytes': 13173040, 'sha256': 'ece7829b8e7448a9d59c88080e2b16253b885c560f792002837901c7f24b7695'}}
DIRECT_TOOL_VERSIONS = {'cargo': 'cargo 1.93.0 (083ac5135 2025-12-15)\n', 'rustc': 'rustc 1.93.0 (254b59607 2026-01-19)\nbinary: rustc\ncommit-hash: 254b59607d4417e9dffbc307138ae5c86280fe4c\ncommit-date: 2026-01-19\nhost: x86_64-unknown-linux-gnu\nrelease: 1.93.0\nLLVM version: 21.1.8\n'}
DIRECT_TOOL_OBSERVATION_SHA = '60f543d7a5fc552add6824160794c2c2e8b1a5f908401aab9b176a0a737789fb'
DIRECT_TOOL_ACTUAL_BUILD_SHA = '2d6c80a29e957b1e97764d8785257eb47c3d0b899f301e64c9a9c418e96ea0ab'

PRIOR_RECEIPT = BASE / "compile-result.json"
PRIOR_RECEIPT_SHA = '3327495b8cc3302dcc18ac72a7495f88d3354788404d2b05d1194d1e6e89ee30'
PRIOR_INVENTORY_SHA = 'acd7a623dc28f83363d67aec1d4befe64c85cf852fa564312783005abc7a05b8'
ORIGINAL_DIFF_SHA = 'cf5ba26e0f3efe86b6eec6ed140c8688df4ebc24f043dbdee4a07b94239744ef'
EXACT_OVERLAY = {
    'runtime/droidloom-supervisor/src/relay_lifecycle/audit.rs': (34440, '7322b9a314d2431af687350dc133b40f25dc244931b2a28d25cf50a4bbcc32a4'),
    'runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs': (31106, 'c821e6c62906c9f4d4f27c22781f7521518f715588ca3be791055d32fbed174f'),
    'runtime/droidloom-supervisor/src/relay_lifecycle/init_log.rs': (15994, 'bd376b6b334776c25ec1276acb4c0232d00baaf80c6051e10ec2da75f7100ac2'),
    'runtime/droidloom-supervisor/src/relay_lifecycle/mod.rs': (357, '2807edf9538722a11909c2702770f24624343429e18fe53db70db82f6dfad1be'),
    'runtime/droidloom-supervisor/src/relay_lifecycle/owner.rs': (41593, '5e00ba0a96de8c972663f6293e214f670b44699cdb6102c167e2508b2967fb32'),
}
NEW_SOURCE_FILES = {'runtime/droidloom-supervisor/src/relay_lifecycle/init_log.rs'}
BINARIES = ["droidloomd", "droidloom-supervisor", "droidloom-psi-owner", "owned-ipc-controls"]
EXPECTED_TEST_TARGETS = {
    ("droidloom_pressure_relay", "lib"),
    ("droidloom_supervisor", "lib"),
}
SOURCE_LIMIT = 128 * 1024 * 1024
LOG_LIMIT = 8 * 1024 * 1024

def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

def stamp(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def read_regular(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
             "not a bounded regular file: " + str(path))
        parts = []
        length = 0
        while True:
            block = os.read(fd, min(65536, maximum + 1 - length))
            if not block:
                break
            parts.append(block)
            length += len(block)
            need(length <= maximum, "file exceeded read bound: " + str(path))
        after = os.fstat(fd)
        need(stamp(before) == stamp(after) and length == before.st_size,
             "file changed during held read: " + str(path))
        return b"".join(parts)
    finally:
        os.close(fd)

def file_pin(path, maximum=256 * 1024 * 1024, require_elf=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
             "artifact is not a bounded regular file: " + str(path))
        h = hashlib.sha256()
        size = 0
        first = b""
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            if not first:
                first = block[:4]
            size += len(block)
            need(size <= maximum, "artifact exceeded bound")
            h.update(block)
        need(stamp(before) == stamp(os.fstat(fd)) and size == before.st_size,
             "artifact changed during held hashing")
        if require_elf:
            need(first == b"\x7fELF" and before.st_mode & 0o111,
                 "compiled artifact is not an executable ELF")
        return {"path": str(path), "bytes": size, "sha256": h.hexdigest(),
                "device": before.st_dev, "inode": before.st_ino,
                "mode": stat.S_IMODE(before.st_mode)}
    finally:
        os.close(fd)

def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())

def all_source(root):
    # Same serialized inventory as actual producer05 build-template.py.
    # The bounded regular-file reader adds held-open race rejection only.
    rows = []
    total = 0
    for path in sorted(root.rglob("*")):
        st = path.lstat()
        name = path.relative_to(root).as_posix()
        if stat.S_ISDIR(st.st_mode):
            continue
        if stat.S_ISREG(st.st_mode):
            data = read_regular(path, SOURCE_LIMIT)
            rows.append({"path": name, "bytes": st.st_size, "sha256": sha(data)})
            total += len(data)
        elif stat.S_ISLNK(st.st_mode):
            rows.append({"path": name, "symlink": os.readlink(path)})
        else:
            raise RuntimeError("unexpected non-source inode " + name)
        need(len(rows) <= 4096 and total <= 256 * 1024 * 1024,
             "complete source inventory bound exceeded")
    return json_bytes(rows)

def plain_input_path(root, name, *, must_be_absent=False):
    need(not name.startswith("/") and ".." not in Path(name).parts,
         "invalid input relative path")
    need(root.resolve(strict=True) == root, "source root is not a plain absolute directory")
    current = root
    parts = Path(name).parts
    for part in parts[:-1]:
        current = current / part
        need(stat.S_ISDIR(current.lstat().st_mode), "source parent is not a real directory")
    destination = root / name
    if must_be_absent:
        need(name in NEW_SOURCE_FILES, "only the frozen new module may be created")
        try:
            destination.lstat()
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError("new source module already exists")
    else:
        need(stat.S_ISREG(destination.lstat().st_mode),
             "source input is not a real regular file")
    return destination

def inputs(root, expected):
    result = {}
    for name in sorted(expected):
        need(not name.startswith("/") and ".." not in Path(name).parts,
             "invalid input relative path")
        data = read_regular(plain_input_path(root, name), SOURCE_LIMIT)
        result[name] = {"bytes": len(data), "sha256": sha(data)}
    need(result == expected, "exact source input pins differ")
    return result

def command_env(target):
    # Fresh fixed environment: no ambient rustup selection, wrappers, loader
    # injection or Cargo flags survive. Empty wrapper values also override a
    # same-name Cargo config selection; no doctests are requested.
    return {
        "PATH": RUST_SYSROOT + "/bin:/usr/bin:/bin", "HOME": "/home/alex",
        "CARGO_HOME": "/home/alex/.cargo", "RUSTC": RUSTC, "RUSTDOC": RUSTDOC,
        "LANG": "C", "LC_ALL": "C", "CARGO_NET_OFFLINE": "true",
        "CARGO_BUILD_JOBS": "1", "CARGO_INCREMENTAL": "0",
        "CARGO_PROFILE_DEV_DEBUG": "0", "CARGO_PROFILE_TEST_DEBUG": "0",
        "RUST_TEST_THREADS": "1", "CARGO_TARGET_DIR": str(target),
        "RUSTC_WRAPPER": "", "RUSTC_WORKSPACE_WRAPPER": "", "RUSTFLAGS": "",
        "CARGO_ENCODED_RUSTFLAGS": "", "RUSTDOCFLAGS": "", "CARGO_ENCODED_RUSTDOCFLAGS": "",
        "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER": "/usr/bin/cc",
    }

def direct_tool_pins():
    result = {}
    for name, expected in DIRECT_TOOL_PINS.items():
        path = Path(name)
        need(path.resolve(strict=True) == path, "fixed direct Rust tool acquired an alias")
        before = path.lstat()
        need(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and
             before.st_mode & 0o22 == 0, "direct Rust tool owner/mode differs")
        row = file_pin(path, require_elf=True)
        after = path.lstat()
        need(stamp(before) == stamp(after) and row["device"] == after.st_dev and
             row["inode"] == after.st_ino and path.resolve(strict=True) == path,
             "direct Rust tool named/held identity differs")
        need(row["bytes"] == expected["bytes"] and row["sha256"] == expected["sha256"],
             "actual observed direct Rust tool contents differ: " + name)
        result[name] = row
    return result

def direct_tool_versions(report, env):
    rows = {}
    for name, argv in [("cargo", [CARGO, "--version"]), ("rustc", [RUSTC, "-vV"])]:
        out, err = run_command(report, OUT, argv, CANDIDATE, env, 10)
        need(not err and out.decode("utf-8") == DIRECT_TOOL_VERSIONS[name],
             "actual direct Rust version differs: " + name)
        rows[name] = out.decode("utf-8")
    return rows

def run_command(report, directory, argv, cwd, env, timeout, pass_fds=()):
    index = len(report["commands"])
    stdout_path = directory / ("command-%02d.stdout" % index)
    stderr_path = directory / ("command-%02d.stderr" % index)
    row = {"argv": argv, "cwd": str(cwd), "started_at": now(),
           "timeout_seconds": timeout, "timed_out": False,
           "returncode": None, "stdout_path": str(stdout_path),
           "stderr_path": str(stderr_path)}
    report["commands"].append(row)
    with open(stdout_path, "xb") as stdout, open(stderr_path, "xb") as stderr:
        process = subprocess.Popen(argv, cwd=cwd, env=env,
                                   stdin=subprocess.DEVNULL, stdout=stdout,
                                   stderr=stderr, start_new_session=True,
                                   pass_fds=pass_fds)
        row["exact_child_pid"] = process.pid
        try:
            row["returncode"] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            row["timed_out"] = True
            # The direct child has not been reaped, so its numeric process
            # group cannot be recycled while these two group signals run.
            # Do not poll/wait between TERM and KILL.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            time.sleep(0.2)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            row["returncode"] = process.wait(timeout=5)
        finally:
            stdout.flush()
            stderr.flush()
    row["finished_at"] = now()
    row["stdout_pin"] = file_pin(stdout_path, maximum=64 * 1024 * 1024)
    row["stderr_pin"] = file_pin(stderr_path, maximum=64 * 1024 * 1024)
    out = read_regular(stdout_path, LOG_LIMIT)
    err = read_regular(stderr_path, LOG_LIMIT)
    row["stdout_excerpt"] = out[-4096:].decode("utf-8", errors="replace")
    row["stderr_excerpt"] = err[-4096:].decode("utf-8", errors="replace")
    need(not row["timed_out"] and row["returncode"] == 0,
         "command failed or timed out: " + str(index))
    return out, err

def validate_config(cfg):
    need(set(cfg) == {"schema", "revision", "preimage", "overlays",
                     "original_diff_sha256", "source_manifest_sha256"},
         "unexpected recovery payload fields")
    need(cfg["schema"] == 1 and cfg["revision"] == CONTROL_REVISION,
         "wrong recovery payload revision")
    need(cfg["original_diff_sha256"] == ORIGINAL_DIFF_SHA and
         cfg["source_manifest_sha256"] ==
         "c5afbb0a61653f5fa554ef42cd68f77e71a38893b229151d2b685b5e2d032050",
         "wrong recovered source lineage")
    need(len(cfg["preimage"]) == 32 and
         set(cfg["overlays"]) == set(EXACT_OVERLAY) and
         set(cfg["overlays"]) - set(cfg["preimage"]) == NEW_SOURCE_FILES and
         len(set(cfg["preimage"]) | set(cfg["overlays"])) == 33, "wrong input/overlay set")
    for name, (size, digest) in EXACT_OVERLAY.items():
        row = cfg["overlays"][name]
        data = row["text"].encode("utf-8")
        need(set(row) == {"text", "bytes", "sha256"} and
             row["bytes"] == size and len(data) == size and
             row["sha256"] == digest and sha(data) == digest,
             "overlay does not match original frozen source: " + name)
    return cfg

def candidate_input_pins(cfg):
    result = dict(cfg["preimage"])
    for name, row in cfg["overlays"].items():
        result[name] = {"bytes": row["bytes"], "sha256": row["sha256"]}
    return result

"""Read-only health gate for the controller's exact, held cgroup v2 domain.

This source is inlined unchanged into both recovery03 controllers. It never
writes a cgroup file. Its final observation precedes receipt publication; the
caller still needs the durable outer job terminal to qualify the whole unit.
"""
import ctypes
import os
import re
import stat
import time
import traceback

_RESOURCE_CGROUP2_MAGIC = 0x63677270
_RESOURCE_BAD_EVENTS = ("max", "oom", "oom_kill", "oom_group_kill")
_RESOURCE_LIMIT_NAMES = ("memory.max", "memory.high", "memory.swap.max",
                         "cpu.max", "pids.max")
_RESOURCE_NS_NAMES = ("mnt", "cgroup")


def _resource_need(condition, message):
    if not condition:
        raise RuntimeError("own resource gate: " + message)


def _resource_uint(text):
    _resource_need(re.fullmatch(r"[0-9]+", text) is not None,
                   "counter is not an unsigned decimal")
    value = int(text)
    _resource_need(value <= (1 << 64) - 1, "counter overflow")
    return value


def _resource_limit(text):
    return "max" if text == "max" else _resource_uint(text)


def _resource_counters(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        _resource_need(len(fields) == 2 and fields[0] not in result,
                       "malformed or repeated counter")
        _resource_need(re.fullmatch(r"[a-z_]+", fields[0]) is not None,
                       "invalid counter name")
        result[fields[0]] = _resource_uint(fields[1])
    _resource_need(bool(result), "empty counter record")
    return result


def _resource_membership(text):
    _resource_need(text.endswith("\n") and text.count("\n") == 1 and
                   text.startswith("0::/"), "not one unified cgroup membership")
    relative = text[4:-1]
    parts = relative.split("/")
    _resource_need(bool(relative) and all(part not in ("", ".", "..")
                                        for part in parts),
                   "root or noncanonical cgroup membership")
    return relative


def _resource_identity(fd):
    value = os.fstat(fd)
    _resource_need(stat.S_ISDIR(value.st_mode), "held resource object is not a directory")
    return [value.st_dev, value.st_ino]


def _resource_fstype(fd):
    library = ctypes.CDLL(None, use_errno=True)
    function = library.fstatfs
    function.argtypes = [ctypes.c_int, ctypes.c_void_p]
    function.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(256)
    if function(fd, ctypes.byref(buffer)) != 0:
        raise OSError(ctypes.get_errno(), "fstatfs own cgroup")
    return ctypes.c_long.from_buffer(buffer).value


def _resource_open_descendant(root_fd, relative):
    # This helper never resolves a slash-containing name through an ambient
    # pathname. In particular a replaced/symlink component is not followed.
    parts = relative.split("/")
    _resource_need(bool(relative) and all(part not in ("", ".", "..")
                                        for part in parts), "invalid descendant")
    current = os.dup(root_fd)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY |
                            os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def _resource_read_at(directory, name, maximum=32768):
    _resource_need("/" not in name and name not in ("", ".", ".."),
                   "invalid fixed resource filename")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                 dir_fd=directory)
    try:
        _resource_need(stat.S_ISREG(os.fstat(fd).st_mode),
                       "resource attribute is not a regular virtual file")
        data = bytearray()
        while True:
            part = os.read(fd, min(4096, maximum + 1 - len(data)))
            if not part:
                break
            data.extend(part)
            _resource_need(len(data) <= maximum, "resource attribute exceeds bound")
        return bytes(data).decode("ascii", errors="strict").strip()
    finally:
        os.close(fd)


def _resource_self_membership():
    with open("/proc/self/cgroup", "rt", encoding="ascii") as stream:
        text = stream.read(4097)
    _resource_need(len(text) <= 4096, "membership read exceeds bound")
    return text, _resource_membership(text)


def _resource_namespaces():
    result = {}
    for name in _RESOURCE_NS_NAMES:
        value = os.stat("/proc/self/ns/" + name)
        result[name] = [value.st_dev, value.st_ino]
    return result


def _resource_validate_snapshot(snapshot, expected_memory):
    limits = snapshot["limits"]
    _resource_need(limits["memory.max"] == expected_memory,
                   "actual memory.max differs from admitted request")
    quota, period = limits["cpu.max"]
    _resource_need(isinstance(quota, int) and quota == period and period > 0,
                   "actual CPU quota is not one CPU")
    events = snapshot["memory_events"]
    _resource_need(all(key in events for key in ("max", "oom", "oom_kill")),
                   "required memory event counters absent")
    _resource_need(snapshot["memory_current"] <= expected_memory and
                   snapshot["memory_peak"] <= expected_memory,
                   "observed memory current/peak exceeds admitted limit")


def _resource_qualify(before, after, expected_memory):
    _resource_validate_snapshot(before, expected_memory)
    _resource_validate_snapshot(after, expected_memory)
    for name in ("pid", "cgroup_identity", "mount_identity", "membership",
                 "namespaces", "limits"):
        _resource_need(before[name] == after[name], name + " changed")
    _resource_need(before["started_monotonic_ns"] <= before["completed_monotonic_ns"] <=
                   after["started_monotonic_ns"] <= after["completed_monotonic_ns"],
                   "resource sample clock/order changed")
    _resource_need(after["memory_peak"] >= before["memory_peak"],
                   "memory.peak was reset")
    old_events = before["memory_events"]
    new_events = after["memory_events"]
    _resource_need(set(old_events) == set(new_events), "memory counter set changed")
    delta = {}
    for key in old_events:
        _resource_need(new_events[key] >= old_events[key], "memory counter decreased")
        delta[key] = new_events[key] - old_events[key]
    for key in _RESOURCE_BAD_EVENTS:
        _resource_need(old_events.get(key, 0) == 0 and new_events.get(key, 0) == 0,
                       "memory limit/OOM event observed: " + key)
    return delta


class OwnJobResources:
    def __init__(self, expected_memory):
        _resource_need(expected_memory in (1073741824, 536870912),
                       "unexpected compile/control memory budget")
        self.expected_memory = expected_memory
        self.root_fd = None
        self.fd = None
        self.identity = None
        self.mount_identity = None
        self.membership = None
        self.namespaces = None
        self.pid = os.getpid()
        self.begin_passed = False
        self.record = {
            "schema": 1, "held_own_cgroup_gate_passed": False,
            "expected_memory_max": expected_memory, "expected_cpu_count": 1,
            "cgroup_files_written": False,
            "swap_zero_claimed": False,
            "whole_invocation_resource_qualified": False,
            "scope": "held own cgroup until final pre-receipt sample; durable outer terminal remains required",
        }

    def begin(self):
        _resource_need(self.fd is None and not self.begin_passed, "resource begin replay")
        self.membership, relative = _resource_self_membership()
        self.namespaces = _resource_namespaces()
        self.root_fd = os.open("/sys/fs/cgroup", os.O_RDONLY | os.O_DIRECTORY |
                               os.O_NOFOLLOW | os.O_CLOEXEC)
        _resource_need(_resource_fstype(self.root_fd) == _RESOURCE_CGROUP2_MAGIC,
                       "mount root is not cgroup v2")
        self.mount_identity = _resource_identity(self.root_fd)
        self.fd = _resource_open_descendant(self.root_fd, relative)
        _resource_need(_resource_fstype(self.fd) == _RESOURCE_CGROUP2_MAGIC,
                       "held domain is not cgroup v2")
        self.identity = _resource_identity(self.fd)
        before = self.sample()
        self.record["before"] = before
        _resource_validate_snapshot(before, self.expected_memory)
        for key in _RESOURCE_BAD_EVENTS:
            _resource_need(before["memory_events"].get(key, 0) == 0,
                           "nonzero initial memory limit/OOM counter: " + key)
        self.begin_passed = True

    def sample(self):
        _resource_need(self.fd is not None and self.root_fd is not None,
                       "no retained resource domain")
        started = time.monotonic_ns()
        _resource_need(os.getpid() == self.pid and
                       _resource_identity(self.fd) == self.identity and
                       _resource_identity(self.root_fd) == self.mount_identity,
                       "held resource/process identity changed")
        membership, _ = _resource_self_membership()
        namespaces = _resource_namespaces()
        _resource_need(membership == self.membership and namespaces == self.namespaces,
                       "controller moved domain or namespace")
        limits = {name: _resource_limit(_resource_read_at(self.fd, name))
                  for name in _RESOURCE_LIMIT_NAMES if name != "cpu.max"}
        cpu = _resource_read_at(self.fd, "cpu.max").split()
        _resource_need(len(cpu) == 2, "malformed cpu.max")
        limits["cpu.max"] = [_resource_limit(cpu[0]), _resource_uint(cpu[1])]
        procs = [_resource_uint(line) for line in
                 _resource_read_at(self.fd, "cgroup.procs").splitlines()]
        _resource_need(self.pid in procs and len(procs) == len(set(procs)),
                       "held domain does not contain the controller")
        current = _resource_uint(_resource_read_at(self.fd, "memory.current"))
        swap_current = _resource_uint(_resource_read_at(self.fd, "memory.swap.current"))
        try:
            swap_peak = _resource_uint(_resource_read_at(self.fd, "memory.swap.peak"))
        except FileNotFoundError:
            swap_peak = None
        pids = _resource_uint(_resource_read_at(self.fd, "pids.current"))
        domain_events = _resource_counters(_resource_read_at(self.fd, "cgroup.events"))
        # Event counters are the final attribute read, after the peak/current
        # observations. This is an interval sample, not an atomic snapshot.
        peak = _resource_uint(_resource_read_at(self.fd, "memory.peak"))
        events = _resource_counters(_resource_read_at(self.fd, "memory.events"))
        final_membership, _ = _resource_self_membership()
        _resource_need(final_membership == self.membership and
                       _resource_namespaces() == self.namespaces and
                       _resource_identity(self.fd) == self.identity,
                       "resource scope changed during sample")
        return {
            "pid": self.pid, "cgroup_identity": self.identity,
            "mount_identity": self.mount_identity, "membership": membership,
            "namespaces": namespaces, "limits": limits,
            "memory_current": current, "memory_peak": peak,
            "memory_swap_current": swap_current, "memory_swap_peak": swap_peak,
            "memory_events": events, "cgroup_events": domain_events,
            "pids_current": pids, "direct_cgroup_procs": procs,
            "started_monotonic_ns": started,
            "completed_monotonic_ns": time.monotonic_ns(),
        }

    def finish(self):
        after = self.sample()
        self.record["after"] = after
        _resource_need(self.begin_passed and "before" in self.record,
                       "initial resource gate did not pass")
        self.record["memory_event_delta"] = _resource_qualify(
            self.record["before"], after, self.expected_memory)
        self.record["held_own_cgroup_gate_passed"] = True

    def close(self):
        first_error = None
        for attribute in ("fd", "root_fd"):
            fd = getattr(self, attribute)
            if fd is not None:
                setattr(self, attribute, None)
                try:
                    os.close(fd)
                except OSError as error:
                    if first_error is None:
                        first_error = error
        if first_error is not None:
            raise first_error


def _resource_record_error(report, resources, error):
    report["success"] = False
    resources.record["held_own_cgroup_gate_passed"] = False
    detail = type(error).__name__ + ": " + str(error)
    report.setdefault("resource_gate_errors", []).append(detail)
    if "error" not in report:
        report["error"] = detail
        report["traceback"] = traceback.format_exc()


def finish_own_resource_gate(report, resources):
    try:
        resources.finish()
    except Exception as error:
        # A compile/test failure remains the primary error. A later collection
        # problem cannot erase it or become an apparent cleanup success.
        _resource_record_error(report, resources, error)
    finally:
        try:
            resources.close()
        except Exception as error:
            _resource_record_error(report, resources, error)


import shutil

def compile_recovery(cfg):
    validate_config(cfg)
    need(os.geteuid() != 0, "compile-only recovery must run as the configured non-root operator")
    os.umask(0o077)
    # O_EXCL equivalent for the entire invocation. No reuse, resume, cleanup,
    # repair of an old source directory, or old target cache is permitted.
    OUT.mkdir(mode=0o700)
    report = {
        "schema": 1, "revision": CONTROL_REVISION, "started_at": now(),
        "success": False, "commands": [], "source_origin": str(SOURCE),
        "candidate": str(CANDIDATE), "target": str(TARGET),
        "original_source_diff_sha256": ORIGINAL_DIFF_SHA,
        "original_compile_request_recovered": False,
        "compile_only": True, "test_binaries_executed": False,
        "ordinary_controls_executed": False, "full_owner_runtime_qualified": False,
        "android_runtime_started": False, "barrier_constructor_executed": False,
        "installed_files_changed": False, "namespace_or_network_effects_requested": False,
        "memory_budget_bytes": 1073741824, "cpu_quota_percent": 100,
        "uid": os.geteuid(), "pid": os.getpid(),
    }
    resources = OwnJobResources(1073741824)
    report["resource_health"] = resources.record
    before = None
    tool_before = None
    try:
        resources.begin()
        put(OUT / "payload.json", json_bytes(cfg))
        report["payload_sha256"] = sha(json_bytes(cfg))
        prior_raw = read_regular(PRIOR_RECEIPT, 128 * 1024)
        need(sha(prior_raw) == PRIOR_RECEIPT_SHA, "actual producer15 namespace child exit01 receipt hash differs")
        prior = json.loads(prior_raw)
        need(prior["success"] is True and prior["compile_only"] is True and
             prior["revision"] == "producer15-namespace-child-exit01" and
             prior["candidate"] == str(SOURCE) and
             prior["inputs_before"] == cfg["preimage"] and
             prior["inputs_after"] == cfg["preimage"] and
             prior["all_source_inventory_before_sha256"] == PRIOR_INVENTORY_SHA and
             prior["all_source_inventory_after_sha256"] == PRIOR_INVENTORY_SHA,
             "actual producer15 namespace child exit01 receipt/source binding differs")
        put(OUT / "producer15-namespace-child-exit01-actual-compile-result.json", prior_raw)
        report["prior_build_receipt_sha256"] = PRIOR_RECEIPT_SHA
        report["preimage_inputs"] = inputs(SOURCE, cfg["preimage"])
        baseline = all_source(SOURCE)
        need(sha(baseline) == PRIOR_INVENTORY_SHA, "full original candidate inventory differs")
        # Prevent a copied link from redirecting Cargo or an overlay write to
        # the original source tree or an unrelated workspace.
        for row in json.loads(baseline):
            if "symlink" in row:
                link = SOURCE / row["path"]
                need(not os.path.isabs(row["symlink"]) and
                     link.resolve(strict=True).is_relative_to(SOURCE),
                     "source symlink escapes isolated copy")
        put(OUT / "original-source-inventory.json", baseline)
        shutil.copytree(SOURCE, CANDIDATE, symlinks=True)
        need(all_source(CANDIDATE) == baseline, "new copy does not match original inventory")
        for name, row in cfg["overlays"].items():
            creating = name in NEW_SOURCE_FILES
            destination = plain_input_path(CANDIDATE, name, must_be_absent=creating)
            flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC
            if creating:
                need(name not in cfg["preimage"], "new source must have no preimage")
                flags |= os.O_CREAT | os.O_EXCL
            else:
                original = read_regular(destination, SOURCE_LIMIT)
                pin = cfg["preimage"][name]
                need(len(original) == pin["bytes"] and sha(original) == pin["sha256"],
                     "copied overlay preimage changed")
                put(OUT / "preimage" / name, original)
                flags |= os.O_TRUNC
            fd = os.open(destination, flags, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(row["text"].encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
        expected = candidate_input_pins(cfg)
        report["inputs_before"] = inputs(CANDIDATE, expected)
        before = all_source(CANDIDATE)
        put(OUT / "source-inventory-before.json", before)
        report["all_source_inventory_before_sha256"] = sha(before)
        env = command_env(TARGET)
        tool_before = direct_tool_pins()
        report["direct_toolchain_before"] = tool_before
        report["direct_tool_authority"] = {"observation_sha256": DIRECT_TOOL_OBSERVATION_SHA,
            "actual_builder_compile_sha256": DIRECT_TOOL_ACTUAL_BUILD_SHA,
            "rustup_proxy_executed": False, "tool_install_or_update_requested": False,
            "compiler_runtime_libraries_not_rehashed_by_this_narrow_gate": True}
        report["direct_versions_before"] = direct_tool_versions(report, env)
        report["build_environment_overrides"] = {
            key: env[key] for key in [
                "CARGO_BUILD_JOBS", "CARGO_INCREMENTAL", "CARGO_PROFILE_DEV_DEBUG",
                "CARGO_PROFILE_TEST_DEBUG", "RUST_TEST_THREADS", "CARGO_TARGET_DIR",
                "CARGO_HOME", "PATH", "RUSTC", "RUSTDOC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"
            ]
        }
        build_out, _ = run_command(report, OUT, [
            CARGO, "build", "--locked", "--offline", "-j", "1",
            "-p", "droidloom-pressure-relay", "-p", "droidloom-supervisor",
            "--bins", "--message-format=json"
        ], CANDIDATE, env, 270)
        test_out, _ = run_command(report, OUT, [
            CARGO, "test", "--locked", "--offline", "-j", "1",
            "-p", "droidloom-pressure-relay", "-p", "droidloom-supervisor",
            "--lib", "--no-run", "--message-format=json"
        ], CANDIDATE, env, 270)
        report["artifacts"] = {}
        build_messages = [json.loads(line) for line in build_out.splitlines() if line.strip()]
        test_messages = [json.loads(line) for line in test_out.splitlines() if line.strip()]
        need(any(row.get("reason") == "build-finished" and row.get("success") is True
                 for row in build_messages), "Cargo build-finished success missing")
        need(any(row.get("reason") == "build-finished" and row.get("success") is True
                 for row in test_messages), "Cargo no-run build-finished success missing")
        for name in BINARIES:
            path = TARGET / "debug" / name
            matches = [row for row in build_messages
                       if row.get("reason") == "compiler-artifact" and
                       row.get("executable") == str(path) and
                       row.get("target", {}).get("name") == name and
                       row.get("target", {}).get("kind") == ["bin"] and
                       row.get("profile", {}).get("test") is False]
            need(len(matches) == 1, "missing or duplicate actual Cargo binary artifact " + name)
            source_path = Path(matches[0]["target"]["src_path"])
            need(source_path.is_relative_to(CANDIDATE / "runtime"),
                 "binary artifact does not derive from isolated workspace")
            row = file_pin(path, require_elf=True)
            row["cargo_package_id"] = matches[0]["package_id"]
            row["cargo_target_source"] = str(source_path)
            report["artifacts"][name] = row
        tests = {}
        for item in test_messages:
            if item.get("reason") != "compiler-artifact" or \
               item.get("profile", {}).get("test") is not True or \
               not item.get("executable"):
                continue
            target = item["target"]
            need(len(target["kind"]) == 1, "ambiguous Cargo test target kind")
            key = (target["name"], target["kind"][0])
            need(key in EXPECTED_TEST_TARGETS and key not in tests,
                 "unexpected or repeated test artifact")
            path = Path(item["executable"])
            source_path = Path(target["src_path"])
            need(path.is_relative_to(TARGET / "debug" / "deps") and
                 source_path.is_relative_to(CANDIDATE / "runtime"),
                 "test executable or source is outside isolated candidate/target")
            row = file_pin(path, require_elf=True)
            row.update(target_name=key[0], target_kind=key[1],
                       cargo_package_id=item["package_id"],
                       cargo_target_source=str(source_path))
            tests[key] = row
        need(set(tests) == EXPECTED_TEST_TARGETS, "compiled test target set incomplete")
        report["compiled_test_artifacts"] = [tests[key] for key in sorted(tests)]
        report["inputs_after"] = inputs(CANDIDATE, expected)
        after = all_source(CANDIDATE)
        put(OUT / "source-inventory-after.json", after)
        report["all_source_inventory_after_sha256"] = sha(after)
        need(after == before, "isolated source changed during compile")
        original_after = all_source(SOURCE)
        report["original_source_inventory_after_sha256"] = sha(original_after)
        need(original_after == baseline, "original source changed during compile")
        need(report["inputs_before"] == report["inputs_after"], "32 inputs changed during compile")
        report["success"] = True
    except Exception as failure:
        report["error"] = type(failure).__name__ + ": " + str(failure)
        report["traceback"] = traceback.format_exc()
        # Keep the first compile/admission failure. Evidence collection errors
        # cannot overwrite it or produce a success-shaped result.
        report["failure_collection_errors"] = []
        if CANDIDATE.is_dir():
            try:
                after_failure = all_source(CANDIDATE)
                put(OUT / "source-inventory-after-failure.json", after_failure)
                report["all_source_inventory_after_failure_sha256"] = sha(after_failure)
            except Exception as capture:
                report["failure_collection_errors"].append(str(capture))
    if tool_before is not None:
        try:
            report["direct_toolchain_after"] = direct_tool_pins()
            need(report["direct_toolchain_after"] == tool_before, "direct Rust tools changed during compilation")
            report["direct_versions_after"] = direct_tool_versions(report, env)
            need(report["direct_versions_before"] == report["direct_versions_after"], "direct Rust version changed during compilation")
        except Exception as failure:
            report["success"] = False
            if "error" not in report:
                report["error"] = type(failure).__name__ + ": " + str(failure)
                report["traceback"] = traceback.format_exc()
            else:
                report.setdefault("failure_collection_errors", []).append("direct tool final check: " + str(failure))
    finish_own_resource_gate(report, resources)
    report["finished_at"] = now()
    raw = json_bytes(report)
    put(OUT / "compile-result.json", raw)
    print(json.dumps({
        "success": report["success"], "revision": CONTROL_REVISION,
        "report": str(OUT / "compile-result.json"), "bytes": len(raw),
        "sha256": sha(raw), "commands": len(report["commands"]),
        "test_binaries_executed": False, "full_owner_runtime_qualified": False,
        "error": report.get("error")
    }), flush=True)
    raise SystemExit(0 if report["success"] else 1)

compile_recovery(json.loads(r'''{
  "original_diff_sha256": "cf5ba26e0f3efe86b6eec6ed140c8688df4ebc24f043dbdee4a07b94239744ef",
  "overlays": {
    "runtime/droidloom-supervisor/src/relay_lifecycle/audit.rs": {
      "bytes": 34440,
      "sha256": "7322b9a314d2431af687350dc133b40f25dc244931b2a28d25cf50a4bbcc32a4",
      "text": "//! Bounded observations of the existing owner, never lifecycle authority.\n//!\n//! A reader must independently bind this producer to its held process/ELF,\n//! outer unit/cgroup and initial Main fence. No API accepts these serialized\n//! values as permission to spawn, commit, signal, retire or release a claim.\nuse super::capability::{self, Process};\nuse super::domain::{self, Identity};\nuse super::init_peer::Hello;\nuse super::init_log;\nuse super::policy::{self, PressureRelaySpec};\nuse droidloom_pressure_relay::{BootstrapStatus, LifecycleBroker};\nuse serde::{Deserialize, Serialize};\nuse std::fs::File;\nuse std::io;\nuse std::os::unix::fs::MetadataExt;\nuse std::os::unix::process::ExitStatusExt;\nuse std::process::ExitStatus;\nuse std::sync::{Arc, Mutex, MutexGuard};\n\nconst MAX_RECORDS: usize = 16;\nconst MAX_ERROR_BYTES: usize = 512;\n\n#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]\npub(crate) struct FileRecord { pub device: u64, pub inode: u64 }\nimpl From<Identity> for FileRecord {\n    fn from(id: Identity) -> Self { Self { device: id.device, inode: id.inode } }\n}\nimpl From<droidloom_pressure_relay::FileId> for FileRecord {\n    fn from(id: droidloom_pressure_relay::FileId) -> Self {\n        Self { device: id.device, inode: id.inode }\n    }\n}\nfn file_record(file: &File) -> io::Result<FileRecord> { Ok(Identity::of(file)?.into()) }\n\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\npub(crate) struct ProcessRecord {\n    pub pid: i32,\n    pub birth: u64,\n    pub pidfd: FileRecord,\n    pub proc_dir: FileRecord,\n}\nimpl From<droidloom_pressure_relay::LifecycleProcessObservation> for ProcessRecord {\n    fn from(value: droidloom_pressure_relay::LifecycleProcessObservation) -> Self {\n        Self { pid: value.pid, birth: value.birth, pidfd: value.pidfd.into(), proc_dir: value.proc_dir.into() }\n    }\n}\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\nstruct ProducerRecord {\n    process: ProcessRecord,\n    namespaces: [FileRecord; 10],\n    executable: FileRecord,\n    executable_sha256: String,\n}\nimpl ProducerRecord {\n    fn capture() -> io::Result<Self> {\n        let process = Process::current_leader_for_observation()?;\n        let namespaces = process.namespaces_for_observation()?;\n        let executable = process.executable()?;\n        let before = executable.metadata()?;\n        let digest = capability::hash(&executable)?;\n        let after = executable.metadata()?;\n        let stamp = |m: &std::fs::Metadata| {\n            (m.dev(), m.ino(), m.size(), m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec())\n        };\n        if stamp(&before) != stamp(&after) {\n            return Err(domain::error(\"audit producer executable changed while hashing\"));\n        }\n        let result = Self {\n            process: process.observation()?,\n            namespaces,\n            executable: file_record(&executable)?,\n            executable_sha256: policy::hex(&digest),\n        };\n        process.live()?;\n        Ok(result)\n    }\n}\n\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\npub(crate) struct BrokerRecord {\n    state: u32,\n    nonce: String,\n    generation: String,\n    budget: String,\n    endpoint: FileRecord,\n    cgroup: FileRecord,\n    granted: bool,\n    faulted: bool,\n}\nimpl From<&BootstrapStatus> for BrokerRecord {\n    fn from(status: &BootstrapStatus) -> Self {\n        Self {\n            state: status.state as u32, nonce: policy::hex(&status.nonce),\n            generation: policy::hex(&status.generation), budget: policy::hex(&status.budget),\n            endpoint: status.endpoint.into(), cgroup: status.cgroup.into(),\n            granted: status.granted, faulted: status.faulted,\n        }\n    }\n}\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\npub(crate) struct InitRecord {\n    process: ProcessRecord,\n    namespaces: [FileRecord; 10],\n    root: FileRecord,\n    cgroup: FileRecord,\n    executable: FileRecord,\n    executable_sha256: String,\n    compat: FileRecord,\n    compat_sha256: String,\n    linker: FileRecord,\n    linker_sha256: String,\n    hello_wire_hex: String,\n}\nimpl InitRecord {\n    pub(crate) fn capture(hello: &Hello, wire: &[u8; 128]) -> io::Result<Self> {\n        let namespaces = hello.namespaces.iter().map(file_record).collect::<io::Result<Vec<_>>>()?;\n        Ok(Self {\n            process: hello.process.observation()?,\n            namespaces: namespaces.try_into().map_err(|_| domain::error(\"audit init namespace count differs\"))?,\n            root: file_record(&hello.root)?, cgroup: file_record(&hello.guest_domain)?,\n            executable: hello.executable.identity().into(),\n            executable_sha256: policy::hex(&hello.executable.digest()),\n            compat: hello.compat.identity().into(), compat_sha256: policy::hex(&hello.compat.digest()),\n            linker: hello.linker.identity().into(), linker_sha256: policy::hex(&hello.linker.digest()),\n            hello_wire_hex: policy::hex(wire),\n        })\n    }\n}\n\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\nstruct RegistrationRecord {\n    level: u32,\n    window_us: u64,\n    stall_us: u64,\n    pressure: FileRecord,\n    write_started_ns: u64,\n    write_completed_ns: u64,\n    bytes_written: u64,\n    trigger: String,\n}\n/// Only the bounded registration/retirement summary is exposed here. Event\n/// correlation, native expiry and kill effects need their separate evidence.\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\npub(crate) struct RetirementRecord {\n    status: BrokerRecord,\n    authority_generation: String,\n    lease_generation: String,\n    cgroup: FileRecord,\n    budget: String,\n    granted: bool,\n    faulted: bool,\n    incomplete: bool,\n    registrations: Vec<RegistrationRecord>,\n    observations: u64,\n    packets_queued: u64,\n    event_records: u32,\n    event_overflow: bool,\n    stop_reason: u32,\n    retired_monotonic_ns: u64,\n}\nimpl RetirementRecord {\n    pub(crate) fn capture(broker: &LifecycleBroker) -> io::Result<Self> {\n        if !broker.retirement_complete() {\n            return Err(domain::error(\"audit broker has not joined\"));\n        }\n        let status = broker.latest_status().ok_or_else(|| domain::error(\"audit terminal status missing\"))?;\n        let audit = broker.pressure_audit().ok_or_else(|| domain::error(\"audit joined pressure receipt missing\"))?;\n        audit.validate().map_err(io::Error::other)?;\n        let registrations = audit.registrations.records[..audit.registrations.count as usize].iter()\n            .map(|r| Ok(RegistrationRecord {\n                level: r.level, window_us: r.window_us, stall_us: r.stall_us,\n                pressure: FileRecord { device: r.pressure_device, inode: r.pressure_inode },\n                write_started_ns: r.write_started_ns, write_completed_ns: r.write_completed_ns,\n                bytes_written: r.bytes_written, trigger: r.trigger_text().map_err(io::Error::other)?.to_owned(),\n            })).collect::<io::Result<Vec<_>>>()?;\n        Ok(Self {\n            status: status.into(), authority_generation: policy::hex(&audit.authority_generation),\n            lease_generation: policy::hex(&audit.registrations.lease_generation),\n            cgroup: audit.cgroup.into(), budget: policy::hex(&audit.budget),\n            granted: audit.granted, faulted: audit.faulted, incomplete: audit.incomplete,\n            registrations, observations: audit.observations, packets_queued: audit.packets_queued,\n            event_records: audit.events.count, event_overflow: audit.events.overflow,\n            stop_reason: audit.stop_reason, retired_monotonic_ns: audit.retired_monotonic_ns,\n        })\n    }\n}\n\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\n#[serde(tag = \"event\", rename_all = \"snake_case\")]\npub(crate) enum Event {\n    Prepared { domain: FileRecord },\n    OwnerAttached { process: ProcessRecord },\n    InitHello { init: InitRecord },\n    BrokerReady { process: ProcessRecord, status: BrokerRecord },\n    InitProjectSent { wire_hex: String },\n    InitProjectedAccepted { wire_hex: String },\n    InitCommitSent { wire_hex: String },\n    InitDoneAccepted { wire_hex: String },\n    BrokerActive { status: BrokerRecord },\n    Retiring,\n    BrokerRetired { receipt: RetirementRecord },\n    ProcessesDead,\n    DomainEmpty,\n    Retired,\n    ResourcesRemoved,\n    ClaimReleased,\n}\nimpl Event {\n    fn bounded(&self) -> bool {\n        let hex = |value: &str, bytes: usize| value.len() == bytes * 2\n            && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c));\n        let broker = |value: &BrokerRecord| hex(&value.nonce, 32)\n            && hex(&value.generation, 32) && hex(&value.budget, 32);\n        match self {\n            Self::InitHello { init } => hex(&init.hello_wire_hex, 128)\n                && hex(&init.executable_sha256, 32) && hex(&init.compat_sha256, 32) && hex(&init.linker_sha256, 32),\n            Self::BrokerReady { status, .. } | Self::BrokerActive { status } => broker(status),\n            Self::InitProjectSent { wire_hex } | Self::InitProjectedAccepted { wire_hex }\n                | Self::InitCommitSent { wire_hex } | Self::InitDoneAccepted { wire_hex } => hex(wire_hex, 128),\n            Self::BrokerRetired { receipt } => broker(&receipt.status)\n                && hex(&receipt.authority_generation, 32) && hex(&receipt.lease_generation, 32)\n                && hex(&receipt.budget, 32) && receipt.registrations.len() <= 2\n                && receipt.registrations.iter().all(|r| r.trigger.len() <= 64),\n            _ => true,\n        }\n    }\n    fn rank(&self) -> u8 {\n        match self {\n            Self::Prepared { .. } => 1, Self::OwnerAttached { .. } => 2,\n            Self::InitHello { .. } => 3, Self::BrokerReady { .. } => 4,\n            Self::InitProjectSent { .. } => 5, Self::InitProjectedAccepted { .. } => 6,\n            Self::InitCommitSent { .. } => 7, Self::InitDoneAccepted { .. } => 8,\n            Self::BrokerActive { .. } => 9, Self::Retiring => 10,\n            Self::BrokerRetired { .. } => 11, Self::ProcessesDead => 12,\n            Self::DomainEmpty => 13, Self::Retired => 14,\n            Self::ResourcesRemoved => 15, Self::ClaimReleased => 16,\n        }\n    }\n}\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\nstruct Record { sequence: u32, observed_monotonic_ns: u64, detail: Event }\n#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]\n#[serde(rename_all = \"snake_case\")]\npub(crate) enum FailureOrigin { Admission, Runtime, Retirement, Cleanup, Panic }\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\nstruct FailureRecord { origin: FailureOrigin, observed_monotonic_ns: u64, message: String }\n\n/// The exact parent's wait result, not an inferred init exit or signal sender.\n/// The process identity is the earlier live OwnerAttached observation. Missing\n/// identity makes the journal incomplete but must not discard the wait result.\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\nstruct NamespaceOwnerExit {\n    host_pid: u32,\n    process: Option<ProcessRecord>,\n    observed_monotonic_ns: u64,\n    raw_status: i32,\n    exit_code: Option<i32>,\n    signal: Option<i32>,\n    core_dumped: bool,\n    explicit_stop_requested_before_observation: bool,\n    worker_retirement_started_before_observation: bool,\n}\n\n/// Data-only, bounded lifecycle observations. This is not an enrollment,\n/// pressure, cleanup or production qualification by itself. Missing milestones\n/// and `recording_incomplete` must never be inferred as successful operations.\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\npub struct RelayLifecycleAudit {\n    schema: u32,\n    retained_after_exit: bool,\n    nonce: String,\n    canonical_spec_sha256: String,\n    host_uid: u32,\n    producer: Option<ProducerRecord>,\n    memory_max_bytes: u64,\n    memory_high_bytes: u64,\n    memory_swap_max_bytes: u64,\n    cpu_quota_us: u64,\n    cpu_period_us: u64,\n    tasks_max: u32,\n    recording_incomplete: bool,\n    recording_error: Option<String>,\n    first_failure: Option<FailureRecord>,\n    retirement_failure: Option<FailureRecord>,\n    cleanup_failure: Option<FailureRecord>,\n    #[serde(default, skip_serializing_if = \"Option::is_none\")]\n    namespace_owner_exit: Option<NamespaceOwnerExit>,\n    #[serde(default, skip_serializing_if = \"Option::is_none\")]\n    init_log: Option<init_log::Observation>,\n    records: Vec<Record>,\n}\nimpl RelayLifecycleAudit {\n    pub(crate) fn retained(mut self) -> Self { self.retained_after_exit = true; self }\n}\nstruct Journal { snapshot: RelayLifecycleAudit, last_rank: u8 }\n#[derive(Clone)]\npub(crate) struct Audit(Arc<Mutex<Journal>>);\nfn monotonic_ns() -> io::Result<u64> {\n    let mut value = libc::timespec { tv_sec: 0, tv_nsec: 0 };\n    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut value) } != 0 {\n        return Err(io::Error::last_os_error());\n    }\n    if value.tv_sec < 0 || value.tv_nsec < 0 || value.tv_nsec >= 1_000_000_000 {\n        return Err(domain::error(\"audit monotonic clock invalid\"));\n    }\n    (value.tv_sec as u64).checked_mul(1_000_000_000)\n        .and_then(|n| n.checked_add(value.tv_nsec as u64))\n        .ok_or_else(|| domain::error(\"audit monotonic clock overflow\"))\n}\nfn bounded(message: &str) -> (String, bool) {\n    let mut end = message.len().min(MAX_ERROR_BYTES);\n    while !message.is_char_boundary(end) { end -= 1; }\n    (message[..end].to_owned(), end != message.len())\n}\nimpl Journal {\n    fn gap(&mut self, message: &str) {\n        self.snapshot.recording_incomplete = true;\n        if self.snapshot.recording_error.is_none() { self.snapshot.recording_error = Some(bounded(message).0); }\n    }\n    fn append(&mut self, event: Event, now: u64) {\n        if self.snapshot.records.len() >= MAX_RECORDS || !event.bounded() || event.rank() <= self.last_rank\n            || now == 0 || self.snapshot.records.last().is_some_and(|r| r.observed_monotonic_ns > now) {\n            self.gap(\"audit payload/order/capacity/clock violation\");\n            return;\n        }\n        self.last_rank = event.rank();\n        self.snapshot.records.push(Record {\n            sequence: self.snapshot.records.len() as u32 + 1, observed_monotonic_ns: now, detail: event,\n        });\n    }\n    fn failure(&mut self, origin: FailureOrigin, message: &str, observed_monotonic_ns: u64) {\n        let (message, truncated) = bounded(message);\n        if truncated { self.gap(\"audit failure text truncated\"); }\n        let failure = FailureRecord { origin, observed_monotonic_ns, message };\n        if self.snapshot.first_failure.is_none() { self.snapshot.first_failure = Some(failure.clone()); }\n        if origin == FailureOrigin::Retirement && self.snapshot.retirement_failure.is_none() {\n            self.snapshot.retirement_failure = Some(failure.clone());\n        }\n        if origin == FailureOrigin::Cleanup && self.snapshot.cleanup_failure.is_none() {\n            self.snapshot.cleanup_failure = Some(failure);\n        }\n    }\n}\n\n#[cfg(test)]\nfn fixture() -> Audit {\n    // Data-only recording fixture; no HostContext, process authority or cell.\n    Audit(Arc::new(Mutex::new(Journal {\n        snapshot: RelayLifecycleAudit {\n            schema: 1, retained_after_exit: false, nonce: \"07\".repeat(32),\n            canonical_spec_sha256: \"08\".repeat(32), host_uid: 1001, producer: None,\n            memory_max_bytes: 512 * 1024 * 1024, memory_high_bytes: 384 * 1024 * 1024,\n            memory_swap_max_bytes: 0, cpu_quota_us: 100000, cpu_period_us: 100000, tasks_max: 64,\n            recording_incomplete: false, recording_error: None, first_failure: None,\n            retirement_failure: None, cleanup_failure: None, namespace_owner_exit: None, init_log: None,\n            records: Vec::with_capacity(MAX_RECORDS),\n        }, last_rank: 0,\n    })))\n}\n#[cfg(test)]\npub(crate) fn test_snapshot() -> RelayLifecycleAudit {\n    let audit = fixture();\n    audit.lock().gap(\"synthetic data-only test snapshot; no lifecycle qualification\");\n    audit.snapshot()\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    use std::io::Write;\n    use std::process::{Child, Command, Stdio};\n    use std::time::{Duration, Instant};\n\n    struct OwnedChild(Child);\n    impl Drop for OwnedChild {\n        fn drop(&mut self) {\n            if self.0.try_wait().ok().flatten().is_none() { let _ = self.0.kill(); }\n            let _ = self.0.wait();\n        }\n    }\n    fn owned_wait(audit: &Audit, exit_code: u8, signal: Option<i32>, bind: bool) -> (u32, ExitStatus) {\n        // An ordinary exact child, not a real Android namespace or an Owner\n        // retirement certificate. The production Process pin and audit method\n        // below observe the actual kernel identity and actual wait status.\n        let mut child = OwnedChild(Command::new(\"/bin/sh\")\n            .args([\"-c\", &format!(\"read gate; exit {exit_code}\")])\n            .stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::null())\n            .spawn().unwrap());\n        let process = Process::from_child(&mut child.0).unwrap();\n        if bind { audit.record(process.observation().map(|process| Event::OwnerAttached { process })); }\n        if let Some(signal) = signal { process.signal(signal).unwrap(); }\n        else {\n            child.0.stdin.as_mut().unwrap().write_all(b\"exit\\n\").unwrap();\n            drop(child.0.stdin.take());\n        }\n        let deadline = Instant::now() + Duration::from_secs(2);\n        let status = loop {\n            if let Some(status) = child.0.try_wait().unwrap() { break status; }\n            assert!(Instant::now() < deadline, \"owned audit child did not exit\");\n            std::thread::sleep(Duration::from_millis(2));\n        };\n        assert!(process.dead().unwrap());\n        (child.0.id(), status)\n    }\n\n    #[test]\n    fn unexpected_owned_hup_is_retained_before_later_stop_or_retirement() {\n        let audit = fixture();\n        let (pid, status) = owned_wait(&audit, 0, Some(libc::SIGHUP), true);\n        assert_eq!(status.signal(), Some(libc::SIGHUP));\n        audit.namespace_owner_exit(pid, status, false, false);\n        let first = audit.snapshot();\n        let exit = first.namespace_owner_exit.as_ref().unwrap();\n        assert_eq!(exit.host_pid, pid);\n        assert_eq!(exit.process.as_ref().unwrap().pid as u32, pid);\n        assert_eq!(exit.raw_status, status.into_raw());\n        assert_eq!(exit.signal, Some(libc::SIGHUP));\n        assert_eq!(exit.exit_code, None);\n        assert!(!exit.explicit_stop_requested_before_observation);\n        let cause = first.first_failure.as_ref().unwrap();\n        assert_eq!(cause.origin, FailureOrigin::Runtime);\n        assert!(cause.message.contains(\"signal=Some(1)\"));\n        audit.namespace_owner_exit(pid, status, true, true);\n        audit.record(Ok(Event::Retiring));\n        audit.record(Ok(Event::Retired));\n        audit.record(Ok(Event::ResourcesRemoved));\n        audit.record(Ok(Event::ClaimReleased));\n        let retired = audit.snapshot();\n        assert_eq!(retired.namespace_owner_exit, first.namespace_owner_exit);\n        assert_eq!(retired.first_failure, first.first_failure);\n        assert_eq!(audit.first_failure_message().as_deref(), Some(cause.message.as_str()));\n        assert!(!retired.recording_incomplete);\n        assert_eq!(serde_json::from_slice::<RelayLifecycleAudit>(&serde_json::to_vec(&retired).unwrap()).unwrap(), retired);\n    }\n\n    #[test]\n    fn owned_nonzero_code_retains_the_actual_raw_wait_status() {\n        let audit = fixture();\n        let (pid, status) = owned_wait(&audit, 17, None, true);\n        assert_eq!(status.code(), Some(17));\n        audit.namespace_owner_exit(pid, status, false, false);\n        let result = audit.snapshot();\n        let exit = result.namespace_owner_exit.unwrap();\n        assert_eq!(exit.raw_status, status.into_raw());\n        assert_eq!(exit.exit_code, Some(17));\n        assert_eq!(exit.signal, None);\n        assert!(result.first_failure.unwrap().message.contains(\"exit_code=Some(17)\"));\n    }\n\n    #[test]\n    fn explicit_stop_records_owned_term_without_inventing_runtime_failure() {\n        let audit = fixture();\n        let (pid, status) = owned_wait(&audit, 0, Some(libc::SIGTERM), true);\n        audit.namespace_owner_exit(pid, status, true, false);\n        let result = audit.snapshot();\n        let exit = result.namespace_owner_exit.unwrap();\n        assert_eq!(exit.signal, Some(libc::SIGTERM));\n        assert!(exit.explicit_stop_requested_before_observation);\n        assert!(result.first_failure.is_none());\n        assert!(!result.recording_incomplete);\n    }\n\n    #[test]\n    fn worker_retirement_keeps_the_earlier_failure_and_exact_child_status() {\n        let audit = fixture();\n        audit.failure(FailureOrigin::Runtime, \"original enrollment failure\");\n        let (pid, status) = owned_wait(&audit, 0, Some(libc::SIGTERM), true);\n        audit.namespace_owner_exit(pid, status, false, true);\n        audit.failure(FailureOrigin::Cleanup, \"later cleanup failure\");\n        let result = audit.snapshot();\n        assert_eq!(result.first_failure.unwrap().message, \"original enrollment failure\");\n        assert_eq!(result.cleanup_failure.unwrap().message, \"later cleanup failure\");\n        assert!(result.namespace_owner_exit.unwrap().worker_retirement_started_before_observation);\n    }\n\n    #[test]\n    fn successful_owned_exit_is_observed_without_reclassifying_android_shutdown() {\n        let audit = fixture();\n        let legacy = serde_json::to_vec(&audit.snapshot()).unwrap();\n        assert!(!String::from_utf8(legacy.clone()).unwrap().contains(\"namespace_owner_exit\"));\n        let decoded: RelayLifecycleAudit = serde_json::from_slice(&legacy).unwrap();\n        assert!(decoded.namespace_owner_exit.is_none());\n        assert_eq!(serde_json::to_vec(&decoded).unwrap(), legacy);\n        let (pid, status) = owned_wait(&audit, 0, None, true);\n        assert!(status.success());\n        audit.namespace_owner_exit(pid, status, false, false);\n        let result = audit.snapshot();\n        assert_eq!(result.namespace_owner_exit.unwrap().exit_code, Some(0));\n        assert!(result.first_failure.is_none());\n        assert!(!result.recording_incomplete);\n    }\n\n    #[test]\n    fn missing_held_owner_identity_cannot_make_the_exit_record_complete() {\n        let audit = fixture();\n        let (pid, status) = owned_wait(&audit, 0, Some(libc::SIGHUP), false);\n        audit.namespace_owner_exit(pid, status, false, false);\n        let result = audit.snapshot();\n        let exit = result.namespace_owner_exit.unwrap();\n        assert_eq!(exit.raw_status, status.into_raw());\n        assert!(exit.process.is_none());\n        assert!(result.recording_incomplete);\n        assert!(result.recording_error.unwrap().contains(\"earlier held identity\"));\n    }\n\n    #[test]\n    fn saturated_init_prefix_roundtrips_without_replacing_the_lifecycle_failure() {\n        let audit = fixture();\n        audit.failure(FailureOrigin::Runtime, \"original init namespace failure\");\n        let first = audit.snapshot().first_failure;\n        let capture = init_log::Capture::new([7; 32]).unwrap();\n        // Real owned memfd plus synthetic longest bytes, not an Android log.\n        (&*capture.writer().unwrap()).write_all(&vec![0xff; init_log::CAPACITY]).unwrap();\n        let record = capture.finish(false);\n        assert!(record.capacity_reached && record.held_fds_closed);\n        assert_eq!(record.captured_hex.len(), 512 * 1024);\n        audit.init_log(record.clone());\n        let result = audit.snapshot();\n        assert_eq!(result.first_failure, first);\n        assert!(!result.recording_incomplete);\n        let encoded = serde_json::to_vec(&result).unwrap();\n        assert!(encoded.len() > 512 * 1024 && encoded.len() < 1024 * 1024);\n        let decoded: RelayLifecycleAudit = serde_json::from_slice(&encoded).unwrap();\n        assert_eq!(decoded, result);\n        // A duplicate final observation is a recording gap, never a new\n        // lifecycle success or an overwrite of the first capture/failure.\n        audit.init_log(record);\n        assert!(audit.snapshot().recording_incomplete);\n        assert_eq!(audit.snapshot().first_failure, first);\n        assert_eq!(audit.snapshot().init_log, result.init_log);\n    }\n\n    #[test]\n    fn wrong_nonce_or_overbound_log_cannot_enter_the_retained_audit() {\n        for foreign in [false, true] {\n            let audit = fixture();\n            audit.failure(FailureOrigin::Admission, \"original attach failure\");\n            let mut record = init_log::Capture::new(if foreign { [8; 32] } else { [7; 32] })\n                .unwrap().finish(false);\n            if !foreign { record.captured_bytes = init_log::CAPACITY + 1; }\n            audit.init_log(record);\n            let result = audit.snapshot();\n            assert!(result.init_log.is_none() && result.recording_incomplete);\n            assert_eq!(result.first_failure.unwrap().message, \"original attach failure\");\n        }\n    }\n\n    #[test]\n    fn missing_observation_and_clock_or_order_failure_remain_incomplete() {\n        let audit = fixture();\n        audit.record(Err(domain::error(\"failed held-pidfd observation\")));\n        audit.record(Ok(Event::Retiring));\n        audit.record(Ok(Event::Retired));\n        let result = audit.snapshot();\n        assert!(result.recording_incomplete);\n        assert_eq!(result.recording_error.as_deref(), Some(\"failed held-pidfd observation\"));\n        assert_eq!(result.records.len(), 2);\n        assert!(result.first_failure.is_none());\n        for (first, second, now) in [\n            (Event::Retiring, Event::Retiring, 2),\n            (Event::Retired, Event::Retiring, 2),\n            (Event::Retiring, Event::Retired, 0),\n            (Event::Retiring, Event::Retired, 1),\n        ] {\n            let audit = fixture();\n            audit.lock().append(first, 2);\n            audit.lock().append(second, now);\n            assert!(audit.snapshot().recording_incomplete);\n            assert_eq!(audit.snapshot().records.len(), 1);\n        }\n    }\n    #[test]\n    fn successful_retirement_does_not_erase_run_or_cleanup_failure() {\n        let audit = fixture();\n        audit.failure(FailureOrigin::Runtime, \"actual native enrollment deadline\");\n        audit.failure(FailureOrigin::Retirement, \"broker receipt unavailable\");\n        audit.failure(FailureOrigin::Cleanup, \"owned runtime could not be removed\");\n        audit.failure(FailureOrigin::Cleanup, \"retry still blocked\");\n        audit.record(Ok(Event::Retiring));\n        audit.record(Ok(Event::Retired));\n        audit.record(Ok(Event::ResourcesRemoved));\n        audit.record(Ok(Event::ClaimReleased));\n        let result = audit.snapshot();\n        assert_eq!(result.first_failure.as_ref().unwrap().origin, FailureOrigin::Runtime);\n        assert_eq!(result.first_failure.as_ref().unwrap().message, \"actual native enrollment deadline\");\n        assert_eq!(result.retirement_failure.as_ref().unwrap().message, \"broker receipt unavailable\");\n        assert_eq!(result.cleanup_failure.as_ref().unwrap().message, \"owned runtime could not be removed\");\n        assert!(!result.recording_incomplete);\n        let encoded = serde_json::to_vec(&result).unwrap();\n        assert_eq!(serde_json::from_slice::<RelayLifecycleAudit>(&encoded).unwrap(), result);\n    }\n    #[test]\n    fn oversized_payload_and_utf8_truncation_cannot_be_silent() {\n        let audit = fixture();\n        audit.record(Ok(Event::InitCommitSent { wire_hex: \"ff\".repeat(129) }));\n        assert!(audit.snapshot().records.is_empty());\n        assert!(audit.snapshot().recording_incomplete);\n        let audit = fixture();\n        audit.failure(FailureOrigin::Runtime, &\"\u754c\".repeat(600));\n        let result = audit.snapshot();\n        assert!(result.recording_incomplete);\n        assert!(result.first_failure.as_ref().unwrap().message.len() <= MAX_ERROR_BYTES);\n        let encoded = serde_json::to_vec(&result).unwrap();\n        assert!(encoded.len() < 32768);\n        assert!(serde_json::from_slice::<RelayLifecycleAudit>(&encoded).is_ok());\n    }\n    #[test]\n    fn journal_poison_is_visible_and_never_panics_during_cleanup_recording() {\n        let audit = fixture();\n        let other = audit.clone();\n        assert!(std::thread::spawn(move || {\n            let _guard = other.0.lock().unwrap();\n            panic!(\"owned audit mutex poison control\");\n        }).join().is_err());\n        audit.failure(FailureOrigin::Cleanup, \"original cleanup error\");\n        audit.record(Ok(Event::Retired));\n        let result = audit.snapshot();\n        assert!(result.recording_incomplete);\n        assert_eq!(result.first_failure.unwrap().message, \"original cleanup error\");\n        assert!(result.recording_error.unwrap().contains(\"mutex poisoned\"));\n    }\n}\nimpl Audit {\n    /// Called only after the original leader-only HostContext admission. Audit\n    /// errors are sticky observations and do not replace its capability token.\n    pub(crate) fn new(nonce: &[u8; 32], canonical_spec: &[u8; 32], host_uid: u32, policy: &PressureRelaySpec) -> Self {\n        let producer = ProducerRecord::capture();\n        let snapshot = RelayLifecycleAudit {\n            schema: 1, retained_after_exit: false,\n            nonce: policy::hex(nonce), canonical_spec_sha256: policy::hex(canonical_spec), host_uid,\n            producer: producer.as_ref().ok().cloned(),\n            memory_max_bytes: policy.memory_max_bytes, memory_high_bytes: policy.memory_high_bytes,\n            memory_swap_max_bytes: policy.memory_swap_max_bytes, cpu_quota_us: policy.cpu_quota_us,\n            cpu_period_us: policy.cpu_period_us, tasks_max: policy.tasks_max,\n            recording_incomplete: producer.is_err(), recording_error: producer.err().map(|e| bounded(&e.to_string()).0),\n            first_failure: None, retirement_failure: None, cleanup_failure: None, namespace_owner_exit: None, init_log: None,\n            records: Vec::with_capacity(MAX_RECORDS),\n        };\n        Self(Arc::new(Mutex::new(Journal { snapshot, last_rank: 0 })))\n    }\n    fn lock(&self) -> MutexGuard<'_, Journal> {\n        match self.0.lock() {\n            Ok(guard) => guard,\n            Err(poison) => {\n                let mut guard = poison.into_inner();\n                guard.gap(\"audit journal mutex poisoned\");\n                guard\n            }\n        }\n    }\n    pub(crate) fn record(&self, event: io::Result<Event>) {\n        let mut journal = self.lock();\n        match event.and_then(|event| Ok((event, monotonic_ns()?))) {\n            Ok((event, now)) => journal.append(event, now),\n            Err(error) => journal.gap(&error.to_string()),\n        }\n    }\n    pub(crate) fn failure(&self, origin: FailureOrigin, message: &str) {\n        let mut journal = self.lock();\n        let observed_monotonic_ns = monotonic_ns().unwrap_or_else(|error| {\n            journal.gap(&error.to_string()); 0\n        });\n        journal.failure(origin, message, observed_monotonic_ns);\n    }\n    /// Called only with the retained std::process::Child's actual wait result,\n    /// before cleanup requests cancellation. A later Stop cannot reclassify an\n    /// already observed failure. No serialized field is lifecycle authority.\n    pub(crate) fn namespace_owner_exit(&self, host_pid: u32, status: ExitStatus,\n        explicit_stop_requested: bool, worker_retirement_started: bool) {\n        let mut journal = self.lock();\n        if let Some(original) = &journal.snapshot.namespace_owner_exit {\n            if original.host_pid != host_pid || original.raw_status != status.into_raw() {\n                journal.gap(\"namespace owner Child wait result changed\");\n            }\n            return;\n        }\n        let observed_monotonic_ns = monotonic_ns().unwrap_or_else(|error| {\n            journal.gap(&error.to_string()); 0\n        });\n        let process = journal.snapshot.records.iter().find_map(|record| match &record.detail {\n            Event::OwnerAttached { process } if process.pid as u32 == host_pid => Some(process.clone()),\n            _ => None,\n        });\n        if process.is_none() { journal.gap(\"namespace owner exit lacks its earlier held identity\"); }\n        journal.snapshot.namespace_owner_exit = Some(NamespaceOwnerExit {\n            host_pid, process, observed_monotonic_ns,\n            raw_status: status.into_raw(), exit_code: status.code(), signal: status.signal(),\n            core_dumped: status.core_dumped(),\n            explicit_stop_requested_before_observation: explicit_stop_requested,\n            worker_retirement_started_before_observation: worker_retirement_started,\n        });\n        // Successful Android shutdown is not reclassified as an error. For a\n        // failed wait status, these flags describe observed prior intent only;\n        // neither identifies the sender of a signal or the guest boot cause.\n        if !status.success() && !explicit_stop_requested && !worker_retirement_started {\n            journal.failure(FailureOrigin::Runtime, &format!(\n                \"namespace owner Child exited before explicit stop or worker retirement: pid={host_pid} raw_status={} exit_code={:?} signal={:?} core_dumped={}\",\n                status.into_raw(), status.code(), status.signal(), status.core_dumped()), observed_monotonic_ns);\n        }\n    }\n    /// First observed run/cleanup cause for status propagation after retirement.\n    /// This does not authorize retirement, resource removal or a new generation.\n    pub(crate) fn first_failure_message(&self) -> Option<String> {\n        self.lock().snapshot.first_failure.as_ref().map(|failure| failure.message.clone())\n    }\n    pub(crate) fn snapshot(&self) -> RelayLifecycleAudit { self.lock().snapshot.clone() }\n    /// Diagnostic data only. Preserve lifecycle first_failure and every\n    /// retirement gate even if logging was unavailable, full or incomplete.\n    pub(crate) fn init_log(&self, value: init_log::Observation) {\n        let mut journal = self.lock();\n        if journal.snapshot.init_log.is_some() {\n            journal.gap(\"init log final observation supplied twice\");\n            return;\n        }\n        if value.nonce != journal.snapshot.nonce\n            || value.capacity_bytes != init_log::CAPACITY\n            || value.captured_bytes > init_log::CAPACITY\n            || value.captured_hex.len() != value.captured_bytes * 2\n        {\n            journal.gap(\"init log final observation binding/bound differs\");\n            return;\n        }\n        journal.snapshot.init_log = Some(value);\n    }\n}\n"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs": {
      "bytes": 31106,
      "sha256": "c821e6c62906c9f4d4f27c22781f7521518f715588ca3be791055d32fbed174f",
      "text": "//! Single-threaded namespace-entry half of the real init barrier.\n//!\n//! All inherited capabilities are sealed before a helper can execute. Only\n//! the constructor channel and optional bounded diagnostic writer are inherited\n//! by the final init exec. The constructor closes the former and makes the\n//! latter CLOEXEC before services may start; neither opt-in survives in env.\nuse super::capability::{self, Artifact};\nuse super::domain::{self, Identity};\nuse super::init_peer;\nuse super::init_log;\nuse super::policy::{self, PressureRelaySpec};\nuse crate::CellSpec;\nuse sha2::{Digest, Sha256};\nuse std::cell::Cell;\nuse std::ffi::{CString, OsString};\nuse std::fs::File;\nuse std::io::{self, Write};\nuse std::os::fd::{AsRawFd, FromRawFd, RawFd};\nuse std::os::unix::fs::{FileExt, MetadataExt};\nuse std::os::unix::process::CommandExt;\nuse std::path::Path;\nuse std::process::Command;\n\n/// Exact pure-CLI pairing value required before private relay entry may spawn.\npub const ABI: &str = \"droidloom-relay-entry-v3\";\npub(crate) const ENTRY_ENV: [&str; 3] = [\n    \"DROIDLOOM_RELAY_ENTRY_ABI\",\n    \"DROIDLOOM_RELAY_ENTRY_NONCE\",\n    \"DROIDLOOM_RELAY_ENTRY_SPEC_SHA256\",\n];\nconst INIT_ENV: [&str; 5] = [\n    \"DROIDLOOM_INIT_RELAY_REQUIRED\",\n    \"DROIDLOOM_INIT_RELAY_ABI\",\n    \"DROIDLOOM_INIT_RELAY_FD\",\n    \"DROIDLOOM_INIT_RELAY_NONCE\",\n    \"DROIDLOOM_INIT_RELAY_TIMEOUT_MS\",\n];\nconst FIXED: [RawFd; 4] = [\n    init_peer::CONTROL_FD,\n    init_peer::DOMAIN_FD,\n    init_peer::OWNER_FD,\n    init_peer::ENTRY_FD,\n];\nconst BOOTSTRAP: &str = \"droidloom/lmkd-bootstrap\";\nconst INIT_LINKER: &str = \"/system/bin/bootstrap/linker64\";\n#[derive(Clone, Copy, Eq, PartialEq)]\nenum ProjectionPhase { Fresh, Poisoned, Ready }\nfn error(message: &'static str) -> io::Error {\n    domain::error(message)\n}\n\npub(crate) fn spec_digest(spec: &CellSpec) -> io::Result<[u8; 32]> {\n    let bytes = serde_json::to_vec(spec).map_err(io::Error::other)?;\n    Ok(Sha256::digest(bytes).into())\n}\npub(crate) fn clean_command_environment(command: &mut Command) {\n    for key in ENTRY_ENV.into_iter().chain(INIT_ENV)\n        .chain([init_log::ENTRY_ENV, init_log::ABI_ENV, init_log::FD_ENV]) {\n        command.env_remove(key);\n    }\n}\nfn close_on_exec(fd: RawFd, enabled: bool) -> io::Result<()> {\n    let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };\n    if flags < 0 {\n        return Err(io::Error::last_os_error());\n    }\n    let flags = if enabled {\n        flags | libc::FD_CLOEXEC\n    } else {\n        flags & !libc::FD_CLOEXEC\n    };\n    if unsafe { libc::fcntl(fd, libc::F_SETFD, flags) } < 0 {\n        return Err(io::Error::last_os_error());\n    }\n    Ok(())\n}\nfn pidfd_alive(fd: &File) -> io::Result<()> {\n    let path = format!(\"/proc/self/fdinfo/{}\", fd.as_raw_fd());\n    let text = std::fs::read_to_string(path)?;\n    // The parent's PID is deliberately 0 in this child PID namespace. A Pid\n    // field plus the kernel pidfd poll semantics establishes descriptor type;\n    // no positive numeric PID is used to open, signal, or authenticate a peer.\n    let mut fields = text.lines().filter_map(|line| line.strip_prefix(\"Pid:\\t\"));\n    let pid: i64 = fields\n        .next()\n        .ok_or_else(|| error(\"entry owner FD is not a pidfd\"))?\n        .trim()\n        .parse()\n        .map_err(|_| error(\"entry owner pidfd identity malformed\"))?;\n    if pid < 0 || fields.next().is_some() {\n        return Err(error(\"entry owner pidfd retired\"));\n    }\n    let mut poll = libc::pollfd {\n        fd: fd.as_raw_fd(),\n        events: libc::POLLIN,\n        revents: 0,\n    };\n    let count = unsafe { libc::poll(&mut poll, 1, 0) };\n    if count < 0 {\n        return Err(io::Error::last_os_error());\n    }\n    if count != 0 || poll.revents != 0 {\n        return Err(error(\"entry owner is no longer alive\"));\n    }\n    Ok(())\n}\nfn require_control(fd: &File) -> io::Result<()> {\n    let mut kind: libc::c_int = 0;\n    let mut length = std::mem::size_of_val(&kind) as libc::socklen_t;\n    if unsafe {\n        libc::getsockopt(\n            fd.as_raw_fd(),\n            libc::SOL_SOCKET,\n            libc::SO_TYPE,\n            (&mut kind as *mut libc::c_int).cast(),\n            &mut length,\n        )\n    } < 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    if kind != libc::SOCK_SEQPACKET || length as usize != std::mem::size_of_val(&kind) {\n        return Err(error(\"entry control is not a seqpacket channel\"));\n    }\n    let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFL) };\n    if flags < 0 || flags & libc::O_NONBLOCK == 0 {\n        return Err(error(\"entry control is not nonblocking\"));\n    }\n    let mut peer: libc::ucred = unsafe { std::mem::zeroed() };\n    let mut size = std::mem::size_of_val(&peer) as libc::socklen_t;\n    if unsafe {\n        libc::getsockopt(\n            fd.as_raw_fd(),\n            libc::SOL_SOCKET,\n            libc::SO_PEERCRED,\n            (&mut peer as *mut libc::ucred).cast(),\n            &mut size,\n        )\n    } < 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    if peer.uid != 0\n        || peer.gid != 0\n        || peer.pid < 0\n        || size as usize != std::mem::size_of_val(&peer)\n    {\n        return Err(error(\"entry channel peer is not the root lifecycle owner\"));\n    }\n    Ok(())\n}\n\n/// Private fields make a partial inherited contract unusable by later phases.\npub(crate) struct Entry {\n    channel: File,\n    init_log: Option<File>,\n    domain: File,\n    bootstrap_leaf: File,\n    bootstrap_identity: Identity,\n    projection: Cell<ProjectionPhase>,\n    owner: File,\n    executable: Artifact,\n    policy: PressureRelaySpec,\n    nonce: [u8; 32],\n    domain_identity: Identity,\n    barrier: Artifact,\n    lmkd: Artifact,\n    prepared: bool,\n    sealed: bool,\n}\nimpl Entry {\n    /// This is the first operation in development-enter, before validation\n    /// helpers or any process spawn. Failure always terminates that entry.\n    pub(crate) fn receive(spec: &CellSpec) -> io::Result<Option<Self>> {\n        let env: Vec<Option<OsString>> = ENTRY_ENV.iter().map(std::env::var_os).collect();\n        let log_opt_in = std::env::var_os(init_log::ENTRY_ENV);\n        let leaked_init = INIT_ENV.iter().chain([&init_log::ABI_ENV, &init_log::FD_ENV])\n            .any(|key| std::env::var_os(key).is_some());\n        let Some(policy) = spec.pressure_relay.as_ref() else {\n            if env.iter().any(Option::is_some) || leaked_init || log_opt_in.is_some() {\n                return Err(error(\"relay capability environment without relay policy\"));\n            }\n            return Ok(None);\n        };\n        // Seal every known descriptor even if the textual contract is bad.\n        // Do not construct owners until sealing has succeeded for all four.\n        for fd in FIXED {\n            close_on_exec(fd, true)?;\n        }\n        if log_opt_in.is_some() { close_on_exec(init_log::FD, true)?; }\n        if log_opt_in.as_deref().is_some_and(|value| value != std::ffi::OsStr::new(init_log::ABI))\n            || (log_opt_in.is_some() && std::env::var_os(init_log::LOGGER_ENV).is_some()) {\n            return Err(error(\"entry diagnostic opt-in or ambient logger environment differs\"));\n        }\n        if leaked_init || env[0].as_deref() != Some(std::ffi::OsStr::new(ABI)) {\n            return Err(error(\"entry ABI or inherited init environment differs\"));\n        }\n        let nonce = policy::digest(\n            env[1]\n                .as_ref()\n                .and_then(|s| s.to_str())\n                .ok_or_else(|| error(\"entry nonce missing\"))?,\n        )\n        .map_err(error)?;\n        let declared = policy::digest(\n            env[2]\n                .as_ref()\n                .and_then(|s| s.to_str())\n                .ok_or_else(|| error(\"entry specification pin missing\"))?,\n        )\n        .map_err(error)?;\n        if declared != spec_digest(spec)? {\n            return Err(error(\"entry specification changed after host admission\"));\n        }\n        if unsafe { libc::getuid() } != 0\n            || unsafe { libc::geteuid() } != 0\n            || unsafe { libc::getgid() } != 0\n            || unsafe { libc::getegid() } != 0\n            || unsafe { libc::getpid() } != 1\n            || unsafe { libc::getppid() } != 0\n        {\n            return Err(error(\n                \"relay entry is not private root PID 1 with an outer owner\",\n            ));\n        }\n        // SAFETY: the private ABI transfers these four distinct inherited FDs\n        // exactly once; they have all just been sealed CLOEXEC.\n        let [channel, domain_fd, owner, executable] =\n            FIXED.map(|fd| unsafe { File::from_raw_fd(fd) });\n        let init_log = log_opt_in.map(|_| unsafe { File::from_raw_fd(init_log::FD) });\n        if let Some(log) = &init_log {\n            init_log::validate_writer(log)?;\n            if unsafe { libc::lseek(log.as_raw_fd(), 0, libc::SEEK_CUR) } != 0 {\n                return Err(error(\"entry diagnostic writer was already used\"));\n            }\n        }\n        if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } < 0 {\n            return Err(io::Error::last_os_error());\n        }\n        // The pidfd closes the race where the outside parent died before\n        // PR_SET_PDEATHSIG could be armed in this new PID namespace.\n        pidfd_alive(&owner)?;\n        require_control(&channel)?;\n        let executable = Artifact::from_file(\n            executable,\n            policy::digest(&policy.entry_supervisor.sha256).map_err(error)?,\n            true,\n        )?;\n        let actual = File::open(\"/proc/self/exe\")?;\n        if Identity::of(&actual)? != executable.identity()\n            || capability::hash(&actual)? != executable.digest()\n        {\n            return Err(error(\n                \"actual entry executable differs from inherited package pin\",\n            ));\n        }\n        let barrier = Artifact::open(&policy.init_barrier, false)?;\n        let lmkd = Artifact::open(&policy.lmkd, true)?;\n        let domain_identity = Identity::of(&domain_fd)?;\n        let bootstrap_leaf = domain::open_bootstrap(&domain_fd)?;\n        let bootstrap_identity = Identity::of(&bootstrap_leaf)?;\n        domain::enter_self(&domain_fd, policy)?;\n        pidfd_alive(&owner)?;\n        Ok(Some(Self {\n            channel,\n            init_log,\n            domain: domain_fd,\n            bootstrap_leaf,\n            bootstrap_identity,\n            projection: Cell::new(ProjectionPhase::Fresh),\n            owner,\n            executable,\n            policy: policy.clone(),\n            nonce,\n            domain_identity,\n            barrier,\n            lmkd,\n            prepared: false,\n            sealed: false,\n        }))\n    }\n\n    /// Runs after the normal image overlays, but before pivot_root or init.\n    pub(crate) fn prepare_image(&mut self, root_path: &Path) -> io::Result<()> {\n        if self.prepared || self.sealed {\n            return Err(error(\"relay image preparation is a single attempt\"));\n        }\n        self.sealed = true; // Any partial mount failure permanently closes this entry.\n        pidfd_alive(&self.owner)?;\n        self.executable.validate(true)?;\n        self.barrier.validate(true)?;\n        self.lmkd.validate(true)?;\n        let root = domain::directory(root_path)?;\n        let init = Artifact::from_file(\n            domain::beneath(&root, \"system/bin/init\", libc::O_RDONLY)?,\n            policy::digest(&self.policy.init_sha256).map_err(error)?,\n            true,\n        )?;\n        require_init_alias(&root, init.identity())?;\n        require_interpreter(init.file(), INIT_LINKER)?;\n        let linker = Artifact::from_file(\n            domain::beneath(&root, INIT_LINKER.trim_start_matches('/'), libc::O_RDONLY)?,\n            policy::digest(&self.policy.init_linker_sha256).map_err(error)?,\n            true,\n        )?;\n        let compat = Artifact::from_file(\n            domain::beneath(\n                &root,\n                init_peer::COMPAT.trim_start_matches('/'),\n                libc::O_RDONLY,\n            )?,\n            policy::digest(&self.policy.compat_preload_sha256).map_err(error)?,\n            false,\n        )?;\n        let old_rc = Artifact::from_file(\n            domain::beneath(&root, \"system/etc/init/lmkd.rc\", libc::O_RDONLY)?,\n            policy::digest(&self.policy.lmkd_rc_sha256).map_err(error)?,\n            false,\n        )?;\n        let droidloom = make_parent(&root, \"droidloom\")?;\n        if unsafe { libc::mkdirat(droidloom.as_raw_fd(), c\"lmkd-bootstrap\".as_ptr(), 0o755) } != 0 {\n            return Err(io::Error::last_os_error());\n        }\n        let directory = domain::named(\n            &droidloom,\n            \"lmkd-bootstrap\",\n            libc::O_RDONLY | libc::O_DIRECTORY,\n        )?;\n        for (name, mode) in [(\"libdroidloom_init_relay.so\", 0o644), (\"lmkd\", 0o755)] {\n            drop(domain::at(\n                directory.as_raw_fd(),\n                &CString::new(name).expect(\"fixed name\"),\n                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,\n                mode,\n            )?);\n        }\n        bind_readonly(\n            &root,\n            &format!(\"{BOOTSTRAP}/libdroidloom_init_relay.so\"),\n            self.barrier.file(),\n        )?;\n        bind_readonly(&root, &format!(\"{BOOTSTRAP}/lmkd\"), self.lmkd.file())?;\n        let mut generated = domain::at(\n            directory.as_raw_fd(),\n            c\"lmkd.rc\",\n            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,\n            0o644,\n        )?;\n        generated.write_all(lmkd_rc(self.policy.lmkd_uid, self.policy.lmkd_gid).as_bytes())?;\n        generated.sync_all()?;\n        old_rc.validate(true)?;\n        bind_readonly(&root, \"system/etc/init/lmkd.rc\", &generated)?;\n        // Preserve the pre-existing loader/preload pair and a non-set-ID init\n        // on an explicit nosuid read-only bind before relying on PDEATHSIG.\n        bind_readonly(&root, \"system/bin/init\", init.file())?;\n        init.validate(true)?;\n        linker.validate(true)?;\n        compat.validate(true)?;\n        self.barrier.validate(true)?;\n        self.lmkd.validate(true)?;\n        self.prepared = true;\n        self.sealed = false;\n        pidfd_alive(&self.owner)\n    }\n\n    /// cpu_placement::prepare has sealed CLONE_NEWCGROUP immediately before\n    /// this call. Its v2 namespace root must be the exact inherited domain.\n    pub(crate) fn project_cgroup(&self, root: &Path) -> io::Result<()> {\n        if !self.prepared || self.sealed {\n            return Err(error(\"relay image is not prepared\"));\n        }\n        if self.projection.replace(ProjectionPhase::Poisoned) != ProjectionPhase::Fresh {\n            return Err(error(\"relay cgroup projection is a single attempt\"));\n        }\n        pidfd_alive(&self.owner)?;\n        if Identity::of(&self.domain)? != self.domain_identity {\n            return Err(error(\"held domain identity changed\"));\n        }\n        domain::mount_private_view(root, self.domain_identity)?;\n        domain::enter_bootstrap(&self.domain, &self.bootstrap_leaf,\n                                self.bootstrap_identity, &self.policy)?;\n        self.projection.set(ProjectionPhase::Ready);\n        Ok(())\n    }\n\n    /// Attach only to the final /init second_stage command. No ordinary\n    /// helper may inherit these capabilities or the private opt-in variables.\n    pub(crate) fn configure_init(&mut self, command: &mut Command) -> io::Result<()> {\n        if !self.prepared || self.sealed || self.projection.get() != ProjectionPhase::Ready {\n            return Err(error(\"init release preparation reused or incomplete\"));\n        }\n        self.sealed = true;\n        domain::validate_entry_bootstrap(&self.domain, &self.bootstrap_leaf,\n                                         self.bootstrap_identity, &self.policy)?;\n        require_init_command(command)?;\n        pidfd_alive(&self.owner)?;\n        self.barrier.validate(false)?;\n        self.lmkd.validate(false)?;\n        clean_command_environment(command);\n        command\n            .env(\"LD_PRELOAD\", init_peer::preload())\n            .env(INIT_ENV[0], \"1\")\n            .env(INIT_ENV[1], init_peer::INIT_ABI_TEXT)\n            .env(INIT_ENV[2], init_peer::CONTROL_FD.to_string())\n            .env(INIT_ENV[3], policy::hex(&self.nonce))\n            .env(INIT_ENV[4], self.policy.bootstrap_timeout_ms.to_string());\n        if let Some(log) = &self.init_log {\n            init_log::validate_writer(log)?;\n            command.env_remove(init_log::LOGGER_ENV)\n                .env(init_log::ABI_ENV, init_log::ABI)\n                .env(init_log::FD_ENV, init_log::FD.to_string());\n        }\n        let control = self.channel.as_raw_fd();\n        let log = self.init_log.as_ref().map(AsRawFd::as_raw_fd);\n        let owner = self.owner.as_raw_fd();\n        let domain = self.domain.as_raw_fd();\n        let domain_identity = self.domain_identity;\n        let bootstrap = self.bootstrap_leaf.as_raw_fd();\n        let bootstrap_identity = self.bootstrap_identity;\n        // SAFETY: the entry is single-threaded. This pre-exec closure performs\n        // only async-signal-safe syscalls and changes no shared parent state.\n        unsafe {\n            command.pre_exec(move || {\n                // This is the final pre-exec callback, after any CPU placement\n                // callbacks. Keep the inherited parent-death link explicit at\n                // the exact direct, nonprivileged init exec boundary.\n                if libc::getuid() != 0\n                    || libc::geteuid() != 0\n                    || libc::getgid() != 0\n                    || libc::getegid() != 0\n                    || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0\n                {\n                    return Err(io::Error::other(\n                        \"init credentials or parent-death contract changed before exec\",\n                    ));\n                }\n                let mut poll = libc::pollfd {\n                    fd: owner,\n                    events: libc::POLLIN,\n                    revents: 0,\n                };\n                if libc::poll(&mut poll, 1, 0) != 0 || poll.revents != 0 {\n                    return Err(io::Error::other(\n                        \"entry owner died immediately before init exec\",\n                    ));\n                }\n                domain::validate_bootstrap_before_exec(domain, domain_identity,\n                                                       bootstrap, bootstrap_identity)?;\n                close_on_exec(control, false)?;\n                if let Some(log) = log { close_on_exec(log, false)?; }\n                Ok(())\n            });\n        }\n        Ok(())\n    }\n}\n\nfn require_init_command(command: &Command) -> io::Result<()> {\n    let mut args = command.get_args();\n    if command.get_program() != std::ffi::OsStr::new(\"/init\")\n        || args.next() != Some(std::ffi::OsStr::new(\"second_stage\"))\n        || args.next().is_some()\n    {\n        return Err(error(\n            \"relay barrier requires a direct exact /init second_stage exec\",\n        ));\n    }\n    Ok(())\n}\n\nfn make_parent(root: &File, name: &str) -> io::Result<File> {\n    let name = CString::new(name).map_err(|_| error(\"invalid fixed parent\"))?;\n    if unsafe { libc::mkdirat(root.as_raw_fd(), name.as_ptr(), 0o755) } != 0 {\n        let e = io::Error::last_os_error();\n        if e.kind() != io::ErrorKind::AlreadyExists {\n            return Err(e);\n        }\n    }\n    let file = domain::at(\n        root.as_raw_fd(),\n        &name,\n        libc::O_RDONLY | libc::O_DIRECTORY,\n        0,\n    )?;\n    let m = file.metadata()?;\n    if m.uid() != 0 || m.mode() & 0o022 != 0 {\n        return Err(error(\"bootstrap parent is writable by another role\"));\n    }\n    Ok(file)\n}\nfn bind_readonly(root: &File, relative: &str, source: &File) -> io::Result<()> {\n    let target = domain::beneath(root, relative, libc::O_PATH)?;\n    if !target.metadata()?.is_file() || !source.metadata()?.is_file() {\n        return Err(error(\"readonly overlay is not a regular file\"));\n    }\n    let source_path =\n        CString::new(format!(\"/proc/self/fd/{}\", source.as_raw_fd())).expect(\"descriptor path\");\n    let target_path =\n        CString::new(format!(\"/proc/self/fd/{}\", target.as_raw_fd())).expect(\"descriptor path\");\n    if unsafe {\n        libc::mount(\n            source_path.as_ptr(),\n            target_path.as_ptr(),\n            std::ptr::null(),\n            libc::MS_BIND,\n            std::ptr::null(),\n        )\n    } != 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    // Reopen through the held root after binding: the old target FD still\n    // names the covered mount and cannot identify the newly attached mount.\n    let mounted = domain::beneath(root, relative, libc::O_PATH)?;\n    if Identity::of(&mounted)? != Identity::of(source)? {\n        return Err(error(\"readonly overlay identity mismatch\"));\n    }\n    let target_path =\n        CString::new(format!(\"/proc/self/fd/{}\", mounted.as_raw_fd())).expect(\"descriptor path\");\n    if unsafe {\n        libc::mount(\n            std::ptr::null(),\n            target_path.as_ptr(),\n            std::ptr::null(),\n            libc::MS_BIND | libc::MS_REMOUNT | libc::MS_RDONLY | libc::MS_NOSUID | libc::MS_NODEV,\n            std::ptr::null(),\n        )\n    } != 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    Ok(())\n}\nfn require_init_alias(root: &File, expected: Identity) -> io::Result<()> {\n    let alias = domain::named(root, \"init\", libc::O_PATH)?;\n    if alias.metadata()?.file_type().is_symlink() {\n        let mut buffer = [0u8; 256];\n        let count = unsafe {\n            libc::readlinkat(\n                root.as_raw_fd(),\n                c\"init\".as_ptr(),\n                buffer.as_mut_ptr().cast(),\n                buffer.len(),\n            )\n        };\n        if count < 0 {\n            return Err(io::Error::last_os_error());\n        }\n        let value = &buffer[..count as usize];\n        if value != b\"system/bin/init\" && value != b\"/system/bin/init\" {\n            return Err(error(\"/init alias is not the paired executable\"));\n        }\n    } else if !alias.metadata()?.is_file() || Identity::of(&alias)? != expected {\n        return Err(error(\"/init is not the paired executable inode\"));\n    }\n    Ok(())\n}\nfn read_exact(file: &File, buffer: &mut [u8], offset: u64) -> io::Result<()> {\n    let mut filled = 0;\n    while filled != buffer.len() {\n        let count = file.read_at(&mut buffer[filled..], offset + filled as u64)?;\n        if count == 0 {\n            return Err(error(\"ELF input truncated\"));\n        }\n        filled += count;\n    }\n    Ok(())\n}\nfn require_interpreter(file: &File, expected: &str) -> io::Result<()> {\n    let mut header = [0u8; 64];\n    read_exact(file, &mut header, 0)?;\n    let u16_at = |at| u16::from_le_bytes(header[at..at + 2].try_into().expect(\"header width\"));\n    let u64_at = |at| u64::from_le_bytes(header[at..at + 8].try_into().expect(\"header width\"));\n    #[cfg(target_arch = \"x86_64\")]\n    let machine = 62;\n    #[cfg(target_arch = \"aarch64\")]\n    let machine = 183;\n    if &header[..7] != b\"\\x7fELF\\x02\\x01\\x01\"\n        || !matches!(u16_at(16), 2 | 3)\n        || u16_at(18) != machine\n        || u16_at(52) != 64\n        || u16_at(54) != 56\n        || u16_at(56) == 0\n        || u16_at(56) > 1024\n    {\n        return Err(error(\"init is not a bounded native ELF64 executable\"));\n    }\n    let bytes = file.metadata()?.size();\n    let start = u64_at(32);\n    let end = start\n        .checked_add(u64::from(u16_at(56)) * 56)\n        .ok_or_else(|| error(\"ELF headers overflow\"))?;\n    if end > bytes {\n        return Err(error(\"ELF program headers exceed file\"));\n    }\n    let mut found = false;\n    for index in 0..u16_at(56) {\n        let mut ph = [0u8; 56];\n        read_exact(file, &mut ph, start + u64::from(index) * 56)?;\n        if u32::from_le_bytes(ph[..4].try_into().expect(\"program type\")) != 3 {\n            continue;\n        }\n        let offset = u64::from_le_bytes(ph[8..16].try_into().expect(\"program offset\"));\n        let size = u64::from_le_bytes(ph[32..40].try_into().expect(\"program size\"));\n        if found\n            || size != expected.len() as u64 + 1\n            || offset.checked_add(size).is_none_or(|n| n > bytes)\n        {\n            return Err(error(\n                \"init PT_INTERP duplicate or outside paired loader contract\",\n            ));\n        }\n        let mut interpreter = vec![0; size as usize];\n        read_exact(file, &mut interpreter, offset)?;\n        if interpreter.last() != Some(&0)\n            || &interpreter[..interpreter.len() - 1] != expected.as_bytes()\n        {\n            return Err(error(\n                \"init dynamic loader differs from paired bootstrap linker\",\n            ));\n        }\n        found = true;\n    }\n    if !found {\n        return Err(error(\n            \"init has no PT_INTERP; constructor cannot be guaranteed\",\n        ));\n    }\n    Ok(())\n}\nfn lmkd_rc(uid: u32, gid: u32) -> String {\n    // Do not use escaped physical newlines: Rust strips their leading\n    // whitespace and would remove the service-option indentation.\n    format!(\n        concat!(\n            \"# Package-owned native relay LMKD; init constructor owns the startup barrier.\\n\",\n            \"service lmkd {}\\n\",\n            \"    class core\\n\",\n            \"    user {}\\n\",\n            \"    group {} system readproc\\n\",\n            \"    capabilities DAC_OVERRIDE KILL IPC_LOCK SYS_NICE SYS_RESOURCE\\n\",\n            \"    socket lmkd seqpacket+passcred 0660 system system\\n\",\n            \"    task_profiles ServiceCapacityLow\\n\",\n            \"    stdio_to_kmsg\\n\",\n            \"    setenv DROIDLOOM_CELL 1\\n\",\n            \"    setenv DROIDLOOM_LMKD_CGROUP /sys/fs/cgroup\\n\",\n            \"    setenv DROIDLOOM_LMKD_PRESSURE relay-required\\n\",\n        ),\n        init_peer::LMKD,\n        uid,\n        gid\n    )\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    use std::os::unix::fs::symlink;\n    #[test]\n    fn final_init_exec_contract_rejects_wrappers_and_other_stage() {\n        let mut command = Command::new(\"/init\");\n        command.arg(\"second_stage\");\n        require_init_command(&command).unwrap();\n        command.arg(\"unexpected\");\n        assert!(require_init_command(&command).is_err());\n        let mut wrong = Command::new(\"/init\");\n        wrong.arg(\"first_stage\");\n        assert!(require_init_command(&wrong).is_err());\n        let mut wrapper = Command::new(\"taskset\");\n        wrapper.args([\"/init\", \"second_stage\"]);\n        assert!(require_init_command(&wrapper).is_err());\n    }\n    #[test]\n    fn generated_native_lmkd_options_remain_inside_one_service_block() {\n        let text = lmkd_rc(1069, 1069);\n        let mut lines = text\n            .lines()\n            .filter(|line| !line.is_empty() && !line.starts_with('#'));\n        assert_eq!(\n            lines.next(),\n            Some(\"service lmkd /droidloom/lmkd-bootstrap/lmkd\")\n        );\n        let options: Vec<_> = lines.collect();\n        assert_eq!(options.len(), 10);\n        assert!(\n            options\n                .iter()\n                .all(|line| line.starts_with(\"    \") && !line.starts_with(\"     \"))\n        );\n        assert!(options.contains(&\"    user 1069\"));\n        assert!(options.contains(&\"    group 1069 system readproc\"));\n        assert!(options.contains(&\"    setenv DROIDLOOM_LMKD_PRESSURE relay-required\"));\n    }\n    #[test]\n    fn init_alias_cannot_escape_the_private_image() {\n        let temp = tempfile::tempdir().unwrap();\n        let root = domain::directory(temp.path()).unwrap();\n        symlink(\"../../host/init\", temp.path().join(\"init\")).unwrap();\n        assert!(\n            require_init_alias(\n                &root,\n                Identity {\n                    device: 1,\n                    inode: 1\n                }\n            )\n            .is_err()\n        );\n        std::fs::remove_file(temp.path().join(\"init\")).unwrap();\n        symlink(\"/system/bin/init\", temp.path().join(\"init\")).unwrap();\n        require_init_alias(\n            &root,\n            Identity {\n                device: 1,\n                inode: 1,\n            },\n        )\n        .unwrap();\n    }\n    #[test]\n    fn wrong_or_missing_dynamic_loader_cannot_open_init_barrier() {\n        let mut file = tempfile::tempfile().unwrap();\n        let mut bytes = vec![0u8; 256];\n        bytes[..7].copy_from_slice(b\"\\x7fELF\\x02\\x01\\x01\");\n        bytes[16..18].copy_from_slice(&3u16.to_le_bytes());\n        #[cfg(target_arch = \"x86_64\")]\n        bytes[18..20].copy_from_slice(&62u16.to_le_bytes());\n        #[cfg(target_arch = \"aarch64\")]\n        bytes[18..20].copy_from_slice(&183u16.to_le_bytes());\n        bytes[32..40].copy_from_slice(&64u64.to_le_bytes());\n        bytes[52..54].copy_from_slice(&64u16.to_le_bytes());\n        bytes[54..56].copy_from_slice(&56u16.to_le_bytes());\n        bytes[56..58].copy_from_slice(&1u16.to_le_bytes());\n        bytes[64..68].copy_from_slice(&3u32.to_le_bytes());\n        bytes[72..80].copy_from_slice(&128u64.to_le_bytes());\n        bytes[96..104].copy_from_slice(&(INIT_LINKER.len() as u64 + 1).to_le_bytes());\n        bytes[128..128 + INIT_LINKER.len()].copy_from_slice(INIT_LINKER.as_bytes());\n        file.write_all(&bytes).unwrap();\n        require_interpreter(&file, INIT_LINKER).unwrap();\n        file.write_at(b\"x\", 128).unwrap();\n        assert!(require_interpreter(&file, INIT_LINKER).is_err());\n        file.write_at(&0u32.to_le_bytes(), 64).unwrap();\n        assert!(require_interpreter(&file, INIT_LINKER).is_err());\n        file.set_len(63).unwrap();\n        assert!(require_interpreter(&file, INIT_LINKER).is_err());\n    }\n    #[test]\n    fn ordinary_file_does_not_substitute_for_entry_owner_pidfd() {\n        let file = tempfile::tempfile().unwrap();\n        assert!(pidfd_alive(&file).is_err());\n        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) };\n        assert!(raw >= 0);\n        let pidfd = unsafe { File::from_raw_fd(raw as i32) };\n        pidfd_alive(&pidfd).unwrap();\n    }\n    #[test]\n    fn sealed_fixed_capabilities_do_not_reach_an_ordinary_exec() {\n        let source = tempfile::tempfile().unwrap();\n        let high = unsafe { libc::fcntl(source.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 256) };\n        assert!(high >= 256);\n        let source = unsafe { File::from_raw_fd(high) };\n        for sealed in [false, true] {\n            let raw = source.as_raw_fd();\n            let mut command = Command::new(\"/bin/sh\");\n            command.args([\n                \"-c\",\n                \"for n in 198 199 200 201; do if [ -e /proc/self/fd/$n ]; then exit 9; fi; done\",\n            ]);\n            unsafe {\n                command.pre_exec(move || {\n                    for target in FIXED {\n                        if libc::dup2(raw, target) < 0 {\n                            return Err(io::Error::last_os_error());\n                        }\n                        close_on_exec(target, sealed)?;\n                    }\n                    Ok(())\n                });\n            }\n            let status = command.status().unwrap();\n            assert_eq!(status.code(), Some(if sealed { 0 } else { 9 }));\n        }\n    }\n}\n"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/init_log.rs": {
      "bytes": 15994,
      "sha256": "bd376b6b334776c25ec1276acb4c0232d00baaf80c6051e10ec2da75f7100ac2",
      "text": "//! A bounded, generation-private diagnostic sink, never lifecycle authority.\n//!\n//! The paired constructor primes the actual loaded KernelLogger with a nonce\n//! marker, then removes its temporary environment and seals the writer across\n//! exec. The host checks the bytes after the real HELLO identity admission.\n//! A fixed-size shmem file has no reader dependency and cannot grow on overflow.\n//! This captures a prefix, not a promise that every logger write succeeded.\nuse super::domain::{self, Identity};\nuse super::policy;\nuse serde::{Deserialize, Serialize};\nuse sha2::{Digest, Sha256};\nuse std::fs::{File, OpenOptions};\nuse std::io;\nuse std::os::fd::{AsRawFd, FromRawFd, IntoRawFd, RawFd};\nuse std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};\nuse std::sync::{Arc, Mutex};\n\npub(crate) const FD: RawFd = 202;\npub(crate) const CAPACITY: usize = 256 * 1024;\npub(crate) const ENTRY_ENV: &str = \"DROIDLOOM_RELAY_ENTRY_INIT_LOG\";\npub(crate) const ABI_ENV: &str = \"DROIDLOOM_INIT_LOG_ABI\";\npub(crate) const FD_ENV: &str = \"DROIDLOOM_INIT_LOG_FD\";\npub(crate) const LOGGER_ENV: &str = \"ANDROID_FILE__dev_kmsg\";\npub(crate) const ABI: &str = \"1\";\nconst SEALS: i32 = libc::F_SEAL_GROW | libc::F_SEAL_SHRINK | libc::F_SEAL_SEAL;\n\nfn error(message: &'static str) -> io::Error { domain::error(message) }\n\npub(crate) fn marker(nonce: &[u8; 32]) -> Vec<u8> {\n    format!(\"<6>droidloom-init-log: P4_INIT_LOG_V1 nonce={}\\n<6>droidloom-init-log: P4_INIT_LOG_CACHED_V1 nonce={}\\n\",\n        policy::hex(nonce), policy::hex(nonce)).into_bytes()\n}\n\n/// Validate only the explicitly inherited diagnostic writer. A pipe, socket,\n/// ordinary file, arbitrary size, append position or writable growth is denied.\npub(crate) fn validate_writer(file: &File) -> io::Result<Identity> {\n    let m = file.metadata()?;\n    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };\n    if flags < 0 { return Err(io::Error::last_os_error()); }\n    let seals = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GET_SEALS) };\n    if seals < 0 { return Err(io::Error::last_os_error()); }\n    let mut fs: libc::statfs = unsafe { std::mem::zeroed() };\n    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } < 0 {\n        return Err(io::Error::last_os_error());\n    }\n    if !m.is_file() || m.uid() != unsafe { libc::geteuid() }\n        || m.gid() != unsafe { libc::getegid() } || m.nlink() != 0\n        || m.mode() & 0o7777 != 0o600 || m.size() != CAPACITY as u64\n        || flags & libc::O_ACCMODE != libc::O_WRONLY || flags & libc::O_NONBLOCK == 0\n        || flags & (libc::O_APPEND | libc::O_PATH) != 0 || seals != SEALS\n        || fs.f_type as u64 != 0x0102_1994\n    {\n        return Err(error(\"init diagnostic writer identity/type/flags/seals differ\"));\n    }\n    Identity::of(file)\n}\n\n#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]\npub(crate) struct Observation {\n    pub schema: u32,\n    pub nonce: String,\n    pub device: u64,\n    pub inode: u64,\n    pub capacity_bytes: usize,\n    pub marker_verified_after_held_init_hello: bool,\n    pub retirement_proven_before_capture: bool,\n    pub observed_writer_offset: Option<u64>,\n    pub captured_bytes: usize,\n    pub captured_sha256: String,\n    pub captured_hex: String,\n    pub capacity_reached: bool,\n    pub stream_completeness_claimed: bool,\n    pub exact_writer_per_line_proven: bool,\n    pub source_scope: String,\n    pub first_error: Option<String>,\n    pub secondary_errors: Vec<String>,\n    pub held_fds_closed: bool,\n}\nimpl Observation {\n    fn remember(&mut self, message: String) {\n        let mut end = message.len().min(512);\n        while !message.is_char_boundary(end) { end -= 1; }\n        let message = message[..end].to_owned();\n        if self.first_error.is_none() { self.first_error = Some(message); }\n        else if self.secondary_errors.len() < 4 { self.secondary_errors.push(message); }\n    }\n}\n\npub(crate) struct Capture {\n    read: Option<File>,\n    write: Option<File>,\n    identity: Identity,\n    nonce: [u8; 32],\n    admission_attempted: bool,\n    primed: bool,\n}\n\n/// Owner retains the same sink through every fallible attach/start step. A\n/// partially constructed Session or failed worker spawn cannot silently drop\n/// the only copy. Capture/close is still a single take of the actual two FDs.\n#[derive(Clone)]\npub(crate) struct SharedCapture(Arc<Mutex<Option<Capture>>>);\nimpl SharedCapture {\n    pub(crate) fn new(nonce: [u8; 32]) -> io::Result<Self> {\n        Ok(Self(Arc::new(Mutex::new(Some(Capture::new(nonce)?)))))\n    }\n    pub(crate) fn duplicate_writer(&self) -> io::Result<File> {\n        let held = self.0.lock().map_err(|_| error(\"init log owner lock poisoned\"))?;\n        held.as_ref().ok_or_else(|| error(\"init log capture already finalized\"))?.writer()?.try_clone()\n    }\n    pub(crate) fn require_marker(&self) -> io::Result<()> {\n        let mut held = self.0.lock().map_err(|_| error(\"init log owner lock poisoned\"))?;\n        held.as_mut().ok_or_else(|| error(\"init log capture already finalized\"))?.require_marker()\n    }\n    pub(crate) fn finish(&self, retired: bool) -> Option<Observation> {\n        let (capture, poisoned) = match self.0.lock() {\n            Ok(mut held) => (held.take(), false),\n            Err(poison) => (poison.into_inner().take(), true),\n        };\n        let mut result = capture?.finish(retired && !poisoned);\n        if poisoned { result.remember(\"init log owner lock poisoned\".into()); }\n        Some(result)\n    }\n}\nimpl Capture {\n    pub(crate) fn new(nonce: [u8; 32]) -> io::Result<Self> {\n        let fd = unsafe {\n            libc::memfd_create(c\"droidloom-init-log\".as_ptr(), libc::MFD_CLOEXEC | libc::MFD_ALLOW_SEALING)\n        };\n        if fd < 0 { return Err(io::Error::last_os_error()); }\n        let read = unsafe { File::from_raw_fd(fd) };\n        if unsafe { libc::fchmod(fd, 0o600) } < 0\n            || unsafe { libc::ftruncate(fd, CAPACITY as libc::off_t) } < 0\n        {\n            return Err(io::Error::last_os_error());\n        }\n        if unsafe { libc::fcntl(fd, libc::F_ADD_SEALS, SEALS) } < 0 {\n            return Err(io::Error::last_os_error());\n        }\n        // Reopening our own anonymous object creates a write-only OFD. The\n        // parent retains this OFD solely to observe its final offset; pread on\n        // the other OFD never changes the logger's position.\n        let write = OpenOptions::new().write(true)\n            .custom_flags(libc::O_NONBLOCK | libc::O_CLOEXEC)\n            .open(format!(\"/proc/self/fd/{fd}\"))?;\n        let identity = validate_writer(&write)?;\n        if Identity::of(&read)? != identity { return Err(error(\"init log reopen changed inode\")); }\n        let result = Self { read: Some(read), write: Some(write), identity, nonce,\n            admission_attempted: false, primed: false };\n        if result.position()? != 0 { return Err(error(\"new init log writer offset is not zero\")); }\n        Ok(result)\n    }\n\n    pub(crate) fn writer(&self) -> io::Result<&File> {\n        self.write.as_ref().ok_or_else(|| error(\"init log writer was already consumed\"))\n    }\n    fn reader(&self) -> io::Result<&File> {\n        self.read.as_ref().ok_or_else(|| error(\"init log reader was already consumed\"))\n    }\n    fn position(&self) -> io::Result<u64> {\n        let value = unsafe { libc::lseek(self.writer()?.as_raw_fd(), 0, libc::SEEK_CUR) };\n        if value < 0 { return Err(io::Error::last_os_error()); }\n        if value as u64 > CAPACITY as u64 { return Err(error(\"init log offset exceeds fixed capacity\")); }\n        Ok(value as u64)\n    }\n    fn validate(&self) -> io::Result<()> {\n        if validate_writer(self.writer()?)? != self.identity\n            || Identity::of(self.reader()?)? != self.identity\n        {\n            return Err(error(\"held init log identity changed\"));\n        }\n        Ok(())\n    }\n    /// Called only after InitPeer::accept has retained the real init process,\n    /// executable and namespace proof, and before creating the relay broker.\n    pub(crate) fn require_marker(&mut self) -> io::Result<()> {\n        if self.admission_attempted { return Err(error(\"init logger marker admission is one attempt\")); }\n        self.admission_attempted = true;\n        self.validate()?;\n        let expected = marker(&self.nonce);\n        if self.position()? < expected.len() as u64 {\n            return Err(error(\"actual init KernelLogger did not write its generation marker\"));\n        }\n        let mut actual = vec![0; expected.len()];\n        self.reader()?.read_exact_at(&mut actual, 0)?;\n        if actual != expected { return Err(error(\"actual init logger marker differs\")); }\n        self.validate()?;\n        self.primed = true;\n        Ok(())\n    }\n    /// Capture a stable prefix after retirement where possible. A failed\n    /// retirement is explicitly labelled; its diagnostic read cannot certify\n    /// that init stopped, that writes are complete, or that every line came\n    /// from PID1 (pre-exec fork children may share the cached descriptor).\n    pub(crate) fn finish(mut self, retired: bool) -> Observation {\n        let mut out = Observation {\n            schema: 1, nonce: policy::hex(&self.nonce), device: self.identity.device,\n            inode: self.identity.inode, capacity_bytes: CAPACITY,\n            marker_verified_after_held_init_hello: self.primed,\n            retirement_proven_before_capture: retired, observed_writer_offset: None,\n            captured_bytes: 0, captured_sha256: policy::hex(&Sha256::digest(b\"\")),\n            captured_hex: String::new(), capacity_reached: false,\n            stream_completeness_claimed: false, exact_writer_per_line_proven: false,\n            source_scope: \"generation-private cached init logger; fork-before-exec writers not individually attributed\".into(),\n            first_error: None, secondary_errors: Vec::new(), held_fds_closed: false,\n        };\n        let captured = (|| -> io::Result<()> {\n            self.validate()?;\n            let before = self.position()?;\n            out.observed_writer_offset = Some(before);\n            out.capacity_reached = before == CAPACITY as u64;\n            let mut raw = vec![0; before as usize];\n            self.reader()?.read_exact_at(&mut raw, 0)?;\n            out.captured_bytes = raw.len();\n            out.captured_sha256 = policy::hex(&Sha256::digest(&raw));\n            out.captured_hex = policy::hex(&raw);\n            self.validate()?;\n            if self.position()? != before {\n                return Err(error(\"init diagnostic writer moved during final capture\"));\n            }\n            Ok(())\n        })();\n        if let Err(error) = captured { out.remember(error.to_string()); }\n        // Explicit one-attempt close evidence; never retry a possibly reused\n        // integer. The original capture error remains primary.\n        let mut all_closed = true;\n        for file in [self.write.take(), self.read.take()].into_iter().flatten() {\n            if unsafe { libc::close(file.into_raw_fd()) } < 0 {\n                all_closed = false;\n                out.remember(format!(\"close init diagnostic FD: {}\", io::Error::last_os_error()));\n            }\n        }\n        out.held_fds_closed = all_closed;\n        out\n    }\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    use std::io::Write;\n    use std::os::unix::process::CommandExt;\n    use std::process::Command;\n\n    #[test]\n    fn real_memfd_is_bounded_and_preserves_the_observed_prefix() {\n        let mut capture = Capture::new([7; 32]).unwrap();\n        // Explicit synthetic logger bytes; this is not Android ABI evidence.\n        let head = marker(&[7; 32]);\n        (&*capture.writer().unwrap()).write_all(&head).unwrap();\n        capture.require_marker().unwrap();\n        let tail = vec![b'x'; CAPACITY - head.len()];\n        (&*capture.writer().unwrap()).write_all(&tail).unwrap();\n        let overflow = (&*capture.writer().unwrap()).write(b\"overflow\").unwrap_err();\n        assert_eq!(overflow.raw_os_error(), Some(libc::EPERM));\n        let record = capture.finish(true);\n        assert!(record.marker_verified_after_held_init_hello && record.capacity_reached);\n        assert_eq!(record.captured_bytes, CAPACITY);\n        assert!(record.captured_hex.starts_with(&policy::hex(&head)));\n        assert!(record.held_fds_closed && record.first_error.is_none());\n        assert!(!record.stream_completeness_claimed && !record.exact_writer_per_line_proven);\n    }\n\n    #[test]\n    fn missing_or_foreign_marker_never_admits_a_generation() {\n        let mut capture = Capture::new([8; 32]).unwrap();\n        assert!(capture.require_marker().is_err());\n        (&*capture.writer().unwrap()).write_all(&marker(&[8; 32])).unwrap();\n        assert!(capture.require_marker().is_err());\n        let record = capture.finish(false);\n        assert!(!record.marker_verified_after_held_init_hello);\n        assert!(!record.retirement_proven_before_capture);\n        assert!(record.held_fds_closed);\n        let mut wrong = Capture::new([8; 32]).unwrap();\n        (&*wrong.writer().unwrap()).write_all(&marker(&[9; 32])).unwrap();\n        assert!(wrong.require_marker().is_err());\n        assert!(wrong.finish(false).held_fds_closed);\n    }\n\n    #[test]\n    fn ordinary_file_and_read_write_descriptor_are_not_log_writers() {\n        let capture = Capture::new([10; 32]).unwrap();\n        assert!(validate_writer(capture.reader().unwrap()).is_err());\n        assert!(validate_writer(&File::open(\"/dev/null\").unwrap()).is_err());\n        assert!(capture.finish(false).held_fds_closed);\n    }\n\n    #[test]\n    fn attach_and_worker_start_error_seams_retain_the_owners_only_sink() {\n        for phase in [\"later attach field\", \"worker start\"] {\n            let owner = SharedCapture::new([12; 32]).unwrap();\n            let mut writer = owner.duplicate_writer().unwrap();\n            writer.write_all(&marker(&[12; 32])).unwrap();\n            drop(writer);\n            // Explicit failure seam around the actual shared type: later\n            // field construction or thread creation returns Err and drops\n            // the temporary Session copy. No HostContext/Android is invented.\n            let failed = (|| -> io::Result<()> {\n                let _partial_session = owner.clone();\n                Err(error(phase))\n            })().unwrap_err();\n            assert_eq!(failed.to_string(), phase);\n            let record = owner.finish(false).unwrap();\n            assert_eq!(record.captured_hex, policy::hex(&marker(&[12; 32])));\n            assert!(record.held_fds_closed);\n            assert!(!record.marker_verified_after_held_init_hello);\n            assert!(!record.retirement_proven_before_capture);\n            assert!(owner.finish(false).is_none());\n        }\n    }\n\n    #[test]\n    fn poisoned_capture_keeps_data_and_closes_without_claiming_retirement() {\n        let owner = SharedCapture::new([13; 32]).unwrap();\n        let thread_copy = owner.clone();\n        assert!(std::thread::spawn(move || {\n            let _guard = thread_copy.0.lock().unwrap();\n            panic!(\"owned diagnostic lock poison control\");\n        }).join().is_err());\n        let record = owner.finish(true).unwrap();\n        assert!(!record.retirement_proven_before_capture);\n        assert!(record.held_fds_closed && record.first_error.unwrap().contains(\"poisoned\"));\n        assert!(owner.finish(false).is_none());\n    }\n\n    #[test]\n    fn real_child_exec_does_not_receive_the_cloexec_writer() {\n        let capture = Capture::new([11; 32]).unwrap();\n        let raw = capture.writer().unwrap().as_raw_fd();\n        let mut command = Command::new(\"/bin/sh\");\n        command.args([\"-c\", \"test ! -e /proc/self/fd/202\"]);\n        unsafe {\n            command.pre_exec(move || {\n                if libc::dup3(raw, FD, libc::O_CLOEXEC) < 0 {\n                    return Err(io::Error::last_os_error());\n                }\n                Ok(())\n            });\n        }\n        assert!(command.status().unwrap().success());\n        assert!(capture.finish(false).held_fds_closed);\n    }\n}\n"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/mod.rs": {
      "bytes": 357,
      "sha256": "2807edf9538722a11909c2702770f24624343429e18fe53db70db82f6dfad1be",
      "text": "//! Opt-in real cell relay lifecycle; integration in progress.\npub mod policy;\nmod domain;\nmod capability;\nmod init_peer;\nmod init_log;\npub mod entry;\npub(crate) mod owner;\nmod worker;\nmod audit;\npub use policy::{PressureRelaySpec, RelayArtifact};\npub use audit::RelayLifecycleAudit;\n#[cfg(test)]\npub(crate) use audit::test_snapshot as audit_test_snapshot;\n"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/owner.rs": {
      "bytes": 41593,
      "sha256": "5e00ba0a96de8c972663f6293e214f670b44699cdb6102c167e2508b2967fb32",
      "text": "//! One retained supervisor owner for claim, finite domain, real init and broker.\nuse super::capability::{Artifact, Process};\nuse super::audit::{Audit, Event, FailureOrigin, RelayLifecycleAudit, RetirementRecord};\nuse super::domain::{self, Domain, Identity};\nuse super::entry;\nuse super::init_log;\nuse super::init_peer::{self, Hello, InitPeer};\nuse super::policy::{self, PressureRelaySpec};\nuse super::worker::Worker;\nuse crate::CellSpec;\nuse crate::generation_claim::{Claim, Store};\nuse droidloom_pressure_relay::{\n    BootstrapSpec, BootstrapState, BootstrapStatus, ExecutablePin, HostContext, LifecycleBroker,\n    MAX_LIFECYCLE_IO_TIMEOUT,\n};\nuse std::ffi::CString;\nuse std::fs::File;\nuse std::io::{self, Read};\nuse std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd};\nuse std::os::unix::fs::{FileExt, FileTypeExt, MetadataExt};\nuse std::os::unix::process::CommandExt;\nuse std::path::{Path, PathBuf};\nuse std::process::{Child, Command, ExitStatus, Stdio};\nuse std::sync::{\n    Arc,\n    atomic::{AtomicU8, Ordering},\n};\nuse std::time::{Duration, Instant};\n\nconst ENDPOINT_CLAIM: &str = \"droidloom-lmkd-psi.claim\";\nconst WAITING: u8 = 1;\nconst COMMITTED: u8 = 2;\nconst ACTIVE: u8 = 3;\nconst RETIRING: u8 = 4;\nconst RETIRED: u8 = 5;\nconst FAILED: u8 = 6;\nfn error(message: &'static str) -> io::Error {\n    domain::error(message)\n}\nfn relay<T>(result: droidloom_pressure_relay::Result<T>) -> io::Result<T> {\n    result.map_err(io::Error::other)\n}\n\nstruct Cancel(File);\nimpl Cancel {\n    fn new() -> io::Result<Self> {\n        let fd = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) };\n        if fd < 0 {\n            Err(io::Error::last_os_error())\n        } else {\n            Ok(Self(unsafe { File::from_raw_fd(fd) }))\n        }\n    }\n    fn request(&self) -> io::Result<()> {\n        let value = 1u64.to_ne_bytes();\n        loop {\n            let count =\n                unsafe { libc::write(self.0.as_raw_fd(), value.as_ptr().cast(), value.len()) };\n            if count == value.len() as isize {\n                return Ok(());\n            }\n            let e = io::Error::last_os_error();\n            if e.kind() == io::ErrorKind::Interrupted {\n                continue;\n            }\n            if e.kind() == io::ErrorKind::WouldBlock {\n                return Ok(());\n            }\n            return Err(e);\n        }\n    }\n    fn requested(&self) -> io::Result<bool> {\n        let mut poll = libc::pollfd {\n            fd: self.0.as_raw_fd(),\n            events: libc::POLLIN,\n            revents: 0,\n        };\n        let result = unsafe { libc::poll(&mut poll, 1, 0) };\n        if result < 0 {\n            return Err(io::Error::last_os_error());\n        }\n        if poll.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0 {\n            return Err(error(\"lifecycle cancellation FD fault\"));\n        }\n        Ok(poll.revents & libc::POLLIN != 0)\n    }\n}\n\nstruct Endpoint {\n    parent: File,\n    directory: File,\n    name: CString,\n    identity: Identity,\n    removed: bool,\n    poisoned: bool,\n}\nstruct EndpointProof {\n    socket: File,\n    marker: File,\n    marker_bytes: [u8; 104],\n}\nimpl Endpoint {\n    fn create(runtime: &Path, nonce: &[u8; 32]) -> io::Result<Self> {\n        let parent = domain::directory(runtime)?;\n        let m = parent.metadata()?;\n        if m.uid() != 0 || m.gid() != 0 || m.mode() & 0o077 != 0 {\n            return Err(error(\"relay runtime directory is not private root-owned\"));\n        }\n        let name =\n            CString::new(format!(\"lmkd-relay-{}\", policy::hex(nonce))).expect(\"hex component\");\n        if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {\n            return Err(io::Error::last_os_error());\n        }\n        let directory = domain::at(\n            parent.as_raw_fd(),\n            &name,\n            libc::O_RDONLY | libc::O_DIRECTORY,\n            0,\n        )?;\n        let identity = Identity::of(&directory)?;\n        Ok(Self {\n            parent,\n            directory,\n            name,\n            identity,\n            removed: false,\n            poisoned: false,\n        })\n    }\n    fn validate(&self) -> io::Result<()> {\n        if self.removed || self.poisoned {\n            return Err(error(\"endpoint directory retired or poisoned\"));\n        }\n        let named = domain::at(\n            self.parent.as_raw_fd(),\n            &self.name,\n            libc::O_RDONLY | libc::O_DIRECTORY,\n            0,\n        )?;\n        let m = named.metadata()?;\n        if Identity::of(&named)? != self.identity\n            || Identity::of(&self.directory)? != self.identity\n            || m.uid() != 0\n            || m.gid() != 0\n            || m.mode() & 0o077 != 0\n        {\n            return Err(error(\"endpoint directory identity or ownership changed\"));\n        }\n        Ok(())\n    }\n    fn remove_after(\n        &mut self,\n        proof: &EndpointProof,\n        processes_retired: impl FnOnce() -> io::Result<()>,\n    ) -> io::Result<()> {\n        if self.poisoned {\n            return Err(error(\"endpoint cleanup is poisoned\"));\n        }\n        if self.removed {\n            return Ok(());\n        }\n        let result = (|| {\n            processes_retired()?;\n            self.validate()?;\n            for item in std::fs::read_dir(format!(\"/proc/self/fd/{}\", self.directory.as_raw_fd()))?\n            {\n                let name = item?.file_name();\n                if name != init_peer::ENDPOINT && name != ENDPOINT_CLAIM {\n                    return Err(error(\"unexpected entry in owned relay endpoint directory\"));\n                }\n            }\n            match domain::named(&self.directory, init_peer::ENDPOINT, libc::O_PATH) {\n                Ok(named) => {\n                    if Identity::of(&named)? != Identity::of(&proof.socket)?\n                        || !named.metadata()?.file_type().is_socket()\n                    {\n                        return Err(error(\"relay endpoint replaced before exact cleanup\"));\n                    }\n                    if unsafe {\n                        libc::unlinkat(\n                            self.directory.as_raw_fd(),\n                            c\"droidloom-lmkd-psi\".as_ptr(),\n                            0,\n                        )\n                    } != 0\n                    {\n                        return Err(io::Error::last_os_error());\n                    }\n                }\n                // The joined broker normally removes its own listener.\n                Err(e) if e.kind() == io::ErrorKind::NotFound => {}\n                Err(e) => return Err(e),\n            }\n            let marker = domain::named(&self.directory, ENDPOINT_CLAIM, libc::O_RDONLY)?;\n            validate_marker(&marker, &proof.marker_bytes)?;\n            if Identity::of(&marker)? != Identity::of(&proof.marker)? {\n                return Err(error(\"relay endpoint claim replaced\"));\n            }\n            if unsafe {\n                libc::unlinkat(\n                    self.directory.as_raw_fd(),\n                    c\"droidloom-lmkd-psi.claim\".as_ptr(),\n                    0,\n                )\n            } != 0\n            {\n                return Err(io::Error::last_os_error());\n            }\n            self.validate()?;\n            if unsafe {\n                libc::unlinkat(\n                    self.parent.as_raw_fd(),\n                    self.name.as_ptr(),\n                    libc::AT_REMOVEDIR,\n                )\n            } != 0\n            {\n                return Err(io::Error::last_os_error());\n            }\n            Ok(())\n        })();\n        if result.is_ok() {\n            self.removed = true;\n        } else {\n            self.poisoned = true;\n        }\n        result\n    }\n    fn prove_removed(&self) -> io::Result<()> {\n        if !self.removed || self.poisoned {\n            return Err(error(\"endpoint has no completed removal proof\"));\n        }\n        match domain::at(self.parent.as_raw_fd(), &self.name, libc::O_PATH, 0) {\n            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),\n            _ => Err(error(\"retired endpoint name reappeared\")),\n        }\n    }\n}\nfn validate_marker(marker: &File, expected: &[u8; 104]) -> io::Result<()> {\n    let m = marker.metadata()?;\n    if !m.is_file()\n        || m.uid() != 0\n        || m.gid() != 0\n        || m.mode() & 0o7777 != 0o600\n        || m.nlink() != 1\n        || m.size() != 104\n    {\n        return Err(error(\"broker one-shot marker type/owner/length differs\"));\n    }\n    validate_marker_bytes(marker, expected)\n}\nfn validate_marker_bytes(marker: &File, expected: &[u8; 104]) -> io::Result<()> {\n    if marker.metadata()?.size() != expected.len() as u64 {\n        return Err(error(\"broker marker length differs\"));\n    }\n    let mut actual = [0; 104];\n    let mut filled = 0;\n    while filled != actual.len() {\n        let count = marker.read_at(&mut actual[filled..], filled as u64)?;\n        if count == 0 {\n            return Err(error(\"broker one-shot marker truncated\"));\n        }\n        filled += count;\n    }\n    if &actual != expected {\n        return Err(error(\n            \"broker one-shot marker differs from owned generation\",\n        ));\n    }\n    Ok(())\n}\nfn endpoint_proof(\n    directory: &File,\n    nonce: &[u8; 32],\n    ready: &BootstrapStatus,\n    owner: &Process,\n    init: &Process,\n) -> io::Result<EndpointProof> {\n    let socket = domain::named(directory, init_peer::ENDPOINT, libc::O_PATH)?;\n    if Identity::of(&socket)?\n        != (Identity {\n            device: ready.endpoint.device,\n            inode: ready.endpoint.inode,\n        })\n    {\n        return Err(error(\"actual listener inode differs from broker READY\"));\n    }\n    let mut bytes = [0; 104];\n    bytes[..8].copy_from_slice(b\"P4SLOT1!\");\n    bytes[8..40].copy_from_slice(nonce);\n    bytes[40..72].copy_from_slice(&ready.generation);\n    for (at, value) in [\n        (72, ready.cgroup.device),\n        (80, ready.cgroup.inode),\n        (88, owner.start()),\n        (96, init.start()),\n    ] {\n        bytes[at..at + 8].copy_from_slice(&value.to_le_bytes());\n    }\n    let marker = domain::named(directory, ENDPOINT_CLAIM, libc::O_RDONLY)?;\n    validate_marker(&marker, &bytes)?;\n    Ok(EndpointProof {\n        socket,\n        marker,\n        marker_bytes: bytes,\n    })\n}\n\nstruct Session {\n    audit: Audit,\n    init_log: init_log::SharedCapture,\n    host: Option<HostContext>,\n    owner: Process,\n    domain: Option<Arc<Domain>>,\n    peer: InitPeer,\n    policy: PressureRelaySpec,\n    nonce: [u8; 32],\n    directory: File,\n    barrier: Artifact,\n    lmkd: Artifact,\n    broker_image: Artifact,\n    cancel: Arc<Cancel>,\n    phase: Arc<AtomicU8>,\n    hello: Option<Hello>,\n    broker: Option<LifecycleBroker>,\n    initialize_started: bool,\n    endpoint: Option<EndpointProof>,\n    retired_init: Option<Process>,\n    reason: Option<String>,\n    retirement_error: Option<String>,\n}\nimpl Session {\n    fn run(&mut self) {\n        let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| self.run_inner()));\n        if let Err(payload) = outcome {\n            self.audit.failure(FailureOrigin::Panic, \"lifecycle worker panicked; generation remains persistently closed\");\n            self.phase.store(FAILED, Ordering::Release);\n            self.retirement_error =\n                Some(\"lifecycle worker panicked; generation remains persistently closed\".into());\n            self.peer.close();\n            if let Some(broker) = &mut self.broker {\n                let _ = relay(broker.revoke_unproven_control());\n            }\n            let _ = self.stop_exact_processes();\n            if let Some(log) = self.init_log.finish(false) {\n                self.audit.init_log(log);\n            }\n            // Worker::join records permanent poison and keeps this exact\n            // Session in its poisoned mutex. No handle is substituted.\n            std::panic::resume_unwind(payload);\n        }\n    }\n    fn run_inner(&mut self) {\n        let outcome = self.run_generation();\n        if let Err(e) = outcome {\n            self.audit.failure(FailureOrigin::Runtime, &e.to_string());\n            self.reason = Some(e.to_string());\n        }\n        self.phase.store(RETIRING, Ordering::Release);\n        self.audit.record(Ok(Event::Retiring));\n        self.peer.close();\n        let retired = self.retire_generation();\n        if let Some(log) = self.init_log.finish(retired.is_ok()) {\n            self.audit.init_log(log);\n        }\n        if let Err(e) = retired {\n            self.audit.failure(FailureOrigin::Retirement, &e.to_string());\n            self.retirement_error = Some(e.to_string());\n            self.phase.store(FAILED, Ordering::Release);\n        } else {\n            self.phase.store(RETIRED, Ordering::Release);\n            self.audit.record(Ok(Event::Retired));\n        }\n    }\n    fn run_generation(&mut self) -> io::Result<()> {\n        let domain = Arc::clone(\n            self.domain\n                .as_ref()\n                .ok_or_else(|| error(\"worker domain missing\"))?,\n        );\n        self.hello = Some(self.peer.accept(\n            &self.owner,\n            &domain,\n            &self.policy,\n            &self.barrier,\n            &self.cancel.0,\n            &self.audit,\n        )?);\n        let hello = self.hello.as_ref().expect(\"retained actual init HELLO\");\n        self.init_log.require_marker()?;\n        let spec = BootstrapSpec {\n            nonce: self.nonce,\n            uid: self.policy.lmkd_uid,\n            gid: self.policy.lmkd_gid,\n            lmkd_sha256: self.lmkd.digest(),\n            init_sha256: hello.executable.digest(),\n        };\n        let handles: [BorrowedFd<'_>; 16] = std::array::from_fn(|index| match index {\n            0 => domain.android().as_fd(),\n            1 => self.owner.fd().as_fd(),\n            2 => hello.process.fd().as_fd(),\n            3 => self.lmkd.file().as_fd(),\n            4 => hello.executable.file().as_fd(),\n            5 => self.directory.as_fd(),\n            i => hello.namespaces[i - 6].as_fd(),\n        });\n        let executable = relay(ExecutablePin::from_lifecycle(\n            self.broker_image.file().try_clone()?,\n            self.broker_image.digest(),\n        ))?;\n        let host = self\n            .host\n            .take()\n            .ok_or_else(|| error(\"host origin token already consumed\"))?;\n        // spawn returns actual Child ownership before any protocol I/O.\n        self.broker = Some(relay(LifecycleBroker::spawn_holding_in_context(\n            host, executable, spec, &handles,\n        ))?);\n        self.initialize_started = true;\n        let broker = self.broker.as_mut().expect(\"retained real broker\");\n        let ready = relay(broker.initialize())?.clone();\n        self.audit.record(relay(broker.process_observation()).map(|process| Event::BrokerReady {\n            process: process.into(), status: (&ready).into(),\n        }));\n        self.endpoint = Some(endpoint_proof(\n            &self.directory,\n            &self.nonce,\n            &ready,\n            &self.owner,\n            &hello.process,\n        )?);\n        self.peer.commit(\n            hello,\n            &self.owner,\n            &domain,\n            &self.policy,\n            &self.barrier,\n            &ready,\n            &self.endpoint.as_ref().expect(\"held endpoint proof\").socket,\n            &self.cancel.0,\n            &mut || relay(broker.ready_for_init_commit()),\n            &self.audit,\n        )?;\n        self.phase.store(COMMITTED, Ordering::Release);\n        // Enrollment has a finite window separate from the constructor's\n        // handshake. Values come from the explicit cell entry policy.\n        let enrollment_deadline =\n            Instant::now() + Duration::from_millis(self.policy.entry_timeout_ms as u64);\n        let mut enrolled = false;\n        loop {\n            if self.cancel.requested()? {\n                return Ok(());\n            }\n            self.owner.live()?;\n            hello.process.live()?;\n            domain.validate()?;\n            if relay(broker.progress_available())? {\n                let status = relay(broker.receive_progress(Duration::from_secs(1)))?;\n                match status.state {\n                    BootstrapState::Active if status.granted && !status.faulted => {\n                        enrolled = true;\n                        self.phase.store(ACTIVE, Ordering::Release);\n                        self.audit.record(Ok(Event::BrokerActive { status: status.into() }));\n                    }\n                    BootstrapState::Retired => {\n                        return Err(error(\n                            \"real broker retired; complete old cell recovery is required\",\n                        ));\n                    }\n                    _ => return Err(error(\"unexpected broker progress after init release\")),\n                }\n            }\n            if !enrolled && Instant::now() >= enrollment_deadline {\n                return Err(error(\n                    \"native LMKD did not enroll before its finite startup deadline\",\n                ));\n            }\n            std::thread::sleep(Duration::from_millis(50));\n        }\n    }\n    fn retire_generation(&mut self) -> io::Result<()> {\n        // Preserve the first retirement failure, while still terminating the\n        // exact owned processes. No missing receipt is replaced by exit alone.\n        let mut failure = None;\n        if let Some(broker) = self.broker.as_mut() {\n            let result = if self.initialize_started {\n                match relay(broker.retire(MAX_LIFECYCLE_IO_TIMEOUT)) {\n                    Ok(true) => Ok(()),\n                    Ok(false) => Err(error(\"broker retirement remains incomplete\")),\n                    Err(e) => Err(e),\n                }\n            } else {\n                relay(broker.abort_before_initialize())\n            };\n            if let Err(e) = result {\n                failure = Some(e);\n                // Revokes the owned transport but explicitly supplies no\n                // retirement receipt. The broker handle remains in Session.\n                let _ = relay(broker.revoke_unproven_control());\n            } else if self.initialize_started {\n                self.audit.record(RetirementRecord::capture(broker).map(|receipt| Event::BrokerRetired { receipt }));\n            }\n        }\n        if let Err(e) = self.stop_exact_processes() {\n            if failure.is_none() {\n                failure = Some(e);\n            }\n        }\n        if let Some(e) = failure {\n            return Err(e);\n        }\n        if self.hello.is_none() {\n            return Err(error(\n                \"no authenticated actual init peer; generation remains persistently closed\",\n            ));\n        }\n        self.audit.record(Ok(Event::ProcessesDead));\n        if self\n            .broker\n            .as_ref()\n            .is_some_and(|b| !b.retirement_complete())\n            || self.endpoint.is_none()\n        {\n            return Err(error(\n                \"generation lacks a complete broker/endpoint retirement chain\",\n            ));\n        }\n        self.domain\n            .as_ref()\n            .ok_or_else(|| error(\"retirement domain missing\"))?\n            .prove_empty()?;\n        self.audit.record(Ok(Event::DomainEmpty));\n        // Release all init root/mount/namespace file references after its\n        // exact death. Keep the pidfd as final immutable retirement evidence.\n        let Hello { process, .. } = self.hello.take().expect(\"checked actual init\");\n        self.retired_init = Some(process);\n        self.domain = None;\n        Ok(())\n    }\n    fn stop_exact_processes(&self) -> io::Result<()> {\n        self.owner.signal(libc::SIGTERM)?;\n        let deadline = Instant::now() + Duration::from_secs(2);\n        loop {\n            let init_dead = match self.hello.as_ref() {\n                Some(h) => h.process.dead()?,\n                None => true,\n            };\n            if self.owner.dead()? && init_dead {\n                return Ok(());\n            }\n            if Instant::now() >= deadline {\n                break;\n            }\n            std::thread::sleep(Duration::from_millis(10));\n        }\n        if let Some(hello) = self.hello.as_ref() {\n            hello.process.signal(libc::SIGKILL)?;\n        }\n        self.owner.signal(libc::SIGKILL)?;\n        if let Some(hello) = self.hello.as_ref() {\n            hello.process.require_dead(Duration::from_secs(2))?;\n        }\n        self.owner.require_dead(Duration::from_secs(2))\n    }\n    fn prove_retired(&self) -> io::Result<()> {\n        if let Some(retirement) = &self.retirement_error {\n            let first = self\n                .reason\n                .as_deref()\n                .unwrap_or(\"lifecycle retirement requested\");\n            return Err(io::Error::other(format!(\n                \"{first}; retirement remains incomplete: {retirement}\"\n            )));\n        }\n        if self.phase.load(Ordering::Acquire) != RETIRED\n            || self.domain.is_some()\n            || self.hello.is_some()\n            || self\n                .broker\n                .as_ref()\n                .is_none_or(|b| !b.retirement_complete())\n        {\n            return Err(error(\"worker has no complete generation retirement proof\"));\n        }\n        self.owner.require_dead(Duration::ZERO)?;\n        self.retired_init\n            .as_ref()\n            .ok_or_else(|| error(\"retired init pidfd missing\"))?\n            .require_dead(Duration::ZERO)\n    }\n}\n\npub(crate) struct Owner {\n    audit: Audit,\n    init_log: init_log::SharedCapture,\n    policy: PressureRelaySpec,\n    nonce: [u8; 32],\n    canonical_spec: [u8; 32],\n    runtime: PathBuf,\n    claim: Claim,\n    domain: Arc<Domain>,\n    endpoint: Option<Endpoint>,\n    host: Option<HostContext>,\n    entry_image: Artifact,\n    broker_image: Option<Artifact>,\n    barrier_image: Option<Artifact>,\n    lmkd_image: Option<Artifact>,\n    channel_host: Option<File>,\n    channel_child: Option<File>,\n    transfers: Option<[File; 4]>,\n    cancel: Arc<Cancel>,\n    phase: Arc<AtomicU8>,\n    process: Option<Process>,\n    worker: Option<Worker<Session>>,\n    failure: Option<String>,\n    termination_reason: Option<String>,\n    explicit_stop_requested: bool,\n    resources_removed: bool,\n    released: bool,\n}\nimpl Owner {\n    /// All read-only image/ABI checks precede the durable claim. The claim\n    /// precedes the first finite-domain/runtime/network resource mutation.\n    pub(crate) fn prepare(spec: &CellSpec, entry_path: &Path) -> io::Result<Option<Self>> {\n        let Some(policy) = spec.pressure_relay.as_ref() else {\n            return Ok(None);\n        };\n        if entry_path != policy.entry_supervisor.path {\n            return Err(error(\n                \"configured entry path differs from the explicit relay package\",\n            ));\n        }\n        let entry_image = Artifact::open(&policy.entry_supervisor, true)?;\n        query_entry_abi(&entry_image)?;\n        let broker_image = Artifact::open(&policy.broker, true)?;\n        let barrier_image = Artifact::open(&policy.init_barrier, false)?;\n        let lmkd_image = Artifact::open(&policy.lmkd, true)?;\n        let host = relay(HostContext::open())?;\n        let nonce = PressureRelaySpec::nonce()?;\n        let canonical_spec = entry::spec_digest(spec)?;\n        let audit = Audit::new(&nonce, &canonical_spec, spec.host_uid, policy);\n        let init_log = init_log::SharedCapture::new(nonce)?;\n        let record = serde_json::to_vec(&serde_json::json!({\"schema\":1,\"entry_abi\":entry::ABI,\n            \"host_uid\":spec.host_uid,\"nonce\":policy::hex(&nonce),\"canonical_spec_sha256\":policy::hex(&canonical_spec),\n            \"runtime\":spec.runtime_dir,\"domain_name\":format!(\"g-{}\",policy::hex(&nonce)),\"pressure_relay\":policy}))\n            .map_err(io::Error::other)?;\n        let store =\n            Store::production(true)?.ok_or_else(|| error(\"generation store unavailable\"))?;\n        let claim = store.claim(spec.host_uid, &record)?;\n        let domain = Arc::new(Domain::create(policy, &nonce)?);\n        audit.record(Ok(Event::Prepared { domain: domain.identity().into() }));\n        let (channel_host, channel_child) = init_peer::pair()?;\n        Ok(Some(Self {\n            audit,\n            init_log,\n            policy: policy.clone(),\n            nonce,\n            canonical_spec,\n            runtime: spec.runtime_dir.clone(),\n            claim,\n            domain,\n            endpoint: None,\n            host: Some(host),\n            entry_image,\n            broker_image: Some(broker_image),\n            barrier_image: Some(barrier_image),\n            lmkd_image: Some(lmkd_image),\n            channel_host: Some(channel_host),\n            channel_child: Some(channel_child),\n            transfers: None,\n            cancel: Arc::new(Cancel::new()?),\n            phase: Arc::new(AtomicU8::new(WAITING)),\n            process: None,\n            worker: None,\n            failure: None,\n            termination_reason: None,\n            explicit_stop_requested: false,\n            resources_removed: false,\n            released: false,\n        }))\n    }\n    pub(crate) fn prepare_endpoint(&mut self) -> io::Result<()> {\n        if self.endpoint.is_some() {\n            return Err(error(\"generation endpoint is one attempt\"));\n        }\n        self.endpoint = Some(Endpoint::create(&self.runtime, &self.nonce)?);\n        Ok(())\n    }\n    /// The returned path resolves only inside the spawned child's FD table.\n    pub(crate) fn entry_path(&self) -> PathBuf {\n        PathBuf::from(format!(\"/proc/self/fd/{}\", init_peer::ENTRY_FD))\n    }\n    pub(crate) fn configure_command(&mut self, command: &mut Command) -> io::Result<()> {\n        if self.transfers.is_some() || self.process.is_some() {\n            return Err(error(\"generation spawn is one attempt\"));\n        }\n        self.domain.validate()?;\n        self.entry_image.validate(true)?;\n        self.endpoint\n            .as_ref()\n            .ok_or_else(|| error(\"private endpoint not provisioned\"))?\n            .validate()?;\n        let log_writer = self.init_log.duplicate_writer()?;\n        let sources = [\n            self.channel_child\n                .as_ref()\n                .ok_or_else(|| error(\"child init channel missing\"))?\n                .as_raw_fd(),\n            self.domain.android().as_raw_fd(),\n            self.entry_image.file().as_raw_fd(),\n            log_writer.as_raw_fd(),\n        ];\n        let pinned = sources.map(|fd| {\n            let raw = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 256) };\n            if raw < 0 {\n                Err(io::Error::last_os_error())\n            } else {\n                Ok(unsafe { File::from_raw_fd(raw) })\n            }\n        });\n        let [a, b, c, d] = pinned;\n        self.transfers = Some([a?, b?, c?, d?]);\n        let raw = self\n            .transfers\n            .as_ref()\n            .expect(\"retained transfers\")\n            .each_ref()\n            .map(AsRawFd::as_raw_fd);\n        let parent = unsafe { libc::getpid() };\n        entry::clean_command_environment(command);\n        command\n            .env_remove(init_log::LOGGER_ENV)\n            .env(init_log::ENTRY_ENV, init_log::ABI)\n            .env(entry::ENTRY_ENV[0], entry::ABI)\n            .env(entry::ENTRY_ENV[1], policy::hex(&self.nonce))\n            .env(entry::ENTRY_ENV[2], policy::hex(&self.canonical_spec));\n        unsafe {\n            command.pre_exec(move || {\n                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0\n                    || libc::getppid() != parent\n                {\n                    return Err(io::Error::other(\n                        \"relay daemon disappeared before namespace owner exec\",\n                    ));\n                }\n                for (source, target) in raw.into_iter().zip([\n                    init_peer::CONTROL_FD,\n                    init_peer::DOMAIN_FD,\n                    init_peer::ENTRY_FD,\n                    init_log::FD,\n                ]) {\n                    if libc::dup2(source, target) < 0 || libc::fcntl(target, libc::F_SETFD, 0) < 0 {\n                        return Err(io::Error::last_os_error());\n                    }\n                }\n                // This is the exact still-unshared outer Child, not a PID supplied\n                // by a request. Its inherited pidfd closes the PID1 pre-arm race.\n                let owned = libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) as i32;\n                if owned < 0 {\n                    return Err(io::Error::last_os_error());\n                }\n                let result = if owned == init_peer::OWNER_FD {\n                    0\n                } else {\n                    libc::dup2(owned, init_peer::OWNER_FD)\n                };\n                if owned != init_peer::OWNER_FD {\n                    libc::close(owned);\n                }\n                if result < 0 || libc::fcntl(init_peer::OWNER_FD, libc::F_SETFD, 0) < 0 {\n                    return Err(io::Error::last_os_error());\n                }\n                Ok(())\n            });\n        }\n        Ok(())\n    }\n    /// Called only after DevelopmentCell already owns Child/network/self.\n    /// Every failure is stored in that Cell; no post-spawn error drops it.\n    pub(crate) fn attach(&mut self, child: &mut Child) {\n        self.transfers = None;\n        self.channel_child = None;\n        let result = self.attach_inner(child);\n        if let Err(error) = result {\n            self.audit.failure(FailureOrigin::Admission, &error.to_string());\n            self.failure = Some(error.to_string());\n            self.phase.store(FAILED, Ordering::Release);\n            self.channel_host = None;\n            let _ = self.cancel.request();\n        }\n    }\n    fn attach_inner(&mut self, child: &mut Child) -> io::Result<()> {\n        if self.worker.is_some() || self.process.is_some() {\n            return Err(error(\"generation child attached twice\"));\n        }\n        self.process = Some(Process::from_child(child)?);\n        self.audit.record(self.process.as_ref().expect(\"retained exact owner\").observation()\n            .map(|process| Event::OwnerAttached { process }));\n        let process = self\n            .process\n            .as_ref()\n            .expect(\"retained exact owner\")\n            .try_clone()?;\n        let session = Session {\n            audit: self.audit.clone(),\n            init_log: self.init_log.clone(),\n            host: self.host.take(),\n            owner: process,\n            domain: Some(Arc::clone(&self.domain)),\n            peer: InitPeer::new(\n                self.channel_host\n                    .take()\n                    .ok_or_else(|| error(\"host init channel missing\"))?,\n                self.nonce,\n                &self.policy,\n            )?,\n            policy: self.policy.clone(),\n            nonce: self.nonce,\n            directory: self\n                .endpoint\n                .as_ref()\n                .ok_or_else(|| error(\"endpoint missing at attach\"))?\n                .directory\n                .try_clone()?,\n            barrier: self\n                .barrier_image\n                .take()\n                .ok_or_else(|| error(\"barrier image already consumed\"))?,\n            lmkd: self\n                .lmkd_image\n                .take()\n                .ok_or_else(|| error(\"LMKD image already consumed\"))?,\n            broker_image: self\n                .broker_image\n                .take()\n                .ok_or_else(|| error(\"broker image already consumed\"))?,\n            cancel: Arc::clone(&self.cancel),\n            phase: Arc::clone(&self.phase),\n            hello: None,\n            broker: None,\n            initialize_started: false,\n            endpoint: None,\n            retired_init: None,\n            reason: None,\n            retirement_error: None,\n        };\n        self.worker = Some(Worker::new(session));\n        self.worker\n            .as_mut()\n            .expect(\"retained worker\")\n            .start(Session::run)\n    }\n    pub(crate) fn poll(&self) -> io::Result<()> {\n        if let Some(reason) = &self.failure {\n            return Err(io::Error::other(format!(\n                \"relay generation admission failed: {reason}\"\n            )));\n        }\n        if self.phase.load(Ordering::Acquire) == FAILED {\n            return Err(error(\n                \"relay worker retained an incomplete generation retirement\",\n            ));\n        }\n        if self.worker.as_ref().is_some_and(Worker::finished)\n            && self.phase.load(Ordering::Acquire) != RETIRED\n        {\n            return Err(error(\n                \"relay worker ended without complete generation retirement\",\n            ));\n        }\n        Ok(())\n    }\n    pub(crate) fn request_stop(&mut self) -> io::Result<()> {\n        self.explicit_stop_requested = true;\n        self.cancel.request()\n    }\n    pub(crate) fn observe_child_exit(&mut self, child: &Child, status: ExitStatus) {\n        let phase = self.phase.load(Ordering::Acquire);\n        self.audit.namespace_owner_exit(child.id(), status, self.explicit_stop_requested,\n            matches!(phase, RETIRING | RETIRED));\n        if self.termination_reason.is_none() {\n            self.termination_reason = self.audit.first_failure_message();\n        }\n        // Attach (including the worker spawn) may have failed before Session\n        // ran. The Owner still retains the same sink, so preserve its prefix\n        // without claiming init/domain retirement or replaying any phase.\n        if self.failure.is_some() {\n            if let Some(log) = self.init_log.finish(false) { self.audit.init_log(log); }\n        }\n    }\n    pub(crate) fn audit(&self) -> RelayLifecycleAudit { self.audit.snapshot() }\n    pub(crate) fn record_cleanup_failure(&self, message: &str) {\n        self.audit.failure(FailureOrigin::Cleanup, message);\n    }\n    pub(crate) fn termination_reason(&self) -> Option<&str> {\n        self.termination_reason.as_deref()\n    }\n    pub(crate) fn enrolled(&self) -> bool {\n        // ACTIVE can only follow the actual init COMMIT/DONE and the exact\n        // broker's authenticated grant-delivery status. It proves no PSI event.\n        self.failure.is_none() && self.phase.load(Ordering::Acquire) == ACTIVE\n    }\n    pub(crate) fn retire_before_network(&mut self, child: &mut Child) -> io::Result<()> {\n        if self.resources_removed {\n            return Ok(());\n        }\n        let status = child.try_wait();\n        if let Ok(Some(status)) = &status { self.observe_child_exit(child, *status); }\n        self.cancel.request()?;\n        if status?.is_none() {\n            return Err(error(\n                \"namespace Child has not been reaped before relay cleanup\",\n            ));\n        }\n        if let Some(reason) = &self.failure {\n            return Err(io::Error::other(format!(\n                \"relay generation is persistently closed: {reason}\"\n            )));\n        }\n        let worker = self\n            .worker\n            .as_mut()\n            .ok_or_else(|| error(\"actual lifecycle worker missing\"))?;\n        // A bounded join timeout retains its real handle and every resource;\n        // it cannot make the next poll or stop return a synthetic success.\n        worker.join(Duration::from_secs(10))?;\n        let resources = worker.resources()?;\n        resources.prove_retired()?;\n        // Snapshot the original run failure while ownership is still held.\n        // Releasing resources successfully must not erase why the cell died.\n        if self.termination_reason.is_none() {\n            self.termination_reason = self.audit.first_failure_message()\n                .or_else(|| resources.reason.clone());\n        }\n        let process = self\n            .process\n            .as_ref()\n            .ok_or_else(|| error(\"owned namespace process pin missing\"))?;\n        if process.pid() as u32 != child.id() {\n            return Err(error(\"cleanup Child differs from retained owner\"));\n        }\n        process.require_dead(Duration::ZERO)?;\n        let domain = Arc::get_mut(&mut self.domain)\n            .ok_or_else(|| error(\"worker still owns a live domain reference\"))?;\n        domain.remove_after(|| resources.prove_retired())?;\n        let endpoint = self\n            .endpoint\n            .as_mut()\n            .ok_or_else(|| error(\"retirement endpoint missing\"))?;\n        endpoint.remove_after(\n            resources\n                .endpoint\n                .as_ref()\n                .ok_or_else(|| error(\"retired endpoint inode proof missing\"))?,\n            || resources.prove_retired(),\n        )?;\n        self.resources_removed = true;\n        self.audit.record(Ok(Event::ResourcesRemoved));\n        Ok(())\n    }\n    /// Only after the exact network owner and entire runtime have cleaned up.\n    /// Marker unlink is the final fallible operation in successful retirement.\n    pub(crate) fn finish_after_runtime(&mut self, child: &mut Child) -> io::Result<()> {\n        if self.released {\n            return Ok(());\n        }\n        if !self.resources_removed || self.failure.is_some() {\n            return Err(error(\"generation resources are not retired\"));\n        }\n        let resources = self\n            .worker\n            .as_ref()\n            .ok_or_else(|| error(\"retired worker missing\"))?\n            .resources()?;\n        let domain = &self.domain;\n        let endpoint = self\n            .endpoint\n            .as_ref()\n            .ok_or_else(|| error(\"retired endpoint missing\"))?;\n        let owner = self\n            .process\n            .as_ref()\n            .ok_or_else(|| error(\"retired owner missing\"))?;\n        let runtime = &self.runtime;\n        self.claim.release_after(|| {\n            resources.prove_retired()?;\n            owner.require_dead(Duration::ZERO)?;\n            if child.id() != owner.pid() as u32 || child.try_wait()?.is_none() {\n                return Err(error(\"exact Child reap proof changed\"));\n            }\n            domain.prove_removed()?;\n            endpoint.prove_removed()?;\n            match std::fs::symlink_metadata(runtime) {\n                Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),\n                _ => Err(error(\"runtime still exists at final generation release\")),\n            }\n        })?;\n        self.released = true;\n        self.audit.record(Ok(Event::ClaimReleased));\n        Ok(())\n    }\n}\nimpl Drop for Owner {\n    fn drop(&mut self) {\n        if !self.released {\n            let _ = self.cancel.request();\n        }\n        if let Some(log) = self.init_log.finish(false) { self.audit.init_log(log); }\n        // The persistent claim deliberately survives dropping this owner.\n    }\n}\n\nfn query_entry_abi(executable: &Artifact) -> io::Result<()> {\n    executable.validate(true)?;\n    let mut command = Command::new(format!(\"/proc/self/fd/{}\", executable.file().as_raw_fd()));\n    command\n        .arg(\"relay-entry-abi\")\n        .stdin(Stdio::null())\n        .stdout(Stdio::piped())\n        .stderr(Stdio::null());\n    entry::clean_command_environment(&mut command);\n    let parent = unsafe { libc::getpid() };\n    unsafe {\n        command.pre_exec(move || {\n            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0 || libc::getppid() != parent {\n                return Err(io::Error::other(\"entry ABI parent disappeared\"));\n            }\n            Ok(())\n        });\n    }\n    let mut child = command.spawn()?;\n    let deadline = Instant::now() + Duration::from_secs(2);\n    let status = loop {\n        match child.try_wait() {\n            Ok(Some(status)) => break Ok(status),\n            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(5)),\n            Ok(None) => break Err(error(\"entry ABI query timed out\")),\n            Err(e) => break Err(e),\n        }\n    };\n    if status.is_err() {\n        let _ = child.kill();\n        let _ = child.wait();\n    }\n    let status = status?;\n    let mut output = child\n        .stdout\n        .take()\n        .ok_or_else(|| error(\"entry ABI output missing\"))?;\n    let flags = unsafe { libc::fcntl(output.as_raw_fd(), libc::F_GETFL) };\n    if flags < 0\n        || unsafe { libc::fcntl(output.as_raw_fd(), libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    let mut bytes = Vec::new();\n    output.by_ref().take(129).read_to_end(&mut bytes)?;\n    if !status.success() || bytes != format!(\"{}\\n\", entry::ABI).as_bytes() {\n        return Err(error(\"paired entry ABI is unavailable or differs\"));\n    }\n    executable.validate(true)\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    #[test]\n    fn cancellation_remains_latched_across_repeated_stop_requests() {\n        let cancel = Cancel::new().unwrap();\n        assert!(!cancel.requested().unwrap());\n        cancel.request().unwrap();\n        cancel.request().unwrap();\n        assert!(cancel.requested().unwrap());\n        assert!(cancel.requested().unwrap());\n        let flags = unsafe { libc::fcntl(cancel.0.as_raw_fd(), libc::F_GETFD) };\n        assert_ne!(flags & libc::FD_CLOEXEC, 0);\n    }\n    #[test]\n    fn altered_broker_marker_cannot_authorize_directory_cleanup() {\n        let mut file = tempfile::tempfile().unwrap();\n        use std::io::Write;\n        file.write_all(&[7; 104]).unwrap();\n        validate_marker_bytes(&file, &[7; 104]).unwrap();\n        assert!(validate_marker_bytes(&file, &[8; 104]).is_err());\n        // Deliberately no source-side UID or mode relaxation: a normal\n        // caller-owned temporary file cannot become production authority.\n        file.set_len(103).unwrap();\n        assert!(validate_marker_bytes(&file, &[7; 104]).is_err());\n    }\n}\n"
    }
  },
  "preimage": {
    "Cargo.lock": {
      "bytes": 51976,
      "sha256": "ee4ea5f370adc8a1861c4b5496c775a06b34fc733cb89eb0d873ab1eb2df0b98"
    },
    "Cargo.toml": {
      "bytes": 2036,
      "sha256": "1bae47451d41445b30933e0cd787ba5833842ea693c9e6231ee1281583323e85"
    },
    "runtime/droidloom-pressure-relay/Cargo.toml": {
      "bytes": 349,
      "sha256": "373050126db407c8ff001dabf59e62b29bea1ebfefa76fbdd578e1d0aabecb34"
    },
    "runtime/droidloom-pressure-relay/src/ancestry.rs": {
      "bytes": 6882,
      "sha256": "3a5fe5ce5fe921ca36b1ae0e8f92e2dff3d240cd29fb1e3e86a2d329cc847fc5"
    },
    "runtime/droidloom-pressure-relay/src/bin/droidloom_psi_owner.rs": {
      "bytes": 753,
      "sha256": "d4e35cc52529d0f5ad779fe57b0fbd49743ee58f2c16b45a8d46cae9e346bc93"
    },
    "runtime/droidloom-pressure-relay/src/bin/owned_ipc_controls.rs": {
      "bytes": 31007,
      "sha256": "83d49c67ee264b4d765f98d4b99155bd8ad8de74ff9d38fd16333ad013066c56"
    },
    "runtime/droidloom-pressure-relay/src/enrollment.rs": {
      "bytes": 19506,
      "sha256": "1321146aaaa4c0ff1865eab54568c1da821abc53d5c094473d936486d3da5363"
    },
    "runtime/droidloom-pressure-relay/src/event_fixture.rs": {
      "bytes": 23424,
      "sha256": "355105cd3d57307f1067893d6a65729731d735b41748f4a86ec028eddd311e54"
    },
    "runtime/droidloom-pressure-relay/src/lib.rs": {
      "bytes": 57311,
      "sha256": "e3d01d609ce7abff8f195209f62a8a622fd622ef09d676f8a72d953331fd5617"
    },
    "runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs": {
      "bytes": 86381,
      "sha256": "08ffa252cf726c1aa54699918ec5152a2ef5cc8c60277b3ab67225556006e0d1"
    },
    "runtime/droidloom-pressure-relay/src/lifecycle_relay.rs": {
      "bytes": 16497,
      "sha256": "143c8ab64ae6411847878718052cf361e1e11e7674803673005882dc0590f8a9"
    },
    "runtime/droidloom-pressure-relay/src/pressure_audit.rs": {
      "bytes": 20193,
      "sha256": "e68d76f8ce24b1994ddd3620fc04f4f25ac35e9e909e41f399b694443403f08c"
    },
    "runtime/droidloom-pressure-relay/src/psi.rs": {
      "bytes": 16179,
      "sha256": "4e8f566ed27250dd2055a03a5a06b6eda9937341400bb0aac9ccf6f08f101ba2"
    },
    "runtime/droidloom-pressure-relay/tests/data/grant.hex": {
      "bytes": 353,
      "sha256": "1d0c6ae3ad3700abbecb91e434e44ec07ce656812a8380495b3873e65fa1ae29"
    },
    "runtime/droidloom-pressure-relay/tests/data/request.hex": {
      "bytes": 289,
      "sha256": "b23769dba25eef8413378196948bb3bd1c2b30165affca8ccc7e341320adfede"
    },
    "runtime/droidloom-supervisor/Cargo.toml": {
      "bytes": 954,
      "sha256": "e2cee314482ae0d1782287e8de54ab238129fc914275c4122b6847c2e31850e9"
    },
    "runtime/droidloom-supervisor/src/control.rs": {
      "bytes": 83587,
      "sha256": "3818e0023f9dbc09a1b98986354147e5adc24f84f92b89e7f0db2f1872a54870"
    },
    "runtime/droidloom-supervisor/src/development.rs": {
      "bytes": 95905,
      "sha256": "b4a73b76934c79d32fe2a95f6a39829b66be33209ad46c872c14d8ef97d260b1"
    },
    "runtime/droidloom-supervisor/src/development_network.rs": {
      "bytes": 27453,
      "sha256": "11a214c3d344cbe9fab82b99a3aab759217db128d781273f5c0573f60d010f1b"
    },
    "runtime/droidloom-supervisor/src/generation_claim.rs": {
      "bytes": 15267,
      "sha256": "2d37a43e58ba05c5ec014775174c4907effe1ac44b2604593a141197ba16ab32"
    },
    "runtime/droidloom-supervisor/src/lib.rs": {
      "bytes": 34441,
      "sha256": "2de510605987aa6f5486bc0edf6d0400bca9c7a8f5768dc37d66c06df5bd440a"
    },
    "runtime/droidloom-supervisor/src/linux_plan.rs": {
      "bytes": 39632,
      "sha256": "e9be621e1cf8d9536b8ade216a67b1f002768e4299ae2aa15e742f006c0f301b"
    },
    "runtime/droidloom-supervisor/src/main.rs": {
      "bytes": 2872,
      "sha256": "9b97063e9d41e21aa5b028d24328ea976186b9ecc6c2d28725653139792444d8"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/audit.rs": {
      "bytes": 31293,
      "sha256": "f3392bc50f99b558597f23d9fb2d5110f23cab65b514b999a637d931a29a91f1"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/capability.rs": {
      "bytes": 24407,
      "sha256": "1c335ebf2c4892fae9cfae2081828e86ff121f0512ed9fbbb375e01d77f13137"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/domain.rs": {
      "bytes": 30475,
      "sha256": "7bfeffd8f71e8e6bb92c5445fb585e828a6eedb77ba57bd0c76b259a99cad5a1"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs": {
      "bytes": 29561,
      "sha256": "43617fab408b379f7fe6c413931be8bbe4db032c94a5ed084d030989dcd700cc"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/init_peer.rs": {
      "bytes": 28235,
      "sha256": "f3fdb0736697e2a6e06328a38178c7db07127ecc23b50e92d40d241f9a311892"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/mod.rs": {
      "bytes": 343,
      "sha256": "f2eb90f9ff902e342f351318a53acc7d8d3255e2cefa93cc7d0b2e8b0fb4353e"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/owner.rs": {
      "bytes": 40406,
      "sha256": "ebc8c5fb93c45e87102ce76ffc1e597649d2dc949d079d07a38531972cb2ff9d"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/policy.rs": {
      "bytes": 10781,
      "sha256": "eac34bb8e3dd1f7cf14bb74753554209e550beb413895871993a7bdfc03681b4"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/worker.rs": {
      "bytes": 6054,
      "sha256": "c63978f9e77ce1e93ee2562dc6c7326b8593785897b0356d3cc341f8f466a562"
    }
  },
  "revision": "producer16-bounded-init-log01",
  "schema": 1,
  "source_manifest_sha256": "c5afbb0a61653f5fa554ef42cd68f77e71a38893b229151d2b685b5e2d032050"
}
'''))
