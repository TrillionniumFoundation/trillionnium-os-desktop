#!/usr/bin/env python3
"""Exercise the default-off G2 freezer, strict ELF profile and real make flags."""

import importlib.util
import itertools
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


BUILD = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trusted_image", BUILD / "prepare-trusted-image.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def fixture():
    image = bytearray(8192)
    image[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHIQQ", image, 16, 2, 62, 1, 0x401000, 64)
    struct.pack_into("<HHH", image, 52, 64, 56, 2)
    for index, (flags, offset, address) in enumerate(((4, 0, 0x400000), (5, 4096, 0x401000))):
        struct.pack_into("<IIQQQQQQ", image, 64 + index * 56,
                         1, flags, offset, address, address, 4096, 4096, 4096)
    return image


class G2BuildProfileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="g2-profile-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source.elf"
        self.output = self.root / "frozen.elf"
        self.manifest = self.root / "manifest.json"

    def inspect(self, image):
        self.source.write_bytes(image)
        return profile.inspect_g2_elf(self.source)

    def freeze(self):
        return subprocess.run([sys.executable, "-I", str(BUILD / "prepare-trusted-image.py"),
            "--profile", "g2-native-agentd", "--input", str(self.source),
            "--output", str(self.output), "--manifest", str(self.manifest)],
            capture_output=True, text=True, timeout=10)

    def test_manifest_records_measurements_and_no_native_qualification(self):
        original = fixture()
        details = self.inspect(original)
        self.assertEqual(details["mapped_bytes"], 8192)
        self.assertEqual(details["load_segments"], 2)
        self.assertIsNone(details["tls"])
        result = self.freeze()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.source.write_bytes(b"changed source")
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o444)
        manifest = json.loads(self.manifest.read_text())
        self.assertEqual(manifest["schema"], "hepta-g2-trusted-initial-v1")
        self.assertEqual(manifest["elf_profile"], details)
        self.assertEqual(manifest["profile_limits"], profile.G2_LIMITS)
        self.assertEqual(manifest["qualification"], "loader-stage-not-native-qualified")
        self.assertEqual((manifest["guest_memory_mib"], manifest["max_kernel_bytes"]),
                         (3072, 256 * 1024 * 1024))
        self.assertEqual((manifest["bootstrap_version"], manifest["bootstrap_bytes"], manifest["supported_ops"]),
                         (2, 192, 62))
        self.assertEqual(manifest["roles"], ["manager", "workload", "recovery"])

    def test_no_existing_frozen_input_is_replaced(self):
        self.source.write_bytes(fixture())
        self.output.write_bytes(b"retained evidence")
        self.assertNotEqual(self.freeze().returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"retained evidence")
        self.assertFalse(self.manifest.exists())

    def test_static_layout_rejects_malformed_headers_and_loads(self):
        changes = ((16, "H", 3), (18, "H", 183), (32, "Q", (1 << 64) - 1),
                   (56, "H", 65), (54, "H", 55), (120, "I", 3), (120, "I", 2),
                   (124, "I", 7), (136, "Q", 0x400000), (128, "Q", 4097),
                   (96, "Q", 65), (160, "Q", 225 * 1024 * 1024),
                   (152, "Q", 8192), (136, "Q", (1 << 64) - 4096))
        for offset, kind, value in changes:
            with self.subTest(offset=offset, value=value):
                image = fixture()
                struct.pack_into("<" + kind, image, offset, value)
                with self.assertRaises(ValueError):
                    self.inspect(image)

    def test_tls_requires_matching_template_but_not_tbss_load_mapping(self):
        image = fixture()
        struct.pack_into("<H", image, 56, 3)
        struct.pack_into("<IIQQQQQQ", image, 176, 7, 4, 4000, 0x400FA0, 0, 64, 65536, 8)
        self.assertEqual(self.inspect(image)["tls"]["memory_bytes"], 65536)
        for offset, value in ((192, 0x402FA0), (208, 65537), (216, 65537), (224, 3), (224, 8192)):
            with self.subTest(offset=offset, value=value):
                changed = bytearray(image)
                struct.pack_into("<Q", changed, offset, value)
                with self.assertRaises(ValueError):
                    self.inspect(changed)
        struct.pack_into("<H", image, 56, 4)
        image[232:288] = image[176:232]
        with self.assertRaises(ValueError):
            self.inspect(image)

    def test_phdr_cannot_redirect_libc_static_tls_base(self):
        image = fixture()
        struct.pack_into("<H", image, 56, 3)
        struct.pack_into("<IIQQQQQQ", image, 176, 6, 4, 64, 0x400040, 0, 168, 168, 8)
        self.inspect(image)
        struct.pack_into("<Q", image, 192, 0x400048)
        with self.assertRaises(ValueError):
            self.inspect(image)

    def test_file_limit_is_checked_without_reading_sparse_large_file(self):
        with self.source.open("wb") as stream:
            stream.write(fixture())
            stream.truncate(profile.G2_LIMITS["max_file_bytes"] + 1)
        with self.assertRaises(ValueError):
            profile.inspect_g2_elf(self.source)

    def test_phdr_checks_first_mapping_when_file_ranges_overlap(self):
        image = fixture()
        struct.pack_into("<Q", image, 96, 100)
        struct.pack_into("<Q", image, 128, 0)
        struct.pack_into("<QQ", image, 152, 8192, 8192)
        with self.assertRaises(ValueError):
            self.inspect(image)
        image = fixture()
        struct.pack_into("<Q", image, 128, 0)
        struct.pack_into("<H", image, 56, 3)
        struct.pack_into("<IIQQQQQQ", image, 176, 6, 4, 64, 0x401040, 0, 168, 168, 8)
        with self.assertRaises(ValueError):
            self.inspect(image)
        struct.pack_into("<Q", image, 192, 0x400040)
        self.inspect(image)

    def test_final_reserved_user_page_is_not_admitted(self):
        image = fixture()
        address = (1 << 47) - 4096
        struct.pack_into("<Q", image, 24, address)
        struct.pack_into("<Q", image, 136, address)
        with self.assertRaises(ValueError):
            self.inspect(image)

    def test_unaligned_program_header_table_is_rejected_before_parser(self):
        image = fixture()
        image[65:177] = image[64:176]
        struct.pack_into("<Q", image, 32, 65)
        with self.assertRaisesRegex(ValueError, "PHDR table bounds"):
            self.inspect(image)

    def test_make_forwards_exactly_one_default_off_profile(self):
        for selected in itertools.product((0, 1), repeat=3):
            command = ["make", "--no-print-directory", "-f", str(BUILD / "minimal.mk"),
                       "CARGO_OSDK=fixture-osdk"]
            for name, value in zip(("HEPTA_G1C_TRUSTED_OBSERVE", "HEPTA_G1D_TRUSTED_CONTROL", "HEPTA_G2_NATIVE_AGENTD"), selected):
                command.append(f"{name}={value}")
            command += ["--eval=print-g2:;@printf '%s\\n' '$(CARGO_OSDK_BUILD_ARGS)'", "print-g2"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            if sum(selected) > 1:
                self.assertNotEqual(result.returncode, 0)
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                actual = [arg for arg in result.stdout.split() if arg.startswith("--features=")]
                expected = ["--features=" + name for name, chosen in zip(
                    ("g1c-trusted-observe", "g1d-trusted-control", "g2-native-agentd"), selected) if chosen]
                self.assertEqual(actual, expected)

    def test_wrapper_rejects_ambiguous_profiles_and_ordinary_run_before_build(self):
        for index, (observe, control, native, target) in enumerate(((0, 0, 1, "run_kernel"),
                (1, 0, 1, "kernel"), (0, 1, 1, "kernel"), (0, 0, 2, "kernel"))):
            output = self.root / f"invalid-{index}"
            env = dict(os.environ, A01_RUN_DIR=str(output), HEPTA_G1C_TRUSTED_OBSERVE=str(observe),
                       HEPTA_G1D_TRUSTED_CONTROL=str(control), HEPTA_G2_NATIVE_AGENTD=str(native))
            result = subprocess.run(["bash", str(BUILD / "kernel.sh"), target], env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(list(output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
