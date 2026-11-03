"""Reject a successful metadata command that resolved a different product."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_text_product as product


class TextProductProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(Path(__file__).with_name("linux-text-profile.json").read_text())
        self.hepta = json.loads(Path(__file__).with_name("HEPTA_SHARED_PRESENTER.json").read_text())["commit"]
        source = "git+https://github.com/TrillionniumFoundation/hepta-private-ci?rev=" + self.hepta + "#" + self.hepta
        sdk = "git+" + self.profile["makepad_repository"] + "?rev=" + self.profile["makepad_commit"] + "#" + self.profile["makepad_commit"]
        entries = (("trill-shell", None, ["hepta-native-makepad"]),
                   ("hepta-session-host", None, ["native-text"]),
                   ("hepta-robrix-ui", source, ["native-presentation"]),
                   ("hepta-control-core", source, []),
                   ("codex-hepta-agentd", source, []),
                   ("codex-hepta-memory", source, []),
                   ("makepad-widgets", sdk, []))
        self.metadata = {"packages": [{"name": name, "id": name, "source": origin}
                                      for name, origin, _ in entries],
                         "resolve": {"nodes": [{"id": name, "features": features}
                                                for name, _, features in entries]}}

    def test_exact_original_graph_is_accepted(self):
        result = product.validate_graph(self.metadata, self.hepta, self.profile)
        self.assertEqual(result["hepta-session-host"]["features"], ["native-text"])

    def test_egui_or_disconnected_text_feature_is_not_a_text_build(self):
        for name in ("trill-shell", "hepta-session-host", "hepta-robrix-ui"):
            metadata = copy.deepcopy(self.metadata)
            next(node for node in metadata["resolve"]["nodes"] if node["id"] == name)["features"] = []
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Missing native feature"):
                product.validate_graph(metadata, self.hepta, self.profile)

    def test_mixed_original_sources_and_local_runtime_substitution_are_refused(self):
        for value in (None, "git+https://github.com/TrillionniumFoundation/hepta-private-ci?rev=" + "a" * 40 + "#" + "a" * 40):
            metadata = copy.deepcopy(self.metadata)
            next(package for package in metadata["packages"] if package["name"] == "codex-hepta-agentd")["source"] = value
            with self.subTest(source=value), self.assertRaises(ValueError):
                product.validate_graph(metadata, self.hepta, self.profile)

    def test_clipboard_candidate_and_sdk_source_override_are_separate(self):
        metadata = copy.deepcopy(self.metadata)
        metadata["resolve"]["nodes"][0]["features"].append("hepta-native-clipboard-sdk")
        with self.assertRaisesRegex(ValueError, "independent patched SDK"):
            product.validate_graph(metadata, self.hepta, self.profile)
        metadata = copy.deepcopy(self.metadata)
        metadata["packages"][-1]["source"] = None
        with self.assertRaisesRegex(ValueError, "Original Makepad SDK differs"):
            product.validate_graph(metadata, self.hepta, self.profile)

    def test_unresolved_and_duplicate_original_owner_are_refused(self):
        metadata = copy.deepcopy(self.metadata)
        metadata["resolve"]["nodes"] = [node for node in metadata["resolve"]["nodes"] if node["id"] != "codex-hepta-agentd"]
        with self.assertRaisesRegex(ValueError, "one resolved package"):
            product.validate_graph(metadata, self.hepta, self.profile)
        metadata = copy.deepcopy(self.metadata)
        metadata["packages"].append(dict(metadata["packages"][4], id="other-agentd"))
        metadata["resolve"]["nodes"].append({"id": "other-agentd", "features": []})
        with self.assertRaisesRegex(ValueError, "one resolved package"):
            product.validate_graph(metadata, self.hepta, self.profile)


class ActualSourceCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trill-cargo-cache-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.hepta = self.repo("hepta")
        self.sdk = self.repo("makepad")
        self.head = self.git(self.hepta, "rev-parse", "HEAD")
        self.tree = self.git(self.hepta, "rev-parse", "HEAD^{tree}")
        self.profile = {"makepad_repository": "https://github.com/kevinaboos/makepad",
                        "makepad_commit": self.git(self.sdk, "rev-parse", "HEAD")}
        sources = ((self.hepta, "https://github.com/TrillionniumFoundation/hepta-private-ci", self.head),
                   (self.sdk, self.profile["makepad_repository"], self.profile["makepad_commit"]))
        self.metadata = {"packages": [{"name": root.name, "manifest_path": str(root / "Cargo.toml"),
            "source": "git+" + repository + "?rev=" + head + "#" + head} for root, repository, head in sources]}

    def git(self, root, *args):
        return subprocess.check_output(["git", "-C", str(root), "-c", "user.name=Build audit",
            "-c", "user.email=build-audit@example.invalid", *args], text=True, stderr=subprocess.PIPE).strip()

    def repo(self, name):
        root = self.root / name
        root.mkdir()
        self.git(root, "init", "-q")
        (root / "Cargo.toml").write_text('[package]\nname = "' + name + '"\nversion = "0.1.0"\n')
        (root / "src").mkdir()
        (root / "src/lib.rs").write_text("pub fn original() {}\n")
        self.git(root, "add", "Cargo.toml", "src/lib.rs")
        self.git(root, "commit", "-qm", "Original source fixture")
        return root

    def verify(self, metadata=None):
        return product.verify_source_caches(metadata or self.metadata, self.head, self.tree, self.profile)

    def test_actual_roots_and_trees_are_recorded_while_cargo_marker_is_allowed(self):
        (self.hepta / ".cargo-ok").write_text("normal untracked Cargo marker")
        result = self.verify()
        self.assertEqual(result["hepta"]["tree"], self.tree)
        self.assertEqual(result["hepta"]["root"], str(self.hepta))
        self.assertTrue(result["makepad"]["tracked_clean"])

    def test_tracked_poison_and_index_flags_are_refused_on_actual_git_checkout(self):
        source = self.hepta / "src/lib.rs"
        original = source.read_text()
        source.write_text("pub fn substituted() {}\n")
        with self.assertRaisesRegex(ValueError, "tracked source is dirty"):
            self.verify()
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(flag=flag):
                self.git(self.hepta, "update-index", "--" + flag, "src/lib.rs")
                with self.assertRaisesRegex(ValueError, "flags hide source changes"):
                    self.verify()
                self.git(self.hepta, "update-index", "--no-" + flag, "src/lib.rs")
        source.write_text(original)
        self.verify()

    def test_one_family_cannot_mix_two_roots_even_with_the_same_commit(self):
        clone = self.root / "hepta-other"
        self.git(self.root, "clone", "-q", str(self.hepta), str(clone))
        changed = copy.deepcopy(self.metadata)
        changed["packages"].append(dict(changed["packages"][0], manifest_path=str(clone / "Cargo.toml")))
        with self.assertRaisesRegex(ValueError, "one Git worktree"):
            self.verify(changed)

    def test_changed_cache_head_and_claimed_hepta_tree_are_refused(self):
        with self.assertRaisesRegex(ValueError, "HEAD/tree mismatch"):
            product.verify_source_caches(self.metadata, self.head, "0" * 40, self.profile)
        (self.sdk / "src/lib.rs").write_text("pub fn another_sdk() {}\n")
        self.git(self.sdk, "add", "src/lib.rs")
        self.git(self.sdk, "commit", "-qm", "Different SDK head")
        with self.assertRaisesRegex(ValueError, "HEAD/tree mismatch"):
            self.verify()

    def test_compiler_wrappers_and_flags_cannot_survive_the_controlled_environment(self):
        tools = {name: "/fixed/toolchain/bin/" + name for name in ("cargo", "rustc", "rustdoc")}
        inherited = {"RUSTC": "/different/compiler", "RUSTDOC": "/different/docs", "RUSTC_WRAPPER": "/wrapper",
                     "CARGO_ENCODED_RUSTFLAGS": "--cfg\x1fsubstituted", "CARGO_BUILD_RUSTC_WRAPPER": "/wrapper",
                     "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS": "--cfg substituted",
                     "RUSTC_BOOTSTRAP": "1", "CFLAGS": "-DSUBSTITUTED", "CARGO_HOME": "/existing/cache"}
        env, removed = product.controlled_environment({"toolchain": "1.96.0"}, self.root / "target", 2, tools, inherited)
        self.assertEqual(env["RUSTC"], tools["rustc"])
        self.assertEqual(env["RUSTDOC"], tools["rustdoc"])
        self.assertEqual(env["RUSTC_WRAPPER"], "")
        self.assertEqual(env["CARGO_ENCODED_RUSTFLAGS"], "")
        self.assertNotIn("RUSTC_BOOTSTRAP", env)
        self.assertNotIn("CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS", env)
        self.assertNotIn("CFLAGS", env)
        self.assertEqual(env["CARGO_HOME"], "/existing/cache")
        self.assertIn("CARGO_BUILD_RUSTC_WRAPPER", removed)


if __name__ == "__main__":
    unittest.main()
