"""Real deployment filesystem/lock transactions; fixture ELFs are not UI runs."""
import os
from pathlib import Path
import tarfile
import unittest
from unittest.mock import patch

import desktop
import test_desktop as fixtures
import trusted_desktop as trusted


@unittest.skipUnless(os.geteuid() == 0, "protected deployment tests require a disposable root test process")
class TrustedDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProductTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.prefix = self.root / "root-installed"
        self.resources = self.fixture.resource_fixture()
        self.package = self.bundle("a" * 40, b"first")

    def bundle(self, commit, payload):
        output = self.root / (commit[:12] + ".tar.gz")
        desktop.pack(self.fixture.make_archive(commit, payload), commit,
                     self.root / "profile.json", output, self.resources)
        extracted = self.root / (commit[:12] + "-extracted")
        extracted.mkdir()
        with tarfile.open(output) as archive:
            archive.extractall(extracted, filter="data")
        return extracted / "trillionnium-desktop"

    def stage(self, package=None):
        package = package or self.package
        return trusted.stage(package, self.prefix, desktop.digest((package / "manifest.json").read_bytes()))

    def test_stage_upgrade_rollback_keep_immutable_program_paths_and_resources(self):
        first = self.stage()
        old_bytes = Path(first["program"]).read_bytes()
        second = self.stage(self.bundle("c" * 40, b"upgrade"))
        self.assertNotEqual(first["program"], second["program"])
        self.assertEqual(Path(first["program"]).read_bytes(), old_bytes)
        self.assertEqual(Path(second["program"]).stat().st_mode & 0o777, 0o755)
        self.assertEqual(Path(second["resources"]).stat().st_mode & 0o777, 0o755)
        restored = trusted.rollback(self.prefix)
        self.assertEqual((restored["program"], restored["generation"]), (first["program"], 3))
        self.assertFalse(restored["production_authority_verified"])

    def test_active_original_lock_blocks_upgrade_and_rollback(self):
        self.stage()
        upgrade = self.bundle("c" * 40, b"upgrade")
        before = (self.prefix / trusted.RECORD).read_bytes()
        with trusted.deployment_lock(self.prefix):
            with self.assertRaisesRegex(desktop.ProductError, "Root is active"):
                self.stage(upgrade)
            with self.assertRaisesRegex(desktop.ProductError, "Root is active"):
                trusted.rollback(self.prefix)
        self.assertEqual((self.prefix / trusted.RECORD).read_bytes(), before)
        self.stage(upgrade)

    def test_interrupted_selection_write_keeps_old_release_and_can_retry(self):
        first = self.stage()
        upgrade = self.bundle("c" * 40, b"upgrade")
        original = desktop.atomic_write
        def fail_selection(path, *args, **kwargs):
            if Path(path) == self.prefix / trusted.RECORD:
                raise OSError("injected durable selection failure")
            return original(path, *args, **kwargs)
        with patch.object(desktop, "atomic_write", side_effect=fail_selection):
            with self.assertRaisesRegex(OSError, "selection failure"):
                self.stage(upgrade)
        self.assertEqual(trusted.binding(self.prefix, trusted.read_record(self.prefix))["program"], first["program"])
        self.stage(upgrade)
        self.assertEqual(trusted.rollback(self.prefix)["program"], first["program"])

    def test_unreviewed_or_changed_package_cannot_replace_current(self):
        self.stage()
        before = (self.prefix / trusted.RECORD).read_bytes()
        with self.assertRaisesRegex(desktop.ProductError, "reviewed manifest"):
            trusted.stage(self.package, self.prefix, "0" * 64)
        (self.package / "bin/trill-shell").write_bytes(b"\x7fELFchanged")
        with self.assertRaisesRegex(desktop.ProductError, "checksum mismatch"):
            self.stage()
        self.assertEqual((self.prefix / trusted.RECORD).read_bytes(), before)

    def test_root_protection_rejects_hardlinks_symlinks_and_writable_ancestors(self):
        result = self.stage()
        program = Path(result["program"])
        os.link(program, self.root / "second-link")
        with self.assertRaisesRegex(desktop.ProductError, "one linked"):
            trusted.binding(self.prefix, trusted.read_record(self.prefix))
        (self.root / "second-link").unlink()
        link = self.root / "alias"
        link.symlink_to(self.prefix, target_is_directory=True)
        with self.assertRaisesRegex(desktop.ProductError, "symlink"):
            with trusted.deployment_lock(link):
                self.fail("symlink accepted")
        self.root.chmod(0o777)
        try:
            with self.assertRaisesRegex(desktop.ProductError, "mutable ancestor"):
                trusted.protected_file(program)
        finally:
            self.root.chmod(0o700)

    def test_missing_bundled_resources_never_create_native_installation(self):
        with self.assertRaisesRegex(desktop.ProductError, "bundled resources"):
            self.stage(self.fixture.package)
        self.assertFalse(self.prefix.exists())

    def test_wrong_installed_profile_is_refused_before_any_authority_exec(self):
        result = self.stage()
        profile = self.root / "existing-profile.json"
        desktop.atomic_write(profile, desktop.json_bytes({
            "program": result["program"], "program_sha256": "0" * 64,
            "environment": {"TRILL_UI_MAKEPAD_RESOURCES": result["resources"]}}))
        with patch.object(os, "execve") as execute:
            with self.assertRaisesRegex(desktop.ProductError, "does not name this installed"):
                trusted.launch(self.prefix, self.root / "absent-authority", "0" * 64,
                               self.root / "absent-config", self.root / "absent-registration", profile)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
