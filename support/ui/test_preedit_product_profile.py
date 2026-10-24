"""Reject profile/source substitutions before any compiler or product writes."""
import json
import importlib.util
import os
from pathlib import Path
import py_compile
import tempfile
import unittest
from unittest.mock import patch

import build_text_product as product
import preedit_source
import test_text_product_profile as baseline
from test_preedit_sdk import profile_fixture


class PreeditProductProfileTests(unittest.TestCase):
    def setUp(self):
        original = baseline.TextProductProfileTests()
        original.setUp()
        self.metadata, self.hepta = original.metadata, original.hepta
        self.profile = preedit_source.settings()
        self.sdk = profile_fixture()
        self.metadata["resolve"]["nodes"][0]["features"].append("hepta-native-preedit-sdk")
        self.metadata["packages"][-1].update(source=None,
            manifest_path=self.sdk["prepared_root"] + "/widgets/Cargo.toml")

    def test_preedit_accepts_one_verified_source_without_changing_original_owners(self):
        result = product.validate_graph(self.metadata, self.hepta, self.profile, self.sdk)
        self.assertEqual(result["codex-hepta-agentd"]["source"], self.metadata["packages"][4]["source"])
        self.assertEqual(result["makepad-widgets"]["source"], None)

    def test_missing_compiled_contract_or_source_verification_is_refused(self):
        with self.assertRaisesRegex(ValueError, "verified before accepting"):
            product.validate_graph(self.metadata, self.hepta, self.profile)
        self.metadata["resolve"]["nodes"][0]["features"].remove("hepta-native-preedit-sdk")
        with self.assertRaisesRegex(ValueError, "explicit compiled resource contract"):
            product.validate_graph(self.metadata, self.hepta, self.profile, self.sdk)

    def test_same_named_sdk_at_another_prepared_root_is_refused(self):
        self.metadata["packages"][-1]["manifest_path"] = "/synthetic/another-source/widgets/Cargo.toml"
        with self.assertRaisesRegex(ValueError, "Substituted prepared SDK"):
            product.validate_graph(self.metadata, self.hepta, self.profile, self.sdk)

    def test_baseline_cannot_silently_select_the_new_compiled_contract(self):
        original = baseline.TextProductProfileTests()
        original.setUp()
        original.metadata["resolve"]["nodes"][0]["features"].append("hepta-native-preedit-sdk")
        with self.assertRaisesRegex(ValueError, "explicit compiled resource contract"):
            product.validate_graph(original.metadata, original.hepta, original.profile)

    def test_non_ui_locks_cannot_keep_an_older_runtime_companion(self):
        with tempfile.TemporaryDirectory(prefix="trill-preedit-lock-") as directory:
            path = Path(directory) / "observer-Cargo.lock"
            for commit, expected_pass in ((self.hepta, True), ("e" * 40, False)):
                source = "git+https://github.com/TrillionniumFoundation/hepta-private-ci?rev=" + commit + "#" + commit
                path.write_text('version = 4\n[[package]]\nname = "original-owner"\nversion = "0.1.0"\nsource = '
                                + json.dumps(source) + '\n')
                if expected_pass:
                    self.assertEqual(product.validate_hepta_lock(path, self.hepta), product.digest(path))
                else:
                    with self.assertRaisesRegex(ValueError, "different Hepta companion"):
                        product.validate_hepta_lock(path, self.hepta)

    def test_ignored_bytecode_cannot_replace_checked_source_helpers(self):
        with tempfile.TemporaryDirectory(prefix="trill-preedit-bytecode-") as directory:
            root = Path(directory)
            prepare = root / "prepare-native-clipboard-sdk.py"
            verifier = root / "verify-native-clipboard-sdk.py"
            prepare_source = "VALUE = " + repr(self.sdk) + "\n"
            verifier_source = ("import importlib.util\nfrom pathlib import Path\n"
                "spec = importlib.util.spec_from_file_location('preedit_fixture_prepare', "
                "Path(__file__).with_name('prepare-native-clipboard-sdk.py'))\n"
                "prepare = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(prepare)\n"
                "def verify(*args):\n    return prepare.VALUE\n")
            for path, source in ((prepare, prepare_source), (verifier, verifier_source)):
                poisoned = "raise AssertionError('ignored helper bytecode executed')\n"
                path.write_text(poisoned.ljust(len(source)))
                os.utime(path, (1700000000, 1700000000))
                py_compile.compile(str(path), doraise=True)
                path.write_text(source)
                os.utime(path, (1700000000, 1700000000))
            spec = importlib.util.spec_from_file_location("poisoned_helper_control", verifier)
            with self.assertRaisesRegex(AssertionError, "ignored helper bytecode"):
                spec.loader.exec_module(importlib.util.module_from_spec(spec))
            original, config = root / "metadata.json", root / "config.toml"
            original.write_text("{}")
            config.write_text("")
            with patch.object(preedit_source, "verified_helper", return_value=(root, root)):
                actual = preedit_source.verify(b"{}", root, None, original, config, root)
            self.assertEqual(actual, self.sdk)
