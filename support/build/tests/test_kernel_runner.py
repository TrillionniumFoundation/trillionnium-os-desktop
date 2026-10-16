#!/usr/bin/env python3
"""Exercise the real shell runner with disposable tools, never a real kernel.

The copied runner and boot checker are unmodified. Only its external build
inputs and host tools are fixtures; locking, directory allocation, manifest
installation/cleanup, pipeline status, and boot acceptance remain under test.
"""

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
        for name in ("kernel.sh", "kernel-supervisor.py", "check-boot.py"):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
