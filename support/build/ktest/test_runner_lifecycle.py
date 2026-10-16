"""Host-only ownership checks; fixtures do not execute Cargo, Rust or QEMU."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
PYTHON = [sys.executable, "-I"] + (["-O"] if sys.flags.optimize else [])
SPEC = importlib.util.spec_from_file_location("ktest_runner_lifecycle", HERE / "run.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)

# One copied fixture handles every pipeline stage, including metadata commands.
# Its descendant owns a TCP lease and ignores TERM, forcing group KILL cleanup.
FIXTURE = r'''
import json, os, shutil, signal, socket, subprocess, sys, time
from pathlib import Path
root = Path(os.environ['FIXTURE_ROOT'])
with (root/'tool-invocations.jsonl').open('a') as trace:
    trace.write(json.dumps({'file':__file__, 'argv':sys.argv})+'\n')
if '--descendant' in sys.argv:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    lease = socket.socket(); lease.bind(('127.0.0.1', 0)); lease.listen()
    (root/'descendant.json').write_text(json.dumps({'pid':os.getpid(), 'address':lease.getsockname()}))
    time.sleep(60)
    raise SystemExit(0)
name = Path(__file__).name
if name == 'verify-source.py': stage = 'verify'
elif name == 'check.py': stage = 'checker'
elif name == 'rustc': stage = 'rustc-version'
elif name == 'git': stage = 'git-head' if 'rev-parse' in sys.argv else 'git-status'
elif 'install' in sys.argv: stage = 'install'
elif '-Vv' in sys.argv: stage = 'cargo-version'
else: stage = 'cargo-test'
if stage == os.environ.get('FIXTURE_STAGE'):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    descendant = subprocess.Popen([sys.executable, '-I', __file__, '--descendant'])
    deadline = time.monotonic() + 5
    while not (root/'descendant.json').exists():
        if time.monotonic() > deadline: raise RuntimeError('descendant not ready')
        time.sleep(.01)
    info = json.loads((root/'descendant.json').read_text())
    info.update(leader=os.getpid(), descendant_popen_pid=descendant.pid, stage=stage)
    (root/'ready.json').write_text(json.dumps(info))
    while not (root/'proceed').exists(): time.sleep(.01)
    raise SystemExit(int(os.environ.get('FIXTURE_EXIT_CODE', '0')))
if stage == 'cargo-test':
    target = Path(os.environ['CARGO_TARGET_DIR'])/'osdk'/(os.environ['A01_KTEST_CRATE']+'-test-base')
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(os.environ['OSDK_CARGO_LOCK'], target/'Cargo.lock')
    Path(os.environ['A01_KTEST_GUESTS']).mkdir()
if stage in ('verify', 'checker'): print(json.dumps({'passed':True, 'fixture_only':True}))
elif stage == 'git-head': print('fixture-head')
elif stage == 'git-status': print('')
else: print('host-only fixture: '+stage)
'''

WRAPPER = r'''
import importlib.util, json, os, signal, sys, time
from pathlib import Path
path, seam = sys.argv[1:3]
sys.argv = [path] + sys.argv[3:]
spec = importlib.util.spec_from_file_location('copied_runner', path)
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
root = Path(os.environ['FIXTURE_ROOT'])
real_popen, real_stop, real_killpg = runner.subprocess.Popen, runner.OwnedSession.stop, runner.os.killpg
real_write = Path.write_text
fired = False

def inject():
    global fired
    fired = True
    (root/'seam-fired').write_text(seam)
    os.kill(os.getpid(), signal.SIGTERM)

def popen(*args, **kwargs):
    process = real_popen(*args, **kwargs)
    if seam == 'publication' and not fired:
        deadline = time.monotonic() + 5
        while not (root/'ready.json').exists():
            if time.monotonic()>deadline: raise RuntimeError('publication fixture not ready')
            time.sleep(.01)
        inject()
        os.kill(os.getpid(), signal.SIGINT)
    return process

def stop(self, *args, **kwargs):
    if seam in ('cleanup-entry', 'normal-cleanup') and not fired: inject()
    return real_stop(self, *args, **kwargs)

def killpg(pid, number):
    result = real_killpg(pid, number)
    if seam == 'between-signals' and not fired and number == signal.SIGTERM: inject()
    return result

def write_text(self, data, *args, **kwargs):
    result = real_write(self, data, *args, **kwargs)
    if seam == 'result-publication' and not fired and self == root/'output/result.json' and json.loads(data).get('passed'):
        inject()
    return result

runner.subprocess.Popen = popen
runner.OwnedSession.stop = stop
runner.os.killpg = killpg
Path.write_text = write_text
raise SystemExit(runner.main())
'''


class RunnerLifecycleTests(unittest.TestCase):
    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            self.assertLess(time.monotonic(), deadline, "fixture readiness deadline expired")
            time.sleep(.01)

    def fixture(self, root):
        project = root / "project"
        here = project / "support/build/ktest"
        here.mkdir(parents=True)
        shutil.copyfile(HERE / "run.py", here / "run.py")
        for name in ("verify-source.py", "ktest/check.py"):
            (project / "support/build" / name).write_text(FIXTURE)
        for crate in RUNNER.CRATES:
            directory = project / "kernel/asterinas" / RUNNER.CRATES[crate]
            directory.mkdir(parents=True, exist_ok=True)
            (here / "locks").mkdir(exist_ok=True)
            (here / "locks" / (crate + ".Cargo.lock")).write_text("fixture fixed lock\n")
        build = project / "kernel/asterinas/osdk/src/commands/build/mod.rs"
        build.parent.mkdir(parents=True)
        build.write_text("host fixture input\n")
        bin_path = root / "cargo/bin"
        bin_path.mkdir(parents=True)
        for name in ("cargo", "rustc", "git"):
            executable = bin_path / name
            executable.write_text("#!" + sys.executable + "\n" + FIXTURE)
            executable.chmod(0o755)
        (bin_path / "cargo-osdk").write_text("fixture source-built marker\n")
        vdso = root / "vdso"
        vdso.mkdir()
        (vdso / "vdso_x86_64.so").write_text("fixture vdso\n")
        env = os.environ | {"FIXTURE_ROOT": str(root), "CARGO_HOME": str(root / "cargo"),
                            "VDSO_LIBRARY_DIR": str(vdso)}
        argv = PYTHON + [str(here / "run.py"), "--output", str(root / "output"), "--crate", "ostd"]
        return project, argv, env

    def lock_free(self, project):
        with (project / "support/build/out-kernel.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            return True

    def exercise_cancel(self, stage="verify", first=signal.SIGTERM, seam="", normal=False, leader_status=0):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, argv, env = self.fixture(root)
            env["FIXTURE_STAGE"] = stage
            env["FIXTURE_EXIT_CODE"] = str(leader_status)
            if seam:
                argv = PYTHON + ["-c", WRAPPER, str(project/"support/build/ktest/run.py"), seam] + argv[len(PYTHON)+1:]
            descriptors = []
            with (root / "console.log").open("wb") as output:
                worker = subprocess.Popen(argv, env=env, stdout=output, stderr=subprocess.STDOUT,
                                          start_new_session=True)
                try:
                    self.wait_for((root / "ready.json").exists)
                    info = json.loads((root / "ready.json").read_text())
                    self.assertEqual(info["pid"], info["descendant_popen_pid"])
                    descriptors = [os.pidfd_open(info[key]) for key in ("leader", "pid")]
                    self.assertTrue(all(not select.select([fd], [], [], 0)[0] for fd in descriptors))
                    self.assertFalse(self.lock_free(project))
                    with socket.socket() as lease:
                        with self.assertRaises(OSError):
                            lease.bind(tuple(info["address"]))
                    if normal:
                        (root / "proceed").write_text("exit leader\n")
                    elif seam != "publication":
                        worker.send_signal(first)
                    cancelled_run = not normal or bool(seam)
                    expected = 128 + (signal.SIGTERM if seam in ("publication", "normal-cleanup") else first) \
                        if cancelled_run else 1 if leader_status else 0
                    self.assertEqual(worker.wait(timeout=8), expected, (root / "console.log").read_text())
                    for descriptor in descriptors:
                        self.assertTrue(select.select([descriptor], [], [], 2)[0], "owned fixture survived cleanup")
                    with socket.socket() as lease:
                        lease.bind(tuple(info["address"]))
                    self.assertTrue(self.lock_free(project))
                    result = json.loads((root / "output/result.json").read_text())
                    self.assertEqual(result["runner_sha256"], hashlib.sha256((project/"support/build/ktest/run.py").read_bytes()).hexdigest())
                    self.assertEqual(len(result["command_receipts"]), len(list((root/"output").rglob("*.command.json"))))
                    self.assertEqual(result["passed"], not cancelled_run and leader_status == 0)
                    if cancelled_run:
                        self.assertEqual(result["exit_code"], expected)
                    records = [json.loads(path.read_text()) for path in (root / "output").rglob("*.command.json")]
                    cancelled = [record for record in records if record.get("interrupted_by")]
                    self.assertEqual(len(cancelled), int(cancelled_run))
                    observed = cancelled[0] if cancelled_run else json.loads((root/"output/source-inputs.json.command.json").read_text())
                    self.assertEqual(observed["exit_code"], expected if cancelled_run else leader_status)
                    self.assertEqual(observed["raw_exit_code"], observed["group_cleanup"]["leader_exit_code"])
                    if not cancelled_run:
                        self.assertEqual(observed["raw_exit_code"], leader_status)
                    self.assertTrue(observed["group_cleanup"]["leader_reaped"])
                    self.assertFalse(observed["group_cleanup"]["external_reap_disarmed"])
                    if seam:
                        self.assertTrue((root / "seam-fired").exists())
                        expected_signals = ["SIGTERM", "SIGINT"] if seam == "publication" else \
                            ["SIGTERM"] if seam == "normal-cleanup" else ["SIGINT", "SIGTERM"]
                        self.assertEqual(result["received_signals"], expected_signals)
                finally:
                    if worker.poll() is None:
                        worker.kill()
                        worker.wait(timeout=5)
                    for descriptor in descriptors:
                        try:
                            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        os.close(descriptor)

    def test_sigterm_owns_every_pipeline_subprocess_including_metadata(self):
        for stage in ("verify", "install", "rustc-version", "cargo-version", "git-head", "git-status", "cargo-test", "checker"):
            with self.subTest(stage=stage):
                self.exercise_cancel(stage)

    def test_successful_leader_exit_cleans_remaining_descendant(self):
        self.exercise_cancel(normal=True)

    def test_failed_leader_exit_cleans_remaining_descendant_and_keeps_failure(self):
        self.exercise_cancel(normal=True, leader_status=7)

    def test_sigint_cleans_group_and_preserves_first_status(self):
        self.exercise_cancel(first=signal.SIGINT)

    def test_repeated_signals_during_popen_publication_are_deferred(self):
        self.exercise_cancel(seam="publication")

    def test_repeated_signal_at_cleanup_entry_cannot_skip_cleanup(self):
        self.exercise_cancel(first=signal.SIGINT, seam="cleanup-entry")

    def test_repeated_signal_between_group_signals_cannot_skip_reap(self):
        self.exercise_cancel(first=signal.SIGINT, seam="between-signals")

    def test_first_signal_during_normal_cleanup_is_preserved(self):
        self.exercise_cancel(seam="normal-cleanup", normal=True)

    def test_lock_remains_owned_during_group_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, _, env = self.fixture(root)
            args = type("Args", (), {"output":root/"output"})()
            seen = []
            def execute(*_args):
                code = RUNNER.run(PYTHON + ["-c", "pass"], root, env, root/"output/command.log")
                self.assertEqual(code, 0)
                return []
            real_killpg = RUNNER.os.killpg
            def while_stopping(pid, number):
                seen.append(self.lock_free(project))
                return real_killpg(pid, number)
            with mock.patch.object(RUNNER, "__file__", str(project/"support/build/ktest/run.py")), \
                 mock.patch.object(RUNNER, "run_locked", side_effect=execute), \
                 mock.patch.object(RUNNER.os, "killpg", side_effect=while_stopping), \
                 RUNNER.interruption_handlers() as shutdown:
                RUNNER.run_main(args, shutdown)
            self.assertEqual(seen, [False, False])
            self.assertTrue(self.lock_free(project))

    def test_success_fixture_retains_all_command_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, argv, env = self.fixture(root)
            completed = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads((root/"output/result.json").read_text())
            self.assertTrue(result["passed"])
            self.assertEqual(result["runner_sha256"], hashlib.sha256((project/"support/build/ktest/run.py").read_bytes()).hexdigest())
            self.assertTrue(result["crates"][0]["fixture_only"])
            records = list((root/"output").rglob("*.command.json"))
            self.assertEqual(len(records), 8)
            for path in records:
                record = json.loads(path.read_text())
                self.assertEqual(record["raw_exit_code"], 0)
                self.assertEqual(record["exit_code"], 0)
                self.assertTrue(record["group_cleanup"]["leader_reaped"])
            self.assertTrue(self.lock_free(project))

    def test_nonzero_child_preserves_failure_and_cleanup_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(RUNNER.run(PYTHON + ["-c", "print('real failure'); raise SystemExit(7)"],
                                        root, os.environ.copy(), root/"failure.log"), 7)
            self.assertIn("real failure", (root/"failure.log").read_text())
            record = json.loads((root/"failure.log.command.json").read_text())
            self.assertEqual(record["raw_exit_code"], 7)
            self.assertEqual(record["exit_code"], 7)
            self.assertTrue(record["group_cleanup"]["leader_reaped"])

    def test_busy_lock_consumes_no_explicit_or_default_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, argv, env = self.fixture(root)
            requested = root/"missing-parent/evidence"
            argv[argv.index("--output") + 1] = str(requested)
            with (project/"support/build/out-kernel.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                for call in (argv, argv[:len(PYTHON)+1]):
                    completed = subprocess.run(call, env=env, capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn("another kernel build/test", completed.stderr)
            self.assertFalse(requested.parent.exists())
            self.assertFalse((project/"support/build/out").exists())

    def exercise_encoded_flags_rejection(self, value):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, argv, env = self.fixture(root)
            requested = root/"missing-parent/evidence"
            argv[argv.index("--output") + 1] = str(requested)
            env["CARGO_ENCODED_RUSTFLAGS"] = value
            for call in (argv, argv[:len(PYTHON)+1]):
                completed = subprocess.run(call, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertIn("unset CARGO_ENCODED_RUSTFLAGS and retry", completed.stderr)
                self.assertFalse(requested.parent.exists())
                self.assertFalse((project/"support/build/out").exists())
                self.assertFalse((project/"support/build/out-kernel.lock").exists())
                self.assertFalse((root/"tool-invocations.jsonl").exists())
                self.assertFalse((project/"kernel/asterinas/target").exists())
            del env["CARGO_ENCODED_RUSTFLAGS"]
            completed = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            result = json.loads((requested/"result.json").read_text())
            self.assertTrue(result["passed"])
            self.assertTrue(result["crates"][0]["fixture_only"])
            self.assertEqual(len((root/"tool-invocations.jsonl").read_text().splitlines()), 8)
            self.assertTrue(self.lock_free(project))

    def test_empty_encoded_flags_reject_before_work_and_same_output_retries(self):
        self.exercise_encoded_flags_rejection("")

    def test_nonempty_encoded_flags_reject_before_work_and_same_output_retries(self):
        self.exercise_encoded_flags_rejection("--cfg\x1fhost_supplied_flag")

    def test_existing_failed_evidence_survives_and_lock_is_released(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, argv, env = self.fixture(root)
            (root/"output").mkdir()
            marker = root/"output/failed.log"
            marker.write_bytes(b"original failure evidence\n")
            completed = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(marker.read_bytes(), b"original failure evidence\n")
            self.assertTrue(self.lock_free(project))

    def test_external_reap_permanently_disarms_numeric_group_signals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (root/"child.log").open("wb") as output:
                owned = RUNNER.OwnedSession(PYTHON + ["-c", "pass"],
                                            cwd=root, env=os.environ.copy(), output=output)
                _, status = os.waitpid(owned.process.pid, 0)
                with mock.patch.object(RUNNER.os, "killpg") as killpg:
                    with self.assertRaisesRegex(RuntimeError, "externally reaped"):
                        owned.stop()
                    self.assertIsNone(owned.stop())
                    killpg.assert_not_called()
                owned.process.returncode = os.waitstatus_to_exitcode(status)

    def test_cancellation_during_success_result_publication_rewrites_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, argv, env = self.fixture(root)
            argv = PYTHON + ["-c", WRAPPER, str(project/"support/build/ktest/run.py"), "result-publication"] + argv[len(PYTHON)+1:]
            completed = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 143, completed.stderr)
            result = json.loads((root/"output/result.json").read_text())
            self.assertFalse(result["passed"])
            self.assertEqual(result["interrupted_by"], "SIGTERM")
            self.assertTrue((root/"seam-fired").exists())


if __name__ == "__main__":
    unittest.main()
