"""Real bounded host I/O tests; synthetic child output never qualifies a guest."""
import contextlib
import gzip
import inspect
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
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

    def test_entropy_control_disables_hardware_and_refuses_role_resume(self):
        argv = runner.qemu_argv("qemu-system-x86_64", self.root, self.root, False, entropy_control=True)
        ordinary = runner.qemu_argv("qemu-system-x86_64", self.root, self.root, True)
        self.assertEqual(argv[argv.index("-cpu") + 1], "max,-rdrand")
        self.assertEqual(ordinary[ordinary.index("-cpu") + 1], "max")
        self.assertNotIn("-drive", argv)
        raw = (b"use randomness based on the timestamp, which is insecure\n"
               b"[hepta-g2] rejected trusted startup: entropy-not-ready\n"
               b"failed to run the init process\n")
        record = {"raw_exit_code": 65, "timed_out": False, "serial_excessive": False,
                  "profile": {"cpu": "max,-rdrand"}, "argv": argv}
        self.assertTrue(runner.rejection(raw, record, "entropy-not-ready")["passed"])
        for changed_raw, changed_record in (
                (raw.replace(b"use randomness based on the timestamp, which is insecure\n", b""), record),
                (raw + b"use randomness generated by hardware\n", record),
                (raw + b"[hepta-g2] initial roles activated: root=1\n", record),
                (raw, {**record, "raw_exit_code": 33}),
                (raw, {**record, "timed_out": True}),
                (raw, {**record, "argv": ordinary}),
                (raw, {**record, "profile": {"cpu": "max"}})):
            with self.subTest(raw=changed_raw, record=changed_record), self.assertRaises(ValueError):
                runner.rejection(changed_raw, changed_record, "entropy-not-ready")


class NativeOwnerArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, cls.replay = inputs.original_helpers(runner.ROOT)

    def test_normal_legacy_archive_keeps_the_original_codec_default(self):
        fields = [1, 0o040755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        original = gzip.compress(self.replay.pack([("test", fields, b"")]), mtime=0)
        owner = b"inert archive content; never an admitted executable"
        plan = {"schema_version": 1, "scenario": "steady-state-v1", "nonce": "01" * 32}
        output = runner.build_initramfs(original, owner, plan, self.replay)
        restored = {name: content for name, _, content in self.replay.unpack(gzip.decompress(output))}
        self.assertEqual(restored["test/hepta-g2-owner"], owner)
        self.assertEqual(json.loads(restored["test/hepta-g2-run.json"]), plan)
        self.assertEqual(inspect.signature(self.replay.unpack).parameters["max_bytes"].default, 16 * 1024**2)

    def test_fixed_contract_uses_the_source_owned_original_image(self):
        contract = runner.original_owner_archive_contract()
        exact = inputs.image_module(inputs.EXACT_IMAGE_PROFILE)
        self.assertEqual(contract["image_profile_descriptor_sha256"], exact.DESCRIPTOR_SHA256)
        self.assertEqual(contract["owner_file_bytes"], exact.descriptor()["image"]["file_bytes"])
        self.assertEqual(contract["maximum_archive_bytes"], 22_268_496)
        self.assertEqual(contract["legacy_default_archive_bytes"], 16 * 1024**2)
        self.assertFalse(contract["native_execution_verified"])

    def test_only_the_two_finite_compact_plans_fit_the_named_contract(self):
        for scenario, length in (("steady-state-v1", 125), ("manager-exit-after-terminal-v1", 140)):
            plan = {"schema_version": 1, "scenario": scenario, "nonce": "ab" * 32}
            encoded = runner.original_owner_archive_plan(plan)
            self.assertEqual(len(encoded), length)
            self.assertEqual(json.loads(encoded), plan)
        valid = {"schema_version": 1, "scenario": "steady-state-v1", "nonce": "ab" * 32}
        for change in ({"schema_version": True}, {"scenario": "unreviewed"}, {"nonce": "ab" * 31},
                       {"nonce": "AB" * 32}, {"max_bytes": 64 * 1024**2}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.original_owner_archive_plan({**valid, **change})


class NativeOwnerQuietPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_successful_quiet_command_keeps_its_exact_empty_log(self):
        log = self.root / "original-packaging.log"
        with log.open("xb") as stream:
            completed = subprocess.run([sys.executable, "-I", "-B", "-c", "pass"],
                                       stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                       timeout=5, check=False)
        self.assertEqual(completed.returncode, 0)
        empty_sha = hashlib.sha256(b"").hexdigest()
        self.assertEqual(inputs.read(log, 64 * 1024**2, empty_sha, allow_empty=True), b"")
        retained = runner.retain_files(self.root / "retained", {log.name: log},
                                       empty_logs=inputs.EMPTY_ORIGINAL_COMMAND_LOGS)
        self.assertEqual(retained[log.name]["bytes"], 0)
        self.assertEqual(retained[log.name]["sha256"], empty_sha)
        self.assertEqual((self.root / "retained" / log.name).read_bytes(), b"")
        self.assertEqual((self.root / "retained" / log.name).stat().st_mode & 0o777, 0o444)

    def test_ordinary_inputs_documents_and_default_retention_still_require_bytes(self):
        path = self.root / "input.json"
        path.write_bytes(b"")
        with self.assertRaises(ValueError):
            inputs.read(path, 1024)
        with self.assertRaises(ValueError):
            inputs.document(path, 1024)
        with self.assertRaises(ValueError):
            runner.retain_files(self.root / "retained", {path.name: path})
        self.assertFalse((self.root / "retained").exists())

    def test_quiet_log_support_preserves_size_and_digest_checks(self):
        log = self.root / "original-packaging.log"
        content = b"normal command output\n"
        log.write_bytes(content)
        self.assertEqual(inputs.read(log, len(content), inputs.sha(log), allow_empty=True), content)
        with self.assertRaises(ValueError):
            inputs.read(log, len(content) - 1, allow_empty=True)
        with self.assertRaisesRegex(ValueError, "frozen digest"):
            inputs.read(log, len(content), hashlib.sha256(b"").hexdigest(), allow_empty=True)


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
