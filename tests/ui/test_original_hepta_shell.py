"""Negative checks for the capture contract; these are not Agentd evidence."""

import copy
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import signal
import subprocess
import sys
import time
import unittest

SPEC = importlib.util.spec_from_file_location("shell_capture_contract",
    Path(__file__).with_name("probe-original-hepta-shell.py"))
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


def phase_record(sequence=1, instance="first-session", pid=41):
    phase = capture.PHASES[sequence - 1]
    lifecycle = ("starting", "running", "draining", "draining", "running", "running")[sequence - 1]
    spawn = 7 if sequence < 5 else 14
    stale = sequence in (4, 6)
    observation = {"sampled_unix_ms": 10_000,
        "agent_id": "11111111-1111-4111-8111-111111111111", "spawn_generation": spawn,
        "current_generation": spawn + {"starting": 0, "running": 1, "draining": 2}[lifecycle],
        "health": {"process_id": 42 if sequence < 5 else 43, "lifecycle": lifecycle,
            "ready": lifecycle == "running", "promotion_ready": lifecycle == "running", "fenced": False},
        "events": [{"cursor": 1, "kind": "bootstrapped", "generation": None, "lifecycle": None},
            {"cursor": 2, "kind": "lifecycle", "generation": spawn,
                "lifecycle": lifecycle}],
        "capabilities": [], "capabilities_truncated": False, "events_omitted_from_view": 0,
        "next_cursor": 2, "latest_cursor": 2, "history_gap": False, "source_changed": False}
    snapshot = {"type": "snapshot", "tasks": [], "session_instance": instance,
        "hepta": {"connection": "stale" if stale else "observed",
            "error_code": "generation_mismatch" if stale else None,
            "last_observation": observation}}
    return {"event": "session_phase_observed", "sequence": sequence, "phase": phase,
        "session_pid": pid, "session_instance": instance, "runtime_dir": "/test/ui-runtime",
        "session_socket_path": "/test/ui-runtime/trillionnium-ui/session.sock",
        "snapshot": snapshot, "ack": {"sequence": sequence, "phase": phase,
            "session_instance": instance}}


class CaptureContract(unittest.TestCase):
    def test_original_phase_and_live_session_identity_cannot_be_substituted(self):
        expected = phase_record()
        self.assertEqual(capture.validate_phase(expected, 1), Path("/test/ui-runtime"))
        for change in (lambda v: v.update(event="scripted_fixture"),
                       lambda v: v.update(sequence=2),
                       lambda v: v.update(session_pid=0),
                       lambda v: v["snapshot"].update(session_instance="different"),
                       lambda v: v.update(session_socket_path="/tmp/untrusted.sock"),
                       lambda v: v["ack"].update(phase="running")):
            value = copy.deepcopy(expected)
            change(value)
            with self.assertRaises(RuntimeError):
                capture.validate_phase(value, 1)

    def test_freshness_and_original_lifecycle_are_required(self):
        phase = phase_record(2)
        capture.compare_snapshot(phase["snapshot"], phase, 10_005)
        for mutation in (lambda v: v["hepta"]["last_observation"].update(sampled_unix_ms=100),
                         lambda v: v["hepta"]["last_observation"].update(sampled_unix_ms=10_006),
                         lambda v: v["hepta"]["last_observation"].update(current_generation=20),
                         lambda v: v["hepta"]["last_observation"]["health"].update(process_id=99),
                         lambda v: v["hepta"]["last_observation"]["health"].update(ready=False)):
            value = copy.deepcopy(phase["snapshot"])
            mutation(value)
            with self.assertRaises(RuntimeError):
                capture.compare_snapshot(value, phase, 10_005)

    def test_starting_accepts_real_async_readiness_and_event_progress_across_rpc_samples(self):
        # Same transition as the retained real capture01: Starting health gains
        # promotion_ready and the event window appends app_server_ready. These
        # contract values are synthetic; the failed real PNG is separate proof.
        phase = phase_record()
        baseline = phase["snapshot"]["hepta"]
        after = copy.deepcopy(phase["snapshot"])
        observed = after["hepta"]["last_observation"]
        observed["sampled_unix_ms"] = 10_003
        observed["health"]["promotion_ready"] = True
        ready_event = {"cursor": 3, "kind": "app_server_ready", "generation": None, "lifecycle": None}
        observed["events"].append(ready_event)
        observed.update(next_cursor=3, latest_cursor=3)
        capture.compare_snapshot(after, phase, 10_005, baseline)
        # Health and Events use separate RPCs: either intermediate view is
        # legitimate, and the later complete sample must preserve its prefix.
        for health_first in (True, False):
            intermediate = copy.deepcopy(phase["snapshot"])
            previous = intermediate["hepta"]["last_observation"]
            previous["sampled_unix_ms"] = 10_001
            if health_first:
                previous["health"]["promotion_ready"] = True
            else:
                previous["events"].append(ready_event)
                previous.update(next_cursor=3, latest_cursor=3)
            capture.compare_snapshot(intermediate, phase, 10_005, baseline)
            capture.compare_snapshot(after, phase, 10_005, intermediate["hepta"])

    def test_live_progress_cannot_rewrite_source_history_or_regress_after_actual_before(self):
        phase = phase_record()
        before = copy.deepcopy(phase["snapshot"])
        old = before["hepta"]["last_observation"]
        old["sampled_unix_ms"] = 10_002
        old["health"]["promotion_ready"] = True
        old["events"].append({"cursor": 3, "kind": "app_server_ready", "generation": None, "lifecycle": None})
        old.update(next_cursor=3, latest_cursor=3)
        capture.compare_snapshot(before, phase, 10_005)
        # Each mutation could otherwise hide behind the older held phase.
        for mutation in (
                lambda v: v["health"].update(promotion_ready=False),
                lambda v: v.update(sampled_unix_ms=10_001),
                lambda v: v.update(next_cursor=2),
                lambda v: v.update(latest_cursor=2),
                lambda v: v["events"][2].update(kind="rewritten"),
                lambda v: v["events"].pop(),
                lambda v: v["health"].update(process_id=99),
                lambda v: v["health"].update(fenced=True),
                lambda v: v["health"].update(promotion_ready=1),
                lambda v: v.update(agent_id="22222222-2222-4222-8222-222222222222"),
                lambda v: v.update(history_gap=True),
                lambda v: v.update(source_changed=True)):
            after = copy.deepcopy(before)
            mutation(after["hepta"]["last_observation"])
            with self.assertRaises(RuntimeError):
                capture.compare_snapshot(after, phase, 10_005, before["hepta"])
        for sequence, promotion in ((2, False), (3, True)):
            invalid = phase_record(sequence)
            invalid["snapshot"]["hepta"]["last_observation"]["health"]["promotion_ready"] = promotion
            with self.assertRaises(RuntimeError):
                capture.validate_phase(invalid, sequence)
        invalid = copy.deepcopy(phase["snapshot"])
        invalid["tasks"] = [{"unexpected": "host application"}]
        with self.assertRaises(RuntimeError):
            capture.compare_snapshot(invalid, phase, 10_005)

    def test_stale_retains_exact_old_observation_and_only_phase_five_replaces_session(self):
        previous = phase_record(3)
        stale = phase_record(4)
        capture.validate_phase(stale, 4, previous=previous)
        capture.compare_snapshot(stale["snapshot"], stale, 30_000)
        forged = copy.deepcopy(stale["snapshot"])
        forged["hepta"]["last_observation"]["sampled_unix_ms"] += 1
        with self.assertRaises(RuntimeError):
            capture.compare_snapshot(forged, stale, 30_000)
        replacement = phase_record(5, "replacement-session", 51)
        capture.validate_phase(replacement, 5, previous=stale)
        with self.assertRaises(RuntimeError):
            capture.validate_phase(phase_record(5), 5, previous=stale)
        with self.assertRaises(RuntimeError):
            capture.validate_phase(phase_record(4, "unexpected-replacement", 51), 4, previous=previous)
        stopped = phase_record(6, "replacement-session", 51)
        observed = stopped["snapshot"]["hepta"]["last_observation"]
        observed["health"].update(lifecycle="draining", ready=False, promotion_ready=False)
        observed["current_generation"] = observed["spawn_generation"] + 2
        capture.validate_phase(stopped, 6, previous=replacement)
        capture.compare_snapshot(stopped["snapshot"], stopped, 30_000)

    def test_ack_is_atomic_private_single_link_and_never_replaces_existing_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ack = phase_record()["ack"]
            capture.acknowledge(root, 1, ack)
            path = root / "ack-1.json"
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertEqual(json.loads(path.read_bytes()), ack)
            with self.assertRaises(FileExistsError):
                capture.acknowledge(root, 1, {"bad": "replacement"})
            self.assertEqual(json.loads(path.read_bytes()), ack)
            self.assertEqual([p.name for p in root.iterdir()], ["ack-1.json"])

    def test_phase_file_cannot_be_public_symlink_or_oversized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "phase-1.json"
            path.write_text(json.dumps(phase_record()))
            path.chmod(0o600)
            value, _ = capture.read_phase(path)
            self.assertEqual(value["sequence"], 1)
            path.chmod(0o644)
            with self.assertRaises(RuntimeError):
                capture.read_phase(path)
            path.chmod(0o600)
            link = root / "linked.json"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                capture.read_phase(link)
            path.write_bytes(b"x" * (capture.MAX_FRAME + 1))
            with self.assertRaises(RuntimeError):
                capture.read_phase(path)

    @unittest.skipUnless(sys.platform == "linux" and hasattr(os, "waitid"), "Linux child-death contract")
    def test_actual_exec_child_dies_when_its_capture_parent_is_killed(self):
        # This test process adopts only its own disposable grandchild so the
        # kernel's actual SIGKILL exit status can be checked after parent death.
        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        parent, target_pid, reaped = None, None, False
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target_ready, parent_ready = root / "target.json", root / "parent.json"
                target_code = ("import json,os,signal;from pathlib import Path;"
                    + f"Path({str(target_ready)!r}).write_text(json.dumps({{'pid':os.getpid(),'parent_pid':os.getppid(),'exec':os.readlink('/proc/self/exe')}}));"
                    + "signal.pause()")
                parent_code = ("import json,os,subprocess,time;from pathlib import Path;"
                    + f"p=subprocess.Popen([{sys.executable!r},'-B',{str(Path(capture.__file__).resolve())!r},"
                    + "'--parent-pid',str(os.getpid()),'--exec-child',"
                    + f"{sys.executable!r},'-B','-c',{target_code!r}],start_new_session=True);"
                    + f"Path({str(parent_ready)!r}).write_text(json.dumps({{'pid':os.getpid(),'child_pid':p.pid}}));"
                    + "time.sleep(20)")
                parent = subprocess.Popen([sys.executable, "-B", "-c", parent_code],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
                deadline = time.monotonic() + 5
                while not (target_ready.exists() and parent_ready.exists()):
                    self.assertIsNone(parent.poll(), "disposable capture parent exited early")
                    self.assertLess(time.monotonic(), deadline, "exec target readiness timeout")
                    time.sleep(0.01)
                target = json.loads(target_ready.read_text())
                creator = json.loads(parent_ready.read_text())
                target_pid = target["pid"]
                self.assertEqual(creator["pid"], parent.pid)
                self.assertEqual(creator["child_pid"], target_pid)
                self.assertEqual(target["parent_pid"], parent.pid)
                self.assertEqual(Path(target["exec"]).resolve(), Path(sys.executable).resolve())
                parent.kill()
                self.assertEqual(parent.wait(timeout=3), -signal.SIGKILL)
                deadline = time.monotonic() + 3
                while True:
                    exited = os.waitid(os.P_PID, target_pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
                    if exited is not None:
                        break
                    self.assertLess(time.monotonic(), deadline, "parent-bound target survived parent death")
                    time.sleep(0.01)
                self.assertEqual((exited.si_pid, exited.si_code, exited.si_status),
                    (target_pid, os.CLD_KILLED, signal.SIGKILL))
                os.waitpid(target_pid, 0)
                reaped = True
                print(json.dumps({"test": "fresh_exec_parent_death", "parent_pid": parent.pid,
                    "actual_exec_child_pid": target_pid, "target_executable": target["exec"],
                    "observed_si_code": exited.si_code, "observed_si_status": exited.si_status,
                    "child_reaped": True}))
        finally:
            if parent is not None and parent.poll() is None:
                parent.kill()
                parent.wait(timeout=3)
            if target_pid is not None and not reaped:
                # With the subreaper set and parent waited, this remains our
                # unreaped child, so its PID cannot be recycled before cleanup.
                try:
                    owned = os.waitid(os.P_PID, target_pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
                    if owned is None:
                        os.kill(target_pid, signal.SIGKILL)
                    os.waitpid(target_pid, 0)
                except ChildProcessError:
                    pass
            self.assertEqual(libc.prctl(36, previous.value, 0, 0, 0), 0)


if __name__ == "__main__":
    unittest.main()
