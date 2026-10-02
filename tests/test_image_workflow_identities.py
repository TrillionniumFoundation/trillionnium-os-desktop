from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNERS = ("run_d1_final_qualification.sh", "run_d2i_integrated_image.sh")


class ImageWorkflowIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.repository = self.directory / "checkout"
        self.remote = self.directory / "remote.git"
        self.repository.mkdir()
        self.git("init", "--bare", str(self.remote), cwd=self.directory)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Identity fixture")
        self.git("remote", "add", "origin", str(self.remote))
        self.commit("baseline")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "main")
        self.git("switch", "-c", "candidate")
        self.commit("candidate")
        self.head = self.git("rev-parse", "HEAD").strip()
        self.git("switch", "main")
        self.git("merge", "--no-ff", "candidate", "-m", "synthetic merge fixture")

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *arguments, cwd=None):
        result = subprocess.run(
            ["git", *arguments], cwd=cwd or self.repository,
            check=True, capture_output=True, text=True,
        )
        return result.stdout

    def commit(self, text):
        (self.repository / "input").write_text(text)
        self.git("add", "input")
        self.git("commit", "-m", text)

    def run_identity(self, runner, event, ref, expected_head=None):
        environment_file = self.directory / "environment"
        environment_file.write_text("")
        environment = dict(os.environ)
        environment.update({
            "GITHUB_EVENT_NAME": event,
            "GITHUB_REF": ref,
            "GITHUB_REF_NAME": ref.removeprefix("refs/heads/"),
            "GITHUB_ENV": str(environment_file),
            "EXPECTED_PR_HEAD": expected_head or self.head,
        })
        result = subprocess.run(
            ["bash", str(ROOT / "tools" / runner), "identities"],
            cwd=self.repository, env=environment, capture_output=True, text=True,
        )
        return result, environment_file.read_text()

    def test_exact_two_parent_merge_binds_candidate_and_remains_non_authoritative(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                result, record = self.run_identity(runner, "pull_request", "refs/pull/1/merge")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"BASE_SHA={self.base}\n", record)
                self.assertIn(f"CANDIDATE_HEAD_SHA={self.head}\n", record)
                self.assertIn("EVIDENCE_ROLE=pr_synthetic_merge\n", record)
                self.assertIn("PROMOTION_AUTHORITATIVE=false\n", record)

    def test_forged_candidate_parent_fails_before_identity_publication(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                result, record = self.run_identity(runner, "pull_request", "refs/pull/1/merge", "0" * 40)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(record, "")

    def test_stale_merge_base_is_rejected_after_main_moves(self):
        self.git("switch", "-c", "new-main", self.base)
        self.commit("new main")
        self.git("push", "origin", "HEAD:main")
        self.git("switch", "main")
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                result, record = self.run_identity(runner, "pull_request", "refs/pull/1/merge")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(record, "")

    def test_branch_push_cannot_mint_main_authority(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                result, record = self.run_identity(runner, "push", "refs/heads/candidate")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(record, "")

    def test_manual_runs_are_explicitly_non_authoritative(self):
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                result, record = self.run_identity(runner, "workflow_dispatch", "refs/heads/candidate")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("EVIDENCE_ROLE=manual_non_authoritative\n", record)
                self.assertIn("PROMOTION_AUTHORITATIVE=false\n", record)


if __name__ == "__main__":
    unittest.main()
