#!/usr/bin/env python3
"""The candidate runner must stop if any build step changes its bound inputs."""
import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

RUNNER = Path(__file__).resolve().parents[2] / "support/ui/verify_native_sdk_candidate.py"


class CandidateInputDrift(unittest.TestCase):
    def test_real_cargo_external_plugin_receives_candidate_config(self):
        cargo = shutil.which("cargo")
        if cargo is None:
            self.skipTest("requires the project's real Rust 1.96 Cargo installation")
        # The actual Cargo frontend launches a harmless temporary external
        # plugin. This exercises its argument forwarding, without compiling a
        # Rust crate or substituting the compiler/production Clippy binary.
        with tempfile.TemporaryDirectory(prefix="sdk-plugin-forwarding-") as folder:
            root = Path(folder)
            config = root / "candidate.toml"
            config.write_text("# exact candidate config path fixture\n")
            plugin = root / "cargo-candidate-config-fixture"
            plugin.write_text(f"#!{sys.executable}\nimport json,sys\nprint(json.dumps(sys.argv))\n")
            plugin.chmod(0o700)
            sys.path.insert(0, str(RUNNER.parent))
            try:
                spec = importlib.util.spec_from_file_location("sdk_build_runner", RUNNER)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                args = SimpleNamespace(cargo=cargo, sdk_cargo_config=config, source=root, offline=True,
                                       profile="release", target_dir=root / "target")
                generated = dict(module.cargo_commands(args, "1.96.0"))["clippy"]
            finally:
                sys.path.pop(0)
            generated[generated.index("clippy")] = "candidate-config-fixture"
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"])
            observed = json.loads(subprocess.check_output(generated, cwd=root, env=env, text=True, timeout=30))
            self.assertEqual(observed[observed.index("--config") + 1], str(config))
            # Reproduce the old historical invocation, on the same real Cargo.
            # The outer --config is consumed; the plugin does not receive it.
            old = [cargo, "+1.96.0", "--config", str(config), "candidate-config-fixture", "--locked"]
            missing = json.loads(subprocess.check_output(old, cwd=root, env=env, text=True, timeout=30))
            self.assertNotIn("--config", missing)

    def test_real_child_mutating_lock_or_config_cannot_reach_test_clippy_or_build(self):
        for changed in ("lock", "config"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory(prefix="sdk-input-drift-") as folder:
                root = Path(folder)
                desktop, hepta, sdk = (root / name for name in ("desktop", "hepta", "sdk"))
                for checkout in (desktop, hepta):
                    checkout.mkdir()
                    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
                    (checkout / "tracked").write_text("original source\n")
                ui = desktop / "ui"
                ui.mkdir()
                (ui / "Cargo.toml").write_text("[workspace]\nmembers = []\n")
                (ui / "Cargo.lock").write_text("# committed candidate lock\nversion = 4\n")
                (ui / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.96.0"\n')
                for checkout in (desktop, hepta):
                    subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
                    subprocess.run(["git", "-C", str(checkout), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                                    "commit", "-qm", "fixed source"], check=True)
                sdk.mkdir()
                original, config, cargo = (root / name for name in ("original.json", "sdk.toml", "cargo-fixture"))
                original.write_text("{}\n")
                config.write_text("# original all-crate config\n")
                selected = ui / "Cargo.lock" if changed == "lock" else config
                cargo.write_text("#!/usr/bin/env python3\nimport pathlib,sys\n"
                                 "if '--version' in sys.argv: print('cargo fixture'); sys.exit(0)\n"
                                 f"pathlib.Path({str(root / 'invoked.json')!r}).write_text(__import__('json').dumps(sys.argv))\n"
                                 f"pathlib.Path({str(selected)!r}).write_text('changed by child\\n')\n"
                                 "print('{}')\n")
                cargo.chmod(0o700)
                output = root / "evidence"
                result = subprocess.run([sys.executable, "-B", str(RUNNER), "--source", str(desktop),
                                         "--hepta-root", str(hepta), "--prepared-sdk", str(sdk), "--sdk-cargo-config", str(config),
                                         "--original-metadata", str(original), "--target-dir", str(root / "target"),
                                         "--output", str(output), "--cargo", str(cargo)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 1, result.stderr)
                receipt = json.loads((output / "receipt.json").read_text())
                self.assertIn("inputs changed", receipt["error"])
                self.assertFalse(receipt["passed"])
                self.assertFalse(receipt["compiled"])
                self.assertEqual(receipt["status"], "failed")
                self.assertEqual(receipt["exit_code"], result.returncode)
                self.assertEqual(receipt["binaries"], {})
                self.assertEqual([step["name"] for step in receipt["steps"]], ["metadata"])
                invoked = json.loads((root / "invoked.json").read_text())
                self.assertIn("--locked", invoked)
                self.assertEqual(invoked[invoked.index("--config") + 1], str(config))
                self.assertEqual(selected.read_text(), "changed by child\n")  # Keep the failure available for review.


if __name__ == "__main__":
    unittest.main()
