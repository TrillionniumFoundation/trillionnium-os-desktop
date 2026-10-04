"""Execute five CI identity bodies against actual private Git repositories.

The private mount hides the reference body's fixed /tmp output, then runs its
unaltered Bash body as the fixture creator. It grants no product authority.
Missing Git or namespace fixture privileges fail these tests; none are skipped.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BODIES = (
    ("update-boot-observer", "actual-host-corpus", True),
    ("controlled-egress", "actual-host-corpus", True),
    ("agent-transport-reference", "reference-prospective-merge", False),
    ("s04-transport-custody", "source-policy-prospective-merge", False),
    ("s04-transport-custody", "rust-prospective-merge", False),
)
IDENTITY_NAMES = {
    "Bind exact source and current prospective parents",
    "Verify merge identity against live branch refs",
}


def identity_body(workflow, job):
    """Select a complete literal run body, including its original output code."""
    lines = workflow.splitlines()
    start = lines.index("  " + job + ":")
    end = next((i for i in range(start + 1, len(lines))
                if re.fullmatch(r"  [A-Za-z0-9_-]+:", lines[i])), len(lines))
    names = [i for i in range(start, end)
             if lines[i].startswith("      - name: ")
             and lines[i][14:] in IDENTITY_NAMES]
    if len(names) != 1:
        raise ValueError("exactly one identity step required in " + job)
    begin = next(i for i in range(names[0] + 1, end)
                 if lines[i] == "        run: |") + 1
    finish = begin
    while finish < end and (not lines[finish].strip()
                           or lines[finish].startswith("          ")):
        finish += 1
    return "\n".join(line[10:] if line.startswith("          ") else line
                     for line in lines[begin:finish]) + "\n"


class CIPrRefIdentityTests(unittest.TestCase):
    def setUp(self):
        # Keep the checkout visible after mounting the subprocess-only /tmp.
        self.temp = tempfile.TemporaryDirectory(prefix=".ci-pr-ref-", dir=ROOT.parent)
        self.directory = Path(self.temp.name)
        self.repository = self.directory / "checkout"
        self.remote = self.directory / "origin.git"
        self.repository.mkdir()
        self.git("init", "--bare", str(self.remote), cwd=self.directory)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Private CI identity fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("remote", "add", "origin", str(self.remote))
        # Binding placeholders, never observed or approved product identities.
        for relative in ("platform/update_boot_observer.py",
                         "tools/inspect_pending_update.py",
                         "contracts/update-boot-observer.v1.json",
                         "manifests/update-observation.v1.json",
                         "platform/controlled_egress.py",
                         "tests/test_controlled_egress.py",
                         "contracts/controlled-egress.v1.json"):
            path = self.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("private Git source-binding fixture\n")
        self.commit("base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "main")
        self.git("switch", "-c", "fork-topic")
        self.commit("fork head")
        self.head = self.git("rev-parse", "HEAD").strip()
        self.git("push", "origin", "HEAD:refs/pull/7/head")
        self.git("switch", "main")
        self.git("merge", "--no-ff", "fork-topic", "-m", "prospective")
        self.merge = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *arguments, cwd=None):
        return subprocess.run(
            ["git", *arguments], cwd=cwd or self.repository, check=True,
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null",
                 "GIT_CONFIG_NOSYSTEM": "1"},
        ).stdout

    def commit(self, message):
        (self.repository / "input").write_text(message + "\n")
        self.git("add", ".")
        self.git("commit", "-m", message)

    def execute(self, entry, source="prospective-merge", checkout=None,
                body=None, **changes):
        workflow, job, _matrix = entry
        tested = checkout or (self.merge if source == "prospective-merge"
                              else self.head)
        self.git("checkout", "--detach", tested)
        if body is None:
            body = identity_body((ROOT / ".github/workflows" /
                                  (workflow + ".yml")).read_text(), job)
        facts = {
            "EVENT_NAME": "pull_request", "PR_NUMBER": "7",
            "SOURCE_OBJECT": source, "EVENT_HEAD": self.head,
            "EVENT_TESTED": tested, "HEAD_REF": "fork-topic",
            "BASE_REF": "main", "EVENT_BASE": self.base,
            "GITHUB_STEP_SUMMARY": str(self.directory / "summary"),
            "LC_ALL": "C", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        facts.update(changes)
        # This sole GitHub expression is rendered from the actual fixture object.
        body = body.replace("${{ github.sha }}", facts["EVENT_TESTED"])
        if "${{" in body:
            raise ValueError("unresolved source expression")
        uid, gid = os.getuid(), os.getgid()
        wrapper = (
            "set -euo pipefail\n"
            f"mount -t tmpfs -o mode=0700,uid={uid},gid={gid},size=16m tmpfs /tmp\n"
            f'exec /usr/bin/setpriv --reuid={uid} --regid={gid} --clear-groups '
            'bash --noprofile --norc -c "$1"'
        )
        return subprocess.run(
            ["/usr/bin/sudo", "--non-interactive", "--", "/usr/bin/env",
             *[key + "=" + value for key, value in facts.items()],
             "/usr/bin/unshare", "--mount", "--propagation", "private",
             "bash", "--noprofile", "--norc", "-c", wrapper,
             "private-source-identity", body],
            cwd=self.repository, capture_output=True, text=True, timeout=10,
        )

    def assert_table(self, expected, **changes):
        for entry in BODIES:
            with self.subTest(workflow=entry[0], job=entry[1], changes=changes):
                result = self.execute(entry, **changes)
                if expected == 0:
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertEqual(result.returncode, 1, result.stderr)

    def test_fork_only_pull_ref_accepts_exact_head_and_ordered_merge(self):
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/fork-topic"), "")
        self.assert_table(0)
        for entry in BODIES[:2]:
            result = self.execute(entry, source="head")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines()[:2], [
                self.head, self.git("rev-parse", self.head + "^{tree}").strip()])

    def test_positive_canonical_one_and_large_number(self):
        for number in ("1", "123456789"):
            self.git("push", "origin", self.head + ":refs/pull/" + number + "/head")
            self.assert_table(0, PR_NUMBER=number)

    def test_same_named_branch_never_masks_wrong_or_missing_pr(self):
        self.git("push", "origin", self.head + ":refs/heads/fork-topic")
        self.git("push", "--force", "origin", self.base + ":refs/pull/7/head")
        self.assert_table(1)
        self.git("push", "origin", ":refs/pull/7/head")
        self.assert_table(1)

    def test_advertised_noncanonical_numbers_refuse_before_git_matching(self):
        for number in ("0", "07", "-7", "+7", "7.0"):
            self.git("push", "origin", self.head + ":refs/pull/" + number + "/head")
        for number in ("", "0", "07", "-7", "+7", "7.0", "7/head", "*", "7\n8"):
            self.assert_table(1, PR_NUMBER=number)

    def test_slash_suffix_head_and_base_advertisements_do_not_substitute_refs(self):
        self.git("push", "origin", self.head + ":refs/heads/refs/pull/8/head")
        self.assertIn("refs/heads/refs/pull/8/head",
                      self.git("ls-remote", "origin", "refs/pull/8/head"))
        self.assert_table(1, PR_NUMBER="8")
        self.git("push", "origin", self.base + ":refs/heads/refs/heads/unadvertised")
        self.assertIn("refs/heads/refs/heads/unadvertised",
                      self.git("ls-remote", "origin", "refs/heads/unadvertised"))
        self.assert_table(1, BASE_REF="unadvertised")

    def test_stale_head_checkout_tested_object_and_live_base_refuse(self):
        self.assert_table(1, EVENT_HEAD=self.base)
        self.assert_table(1, checkout=self.base)
        self.assert_table(1, EVENT_TESTED=self.head)
        for entry in BODIES[:2]:
            self.assertEqual(self.execute(entry, source="head", checkout=self.base)
                             .returncode, 1)
            self.assertEqual(self.execute(entry, EVENT_BASE=self.head).returncode, 1)
        self.git("switch", "-c", "base-moved", self.base)
        self.commit("live base advanced")
        self.git("push", "origin", "HEAD:refs/heads/main")
        self.assert_table(1)

    def test_reversed_and_three_actual_git_parents_refuse_all_five_bodies(self):
        tree = self.git("rev-parse", self.merge + "^{tree}").strip()
        reversed_merge = self.git("commit-tree", tree, "-p", self.head,
                                  "-p", self.base, "-m", "reversed").strip()
        self.assert_table(1, checkout=reversed_merge)
        third = self.git("commit-tree", tree, "-m", "independent parent").strip()
        three = self.git("commit-tree", tree, "-p", self.base, "-p", self.head,
                         "-p", third, "-m", "three-parent").strip()
        self.assertEqual(len(self.git("show", "-s", "--format=%P", three).split()), 3)
        self.assert_table(1, checkout=three)

    def test_matrix_push_requires_exact_current_branch_and_supported_event(self):
        for entry in BODIES[:2]:
            self.assertEqual(self.execute(entry, source="head", EVENT_NAME="push",
                                          PR_NUMBER="").returncode, 1)
        self.git("push", "origin", self.head + ":refs/heads/fork-topic")
        for entry in BODIES[:2]:
            self.assertEqual(self.execute(entry, source="head", EVENT_NAME="push",
                                          PR_NUMBER="").returncode, 0)
            for changes in ({"HEAD_REF": "fork-*"}, {"EVENT_HEAD": self.base},
                            {"EVENT_NAME": "workflow_dispatch"}):
                facts = {"EVENT_NAME": "push", "PR_NUMBER": "", **changes}
                result = self.execute(entry, source="head", **facts)
                self.assertEqual(result.returncode, 1, result.stderr)

    def test_exact_reference_field_regression_rejects_real_matching_suffix(self):
        self.git("push", "origin", self.head + ":refs/heads/refs/pull/8/head")
        for entry in BODIES:
            body = identity_body((ROOT / ".github/workflows" /
                                  (entry[0] + ".yml")).read_text(), entry[1])
            mutant = body.replace("$2 == ref {", "{", 1)
            self.assertNotEqual(mutant, body)
            self.assertEqual(self.execute(entry, body=mutant, PR_NUMBER="8")
                             .returncode, 0)
            self.assertEqual(self.execute(entry, PR_NUMBER="8").returncode, 1)

    def test_workflow_invocations_trigger_paths_and_module_mapping(self):
        for workflow in {entry[0] for entry in BODIES}:
            source = (ROOT / ".github/workflows" / (workflow + ".yml")).read_text()
            self.assertEqual(source.count('      - "tests/test_ci_pr_ref_identities.py"'), 2)
            self.assertIn("python3 -B -m unittest discover -s tests -p test_ci_pr_ref_identities.py -v", source)
            self.assertNotIn("continue-on-error", source)
        modules = json.loads((ROOT / "manifests/modules.v1.json").read_text())["modules"]
        transport = next(module for module in modules if module["id"] == "hepta-agent-transport")
        self.assertIn("tests/test_ci_pr_ref_identities.py", transport["tests"])


if __name__ == "__main__":
    unittest.main()
