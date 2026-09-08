from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "qualify_servo_exact_pin_evidence_identity",
    ROOT / "tools/qualify_servo_exact_pin_evidence.py",
)
assert SPEC is not None and SPEC.loader is not None
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


def identity_for(event: str = "pull_request") -> dict[str, str]:
    values = {
        "EVENT_NAME": event,
        "SOURCE_REF": "refs/pull/7/merge",
        "SOURCE_REF_NAME": "7/merge",
        "TESTED_SHA": "c" * 40,
        "TESTED_TREE_SHA": "d" * 40,
        "BASE_SHA": "a" * 40,
        "CANDIDATE_HEAD_SHA": "b" * 40,
        "TESTED_MERGE_SHA": "c" * 40,
        "INTEGRATED_MAIN_SHA": "",
        "EVIDENCE_ROLE": "pr_synthetic_merge",
        "PROMOTION_AUTHORITATIVE": "false",
    }
    if event == "push":
        values.update(
            {
                "SOURCE_REF": "refs/heads/main",
                "SOURCE_REF_NAME": "main",
                "CANDIDATE_HEAD_SHA": values["TESTED_SHA"],
                "TESTED_MERGE_SHA": "",
                "INTEGRATED_MAIN_SHA": values["TESTED_SHA"],
                "EVIDENCE_ROLE": "exact_main_push",
                "PROMOTION_AUTHORITATIVE": "true",
            }
        )
    elif event == "workflow_dispatch":
        values.update(
            {
                "SOURCE_REF": "refs/heads/feature",
                "SOURCE_REF_NAME": "feature",
                "CANDIDATE_HEAD_SHA": values["TESTED_SHA"],
                "TESTED_MERGE_SHA": "",
                "INTEGRATED_MAIN_SHA": "",
                "EVIDENCE_ROLE": "manual_non_authoritative",
                "PROMOTION_AUTHORITATIVE": "false",
            }
        )
    return values


class ServoEvidenceIdentityTests(unittest.TestCase):
    def test_complete_event_identity_is_accepted(self) -> None:
        for event in ("pull_request", "push", "workflow_dispatch"):
            with self.subTest(event=event):
                validated = EVIDENCE.validate_identity_environment(identity_for(event))
                self.assertEqual(validated["EVENT_NAME"], event)

    def test_missing_sha_or_mismatched_event_fields_is_rejected(self) -> None:
        missing = identity_for()
        missing["TESTED_TREE_SHA"] = ""
        with self.assertRaises(ValueError):
            EVIDENCE.validate_identity_environment(missing)

        mismatched = identity_for("push")
        mismatched["INTEGRATED_MAIN_SHA"] = "e" * 40
        with self.assertRaises(ValueError):
            EVIDENCE.validate_identity_environment(mismatched)

    def test_repository_and_run_identity_are_required_and_canonical(self) -> None:
        valid = {
            "GITHUB_REPOSITORY": EVIDENCE.REPOSITORY,
            "GITHUB_RUN_ID": "12345",
            "GITHUB_RUN_ATTEMPT": "2",
        }
        with patch.dict("os.environ", valid, clear=False):
            repository, attempt, run_id = EVIDENCE.validate_run_environment()
        self.assertEqual(repository, EVIDENCE.REPOSITORY)
        self.assertEqual(attempt, 2)
        self.assertEqual(run_id, "12345")

        for field, value in (
            ("GITHUB_REPOSITORY", ""),
            ("GITHUB_REPOSITORY", "evil/fork"),
            ("GITHUB_RUN_ID", "0"),
            ("GITHUB_RUN_ID", "12x"),
            ("GITHUB_RUN_ATTEMPT", "0"),
            ("GITHUB_RUN_ATTEMPT", "01"),
        ):
            env = valid.copy()
            env[field] = value
            with self.subTest(field=field, value=value), patch.dict(
                "os.environ", env, clear=False
            ):
                with self.assertRaises(ValueError):
                    EVIDENCE.validate_run_environment()


if __name__ == "__main__":
    unittest.main()
