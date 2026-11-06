"""Local boundary tests; no device, Android command or real APK is invoked."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
SOURCE = Path(__file__).with_name("audit_successor_apks.py")
spec = importlib.util.spec_from_file_location("apk_audit_tested", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AuditBoundaries(unittest.TestCase):
    def test_fixed_roster_includes_system_and_original_eight(self):
        self.assertEqual(len(m.PACKAGES), 45)
        self.assertEqual(len(set(m.PACKAGES)), 45)
        req = {"schema": "pocket4-successor-apk-audit-request-v1", "guard": {}, "app_scope": {},
               "packages": ["com.android.settings", "org.fcitx.fcitx5.android"],
               "output_root": "UNBOUND", "official_release_assets": None}
        m.validate_request(req)
        bad = copy.deepcopy(req); bad["packages"] += ["com.android.settings"]
        with self.assertRaisesRegex(RuntimeError, "EXPLICIT_REVIEWED"):
            m.validate_request(bad)
        bad = copy.deepcopy(req); bad["packages"] = ["com.unreviewed.arbitrary"]
        with self.assertRaisesRegex(RuntimeError, "EXPLICIT_REVIEWED"):
            m.validate_request(bad)

    def test_base_split_metadata_does_not_invent_missing_fields(self):
        base = m.badging_manifest(b"package: name='com.example.app' versionCode='42' versionName='1.2'\nsdkVersion:'24'\ntargetSdkVersion:'36'\nnative-code: 'arm64-v8a' 'armeabi-v7a'\n")
        self.assertEqual(base["version_name"], "1.2")
        self.assertEqual(base["native_abis"], ["arm64-v8a", "armeabi-v7a"])
        self.assertIsNone(base["split_name"])
        split = m.badging_manifest(b"package: name='com.example.app' versionCode='42' split='config.arm64_v8a'\n")
        self.assertEqual(split["split_name"], "config.arm64_v8a")
        self.assertIsNone(split["version_name"])
        self.assertIsNone(split["min_sdk"])
        self.assertEqual(split["native_abis"], [])
        with self.assertRaisesRegex(RuntimeError, "UNPARSED"):
            m.badging_manifest(b"package: name='com.example.app' versionCode='42' versionName='1.2'trailing'\n")

    def test_permission_names_and_typed_attrs_are_preserved_not_granted(self):
        text = b'''N: android=http://schemas.android.com/apk/res/android
  E: manifest (line=2)
    A: package="com.example.app" (Raw: "com.example.app")
    E: uses-permission (line=3)
      A: android:name(0x01010003)="       android.permission.VIBRATE" (Raw: "       android.permission.VIBRATE")
      A: android:maxSdkVersion(0x01010271)=(type 0x10)0x20
    E: permission (line=4)
      A: android:name(0x01010003)="com.example.permission" (Raw: "com.example.permission")
      A: android:protectionLevel(0x01010009)=(type 0x11)0x2
    E: application (line=5)
      E: uses-permission (line=6)
        A: android:name(0x01010003)="not.a.manifest.permission"
'''
        value = m.xml_permissions(text)
        self.assertEqual(len(value["entries"]), 2)
        self.assertEqual(value["entries"][0]["name"], "       android.permission.VIBRATE")
        self.assertEqual(value["entries"][0]["attributes"]["android:maxSdkVersion"], "(type 0x10)0x20")
        self.assertEqual(value["entries"][1]["tag"], "permission")
        self.assertEqual(value["effective_permission_grants"], "UNKNOWN_NOT_QUERIED")

    def test_signature_failure_does_not_become_verified_from_printed_certificate(self):
        raw = ("Verifies\nVerified using v1 scheme (JAR signing): false\nVerified using v2 scheme (APK Signature Scheme v2): true\nSigner #1 certificate SHA-256 digest: " + "ab" * 32 + "\n").encode()
        command = {"returncode": 0, "joined": True, "output_capture_complete": True, "timed_out": False}
        value = m.parse_signature(raw, command)
        self.assertTrue(value["verified"])
        self.assertFalse(value["API_minimum_override_used"])
        command["returncode"] = 1
        self.assertFalse(m.parse_signature(raw, command)["verified"])

    def test_actual_fd_pass_and_child_pipe_retirement(self):
        with tempfile.TemporaryFile(dir="/dev/shm") as f:
            f.write(b"public test bytes"); f.flush(); f.seek(0)
            receipt = {}
            output = m.run_tool([sys.executable, "-c", "import os,sys;sys.stdout.buffer.write(os.read(int(sys.argv[1]),64))", str(f.fileno())], [f.fileno()], receipt, time.monotonic() + 3)
            self.assertEqual(output["stdout"], b"public test bytes")
            self.assertEqual(output["stderr"], b"")
            self.assertTrue(receipt["joined"] and receipt["pipes_closed"] and receipt["output_capture_complete"])
            self.assertEqual(receipt["returncode"], 0)

    def test_timeout_preserves_partial_output_and_joins_only_owned_child(self):
        receipt = {}
        output = m.run_tool([sys.executable, "-c", "import sys,time;print('prefix',flush=True);time.sleep(10)"], [], receipt, time.monotonic() + .15)
        self.assertEqual(output["stdout"], b"prefix\n")
        self.assertTrue(receipt["timed_out"] and receipt["joined"] and receipt["pipes_closed"] and receipt["own_group_kill_requested"])
        self.assertFalse(receipt["output_capture_complete"])

    def test_output_bound_is_explicit_and_cannot_report_complete(self):
        previous = m.MAX_TOOL_OUTPUT
        m.MAX_TOOL_OUTPUT = 1024
        try:
            receipt = {}
            output = m.run_tool([sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*4096);sys.stdout.flush()"], [], receipt, time.monotonic() + 3)
        finally:
            m.MAX_TOOL_OUTPUT = previous
        self.assertEqual(len(output["stdout"]), 1024)
        self.assertTrue(receipt["output_truncated"] and receipt["joined"] and receipt["pipes_closed"])
        self.assertFalse(receipt["output_capture_complete"])

    def test_large_stat_evidence_retains_exact_python_integers(self):
        value = {"st_mtime_ns": 1793961899814391132}
        self.assertEqual(json.loads(m.canonical(value)), value)
        changed = {"st_mtime_ns": int(float(value["st_mtime_ns"]))}
        self.assertNotEqual(m.sha(m.canonical(value)), m.sha(m.canonical(changed)))


if __name__ == "__main__":
    unittest.main()
