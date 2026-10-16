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
    def invoke(self, args=("build",), *, drift=False, allowed=True, mutate=False,
               adapter=None, missing_compiler=False):
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
            fake.write_text('#!' + sys.executable + '\nimport sys,json,os\nfrom pathlib import Path\n'
                            'root=Path(' + repr(str(workspace)) + ')\n'
                            'args=sys.argv[1:]\n'
                            'with (root/"calls.jsonl").open("a") as log:\n'
                            ' log.write(json.dumps({"args":args,"env":{key:os.environ.get(key) '
                            'for key in ("RUSTC","RUSTDOC","RUSTUP_TOOLCHAIN","RUSTUP_AUTO_INSTALL")}})+"\\n")\n'
                            'if args==["-Vv"]: print("cargo fixed fixture")\n'
                            'elif args[0]=="locate-project": print(root/"Cargo.toml")\n'
                            'elif args[0]=="metadata" and "--locked" not in args:\n'
                            ' (root/"Cargo.lock").write_text(' + repr(normalized) + ')\n'
                            ' print("{}")\n'
                            'else:\n'
                            ' (root/"actual.json").write_text(json.dumps(args))\n'
                            + (' (root/"Cargo.lock").write_text("version=4\\n")\n' if mutate else ' pass\n'))
            fake.chmod(0o755)
            for name in ("rustc", "rustdoc"):
                executable = root / name
                executable.write_text('#!' + sys.executable + '\nprint("' + name + ' fixed fixture")\n')
                executable.chmod(0o755)
            if missing_compiler:
                (root / "rustc").unlink()
            output = root / "output"
            output.mkdir()
            env = os.environ.copy()
            env.update(A01_REAL_CARGO=str(fake), A01_OSDK_CASE_OUTPUT=str(output),
                       OSDK_CARGO_LOCK=str(SEED),
                       RUSTC="/inherited/wrong-rustc", RUSTDOC="/inherited/wrong-rustdoc",
                       RUSTUP_TOOLCHAIN="unqualified-nightly", RUSTUP_AUTO_INSTALL="1",
                       A01_OSDK_ALLOWED_ROOTS=json.dumps([str(workspace if allowed else root / "other")]))
            result = subprocess.run([sys.executable, "-I", str(adapter or HERE / "cargo.py"), *args],
                                    cwd=workspace, env=env, capture_output=True, text=True)
            actual = workspace / "actual.json"
            calls = workspace / "calls.jsonl"
            return {"status": result.returncode,
                    "actual": json.loads(actual.read_text()) if actual.exists() else None,
                    "calls": [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else [],
                    "stderr": result.stderr,
                    "fixed_compilers": [str(root / name) for name in ("rustc", "rustdoc")],
                    "reports": [json.loads(path.read_text()) for path in sorted((output / "cargo").glob("request-*.json"))]}

    def test_real_adapter_forces_locked_offline_after_verified_normalization(self):
        result = self.invoke()
        self.assertEqual(result["status"], 0, result["stderr"])
        self.assertIn("--locked", result["actual"])
        self.assertIn("--offline", result["actual"])

    def test_new_external_identity_prevents_actual_build(self):
        result = self.invoke(drift=True)
        self.assertNotEqual(result["status"], 0)
        self.assertIsNone(result["actual"])

    def test_path_outside_generated_roots_is_rejected(self):
        result = self.invoke(allowed=False)
        self.assertNotEqual(result["status"], 0)
        self.assertIsNone(result["actual"])

    def test_lock_mutation_by_actual_command_is_rejected(self):
        result = self.invoke(mutate=True)
        self.assertNotEqual(result["status"], 0)
        self.assertIsNotNone(result["actual"])

    def test_value_bearing_display_options_do_not_bypass_lock_validation(self):
        for options in (("--color", "always"), ("--color=never",), ("-vv", "--color", "auto")):
            with self.subTest(options=options):
                result = self.invoke((*options, "build"), drift=True)
                self.assertNotEqual(result["status"], 0)
                self.assertIsNone(result["actual"])
                self.assertTrue(result["reports"])

    def test_dependency_commands_and_builtin_aliases_all_use_locked_path(self):
        for command, canonical in (("b", "build"), ("c", "check"), ("t", "test"),
                                   ("r", "run"), ("d", "doc"), ("bench", "bench"),
                                   ("rustc", "rustc"), ("fetch", "fetch"), ("tree", "tree")):
            with self.subTest(command=command):
                result = self.invoke((command,))
                self.assertEqual(result["status"], 0, result["stderr"])
                self.assertEqual(result["actual"], ["--locked", "--offline", canonical])
                self.assertEqual(result["reports"][0]["command"], canonical)

    def test_program_arguments_cannot_impersonate_cargo_lock_flags(self):
        result = self.invoke(("r", "--", "--locked", "--offline"))
        self.assertEqual(result["status"], 0, result["stderr"])
        self.assertEqual(result["actual"], ["--locked", "--offline", "run", "--", "--locked", "--offline"])

    def test_existing_cargo_lock_flags_are_not_duplicated(self):
        result = self.invoke(("--offline", "build", "--locked"))
        self.assertEqual(result["status"], 0, result["stderr"])
        self.assertEqual(result["actual"].count("--offline"), 1)
        self.assertEqual(result["actual"].count("--locked"), 1)

    def test_fixed_toolchain_selector_is_consumed_and_every_subprocess_is_pinned(self):
        result = self.invoke(("+nightly-2026-07-21", "--color", "never", "b"))
        self.assertEqual(result["status"], 0, result["stderr"])
        self.assertTrue(result["calls"])
        for call in result["calls"]:
            self.assertNotIn("+nightly-2026-07-21", call["args"])
            self.assertEqual(call["env"], {"RUSTC": result["fixed_compilers"][0],
                                           "RUSTDOC": result["fixed_compilers"][1],
                                           "RUSTUP_TOOLCHAIN": "nightly-2026-07-21",
                                           "RUSTUP_AUTO_INSTALL": "0"})

    def test_unknown_commands_toolchains_and_redirections_never_execute_cargo(self):
        requests = (("+nightly", "build"), ("+stable", "b"), ("external-command",), ("clippy",),
                    ("--color", "always", "custom-alias"), ("help", "external-command"),
                    ("--config", 'alias.x="!arbitrary"', "x"), ("--config=net.offline=false", "b"),
                    ("b", "--config", "extra.toml"), ("-C", "elsewhere", "build"),
                    ("build", "--lockfile-path=other.lock"), ("-Zscript", "other.rs"),
                    ("build", "-Z", "script"),
                    ("--unknown", "build"), ("--color", "build"))
        for args in requests:
            with self.subTest(args=args):
                result = self.invoke(args)
                self.assertNotEqual(result["status"], 0)
                self.assertEqual(result["calls"], [])
                self.assertIsNone(result["actual"])

    def test_missing_fixed_compiler_never_falls_back_to_inherited_path(self):
        result = self.invoke(missing_compiler=True)
        self.assertNotEqual(result["status"], 0)
        self.assertEqual(result["calls"], [])

    def test_non_resolving_cargo_queries_and_new_remain_available(self):
        for args in (("--version",), ("--color", "never", "--list"), ("help", "build"),
                     ("locate-project", "--workspace"), ("new", "new-project", "--lib")):
            with self.subTest(args=args):
                result = self.invoke(args)
                self.assertEqual(result["status"], 0, result["stderr"])
                self.assertEqual(result["reports"], [])

    def test_metadata_no_deps_preserves_the_template_manifest_query(self):
        result = self.invoke(("--color", "never", "metadata", "--no-deps", "--format-version", "1"))
        self.assertEqual(result["status"], 0, result["stderr"])
        self.assertTrue(result["reports"][0]["metadata_no_deps_only"])
        self.assertIsNone(result["reports"][0]["normalization_exit"])
        self.assertIn("--locked", result["actual"])
        self.assertIn("--offline", result["actual"])


if __name__ == "__main__":
    unittest.main()
