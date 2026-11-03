"""Host oracle tests; all guest records here are explicitly synthetic."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = load("partition_report_fixture", HERE / "test_report.py")
checker = fixture.checker
runner = fixture.aggregate.runner
prepare = load("partition_lock_prepare", HERE / "prepare-locks.py")


def serial(names=None):
    names = list(checker.REQUIRED_PARTITION_TESTS if names is None else names)
    lines = [f"[ktest runner] running {len(names)} tests in 1 crates",
             f'running {len(names)} tests in crate "aster-block"']
    for name in names:
        lines.extend((f"test {name} ...", "    ok"))
    lines.extend((f"test result: ok. {len(names)} passed; 0 failed; 0 filtered out.",
                  "[ktest runner] All crates tested."))
    return ("\n".join(lines) + "\n").encode()


class PartitionGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.guest = Path(self.temporary.name) / "guest-0001"
        self.guest.mkdir()

    def check(self, raw=None, transform=None, allow_filtered=False):
        raw = serial() if raw is None else raw
        qemu = fixture.qemu("aster-block", self.guest, raw)
        if transform:
            transform(qemu)
        (self.guest / "serial.log").write_bytes(raw)
        (self.guest / "qemu.json").write_text(json.dumps(qemu))
        return checker.check_guest(self.guest, "aster-block", allow_filtered)

    def test_complete_named_suite_and_source_inventory_match(self):
        result = self.check()
        self.assertEqual(result["passed"], 24)
        self.assertFalse(result["physical_media_qualified"])
        source = (PROJECT / "kernel/asterinas/kernel/core/comps/block/src/partition/table/tests.rs").read_text()
        names = re.findall(r"#\[cfg_attr\(ktest, ktest\)\]\s*#\[cfg_attr\(test, test\)\]\s*fn (\w+)\(", source)
        self.assertEqual(sorted("aster_block::partition::table::tests::" + name for name in names),
                         sorted(checker.REQUIRED_PARTITION_TESTS))

    def test_missing_duplicate_and_substituted_cases_are_rejected(self):
        names = list(checker.REQUIRED_PARTITION_TESTS)
        for changed in (names[:-1], names[:-1] + [names[0]], names[:-1] + ["aster_block::fixture::fake"]):
            with self.assertRaises(ValueError):
                self.check(serial(changed))

    def test_skips_missing_terminal_and_early_completion_are_rejected(self):
        raw = serial()
        for changed in (
            raw.replace(b"    ok", b"[skipped: synthetic]\n    ok", 1),
            raw.replace(b"    ok", b"", 1),
            raw.replace(b"[ktest runner] All crates tested.\n", b"")
               .replace(b"test result:", b"[ktest runner] All crates tested.\ntest result:"),
        ):
            with self.assertRaises(ValueError):
                self.check(changed)

    def test_filters_timeouts_and_changed_qemu_profile_are_rejected(self):
        with self.assertRaises(ValueError):
            self.check(allow_filtered=True)
        for transform in (
            lambda record: record.update(timed_out=True),
            lambda record: record.update(raw_exit_code=0),
            lambda record: record["profile"].update(vcpus=2),
            lambda record: record.update(test_name="one_case"),
        ):
            with self.assertRaises(ValueError):
                self.check(transform=transform)

    def test_default_four_crate_gate_is_unchanged(self):
        expected = {"ostd", "aster-core", "osdk-frame-allocator", "aster-mlsdisk"}
        self.assertEqual(set(runner.CRATES), expected)
        self.assertEqual(set(prepare.CRATES), expected)
        self.assertEqual(runner.OPTIONAL_CRATES, {"aster-block": "kernel/core/comps/block"})
        self.assertEqual(prepare.OPTIONAL_CRATES, runner.OPTIONAL_CRATES)

    def test_seed_audit_allows_only_exact_new_local_base(self):
        base = {"name": "aster-block-osdk-bin", "version": "0.1.0"}
        seed_package = {"name": "existing", "version": "1.0.0", "source": "registry+fixture", "checksum": "a" * 64}
        seed = {prepare.package_key(seed_package)}
        prepare.audit_packages([seed_package, base], seed, "aster-block")
        for extra in (
            {"name": "extra-local", "version": "0.1.0"},
            {**seed_package, "version": "1.0.1"},
            {**seed_package, "checksum": "b" * 64},
        ):
            with self.assertRaises(SystemExit):
                prepare.audit_packages([seed_package, base, extra], seed, "aster-block")
        with self.assertRaises(SystemExit):
            prepare.audit_packages([seed_package, {**base, "version": "0.19.0"}], seed, "aster-block")

    def test_optional_bootstrap_cannot_bypass_original_suite_prefetch(self):
        for arguments in ([], ["--crate", "aster-core"]):
            result = subprocess.run(
                [sys.executable, "-I", "-B", str(HERE / "prepare-locks.py"),
                 "--bootstrap-optional", *arguments], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("optional crates only", result.stderr)


if __name__ == "__main__":
    unittest.main()
