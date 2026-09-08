from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "tests/qemu/run-d1-pipeline.sh"


class D1PipelineExitStatusTests(unittest.TestCase):
    def test_evidence_gather_failure_cannot_be_suppressed(self) -> None:
        source = PIPELINE.read_text(encoding="utf-8")
        start = source.index("on_exit() {")
        end = source.index("\n}\ntrap on_exit EXIT", start)
        handler = source[start:end]
        self.assertIn("gather_evidence\n  gather_code=$?", handler)
        self.assertIn('if [[ "$gather_code" -ne 0 ]]; then', handler)
        self.assertIn('if [[ "$code" -eq 0 ]]; then', handler)
        self.assertIn("code=1", handler)
        self.assertNotIn("gather_evidence || true", handler)
        gather_start = source.index("gather_evidence() {")
        gather_end = source.index("\n}\n\non_exit()", gather_start)
        gather = source[gather_start:gather_end]
        self.assertIn("write_result || return 1", gather)
        self.assertGreaterEqual(gather.count("|| return 1"), 10)


if __name__ == "__main__":
    unittest.main()
