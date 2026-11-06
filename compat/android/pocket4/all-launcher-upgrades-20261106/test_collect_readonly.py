"""Focused offline controls. They never invoke collect(), a guard, or Android."""
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).with_name("collect_readonly.py")
spec = importlib.util.spec_from_file_location("collector_under_test", SOURCE)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

# Hand-written ABX0 wire from the inspected AOSP protocol:
# startDoc, <r n=int(7)><x/></r>, endDoc; global intern ids r=0,n=1,x=2.
WIRE = bytes.fromhex(
    "41425800 10 32ffff000172 6fffff00016e00000007 "
    "32ffff000178 330002 330000 11"
)


class ParserControls(unittest.TestCase):
    def test_known_wire_and_modified_utf8(self):
        root = c.parse_xml(WIRE)
        self.assertEqual((root.tag, root.attrs, [x.tag for x in root.children]),
                         ("r", {"n": 7}, ["x"]))
        self.assertEqual(c.modified_utf8(bytes.fromhex("e4b8ade69687f09f9880")), "中文😀")
        self.assertEqual(c.modified_utf8(bytes.fromhex("eda0bdedb880")), "😀")

    def test_truncation_bad_reference_type_and_close_are_rejected(self):
        cases = {
            "missing_end_document": WIRE[:-1],
            "truncated_intern_string": bytes.fromhex("41425800 10 32ffff0005 6162"),
            "uninitialized_intern_reference": bytes.fromhex("41425800 10 320000"),
            "unknown_token": bytes.fromhex("41425800 10 1e"),
            "wrong_start_tag_type": bytes.fromhex("41425800 10 22ffff000172"),
            "mismatched_close": WIRE.replace(bytes.fromhex("330002"), bytes.fromhex("330000")),
            "trailing_bytes": WIRE + b"\0",
            "duplicate_attribute": bytes.fromhex(
                "41425800 10 32ffff000172 6fffff00016e00000007 "
                "6f000100000008 330000 11"),
        }
        for name, raw in cases.items():
            with self.subTest(name=name), self.assertRaises(c.Rejected):
                c.parse_xml(raw)
        for raw in (b"\xC0\xAF", b"\x80", b"\xE0\x80\x80", b"\xED\xA0\xBD"):
            with self.subTest(utf8=raw.hex()), self.assertRaises(c.Rejected):
                c.modified_utf8(raw)

    def test_entities_dtd_and_excessive_depth_are_rejected(self):
        for raw in (
            b'<!DOCTYPE r [<!ENTITY a "x">]><r/>',
            b'<r value="&amp;"/>',
            b'<?external instruction?><r/>',
            b"<r>" * 65 + b"</r>" * 65,
            bytes.fromhex("41425800 10 a6"),
        ):
            with self.subTest(raw=raw[:30]), self.assertRaises(c.Rejected):
                c.parse_xml(raw)


class PermissionControls(unittest.TestCase):
    def test_uncovered_package_and_missing_permission_remain_unknown(self):
        root = c.parse_xml(
            b'<runtime-permissions><package name="another.package">'
            b'<item name="android.permission.ACCESS_FINE_LOCATION" granted="false"/>'
            b'</package></runtime-permissions>')
        out = c.permission_projection(root, "com.sankuai.meituan.takeoutnew", 10147)
        self.assertFalse(out["coverage"])
        self.assertEqual(out["effective_grant_state"], "UNKNOWN")
        self.assertEqual(out["entries"], [])
        self.assertTrue(out["absent_permissions_not_denied"])

    def test_raw_access_zero_or_nonzero_flags_do_not_become_grants(self):
        root = c.parse_xml(
            b'<access><app-id-permissions><app-id id="10147">'
            b'<permission name="android.permission.ACCESS_FINE_LOCATION" flags="0"/>'
            b'<permission name="android.permission.ACCESS_COARSE_LOCATION" flags="16"/>'
            b'</app-id></app-id-permissions></access>')
        out = c.permission_projection(root, "com.sankuai.meituan.takeoutnew", 10147)
        self.assertTrue(out["coverage"])
        self.assertEqual(out["effective_grant_state"], "UNKNOWN")
        self.assertEqual(len(out["entries"]), 2)
        self.assertTrue(all("stored_granted" not in item for item in out["entries"]))

    def test_observed_noncanonical_name_is_never_normalized_to_a_real_permission(self):
        root = c.parse_xml(
            b'<access><app-id-permissions><app-id id="10143">'
            b'<permission name="       android.permission.VIBRATE" flags="2"/>'
            b'</app-id></app-id-permissions></access>')
        out = c.permission_projection(root, "com.lianjia.beike", 10143)
        self.assertEqual(out["entries"][0]["name"], "       android.permission.VIBRATE")
        self.assertTrue(out["entries"][0]["noncanonical_name_preserved"])
        self.assertEqual(out["effective_grant_state"], "UNKNOWN")
        self.assertNotIn("stored_granted", out["entries"][0])

    def test_explicit_saved_denial_is_not_live_authority(self):
        root = c.parse_xml(
            b'<runtime-permissions><package name="com.sankuai.meituan.takeoutnew">'
            b'<item name="android.permission.ACCESS_FINE_LOCATION" granted="false" flags="0"/>'
            b'</package></runtime-permissions>')
        out = c.permission_projection(root, "com.sankuai.meituan.takeoutnew", 10147)
        self.assertIs(out["entries"][0]["stored_granted"], False)
        self.assertEqual(out["effective_grant_state"], "UNKNOWN")


class SignatureReferenceControls(unittest.TestCase):
    @staticmethod
    def fixture():
        # Synthetic evidence objects exercise reference logic; they are not APK
        # files, verifier executions, signing evidence, or device qualification.
        package, cert = "com.Hyatt.hyt", "a" * 64
        artifacts = [("base.apk", b"test-base", None),
                     ("split_config.apk", b"test-split", "config.arm64_v8a")]
        old, current = [], []
        for name, body, split in artifacts:
            identity = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            current.append({"name": name, **identity})
            old.append({**identity, "held_file_unchanged": True,
                "manifest": {"package": package, "version_code": 1, "version_name": "1",
                             "split_name": split, "declared_min_sdk": "35",
                             "declared_target_sdk": "36", "embedded_native_abis": []},
                "signature": {"status": "VERIFIED", "verified": True, "joined": True,
                    "timed_out": False, "tool_exit_code": 0,
                    "signer_certificate_sha256": [cert]}})
        history = {"package": package, "android_user": 0, "apks": old,
                   "identity": {"uid": 10138, "version_code": 1},
                   "signature_complete": True, "base_split_certificates_equal": True,
                   "current_path_inode_readback_equal": True}
        now = {"package": package, "uid": 10138, "version_code": 1, "apks": current,
               "package_manager_signing": {"certificate_sha256": [cert]}}
        return package, history, now

    def test_exact_set_is_only_historical_reference_and_changed_split_loses_credit(self):
        package, history, now = self.fixture()
        positive = c.historical_projection(package, copy.deepcopy(now), history, "f" * 64)
        self.assertEqual(positive["signature"]["status"],
                         "HISTORICAL_VERIFIED_REFERENCE_FOR_IDENTICAL_APK_BYTES")
        self.assertIs(positive["signature"]["new_signature_verification_performed"], False)
        for change in ("mismatch", "missing", "extra"):
            altered = copy.deepcopy(now)
            if change == "mismatch":
                altered["apks"][1]["sha256"] = "b" * 64
            elif change == "missing":
                altered["apks"].pop()
            else:
                altered["apks"].append({"name": "extra.apk", "bytes": 5, "sha256": "c" * 64})
            with self.subTest(change=change):
                negative = c.historical_projection(package, altered, history, "f" * 64)
                self.assertFalse(negative["comparison"]["all_base_and_split_bytes_identical"])
                self.assertEqual(negative["signature"]["status"], "UNKNOWN_CURRENT_CONTENT_NOT_FULLY_MATCHED")
                self.assertNotIn("signer_certificate_sha256", negative["signature"])


class FilesystemControls(unittest.TestCase):
    def test_same_bytes_replacement_fails_final_path_recheck_and_closes_descriptors(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / "base.apk").write_bytes(b"identical bytes")
            fds = c.Descriptors()
            root = fds.own(os.open(path, os.O_PATH | os.O_DIRECTORY))
            reader = c.Reader(root, fds, c.Budget(10))
            try:
                raw, observed = reader.read("/base.apk", 100)
                self.assertEqual(raw, b"identical bytes")
                self.assertTrue(observed["held_and_path_unchanged"])
                (path / "replacement.apk").write_bytes(raw)
                os.replace(path / "replacement.apk", path / "base.apk")
                with self.assertRaisesRegex(c.Rejected, "CURRENT_PATH_INODE_OR_METADATA_CHANGED"):
                    reader.recheck()
            finally:
                fds.close_remaining()
            self.assertEqual(fds.acquired, fds.closed)
            self.assertFalse(fds.live)
            self.assertFalse(fds.close_errors)

    def test_symlink_and_hardlink_inputs_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / "original").write_bytes(b"not a private source")
            os.symlink("original", path / "link")
            os.link(path / "original", path / "hard")
            fds = c.Descriptors()
            root = fds.own(os.open(path, os.O_PATH | os.O_DIRECTORY))
            reader = c.Reader(root, fds, c.Budget(10))
            try:
                with self.assertRaises(OSError):
                    reader.read("/link", 100)
                with self.assertRaisesRegex(c.Rejected, "SINGLE_REGULAR_FILE_BOUND"):
                    reader.read("/hard", 100)
            finally:
                fds.close_remaining()
            self.assertEqual(fds.acquired, fds.closed)
            self.assertFalse(fds.live)


if __name__ == "__main__":
    unittest.main(verbosity=2)

