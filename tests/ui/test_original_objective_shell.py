#!/usr/bin/env python3
"""Capture validator checks only; these records never qualify original runtime or pixels.

No test starts a Shell, Xvfb, Agentd or a fake Session. The single Unix socket
case proves that a mismatched real kernel peer is refused before a request.
"""

import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("objective_shell_capture_contract",
    Path(__file__).with_name("probe-original-objective-shell.py"))
capture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture)


def validator_phases():
    """Synthetic values for pure acceptance predicates, never renderer input."""
    run = {"run_id": "run.desktop-compiled", "revision": 1, "phase": "admitted",
        "authority_epoch": 1, "generation": 2, "terminal_observed": False, "idempotent": False}
    old_owner = {"agent_id": "33333333-3333-4333-8333-333333333333",
        "spawn_generation": 1, "process_id": 3001, "active": True, "healthy": True}
    new_owner = dict(old_owner, spawn_generation=4, process_id=3002)
    runtime = "/tmp/ho-validator-only/objective-ui"
    old_observation = {"agent_id": old_owner["agent_id"], "spawn_generation": 1,
        "current_generation": 2, "sampled_unix_ms": 10_000,
        "health": {"process_id": 3001, "lifecycle": "running", "ready": True,
            "promotion_ready": True, "fenced": False},
        "events": [], "capabilities": [], "capabilities_truncated": False,
        "events_omitted_from_view": 0, "next_cursor": 0, "latest_cursor": 0,
        "history_gap": False, "source_changed": False}
    result = []
    for sequence, name in enumerate(capture.PHASES, 1):
        instance = ("b" if sequence == 3 else "a") * 32
        observation = copy.deepcopy(old_observation)
        if sequence == 3:
            observation.update(spawn_generation=4, current_generation=5, sampled_unix_ms=40_000)
            observation["health"]["process_id"] = 3002
        sampled = dict(run, sampled_unix_ms=10_000, observation_sequence=2) if sequence < 3 else None
        projection = {"run_id": run["run_id"],
            "connection": ("observed", "stale", "projection_missing")[sequence - 1],
            "last_attempt_unix_ms": 10_000 if sequence < 3 else 40_000,
            "last_observation": sampled, "observation_gap": sequence == 2,
            "error_code": (None, "generation_fenced", "run_projection_missing")[sequence - 1]}
        if sequence < 3:
            projection["sample_age_at_snapshot_ms"] = 1 if sequence == 1 else 20_001
        snapshot = {"type": "snapshot", "tasks": [], "session_instance": instance,
            "hepta": {"connection": "stale" if sequence == 2 else "observed",
                "last_attempt_unix_ms": (10_000, 30_000, 40_000)[sequence - 1],
                "error_code": "generation_fenced" if sequence == 2 else None,
                "last_observation": observation, "run": projection}}
        result.append({"event": "objective_session_phase_observed", "sequence": sequence,
            "phase": name, "session_pid": 2010 if sequence == 3 else 2001,
            "worker_tid": 2011 if sequence == 3 else 2002, "session_instance": instance,
            "runtime_dir": runtime, "session_socket_path": runtime + "/trillionnium-ui/session.sock",
            "recorded_unix_ms": (10_001, 30_001, 40_001)[sequence - 1],
            "snapshot": snapshot, "original": copy.deepcopy(old_owner if sequence == 1 else new_owner),
            "ack": {"sequence": sequence, "phase": name, "session_instance": instance},
            "ack_timeout_seconds": 120, "capture_ack_is_coordination_only": True,
            "evidence": {}})
    result[0]["evidence"]["original_run"] = copy.deepcopy(run)
    result[1]["evidence"]["retained_run_unchanged_across_failed_samples"] = True
    result[2]["evidence"] = {"historical_admission_still_requires_original_journal": True,
        "missing_projection_is_not_non_admission": True}
    return result


class ObjectiveShellContract(unittest.TestCase):
    def test_exact_three_phases_and_before_after_snapshots(self):
        previous = None
        runtime = None
        for sequence, phase in enumerate(validator_phases(), 1):
            runtime = capture.validate_phase(phase, sequence, runtime, previous)
            capture.compare_snapshot(phase["snapshot"], phase, phase["recorded_unix_ms"] + 5)
            capture.compare_snapshot(phase["snapshot"], phase, phase["recorded_unix_ms"] + 10,
                copy.deepcopy(phase["snapshot"]["hepta"]))
            previous = phase

    def test_phase_and_owner_identity_cannot_be_substituted(self):
        first = validator_phases()[0]
        for change in (
                lambda value: value.update(event="fixture"),
                lambda value: value.update(sequence=2),
                lambda value: value.update(session_pid=0),
                lambda value: value.update(worker_tid=0),
                lambda value: value.update(ack_timeout_seconds=0),
                lambda value: value["snapshot"].update(session_instance="f" * 32),
                lambda value: value.update(session_socket_path="/tmp/unrelated.sock"),
                lambda value: value["ack"].update(phase="different"),
                lambda value: value["original"].update(process_id=3999),
                lambda value: value["snapshot"]["hepta"]["last_observation"]["health"].update(fenced=True),
                lambda value: value["snapshot"].update(tasks=[{"id": "unexpected-task"}])):
            with self.subTest(change=change):
                changed = copy.deepcopy(first)
                change(changed)
                with self.assertRaises(RuntimeError):
                    capture.validate_phase(changed, 1)

    def test_every_original_run_field_is_bound_to_the_direct_owner_read(self):
        for field, wrong in (("run_id", "run.other"), ("revision", 2), ("phase", "completed"),
                ("authority_epoch", 2), ("generation", 9), ("terminal_observed", True), ("idempotent", True)):
            with self.subTest(field=field):
                phase = validator_phases()[0]
                phase["snapshot"]["hepta"]["run"]["last_observation"][field] = wrong
                with self.assertRaises(RuntimeError):
                    capture.validate_phase(phase, 1)

    def test_fresh_runtime_health_cannot_renew_an_old_run_sample(self):
        first = validator_phases()[0]
        actual = copy.deepcopy(first["snapshot"])
        actual["hepta"]["last_attempt_unix_ms"] = 30_000
        actual["hepta"]["last_observation"]["sampled_unix_ms"] = 30_000
        actual["hepta"]["run"]["last_attempt_unix_ms"] = 30_000
        with self.assertRaises(RuntimeError):
            capture.compare_snapshot(actual, first, 30_005)
        # A new completed RPC cannot move the independently sampled payload into the future.
        actual["hepta"]["run"]["last_observation"].update(sampled_unix_ms=30_006, observation_sequence=3)
        actual["hepta"]["run"]["last_attempt_unix_ms"] = 30_006
        with self.assertRaises(RuntimeError):
            capture.compare_snapshot(actual, first, 30_005)
        actual = copy.deepcopy(first["snapshot"])
        actual["hepta"]["run"]["sample_age_at_snapshot_ms"] = 7000
        with self.assertRaises(RuntimeError):
            capture.compare_snapshot(actual, first, 10_005, transport_elapsed_ms=1)

    def test_stale_history_and_retained_attempt_do_not_become_new_samples(self):
        first, stale, replacement = validator_phases()
        capture.validate_phase(stale, 2, previous=first)
        advancing_age = copy.deepcopy(stale["snapshot"])
        advancing_age["hepta"]["run"]["sample_age_at_snapshot_ms"] += 5
        capture.compare_snapshot(advancing_age, stale, 30_005, stale["snapshot"]["hepta"])
        for change in (
                lambda value: value["hepta"]["run"].update(last_attempt_unix_ms=30_000),
                lambda value: value["hepta"]["run"]["last_observation"].update(sampled_unix_ms=10_001),
                lambda value: value["hepta"]["run"]["last_observation"].update(observation_sequence=3),
                lambda value: value["hepta"]["last_observation"].update(sampled_unix_ms=30_000),
                lambda value: value["hepta"]["run"].update(sample_age_at_snapshot_ms=20_000),
                lambda value: value["hepta"]["run"].update(observation_gap=False)):
            changed = copy.deepcopy(stale["snapshot"])
            change(changed)
            with self.assertRaises(RuntimeError):
                capture.compare_snapshot(changed, stale, 30_005, stale["snapshot"]["hepta"])
        capture.validate_phase(replacement, 3, previous=stale)

    def test_only_explicit_replacement_changes_session_and_keeps_one_runtime(self):
        first, stale, replacement = validator_phases()
        for field, wrong in (("session_pid", 2050), ("worker_tid", 2051), ("session_instance", "c" * 32)):
            changed = copy.deepcopy(stale)
            changed[field] = wrong
            if field == "session_instance":
                changed["snapshot"]["session_instance"] = wrong
                changed["ack"]["session_instance"] = wrong
            with self.assertRaises(RuntimeError):
                capture.validate_phase(changed, 2, previous=first)
        changed = copy.deepcopy(replacement)
        changed["runtime_dir"] = "/tmp/ho-another/objective-ui"
        changed["session_socket_path"] = changed["runtime_dir"] + "/trillionnium-ui/session.sock"
        with self.assertRaises(RuntimeError):
            capture.validate_phase(changed, 3, Path(first["runtime_dir"]), stale)
        changed = copy.deepcopy(replacement)
        changed["session_pid"] = stale["session_pid"]
        with self.assertRaises(RuntimeError):
            capture.validate_phase(changed, 3, previous=stale)

    def test_missing_current_projection_cannot_erase_or_reinvent_historical_admission(self):
        first, stale, replacement = validator_phases()
        for change in (
                lambda value: value["snapshot"]["hepta"]["run"].update(last_observation=first["snapshot"]["hepta"]["run"]["last_observation"]),
                lambda value: value["snapshot"]["hepta"]["run"].update(observation_gap=True),
                lambda value: value["snapshot"]["hepta"]["run"].update(sample_age_at_snapshot_ms=0),
                lambda value: value["snapshot"]["hepta"]["run"].update(error_code="not_admitted"),
                lambda value: value["evidence"].update(missing_projection_is_not_non_admission=False),
                lambda value: value["evidence"].update(historical_admission_still_requires_original_journal=False)):
            changed = copy.deepcopy(replacement)
            change(changed)
            with self.assertRaises(RuntimeError):
                capture.validate_phase(changed, 3, previous=stale)

    def test_phase_is_private_single_link_and_bounded_and_ack_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            phase = validator_phases()[0]
            path = root / "phase-1.json"
            path.write_text(json.dumps(phase))
            path.chmod(0o600)
            self.assertEqual(capture.read_phase(path)[0], phase)
            link = root / "hardlink.json"
            os.link(path, link)
            with self.assertRaises(RuntimeError):
                capture.read_phase(path)
            link.unlink()
            link.symlink_to(path)
            with self.assertRaises(OSError):
                capture.read_phase(link)
            path.chmod(0o644)
            with self.assertRaises(RuntimeError):
                capture.read_phase(path)
            path.chmod(0o600)
            path.write_bytes(b"x" * (capture.MAX_FRAME + 1))
            with self.assertRaises(RuntimeError):
                capture.read_phase(path)
            capture.acknowledge(root, 1, phase["ack"])
            self.assertEqual(json.loads((root / "ack-1.json").read_bytes()), phase["ack"])
            self.assertEqual((root / "ack-1.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                capture.acknowledge(root, 1, {"different": "ack"})

    @unittest.skipUnless(sys.platform == "linux" and hasattr(socket, "SO_PEERCRED"), "Linux peer identity")
    def test_actual_kernel_peer_mismatch_is_refused_before_snapshot_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "peer.sock"
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(str(path))
                path.chmod(0o600)
                listener.listen(1)
                listener.settimeout(1)
                phase = {"session_socket_path": str(path), "session_pid": os.getpid() + 1}
                with self.assertRaisesRegex(RuntimeError, "kernel peer identity"):
                    capture.actual_snapshot(phase, root, "must-not-be-written")
                accepted, _ = listener.accept()
                with accepted:
                    accepted.settimeout(1)
                    self.assertEqual(accepted.recv(1), b"")
                self.assertFalse((root / "must-not-be-written.snapshot.json").exists())

    def test_host_manifest_cannot_be_replaced_by_an_unrelated_or_changed_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(RuntimeError):
                capture.host_dependencies(root, root / "missing-shell")
            path = root / "validator-only-file"
            path.write_bytes(b"first")
            record = {"files": {str(path): {"bytes": path.stat().st_size, "sha256": capture.digest(path)}}}
            capture.verify_dependency_files(record)
            path.write_bytes(b"other")
            with self.assertRaises(RuntimeError):
                capture.verify_dependency_files(record)


if __name__ == "__main__":
    unittest.main()
