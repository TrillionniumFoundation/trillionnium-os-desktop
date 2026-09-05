from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import finalize_d1_evidence  # noqa: E402
import verify_d1_artifact  # noqa: E402


class D1EvidenceDuplicateKeyTests(unittest.TestCase):
    def test_finalizer_rejects_duplicate_members(self) -> None:
        self._assert_rejected(finalize_d1_evidence.load_json)

    def test_portable_verifier_rejects_duplicate_members(self) -> None:
        self._assert_rejected(
            lambda path: verify_d1_artifact.load_json(path, "evidence")
        )

    def _assert_rejected(self, loader) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            path.write_text(
                '{"status":"PASS","nested":{"claim":true,"claim":false}}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                loader(path)


if __name__ == "__main__":
    unittest.main()
