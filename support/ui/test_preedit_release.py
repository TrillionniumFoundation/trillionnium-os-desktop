"""Reject lock/source/runtime substitutions in the derived release boundary."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_preedit as release


SDK = "git+https://example.invalid/reviewed-sdk?rev=" + "a" * 40 + "#" + "a" * 40


def lock(packages):
    lines = ["version = 4"]
    for package in packages:
        lines.append("[[package]]")
        lines.extend(key + " = " + json.dumps(value) for key, value in package.items())
    return ("\n".join(lines) + "\n").encode()


class LockTransitionTests(unittest.TestCase):
    def setUp(self):
        self.sdk = [{"name": "sdk-" + str(i), "version": "1.0.0", "source": SDK} for i in range(102)]
        self.packages = {(p["name"], p["version"]) for p in self.sdk}
        self.before = [*copy.deepcopy(self.sdk),
            {"name": "registry", "version": "2.0.0", "source": "registry+https://example.invalid/index", "checksum": "b" * 64},
            {"name": "app", "version": "1.0.0", "dependencies": ["sdk-0", "registry"]}]
        self.after = copy.deepcopy(self.before)
        for package in self.after[:102]:
            package.pop("source")

    def compare(self, after=None):
        return release.compare_locks(lock(self.before), lock(self.after if after is None else after), SDK, self.packages)

    def test_only_102_origins_change_while_all_other_graph_content_is_retained(self):
        self.assertEqual(self.compare()["sdk_origins_changed"], 102)
        self.assertEqual(self.compare()["packages"], 104)
        # A path dependency of the same name/version is unqualified in Cargo's
        # serialization; a registry dependency still needs its source suffix.
        self.before.append({"name": "sdk-0", "version": "1.0.0", "source": "registry+https://example.invalid/index", "checksum": "c" * 64})
        self.after.append(copy.deepcopy(self.before[-1]))
        self.before[103]["dependencies"][0] = "sdk-0 1.0.0 (" + SDK.split("#")[0] + ")"
        self.after[103]["dependencies"][0] = "sdk-0 1.0.0"
        self.assertTrue(self.compare()["all_versions_checksums_and_dependency_edges_preserved"])

    def test_package_version_checksum_source_and_dependency_edge_changes_fail(self):
        mutations = (
            lambda p: p[102].update(version="2.0.1"),
            lambda p: p[102].update(checksum="d" * 64),
            lambda p: p[102].update(source="registry+https://example.invalid/other"),
            lambda p: p[103].update(dependencies=["sdk-1", "registry"]),
            lambda p: p.append({"name": "extra", "version": "1.0.0"}),
            lambda p: p.pop(1),
            lambda p: p[0].update(source=SDK),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(self.after)
                mutate(changed)
                with self.assertRaises(ValueError):
                    self.compare(changed)

    def test_incomplete_metadata_cannot_authorize_a_partial_sdk_override(self):
        with self.assertRaisesRegex(ValueError, "102"):
            release.compare_locks(lock(self.before), lock(self.after), SDK, list(self.packages)[:101])


class ActualDerivedSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trill-release-source-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.candidate = self.root / "base", self.root / "candidate"
        self.source.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_AUTHOR_NAME="Release fixture", GIT_COMMITTER_NAME="Release fixture",
            GIT_AUTHOR_EMAIL="fixture@example.invalid", GIT_COMMITTER_EMAIL="fixture@example.invalid",
            GIT_AUTHOR_DATE="1700000000 +0000", GIT_COMMITTER_DATE="1700000000 +0000")
        self.git(self.source, "init", "-q")
        (self.source / "ui").mkdir()
        (self.source / "ui/Cargo.lock").write_bytes(b"version = 4\n# base fixture\n")
        (self.source / "source.rs").write_text("pub fn original() {}\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "Base fixture")
        self.base = self.git(self.source, "rev-parse", "HEAD").strip()
        self.git(self.source, "worktree", "add", "--detach", str(self.candidate), self.base)
        (self.candidate / "ui/Cargo.lock").write_bytes(b"version = 4\n# derived fixture\n")

    def git(self, directory, *args):
        return subprocess.check_output(["git", "-C", str(directory), *args], env=self.env, stderr=subprocess.PIPE, text=True)

    def test_real_detached_commit_bundle_and_reconstruction_leave_base_untouched(self):
        original_lock = (self.source / "ui/Cargo.lock").read_bytes()
        result = release.freeze_candidate(self.candidate, self.base, self.env)
        self.assertFalse(result["published"])
        self.assertEqual(self.git(self.source, "rev-parse", "HEAD").strip(), self.base)
        self.assertEqual((self.source / "ui/Cargo.lock").read_bytes(), original_lock)
        self.assertFalse(self.git(self.source, "status", "--porcelain=v1"))
        self.assertFalse(self.git(self.candidate, "status", "--porcelain=v1"))
        bundle = self.root / "derived.bundle"
        self.git(self.candidate, "bundle", "create", str(bundle), "HEAD", "^" + self.base)
        self.git(self.source, "bundle", "verify", str(bundle))
        restored = self.root / "restored"
        self.git(self.source, "clone", "-q", "--no-hardlinks", str(self.source), str(restored))
        self.git(restored, "fetch", str(bundle), "HEAD")
        self.git(restored, "checkout", "--detach", "FETCH_HEAD")
        self.assertEqual(self.git(restored, "rev-parse", "HEAD^{tree}").strip(), result["tree"])
        self.assertEqual((restored / "ui/Cargo.lock").read_bytes(), (self.candidate / "ui/Cargo.lock").read_bytes())
        # A repeat from the same base and Cargo lock has the same Git identity.
        second = self.root / "second"
        self.git(self.source, "worktree", "add", "--detach", str(second), self.base)
        (second / "ui/Cargo.lock").write_bytes((self.candidate / "ui/Cargo.lock").read_bytes())
        self.assertEqual(release.freeze_candidate(second, self.base, self.env), result)

    def test_source_edits_untracked_files_and_attached_branch_are_not_frozen(self):
        extra = self.candidate / "source.rs"
        extra.write_text("pub fn substituted() {}\n")
        with self.assertRaisesRegex(ValueError, "Only"):
            release.freeze_candidate(self.candidate, self.base, self.env)
        self.git(self.candidate, "restore", "source.rs")
        extra = self.candidate / "untracked"
        extra.write_text("unexpected")
        with self.assertRaisesRegex(ValueError, "untracked"):
            release.freeze_candidate(self.candidate, self.base, self.env)
        extra.unlink()
        self.git(self.candidate, "switch", "-c", "fixture-branch")
        with self.assertRaisesRegex(ValueError, "detached"):
            release.freeze_candidate(self.candidate, self.base, self.env)


class WindowReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trill-release-receipt-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.derived = {"commit": "a" * 40, "tree": "b" * 40}
        self.build = {"packaged_binaries": {"trill-shell": {"sha256": "c" * 64}}}
        self.report = {key: True for key in ("passed", "preedit_profile_qualified", "supported_atspi_checks_passed",
            "real_virtual_x11_ibus_checks_passed", "atomic_editable_text_methods_passed", "private_credentials_and_state_removed")}
        self.report["provenance"] = {"source_commit": self.derived["commit"], "source_tree": self.derived["tree"],
            "build_artifact_kind": "packaged_binaries", "shell": {"sha256": "c" * 64}}
        self.write("receipt.json", self.report)
        for name, checks in release.CHECKS.items():
            self.write(name, {"passed": True, "checks": [{"name": check, "passed": True} for check in checks]})

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def verify(self):
        return release.qualified_checks(self.root, self.build, self.derived)

    def test_requires_the_exact_17_original_checks_on_the_same_packaged_source(self):
        self.assertEqual(sum(item["passed"] for item in self.verify().values()), 17)
        for mutation in (lambda p: p.update(private_credentials_and_state_removed=False),
                         lambda p: p.update(cleanup_errors=["owned child still alive"]),
                         lambda p: p["provenance"].update(source_commit="d" * 40),
                         lambda p: p["provenance"].update(build_artifact_kind="binaries"),
                         lambda p: p["provenance"]["shell"].update(sha256="e" * 64)):
            report = copy.deepcopy(self.report)
            mutation(report)
            self.write("receipt.json", report)
            with self.assertRaises(ValueError):
                self.verify()

    def test_pass_boolean_or_duplicate_names_cannot_replace_actual_gate_records(self):
        name = "ibus-receipt.json"
        for checks in ([], [{"name": release.CHECKS[name][0], "passed": True}] * 5,
                       [{"name": value, "passed": i != 4} for i, value in enumerate(release.CHECKS[name])]):
            self.write(name, {"passed": True, "checks": checks})
            with self.assertRaisesRegex(ValueError, "window checks"):
                self.verify()


class DirectToolDispatchTests(unittest.TestCase):
    def test_clippy_and_fmt_do_not_dispatch_through_the_ambient_cargo_proxy(self):
        with tempfile.TemporaryDirectory(prefix="trill-release-tools-") as directory:
            root = Path(directory)
            proxy = root / "cargo"
            proxy.write_text("#!/bin/sh\necho wrong-Cargo-proxy >&2\nexit 99\n")
            proxy.chmod(0o700)
            tools = {"cargo": str(proxy)}
            for name in ("clippy", "fmt"):
                executable = root / ("cargo-" + name)
                executable.write_text("#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
                executable.chmod(0o700)
                tools["cargo-" + name] = str(executable)
                arguments = ["cargo", name, "--manifest-path", "ui/Cargo.toml", "--", "--check" if name == "fmt" else "-Dwarnings"]
                result = subprocess.run(release.product.tool_command(arguments, tools), capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(result.stdout), arguments[1:])


if __name__ == "__main__":
    unittest.main()
