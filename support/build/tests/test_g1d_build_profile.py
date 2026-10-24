#!/usr/bin/env python3
"""Exercise the G1-d build input and actual make flag forwarding without Rust."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BUILD = Path(__file__).resolve().parents[1]


class G1dBuildProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="g1d-build-input-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_flags(self, observe, control, daemon=0):
        return subprocess.run(
            ["make", "--no-print-directory", "-f", str(BUILD / "minimal.mk"),
             "CARGO_OSDK=fixture-osdk", f"HEPTA_G1C_TRUSTED_OBSERVE={observe}",
             f"HEPTA_G1D_TRUSTED_CONTROL={control}",
             f"HEPTA_G2_TRUSTED_DAEMON={daemon}",
             "--eval=print-g1d-flags:;@printf '%s\\n' '$(CARGO_OSDK_BUILD_ARGS)'",
             "print-g1d-flags"],
            capture_output=True, text=True, timeout=10,
        )

    def test_only_the_selected_profile_reaches_the_osdk_argv(self):
        for observe, control, daemon, feature in (
                (0, 0, 0, None), (1, 0, 0, "g1c-trusted-observe"),
                (0, 1, 0, "g1d-trusted-control"), (0, 0, 1, "g2-trusted-daemon")):
            with self.subTest(observe=observe, control=control, daemon=daemon):
                result = self.make_flags(observe, control, daemon)
                self.assertEqual(result.returncode, 0, result.stderr)
                features = [arg for arg in result.stdout.split() if arg.startswith("--features=")]
                self.assertEqual(features, [f"--features={feature}"] if feature else [])
                self.assertIn("--boot-method=vmm-direct", result.stdout)

    def test_make_rejects_ambiguous_or_invalid_profile_flags(self):
        for observe, control, daemon in (
                (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1),
                (0, 2, 0), ("invalid", 0, 0), (0, 0, 2), (0, 0, "invalid")):
            with self.subTest(observe=observe, control=control, daemon=daemon):
                result = self.make_flags(observe, control, daemon)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("profile", result.stderr)

    def test_g2_kernel_recipe_passes_selected_feature_to_actual_cargo_invocation(self):
        (self.root / "kernel").mkdir()
        capture = self.root / "osdk-argv.json"
        cargo = self.root / "cargo"
        cargo.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['OSDK_ARGV_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
        )
        cargo.chmod(0o755)
        result = subprocess.run(
            ["make", "--no-print-directory", "--always-make", "-f", str(BUILD / "minimal.mk"),
             "CARGO_OSDK=fixture-osdk", "HEPTA_G1C_TRUSTED_OBSERVE=0",
             "HEPTA_G1D_TRUSTED_CONTROL=0", "HEPTA_G2_TRUSTED_DAEMON=1",
             "FEATURES=g2-trusted-daemon", "kernel"],
            cwd=self.root,
            env={**os.environ, "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                 "OSDK_ARGV_CAPTURE": str(capture)},
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = json.loads(capture.read_text())
        self.assertEqual(argv[:2], ["osdk", "build"])
        self.assertEqual([arg for arg in argv if arg.startswith("--features=")],
                         ["--features=g2-trusted-daemon"])
        self.assertIn("--features=g2-trusted-daemon", result.stdout)

    def test_manifest_binds_the_independent_roles_to_one_frozen_input(self):
        source = self.root / "reviewed.elf"
        output = self.root / "embedded.elf"
        manifest = self.root / "manifest.json"
        content = bytearray(64)
        content[:7] = b"\x7fELF\x02\x01\x01"
        content[16:20] = b"\x02\x00\x3e\x00"
        content.extend(b"reviewed G1-d byte input")
        source.write_bytes(content)
        result = subprocess.run(
            [sys.executable, "-I", str(BUILD / "prepare-trusted-image.py"),
             "--input", str(source), "--output", str(output),
             "--manifest", str(manifest), "--profile", "g1d-trusted-control"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        source.write_bytes(b"later untrusted input")
        self.assertEqual(output.read_bytes(), content)
        self.assertEqual(output.stat().st_mode & 0o777, 0o444)
        self.assertEqual(json.loads(manifest.read_text()), {
            "schema": "hepta-g1d-trusted-initial-v1",
            "profile": "g1d-trusted-control",
            "source": str(source), "embedded_input": str(output),
            "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            "supported_ops": 62, "features": 0,
            "bootstrap_version": 2, "bootstrap_bytes": 192,
            "roles": ["manager", "workload", "recovery"],
            "cap_ns": 50_000_000, "period_ns": 100_000_000,
            "lease_ns": 300_000_000_000,
            "recovery_grace_ns": 30_000_000_000,
            "workload_address_space_bytes": 256 * 1024 * 1024,
        })

    def test_kernel_wrapper_refuses_profile_run_and_ambiguous_selection_before_build(self):
        for index, (observe, control, target) in enumerate(((0, 1, "run_kernel"),
                                                           (1, 1, "kernel"),
                                                           (0, 2, "kernel"))):
            with self.subTest(observe=observe, control=control, target=target):
                run_dir = self.root / f"invalid-{index}"
                env = dict(os.environ, A01_RUN_DIR=str(run_dir),
                           HEPTA_G1C_TRUSTED_OBSERVE=str(observe),
                           HEPTA_G1D_TRUSTED_CONTROL=str(control),
                           HEPTA_TRUSTED_INITIAL_ELF=str(self.root / "unused.elf"))
                result = subprocess.run(["bash", str(BUILD / "kernel.sh"), target],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(list(run_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
