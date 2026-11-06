#!/usr/bin/env python3
"""Only owned temporary host files; never invokes inventory.main or a binary."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("inventory_under_local_test", HERE / "inventory_fixed_aapt2_candidates.py")
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class InventoryControls(unittest.TestCase):
    def setUp(self):
        self.start = len(os.listdir("/proc/self/fd"))
        self.temp = tempfile.TemporaryDirectory(prefix="pocket4-aapt2-inventory-owned-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()
        self.assertEqual(self.start, len(os.listdir("/proc/self/fd")))

    def test_real_byte_hash_owner_and_no_execution(self):
        marker = self.root / "MUST_NOT_EXIST"
        raw = ("#!/bin/sh\ntouch " + str(marker) + "\n").encode()
        path = self.root / "executable-looking-file"
        path.write_bytes(raw)
        path.chmod(0o755)
        row, unused = inventory.read_regular(str(path), inventory.MAX_CANDIDATE)
        self.assertEqual(row["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(row["stat"]["st_uid"], path.stat().st_uid)
        self.assertTrue(row["held_file_and_path_full_stat_rechecked"])
        self.assertFalse(inventory.elf_header(row)["elf"])
        self.assertFalse(marker.exists())

    def test_missing_component_report_has_no_availability_claim(self):
        row, body = inventory.read_regular(str(self.root / "missing" / "aapt2"), 64)
        self.assertEqual(row["status"], "ABSENT_AT_OBSERVATION")
        self.assertEqual(row["missing_component"], str(self.root / "missing"))
        self.assertIsNone(body)
        self.assertNotIn("sha256", row)

    def test_symlink_in_parent_is_not_followed(self):
        (self.root / "target").mkdir()
        (self.root / "target" / "aapt2").write_bytes(b"owned fixture")
        (self.root / "link").symlink_to(self.root / "target", target_is_directory=True)
        with self.assertRaises(OSError):
            inventory.read_regular(str(self.root / "link" / "aapt2"), 64)

    def test_symlink_leaf_and_hardlink_rejected(self):
        target = self.root / "target"
        target.write_bytes(b"owned fixture")
        link = self.root / "link"
        link.symlink_to(target)
        with self.assertRaises(OSError):
            inventory.read_regular(str(link), 64)
        link.unlink()
        os.link(target, link)
        with self.assertRaisesRegex(RuntimeError, "REGULAR_SINGLE_LINK"):
            inventory.read_regular(str(target), 64)

    def test_parent_path_replacement_rejected(self):
        parent = self.root / "parent"
        parent.mkdir()
        path = parent / "aapt2"
        path.write_bytes(b"held fixture")
        original = inventory.os.read
        changed = False
        def changing_read(fd, size):
            nonlocal changed
            raw = original(fd, size)
            if raw and not changed:
                changed = True
                parent.rename(self.root / "retained-parent")
                parent.mkdir()
            return raw
        with mock.patch.object(inventory.os, "read", changing_read):
            with self.assertRaisesRegex(RuntimeError, "PARENT_IDENTITY_CHANGED"):
                inventory.read_regular(str(path), 64)

    def test_size_and_pinned_hash_rejected(self):
        path = self.root / "aapt2"
        path.write_bytes(b"over-limit-file")
        with self.assertRaisesRegex(RuntimeError, "FILE_SIZE_BOUND"):
            inventory.read_regular(str(path), 1)
        with self.assertRaisesRegex(RuntimeError, "EXISTING_PIN_CHANGED"):
            inventory.read_regular(str(path), 64, expected={"sha256": "0" * 64})

    def test_elf_header_is_only_a_header_observation(self):
        raw = bytearray(64)
        raw[:7] = b"\x7fELF\x02\x01\x01"
        struct.pack_into("<HHI", raw, 16, 3, 62, 1)
        value = inventory.elf_header({"header_64_hex": raw.hex()})
        self.assertTrue(value["host_x86_64_header"])
        self.assertFalse(value["execution_performed"])
        self.assertNotIn("compatibility_verified", value)
        self.assertNotIn("provenance_verified", value)
        struct.pack_into("<H", raw, 18, 183)
        self.assertFalse(inventory.elf_header({"header_64_hex": raw.hex()})["host_x86_64_header"])


if __name__ == "__main__":
    count_before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InventoryControls))
    count_after = len(os.listdir("/proc/self/fd"))
    summary = {"schema": "pocket4-aapt2-inventory-local-controls-v1", "tests_run": result.testsRun,
               "ok": result.wasSuccessful() and count_before == count_after, "skipped": len(result.skipped),
               "process_FDs_before": count_before, "process_FDs_after": count_after,
               "only_owned_local_temporary_files": True, "candidate_executions": 0, "remote_calls": 0,
               "Main_reads": 0, "action_lock_acquired": False}
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")), flush=True)
    raise SystemExit(0 if summary["ok"] else 1)
