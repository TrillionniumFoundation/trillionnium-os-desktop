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

    def test_interrupted_rollback_retries_the_original_target(self):
        fixture = self.fixture()
        fixture.install()
        original = desktop.current_release(fixture.prefix).name
        second = fixture.make_package("c" * 40, b"upgrade")
        fixture.install(second)
        upgraded = desktop.current_release(fixture.prefix).name
        with patch.object(desktop, "switch_release", side_effect=OSError(errno.ENOSPC, "rollback cut")):
            with self.assertRaisesRegex(OSError, "rollback cut"):
                desktop.rollback(fixture.prefix, lambda _unit: None)
        self.assertEqual(desktop.current_release(fixture.prefix).name, upgraded)
        desktop.rollback(fixture.prefix, lambda _unit: None)
        record, release, _manifest, _cfg = desktop.installed(fixture.prefix)
        self.assertEqual(release.name, original)
        self.assertEqual(record["previous_release"], upgraded)

    def rollback_fixture(self):
        fixture = self.fixture()
        fixture.install()
        original = desktop.current_release(fixture.prefix).name
        fixture.install(fixture.make_package("c" * 40, b"upgrade"))
        return fixture, original, desktop.current_release(fixture.prefix).name

    def interrupt_rollback(self, fixture, boundary, after=False):
        targets = {"intent": fixture.prefix / "rollback.pending.json",
                   "record": fixture.prefix / "installation.json"}
        real_write, real_switch, real_unlink = desktop.atomic_write, desktop.switch_release, Path.unlink

        def write(path, *args, **kwargs):
            if Path(path) != targets.get(boundary):
                return real_write(path, *args, **kwargs)
            if after:
                real_write(path, *args, **kwargs)
            raise OSError(errno.ENOSPC, "injected rollback boundary")

        def switch(*args, **kwargs):
            if after:
                real_switch(*args, **kwargs)
            raise OSError(errno.ENOSPC, "injected rollback boundary")

        def unlink(path, *args, **kwargs):
            if boundary == "cleanup" and path == targets["intent"]:
                raise OSError(errno.ENOSPC, "injected rollback boundary")
            return real_unlink(path, *args, **kwargs)

        with patch.object(desktop, "atomic_write", side_effect=write), \
                patch.object(desktop, "switch_release", side_effect=switch if boundary == "switch" else real_switch), \
                patch.object(Path, "unlink", unlink):
            with self.assertRaisesRegex(OSError, "injected rollback boundary"):
                desktop.rollback(fixture.prefix, lambda _unit: None)

    def test_rollback_recovery_retains_selection_across_record_and_switch_boundaries(self):
        cuts = [(point, after) for point in ("intent", "record", "switch") for after in (False, True)]
        cuts.append(("cleanup", False))
        for boundary, after in cuts:
            with self.subTest(boundary=boundary, after=after):
                fixture, original, upgraded = self.rollback_fixture()
                config = Path(fixture.paths["config"])
                config_before = config.read_bytes()
                self.interrupt_rollback(fixture, boundary, after)
                pending = fixture.prefix / "rollback.pending.json"
                if pending.exists():
                    with self.assertRaisesRegex(desktop.ProductError, "Rollback is incomplete"):
                        desktop.installed(fixture.prefix)
                result = desktop.rollback(fixture.prefix, lambda _unit: None)
                record, release, _manifest, _cfg = desktop.installed(fixture.prefix)
                self.assertEqual(result["current_release"], original)
                self.assertEqual(release.name, original)
                self.assertEqual(record["previous_release"], upgraded)
                self.assertEqual(config.read_bytes(), config_before)
                self.assertFalse(pending.exists())

    def test_pending_rollback_blocks_other_lifecycle_commands_before_service_actions(self):
        fixture, _original, _upgraded = self.rollback_fixture()
        self.interrupt_rollback(fixture, "record", after=True)
        pending = fixture.prefix / "rollback.pending.json"
        before = pending.read_bytes()
        operations = (lambda: desktop.installed(fixture.prefix),
                      lambda: desktop.run(fixture.prefix),
                      lambda: desktop.run(fixture.prefix, session=True),
                      lambda: fixture.install(),
                      lambda: desktop.uninstall(fixture.prefix, lambda _unit: None))
        with patch.object(desktop, "systemctl") as service:
            for operation in operations:
                with self.assertRaisesRegex(desktop.ProductError, "Rollback is incomplete"):
                    operation()
            service.assert_not_called()
        self.assertEqual(pending.read_bytes(), before)

    def test_rollback_resume_rejects_changed_record_current_and_user_integration(self):
        for changed in ("record", "current", "integration"):
            with self.subTest(changed=changed):
                fixture, _original, _upgraded = self.rollback_fixture()
                self.interrupt_rollback(fixture, "record", after=True)
                pending = fixture.prefix / "rollback.pending.json"
                intent = pending.read_bytes()
                launcher = Path(fixture.paths["bin_dir"]) / "trillionnium-desktop"
                if changed == "record":
                    record_path = fixture.prefix / "installation.json"
                    record = desktop.read_json(record_path)
                    record["previous_release"] = "e" * 12 + "-" + "f" * 12
                    desktop.atomic_write(record_path, desktop.json_bytes(record))
                elif changed == "current":
                    other = "e" * 12 + "-" + "f" * 12
                    (fixture.prefix / "releases" / other).mkdir()
                    desktop.switch_release(fixture.prefix, other)
                else:
                    launcher.write_bytes(launcher.read_bytes() + b"# preserve user change\n")
                contents = launcher.read_bytes()
                with self.assertRaisesRegex(desktop.ProductError, "changed during interrupted|Modified integration preserved"):
                    desktop.rollback(fixture.prefix, lambda _unit: None)
                self.assertEqual(pending.read_bytes(), intent)
                self.assertEqual(launcher.read_bytes(), contents)

    def test_rollback_resume_rejects_aliases_and_inconsistent_intent_without_mutation(self):
        for changed in ("symlink", "hardlink", "record", "path"):
            with self.subTest(changed=changed):
                fixture, _original, upgraded = self.rollback_fixture()
                self.interrupt_rollback(fixture, "record")
                pending = fixture.prefix / "rollback.pending.json"
                original = pending.read_bytes()
                outside = fixture.root / "retain-intent.json"
                if changed == "symlink":
                    pending.rename(outside)
                    pending.symlink_to(outside)
                elif changed == "hardlink":
                    outside.hardlink_to(pending)
                else:
                    intent = desktop.read_json(pending)
                    if changed == "record":
                        intent["record"]["previous_release"] = intent["after_release"]
                    else:
                        intent["record"]["integration_sha256"][str(outside)] = "a" * 64
                    desktop.atomic_write(pending, desktop.json_bytes(intent))
                before = pending.read_bytes()
                with self.assertRaises(desktop.ProductError):
                    desktop.rollback(fixture.prefix, lambda _unit: None)
                self.assertEqual(pending.read_bytes(), before)
                if outside.exists():
                    self.assertEqual(outside.read_bytes(), original)
                self.assertEqual(desktop.current_release(fixture.prefix).name, upgraded)

    def test_active_session_blocks_rollback_before_intent_and_during_recovery(self):
        fixture, _original, upgraded = self.rollback_fixture()

        def active(_unit):
            raise desktop.ProductError("Session active")

        pending = fixture.prefix / "rollback.pending.json"
        with self.assertRaisesRegex(desktop.ProductError, "Session active"):
            desktop.rollback(fixture.prefix, active)
        self.assertFalse(pending.exists())
        self.interrupt_rollback(fixture, "record")
        original = pending.read_bytes()
        with self.assertRaisesRegex(desktop.ProductError, "Session active"):
            desktop.rollback(fixture.prefix, active)
        self.assertEqual(pending.read_bytes(), original)
        self.assertEqual(desktop.current_release(fixture.prefix).name, upgraded)


if __name__ == "__main__":
    unittest.main()
