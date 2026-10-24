"""Interrupt real installation writes and resume without claiming unmanaged files."""
import errno
from pathlib import Path
import unittest
from unittest.mock import patch

import desktop
import test_desktop


class InstallRecoveryTests(unittest.TestCase):
    def fixture(self):
        fixture = test_desktop.ProductTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        return fixture

    def interrupt(self, fixture, package, boundary, after=False):
        writes = list(desktop.integrations(fixture.prefix, fixture.paths))
        targets = {"intent": fixture.prefix / "installation.pending.json",
                   "launcher": Path(writes[0]), "unit": Path(writes[1]),
                   "desktop": Path(writes[2]),
                   "record": fixture.prefix / "installation.json"}
        real_write, real_switch = desktop.atomic_write, desktop.switch_release

        def fail_write(path, *args, **kwargs):
            if Path(path) != targets.get(boundary):
                return real_write(path, *args, **kwargs)
            if after:
                real_write(path, *args, **kwargs)
            raise OSError(errno.ENOSPC, "injected persistence boundary")

        def fail_switch(*args, **kwargs):
            if after:
                real_switch(*args, **kwargs)
            raise OSError(errno.ENOSPC, "injected persistence boundary")

        with patch.object(desktop, "atomic_write", side_effect=fail_write), \
                patch.object(desktop, "switch_release",
                             side_effect=fail_switch if boundary == "switch" else real_switch):
            with self.assertRaisesRegex(OSError, "injected persistence boundary"):
                fixture.install(package)

    def test_first_install_and_upgrade_resume_each_persistence_boundary(self):
        for upgrade in (False, True):
            for boundary in ("intent", "launcher", "unit", "desktop", "record", "switch"):
                for after in (False, True):
                    with self.subTest(upgrade=upgrade, boundary=boundary, after=after):
                        fixture = self.fixture()
                        previous = None
                        package = fixture.package
                        if upgrade:
                            fixture.install()
                            previous = desktop.current_release(fixture.prefix).name
                            package = fixture.make_package("c" * 40, b"upgrade")
                        self.interrupt(fixture, package, boundary, after)
                        config = Path(fixture.paths["config"])
                        config_before = config.read_bytes()
                        pending = fixture.prefix / "installation.pending.json"
                        if pending.exists():
                            with self.assertRaisesRegex(desktop.ProductError, "incomplete"):
                                desktop.installed(fixture.prefix)
                        result = fixture.install(package)
                        record, release, manifest, _cfg = desktop.installed(fixture.prefix)
                        self.assertEqual(result["installed_release"], manifest["release_id"])
                        self.assertEqual(release.name, desktop.verify_package(package)["release_id"])
                        self.assertEqual(record["previous_release"], previous)
                        self.assertEqual(config.read_bytes(), config_before)
                        self.assertFalse(pending.exists())
                        for filename, (data, _mode) in desktop.integrations(fixture.prefix, fixture.paths).items():
                            self.assertEqual(Path(filename).read_bytes(), data)

    def test_resume_preserves_user_edit_and_pending_intent(self):
        fixture = self.fixture()
        self.interrupt(fixture, fixture.package, "record")
        launcher = Path(fixture.paths["bin_dir"]) / "trillionnium-desktop"
        changed = launcher.read_bytes() + b"# local edit\n"
        launcher.write_bytes(changed)
        with self.assertRaisesRegex(desktop.ProductError, "modified/unmanaged"):
            fixture.install()
        self.assertEqual(launcher.read_bytes(), changed)
        self.assertTrue((fixture.prefix / "installation.pending.json").exists())
        self.assertIsNone(desktop.current_release(fixture.prefix))

    def test_resume_rejects_a_different_package_or_installation_paths(self):
        fixture = self.fixture()
        self.interrupt(fixture, fixture.package, "record")
        pending = (fixture.prefix / "installation.pending.json").read_bytes()
        other = fixture.make_package("c" * 40, b"different package")
        with self.assertRaisesRegex(desktop.ProductError, "same package and paths"):
            fixture.install(other)
        paths = dict(fixture.paths, bin_dir=str(fixture.root / "other-bin"))
        with self.assertRaisesRegex(desktop.ProductError, "same package and paths"):
            desktop.install(fixture.package, fixture.prefix, paths, lambda _unit: None)
        self.assertEqual((fixture.prefix / "installation.pending.json").read_bytes(), pending)
        self.assertFalse(Path(paths["bin_dir"]).exists())
        fixture.install()

    def test_resume_rejects_changed_record_and_current_release(self):
        for changed in ("record", "current"):
            with self.subTest(changed=changed):
                fixture = self.fixture()
                fixture.install()
                second = fixture.make_package("c" * 40, b"upgrade")
                self.interrupt(fixture, second, "record")
                if changed == "record":
                    record_path = fixture.prefix / "installation.json"
                    record = desktop.read_json(record_path)
                    record["previous_release"] = "e" * 12 + "-" + "f" * 12
                    desktop.atomic_write(record_path, desktop.json_bytes(record))
                else:
                    other = "e" * 12 + "-" + "f" * 12
                    (fixture.prefix / "releases" / other).mkdir()
                    desktop.switch_release(fixture.prefix, other)
                with self.assertRaisesRegex(desktop.ProductError, "changed during interrupted"):
                    fixture.install(second)

    def test_partial_upgrade_accepts_old_and_new_owned_integration_bytes(self):
        fixture = self.fixture()
        fixture.install()
        launcher = Path(fixture.paths["bin_dir"]) / "trillionnium-desktop"
        older_wrapper = launcher.read_bytes() + b"# preceding installer version\n"
        launcher.write_bytes(older_wrapper)
        record_path = fixture.prefix / "installation.json"
        record = desktop.read_json(record_path)
        record["integration_sha256"][str(launcher)] = desktop.digest(older_wrapper)
        desktop.atomic_write(record_path, desktop.json_bytes(record))
        second = fixture.make_package("c" * 40, b"upgrade")
        self.interrupt(fixture, second, "launcher", after=True)
        self.assertNotEqual(launcher.read_bytes(), older_wrapper)
        fixture.install(second)
        self.assertEqual(desktop.current_release(fixture.prefix).name,
                         desktop.verify_package(second)["release_id"])


if __name__ == "__main__":
    unittest.main()
