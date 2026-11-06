#!/usr/bin/env python3
"""Offline parsing controls over exact actual b13 logs; no tool/Android calls."""
import sys
sys.dont_write_bytecode = True
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import types
import unittest

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
OLD = HERE.parent / "linked-official-continuation-r2"
RAW = PROJECT / "successor_audit_requests/diagnostics/b13-fixture-manifest-raw-readback-r1/actual"


def load(path, name):
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


W = load(HERE / "audit_fixture_version_repair.py", "fixture_candidate_offline")
O = load(OLD / "audit_remaining_batches.py", "original_linked_collector_offline")


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.badging = (RAW / "p00-a00-badging.stdout").read_bytes()
        cls.xml = (RAW / "p00-a00-manifest.stdout").read_bytes()
        assert len(cls.badging) == 686 and hashlib.sha256(cls.badging).hexdigest() == W.FIXTURE_BADGING_PIN["sha256"]
        assert len(cls.xml) == 1244 and hashlib.sha256(cls.xml).hexdigest() == W.FIXTURE_XML_PIN["sha256"]
        artifact = (PROJECT / "successor_audit_requests/actual/batches-final-r1/batch-13/artifact.original.json").read_bytes()
        assert len(artifact) == 72536 and hashlib.sha256(artifact).hexdigest() == "db979e50d6bfa1e0c83fd7ae876239b48bdca3b4be80bfb5cce6e24f30948d33"
        cls.signature = json.loads(artifact)["apps"][0]["apks"][0]["signature"]
        cls.scope = W.FIXTURE_SCOPE
        cls.apk = cls.scope["apks"][0]

    def parse(self, badging=None, xml=None, scope=None, apk=None, signature=None, package="local.pocket4.fixture"):
        return W.manifest_with_exact_fixture_default(self.badging if badging is None else badging,
            self.xml if xml is None else xml, package, self.scope if scope is None else scope,
            self.apk if apk is None else apk, self.signature if signature is None else signature)

    def test_01_actual_old_failure_remains_and_new_absence_is_explicit(self):
        with self.assertRaisesRegex(RuntimeError, "AAPT_PACKAGE_VERSION_REQUIRED"):
            O.badging_manifest(self.badging)
        value = self.parse()
        self.assertIsNone(value["version_code"])
        self.assertIsNone(value["version_code_major"])
        self.assertIsNone(value["version_name"])
        self.assertEqual(value["version_code_raw"], "")
        self.assertEqual(value["version_name_raw"], "")
        self.assertEqual(value["long_version_code"], 0)
        self.assertEqual((value["min_sdk"], value["target_sdk"]), ("26", "35"))
        self.assertTrue(value["version_default_evidence"]["xml_absence"]["all_three_version_attributes_absent"])

    def test_02_missing_empty_or_conflicting_XML_rejected(self):
        for xml in (b"", b"  E: manifest (line=1)\n", self.xml.replace(b"    E: uses-sdk", b"    A: android:versionCode(0x0101021b)=(type 0x10)0x0\n    E: uses-sdk")):
            with self.subTest(size=len(xml)), self.assertRaises(RuntimeError):
                self.parse(xml=xml)

    def test_03_nonempty_wrong_or_missing_badging_version_rejected(self):
        for badging in (self.badging.replace(b"versionCode=''", b"versionCode='0'"),
                        self.badging.replace(b"versionName=''", b"versionName='invented'"),
                        self.badging.replace(b" versionCode=''", b""),
                        self.badging.replace(b"name='local.pocket4.fixture'", b"name='local.other'")):
            with self.subTest(size=len(badging)), self.assertRaises(RuntimeError):
                self.parse(badging=badging)

    def test_04_PM_UID_or_APK_identity_change_rejected(self):
        for field, wrong in (("uid", 10116), ("version_code", 1), ("version_code", False), ("package", "local.other")):
            scope = copy.deepcopy(self.scope); scope[field] = wrong
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.parse(scope=scope)
        apk = copy.deepcopy(self.apk); apk["sha256"] = "0" * 64
        with self.assertRaises(RuntimeError):
            self.parse(apk=apk)

    def test_05_signature_missing_unverified_or_different_signer_rejected(self):
        for field, wrong in (("verified", False), ("integrity_check_bypassed", True),
                             ("API_minimum_override_used", True), ("signer_certificate_sha256", ["0" * 64])):
            value = copy.deepcopy(self.signature); value[field] = wrong
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.parse(signature=value)
        with self.assertRaises(RuntimeError):
            self.parse(signature={})

    def test_06_other_packages_keep_original_strict_numeric_parser(self):
        ordinary = b"package: name='local.other' versionCode='10' versionName='1.0'\nminSdkVersion:'23'\ntargetSdkVersion:'35'\n"
        self.assertEqual(self.parse(badging=ordinary, package="local.other"), O.badging_manifest(ordinary))
        with self.assertRaisesRegex(RuntimeError, "AAPT_PACKAGE_VERSION_REQUIRED"):
            self.parse(badging=self.badging.replace(b"local.pocket4.fixture", b"local.other"), package="local.other")

    def test_07_exact_three_package_request_and_embedded_source_closure(self):
        plan = json.loads((HERE / "REPAIR_PLAN.json").read_bytes())
        request = json.loads((HERE / "request.review-only.json").read_bytes())
        W.validate_request(request)
        wrong = copy.deepcopy(request); wrong["original_batch"] = 12
        with self.assertRaises(RuntimeError):
            W.validate_request(wrong)
        wrong = copy.deepcopy(request); wrong["original_b13_failure"]["state"] = "succeeded"
        with self.assertRaises(RuntimeError):
            W.validate_request(wrong)
        packet = json.loads((HERE / "process-request.review-only.json").read_bytes())
        self.assertEqual(packet["args"][-1].encode(), (HERE / "stage_and_run.py").read_bytes())
        self.assertEqual(packet["stdin"].encode(), (HERE / "stage.stdin.original.json").read_bytes())
        payload = json.loads(packet["stdin"])
        for item, pin in zip(payload["files"], plan["stage_files"]):
            raw = item["text"].encode()
            self.assertEqual(item["name"], pin["name"])
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (pin["bytes"], pin["sha256"]))
            self.assertEqual(raw, (HERE / item["name"]).read_bytes())
        self.assertEqual((plan["package_count"], plan["APK_count"], plan["primary_commands_required"], plan["official_layout_observations_required"]), (3, 3, 9, 20))


def main():
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    value = {"schema": "pocket4-b13-fixture-absence-local-parser-controls-v1", "ok": result.wasSuccessful() and before == after,
             "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
             "FDs_before": before, "FDs_after": after, "Android_commands": 0, "APK_tool_commands": 0,
             "new_runtime_signature_verification": False, "original_failed_B13_unchanged": True,
             "runtime_correction_completed": False, "ledger_claims": 0, "remote_jobs": 0}
    print(json.dumps(value, sort_keys=True))
    return 0 if value["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
