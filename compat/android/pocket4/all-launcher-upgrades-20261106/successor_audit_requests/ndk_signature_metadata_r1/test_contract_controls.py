#!/usr/bin/env python3
"""Pure local evidence/parser controls. No APK tool, Main read or target command."""
import copy
import hashlib
import json
import os
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent


def load(path):
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def census():
    value = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            st = os.fstat(int(name))
            value[name] = [os.readlink("/proc/self/fd/" + name), st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid, st.st_rdev]
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno != 9:
                raise
    return value


def main():
    before = census()
    worker = load(ROOT / "audit_ndk_current.py")
    validator = load(PROJECT / "successor_audit_requests/explicit48_scope_r1/owned_readonly_lifetime.py")
    outer = (ROOT / "inputs/scope48.stdout.original.jsonl").read_bytes()
    terminal = (ROOT / "inputs/scope48.terminal.original.json").read_bytes()
    observed = worker.validate_scope_qualification(outer, terminal, validator)
    assert observed["scope_is_signature_evidence"] is False
    cases = [{"name": "actual_complete_scope48_joint_accepted_only_as_identity", "status": "PASS"}]

    def reject(name, fn, expected):
        try:
            fn()
        except RuntimeError as error:
            if str(error) != expected:
                raise RuntimeError("UNEXPECTED_REJECTION:" + name + ":" + str(error))
            cases.append({"name": name, "status": "PASS", "rejection": str(error)})
        else:
            raise RuntimeError("MISSING_REJECTION:" + name)

    bad_terminal = json.loads(terminal)
    bad_terminal["output_durable"] = False
    reject("incomplete_scope_terminal_rejected", lambda: worker.validate_scope_qualification(
        outer, worker.canonical(bad_terminal), validator), "ACTUAL_SCOPE_DURABLE_NORMAL_SUCCESS_REQUIRED")
    req = json.loads((ROOT / "request.review-only.json").read_bytes())
    req["protected_packages"].pop()
    reject("request_omitting_one_protected_package_rejected", lambda: worker.validate_request(req),
           "EXACT_CURRENT_48_PROTECTION_AND_ONE_NDK_AUDIT")

    previous = PROJECT / "successor_audit_requests/diagnostics/b13-fixture-manifest-raw-readback-r1/actual"
    fixture_badging = (previous / "p00-a00-badging.stdout").read_bytes()
    fixture_xml = (previous / "p00-a00-manifest.stdout").read_bytes()
    assert len(fixture_badging) == 686 and hashlib.sha256(fixture_badging).hexdigest() == "28b2cf92369048b078c8fbf337bf8ae08173f49768e946baee8421bb0d0860b5"
    assert len(fixture_xml) == 1244 and hashlib.sha256(fixture_xml).hexdigest() == "2deafdbfa41af5daf85f7980a82491408b1472bcb5aafb0904fa1ea72e9b351f"
    # Deliberately synthetic language fixtures, never presented as NDK's actual output.
    badging = fixture_badging.replace(b"local.pocket4.fixture", b"com.example.ndk_tests")
    xml = fixture_xml.replace(b"local.pocket4.fixture", b"com.example.ndk_tests")
    expected = worker.NDK_EXPECTED
    apk = expected["apks"][0]
    signature = {"verified": True, "cryptographic_verification_performed": True, "API_minimum_override_used": False,
                 "integrity_check_bypassed": False, "signer_certificate_sha256": expected["package_manager_certificate_sha256"]}
    parsed = worker.ndk_manifest_with_observed_absence(badging, xml, expected, apk, signature)
    assert parsed["version_code"] is None and parsed["version_code_major"] is None and parsed["version_name"] is None
    assert parsed["long_version_code"] == 0 and parsed["version_code_raw"] == parsed["version_name_raw"] == ""
    assert parsed["xml_root_observation"]["all_three_version_attributes_absent"] is True
    cases.append({"name": "synthetic_XML_absence_preserves_declared_null_and_raw_empty", "status": "PASS",
                  "fixture_is_actual_NDK_output": False, "signature_dictionary_is_actual_verification": False})
    reject("missing_XML_never_means_attribute_absence", lambda: worker.ndk_manifest_with_observed_absence(
        badging, b"", expected, apk, signature), "NDK_XML_ANDROID_NAMESPACE_REQUIRED")
    explicit = xml.replace(b"  E: manifest (line=1)\n", b"  E: manifest (line=1)\n    A: android:versionCode(0x0101021b)=(type 0x10)0x0\n")
    if explicit == xml:
        lines = xml.splitlines(True)
        explicit = b"".join(lines[:2] + [b"    A: android:versionCode(0x0101021b)=(type 0x10)0x0\n"] + lines[2:])
    reject("explicit_XML_version_cannot_use_absence_fallback", lambda: worker.ndk_manifest_with_observed_absence(
        badging, explicit, expected, apk, signature), "ACTUAL_EMPTY_BADGING_AND_COMPLETE_XML_ABSENCE_REQUIRED_FOR_DEFAULT_ZERO")
    bad_signature = dict(signature, verified=False)
    reject("ordinary_signature_failure_cannot_use_default", lambda: worker.ndk_manifest_with_observed_absence(
        badging, xml, expected, apk, bad_signature), "NORMAL_CURRENT_SIGNATURE_MATCHING_PM_REQUIRED")
    wrong = copy.deepcopy(expected)
    wrong["uid"] += 1
    reject("changed_scoped_UID_rejected", lambda: worker.ndk_manifest_with_observed_absence(
        badging, xml, wrong, apk, signature), "ONLY_EXACT_FRESH_SCOPED_NDK_IDENTITY")
    reject("duplicate_SDK_alias_rejected", lambda: worker.ndk_manifest_with_observed_absence(
        badging + b"\nsdkVersion:'26'\n", xml, expected, apk, signature), "AMBIGUOUS_AAPT_SDK")
    reject("missing_badging_versionName_not_invented", lambda: worker.ndk_manifest_with_observed_absence(
        badging.replace(b" versionName=''", b""), xml, expected, apk, signature),
        "ACTUAL_EMPTY_BADGING_AND_COMPLETE_XML_ABSENCE_REQUIRED_FOR_DEFAULT_ZERO")
    after = census()
    assert after == before
    print(json.dumps({"schema": "pocket4-ndk-signature-metadata-local-controls-v1", "ok": True, "cases": cases,
                      "FDs_before": before, "FDs_after": after, "UID": os.getuid(), "EUID": os.geteuid(),
                      "root_identity_simulated": False, "APK_tools_executed": 0, "Main_reads": 0,
                      "remote_jobs": 0, "actual_NDK_manifest_observed": False,
                      "actual_NDK_signature_verified": False}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
