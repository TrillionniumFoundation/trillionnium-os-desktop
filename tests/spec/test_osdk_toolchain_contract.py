"""Guard the pinned nightly used by the generated OSDK kernel build."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
BUILD_RS = ROOT / "kernel/asterinas/osdk/src/commands/build/mod.rs"
KERNEL_SH = ROOT / "support/build/kernel.sh"


class OSDKToolchainContract(unittest.TestCase):
    def test_kernel_build_inherits_runner_toolchain(self):
        source = BUILD_RS.read_text()
        self.assertIn("let mut command = cargo();", source)
        self.assertIn("command.args(COMMON_CARGO_ARGS);", source)
        self.assertNotIn(
            'env_remove("RUSTUP_TOOLCHAIN")',
            source,
            "the generated base-crate workspace must inherit the pinned nightly",
        )

    def test_kernel_runner_exports_pinned_nightly(self):
        script = KERNEL_SH.read_text()
        self.assertIn(
            "export RUSTUP_TOOLCHAIN=nightly-2026-07-21",
            script,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
