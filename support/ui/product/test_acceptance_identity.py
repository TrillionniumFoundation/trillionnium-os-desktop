"""Read-only acceptance gates; these tests do not qualify a Rust GUI package."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import acceptance_identity as identity
import desktop


class AcceptanceIdentityTests(unittest.TestCase):
    def test_external_manifest_pin_rejects_before_installation_or_binary_execution(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "manifest.json").write_bytes(b'{}\n')
            with patch.object(desktop, "verify_package") as verify:
                with self.assertRaisesRegex(RuntimeError, "build manifest pin"):
                    identity.pinned_package(root, "a" * 64)
            verify.assert_not_called()

    def test_manifest_replacement_during_verification_rejects(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            path = root / "manifest.json"
            before = b'{}\n'
            path.write_bytes(before)
            def changed(_package):
                path.write_bytes(b'{"changed":true}\n')
                return {}
            with patch.object(desktop, "verify_package", side_effect=changed):
                with self.assertRaisesRegex(RuntimeError, "changed during verification"):
                    identity.pinned_package(root, desktop.digest(before))

    def test_isolation_keeps_user_manager_and_home_without_inheriting_lanes(self):
        source = {"HOME": "/unchanged", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
                  "TRILL_UI_CHAT_SOCKET": "/private/production", "TRILL_OBJECTIVE_HOST_PID": "9",
                  "HEPTA_AUTH_TOKEN": "must not propagate", "CODEX_SANDBOX_NETWORK_DISABLED": "1"}
        self.assertEqual(identity.isolated_environment(source), {
            "HOME": source["HOME"], "DBUS_SESSION_BUS_ADDRESS": source["DBUS_SESSION_BUS_ADDRESS"],
            "CODEX_SANDBOX_NETWORK_DISABLED": "1"})
        self.assertEqual(source["TRILL_UI_CHAT_SOCKET"], "/private/production")
        names = identity.manager_lane_names(b"UNRELATED=secret\nTRILL_UI_CHAT_SOCKET=private\nHEPTA_AUTH_TOKEN=secret\n")
        self.assertEqual(names, {"TRILL_UI_CHAT_SOCKET", "HEPTA_AUTH_TOKEN"})

    @unittest.skipUnless(hasattr(os, "pidfd_open"), "requires the actual Linux pidfd identity gate")
    def test_real_process_image_and_start_time_match_and_wrong_hash_rejects(self):
        binary = Path(sys.executable).resolve()
        digest = desktop.digest(desktop.regular_bytes(binary))
        child = subprocess.Popen([str(binary), "-c", "import sys; sys.stdin.buffer.read()"],
                                 stdin=subprocess.PIPE, env=identity.isolated_environment(os.environ))
        try:
            try:
                first = identity.process_identity(child.pid, binary, digest)
            except PermissionError:
                self.skipTest("sandbox does not expose the actual child /proc image; real-host qualification still required")
            self.assertEqual(identity.process_identity(child.pid, binary, digest), first)
            self.assertEqual(first["executable"], str(binary))
            self.assertEqual(first["executable_sha256"], digest)
            with self.assertRaisesRegex(RuntimeError, "package hash"):
                identity.process_identity(child.pid, binary, "0" * 64)
        finally:
            child.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
