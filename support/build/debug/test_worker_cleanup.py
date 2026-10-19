#!/usr/bin/env python3
"""Host models for bounded worker cleanup; no kernel or VM."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import unittest

BUILD = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DEBUG = load(BUILD / "debug/run.py", "cleanup_debug")
REPRO = load(BUILD / "repro/run.py", "cleanup_repro")
FIXTURES = load(BUILD / "tests/test_kernel_runner.py", "cleanup_shell_fixtures")


class WorkerCleanupTests(unittest.TestCase):
    def setUp(self):
        self.fixture = FIXTURES.KernelRunnerTests("test_owned_manifest_removed_after_success")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.helper = self.fixture.build / "cleanup-manifest.py"
        self.helper_original = self.helper.read_bytes()

    def prepare(self, delay, status=None):
        self.helper.write_bytes(f"import time\ntime.sleep({delay!r})\n".encode() + self.helper_original)
        self.fixture.write_tool("make", """#!/usr/bin/python3
import json,os,sys,time
from pathlib import Path
if '--version' in sys.argv: print('GNU Make host cleanup model');raise SystemExit(0)
root=Path(os.environ['MOCK_PROJECT'])
(root/'make-ready.json').write_text(json.dumps({'pid':os.getpid(),'group':os.getpgrp()}))
ACTION
""".replace("ACTION", f"raise SystemExit({status})" if status is not None else "time.sleep(30)"))

    def ready(self, owned=None):
        path = self.fixture.root / "make-ready.json"
        deadline = time.monotonic() + 8
        while not path.exists():
            if owned is not None:
                self.assertFalse(owned.exited(), "owned host worker exited before publishing its manifest")
            self.assertLess(time.monotonic(), deadline, "host worker readiness deadline")
            time.sleep(.01)
        self.assertTrue((self.fixture.kernel / "OSDK.toml").is_file())
        return json.loads(path.read_text())

    def save(self, name, record):
        setting = os.environ.get("A01_WORKER_CLEANUP_OUT")
        if not setting:
            return
        destination = Path(setting) / name
        destination.mkdir(parents=True, exist_ok=False)
        record.update(kind="real_shell_and_cleanup_with_delayed_host_helper_no_kernel_no_vm",
            source_sha256={str(path.relative_to(BUILD)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in (BUILD / "debug/run.py", BUILD / "repro/run.py",
                                        BUILD / "kernel.sh", BUILD / "kernel-supervisor.py")})
        (destination / "observation.json").write_text(json.dumps(record, indent=2) + "\n")
        for path in self.fixture.root.rglob("*"):
            if path.is_file() and (path.name in ("console.log", "manifest-cleanup.json",
                    "manifest-cleanup-exit-code.txt", "run-exit-code.txt", "make-ready.json")
                    or path.name.endswith(".command.json")):
                (destination / str(path.relative_to(self.fixture.root)).replace("/", "-")).write_bytes(path.read_bytes())

    def private(self, name, delay, *, repro=False, status=None, residue=False):
        self.prepare(delay, status)
        fixture = self.fixture
        owned, record = None, {"helper_delay_seconds": delay, "requested_child_status": status}
        with DEBUG.workspace_lock(fixture.root) as descriptor:
            environment = dict(fixture.environment, A01_KERNEL_WORKER="1",
                A01_KERNEL_LOCK_FD=str(descriptor), A01_RUN_DIR=str(fixture.root / "evidence"))
            command = ["bash", str(fixture.build / "kernel.sh"), "kernel"]
            try:
                start = time.monotonic()
                if repro:
                    notifier_error = []
                    def notify():
                        try:
                            self.ready()
                            os.kill(os.getpid(), signal.SIGTERM)
                        except BaseException as error:
                            notifier_error.append(str(error))
                    with REPRO.lifecycle.interruption_handlers() as shutdown:
                        notifier = threading.Thread(target=notify)
                        notifier.start()
                        receipt = REPRO.owned_command(command, cwd=fixture.root, env=environment,
                            log=fixture.root / "console.log", shutdown=shutdown, pass_fds=(descriptor,))
                        notifier.join(timeout=10)
                        self.assertFalse(notifier.is_alive())
                        self.assertEqual(notifier_error, [])
                    raw = receipt["raw_exit_code"]
                    reaped = receipt["group_cleanup"]["leader_reaped"]
                    self.assertEqual(receipt["exit_code"], 143)
                    record["command_receipt"] = receipt
                else:
                    with (fixture.root / "console.log").open("wb") as output:
                        owned = DEBUG.OwnedSession(command, cwd=fixture.root, env=environment,
                                                   output=output, pass_fds=(descriptor,))
                        self.ready(owned if status is None else None)
                        if status is None:
                            raw = owned.stop()
                        else:
                            raw = owned.wait(8)
                        reaped = owned.reaped
                elapsed = time.monotonic() - start
                manifest = fixture.kernel / "OSDK.toml"
                record.update(raw_status=raw, elapsed_seconds=elapsed, leader_reaped=reaped,
                              manifest_present_after_stop=manifest.exists())
                self.assertTrue(reaped)
                if residue:
                    # A finite budget cannot guarantee arbitrary slow cleanup.
                    # Keep observed residue and prove the next runner refuses
                    # to overwrite it; there is no automatic deletion.
                    self.assertEqual(raw, -signal.SIGKILL)
                    self.assertTrue(manifest.is_file())
                    before = manifest.read_bytes()
                    self.helper.write_bytes(self.helper_original)
                    retry = fixture.run_runner(name="retry", pass_fds=(descriptor,), extra={
                        "A01_KERNEL_WORKER": "1", "A01_KERNEL_LOCK_FD": str(descriptor)})
                    record.update(retry_status=retry.returncode, retry_log=retry.stdout,
                                  residue_preserved=manifest.read_bytes() == before)
                    self.assertNotEqual(retry.returncode, 0)
                    self.assertEqual(manifest.read_bytes(), before)
                else:
                    normalized = raw if raw >= 0 else 128 - raw
                    self.assertEqual(normalized, status if status is not None else 143)
                    self.assertFalse(manifest.exists())
                    self.assertEqual((fixture.root / "evidence/manifest-cleanup-exit-code.txt").read_text().strip(), "0")
                    cleanup = json.loads((fixture.root / "evidence/manifest-cleanup.json").read_text())
                    self.assertTrue(cleanup["passed"])
                    record["manifest_cleanup"] = cleanup
                record["passed"] = True
            finally:
                if owned is not None:
                    owned.stop()
                self.save(name, record)

    def test_debug_private_worker_allows_delayed_exit_cleanup(self):
        self.private("debug-delayed", .6)

    def test_repro_cancel_allows_delayed_exit_cleanup_and_returns_143(self):
        self.private("repro-delayed", .6, repro=True)

    def test_original_status_37_survives_delayed_exit_cleanup(self):
        self.private("status37-delayed", .6, status=37)

    def test_cleanup_beyond_bounded_grace_keeps_residue_and_next_run_refuses_it(self):
        self.private("bounded-residue", 3.0, residue=True)

    def test_public_supervisor_allows_delayed_exit_cleanup(self):
        self.prepare(.6)
        fixture = self.fixture
        process = None
        record = {"helper_delay_seconds": .6}
        try:
            environment = dict(fixture.environment, A01_RUN_DIR=str(fixture.root / "evidence"))
            with (fixture.root / "console.log").open("wb") as log:
                process = subprocess.Popen(["bash", str(fixture.build / "kernel.sh"), "kernel"],
                    env=environment, stdout=log, stderr=subprocess.STDOUT)
                self.ready()
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=8)
            record.update(status=process.returncode,
                          manifest_present_after_stop=(fixture.kernel / "OSDK.toml").exists())
            self.assertEqual(process.returncode, 143)
            self.assertFalse(record["manifest_present_after_stop"])
            receipts = [json.loads(line.removeprefix("A01_KERNEL_SUPERVISOR "))
                for line in (fixture.root / "console.log").read_text().splitlines()
                if line.startswith("A01_KERNEL_SUPERVISOR ")]
            self.assertEqual(len(receipts), 1)
            self.assertTrue(receipts[0]["worker_reaped"])
            record["receipt"] = receipts[0]
            record["passed"] = True
        finally:
            if process is not None and process.poll() is None:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=8)
            self.save("public-delayed", record)


if __name__ == "__main__":
    unittest.main()
