#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Negative controls for CI product reuse; no host probes or QEMU are run."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("safety_runner", Path(__file__).with_name("run.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ProductReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.head, self.tree = "a" * 40, "b" * 40
        self.snapshot = {"head": self.head, "tree": self.tree, "files": {"input": {"sha256": "c" * 64}}}
        self.artifacts = {"-kernel": b"kernel", "-initrd": b"original-initrd", "-bios": b"bios"}
        boot = self.directory / "product-boot"
        boot.mkdir()
        (boot / "qemu.json").write_bytes(b"{}")
        (self.directory / "product-kernel.elf").write_bytes(self.artifacts["-kernel"])
        for name in ("source-before.json", "source-after-boot.json", "source-after-guest.json"):
            (self.directory / name).write_text(json.dumps(self.snapshot))
        candidate = runner.candidate
        markers = (*candidate.replay.REQUIRED_SECURITY_MARKERS, candidate.replay.EXPECTED_SUCCESS,
                   *candidate.LIFECYCLE_MARKERS, *candidate.OP_MARKERS,
                   candidate.CANDIDATE_MARKER, candidate.FINAL_BOOT_MARKER)
        self.serial = ("\n".join(markers) + "\n").encode()
        (self.directory / "serial.log").write_bytes(self.serial)
        self.receipt = {
            "schema": "a06.g1-queryabi-product-candidate.v1", "passed": True,
            "source_inputs_unchanged": True, "stage": "complete",
            "source_head": self.head, "source_tree": self.tree, "source_file_count": 1,
            "cargo_target_dir": str(self.directory / "target"),
            "product_qemu_record_sha256": runner.digest(b"{}"),
            "kernel_elf_sha256": runner.digest(self.artifacts["-kernel"]),
            "original_initramfs_sha256": runner.digest(self.artifacts["-initrd"]),
            "bios_sha256": runner.digest(self.artifacts["-bios"]),
            "raw_serial_sha256": runner.digest(self.serial), "qemu_exit": 33, "timed_out": False,
        }
        self.save_receipt()
        self.source = patch.object(candidate, "source_snapshot", return_value=self.snapshot).start()
        self.boot = patch.object(candidate, "verify_product_boot", return_value=(
            {"qemu_sha256": "d" * 64}, self.artifacts, "lock-hash")).start()
        self.addCleanup(patch.stopall)

    def save_receipt(self):
        (self.directory / "result.json").write_text(json.dumps(self.receipt))

    def load(self):
        return runner.load_product(self.directory, self.head, self.tree)

    def test_reuses_verified_original_boot_without_building(self):
        with patch.object(runner.subprocess, "run", side_effect=AssertionError("unexpected build")):
            artifacts, qemu_sha, provenance = self.load()
        self.assertEqual(artifacts, self.artifacts)
        self.assertEqual(qemu_sha, "d" * 64)
        self.assertFalse(provenance["kernel_rebuilt"])
        self.source.assert_called_once_with(runner.ROOT, self.head, self.tree)
        self.boot.assert_called_once()

    def test_rejects_failed_or_wrong_source_receipt(self):
        for field, value in (("passed", False), ("stage", "incomplete"),
                             ("source_inputs_unchanged", False), ("source_head", "e" * 40),
                             ("schema", "unrelated")):
            with self.subTest(field=field):
                original = copy.deepcopy(self.receipt)
                self.receipt[field] = value
                self.save_receipt()
                with self.assertRaises(ValueError):
                    self.load()
                self.receipt = original
        self.save_receipt()

    def test_rejects_dirty_checkout_and_changed_snapshot(self):
        self.source.side_effect = ValueError("dirty checkout")
        with self.assertRaises(ValueError):
            self.load()
        self.source.side_effect = None
        (self.directory / "source-after-guest.json").write_text("{}")
        with self.assertRaises(ValueError):
            self.load()

    def test_rejects_changed_kernel_boot_record_or_serial(self):
        for path in ("product-kernel.elf", "product-boot/qemu.json", "serial.log"):
            with self.subTest(path=path):
                target = self.directory / path
                original = target.read_bytes()
                target.write_bytes(original + b"changed")
                with self.assertRaises(ValueError):
                    self.load()
                target.write_bytes(original)

    def test_rejects_failed_queryabi_execution_even_with_updated_digest(self):
        self.receipt["qemu_exit"] = 0
        self.save_receipt()
        with self.assertRaises(ValueError):
            self.load()

    def test_rejects_failed_ordinary_boot_validation(self):
        self.boot.side_effect = ValueError("ordinary boot failed")
        with self.assertRaises(ValueError):
            self.load()


def original_initramfs(content=None):
    fields = [1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    content = content or b'#!/bin/sh\nset -eu\ntest "$cpu_count" -eq 1\n' + runner.BOOT_MARKER + b"\n"
    return gzip.compress(runner.pack([("init", fields, content)]), mtime=0)


class GuestAssemblyTests(unittest.TestCase):
    def test_injects_all_probes_and_exact_smp_check(self):
        binaries = {name: b"probe" for name in runner.PROBES}
        archive = runner.initramfs(original_initramfs(), binaries, "test-nonce", 4)
        files = {name: data for name, _, data in runner.unpack(gzip.decompress(archive))}
        self.assertEqual(len(files), 1 + len(runner.PROBES))
        self.assertIn(b'test "$cpu_count" -eq 4', files["init"])
        self.assertEqual(files["init"].count(b"HEPTA_SAFETY nonce=test-nonce"), len(runner.PROBES))

    def test_missing_cpu_check_rejected_even_under_python_optimization(self):
        with self.assertRaises(ValueError):
            runner.initramfs(original_initramfs(runner.BOOT_MARKER), {}, "nonce", 2)

    def test_ci_main_never_builds_and_rejects_changed_guest_artifact(self):
        for tamper in (False, True):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                qemu = base / "qemu"
                qemu.write_bytes(b"test-qemu")
                output = base / "output"
                snapshot = {"head": "a" * 40, "files": {}, "kind": "development-working-bytes"}
                artifacts = {"-kernel": b"kernel", "-initrd": original_initramfs(), "-bios": b"bios"}

                def compile_only(argv, **_):
                    self.assertEqual(argv[0], "test-cc", "CI reuse must not invoke a kernel build")
                    Path(argv[-1]).write_bytes(b"compiled-probe")
                    return subprocess.CompletedProcess(argv, 0, b"", b"")

                def guest_only(argv, directory, timeout):
                    self.assertIn("4", argv)
                    self.assertEqual(timeout, 120)
                    report = json.loads((directory / "result.json").read_text())
                    raw = "".join(f"HEPTA_SAFETY nonce={report['nonce']} probe={name} exit=0\n"
                                  for name in runner.PROBES).encode()
                    if tamper:
                        (directory / "kernel.elf").write_bytes(b"changed")
                    return raw, 33, False, False, 0.1

                args = ["run.py", "--output", str(output), "--product-evidence", str(base / "product"),
                        "--cc", "test-cc", "--smp", "4"]
                with patch.object(sys, "argv", args), patch.object(runner, "snapshot", return_value=snapshot), \
                     patch.object(runner.subprocess, "run", side_effect=compile_only), \
                     patch.object(runner.subprocess, "check_output", return_value="b" * 40), \
                     patch.object(runner, "load_product", return_value=(artifacts, runner.digest(qemu.read_bytes()),
                                  {"kernel_rebuilt": False, "source_kind": "committed-exact-source-product-reuse"})), \
                     patch.object(runner.shutil, "which", return_value=str(qemu)), \
                     patch.object(runner, "run_qemu", side_effect=guest_only), patch("builtins.print"):
                    self.assertEqual(runner.main(), int(tamper))
                report = json.loads((output / "result.json").read_text())
                self.assertEqual(report["passed"], not tamper)
                self.assertFalse(report["kernel_rebuilt"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
