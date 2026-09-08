from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/lab-d3-servo-retained-node-action.v1.json"
WORKFLOW = ROOT / ".github/workflows/s07-servo-retained-node.yml"
DOCUMENT = ROOT / "docs/implementation/D3_SERVO_RETAINED_NODE_ACTION.md"
EXPECTED_BASE = "ea05a5eaf520365aa0086d7795d66a1d5c5537dd"
EXPECTED_SOURCE = "62004b70385dc70557190bd7c0a72b40239cb078"
EXPECTED_SERVO = "670ae8a70801b162e186f81cbb5bdd2d59c39108"


class S07ServoPatchPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.workflow = WORKFLOW.read_text(encoding="utf-8")
        self.document = DOCUMENT.read_text(encoding="utf-8")

    def test_exact_successor_and_provenance_identity(self) -> None:
        self.assertEqual(
            self.manifest["carrier_branch"],
            "codex/s07-servo-retained-node-v1",
        )
        self.assertEqual(self.manifest["carrier_base_commit"], EXPECTED_BASE)
        self.assertEqual(
            self.manifest["extracted_from"],
            {"pull_request": 73, "commit": EXPECTED_SOURCE},
        )
        self.assertEqual(self.manifest["upstream"]["commit"], EXPECTED_SERVO)

    def test_ordered_parts_and_digests_are_exact(self) -> None:
        base = self.manifest["patch"]
        hardening = self.manifest["hardening"]
        entries = base["parts"] + hardening["parts"]
        self.assertEqual(
            [Path(entry["path"]).name for entry in entries],
            [f"{index:03d}.patch" for index in range(8)],
        )
        chunks: list[bytes] = []
        for entry in entries:
            path = ROOT / entry["path"]
            self.assertTrue(path.is_file() and not path.is_symlink())
            data = path.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
            chunks.append(data)
        self.assertEqual(
            hashlib.sha256(b"".join(chunks[:7])).hexdigest(),
            base["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(chunks[7]).hexdigest(),
            hardening["sha256"],
        )

    def test_workflow_separates_head_and_merge_evidence(self) -> None:
        for token in (
            "Check out exact source head",
            "github.event.pull_request.head.sha || github.sha",
            'test "$(git rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA"',
            "exact-head-real-servo-behavior",
            "Check out prospective merge object",
            "refs/pull/${{ github.event.pull_request.number }}/merge",
            'test "$(git rev-parse HEAD^1)" = "$EXPECTED_BASE_SHA"',
            'test "$(git rev-parse HEAD^2)" = "$EXPECTED_HEAD_SHA"',
            "prospective-merge-patch-package",
        ):
            self.assertIn(token, self.workflow)
        self.assertNotIn("Check out exact carrier\n", self.workflow)

    def test_behavior_evidence_is_conditional_and_bounded(self) -> None:
        for token in (
            "evidence_complete:(",
            'retained_node_valid_click_tested:($behavior == "success")',
            "forbidden_fallback_used:false",
            "installed_runtime_proven:false",
            "physical_hardware_proven:false",
            "hsm_signing_proven:false",
            "d3_promoted:false",
        ):
            self.assertIn(token, self.workflow)

    def test_document_preserves_non_claims(self) -> None:
        # Markdown wrapping is not semantic. Normalize all runs of whitespace so
        # line-width-only edits cannot turn a claim-ceiling assertion into a
        # deterministic CI failure.
        normalized_document = " ".join(self.document.split())
        for token in (
            "source/test-harness candidate",
            "forbidden",
            "prospective-merge",
            "Neither is installed-product",
            "S08",
            "S10",
        ):
            self.assertIn(token, normalized_document)


if __name__ == "__main__":
    unittest.main()
