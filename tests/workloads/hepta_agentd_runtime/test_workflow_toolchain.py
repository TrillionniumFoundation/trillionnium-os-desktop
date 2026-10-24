#!/usr/bin/env python3
"""Exercise the real workflow resolver with isolated reviewed inputs."""
import hashlib
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


class WorkflowToolchainTests(unittest.TestCase):
    def resolve(self, channel):
        workflow = (ROOT / ".github/workflows/f1-original-runtime-native.yml").read_text()
        step = workflow.split("      - name: Resolve the reviewed original source pair\n", 1)[1].split("      - name:", 1)[0]
        program = step.split("          python3 -I -B - <<'PYCODE'\n", 1)[1].split("          PYCODE\n", 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = root / "tests/workloads/hepta_agentd_runtime"
            module.mkdir(parents=True)
            shutil.copyfile(HERE / "reviewed_toolchain.py", module / "reviewed_toolchain.py")
            review = {"schema": "hepta.native-original-runtime-source-review.v1",
                      "desktop": {"head": "a" * 40, "tree": "b" * 40},
                      "hepta": {"head": "c" * 40, "tree": "d" * 40},
                      "userspace_toolchain": {"channel": channel, "manifest": "codex-rs/rust-toolchain.toml",
                                              "sha256": hashlib.sha256(b"fixture manifest").hexdigest()}}
            (module / "source-review.json").write_text(json.dumps(review))
            output = root / "github-env"
            result = subprocess.run([sys.executable, "-I", "-B", "-c", textwrap.dedent(program)],
                                    cwd=root, env={"GITHUB_ENV": str(output), "LANG": "C.UTF-8"},
                                    capture_output=True, text=True, timeout=10, check=False)
            return result, output.read_text() if output.exists() else None

    def test_actual_workflow_exports_one_reviewed_version_with_source_pins(self):
        result, output = self.resolve("1.96.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.splitlines(), ["DESKTOP_SOURCE_PIN=" + "a" * 40,
                                               "HEPTA_SOURCE_PIN=" + "c" * 40,
                                               "USERSPACE_TOOLCHAIN_PIN=1.96.0"])

    def test_unpinned_toolchain_stops_before_exporting_any_inputs(self):
        result, output = self.resolve("stable")
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(output)


if __name__ == "__main__":
    unittest.main()
