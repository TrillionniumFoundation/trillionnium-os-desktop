#!/usr/bin/env python3
"""Exercise compiler selection and child dispatch with real temporary programs.

These programs are controlled process-boundary fixtures, not Rust compilers or
build evidence. The original store must still be compiled and linted on the
operator host with the reviewed real toolchain.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import prepare_inputs as preparation

toolchain = preparation.toolchain


class StoreToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "hepta"
        self.manifest = self.source / "codex-rs/rust-toolchain.toml"
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text('[toolchain]\nchannel="1.96.0"\ncomponents=["clippy"]\n')
        (self.manifest.parent / "Cargo.lock").write_text("controlled source-lock fixture")
        self.review = {"userspace_toolchain": {"channel": "1.96.0", "manifest": "codex-rs/rust-toolchain.toml",
                      "sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest()}}
        self.bin = self.root / "reviewed/bin"
        self.bin.mkdir(parents=True)
        self.home = self.root / "cargo-home"
        (self.home / "bin").mkdir(parents=True)
        self.dispatch = self.root / "dispatch.jsonl"
        self.trap = self.root / "ambient-clippy-was-used"
        self.write_tools()
        self.selector = self.root / "selector"
        self.selector.mkdir()
        self.program(self.selector / "rustup", f'''
import sys
assert sys.argv[1:] == ["which", "--toolchain", "1.96.0", "cargo"]
print({str(self.bin / "cargo")!r})
''')
        self.program(self.home / "bin/cargo-clippy", f'''
from pathlib import Path
Path({str(self.trap)!r}).write_text("ambient 1.94 proxy was selected")
raise SystemExit(94)
''')
        ambient = {"PATH": str(self.selector) + ":/usr/bin:/bin", "CARGO_HOME": str(self.home),
                   "RUSTUP_TOOLCHAIN": "1.94.0", "RUSTC": "/ambient/rustc",
                   "RUSTDOC": "/ambient/rustdoc", "CARGO": "/ambient/cargo",
                   "RUSTC_WRAPPER": "/ambient/wrapper", "RUSTC_WORKSPACE_WRAPPER": "/ambient/workspace-wrapper"}
        self.environment = mock.patch.dict(os.environ, ambient)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.target = self.root / "target"
        self.out = self.root / "output"
        self.out.mkdir()

    def program(self, path, body):
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o755)

    def write_tools(self, *, linked="1.96.0", clippy="0.1.96", rustdoc="1.96.0"):
        body = f'''
import json, os, subprocess, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
rust_version = "rustc 1.96.0 (123456789 2026-05-18)"
clippy_version = "clippy {clippy} (abcdef123 2026-05-18)"
if name == "clippy-driver" and args == ["--rustc", "--version"]:
    print("rustc {linked} (123456789 2026-05-18)")
    raise SystemExit(0)
if args == ["--version"]:
    print(clippy_version if name in ("cargo-clippy", "clippy-driver") else
          ("rustdoc {rustdoc} (123456789 2026-05-18)" if name == "rustdoc" else name + " 1.96.0 (123456789 2026-05-18)"))
    raise SystemExit(0)
with Path({str(self.dispatch)!r}).open("a") as log:
    log.write(json.dumps({{"name": name, "argv": args, "channel": os.environ.get("RUSTUP_TOOLCHAIN"),
                          "cargo": os.environ.get("CARGO"), "rustc": os.environ.get("RUSTC"),
                          "rustdoc": os.environ.get("RUSTDOC"),
                          "wrapper": os.environ.get("RUSTC_WORKSPACE_WRAPPER")}}) + "\\n")
if name == "cargo" and args and args[0] == "clippy":
    # Reproduce Cargo's documented CARGO_HOME/bin precedence over PATH.
    os.execv(str(Path(os.environ["CARGO_HOME"]) / "bin/cargo-clippy"), ["cargo-clippy", *args])
if name == "cargo-clippy":
    assert args[0] == "clippy" and args[-3:] == ["--", "-D", "warnings"]
    if Path({str(self.root / 'reject-clippy')!r}).exists():
        print("controlled strict lint failure", file=sys.stderr)
        raise SystemExit(101)
    env = dict(os.environ, RUSTC_WORKSPACE_WRAPPER=str(Path(sys.argv[0]).with_name("clippy-driver")))
    raise SystemExit(subprocess.run([os.environ["CARGO"], "check", *args[1:]], env=env).returncode)
if name == "cargo" and args and args[0] == "check":
    driver = os.environ["RUSTC_WORKSPACE_WRAPPER"]
    raise SystemExit(subprocess.run([driver, os.environ["RUSTC"], "--controlled-compile"]).returncode)
if name == "cargo" and args and args[0] == "build":
    binary = Path(os.environ["CARGO_TARGET_DIR"]) / "dev-small" / {preparation.NAME!r}
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"controlled dispatch fixture; not a native Rust build")
'''
        for name in toolchain.CLIPPY_TOOLS:
            self.program(self.bin / name, body)

    def bound(self):
        return toolchain.clippy_environment(self.source, self.review, preparation.HELPER.build_environment(self.target))

    def runner(self, source, runner):
        (runner / "src").mkdir(parents=True)
        (runner / "Cargo.lock").write_text("controlled original-lock fixture")
        (runner / "rust-toolchain.toml").write_bytes(self.manifest.read_bytes())
        (runner / "src/main.rs").write_bytes((preparation.HERE / "store_probe.rs").read_bytes())
        return {}

    def execute_store_dispatch(self, environment, versions):
        report = {"commands": [], "built": False, "cargo_targets": {"cache_reused": False},
                  "dependency_artifacts": {}}
        with mock.patch.object(preparation, "prepare_runner", side_effect=self.runner), \
             mock.patch.object(preparation, "verify_lock", return_value={}), \
             mock.patch.object(preparation, "verify_source", return_value=self.review), \
             mock.patch.object(preparation.dependency_artifacts, "verify_frozen"):
            preparation.build_store(self.source, self.out, self.review, report, self.target,
                                    environment, versions, None)
        return report

    def test_actual_subprocess_chain_avoids_ambient_proxy_and_preserves_strict_lints(self):
        environment, versions = self.bound()
        # Demonstrate the failure mode independently: real process dispatch via
        # Cargo finds the trap despite the reviewed installation leading PATH.
        old = subprocess.run([str(self.bin / "cargo"), "clippy", "--", "-D", "warnings"],
                             env=environment, capture_output=True, timeout=10)
        self.assertEqual(old.returncode, 94)
        self.assertTrue(self.trap.is_file())
        self.trap.unlink()
        self.dispatch.unlink()
        report = self.execute_store_dispatch(environment, versions)
        self.assertFalse(self.trap.exists())
        calls = [json.loads(line) for line in self.dispatch.read_text().splitlines()]
        self.assertEqual([call["name"] for call in calls], ["cargo", "cargo", "cargo", "cargo-clippy", "cargo", "clippy-driver"])
        for call in calls:
            self.assertEqual(call["channel"], "1.96.0")
            for key in ("cargo", "rustc", "rustdoc"):
                self.assertEqual(call[key], str(self.bin / key))
        self.assertEqual(calls[-1]["wrapper"], str(self.bin / "clippy-driver"))
        self.assertEqual(report["commands"][-1], [str(self.bin / "cargo-clippy"), "clippy", "--locked", "--offline", "--profile", "dev-small", "--", "-D", "warnings"])
        self.assertEqual(set(versions), set(toolchain.CLIPPY_TOOLS))
        self.assertEqual(versions["clippy-driver"]["rustc_version"], versions["rustc"]["version"])

    def test_mislabelled_driver_with_old_embedded_compiler_is_rejected_before_output(self):
        self.write_tools(linked="1.94.0")
        self.out.rmdir()
        with mock.patch.object(preparation.shutil, "disk_usage", return_value=SimpleNamespace(free=16 * 1024**3)), \
             self.assertRaisesRegex(ValueError, "installed rustc differs"):
            preparation.build(SimpleNamespace(target=None), self.source, self.out, self.review, {})
        self.assertFalse(self.out.exists())
        self.assertFalse(self.dispatch.exists())

    def test_old_clippy_and_rustdoc_are_rejected_even_with_current_cargo_and_rustc(self):
        for component in ("clippy", "rustdoc"):
            with self.subTest(component=component):
                self.write_tools(**{component: "0.1.94" if component == "clippy" else "1.94.0"})
                with self.assertRaisesRegex(ValueError, "differs from reviewed Rust"):
                    self.bound()

    def test_missing_or_proxy_driver_is_rejected_before_executing_any_component(self):
        driver = self.bin / "clippy-driver"
        driver.unlink()
        with self.assertRaises(FileNotFoundError):
            self.bound()
        driver.symlink_to(self.home / "bin/cargo-clippy")
        with self.assertRaisesRegex(ValueError, "canonical executable"):
            self.bound()
        self.assertFalse(self.trap.exists())

    def test_changed_component_cannot_be_frozen_as_the_preflight_identity(self):
        _, versions = self.bound()
        with (self.bin / "clippy-driver").open("a") as stream:
            stream.write("\n# a changed driver after preflight\n")
        with self.assertRaisesRegex(ValueError, "tool executable changed: clippy-driver"):
            toolchain.verify_executables(versions)

    def test_strict_clippy_failure_remains_a_failed_build(self):
        (self.root / "reject-clippy").write_text("fail the real child process")
        self.out.rmdir()
        report = {"commands": [], "built": False, "dependency_artifacts": {}}
        with mock.patch.object(preparation.shutil, "disk_usage", return_value=SimpleNamespace(free=16 * 1024**3)), \
             mock.patch.object(preparation, "prepare_runner", side_effect=self.runner), \
             mock.patch.object(preparation, "verify_lock", return_value={}), \
             mock.patch.object(preparation.dependency_artifacts, "freeze", return_value={}), \
             self.assertRaisesRegex(preparation.HELPER.GateError, "command_failed_exit_101"):
            preparation.build(SimpleNamespace(target=None), self.source, self.out, self.review, report)
        self.assertFalse(report["built"])
        self.assertEqual(set(report["toolchains"]), set(toolchain.CLIPPY_TOOLS))
        self.assertEqual(report["toolchain_selection"]["rustup_toolchain"], "1.96.0")
        self.assertFalse((self.out / preparation.NAME).exists())
        self.assertIn("controlled strict lint failure", (self.out / "clippy.log").read_text())


if __name__ == "__main__":
    unittest.main()
