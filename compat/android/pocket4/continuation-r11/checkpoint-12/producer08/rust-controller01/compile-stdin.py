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

CONTROL_REVISION = "producer08-projection01"
BASE = Path("/home/alex/work/pocket4-supervisor-lmkd-audit-r11-build-07-02")
SOURCE = BASE / "candidate"
OUT = Path("/home/alex/work/pocket4-supervisor-lmkd-projection-r11-build-08-01")
CANDIDATE = OUT / "candidate"
TARGET = OUT / "target"
CARGO = "/home/alex/.cargo/bin/cargo"
PRIOR_RECEIPT = BASE / "compile-result.json"
PRIOR_RECEIPT_SHA = "d5ead1b1e83447a4037a07262830fc2b8ad807e004c3dbca95ec0051b3e0fbcf"
PRIOR_INVENTORY_SHA = "2cc80213dd99a6b7ea4211f4bead6b9f6e15cfe4b7066636929435422bde958f"
ORIGINAL_DIFF_SHA = "0cbe37b1625edeef8c88513025573d4a24a8bac6af442a42b1ca10aa30211233"
EXACT_OVERLAY = {
    'runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs': (28125, 'eb217e5f2d2a3ff34468d67bc0965b3b0196af08836690792d315c8c4fea6dd2'),
    'runtime/droidloom-supervisor/src/relay_lifecycle/init_peer.rs': (28125, 'd974d02115f686c8cd28a294e9e35428c23d8a54ec0b3bd7ea1398e3a74c0d6c'),
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
         "fc6b1699bb50f741a7483c165095393dce44c285186408b25a7c3938f34fe0a6",
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
        need(sha(prior_raw) == PRIOR_RECEIPT_SHA, "actual producer07 audit02 receipt hash differs")
        prior = json.loads(prior_raw)
        need(prior["success"] is True and prior["compile_only"] is True and
             prior["revision"] == "producer07-audit02" and
             prior["candidate"] == str(SOURCE) and
             prior["inputs_before"] == cfg["preimage"] and
             prior["inputs_after"] == cfg["preimage"] and
             prior["all_source_inventory_before_sha256"] == PRIOR_INVENTORY_SHA and
             prior["all_source_inventory_after_sha256"] == PRIOR_INVENTORY_SHA,
             "actual producer07 audit02 receipt/source binding differs")
        put(OUT / "producer07-audit02-actual-compile-result.json", prior_raw)
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
  "original_diff_sha256": "0cbe37b1625edeef8c88513025573d4a24a8bac6af442a42b1ca10aa30211233",
  "overlays": {
    "runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs": {
      "bytes": 28125,
      "sha256": "eb217e5f2d2a3ff34468d67bc0965b3b0196af08836690792d315c8c4fea6dd2",
      "text": "//! Single-threaded namespace-entry half of the real init barrier.\n//!\n//! All inherited capabilities are sealed before a helper can execute. Only\n//! the constructor channel is deliberately inherited by the final init exec;\n//! the constructor closes it before init can start any service.\nuse super::capability::{self, Artifact};\nuse super::domain::{self, Identity};\nuse super::init_peer;\nuse super::policy::{self, PressureRelaySpec};\nuse crate::CellSpec;\nuse sha2::{Digest, Sha256};\nuse std::ffi::{CString, OsString};\nuse std::fs::File;\nuse std::io::{self, Write};\nuse std::os::fd::{AsRawFd, FromRawFd, RawFd};\nuse std::os::unix::fs::{FileExt, MetadataExt};\nuse std::os::unix::process::CommandExt;\nuse std::path::Path;\nuse std::process::Command;\n\n/// Exact pure-CLI pairing value required before private relay entry may spawn.\npub const ABI: &str = \"droidloom-relay-entry-v2\";\npub(crate) const ENTRY_ENV: [&str; 3] = [\n    \"DROIDLOOM_RELAY_ENTRY_ABI\",\n    \"DROIDLOOM_RELAY_ENTRY_NONCE\",\n    \"DROIDLOOM_RELAY_ENTRY_SPEC_SHA256\",\n];\nconst INIT_ENV: [&str; 5] = [\n    \"DROIDLOOM_INIT_RELAY_REQUIRED\",\n    \"DROIDLOOM_INIT_RELAY_ABI\",\n    \"DROIDLOOM_INIT_RELAY_FD\",\n    \"DROIDLOOM_INIT_RELAY_NONCE\",\n    \"DROIDLOOM_INIT_RELAY_TIMEOUT_MS\",\n];\nconst FIXED: [RawFd; 4] = [\n    init_peer::CONTROL_FD,\n    init_peer::DOMAIN_FD,\n    init_peer::OWNER_FD,\n    init_peer::ENTRY_FD,\n];\nconst BOOTSTRAP: &str = \"droidloom/lmkd-bootstrap\";\nconst INIT_LINKER: &str = \"/system/bin/bootstrap/linker64\";\nfn error(message: &'static str) -> io::Error {\n    domain::error(message)\n}\n\npub(crate) fn spec_digest(spec: &CellSpec) -> io::Result<[u8; 32]> {\n    let bytes = serde_json::to_vec(spec).map_err(io::Error::other)?;\n    Ok(Sha256::digest(bytes).into())\n}\npub(crate) fn clean_command_environment(command: &mut Command) {\n    for key in ENTRY_ENV.into_iter().chain(INIT_ENV) {\n        command.env_remove(key);\n    }\n}\nfn close_on_exec(fd: RawFd, enabled: bool) -> io::Result<()> {\n    let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };\n    if flags < 0 {\n        return Err(io::Error::last_os_error());\n    }\n    let flags = if enabled {\n        flags | libc::FD_CLOEXEC\n    } else {\n        flags & !libc::FD_CLOEXEC\n    };\n    if unsafe { libc::fcntl(fd, libc::F_SETFD, flags) } < 0 {\n        return Err(io::Error::last_os_error());\n    }\n    Ok(())\n}\nfn pidfd_alive(fd: &File) -> io::Result<()> {\n    let path = format!(\"/proc/self/fdinfo/{}\", fd.as_raw_fd());\n    let text = std::fs::read_to_string(path)?;\n    // The parent's PID is deliberately 0 in this child PID namespace. A Pid\n    // field plus the kernel pidfd poll semantics establishes descriptor type;\n    // no positive numeric PID is used to open, signal, or authenticate a peer.\n    let mut fields = text.lines().filter_map(|line| line.strip_prefix(\"Pid:\\t\"));\n    let pid: i64 = fields\n        .next()\n        .ok_or_else(|| error(\"entry owner FD is not a pidfd\"))?\n        .trim()\n        .parse()\n        .map_err(|_| error(\"entry owner pidfd identity malformed\"))?;\n    if pid < 0 || fields.next().is_some() {\n        return Err(error(\"entry owner pidfd retired\"));\n    }\n    let mut poll = libc::pollfd {\n        fd: fd.as_raw_fd(),\n        events: libc::POLLIN,\n        revents: 0,\n    };\n    let count = unsafe { libc::poll(&mut poll, 1, 0) };\n    if count < 0 {\n        return Err(io::Error::last_os_error());\n    }\n    if count != 0 || poll.revents != 0 {\n        return Err(error(\"entry owner is no longer alive\"));\n    }\n    Ok(())\n}\nfn require_control(fd: &File) -> io::Result<()> {\n    let mut kind: libc::c_int = 0;\n    let mut length = std::mem::size_of_val(&kind) as libc::socklen_t;\n    if unsafe {\n        libc::getsockopt(\n            fd.as_raw_fd(),\n            libc::SOL_SOCKET,\n            libc::SO_TYPE,\n            (&mut kind as *mut libc::c_int).cast(),\n            &mut length,\n        )\n    } < 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    if kind != libc::SOCK_SEQPACKET || length as usize != std::mem::size_of_val(&kind) {\n        return Err(error(\"entry control is not a seqpacket channel\"));\n    }\n    let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFL) };\n    if flags < 0 || flags & libc::O_NONBLOCK == 0 {\n        return Err(error(\"entry control is not nonblocking\"));\n    }\n    let mut peer: libc::ucred = unsafe { std::mem::zeroed() };\n    let mut size = std::mem::size_of_val(&peer) as libc::socklen_t;\n    if unsafe {\n        libc::getsockopt(\n            fd.as_raw_fd(),\n            libc::SOL_SOCKET,\n            libc::SO_PEERCRED,\n            (&mut peer as *mut libc::ucred).cast(),\n            &mut size,\n        )\n    } < 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    if peer.uid != 0\n        || peer.gid != 0\n        || peer.pid < 0\n        || size as usize != std::mem::size_of_val(&peer)\n    {\n        return Err(error(\"entry channel peer is not the root lifecycle owner\"));\n    }\n    Ok(())\n}\n\n/// Private fields make a partial inherited contract unusable by later phases.\npub(crate) struct Entry {\n    channel: File,\n    domain: File,\n    owner: File,\n    executable: Artifact,\n    policy: PressureRelaySpec,\n    nonce: [u8; 32],\n    domain_identity: Identity,\n    barrier: Artifact,\n    lmkd: Artifact,\n    prepared: bool,\n    sealed: bool,\n}\nimpl Entry {\n    /// This is the first operation in development-enter, before validation\n    /// helpers or any process spawn. Failure always terminates that entry.\n    pub(crate) fn receive(spec: &CellSpec) -> io::Result<Option<Self>> {\n        let env: Vec<Option<OsString>> = ENTRY_ENV.iter().map(std::env::var_os).collect();\n        let leaked_init = INIT_ENV.iter().any(|key| std::env::var_os(key).is_some());\n        let Some(policy) = spec.pressure_relay.as_ref() else {\n            if env.iter().any(Option::is_some) || leaked_init {\n                return Err(error(\"relay capability environment without relay policy\"));\n            }\n            return Ok(None);\n        };\n        // Seal every known descriptor even if the textual contract is bad.\n        // Do not construct owners until sealing has succeeded for all four.\n        for fd in FIXED {\n            close_on_exec(fd, true)?;\n        }\n        if leaked_init || env[0].as_deref() != Some(std::ffi::OsStr::new(ABI)) {\n            return Err(error(\"entry ABI or inherited init environment differs\"));\n        }\n        let nonce = policy::digest(\n            env[1]\n                .as_ref()\n                .and_then(|s| s.to_str())\n                .ok_or_else(|| error(\"entry nonce missing\"))?,\n        )\n        .map_err(error)?;\n        let declared = policy::digest(\n            env[2]\n                .as_ref()\n                .and_then(|s| s.to_str())\n                .ok_or_else(|| error(\"entry specification pin missing\"))?,\n        )\n        .map_err(error)?;\n        if declared != spec_digest(spec)? {\n            return Err(error(\"entry specification changed after host admission\"));\n        }\n        if unsafe { libc::getuid() } != 0\n            || unsafe { libc::geteuid() } != 0\n            || unsafe { libc::getgid() } != 0\n            || unsafe { libc::getegid() } != 0\n            || unsafe { libc::getpid() } != 1\n            || unsafe { libc::getppid() } != 0\n        {\n            return Err(error(\n                \"relay entry is not private root PID 1 with an outer owner\",\n            ));\n        }\n        // SAFETY: the private ABI transfers these four distinct inherited FDs\n        // exactly once; they have all just been sealed CLOEXEC.\n        let [channel, domain_fd, owner, executable] =\n            FIXED.map(|fd| unsafe { File::from_raw_fd(fd) });\n        if unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) } < 0 {\n            return Err(io::Error::last_os_error());\n        }\n        // The pidfd closes the race where the outside parent died before\n        // PR_SET_PDEATHSIG could be armed in this new PID namespace.\n        pidfd_alive(&owner)?;\n        require_control(&channel)?;\n        let executable = Artifact::from_file(\n            executable,\n            policy::digest(&policy.entry_supervisor.sha256).map_err(error)?,\n            true,\n        )?;\n        let actual = File::open(\"/proc/self/exe\")?;\n        if Identity::of(&actual)? != executable.identity()\n            || capability::hash(&actual)? != executable.digest()\n        {\n            return Err(error(\n                \"actual entry executable differs from inherited package pin\",\n            ));\n        }\n        let barrier = Artifact::open(&policy.init_barrier, false)?;\n        let lmkd = Artifact::open(&policy.lmkd, true)?;\n        let domain_identity = Identity::of(&domain_fd)?;\n        domain::enter_self(&domain_fd, policy)?;\n        pidfd_alive(&owner)?;\n        Ok(Some(Self {\n            channel,\n            domain: domain_fd,\n            owner,\n            executable,\n            policy: policy.clone(),\n            nonce,\n            domain_identity,\n            barrier,\n            lmkd,\n            prepared: false,\n            sealed: false,\n        }))\n    }\n\n    /// Runs after the normal image overlays, but before pivot_root or init.\n    pub(crate) fn prepare_image(&mut self, root_path: &Path) -> io::Result<()> {\n        if self.prepared || self.sealed {\n            return Err(error(\"relay image preparation is a single attempt\"));\n        }\n        self.sealed = true; // Any partial mount failure permanently closes this entry.\n        pidfd_alive(&self.owner)?;\n        self.executable.validate(true)?;\n        self.barrier.validate(true)?;\n        self.lmkd.validate(true)?;\n        let root = domain::directory(root_path)?;\n        let init = Artifact::from_file(\n            domain::beneath(&root, \"system/bin/init\", libc::O_RDONLY)?,\n            policy::digest(&self.policy.init_sha256).map_err(error)?,\n            true,\n        )?;\n        require_init_alias(&root, init.identity())?;\n        require_interpreter(init.file(), INIT_LINKER)?;\n        let linker = Artifact::from_file(\n            domain::beneath(&root, INIT_LINKER.trim_start_matches('/'), libc::O_RDONLY)?,\n            policy::digest(&self.policy.init_linker_sha256).map_err(error)?,\n            true,\n        )?;\n        let compat = Artifact::from_file(\n            domain::beneath(\n                &root,\n                init_peer::COMPAT.trim_start_matches('/'),\n                libc::O_RDONLY,\n            )?,\n            policy::digest(&self.policy.compat_preload_sha256).map_err(error)?,\n            false,\n        )?;\n        let old_rc = Artifact::from_file(\n            domain::beneath(&root, \"system/etc/init/lmkd.rc\", libc::O_RDONLY)?,\n            policy::digest(&self.policy.lmkd_rc_sha256).map_err(error)?,\n            false,\n        )?;\n        let droidloom = make_parent(&root, \"droidloom\")?;\n        if unsafe { libc::mkdirat(droidloom.as_raw_fd(), c\"lmkd-bootstrap\".as_ptr(), 0o755) } != 0 {\n            return Err(io::Error::last_os_error());\n        }\n        let directory = domain::named(\n            &droidloom,\n            \"lmkd-bootstrap\",\n            libc::O_RDONLY | libc::O_DIRECTORY,\n        )?;\n        for (name, mode) in [(\"libdroidloom_init_relay.so\", 0o644), (\"lmkd\", 0o755)] {\n            drop(domain::at(\n                directory.as_raw_fd(),\n                &CString::new(name).expect(\"fixed name\"),\n                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL,\n                mode,\n            )?);\n        }\n        bind_readonly(\n            &root,\n            &format!(\"{BOOTSTRAP}/libdroidloom_init_relay.so\"),\n            self.barrier.file(),\n        )?;\n        bind_readonly(&root, &format!(\"{BOOTSTRAP}/lmkd\"), self.lmkd.file())?;\n        let mut generated = domain::at(\n            directory.as_raw_fd(),\n            c\"lmkd.rc\",\n            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL,\n            0o644,\n        )?;\n        generated.write_all(lmkd_rc(self.policy.lmkd_uid, self.policy.lmkd_gid).as_bytes())?;\n        generated.sync_all()?;\n        old_rc.validate(true)?;\n        bind_readonly(&root, \"system/etc/init/lmkd.rc\", &generated)?;\n        // Preserve the pre-existing loader/preload pair and a non-set-ID init\n        // on an explicit nosuid read-only bind before relying on PDEATHSIG.\n        bind_readonly(&root, \"system/bin/init\", init.file())?;\n        init.validate(true)?;\n        linker.validate(true)?;\n        compat.validate(true)?;\n        self.barrier.validate(true)?;\n        self.lmkd.validate(true)?;\n        self.prepared = true;\n        self.sealed = false;\n        pidfd_alive(&self.owner)\n    }\n\n    /// cpu_placement::prepare has sealed CLONE_NEWCGROUP immediately before\n    /// this call. Its v2 namespace root must be the exact inherited domain.\n    pub(crate) fn project_cgroup(&self, root: &Path) -> io::Result<()> {\n        if !self.prepared || self.sealed {\n            return Err(error(\"relay image is not prepared\"));\n        }\n        pidfd_alive(&self.owner)?;\n        if Identity::of(&self.domain)? != self.domain_identity {\n            return Err(error(\"held domain identity changed\"));\n        }\n        domain::mount_private_view(root, self.domain_identity)\n    }\n\n    /// Attach only to the final /init second_stage command. No ordinary\n    /// helper may inherit these capabilities or the private opt-in variables.\n    pub(crate) fn configure_init(&mut self, command: &mut Command) -> io::Result<()> {\n        if !self.prepared || self.sealed {\n            return Err(error(\"init release preparation reused or incomplete\"));\n        }\n        self.sealed = true;\n        require_init_command(command)?;\n        pidfd_alive(&self.owner)?;\n        self.barrier.validate(false)?;\n        self.lmkd.validate(false)?;\n        clean_command_environment(command);\n        command\n            .env(\"LD_PRELOAD\", init_peer::preload())\n            .env(INIT_ENV[0], \"1\")\n            .env(INIT_ENV[1], init_peer::INIT_ABI_TEXT)\n            .env(INIT_ENV[2], init_peer::CONTROL_FD.to_string())\n            .env(INIT_ENV[3], policy::hex(&self.nonce))\n            .env(INIT_ENV[4], self.policy.bootstrap_timeout_ms.to_string());\n        let control = self.channel.as_raw_fd();\n        let owner = self.owner.as_raw_fd();\n        // SAFETY: the entry is single-threaded. This pre-exec closure performs\n        // only async-signal-safe syscalls and changes no shared parent state.\n        unsafe {\n            command.pre_exec(move || {\n                // This is the final pre-exec callback, after any CPU placement\n                // callbacks. Keep the inherited parent-death link explicit at\n                // the exact direct, nonprivileged init exec boundary.\n                if libc::getuid() != 0\n                    || libc::geteuid() != 0\n                    || libc::getgid() != 0\n                    || libc::getegid() != 0\n                    || libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) < 0\n                {\n                    return Err(io::Error::other(\n                        \"init credentials or parent-death contract changed before exec\",\n                    ));\n                }\n                let mut poll = libc::pollfd {\n                    fd: owner,\n                    events: libc::POLLIN,\n                    revents: 0,\n                };\n                if libc::poll(&mut poll, 1, 0) != 0 || poll.revents != 0 {\n                    return Err(io::Error::other(\n                        \"entry owner died immediately before init exec\",\n                    ));\n                }\n                close_on_exec(control, false)\n            });\n        }\n        Ok(())\n    }\n}\n\nfn require_init_command(command: &Command) -> io::Result<()> {\n    let mut args = command.get_args();\n    if command.get_program() != std::ffi::OsStr::new(\"/init\")\n        || args.next() != Some(std::ffi::OsStr::new(\"second_stage\"))\n        || args.next().is_some()\n    {\n        return Err(error(\n            \"relay barrier requires a direct exact /init second_stage exec\",\n        ));\n    }\n    Ok(())\n}\n\nfn make_parent(root: &File, name: &str) -> io::Result<File> {\n    let name = CString::new(name).map_err(|_| error(\"invalid fixed parent\"))?;\n    if unsafe { libc::mkdirat(root.as_raw_fd(), name.as_ptr(), 0o755) } != 0 {\n        let e = io::Error::last_os_error();\n        if e.kind() != io::ErrorKind::AlreadyExists {\n            return Err(e);\n        }\n    }\n    let file = domain::at(\n        root.as_raw_fd(),\n        &name,\n        libc::O_RDONLY | libc::O_DIRECTORY,\n        0,\n    )?;\n    let m = file.metadata()?;\n    if m.uid() != 0 || m.mode() & 0o022 != 0 {\n        return Err(error(\"bootstrap parent is writable by another role\"));\n    }\n    Ok(file)\n}\nfn bind_readonly(root: &File, relative: &str, source: &File) -> io::Result<()> {\n    let target = domain::beneath(root, relative, libc::O_PATH)?;\n    if !target.metadata()?.is_file() || !source.metadata()?.is_file() {\n        return Err(error(\"readonly overlay is not a regular file\"));\n    }\n    let source_path =\n        CString::new(format!(\"/proc/self/fd/{}\", source.as_raw_fd())).expect(\"descriptor path\");\n    let target_path =\n        CString::new(format!(\"/proc/self/fd/{}\", target.as_raw_fd())).expect(\"descriptor path\");\n    if unsafe {\n        libc::mount(\n            source_path.as_ptr(),\n            target_path.as_ptr(),\n            std::ptr::null(),\n            libc::MS_BIND,\n            std::ptr::null(),\n        )\n    } != 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    // Reopen through the held root after binding: the old target FD still\n    // names the covered mount and cannot identify the newly attached mount.\n    let mounted = domain::beneath(root, relative, libc::O_PATH)?;\n    if Identity::of(&mounted)? != Identity::of(source)? {\n        return Err(error(\"readonly overlay identity mismatch\"));\n    }\n    let target_path =\n        CString::new(format!(\"/proc/self/fd/{}\", mounted.as_raw_fd())).expect(\"descriptor path\");\n    if unsafe {\n        libc::mount(\n            std::ptr::null(),\n            target_path.as_ptr(),\n            std::ptr::null(),\n            libc::MS_BIND | libc::MS_REMOUNT | libc::MS_RDONLY | libc::MS_NOSUID | libc::MS_NODEV,\n            std::ptr::null(),\n        )\n    } != 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    Ok(())\n}\nfn require_init_alias(root: &File, expected: Identity) -> io::Result<()> {\n    let alias = domain::named(root, \"init\", libc::O_PATH)?;\n    if alias.metadata()?.file_type().is_symlink() {\n        let mut buffer = [0u8; 256];\n        let count = unsafe {\n            libc::readlinkat(\n                root.as_raw_fd(),\n                c\"init\".as_ptr(),\n                buffer.as_mut_ptr().cast(),\n                buffer.len(),\n            )\n        };\n        if count < 0 {\n            return Err(io::Error::last_os_error());\n        }\n        let value = &buffer[..count as usize];\n        if value != b\"system/bin/init\" && value != b\"/system/bin/init\" {\n            return Err(error(\"/init alias is not the paired executable\"));\n        }\n    } else if !alias.metadata()?.is_file() || Identity::of(&alias)? != expected {\n        return Err(error(\"/init is not the paired executable inode\"));\n    }\n    Ok(())\n}\nfn read_exact(file: &File, buffer: &mut [u8], offset: u64) -> io::Result<()> {\n    let mut filled = 0;\n    while filled != buffer.len() {\n        let count = file.read_at(&mut buffer[filled..], offset + filled as u64)?;\n        if count == 0 {\n            return Err(error(\"ELF input truncated\"));\n        }\n        filled += count;\n    }\n    Ok(())\n}\nfn require_interpreter(file: &File, expected: &str) -> io::Result<()> {\n    let mut header = [0u8; 64];\n    read_exact(file, &mut header, 0)?;\n    let u16_at = |at| u16::from_le_bytes(header[at..at + 2].try_into().expect(\"header width\"));\n    let u64_at = |at| u64::from_le_bytes(header[at..at + 8].try_into().expect(\"header width\"));\n    #[cfg(target_arch = \"x86_64\")]\n    let machine = 62;\n    #[cfg(target_arch = \"aarch64\")]\n    let machine = 183;\n    if &header[..7] != b\"\\x7fELF\\x02\\x01\\x01\"\n        || !matches!(u16_at(16), 2 | 3)\n        || u16_at(18) != machine\n        || u16_at(52) != 64\n        || u16_at(54) != 56\n        || u16_at(56) == 0\n        || u16_at(56) > 1024\n    {\n        return Err(error(\"init is not a bounded native ELF64 executable\"));\n    }\n    let bytes = file.metadata()?.size();\n    let start = u64_at(32);\n    let end = start\n        .checked_add(u64::from(u16_at(56)) * 56)\n        .ok_or_else(|| error(\"ELF headers overflow\"))?;\n    if end > bytes {\n        return Err(error(\"ELF program headers exceed file\"));\n    }\n    let mut found = false;\n    for index in 0..u16_at(56) {\n        let mut ph = [0u8; 56];\n        read_exact(file, &mut ph, start + u64::from(index) * 56)?;\n        if u32::from_le_bytes(ph[..4].try_into().expect(\"program type\")) != 3 {\n            continue;\n        }\n        let offset = u64::from_le_bytes(ph[8..16].try_into().expect(\"program offset\"));\n        let size = u64::from_le_bytes(ph[32..40].try_into().expect(\"program size\"));\n        if found\n            || size != expected.len() as u64 + 1\n            || offset.checked_add(size).is_none_or(|n| n > bytes)\n        {\n            return Err(error(\n                \"init PT_INTERP duplicate or outside paired loader contract\",\n            ));\n        }\n        let mut interpreter = vec![0; size as usize];\n        read_exact(file, &mut interpreter, offset)?;\n        if interpreter.last() != Some(&0)\n            || &interpreter[..interpreter.len() - 1] != expected.as_bytes()\n        {\n            return Err(error(\n                \"init dynamic loader differs from paired bootstrap linker\",\n            ));\n        }\n        found = true;\n    }\n    if !found {\n        return Err(error(\n            \"init has no PT_INTERP; constructor cannot be guaranteed\",\n        ));\n    }\n    Ok(())\n}\nfn lmkd_rc(uid: u32, gid: u32) -> String {\n    // Do not use escaped physical newlines: Rust strips their leading\n    // whitespace and would remove the service-option indentation.\n    format!(\n        concat!(\n            \"# Package-owned native relay LMKD; init constructor owns the startup barrier.\\n\",\n            \"service lmkd {}\\n\",\n            \"    class core\\n\",\n            \"    user {}\\n\",\n            \"    group {} system readproc\\n\",\n            \"    capabilities DAC_OVERRIDE KILL IPC_LOCK SYS_NICE SYS_RESOURCE\\n\",\n            \"    socket lmkd seqpacket+passcred 0660 system system\\n\",\n            \"    task_profiles ServiceCapacityLow\\n\",\n            \"    stdio_to_kmsg\\n\",\n            \"    setenv DROIDLOOM_CELL 1\\n\",\n            \"    setenv DROIDLOOM_LMKD_CGROUP /sys/fs/cgroup\\n\",\n            \"    setenv DROIDLOOM_LMKD_PRESSURE relay-required\\n\",\n        ),\n        init_peer::LMKD,\n        uid,\n        gid\n    )\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    use std::os::unix::fs::symlink;\n    #[test]\n    fn final_init_exec_contract_rejects_wrappers_and_other_stage() {\n        let mut command = Command::new(\"/init\");\n        command.arg(\"second_stage\");\n        require_init_command(&command).unwrap();\n        command.arg(\"unexpected\");\n        assert!(require_init_command(&command).is_err());\n        let mut wrong = Command::new(\"/init\");\n        wrong.arg(\"first_stage\");\n        assert!(require_init_command(&wrong).is_err());\n        let mut wrapper = Command::new(\"taskset\");\n        wrapper.args([\"/init\", \"second_stage\"]);\n        assert!(require_init_command(&wrapper).is_err());\n    }\n    #[test]\n    fn generated_native_lmkd_options_remain_inside_one_service_block() {\n        let text = lmkd_rc(1069, 1069);\n        let mut lines = text\n            .lines()\n            .filter(|line| !line.is_empty() && !line.starts_with('#'));\n        assert_eq!(\n            lines.next(),\n            Some(\"service lmkd /droidloom/lmkd-bootstrap/lmkd\")\n        );\n        let options: Vec<_> = lines.collect();\n        assert_eq!(options.len(), 10);\n        assert!(\n            options\n                .iter()\n                .all(|line| line.starts_with(\"    \") && !line.starts_with(\"     \"))\n        );\n        assert!(options.contains(&\"    user 1069\"));\n        assert!(options.contains(&\"    group 1069 system readproc\"));\n        assert!(options.contains(&\"    setenv DROIDLOOM_LMKD_PRESSURE relay-required\"));\n    }\n    #[test]\n    fn init_alias_cannot_escape_the_private_image() {\n        let temp = tempfile::tempdir().unwrap();\n        let root = domain::directory(temp.path()).unwrap();\n        symlink(\"../../host/init\", temp.path().join(\"init\")).unwrap();\n        assert!(\n            require_init_alias(\n                &root,\n                Identity {\n                    device: 1,\n                    inode: 1\n                }\n            )\n            .is_err()\n        );\n        std::fs::remove_file(temp.path().join(\"init\")).unwrap();\n        symlink(\"/system/bin/init\", temp.path().join(\"init\")).unwrap();\n        require_init_alias(\n            &root,\n            Identity {\n                device: 1,\n                inode: 1,\n            },\n        )\n        .unwrap();\n    }\n    #[test]\n    fn wrong_or_missing_dynamic_loader_cannot_open_init_barrier() {\n        let mut file = tempfile::tempfile().unwrap();\n        let mut bytes = vec![0u8; 256];\n        bytes[..7].copy_from_slice(b\"\\x7fELF\\x02\\x01\\x01\");\n        bytes[16..18].copy_from_slice(&3u16.to_le_bytes());\n        #[cfg(target_arch = \"x86_64\")]\n        bytes[18..20].copy_from_slice(&62u16.to_le_bytes());\n        #[cfg(target_arch = \"aarch64\")]\n        bytes[18..20].copy_from_slice(&183u16.to_le_bytes());\n        bytes[32..40].copy_from_slice(&64u64.to_le_bytes());\n        bytes[52..54].copy_from_slice(&64u16.to_le_bytes());\n        bytes[54..56].copy_from_slice(&56u16.to_le_bytes());\n        bytes[56..58].copy_from_slice(&1u16.to_le_bytes());\n        bytes[64..68].copy_from_slice(&3u32.to_le_bytes());\n        bytes[72..80].copy_from_slice(&128u64.to_le_bytes());\n        bytes[96..104].copy_from_slice(&(INIT_LINKER.len() as u64 + 1).to_le_bytes());\n        bytes[128..128 + INIT_LINKER.len()].copy_from_slice(INIT_LINKER.as_bytes());\n        file.write_all(&bytes).unwrap();\n        require_interpreter(&file, INIT_LINKER).unwrap();\n        file.write_at(b\"x\", 128).unwrap();\n        assert!(require_interpreter(&file, INIT_LINKER).is_err());\n        file.write_at(&0u32.to_le_bytes(), 64).unwrap();\n        assert!(require_interpreter(&file, INIT_LINKER).is_err());\n        file.set_len(63).unwrap();\n        assert!(require_interpreter(&file, INIT_LINKER).is_err());\n    }\n    #[test]\n    fn ordinary_file_does_not_substitute_for_entry_owner_pidfd() {\n        let file = tempfile::tempfile().unwrap();\n        assert!(pidfd_alive(&file).is_err());\n        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, libc::getpid(), 0) };\n        assert!(raw >= 0);\n        let pidfd = unsafe { File::from_raw_fd(raw as i32) };\n        pidfd_alive(&pidfd).unwrap();\n    }\n    #[test]\n    fn sealed_fixed_capabilities_do_not_reach_an_ordinary_exec() {\n        let source = tempfile::tempfile().unwrap();\n        let high = unsafe { libc::fcntl(source.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 256) };\n        assert!(high >= 256);\n        let source = unsafe { File::from_raw_fd(high) };\n        for sealed in [false, true] {\n            let raw = source.as_raw_fd();\n            let mut command = Command::new(\"/bin/sh\");\n            command.args([\n                \"-c\",\n                \"for n in 198 199 200 201; do if [ -e /proc/self/fd/$n ]; then exit 9; fi; done\",\n            ]);\n            unsafe {\n                command.pre_exec(move || {\n                    for target in FIXED {\n                        if libc::dup2(raw, target) < 0 {\n                            return Err(io::Error::last_os_error());\n                        }\n                        close_on_exec(target, sealed)?;\n                    }\n                    Ok(())\n                });\n            }\n            let status = command.status().unwrap();\n            assert_eq!(status.code(), Some(if sealed { 0 } else { 9 }));\n        }\n    }\n}\n"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/init_peer.rs": {
      "bytes": 28125,
      "sha256": "d974d02115f686c8cd28a294e9e35428c23d8a54ec0b3bd7ea1398e3a74c0d6c",
      "text": "//! Private supervisor-to-real-init handshake. A HELLO is a claim to verify;\n//! all kernel identity, role, filesystem and budget evidence is held and checked.\nuse super::capability::{Artifact, Process};\nuse super::domain::{self, Domain, Identity};\nuse super::policy::{self, PressureRelaySpec, digest};\nuse droidloom_pressure_relay::{BootstrapState, BootstrapStatus, Budget};\nuse std::fs::File;\nuse std::io;\nuse std::mem::{size_of, zeroed};\nuse std::os::fd::{AsRawFd, FromRawFd, RawFd};\nuse std::os::unix::fs::{FileTypeExt, MetadataExt};\nuse std::time::{Duration, Instant};\n\npub(crate) const CONTROL_FD: i32 = 198;\npub(crate) const DOMAIN_FD: i32 = 199;\npub(crate) const OWNER_FD: i32 = 200;\npub(crate) const ENTRY_FD: i32 = 201;\npub(crate) const LIBRARY: &str = \"/droidloom/lmkd-bootstrap/libdroidloom_init_relay.so\";\npub(crate) const LMKD: &str = \"/droidloom/lmkd-bootstrap/lmkd\";\npub(crate) const ENDPOINT: &str = \"droidloom-lmkd-psi\";\n// ABI 2 PROJECT owns one detached mount cloned by the current source-namespace\n// owner. A raw foreign O_PATH descriptor is no longer a projection capability.\npub(crate) const INIT_ABI_TEXT: &str = \"2\";\nconst INIT_ABI: u32 = 2;\n#[cfg(target_arch = \"x86_64\")]\npub(crate) const COMPAT: &str = \"/system/lib64/libclang_rt.asan-x86_64-android.so\";\n#[cfg(target_arch = \"aarch64\")]\npub(crate) const COMPAT: &str = \"/system/lib64/bootstrap/libclang_rt.hwasan-aarch64-android.so\";\nconst WIRE: usize = 128;\nconst HELLO: u32 = 1;\nconst PROJECT: u32 = 2;\nconst PROJECTED: u32 = 3;\nconst COMMIT: u32 = 4;\nconst DONE: u32 = 5;\nfn error(message: &'static str) -> io::Error {\n    domain::error(message)\n}\npub(crate) fn preload() -> String {\n    format!(\"{LIBRARY}:{COMPAT}\")\n}\nfn number(wire: &[u8; WIRE], offset: usize, width: usize) -> u64 {\n    let mut bytes = [0; 8];\n    bytes[..width].copy_from_slice(&wire[offset..offset + width]);\n    u64::from_le_bytes(bytes)\n}\nfn put(wire: &mut [u8; WIRE], offset: usize, value: u64, width: usize) {\n    wire[offset..offset + width].copy_from_slice(&value.to_le_bytes()[..width]);\n}\nfn frame(kind: u32, nonce: &[u8; 32]) -> [u8; WIRE] {\n    let mut wire = [0; WIRE];\n    wire[..8].copy_from_slice(b\"P4IBV2!!\");\n    put(&mut wire, 8, INIT_ABI as u64, 4);\n    put(&mut wire, 12, kind as u64, 4);\n    wire[16..48].copy_from_slice(nonce);\n    wire\n}\nfn require_frame(wire: &[u8; WIRE], kind: u32, nonce: &[u8; 32]) -> io::Result<()> {\n    if nonce == &[0; 32] || wire[..48] != frame(kind, nonce)[..48] {\n        return Err(error(\"init protocol ABI/kind/nonce differs\"));\n    }\n    Ok(())\n}\nfn detached_endpoint(endpoint: &File) -> io::Result<File> {\n    let original = endpoint.metadata()?;\n    let flags = unsafe { libc::fcntl(endpoint.as_raw_fd(), libc::F_GETFL) };\n    let descriptor = unsafe { libc::fcntl(endpoint.as_raw_fd(), libc::F_GETFD) };\n    if !original.file_type().is_socket()\n        || flags < 0 || flags & libc::O_PATH == 0\n        || descriptor < 0 || descriptor & libc::FD_CLOEXEC == 0\n    {\n        return Err(error(\"source endpoint is not a sealed O_PATH socket\"));\n    }\n    // The caller has just validated the original HostContext and READY. The\n    // endpoint was opened in that same namespace, not received from init.\n    // OPEN_TREE_CLONE creates an owned anonymous mount; closing the last FD\n    // after any failure releases it. No path reopen or foreign-FD fallback.\n    const OPEN_TREE_CLONE: libc::c_uint = 1;\n    let raw = unsafe {\n        libc::syscall(\n            libc::SYS_open_tree,\n            endpoint.as_raw_fd(),\n            c\"\".as_ptr(),\n            OPEN_TREE_CLONE | libc::AT_EMPTY_PATH as libc::c_uint\n                | libc::O_CLOEXEC as libc::c_uint,\n        )\n    };\n    if raw < 0 { return Err(io::Error::last_os_error()); }\n    // SAFETY: open_tree returned a new owned descriptor.\n    let detached = unsafe { File::from_raw_fd(raw as RawFd) };\n    let cloned = detached.metadata()?;\n    let flags = unsafe { libc::fcntl(detached.as_raw_fd(), libc::F_GETFL) };\n    let descriptor = unsafe { libc::fcntl(detached.as_raw_fd(), libc::F_GETFD) };\n    if !cloned.file_type().is_socket()\n        || cloned.dev() != original.dev() || cloned.ino() != original.ino()\n        || cloned.uid() != original.uid() || cloned.gid() != original.gid()\n        || cloned.mode() != original.mode()\n        || flags < 0 || flags & libc::O_PATH == 0\n        || descriptor < 0 || descriptor & libc::FD_CLOEXEC == 0\n    {\n        return Err(error(\"detached endpoint identity or sealing differs\"));\n    }\n    Ok(detached)\n}\npub(crate) fn pair() -> io::Result<(File, File)> {\n    let mut fds = [-1; 2];\n    if unsafe {\n        libc::socketpair(\n            libc::AF_UNIX,\n            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,\n            0,\n            fds.as_mut_ptr(),\n        )\n    } != 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    // SAFETY: socketpair returned two distinct owned descriptors.\n    let host = unsafe { File::from_raw_fd(fds[0]) };\n    let child = unsafe { File::from_raw_fd(fds[1]) };\n    let on: libc::c_int = 1;\n    if unsafe {\n        libc::setsockopt(\n            host.as_raw_fd(),\n            libc::SOL_SOCKET,\n            libc::SO_PASSCRED,\n            (&on as *const libc::c_int).cast(),\n            size_of::<libc::c_int>() as libc::socklen_t,\n        )\n    } != 0\n    {\n        return Err(io::Error::last_os_error());\n    }\n    Ok((host, child))\n}\n#[repr(C, align(16))]\nstruct Ancillary([u8; 512]);\nstruct Packet {\n    wire: [u8; WIRE],\n    rights: Vec<File>,\n    credential: libc::ucred,\n}\nfn receive_packet(fd: RawFd) -> io::Result<Packet> {\n    let mut wire = [0; WIRE];\n    let mut control = Ancillary([0; 512]);\n    let mut vector = libc::iovec {\n        iov_base: wire.as_mut_ptr().cast(),\n        iov_len: WIRE,\n    };\n    let mut message: libc::msghdr = unsafe { zeroed() };\n    message.msg_iov = &mut vector;\n    message.msg_iovlen = 1;\n    message.msg_control = control.0.as_mut_ptr().cast();\n    message.msg_controllen = control.0.len();\n    let count = unsafe {\n        libc::recvmsg(\n            fd,\n            &mut message,\n            libc::MSG_DONTWAIT | libc::MSG_CMSG_CLOEXEC | libc::MSG_TRUNC,\n        )\n    };\n    if count < 0 {\n        return Err(io::Error::last_os_error());\n    }\n    let mut rights = Vec::new();\n    let mut credentials = Vec::new();\n    let mut malformed = false;\n    // Every delivered descriptor becomes owned before any framing error can\n    // return. MSG_CTRUNC is rejected after the delivered subset is adopted.\n    let mut header = unsafe { libc::CMSG_FIRSTHDR(&message) };\n    while !header.is_null() {\n        let minimum = unsafe { libc::CMSG_LEN(0) } as usize;\n        let h = unsafe { &*header };\n        if h.cmsg_len < minimum {\n            malformed = true;\n            break;\n        }\n        let bytes = h.cmsg_len - minimum;\n        let data = unsafe { libc::CMSG_DATA(header) };\n        if (data as usize)\n            .checked_add(bytes)\n            .is_none_or(|end| end > control.0.as_ptr() as usize + message.msg_controllen)\n        {\n            malformed = true;\n            break;\n        }\n        if h.cmsg_level == libc::SOL_SOCKET && h.cmsg_type == libc::SCM_RIGHTS {\n            if bytes == 0 || bytes % size_of::<RawFd>() != 0 {\n                malformed = true;\n            }\n            for index in 0..bytes / size_of::<RawFd>() {\n                let raw = unsafe {\n                    std::ptr::read_unaligned(data.add(index * size_of::<RawFd>()).cast::<RawFd>())\n                };\n                if raw < 0 {\n                    malformed = true;\n                    continue;\n                }\n                // SAFETY: each kernel-delivered SCM_RIGHTS number is fresh.\n                rights.push(unsafe { File::from_raw_fd(raw) });\n            }\n        } else if h.cmsg_level == libc::SOL_SOCKET\n            && h.cmsg_type == libc::SCM_CREDENTIALS\n            && bytes == size_of::<libc::ucred>()\n        {\n            credentials.push(unsafe { std::ptr::read_unaligned(data.cast::<libc::ucred>()) });\n        } else {\n            malformed = true;\n        }\n        header = unsafe { libc::CMSG_NXTHDR(&message, header) };\n    }\n    if count != WIRE as isize\n        || message.msg_flags & (libc::MSG_TRUNC | libc::MSG_CTRUNC) != 0\n        || malformed\n        || rights.len() > 16\n        || credentials.len() != 1\n    {\n        return Err(error(\n            \"init message size/ancillary credentials/rights differ\",\n        ));\n    }\n    for fd in &rights {\n        let flags = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_GETFD) };\n        if flags < 0 || flags & libc::FD_CLOEXEC == 0 {\n            return Err(error(\"received init capability is not CLOEXEC\"));\n        }\n    }\n    Ok(Packet {\n        wire,\n        rights,\n        credential: credentials.remove(0),\n    })\n}\nfn send_packet(fd: RawFd, wire: &[u8; WIRE], right: Option<&File>) -> io::Result<()> {\n    let mut control = Ancillary([0; 512]);\n    let mut vector = libc::iovec {\n        iov_base: wire.as_ptr() as *mut libc::c_void,\n        iov_len: WIRE,\n    };\n    let mut message: libc::msghdr = unsafe { zeroed() };\n    message.msg_iov = &mut vector;\n    message.msg_iovlen = 1;\n    if let Some(file) = right {\n        message.msg_control = control.0.as_mut_ptr().cast();\n        message.msg_controllen = unsafe { libc::CMSG_SPACE(size_of::<RawFd>() as u32) } as usize;\n        let header = unsafe { libc::CMSG_FIRSTHDR(&message) };\n        unsafe {\n            (*header).cmsg_level = libc::SOL_SOCKET;\n            (*header).cmsg_type = libc::SCM_RIGHTS;\n            (*header).cmsg_len = libc::CMSG_LEN(size_of::<RawFd>() as u32) as usize;\n            std::ptr::write_unaligned(libc::CMSG_DATA(header).cast::<RawFd>(), file.as_raw_fd());\n        }\n    }\n    let sent = unsafe { libc::sendmsg(fd, &message, libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT) };\n    if sent < 0 {\n        return Err(io::Error::last_os_error());\n    }\n    if sent != WIRE as isize {\n        return Err(error(\"short init seqpacket send\"));\n    }\n    Ok(())\n}\nstruct Wait<'a> {\n    socket: RawFd,\n    owner: &'a Process,\n    init: Option<&'a Process>,\n    cancel: &'a File,\n    deadline: Instant,\n}\nimpl Wait<'_> {\n    fn ready(&self, events: i16, terminal: bool) -> io::Result<()> {\n        loop {\n            self.owner.live()?;\n            if let Some(init) = self.init {\n                init.live()?;\n            }\n            let now = Instant::now();\n            if now >= self.deadline {\n                return Err(error(\"init barrier deadline expired\"));\n            }\n            let mut polls = [\n                libc::pollfd {\n                    fd: self.socket,\n                    events,\n                    revents: 0,\n                },\n                libc::pollfd {\n                    fd: self.owner.fd().as_raw_fd(),\n                    events: libc::POLLIN,\n                    revents: 0,\n                },\n                libc::pollfd {\n                    fd: self.init.map_or(-1, |p| p.fd().as_raw_fd()),\n                    events: libc::POLLIN,\n                    revents: 0,\n                },\n                libc::pollfd {\n                    fd: self.cancel.as_raw_fd(),\n                    events: libc::POLLIN,\n                    revents: 0,\n                },\n            ];\n            let timeout = i32::try_from(\n                self.deadline\n                    .saturating_duration_since(now)\n                    .as_millis()\n                    .max(1),\n            )\n            .unwrap_or(i32::MAX);\n            let count =\n                unsafe { libc::poll(polls.as_mut_ptr(), polls.len() as libc::nfds_t, timeout) };\n            if count < 0 {\n                let e = io::Error::last_os_error();\n                if e.kind() == io::ErrorKind::Interrupted {\n                    continue;\n                }\n                return Err(e);\n            }\n            // Retirement wins a batch even if a valid init packet is waiting.\n            if polls[1..].iter().any(|p| p.revents != 0) {\n                return Err(error(\"init barrier owner/init/cancellation changed\"));\n            }\n            let flags = polls[0].revents;\n            if flags & (libc::POLLERR | libc::POLLNVAL) != 0 {\n                return Err(error(\"init barrier channel fault\"));\n            }\n            let hup = flags & (libc::POLLHUP | libc::POLLRDHUP) != 0;\n            if hup && !(terminal && flags & libc::POLLIN != 0) {\n                return Err(error(\"init barrier closed before complete DONE\"));\n            }\n            if flags & events != 0 {\n                return Ok(());\n            }\n        }\n    }\n    fn receive(&self, terminal: bool) -> io::Result<Packet> {\n        loop {\n            self.ready(libc::POLLIN | libc::POLLRDHUP, terminal)?;\n            match receive_packet(self.socket) {\n                Err(e)\n                    if e.kind() == io::ErrorKind::WouldBlock\n                        || e.kind() == io::ErrorKind::Interrupted =>\n                {\n                    continue;\n                }\n                result => return result,\n            }\n        }\n    }\n    fn send(\n        &self,\n        wire: &[u8; WIRE],\n        right: Option<&File>,\n        before_send: &mut dyn FnMut() -> io::Result<()>,\n    ) -> io::Result<()> {\n        loop {\n            self.ready(libc::POLLOUT | libc::POLLRDHUP, false)?;\n            before_send()?;\n            match send_packet(self.socket, wire, right) {\n                Err(e)\n                    if e.kind() == io::ErrorKind::WouldBlock\n                        || e.kind() == io::ErrorKind::Interrupted =>\n                {\n                    continue;\n                }\n                result => return result,\n            }\n        }\n    }\n}\n#[derive(Clone, Copy, Eq, PartialEq)]\nenum Phase {\n    Fresh,\n    Hello,\n    Done,\n    Poisoned,\n}\npub(crate) struct InitPeer {\n    socket: Option<File>,\n    nonce: [u8; 32],\n    phase: Phase,\n    entry_deadline: Instant,\n    handshake: Duration,\n}\npub(crate) struct Hello {\n    pub process: Process,\n    pub namespaces: Vec<File>,\n    pub executable: Artifact,\n    pub root: File,\n    pub guest_domain: File,\n    pub compat: Artifact,\n    pub linker: Artifact,\n}\nimpl Hello {\n    pub(crate) fn validate(\n        &self,\n        owner: &Process,\n        domain: &Domain,\n        barrier: &Artifact,\n    ) -> io::Result<()> {\n        self.process.validate_init_child(owner)?;\n        self.process.validate_namespaces(&self.namespaces)?;\n        domain.validate()?;\n        let root = self.process.root()?;\n        if Identity::of(&root)? != Identity::of(&self.root)? {\n            return Err(error(\"init root changed\"));\n        }\n        let projection =\n            domain::beneath(&root, \"sys/fs/cgroup\", libc::O_RDONLY | libc::O_DIRECTORY)?;\n        domain::filesystem(&projection, 0x6367_7270)?;\n        if Identity::of(&projection)? != domain.identity()\n            || Identity::of(&self.guest_domain)? != domain.identity()\n        {\n            return Err(error(\"init cgroup projection changed\"));\n        }\n        self.executable.validate(false)?;\n        self.compat.validate(false)?;\n        self.linker.validate(false)?;\n        barrier.validate(false)?;\n        self.process.require_preload(&preload())?;\n        self.process.live()\n    }\n}\nimpl InitPeer {\n    pub(crate) fn new(\n        socket: File,\n        nonce: [u8; 32],\n        policy: &PressureRelaySpec,\n    ) -> io::Result<Self> {\n        if nonce == [0; 32] {\n            return Err(error(\"zero init barrier nonce\"));\n        }\n        Ok(Self {\n            socket: Some(socket),\n            nonce,\n            phase: Phase::Fresh,\n            entry_deadline: Instant::now() + Duration::from_millis(policy.entry_timeout_ms as u64),\n            handshake: Duration::from_millis(policy.bootstrap_timeout_ms as u64),\n        })\n    }\n    pub(crate) fn close(&mut self) {\n        self.socket = None;\n        if self.phase != Phase::Done {\n            self.phase = Phase::Poisoned;\n        }\n    }\n    pub(crate) fn accept(\n        &mut self,\n        owner: &Process,\n        domain: &Domain,\n        policy: &PressureRelaySpec,\n        barrier: &Artifact,\n        cancel: &File,\n        audit: &super::audit::Audit,\n    ) -> io::Result<Hello> {\n        if self.phase != Phase::Fresh {\n            return Err(error(\"init HELLO is a single attempt\"));\n        }\n        self.phase = Phase::Poisoned;\n        let socket = self\n            .socket\n            .as_ref()\n            .ok_or_else(|| error(\"init channel missing\"))?\n            .as_raw_fd();\n        let packet = Wait {\n            socket,\n            owner,\n            init: None,\n            cancel,\n            deadline: self.entry_deadline,\n        }\n        .receive(false)?;\n        require_frame(&packet.wire, HELLO, &self.nonce)?;\n        if packet.rights.len() != 12\n            || number(&packet.wire, 88, 4) != 12\n            || packet.wire[92..].iter().any(|v| *v != 0)\n            || packet.credential.uid != 0\n            || packet.credential.gid != 0\n            || packet.credential.pid <= 0\n        {\n            return Err(error(\"init HELLO role/rights/reserved bytes differ\"));\n        }\n        let mut rights = packet.rights.into_iter();\n        let guest_domain = rights.next().expect(\"length checked\");\n        let process = Process::from_received_pidfd(rights.next().expect(\"length checked\"))?;\n        if process.pid() != packet.credential.pid {\n            return Err(error(\"init HELLO sender differs from received pidfd\"));\n        }\n        process.validate_init_child(owner)?;\n        let namespaces: Vec<File> = rights.collect();\n        process.validate_namespaces(&namespaces)?;\n        domain.validate()?;\n        domain::filesystem(&guest_domain, 0x6367_7270)?;\n        let identity = Identity::of(&guest_domain)?;\n        if identity != domain.identity()\n            || number(&packet.wire, 48, 8) != identity.device\n            || number(&packet.wire, 56, 8) != identity.inode\n            || number(&packet.wire, 64, 8) != policy.memory_max_bytes\n            || number(&packet.wire, 72, 8) != policy.memory_high_bytes\n            || number(&packet.wire, 80, 8) != policy.memory_swap_max_bytes\n        {\n            return Err(error(\"init HELLO domain or explicit budget differs\"));\n        }\n        // The broker receives our original host domain descriptor. The guest\n        // copy is evidence of the projection, never the source of authority.\n        let root = process.root()?;\n        let projection =\n            domain::beneath(&root, \"sys/fs/cgroup\", libc::O_RDONLY | libc::O_DIRECTORY)?;\n        if Identity::of(&projection)? != domain.identity() {\n            return Err(error(\"actual init root exposes a different cgroup\"));\n        }\n        let executable = Artifact::from_file(\n            process.executable()?,\n            digest(&policy.init_sha256).map_err(error)?,\n            true,\n        )?;\n        let compat = Artifact::from_file(\n            domain::beneath(&root, COMPAT.trim_start_matches('/'), libc::O_RDONLY)?,\n            digest(&policy.compat_preload_sha256).map_err(error)?,\n            false,\n        )?;\n        let linker = Artifact::from_file(\n            domain::beneath(&root, \"system/bin/bootstrap/linker64\", libc::O_RDONLY)?,\n            digest(&policy.init_linker_sha256).map_err(error)?,\n            true,\n        )?;\n        process.require_preload(&preload())?;\n        executable.validate_mapped(&process)?;\n        compat.validate_mapped(&process)?;\n        linker.validate_mapped(&process)?;\n        barrier.validate_mapped(&process)?;\n        let hello = Hello {\n            process,\n            namespaces,\n            executable,\n            root,\n            guest_domain,\n            compat,\n            linker,\n        };\n        hello.validate(owner, domain, barrier)?;\n        self.entry_deadline = Instant::now() + self.handshake;\n        self.phase = Phase::Hello;\n        audit.record(super::audit::InitRecord::capture(&hello, &packet.wire)\n            .map(|init| super::audit::Event::InitHello { init }));\n        Ok(hello)\n    }\n    pub(crate) fn commit(\n        &mut self,\n        hello: &Hello,\n        owner: &Process,\n        domain: &Domain,\n        policy: &PressureRelaySpec,\n        barrier: &Artifact,\n        ready: &BootstrapStatus,\n        endpoint: &File,\n        cancel: &File,\n        broker_gate: &mut dyn FnMut() -> io::Result<()>,\n        audit: &super::audit::Audit,\n    ) -> io::Result<()> {\n        if self.phase != Phase::Hello {\n            return Err(error(\"init projection/COMMIT is a single attempt\"));\n        }\n        self.phase = Phase::Poisoned;\n        let expected_budget = Budget {\n            maximum: policy.memory_max_bytes,\n            high: Some(policy.memory_high_bytes),\n            swap_maximum: Some(policy.memory_swap_max_bytes),\n        }\n        .canonical();\n        if ready.state != BootstrapState::Ready\n            || ready.nonce != self.nonce\n            || ready.faulted\n            || ready.granted\n            || ready.cgroup.device != domain.identity().device\n            || ready.cgroup.inode != domain.identity().inode\n            || ready.budget != expected_budget\n        {\n            return Err(error(\n                \"broker READY does not bind this exact init/domain/budget\",\n            ));\n        }\n        let metadata = endpoint.metadata()?;\n        let identity = Identity::of(endpoint)?;\n        let flags = unsafe { libc::fcntl(endpoint.as_raw_fd(), libc::F_GETFL) };\n        if flags < 0\n            || flags & libc::O_PATH == 0\n            || !metadata.file_type().is_socket()\n            || metadata.uid() != policy.lmkd_uid\n            || metadata.gid() != policy.lmkd_gid\n            || metadata.mode() & 0o7777 != 0o600\n            || ready.endpoint.device != identity.device\n            || ready.endpoint.inode != identity.inode\n        {\n            return Err(error(\"broker socket capability differs from READY\"));\n        }\n        let mut wire = frame(PROJECT, &self.nonce);\n        put(&mut wire, 48, identity.device, 8);\n        put(&mut wire, 56, identity.inode, 8);\n        put(&mut wire, 64, policy.lmkd_uid as u64, 4);\n        put(&mut wire, 68, policy.lmkd_gid as u64, 4);\n        put(&mut wire, 72, 0o600, 4);\n        let socket = self\n            .socket\n            .as_ref()\n            .ok_or_else(|| error(\"init channel missing\"))?\n            .as_raw_fd();\n        let wait = Wait {\n            socket,\n            owner,\n            init: Some(&hello.process),\n            cancel,\n            deadline: self.entry_deadline,\n        };\n        hello.validate(owner, domain, barrier)?;\n        // This gate revalidates the captured process-leader and current worker\n        // namespaces before cloning. Wait::send repeats it at actual transfer.\n        broker_gate()?;\n        let detached = detached_endpoint(endpoint)?;\n        wait.send(&wire, Some(&detached), broker_gate)?;\n        drop(detached);\n        audit.record(Ok(super::audit::Event::InitProjectSent { wire_hex: policy::hex(&wire) }));\n        let projected = wait.receive(false)?;\n        put(&mut wire, 12, PROJECTED as u64, 4);\n        require_exact_peer_packet(&projected, &wire, hello.process.pid())?;\n        let mounted = domain::beneath(&hello.root, \"dev/socket/droidloom-lmkd-psi\", libc::O_PATH)?;\n        let mounted_meta = mounted.metadata()?;\n        if Identity::of(&mounted)? != identity\n            || !mounted_meta.file_type().is_socket()\n            || mounted_meta.uid() != policy.lmkd_uid\n            || mounted_meta.gid() != policy.lmkd_gid\n            || mounted_meta.mode() & 0o7777 != 0o600\n        {\n            return Err(error(\n                \"actual init socket projection differs from the permitted inode\",\n            ));\n        }\n        hello.validate(owner, domain, barrier)?;\n        audit.record(Ok(super::audit::Event::InitProjectedAccepted { wire_hex: policy::hex(&projected.wire) }));\n        put(&mut wire, 12, COMMIT as u64, 4);\n        wait.send(&wire, None, broker_gate)?;\n        audit.record(Ok(super::audit::Event::InitCommitSent { wire_hex: policy::hex(&wire) }));\n        let done = wait.receive(true)?;\n        put(&mut wire, 12, DONE as u64, 4);\n        require_exact_peer_packet(&done, &wire, hello.process.pid())?;\n        // DONE may share a poll batch with HUP. It is valid only with exact\n        // identity and both real process generations still alive.\n        owner.live()?;\n        hello.process.live()?;\n        domain.validate()?;\n        self.phase = Phase::Done;\n        self.socket = None;\n        audit.record(Ok(super::audit::Event::InitDoneAccepted { wire_hex: policy::hex(&done.wire) }));\n        Ok(())\n    }\n}\nfn require_exact_peer_packet(packet: &Packet, expected: &[u8; WIRE], pid: i32) -> io::Result<()> {\n    if packet.wire != *expected\n        || !packet.rights.is_empty()\n        || packet.credential.pid != pid\n        || packet.credential.uid != 0\n        || packet.credential.gid != 0\n    {\n        return Err(error(\n            \"init phase echo/credentials/unexpected rights differ\",\n        ));\n    }\n    Ok(())\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n    fn packet_pair() -> (File, File) {\n        pair().unwrap()\n    }\n    #[test]\n    fn actual_scm_rights_are_closed_on_invalid_ancillary_or_phase() {\n        let (receive, send) = packet_pair();\n        let mut pipes = [-1; 2];\n        assert_eq!(\n            unsafe { libc::pipe2(pipes.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) },\n            0\n        );\n        let reader = unsafe { File::from_raw_fd(pipes[0]) };\n        let writer = unsafe { File::from_raw_fd(pipes[1]) };\n        let nonce = [7; 32];\n        let mut wire = frame(DONE, &nonce);\n        wire[0] = 0;\n        send_packet(send.as_raw_fd(), &wire, Some(&writer)).unwrap();\n        drop(writer);\n        let packet = receive_packet(receive.as_raw_fd()).unwrap();\n        assert_eq!(packet.rights.len(), 1);\n        assert!(require_frame(&packet.wire, DONE, &nonce).is_err());\n        drop(packet);\n        let mut item = libc::pollfd {\n            fd: reader.as_raw_fd(),\n            events: libc::POLLIN,\n            revents: 0,\n        };\n        assert_eq!(unsafe { libc::poll(&mut item, 1, 0) }, 1);\n        assert_ne!(item.revents & libc::POLLHUP, 0);\n    }\n    #[test]\n    fn kernel_credentials_are_required_and_terminal_packet_survives_hup() {\n        let (receive, send) = packet_pair();\n        let wire = frame(DONE, &[9; 32]);\n        send_packet(send.as_raw_fd(), &wire, None).unwrap();\n        drop(send);\n        let packet = receive_packet(receive.as_raw_fd()).unwrap();\n        assert_eq!(packet.wire, wire);\n        assert_eq!(packet.credential.pid, unsafe { libc::getpid() });\n        assert_eq!(packet.credential.uid, unsafe { libc::geteuid() });\n        assert!(packet.rights.is_empty());\n    }\n    #[test]\n    fn exact_wire_rejects_old_abi_nonce_and_phase() {\n        let nonce = [3; 32];\n        let wire = frame(HELLO, &nonce);\n        require_frame(&wire, HELLO, &nonce).unwrap();\n        assert!(require_frame(&wire, DONE, &nonce).is_err());\n        assert!(require_frame(&wire, HELLO, &[4; 32]).is_err());\n        for abi in [0, 1] {\n            let mut old = wire;\n            put(&mut old, 8, abi, 4);\n            assert!(require_frame(&old, HELLO, &nonce).is_err());\n        }\n        let mut old = wire;\n        old[..8].copy_from_slice(b\"P4IBV1!!\");\n        assert!(require_frame(&old, HELLO, &nonce).is_err());\n        assert_eq!(INIT_ABI_TEXT.parse::<u32>().unwrap(), INIT_ABI);\n        assert!(require_frame(&frame(HELLO, &[0; 32]), HELLO, &[0; 32]).is_err());\n    }\n    #[test]\n    fn detached_projection_rejects_non_path_capabilities_before_mount_creation() {\n        let file = tempfile::tempfile().unwrap();\n        assert_eq!(detached_endpoint(&file).unwrap_err().kind(), io::ErrorKind::Other);\n        let (socket, _peer) = std::os::unix::net::UnixStream::pair().unwrap();\n        let socket = File::from(std::os::fd::OwnedFd::from(socket));\n        assert_eq!(detached_endpoint(&socket).unwrap_err().kind(), io::ErrorKind::Other);\n    }\n}\n"
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
      "bytes": 19521,
      "sha256": "1ed089df4cedd9704b1b2b0425468fb7aa66c7cd837ab159e7c86f6a85daef38"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs": {
      "bytes": 28104,
      "sha256": "2907c716d982ef34885e36368d167d50eb30d2a5858208c62b0ba9196db896fc"
    },
    "runtime/droidloom-supervisor/src/relay_lifecycle/init_peer.rs": {
      "bytes": 24924,
      "sha256": "959b554c7be8a8d00cefb8e76097977d9074ea5f553978cc1d454ce9791a7cf4"
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
  "revision": "producer08-projection01",
  "schema": 1,
  "source_manifest_sha256": "fc6b1699bb50f741a7483c165095393dce44c285186408b25a7c3938f34fe0a6"
}
'''))
