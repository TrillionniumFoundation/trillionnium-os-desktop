#!/usr/bin/env python3
"""Exercise the actual trusted-image freezer and profile-selection boundary."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
FREEZER = ROOT / "support/build/prepare-trusted-image.py"


class TrustedDaemonProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        # This freezer checks only the obvious ELF header. The complete real
        # ELF gate and kernel loader are deliberately not claimed by this test.
        self.bytes = bytearray(64)
        self.bytes[:7] = b"\x7fELF\x02\x01\x01"
        self.bytes[16:20] = b"\x02\x00\x3e\x00"
        self.source = self.directory / "entry"
        self.source.write_bytes(self.bytes)

    def freeze(self, profile, suffix):
        output = self.directory / (suffix + ".elf")
        manifest = self.directory / (suffix + ".json")
        result = subprocess.run([sys.executable, "-I", "-B", str(FREEZER), "--input", str(self.source),
                                 "--output", str(output), "--manifest", str(manifest), "--profile", profile],
                                capture_output=True, text=True, timeout=10, check=False)
        return result, output, manifest

    def test_old_profiles_keep_original_manifest_versions_and_slots(self):
        for profile, schema, operations in (
                ("g1c-trusted-observe", "hepta-g1c-trusted-initial-v1", 6),
                ("g1d-trusted-control", "hepta-g1d-trusted-initial-v1", 62)):
            with self.subTest(profile=profile):
                result, output, manifest = self.freeze(profile, profile)
                self.assertEqual(result.returncode, 0, result.stderr)
                value = json.loads(manifest.read_text())
                self.assertEqual(value["schema"], schema)
                self.assertEqual(value["supported_ops"], operations)
                self.assertNotIn("manager_history_ack", value)
                self.assertNotIn("root_role", value)
                self.assertEqual(output.read_bytes(), self.bytes)
                self.assertEqual(output.stat().st_mode & 0o777, 0o444)
                if profile == "g1d-trusted-control":
                    self.assertEqual(value["roles"], ["manager", "workload", "recovery"])
                    self.assertEqual((value["bootstrap_version"], value["bootstrap_bytes"]), (2, 192))
                    self.assertNotIn("slot", value)
                else:
                    self.assertEqual((value["slot"], value["generation"]), (1, 1))

    def test_g2_freezes_same_bytes_and_explicitly_does_not_attest_durability(self):
        result, output, manifest = self.freeze("g2-trusted-daemon", "g2")
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(manifest.read_text())
        self.assertEqual(value["schema"], "hepta-g2-trusted-initial-v1")
        self.assertEqual(value["roles"], ["root", "manager", "workload", "recovery"])
        self.assertEqual((value["bootstrap_version"], value["bootstrap_bytes"], value["root_pid_offset"]), (3, 200, 192))
        self.assertEqual((value["workload_uid"], value["workload_gid"]), (60002, 60002))
        self.assertTrue(value["manager_history_ack"])
        self.assertFalse(value["original_writer_durability_verified"])
        self.assertFalse(value["g2_complete"])
        self.assertEqual(value["sha256"], hashlib.sha256(self.bytes).hexdigest())
        self.assertEqual(output.read_bytes(), self.bytes)

    def test_g2_does_not_relax_static_or_file_size_rejection(self):
        self.bytes[16:18] = b"\x03\x00"
        self.source.write_bytes(self.bytes)
        result, output, manifest = self.freeze("g2-trusted-daemon", "pie")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ET_EXEC", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(manifest.exists())
        self.source.write_bytes(b"\0" * (8 * 1024 * 1024 + 1))
        result, output, manifest = self.freeze("g2-trusted-daemon", "large")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("8 MiB", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(manifest.exists())

    def test_mixed_profile_flags_fail_before_any_build(self):
        for index, flags in enumerate(((1, 0, 1), (0, 1, 1), (1, 1, 0), (0, 0, 2))):
            with self.subTest(flags=flags):
                env = {**os.environ, "A01_RUN_DIR": str(self.directory / ("run-" + str(index))),
                       "HEPTA_G1C_TRUSTED_OBSERVE": str(flags[0]),
                       "HEPTA_G1D_TRUSTED_CONTROL": str(flags[1]),
                       "HEPTA_G2_TRUSTED_DAEMON": str(flags[2])}
                result = subprocess.run(["/bin/bash", str(ROOT / "support/build/kernel.sh"), "kernel"],
                                        env=env, capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("select at most one", result.stderr)
                self.assertFalse((self.directory / ("run-" + str(index)) / "command.sh").exists())


if __name__ == "__main__":
    unittest.main()
