from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

import test_image_workflow_identities as fixture

ROOT = Path(__file__).resolve().parents[1]


class NativeRuntimeIdentityTests(unittest.TestCase):
    setUp = fixture.ImageWorkflowIdentityTests.setUp
    tearDown = fixture.ImageWorkflowIdentityTests.tearDown
    git = fixture.ImageWorkflowIdentityTests.git
    commit = fixture.ImageWorkflowIdentityTests.commit

    def identity(self, event="pull_request", candidate=None, **overrides):
        environment_path = self.directory / "native-env"
        environment_path.write_text("")
        env = dict(os.environ, EVENT_NAME=event, EVENT_HEAD_SHA=candidate or self.head,
                   EXPECTED_BASE_REF="main", GITHUB_REF_NAME="candidate",
                   GITHUB_EVENT_NAME=event, GITHUB_SHA=self.git("rev-parse", "HEAD").strip(),
                   GITHUB_REF="refs/pull/1/merge" if event == "pull_request" else "refs/heads/candidate",
                   GITHUB_REPOSITORY="TrillionniumFoundation/trillionnium-os-desktop",
                   GITHUB_ENV=str(environment_path))
        env.update(overrides)
        result = subprocess.run(["bash", str(ROOT / "tools/run_servo_headed_runtime_gate.sh"), "identities"],
                                cwd=self.repository, env=env, capture_output=True, text=True, timeout=10)
        return result, environment_path.read_text()

    def test_real_merge_uses_its_actual_parents(self):
        result, record = self.identity()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"BASE_SHA={self.base}\n", record)
        self.assertIn(f"CANDIDATE_HEAD_SHA={self.head}\n", record)
        self.assertIn("EVIDENCE_MODE=pr_synthetic_merge\n", record)

    def test_forged_head_is_refused_without_publishing_identity(self):
        result, record = self.identity(candidate="0" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(record, "")

    def test_moved_base_invalidates_old_merge(self):
        self.git("switch", "-c", "moved-main", self.base)
        self.commit("moved main")
        self.git("push", "origin", "HEAD:main")
        self.git("switch", "main")
        result, record = self.identity()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(record, "")

    def test_manual_run_stays_diagnostic(self):
        result, record = self.identity("workflow_dispatch")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE_MODE=manual_exact_object\n", record)

    def test_push_cannot_mint_main_authority_from_wrong_checkout(self):
        for builtin_sha in (self.base, self.git("rev-parse", "HEAD").strip()):
            result, record = self.identity("push", GITHUB_REF_NAME="main", GITHUB_REF="refs/heads/main", GITHUB_SHA=builtin_sha)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(record, "")

    def test_builtin_event_repository_and_ref_must_match(self):
        for override in ({"GITHUB_EVENT_NAME":"pull_request"}, {"GITHUB_REPOSITORY":"other/project"},
                         {"GITHUB_REF":"refs/heads/main"}):
            result, record = self.identity("push", **override)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(record, "")

    def test_exact_current_main_push_is_bound_to_remote_object(self):
        self.git("switch", "-c", "actual-main", self.base)
        self.commit("new actual main")
        exact = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "HEAD:main")
        result, record = self.identity("push", GITHUB_REF_NAME="main", GITHUB_REF="refs/heads/main")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE_MODE=exact_main_push\n", record)
        self.assertIn(f"TESTED_SHA={exact}\n", record)


if __name__ == "__main__":
    unittest.main()
