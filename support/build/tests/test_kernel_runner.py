#!/usr/bin/env python3
"""Exercise the real shell runner with disposable tools, never a real kernel.

The copied runner and boot checker are unmodified. Only its external build
inputs and host tools are fixtures; locking, directory allocation, manifest
installation/cleanup, pipeline status, and boot acceptance remain under test.
"""

import errno
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from unittest import mock


BUILD = Path(__file__).resolve().parents[1]

PREPARE_INITRAMFS = """\
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--upstream', type=Path, required=True)
parser.add_argument('--busybox')
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--manifest', type=Path, required=True)
args = parser.parse_args()
args.output.write_bytes(b'fixture initramfs')
args.manifest.write_text('{}\\n')
if __import__('os').environ.get('MOCK_MANIFEST_ACTION') == 'race_create':
    (args.upstream / 'kernel/OSDK.toml').write_text('foreign race manifest\\n')
"""

MOCK_MAKE = """\
#!/usr/bin/python3
import json
import os
from pathlib import Path
import sys
import time

if '--version' in sys.argv:
    print('GNU Make fixture')
    raise SystemExit(0)

root = Path(os.environ['MOCK_PROJECT'])
(root / 'make-call.json').write_text(json.dumps({
    'argv': sys.argv[1:], 'inherited_initramfs': os.environ.get('INITRAMFS')
}))
manifest = root / 'kernel/asterinas/kernel/OSDK.toml'
if os.environ.get('MOCK_MANIFEST_ACTION') == 'replace':
    replacement = manifest.with_suffix('.replacement')
    replacement.write_text('foreign replacement manifest\\n')
    os.replace(replacement, manifest)
if os.environ.get('MOCK_GATE'):
    gate = Path(os.environ['MOCK_GATE'])
    gate.with_suffix('.ready').touch()
    deadline = time.monotonic() + 10
    while not gate.with_suffix('.release').exists():
        if time.monotonic() >= deadline:
            raise SystemExit('fixture gate was not released')
        time.sleep(0.01)
print('fixture make completed; no kernel or QEMU was executed')
"""


class KernelRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="a01-runner-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build = self.root / "support/build"
        self.kernel = self.root / "kernel/asterinas/kernel"
        self.mock = self.root / "mock-bin"
        self.vdso = self.root / "vdso"
        for directory in (self.build / "minimal", self.kernel, self.mock, self.vdso):
            directory.mkdir(parents=True)
        for name in ("kernel.sh", "kernel-supervisor.py", "check-boot.py", "cleanup-manifest.py"):
            shutil.copyfile(BUILD / name, self.build / name)
        (self.build / "verify-source.py").write_text("print('{}')\n")
        (self.build / "minimal/prepare-initramfs.py").write_text(PREPARE_INITRAMFS)
        (self.build / "minimal/OSDK.toml").write_text("# owned fixture manifest\n")
        (self.build / "minimal/Cargo.lock").write_text("# fixture lock\n")
        (self.vdso / "vdso_x86_64.so").write_bytes(b"fixture vdso")
        for name in ("cargo", "rustc", "rustup", "gcc", "qemu-system-x86_64", "git"):
            self.write_tool(name, "#!/bin/sh\nprintf 'fixture host tool\\n'\n")
        self.write_tool("make", MOCK_MAKE)
        self.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("A01_", "CARGO_", "RUSTUP_", "MOCK_"))
            and key not in ("MAKEFLAGS", "MFLAGS", "VDSO_LIBRARY_DIR", "INITRAMFS")
        }
        self.environment.update({
            "PATH": f"{self.mock}:/usr/bin:/bin",
            "CARGO_HOME": str(self.root / "cargo-home"),
            "VDSO_LIBRARY_DIR": str(self.vdso),
            "MOCK_PROJECT": str(self.root),
        })

    def write_tool(self, name, content):
        path = self.mock / name
        path.write_text(content)
        path.chmod(0o755)

    def run_runner(self, name="evidence", target="kernel", extra=None):
        environment = dict(self.environment, A01_RUN_DIR=str(self.root / name))
        environment.update(extra or {})
        return subprocess.run(
            ["bash", str(self.build / "kernel.sh"), target],
            env=environment, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=15,
        )

    def test_existing_directory_and_stale_success_are_rejected(self):
        run = self.root / "evidence"
        run.mkdir()
        stale = {
            "qemu.json": json.dumps({"raw_exit_code": 33, "timed_out": False}),
            "serial.log": "\n".join((
                "OSTD initialized. Preparing components.",
                "TRILLIONNIUM_A01_INIT_BEGIN", "TRILLIONNIUM_A01_CPU_COUNT=1",
                "Successfully booted.", "TRILLIONNIUM_A01_BOOT_OK",
            )),
        }
        for name, content in stale.items():
            (run / name).write_text(content)
        result = self.run_runner(target="run_kernel")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("must be a new directory", result.stdout)
        self.assertFalse((self.root / "make-call.json").exists())
        for name, content in stale.items():
            self.assertEqual((run / name).read_text(), content)

    def test_fresh_make_success_without_qemu_is_not_boot_success(self):
        result = self.run_runner(target="run_kernel")
        run = self.root / "evidence"
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual((run / "make-exit-code.txt").read_text().strip(), "0")
        self.assertNotEqual((run / "run-exit-code.txt").read_text().strip(), "0")
        self.assertFalse((run / "qemu.json").exists())
        self.assertNotIn("PASS:", result.stdout)

    def test_concurrent_runner_refused_and_lock_inode_survives_exit(self):
        gate = self.root / "gate"
        environment = dict(
            self.environment, A01_RUN_DIR=str(self.root / "first"), MOCK_GATE=str(gate)
        )
        first = subprocess.Popen(
            ["bash", str(self.build / "kernel.sh"), "kernel"], env=environment,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 8
            while not gate.with_suffix(".ready").exists():
                if first.poll() is not None:
                    self.fail(f"first runner exited before gate: {first.communicate()[0]}")
                if time.monotonic() >= deadline:
                    self.fail("first runner did not reach the fixture make gate")
                time.sleep(0.01)
            lock = self.build / "out-kernel.lock"
            identity = (lock.stat().st_dev, lock.stat().st_ino)
            second = self.run_runner(name="second")
            self.assertNotEqual(second.returncode, 0, second.stdout)
            self.assertIn("another A01 build", second.stdout)
            self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
            gate.with_suffix(".release").touch()
            output = first.communicate(timeout=8)[0]
            self.assertEqual(first.returncode, 0, output)
            self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
            third = self.run_runner(name="third")
            self.assertEqual(third.returncode, 0, third.stdout)
            self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
        finally:
            gate.with_suffix(".release").touch()
            if first.poll() is None:
                try:
                    first.communicate(timeout=8)
                except subprocess.TimeoutExpired:
                    first.kill()
                    first.communicate(timeout=3)

    def test_owned_manifest_removed_after_success(self):
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.kernel / "OSDK.toml").exists())
        self.assertEqual(list(self.kernel.glob(".a01-osdk-*")), [])

    def test_signal_immediately_after_manifest_publication_cleans_owned_inode(self):
        real_ln = shutil.which("ln")
        self.assertIsNotNone(real_ln, "the native runner requires the host ln tool")
        # Publish a real hard link, then interrupt the waiting runner before it
        # executes its next shell statement. This exercises its EXIT trap in
        # the otherwise tiny ownership-registration window.
        self.write_tool("ln", (
            "#!/bin/sh\n"
            f"{shlex.quote(real_ln)} \"$@\" || exit $?\n"
            "kill -TERM \"$PPID\"\n"
        ))
        result = self.run_runner()
        self.assertIn(result.returncode, (-signal.SIGTERM, 128 + signal.SIGTERM), result.stdout)
        self.assertFalse((self.root / "make-call.json").exists())
        self.assertEqual(list(self.kernel.glob(".a01-osdk-*")), [])
        self.assertFalse(
            (self.kernel / "OSDK.toml").exists(),
            "interrupted publication left the runner's owned OSDK manifest behind",
        )

    def test_existing_manifest_is_preserved(self):
        manifest = self.kernel / "OSDK.toml"
        manifest.write_text("preexisting foreign manifest\n")
        identity = manifest.stat().st_ino
        result = self.run_runner()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("already exists", result.stdout)
        self.assertEqual(manifest.read_text(), "preexisting foreign manifest\n")
        self.assertEqual(manifest.stat().st_ino, identity)
        self.assertFalse((self.root / "make-call.json").exists())

    def test_manifest_created_during_preparation_is_preserved(self):
        result = self.run_runner(extra={"MOCK_MANIFEST_ACTION": "race_create"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            (self.kernel / "OSDK.toml").read_text(), "foreign race manifest\n"
        )
        self.assertEqual(list(self.kernel.glob(".a01-osdk-*")), [])
        self.assertFalse((self.root / "make-call.json").exists())

    def test_manifest_replaced_during_build_is_preserved(self):
        result = self.run_runner(extra={"MOCK_MANIFEST_ACTION": "replace"})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            (self.kernel / "OSDK.toml").read_text(), "foreign replacement manifest\n"
        )
        self.assertEqual(list(self.kernel.glob(".a01-osdk-*")), [])

    def test_fixed_initramfs_argument_overrides_inherited_off(self):
        result = self.run_runner(extra={"INITRAMFS": "off"})
        self.assertEqual(result.returncode, 0, result.stdout)
        call = json.loads((self.root / "make-call.json").read_text())
        self.assertEqual(call["inherited_initramfs"], "off")
        self.assertIn("INITRAMFS=on", call["argv"])
        self.assertNotIn("INITRAMFS=off", call["argv"])

    def test_log_write_failure_overrides_successful_make(self):
        self.write_tool("tee", "#!/bin/sh\ncat >/dev/null\nexit 17\n")
        result = self.run_runner()
        run = self.root / "evidence"
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("failed to retain the complete command log", result.stdout)
        self.assertEqual((run / "make-exit-code.txt").read_text().strip(), "0")
        self.assertEqual((run / "log-exit-code.txt").read_text().strip(), "17")
        self.assertNotEqual((run / "run-exit-code.txt").read_text().strip(), "0")

    def inject_cleanup_restore_conflict(self):
        """Use the real helper, injecting writers at its atomic boundaries."""
        helper = BUILD / "cleanup-manifest.py"
        (self.build / "cleanup-manifest.py").write_text(
            "import os, runpy\n"
            f"namespace=runpy.run_path({str(helper)!r}, run_name='cleanup_fixture')\n"
            "state=namespace['clean_manifest'].__globals__\n"
            "capture=state['capture_candidate']\n"
            "restore=state['restore_no_replace']\n"
            "def replace_before_capture(manifest, candidate):\n"
            " replacement=manifest.with_name('first-foreign.toml')\n"
            " replacement.write_text('first foreign manifest\\n')\n"
            " os.replace(replacement, manifest)\n"
            " capture(manifest, candidate)\n"
            "def conflict_before_restore(candidate, manifest):\n"
            " with manifest.open('x') as stream: stream.write('second foreign manifest\\n')\n"
            " restore(candidate, manifest)\n"
            "state['capture_candidate']=replace_before_capture\n"
            "state['restore_no_replace']=conflict_before_restore\n"
            "raise SystemExit(namespace['main']())\n"
        )

    def assert_cleanup_retained_foreign(self):
        run = self.root / "evidence"
        cleanup = json.loads((run / "manifest-cleanup.json").read_text())
        self.assertFalse(cleanup["passed"])
        self.assertEqual(cleanup["outcome"], "foreign_retained")
        self.assertEqual(Path(cleanup["retained_path"]).read_text(), "first foreign manifest\n")
        self.assertEqual((self.kernel / "OSDK.toml").read_text(), "second foreign manifest\n")
        self.assertEqual((run / "manifest-cleanup-exit-code.txt").read_text(), "1\n")

    def test_cleanup_restore_conflict_changes_success_to_failure(self):
        self.inject_cleanup_restore_conflict()
        result = self.run_runner()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assert_cleanup_retained_foreign()
        run = self.root / "evidence"
        self.assertEqual((run / "make-exit-code.txt").read_text(), "0\n")
        self.assertEqual((run / "run-exit-code.txt").read_text(), "1\n")
        self.assertIn("retained for recovery:", result.stdout)

    def test_cleanup_restore_conflict_preserves_original_make_failure(self):
        self.inject_cleanup_restore_conflict()
        self.write_tool("make", MOCK_MAKE + "\nraise SystemExit(37)\n")
        result = self.run_runner()
        self.assertEqual(result.returncode, 37, result.stdout)
        self.assert_cleanup_retained_foreign()
        run = self.root / "evidence"
        self.assertEqual((run / "make-exit-code.txt").read_text(), "37\n")
        self.assertEqual((run / "run-exit-code.txt").read_text(), "37\n")


class ManifestCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="a01-manifest-custody-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = self.root / "OSDK.toml"
        self.manifest.write_text("owned manifest\n")
        self.anchor = self.manifest.open("rb")
        self.addCleanup(self.anchor.close)
        self.owned_identity = (os.fstat(self.anchor.fileno()).st_dev,
                               os.fstat(self.anchor.fileno()).st_ino)
        spec = importlib.util.spec_from_file_location("manifest_cleanup", BUILD / "cleanup-manifest.py")
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)

    def cleanup_manifest(self):
        return self.helper.clean_manifest(self.manifest, self.anchor.fileno())

    def replace_with_foreign(self, text="foreign manifest\n"):
        replacement = self.root / "replacement.toml"
        replacement.write_text(text)
        identity = replacement.stat().st_dev, replacement.stat().st_ino
        os.replace(replacement, self.manifest)
        self.assertNotEqual(identity, self.owned_identity)
        return identity

    def test_owned_inode_is_removed_from_private_custody(self):
        result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["outcome"], "owned_removed")
        self.assertFalse(self.manifest.exists())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(os.fstat(self.anchor.fileno()).st_nlink, 0)

    def test_missing_public_path_is_a_noop(self):
        self.manifest.unlink()
        result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["outcome"], "absent")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_replacement_immediately_before_capture_is_restored(self):
        capture = self.helper.capture_candidate
        identity = []

        def replace_then_capture(manifest, candidate):
            identity.append(self.replace_with_foreign())
            capture(manifest, candidate)

        with mock.patch.object(self.helper, "capture_candidate", side_effect=replace_then_capture):
            result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["outcome"], "foreign_restored")
        self.assertEqual((self.manifest.stat().st_dev, self.manifest.stat().st_ino), identity[0])
        self.assertEqual(self.manifest.read_text(), "foreign manifest\n")

    def test_new_public_entry_after_owned_capture_is_untouched(self):
        capture = self.helper.capture_candidate

        def capture_then_replace(manifest, candidate):
            capture(manifest, candidate)
            manifest.write_text("new public manifest\n")

        with mock.patch.object(self.helper, "capture_candidate", side_effect=capture_then_replace):
            result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["outcome"], "owned_removed")
        self.assertEqual(self.manifest.read_text(), "new public manifest\n")

    def test_foreign_dangling_symlink_is_restored_without_following(self):
        self.manifest.unlink()
        self.manifest.symlink_to("missing-target")
        identity = self.manifest.lstat().st_ino
        result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertTrue(self.manifest.is_symlink())
        self.assertEqual(self.manifest.lstat().st_ino, identity)
        self.assertEqual(os.readlink(self.manifest), "missing-target")
        self.assertFalse((self.root / "missing-target").exists())

    def test_foreign_directory_and_contents_are_restored(self):
        self.manifest.unlink()
        self.manifest.mkdir()
        (self.manifest / "contents").write_text("directory contents\n")
        identity = self.manifest.stat().st_ino
        result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(self.manifest.stat().st_ino, identity)
        self.assertEqual((self.manifest / "contents").read_text(), "directory contents\n")

    def test_restore_conflict_retains_both_foreign_entries(self):
        self.replace_with_foreign("first foreign\n")
        restore = self.helper.restore_no_replace

        def concurrent_public_writer(candidate, manifest):
            manifest.write_text("second foreign\n")
            restore(candidate, manifest)

        with mock.patch.object(self.helper, "restore_no_replace", side_effect=concurrent_public_writer):
            result = self.cleanup_manifest()
        self.assertFalse(result["passed"], result)
        self.assertEqual(result["errno"], errno.EEXIST)
        self.assertEqual(Path(result["retained_path"]).read_text(), "first foreign\n")
        self.assertEqual(self.manifest.read_text(), "second foreign\n")
        self.assertEqual(Path(result["custody"]).stat().st_mode & 0o777, 0o700)

    def test_unavailable_noreplace_retains_foreign_candidate(self):
        self.replace_with_foreign()
        with mock.patch.object(self.helper, "restore_no_replace", side_effect=OSError(errno.ENOSYS, "unsupported")):
            result = self.cleanup_manifest()
        self.assertFalse(result["passed"], result)
        self.assertEqual(Path(result["retained_path"]).read_text(), "foreign manifest\n")
        self.assertFalse(self.manifest.exists())

    def test_exception_after_capture_preserves_candidate(self):
        capture = self.helper.capture_candidate

        def capture_then_fail(manifest, candidate):
            capture(manifest, candidate)
            raise RuntimeError("injected after atomic capture")

        with mock.patch.object(self.helper, "capture_candidate", side_effect=capture_then_fail):
            result = self.cleanup_manifest()
        self.assertFalse(result["passed"], result)
        self.assertEqual(Path(result["candidate"]).read_text(), "owned manifest\n")
        self.assertTrue(Path(result["retained_path"]).exists())

    def test_invalid_anchor_never_moves_public_entry(self):
        result = self.helper.clean_manifest(self.manifest, -1)
        self.assertFalse(result["passed"], result)
        self.assertEqual(self.manifest.read_text(), "owned manifest\n")
        self.assertEqual(list(self.root.iterdir()), [self.manifest])


if __name__ == "__main__":
    unittest.main(verbosity=2)
