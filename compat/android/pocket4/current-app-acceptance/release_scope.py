#!/usr/bin/env python3
"""Bind a pinned native 39-app release-check report to the user's exact scope.

This is ordinary JSON processing. It executes no Android commands, follows no
evidence references, and never establishes current versions or runtime readiness.
The original 42-app selection and three unverified exclusions remain explicit.
Existing 42-app reports are never relabeled; the native checker must produce a
fresh report for the exact 39-app manifest without fabricating missing APKs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

LIMIT = 8 * 1024 * 1024
COMMON = frozenset(("identity", "lifecycle", "stability", "data_permissions",
                    "release_scope", "ui_observation"))
EXEMPT = frozenset(("com.enflick.android.TextNow", "com.pinger.textfree", "com.ubercab"))
SCOPE_PATH = Path(__file__).with_name("release-scope-20261118.json")
SCOPE_SHA256 = "7d3715d360abbdadf3206406c331d575eed4020040d7963c182af9bad85bf24d"
COUNTS = ("passed_gates", "failed_gates", "blocked_gates", "unsupported_gates")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def is_sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def integer(value, maximum=1024):
    return type(value) is int and 0 <= value <= maximum


def strings(value, *, distinct=False):
    return (type(value) is list and all(type(x) is str and x.strip() for x in value)
            and (not distinct or len(value) == len(set(value))))


def fields(value, expected, label):
    need(type(value) is dict and set(value) == set(expected.split()), label + " fields differ")


def decode(raw, expected_sha, label):
    need(type(raw) is bytes and len(raw) <= LIMIT and is_sha(expected_sha)
         and sha256(raw) == expected_sha, label + " external SHA-256 differs")

    def pairs(rows):
        value = {}
        for key, item in rows:
            need(key not in value, label + " contains duplicate JSON key: " + key)
            value[key] = item
        return value

    def constant(value):
        raise ValueError(label + " contains non-finite JSON number: " + value)

    return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
                      parse_constant=constant)


def read_input(path):
    """Read only this explicit regular file; never resolve embedded references."""
    path = Path(path)
    need(path.is_absolute() and path.resolve(strict=True) == path,
         "input path must be absolute and canonical")
    named = path.lstat()
    need(stat.S_ISREG(named.st_mode) and named.st_size <= LIMIT,
         "input must be a bounded regular file")
    identity = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_uid, x.st_gid,
                          x.st_nlink, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        need(identity(named) == identity(before), "input changed before opening")
        raw = stream.read(LIMIT + 1)
        need(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
             == identity(path.lstat()), "input changed while reading")
    return raw


def validate_identity(value):
    """Match the native manifest's identity shape without opening APK references."""
    fields(value, "package android_user uid version_code version_name engine_mapping_sha256 apks", "APK identity")
    need(integer(value["android_user"], 2**32 - 1) and integer(value["uid"], 2**32 - 1)
         and integer(value["version_code"], 2**64 - 1)
         and type(value["version_name"]) is str and 0 < len(value["version_name"].encode("utf-8")) <= 256
         and is_sha(value["engine_mapping_sha256"])
         and type(value["apks"]) is list and 1 <= len(value["apks"]) <= 256,
         "complete native APK identity required")
    names = set()
    common_signers = None
    for apk in value["apks"]:
        fields(apk, "name bytes sha256 signer_sha256", "APK member")
        name = apk["name"]
        signers = apk["signer_sha256"]
        need(type(name) is str and 0 < len(name.encode("utf-8")) <= 255 and name.endswith(".apk")
             and "/" not in name and "\\" not in name and name not in names
             and integer(apk["bytes"], 2**64 - 1) and apk["bytes"] > 0 and is_sha(apk["sha256"])
             and strings(signers, distinct=True) and 1 <= len(signers) <= 16
             and all(is_sha(s) for s in signers), "invalid, duplicate or incomplete APK member")
        need(common_signers is None or common_signers == set(signers), "APK split signers disagree")
        common_signers = set(signers)
        names.add(name)
    need("base.apk" in names, "native APK identity requires base.apk")


def assess(manifest_raw, registry_raw, report_raw, *, manifest_sha256,
           registry_sha256, report_sha256):
    scope = decode(read_input(SCOPE_PATH), SCOPE_SHA256, "fixed user scope")
    selected = scope["selected_packages"]
    need(strings(selected, distinct=True) and len(selected) == 42,
         "fixed scope must retain all 42 historical package identities")
    exemptions = scope["exemptions"]
    need(type(exemptions) is list and len(exemptions) == 3
         and {x["package"] for x in exemptions} == EXEMPT,
         "only the three explicit user exclusions are allowed")
    expected = set(selected)
    need(EXEMPT <= expected, "exclusions must belong to the original selection")
    required = expected - EXEMPT
    manifest = decode(manifest_raw, manifest_sha256, "manifest")
    registry = decode(registry_raw, registry_sha256, "gate registry")
    report = decode(report_raw, report_sha256, "native checker report")
    fields(manifest, "schema main apps", "native manifest")
    need(type(manifest["schema"]) is int and manifest["schema"] == 1,
         "native manifest schema must be 1")
    fields(manifest["main"], "main_sha256 boot_id framework_epoch_sha256 cohort_sha256", "Main")
    main = manifest["main"]
    need(all(is_sha(main[k]) for k in ("main_sha256", "framework_epoch_sha256", "cohort_sha256"))
         and type(main["boot_id"]) is str
         and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", main["boot_id"]),
         "complete original Main/boot/framework/cohort binding required")
    fields(registry, "schema common_gates profiles packages", "gate registry")
    need(registry["schema"] == "pocket4-app-release-gates-v1"
         and type(registry["common_gates"]) is dict and set(registry["common_gates"]) == COMMON
         and all(type(v) is str and v.strip() for v in registry["common_gates"].values())
         and type(registry["profiles"]) is dict and type(registry["packages"]) is dict,
         "complete known common gates and profile registry required")
    need(type(manifest["apps"]) is list and len(manifest["apps"]) == 39,
         "native manifest must contain the exact 39 required applications")
    gates_by_package = {}
    for app in manifest["apps"]:
        fields(app, "identity required_gates", "expected application")
        validate_identity(app["identity"])
        package = app["identity"].get("package")
        need(type(package) is str and package in required and package not in gates_by_package,
             "missing, duplicate or foreign selected package")
        row = registry["packages"].get(package)
        need(type(row) is dict and type(row.get("profile")) is str,
             "selected package has no gate profile: " + package)
        profile = registry["profiles"].get(row["profile"])
        need(type(profile) is dict and type(profile.get("checks")) is dict and profile["checks"],
             "nonempty business gate definitions required: " + package)
        business = profile["checks"]
        need(all(type(k) is str and 0 < len(k.encode("utf-8")) <= 128 and k not in COMMON
                 and type(v) is str and v.strip() for k, v in business.items()),
             "business gate definition is invalid: " + package)
        gates = app["required_gates"]
        need(strings(gates, distinct=True) and len(gates) <= 128
             and set(gates) == COMMON | set(business),
             "all common and profile business gates must be retained: " + package)
        gates_by_package[package] = set(gates)
    need(set(gates_by_package) == required, "required package set differs from original 42 minus the exact three")
    fields(report, "schema evidence_complete expected_applications complete_applications "
           "manifest_sha256 results_sha256 main_sha256 tests_executed_by_checker "
           "production_ready runtime_qualified meaning issues applications", "native report")
    need(type(report["schema"]) is int and report["schema"] == 1
         and type(report["expected_applications"]) is int and report["expected_applications"] == 39
         and integer(report["complete_applications"], 39)
         and type(report["evidence_complete"]) is bool
         and type(report["tests_executed_by_checker"]) is int and report["tests_executed_by_checker"] == 0
         and report["production_ready"] is False and report["runtime_qualified"] is False,
         "only a native report calculated for the exact 39-app manifest is accepted")
    need(report["manifest_sha256"] == manifest_sha256
         and report["main_sha256"] == main["main_sha256"] and is_sha(report["results_sha256"]),
         "native report belongs to another manifest or Main generation")
    need(strings(report["issues"]) and type(report["meaning"]) is str and report["meaning"].strip()
         and type(report["applications"]) is list and len(report["applications"]) == 39,
         "complete original report rows and global issues required")
    by_package = {}
    for row in report["applications"]:
        fields(row, "package evidence_complete passed_gates failed_gates blocked_gates "
               "unsupported_gates missing_gates issues", "native app assessment")
        package = row["package"]
        need(type(package) is str and package in required and package not in by_package,
             "native report contains missing, duplicate or foreign packages")
        gates = gates_by_package[package]
        need(type(row["evidence_complete"]) is bool and all(integer(row[k], len(gates)) for k in COUNTS)
             and strings(row["missing_gates"], distinct=True) and set(row["missing_gates"]) <= gates
             and strings(row["issues"]), "invalid native application assessment: " + package)
        need(sum(row[k] for k in COUNTS) + len(row["missing_gates"]) == len(gates),
             "native application gate counts differ: " + package)
        complete = not row["issues"] and not row["missing_gates"] and row["passed_gates"] == len(gates)
        need(row["evidence_complete"] is complete,
             "native application completeness contradicts its gates: " + package)
        by_package[package] = row
    total = sum(row["evidence_complete"] for row in by_package.values())
    need(report["complete_applications"] == total
         and report["evidence_complete"] is (not report["issues"] and total == 39),
         "native report totals contradict its 39 rows")
    completed = [package for package in sorted(required) if by_package[package]["evidence_complete"]]
    return {
        "schema": "pocket4-application-release-scope-report-v1",
        "scope_id": scope["scope_id"],
        "historical_selection_source": scope["historical_selection_source"],
        "source_sha256": {"scope": SCOPE_SHA256, "manifest": manifest_sha256,
                          "gate_registry": registry_sha256, "native_report": report_sha256},
        "original_selected_applications": 42,
        "native_input_applications": 39,
        "required_applications": 39,
        "complete_required_applications": len(completed),
        "required_evidence_complete": not report["issues"] and len(completed) == 39,
        "required_packages": sorted(required),
        "complete_required_packages": completed,
        "exempted_applications": exemptions,
        "exemptions_credited_as_pass": 0,
        "production_ready": False, "runtime_qualified": False, "latest_versions_verified": False,
        "tests_executed_by_scope_checker": 0, "deletion_authorized": False,
        "meaning": "Derived declared evidence coverage from the pinned native report. "
                   "It does not authenticate evidence, establish freshness, verify current versions, "
                   "run Android tests or authorize deployment or deletion.",
        "native_report": report,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "registry", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        value = assess(read_input(args.manifest), read_input(args.registry), read_input(args.report),
                       manifest_sha256=args.manifest_sha256, registry_sha256=args.registry_sha256,
                       report_sha256=args.report_sha256)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value["required_evidence_complete"] else 1
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
        print(json.dumps({"schema": "pocket4-application-release-scope-error-v1",
                          "error": str(error), "production_ready": False,
                          "runtime_qualified": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
