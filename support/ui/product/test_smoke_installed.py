"""Installation entry-point dry runs; no manager, bus or GUI is started."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import smoke_installed as smoke


class DryRunStopped(Exception):
    pass


class InstalledSmokeEnvironmentTests(unittest.TestCase):
    def test_existing_manager_bus_never_replaces_the_private_runtime_root(self):
        for explicit_bus in (False, True):
            with self.subTest(explicit_bus=explicit_bus), tempfile.TemporaryDirectory(prefix="tr-env-") as scratch:
                root = Path(scratch).resolve()
                runtime, manager_runtime = root / "r", root / "manager"
                runtime.mkdir(mode=0o700)
                manager_runtime.mkdir(mode=0o700)
                evidence, units = root / "evidence", root / "units"
                helper = root / "helper/apps/hepta-control-ui/test/x11_client_owner.py"
                helper.parent.mkdir(parents=True)
                helper.write_text("# Inert entry-point fixture; never executed.\n")
                first, second = root / "first", root / "second"
                for package in (first, second):
                    (package / "resources").mkdir(parents=True)
                bus = "unix:path=" + str(manager_runtime / "bus")
                environment = dict(os.environ, XDG_RUNTIME_DIR=str(manager_runtime))
                environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
                if explicit_bus:
                    environment["DBUS_SESSION_BUS_ADDRESS"] = bus
                manifests = [{"desktop_commit": "a" * 40, "hepta_commit": "b" * 40, "release_id": name}
                             for name in ("first-fixture", "second-fixture")]
                argv = ["smoke_installed.py", "--package", str(first), "--upgrade-package", str(second),
                        "--expected-manifest-sha256", "c" * 64, "--expected-upgrade-manifest-sha256", "d" * 64,
                        "--expected-desktop", "a" * 40, "--expected-hepta", "b" * 40,
                        "--hepta-source", str(root / "helper"), "--evidence", str(evidence),
                        "--runtime-root", str(runtime), "--unit-dir", str(units)]
                manager_calls = []

                def inspect_manager(command, **kwargs):
                    self.assertIn(command, (["systemctl", "--user", "show", "--property=Version", "--value"],
                                            ["systemctl", "--user", "show-environment"]))
                    self.assertEqual(kwargs["env"]["DBUS_SESSION_BUS_ADDRESS"], bus)
                    self.assertEqual(kwargs["env"]["XDG_RUNTIME_DIR"], str(manager_runtime))
                    manager_calls.append(command)
                    return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

                # Package behavior has separate real filesystem tests. This
                # dry run selects its two identity results, simulates only the
                # existing manager inspection and stops at the first launch.
                # In particular, no D-Bus socket or service is created here.
                with patch.object(sys, "argv", argv), patch.dict(os.environ, environment, clear=True), \
                     patch.object(smoke.acceptance_identity, "pinned_package", side_effect=manifests), \
                     patch.object(smoke.shutil, "which", return_value="/unused/installed-tool"), \
                     patch.object(Path, "is_socket", autospec=True, side_effect=lambda path: path == manager_runtime / "bus"), \
                     patch.object(smoke.subprocess, "run", side_effect=inspect_manager), \
                     patch.object(smoke.subprocess, "Popen", side_effect=DryRunStopped("before first child")) as launch:
                    with self.assertRaisesRegex(DryRunStopped, "before first child"):
                        smoke.main()
                self.assertEqual(len(manager_calls), 2)
                self.assertEqual(launch.call_count, 1)
                self.assertEqual(launch.call_args.args[0][0], "Xvfb")
                report = json.loads((evidence / "acceptance.json").read_text())
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["runtime_root_identity"]["path"], str(runtime))
                self.assertEqual(report["private_xdg_environment"]["XDG_RUNTIME_DIR"], str(runtime))
                for name in ("config", "cache", "data", "tmp", "state"):
                    self.assertTrue((runtime / name).is_dir())
                self.assertEqual(list(manager_runtime.iterdir()), [])
                self.assertFalse(units.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
