#!/usr/bin/env python3
"""Mutate synthetic MLSDisk evidence; these host tests never execute a kernel."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

BUILD = Path(__file__).resolve().parents[1]
ROOT = BUILD.parents[1]
CHECK = runpy.run_path(str(BUILD / "ktest/check.py"))
LOCKS = runpy.run_path(str(BUILD / "ktest/prepare-locks.py"))
N0_FIXTURE = runpy.run_path(str(BUILD / "tests/test_allocator_ktest_evidence.py"))
CRATE = "aster-mlsdisk"
NAMES = CHECK["REQUIRED_MLSDISK_TESTS"]


def serial_log(names=NAMES):
    lines = ["[ktest runner] running 430 tests in 6 crates",
             '[ktest runner] skipping crate "ostd".',
             f'running {len(names)} tests in crate "{CRATE}"']
    lines.extend(f"test {name} ... ok" for name in names)
    lines.extend((f"test result: ok. {len(names)} passed; 0 failed; 0 filtered out.",
                  '[ktest runner] skipping crate "osdk-test-kernel".',
                  "[ktest runner] All crates tested."))
    return ("\r\n".join(lines) + "\r\n").encode()


class MlsDiskEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mlsdisk-evidence-host-only-")
        self.addCleanup(self.temporary.cleanup)
        self.guest = Path(self.temporary.name) / "guest-001"
        self.guest.mkdir()

    def evidence(self, serial=None, mutate=None):
        serial = serial_log() if serial is None else serial
        record = N0_FIXTURE["qemu_record"](self.guest, serial)
        record["crate"] = CRATE
        if mutate:
            mutate(record)
        (self.guest / "serial.log").write_bytes(serial)
        (self.guest / "qemu.json").write_text(json.dumps(record))

    def check(self, allow_filtered=False):
        return CHECK["check_guest"](self.guest, CRATE, allow_filtered)

    def test_complete_native_tests_do_not_claim_physical_durability(self):
        self.evidence()
        result = self.check()
        self.assertEqual((result["declared"], result["passed"], result["filtered"], result["soft_skipped"]), (15, 15, 0, 0))
        self.assertEqual(result["required_mlsdisk_tests"], list(NAMES))
        self.assertIs(result["mlsdisk_media_durability_qualified"], False)

    def test_inventory_preserves_original_native_test_and_distinguishes_host_tests(self):
        source = ROOT / "kernel/asterinas/kernel/core/comps/mlsdisk/src"
        names = []
        host_tests = 0
        for path in source.rglob("*.rs"):
            text = path.read_text()
            found = re.findall(r"#\[ktest\]\s+fn (\w+)\(", text)
            if found:
                modules = {
                    source / "lib.rs": "aster_mlsdisk::test::",
                    source / "os/mod.rs": "aster_mlsdisk::os::entropy_test::",
                    source / "layers/3-log/tx_log.rs": "aster_mlsdisk::layers::log::tx_log::entropy_tests::",
                }
                self.assertIn(path, modules, "review every new native test module")
                names.extend(modules[path] + name for name in found)
            host_tests += len(re.findall(r"#\[test\]\s+fn \w+\(", text))
        self.assertEqual(set(names), set(NAMES))
        self.assertEqual(len(names), len(NAMES))
        self.assertIn("aster_mlsdisk::test::write_sync_read", names)
        self.assertEqual(host_tests, 34)

    def test_every_named_test_is_required_exactly_once(self):
        for name in NAMES:
            variants = (tuple(n for n in NAMES if n != name), (*NAMES, name),
                        tuple("aster_mlsdisk::test::replacement" if n == name else n for n in NAMES))
            for names in variants:
                with self.subTest(name=name, names=names):
                    self.evidence(serial_log(names))
                    with self.assertRaisesRegex(ValueError, "exactly once"):
                        self.check()

    def test_no_filter_or_soft_skip_can_qualify(self):
        self.evidence()
        with self.assertRaisesRegex(ValueError, "never permits filtered"):
            self.check(allow_filtered=True)
        filtered = serial_log().replace(b"15 tests in crate", b"16 tests in crate").replace(
            b"0 filtered out", b"1 filtered out")
        self.evidence(filtered)
        with self.assertRaisesRegex(ValueError, "unexpected filtered"):
            self.check()
        for name in NAMES:
            self.evidence(serial_log().replace(f"test {name} ...".encode(),
                                              f"test {name} ...[skipped: fixture]".encode()))
            with self.assertRaisesRegex(ValueError, "soft-skipped"):
                self.check()

    def test_summary_cannot_replace_each_terminal_ok(self):
        for name in NAMES:
            for after in ("FAILED", "", "ok\n later unexpected text"):
                with self.subTest(name=name, after=after):
                    self.evidence(serial_log().replace(f"test {name} ... ok".encode(),
                                                      f"test {name} ... {after}".encode()))
                    with self.assertRaisesRegex(ValueError, "terminal ok"):
                        self.check()

    def test_raw_exit_timeout_and_log_identity_remain_mandatory(self):
        for code in (0, 1, 65, 124, -9):
            self.evidence(mutate=lambda r: r.update(raw_exit_code=code))
            with self.assertRaisesRegex(ValueError, "status 33"):
                self.check()
        self.evidence(mutate=lambda r: r.update(timed_out=True))
        with self.assertRaisesRegex(ValueError, "status 33"):
            self.check()
        self.evidence()
        (self.guest / "serial.log").write_bytes(serial_log() + b"changed bytes")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.check()

    def test_fixed_profile_and_actual_qemu_invocation_must_agree(self):
        mutations = (
            lambda r: r.update(crate="aster-core"),
            lambda r: r.update(test_name="flush"),
            lambda r: r.update(ktest_profile="permission-attr-smp"),
            lambda r: r["profile"].update(vcpus=2),
            lambda r: r["argv"].__setitem__(r["argv"].index("-accel") + 1, "kvm"),
            lambda r: r["argv"].extend(("-device", "virtio-blk-pci")),
            lambda r: r["artifacts"]["-kernel"].update(path="/different/kernel.elf"),
            lambda r: r["artifacts"]["-kernel"].pop("sha256"),
            lambda r: r.update(timed_out=None),
        )
        for mutation in mutations:
            self.evidence(mutate=mutation)
            with self.assertRaises(ValueError):
                self.check()

    def test_runner_completion_must_follow_all_tests_and_summary(self):
        marker = b"[ktest runner] All crates tested."
        self.evidence(marker + b"\n" + serial_log().replace(marker, b""))
        with self.assertRaisesRegex(ValueError, "finish before"):
            self.check()

    def test_run_entry_rejects_filters_before_any_build_or_output(self):
        output = self.guest / "must-not-exist"
        for crates in (["--crate", CRATE], ["--crate", "ostd", "--crate", CRATE]):
            result = subprocess.run([sys.executable, "-I", str(BUILD / "ktest/run.py"),
                                     *crates, "--test-name", "flush", "--output", str(output)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("complete unfiltered default N0", result.stderr)
            self.assertFalse(output.exists())

    def test_recorder_rejects_filter_and_smp_before_qemu(self):
        recorder = runpy.run_path(str(BUILD / "ktest/record-qemu.py"))
        for extra in ({"A01_KTEST_TEST_NAME": "flush"}, {"A01_KTEST_PROFILE": "permission-attr-smp"}):
            with patch.dict(os.environ, {"A01_KTEST_CRATE": CRATE, **extra}, clear=True), \
                    patch.object(sys, "argv", ["record-qemu.py"]):
                with self.assertRaisesRegex(SystemExit, "complete unfiltered default N0"):
                    recorder["main"]()

    def test_fourth_manifest_retains_original_generator_runtime_dependencies(self):
        manifest = tomllib.loads(LOCKS["generated_manifest"](ROOT / "kernel/asterinas", CRATE))
        self.assertEqual(manifest["package"]["version"], "0.1.0")
        self.assertEqual(manifest["package"]["name"], "aster-mlsdisk-osdk-bin")
        self.assertEqual(set(manifest["dependencies"]),
                         {CRATE, "ostd", "osdk-frame-allocator", "osdk-heap-allocator", "osdk-test-kernel"})
        self.assertIs(manifest["dependencies"][CRATE]["default-features"], False)
        self.assertNotIn("default-features", manifest["dependencies"]["ostd"])
        self.assertEqual(manifest["features"], {})

    def test_independent_lock_only_adds_mlsdisk_test_base_to_pinned_seed(self):
        upstream = ROOT / "kernel/asterinas"
        seed = tomllib.loads(LOCKS["original_seed"](upstream).decode())["package"]
        seed_set = {LOCKS["package_key"](p) for p in seed}
        packages = tomllib.loads((BUILD / "ktest/locks/aster-mlsdisk.Cargo.lock").read_text())["package"]
        expected = LOCKS["audit_packages"](packages, seed_set, CRATE)
        self.assertEqual(expected, [("aster-mlsdisk-osdk-bin", "0.1.0", "", "")])
        wrong = [dict(p) for p in packages]
        next(p for p in wrong if p["name"] == "aster-mlsdisk-osdk-bin")["version"] = "0.19.0"
        with self.assertRaisesRegex(SystemExit, "dependency drift"):
            LOCKS["audit_packages"](wrong, seed_set, CRATE)
        replacement = tomllib.loads((BUILD / "ktest/locks/ostd.Cargo.lock").read_text())["package"]
        with self.assertRaisesRegex(SystemExit, "dependency drift"):
            LOCKS["audit_packages"](replacement, seed_set, CRATE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
