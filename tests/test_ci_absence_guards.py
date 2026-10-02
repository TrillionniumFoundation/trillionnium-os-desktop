"""Actual native absence scans; source guards do not qualify product execution."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def blocks(path, name):
    lines = (ROOT / path).read_text().splitlines()
    result = []
    for index, line in enumerate(lines):
        if line.strip() != "- name: " + name:
            continue
        start = next(i for i in range(index + 1, len(lines))
                     if lines[i].strip() == "run: |") + 1
        end = start
        while end < len(lines) and (not lines[end].strip() or lines[end].startswith("          ")):
            end += 1
        result.append("\n".join(line[10:] if line.startswith("          ") else line
                                for line in lines[start:end]) + "\n")
    return result


def helper(body, name):
    start = body.index(name + "() {")
    end = body.index("\n}\n", start) + 3
    return body[start:end]


def shell(body, directory):
    return subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", body],
                          cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=10, env={**os.environ, "LC_ALL": "C"})


class NativeCiAbsenceGuardTests(unittest.TestCase):
    def actor_fixture(self, directory, marker=""):
        target = directory / "crates/hepta-browser-actor/src"
        target.mkdir(parents=True)
        (target / "fixture.rs").write_text("pub fn from_attested() {}\n"
                                           "pub fn handle_attested() {}\n" + marker + "\n")
        contracts = directory / "contracts"
        contracts.mkdir()
        (contracts / "browser-actor.v1.json").write_bytes(
            (ROOT / "contracts/browser-actor.v1.json").read_bytes())

    def actor_bodies(self):
        result = blocks(".github/workflows/s06-browser-actor.yml",
                        "Reconfirm sealed product API and claim ceiling")
        self.assertEqual(len(result), 2)
        return result

    def test_both_complete_actor_bodies_reject_both_exposed_api_groups(self):
        for body in self.actor_bodies():
            for marker in ("pub struct BrowserActor<R> {}", "pub type PrincipalBinding = (); "):
                with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temp:
                    directory = Path(temp)
                    self.actor_fixture(directory, marker)
                    result = shell(body, directory)
                    self.assertEqual(result.returncode, 1, result.stdout.decode())
                    self.assertIn(b"forbidden source match", result.stdout)

    def test_both_complete_actor_bodies_preserve_clean_source_result(self):
        for body in self.actor_bodies():
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                self.actor_fixture(directory)
                result = shell(body, directory)
                self.assertEqual(result.returncode, 0, result.stdout.decode())

    def test_actor_native_missing_input_fails_before_following_success(self):
        for body in self.actor_bodies():
            commands = [line for line in body.splitlines() if line.startswith("reject_match -R")]
            self.assertEqual(len(commands), 2)
            for command in commands:
                with tempfile.TemporaryDirectory() as temp:
                    result = shell("set -euo pipefail\n" + helper(body, "reject_match")
                                   + command + "\nprintf reached-success\n", temp)
                    self.assertEqual(result.returncode, 2, result.stdout.decode())
                    self.assertNotIn(b"reached-success", result.stdout)

    def test_servo_native_guard_tail_refuses_marker_and_missing_source(self):
        source = (ROOT / ".github/workflows/s07-servo-retained-node.yml").read_text()
        text = "\n".join(line[10:] if line.startswith("          ") else line
                         for line in source.splitlines()) + "\n"
        command = next(line for line in text.splitlines()
                       if line.startswith('reject_match -R -F "TODO(#4344)'))
        body = "set -euo pipefail\n" + helper(text, "reject_match") + command + "\ngit -C servo diff --check\n"
        for case, expected in (("clean", 0), ("marker", 1), ("missing", 2)):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                target = directory / "servo/ports/servoshell/desktop/headed_window.rs"
                target.parent.mkdir(parents=True)
                subprocess.run(["git", "init", "-q", str(directory / "servo")], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if case != "missing":
                    target.write_text("// TODO(#4344): Forward action to Servo\n" if case == "marker"
                                      else "// actual forwarded callback\n")
                result = shell(body, directory)
                self.assertEqual(result.returncode, expected, result.stdout.decode())

    def test_d2i_native_guard_tail_distinguishes_clean_forbidden_and_read_error(self):
        text = (ROOT / "tools/run_d2i_integrated_image.sh").read_text()
        lines = text.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("  reject_source_match -RInE"))
        body = "set -euo pipefail\n" + helper(text, "reject_source_match") + "\n".join(lines[start:start + 2]) + "\n"
        for case, expected in (("clean", 0), ("write_permission", 1), ("push", 1), ("missing", 2)):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                (directory / "tools").mkdir()
                (directory / "tools/run_d2i_integrated_image.sh").write_text(text)
                if case != "missing":
                    (directory / ".github/workflows").mkdir(parents=True)
                    content = {"clean": "permissions:\n  contents: read\n",
                               "write_permission": "permissions:\n  contents: write\n",
                               "push": "# forbidden command: git push\n"}[case]
                    (directory / ".github/workflows/d2i-integrated-image.yml").write_text(content)
                result = shell(body, directory)
                self.assertEqual(result.returncode, expected, result.stdout.decode())


if __name__ == "__main__":
    unittest.main()
