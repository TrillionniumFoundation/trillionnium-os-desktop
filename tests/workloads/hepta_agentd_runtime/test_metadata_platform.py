#!/usr/bin/env python3
"""Reproduce the platform-only prefetch mismatch using real offline Cargo.

The target-only registry record is inert test data and has no crate archive.
No original library, compiler output or native execution is simulated here.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import prepare_inputs
import reviewed_toolchain


class MetadataPlatformTests(unittest.TestCase):
    def test_real_offline_metadata_does_not_fetch_a_foreign_target_archive(self):
        review = json.loads((Path(__file__).parent / "source-review.json").read_text())
        channel = reviewed_toolchain.reviewed_channel(review)
        rustup = shutil.which("rustup")
        self.assertIsNotNone(rustup, "the reviewed Cargo must be installed for this actual regression")
        tools = {}
        for name in ("cargo", "rustc"):
            tools[name] = subprocess.check_output([rustup, "which", "--toolchain", channel, name],
                                                  text=True, timeout=30).strip()
        with tempfile.TemporaryDirectory(prefix="f1-real-offline-platform-") as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "src/lib.rs").write_text("// Cargo metadata never executes this source.\n")
            name = "f1-inert-android-only"
            (source / "Cargo.toml").write_text(
                '[package]\nname="f1-real-platform-regression"\nversion="0.0.0"\nedition="2024"\n'
                '[workspace]\nresolver="2"\n'
                '[target.\'cfg(target_os = "android")\'.dependencies]\n' + name + '="=0.1.0"\n')
            registry = root / "registry"
            index = registry / "index/f1/-i"
            index.mkdir(parents=True)
            # This local registry deliberately contains no .crate payload.
            # Cargo may resolve the foreign target, but must not download it
            # to describe the independently selected native platform.
            (index / name).write_text(json.dumps({"name": name, "vers": "0.1.0", "deps": [],
                                                 "cksum": "0" * 64, "features": {}, "yanked": False}) + "\n")
            config = root / "cargo-config.toml"
            config.write_text('[source.crates-io]\nreplace-with="local"\n'
                              '[source.local]\nlocal-registry=' + json.dumps(str(registry)) + '\n')
            home = root / "cargo-home"
            home.mkdir()
            environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(root),
                           "CARGO_HOME": str(home), "CARGO_NET_OFFLINE": "true", "RUSTC": tools["rustc"]}
            base = [tools["cargo"], "--config", str(config)]
            locked = subprocess.run([*base, "generate-lockfile", "--offline"], cwd=source,
                                    env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(locked.returncode, 0, locked.stderr)
            before = (source / "Cargo.lock").read_bytes()
            common = ["metadata", "--locked", "--offline", "--format-version", "1"]
            old = subprocess.run([*base, *common], cwd=source, env=environment,
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(old.returncode, 101)
            self.assertIn("failed to download", old.stderr)
            self.assertIn(name, old.stderr)
            fixed = subprocess.run([*base, *common, "--filter-platform", "x86_64-unknown-linux-gnu"],
                                   cwd=source, env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(fixed.returncode, 0, fixed.stderr)
            graph = json.loads(fixed.stdout)
            self.assertEqual([item["name"] for item in graph["packages"]], ["f1-real-platform-regression"])
            self.assertEqual((source / "Cargo.lock").read_bytes(), before)
            self.assertEqual(list(registry.glob("*.crate")), [])

            # Exercise the actual production command builder as well. Only its
            # unrelated owner-build boundary is stubbed; both emitted metadata
            # commands are executed by the real Cargo against this missing
            # foreign archive. Removing either production filter fails here.
            class MetadataComplete(Exception):
                pass

            calls = []
            output = root / "builder-output"
            output.mkdir()

            class Helper:
                GateError = ValueError

                @staticmethod
                def prepare_runner(_original, destination):
                    shutil.copytree(source, destination)
                    settings = destination / ".cargo"
                    settings.mkdir()
                    shutil.copyfile(config, settings / "config.toml")

                @staticmethod
                def verify_runner_lock(_original, _runner):
                    return None

                @staticmethod
                def bounded_command(command, cwd, env, log, _timeout):
                    if command[1] != "metadata":
                        return
                    result = subprocess.run(command, cwd=cwd, env=env,
                                            capture_output=True, timeout=30)
                    log.write_bytes(result.stdout + result.stderr)
                    if result.returncode != 0:
                        raise ValueError(result.stderr.decode(errors="replace"))
                    calls.append(command)
                    if len(calls) == 2:
                        raise MetadataComplete()

            args = type("Arguments", (), {"fetch_dependencies": False})()
            roots = {"desktop": source, "hepta": source}
            with mock.patch.object(prepare_inputs, "original_helper", return_value=Helper), \
                    mock.patch.object(prepare_inputs, "verify_target_caches"), \
                    self.assertRaises(MetadataComplete):
                prepare_inputs.build_userspace(args, roots, output,
                                              {"steps": [], "cargo_targets": {}}, [], {},
                                              environment, {"cargo": {"path": tools["cargo"]}},
                                              {"original": root / "original-target",
                                               "observer": root / "observer-target"})
            self.assertEqual(len(calls), 2)
            self.assertEqual((output / "fixture-build/Cargo.lock").read_bytes(), before)
