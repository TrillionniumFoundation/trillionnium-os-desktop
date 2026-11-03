"""Exercise the real archive helper with system ELF copies, not Rust build evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

import native_sdk


@unittest.skipUnless(all(shutil.which(name) for name in ("bash", "git", "strip", "tar", "true")),
                     "Host archive tools are required")
class HostArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="trill-host-archive-test-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "source"
        product = self.repo / "support/ui/product"
        product.mkdir(parents=True)
        here = Path(__file__).resolve().parent
        for name in ("desktop.py", "native_sdk.py"):
            shutil.copyfile(here / name, product / name)
        self.script = self.repo / "support/ui/package-host-binaries.sh"
        shutil.copyfile(here.parent / "package-host-binaries.sh", self.script)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=Archive Test", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "archive fixture"], cwd=self.repo, check=True)
        tools = self.root / "tools"
        tools.mkdir()
        for name in ("rustc", "cargo"):
            path = tools / name
            path.write_text("#!/bin/sh\nprintf '%s\\n' 'archive-test metadata fixture, not a Rust build'\n")
            path.chmod(0o755)
        self.target = self.root / "target"
        release = self.target / "release"
        release.mkdir(parents=True)
        for name in ("trill-session", "trill-shell", "trill-app-window", "trill-ctl", "trill-notes-recovery"):
            shutil.copyfile(shutil.which("true"), release / name)
            (release / name).chmod(0o755)
        self.environment = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                                CARGO_TARGET_DIR=str(self.target), TRILL_UI_BUILD_PROFILE="release")
        self.receipt = self.root / "sdk.json"
        packages = [{"name": name, "version": "1.0.0", "manifest": manifest}
                    for name, manifest in native_sdk.REQUIRED.items()]
        packages.append({"name": "unicode-segmentation", "version": "1.12.0",
                         "manifest": "libs/unicode-segmentation/Cargo.toml"})
        self.profile = {"schema": "hepta.verified-original-sdk-source.v1", "native_ui_feature": "native-clipboard-sdk",
                        "upstream_repository": native_sdk.UPSTREAM, "upstream_commit": native_sdk.REVISION,
                        "patched_tree": native_sdk.TREE, "manifest_sha256": native_sdk.MANIFEST_SHA256,
                        "patches": native_sdk.PATCHES, "prepared_root": str(self.root / "prepared"),
                        "resolved_packages": packages, "original_metadata_sha256": "a" * 64,
                        "candidate_metadata_sha256": "b" * 64, "cargo_config_sha256": "c" * 64,
                        "source_tree_verified": True, "all_sdk_packages_same_tree": True,
                        "dependency_edges_verified": True, "effects_authority": False,
                        "compiled": False, "runtime_qualified": False}
        self.receipt.write_text(json.dumps(self.profile, indent=3) + "\n")

    def tearDown(self):
        self.temporary.cleanup()

    def archive(self, *receipt, environment=None):
        return subprocess.run(["bash", str(self.script), str(self.root / "output"), *map(str, receipt)],
                              cwd=self.repo, env=environment or self.environment,
                              capture_output=True, text=True, timeout=15)

    def test_release_archive_binds_exact_receipt_bytes_and_all_five_elfs(self):
        result = self.archive(self.receipt)
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(self.root / "output/a10-linux-host-binaries.tar.gz") as archive:
            base = "a10-linux-host-binaries/"
            provenance = archive.extractfile(base + "PROVENANCE.txt").read().decode()
            self.assertIn("Cargo build profile: release\n", provenance)
            self.assertIn("Makepad source profile SHA256: "
                          + hashlib.sha256(self.receipt.read_bytes()).hexdigest() + "\n", provenance)
            lines = archive.extractfile(base + "SHA256SUMS").read().decode().splitlines()
            self.assertEqual(len(lines), 5)
            for line in lines:
                expected, name = line.split("  ")
                actual = archive.extractfile(base + name).read()
                self.assertEqual(actual[:4], b"\x7fELF")
                self.assertEqual(hashlib.sha256(actual).hexdigest(), expected)

    def test_invalid_sdk_and_dirty_source_are_refused(self):
        self.profile["patched_tree"] = "f" * 40
        self.receipt.write_text(json.dumps(self.profile))
        result = self.archive(self.receipt)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown original SDK source", result.stderr)
        (self.repo / "unexpected-source").write_text("modified")
        result = self.archive()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("modified source checkout", result.stderr)
        self.assertFalse((self.root / "output/a10-linux-host-binaries.tar.gz").exists())

    def test_profile_is_explicit_and_debug_remains_the_default(self):
        environment = dict(self.environment, TRILL_UI_BUILD_PROFILE="other")
        result = self.archive(environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be debug or release", result.stderr)
        environment.pop("TRILL_UI_BUILD_PROFILE")
        result = self.archive(environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/debug/trill-session", result.stderr)


if __name__ == "__main__":
    unittest.main()
