"""Reuse the original inert oracle records; no native benchmark is executed."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import native_observation as adapter

ORIGINAL_TEST = adapter.ORACLE_PATH.parent / "test_native_owner_evidence.py"
# That existing fixture explicitly imports its sibling oracle. Both remain the
# original modules; do not duplicate the native owner or its expected protocol.
sys.modules.setdefault("native_owner_evidence", adapter.oracle)
spec = importlib.util.spec_from_file_location("original_inert_native_owner_records", ORIGINAL_TEST)
inert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inert)


def save(path, value):
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def fixture(root, mutate=False):
    name = adapter.oracle.SCENARIOS[0]
    directory = root / name
    directory.mkdir()
    raw = inert.InertRecords(name).raw()
    observed = adapter.oracle.evaluate(raw, 33, False, False, name, inert.NONCE, inert.ELF)
    if mutate:
        raw = raw.replace(b'"event":"complete"', b'"event":"unknown-complete"')
    serial_sha = hashlib.sha256(raw).hexdigest()
    (directory / "serial.log").write_bytes(raw)
    qemu_sha = save(directory / "qemu.json", {"raw_exit_code": 33, "timed_out": False,
                    "serial_excessive": False, "serial_sha256": serial_sha, "serial_bytes": len(raw)})
    case = {**observed, "raw_serial_sha256": serial_sha, "actual_qemu_record_sha256": qemu_sha}
    save(directory / "result.json", case)
    sources = {name: {"head": digit * 40, "tree": digit * 40} for name, digit in (("desktop", "1"), ("hepta", "2"))}
    receipt = {"schema": "hepta.native-original-owner-result.v1", "stage": "complete", "passed": True,
               "original_native_owner_cycle_verified": True, "source_inputs_unchanged": True,
               "sources": sources, "harness_source": sources["desktop"], "g2_complete": False,
               "production_ready": False, "scenarios": {name: case}, "original_elf_shape": inert.ELF}
    return save(root / "result.json", receipt), sources


class NativeObservationTests(unittest.TestCase):
    def test_original_oracle_replay_stays_a_prerequisite_not_a_policy_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt, sources = fixture(root)
            result = adapter.import_cycle(root, receipt, sources)
            self.assertTrue(result["scenarios"][adapter.oracle.SCENARIOS[0]]["original_oracle_replayed"])
            self.assertFalse(result["comparison_complete"])
            self.assertFalse(result["ranking_allowed"])
            self.assertIsNone(result["policy_arm"])
            self.assertIsNone(result["whole_arm_costs"])
            self.assertIsNone(result["energy"])

    def test_rehashing_a_passed_receipt_cannot_hide_an_invalid_raw_native_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt, sources = fixture(root, mutate=True)
            with self.assertRaises(ValueError):
                adapter.import_cycle(root, receipt, sources)

    def test_original_native_source_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt, sources = fixture(root)
            sources["hepta"]["head"] = "3" * 40
            with self.assertRaisesRegex(ValueError, "another hepta source"):
                adapter.import_cycle(root, receipt, sources)


if __name__ == "__main__":
    unittest.main()
