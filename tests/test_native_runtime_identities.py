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

    def identity(self, event="pull_request", candidate=None):
        environment_path = self.directory / "native-env"
        environment_path.write_text("")
        env = dict(os.environ, EVENT_NAME=event, EVENT_HEAD_SHA=candidate or self.head,
                   EXPECTED_BASE_REF="main", GITHUB_REF_NAME="candidate",
                   GITHUB_ENV=str(environment_path))
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


if __name__ == "__main__":
    unittest.main()
