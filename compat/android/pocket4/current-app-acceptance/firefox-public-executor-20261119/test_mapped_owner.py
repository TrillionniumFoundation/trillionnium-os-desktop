"""Ordinary host regression controls, never an Android ownership observation.

The exact existing Main mapping helper reads real temporary proc-shaped files.
Only its namespace ioctl and the APK's host UID/GID fstat fields are injected;
FDs, bytes, complete hashes, inode replacement, limits and descriptor closure
are real. No chown, user namespace creation, Android or privileged call occurs.
"""
from contextlib import ExitStack, nullcontext
import errno
import hashlib
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import firefox_custody as c

COMMON_PATH = (Path(__file__).resolve().parent.parent /
               "calendar-core-live-id-map-20261120/source/app_common.py")
COMMON_SHA256 = "adebfe99b64afc5a06caf30d2023d113f937920cba92dbe751a53c473ea8c2b4"
_raw = COMMON_PATH.read_bytes()
if len(_raw) != 44032 or hashlib.sha256(_raw).hexdigest() != COMMON_SHA256:
    raise RuntimeError("EXACT_REVIEWED_COMMON_TEST_SOURCE_REQUIRED")
m = types.ModuleType("offline_exact_current_main_common")
m.__file__ = str(COMMON_PATH)
exec(compile(_raw, str(COMMON_PATH), "exec"), m.__dict__)

REAL_FSTAT = os.fstat
REAL_CLOSE = os.close
STAT_FIELDS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
               "st_size", "st_mtime_ns", "st_ctime_ns")
GUEST_PATH = "/data/app/~~fixture/org.mozilla.firefox-fixture/base.apk"


class ProcFixture:
    """Explicitly synthetic admission with ordinary, genuinely held host FDs."""
    def __init__(self, uid_base=100000, gid_base=200000):
        self.stack = ExitStack()
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(
            prefix="firefox-owner-boundary-")))
        self.proc = self.root / "proc-fixture"
        (self.proc / "ns").mkdir(parents=True)
        (self.proc / "ns/user").write_bytes(b"injected namespace ioctl boundary\n")
        self.uid_map = self.proc / "uid_map"
        self.gid_map = self.proc / "gid_map"
        self.uid_map.write_bytes(f"0 {uid_base} 100000\n".encode())
        self.gid_map.write_bytes(f"0 {gid_base} 100000\n".encode())
        (self.proc / "status").write_bytes(
            ("Name:\tfixture\nGid:\t" + "\t".join([str(gid_base)] * 4) + "\n").encode())
        self.apk = self.root / "ordinary-fixture.bin"
        self.body = (b"ordinary host mapping control body\n" * 3000) + b"EOF"
        self.apk.write_bytes(self.body)
        self.apk.chmod(0o600)
        self.sha = hashlib.sha256(self.body).hexdigest()
        actual = self.apk.stat()
        self.apk_node = (actual.st_dev, actual.st_ino)
        self.owners = (uid_base + 1000, gid_base + 1000)
        self.proc_fd = os.open(self.proc, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.stack.callback(REAL_CLOSE, self.proc_fd)
        self.apk_fds = []
        self.guard_calls = 0
        self.target_verify_calls = 0
        self.view_close_calls = 0
        self.target = types.SimpleNamespace(proc_fd=self.proc_fd,
            expected={"pid": 4321, "uid": [str(uid_base)] * 4},
            lease=lambda: nullcontext(), verify=self.verify_target, open_root=self.open_root)
        # Bypass only Main admission for this offline fixture. The actual helper
        # still requires this exact original class and checks all live-map logic.
        self.view = m.MainView.__new__(m.MainView)
        self.view.closed = False
        self.view.target = self.target
        self.view.baseline = types.SimpleNamespace(value={"framework_epoch": {
            "binding": {"processes": {"init": {
                "host_pid": 4321, "uids": [uid_base] * 4}}}}})
        self.view.guard = self.guard
        self.view.close = self.close_view
        self.stack.enter_context(patch.object(os, "fstat", side_effect=self.stat_boundary))
        self.stack.enter_context(patch.object(m.fcntl, "ioctl", side_effect=self.namespace_boundary))
        self.stack.enter_context(patch.object(c, "APK_BYTES", len(self.body)))
        self.stack.enter_context(patch.object(c, "APK_SHA256", self.sha))
        fd = self.open_root(GUEST_PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            observed = c.identity(fd)
        finally:
            REAL_CLOSE(fd)
        self.artifact = {"guest_path": GUEST_PATH, "bytes": len(self.body),
                         "sha256": self.sha, "stat_file": observed}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stack.close()

    def stat_boundary(self, fd):
        info = REAL_FSTAT(fd)
        if (info.st_dev, info.st_ino) != self.apk_node:
            return info
        values = {key: getattr(info, key) for key in STAT_FIELDS}
        values["st_uid"], values["st_gid"] = self.owners
        return types.SimpleNamespace(**values)

    def namespace_boundary(self, fd, request):
        if request != 0xb703:
            raise AssertionError("unexpected ioctl in ordinary fixture")
        info = REAL_FSTAT(fd)
        named = (self.proc / "ns/user").stat()
        if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
            # A replaced named namespace may leave an earlier genuine FD open.
            if info.st_size != len(b"injected namespace ioctl boundary\n"):
                raise AssertionError("ioctl on a non-namespace fixture FD")
        return 0x10000000

    def verify_target(self):
        self.target_verify_calls += 1

    def guard(self):
        self.guard_calls += 1
        if self.view.closed:
            raise RuntimeError("fixture Main was closed")
        return "FIXTURE_ADMISSION_NO_ANDROID_CREDIT"

    def close_view(self):
        self.view_close_calls += 1
        self.view.closed = True

    def open_root(self, path, flags):
        if path != GUEST_PATH or flags != os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC:
            raise AssertionError("unexpected installed path or flags")
        fd = os.open(self.apk, flags)
        self.apk_fds.append(fd)
        return fd

    def held(self):
        return c.HeldFirefoxAPK(self.target, self.artifact,
            deadline=time.monotonic() + 10, main_view=self.view, original_common=m)


class MapRangeControls(unittest.TestCase):
    def test_zero_shifted_distinct_uid_gid_and_upper_endpoint(self):
        for raw, guest, expected in ((b"0 0 100000\n", 1000, 1000),
                (b"0 100000 100000\n", 1000, 101000),
                (b"0 200000 100000\n", 1000, 201000),
                (b"0 4294867295 100000\n", 99999, 4294967294)):
            with self.subTest(raw=raw, guest=guest):
                self.assertEqual(m._mapped_guest_id(raw, guest), expected)

    def test_malformed_partial_multiple_and_overflow_ranges_rejected(self):
        for raw in (b"", b"0 0 100000", b"0 0 100000\n0 200000 100000\n",
                    b"1 100000 100000\n", b"0 100000 99999\n",
                    b"0 4294867297 100000\n", b"0 0 4294967296\n",
                    b"0 -1 100000\n", b"0 0 00000000000\n", b" " * 8193,
                    "0 100000 100000\n"):
            with self.subTest(raw=repr(raw)[:100]), self.assertRaises(RuntimeError):
                m._mapped_guest_id(raw, 1000)

    def test_boolean_negative_and_non_user_zero_ids_rejected(self):
        for guest in (True, False, -1, 100000, 2**32, 1000.0, "1000", None):
            with self.subTest(guest=guest), self.assertRaises(RuntimeError):
                m._mapped_guest_id(b"0 100000 100000\n", guest)


class InstalledOwnerControls(unittest.TestCase):
    def assert_closed(self, fd):
        with self.assertRaises(OSError) as caught:
            REAL_FSTAT(fd)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_shifted_uid_gid_use_real_fd_and_complete_body(self):
        with ProcFixture() as fixture:
            held = fixture.held()
            try:
                self.assertEqual((held.before["stat_file"]["uid"],
                                  held.before["stat_file"]["gid"]), (101000, 201000))
                self.assertEqual(held.before["bytes"], len(fixture.body))
                self.assertEqual(held.before["sha256"], hashlib.sha256(fixture.body).hexdigest())
                self.assertTrue(held.before["same_fd_streamed"])
                self.assertEqual(held.revalidate(), held.before)
                self.assertIs(held.main_view, fixture.view)
                self.assertGreater(fixture.guard_calls, 4)
                self.assertEqual(fixture.view_close_calls, 0)
                fd = held.fd
            finally:
                held.close()
            self.assert_closed(fd)
            self.assertFalse(fixture.view.closed)
            self.assertEqual(fixture.view_close_calls, 0)

    def test_unshifted_mapping_also_requires_actual_owner(self):
        with ProcFixture(uid_base=0, gid_base=0) as fixture:
            held = fixture.held()
            try:
                self.assertEqual(held.revalidate()["stat_file"]["uid"], 1000)
            finally:
                held.close()

    def test_wrong_uid_and_wrong_gid_each_refuse_and_release_fd(self):
        for owners in ((1000, 201000), (101000, 1000), (1000, 1000)):
            with self.subTest(owners=owners), ProcFixture() as fixture:
                fixture.owners = owners
                fixture.artifact["stat_file"].update(uid=owners[0], gid=owners[1])
                with self.assertRaisesRegex(c.Refused, "NOT_MAPPED_ANDROID_SYSTEM"):
                    fixture.held()
                self.assert_closed(fixture.apk_fds[-1])
                self.assertEqual(fixture.view_close_calls, 0)

    def test_mapping_helper_required_before_file_is_opened(self):
        with ProcFixture() as fixture:
            before = len(fixture.apk_fds)
            with patch.object(m, "mapped_file_info", None):
                with self.assertRaisesRegex(c.Refused, "MAPPING_HELPER_REQUIRED"):
                    fixture.held()
            self.assertEqual(len(fixture.apk_fds), before)

    def test_wrong_original_view_or_target_refuses_before_file_open(self):
        with ProcFixture() as fixture:
            before = len(fixture.apk_fds)
            for wrong in (None, types.SimpleNamespace(target=fixture.target, closed=False)):
                with self.subTest(view=wrong), self.assertRaisesRegex(c.Refused, "SAME_ORIGINAL_MAIN"):
                    c.HeldFirefoxAPK(fixture.target, fixture.artifact,
                        deadline=time.monotonic() + 10, main_view=wrong, original_common=m)
            fixture.view.target = object()
            with self.assertRaisesRegex(c.Refused, "SAME_ORIGINAL_MAIN"):
                fixture.held()
            self.assertEqual(len(fixture.apk_fds), before)

    def test_main_target_replaced_before_verify_refuses(self):
        with ProcFixture() as fixture:
            held = fixture.held()
            try:
                fixture.view.target = object()
                with self.assertRaisesRegex(c.Refused, "SAME_ORIGINAL_MAIN"):
                    held.verify()
            finally:
                held.close()

    def test_main_target_replaced_during_mapping_refuses_and_releases(self):
        with ProcFixture() as fixture:
            original = m.mapped_file_info
            def replace_target(*args):
                result = original(*args)
                fixture.view.target = object()
                return result
            with patch.object(m, "mapped_file_info", replace_target):
                with self.assertRaisesRegex(c.Refused, "SAME_ORIGINAL_MAIN"):
                    fixture.held()
            self.assert_closed(fixture.apk_fds[-1])

    def test_changed_map_rejected_on_verify_and_revalidate(self):
        for map_name in ("uid_map", "gid_map"):
            for phase in ("verify", "revalidate"):
                with self.subTest(map_name=map_name, phase=phase), ProcFixture() as fixture:
                    held = fixture.held()
                    try:
                        path = getattr(fixture, map_name)
                        path.write_bytes(path.read_bytes().replace(b"100000\n", b"200000\n"))
                        with self.assertRaisesRegex(RuntimeError, "NAMESPACE_OR_ID_MAP_CHANGED"):
                            getattr(held, phase)()
                    finally:
                        held.close()

    def test_namespace_inode_replaced_after_initial_mapping_refuses(self):
        with ProcFixture() as fixture:
            held = fixture.held()
            try:
                replacement = fixture.proc / "ns/replacement"
                replacement.write_bytes(b"injected namespace ioctl boundary\n")
                replacement.replace(fixture.proc / "ns/user")
                with self.assertRaisesRegex(RuntimeError, "NAMESPACE_OR_ID_MAP_CHANGED"):
                    held.revalidate()
            finally:
                held.close()

    def test_mapping_changes_within_observation_refuse(self):
        with ProcFixture() as fixture:
            original_guard = fixture.view.guard
            def mutate_after_first_guard():
                value = original_guard()
                if fixture.guard_calls == 2:
                    fixture.gid_map.write_bytes(b"0 200000 200000\n")
                return value
            fixture.view.guard = mutate_after_first_guard
            with self.assertRaisesRegex(RuntimeError, "MAPPING_CHANGED_DURING_FILE_OBSERVATION"):
                fixture.held()
            self.assert_closed(fixture.apk_fds[-1])

    def test_original_main_root_binding_mismatch_refuses(self):
        with ProcFixture() as fixture:
            fixture.target.expected["uid"] = ["0"] * 4
            with self.assertRaisesRegex(RuntimeError, "ORIGINAL_MAIN_ROOT_UID"):
                fixture.held()
            self.assert_closed(fixture.apk_fds[-1])

    def test_replaced_mapper_after_construction_refuses(self):
        with ProcFixture() as fixture:
            held = fixture.held()
            try:
                with patch.object(m, "mapped_file_info", lambda *args: self.fail("new mapper called")):
                    with self.assertRaisesRegex(c.Refused, "SAME_ORIGINAL_MAIN"):
                        held.verify()
            finally:
                held.close()

    def test_mapper_stat_cannot_disagree_with_real_held_file(self):
        with ProcFixture() as fixture:
            original = m.mapped_file_info
            def changed_inode(*args):
                info, owners = original(*args)
                values = {key: getattr(info, key) for key in STAT_FIELDS}
                values["st_ino"] += 1
                return types.SimpleNamespace(**values), owners
            with patch.object(m, "mapped_file_info", changed_inode):
                with self.assertRaisesRegex(c.Refused, "MAPPED_OWNER_FILE_IDENTITY_CHANGED"):
                    fixture.held()
            self.assert_closed(fixture.apk_fds[-1])

    def test_named_inode_replacement_does_not_accept_identical_bytes(self):
        with ProcFixture() as fixture:
            held = fixture.held()
            try:
                replacement = fixture.root / "same-bytes.bin"
                replacement.write_bytes(fixture.body)
                fixture.apk.rename(fixture.root / "held-original.bin")
                replacement.rename(fixture.apk)
                # Rename changes ctime on some filesystems; either the original
                # full identity guard or the named-inode guard must reject it.
                with self.assertRaises(c.Refused):
                    held.verify()
            finally:
                held.close()

    def test_body_hash_is_still_mandatory_after_valid_owner_mapping(self):
        with ProcFixture() as fixture:
            with patch.object(c, "APK_SHA256", "0" * 64):
                fixture.artifact["sha256"] = "0" * 64
                with self.assertRaisesRegex(c.Refused, "COMPLETE_BODY_OR_IDENTITY_CHANGED"):
                    fixture.held()
            self.assert_closed(fixture.apk_fds[-1])

    def test_primary_mapping_error_survives_cleanup_error_and_fd_closes(self):
        with ProcFixture() as fixture:
            original_close = c.HeldFirefoxAPK.close
            primary = RuntimeError("injected mapping failure")
            def release_then_fail(held):
                original_close(held)
                raise OSError("injected post-release failure")
            with patch.object(m, "mapped_file_info", side_effect=primary), \
                 patch.object(c.HeldFirefoxAPK, "close", release_then_fail):
                with self.assertRaises(RuntimeError) as caught:
                    fixture.held()
            self.assertIs(caught.exception, primary)
            self.assertIn("FIREFOX_CONSTRUCTION_CLEANUP:OSError", primary.__notes__)
            self.assert_closed(fixture.apk_fds[-1])
            self.assertEqual(fixture.view_close_calls, 0)


class FlowIntegrationControls(unittest.TestCase):
    def common(self, *, fail_guard=False, fail_close=False):
        common = types.ModuleType("fixture_flow_original_common")
        common.constructed = []
        class OriginalView:
            def __init__(self, target):
                self.target = target
                self.closed = False
                self.close_count = 0
                common.constructed.append(self)
            def guard(self):
                if fail_guard:
                    raise RuntimeError("injected original Main guard failure")
                return "fixture"
            def close(self):
                self.close_count += 1
                self.closed = True
                if fail_close:
                    raise OSError("injected original Main close failure")
        common.MainView = OriginalView
        common.mapped_file_info = lambda *args: None
        return common

    def test_original_view_exact_identity_and_one_factory_call_per_flow(self):
        common = self.common()
        adapter = c.StreamingCommon(common, time.monotonic() + 10)
        target = object()
        view = adapter.MainView(target)
        self.assertIs(type(view), common.MainView)
        self.assertIs(view, common.constructed[0])
        self.assertIs(view.target, target)
        with self.assertRaisesRegex(c.Refused, "ONE_ORIGINAL_MAIN_VIEW"):
            adapter.MainView(target)
        self.assertEqual(len(common.constructed), 1)
        self.assertFalse(view.closed)

    def test_missing_mapper_refuses_before_original_main_constructor(self):
        common = self.common()
        del common.mapped_file_info
        adapter = c.StreamingCommon(common, time.monotonic() + 10)
        with self.assertRaisesRegex(c.Refused, "MAIN_MAPPING_SOURCE_REQUIRED"):
            adapter.MainView(object())
        self.assertEqual(common.constructed, [])

    def test_custody_passes_same_original_view_and_rejects_other_target(self):
        common = self.common()
        adapter = c.StreamingCommon(common, time.monotonic() + 10)
        target = object()
        with patch.object(c, "CombinedCustody") as combined:
            with self.assertRaisesRegex(c.Refused, "ORIGINAL_FLOW_MAIN"):
                adapter.HeldArtifacts(target, [])
            view = adapter.MainView(target)
            with self.assertRaisesRegex(c.Refused, "ORIGINAL_FLOW_MAIN"):
                adapter.HeldArtifacts(object(), [])
            self.assertFalse(combined.called)
            adapter.HeldArtifacts(target, ["fixture identities"])
            combined.assert_called_once_with(common, target, ["fixture identities"],
                                             adapter.deadline, main_view=view)

    def test_failed_view_post_guard_preserves_primary_and_closes_unassigned_view(self):
        common = self.common(fail_guard=True, fail_close=True)
        adapter = c.StreamingCommon(common, time.monotonic() + 10)
        with self.assertRaisesRegex(RuntimeError, "original Main guard failure") as caught:
            adapter.MainView(object())
        self.assertEqual(common.constructed[0].close_count, 1)
        self.assertTrue(common.constructed[0].closed)
        self.assertIsNone(adapter._view)
        self.assertIn("FIREFOX_MAIN_VIEW_CONSTRUCTION_CLEANUP:OSError", caught.exception.__notes__)
        with self.assertRaisesRegex(c.Refused, "ONE_ORIGINAL_MAIN_VIEW"):
            adapter.MainView(object())

    def test_combined_helper_failure_releases_firefox_without_closing_view(self):
        with ProcFixture() as fixture:
            primary = RuntimeError("injected helper custody failure")
            old_close = c.HeldFirefoxAPK.close
            released = []
            def close_then_fail(held):
                released.append(held.fd)
                old_close(held)
                raise OSError("injected Firefox release acknowledgment failure")
            identities = [{"metadata": {"package": c.PACKAGE},
                           "artifacts": [fixture.artifact]},
                          {"metadata": {"package": "fixture.helper"}, "artifacts": []}]
            with patch.object(m, "HeldArtifacts", side_effect=primary), \
                 patch.object(c.HeldFirefoxAPK, "close", close_then_fail):
                with self.assertRaises(RuntimeError) as caught:
                    c.CombinedCustody(m, fixture.target, identities,
                        time.monotonic() + 10, main_view=fixture.view)
            self.assertIs(caught.exception, primary)
            self.assertIn("COMBINED_CUSTODY_CONSTRUCTION_CLEANUP:OSError", primary.__notes__)
            self.assertEqual(len(released), 1)
            with self.assertRaises(OSError) as closed:
                REAL_FSTAT(released[0])
            self.assertEqual(closed.exception.errno, errno.EBADF)
            self.assertEqual(fixture.view_close_calls, 0)

    def test_combined_close_attempts_both_resources_after_first_error(self):
        calls = []
        primary = RuntimeError("first resource close failed")
        def helper_close():
            calls.append("helper")
            raise primary
        combined = c.CombinedCustody.__new__(c.CombinedCustody)
        combined.helpers = types.SimpleNamespace(close=helper_close)
        combined.firefox = types.SimpleNamespace(close=lambda: calls.append("firefox"))
        with self.assertRaises(RuntimeError) as caught:
            combined.close()
        self.assertIs(caught.exception, primary)
        self.assertEqual(calls, ["helper", "firefox"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
