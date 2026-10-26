#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Reject falsified device/retained-disk evidence; fixtures never qualify a VM."""

import copy
import json
import unittest

import native_devices as gate


NONCE = "a4" * 32


def ready(mode="write"):
    return {"nonce": NONCE, "event": "ready", "mode": mode,
            "input_path": "/dev/input/event2", "input_name": "QEMU Virtio Keyboard",
            "input_major": 13, "input_minor": 66, "input_bus": 6, "input_vendor": 0,
            "input_product": 0, "width": 1024, "height": 768, "bpp": 32, "pitch": 4096,
            "fb_bytes": 3145728, "storage_device": 65280, "storage_inode": 12,
            "storage_bytes": 4096, "storage_hash": gate.original_hash(NONCE), "system": "Linux"}


def complete(mode="write"):
    return {"nonce": NONCE, "event": "complete", "mode": mode,
            "key_code": 30, "presses": 1, "releases": 1}


def serial(*rows):
    return b"".join(gate.PREFIX + json.dumps(row).encode() + b"\n" for row in rows)


class EvidenceTests(unittest.TestCase):
    def test_loader_adaptation_changes_only_the_reviewed_osdk_machine_header(self):
        original = b"\x7fELF\x02\x01\x01" + bytes(9) + b"\x02\x00\x03\x00" + bytes(range(256))
        self.assertEqual(gate.grub_loader_image(original),
                         original[:18] + b"\x3e\x00" + original[20:])
        for altered in (original[:30], original[:18] + b"\x3e\x00" + original[20:],
                        b"not-ELF" + original[7:], original[:4] + b"\x01" + original[5:]):
            with self.subTest(altered=altered[:20]), self.assertRaises(ValueError):
                gate.grub_loader_image(altered)

    def test_exact_two_ordered_device_records_are_accepted(self):
        rows = [ready(), complete()]
        self.assertEqual(gate.records(serial(*rows), NONCE, "write", complete=True), rows)

    def test_missing_duplicated_reordered_or_replayed_key_records_fail(self):
        for rows in ([ready()], [ready(), complete(), complete()],
                     [complete(), ready()], [ready(), {**complete(), "releases": 0}],
                     [ready(), {**complete(), "presses": 2}],
                     [ready(), {**complete(), "key_code": 31}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                gate.records(serial(*rows), NONCE, "write", complete=True)

    def test_wrong_owner_mode_nonce_or_device_does_not_pass(self):
        changes = {"nonce": "b5" * 32, "mode": "read", "input_name": "unknown keyboard",
                   "input_path": "/dev/tty0", "input_bus": 3, "input_major": 4,
                   "width": 800, "pitch": 1, "fb_bytes": 1, "storage_inode": 0,
                   "storage_hash": "0" * 16, "storage_bytes": 0, "input_minor": True}
        for key, value in changes.items():
            row = ready()
            row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.records(serial(row, complete()), NONCE, "write", complete=True)

    def test_guest_failure_and_truncated_or_duplicate_json_fields_fail(self):
        for data in (b"TRILL_NATIVE_DRIVER_FAIL storage\n" + serial(ready(), complete()),
                     b"Kernel panic" + serial(ready(), complete()),
                     serial(ready()) + gate.PREFIX + b'{"nonce":',
                     serial(ready()).replace(b'"width": 1024', b'"width": 1024, "width": 1024')):
            with self.subTest(data=data[:100]), self.assertRaises(ValueError):
                gate.records(data, NONCE, "write", complete=True)

    def test_complete_pixel_frame_is_required(self):
        row = b"".join(bytes(color) * 256 for color in gate.COLORS)
        pixels = b"P6\n1024 768\n255\n" + row * 768
        result = gate.framebuffer_pixels(pixels)
        self.assertEqual(result["pixels_checked"], 1024 * 768)
        for altered in (pixels[:-1], pixels + b"x", pixels[:30] + bytes([pixels[30] ^ 1]) + pixels[31:],
                        pixels.replace(b"1024 768", b"1024 767", 1)):
            with self.subTest(size=len(altered)), self.assertRaises(ValueError):
                gate.framebuffer_pixels(altered)

    def test_a_recreated_inode_or_changed_payload_cannot_pass_recovery(self):
        first, second = ready(), ready("read")
        self.assertTrue(gate.retained_boots(first, second)["original_inode_retained"])
        for key in ("storage_inode", "storage_device", "storage_bytes", "storage_hash"):
            changed = copy.deepcopy(second)
            changed[key] = "0" * 16 if key == "storage_hash" else changed[key] + 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.retained_boots(first, changed)
        with self.assertRaises(ValueError):
            gate.retained_boots(second, first)


if __name__ == "__main__":
    unittest.main()
