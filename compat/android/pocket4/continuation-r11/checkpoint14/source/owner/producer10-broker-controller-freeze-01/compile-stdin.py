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

CONTROL_REVISION = "producer10-broker-holding01"
BASE = Path("/home/alex/work/pocket4-supervisor-lmkd-cgroup-r11-build-09-01")
SOURCE = BASE / "candidate"
OUT = Path("/home/alex/work/pocket4-supervisor-lmkd-broker-r11-build-10-01")
CANDIDATE = OUT / "candidate"
TARGET = OUT / "target"
CARGO = "/home/alex/.cargo/bin/cargo"
PRIOR_RECEIPT = BASE / "compile-result.json"
PRIOR_RECEIPT_SHA = "415c12d44b3f2c568c8914126f61c4844b6a1238a565eabc488b8145c64eaae1"
PRIOR_INVENTORY_SHA = "6c1abf6ede0fb5ffd5379c6491a20800705cb59a3da867dabafd71970c0d2e47"
ORIGINAL_DIFF_SHA = "7f6fe8e1a783de07284166b5b89fdb03b4700acb9d6770bc0b994d4dc3490f4b"
EXACT_OVERLAY = {
    'runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs': (65775, '2ed8fb3bd597e9881584ebce997692d9a1c4f1eba564d9603c875e763a039264'),
    'runtime/droidloom-supervisor/src/relay_lifecycle/owner.rs': (39607, '5b011974c71d4a5d96091ea98cd55ffe3f69c0a4abe28eb71c9fea58c8a04994'),
}
NEW_SOURCE_FILES = set()
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
    env = dict(os.environ)
    for key in list(env):
        if key in {"RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS",
                   "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "RUSTDOC",
                   "RUSTC", "CARGO_TARGET_DIR"}:
            env.pop(key, None)
    env.update(CARGO_BUILD_JOBS="1", CARGO_INCREMENTAL="0",
               CARGO_PROFILE_DEV_DEBUG="0", CARGO_PROFILE_TEST_DEBUG="0",
               RUST_TEST_THREADS="1", CARGO_TARGET_DIR=str(target),
               CARGO_HOME="/home/alex/.cargo", RUSTUP_HOME="/home/alex/.rustup")
    return env

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
         "019b34bc655bf76235339b533917d523fd2e5db3355214e5a5466e6a61ee3068",
         "wrong recovered source lineage")
    need(len(cfg["preimage"]) == 32 and
         set(cfg["overlays"]) == set(EXACT_OVERLAY) and
         set(cfg["overlays"]) - set(cfg["preimage"]) == NEW_SOURCE_FILES and
         len(set(cfg["preimage"]) | set(cfg["overlays"])) == 32, "wrong input/overlay set")
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
    try:
        resources.begin()
        put(OUT / "payload.json", json_bytes(cfg))
        report["payload_sha256"] = sha(json_bytes(cfg))
        prior_raw = read_regular(PRIOR_RECEIPT, 128 * 1024)
        need(sha(prior_raw) == PRIOR_RECEIPT_SHA, "actual producer09 cgroup handoff01 receipt hash differs")
        prior = json.loads(prior_raw)
        need(prior["success"] is True and prior["compile_only"] is True and
             prior["revision"] == "producer09-cgroup-handoff01" and
             prior["candidate"] == str(SOURCE) and
             prior["inputs_before"] == cfg["preimage"] and
             prior["inputs_after"] == cfg["preimage"] and
             prior["all_source_inventory_before_sha256"] == PRIOR_INVENTORY_SHA and
             prior["all_source_inventory_after_sha256"] == PRIOR_INVENTORY_SHA,
             "actual producer09 cgroup handoff01 receipt/source binding differs")
        put(OUT / "producer09-cgroup-handoff01-actual-compile-result.json", prior_raw)
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
        report["build_environment_overrides"] = {
            key: env[key] for key in [
                "CARGO_BUILD_JOBS", "CARGO_INCREMENTAL", "CARGO_PROFILE_DEV_DEBUG",
                "CARGO_PROFILE_TEST_DEBUG", "RUST_TEST_THREADS", "CARGO_TARGET_DIR",
                "CARGO_HOME", "RUSTUP_HOME"
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
  "original_diff_sha256": "7f6fe8e1a783de07284166b5b89fdb03b4700acb9d6770bc0b994d4dc3490f4b",
  "overlays": {
    "runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs": {
      "bytes": 65775,
      "sha256": "2ed8fb3bd597e9881584ebce997692d9a1c4f1eba564d9603c875e763a039264",
      "text": "// Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0\n//! Real daemon entry for a trusted supervisor's inherited socketpair.\n//!\n//! This is NOT the Android enrollment socket. Only the exact root parent may\n//! supply the sixteen lifecycle-owned descriptors. No process/path lookup,\n//! threshold override, shell command, or Android-supplied authority is accepted.\nuse super::*;\nuse std::io::Write;\nuse std::os::fd::BorrowedFd;\n\nconst BOOT_SIZE: usize = 128;\nconst STATUS_SIZE: usize = 160;\nconst RETIRE_SIZE: usize = 48;\nconst RIGHTS: usize = 16;\nconst NSFS_MAGIC: libc::c_long = 0x6e73_6673;\nconst NS_GET_NSTYPE: libc::c_ulong = 0xb703;\nconst BAD: libc::c_short = libc::POLLERR | libc::POLLHUP | libc::POLLRDHUP | libc::POLLNVAL;\nconst TMPFS_MAGIC: libc::c_long = 0x0102_1994;\n\n// The layout is chosen only by the trusted lifecycle caller. The legacy\n// owned fixture and the real ABI3 init barrier have different, explicit\n// bootstrap layouts; neither endpoint guesses from a pathname or falls back.\n#[derive(Clone, Copy, Debug, Eq, PartialEq)]\nenum BootstrapLayout { ProjectedRootV1, HoldingLeafV3 }\n\nfn number(bytes: &[u8], at: usize, width: usize) -> u64 {\n    let mut value = [0; 8]; value[..width].copy_from_slice(&bytes[at..at + width]);\n    u64::from_le_bytes(value)\n}\nfn put(bytes: &mut [u8], at: usize, value: u64, width: usize) {\n    bytes[at..at + width].copy_from_slice(&value.to_le_bytes()[..width]);\n}\n\n/// Trusted image policy and a new per-invocation nonce. FD order is fixed:\n/// cgroup root, owner pidfd, init pidfd, LMKD executable, init executable,\n/// private endpoint directory, then pid/pid_for_children/mnt/cgroup/user/net/\n/// ipc/uts/time/time_for_children namespace FDs. The parent must already hold\n/// every descriptor and the corresponding LMKD startup barrier.\n#[derive(Clone, Debug, Eq, PartialEq)]\npub struct BootstrapSpec {\n    pub nonce: [u8; 32],\n    pub uid: u32,\n    pub gid: u32,\n    pub lmkd_sha256: [u8; 32],\n    pub init_sha256: [u8; 32],\n}\nimpl BootstrapSpec {\n    fn validate(&self) -> Result<()> {\n        if self.nonce == [0; 32] || self.lmkd_sha256 == [0; 32] || self.init_sha256 == [0; 32] ||\n            self.uid == 0 || self.uid == u32::MAX || self.gid == 0 || self.gid == u32::MAX {\n            return Err(Error::Reject(\"invalid trusted bootstrap nonce/role/image policy\"));\n        }\n        Ok(())\n    }\n    /// Legacy owned-fixture wire. Real ABI3 init uses the explicitly selected\n    /// holding path below and never retries this version after rejection.\n    pub fn encode(&self) -> Result<[u8; BOOT_SIZE]> {\n        self.encode_with_layout(BootstrapLayout::ProjectedRootV1)\n    }\n    fn encode_with_layout(&self, layout: BootstrapLayout) -> Result<[u8; BOOT_SIZE]> {\n        self.validate()?;\n        let mut wire = [0; BOOT_SIZE]; wire[..8].copy_from_slice(b\"P4BOOT1!\");\n        put(&mut wire, 8, 1, 4); put(&mut wire, 12, self.uid as u64, 4); put(&mut wire, 16, self.gid as u64, 4);\n        if layout == BootstrapLayout::HoldingLeafV3 {\n            wire[..8].copy_from_slice(b\"P4BOOT2!\");\n            put(&mut wire, 8, 2, 4); put(&mut wire, 20, 3, 4);\n        }\n        wire[24..56].copy_from_slice(&self.nonce);\n        wire[56..88].copy_from_slice(&self.lmkd_sha256); wire[88..120].copy_from_slice(&self.init_sha256);\n        Ok(wire)\n    }\n    fn decode(wire: &[u8]) -> Result<Self> {\n        let (spec, layout) = Self::decode_with_layout(wire)?;\n        if layout != BootstrapLayout::ProjectedRootV1 {\n            return Err(Error::Reject(\"owned fixture bootstrap layout differs from root projection\"));\n        }\n        Ok(spec)\n    }\n    fn decode_with_layout(wire: &[u8]) -> Result<(Self, BootstrapLayout)> {\n        if wire.len() != BOOT_SIZE || wire[120..].iter().any(|b| *b != 0) {\n            return Err(Error::Reject(\"bootstrap size/magic/version/reserved field\"));\n        }\n        let layout = if &wire[..8] == b\"P4BOOT1!\" && number(wire, 8, 4) == 1 && number(wire, 20, 4) == 0 {\n            BootstrapLayout::ProjectedRootV1\n        } else if &wire[..8] == b\"P4BOOT2!\" && number(wire, 8, 4) == 2 && number(wire, 20, 4) == 3 {\n            BootstrapLayout::HoldingLeafV3\n        } else {\n            return Err(Error::Reject(\"bootstrap size/magic/version/reserved field\"));\n        };\n        let mut nonce = [0; 32]; nonce.copy_from_slice(&wire[24..56]);\n        let mut lmkd_sha256 = [0; 32]; lmkd_sha256.copy_from_slice(&wire[56..88]);\n        let mut init_sha256 = [0; 32]; init_sha256.copy_from_slice(&wire[88..120]);\n        let spec = Self { nonce, uid: number(wire, 12, 4) as u32, gid: number(wire, 16, 4) as u32,\n            lmkd_sha256, init_sha256 };\n        spec.validate()?; Ok((spec, layout))\n    }\n    /// Legacy owned-fixture datagram, exactly sixteen SCM_RIGHTS. Calling\n    /// again is a protocol fault and retires the broker. This method never\n    /// opens a PID or path and is not the real ABI3 producer's send path.\n    pub fn send(&self, channel: BorrowedFd<'_>, descriptors: &[BorrowedFd<'_>; RIGHTS], timeout: Duration) -> Result<()> {\n        self.send_with_layout(channel, descriptors, timeout, BootstrapLayout::ProjectedRootV1)\n    }\n    fn send_with_layout(&self, channel: BorrowedFd<'_>, descriptors: &[BorrowedFd<'_>; RIGHTS],\n        timeout: Duration, layout: BootstrapLayout) -> Result<()> {\n        let wire = self.encode_with_layout(layout)?;\n        let raw: Vec<RawFd> = descriptors.iter().map(AsRawFd::as_raw_fd).collect();\n        send_packet(channel.as_raw_fd(), &wire, &raw, &mut Deadline::new(timeout)?)\n    }\n    pub fn receive_status(&self, channel: BorrowedFd<'_>, timeout: Duration) -> Result<BootstrapStatus> {\n        let (wire, rights) = receive_packet(channel.as_raw_fd(), STATUS_SIZE, &mut Deadline::new(timeout)?, true)?;\n        if !rights.is_empty() { return Err(Error::Reject(\"bootstrap status carried authority FDs\")); }\n        let status = BootstrapStatus::decode(&wire)?;\n        if status.nonce != self.nonce { return Err(Error::Reject(\"bootstrap status nonce mismatch\")); }\n        Ok(status)\n    }\n    /// Transport helper for a separately held exact lifecycle Child. The\n    /// caller must own that child and the inherited channel; socketpair\n    /// SO_PEERCRED identifies its creator, not a later child. This compares\n    /// against the parent's PREEXISTING spec; the child's packet never defines\n    /// image/nonce policy. The production broker independently verifies lineage.\n    pub fn receive_from_owned_child(&self, channel: BorrowedFd<'_>, timeout: Duration) -> Result<[OwnedFd; RIGHTS]> {\n        let (wire, rights) = receive_packet(channel.as_raw_fd(), BOOT_SIZE, &mut Deadline::new(timeout)?, false)?;\n        if BootstrapSpec::decode(&wire)? != *self { return Err(Error::Reject(\"owned child bootstrap differs from parent pins\")); }\n        rights.try_into().map_err(|_| Error::Reject(\"owned child lifecycle descriptor count\"))\n    }\n    pub fn request_retirement(&self, channel: BorrowedFd<'_>, timeout: Duration) -> Result<()> {\n        let mut wire = [0; RETIRE_SIZE]; wire[..8].copy_from_slice(b\"P4RET01!\");\n        put(&mut wire, 8, 1, 4); wire[16..48].copy_from_slice(&self.nonce);\n        send_packet(channel.as_raw_fd(), &wire, &[], &mut Deadline::new(timeout)?)\n    }\n}\n\n#[derive(Clone, Copy, Debug, Eq, PartialEq)]\n#[repr(u32)]\npub enum BootstrapState { Ready = 1, Active = 2, Retired = 3 }\n/// READY certifies host preparation only. ACTIVE certifies grant delivery, not\n/// a PSI event. RETIRED certifies joined host cleanup, not cell process exit.\n#[derive(Clone, Debug, Eq, PartialEq)]\npub struct BootstrapStatus {\n    pub state: BootstrapState, pub nonce: [u8; 32], pub generation: [u8; 32],\n    pub endpoint: FileId, pub cgroup: FileId, pub budget: [u8; 32],\n    pub granted: bool, pub faulted: bool,\n}\nimpl BootstrapStatus {\n    /// Send an inode-bound projection permit to a held private namespace\n    /// owner's inherited channel. That owner must compare the socket inode,\n    /// project only it, and retain LMKD's barrier until the comparison passes.\n    pub fn permit_projection(&self, channel: BorrowedFd<'_>, timeout: Duration) -> Result<()> {\n        if self.state != BootstrapState::Ready { return Err(Error::Reject(\"projection requires initial READY\")); }\n        let mut wire = [0; 64]; wire[..8].copy_from_slice(b\"P4PROJ1!\"); wire[8..40].copy_from_slice(&self.nonce);\n        put(&mut wire, 40, self.endpoint.device, 8); put(&mut wire, 48, self.endpoint.inode, 8); put(&mut wire, 56, 1, 4);\n        send_packet(channel.as_raw_fd(), &wire, &[], &mut Deadline::new(timeout)?)\n    }\n    fn encode(&self) -> [u8; STATUS_SIZE] {\n        let mut wire = [0; STATUS_SIZE]; wire[..8].copy_from_slice(b\"P4BST01!\");\n        put(&mut wire, 8, 1, 4); put(&mut wire, 12, self.state as u64, 4);\n        wire[16..48].copy_from_slice(&self.nonce); wire[48..80].copy_from_slice(&self.generation);\n        put(&mut wire, 80, self.endpoint.device, 8); put(&mut wire, 88, self.endpoint.inode, 8);\n        put(&mut wire, 96, self.cgroup.device, 8); put(&mut wire, 104, self.cgroup.inode, 8);\n        wire[112..144].copy_from_slice(&self.budget);\n        put(&mut wire, 144, u64::from(self.granted) | (u64::from(self.faulted) << 1), 4);\n        wire\n    }\n    fn decode(wire: &[u8]) -> Result<Self> {\n        if wire.len() != STATUS_SIZE || &wire[..8] != b\"P4BST01!\" || number(wire, 8, 4) != 1 ||\n            wire[148..].iter().any(|b| *b != 0) || number(wire, 144, 4) > 3 {\n            return Err(Error::Reject(\"bootstrap status framing\"));\n        }\n        let state = match number(wire, 12, 4) { 1 => BootstrapState::Ready, 2 => BootstrapState::Active,\n            3 => BootstrapState::Retired, _ => return Err(Error::Reject(\"unknown bootstrap state\")) };\n        let mut nonce = [0; 32]; nonce.copy_from_slice(&wire[16..48]);\n        let mut generation = [0; 32]; generation.copy_from_slice(&wire[48..80]);\n        let mut budget = [0; 32]; budget.copy_from_slice(&wire[112..144]);\n        let endpoint = FileId { device: number(wire, 80, 8), inode: number(wire, 88, 8) };\n        let cgroup = FileId { device: number(wire, 96, 8), inode: number(wire, 104, 8) };\n        if nonce == [0; 32] || generation == [0; 32] || endpoint.device == 0 || endpoint.inode == 0 ||\n            cgroup.device == 0 || cgroup.inode == 0 {\n            return Err(Error::Reject(\"bootstrap status empty identity\"));\n        }\n        let flags = number(wire, 144, 4);\n        if !super::enrollment::valid_budget(&budget) ||\n            (state == BootstrapState::Ready && flags != 0) ||\n            (state == BootstrapState::Active && flags != 1) {\n            return Err(Error::Reject(\"bootstrap status budget/state flags\"));\n        }\n        Ok(Self { state, nonce, generation, endpoint, cgroup, budget, granted: flags & 1 != 0, faulted: flags & 2 != 0 })\n    }\n}\n\n/// Largest supported wait for one lifecycle request/response transaction.\n/// Callers must share this bound; a longer argument is rejected before I/O.\npub const MAX_LIFECYCLE_IO_TIMEOUT: Duration = Duration::from_secs(2);\n\nstruct Deadline(Instant);\nimpl Deadline {\n    fn new(timeout: Duration) -> Result<Self> {\n        if timeout < Duration::from_millis(1) || timeout > MAX_LIFECYCLE_IO_TIMEOUT {\n            return Err(Error::Reject(\"bootstrap I/O bound outside 1..2000 ms\"));\n        }\n        Ok(Self(Instant::now().checked_add(timeout).ok_or(Error::Reject(\"bootstrap deadline overflow\"))?))\n    }\n    fn check(&self) -> Result<()> {\n        if Instant::now() >= self.0 { return Err(Error::Reject(\"bootstrap deadline expired\")); }\n        Ok(())\n    }\n    fn wait(&mut self, fd: RawFd, event: libc::c_short) -> Result<()> {\n        self.wait_packet(fd, event, false)\n    }\n    fn wait_packet(&mut self, fd: RawFd, event: libc::c_short, drain_final: bool) -> Result<()> {\n        loop {\n            self.check()?;\n            let mut p = libc::pollfd { fd, events: event | libc::POLLRDHUP, revents: 0 };\n            let ms = self.0.saturating_duration_since(Instant::now()).as_millis().clamp(1, 100) as libc::c_int;\n            if unsafe { libc::poll(&mut p, 1, ms) } < 0 {\n                if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }\n                return Err(err(\"poll lifecycle bootstrap\"));\n            }\n            let final_packet = drain_final && event == libc::POLLIN && p.revents & libc::POLLIN != 0 &&\n                p.revents & (libc::POLLERR | libc::POLLNVAL) == 0;\n            if p.revents & BAD != 0 && !final_packet { return Err(Error::Reject(\"lifecycle bootstrap disconnected\")); }\n            self.check()?;\n            if p.revents & event != 0 { return Ok(()); }\n        }\n    }\n}\n\nfn send_packet(fd: RawFd, wire: &[u8], rights: &[RawFd], deadline: &mut Deadline) -> Result<()> {\n    if rights.len() > RIGHTS { return Err(Error::Reject(\"too many outgoing lifecycle handles\")); }\n    loop {\n        deadline.wait(fd, libc::POLLOUT)?;\n        let mut iov = libc::iovec { iov_base: wire.as_ptr().cast_mut().cast(), iov_len: wire.len() };\n        let mut control = [0 as libc::c_long; 32];\n        let mut message: libc::msghdr = unsafe { zeroed() };\n        message.msg_iov = &mut iov; message.msg_iovlen = 1;\n        if !rights.is_empty() {\n            message.msg_control = control.as_mut_ptr().cast();\n            message.msg_controllen = unsafe { libc::CMSG_SPACE(std::mem::size_of_val(rights) as u32) } as usize;\n            let header = unsafe { libc::CMSG_FIRSTHDR(&message) };\n            unsafe {\n                (*header).cmsg_level = libc::SOL_SOCKET; (*header).cmsg_type = libc::SCM_RIGHTS;\n                (*header).cmsg_len = libc::CMSG_LEN(std::mem::size_of_val(rights) as u32) as usize;\n                std::ptr::copy_nonoverlapping(rights.as_ptr().cast::<u8>(), libc::CMSG_DATA(header), std::mem::size_of_val(rights));\n            }\n        }\n        let sent = unsafe { libc::sendmsg(fd, &message, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) };\n        if sent < 0 && io::Error::last_os_error().kind() == io::ErrorKind::WouldBlock { continue; }\n        if sent < 0 { return Err(err(\"send lifecycle packet\")); }\n        if sent as usize != wire.len() { return Err(Error::Reject(\"partial lifecycle packet\")); }\n        deadline.check()?; return Ok(());\n    }\n}\nfn receive_packet(fd: RawFd, length: usize, deadline: &mut Deadline, drain_final: bool) -> Result<(Vec<u8>, Vec<OwnedFd>)> {\n    let (wire, rights) = receive_up_to(fd, length, deadline, drain_final)?;\n    if wire.len() != length { return Err(Error::Reject(\"lifecycle packet exact size\")); }\n    Ok((wire, rights))\n}\nfn receive_up_to(fd: RawFd, length: usize, deadline: &mut Deadline, drain_final: bool) -> Result<(Vec<u8>, Vec<OwnedFd>)> {\n    loop {\n        deadline.wait_packet(fd, libc::POLLIN, drain_final)?;\n        let mut wire = vec![0; length];\n        let mut iov = libc::iovec { iov_base: wire.as_mut_ptr().cast(), iov_len: wire.len() };\n        let mut control = [0 as libc::c_long; 64];\n        let mut message: libc::msghdr = unsafe { zeroed() };\n        message.msg_iov = &mut iov; message.msg_iovlen = 1;\n        message.msg_control = control.as_mut_ptr().cast(); message.msg_controllen = std::mem::size_of_val(&control);\n        let got = unsafe { libc::recvmsg(fd, &mut message, libc::MSG_CMSG_CLOEXEC | libc::MSG_DONTWAIT | libc::MSG_TRUNC) };\n        if got < 0 && io::Error::last_os_error().kind() == io::ErrorKind::WouldBlock { continue; }\n        if got < 0 { return Err(err(\"receive lifecycle packet\")); }\n        let mut rights = Vec::new(); let mut malformed = false;\n        let mut header = unsafe { libc::CMSG_FIRSTHDR(&message) };\n        while !header.is_null() {\n            let h = unsafe { &*header };\n            let base = unsafe { libc::CMSG_LEN(0) } as usize;\n            if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS && h.cmsg_len >= base {\n                let payload = h.cmsg_len - base;\n                if payload % size_of::<RawFd>() != 0 { malformed = true; }\n                for i in 0..payload / size_of::<RawFd>() {\n                    let raw = unsafe { std::ptr::read_unaligned(libc::CMSG_DATA(header).add(i * size_of::<RawFd>()).cast::<RawFd>()) };\n                    rights.push(unsafe { OwnedFd::from_raw_fd(raw) });\n                }\n            } else { malformed = true; }\n            header = unsafe { libc::CMSG_NXTHDR(&message, header) };\n        }\n        // Own all delivered FDs before any error. Linux closes undisclosed FDs\n        // on ancillary truncation; RAII closes all visible ones here.\n        if malformed || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0 || got <= 0 || got as usize > length {\n            return Err(Error::Reject(\"lifecycle packet framing/ancillary data\"));\n        }\n        wire.truncate(got as usize);\n        deadline.check()?; return Ok((wire, rights));\n    }\n}\n\nenum ProgressFrame { Audit(PressureAudit), Status(BootstrapStatus) }\nfn receive_progress_frame(fd: RawFd, deadline: &mut Deadline) -> Result<ProgressFrame> {\n    let (wire, rights) = receive_up_to(fd, super::pressure_audit::PRESSURE_AUDIT_SIZE, deadline, true)?;\n    if !rights.is_empty() { return Err(Error::Reject(\"lifecycle progress carried authority FDs\")); }\n    if wire.starts_with(b\"P4AUD01!\") {\n        Ok(ProgressFrame::Audit(PressureAudit::decode(&wire)?))\n    } else {\n        Ok(ProgressFrame::Status(BootstrapStatus::decode(&wire)?))\n    }\n}\n\nfn status_scalar(text: &str, key: &str) -> Result<u64> {\n    let mut lines = text.lines().filter_map(|line| line.strip_prefix(key));\n    let value = lines.next().ok_or(Error::Reject(\"missing lifecycle process scalar\"))?;\n    if lines.next().is_some() { return Err(Error::Reject(\"duplicate lifecycle process scalar\")); }\n    numeric(value.trim())\n}\nfn pidfd_number(host: &HostContext, fd: RawFd) -> Result<libc::pid_t> {\n    // Signal 0 only verifies the kernel descriptor kind/liveness; it sends no\n    // signal. A regular file with forged fdinfo-looking contents cannot pass.\n    if unsafe { libc::syscall(libc::SYS_pidfd_send_signal, fd, 0, std::ptr::null::<libc::siginfo_t>(), 0) } != 0 {\n        return Err(err(\"validate inherited lifecycle pidfd\"));\n    }\n    let value = status_scalar(&read_at(&host.self_proc, &format!(\"fdinfo/{fd}\"), MAX_PROC_BYTES)?, \"Pid:\")?;\n    libc::pid_t::try_from(value).ok().filter(|pid| *pid > 0).ok_or(Error::Reject(\"inherited pidfd has no live host PID\"))\n}\nfn adopt_pidfd(host: &HostContext, fd: OwnedFd) -> Result<ProcessPin> {\n    let pid = pidfd_number(host, fd.as_raw_fd())?;\n    let pin = host.pin(pid, fd)?;\n    let status = read_at(&pin.proc_dir, \"status\", MAX_PROC_BYTES)?;\n    if status_scalar(&status, \"Tgid:\")? != pid as u64 || status_scalar(&status, \"Pid:\")? != pid as u64 ||\n        pidfd_number(host, pin.pidfd.as_raw_fd())? != pid {\n        return Err(Error::Reject(\"inherited lifecycle pidfd is not a stable process leader\"));\n    }\n    pin.live()?; Ok(pin)\n}\nfn trusted_parent(host: &HostContext, channel: RawFd) -> Result<ProcessPin> {\n    if unsafe { libc::geteuid() } != 0 || unsafe { libc::getegid() } != 0 ||\n        socket_integer(channel, libc::SO_TYPE)? != libc::SOCK_SEQPACKET ||\n        socket_integer(channel, libc::SO_DOMAIN)? != libc::AF_UNIX ||\n        socket_integer(channel, libc::SO_ACCEPTCONN)? != 0 {\n        return Err(Error::Reject(\"bootstrap requires root connected Unix seqpacket\"));\n    }\n    let flags = unsafe { libc::fcntl(channel, libc::F_GETFL) };\n    if flags < 0 || flags & libc::O_NONBLOCK == 0 { return Err(Error::Reject(\"bootstrap channel must be nonblocking\")); }\n    if unsafe { libc::fcntl(channel, libc::F_SETFD, libc::FD_CLOEXEC) } < 0 { return Err(err(\"seal inherited channel\")); }\n    let peer = credentials(channel)?;\n    if peer.uid != 0 || peer.gid != 0 || peer.pid != unsafe { libc::getppid() } {\n        return Err(Error::Reject(\"bootstrap peer is not the exact root lifecycle parent\"));\n    }\n    let raw = socket_integer(channel, SO_PEERPIDFD)?;\n    if raw < 0 { return Err(Error::Reject(\"bootstrap parent pidfd unavailable\")); }\n    let parent = adopt_pidfd(host, unsafe { OwnedFd::from_raw_fd(raw) })?;\n    if parent.pid != peer.pid { return Err(Error::Reject(\"bootstrap parent pidfd/credential mismatch\")); }\n    if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } < 0 || unsafe { libc::getppid() } != parent.pid {\n        return Err(Error::Reject(\"bootstrap parent-death contract failed\"));\n    }\n    parent.live()?; Ok(parent)\n}\n\nfn role_namespaces(files: Vec<File>, init: &ProcessPin) -> Result<NamespacePins> {\n    if files.len() != NS_NAMES.len() { return Err(Error::Reject(\"lifecycle namespace handle count\")); }\n    let kinds = [libc::CLONE_NEWPID, libc::CLONE_NEWPID, libc::CLONE_NEWNS, libc::CLONE_NEWCGROUP,\n        libc::CLONE_NEWUSER, libc::CLONE_NEWNET, libc::CLONE_NEWIPC, libc::CLONE_NEWUTS, 0x80, 0x80];\n    let init_pins = init.namespace_pins()?;\n    let mut ids = Vec::with_capacity(NS_NAMES.len());\n    for (index, file) in files.iter().enumerate() {\n        require_fs(file, NSFS_MAGIC)?;\n        if unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE) } != kinds[index] {\n            return Err(Error::Reject(\"lifecycle namespace descriptor type/order\"));\n        }\n        let id = FileId::of(file)?;\n        // LMKD may run in init's explicitly supplied default APEX mount\n        // namespace. All other namespaces must be the stable private init's.\n        if NS_NAMES[index] != \"mnt\" && id != init_pins.ids[index] {\n            return Err(Error::Reject(\"role namespace is outside the lifecycle cell\"));\n        }\n        ids.push(id);\n    }\n    Ok(NamespacePins { files, ids })\n}\nfn claim_directory(directory: &File, spec: &BootstrapSpec, authority: &CellAuthority) -> Result<()> {\n    let m = directory.metadata().map_err(|e| io_err(\"stat lifecycle endpoint directory\", e))?;\n    if !m.is_dir() || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o077 != 0 {\n        return Err(Error::Reject(\"bootstrap endpoint directory is not private root-owned\"));\n    }\n    // Persistent, exclusive marker. Broker exit/crash never makes this same\n    // lifecycle directory reusable. Only the trusted supervisor may provision\n    // a NEW cell directory after old retirement AND both exact old PIDs exit.\n    let name = CString::new(\"droidloom-lmkd-psi.claim\").expect(\"literal\");\n    let raw = unsafe { libc::openat(directory.as_raw_fd(), name.as_ptr(), libc::O_WRONLY | libc::O_CREAT |\n        libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC, 0o600) };\n    if raw < 0 { return Err(err(\"claim one-shot lifecycle endpoint directory\")); }\n    let mut marker = unsafe { File::from_raw_fd(raw) };\n    let mut data = [0; 104]; data[..8].copy_from_slice(b\"P4SLOT1!\");\n    data[8..40].copy_from_slice(&spec.nonce); data[40..72].copy_from_slice(&authority.generation);\n    put(&mut data, 72, authority.root_id.device, 8); put(&mut data, 80, authority.root_id.inode, 8);\n    put(&mut data, 88, authority.owner.start, 8); put(&mut data, 96, authority.init.start, 8);\n    marker.write_all(&data).map_err(|e| io_err(\"record lifecycle one-shot claim\", e))?;\n    marker.sync_all().map_err(|e| io_err(\"persist lifecycle one-shot claim\", e))\n}\n\nfn owned_bootstrap_directory(file: &File, filesystem: libc::c_long) -> Result<()> {\n    require_fs(file, filesystem)?;\n    let m = file.metadata().map_err(|e| io_err(\"stat bootstrap layout directory\", e))?;\n    if !m.is_dir() || m.nlink() == 0 || m.uid() != 0 || m.gid() != 0 || m.mode() & 0o022 != 0 {\n        return Err(Error::Reject(\"bootstrap layout directory owner/type/mode differs\"));\n    }\n    Ok(())\n}\nfn exact_holding_membership(root_procs: &str, leaf_procs: &str, init_pid: libc::pid_t) -> Result<()> {\n    if init_pid <= 0 || !root_procs.is_empty() || leaf_procs != format!(\"{init_pid}\\n\") {\n        return Err(Error::Reject(\"bootstrap holding layout requires empty root and exact init leaf\"));\n    }\n    Ok(())\n}\n// Retain the actual directories and both host-mount ancestry proofs until\n// bootstrap is complete. A second capture must match these same generations;\n// a replacement pathname, sibling, ancestor, or different mount cannot pass.\nstruct BootstrapLayoutPins {\n    layout: BootstrapLayout,\n    files: Vec<File>,\n    ids: Vec<FileId>,\n    ancestry: Vec<ancestry::CgroupAncestry>,\n}\nimpl BootstrapLayoutPins {\n    fn capture(layout: BootstrapLayout, host: &HostContext, root: &File, init: &ProcessPin) -> Result<Self> {\n        init.live()?;\n        let root_id = FileId::of(root)?;\n        let init_root = open_at(&init.proc_dir, \"root\", libc::O_PATH | libc::O_DIRECTORY)?;\n        let member = host.membership(&init.proc_dir)?;\n        let mut ancestry = Vec::new();\n        let files = match layout {\n            BootstrapLayout::ProjectedRootV1 => {\n                let projection = beneath_dir(&init_root, \"sys/fs/cgroup\")?;\n                require_fs(&projection, CGROUP2_MAGIC)?;\n                if FileId::of(&member)? != root_id || FileId::of(&projection)? != root_id {\n                    return Err(Error::Reject(\"bootstrap init membership/projection differs from held root\"));\n                }\n                vec![init_root, member, projection]\n            }\n            BootstrapLayout::HoldingLeafV3 => {\n                owned_bootstrap_directory(root, CGROUP2_MAGIC)?;\n                let holding = beneath_dir(&init_root, \"dev/.droidloom-cgroups\")?;\n                let projection = beneath_dir(&init_root, \"dev/.droidloom-cgroups/relay-v2\")?;\n                let sys = beneath_dir(&init_root, \"sys\")?;\n                let target = beneath_dir(&init_root, \"sys/fs/cgroup\")?;\n                owned_bootstrap_directory(&holding, TMPFS_MAGIC)?;\n                owned_bootstrap_directory(&projection, CGROUP2_MAGIC)?;\n                owned_bootstrap_directory(&sys, TMPFS_MAGIC)?;\n                owned_bootstrap_directory(&target, TMPFS_MAGIC)?;\n                if FileId::of(&projection)? != root_id || FileId::of(&sys)?.device != FileId::of(&target)?.device {\n                    return Err(Error::Reject(\"bootstrap holding projection or native target differs from held layout\"));\n                }\n                let leaf = beneath_dir(root, \"init-bootstrap\")?;\n                owned_bootstrap_directory(&leaf, CGROUP2_MAGIC)?;\n                let parent = open_at(&leaf, \"..\", libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW)?;\n                if FileId::of(&leaf)? == root_id || FileId::of(&member)? != FileId::of(&leaf)? ||\n                    FileId::of(&parent)? != root_id || read_at(root, \"cgroup.type\", 64)? != \"domain\\n\" ||\n                    read_at(&leaf, \"cgroup.type\", 64)? != \"domain\\n\" ||\n                    !read_at(&leaf, \"cgroup.subtree_control\", 256)?.trim().is_empty() {\n                    return Err(Error::Reject(\"bootstrap init is outside the exact controller-free leaf\"));\n                }\n                ancestry.push(ancestry::CgroupAncestry::capture(root, &member)?);\n                ancestry.push(ancestry::CgroupAncestry::capture(root, &leaf)?);\n                exact_holding_membership(&read_at(root, \"cgroup.procs\", 64)?,\n                    &read_at(&leaf, \"cgroup.procs\", 64)?, init.pid)?;\n                vec![init_root, member, projection, holding, sys, target, leaf, parent]\n            }\n        };\n        let ids = files.iter().map(FileId::of).collect::<Result<Vec<_>>>()?;\n        init.live()?;\n        Ok(Self { layout, files, ids, ancestry })\n    }\n    fn validate(&self, host: &HostContext, root: &File, init: &ProcessPin) -> Result<()> {\n        let current = Self::capture(self.layout, host, root, init)?;\n        if self.files.len() != self.ids.len() || current.ids != self.ids || current.ancestry.len() != self.ancestry.len() {\n            return Err(Error::Reject(\"bootstrap layout changed during authority construction\"));\n        }\n        for (file, expected) in self.files.iter().zip(&self.ids) {\n            if FileId::of(file)? != *expected { return Err(Error::Reject(\"held bootstrap layout generation changed\")); }\n        }\n        for (held, observed) in self.ancestry.iter().zip(&current.ancestry) {\n            held.validate()?;\n            if !held.same_as(observed) { return Err(Error::Reject(\"bootstrap leaf ancestor chain changed\")); }\n        }\n        Ok(())\n    }\n}\n\nfn bootstrap(host: &HostContext, parent: &ProcessPin, channel: RawFd) -> Result<(BootstrapSpec, Arc<CellAuthority>, File)> {\n    let mut deadline = Deadline::new(Duration::from_secs(2))?;\n    let (wire, rights) = receive_packet(channel, BOOT_SIZE, &mut deadline, false)?;\n    if rights.len() != RIGHTS { return Err(Error::Reject(\"bootstrap requires exactly sixteen owned descriptors\")); }\n    let (spec, layout) = BootstrapSpec::decode_with_layout(&wire)?;\n    let mut rights = rights.into_iter();\n    let root = File::from(rights.next().expect(\"fixed rights count\"));\n    let owner = adopt_pidfd(host, rights.next().expect(\"fixed rights count\"))?;\n    let init = adopt_pidfd(host, rights.next().expect(\"fixed rights count\"))?;\n    let lmkd = ExecutablePin::from_lifecycle(File::from(rights.next().expect(\"fixed rights count\")), spec.lmkd_sha256)?;\n    let expected_init = ExecutablePin::from_lifecycle(File::from(rights.next().expect(\"fixed rights count\")), spec.init_sha256)?;\n    let directory = File::from(rights.next().expect(\"fixed rights count\"));\n    let owner_status = read_at(&owner.proc_dir, \"status\", MAX_PROC_BYTES)?;\n    let init_status = read_at(&init.proc_dir, \"status\", MAX_PROC_BYTES)?;\n    if owner.pid != parent.pid && status_scalar(&owner_status, \"PPid:\")? != parent.pid as u64 {\n        return Err(Error::Reject(\"namespace owner is not held by bootstrap parent\"));\n    }\n    let identity = parse_status(&init_status, init.pid)?;\n    if init.pid == owner.pid || status_scalar(&init_status, \"PPid:\")? != owner.pid as u64 ||\n        identity.namespace_pids.len() < 2 || identity.namespace_pids.last() != Some(&1) ||\n        identity.uids != [0; 4] || identity.gids != [0; 4] {\n        return Err(Error::Reject(\"init is not the exact private root child of namespace owner\"));\n    }\n    let init_executable = open_at(&init.proc_dir, \"exe\", libc::O_RDONLY)?;\n    expected_init.matches(&init_executable, true)?;\n    let layout_pins = BootstrapLayoutPins::capture(layout, host, &root, &init)?;\n    let namespaces = role_namespaces(rights.map(File::from).collect(), &init)?;\n    if namespaces.identity(\"pid\") == host.host_namespaces.identity(\"pid\") {\n        return Err(Error::Reject(\"bootstrap init must be in a private PID namespace\"));\n    }\n    let role = RolePolicy { uid: spec.uid, gid: spec.gid, namespaces, executable: lmkd };\n    let authority = Arc::new(CellAuthority::from_lifecycle(root, owner, init, role)?);\n    parent.live()?; host.validate_host_view()?; no_unexpected_peer_data(channel)?; deadline.check()?;\n    layout_pins.validate(host, &authority.root, &authority.init)?;\n    claim_directory(&directory, &spec, &authority)?;\n    layout_pins.validate(host, &authority.root, &authority.init)?;\n    deadline.check()?;\n    Ok((spec, authority, directory))\n}\n\nfn valid_retirement(wire: &[u8], spec: &BootstrapSpec) -> bool {\n    wire.len() == RETIRE_SIZE && &wire[..8] == b\"P4RET01!\" && number(wire, 8, 4) == 1 &&\n        number(wire, 12, 4) == 0 && wire[16..48] == spec.nonce\n}\n\n/// Production executable entry. Call once in a freshly exec'd, host-namespace\n/// process leader with one inherited nonblocking seqpacket at fd 3. The exact\n/// parent owns startup, endpoint projection, timeout policy and cell teardown.\n/// No endpoint is opened until its sixteen trusted handles pass validation.\npub fn run_inherited_lifecycle(channel: OwnedFd) -> Result<()> {\n    let host = Arc::new(HostContext::open()?);\n    let parent = trusted_parent(&host, channel.as_raw_fd())?;\n    let (spec, authority, directory) = bootstrap(&host, &parent, channel.as_raw_fd())?;\n    let prepared = PreparedRelay::bind_at(directory, spec.uid, spec.gid)?;\n    let scope = authority.scope_request();\n    let mut status = BootstrapStatus { state: BootstrapState::Ready, nonce: spec.nonce,\n        generation: authority.generation, endpoint: prepared.endpoint_identity(), cgroup: scope.cgroup,\n        budget: scope.budget, granted: false, faulted: false };\n    let mut relay = prepared.activate(Arc::clone(&host), authority)?;\n    let outcome = (|| -> Result<()> {\n        send_packet(channel.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1))?)?;\n        loop {\n            parent.live()?; host.validate_host_view()?;\n            match relay.phase() {\n                RelayPhase::Active if !status.granted => {\n                    status.state = BootstrapState::Active; status.granted = true;\n                    send_packet(channel.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1))?)?;\n                }\n                RelayPhase::Retiring | RelayPhase::Retired | RelayPhase::Poisoned =>\n                    return Err(Error::Reject(\"relay service retired; exact old cell requires lifecycle recovery\")),\n                _ => {}\n            }\n            let mut p = libc::pollfd { fd: channel.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };\n            if unsafe { libc::poll(&mut p, 1, 100) } < 0 {\n                if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }\n                return Err(err(\"wait lifecycle retirement command\"));\n            }\n            if p.revents & BAD != 0 { return Err(Error::Reject(\"lifecycle parent control lost\")); }\n            if p.revents & libc::POLLIN != 0 {\n                let (wire, rights) = receive_packet(channel.as_raw_fd(), RETIRE_SIZE, &mut Deadline::new(Duration::from_secs(1))?, false)?;\n                if !rights.is_empty() || !valid_retirement(&wire, &spec) {\n                    return Err(Error::Reject(\"unexpected lifecycle command or replay\"));\n                }\n                return Ok(());\n            }\n        }\n    })();\n    // Every path after activation goes through verified retirement. A failed\n    // or timed-out join retains the owner and cannot emit RETIRED or exit as a\n    // success. The lifecycle parent must retain its own cell ownership too.\n    relay.request_retirement();\n    loop {\n        match relay.finish_retirement(Duration::from_millis(250)) {\n            Ok(Some(receipt)) => {\n                status.state = BootstrapState::Retired;\n                status.granted = receipt.was_granted();\n                status.faulted = outcome.is_err() || receipt.reason().is_some();\n                let audit = PressureAudit::from_retirement(&status, receipt, super::psi::now_ns()?);\n                // Joined-worker observations use this exact trusted parent\n                // channel. They supply no authority and do not substitute for\n                // the following terminal status and exact process reap.\n                send_packet(channel.as_raw_fd(), &audit.encode()?, &[], &mut Deadline::new(Duration::from_secs(1))?)?;\n                send_packet(channel.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1))?)?;\n                if status.faulted && outcome.is_ok() {\n                    return Err(Error::Reject(\"PSI worker faulted while lifecycle retirement completed\"));\n                }\n                return outcome;\n            }\n            Ok(None) => {}\n            Err(_) => thread::sleep(Duration::from_millis(100)), // permanently unproven, never fabricate a receipt\n        }\n    }\n}\n\n/// Read-only kernel identities from an existing authenticated broker pin.\n/// This serializable-by-the-caller data is never accepted as authority.\n#[derive(Clone, Debug, Eq, PartialEq)]\npub struct LifecycleProcessObservation {\n    pub pid: i32,\n    pub birth: u64,\n    pub pidfd: FileId,\n    pub proc_dir: FileId,\n}\n\n/// Supervisor-side ownership adapter. It executes the exact verified broker\n/// inode through a held FD, keeps the exact Child and a private inherited\n/// socketpair, and uses the SAME process-wide lifecycle slot as PreparedRelay.\n///\n/// Spawn returns the owner before any bootstrap I/O. initialize/retire errors\n/// leave it in the caller's hands. Never remove this value from ActiveCell on\n/// error, and never open LMKD's startup barrier before initialize returns READY.\npub struct LifecycleBroker {\n    child: std::process::Child,\n    running: Option<ProcessPin>,\n    channel: OwnedFd,\n    executable: ExecutablePin,\n    host: HostContext,\n    spec: BootstrapSpec,\n    layout: BootstrapLayout,\n    inputs: Option<Vec<OwnedFd>>,\n    attempted: bool,\n    ready: Option<BootstrapStatus>,\n    latest: Option<BootstrapStatus>,\n    audit: Option<PressureAudit>,\n    retirement_requested: bool,\n    retirement_seen: bool,\n    joined: bool,\n    retired: Arc<AtomicBool>,\n}\nimpl LifecycleBroker {\n    pub fn spawn(executable: ExecutablePin, spec: BootstrapSpec, handles: &[BorrowedFd<'_>; RIGHTS]) -> Result<Self> {\n        Self::spawn_in_context(HostContext::open()?, executable, spec, handles)\n    }\n    /// Legacy owned-fixture entry with an already projected domain root.\n    /// Accepts only a HostContext originally opened by the process leader.\n    /// Its fields are private; forked processes and workers which change any\n    /// namespace fail validation before they can spawn or send authority.\n    pub fn spawn_in_context(host: HostContext, executable: ExecutablePin, spec: BootstrapSpec,\n        handles: &[BorrowedFd<'_>; RIGHTS]) -> Result<Self> {\n        Self::spawn_with_layout(host, executable, spec, handles, BootstrapLayout::ProjectedRootV1)\n    }\n    /// Paired only with the real ABI3 init barrier: the finite domain is at\n    /// its verified holding view and init occupies the exact bootstrap leaf.\n    /// This sends a version-2/layout-3 packet; an old broker rejects it. There\n    /// is no fallback to the legacy fixture's already-projected root layout.\n    pub fn spawn_holding_in_context(host: HostContext, executable: ExecutablePin, spec: BootstrapSpec,\n        handles: &[BorrowedFd<'_>; RIGHTS]) -> Result<Self> {\n        Self::spawn_with_layout(host, executable, spec, handles, BootstrapLayout::HoldingLeafV3)\n    }\n    fn spawn_with_layout(host: HostContext, executable: ExecutablePin, spec: BootstrapSpec,\n        handles: &[BorrowedFd<'_>; RIGHTS], layout: BootstrapLayout) -> Result<Self> {\n        use std::os::unix::process::CommandExt;\n        spec.validate()?;\n        if unsafe { libc::geteuid() } != 0 || unsafe { libc::getegid() } != 0 {\n            return Err(Error::Reject(\"lifecycle broker caller must be root\"));\n        }\n        executable.matches(&executable.file, true)?;\n        host.validate_current_thread()?;\n        let owner = adopt_pidfd(&host, duplicate(handles[1].as_raw_fd())?)?;\n        let init = adopt_pidfd(&host, duplicate(handles[2].as_raw_fd())?)?;\n        let inputs = handles.iter().map(|fd| duplicate(fd.as_raw_fd())).collect::<Result<Vec<_>>>()?;\n        let mut pair = [-1; 2];\n        if unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,\n            0, pair.as_mut_ptr()) } < 0 { return Err(err(\"create private lifecycle bootstrap socketpair\")); }\n        let channel = unsafe { OwnedFd::from_raw_fd(pair[0]) };\n        let child_socket = unsafe { OwnedFd::from_raw_fd(pair[1]) };\n        // The child bootstrap channel is exactly fd 3. Pin the executable at a\n        // different high descriptor before pre_exec can replace that number.\n        let binary_raw = unsafe { libc::fcntl(executable.file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 64) };\n        if binary_raw < 0 { return Err(err(\"pin exact broker exec descriptor\")); }\n        let binary = unsafe { OwnedFd::from_raw_fd(binary_raw) };\n        let source = child_socket.as_raw_fd();\n        let parent_pid = unsafe { libc::getpid() };\n        let mut command = std::process::Command::new(format!(\"/proc/self/fd/{}\", binary.as_raw_fd()));\n        command.args([\"--lifecycle-fd\", \"3\"]).stdin(std::process::Stdio::null());\n        unsafe {\n            command.pre_exec(move || {\n                if source != 3 && libc::dup2(source, 3) < 0 { return Err(io::Error::last_os_error()); }\n                if libc::fcntl(3, libc::F_SETFD, 0) < 0 || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0 {\n                    return Err(io::Error::last_os_error());\n                }\n                if libc::getppid() != parent_pid { return Err(io::Error::other(\"lifecycle parent changed before exec\")); }\n                Ok(())\n            });\n        }\n        let retired = super::lifecycle_relay::reserve_lifecycle_process_slot(owner.pidfd.as_raw_fd(), init.pidfd.as_raw_fd())?;\n        let child = match command.spawn() {\n            Ok(child) => child,\n            Err(error) => {\n                // Command::spawn has reaped a pre-exec failure. No trusted\n                // bootstrap was sent, so no PSI owner can have been created.\n                retired.store(true, Ordering::Release);\n                return Err(io_err(\"execute exact lifecycle broker\", error));\n            }\n        };\n        // No fallible operation between spawn and returning retained ownership.\n        Ok(Self { child, running: None, channel, executable, host, spec, layout, inputs: Some(inputs), attempted: false,\n            ready: None, latest: None, audit: None, retirement_requested: false, retirement_seen: false, joined: false, retired })\n    }\n    pub fn pid(&self) -> u32 { self.child.id() }\n    pub fn latest_status(&self) -> Option<&BootstrapStatus> { self.latest.as_ref() }\n    pub fn retirement_complete(&self) -> bool { self.joined }\n    /// Data-only identity of the existing authenticated, live broker pin.\n    /// No API accepts this value as authority. The origin/worker validation is\n    /// unchanged, and neither a numeric PID nor a new process lookup is used.\n    pub fn process_observation(&self) -> Result<LifecycleProcessObservation> {\n        self.host.validate_current_thread()?;\n        let process = self.running.as_ref().ok_or(Error::Reject(\"broker process not authenticated\"))?;\n        process.live()?;\n        let mut stat: libc::stat = unsafe { std::mem::zeroed() };\n        if unsafe { libc::fstat(process.pidfd.as_raw_fd(), &mut stat) } < 0 {\n            return Err(err(\"observe held broker pidfd\"));\n        }\n        let result = LifecycleProcessObservation {\n            pid: process.pid, birth: process.start,\n            pidfd: FileId { device: stat.st_dev as u64, inode: stat.st_ino as u64 },\n            proc_dir: FileId::of(&process.proc_dir)?,\n        };\n        process.live()?;\n        Ok(result)\n    }\n    /// Close only this exact owned broker's authority channel after an\n    /// unproven retirement failure. This is revocation, never a joined receipt\n    /// or permission to release a generation. Keep this value retained.\n    pub fn revoke_unproven_control(&mut self) -> Result<()> {\n        if self.joined { return Err(Error::Reject(\"joined broker no longer needs unproven revocation\")); }\n        if unsafe { libc::shutdown(self.channel.as_raw_fd(), libc::SHUT_RDWR) } < 0 {\n            return Err(err(\"revoke unproven lifecycle control\"));\n        }\n        Ok(())\n    }\n    /// Audit becomes available only after terminal status and exact child reap.\n    pub fn pressure_audit(&self) -> Option<&PressureAudit> { if self.joined { self.audit.as_ref() } else { None } }\n    /// Returns the kernel listener identity that the caller must compare with\n    /// its socket projection before releasing the owned LMKD startup barrier.\n    /// READY alone is neither enrollment nor a PSI event acceptance receipt.\n    pub fn initialize(&mut self) -> Result<&BootstrapStatus> {\n        if self.attempted || self.joined { return Err(Error::Reject(\"lifecycle broker bootstrap is one attempt\")); }\n        self.attempted = true;\n        self.host.validate_host_view()?;\n        let broker = self.host.pin_owned_child(&mut self.child)?;\n        let running = open_at(&broker.proc_dir, \"exe\", libc::O_RDONLY)?;\n        self.executable.matches(&running, true)?;\n        self.running = Some(broker);\n        let inputs = self.inputs.take().ok_or(Error::Reject(\"bootstrap inputs already consumed\"))?;\n        let borrowed: [BorrowedFd<'_>; RIGHTS] = std::array::from_fn(|index| unsafe {\n            BorrowedFd::borrow_raw(inputs[index].as_raw_fd())\n        });\n        self.spec.send_with_layout(unsafe { BorrowedFd::borrow_raw(self.channel.as_raw_fd()) }, &borrowed,\n            Duration::from_secs(2), self.layout)?;\n        drop(inputs);\n        let status = self.spec.receive_status(unsafe { BorrowedFd::borrow_raw(self.channel.as_raw_fd()) }, Duration::from_secs(2))?;\n        if status.state != BootstrapState::Ready { return Err(Error::Reject(\"lifecycle broker did not return initial READY\")); }\n        self.latest = Some(status.clone()); self.ready = Some(status);\n        // Keep a valid READY even if the child just failed, so the caller can\n        // still consume its terminal receipt and reap it without opening LMKD.\n        self.running.as_ref().expect(\"retained broker process pin\").live()?; self.host.validate_host_view()?;\n        Ok(self.ready.as_ref().expect(\"stored READY\"))\n    }\n    /// Final gate used immediately before releasing real Android init.\n    /// Pending progress is rejected here: enrollment cannot legitimately start\n    /// while init is still held in its constructor.\n    pub fn ready_for_init_commit(&self) -> Result<()> {\n        self.host.validate_current_thread()?;\n        if !self.attempted || self.joined || self.retirement_requested || self.retirement_seen ||\n            self.latest.as_ref().is_none_or(|s| s.state != BootstrapState::Ready || s.faulted || s.granted) {\n            return Err(Error::Reject(\"broker no longer holds its initial READY\"));\n        }\n        self.running.as_ref().ok_or(Error::Reject(\"broker process pin missing\"))?.live()?;\n        let mut p = libc::pollfd { fd: self.channel.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };\n        if unsafe { libc::poll(&mut p, 1, 0) } != 0 || p.revents != 0 {\n            return Err(Error::Reject(\"broker changed before init COMMIT\"));\n        }\n        Ok(())\n    }\n    /// Pure readiness query. Terminal packets may be drained with HUP, but a\n    /// bare dead/closed broker is never treated as successful retirement.\n    pub fn progress_available(&self) -> Result<bool> {\n        self.host.validate_current_thread()?;\n        let mut p = libc::pollfd { fd: self.channel.as_raw_fd(), events: libc::POLLIN | libc::POLLRDHUP, revents: 0 };\n        if unsafe { libc::poll(&mut p, 1, 0) } < 0 { return Err(err(\"poll owned broker progress\")); }\n        if p.revents & (libc::POLLERR | libc::POLLNVAL) != 0 { return Err(Error::Reject(\"broker progress fault\")); }\n        if p.revents & libc::POLLIN != 0 { return Ok(true); }\n        if p.revents & (libc::POLLHUP | libc::POLLRDHUP) != 0 { return Err(Error::Reject(\"broker closed without drained retirement\")); }\n        self.running.as_ref().ok_or(Error::Reject(\"broker process pin missing\"))?.live()?;\n        Ok(false)\n    }\n    fn accept_status(&mut self, status: BootstrapStatus) -> Result<()> {\n        let ready = self.ready.as_ref().ok_or(Error::Reject(\"no completed lifecycle bootstrap\"))?;\n        if status.generation != ready.generation || status.endpoint != ready.endpoint || status.cgroup != ready.cgroup ||\n            status.budget != ready.budget || status.state == BootstrapState::Ready || self.retirement_seen {\n            return Err(Error::Reject(\"lifecycle status changed scope/replayed terminal generation\"));\n        }\n        if status.state == BootstrapState::Active && self.latest.as_ref().is_some_and(|s| s.state == BootstrapState::Active) {\n            return Err(Error::Reject(\"repeated lifecycle ACTIVE status\"));\n        }\n        if status.state == BootstrapState::Retired {\n            let audit = self.audit.as_ref().ok_or(Error::Reject(\"retirement lacks joined pressure audit\"))?;\n            if audit.granted != status.granted || audit.faulted != status.faulted {\n                return Err(Error::Reject(\"pressure audit and retirement flags differ\"));\n            }\n        } else if self.audit.is_some() {\n            return Err(Error::Reject(\"nonterminal lifecycle status after terminal audit\"));\n        }\n        self.retirement_seen = status.state == BootstrapState::Retired;\n        self.latest = Some(status); Ok(())\n    }\n    /// Receives real grant/fault/retirement progress. A faulted RETIRED status\n    /// is the recovery hook: keep ActiveCell owned, finish this broker, then\n    /// stop and reap the exact old owner AND init before another generation.\n    pub fn receive_progress(&mut self, timeout: Duration) -> Result<&BootstrapStatus> {\n        let mut deadline = Deadline::new(timeout)?;\n        loop {\n            match receive_progress_frame(self.channel.as_raw_fd(), &mut deadline)? {\n                ProgressFrame::Audit(audit) => {\n                    let ready = self.ready.as_ref().ok_or(Error::Reject(\"pressure audit before READY\"))?;\n                    if self.audit.is_some() || self.retirement_seen || audit.nonce != self.spec.nonce ||\n                        audit.authority_generation != ready.generation || audit.cgroup != ready.cgroup || audit.budget != ready.budget {\n                        return Err(Error::Reject(\"terminal pressure audit replay/scope mismatch\"));\n                    }\n                    self.audit = Some(audit);\n                }\n                ProgressFrame::Status(status) => {\n                    if status.nonce != self.spec.nonce { return Err(Error::Reject(\"lifecycle progress nonce mismatch\")); }\n                    self.accept_status(status)?;\n                    return Ok(self.latest.as_ref().expect(\"stored progress\"));\n                }\n            }\n        }\n    }\n    /// A timeout/error retains the Child/control/slot. Successful return needs\n    /// both a valid joined-worker RETIRED packet AND reaping the exact broker.\n    /// This still does not certify that the old Android owner/init have died.\n    pub fn retire(&mut self, timeout: Duration) -> Result<bool> {\n        if self.joined { return Ok(true); }\n        if !self.attempted || self.ready.is_none() { return Err(Error::Reject(\"bootstrap incomplete; retain failed owner\")); }\n        let deadline = Deadline::new(timeout)?;\n        if !self.retirement_seen && !self.retirement_requested {\n            self.retirement_requested = true;\n            self.spec.request_retirement(unsafe { BorrowedFd::borrow_raw(self.channel.as_raw_fd()) }, timeout)?;\n        }\n        while !self.retirement_seen {\n            let remaining = deadline.0.saturating_duration_since(Instant::now());\n            if remaining < Duration::from_millis(1) { return Ok(false); }\n            self.receive_progress(remaining)?;\n        }\n        loop {\n            if let Some(exit) = self.child.try_wait().map_err(|e| io_err(\"reap exact lifecycle broker\", e))? {\n                let faulted = self.latest.as_ref().expect(\"retirement status\").faulted;\n                if exit.code() != Some(if faulted { 1 } else { 0 }) {\n                    return Err(Error::Reject(\"broker exit disagrees with retirement receipt\"));\n                }\n                self.joined = true; self.retired.store(true, Ordering::Release); return Ok(true);\n            }\n            if Instant::now() >= deadline.0 { return Ok(false); }\n            thread::sleep(Duration::from_millis(1));\n        }\n    }\n    /// Only before ANY bootstrap send, stopping/reaping this exact child proves\n    /// there was no authority or PSI owner. After initialize starts, failures\n    /// must retain the handle and cannot use this shortcut.\n    pub fn abort_before_initialize(&mut self) -> Result<()> {\n        if self.attempted || self.joined { return Err(Error::Reject(\"bootstrap attempt already consumed\")); }\n        if self.child.try_wait().map_err(|e| io_err(\"poll unbootstrapped broker\", e))?.is_none() {\n            self.child.kill().map_err(|e| io_err(\"stop exact unbootstrapped broker\", e))?;\n        }\n        self.child.wait().map_err(|e| io_err(\"reap unbootstrapped broker\", e))?;\n        self.inputs = None; self.joined = true; self.retired.store(true, Ordering::Release); Ok(())\n    }\n}\nimpl Drop for LifecycleBroker {\n    fn drop(&mut self) {\n        // Closing the inherited control requests broker retirement. Do NOT\n        // fabricate a joined receipt, reset the shared slot, kill a cell, or\n        // silently authorize a replacement from a best-effort destructor.\n        if !self.joined { unsafe { libc::shutdown(self.channel.as_raw_fd(), libc::SHUT_RDWR) }; }\n    }\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    fn spec() -> BootstrapSpec { BootstrapSpec { nonce: [7; 32], uid: 1069, gid: 1069,\n        lmkd_sha256: [8; 32], init_sha256: [9; 32] } }\n    fn sockets() -> (OwnedFd, OwnedFd) {\n        let mut fds = [-1; 2];\n        assert_eq!(unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC |\n            libc::SOCK_NONBLOCK, 0, fds.as_mut_ptr()) }, 0);\n        unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) }\n    }\n    fn empty_audit_and_status() -> (PressureAudit, BootstrapStatus) {\n        let s = spec(); let mut budget = [0; 32]; put(&mut budget, 0, 512 * 1024 * 1024, 8);\n        put(&mut budget, 24, 1, 4); put(&mut budget, 28, 1, 4);\n        let status = BootstrapStatus { state: BootstrapState::Retired, nonce: s.nonce, generation: [6; 32],\n            endpoint: FileId { device: 1, inode: 2 }, cgroup: FileId { device: 3, inode: 4 }, budget,\n            granted: false, faulted: false };\n        let audit = PressureAudit { nonce: s.nonce, authority_generation: status.generation, cgroup: status.cgroup,\n            budget, granted: false, faulted: false, incomplete: false, registrations: RegistrationAudit::default(),\n            observations: 0, packets_queued: 0, stop_reason: 0, events: EventAuditTrail::default(), retired_monotonic_ns: 10 };\n        (audit, status)\n    }\n    #[test]\n    fn producer05_three_second_retirement_is_rejected_before_transport() {\n        let (caller, peer) = sockets();\n        // Producer05 passed this exact argument to LifecycleBroker::retire.\n        // Its first Deadline::new rejects it; the public request path shares\n        // that same bound. Preserve the old failure rather than relaxing it.\n        let result = spec().request_retirement(\n            unsafe { BorrowedFd::borrow_raw(caller.as_raw_fd()) },\n            Duration::from_secs(3),\n        );\n        assert!(matches!(result, Err(Error::Reject(\"bootstrap I/O bound outside 1..2000 ms\"))));\n        let mut byte = 0u8;\n        assert_eq!(unsafe { libc::recv(peer.as_raw_fd(), (&mut byte as *mut u8).cast(), 1,\n            libc::MSG_DONTWAIT) }, -1);\n        assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);\n    }\n    #[test]\n    fn shared_retirement_bound_sends_exact_request_and_receives_terminal_ack() {\n        let (caller, peer) = sockets();\n        let request = spec();\n        let peer_request = request.clone();\n        let (_, expected_ack) = empty_audit_and_status();\n        let peer_ack = expected_ack.clone();\n        let server = std::thread::spawn(move || {\n            let (wire, rights) = receive_packet(peer.as_raw_fd(), RETIRE_SIZE,\n                &mut Deadline::new(MAX_LIFECYCLE_IO_TIMEOUT)?, false)?;\n            let mut expected = [0; RETIRE_SIZE];\n            expected[..8].copy_from_slice(b\"P4RET01!\");\n            put(&mut expected, 8, 1, 4);\n            expected[16..48].copy_from_slice(&peer_request.nonce);\n            if wire != expected || !rights.is_empty() {\n                return Err(Error::Reject(\"ordinary retirement control received a different request\"));\n            }\n            send_packet(peer.as_raw_fd(), &peer_ack.encode(), &[],\n                &mut Deadline::new(MAX_LIFECYCLE_IO_TIMEOUT)?)\n            // Closing peer after the real send also covers terminal POLLIN+HUP.\n        });\n        let actual = request.request_retirement(\n            unsafe { BorrowedFd::borrow_raw(caller.as_raw_fd()) }, MAX_LIFECYCLE_IO_TIMEOUT,\n        ).and_then(|()| request.receive_status(\n            unsafe { BorrowedFd::borrow_raw(caller.as_raw_fd()) }, MAX_LIFECYCLE_IO_TIMEOUT,\n        ));\n        // Join the bounded real peer even when the caller path fails.\n        let peer_result = server.join();\n        peer_result.unwrap().unwrap();\n        assert_eq!(actual.unwrap(), expected_ack);\n    }\n    #[test]\n    fn audit_and_terminal_packet_survive_peer_close_with_exact_framing() {\n        let (send, receive) = sockets(); let (audit, status) = empty_audit_and_status();\n        send_packet(send.as_raw_fd(), &audit.encode().unwrap(), &[], &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();\n        send_packet(send.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();\n        drop(send);\n        match receive_progress_frame(receive.as_raw_fd(), &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap() {\n            ProgressFrame::Audit(actual) => assert_eq!(actual, audit),\n            ProgressFrame::Status(_) => panic!(\"audit packet was confused with terminal status\"),\n        }\n        match receive_progress_frame(receive.as_raw_fd(), &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap() {\n            ProgressFrame::Status(actual) => assert_eq!(actual, status),\n            ProgressFrame::Audit(_) => panic!(\"terminal status was confused with audit\"),\n        }\n        assert!(receive_progress_frame(receive.as_raw_fd(), &mut Deadline::new(Duration::from_secs(1)).unwrap()).is_err());\n    }\n    #[test]\n    fn progress_audit_rejects_and_closes_unexpected_rights() {\n        let (send, receive) = sockets(); let (audit, _) = empty_audit_and_status();\n        let mut pipe = [-1; 2]; assert_eq!(unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) }, 0);\n        let (reader, writer) = unsafe { (OwnedFd::from_raw_fd(pipe[0]), OwnedFd::from_raw_fd(pipe[1])) };\n        send_packet(send.as_raw_fd(), &audit.encode().unwrap(), &[writer.as_raw_fd(); RIGHTS],\n            &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();\n        drop(writer);\n        assert!(receive_progress_frame(receive.as_raw_fd(), &mut Deadline::new(Duration::from_secs(1)).unwrap()).is_err());\n        let mut byte = 0u8;\n        assert_eq!(unsafe { libc::read(reader.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) }, 0);\n    }\n    #[test]\n    fn bootstrap_codec_is_fixed_and_rejects_reserved_policy() {\n        let s = spec(); let wire = s.encode().unwrap(); assert_eq!(BootstrapSpec::decode(&wire).unwrap(), s);\n        for at in [0, 8, 20, 23, 120, 127] {\n            let mut malformed = wire; malformed[at] ^= 1; assert!(BootstrapSpec::decode(&malformed).is_err());\n        }\n        assert!(BootstrapSpec::decode(&wire[..127]).is_err());\n        let mut s = s; s.uid = 0; assert!(s.encode().is_err());\n    }\n    #[test]\n    fn holding_bootstrap_version_is_explicit_and_never_falls_back() {\n        let s = spec();\n        let legacy = s.encode().unwrap();\n        let holding = s.encode_with_layout(BootstrapLayout::HoldingLeafV3).unwrap();\n        assert_eq!(&legacy[..8], b\"P4BOOT1!\");\n        assert_eq!(number(&legacy, 8, 4), 1);\n        assert_eq!(number(&legacy, 20, 4), 0);\n        assert_eq!(&holding[..8], b\"P4BOOT2!\");\n        assert_eq!(number(&holding, 8, 4), 2);\n        assert_eq!(number(&holding, 20, 4), 3);\n        assert_eq!(BootstrapSpec::decode_with_layout(&holding).unwrap(), (s.clone(), BootstrapLayout::HoldingLeafV3));\n        assert_eq!(BootstrapSpec::decode_with_layout(&legacy).unwrap(), (s, BootstrapLayout::ProjectedRootV1));\n        // The old owned-child reader cannot silently reinterpret ABI3 input.\n        assert!(BootstrapSpec::decode(&holding).is_err());\n        for (version, layout) in [(1, 3), (2, 0), (2, 1), (2, 2), (3, 3), (2, u32::MAX)] {\n            let mut wrong = holding;\n            put(&mut wrong, 8, version as u64, 4); put(&mut wrong, 20, layout as u64, 4);\n            assert!(BootstrapSpec::decode_with_layout(&wrong).is_err());\n        }\n        let mut wrong = legacy; put(&mut wrong, 20, 3, 4);\n        assert!(BootstrapSpec::decode_with_layout(&wrong).is_err());\n        for at in [0, 120, 127] {\n            let mut wrong = holding; wrong[at] ^= 1;\n            assert!(BootstrapSpec::decode_with_layout(&wrong).is_err());\n        }\n        assert!(BootstrapSpec::decode_with_layout(&holding[..127]).is_err());\n    }\n    #[test]\n    fn holding_bootstrap_membership_requires_the_exact_init_slot() {\n        exact_holding_membership(\"\", \"17\\n\", 17).unwrap();\n        for (root, leaf, pid) in [(\"17\\n\", \"17\\n\", 17), (\"\\n\", \"17\\n\", 17),\n            (\"\", \"\", 17), (\"\", \"18\\n\", 17), (\"\", \"17\\n18\\n\", 17),\n            (\"\", \"17\\n17\\n\", 17), (\"\", \"017\\n\", 17), (\"\", \"17\", 17),\n            (\"\", \"17\\n\", 0), (\"\", \"17\\n\", -1)] {\n            assert!(exact_holding_membership(root, leaf, pid).is_err());\n        }\n    }\n    #[test]\n    fn holding_packet_rejects_legacy_owned_child_receiver_and_closes_rights() {\n        let (send, receive) = sockets();\n        let mut pipe = [-1; 2];\n        assert_eq!(unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) }, 0);\n        let (reader, writer) = unsafe { (OwnedFd::from_raw_fd(pipe[0]), OwnedFd::from_raw_fd(pipe[1])) };\n        let handles: [BorrowedFd<'_>; RIGHTS] = std::array::from_fn(|_| unsafe { BorrowedFd::borrow_raw(writer.as_raw_fd()) });\n        spec().send_with_layout(unsafe { BorrowedFd::borrow_raw(send.as_raw_fd()) }, &handles,\n            Duration::from_secs(1), BootstrapLayout::HoldingLeafV3).unwrap();\n        drop(writer);\n        assert!(spec().receive_from_owned_child(unsafe { BorrowedFd::borrow_raw(receive.as_raw_fd()) },\n            Duration::from_secs(1)).is_err());\n        let mut byte = 0u8;\n        assert_eq!(unsafe { libc::read(reader.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) }, 0);\n    }\n    #[test]\n    fn inherited_rights_are_cloexec_and_owned_on_reject() {\n        let (send, receive) = sockets();\n        let mut pipe = [-1; 2]; assert_eq!(unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) }, 0);\n        let (reader, writer) = unsafe { (OwnedFd::from_raw_fd(pipe[0]), OwnedFd::from_raw_fd(pipe[1])) };\n        send_packet(send.as_raw_fd(), &spec().encode().unwrap(), &[writer.as_raw_fd(); RIGHTS],\n            &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();\n        let (_, rights) = receive_packet(receive.as_raw_fd(), BOOT_SIZE,\n            &mut Deadline::new(Duration::from_secs(1)).unwrap(), false).unwrap();\n        assert_eq!(rights.len(), RIGHTS);\n        let numbers: Vec<_> = rights.iter().map(AsRawFd::as_raw_fd).collect();\n        for fd in &numbers { assert_ne!(unsafe { libc::fcntl(*fd, libc::F_GETFD) } & libc::FD_CLOEXEC, 0); }\n        drop(writer); drop(rights);\n        let mut byte = 0u8;\n        // EOF proves every transferred writer is closed, without racing\n        // unrelated parallel tests that may reuse numeric FD slots.\n        assert_eq!(unsafe { libc::read(reader.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) }, 0);\n    }\n    #[test]\n    fn bootstrap_parent_channel_rejects_extra_rights_and_old_nonce_commands() {\n        let s = spec();\n        let mut wire = [0; RETIRE_SIZE]; wire[..8].copy_from_slice(b\"P4RET01!\"); put(&mut wire, 8, 1, 4);\n        wire[16..].copy_from_slice(&s.nonce); assert!(valid_retirement(&wire, &s));\n        wire[16] ^= 1; assert!(!valid_retirement(&wire, &s));\n        let (send, receive) = sockets();\n        send_packet(send.as_raw_fd(), &[0; STATUS_SIZE], &[send.as_raw_fd()],\n            &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();\n        assert!(s.receive_status(unsafe { BorrowedFd::borrow_raw(receive.as_raw_fd()) }, Duration::from_secs(1)).is_err());\n    }\n    #[test]\n    fn malformed_packet_closes_all_transferred_rights() {\n        let (send, receive) = sockets();\n        let mut pipe = [-1; 2]; assert_eq!(unsafe { libc::pipe2(pipe.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) }, 0);\n        let (reader, writer) = unsafe { (OwnedFd::from_raw_fd(pipe[0]), OwnedFd::from_raw_fd(pipe[1])) };\n        send_packet(send.as_raw_fd(), &[0; BOOT_SIZE + 1], &[writer.as_raw_fd(); RIGHTS],\n            &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();\n        drop(writer);\n        assert!(receive_packet(receive.as_raw_fd(), BOOT_SIZE,\n            &mut Deadline::new(Duration::from_secs(1)).unwrap(), false).is_err());\n        let mut byte = 0u8;\n        assert_eq!(unsafe { libc::read(reader.as_raw_fd(), (&mut byte as *mut u8).cast(), 1) }, 0);\n    }\n    #[test]\n    fn terminal_status_survives_peer_close_but_never_certifies_pressure() {\n        let (send, receive) = sockets();\n        let s = spec(); let mut budget = [0; 32]; put(&mut budget, 0, 512 * 1024 * 1024, 8);\n        put(&mut budget, 24, 1, 4); put(&mut budget, 28, 1, 4);\n        let status = BootstrapStatus { state: BootstrapState::Retired, nonce: s.nonce, generation: [6; 32],\n            endpoint: FileId { device: 1, inode: 2 }, cgroup: FileId { device: 3, inode: 4 }, budget,\n            granted: false, faulted: true };\n        send_packet(send.as_raw_fd(), &status.encode(), &[], &mut Deadline::new(Duration::from_secs(1)).unwrap()).unwrap();\n        drop(send);\n        assert_eq!(s.receive_status(unsafe { BorrowedFd::borrow_raw(receive.as_raw_fd()) }, Duration::from_secs(1)).unwrap(), status);\n        assert!(s.receive_status(unsafe { BorrowedFd::borrow_raw(receive.as_raw_fd()) }, Duration::from_secs(1)).is_err());\n    }\n}\n"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/owner.rs": {
      "bytes": 39607,
      "sha256": "5b011974c71d4a5d96091ea98cd55ffe3f69c0a4abe28eb71c9fea58c8a04994",
      "text": "//! One retained supervisor owner for claim, finite domain, real init and broker.\nuse super::capability::{Artifact, Process};\nuse super::audit::{Audit, Event, FailureOrigin, RelayLifecycleAudit, RetirementRecord};\nuse super::domain::{self, Domain, Identity};\nuse super::entry;\nuse super::init_peer::{self, Hello, InitPeer};\nuse super::policy::{self, PressureRelaySpec};\nuse super::worker::Worker;\nuse crate::CellSpec;\nuse crate::generation_claim::{Claim, Store};\nuse droidloom_pressure_relay::{\n    BootstrapSpec, BootstrapState, BootstrapStatus, ExecutablePin, HostContext, LifecycleBroker,\n    MAX_LIFECYCLE_IO_TIMEOUT,\n};\nuse std::ffi::CString;\nuse std::fs::File;\nuse std::io::{self, Read};\nuse std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd};\nuse std::os::unix::fs::{FileExt, FileTypeExt, MetadataExt};\nuse std::os::unix::process::CommandExt;\nuse std::path::{Path, PathBuf};\nuse std::process::{Child, Command, Stdio};\nuse std::sync::{\n    Arc,\n    atomic::{AtomicU8, Ordering},\n};\nuse std::time::{Duration, Instant};\n\nconst ENDPOINT_CLAIM: &str = \"droidloom-lmkd-psi.claim\";\nconst WAITING: u8 = 1;\nconst COMMITTED: u8 = 2;\nconst ACTIVE: u8 = 3;\nconst RETIRING: u8 = 4;\nconst RETIRED: u8 = 5;\nconst FAILED: u8 = 6;\nfn error(message: &'static str) -> io::Error {\n    domain::error(message)\n}\nfn relay<T>(result: droidloom_pressure_relay::Result<T>) -> io::Result<T> {\n    result.map_err(io::Error::other)\n}\n\nstruct Cancel(File);\nimpl Cancel {\n    fn new() -> io::Result<Self> {\n        let fd = unsafe { libc::eventfd(0, libc::EFD_CLOEXEC | libc::EFD_NONBLOCK) };\n        if fd < 0 {\n            Err(io::Error::last_os_error())\n        } else {\n            Ok(Self(unsafe { File::from_raw_fd(fd) }))\n        }\n    }\n    fn request(&self) -> io::Result<()> {\n        let value = 1u64.to_ne_bytes();\n        loop {\n            let count =\n                unsafe { libc::write(self.0.as_raw_fd(), value.as_ptr().cast(), value.len()) };\n            if count == value.len() as isize {\n                return Ok(());\n            }\n            let e = io::Error::last_os_error();\n            if e.kind() == io::ErrorKind::Interrupted {\n                continue;\n            }\n            if e.kind() == io::ErrorKind::WouldBlock {\n                return Ok(());\n            }\n            return Err(e);\n        }\n    }\n    fn requested(&self) -> io::Result<bool> {\n        let mut poll = libc::pollfd {\n            fd: self.0.as_raw_fd(),\n            events: libc::POLLIN,\n            revents: 0,\n        };\n        let result = unsafe { libc::poll(&mut poll, 1, 0) };\n        if result < 0 {\n            return Err(io::Error::last_os_error());\n        }\n        if poll.revents & (libc::POLLERR | libc::POLLHUP | libc::POLLNVAL) != 0 {\n            return Err(error(\"lifecycle cancellation FD fault\"));\n        }\n        Ok(poll.revents & libc::POLLIN != 0)\n    }\n}\n\nstruct Endpoint {\n    parent: File,\n    directory: File,\n    name: CString,\n    identity: Identity,\n    removed: bool,\n    poisoned: bool,\n}\nstruct EndpointProof {\n    socket: File,\n    marker: File,\n    marker_bytes: [u8; 104],\n}\nimpl Endpoint {\n    fn create(runtime: &Path, nonce: &[u8; 32]) -> io::Result<Self> {\n        let parent = domain::directory(runtime)?;\n        let m = parent.metadata()?;\n        if m.uid() != 0 || m.gid() != 0 || m.mode() & 0o077 != 0 {\n            return Err(error(\"relay runtime directory is not private root-owned\"));\n        }\n        let name =\n            CString::new(format!(\"lmkd-relay-{}\", policy::hex(nonce))).expect(\"hex component\");\n        if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {\n            return Err(io::Error::last_os_error());\n        }\n        let directory = domain::at(\n            parent.as_raw_fd(),\n            &name,\n            libc::O_RDONLY | libc::O_DIRECTORY,\n            0,\n        )?;\n        let identity = Identity::of(&directory)?;\n        Ok(Self {\n            parent,\n            directory,\n            name,\n            identity,\n            removed: false,\n            poisoned: false,\n        })\n    }\n    fn validate(&self) -> io::Result<()> {\n        if self.removed || self.poisoned {\n            return Err(error(\"endpoint directory retired or poisoned\"));\n        }\n        let named = domain::at(\n            self.parent.as_raw_fd(),\n            &self.name,\n            libc::O_RDONLY | libc::O_DIRECTORY,\n            0,\n        )?;\n        let m = named.metadata()?;\n        if Identity::of(&named)? != self.identity\n            || Identity::of(&self.directory)? != self.identity\n            || m.uid() != 0\n            || m.gid() != 0\n            || m.mode() & 0o077 != 0\n        {\n            return Err(error(\"endpoint directory identity or ownership changed\"));\n        }\n        Ok(())\n    }\n    fn remove_after(\n        &mut self,\n        proof: &EndpointProof,\n        processes_retired: impl FnOnce() -> io::Result<()>,\n    ) -> io::Result<()> {\n        if self.poisoned {\n            return Err(error(\"endpoint cleanup is poisoned\"));\n        }\n        if self.removed {\n            return Ok(());\n        }\n        let result = (|| {\n            processes_retired()?;\n            self.validate()?;\n            for item in std::fs::read_dir(format!(\"/proc/self/fd/{}\", self.directory.as_raw_fd()))?\n            {\n                let name = item?.file_name();\n                if name != init_peer::ENDPOINT && name != ENDPOINT_CLAIM {\n                    return Err(error(\"unexpected entry in owned relay endpoint directory\"));\n                }\n            }\n            match domain::named(&self.directory, init_peer::ENDPOINT, libc::O_PATH) {\n                Ok(named) => {\n                    if Identity::of(&named)? != Identity::of(&proof.socket)?\n                        || !named.metadata()?.file_type().is_socket()\n                    {\n                        return Err(error(\"relay endpoint replaced before exact cleanup\"));\n                    }\n                    if unsafe {\n                        libc::unlinkat(\n                            self.directory.as_raw_fd(),\n                            c\"droidloom-lmkd-psi\".as_ptr(),\n                            0,\n                        )\n                    } != 0\n                    {\n                        return Err(io::Error::last_os_error());\n                    }\n                }\n                // The joined broker normally removes its own listener.\n                Err(e) if e.kind() == io::ErrorKind::NotFound => {}\n                Err(e) => return Err(e),\n            }\n            let marker = domain::named(&self.directory, ENDPOINT_CLAIM, libc::O_RDONLY)?;\n            validate_marker(&marker, &proof.marker_bytes)?;\n            if Identity::of(&marker)? != Identity::of(&proof.marker)? {\n                return Err(error(\"relay endpoint claim replaced\"));\n            }\n            if unsafe {\n                libc::unlinkat(\n                    self.directory.as_raw_fd(),\n                    c\"droidloom-lmkd-psi.claim\".as_ptr(),\n                    0,\n                )\n            } != 0\n            {\n                return Err(io::Error::last_os_error());\n            }\n            self.validate()?;\n            if unsafe {\n                libc::unlinkat(\n                    self.parent.as_raw_fd(),\n                    self.name.as_ptr(),\n                    libc::AT_REMOVEDIR,\n                )\n            } != 0\n            {\n                return Err(io::Error::last_os_error());\n            }\n            Ok(())\n        })();\n        if result.is_ok() {\n            self.removed = true;\n        } else {\n            self.poisoned = true;\n        }\n        result\n    }\n    fn prove_removed(&self) -> io::Result<()> {\n        if !self.removed || self.poisoned {\n            return Err(error(\"endpoint has no completed removal proof\"));\n        }\n        match domain::at(self.parent.as_raw_fd(), &self.name, libc::O_PATH, 0) {\n            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),\n            _ => Err(error(\"retired endpoint name reappeared\")),\n        }\n    }\n}\nfn validate_marker(marker: &File, expected: &[u8; 104]) -> io::Result<()> {\n    let m = marker.metadata()?;\n    if !m.is_file()\n        || m.uid() != 0\n        || m.gid() != 0\n        || m.mode() & 0o7777 != 0o600\n        || m.nlink() != 1\n        || m.size() != 104\n    {\n        return Err(error(\"broker one-shot marker type/owner/length differs\"));\n    }\n    validate_marker_bytes(marker, expected)\n}\nfn validate_marker_bytes(marker: &File, expected: &[u8; 104]) -> io::Result<()> {\n    if marker.metadata()?.size() != expected.len() as u64 {\n        return Err(error(\"broker marker length differs\"));\n    }\n    let mut actual = [0; 104];\n    let mut filled = 0;\n    while filled != actual.len() {\n        let count = marker.read_at(&mut actual[filled..], filled as u64)?;\n        if count == 0 {\n            return Err(error(\"broker one-shot marker truncated\"));\n        }\n        filled += count;\n    }\n    if &actual != expected {\n        return Err(error(\n            \"broker one-shot marker differs from owned generation\",\n        ));\n    }\n    Ok(())\n}\nfn endpoint_proof(\n    directory: &File,\n    nonce: &[u8; 32],\n    ready: &BootstrapStatus,\n    owner: &Process,\n    init: &Process,\n) -> io::Result<EndpointProof> {\n    let socket = domain::named(directory, init_peer::ENDPOINT, libc::O_PATH)?;\n    if Identity::of(&socket)?\n        != (Identity {\n            device: ready.endpoint.device,\n            inode: ready.endpoint.inode,\n        })\n    {\n        return Err(error(\"actual listener inode differs from broker READY\"));\n    }\n    let mut bytes = [0; 104];\n    bytes[..8].copy_from_slice(b\"P4SLOT1!\");\n    bytes[8..40].copy_from_slice(nonce);\n    bytes[40..72].copy_from_slice(&ready.generation);\n    for (at, value) in [\n        (72, ready.cgroup.device),\n        (80, ready.cgroup.inode),\n        (88, owner.start()),\n        (96, init.start()),\n    ] {\n        bytes[at..at + 8].copy_from_slice(&value.to_le_bytes());\n    }\n    let marker = domain::named(directory, ENDPOINT_CLAIM, libc::O_RDONLY)?;\n    validate_marker(&marker, &bytes)?;\n    Ok(EndpointProof {\n        socket,\n        marker,\n        marker_bytes: bytes,\n    })\n}\n\nstruct Session {\n    audit: Audit,\n    host: Option<HostContext>,\n    owner: Process,\n    domain: Option<Arc<Domain>>,\n    peer: InitPeer,\n    policy: PressureRelaySpec,\n    nonce: [u8; 32],\n    directory: File,\n    barrier: Artifact,\n    lmkd: Artifact,\n    broker_image: Artifact,\n    cancel: Arc<Cancel>,\n    phase: Arc<AtomicU8>,\n    hello: Option<Hello>,\n    broker: Option<LifecycleBroker>,\n    initialize_started: bool,\n    endpoint: Option<EndpointProof>,\n    retired_init: Option<Process>,\n    reason: Option<String>,\n    retirement_error: Option<String>,\n}\nimpl Session {\n    fn run(&mut self) {\n        let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| self.run_inner()));\n        if let Err(payload) = outcome {\n            self.audit.failure(FailureOrigin::Panic, \"lifecycle worker panicked; generation remains persistently closed\");\n            self.phase.store(FAILED, Ordering::Release);\n            self.retirement_error =\n                Some(\"lifecycle worker panicked; generation remains persistently closed\".into());\n            self.peer.close();\n            if let Some(broker) = &mut self.broker {\n                let _ = relay(broker.revoke_unproven_control());\n            }\n            let _ = self.stop_exact_processes();\n            // Worker::join records permanent poison and keeps this exact\n            // Session in its poisoned mutex. No handle is substituted.\n            std::panic::resume_unwind(payload);\n        }\n    }\n    fn run_inner(&mut self) {\n        let outcome = self.run_generation();\n        if let Err(e) = outcome {\n            self.audit.failure(FailureOrigin::Runtime, &e.to_string());\n            self.reason = Some(e.to_string());\n        }\n        self.phase.store(RETIRING, Ordering::Release);\n        self.audit.record(Ok(Event::Retiring));\n        self.peer.close();\n        let retired = self.retire_generation();\n        if let Err(e) = retired {\n            self.audit.failure(FailureOrigin::Retirement, &e.to_string());\n            self.retirement_error = Some(e.to_string());\n            self.phase.store(FAILED, Ordering::Release);\n        } else {\n            self.phase.store(RETIRED, Ordering::Release);\n            self.audit.record(Ok(Event::Retired));\n        }\n    }\n    fn run_generation(&mut self) -> io::Result<()> {\n        let domain = Arc::clone(\n            self.domain\n                .as_ref()\n                .ok_or_else(|| error(\"worker domain missing\"))?,\n        );\n        self.hello = Some(self.peer.accept(\n            &self.owner,\n            &domain,\n            &self.policy,\n            &self.barrier,\n            &self.cancel.0,\n            &self.audit,\n        )?);\n        let hello = self.hello.as_ref().expect(\"retained actual init HELLO\");\n        let spec = BootstrapSpec {\n            nonce: self.nonce,\n            uid: self.policy.lmkd_uid,\n            gid: self.policy.lmkd_gid,\n            lmkd_sha256: self.lmkd.digest(),\n            init_sha256: hello.executable.digest(),\n        };\n        let handles: [BorrowedFd<'_>; 16] = std::array::from_fn(|index| match index {\n            0 => domain.android().as_fd(),\n            1 => self.owner.fd().as_fd(),\n            2 => hello.process.fd().as_fd(),\n            3 => self.lmkd.file().as_fd(),\n            4 => hello.executable.file().as_fd(),\n            5 => self.directory.as_fd(),\n            i => hello.namespaces[i - 6].as_fd(),\n        });\n        let executable = relay(ExecutablePin::from_lifecycle(\n            self.broker_image.file().try_clone()?,\n            self.broker_image.digest(),\n        ))?;\n        let host = self\n            .host\n            .take()\n            .ok_or_else(|| error(\"host origin token already consumed\"))?;\n        // spawn returns actual Child ownership before any protocol I/O.\n        self.broker = Some(relay(LifecycleBroker::spawn_holding_in_context(\n            host, executable, spec, &handles,\n        ))?);\n        self.initialize_started = true;\n        let broker = self.broker.as_mut().expect(\"retained real broker\");\n        let ready = relay(broker.initialize())?.clone();\n        self.audit.record(relay(broker.process_observation()).map(|process| Event::BrokerReady {\n            process: process.into(), status: (&ready).into(),\n        }));\n        self.endpoint = Some(endpoint_proof(\n            &self.directory,\n            &self.nonce,\n            &ready,\n            &self.owner,\n            &hello.process,\n        )?);\n        self.peer.commit(\n            hello,\n            &self.owner,\n            &domain,\n            &self.policy,\n            &self.barrier,\n            &ready,\n            &self.endpoint.as_ref().expect(\"held endpoint proof\").socket,\n            &self.cancel.0,\n            &mut || relay(broker.ready_for_init_commit()),\n            &self.audit,\n        )?;\n        self.phase.store(COMMITTED, Ordering::Release);\n        // Enrollment has a finite window separate from the constructor's\n        // handshake. Values come from the explicit cell entry policy.\n        let enrollment_deadline =\n            Instant::now() + Duration::from_millis(self.policy.entry_timeout_ms as u64);\n        let mut enrolled = false;\n        loop {\n            if self.cancel.requested()? {\n                return Ok(());\n            }\n            self.owner.live()?;\n            hello.process.live()?;\n            domain.validate()?;\n            if relay(broker.progress_available())? {\n                let status = relay(broker.receive_progress(Duration::from_secs(1)))?;\n                match status.state {\n                    BootstrapState::Active if status.granted && !status.faulted => {\n                        enrolled = true;\n                        self.phase.store(ACTIVE, Ordering::Release);\n                        self.audit.record(Ok(Event::BrokerActive { status: status.into() }));\n                    }\n                    BootstrapState::Retired => {\n                        return Err(error(\n                            \"real broker retired; complete old cell recovery is required\",\n                        ));\n                    }\n                    _ => return Err(error(\"unexpected broker progress after init release\")),\n                }\n            }\n            if !enrolled && Instant::now() >= enrollment_deadline {\n                return Err(error(\n                    \"native LMKD did not enroll before its finite startup deadline\",\n                ));\n            }\n            std::thread::sleep(Duration::from_millis(50));\n        }\n    }\n    fn retire_generation(&mut self) -> io::Result<()> {\n        // Preserve the first retirement failure, while still terminating the\n        // exact owned processes. No missing receipt is replaced by exit alone.\n        let mut failure = None;\n        if let Some(broker) = self.broker.as_mut() {\n            let result = if self.initialize_started {\n                match relay(broker.retire(MAX_LIFECYCLE_IO_TIMEOUT)) {\n                    Ok(true) => Ok(()),\n                    Ok(false) => Err(error(\"broker retirement remains incomplete\")),\n                    Err(e) => Err(e),\n                }\n            } else {\n                relay(broker.abort_before_initialize())\n            };\n            if let Err(e) = result {\n                failure = Some(e);\n                // Revokes the owned transport but explicitly supplies no\n                // retirement receipt. The broker handle remains in Session.\n                let _ = relay(broker.revoke_unproven_control());\n            } else if self.initialize_started {\n                self.audit.record(RetirementRecord::capture(broker).map(|receipt| Event::BrokerRetired { receipt }));\n            }\n        }\n        if let Err(e) = self.stop_exact_processes() {\n            if failure.is_none() {\n                failure = Some(e);\n            }\n        }\n        if let Some(e) = failure {\n            return Err(e);\n        }\n        if self.hello.is_none() {\n            return Err(error(\n                \"no authenticated actual init peer; generation remains persistently closed\",\n            ));\n        }\n        self.audit.record(Ok(Event::ProcessesDead));\n        if self\n            .broker\n            .as_ref()\n            .is_some_and(|b| !b.retirement_complete())\n            || self.endpoint.is_none()\n        {\n            return Err(error(\n                \"generation lacks a complete broker/endpoint retirement chain\",\n            ));\n        }\n        self.domain\n            .as_ref()\n            .ok_or_else(|| error(\"retirement domain missing\"))?\n            .prove_empty()?;\n        self.audit.record(Ok(Event::DomainEmpty));\n        // Release all init root/mount/namespace file references after its\n        // exact death. Keep the pidfd as final immutable retirement evidence.\n        let Hello { process, .. } = self.hello.take().expect(\"checked actual init\");\n        self.retired_init = Some(process);\n        self.domain = None;\n        Ok(())\n    }\n    fn stop_exact_processes(&self) -> io::Result<()> {\n        self.owner.signal(libc::SIGTERM)?;\n        let deadline = Instant::now() + Duration::from_secs(2);\n        loop {\n            let init_dead = match self.hello.as_ref() {\n                Some(h) => h.process.dead()?,\n                None => true,\n            };\n            if self.owner.dead()? && init_dead {\n                return Ok(());\n            }\n            if Instant::now() >= deadline {\n                break;\n            }\n            std::thread::sleep(Duration::from_millis(10));\n        }\n        if let Some(hello) = self.hello.as_ref() {\n            hello.process.signal(libc::SIGKILL)?;\n        }\n        self.owner.signal(libc::SIGKILL)?;\n        if let Some(hello) = self.hello.as_ref() {\n            hello.process.require_dead(Duration::from_secs(2))?;\n        }\n        self.owner.require_dead(Duration::from_secs(2))\n    }\n    fn prove_retired(&self) -> io::Result<()> {\n        if let Some(retirement) = &self.retirement_error {\n            let first = self\n                .reason\n                .as_deref()\n                .unwrap_or(\"lifecycle retirement requested\");\n            return Err(io::Error::other(format!(\n                \"{first}; retirement remains incomplete: {retirement}\"\n            )));\n        }\n        if self.phase.load(Ordering::Acquire) != RETIRED\n            || self.domain.is_some()\n            || self.hello.is_some()\n            || self\n                .broker\n                .as_ref()\n                .is_none_or(|b| !b.retirement_complete())\n        {\n            return Err(error(\"worker has no complete generation retirement proof\"));\n        }\n        self.owner.require_dead(Duration::ZERO)?;\n        self.retired_init\n            .as_ref()\n            .ok_or_else(|| error(\"retired init pidfd missing\"))?\n            .require_dead(Duration::ZERO)\n    }\n}\n\npub(crate) struct Owner {\n    audit: Audit,\n    policy: PressureRelaySpec,\n    nonce: [u8; 32],\n    canonical_spec: [u8; 32],\n    runtime: PathBuf,\n    claim: Claim,\n    domain: Arc<Domain>,\n    endpoint: Option<Endpoint>,\n    host: Option<HostContext>,\n    entry_image: Artifact,\n    broker_image: Option<Artifact>,\n    barrier_image: Option<Artifact>,\n    lmkd_image: Option<Artifact>,\n    channel_host: Option<File>,\n    channel_child: Option<File>,\n    transfers: Option<[File; 3]>,\n    cancel: Arc<Cancel>,\n    phase: Arc<AtomicU8>,\n    process: Option<Process>,\n    worker: Option<Worker<Session>>,\n    failure: Option<String>,\n    termination_reason: Option<String>,\n    resources_removed: bool,\n    released: bool,\n}\nimpl Owner {\n    /// All read-only image/ABI checks precede the durable claim. The claim\n    /// precedes the first finite-domain/runtime/network resource mutation.\n    pub(crate) fn prepare(spec: &CellSpec, entry_path: &Path) -> io::Result<Option<Self>> {\n        let Some(policy) = spec.pressure_relay.as_ref() else {\n            return Ok(None);\n        };\n        if entry_path != policy.entry_supervisor.path {\n            return Err(error(\n                \"configured entry path differs from the explicit relay package\",\n            ));\n        }\n        let entry_image = Artifact::open(&policy.entry_supervisor, true)?;\n        query_entry_abi(&entry_image)?;\n        let broker_image = Artifact::open(&policy.broker, true)?;\n        let barrier_image = Artifact::open(&policy.init_barrier, false)?;\n        let lmkd_image = Artifact::open(&policy.lmkd, true)?;\n        let host = relay(HostContext::open())?;\n        let nonce = PressureRelaySpec::nonce()?;\n        let canonical_spec = entry::spec_digest(spec)?;\n        let audit = Audit::new(&nonce, &canonical_spec, spec.host_uid, policy);\n        let record = serde_json::to_vec(&serde_json::json!({\"schema\":1,\"entry_abi\":entry::ABI,\n            \"host_uid\":spec.host_uid,\"nonce\":policy::hex(&nonce),\"canonical_spec_sha256\":policy::hex(&canonical_spec),\n            \"runtime\":spec.runtime_dir,\"domain_name\":format!(\"g-{}\",policy::hex(&nonce)),\"pressure_relay\":policy}))\n            .map_err(io::Error::other)?;\n        let store =\n            Store::production(true)?.ok_or_else(|| error(\"generation store unavailable\"))?;\n        let claim = store.claim(spec.host_uid, &record)?;\n        let domain = Arc::new(Domain::create(policy, &nonce)?);\n        audit.record(Ok(Event::Prepared { domain: domain.identity().into() }));\n        let (channel_host, channel_child) = init_peer::pair()?;\n        Ok(Some(Self {\n            audit,\n            policy: policy.clone(),\n            nonce,\n            canonical_spec,\n            runtime: spec.runtime_dir.clone(),\n            claim,\n            domain,\n            endpoint: None,\n            host: Some(host),\n            entry_image,\n            broker_image: Some(broker_image),\n            barrier_image: Some(barrier_image),\n            lmkd_image: Some(lmkd_image),\n            channel_host: Some(channel_host),\n            channel_child: Some(channel_child),\n            transfers: None,\n            cancel: Arc::new(Cancel::new()?),\n            phase: Arc::new(AtomicU8::new(WAITING)),\n            process: None,\n            worker: None,\n            failure: None,\n            termination_reason: None,\n            resources_removed: false,\n            released: false,\n        }))\n    }\n    pub(crate) fn prepare_endpoint(&mut self) -> io::Result<()> {\n        if self.endpoint.is_some() {\n            return Err(error(\"generation endpoint is one attempt\"));\n        }\n        self.endpoint = Some(Endpoint::create(&self.runtime, &self.nonce)?);\n        Ok(())\n    }\n    /// The returned path resolves only inside the spawned child's FD table.\n    pub(crate) fn entry_path(&self) -> PathBuf {\n        PathBuf::from(format!(\"/proc/self/fd/{}\", init_peer::ENTRY_FD))\n    }\n    pub(crate) fn configure_command(&mut self, command: &mut Command) -> io::Result<()> {\n        if self.transfers.is_some() || self.process.is_some() {\n            return Err(error(\"generation spawn is one attempt\"));\n        }\n        self.domain.validate()?;\n        self.entry_image.validate(true)?;\n        self.endpoint\n            .as_ref()\n            .ok_or_else(|| error(\"private endpoint not provisioned\"))?\n            .validate()?;\n        let sources = [\n            self.channel_child\n                .as_ref()\n                .ok_or_else(|| error(\"child init channel missing\"))?\n                .as_raw_fd(),\n            self.domain.android().as_raw_fd(),\n            self.entry_image.file().as_raw_fd(),\n        ];\n        let pinned = sources.map(|fd| {\n            let raw = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 256) };\n            if raw < 0 {\n                Err(io::Error::last_os_error())\n            } else {\n                Ok(unsafe { File::from_raw_fd(raw) })\n            }\n        });\n        let [a, b, c] = pinned;\n        self.transfers = Some([a?, b?, c?]);\n        let raw = self\n            .transfers\n            .as_ref()\n            .expect(\"retained transfers\")\n            .each_ref()\n            .map(AsRawFd::as_raw_fd);\n        let parent = unsafe { libc::getpid() };\n        entry::clean_command_environment(command);\n        command\n            .env(entry::ENTRY_ENV[0], entry::ABI)\n            .env(entry::ENTRY_ENV[1], policy::hex(&self.nonce))\n            .env(entry::ENTRY_ENV[2], policy::hex(&self.canonical_spec));\n        unsafe {\n            command.pre_exec(move || {\n                if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0\n                    || libc::getppid() != parent\n                {\n                    return Err(io::Error::other(\n                        \"relay daemon disappeared before namespace owner exec\",\n                    ));\n                }\n                for (source, target) in raw.into_iter().zip([\n                    init_peer::CONTROL_FD,\n                    init_peer::DOMAIN_FD,\n                    init_peer::ENTRY_FD,\n                ]) {\n                    if libc::dup2(source, target) < 0 || libc::fcntl(target, libc::F_SETFD, 0) < 0 {\n                        return Err(io::Error::last_os_error());\n                    }\n                }\n                // This is the exact still-unshared outer Child, not a PID supplied\n                // by a request. Its inherited pidfd closes the PID1 pre-arm race.\n                let owned = libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) as i32;\n                if owned < 0 {\n                    return Err(io::Error::last_os_error());\n                }\n                let result = if owned == init_peer::OWNER_FD {\n                    0\n                } else {\n                    libc::dup2(owned, init_peer::OWNER_FD)\n                };\n                if owned != init_peer::OWNER_FD {\n                    libc::close(owned);\n                }\n                if result < 0 || libc::fcntl(init_peer::OWNER_FD, libc::F_SETFD, 0) < 0 {\n                    return Err(io::Error::last_os_error());\n                }\n                Ok(())\n            });\n        }\n        Ok(())\n    }\n    /// Called only after DevelopmentCell already owns Child/network/self.\n    /// Every failure is stored in that Cell; no post-spawn error drops it.\n    pub(crate) fn attach(&mut self, child: &mut Child) {\n        self.transfers = None;\n        self.channel_child = None;\n        let result = self.attach_inner(child);\n        if let Err(error) = result {\n            self.audit.failure(FailureOrigin::Admission, &error.to_string());\n            self.failure = Some(error.to_string());\n            self.phase.store(FAILED, Ordering::Release);\n            self.channel_host = None;\n            let _ = self.cancel.request();\n        }\n    }\n    fn attach_inner(&mut self, child: &mut Child) -> io::Result<()> {\n        if self.worker.is_some() || self.process.is_some() {\n            return Err(error(\"generation child attached twice\"));\n        }\n        self.process = Some(Process::from_child(child)?);\n        self.audit.record(self.process.as_ref().expect(\"retained exact owner\").observation()\n            .map(|process| Event::OwnerAttached { process }));\n        let process = self\n            .process\n            .as_ref()\n            .expect(\"retained exact owner\")\n            .try_clone()?;\n        let session = Session {\n            audit: self.audit.clone(),\n            host: self.host.take(),\n            owner: process,\n            domain: Some(Arc::clone(&self.domain)),\n            peer: InitPeer::new(\n                self.channel_host\n                    .take()\n                    .ok_or_else(|| error(\"host init channel missing\"))?,\n                self.nonce,\n                &self.policy,\n            )?,\n            policy: self.policy.clone(),\n            nonce: self.nonce,\n            directory: self\n                .endpoint\n                .as_ref()\n                .ok_or_else(|| error(\"endpoint missing at attach\"))?\n                .directory\n                .try_clone()?,\n            barrier: self\n                .barrier_image\n                .take()\n                .ok_or_else(|| error(\"barrier image already consumed\"))?,\n            lmkd: self\n                .lmkd_image\n                .take()\n                .ok_or_else(|| error(\"LMKD image already consumed\"))?,\n            broker_image: self\n                .broker_image\n                .take()\n                .ok_or_else(|| error(\"broker image already consumed\"))?,\n            cancel: Arc::clone(&self.cancel),\n            phase: Arc::clone(&self.phase),\n            hello: None,\n            broker: None,\n            initialize_started: false,\n            endpoint: None,\n            retired_init: None,\n            reason: None,\n            retirement_error: None,\n        };\n        self.worker = Some(Worker::new(session));\n        self.worker\n            .as_mut()\n            .expect(\"retained worker\")\n            .start(Session::run)\n    }\n    pub(crate) fn poll(&self) -> io::Result<()> {\n        if let Some(reason) = &self.failure {\n            return Err(io::Error::other(format!(\n                \"relay generation admission failed: {reason}\"\n            )));\n        }\n        if self.phase.load(Ordering::Acquire) == FAILED {\n            return Err(error(\n                \"relay worker retained an incomplete generation retirement\",\n            ));\n        }\n        if self.worker.as_ref().is_some_and(Worker::finished)\n            && self.phase.load(Ordering::Acquire) != RETIRED\n        {\n            return Err(error(\n                \"relay worker ended without complete generation retirement\",\n            ));\n        }\n        Ok(())\n    }\n    pub(crate) fn request_stop(&self) -> io::Result<()> {\n        self.cancel.request()\n    }\n    pub(crate) fn audit(&self) -> RelayLifecycleAudit { self.audit.snapshot() }\n    pub(crate) fn record_cleanup_failure(&self, message: &str) {\n        self.audit.failure(FailureOrigin::Cleanup, message);\n    }\n    pub(crate) fn termination_reason(&self) -> Option<&str> {\n        self.termination_reason.as_deref()\n    }\n    pub(crate) fn enrolled(&self) -> bool {\n        // ACTIVE can only follow the actual init COMMIT/DONE and the exact\n        // broker's authenticated grant-delivery status. It proves no PSI event.\n        self.failure.is_none() && self.phase.load(Ordering::Acquire) == ACTIVE\n    }\n    pub(crate) fn retire_before_network(&mut self, child: &mut Child) -> io::Result<()> {\n        if self.resources_removed {\n            return Ok(());\n        }\n        self.cancel.request()?;\n        if child.try_wait()?.is_none() {\n            return Err(error(\n                \"namespace Child has not been reaped before relay cleanup\",\n            ));\n        }\n        if let Some(reason) = &self.failure {\n            return Err(io::Error::other(format!(\n                \"relay generation is persistently closed: {reason}\"\n            )));\n        }\n        let worker = self\n            .worker\n            .as_mut()\n            .ok_or_else(|| error(\"actual lifecycle worker missing\"))?;\n        // A bounded join timeout retains its real handle and every resource;\n        // it cannot make the next poll or stop return a synthetic success.\n        worker.join(Duration::from_secs(10))?;\n        let resources = worker.resources()?;\n        resources.prove_retired()?;\n        // Snapshot the original run failure while ownership is still held.\n        // Releasing resources successfully must not erase why the cell died.\n        self.termination_reason = resources.reason.clone();\n        let process = self\n            .process\n            .as_ref()\n            .ok_or_else(|| error(\"owned namespace process pin missing\"))?;\n        if process.pid() as u32 != child.id() {\n            return Err(error(\"cleanup Child differs from retained owner\"));\n        }\n        process.require_dead(Duration::ZERO)?;\n        let domain = Arc::get_mut(&mut self.domain)\n            .ok_or_else(|| error(\"worker still owns a live domain reference\"))?;\n        domain.remove_after(|| resources.prove_retired())?;\n        let endpoint = self\n            .endpoint\n            .as_mut()\n            .ok_or_else(|| error(\"retirement endpoint missing\"))?;\n        endpoint.remove_after(\n            resources\n                .endpoint\n                .as_ref()\n                .ok_or_else(|| error(\"retired endpoint inode proof missing\"))?,\n            || resources.prove_retired(),\n        )?;\n        self.resources_removed = true;\n        self.audit.record(Ok(Event::ResourcesRemoved));\n        Ok(())\n    }\n    /// Only after the exact network owner and entire runtime have cleaned up.\n    /// Marker unlink is the final fallible operation in successful retirement.\n    pub(crate) fn finish_after_runtime(&mut self, child: &mut Child) -> io::Result<()> {\n        if self.released {\n            return Ok(());\n        }\n        if !self.resources_removed || self.failure.is_some() {\n            return Err(error(\"generation resources are not retired\"));\n        }\n        let resources = self\n            .worker\n            .as_ref()\n            .ok_or_else(|| error(\"retired worker missing\"))?\n            .resources()?;\n        let domain = &self.domain;\n        let endpoint = self\n            .endpoint\n            .as_ref()\n            .ok_or_else(|| error(\"retired endpoint missing\"))?;\n        let owner = self\n            .process\n            .as_ref()\n            .ok_or_else(|| error(\"retired owner missing\"))?;\n        let runtime = &self.runtime;\n        self.claim.release_after(|| {\n            resources.prove_retired()?;\n            owner.require_dead(Duration::ZERO)?;\n            if child.id() != owner.pid() as u32 || child.try_wait()?.is_none() {\n                return Err(error(\"exact Child reap proof changed\"));\n            }\n            domain.prove_removed()?;\n            endpoint.prove_removed()?;\n            match std::fs::symlink_metadata(runtime) {\n                Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),\n                _ => Err(error(\"runtime still exists at final generation release\")),\n            }\n        })?;\n        self.released = true;\n        self.audit.record(Ok(Event::ClaimReleased));\n        Ok(())\n    }\n}\nimpl Drop for Owner {\n    fn drop(&mut self) {\n        if !self.released {\n            let _ = self.cancel.request();\n        }\n        // The persistent claim deliberately survives dropping this owner.\n    }\n}\n\nfn query_entry_abi(executable: &Artifact) -> io::Result<()> {\n    executable.validate(true)?;\n    let mut command = Command::new(format!(\"/proc/self/fd/{}\", executable.file().as_raw_fd()));\n    command\n        .arg(\"relay-entry-abi\")\n        .stdin(Stdio::null())\n        .stdout(Stdio::piped())\n        .stderr(Stdio::null());\n    entry::clean_command_environment(&mut command);\n    let parent = unsafe { libc::getpid() };\n    unsafe {\n        command.pre_exec(move || {\n            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0 || libc::getppid() != parent {\n                return Err(io::Error::other(\"entry ABI parent disappeared\"));\n            }\n            Ok(())\n        });\n    }\n    let mut child = command.spawn()?;\n    let deadline = Instant::now() + Duration::from_secs(2);\n    let status = loop {\n        match child.try_wait() {\n            Ok(Some(status)) => break Ok(status),\n            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(5)),\n            Ok(None) => break Err(error(\"entry ABI query timed out\")),\n            Err(e) => break Err(e),\n        }\n    };\n    if status.is_err() {\n        let _ = child.kill();\n        let _ = child.wait();\n    }\n    let status = status?;\n    let mut output = child\n        .stdout\n        .take()\n        .ok_or_else(|| error(\"entry ABI output missing\"))?;\n    let flags = unsafe { libc::fcntl(output.as_raw_fd(), libc::F_GETFL) };\n    if flags < 0\n        || unsafe { libc::fcntl(output.as_raw_fd(), libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    let mut bytes = Vec::new();\n    output.by_ref().take(129).read_to_end(&mut bytes)?;\n    if !status.success() || bytes != format!(\"{}\\n\", entry::ABI).as_bytes() {\n        return Err(error(\"paired entry ABI is unavailable or differs\"));\n    }\n    executable.validate(true)\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    #[test]\n    fn cancellation_remains_latched_across_repeated_stop_requests() {\n        let cancel = Cancel::new().unwrap();\n        assert!(!cancel.requested().unwrap());\n        cancel.request().unwrap();\n        cancel.request().unwrap();\n        assert!(cancel.requested().unwrap());\n        assert!(cancel.requested().unwrap());\n        let flags = unsafe { libc::fcntl(cancel.0.as_raw_fd(), libc::F_GETFD) };\n        assert_ne!(flags & libc::FD_CLOEXEC, 0);\n    }\n    #[test]\n    fn altered_broker_marker_cannot_authorize_directory_cleanup() {\n        let mut file = tempfile::tempfile().unwrap();\n        use std::io::Write;\n        file.write_all(&[7; 104]).unwrap();\n        validate_marker_bytes(&file, &[7; 104]).unwrap();\n        assert!(validate_marker_bytes(&file, &[8; 104]).is_err());\n        // Deliberately no source-side UID or mode relaxation: a normal\n        // caller-owned temporary file cannot become production authority.\n        file.set_len(103).unwrap();\n        assert!(validate_marker_bytes(&file, &[7; 104]).is_err());\n    }\n}\n"
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
      "bytes": 44547,
      "sha256": "f2fd8a952171809256dd56ef75ff2ffe358b7e3c21279583d83ea20aea812c96"
    },
    "runtime/droidloom-pressure-relay/src/lifecycle_bootstrap.rs": {
      "bytes": 54968,
      "sha256": "3f3f7cc1accb8921b0248adb3257e3737879e90b10bf377231389d5eb18453c1"
    },
    "runtime/droidloom-pressure-relay/src/lifecycle_relay.rs": {
      "bytes": 16229,
      "sha256": "29516250e21cfa6c8bdeedd676155fe34d53c608021e070a5c03635bba13950a"
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
      "bytes": 95133,
      "sha256": "f73b823d53e7bd6a6daca9fff34f7c1ff5844ab39ba55171384414d6d58544c4"
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
      "bytes": 20910,
      "sha256": "ec021636841d88bb2cd52981c0143685593e87750b97073af99a7f3ea4f8038a"
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
      "bytes": 39599,
      "sha256": "4011111e9e1a70dbcec449f1aa961204a8ab568671de29a4c7134b49d2c8ed92"
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
  "revision": "producer10-broker-holding01",
  "schema": 1,
  "source_manifest_sha256": "019b34bc655bf76235339b533917d523fd2e5db3355214e5a5466e6a61ee3068"
}
'''))
