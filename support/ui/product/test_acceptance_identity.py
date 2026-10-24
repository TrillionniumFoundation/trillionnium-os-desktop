"""Read-only acceptance gates; these tests do not qualify a Rust GUI package."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import acceptance_identity as identity
import desktop


capture_path = Path(__file__).resolve().parents[3] / "tests/ui/native-makepad/capture.py"
capture_spec = importlib.util.spec_from_file_location("native_frame_capture", capture_path)
capture = importlib.util.module_from_spec(capture_spec)
capture_spec.loader.exec_module(capture)


class AcceptanceIdentityTests(unittest.TestCase):
    def test_uniform_owned_pixels_do_not_count_as_a_rendered_frame(self):
        for color in (b"\x00\x00\x00", b"\xff\xff\xff", b"\x12\x34\x56"):
            with self.subTest(color=color):
                rows = [b"\0" + color * 4] * 3
                frame = dict(capture.rgb_content(rows, 4), window=41)
                self.assertFalse(identity.nonuniform_window_frame(frame, 41))
                self.assertEqual(frame["uniform_rgb"], list(color))
        rows = [b"\0" + b"\x00\x00\x00" * 4,
                b"\0" + b"\xff\xff\xff" + b"\x00\x00\x00" * 3]
        frame = dict(capture.rgb_content(rows, 4), window=41)
        self.assertTrue(identity.nonuniform_window_frame(frame, 41))
        self.assertIsNone(frame["uniform_rgb"])

    def test_foreign_window_and_root_pixels_cannot_qualify_the_shell(self):
        original = {"matched": True, "window": {"pid": 101, "xid": 41}}
        self.assertEqual(identity.window_identity(original, 101), 41)
        with self.assertRaisesRegex(RuntimeError, "foreign window owner"):
            identity.window_identity(original, 202)
        with self.assertRaisesRegex(RuntimeError, "window changed"):
            identity.window_identity(original, 101, expected_window=42)
        with self.assertRaisesRegex(RuntimeError, "verified owned X11 window"):
            identity.nonuniform_window_frame({"window": 1, "nonuniform_rgb": True}, 41)
        with self.assertRaisesRegex(RuntimeError, "RGB content observation"):
            identity.nonuniform_window_frame({"window": 41}, 41)

    def test_blocking_probe_spends_the_original_deadline_without_rearming_it(self):
        deadline = time.monotonic() + 0.1
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run([sys.executable, "-c", "import time; time.sleep(30)"],
                           timeout=identity.remaining_timeout(deadline, 8), check=True)
        with self.assertRaisesRegex(RuntimeError, "deadline expired"):
            identity.remaining_timeout(deadline, 8)

    def test_retained_pidfd_rejects_foreign_pid_and_actual_child_exit(self):
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
                                 stdin=subprocess.PIPE)
        handle = os.pidfd_open(child.pid)
        try:
            identity.require_live_pidfd(handle, child.pid)
            with self.assertRaisesRegex(RuntimeError, "different process"):
                identity.require_live_pidfd(handle, os.getpid())
            child.communicate(timeout=5)
            with self.assertRaisesRegex(RuntimeError, "exited during window observation"):
                identity.require_live_pidfd(handle, child.pid)
        finally:
            child.communicate(timeout=5)
            os.close(handle)

    def test_runtime_root_is_private_and_its_identity_detects_replacement(self):
        with tempfile.TemporaryDirectory(prefix="tr-run-") as scratch:
            root = Path(scratch) / "r"
            root.mkdir(mode=0o700)
            first = identity.runtime_root_identity(root)
            self.assertEqual(first["session_socket"], str(root / "trillionnium-ui/session.sock"))
            self.assertLessEqual(first["session_socket_bytes"], 107)
            self.assertEqual(list(root.iterdir()), [])
            root.rename(Path(scratch) / "retained")
            root.mkdir(mode=0o700)
            self.assertNotEqual(identity.runtime_root_identity(root), first)

    def test_runtime_root_rejects_shared_or_aliased_directories(self):
        with tempfile.TemporaryDirectory(prefix="tr-run-") as scratch:
            root = Path(scratch) / "r"
            root.mkdir(mode=0o755)
            with self.assertRaisesRegex(RuntimeError, "0700"):
                identity.runtime_root_identity(root)
            root.chmod(0o700)
            alias = Path(scratch) / "alias"
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "canonical directory"):
                identity.runtime_root_identity(alias)

    def test_runtime_root_reserves_space_for_temporary_bus_names(self):
        with tempfile.TemporaryDirectory(prefix="tr-run-") as scratch:
            count = 70 - len(os.fsencode(scratch)) - 1
            root = Path(scratch) / ("r" * count)
            root.mkdir(mode=0o700)
            self.assertLessEqual(len(os.fsencode(desktop.session_socket_path(root))), 107)
            with self.assertRaisesRegex(desktop.ProductError, "Temporary bus socket budget.*at most 107 bytes"):
                identity.runtime_root_identity(root)

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
            handle = os.pidfd_open(child.pid)
            foreign = os.pidfd_open(os.getpid())
            try:
                identity.require_same_process(handle, first)
                with self.assertRaisesRegex(RuntimeError, "different process"):
                    identity.require_same_process(foreign, first)
                with self.assertRaisesRegex(RuntimeError, "start time changed"):
                    identity.require_same_process(handle, dict(first, start_ticks="0"))
                child.communicate(timeout=5)
                with self.assertRaisesRegex(RuntimeError, "exited during window observation"):
                    identity.require_same_process(handle, first)
            finally:
                os.close(foreign)
                os.close(handle)
        finally:
            child.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
