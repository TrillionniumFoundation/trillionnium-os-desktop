"""Exercise pair provenance and actual command failures with temporary Git DAGs."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("check_organ_pair", "check_organ_pair.py")
fixtures = load("release_profile_tests", "test_organ_release_profile.py")


class PairExecutionTests(unittest.TestCase):
    def setUp(self):
        fixtures.SourceCombinationTests.setUp(self)
        self.output = self.root / "execution"
        fixtures.write(self.os, "support/release/organ_source_map.json",
                       runner.profile.canonical(self.mapping))
        fixtures.commit(self.os, "review source map")
        with patch.object(runner.profile, "HISTORY_OWNER", fixtures.profile.HISTORY_OWNER):
            manifest, _ = runner.profile.create_manifest(
                *fixtures.SourceCombinationTests.inputs(self))
        self.manifest = self.root / "profile.json"
        self.manifest.write_bytes(runner.profile.canonical(manifest))
        self.owner = fixtures.profile.HISTORY_OWNER

    def arguments(self):
        return ["--os-repo", str(self.os), "--hepta-repo", str(self.hepta),
                "--os-head", fixtures.git(self.os, "rev-parse", "HEAD"),
                "--os-tree", fixtures.git(self.os, "rev-parse", "HEAD^{tree}"),
                "--manifest", str(self.manifest), "--output-dir", str(self.output)]

    def run_pair(self, *extra):
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            return runner.main(self.arguments() + list(extra))

    def receipt(self):
        return json.loads((self.output / "pair-receipt.json").read_text())

    def test_source_only_never_runs_host_commands(self):
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair(), 0)
        self.assertEqual(self.receipt()["qualification"], "source-only")
        self.assertEqual(self.receipt()["steps"], [])

    def test_wrong_pin_prevents_any_execution_or_output(self):
        manifest = json.loads(self.manifest.read_text())
        manifest["hepta"]["commit"] = "0" * 40
        self.manifest.write_text(json.dumps(manifest))
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair("--execute-host"), 1)
        self.assertFalse(self.output.exists())

    def test_actual_nonzero_child_never_qualifies_pair(self):
        step = ("failure", self.os, "1.95.0", [sys.executable, "-c", "raise SystemExit(7)"])
        with patch.object(runner, "host_steps", return_value=[step]):
            self.assertEqual(self.run_pair("--execute-host"), 1)
        self.assertEqual(self.receipt()["qualification"], "none")
        self.assertEqual(self.receipt()["steps"][0]["exit_code"], 7)

    def test_generator_modifying_sources_invalidates_successful_command(self):
        step = ("generator", self.os, "1.95.0",
                [sys.executable, "-c", "from pathlib import Path; Path('generated.rs').write_text('x')"])
        with patch.object(runner, "host_steps", return_value=[step]):
            self.assertEqual(self.run_pair("--execute-host"), 1)
        self.assertFalse(self.receipt()["passed"])
        self.assertIn("dirty checkout", self.receipt()["error"])

    def test_slow_actual_child_is_stopped_and_cannot_qualify(self):
        step = ("timeout", self.os, "1.95.0",
                [sys.executable, "-c", "import time; time.sleep(60)"])
        with patch.object(runner, "host_steps", return_value=[step]):
            self.assertEqual(self.run_pair("--execute-host", "--step-timeout", "1"), 1)
        self.assertEqual(self.receipt()["qualification"], "none")
        self.assertEqual(self.receipt()["steps"][0]["error"], "step_timeout")

    def test_success_records_real_log_and_retains_source_identity(self):
        step = ("success", self.os, "1.95.0", [sys.executable, "-c", "print('actual child')"])
        with patch.object(runner, "host_steps", return_value=[step]):
            self.assertEqual(self.run_pair("--execute-host"), 0)
        receipt = self.receipt()
        self.assertEqual(receipt["qualification"], "host-build-tests")
        self.assertEqual((self.output / "success.log").read_text(), "actual child\n")
        self.assertEqual(receipt["source"]["os"]["commit"],
                         fixtures.git(self.os, "rev-parse", "HEAD"))
        self.assertEqual(receipt["production_authority"], "not_configured_by_this_tool")

    def test_receipt_hash_binds_the_manifest_bytes_actually_verified(self):
        raw = self.manifest.read_bytes()
        verify = runner.profile.verify_manifest

        def replace_after_verification(*args):
            result = verify(*args)
            self.manifest.write_bytes(b'{"different":"unverified bytes"}\n')
            return result

        with patch.object(runner.profile, "verify_manifest", side_effect=replace_after_verification):
            self.assertEqual(self.run_pair(), 0)
        self.assertEqual(self.receipt()["manifest_sha256"], runner.profile.sha256(raw))

    def test_build_only_runs_binaries_without_claiming_tests(self):
        steps = [(name, self.os, "1.95.0", [sys.executable, "-c", "print('built')"])
                 for name in ("ui-build", "ui-tests", "adapter-tests", "hepta-build", "hepta-tests")]
        with patch.object(runner, "host_steps", return_value=steps):
            self.assertEqual(self.run_pair("--build-host"), 0)
        receipt = self.receipt()
        self.assertEqual([item["name"] for item in receipt["steps"]], ["ui-build", "hepta-build"])
        self.assertEqual(receipt["qualification"], "host-builds")


if __name__ == "__main__":
    unittest.main()
