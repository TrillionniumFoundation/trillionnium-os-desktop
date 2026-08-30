from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_LOCK_SHA256 = "9219ed5bbe3dbac2fdb60b5fcfa58318be4e21f6e3cce395f7f486222827b8bd"
EXPECTED_PACKAGE_SET_SHA256 = (
    "6f0f8ba20a4deba6d1273ea75ea5b2fb209f71f30b810240f1f63c22f67bf6b5"
)


class CommittedD1LockBindingTests(unittest.TestCase):
    def test_selection_is_bound_to_exact_committed_signed_lock(self) -> None:
        selection = json.loads(
            (ROOT / "manifests/debian-d1.selection.json").read_text(encoding="utf-8")
        )
        lock_path = ROOT / "manifests/debian-d1.lock.v1.json"
        lock_bytes = lock_path.read_bytes()
        lock = json.loads(lock_bytes)

        self.assertEqual(selection["status"], "COMMITTED_SIGNED_D1_PACKAGE_LOCK")
        self.assertEqual(
            selection["committed_d1_lock"], "manifests/debian-d1.lock.v1.json"
        )
        self.assertEqual(hashlib.sha256(lock_bytes).hexdigest(), EXPECTED_LOCK_SHA256)
        self.assertEqual(selection["committed_d1_lock_sha256"], EXPECTED_LOCK_SHA256)
        self.assertEqual(lock["resolved_package_count"], 352)
        self.assertEqual(selection["expected_d1_package_count"], 352)
        self.assertEqual(lock["package_set_sha256"], EXPECTED_PACKAGE_SET_SHA256)
        self.assertEqual(
            selection["expected_d1_package_set_sha256"],
            EXPECTED_PACKAGE_SET_SHA256,
        )
        self.assertTrue(all(value is False for value in lock["claims"].values()))


if __name__ == "__main__":
    unittest.main()
