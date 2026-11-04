#!/usr/bin/env python3
"""Actual local /proc/file reads plus explicit synthetic readiness controls.

No Android, systemd, namespace or device operation is performed.  The
readiness scheduler uses an explicit fake clock/guard/census, not a claim of
actual Android boot qualification.  Child /proc controls use owned processes.
"""
from pathlib import Path
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types

sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location("control_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    census = load("framework_census")
    runtime = load("run")
    controls = []

    def passed(name, mode):
        controls.append({"name": name, "passed": True, "evidence_mode": mode})

    def rejects(action, exception=census.CensusError):
        try:
            action()
        except exception:
            return
        raise AssertionError("expected rejection")

    with tempfile.TemporaryDirectory(prefix="owned-framework-census-") as temporary:
        root = Path(temporary)
        file = root / "bounded"
        file.write_bytes(b"12345678")
        assert census.bounded_read(file, 8) == b"12345678"
        file.write_bytes(b"123456789")
        rejects(lambda: census.bounded_read(file, 8))
        passed("exact-read-limit-accepted-and-one-extra-byte-rejected", "actual temporary file")
        group = root / "cgroup-fixture"; group.mkdir()
        (group / "cgroup.procs").write_text("101\n102\n")
        sub = group / "child"; sub.mkdir(); (sub / "cgroup.procs").write_text("102\n103\n")
        pids, count, errors = census.enumerate_owned_pids(group, lambda: None)
        assert pids == [101, 102, 103] and count == 2 and errors == []
        passed("bounded-directory-enumeration-deduplicates-members", "actual files; declared synthetic cgroup fixture")
        link = group / "outside-link"; link.symlink_to(root, target_is_directory=True)
        rejects(lambda: census.enumerate_owned_pids(group, lambda: None)); link.unlink()
        passed("does-not-follow-cgroup-directory-symlink", "actual filesystem symlink")
        (sub / "cgroup.procs").write_text("0\n")
        rejects(lambda: census.enumerate_owned_pids(group, lambda: None))
        (sub / "cgroup.procs").write_text("103\n")
        old = census.MAX_PIDS
        try:
            census.MAX_PIDS = 2
            rejects(lambda: census.enumerate_owned_pids(group, lambda: None))
        finally:
            census.MAX_PIDS = old
        passed("invalid-pid-and-enumeration-bound-rejected", "actual files; declared bound seam")
        (sub / "cgroup.procs").unlink()
        pids, count, errors = census.enumerate_owned_pids(group, lambda: None)
        assert len(errors) == 1 and errors[0]["errno"] == 2
        passed("missing-cgroup-file-error-is-retained", "actual removed fixture file")

    proc_group = census.unified_group(Path("/proc/self/cgroup").read_bytes())
    namespace = os.readlink("/proc/self/ns/pid")
    # The executor mounts an outer-PID-namespace procfs.  Read its visible
    # numeric PID; never assume os.getpid() indexes the mounted /proc tree.
    visible_pid = census.proc_stat(Path("/proc/self/stat").read_bytes())[0]
    own = census.candidate(visible_pid, proc_group, namespace)
    assert own["identity"]["host_pid"] == visible_pid
    assert own["identity"]["uids"] == [os.getuid(), os.geteuid(), os.geteuid(), os.geteuid()]
    assert own["identity"]["executable"] == os.readlink("/proc/self/exe")
    passed("actual-owned-proc-identity-read", "actual local process")
    outside = census.candidate(visible_pid, "/system.slice/not-this-process-daemon.service", namespace)
    assert outside == {"host_pid": visible_pid, "state": "outside-owned-cgroup-before-read"}
    other_ns = census.candidate(visible_pid, proc_group, "pid:[not-this-namespace]")
    assert other_ns["state"] == "different-pid-namespace" and "identity" not in other_ns
    passed("outside-cgroup-or-namespace-excluded-before-argv", "actual local process; declared mismatched expected identities")
    child = subprocess.Popen([sys.executable, "-u", "-c", "from pathlib import Path;import time;print(Path('/proc/self/stat').read_text().split('(',1)[0].strip(),flush=True);time.sleep(20)", "x" * 5000],
                             stdout=subprocess.PIPE, text=True)
    try:
        visible_child = int(child.stdout.readline().strip())
        oversized = census.candidate(visible_child, proc_group, namespace)
        assert oversized["state"] == "read-error" and oversized["error"]["operation"] == "argv"
        assert "identity" not in oversized and "byte bound" in oversized["error"]["message"]
        passed("actual-oversized-child-argv-is-not-retained", "actual owned child /proc")
    finally:
        child.terminate(); child.wait(timeout=5); child.stdout.close()
    vanished = census.candidate(visible_child, proc_group, namespace)
    assert vanished["state"] == "read-error" and vanished["error"]["errno"] in (2, 3)
    passed("reaped-owned-child-records-read-error", "actual owned child reaped")
    rejects(lambda: census.unified_group(b"0::/one\n0::/two\n"))
    rejected = census.collect({}, os.getpid(), "/")
    assert not rejected["complete"] and not rejected["records"]
    passed("unbounded-root-and-ambiguous-cgroup-rejected", "pure parser and no-read root gate")

    class GuardError(RuntimeError):
        def __init__(self, code):
            super().__init__(code); self.code = code
        def receipt(self):
            return {"error": self.code, "action_attempted": False, "automatic_retry": False}

    class Clock:
        value = 0.0
        def now(self): return self.value
        def sleep(self, seconds): self.value += seconds

    init = {"host_pid": 42, "start_ticks": 123}
    epoch = {"binding": {"processes": {"init": init}}, "sha256": "f" * 64}
    successful_census = {"complete": True, "init_before": init, "init_after": init,
                         "role_matches": {"zygote64": [43], "system_server": [44], "surfaceflinger": [45]}}
    original_collect = census.collect

    def fixture(sequence, diag=None, guard_fail_after=None):
        records = {}; calls = []; checks = []; clock = Clock()
        remaining = list(sequence)
        def save(name, value):
            assert name not in records, "receipt overwrite"
            records[name] = copy.deepcopy(value)
        def capture():
            calls.append(1)
            item = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            if callable(item): item = item(clock)
            if isinstance(item, Exception): raise item
            return copy.deepcopy(item)
        def guard():
            checks.append(1)
            if guard_fail_after is not None and len(checks) >= guard_fail_after:
                raise RuntimeError("synthetic Main epoch changed")
        scope = {"PRIVATE_EPOCH": None, "ROWS": [{"role": "daemon", "group": "/system.slice/owned-daemon.service"}],
                 "INIT": {"pid": 42}, "EPOCH_GUARD": {"EpochError": GuardError}, "save": save,
                 "current_guest_epoch": capture}
        census.collect = lambda *a: copy.deepcopy(successful_census if diag is None else diag)
        return scope, records, calls, checks, clock, guard

    def execute(data):
        scope, records, calls, checks, clock, guard = data
        return census.capture_initial(scope, guard, now=clock.now, sleep=clock.sleep)

    try:
        data = fixture([epoch]); assert execute(data) == epoch
        assert len(data[2]) == 1 and data[0]["PRIVATE_EPOCH"] == epoch
        assert data[1]["private-framework-initial-readiness.json"]["attempts"] == 1
        passed("first-strict-success-fixes-one-epoch", "explicit synthetic guard/census/clock")
        rejects(lambda: execute(data)); assert len(data[2]) == 1
        passed("fixed-epoch-cannot-be-recaptured", "explicit synthetic guard/census/clock")
        data = fixture([GuardError("FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING"), epoch])
        assert execute(data) == epoch and len(data[2]) == 2 and data[4].value == 1
        assert "private-framework-initial-0-capture-error.json" in data[1]
        assert data[1]["private-framework-initial-readiness.json"]["attempts"] == 2
        passed("only-initial-readiness-error-reobserved-with-first-error-retained", "explicit synthetic guard/census/clock")
        data = fixture([GuardError("FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING")])
        rejects(lambda: execute(data), GuardError)
        assert data[4].value == 30 and len(data[2]) == 30 and data[0]["PRIVATE_EPOCH"] is None
        assert len([k for k in data[1] if k.endswith("capture-error.json")]) == 30
        passed("30-second-deadline-no-epoch-or-case-after-exhaustion", "explicit synthetic guard/census/clock")
        data = fixture([GuardError("FRAMEWORK_PROCESS_UNVERIFIED"), epoch])
        rejects(lambda: execute(data), GuardError)
        assert len(data[2]) == 1 and data[4].value == 0 and data[0]["PRIVATE_EPOCH"] is None
        passed("other-strict-guard-error-never-retried", "explicit synthetic guard/census/clock")
        data = fixture([epoch], diag={"complete": False, "error": "declared incomplete fixture"})
        rejects(lambda: execute(data)); assert not data[2] and len(data[1]) == 1
        passed("incomplete-census-retained-before-any-capture-or-case", "explicit synthetic guard/census/clock")
        wrong = copy.deepcopy(epoch); wrong["binding"]["processes"]["init"]["start_ticks"] += 1
        data = fixture([wrong]); rejects(lambda: execute(data))
        assert data[0]["PRIVATE_EPOCH"] is None
        passed("init-generation-mismatch-refuses-epoch", "explicit synthetic guard/census/clock")
        def late(clock): clock.value = 31; return epoch
        data = fixture([late]); rejects(lambda: execute(data)); assert data[0]["PRIVATE_EPOCH"] is None
        passed("late-strict-success-does-not-admit-action", "explicit synthetic guard/census/clock")
        data = fixture([GuardError("FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING"), epoch], guard_fail_after=4)
        rejects(lambda: execute(data), RuntimeError); assert len(data[2]) == 1
        passed("Main-epoch-change-stops-readiness-loop", "explicit synthetic guard/census/clock")
        scope = {"FRAMEWORK_CENSUS": types.SimpleNamespace(capture_initial=lambda *a: (_ for _ in ()).throw(AssertionError("must not enter")))}
        flow = runtime.ProbeFlow(scope, None); flow.mutation_attempted = True
        rejects(flow.run, RuntimeError)
        passed("runtime-disallows-initial-wait-after-probe-action", "actual runtime method with explicit synthetic scope")
    finally:
        census.collect = original_collect
    print(json.dumps({"schema": 1, "state": "LOCAL_CENSUS_AND_READINESS_CONTROLS_PASS", "controls": controls,
                      "count": len(controls), "device_operations": 0, "owned_child_reaped": True,
                      "Android_qualification": "NOT_RUN", "synthetic_tests_are_not_device_evidence": True}, indent=2))


if __name__ == "__main__":
    main()
