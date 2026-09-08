from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "validate_project_truth.py"
SPEC = importlib.util.spec_from_file_location("validate_project_truth", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StatusProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = {
            "active_plan_revision": "plan-v1",
            "integrated_implementation_stage": "FOUNDATION",
            "integrated_completed_work_packages": ["D0-01"],
            "source_candidate_work_packages": [
                {
                    "id": "D1-01",
                    "branch": "candidate/runtime",
                    "pr": 42,
                    "status": "SOURCE_CANDIDATE",
                }
            ],
            "not_claimed": ["production_release"],
            "candidate_state_policy": {
                "committed_snapshot_not_live_api": True,
                "live_pr_or_ci_state_must_be_read_from_github": True,
                "promotion_requires_exact_head_and_exact_main_evidence": True,
            },
        }
        self.registry = {
            "schema": MODULE.STATUS_REGISTRY_SCHEMA,
            "project_state": "manifests/project-state.v1.json",
            "documents": {
                "repository_entry": {
                    "path": "README.md",
                    "scope": "repository_entry",
                },
                "integrated": {
                    "path": "docs/CURRENT_STATE.md",
                    "scope": "integrated_main",
                },
                "candidate": {
                    "path": "docs/CANDIDATE_STATUS.md",
                    "scope": "candidate_snapshot_and_live_api",
                },
                "non_claims": {
                    "path": "docs/NON_CLAIMS.md",
                    "scope": "not_claimed",
                },
                "decomposition": {
                    "path": "docs/plan/PR73_DECOMPOSITION.md",
                    "scope": "planning_only",
                },
            },
        }
        self.documents = {
            "README.md": (
                "plan-v1 FOUNDATION manifests/project-state.v1.json "
                "docs/CURRENT_STATE.md docs/CANDIDATE_STATUS.md docs/NON_CLAIMS.md"
            ),
            "docs/CURRENT_STATE.md": (
                "plan-v1 FOUNDATION CANDIDATE_STATUS.md NON_CLAIMS.md `D0-01`"
            ),
            "docs/CANDIDATE_STATUS.md": (
                "CURRENT_STATE.md NON_CLAIMS.md live GitHub state exact final head "
                "`D1-01` `candidate/runtime` PR #42 `SOURCE_CANDIDATE`"
            ),
            "docs/NON_CLAIMS.md": "`production_release`",
            "docs/plan/PR73_DECOMPOSITION.md": (
                "PR #73 remains frozen and is never merged as one unit"
            ),
        }

    def errors(self) -> list[str]:
        return MODULE.status_projection_errors(
            self.project,
            self.registry,
            self.documents,
        )

    def test_valid_projection_does_not_require_retired_pr_numbers(self) -> None:
        self.assertEqual(self.errors(), [])

    def test_missing_candidate_status_is_rejected(self) -> None:
        self.documents["docs/CANDIDATE_STATUS.md"] = (
            "CURRENT_STATE.md NON_CLAIMS.md live GitHub state exact final head "
            "`D1-01` `candidate/runtime` PR #42"
        )
        self.assertTrue(any("SOURCE_CANDIDATE" in error for error in self.errors()))

    def test_missing_machine_non_claim_is_rejected(self) -> None:
        self.documents["docs/NON_CLAIMS.md"] = "human prose only"
        self.assertTrue(any("production_release" in error for error in self.errors()))

    def test_unproven_closure_marker_is_rejected(self) -> None:
        self.documents["docs/CANDIDATE_STATUS.md"] += " merge_permitted=true"
        self.assertTrue(
            any("forbidden unproven closure marker" in error for error in self.errors())
        )


if __name__ == "__main__":
    unittest.main()
