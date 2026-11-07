#!/usr/bin/env python3
"""Owned host controls for runtime r4. No Android, service or namespace entry."""
from contextlib import contextmanager
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).parent
WORK = ROOT.parent
ROWS = []

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

H = module("held_r4_control", ROOT / "held_runtime.py")
R = module("runtime_r4_control", ROOT / "run.py")
F = module("failure_r4_control", ROOT / "failure_evidence.py")
OLD = module("runtime_r3_preimage_control", ROOT / "references/runtime-r3-run.py")

def test(name, function, scope="pure parser/source control"):
    result = function()
    if result is False:
        raise AssertionError(name)
    ROWS.append({"name": name, "passed": True, "scope": scope, "detail": result})

def rejection(function, text=None):
    try:
        function()
    except (H.BindingError, RuntimeError, OSError, UnicodeError) as error:
        if text is not None:
            assert text in str(error), repr(error)
        return {"rejected": type(error).__name__, "message": str(error)}
    raise AssertionError("expected rejection")

class RootFixture:
    def __init__(self, root):
        self.root_fd = os.open(root, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    def open_root(self, path, flags=os.O_RDONLY):
        return H.open_in_root(self.root_fd, path, flags)
    def close(self):
        os.close(self.root_fd)

def read_file(target, path):
    fd = target.open_root(path)
    try:
        return os.read(fd, 4096)
    finally:
        os.close(fd)

VALID = b"IGNORED_SECRET=not-retained\0BOOTCLASSPATH=/system/framework/a.jar:/apex/art/b.jar\0DEX2OATBOOTCLASSPATH=/system/framework/a.jar\0"
test("two-required-classpaths-selected-and-other-env-omitted",
     lambda: H.selected_classpaths(VALID) == {
         "BOOTCLASSPATH": "/system/framework/a.jar:/apex/art/b.jar",
         "DEX2OATBOOTCLASSPATH": "/system/framework/a.jar"})
for name, raw in [
    ("missing-boot", b"DEX2OATBOOTCLASSPATH=/a.jar\0"),
    ("missing-dex2oat", b"BOOTCLASSPATH=/a.jar\0"),
    ("empty-boot", b"BOOTCLASSPATH=\0DEX2OATBOOTCLASSPATH=/a.jar\0"),
    ("duplicate-key", VALID + b"BOOTCLASSPATH=/other.jar\0"),
    ("unterminated-environ", VALID[:-1]),
    ("relative-jar", VALID.replace(b"/system/framework/a.jar", b"relative.jar")),
    ("dotdot-jar", VALID.replace(b"/system/framework/a.jar", b"/system/../a.jar")),
    ("empty-classpath-component", VALID.replace(b":/apex", b"::/apex")),
    ("non-jar", VALID.replace(b"/apex/art/b.jar", b"/apex/art/b")),
    ("duplicate-path", VALID.replace(b"/apex/art/b.jar", b"/system/framework/a.jar")),
    ("oversized-environ", b"X=" + b"a" * H.ENV_LIMIT + b"\0"),
    ("too-many-classpath-entries",
     b"BOOTCLASSPATH=" + b":".join(("/x" + str(i) + ".jar").encode() for i in range(257))
     + b"\0DEX2OATBOOTCLASSPATH=/a.jar\0"),
]:
    test("reject-" + name, lambda raw=raw: rejection(lambda: H.selected_classpaths(raw)))

with tempfile.TemporaryDirectory(prefix="r4-owned-controls-", dir=WORK) as tmp:
    base = Path(tmp)
    root = base / "root"
    (root / "system/framework").mkdir(parents=True)
    (root / "apex/art").mkdir(parents=True)
    (root / "system/framework/a.jar").write_bytes(b"owned-a")
    (root / "apex/art/b.jar").symlink_to("/system/framework/a.jar")
    target = RootFixture(root)
    try:
        values = H.selected_classpaths(VALID)
        def check_hashes():
            files, total = H.hash_classpaths(target, values, time.monotonic() + 5)
            assert len(files) == 2 and total == 14
            assert all(row["sha256"] == hashlib.sha256(b"owned-a").hexdigest() for row in files)
            return {"real_openat2": True, "absolute_apex_symlink_resolved_inside_root": True,
                    "count": len(files), "total_bytes": total}
        test("real-classpath-files-and-absolute-apex-symlink", check_hashes, "real owned filesystem/openat2")

        (base / "outside.jar").write_bytes(b"outside")
        (root / "escape.jar").symlink_to(base / "outside.jar")
        test("absolute-symlink-cannot-read-host-outside-root",
             lambda: rejection(lambda: read_file(target, "/escape.jar")),
             "real owned filesystem/openat2")
        test("guest-dotdot-path-rejected",
             lambda: rejection(lambda: read_file(target, "/../outside.jar")))
        test("expired-classpath-deadline-fails-before-hashing",
             lambda: rejection(lambda: H.hash_classpaths(target, values, time.monotonic() - 1)))

        oversized = root / "oversized.jar"
        with oversized.open("wb") as stream:
            stream.truncate(H.FILE_LIMIT + 1)  # Sparse metadata only; never read the oversized payload.
        over_values = {"BOOTCLASSPATH": "/oversized.jar", "DEX2OATBOOTCLASSPATH": "/oversized.jar"}
        test("real-sparse-file-above-128MiB-rejected-before-read",
             lambda: rejection(lambda: H.hash_classpaths(target, over_values, time.monotonic() + 5)),
             "real owned sparse file; no pressure workload")
        saved_total = H.TOTAL_FILE_LIMIT
        try:
            H.TOTAL_FILE_LIMIT = 7  # Explicitly scaled control of total accounting, not a production change.
            test("scaled-total-budget-rejects-second-real-file",
                 lambda: rejection(lambda: H.hash_classpaths(target, values, time.monotonic() + 5)),
                 "real owned files with declared scaled total limit")
        finally:
            H.TOTAL_FILE_LIMIT = saved_total
        assert H.TOTAL_FILE_LIMIT == 768 * 1024 * 1024

        # Actual directory object replacement models the path-slot aspect of
        # PID reuse. It is not presented as a real kernel PID-reuse experiment.
        original = base / "original"
        replacement = base / "replacement"
        original.mkdir(); replacement.mkdir()
        (original / "marker").write_bytes(b"original")
        (replacement / "marker").write_bytes(b"replacement")
        slot = base / "slot"
        slot.symlink_to(original, target_is_directory=True)
        pinned = RootFixture(slot)
        try:
            slot.unlink(); slot.symlink_to(replacement, target_is_directory=True)
            legacy = (slot / "marker").read_bytes()
            fixed = read_file(pinned, "/marker")
            assert legacy == b"replacement" and fixed == b"original"
            test("old-path-slot-retargets-new-held-root-stays-original",
                 lambda: {"baseline_correct_destination": False, "fixed_correct_destination": True,
                          "real_directory_replacement": True, "real_kernel_pid_reuse": False},
                 "real filesystem object identity; declared PID-slot model")
        finally:
            pinned.close()

        # Reproduce the exact old error-priority bug using both actual case()
        # implementations and a declared command-result seam.
        row = {"package": "org.droidloom.signalprobe", "instrumentation": "Fixture", "version": 1}
        binding = {"package": row["package"], "uid": 10114, "version_code": 1}
        nonce = "1" * 32
        saved = []
        captures = []
        reads = []
        class NoRead:
            def exists(self, path):
                return False
            def read_file(self, *args, **kwargs):
                reads.append(args)
                raise AssertionError("claim was read after failed command")
        def scope():
            return {"P": {"apks": {"r2": row}, "nonces": {"r2-svc": nonce}, "engine_sha256": "a" * 64},
                    "INIT": {"pid": 123}, "save": lambda *args: saved.append(args), "RESULT": {},
                    "FAILURE_EVIDENCE": types.SimpleNamespace(capture=lambda *args: captures.append(args))}
        def fixture(s):
            return types.SimpleNamespace(s=s, target=NoRead(), failure_labels=set(),
                package_binding=lambda *args: binding, command=lambda *args, **kwargs: None,
                android=lambda *args, **kwargs: subprocess.CompletedProcess([], 1, b"", b""),
                instrument_with_mapping=lambda *args: (subprocess.CompletedProcess([], 134, b"", b""), []),
                guard=lambda *args: None)
        old_path = OLD.Path
        try:
            OLD.Path = lambda *args: base / "legacy-proc-model"
            old_error = None
            try:
                OLD.ProbeFlow.case(fixture(scope()), "r2", "svc")
            except Exception as error:
                old_error = error
            assert isinstance(old_error, FileNotFoundError), repr(old_error)
        finally:
            OLD.Path = old_path
        fixed_error = None
        try:
            R.ProbeFlow.case(fixture(scope()), "r2", "svc")
        except Exception as error:
            fixed_error = error
        assert isinstance(fixed_error, RuntimeError) and "status=134" in str(fixed_error), repr(fixed_error)
        assert not reads and len(captures) == 1
        test("actual-r3-case-obscures-134-r4-case-preserves-first-cause",
             lambda: {"baseline_error": repr(old_error), "baseline_expected_behavior": False,
                      "fixed_error": repr(fixed_error), "fixed_expected_behavior": True,
                      "durable_reads_after_nonzero": 0, "diagnostic_attempts": 1},
             "both actual case implementations; declared command-result/path seams")

        flow = R.ProbeFlow({"HELD_API": H}, None)
        test("instrumentation-refused-before-private-classpath-admission",
             lambda: rejection(lambda: flow.guest_command(["/system/bin/am", "instrument"], 2000, 35)))
        flow.classpath_env = H.selected_classpaths(VALID)
        command = flow.guest_command(["/system/bin/am", "instrument", "-w"], 2000, 35)
        assert command[0:2] == ["/system/bin/env", "-i"]
        assert sum(x.startswith("BOOTCLASSPATH=") for x in command) == 1
        assert sum(x.startswith("DEX2OATBOOTCLASSPATH=") for x in command) == 1
        test("env-i-command-has-both-admitted-required-keys", lambda: True)

        tombstones = root / "data/tombstones"
        tombstones.mkdir(parents=True)
        owned = ("Cmdline: app_process /system/bin com.android.commands.am.Am instrument "
                 "-e nonce " + nonce + " " + row["package"] + "/Fixture\nuid: 2000\nsignal 6\n").encode()
        (tombstones / "tombstone_00").write_bytes(owned)
        (tombstones / "tombstone_01").write_bytes(b"Cmdline: unrelated.fixture\nuid: 1000\n")
        captured_files = {}
        result = F.inspect_tombstones(target, "r2-svc", row["package"], 10114, nonce,
                                      lambda name, value: captured_files.setdefault(name, value))
        assert len(result["files"]) == 1 and len(captured_files) == 1
        assert next(iter(captured_files.values())) == owned
        test("failure-tombstone-filter-keeps-exact-owned-nonce-only",
             lambda: {"captured": 1, "unrelated_ignored": True},
             "real owned tombstone fixture, no Android tombstone generated")
    finally:
        target.close()

    host_root = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    own_file = os.open(base / "outside.jar", os.O_RDONLY | os.O_CLOEXEC)
    try:
        test("real-proc-magic-link-rejected-by-openat2",
             lambda: rejection(lambda: H.open_in_root(host_root, "/proc/self/fd/" + str(own_file))),
             "real openat2; only this control's own FD")
    finally:
        os.close(own_file); os.close(host_root)

    # Real init-binding mechanics are exercised against this owned control
    # process/child, without entering any namespace or targeting Android.
    control_cwd = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.chdir("/")  # Match the production init cwd contract without weakening it.
    pid = os.getpid()
    proc = os.open("/proc/" + str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        identity = H.proc_identity_at(proc, pid, time.monotonic() + 5)
    finally:
        os.close(proc)
    before_fds = set(os.listdir("/proc/self/fd"))
    held = H.HeldTarget(identity, "/declared-helper-not-executed")
    try:
        with held.entry(["/declared-command-not-executed"]) as (argv, authorities):
            assert len(authorities) == 7 and len(set(authorities)) == 7
            assert "--target" not in argv and str(pid) not in argv
            assert all(not os.get_inheritable(fd) for fd in authorities)
            assert held.proc_fd not in authorities and held.pid_fd not in authorities
        test("real-held-six-namespaces-and-root-build-no-numeric-entry",
             lambda: {"authority_count": 7, "commands_executed": 0, "procdir_and_pidfd_not_passed": True},
             "real own process procdir/pidfd/namespace/root descriptors")
        active_fds = tuple(held._fds)
        with held.lease():
            error = rejection(held.close, "active commands/readers")
            assert all(os.fstat(fd) for fd in active_fds)
        held.close()
        assert all(not os.path.exists("/proc/self/fd/" + str(fd)) for fd in active_fds)
        test("release-while-active-seals-admission-without-closing-live-fds",
             lambda: error, "real descriptors and actual lease lifecycle")
    finally:
        held.close()
    assert set(os.listdir("/proc/self/fd")) == before_fds
    test("held-binding-releases-all-owned-fds", lambda: True, "real FD-table before/after")

    process = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(30)"])
    child_held = None
    try:
        proc = os.open("/proc/" + str(process.pid), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            child_identity = H.proc_identity_at(proc, process.pid, time.monotonic() + 5)
        finally:
            os.close(proc)
        child_held = H.HeldTarget(child_identity, "/declared-helper-not-executed")
        process.terminate(); process.wait(timeout=5)
        test("dead-original-child-pidfd-refuses-new-admission",
             lambda: rejection(child_held.verify, "no longer alive"),
             "real own child death/pidfd; exact child reaped")
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=5)
        if child_held is not None:
            child_held.close()

    os.fchdir(control_cwd)
    os.close(control_cwd)
    closed = []
    sealed = []
    flow = R.ProbeFlow({"save": lambda *args: None}, None)
    flow.target = types.SimpleNamespace(seal_admission=lambda: sealed.append(True), close=lambda: closed.append(True))
    flow.sampler = types.SimpleNamespace(is_alive=lambda: True)
    failures = []
    flow.release_bindings(failures)
    assert sealed == [True] and closed == [] and len(failures) == 1
    test("live-sampler-release-fails-without-reusing-authority-fds",
         lambda: {"sealed": True, "closed": False, "failure_recorded": True},
         "declared live-sampler lifecycle seam")

    class DirectOwnedCommand:
        @contextmanager
        def entry(self, command):
            yield command, ()
    direct = DirectOwnedCommand()
    env = {"PATH": "/usr/bin:/bin", "LANG": "C"}
    result = F.bounded_command(direct, [sys.executable, "-I", "-c", "print('owned')"], env, timeout=2)
    assert result["returncode"] == 0 and result["stdout"] == b"owned\n" and result["child_reaped"]
    test("bounded-diagnostic-command-completes-and-reaps",
         lambda: {"returncode": 0, "child_reaped": True},
         "real owned subprocess; explicit direct-entry seam")
    result = F.bounded_command(direct, [sys.executable, "-I", "-c",
                               "import os; os.write(1,b'x'*(512*1024+1))"], env, timeout=2)
    assert result["stopped"] == "diagnostic-output-limit" and len(result["stdout"]) == F.LOG_LIMIT and result["child_reaped"]
    test("bounded-diagnostic-output-cap-kills-only-own-child-and-reaps",
         lambda: {"captured_bytes": len(result["stdout"]), "child_reaped": True},
         "real owned subprocess; actual 512KiB bound")
    result = F.bounded_command(direct, [sys.executable, "-I", "-c", "import time; time.sleep(30)"], env, timeout=.15)
    assert result["stopped"] == "diagnostic-timeout" and result["child_reaped"]
    test("bounded-diagnostic-timeout-reaps-own-child",
         lambda: {"child_reaped": True}, "real owned subprocess; no namespace entry")


    # Declared unreaped-child seam: real pipes and the production sticky
    # poison/close methods are used; no stuck kernel child is manufactured.
    class UnreapedTarget(DirectOwnedCommand):
        def __init__(self):
            self._lock = threading.RLock()
            self._active = 0
            self._unjoined_command = False
            self._admission_closed = False
            self._closed = False
            self._fds = list(os.pipe())
        def poison_unjoined_command(self):
            H.HeldTarget.poison_unjoined_command(self)
        def close(self):
            H.HeldTarget.close(self)
    class UnreapedProcess:
        def __init__(self, *args, **kwargs):
            self.returncode = None
            self.kills = 0
            self.waits = 0
            a, b = os.pipe(); os.close(b)
            self.stdout = os.fdopen(a, "rb")
            a, b = os.pipe(); os.close(b)
            self.stderr = os.fdopen(a, "rb")
        def poll(self):
            return None
        def kill(self):
            self.kills += 1
        def wait(self, timeout=None):
            self.waits += 1
            raise subprocess.TimeoutExpired("declared-unreaped-child-seam", timeout)
    unjoined = UnreapedTarget()
    real_popen = F.subprocess.Popen
    try:
        F.subprocess.Popen = UnreapedProcess
        result = F.bounded_command(unjoined, ["/declared-command-never-executed"], env, timeout=.1)
        assert result["child_reaped"] is False and result["stopped"] == "diagnostic-child-not-reaped"
        assert unjoined._unjoined_command and unjoined._admission_closed
        error = rejection(unjoined.close, "unjoined diagnostic child")
        assert all(os.fstat(fd) for fd in unjoined._fds)
        test("unreaped-diagnostic-poisons-entry-and-retains-owned-fds",
             lambda: {"child_reaped": False, "permanent_admission_closed": True,
                      "release_refused": True, "owned_fds_still_open": True},
             "declared unreaped-child seam, real pipes, actual production poison/close methods")
    finally:
        F.subprocess.Popen = real_popen
        # No child was launched by this declared seam. This is test fixture
        # teardown, not a supported way to recover a poisoned runtime target.
        for fd in unjoined._fds:
            os.close(fd)

# The original retained source is still byte-for-byte unchanged.
assert hashlib.sha256((ROOT / "references/runtime-r3-run.py").read_bytes()).hexdigest() == \
    "fe2536e3ac510b811c3b079e5791ecb2eb015bec4163b5a0fb73b8e85542c8e7"
assert hashlib.sha256((ROOT / "references/preparation-r1/v5_original.py").read_bytes()).hexdigest() == \
    "895ecbfec6d04170adf0dbc16a0fd18d3de0b78317efec86de1846295dfcddb8"
assert R.HELPER_SOURCE_SHA == H.HELPER_SOURCE_SHA and R.HELPER_BINARY_SHA == H.HELPER_BINARY_SHA
test("retained-preimages-and-shared-helper-pins-unchanged", lambda: True, "actual SHA256 reads")

report = {"schema": 1, "state": "OWNED_HOST_R4_CONTROLS_PASS", "controls": ROWS,
          "passed": len(ROWS), "android_operations": 0, "namespace_entries": 0,
          "services_started": 0, "kernel_pid_reuse_experiment": False,
          "shared_helper_namespace_execution": "qualified separately by parent receipt",
          "private_Android_qualification": "NOT_RUN", "production_ready": False,
          "source_pins": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in ("run.py", "held_runtime.py", "failure_evidence.py", "verify_r4.py")}}
print(json.dumps(report, sort_keys=True, indent=2))
