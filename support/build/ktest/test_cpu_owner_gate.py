"""Tampered-log oracle tests, never kernel execution receipts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cpu_owner_gate", HERE / "check.py")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class CpuOwnerGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.guest = Path(self.temporary.name)
        self.names = list(CHECKER.REQUIRED_CORE_TESTS)
        self.names += [f"aster_core::inert::filler_{i}" for i in
                       range(CHECKER.MINIMUM_CORE_TESTS - len(self.names))]

    def write(self, names=None, changed=None, after_summary=False):
        names = self.names if names is None else names
        changed = {} if changed is None else changed
        blocks = [f"test {name} ...{changed.get(name, ' ok')}\n" for name in names]
        summary = f"test result: ok. {len(names)} passed; 0 failed; 0 filtered out.\n"
        if after_summary:
            index = names.index(CHECKER.CPU_OWNER_CONTINUITY_TESTS[0])
            moved = blocks.pop(index)
            payload = "".join(blocks) + summary + moved
        else:
            payload = "".join(blocks) + summary
        serial = (f"[ktest runner] running {len(names)} tests in 1 crates\n"
                  f'running {len(names)} tests in crate "aster-core"\n'
                  + payload + "[ktest runner] All crates tested.\n").encode()
        (self.guest / "serial.log").write_bytes(serial)
        (self.guest / "qemu.json").write_text(json.dumps({
            "serial_sha256": hashlib.sha256(serial).hexdigest(), "raw_exit_code": 33,
            "timed_out": False, "crate": "aster-core",
        }))

    def test_retains_all_previous_names_and_adds_three(self):
        self.assertEqual(CHECKER.MINIMUM_CORE_TESTS, 368)
        self.assertEqual(len(CHECKER.REQUIRED_CORE_TESTS), 129)
        retained = [name for name in CHECKER.REQUIRED_CORE_TESTS
                    if name not in CHECKER.CPU_OWNER_CONTINUITY_TESTS]
        self.assertEqual(len(retained), 126)
        digest = hashlib.sha256(json.dumps(retained, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, "57a8097d6d45abd2629a9fa5f1cd4749473d5ea8ef0756bdc6d235a382fb0500")

    def test_complete_new_inventory(self):
        self.write()
        result = CHECKER.check_guest(self.guest, "aster-core", False)
        self.assertEqual(result["passed"], 368)
        self.assertEqual(result["required_core_tests"], list(CHECKER.REQUIRED_CORE_TESTS))

    def test_missing_or_repeated_new_test(self):
        target = CHECKER.CPU_OWNER_CONTINUITY_TESTS[0]
        for names in ([name if name != target else "aster_core::inert::replacement" for name in self.names],
                      self.names[:-1] + [target]):
            self.write(names)
            with self.assertRaisesRegex(ValueError, "required core"):
                CHECKER.check_guest(self.guest, "aster-core", False)

    def test_new_case_requires_own_terminal_and_no_skip(self):
        for block in ("\n diagnostics", " FAILED", "\n [skipped: feature]\n ok"):
            self.write(changed={CHECKER.CPU_OWNER_CONTINUITY_TESTS[0]: block})
            with self.subTest(block=block), self.assertRaises(ValueError):
                CHECKER.check_guest(self.guest, "aster-core", False)

    def test_new_case_cannot_follow_summary(self):
        self.write(after_summary=True)
        with self.assertRaises(ValueError):
            CHECKER.check_guest(self.guest, "aster-core", False)

    def test_old_required_name_still_required(self):
        target = next(name for name in CHECKER.REQUIRED_CORE_TESTS
                      if name not in CHECKER.CPU_OWNER_CONTINUITY_TESTS)
        self.write([name if name != target else "aster_core::inert::replacement" for name in self.names])
        with self.assertRaisesRegex(ValueError, "required core"):
            CHECKER.check_guest(self.guest, "aster-core", False)

    def test_old_denominator_cannot_satisfy_new_full_gate(self):
        self.write(self.names[:365])
        with self.assertRaisesRegex(ValueError, "shrank"):
            CHECKER.check_guest(self.guest, "aster-core", False)


if __name__ == "__main__":
    unittest.main()
