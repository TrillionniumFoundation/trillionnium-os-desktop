#!/usr/bin/env python3
"""Run the real workflow program against real isolated shallow Git sources.

The only wrapper rewrites the public upstream URL to the test's local Git
repository. No kernel build or guest execution is claimed by these tests.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STEP = "      - name: Fetch immutable upstream objects required by the original source verifier\n"


class WorkflowSourceObjectTests(unittest.TestCase):
    def git(self, directory, *arguments, **kwargs):
        return subprocess.check_output([self.real_git, "-C", str(directory), *arguments],
                                       env=self.environment, **kwargs)

    def commit(self, directory):
        self.git(directory, "add", "--all")
        self.git(directory, "-c", "user.name=Source object regression", "-c", "user.email=ci@invalid.example",
                 "commit", "--quiet", "-m", "Isolated source fixture")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.real_git = shutil.which("git")
        self.environment = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                                GIT_TERMINAL_PROMPT="0")
        self.upstream = self.root / "upstream"
        self.upstream.mkdir()
        self.git(self.upstream, "init", "--quiet")
        (self.upstream / "Cargo.lock").write_bytes(b"immutable upstream lock seed\n")
        (self.upstream / "kernel.rs").write_bytes(b"original upstream source\n")
        self.commit(self.upstream)
        self.kernel = {
            "repository": "asterinas/asterinas",
            "commit": self.git(self.upstream, "rev-parse", "HEAD", text=True).strip(),
            "tree": self.git(self.upstream, "rev-parse", "HEAD^{tree}", text=True).strip(),
        }
        origin = self.root / "desktop-origin"
        (origin / "support").mkdir(parents=True)
        self.git(origin, "init", "--quiet")
        (origin / "support/upstream-lock.json").write_text(json.dumps({"kernel": self.kernel}))
        (origin / "README.md").write_text("Independent downstream source\n")
        self.commit(origin)
        self.ci = self.root / "ci"
        (self.ci / "identity").mkdir(parents=True)
        self.desktop = self.ci / "desktop-source"
        subprocess.run([self.real_git, "clone", "--quiet", "--depth=1", "--no-local",
                        origin.as_uri(), str(self.desktop)], env=self.environment, check=True)
        self.commands = self.root / "git-commands.jsonl"
        binary = self.root / "bin"
        binary.mkdir()
        wrapper = binary / "git"
        wrapper.write_text(
            "#!/usr/bin/python3\nimport json, os, sys\n"
            f"real = {self.real_git!r}\ncommands = {str(self.commands)!r}\n"
            "arguments = sys.argv[1:]\n"
            "with open(commands, 'a') as output: output.write(json.dumps(arguments) + '\\n')\n"
            "url = 'https://github.com/asterinas/asterinas.git'\n"
            f"if url in arguments: arguments[arguments.index(url)] = {self.upstream.as_uri()!r}\n"
            "os.execv(real, [real, *arguments])\n"
        )
        wrapper.chmod(0o755)
        self.environment.update(PATH=str(binary) + ":/usr/bin:/bin", F1_CI_ROOT=str(self.ci))
        self.update_pin()
        self.receipt = self.ci / "identity/upstream-source.json"

    def update_pin(self):
        self.environment["DESKTOP_SOURCE_PIN"] = self.git(self.desktop, "rev-parse", "HEAD", text=True).strip()

    def run_workflow(self):
        workflow = (ROOT / ".github/workflows/f1-original-runtime-native.yml").read_text()
        step = workflow.split(STEP, 1)[1].split("      - name:", 1)[0]
        lines = step.splitlines()
        start = next(index for index, line in enumerate(lines) if "python3 -I -B - <<'PYCODE'" in line) + 1
        end = next(index for index in range(start, len(lines)) if lines[index].strip() == "PYCODE")
        program = textwrap.dedent("\n".join(lines[start:end]))
        return subprocess.run([sys.executable, "-I", "-B", "-c", program], cwd=ROOT,
                              env=self.environment, capture_output=True, text=True, timeout=20, check=False)

    def fetch_commands(self):
        return [command for command in map(json.loads, self.commands.read_text().splitlines())
                if "fetch" in command] if self.commands.exists() else []

    def replace_lock(self, kernel):
        (self.desktop / "support/upstream-lock.json").write_text(json.dumps({"kernel": kernel}))
        self.commit(self.desktop)
        self.update_pin()

    def test_depth_one_failure_is_fixed_without_changing_reviewed_source(self):
        before = self.git(self.desktop, "rev-parse", "HEAD", "HEAD^{tree}")
        absent = subprocess.run([self.real_git, "-C", str(self.desktop), "cat-file", "-e", self.kernel["tree"]],
                                env=self.environment, capture_output=True, check=False)
        self.assertNotEqual(absent.returncode, 0, "fixture must reproduce the missing upstream Git tree")
        result = self.run_workflow()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.desktop, "ls-tree", "-rz", self.kernel["tree"]),
                         self.git(self.upstream, "ls-tree", "-rz", self.kernel["tree"]))
        self.assertEqual(self.git(self.desktop, "show", self.kernel["commit"] + ":Cargo.lock"),
                         b"immutable upstream lock seed\n")
        self.assertEqual(self.git(self.desktop, "rev-parse", "HEAD", "HEAD^{tree}"), before)
        self.assertEqual(self.git(self.desktop, "status", "--porcelain=v1", "--untracked-files=all"), b"")
        self.assertEqual(json.loads(self.receipt.read_text()), dict(
            self.kernel, desktop_identity_unchanged=True, tracked_files_unchanged=True))
        self.assertEqual(self.fetch_commands(), [["-C", str(self.desktop), "-c", "credential.helper=",
                                                 "-c", "core.askPass=", "fetch", "--depth=1", "--no-tags",
                                                 "https://github.com/asterinas/asterinas.git", self.kernel["commit"]]])

    def test_wrong_upstream_tree_fails_after_exact_fetch(self):
        self.replace_lock(dict(self.kernel, tree="0" * 40))
        result = self.run_workflow()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the immutable tree", result.stderr)
        self.assertEqual(len(self.fetch_commands()), 1)
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.git(self.desktop, "status", "--porcelain=v1", "--untracked-files=all"), b"")

    def test_unreviewed_repository_or_moving_identity_fails_before_fetch(self):
        for field, value in (("repository", "elsewhere/kernel"), ("commit", "main"), ("tree", True)):
            with self.subTest(field=field):
                self.replace_lock(dict(self.kernel, **{field: value}))
                result = self.run_workflow()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid immutable upstream source identity", result.stderr)
                self.assertEqual(self.fetch_commands(), [])
                self.assertFalse(self.receipt.exists())

    def test_dirty_or_wrong_reviewed_desktop_stops_before_fetch(self):
        original_pin = self.environment["DESKTOP_SOURCE_PIN"]
        self.environment["DESKTOP_SOURCE_PIN"] = "0" * 40
        result = self.run_workflow()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must remain exact before fetching", result.stderr)
        self.environment["DESKTOP_SOURCE_PIN"] = original_pin
        (self.desktop / "unreviewed-input").write_bytes(b"dirty")
        result = self.run_workflow()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must remain exact before fetching", result.stderr)
        self.assertEqual(self.fetch_commands(), [])
        self.assertFalse(self.receipt.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
