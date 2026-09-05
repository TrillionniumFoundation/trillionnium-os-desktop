"""Run the canonical project-truth tests with explicit PR-66 expectations.

The historical test module is imported normally.  The two tests whose policy
subject changed from PR #33 to PR #66 are replaced with ordinary Python methods;
no source text is rewritten or executed dynamically.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

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
            self.assertEqual(promotion.get("superseded_by_pr"), 66)
            self.assertEqual(
                promotion.get("stale_reason"), _suite.VALIDATOR.D0A02_STALE_REASON
            )


def _manifest_entries_preserve_pr66_claim_ceiling_without_readiness(
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
            self.assertEqual(entry.get("superseded_by_pr"), 66)
            self.assertEqual(
                entry.get("stale_reason"), _suite.VALIDATOR.D0A02_STALE_REASON
            )

    candidate = next(
        item
        for item in project["source_candidate_work_packages"]
        if item.get("id") == "D0A-02"
    )
    self.assertEqual(candidate.get("pr"), 66)
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
    _manifest_entries_preserve_pr66_claim_ceiling_without_readiness
)

for _name, _value in vars(_suite).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value


class CandidateSnapshotAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = json.loads(
            (ROOT / "manifests/project-state.v1.json").read_text(encoding="utf-8")
        )
        self.docs = json.loads(
            (ROOT / "docs/MANIFEST.json").read_text(encoding="utf-8")
        )
        self.repository = json.loads(
            (ROOT / "manifests/repository-state.json").read_text(encoding="utf-8")
        )

    def errors(
        self,
        project: object | None = None,
        docs: object | None = None,
        repository: object | None = None,
    ) -> list[str]:
        return VALIDATOR.candidate_snapshot_alignment_errors(
            self.project if project is None else project,
            self.docs if docs is None else docs,
            self.repository if repository is None else repository,
        )

    def test_current_snapshots_and_active_candidates_align(self) -> None:
        self.assertEqual(self.errors(), [])

    def test_rejects_cross_projection_snapshot_drift(self) -> None:
        docs = copy.deepcopy(self.docs)
        docs["candidate_state_snapshot"]["observed_candidate_pr"] += 1
        errors = self.errors(docs=docs)
        self.assertTrue(
            any("docs manifest candidate_state_snapshot disagrees" in error for error in errors),
            errors,
        )

    def test_rejects_active_candidate_binding_drift(self) -> None:
        project = copy.deepcopy(self.project)
        candidate = project["source_candidate_work_packages"][0]
        candidate["base_sha"] = "a" * 40
        candidate["candidate_head_sha"] = "b" * 40
        candidate["pr"] += 1
        candidate["branch"] = "codex/stale-candidate"
        errors = self.errors(project=project)
        for field in ("base_sha", "candidate_head_sha", "pr", "branch"):
            with self.subTest(field=field):
                self.assertTrue(
                    any(field in error and "candidate_state_snapshot" in error for error in errors),
                    errors,
                )

    def test_rejects_malformed_or_weakened_snapshot(self) -> None:
        project = copy.deepcopy(self.project)
        snapshot = project["candidate_state_snapshot"]
        snapshot["observed_at"] = "not-a-timestamp"
        snapshot["observed_candidate_tree_sha"] = "0" * 40
        snapshot["source"] = "manual"
        snapshot["live_pr_or_ci_state_must_be_read_from_github"] = False
        repository = copy.deepcopy(self.repository)
        repository["candidate_state_snapshot"] = copy.deepcopy(snapshot)
        docs = copy.deepcopy(self.docs)
        docs["candidate_state_snapshot"] = copy.deepcopy(snapshot)
        errors = self.errors(project=project, docs=docs, repository=repository)
        self.assertTrue(any("observed_at" in error for error in errors), errors)
        self.assertTrue(any("observed_candidate_tree_sha" in error for error in errors), errors)
        self.assertTrue(any("snapshot.source" in error for error in errors), errors)
        self.assertTrue(any("live PR/CI" in error for error in errors), errors)
