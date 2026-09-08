from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "validate_status_facts.py"
SPEC = importlib.util.spec_from_file_location("validate_status_facts", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StatusFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = {
            "active_plan_revision": "plan-v1",
            "integrated_implementation_stage": "FOUNDATION",
            "integrated_completed_work_packages": ["D0-01"],
        }
        self.facts = {
            "schema": MODULE.SCHEMA,
            "document_updated": "2026-09-08",
            "projection_subject": {
                "role": "integrated_main",
                "source_candidate": {"pull_request": 75, "branch": "candidate/truth"},
            },
            "workspace_members": ["crates/core"],
            "governance_observations": [
                {
                    "id": "main-protection-snapshot",
                    "kind": "github_repository_protection",
                    "source": "github_rest_api",
                    "observed_at": "2026-09-08T03:15:06Z",
                    "observed_main_sha": "0123456789abcdef0123456789abcdef01234567",
                    "validity": "snapshot_only",
                    "main_protected": False,
                    "required_status_enforcement": "off",
                    "tracking_issue": 76,
                }
            ],
            "unmerged_candidates": [
                {
                    "kind": "pull_request",
                    "number": 73,
                    "branch": "candidate/convergence",
                    "state": "frozen_draft",
                    "merge_policy": "must_decompose_never_merge_as_unit",
                }
            ],
            "pending_actions": [
                {
                    "id": "protect-main",
                    "kind": "external_control",
                    "target": {"kind": "issue", "number": 76},
                    "summary": "Enable protected main.",
                }
            ],
        }

    def make_repo(self, projection: str | None = None) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        (root / "manifests").mkdir()
        (root / "docs").mkdir()
        (root / "manifests/project-state.v1.json").write_text(json.dumps(self.project), encoding="utf-8")
        (root / "docs/status-facts.v1.json").write_text(json.dumps(self.facts), encoding="utf-8")
        if projection is None:
            projection = MODULE.render(self.project, self.facts)
        (root / "docs/CURRENT_STATE.md").write_text(projection, encoding="utf-8")
        return root

    def validate_repo(self, root: Path) -> list[str]:
        project = MODULE.load_object(root / "manifests/project-state.v1.json")
        facts = MODULE.load_object(root / "docs/status-facts.v1.json")
        errors = MODULE.validate(project, facts)
        expected = MODULE.render(project, facts)
        if (root / "docs/CURRENT_STATE.md").read_text(encoding="utf-8") != expected:
            errors.append("projection mismatch")
        return errors

    def test_valid_projection_passes(self) -> None:
        self.assertEqual(self.validate_repo(self.make_repo()), [])

    def test_direct_merge_paraphrase_cannot_be_injected(self) -> None:
        projection = MODULE.render(self.project, self.facts)
        projection += "\n1. merge the repository-truth bootstrap on its final head\n"
        self.assertIn("projection mismatch", self.validate_repo(self.make_repo(projection)))

    def test_review_then_merge_paraphrase_cannot_be_injected(self) -> None:
        projection = MODULE.render(self.project, self.facts)
        projection += "\n1. obtain review, then merge the repository-truth bootstrap\n"
        self.assertIn("projection mismatch", self.validate_repo(self.make_repo(projection)))

    def test_unbound_governance_paraphrase_cannot_be_injected(self) -> None:
        projection = MODULE.render(self.project, self.facts)
        projection += "\nGitHub now reports main as protected.\n"
        self.assertIn("projection mismatch", self.validate_repo(self.make_repo(projection)))

    def test_no_governance_observation_is_valid(self) -> None:
        self.facts["governance_observations"] = []
        self.assertEqual(self.validate_repo(self.make_repo()), [])

    def test_non_self_follow_up_is_valid(self) -> None:
        self.facts["pending_actions"].append(
            {
                "id": "runtime-slice",
                "kind": "runtime_integration",
                "target": {"kind": "issue", "number": 86},
                "summary": "Complete the bounded runtime vertical slice.",
            }
        )
        self.assertEqual(self.validate_repo(self.make_repo()), [])

    def test_self_targeted_pull_request_is_rejected(self) -> None:
        self.facts["pending_actions"] = [
            {
                "id": "self-integration",
                "kind": "successor_train",
                "target": {"kind": "pull_request", "number": 75, "branch": "candidate/truth"},
                "summary": "Integrate this candidate.",
            }
        ]
        errors = MODULE.validate(self.project, self.facts)
        self.assertTrue(any("own pending integration" in error for error in errors))

    def test_unknown_top_level_field_is_rejected(self) -> None:
        self.facts["free_form_override"] = "not allowed"
        errors = MODULE.validate(self.project, self.facts)
        self.assertTrue(any("keys must be exactly" in error for error in errors))

    def test_duplicate_json_key_is_rejected(self) -> None:
        root = self.make_repo()
        path = root / "docs/status-facts.v1.json"
        path.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            MODULE.load_object(path)

    def test_unbound_observation_is_rejected(self) -> None:
        self.facts["governance_observations"][0].pop("observed_main_sha")
        errors = MODULE.validate(self.project, self.facts)
        self.assertTrue(any("keys must be exactly" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
