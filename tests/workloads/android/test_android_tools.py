#!/usr/bin/env python3
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from support.android import aosp_reference
from tests.workloads.android import run_apk_workload


class AndroidToolTests(unittest.TestCase):
    def test_locked_profile_is_explicit_and_4k(self):
        profile = aosp_reference.load_profile()
        self.assertEqual(profile["aosp"]["tag"], "android-15.0.0_r36")
        self.assertEqual(profile["target"]["lunch"], "aosp_cf_x86_64_phone-trunk_staging-userdebug")
        self.assertEqual(profile["target"]["page_size_bytes"], 4096)
        self.assertFalse(profile["execution_boundary"]["native_android_claim"])
        self.assertFalse(profile["toolchain"]["build_verified_here"])
        self.assertTrue(profile["aosp"]["release_config"]["RELEASE_AIDL_USE_UNFROZEN"])
        self.assertEqual(profile["vintf"]["active_framework_matrix_level"], 202504)
        self.assertIn("build/soong", profile["aosp"]["source_projects"])
        self.assertEqual(profile["target"]["native_bridge_status"], "declared_only_not_verified")

    def test_host_probe_is_not_native_android_evidence(self):
        report = aosp_reference.host_probe(aosp_reference.load_profile())
        self.assertEqual(report["execution_class"], "host-model")
        self.assertFalse(report["native_android_claim"])
        self.assertEqual(report["page_size_bytes"], 4096)

    def test_apk_inventory_keeps_hash_and_abi_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "sample.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("classes.dex", b"dex\n035\0")
                archive.writestr("lib/x86_64/libsample.so", b"so")
                archive.writestr("lib/arm64-v8a/libsample.so", b"so")
            metadata = run_apk_workload.inventory(apk, aapt2="/does/not/exist")
            self.assertEqual(metadata["abi_classes"], ["arm64-v8a", "x86_64"])
            self.assertEqual(metadata["dex_files"], ["classes.dex"])
            self.assertEqual(len(run_apk_workload.digest(apk)), 64)

    def test_badging_parser_does_not_drop_permissions(self):
        badging = """package: name='org.example' versionCode='7' versionName='1.2'\nuses-permission: name='android.permission.INTERNET'\nnative-code: 'x86_64' 'arm64-v8a'\nlaunchable-activity: name='org.example.Main'\n"""
        parsed = run_apk_workload.parse_badging(badging)
        self.assertEqual(parsed["package"], "org.example")
        self.assertEqual(parsed["permissions"], ["android.permission.INTERNET"])
        self.assertEqual(parsed["native_code"], ["x86_64", "arm64-v8a"])
        self.assertEqual(parsed["launchable_activity"], "org.example.Main")

    def test_execute_scenario_gates_after_failed_install(self):
        calls = []

        def fake_adb(adb, serial, args):
            calls.append(args)
            return {"command": [adb, *args], "returncode": 1, "output": "install failed"}

        with patch.object(run_apk_workload, "adb_call", fake_adb):
            result = run_apk_workload.execute_scenario(
                Path("/tmp/example.apk"),
                {"package": "org.example", "launchable_activity": "org.example.Main"},
                "/usr/bin/adb",
                "serial-1",
            )
        self.assertEqual([item["scenario"] for item in result], ["install"])
        self.assertEqual(result[0]["status"], "failed")
        self.assertEqual(calls, [["install", "-r", "/tmp/example.apk"]])

    def test_execute_scenario_blocks_without_package_metadata(self):
        with patch.object(run_apk_workload, "adb_call") as adb_call:
            result = run_apk_workload.execute_scenario(
                Path("/tmp/example.apk"), {}, "/usr/bin/adb", None
            )
        self.assertEqual(result, [{"scenario": "install", "status": "blocked_missing_package_metadata"}])
        adb_call.assert_not_called()

    def test_execute_cli_returns_failure_for_blocked_guest_run(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "sample.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("classes.dex", b"dex")
            output = Path(directory) / "nested" / "report.json"
            with patch.object(run_apk_workload, "inventory", return_value={
                "package": "org.example", "launchable_activity": "org.example.Main"
            }), patch.object(run_apk_workload, "reference_target_check", return_value={"status": "passed", "checks": []}), patch.object(run_apk_workload, "execute_scenario", return_value=[{
                "scenario": "install", "status": "blocked_missing_package_metadata"
            }]):
                rc = run_apk_workload.main([
                    "--apk", str(apk), "--output", str(output), "--execute", "--adb", "/usr/bin/adb"
                ])
            self.assertEqual(rc, 1)
            report = json.loads(output.read_text())
            self.assertEqual(report["execution"]["status"], "blocked")
            self.assertEqual(report["scenarios"][0]["name"], "install")
            self.assertEqual(report["scenarios"][0]["status"], "blocked_missing_package_metadata")
            self.assertEqual(report["scenarios"][1]["status"], "not_run")

    def test_execute_cli_blocks_missing_serial_before_adb_write(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "sample.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("classes.dex", b"dex")
            output = Path(directory) / "report.json"
            with patch.object(run_apk_workload, "inventory", return_value={"package": "org.example"}), patch.object(run_apk_workload, "adb_call") as adb_call:
                rc = run_apk_workload.main(["--apk", str(apk), "--output", str(output), "--execute", "--adb", "/usr/bin/adb"])
            self.assertEqual(rc, 1)
            adb_call.assert_not_called()
            report = json.loads(output.read_text())
            self.assertEqual(report["execution"]["status"], "blocked")
            self.assertEqual(report["execution"]["identity"]["status"], "blocked_missing_serial")

    def test_execute_cli_does_not_treat_unknown_status_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "sample.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("classes.dex", b"dex")
            with patch.object(run_apk_workload, "inventory", return_value={
                "package": "org.example", "launchable_activity": "org.example.Main"
            }), patch.object(run_apk_workload, "reference_target_check", return_value={"status": "passed", "checks": []}), patch.object(run_apk_workload, "execute_scenario", return_value=[{
                "scenario": "install", "status": "future_status"
            }]):
                rc = run_apk_workload.main([
                    "--apk", str(apk), "--output", str(Path(directory) / "result.json"),
                    "--execute", "--adb", "/usr/bin/adb", "--serial", "serial-1"
                ])
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
