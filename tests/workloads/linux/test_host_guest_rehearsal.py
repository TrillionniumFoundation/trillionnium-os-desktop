"""Original Linux guest-script rehearsal helpers; NO QEMU claim."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a04_guest_shell", HERE / "host_guest_rehearsal.py")
rehearsal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearsal)


class GuestShellRehearsal(unittest.TestCase):
    def setUp(self):
        self.reference = json.loads((HERE / "baselines/linux-debian13-x86_64.json").read_text())

    def serial_lines(self):
        lines = []
        for name, _, _ in rehearsal.guest.reference_elf_cases(self.reference):
            lines += ["A04_CASE_BEGIN=" + name,
                      json.dumps(self.reference["cases"][name]["facts"], sort_keys=True),
                      "A04_CASE_END=" + name + ":0"]
        return "\n".join(lines) + "\n"

    def test_original_linux_shell_replay_never_claims_guest(self):
        ok, evidence = rehearsal.evaluate_output(self.serial_lines(), 0, self.reference)
        self.assertTrue(ok)
        self.assertEqual(evidence["counts"], {"pass": 28, "fail": 0, "not_run": 4})
        self.assertFalse(evidence["guest_execution_verified"])
        self.assertFalse(evidence["guest_compatibility_passed"])
        self.assertIsNone(evidence["boot_evidence"]["qemu_exit_code"])

    def test_shell_rehearsal_rejects_changed_errno(self):
        changed = self.serial_lines().replace('"ENOENT": 2', '"ENOENT": 38', 1)
        self.assertNotEqual(changed, self.serial_lines())
        ok, evidence = rehearsal.evaluate_output(changed, 0, self.reference)
        self.assertFalse(ok)
        self.assertEqual(evidence["counts"]["fail"], 1)

    def test_missing_case_or_nonzero_exit_is_not_success(self):
        baseline = self.serial_lines()
        self.assertFalse(rehearsal.evaluate_output(baseline.replace(
            "A04_CASE_BEGIN=dynamic.smoke", "A04_CASE_BEGIN=invalid.smoke"),
            0, self.reference)[0])
        self.assertFalse(rehearsal.evaluate_output(baseline, 1, self.reference)[0])

    def test_absent_busybox_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "BusyBox input is absent"):
                rehearsal.stage_busybox(Path(tmp), Path(tmp) / "missing-busybox")


if __name__ == "__main__":
    unittest.main()
