"""Offline controls for launcher/system/shared-UID metadata; no device calls."""
import sys
sys.dont_write_bytecode = True
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import zlib


PATH = Path(__file__).with_name("collect_launcher_metadata.py")
spec = importlib.util.spec_from_file_location("launcher_metadata_under_test", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
c, UNUSED_PATH = m.load_base()

PACKAGES = b'''<packages>
<package name="com.android.settings" sharedUserId="1000" version="37"
 codePath="/system/priv-app/Settings/Settings.apk" publicFlags="1">
 <sigs count="1"><cert index="0" key="010203"/></sigs></package>
<package name="com.android.documentsui" sharedUserId="1000" version="37"
 codePath="/system_ext/priv-app/DocumentsUI"><sigs count="1"><cert index="0"/></sigs></package>
<package name="com.android.calendar" userId="10042" version="37"
 codePath="/product/app/Calendar"><sigs count="0"/></package>
<package name="com.lianjia.beike" userId="10143" version="3066010"
 codePath="/data/app/observed-beike"><sigs count="1"><cert index="0"/></sigs></package>
<shared-user name="android.uid.system" userId="1000">
 <sigs count="1"><cert index="0"/></sigs>
 <perms><item name="android.permission.MANAGE_USERS" granted="true" flags="0"/></perms>
</shared-user></packages>'''


def project():
    root = c.parse_xml(PACKAGES)
    packages = {"com.android.settings", "com.android.documentsui", "com.android.calendar", "com.lianjia.beike"}
    return m.package_projection(c, root, packages)


class LauncherControls(unittest.TestCase):
    def test_observed_catalog_all_45_and_multiple_components_are_preserved(self):
        actual = json.loads((PATH.parent / "reference/current-native-launcher-catalog.json").read_bytes())["catalog"]
        out = m.catalog_projection(c, m.canonical(actual), 3588089)
        self.assertEqual(out["entry_count"], 45)
        self.assertEqual(out["package_count"], 45)
        self.assertFalse(out["cache_freshness_proven"])
        self.assertFalse(out["current_android_launcher_resolution_proven"])
        extra = dict(actual["applications"][0], component="com.Hyatt.hyt/com.hyt.SecondActivity")
        actual["applications"].append(extra)
        changed = m.catalog_projection(c, m.canonical(actual), 3588089)
        self.assertEqual(changed["entry_count"], 46)
        self.assertEqual(changed["package_count"], 45)
        self.assertNotEqual(out["package_component_sha256"], changed["package_component_sha256"])

    def test_wrong_epoch_host_duplicate_and_foreign_component_are_rejected(self):
        fixture = {"ok": True, "state": "running", "host_pid": 3588089,
                   "applications": [{"name": "Test", "package": "com.test.app", "component": "com.test.app/.Main"}]}
        with self.assertRaisesRegex(c.Rejected, "MAIN_IDENTITY"):
            m.catalog_projection(c, m.canonical(fixture), 99)
        fixture["applications"].append(dict(fixture["applications"][0]))
        with self.assertRaisesRegex(c.Rejected, "DUPLICATE"):
            m.catalog_projection(c, m.canonical(fixture), 3588089)
        fixture["applications"] = [dict(fixture["applications"][0], component="com.foreign/.Main")]
        with self.assertRaisesRegex(c.Rejected, "COMPONENT_SCOPE"):
            m.catalog_projection(c, m.canonical(fixture), 3588089)


class PackageControls(unittest.TestCase):
    def test_system_shared_uid_and_non_base_apk_names_are_metadata_only(self):
        apps, unused_nodes, unused_shared = project()
        settings = apps["com.android.settings"]
        self.assertEqual(settings["uid"], 1000)
        self.assertTrue(settings["uid_below_10000"])
        self.assertEqual(settings["shared_user"]["name"], "android.uid.system")
        self.assertEqual(settings["code_path"], "/system/priv-app/Settings/Settings.apk")
        self.assertFalse(settings["code_path_opened"])
        self.assertFalse(settings["apk_set_hashed"])
        self.assertEqual(settings["package_manager_signing"]["certificate_sha256"], [hashlib.sha256(b"\x01\x02\x03").hexdigest()])
        self.assertFalse(settings["package_manager_signing"]["cryptographic_verification_performed"])
        self.assertEqual(apps["com.android.calendar"]["package_manager_signing"]["status"],
                         "UNKNOWN_EMPTY_PACKAGE_MANAGER_SIGNATURE_RECORD")

    def test_restriction_fields_are_never_defaulted(self):
        root = c.parse_xml(b'<package-restrictions><pkg name="com.android.settings" stopped="false">'
                          b'<disabled-components><item name="com.android.settings.Settings"/></disabled-components>'
                          b'</pkg></package-restrictions>')
        row = m.restrictions_projection(c, root, {"com.android.settings"})["com.android.settings"]
        self.assertNotIn("enabled", row["recorded_fields"])
        self.assertTrue(row["absent_fields_not_defaulted"])
        self.assertEqual(row["recorded_components"]["disabled-components"], ["com.android.settings.Settings"])


class PermissionControls(unittest.TestCase):
    def test_shared_runtime_subject_is_deduplicated_without_effective_grants(self):
        apps, nodes, shared = project()
        access = c.parse_xml(b'<access><app-id-permissions><app-id id="1000">'
            b'<permission name="android.permission.ACCESS_FINE_LOCATION" flags="16"/>'
            b'</app-id><app-id id="10143">'
            b'<permission name="       android.permission.VIBRATE" flags="2"/>'
            b'</app-id></app-id-permissions></access>')
        legacy = c.parse_xml(b'<runtime-permissions><shared-user name="android.uid.system">'
            b'<item name="android.permission.ACCESS_FINE_LOCATION" granted="false" flags="0"/>'
            b'</shared-user></runtime-permissions>')
        subjects = m.permission_subjects(c, [{"path": "access", "document": access},
            {"path": "legacy", "document": legacy}], apps, nodes, shared)
        system = [x for x in subjects if x["kind"] == "access_app_id" and x["subject"] == 1000]
        self.assertEqual(len(system), 1)
        self.assertIn(system[0]["id"], apps["com.android.settings"]["permission_subject_refs"])
        self.assertIn(system[0]["id"], apps["com.android.documentsui"]["permission_subject_refs"])
        self.assertTrue(all(x["effective_grant_state"] == "UNKNOWN" for x in subjects))
        self.assertTrue(all(x["effective_grant_state"] == "UNKNOWN" for x in
                            apps["com.android.settings"]["location_permission_observations"]))
        noncanonical = next(x for x in subjects if x["subject"] == 10143)["entries"][0]
        self.assertEqual(noncanonical["name"], "       android.permission.VIBRATE")
        self.assertTrue(noncanonical["noncanonical_name_preserved"])
        saved_denial = next(x for x in subjects if x["kind"] == "legacy_shared_user")["entries"][0]
        self.assertIs(saved_denial["stored_granted"], False)

    def test_system_permission_count_over_old_eight_app_limit_is_bounded_and_complete(self):
        node = c.Node("perms")
        for number in range(300):
            child = c.Node("item")
            child.attrs.update(name="android.permission.P%d" % number, flags="0")
            node.children.append(child)
        out = m.permission_entries(c, node, "item")
        self.assertEqual(len(out), 300)
        self.assertTrue(all("stored_granted" not in x for x in out))
        node.children.append(node.children[0])
        with self.assertRaisesRegex(c.Rejected, "PERMISSION_NAME_OR_COUNT"):
            m.permission_entries(c, node, "item")


class HistoricalAndOutputControls(unittest.TestCase):
    def test_historical_version_match_does_not_become_current_version_name(self):
        apps, unused_nodes, unused_shared = project()
        history = {"package": "com.android.settings", "android_user": 0,
            "apks": [{"manifest": {"package": "com.android.settings", "split_name": None,
                                    "version_name": "17", "version_code": 37}}]}
        raw = m.canonical(history)
        class Host:
            def directory(self, path, predicate):
                return ["app-99.json"]
            def read(self, path, limit, pin=None):
                return raw, {"path": path, "bytes": len(raw), "sha256": m.sha(raw)}
        refs, unused = m.historical_references(c, Host(), apps, c.Budget())
        row = refs["com.android.settings"][0]
        self.assertTrue(row["current_stored_version_code_equal"])
        self.assertFalse(row["current_apk_byte_match_proven"])
        self.assertFalse(row["current_version_name_verified"])
        self.assertIsNone(apps["com.android.settings"]["version_name"]["value"])

    def test_envelope_roundtrip_is_lossless_and_over_bound_never_claims_complete(self):
        original = {"schema": m.SCHEMA, "status": "READONLY_LAUNCHER_METADATA_COMPLETE",
                    "text": "中文 " * 100, "effective_grant_state": "UNKNOWN"}
        wrapped = m.envelope(original)
        packed = base64.b64decode(wrapped["data_base64"], validate=True)
        raw = zlib.decompress(packed)
        self.assertEqual(len(raw), wrapped["artifact_bytes"])
        self.assertEqual(m.sha(raw), wrapped["artifact_sha256"])
        self.assertEqual(m.sha(packed), wrapped["compressed_sha256"])
        self.assertEqual(json.loads(raw), original)
        too_large = dict(original, text="x" * m.MAX_ARTIFACT)
        failed = m.envelope(too_large)
        self.assertEqual(failed["status"], "FAILED_OUTPUT_BOUND")
        self.assertLessEqual(failed["artifact_bytes"], m.MAX_ARTIFACT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
