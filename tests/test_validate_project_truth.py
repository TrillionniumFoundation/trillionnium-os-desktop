"""Run the canonical project-truth tests with explicit PR-60 expectations.

The historical test module is imported normally.  The two tests whose policy
subject changed from PR #33 to PR #60 are replaced with ordinary Python methods;
no source text is rewritten or executed dynamically.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

_IMPL_PATH = Path(__file__).with_name("_test_validate_project_truth_impl.py")
_SPEC = importlib.util.spec_from_file_location(
    "_trillionnium_test_validate_project_truth_impl", _IMPL_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load project-truth test implementation: {_IMPL_PATH}")
_suite = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _suite
_SPEC.loader.exec_module(_suite)


def _generated_headed_evidence_is_explicitly_stale(self: object) -> None:
    for relative in (
        "docs/evidence/generated/d0a02-headed-runtime-evidence.json",
        "docs/evidence/generated/d0a02-headed-runtime-result.json",
    ):
        with self.subTest(relative=relative):
            record = json.loads((_suite.ROOT / relative).read_text(encoding="utf-8"))
            self.assertEqual(
                record.get("evidence_lifecycle"),
                _suite.VALIDATOR.D0A02_EVIDENCE_LIFECYCLE,
            )
            self.assertEqual(
                record.get("stale_reason"),
                _suite.VALIDATOR.D0A02_STALE_REASON,
            )
            promotion = record.get("promotion")
            self.assertIsInstance(promotion, dict)
            assert isinstance(promotion, dict)
            self.assertEqual(promotion.get("evidence_freshness"), "STALE_EVIDENCE")
            self.assertFalse(promotion.get("merge_ready"))
            self.assertEqual(promotion.get("superseded_by_pr"), 60)
            self.assertEqual(
                promotion.get("stale_reason"), _suite.VALIDATOR.D0A02_STALE_REASON
            )


def _manifest_entries_preserve_pr60_claim_ceiling_without_readiness(
    self: object,
) -> None:
    docs = json.loads((_suite.ROOT / "docs/MANIFEST.json").read_text(encoding="utf-8"))
    repository = json.loads(
        (_suite.ROOT / "manifests/repository-state.json").read_text(encoding="utf-8")
    )
    project = json.loads(
        (_suite.ROOT / "manifests/project-state.v1.json").read_text(encoding="utf-8")
    )
    checkpoint = next(
        item
        for item in docs["implementation_checkpoints"]
        if item.get("id") == "TOS-D0A-02"
    )
    qualification = next(
        item
        for item in repository["qualification_work_packages"]
        if item.get("id") == "D0A-02"
    )
    for entry in (checkpoint, qualification):
        with self.subTest(entry=entry.get("id")):
            self.assertEqual(
                entry.get("evidence_lifecycle"),
                _suite.VALIDATOR.D0A02_EVIDENCE_LIFECYCLE,
            )
            self.assertFalse(entry.get("merge_ready"))
            self.assertEqual(entry.get("superseded_by_pr"), 60)
            self.assertEqual(
                entry.get("stale_reason"), _suite.VALIDATOR.D0A02_STALE_REASON
            )

    candidate = next(
        item
        for item in project["source_candidate_work_packages"]
        if item.get("id") == "D0A-02"
    )
    self.assertEqual(candidate.get("pr"), 60)
    self.assertEqual(candidate.get("status"), "MODULE_CLOSED_CANDIDATE")
    self.assertTrue(
        candidate.get("claim_ceiling", "").startswith(
            "headed_host_local_fixture_only"
        )
    )


_suite.D0A02EvidenceLifecycleTests.test_generated_headed_evidence_is_explicitly_stale = (
    _generated_headed_evidence_is_explicitly_stale
)
_suite.D0A02EvidenceLifecycleTests.test_manifest_entries_preserve_pr33_claim_ceiling_without_readiness = (
    _manifest_entries_preserve_pr60_claim_ceiling_without_readiness
)

for _name, _value in vars(_suite).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value
