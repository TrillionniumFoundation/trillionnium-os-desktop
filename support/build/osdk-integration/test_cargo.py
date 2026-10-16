"""Exercise the real Cargo adapter's dependency and path rejection boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SEED = HERE.parents[2] / "kernel/asterinas/Cargo.lock"


class CargoAdapterTests(unittest.TestCase):
    def invoke(self, *, drift=False, allowed=True, mutate=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "generated"
            workspace.mkdir()
            (workspace / "Cargo.toml").write_text('[package]\nname="generated"\nversion="0.0.0"\n')
            normalized = ('version = 4\n\n[[package]]\nname = "generated"\nversion = "0.0.0"\n')
            if drift:
                normalized += ('\n[[package]]\nname="unreviewed"\nversion="999.0.0"\n'
                               'source="registry+https://github.com/rust-lang/crates.io-index"\n'
                               'checksum="abcdef"\n')
            fake = root / "real-cargo"
            fake.write_text('#!' + sys.executable + '\nimport sys,json\nfrom pathlib import Path\n'
                            'root=Path(' + repr(str(workspace)) + ')\n'
                            'args=sys.argv[1:]\n'
                            'if args==["-Vv"]: print("cargo fixed fixture")\n'
                            'elif args[0]=="locate-project": print(root/"Cargo.toml")\n'
                            'elif args[0]=="metadata" and "--locked" not in args:\n'
                            ' (root/"Cargo.lock").write_text(' + repr(normalized) + ')\n'
                            ' print("{}")\n'
                            'else:\n'
                            ' (root/"actual.json").write_text(json.dumps(args))\n'
                            + (' (root/"Cargo.lock").write_text("version=4\\n")\n' if mutate else ' pass\n'))
            fake.chmod(0o755)
            rustc = root / "rustc"
            rustc.write_text('#!' + sys.executable + '\nprint("rustc fixed fixture")\n')
            rustc.chmod(0o755)
            output = root / "output"
            output.mkdir()
            env = os.environ.copy()
            env.update(A01_REAL_CARGO=str(fake), A01_OSDK_CASE_OUTPUT=str(output),
                       OSDK_CARGO_LOCK=str(SEED),
                       A01_OSDK_ALLOWED_ROOTS=json.dumps([str(workspace if allowed else root / "other")]))
            result = subprocess.run([sys.executable, "-I", str(HERE / "cargo.py"), "build"],
                                    cwd=workspace, env=env, capture_output=True, text=True)
            actual = workspace / "actual.json"
            return result.returncode, json.loads(actual.read_text()) if actual.exists() else None

    def test_real_adapter_forces_locked_offline_after_verified_normalization(self):
        status, args = self.invoke()
        self.assertEqual(status, 0)
        self.assertIn("--locked", args)
        self.assertIn("--offline", args)

    def test_new_external_identity_prevents_actual_build(self):
        status, args = self.invoke(drift=True)
        self.assertNotEqual(status, 0)
        self.assertIsNone(args)

    def test_path_outside_generated_roots_is_rejected(self):
        status, args = self.invoke(allowed=False)
        self.assertNotEqual(status, 0)
        self.assertIsNone(args)

    def test_lock_mutation_by_actual_command_is_rejected(self):
        status, args = self.invoke(mutate=True)
        self.assertNotEqual(status, 0)
        self.assertIsNotNone(args)


if __name__ == "__main__":
    unittest.main()
