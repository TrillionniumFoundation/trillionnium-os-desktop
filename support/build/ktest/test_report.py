"""Host-only aggregate regressions using explicit synthetic guest evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("ktest_report", Path(__file__).with_name("check-report.py"))
aggregate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aggregate)
checker = aggregate.checker


def serial(crate):
    if crate == "ostd":
        names, count = list(checker.REQUIRED_OSTD_TESTS), checker.MINIMUM_OSTD_TESTS
    elif crate == "aster-core":
        names, count = list(checker.REQUIRED_CORE_TESTS), checker.MINIMUM_CORE_TESTS
    elif crate == "osdk-frame-allocator":
        names = list(checker.REQUIRED_ALLOCATOR_TESTS)
        count = len(names)
    elif crate == "aster-mlsdisk":
        names = list(checker.REQUIRED_MLSDISK_TESTS)
        count = len(names)
    else:
        raise ValueError("fixture has no reviewed crate inventory")
    names.extend(f"{crate.replace('-', '_')}::fixture::test_{index}" for index in range(count - len(names)))
    lines = [f"[ktest runner] running {count} tests in 1 crates", f'running {count} tests in crate "{crate}"']
    for name in names:
        lines.append(f"test {name} ...")
        if name == checker.RESERVE_ALLOCATOR_TESTS[-1]:
            lines.append("PHYSICAL_RESERVE_EXHAUSTION ordinary_frames=65 reserve_start=0x1000 "
                         "reserve_pages=64 ordinary_denied=true reserved_succeeded=true "
                         "returned_to_original_owner=true global_recovery_guarantee=false")
        lines.append("    ok")
    lines.extend((f"test result: ok. {count} passed; 0 failed; 0 filtered out.",
                  "[ktest runner] All crates tested."))
    return ("\n".join(lines) + "\n").encode()


def qemu(crate, guest, raw):
    firmware = "/usr/share/seabios/bios-256k.bin"
    return {"crate": crate, "raw_exit_code": 33, "timed_out": False,
            "serial_sha256": hashlib.sha256(raw).hexdigest(),
            "ktest_profile": "default", "test_name": None,
            "profile": {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
                        "vcpus": 1, "memory_mib": 512, "network": False, "data_disks": False},
            "argv": ["/usr/bin/qemu-system-x86_64", "-kernel", "/fixture/kernel", "-append", "loglevel=error",
                     "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", firmware,
                     "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot",
                     "-nographic", "-display", "none", "-monitor", "none", "-serial", "chardev:serial",
                     "-chardev", f"stdio,id=serial,signal=off,logfile={guest}/serial.log",
                     "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"],
            "artifacts": {"-kernel": {"path": "/fixture/kernel", "size": 1, "sha256": "a" * 64},
                          "-bios": {"path": firmware, "size": 1, "sha256": "b" * 64}}}


def save(path, value):
    path.write_text(json.dumps(value))


class CompleteReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.report = {"passed": True, "crates": []}
        for crate in aggregate.runner.CRATES:
            guest = self.root / crate / "guests/guest-0001"
            guest.mkdir(parents=True)
            raw = serial(crate)
            (guest / "serial.log").write_bytes(raw)
            save(guest / "qemu.json", qemu(crate, guest, raw))
            result = {"passed": True, "guests": [checker.check_guest(guest, crate)]}
            save(self.root / crate / "result.json", result)
            self.report["crates"].append(result)
        save(self.root / "result.json", self.report)

    def reject(self, report):
        save(self.root / "result.json", report)
        with self.assertRaises((ValueError, TypeError)):
            aggregate.check_report(self.root)

    def test_every_current_runner_crate_and_raw_guest_are_rechecked(self):
        self.assertEqual(aggregate.check_report(self.root), self.report)
        self.assertEqual({entry["guests"][0]["crate"] for entry in self.report["crates"]},
                         set(aggregate.runner.CRATES))

    def test_old_two_crate_result_and_missing_or_extra_suites_are_rejected(self):
        for entries in (self.report["crates"][:2], self.report["crates"][:-1],
                        self.report["crates"] + [self.report["crates"][0]]):
            with self.subTest(count=len(entries)):
                self.reject({"passed": True, "crates": entries})

    def test_duplicate_unknown_and_mixed_crate_identities_are_rejected(self):
        duplicate = copy.deepcopy(self.report)
        duplicate["crates"][-1] = duplicate["crates"][0]
        unknown = copy.deepcopy(self.report)
        unknown["crates"][-1]["guests"][0]["crate"] = "unknown"
        mixed = copy.deepcopy(self.report)
        mixed["crates"][0]["guests"].append(copy.deepcopy(mixed["crates"][1]["guests"][0]))
        for report in (duplicate, unknown, mixed):
            self.reject(report)

    def test_false_incomplete_empty_or_duplicate_guest_receipts_are_rejected(self):
        cases = []
        failed = copy.deepcopy(self.report)
        failed["passed"] = False
        cases.append(failed)
        for replacement in ({"passed": False, "guests": []}, {"passed": True, "guests": []},
                            {"passed": True, "guests": [None]}):
            report = copy.deepcopy(self.report)
            report["crates"][0] = replacement
            cases.append(report)
        duplicated = copy.deepcopy(self.report)
        duplicated["crates"][0]["guests"] *= 2
        cases.append(duplicated)
        for report in cases:
            self.reject(report)

    def test_consistent_aggregate_tampering_cannot_replace_raw_execution(self):
        report = copy.deepcopy(self.report)
        report["crates"][0]["guests"][0]["passed"] += 1
        crate = next(iter(aggregate.runner.CRATES))
        save(self.root / crate / "result.json", report["crates"][0])
        self.reject(report)

    def test_raw_log_hash_timeout_and_failed_exit_cannot_be_hidden(self):
        crate = next(iter(aggregate.runner.CRATES))
        guest = self.root / crate / "guests/guest-0001"
        original = aggregate.read_json(guest / "qemu.json")
        for fields in ({"serial_sha256": "0" * 64}, {"timed_out": True}, {"raw_exit_code": 65}):
            with self.subTest(fields=fields):
                save(guest / "qemu.json", dict(original, **fields))
                self.reject(self.report)

    def test_missing_extra_or_linked_raw_guests_are_rejected(self):
        crate = next(iter(aggregate.runner.CRATES))
        directory = self.root / crate / "guests"
        guest = directory / "guest-0001"
        extra = directory / "guest-0002"
        extra.symlink_to(guest, target_is_directory=True)
        self.reject(self.report)
        extra.unlink()
        (guest / "serial.log").unlink()
        self.reject(self.report)

    def test_required_test_soft_skip_is_rejected_even_with_fresh_log_hash(self):
        guest = self.root / "aster-core/guests/guest-0001"
        raw = (guest / "serial.log").read_bytes()
        target = ("test " + checker.REQUIRED_CORE_TESTS[0] + " ...\n    ok").encode()
        self.assertIn(target, raw)
        raw = raw.replace(target, target.replace(b"    ok", b"    [skipped: fixture]\n    ok"), 1)
        (guest / "serial.log").write_bytes(raw)
        record = aggregate.read_json(guest / "qemu.json")
        record["serial_sha256"] = hashlib.sha256(raw).hexdigest()
        save(guest / "qemu.json", record)
        self.reject(self.report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
