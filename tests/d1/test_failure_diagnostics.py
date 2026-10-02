from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ImageFailureDiagnosticsTests(unittest.TestCase):
    def test_failure_uploads_use_bounded_evidence_without_guest_disk(self) -> None:
        for name in ("d1-final-qualification", "d2i-integrated-image", "s10-production-debian-qemu"):
            with self.subTest(workflow=name):
                text = (ROOT / f".github/workflows/{name}.yml").read_text()
                upload = text.split("- name: Upload bounded failure diagnostics\n", 1)[1]
                self.assertIn("/evidence", upload)
                self.assertNotIn("/qemu", upload)
                self.assertNotIn(".ext4", upload)

    def test_collector_keeps_log_tail_and_skips_large_disk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            d1 = root / "trillionnium-d1"
            d1.mkdir()
            disk = d1 / "run.ext4"
            with disk.open("wb") as stream:
                stream.truncate(3 * 1024**3)
            (d1 / "serial.log").write_bytes(b"old\n" * (2 * 1024**2) + b"final failure\n")
            (d1 / "acceptance.json").write_text('{"status":"FAIL"}\n')
            script = root / "collect.sh"
            source = (ROOT / "tools/collect_d2i_failure_diagnostics.sh").read_text()
            script.write_text(source.replace("/tmp/trillionnium-", str(root / "trillionnium-")))
            environment = dict(os.environ, RUNNER_TEMP=str(root), GITHUB_WORKSPACE=str(root))
            result = subprocess.run(["bash", str(script)], env=environment, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            destination = root / "trillionnium-d2i/evidence/failure-diagnostics"
            manifest = json.loads((destination / "manifest.json").read_text())
            self.assertFalse(any(record["source"].endswith(".ext4") for record in manifest["records"]))
            log = next(record for record in manifest["records"] if record["source"].endswith("serial.log"))
            self.assertTrue(log["tail_truncated"])
            self.assertEqual(log["copied_bytes"], 4 * 1024**2)
            self.assertTrue((destination / log["copied_path"]).read_bytes().endswith(b"final failure\n"))

    def test_guest_failure_preserves_service_cause_before_poweroff(self) -> None:
        source = (ROOT / "packaging/debian/image/rootfs-overlay/usr/local/libexec/trillionnium-d1-acceptance").read_text()
        failure = source.split("fail() {", 1)[1].split("\n}\n", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            script = "set -euo pipefail\nresult_dir=$1\n"
            script += "journalctl() { printf 'peer attestation refused\\n'; }\n"
            script += "systemctl() { return 0; }\nsync() { return 0; }\n"
            script += "fail() {" + failure + "\n}\nfail authorized_health_request_failed\n"
            result = subprocess.run(["bash", "-c", script, "failure-test", directory], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertIn("peer attestation refused", result.stdout)
            self.assertIn("TRILLIONNIUM_D1_ACCEPTANCE_FAIL:authorized_health_request_failed", result.stdout)
            acceptance = json.loads((Path(directory) / "acceptance.json").read_text())
            self.assertEqual(acceptance["status"], "FAIL")
            self.assertEqual((Path(directory) / "agent-port-journal.txt").read_text(), "peer attestation refused\n")


if __name__ == "__main__":
    unittest.main()
