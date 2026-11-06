"""Real Linux negative controls; these do not simulate a Pocket4 restart."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("successor_under_test", HERE / "successor_runtime.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
R.E = R.load_module((HERE / "framework_epoch.py").read_bytes(), "test_frozen_epoch", str(HERE / "framework_epoch.py"))
R.H = R.load_module((HERE / "held_runtime_r5.py").read_bytes(), "test_frozen_held", str(HERE / "held_runtime_r5.py"))


def pin(path):
    data = Path(path).read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class RecoveryControls(unittest.TestCase):
    def test_pidfd_distinguishes_actual_child_exit_from_live_parent(self):
        child = subprocess.Popen([sys.executable, "-B", "-I", "-c", "import signal;signal.pause()"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        child_fd = os.pidfd_open(child.pid)
        own_fd = os.pidfd_open(os.getpid())
        try:
            self.assertFalse(R.pidfd_dead(child_fd))
            self.assertFalse(R.pidfd_dead(own_fd))
            child.terminate()
            child.wait(timeout=3)
            self.assertTrue(R.pidfd_dead(child_fd))
            self.assertFalse(R.pidfd_dead(own_fd))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            os.close(child_fd)
            os.close(own_fd)

    def test_existing_flock_is_not_bypassed_or_recreated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flow.lock"
            path.write_bytes(b"")
            before = path.stat()
            holder = os.open(path, os.O_RDWR)
            pool = R.FDs()
            try:
                fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
                contender = pool.own(os.open(path, os.O_RDWR))
                with self.assertRaisesRegex(R.Rejected, "OTHER_ACTION_OR_FLOW_LEASE_ACTIVE"):
                    R.take_exclusive_lock(contender)
                if os.getuid() != 0:
                    with self.assertRaisesRegex(R.Rejected, "EXISTING_LOCK_FILE_REQUIRED"):
                        R.acquire_lock(pool, str(path))
                self.assertEqual(path.stat().st_ino, before.st_ino)
            finally:
                pool.close_all()
                os.close(holder)

    def test_held_artifact_replacement_is_detected_even_for_equal_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact"
            path.write_bytes(b"identical bytes")
            pool = R.FDs()
            root = pool.own(os.open(directory, os.O_PATH | os.O_DIRECTORY))
            old = pool.own(os.open(path, os.O_RDONLY))
            expected = R.metadata(old)
            replacement = Path(directory) / "replacement"
            replacement.write_bytes(path.read_bytes())
            os.replace(replacement, path)
            try:
                with self.assertRaisesRegex(R.Rejected, "OBSERVED_ARTIFACT_PATH_REPLACED"):
                    R.check_path(pool, root, "/artifact", expected)
            finally:
                pool.close_all()

    def test_live_reviewed_worker_blocks_before_flow_or_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "connector-terminal-receipt.json"
            source.write_text('{"status":"example review input, not runtime proof"}')
            own = R.E.process_identity(os.getpid())
            record = {"schema": "pocket4-owned-worker-drain-v1", "boot_id": R.boot_id(),
                      "reviewed_monotonic_ns": time.monotonic_ns(), "unresolved_start_attempts": [],
                      "workers": [{"host_pid": own["host_pid"], "start_ticks": own["start_ticks"]}],
                      "flow_locks": [], "source_receipts": [pin(source)],
                      "review_scope": "all-known-pocket4-UI-install-observer-restart-jobs"}
            path = Path(directory) / "review.json"
            path.write_bytes(R.canonical(record))
            pool = R.FDs()
            try:
                with self.assertRaisesRegex(R.Rejected, "KNOWN_WORKER_STILL_ALIVE"):
                    R.reviewed_drain(pool, pin(path))
            finally:
                pool.close_all()

    def test_unknown_start_attempt_cannot_be_presented_as_drained(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            value = {"schema": "pocket4-owned-worker-drain-v1", "boot_id": R.boot_id(),
                     "reviewed_monotonic_ns": time.monotonic_ns(), "unresolved_start_attempts": ["timed-out-shell-start"],
                     "workers": [], "flow_locks": [], "source_receipts": [],
                     "review_scope": "all-known-pocket4-UI-install-observer-restart-jobs"}
            path.write_bytes(R.canonical(value))
            pool = R.FDs()
            try:
                with self.assertRaisesRegex(R.Rejected, "REVIEWED_COMPLETE_WORKER_DRAIN_REQUIRED"):
                    R.reviewed_drain(pool, pin(path))
            finally:
                pool.close_all()

    def test_success_text_does_not_override_failed_native_client(self):
        body = R.canonical({"ok": True, "state": "running", "host_pid": 123})
        for command in ({"complete": False, "joined": True, "returncode": 0},
                        {"complete": True, "joined": False, "returncode": 0},
                        {"complete": True, "joined": True, "returncode": 1}):
            with self.subTest(command=command), self.assertRaisesRegex(R.Rejected, "NATIVE_CLIENT_NOT_JOINED_SUCCESSFULLY"):
                R.native_running(body, command)

    def test_timestamp_span_cannot_hide_framework_generation_change(self):
        samples = [{"binding": {"processes": {"system_server": {"start_ticks": ticks}}},
                    "collected_monotonic_ns": when}
                   for ticks, when in ((100, 1), (100, 5_000_000_001), (101, 10_000_000_001))]
        with self.assertRaisesRegex(R.Rejected, "SAMPLED_PROCESS_IDENTITIES_CHANGED"):
            R.validate_span(samples)
        for sample in samples:
            sample["binding"]["processes"]["system_server"]["start_ticks"] = 100
        self.assertEqual(R.validate_span(samples), [1, 5_000_000_001, 10_000_000_001])
        samples[-1]["collected_monotonic_ns"] = 9_999_999_999
        with self.assertRaisesRegex(R.Rejected, "EXPLICIT_TEN_TO_NINETY_SECOND_OBSERVATION_REQUIRED"):
            R.validate_span(samples)

    def test_source_manifest_cannot_reauthorize_modified_frozen_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            files = {}
            for name in R.SOURCE_NAMES:
                content = (HERE / name).read_bytes()
                if name == "framework_epoch.py":
                    content += b"\n# tampered frozen reference\n"
                (base / name).write_bytes(content)
                files[name] = {"bytes": len(content), "sha256": R.digest(content)}
            manifest = R.canonical({"schema": "pocket4-successor-source-v1", "files": files})
            (base / "SOURCE_PINS.json").write_bytes(manifest)
            with self.assertRaisesRegex(R.Rejected, "FROZEN_READER_SOURCE_CHANGED"):
                R.configure(directory, R.digest(manifest))

    def test_generated_guard_bootstrap_rejects_symlink_and_detects_pin_change(self):
        with tempfile.TemporaryDirectory() as directory:
            source = R.guard_source(directory, "a" * 64, {}, {})
            module = R.load_module(source, "test_generated_guard", directory + "/guard.py")
            path = Path(directory) / "exact"
            path.write_bytes(b"exact source")
            self.assertEqual(module._read(str(path), 64, R.digest(b"exact source")), b"exact source")
            with self.assertRaisesRegex(RuntimeError, "GUARD_PIN"):
                module._read(str(path), 64, "a" * 64)
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                module._read(str(link), 64, R.digest(b"exact source"))

    def test_bounded_child_timeout_joins_owned_child(self):
        _, _, record = R.bounded_child([sys.executable, "-B", "-I", "-c", "import signal;signal.pause()"], seconds=0.1)
        self.assertFalse(record["complete"])
        self.assertTrue(record["termination_attempted"])
        self.assertTrue(record["joined"])
        with self.assertRaises(FileNotFoundError):
            os.stat("/proc/" + str(record["host_pid"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
