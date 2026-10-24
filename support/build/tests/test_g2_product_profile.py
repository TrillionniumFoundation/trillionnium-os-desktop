"""Run GNU make's actual upstream/overlay expansion, without a kernel build.

This tests the command handed to OSDK. The kernel shell's FEATURES assignment
alone cannot detect an overlay that has discarded CARGO_OSDK_COMMON_ARGS.
"""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = ROOT / "kernel/asterinas"
OVERLAY = ROOT / "support/build/minimal.mk"
SELECTORS = ("HEPTA_G1C_TRUSTED_OBSERVE", "HEPTA_G1D_TRUSTED_CONTROL", "HEPTA_G2_TRUSTED_DAEMON")
FEATURES = ("g1c-trusted-observe", "g1d-trusted-control", "g2-trusted-daemon")


class ProductProfileForwardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.make = shutil.which("make")
        self.assertIsNotNone(self.make, "the original GNU make command is required")
        # This file merely satisfies a make prerequisite in a dry-run. No tool,
        # ELF, initramfs or source-qualified build is created or executed here.
        self.osdk_prerequisite = self.directory / "not-executed-osdk"
        self.osdk_prerequisite.write_bytes(b"dry-run prerequisite only\n")

    def dry_run(self, flags, feature=""):
        argv = [self.make, "--no-print-directory", "--dry-run", "-f", str(UPSTREAM / "Makefile"),
                "-f", str(OVERLAY), "kernel", "CARGO_OSDK=" + str(self.osdk_prerequisite),
                "OSDK_SRC_FILES=", "A01_INITRAMFS=" + str(self.directory / "unused-initramfs"),
                "A01_QEMU_WRAPPER=" + str(ROOT / "support/build/record-qemu.py"),
                "TARGET_ARCH=x86_64", "SMP=1", "MEM=512M", "ENABLE_KVM=0", "BOOT_PROTOCOL=multiboot",
                "INITRAMFS=on", "AUTO_TEST=none", "FEATURES=" + feature]
        argv.extend(name + "=" + str(value) for name, value in zip(SELECTORS, flags))
        return subprocess.run(argv, cwd=UPSTREAM,
                              env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C", "VDSO_LIBRARY_DIR": str(self.directory)},
                              capture_output=True, text=True, timeout=10, check=False)

    def command(self, flags, feature=""):
        result = self.dry_run(flags, feature)
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = [shlex.split(line) for line in result.stdout.splitlines()
                    if line.startswith("cd kernel && cargo osdk build ")]
        self.assertEqual(len(commands), 1, result.stdout)
        command = commands[0]
        self.assertEqual(command[:6], ["cd", "kernel", "&&", "cargo", "osdk", "build"])
        self.assertIn("--release", command)
        self.assertIn("--boot-method=vmm-direct", command)
        self.assertIn("--grub-boot-protocol=multiboot", command)
        self.assertNotIn("--no-default-features", command)
        return command

    def test_ordinary_overlay_does_not_enable_a_trusted_profile(self):
        command = self.command((0, 0, 0))
        self.assertFalse(any(value.startswith("--features") for value in command))

    def test_existing_g1_profiles_keep_their_exact_actual_osdk_feature(self):
        for index in (0, 1):
            flags = [0, 0, 0]
            flags[index] = 1
            with self.subTest(profile=FEATURES[index]):
                command = self.command(flags, FEATURES[index])
                self.assertEqual([value for value in command if value.startswith("--features")],
                                 ["--features=" + FEATURES[index]])

    def test_g2_reaches_actual_osdk_argv_after_common_arguments_are_overridden(self):
        command = self.command((0, 0, 1), "g2-trusted-daemon")
        self.assertEqual([value for value in command if value.startswith("--features")],
                         ["--features=g2-trusted-daemon"])

    def test_mixed_and_invalid_direct_make_selectors_fail_before_osdk(self):
        for flags in ((1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1), (0, 0, 2), (-1, 0, 0)):
            with self.subTest(flags=flags):
                result = self.dry_run(flags)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("trusted profile flags" if any(value not in (0, 1) for value in flags)
                              else "select at most one", result.stderr)
                self.assertNotIn("cargo osdk build", result.stdout)


if __name__ == "__main__":
    unittest.main()
