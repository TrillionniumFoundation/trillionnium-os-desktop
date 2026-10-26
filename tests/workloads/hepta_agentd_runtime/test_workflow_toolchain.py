#!/usr/bin/env python3
"""Exercise the actual workflow selectors against real current Git sources."""
import json
import subprocess
import textwrap
import unittest

from test_current_source_review import SourceFixture, HERE, ROOT
import current_source_review as source


class WorkflowToolchainTests(SourceFixture, unittest.TestCase):
    def run_step(self, name):
        directory = self.desktop / "tests/workloads/hepta_agentd_runtime"
        (directory / "current_source_review.py").write_bytes((HERE / "current_source_review.py").read_bytes())
        self.commit(self.desktop)
        ci = self.root / "ci"
        (ci / "identity").mkdir(parents=True, exist_ok=True)
        envfile = self.root / "github-env"
        workflow = (ROOT / ".github/workflows/f1-original-runtime-native.yml").read_text()
        step = workflow.split("      - name: " + name + "\n", 1)[1].split("      - name:", 1)[0]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        # The real source directory must be canonical; use a real independent
        # clone at the exact workflow path, rather than a pathname mock.
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(self.hepta), str(ci / "hepta-source")],
                       env=source.ENV, capture_output=True, check=True)
        result = subprocess.run(["/bin/bash", "-c", script], cwd=self.desktop,
                                env=dict(source.ENV, GITHUB_WORKSPACE=str(self.desktop), F1_CI_ROOT=str(ci),
                                         GITHUB_ENV=str(envfile)), capture_output=True, text=True,
                                timeout=30, check=False)
        return result, envfile.read_text() if envfile.exists() else None, ci

    def test_actual_workflow_exports_current_checkout_and_canonical_hepta_pins(self):
        result, output, ci = self.run_step("Resolve the reviewed original source pair")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.splitlines(), ["DESKTOP_SOURCE_PIN=" + self.git(self.desktop, "rev-parse", "HEAD"),
                                               "HEPTA_SOURCE_PIN=" + self.contract["commit"]])
        self.assertTrue((ci / "identity/source-selection.json").is_file())

    def test_actual_workflow_exports_only_the_real_manifest_version_and_pinned_review(self):
        result, output, ci = self.run_step("Freeze and verify the current canonical source review")
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = dict(line.split("=", 1) for line in output.splitlines())
        self.assertEqual(exported["USERSPACE_TOOLCHAIN_PIN"], "1.96.0")
        review = source.load_external(ci / "identity/current-source-review.json", exported["F1_SOURCE_REVIEW_SHA256"],
                                      self.desktop, ci / "hepta-source")
        self.assertEqual(review["userspace_toolchain"]["channel"], "1.96.0")
        self.assertEqual(json.loads((ci / "identity/current-source-review.json").read_text()), review)

    def test_unpinned_actual_toolchain_stops_before_exporting_any_inputs(self):
        old = self.contract["commit"]
        self.put(self.hepta, "codex-rs/rust-toolchain.toml", '[toolchain]\nchannel = "stable"\n')
        self.commit(self.hepta)
        self.contract.update(commit=self.git(self.hepta, "rev-parse", "HEAD"),
                             tree=self.git(self.hepta, "rev-parse", "HEAD^{tree}"))
        for name in source.MANIFESTS:
            path = self.desktop / name
            path.write_text(path.read_text().replace(old, self.contract["commit"]))
        self.save_contract()
        result, output, ci = self.run_step("Freeze and verify the current canonical source review")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exact original userspace toolchain required", result.stderr)
        self.assertIsNone(output)
        self.assertFalse((ci / "identity/current-source-review.json").exists())


if __name__ == "__main__":
    unittest.main()
