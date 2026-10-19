"""Regression checks for the first real A04 guest capability receipt."""

import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent


class GuestQemuEvidence(unittest.TestCase):
    def load(self, name):
        with (HERE / "baselines" / name).open(encoding="utf-8") as stream:
            return json.load(stream)

    def test_guest_probe_is_capability_evidence_with_two_kernel_gaps(self):
        receipt = self.load("guest-qemu-probe-20261017.json")
        self.assertFalse(receipt["kernel_compatibility_claimed"])
        self.assertEqual(receipt["execution"]["raw_qemu_exit_code"], 33)
        self.assertTrue(receipt["execution"]["guest_boot_verified"])
        self.assertEqual(len(receipt["cases"]), 13)
        statuses = [case["status"] for case in receipt["cases"].values()]
        self.assertEqual(statuses.count("pass"), 11)
        self.assertEqual(statuses.count("blocked_kernel_gap"), 2)
        self.assertIn("scm_rights", receipt["focused_followups"])
        self.assertIn("fd_limit", receipt["focused_followups"])
        self.assertIn("af_unix_abstract", receipt["focused_followups"])
        self.assertEqual(
            receipt["focused_followups"]["scm_rights"]["observed"]["received_fd"],
            "fd_flags=0; cloexec=0",
        )
        self.assertEqual(
            receipt["focused_followups"]["fd_limit"]["observed"]["open_loop"],
            "256 opens succeeded; errno=0",
        )

    def test_exact_rootfs_rebuild_fails_closed_on_elf_bytes(self):
        receipt = self.load("exact-rootfs-input-recheck-20261017.json")
        self.assertFalse(receipt["result"]["exact_elf_match"])
        self.assertFalse(receipt["result"]["full_replay_eligible"])
        self.assertNotEqual(
            receipt["candidate_elf_sha256"]["probe_dynamic"],
            receipt["manifest_expected_sha256"]["probe_dynamic"],
        )


if __name__ == "__main__":
    unittest.main()
