from __future__ import annotations

import copy
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
            "contract": MODULE.STATUS_REGISTRY_CONTRACT,
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
            "integrated_state": {
                "schema": MODULE.INTEGRATED_STATE_SCHEMA,
                "updated": "2026-09-08",
                "repository_mode": "FULL_PRODUCT_REPOSITORY",
                "workspace_members": ["crates/example"],
                "capabilities": ["bounded_contract_primitives"],
                "governance_observation": None,
                "frozen_candidate": {
                    "kind": "pull_request",
                    "pull_request": 73,
                    "state": "draft_frozen",
                    "decomposition_issue": 78,
                    "merge_policy": "never_merge_as_one_unit",
                },
                "next_work": [
                    {
                        "type": "enable_repository_protection",
                        "issue": 76,
                        "target_branch": "main",
                    }
                ],
            },
        }
        self.integrated_path = "docs/CURRENT_STATE.md"
        self.documents = {
            "README.md": (
                "plan-v1 FOUNDATION manifests/project-state.v1.json "
                "docs/CURRENT_STATE.md docs/CANDIDATE_STATUS.md docs/NON_CLAIMS.md"
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
        self.rerender_integrated()

    def role_paths(self) -> dict[str, str]:
        return {
            role: entry["path"]
            for role, entry in self.registry["documents"].items()
        }

    def rerender_integrated(self) -> None:
        self.documents[self.integrated_path] = MODULE.render_integrated_state(
            self.project,
            self.registry["integrated_state"],
            self.role_paths(),
        )

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

    def test_all_free_form_self_merge_phrasings_are_rejected_by_exact_projection(self) -> None:
        additions = (
            "\n1. merge the repository-truth bootstrap on its final head",
            "\n1. obtain review, then merge the repository-truth bootstrap",
            "\nThe current pull request should now be integrated.",
        )
        original = self.documents[self.integrated_path]
        for addition in additions:
            with self.subTest(addition=addition):
                self.documents[self.integrated_path] = original + addition
                self.assertTrue(
                    any("not the exact projection" in error for error in self.errors())
                )
        self.documents[self.integrated_path] = original

    def test_governance_snapshot_requires_closed_identity_fields(self) -> None:
        observation = {
            "kind": "github_repository_settings_snapshot",
            "source": "github_rest_api",
            "repository": "TrillionniumFoundation/trillionnium-os-desktop",
            "branch": "main",
            "observed_at": "2026-09-08T03:15:06Z",
            "observed_main_sha": "0123456789abcdef0123456789abcdef01234567",
            "branch_protected": False,
            "required_status_checks": "disabled",
            "validity": "snapshot_only",
            "invalidation": ["main_ref_change", "repository_settings_change"],
            "tracking_issue": 76,
        }
        self.registry["integrated_state"]["governance_observation"] = observation
        self.rerender_integrated()
        self.assertEqual(self.errors(), [])

        for missing in ("observed_at", "observed_main_sha", "validity"):
            with self.subTest(missing=missing):
                broken = copy.deepcopy(observation)
                del broken[missing]
                self.registry["integrated_state"]["governance_observation"] = broken
                self.assertTrue(
                    any("closed-schema compliant" in error for error in self.errors())
                )
        self.registry["integrated_state"]["governance_observation"] = observation

    def test_governance_prose_rewording_cannot_bypass_identity(self) -> None:
        self.registry["integrated_state"]["governance_observation"] = {
            "kind": "github_repository_settings_snapshot",
            "source": "github_rest_api",
            "repository": "TrillionniumFoundation/trillionnium-os-desktop",
            "branch": "main",
            "observed_at": "2026-09-08T03:15:06Z",
            "observed_main_sha": "0123456789abcdef0123456789abcdef01234567",
            "branch_protected": False,
            "required_status_checks": "disabled",
            "validity": "snapshot_only",
            "invalidation": ["main_ref_change", "repository_settings_change"],
            "tracking_issue": 76,
        }
        self.rerender_integrated()
        self.documents[self.integrated_path] = self.documents[
            self.integrated_path
        ].replace("GitHub REST reported", "repository settings were observed as")
        self.assertTrue(any("not the exact projection" in error for error in self.errors()))

    def test_valid_non_self_next_work_without_governance_observation(self) -> None:
        self.registry["integrated_state"]["governance_observation"] = None
        self.registry["integrated_state"]["next_work"] = [
            {
                "type": "decompose_frozen_pull_request",
                "issue": 78,
                "target_pull_request": 73,
            },
            {
                "type": "qualify_successor_pull_requests",
                "issue": 78,
                "target_set": "bounded_successor_pull_requests",
            },
        ]
        self.rerender_integrated()
        self.assertEqual(self.errors(), [])
        self.assertNotIn("Repository governance observation", self.documents[self.integrated_path])

    def test_unknown_pending_action_type_is_rejected(self) -> None:
        self.registry["integrated_state"]["next_work"] = [
            {"type": "merge_pull_request", "issue": 75, "target_pull_request": 75}
        ]
        self.assertTrue(any("unsupported action type" in error for error in self.errors()))

    def test_unknown_registry_fields_are_rejected(self) -> None:
        self.registry["unexpected"] = True
        self.assertTrue(any("unknown=['unexpected']" in error for error in self.errors()))


if __name__ == "__main__":
    unittest.main()
