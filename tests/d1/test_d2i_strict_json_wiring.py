from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class D2IStrictJsonWiringTests(unittest.TestCase):
    def test_workflow_uses_duplicate_rejecting_loader_for_guest_records(self) -> None:
        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("load_json_strict", workflow)
        self.assertIn("def read_json(path):", workflow)
        for name in (
            "d1",
            "repro",
            "prep_a",
            "prep_b",
            "boot",
            "acceptance",
            "runtime",
            "crash_proof",
        ):
            self.assertIn(f"{name} = read_json(", workflow)
        self.assertNotIn("d1 = json.loads(", workflow)
        self.assertNotIn("crash_proof = json.loads(", workflow)

    def test_qemu_runner_uses_duplicate_rejecting_loader_for_guest_records(self) -> None:
        runner = (ROOT / "tests/qemu/run-d2i-boot-test.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("from gate_evidence_envelope import load_json_strict", runner)
        self.assertIn("def read_json(path):", runner)
        self.assertIn("acceptance = read_json(", runner)
        self.assertIn("runtime = read_json(", runner)
        self.assertIn("proof = read_json(", runner)
        self.assertNotIn("acceptance = json.loads(", runner)
        self.assertNotIn("runtime = json.loads(", runner)
        self.assertNotIn("proof = json.loads(", runner)


if __name__ == "__main__":
    unittest.main()
