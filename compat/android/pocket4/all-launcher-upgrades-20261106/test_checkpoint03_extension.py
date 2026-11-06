#!/usr/bin/env python3
"""Offline checks against actual receipts and corrupted temporary copies only."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import checkpoint03_extension as audit

ROOT = Path(__file__).resolve().parent


class CheckpointReceiptControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recovery = audit.successor_recovery(ROOT)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="checkpoint03-receipt-control-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def install_copy(self, name="jd-02"):
        source = ROOT / "successor_install/actual" / name
        target = self.root / "successor_install/actual" / name
        target.mkdir(parents=True)
        for file in ("stdout.raw.jsonl", "terminal.raw.json"):
            shutil.copyfile(source / file, target / file)
        return target

    def rewrite_result(self, directory, mutator):
        path = directory / "stdout.raw.jsonl"
        stage, value = map(audit.parse, path.read_bytes().splitlines())
        mutator(value)
        # Keep the copied envelope internally consistent so the negative test
        # reaches the semantic boundary rather than only a checksum failure.
        result_bytes = audit.canonical({k: v for k, v in value.items() if k != "final_receipt"}) + b"\n"
        value["final_receipt"].update(bytes=len(result_bytes), sha256=hashlib.sha256(result_bytes).hexdigest())
        raw = audit.canonical(stage) + b"\n" + audit.canonical(value) + b"\n"
        path.write_bytes(raw)
        terminal_path = directory / "terminal.raw.json"
        terminal = audit.parse(terminal_path.read_bytes())
        terminal["log_bytes"]["stdout"].update(stored=len(raw), seen=len(raw))
        terminal_path.write_bytes(audit.canonical(terminal) + b"\n")

    def evaluate(self):
        return audit.successor_installations(self.root, self.recovery)

    def test_actual_split_install_keeps_both_old_APKs_and_first_rejection(self):
        self.install_copy("jd-01")
        self.install_copy("jd-02")
        updates, attempts, incomplete, current = self.evaluate()
        self.assertEqual(set(updates), {"com.jingdong.app.mall"})
        self.assertEqual([a["counted_as_upgrade"] for a in attempts], [False, True])
        self.assertEqual(attempts[1]["retained_previous_APK_count"], 2)
        self.assertEqual(attempts[1]["retained_previous_APK_bytes"], 294389107)
        self.assertEqual(current["com.jingdong.app.mall"]["version_code"], 102918)
        self.assertEqual(incomplete, [])

    def test_missing_terminal_does_not_count_upgrade(self):
        directory = self.install_copy()
        (directory / "terminal.raw.json").unlink()
        updates, attempts, incomplete, _ = self.evaluate()
        self.assertEqual(updates, {})
        self.assertEqual(attempts, [])
        self.assertEqual(len(incomplete), 1)

    def test_nondurable_terminal_refused(self):
        directory = self.install_copy()
        path = directory / "terminal.raw.json"
        value = audit.parse(path.read_bytes())
        value["output_durable"] = False
        path.write_bytes(audit.canonical(value))
        with self.assertRaisesRegex(ValueError, "terminal_not_durable_complete"):
            self.evaluate()

    def test_lost_old_split_is_refused_even_with_resealed_envelope(self):
        directory = self.install_copy()
        self.rewrite_result(directory, lambda v: v["previous_apks_retained"].pop())
        with self.assertRaisesRegex(ValueError, "R2_complete_old_set_not_retained"):
            self.evaluate()

    def test_replaced_old_split_hash_is_refused(self):
        directory = self.install_copy()
        def mutate(value):
            value["previous_apks_retained"][1]["retained"]["sha256"] = "0" * 64
        self.rewrite_result(directory, mutate)
        with self.assertRaisesRegex(ValueError, "R2_retained_old_set_bytes_or_identity_mismatch"):
            self.evaluate()

    def test_current_epoch_mismatch_refused(self):
        directory = self.install_copy()
        def mutate(value):
            value["guard_after"]["runtime_epoch_sha256"] = "0" * 64
        self.rewrite_result(directory, mutate)
        with self.assertRaisesRegex(ValueError, "install_guard_epoch_changed"):
            self.evaluate()

    def test_data_identity_change_refused(self):
        directory = self.install_copy()
        def mutate(value):
            value["after"]["data_directories"]["user"]["inode"] += 1
        self.rewrite_result(directory, mutate)
        with self.assertRaisesRegex(ValueError, "install_UID_signer_data_or_version_chain"):
            self.evaluate()

    def test_json_integer_precision_and_duplicate_key(self):
        actual = audit.parse((ROOT / "successor_install/actual/jd-02/stdout.raw.jsonl").read_bytes().splitlines()[-1])
        value = actual["previous_apks_retained"][0]["original"]["file"]["st_ctime_ns"]
        self.assertGreater(value, 2 ** 53)
        self.assertEqual(audit.parse(audit.canonical({"ns": value}))["ns"], value)
        with self.assertRaisesRegex(ValueError, "duplicate_JSON_key"):
            audit.parse(b'{"ns":1,"ns":2}')

    def test_actual_s33_manifest_matches_douyin_installed_bytes(self):
        candidate = audit.additional_candidates(ROOT)["com.ss.android.ugc.aweme"]
        actual = audit.parse((ROOT / "successor_install/actual/douyin-01/stdout.raw.jsonl").read_bytes().splitlines()[-1])
        self.assertEqual(candidate["actual"]["manifest"]["version_name"], "41.0.0")
        self.assertEqual(candidate["actual"]["manifest"]["version_code"], actual["after"]["version_code"])
        self.assertTrue(audit.matches(candidate["actual"]["apk"], actual["after"]["apks"][0]))
        self.assertEqual(candidate["job_id"], "1a1b107d8dc-fc05-7523")

    def test_unknown_new_version_name_never_uses_old_reference(self):
        row = {"installed_version_name": None, "version_name_reference": "40.8.0", "installed_version_code": 410001,
               "install_job_id": "saved-success-only"}
        self.assertEqual(audit.installed_version_label(row), "未读新 manifest")
        self.assertNotIn("40.8.0", audit.installed_version_label(row))


if __name__ == "__main__":
    unittest.main(verbosity=2)
