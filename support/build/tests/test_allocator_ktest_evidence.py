#!/usr/bin/env python3
"""Mutate synthetic allocator evidence; these host tests never run a kernel."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BUILD = Path(__file__).resolve().parents[1]
ROOT = BUILD.parents[1]
CHECK = runpy.run_path(str(BUILD / "ktest/check.py"))
CRATE = "osdk-frame-allocator"
NAMES = CHECK["REQUIRED_ALLOCATOR_TESTS"]
BASELINE = CHECK["BASELINE_ALLOCATOR_TESTS"]
RESERVE = CHECK["RESERVE_ALLOCATOR_TESTS"]
MARKER = ("PHYSICAL_RESERVE_EXHAUSTION ordinary_frames=90000 reserve_start=0x200000 "
          "reserve_pages=64 ordinary_denied=true reserved_succeeded=true "
          "returned_to_original_owner=true global_recovery_guarantee=false")


def serial_log(names=NAMES):
    lines = ["[ktest runner] running 430 tests in 6 crates",
             '[ktest runner] skipping crate "ostd".',
             f'running {len(names)} tests in crate "{CRATE}"']
    for name in names:
        output = MARKER + "\n" if name == RESERVE[-1] else ""
        lines.append(f"test {name} ...{output} ok")
    lines.extend((f"test result: ok. {len(names)} passed; 0 failed; 0 filtered out.",
                  '[ktest runner] skipping crate "osdk-test-kernel".',
                  "[ktest runner] All crates tested."))
    return ("\r\n".join(lines) + "\r\n").encode()


def qemu_record(guest, serial):
    firmware = "/usr/share/seabios/bios-256k.bin"
    kernel = "/fixture/kernel.elf"
    return {"schema": 1, "crate": CRATE, "raw_exit_code": 33, "timed_out": False,
            "serial_sha256": hashlib.sha256(serial).hexdigest(),
            "ktest_profile": "default", "test_name": None,
            "profile": {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
                        "vcpus": 1, "memory_mib": 512, "network": False, "data_disks": False},
            "artifacts": {option: {"path": path, "size": 10, "sha256": "0" * 64}
                          for option, path in (("-kernel", kernel), ("-bios", firmware))},
            "argv": ["/fixture/qemu-system-x86_64", "-kernel", kernel, "-append", "console=ttyS0",
                     "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", firmware,
                     "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot",
                     "-nographic", "-display", "none", "-monitor", "none", "-serial", "chardev:serial",
                     "-chardev", f"stdio,id=serial,signal=off,logfile={guest}/serial.log",
                     "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]}


class AllocatorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="allocator-evidence-host-only-")
        self.addCleanup(self.temporary.cleanup)
        self.guest = Path(self.temporary.name) / "guest-001"
        self.guest.mkdir()

    def evidence(self, serial=None, mutate=None):
        serial = serial_log() if serial is None else serial
        record = qemu_record(self.guest, serial)
        if mutate:
            mutate(record)
        (self.guest / "serial.log").write_bytes(serial)
        (self.guest / "qemu.json").write_text(json.dumps(record))

    def check(self, allow_filtered=False):
        return CHECK["check_guest"](self.guest, CRATE, allow_filtered)

    def test_complete_inventory_preserves_nine_original_and_eight_added_tests(self):
        self.assertEqual((len(BASELINE), len(RESERVE), len(NAMES)), (9, 8, 17))
        self.evidence()
        result = self.check()
        self.assertEqual((result["passed"], result["filtered"], result["soft_skipped"]), (17, 0, 0))
        self.assertEqual(result["required_allocator_tests"], list(NAMES))
        self.assertEqual(result["allocator_exhaustion"]["ordinary_frames"], 90000)
        self.assertIs(result["allocator_exhaustion"]["global_recovery_guarantee"], False)

    def test_inventory_covers_all_original_and_reserve_source_tests(self):
        source = ROOT / "kernel/asterinas/osdk/deps/frame-allocator/src"
        files = {"chunk.rs": "chunk::test", "set.rs": "set::test",
                 "smp_counter.rs": "smp_counter::test", "test.rs": "test",
                 "reserve/tests.rs": "reserve::tests"}
        actual = set()
        for path in source.rglob("*.rs"):
            names = re.findall(r"#\[ktest\]\s+fn (\w+)\(", path.read_text())
            if names:
                relative = str(path.relative_to(source))
                self.assertIn(relative, files, "new allocator test module requires explicit gate review")
                actual.update(f"osdk_frame_allocator::{files[relative]}::{name}" for name in names)
        self.assertEqual(actual, set(NAMES))

    def test_each_original_and_new_test_is_required_exactly_once(self):
        for name in NAMES:
            for mode in ("missing", "renamed", "duplicate"):
                with self.subTest(name=name, mode=mode):
                    names = tuple(n for n in NAMES if n != name) if mode == "missing" else (
                        tuple("osdk_frame_allocator::fixture::other" if n == name else n for n in NAMES)
                        if mode == "renamed" else (*NAMES, name))
                    self.evidence(serial_log(names))
                    with self.assertRaisesRegex(ValueError, "exactly once"):
                        self.check()

    def test_neither_original_only_nor_reserve_only_is_complete(self):
        for names in (BASELINE, RESERVE):
            with self.subTest(names=names):
                self.evidence(serial_log(names))
                with self.assertRaisesRegex(ValueError, "exactly once"):
                    self.check()

    def test_allow_filtered_cannot_weaken_allocator_gate(self):
        self.evidence()
        with self.assertRaisesRegex(ValueError, "never permits filtered"):
            self.check(allow_filtered=True)
        filtered = serial_log().replace(b"17 tests in crate", b"18 tests in crate").replace(
            b"0 filtered out", b"1 filtered out")
        self.evidence(filtered)
        with self.assertRaisesRegex(ValueError, "unexpected filtered"):
            self.check()
        with self.assertRaisesRegex(ValueError, "never permits filtered"):
            self.check(allow_filtered=True)

    def test_every_soft_skip_is_rejected_including_original_tests(self):
        for name in NAMES:
            with self.subTest(name=name):
                skipped = serial_log().replace(f"test {name} ...".encode(),
                                              f"test {name} ...[skipped: fixture]".encode())
                self.evidence(skipped)
                with self.assertRaisesRegex(ValueError, "soft-skipped"):
                    self.check()

    def test_summary_cannot_replace_individual_success_results(self):
        for name in NAMES:
            with self.subTest(name=name):
                raw = serial_log()
                if name == RESERVE[-1]:
                    raw = raw.replace((MARKER + "\n ok").encode(), (MARKER + "\n FAILED").encode())
                else:
                    raw = raw.replace(f"test {name} ... ok".encode(), f"test {name} ... FAILED".encode())
                self.evidence(raw)
                with self.assertRaisesRegex(ValueError, "terminal ok"):
                    self.check()

    def test_missing_duplicate_or_out_of_scope_exhaustion_markers_are_rejected(self):
        raw = serial_log()
        missing = raw.replace(MARKER.encode(), b"")
        for serial in (missing, raw + MARKER.encode(), MARKER.encode() + b"\n" + missing,
                       missing.replace(b"test osdk_frame_allocator::chunk::test::greater_order_of_works ...",
                                       b"test osdk_frame_allocator::chunk::test::greater_order_of_works ..." +
                                       MARKER.encode() + b"\n")):
            with self.subTest(serial=serial[:70]):
                self.evidence(serial)
                with self.assertRaisesRegex(ValueError, "exhaustion marker"):
                    self.check()

    def test_exhaustion_receipt_rejects_false_or_inconsistent_claims(self):
        for before, after in (("ordinary_frames=90000", "ordinary_frames=64"),
                              ("reserve_start=0x200000", "reserve_start=0x200001"),
                              ("reserve_start=0x200000", "reserve_start=0x0"),
                              ("reserve_pages=64", "reserve_pages=63"),
                              ("ordinary_denied=true", "ordinary_denied=false"),
                              ("reserved_succeeded=true", "reserved_succeeded=false"),
                              ("returned_to_original_owner=true", "returned_to_original_owner=false"),
                              ("global_recovery_guarantee=false", "global_recovery_guarantee=true")):
            with self.subTest(mutation=after):
                self.evidence(serial_log().replace(before.encode(), after.encode()))
                with self.assertRaisesRegex(ValueError, "exhaustion"):
                    self.check()

    def test_n0_profile_and_actual_invocation_must_agree(self):
        mutations = (
            lambda r: r.update(ktest_profile="permission-attr-smp"),
            lambda r: r.update(test_name="reserve"),
            lambda r: r.pop("test_name"),
            lambda r: r["profile"].update(vcpus=2),
            lambda r: r["profile"].update(accel="kvm"),
            lambda r: r["argv"].__setitem__(r["argv"].index("-smp") + 1, "2"),
            lambda r: r["argv"].extend(("-smp", "1")),
            lambda r: r["argv"].extend(("-device", "virtio-net-pci")),
            lambda r: r["argv"].__setitem__(r["argv"].index("-accel") + 1, "kvm"),
            lambda r: r["artifacts"]["-kernel"].update(path="/another/kernel.elf"),
            lambda r: r["artifacts"]["-kernel"].pop("sha256"),
            lambda r: r.update(timed_out=None),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                self.evidence(mutate=mutation)
                with self.assertRaises(ValueError):
                    self.check()

    def test_raw_qemu_failure_timeout_or_changed_serial_cannot_pass(self):
        for code in (0, 1, 65, 124, -9):
            self.evidence(mutate=lambda r: r.update(raw_exit_code=code))
            with self.assertRaisesRegex(ValueError, "status 33"):
                self.check()
        self.evidence(mutate=lambda r: r.update(timed_out=True))
        with self.assertRaisesRegex(ValueError, "status 33"):
            self.check()
        self.evidence()
        with (self.guest / "serial.log").open("ab") as output:
            output.write(b"changed bytes\n")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.check()

    def test_early_runner_completion_is_not_complete_execution(self):
        marker = b"[ktest runner] All crates tested."
        self.evidence(marker + b"\n" + serial_log().replace(marker, b""))
        with self.assertRaisesRegex(ValueError, "finish before"):
            self.check()

    def test_run_entry_rejects_allocator_filter_before_any_build_or_output(self):
        output = self.guest / "must-not-exist"
        for crates in ([], ["--crate", CRATE], ["--crate", "ostd", "--crate", CRATE]):
            result = subprocess.run([sys.executable, "-I", str(BUILD / "ktest/run.py"),
                                     *crates, "--test-name", "reserve", "--output", str(output)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("complete unfiltered default N0", result.stderr)
            self.assertFalse(output.exists())

    def test_recorder_rejects_allocator_filter_or_smp_before_qemu(self):
        recorder = runpy.run_path(str(BUILD / "ktest/record-qemu.py"))
        for extra in ({"A01_KTEST_TEST_NAME": "reserve"}, {"A01_KTEST_PROFILE": "permission-attr-smp"}):
            environment = {"A01_KTEST_CRATE": CRATE, **extra}
            with patch.dict(os.environ, environment, clear=True), patch.object(sys, "argv", ["record-qemu.py"]):
                with self.assertRaisesRegex(SystemExit, "complete unfiltered default N0"):
                    recorder["main"]()


if __name__ == "__main__":
    unittest.main(verbosity=2)
