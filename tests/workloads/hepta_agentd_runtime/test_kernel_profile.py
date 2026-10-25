"""Actual command decoding regressions for the ordinary/trusted boundary."""
import unittest

from kernel_profile import require_ordinary_command


class OrdinaryProfileTests(unittest.TestCase):
    def test_actual_ordinary_command_has_no_trusted_role(self):
        command = "make -C /source/kernel/asterinas -f Makefile -f /source/support/build/minimal.mk kernel CARGO_OSDK=/cache/bin/cargo-osdk TARGET_ARCH=x86_64 SMP=1 MEM=512M ENABLE_KVM=0 BOOT_PROTOCOL=multiboot INITRAMFS=on AUTO_TEST=none\n"
        self.assertEqual(require_ordinary_command(command)[0], "make")

    def test_each_trusted_flag_and_feature_is_refused_independently(self):
        for argument in (
            "HEPTA_TRUSTED_INITIAL_ELF=/frozen/owner.elf",
            "HEPTA_G1C_TRUSTED_OBSERVE=1", "HEPTA_G1D_TRUSTED_CONTROL=1",
            "HEPTA_G2_TRUSTED_DAEMON=1", "FEATURES=g1c-trusted-observe",
            "FEATURES=g1d-trusted-control", "FEATURES=g2-trusted-daemon",
            "--features=g2-trusted-daemon", "HEPTA_G2_TRUSTED_DAEMON=0",
        ):
            with self.subTest(argument=argument), self.assertRaisesRegex(ValueError, "trusted role"):
                require_ordinary_command("make kernel " + argument)

    def test_shell_quoting_cannot_hide_g2_profile(self):
        for command in (
            "make kernel 'FEATURES=g2-trusted-daemon'",
            'make kernel FEATURES="g2-trusted-daemon"',
            r"make kernel FEATURES=g2\-trusted\-daemon",
            "make kernel HEPTA_G2_TRUSTED_''DAEMON=1",
        ):
            with self.subTest(command=command), self.assertRaisesRegex(ValueError, "trusted role"):
                require_ordinary_command(command)

    def test_empty_malformed_and_unbounded_transcripts_fail_closed(self):
        for command in ("", "  \n", "make kernel '", "x" * (64 * 1024 + 1), None):
            with self.subTest(command=str(command)[:40]), self.assertRaises(ValueError):
                require_ordinary_command(command)


if __name__ == "__main__":
    unittest.main()
