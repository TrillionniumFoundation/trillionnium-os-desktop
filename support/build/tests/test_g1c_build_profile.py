#!/usr/bin/env python3
"""Validate the actual profile input freezer and make overlay, without Rust/QEMU."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BUILD = Path(__file__).resolve().parents[1]


def elf_header(kind=2):
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    header[16:20] = bytes((kind, 0, 62, 0))
    return bytes(header)


class G1cBuildProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="g1c-build-input-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "reviewed.elf"
        self.output = self.root / "embedded.elf"
        self.manifest = self.root / "manifest.json"

    def freeze(self):
        return subprocess.run(
            [sys.executable, "-I", str(BUILD / "prepare-trusted-image.py"),
             "--input", str(self.source), "--output", str(self.output),
             "--manifest", str(self.manifest)],
            capture_output=True, text=True, timeout=10,
        )

    def test_profile_is_forwarded_after_the_overlay_replaces_build_args(self):
        for enabled in (0, 1):
            result = subprocess.run(
                ["make", "--no-print-directory", "-f", str(BUILD / "minimal.mk"),
                 "CARGO_OSDK=fixture-osdk", f"HEPTA_G1C_TRUSTED_OBSERVE={enabled}",
                 "--eval=print-g1c-flags:;@printf '%s\\n' '$(CARGO_OSDK_BUILD_ARGS)'",
                 "print-g1c-flags"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual("--features=g1c-trusted-observe" in result.stdout, bool(enabled))
            self.assertIn("--boot-method=vmm-direct", result.stdout)

    def test_reviewed_input_is_frozen_and_bound_to_its_manifest(self):
        original = elf_header() + b"reviewed build input"
        self.source.write_bytes(original)
        result = self.freeze()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.source.write_bytes(elf_header() + b"later source mutation")
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o444)
        manifest = json.loads(self.manifest.read_text())
        self.assertEqual(manifest["sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(manifest["bytes"], len(original))
        self.assertEqual(manifest["embedded_input"], str(self.output))
        self.assertEqual((manifest["supported_ops"], manifest["features"]), (6, 0))
        self.assertEqual(manifest["lease_ns"], 300_000_000_000)

    def test_script_and_pie_are_rejected_before_embedding(self):
        for content in (b"#!/bin/sh\nexit 0\n", elf_header(kind=3)):
            self.source.write_bytes(content)
            self.assertNotEqual(self.freeze().returncode, 0)
            self.assertFalse(self.output.exists())
            self.assertFalse(self.manifest.exists())

    def test_existing_embedded_input_is_never_replaced(self):
        self.source.write_bytes(elf_header())
        self.output.write_bytes(b"previous evidence")
        self.assertNotEqual(self.freeze().returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"previous evidence")
        self.assertFalse(self.manifest.exists())

    def test_input_read_is_bounded(self):
        self.source.write_bytes(elf_header() + bytes(8 * 1024 * 1024))
        self.assertNotEqual(self.freeze().returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())


if __name__ == "__main__":
    unittest.main()
