"""Check manifest generation against an unchanged, fixed original checkout.

Set HEPTA_ORIGINAL_SOURCE to that checkout. Missing or changed source fails;
these checks never resolve Cargo dependencies, compile or launch Agentd.
"""

import copy
import os
from pathlib import Path
import re
import tempfile
import tomllib
import unittest

import run_original_agentd as gate


class OriginalBuildManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("HEPTA_ORIGINAL_SOURCE")
        if not source:
            raise RuntimeError("HEPTA_ORIGINAL_SOURCE must name the fixed original checkout")
        cls.source = Path(source).resolve(strict=True)
        cls.identity = gate.verify_source(cls.source)
        cls.workspace_path = cls.source / "codex-rs/Cargo.toml"
        cls.workspace_text = cls.workspace_path.read_text()
        cls.workspace = tomllib.loads(cls.workspace_text)

    def test_fixed_source_resolver_survives_external_workspace(self):
        self.assertEqual(self.identity["commit"], gate.PIN)
        self.assertEqual(self.workspace["workspace"]["resolver"], "2")
        with tempfile.TemporaryDirectory(prefix="hepta-manifest-") as temporary:
            runner = Path(temporary) / "probe"
            omission = gate.prepare_runner(self.source, runner)
            generated = tomllib.loads((runner / "Cargo.toml").read_text())
            self.assertEqual(
                generated["workspace"].get("resolver"),
                self.workspace["workspace"]["resolver"],
                "external package edition must not replace the original explicit resolver",
            )
            self.assertEqual(generated["package"]["edition"], "2024")
            for profile in ["dev", "dev-small"]:
                self.assertEqual(generated["profile"][profile], self.workspace["profile"][profile])
            self.assertEqual(
                (runner / "Cargo.lock").read_bytes(),
                (self.source / "codex-rs/Cargo.lock").read_bytes(),
            )
            self.assertEqual(omission["origin"], gate.UNUSED_PATCH_ORIGIN)
            self.assertEqual(omission["target"], self.workspace["patch"]["crates-io"]["tungstenite"])
            expected_patches = copy.deepcopy(self.workspace["patch"])
            del expected_patches[gate.UNUSED_PATCH_ORIGIN]
            for patches in expected_patches.values():
                for target in patches.values():
                    if "path" in target:
                        target["path"] = str((self.source / "codex-rs" / target["path"]).resolve(strict=True))
            self.assertEqual(generated["patch"], expected_patches,
                             "every other patch mapping must remain unchanged")
            with self.assertRaisesRegex(gate.GateError, "probe_omitted_patch_target_is_active"):
                gate.verify_runner_lock(self.source, runner)
            self.assertEqual(
                (runner / "src/original_session_probe.rs").read_bytes(),
                (gate.HERE / "original_session_probe.rs").read_bytes(),
                "the linked original probe must compile the actual Session acceptance module",
            )

    def check_rejected_resolver(self, replacement):
        # Only a private copy of the manifest is changed for negative cases.
        # Missing supporting files would make an accidental fall-through fail.
        changed, count = re.subn(
            r'^resolver = "2"$', replacement, self.workspace_text, flags=re.MULTILINE,
        )
        self.assertEqual(count, 1, "negative case must derive from the pinned resolver declaration")
        with tempfile.TemporaryDirectory(prefix="hepta-manifest-reject-") as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "codex-rs").mkdir(parents=True)
            (source / "codex-rs/Cargo.toml").write_text(changed)
            runner = root / "probe"
            with self.assertRaisesRegex(gate.GateError, "upstream_explicit_resolver_required"):
                gate.prepare_runner(source, runner)
            self.assertFalse(runner.exists(), "reject invalid resolver before creating build inputs")

    def test_missing_resolver_is_rejected_before_preparing_directory(self):
        self.check_rejected_resolver("")

    def test_unknown_or_non_string_resolver_is_rejected(self):
        for replacement in ['resolver = "future"', "resolver = 2", 'resolver = ["2"]']:
            with self.subTest(replacement=replacement):
                self.check_rejected_resolver(replacement)

    def test_nonduplicate_source_patch_is_never_silently_dropped(self):
        for alteration in ["different_target", "additional_mapping", "missing_origin"]:
            upstream = copy.deepcopy(self.workspace)
            if alteration == "different_target":
                upstream["patch"][gate.UNUSED_PATCH_ORIGIN]["tungstenite"]["rev"] = "0" * 40
            elif alteration == "additional_mapping":
                upstream["patch"][gate.UNUSED_PATCH_ORIGIN]["other"] = {"version": "1"}
            else:
                del upstream["patch"][gate.UNUSED_PATCH_ORIGIN]
            with self.subTest(alteration=alteration), self.assertRaisesRegex(
                gate.GateError, "probe_unused_patch_alias_is_not_an_exact_duplicate",
            ):
                gate.runner_patch_omission(upstream)

    def check_lock(self, packages, unused):
        # Minimal negative fixtures exercise the lock guard, not Cargo or runtime.
        with tempfile.TemporaryDirectory(prefix="hepta-lock-guard-") as temporary:
            runner = Path(temporary)
            (runner / "Cargo.lock").write_text(
                "version=4\npackage=" + gate.toml_value(packages)
                + "\n[patch]\nunused=" + gate.toml_value(unused) + "\n",
            )
            return gate.verify_runner_lock(self.source, runner)

    def test_omitted_alias_target_must_be_unused_exactly_once(self):
        omission = gate.runner_patch_omission(self.workspace)
        target = omission["target"]
        source = f'git+{target["git"]}?rev={target["rev"]}#{target["rev"]}'
        original = tomllib.loads((self.source / "codex-rs/Cargo.lock").read_text())
        selected = [item for item in original["package"] if item.get("source") == source]
        self.assertEqual(len(selected), 1)
        unused = {key: selected[0][key] for key in ["name", "version", "source"]}
        root = {"name": gate.RUNNER_NAME, "version": "0.0.0"}
        checked = self.check_lock([root], [unused])
        self.assertTrue(checked["omitted_target_unused"])
        for patches in [[], [unused, unused]]:
            with self.subTest(unused_count=len(patches)), self.assertRaisesRegex(
                gate.GateError, "probe_omitted_patch_target_must_remain_unused_once",
            ):
                self.check_lock([root], patches)
        with self.assertRaisesRegex(gate.GateError, "probe_omitted_patch_target_is_active"):
            self.check_lock([root, unused], [unused])
        ssh_package = dict(unused, source="git+" + gate.UNUSED_PATCH_ORIGIN)
        with self.assertRaises(gate.GateError):
            self.check_lock([root, ssh_package], [unused])


if __name__ == "__main__":
    unittest.main()
