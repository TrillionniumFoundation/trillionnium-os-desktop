from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import qualify_servo_exact_pin_evidence as EVIDENCE  # noqa: E402
import qualify_servo_exact_pin_identity as IDENTITY  # noqa: E402


def sha(character: str) -> str:
    return character * 40


class ServoExactPinIdentityTests(unittest.TestCase):
    def test_current_main_target_keeps_standard_pr_role(self) -> None:
        value = IDENTITY.derive_identity(
            event_name="pull_request",
            source_ref="refs/pull/56/merge",
            source_ref_name="56/merge",
            event_sha=sha("d"),
            tested_sha=sha("d"),
            tested_tree_sha=sha("e"),
            parents=[sha("a"), sha("b")],
            current_main_sha=sha("a"),
            pr_base_sha=sha("a"),
            pr_head_sha=sha("b"),
        )
        self.assertEqual(value["EVIDENCE_ROLE"], "pr_synthetic_merge")
        self.assertEqual(value["PROMOTION_AUTHORITATIVE"], "false")
        self.assertEqual(value["BASE_SHA"], sha("a"))

    def test_stacked_pr_is_accepted_only_after_main_ancestry_probe(self) -> None:
        arguments = dict(
            event_name="pull_request",
            source_ref="refs/pull/57/merge",
            source_ref_name="57/merge",
            event_sha=sha("d"),
            tested_sha=sha("d"),
            tested_tree_sha=sha("e"),
            parents=[sha("c"), sha("b")],
            current_main_sha=sha("a"),
            pr_base_sha=sha("c"),
            pr_head_sha=sha("b"),
        )
        with self.assertRaisesRegex(ValueError, "does not contain"):
            IDENTITY.derive_identity(**arguments)
        value = IDENTITY.derive_identity(
            **arguments,
            pr_base_contains_current_main=True,
        )
        self.assertEqual(value["EVIDENCE_ROLE"], "stacked_pr_synthetic_merge")
        self.assertEqual(value["PROMOTION_AUTHORITATIVE"], "false")
        self.assertEqual(value["INTEGRATED_MAIN_SHA"], "")

    def test_declared_pr_parents_remain_exact(self) -> None:
        with self.assertRaisesRegex(ValueError, "first parent"):
            IDENTITY.derive_identity(
                event_name="pull_request",
                source_ref="refs/pull/57/merge",
                source_ref_name="57/merge",
                event_sha=sha("d"),
                tested_sha=sha("d"),
                tested_tree_sha=sha("e"),
                parents=[sha("f"), sha("b")],
                current_main_sha=sha("a"),
                pr_base_sha=sha("c"),
                pr_head_sha=sha("b"),
                pr_base_contains_current_main=True,
            )

    def test_stacked_evidence_role_is_non_authoritative_and_distinct(self) -> None:
        identity = {
            "EVENT_NAME": "pull_request",
            "SOURCE_REF": "refs/pull/57/merge",
            "SOURCE_REF_NAME": "57/merge",
            "CURRENT_MAIN_SHA": sha("a"),
            "TESTED_SHA": sha("d"),
            "TESTED_TREE_SHA": sha("e"),
            "BASE_SHA": sha("c"),
            "CANDIDATE_HEAD_SHA": sha("b"),
            "TESTED_MERGE_SHA": sha("d"),
            "INTEGRATED_MAIN_SHA": "",
            "EVIDENCE_ROLE": "stacked_pr_synthetic_merge",
            "PROMOTION_AUTHORITATIVE": "false",
        }
        self.assertIs(EVIDENCE.validate_identity_environment(identity), identity)
        forged = dict(identity)
        forged["BASE_SHA"] = forged["CURRENT_MAIN_SHA"]
        with self.assertRaisesRegex(ValueError, "stacked pull-request"):
            EVIDENCE.validate_identity_environment(forged)

    def test_exact_main_is_the_only_authoritative_role(self) -> None:
        value = IDENTITY.derive_identity(
            event_name="push",
            source_ref="refs/heads/main",
            source_ref_name="main",
            event_sha=sha("d"),
            tested_sha=sha("d"),
            tested_tree_sha=sha("e"),
            parents=[sha("c")],
            current_main_sha=sha("d"),
        )
        self.assertEqual(value["EVIDENCE_ROLE"], "exact_main_push")
        self.assertEqual(value["PROMOTION_AUTHORITATIVE"], "true")
        self.assertEqual(value["INTEGRATED_MAIN_SHA"], sha("d"))


if __name__ == "__main__":
    unittest.main()
