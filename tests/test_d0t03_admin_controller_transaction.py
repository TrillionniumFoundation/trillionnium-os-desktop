from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/d0t03_admin_controller.py"
spec = importlib.util.spec_from_file_location("d0t03_admin_controller_transaction", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class D0T03TransactionTests(unittest.TestCase):
    def test_main_never_closes_when_main_moves_after_probe_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = root / "packet.json"
            signature = root / "packet.sig"
            public_key = root / "probe.pub"
            output = root / "evidence.json"
            packet.write_text("{}\n", encoding="utf-8")
            signature.write_bytes(b"signature")
            public_key.write_bytes(b"public-key")
            args = SimpleNamespace(
                apply=False,
                output=output,
                probe_evidence=packet,
                probe_signature=signature,
                probe_public_key=public_key,
                expected_probe_public_key_sha256="b" * 64,
                expected_probe_attestor_id=999999,
                expected_probe_attestor_login="independent-attestor",
                check_config=False,
            )
            with (
                mock.patch.object(module, "parse_args", return_value=args),
                mock.patch.object(
                    module,
                    "readback",
                    return_value={"main_sha": "a" * 40, "verification_errors": []},
                ),
                mock.patch.object(
                    module, "verify_detached_signature", return_value="b" * 64
                ),
                mock.patch.object(module, "strict_json", return_value={}),
                mock.patch.object(module, "validate_probe_evidence", return_value=[]),
                mock.patch.object(module, "read_current_main_sha", return_value="c" * 40),
            ):
                self.assertEqual(module.main(), 1)
            evidence = module.strict_json(output.read_text(encoding="utf-8"))
            self.assertFalse(evidence["all_gaps_closed"])
            self.assertTrue(
                any(
                    "advanced during signed-probe" in error
                    for error in evidence["probe_verification_errors"]
                )
            )


if __name__ == "__main__":
    unittest.main()
