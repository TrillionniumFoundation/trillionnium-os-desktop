"""Exercise the tracked CI evidence packager as a real shell process."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class S08EvidenceTests(unittest.TestCase):
    def package(self, directory):
        workflow = (ROOT / ".github/workflows/s08-servo-vertical-slice.yml").read_text()
        start = workflow.index("      - name: Collect exact-head evidence\n")
        end = workflow.index("      - name: Upload exact-head S08 evidence\n", start)
        block = workflow[start:end]
        script = textwrap.dedent(block.split("        run: |\n", 1)[1])
        environment = os.environ.copy()
        environment.update(
            RUNNER_TEMP=str(directory),
            EXPECTED_HEAD="a" * 40,
            SERVO_COMMIT="b" * 40,
        )
        subprocess.run(
            ["bash", "-c", script],
            env=environment,
            check=True,
            capture_output=True,
            timeout=20,
        )
        return directory / "s08-evidence"

    def test_real_packet_repackages_and_verifies_after_relocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "source-tree.txt").write_text("c" * 40 + "\n")
            (directory / "s08-product.log").write_text("bounded fixture diagnostic\n")
            evidence = self.package(directory)
            self.package(directory)
            manifest = (evidence / "SHA256SUMS").read_text()
            self.assertNotIn("SHA256SUMS", manifest)
            self.assertNotIn(str(directory), manifest)
            names = {line.split("  ", 1)[1] for line in manifest.splitlines()}
            self.assertEqual(
                names,
                {"./evidence.json", "./s08-product.log", "./source-tree.txt"},
            )
            relocated = directory / "relocated"
            shutil.move(evidence, relocated)
            subprocess.run(
                ["sha256sum", "-c", "SHA256SUMS"],
                cwd=relocated,
                check=True,
                capture_output=True,
                timeout=10,
            )

    def test_actual_verifier_rejects_changed_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = self.package(Path(temporary))
            (evidence / "evidence.json").write_text('{"release_proven":true}\n')
            result = subprocess.run(
                ["sha256sum", "-c", "SHA256SUMS"],
                cwd=evidence,
                capture_output=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"FAILED", result.stdout)
