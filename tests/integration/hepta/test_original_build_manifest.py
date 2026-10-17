"""Check manifest generation against an unchanged, fixed original checkout.

Set HEPTA_ORIGINAL_SOURCE to that checkout. Missing or changed source fails;
these checks never resolve Cargo dependencies, compile or launch Agentd.
"""

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
            gate.prepare_runner(self.source, runner)
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
            gate.verify_runner_lock(self.source, runner)

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


if __name__ == "__main__":
    unittest.main()
