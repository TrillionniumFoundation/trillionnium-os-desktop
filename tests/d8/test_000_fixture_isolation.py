from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from hardware_evidence_verifier import (  # noqa: E402
    create_fixture_bundle,
    verify_evidence,
)

SEED = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)


class FixtureIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (ROOT / "contracts/hardware-beta-qualification.v1.json").read_text()
        )

    def test_fixture_factory_removes_stale_files_directories_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, _ = create_fixture_bundle(self.contract, root, SEED)
            boot_logs = next(
                item for item in evidence["artifacts"] if item["role"] == "boot_logs"
            )
            boot_path = root / boot_logs["path"]
            boot_path.unlink()
            target = root / "stale-target.txt"
            target.write_text("stale\n", encoding="utf-8")
            if hasattr(os, "symlink"):
                os.symlink(target.name, boot_path)
            else:
                boot_path.write_text("stale\n", encoding="utf-8")
            (root / "unlisted.txt").write_text("extra\n", encoding="utf-8")
            stale_dir = root / "stale-dir"
            stale_dir.mkdir()
            (stale_dir / "payload").write_text("stale\n", encoding="utf-8")

            evidence, trust = create_fixture_bundle(self.contract, root, SEED)

            self.assertFalse((root / "unlisted.txt").exists())
            self.assertFalse(target.exists())
            self.assertFalse(stale_dir.exists())
            self.assertFalse((root / boot_logs["path"]).is_symlink())
            result = verify_evidence(
                evidence,
                root,
                trust,
                self.contract,
                now_epoch=500,
                require_physical=False,
            )
            self.assertEqual(result["status"], "PASS_FIXTURE_FORMAT_ONLY")

    def test_fixture_key_covers_contract_stability_window_but_is_not_production(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, trust = create_fixture_bundle(
                self.contract, Path(temporary), SEED
            )
        key = trust["labs"]["fixture-lab"]["keys"]["fixture-lab-key-1"]
        end = 100 + self.contract["thresholds"]["final_stability_seconds_min"]
        self.assertGreaterEqual(key["expires_at_epoch"], end + 10)
        self.assertEqual(key["signer_role"], "fixture_only")
        self.assertFalse(key["production_enrolled"])


if __name__ == "__main__":
    unittest.main()
