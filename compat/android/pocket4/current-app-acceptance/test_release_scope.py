#!/usr/bin/env python3
"""Host-only controls using synthetic JSON; no APK, device or account is opened."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("release_scope", ROOT / "release_scope.py")
scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope)


def raw(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def fixture(complete=False):
    selected = json.loads(scope.SCOPE_PATH.read_text())["selected_packages"]
    packages = sorted(set(selected) - scope.EXEMPT)
    main = {"main_sha256": "1" * 64, "framework_epoch_sha256": "2" * 64,
            "cohort_sha256": "3" * 64, "boot_id": "97d9600f-e081-465c-9e6e-62651e09806b"}
    registry = {"schema": "pocket4-app-release-gates-v1",
                "common_gates": {key: "Synthetic requirement" for key in scope.COMMON},
                "profiles": {"fixture": {"checks": {"fixture.query": "Synthetic query",
                                                     "fixture.return": "Synthetic return"}}},
                "packages": {package: {"profile": "fixture"} for package in selected}}
    # The real registry also contains four non-selected dependencies/fixtures.
    for i in range(4):
        registry["packages"]["org.example.dependency" + str(i)] = {"profile": "fixture"}
    gates = sorted(scope.COMMON | {"fixture.query", "fixture.return"})
    manifest = {"schema": 1, "main": main, "apps": [
        {"identity": {"package": package, "android_user": 0, "uid": 10000 + i,
                      "version_code": 2, "version_name": "2.fixture", "engine_mapping_sha256": "4" * 64,
                      "apks": [{"name": "base.apk", "bytes": 3, "sha256": "5" * 64,
                                "signer_sha256": ["6" * 64]}]}, "required_gates": gates[:]}
        for i, package in enumerate(packages)]}
    report = {"schema": 1, "evidence_complete": complete, "expected_applications": 39,
              "complete_applications": 39 if complete else 0, "manifest_sha256": scope.sha256(raw(manifest)),
              "results_sha256": "7" * 64, "main_sha256": main["main_sha256"],
              "tests_executed_by_checker": 0, "production_ready": False, "runtime_qualified": False,
              "meaning": "Synthetic declared evidence only; no Android test.", "issues": [],
              "applications": [{"package": package, "evidence_complete": complete,
                                "passed_gates": len(gates) if complete else 0,
                                "failed_gates": 0, "blocked_gates": 0 if complete else len(gates),
                                "unsupported_gates": 0, "missing_gates": [], "issues": []}
                               for package in packages]}
    return manifest, registry, report


def assess(values, *, rebind=True):
    manifest, registry, report = copy.deepcopy(values)
    m, g = raw(manifest), raw(registry)
    if rebind:
        report["manifest_sha256"] = scope.sha256(m)
    r = raw(report)
    return scope.assess(m, g, r, manifest_sha256=scope.sha256(m),
                        registry_sha256=scope.sha256(g), report_sha256=scope.sha256(r))


class ScopeTests(unittest.TestCase):
    def test_fixed_selection_is_exact42_minus_three(self):
        value = assess(fixture())
        self.assertEqual(value["original_selected_applications"], 42)
        self.assertEqual(value["required_applications"], 39)
        self.assertEqual(value["complete_required_applications"], 0)
        self.assertFalse(value["required_evidence_complete"])
        self.assertEqual({x["package"] for x in value["exempted_applications"]}, scope.EXEMPT)
        self.assertTrue(all(x["status"] == "exempt_unverified" for x in value["exempted_applications"]))

    def test_complete39_does_not_credit_exemptions_or_production(self):
        inputs = fixture(True)
        before = copy.deepcopy(inputs)
        value = assess(inputs)
        self.assertTrue(value["required_evidence_complete"])
        self.assertEqual(value["complete_required_applications"], 39)
        self.assertEqual(value["exemptions_credited_as_pass"], 0)
        for key in ("production_ready", "runtime_qualified", "latest_versions_verified", "deletion_authorized"):
            self.assertIs(value[key], False)
        self.assertEqual(value["native_report"], inputs[2])
        self.assertEqual(inputs, before)

    def test_old42_report_is_not_relabelled(self):
        inputs = fixture(True)
        inputs[2]["expected_applications"] = 42
        with self.assertRaisesRegex(ValueError, "39-app"):
            assess(inputs)

    def test_no_fourth_exemption_or_package_substitution(self):
        for mutation in ("missing", "exempt", "alias", "foreign", "duplicate"):
            with self.subTest(mutation=mutation):
                inputs = fixture(True)
                if mutation == "missing":
                    inputs[0]["apps"].pop()
                else:
                    inputs[0]["apps"][0]["identity"]["package"] = {
                        "exempt": "com.ubercab", "alias": "com.pinger.textfree.call",
                        "foreign": "org.example.foreign", "duplicate": inputs[0]["apps"][1]["identity"]["package"]
                    }[mutation]
                with self.assertRaises(ValueError):
                    assess(inputs)

    def test_common_and_all_dynamic_business_gates_required(self):
        for mutation in ("common", "business", "empty", "profile", "duplicate"):
            with self.subTest(mutation=mutation):
                inputs = fixture(True)
                if mutation == "common":
                    inputs[0]["apps"][0]["required_gates"].remove("identity")
                elif mutation == "business":
                    inputs[0]["apps"][0]["required_gates"].remove("fixture.return")
                elif mutation == "empty":
                    inputs[1]["profiles"]["fixture"]["checks"] = {}
                elif mutation == "profile":
                    inputs[1]["profiles"] = {}
                else:
                    inputs[0]["apps"][0]["required_gates"].append("fixture.query")
                with self.assertRaises(ValueError):
                    assess(inputs)

    def test_unknown_or_missing_required_result_stays_incomplete(self):
        inputs = fixture(True)
        row = inputs[2]["applications"][0]
        row.update(evidence_complete=False, passed_gates=0,
                   missing_gates=inputs[0]["apps"][0]["required_gates"][:],
                   issues=["application has no result in this run"])
        inputs[2].update(evidence_complete=False, complete_applications=38)
        value = assess(inputs)
        self.assertEqual(value["complete_required_applications"], 38)
        self.assertFalse(value["required_evidence_complete"])
        row["evidence_complete"] = "UNKNOWN"
        with self.assertRaises(ValueError):
            assess(inputs)

    def test_global_issues_prevent_scope_completion(self):
        inputs = fixture(True)
        inputs[2].update(issues=["unexpected application: org.example.extra"], evidence_complete=False)
        value = assess(inputs)
        self.assertEqual(value["complete_required_applications"], 39)
        self.assertFalse(value["required_evidence_complete"])
        self.assertEqual(value["native_report"]["issues"], inputs[2]["issues"])

    def test_duplicate_missing_foreign_report_rows_rejected(self):
        for mutation in ("duplicate", "missing", "foreign"):
            with self.subTest(mutation=mutation):
                inputs = fixture(True)
                if mutation == "missing":
                    inputs[2]["applications"].pop()
                else:
                    inputs[2]["applications"][0]["package"] = (
                        inputs[2]["applications"][1]["package"] if mutation == "duplicate" else "com.ubercab")
                with self.assertRaises(ValueError):
                    assess(inputs)

    def test_main_and_complete_manifest_generation_binding(self):
        for field in ("main_sha256", "boot_id", "framework_epoch_sha256", "cohort_sha256"):
            with self.subTest(field=field):
                inputs = fixture(True)
                inputs[0]["main"][field] = "9" * 64 if field != "boot_id" else "11111111-1111-1111-1111-111111111111"
                with self.assertRaisesRegex(ValueError, "another manifest or Main"):
                    assess(inputs, rebind=False)

    def test_independent_external_sha_pins_are_required(self):
        values = fixture(True)
        inputs = tuple(raw(v) for v in values)
        pins = dict(zip(("manifest_sha256", "registry_sha256", "report_sha256"), map(scope.sha256, inputs)))
        for key in pins:
            bad = dict(pins, **{key: "0" * 64})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "external SHA-256"):
                scope.assess(*inputs, **bad)

    def test_json_duplicate_keys_and_nonfinite_numbers_rejected(self):
        for value in (b'{"a":1,"a":2}', b'{"a":{"x":1,"x":2}}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scope.decode(value, scope.sha256(value), "fixture")

    def test_strict_counts_booleans_and_schema(self):
        for key, bad in (("schema", True), ("expected_applications", 39.0),
                         ("complete_applications", True), ("evidence_complete", 1),
                         ("production_ready", 0), ("runtime_qualified", 0), ("tests_executed_by_checker", False)):
            inputs = fixture(True)
            inputs[2][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                assess(inputs)
        inputs = fixture(True)
        inputs[2]["applications"][0]["failed_gates"] = False
        with self.assertRaises(ValueError):
            assess(inputs)

    def test_inconsistent_counts_and_false_passes_rejected(self):
        for mutation in ("total", "per_app", "missing", "issue"):
            inputs = fixture(True)
            if mutation == "total":
                inputs[2]["complete_applications"] = 38
            elif mutation == "per_app":
                inputs[2]["applications"][0]["passed_gates"] -= 1
            elif mutation == "missing":
                inputs[2]["applications"][0]["missing_gates"] = ["fixture.query"]
            else:
                inputs[2]["applications"][0]["issues"] = ["identity differs"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                assess(inputs)

    def test_complete_native_identity_and_split_signers_required(self):
        for mutation in ("identity", "uid", "version", "base", "hash", "split", "signer"):
            inputs = fixture(True)
            identity = inputs[0]["apps"][0]["identity"]
            if mutation == "identity":
                inputs[0]["apps"][0]["identity"] = {"package": identity["package"]}
            elif mutation in ("uid", "version"):
                identity["uid" if mutation == "uid" else "version_code"] = True
            elif mutation == "base":
                identity["apks"][0]["name"] = "split.apk"
            elif mutation == "hash":
                identity["apks"][0]["sha256"] = "missing"
            else:
                extra = copy.deepcopy(identity["apks"][0])
                if mutation == "signer":
                    extra.update(name="split.apk", signer_sha256=["8" * 64])
                identity["apks"].append(extra)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                assess(inputs)

    def test_scope_file_cannot_add_fourth_exemption(self):
        definition = json.loads(scope.SCOPE_PATH.read_text())
        definition["exemptions"].append({"package": "org.mozilla.firefox", "status": "exempt_unverified"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scope.json"
            path.write_bytes(raw(definition))
            with patch.object(scope, "SCOPE_PATH", path), self.assertRaisesRegex(ValueError, "fixed user scope"):
                assess(fixture(True))

    def test_native_string_limits_count_utf8_bytes(self):
        for field in ("version", "apk_name", "gate"):
            inputs = fixture(True)
            if field == "version":
                inputs[0]["apps"][0]["identity"]["version_name"] = "界" * 100
            elif field == "apk_name":
                inputs[0]["apps"][0]["identity"]["apks"][0]["name"] = "界" * 84 + ".apk"
            else:
                key = "界" * 43
                inputs[1]["profiles"]["fixture"]["checks"][key] = "Synthetic requirement"
                for app in inputs[0]["apps"]:
                    app["required_gates"].append(key)
            with self.subTest(field=field), self.assertRaises(ValueError):
                assess(inputs)

    def test_cli_outputs_status_and_never_follows_embedded_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for complete, expected_status in ((False, 1), (True, 0)):
                inputs = fixture(complete)
                args = [sys.executable, "-I", "-B", str(ROOT / "release_scope.py")]
                for name, value in zip(("manifest", "registry", "report"), inputs):
                    path = root / (name + ".json")
                    data = raw(value); path.write_bytes(data)
                    args.extend(("--" + name, str(path), "--" + name + "-sha256", scope.sha256(data)))
                result = subprocess.run(args, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected_status, result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual(output["complete_required_applications"], 39 if complete else 0)
                self.assertEqual(sorted(p.name for p in root.iterdir()), ["manifest.json", "registry.json", "report.json"])
            args[-1] = "0" * 64
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertFalse(json.loads(result.stderr)["production_ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
