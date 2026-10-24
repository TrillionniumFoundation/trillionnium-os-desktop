"""Real bounded host I/O tests; synthetic child output never qualifies a guest."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import native_owner_inputs as inputs
import run_native_owner as runner


class NativeOwnerInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def review(self):
        path = self.root / "source-review.json"
        value = {"schema": "hepta.native-original-owner-source-review.v1",
                 "desktop": {"head": "a" * 40, "tree": "b" * 40}, "hepta": {"head": "c" * 40, "tree": "d" * 40},
                 "entry": {"package": "codex-hepta-agentd", "kind": "bin", "name": "original-entry",
                           "path": "codex-rs/hepta-agentd/src/bin/original-entry.rs", "sha256": "e" * 64},
                 "userspace_toolchain": {"channel": "1.96.0", "manifest": "codex-rs/rust-toolchain.toml", "sha256": "f" * 64},
                 "scope": "inert parser input, not a reviewed product or execution"}
        path.write_text(json.dumps(value))
        return path, value

    def test_frozen_review_requires_its_own_schema_original_package_and_toolchain(self):
        path, value = self.review()
        self.assertEqual(inputs.review_inputs(path, inputs.sha(path)), value)
        for kind in ("old-runtime", "fixture", "floating", "escape", "unknown-field"):
            path, value = self.review()
            if kind == "old-runtime": value["schema"] = "hepta.native-original-runtime-source-review.v1"
            if kind == "fixture": value["entry"]["package"] = "qualification-helper"
            if kind == "floating": value["userspace_toolchain"]["channel"] = "stable"
            if kind == "escape": value["entry"]["path"] = "codex-rs/hepta-agentd/../fixture.rs"
            if kind == "unknown-field": value["reviewed"] = True
            path.write_text(json.dumps(value))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                inputs.review_inputs(path, inputs.sha(path))

    def test_review_cannot_change_after_caller_pins_it(self):
        path, value = self.review()
        expected = inputs.sha(path)
        value["hepta"]["head"] = "e" * 40
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "frozen digest"):
            inputs.review_inputs(path, expected)

    def test_alias_missing_empty_oversized_and_changed_bytes_are_refused(self):
        source = self.root / "input"
        source.write_bytes(b"original")
        digest = inputs.sha(source)
        alias = self.root / "alias"
        alias.symlink_to(source)
        for path, bound in ((alias, 100), (self.root / "absent", 100), (source, 2)):
            with self.subTest(path=path, bound=bound), self.assertRaises(ValueError):
                inputs.read(path, bound, digest)
        source.write_bytes(b"changed")
        with self.assertRaises(ValueError): inputs.read(source, 100, digest)
        source.write_bytes(b"")
        with self.assertRaises(ValueError): inputs.read(source, 100)

    def test_disabled_runner_does_not_read_build_inputs_or_create_output(self):
        destination = self.root / "must-not-exist"
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            code = runner.main(["--output", str(destination)])
        value = json.loads(captured.getvalue())
        self.assertEqual(code, 0)
        self.assertFalse(value["passed"])
        self.assertFalse(value["native_execution_attempted"])
        self.assertFalse(destination.exists())

    def test_negative_loader_control_requires_exact_failure_before_any_resume(self):
        raw = b"[hepta-g2] rejected initial image: manifest-byte-mismatch\nfailed to run the init process\n"
        record = {"raw_exit_code": 65, "timed_out": False, "serial_excessive": False}
        self.assertTrue(runner.rejection(raw, record, "manifest-byte-mismatch")["passed"])
        for extra in (b"[hepta-g2] trusted initial image committed: bytes=123 entry=0x400000\n",
                      b"HEPTA_G2_EVIDENCE_V1 {}\n", raw, b"[hepta-g2] unknown\n"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                runner.rejection(raw + extra, record, "manifest-byte-mismatch")


class NativeOwnerBoundedIoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in ("kernel", "initrd", "bios"):
            (self.root / name).write_bytes(("inert " + name).encode())
        self.identity = {"path": sys.executable, "sha256": inputs.sha(Path(sys.executable).resolve())}

    def child(self, source, timeout=2):
        directory = self.root / "run"
        directory.mkdir()
        argv = [sys.executable, "-I", "-c", source]
        for name in ("kernel", "initrd", "bios"):
            argv += ["-" + name, str(self.root / name)]
        return runner.run_qemu(argv, directory, timeout, self.identity)

    def test_real_subprocess_output_exit_and_artifact_hashes_are_retained(self):
        raw, record = self.child("import sys; print('inert transcript'); sys.exit(33)")
        self.assertEqual(raw, b"inert transcript\n")
        self.assertEqual(record["raw_exit_code"], 33)
        self.assertEqual(record["serial_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(record["timed_out"])
        self.assertEqual(set(record["artifacts"]), {"-kernel", "-initrd", "-bios"})
        self.assertFalse((self.root / "run/result.json").exists())

    def test_actual_hanging_child_is_terminated_and_retained_as_timeout(self):
        raw, record = self.child("import time; print('inert started',flush=True); time.sleep(10)", 0.15)
        self.assertEqual(raw, b"inert started\n")
        self.assertTrue(record["timed_out"])
        self.assertNotEqual(record["raw_exit_code"], 33)
        self.assertLess(record["elapsed_seconds"], 3)

    def test_real_excess_output_is_bounded_and_never_a_success(self):
        _, record = self.child("import os; block=b'x'*65536\nwhile True: os.write(1,block)")
        self.assertTrue(record["serial_excessive"])
        self.assertEqual((self.root / "run/serial.log").stat().st_size, runner.oracle.MAX_SERIAL_BYTES)
        self.assertNotEqual(record["raw_exit_code"], 33)

    def test_input_mutation_during_real_subprocess_is_detected(self):
        source = "import pathlib,sys; pathlib.Path(sys.argv[sys.argv.index('-kernel')+1]).write_bytes(b'tampered'); sys.exit(33)"
        with self.assertRaisesRegex(ValueError, "input changed"):
            self.child(source)
        self.assertTrue((self.root / "run/qemu.json").is_file())

    def test_real_ext2_format_has_original_bounds_and_exact_retained_preimage(self):
        binary = shutil.which("mkfs.ext2")
        self.assertIsNotNone(binary, "the original ext2 formatter is required for this real storage-harness test")
        path, identity = runner.tool(binary)
        result = runner.format_state(self.root, path, identity)
        self.assertEqual((self.root / "state.raw").stat().st_size, 256 * 1024**2)
        self.assertEqual(inputs.sha(self.root / "state.raw"), result["before_sha256"])
        self.assertEqual(inputs.sha(self.root / "state-before.raw"), result["before_sha256"])
        self.assertEqual((self.root / "state-before.raw").stat().st_mode & 0o777, 0o444)
        self.assertFalse((self.root / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
