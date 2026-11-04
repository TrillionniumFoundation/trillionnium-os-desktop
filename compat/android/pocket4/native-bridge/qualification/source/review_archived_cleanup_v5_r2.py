#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only independent review of saved v5 private-canary cleanup evidence.
This does not re-enter a stopped Android namespace or execute an application.
This review independently rechecks complete UID-registry coverage and saved
namespace cleanup without changing the frozen runner or its original result.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

PACKAGE = r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*"
SOURCE_PINS = {
    "run_arm-v5-once.py": "895ecbfec6d04170adf0dbc16a0fd18d3de0b78317efec86de1846295dfcddb8",
    "assess-default-once.py": "6cd85a2e6c58ec39cdaf38eb1fbbab87d3960ba4459b49977d6174edd3ade766",
    "assess-v2.py": "c3d88977418a8a8a522db604d4b6930eefaf5dddbf406ddb2175c5b748356f0c",
    "runner-v5-once-manifest.json": "72d3151d28485f536b9f28b9575b248da92c6b289998e28066a82a8a2f776f67",
    "cpu-inventory-v2.json": "590d32e10c5a86934afbd18eebd620d5a07f0e13a4c4af2e4094fac801dc5c62",
}
APK_PINS = {
    "v8": "dc1777871e32681a823253c36dba0a553ef596a464a3c4d7a282d3f9a6bafa67",
    "v4": "74c566cefda4877e1b156394a5f8a38e043db95cd33780fd8a45021f9cb6704a",
    "v5": "4cea86be78ba70aba56f5a37bbfe73be9ab10af958cd528a0015fba45f4ced95",
    "v6": "8706242bc7d24bb2f4fc1c0b7358d3c1839b36b8be71470e6f323c5c1b5b43fe",
}
ENGINE_PINS = {
    "r14": "a74cba50358ab473b4261e33daee98107fb45fcc78110f71599ad38b63822d2c",
    "r15": "a770eda38e27d072f10568b7dee164a429f9eb05261667f7cb3c6f1c10e0d535",
    "r16": "c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d",
}
BOOTSTRAP = {
    "com.android.droidloom.home": "4580d4ba3db94de30204f2a654dbeefae8d52684cdd3d93ba31cb943324b8484",
    "com.android.droidloom.ime": "1345fb142061e5d8cb3979d1fce3f3a5d125cc9dab2e9287a3ac7db904a8058a",
}


def require(condition, label):
    if not condition:
        raise ValueError(label)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1, "not single-link regular evidence")
        require(0 <= first.st_size <= 4 * 1024 * 1024, "evidence size outside limit")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        last = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        require(all(getattr(first, k) == getattr(last, k) for k in fields), "evidence changed during read")
        require(len(raw) == first.st_size, "short or oversized evidence read")
        return raw
    finally:
        os.close(fd)


def package_names(raw):
    result = []
    for line in raw.decode("utf-8", "strict").splitlines():
        found = re.fullmatch(r"package:(" + PACKAGE + r")", line)
        require(found is not None, "malformed package line")
        result.append(found[1])
    require(bool(result), "empty package inventory")
    require(len(result) == len(set(result)), "duplicate package record")
    return set(result)


def uid_records(raw, expected_names):
    result = {}
    for line in raw.decode("utf-8", "strict").splitlines():
        found = re.fullmatch(r"package:(" + PACKAGE + r") uid:([0-9]+)", line)
        require(found is not None, "malformed UID line")
        name, uid = found[1], int(found[2])
        require(name not in result, "duplicate UID package record")
        require(0 <= uid < 100000, "UID outside Android user-0 range")
        result[name] = uid
    require(set(result) == expected_names, "UID registry does not cover complete package set")
    return result


def namespace_checks(rows, expected_paths):
    require(isinstance(rows, list) and len(rows) == len(expected_paths), "namespace check count")
    seen = set()
    for row in rows:
        path = row.get("path")
        require(path in expected_paths and path not in seen, "unexpected or duplicate namespace path")
        seen.add(path)
        require(type(row.get("returncode")) is int and row["returncode"] == 1, "namespace absence return code")
        require(row.get("stdout") == "", "namespace absence has successful output")
        require(row.get("stderr") == "ls: " + path + ": No such file or directory\n",
                "namespace error is not exact ENOENT for checked path")
    require(seen == expected_paths, "incomplete namespace coverage")


def expect_rejected(callback):
    try:
        callback()
    except (ValueError, KeyError, TypeError):
        return
    raise ValueError("reviewer negative control accepted incomplete evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm-dir", type=Path, required=True)
    parser.add_argument("--arm", choices=tuple(ENGINE_PINS), required=True)
    args = parser.parse_args()
    root = args.arm_dir
    files = {}
    paths = {}

    def read(name, base=None):
        label = name if base is None else "runner-source/" + name
        if label not in files:
            path = (root if base is None else base) / name
            files[label] = strict_file(path)
            paths[label] = path
        return files[label]

    def obj(name):
        return json.loads(read(name))

    for name, pin in SOURCE_PINS.items():
        require(digest(read(name, root.parent)) == pin, "frozen runner/source pin mismatch")
    manifest = json.loads(read("runner-v5-once-manifest.json", root.parent))
    require(manifest["v8_apk_sha256"] == APK_PINS["v8"], "manifest V8 APK pin")
    prepared = obj("prepared.json")
    require(prepared["arm"] == args.arm and set(prepared["apks"]) == set(APK_PINS), "prepared arm or APK set")
    result = obj("runtime-result.json")
    require(result.get("arm") == args.arm, "runtime arm mismatch")
    for key in ("run_returned", "all_native_contracts_observed", "all_owned_contracts_complete",
                "main_preserved", "own_packages_removed", "source_contract_preserved",
                "owned_memory_events_zero"):
        require(result.get(key) is True, "incomplete original runtime result: " + key)
    require(result.get("production_ready") is False, "unexpected production qualification claim")
    require(result.get("adbd_before_cleanup") == "stopped", "adbd not stopped")
    require(result.get("cleanup", {}).get("errors") == [], "original cleanup reported errors")
    require(result["main_resources_before"] == result["main_resources_after"], "saved Main limits changed")
    require(set(result["main_resources_before"]) ==
            {"cpu.max", "memory.high", "memory.max", "memory.swap.max", "pids.max"}, "Main resource field coverage")
    expected_contract = {
        "files": {name: SOURCE_PINS[name] for name in ("assess-v2.py", "run_arm-v5-once.py", "assess-default-once.py")},
        "inventory_sha256": SOURCE_PINS["cpu-inventory-v2.json"],
        "manifest_sha256": SOURCE_PINS["runner-v5-once-manifest.json"],
    }
    require(result["source_contract_before"] == expected_contract ==
            result["source_contract_after"], "runtime source contracts do not match exact frozen source")
    require(result["boot"]["engine_sha256"] == ENGINE_PINS[args.arm], "boot engine pin")
    for probe in ("v8", "v4", "v5", "v6"):
        require(result[probe]["engine_loaded"]["engine_sha256"] == ENGINE_PINS[args.arm],
                "saved mapped engine pin: " + probe)

    before = package_names(read("packages-before.txt"))
    after = package_names(read("packages-after.txt"))
    third_before = package_names(read("packages-before-third-party.txt"))
    third_after = package_names(read("packages-after-third-party.txt"))
    require(before == after, "full before/after package sets differ")
    require(third_before == third_after, "third-party before/after package sets differ")
    require(third_after <= after and set(BOOTSTRAP) <= third_after, "bootstrap or third-party set missing")
    uids = uid_records(read("package-uids-after.txt"), after)

    bootstrap = obj("bootstrap-ready.json")
    require(bootstrap.get("complete") is True and bootstrap.get("source_driven_passive_wait") is True,
            "bootstrap readiness not recorded")
    final_bootstrap = bootstrap["observations"][-1]
    require(final_bootstrap["home_setup_state"] == "stopped" and
            final_bootstrap["ime_setup_state"] == "stopped", "bootstrap oneshot incomplete")
    for package, pin in BOOTSTRAP.items():
        record = final_bootstrap["packages"][package]
        require(record["installed"] is True and record["sha256"] == pin and
                record["marker_sha256"] == pin and record["marker_returncode"] == 0 and
                record["versionCode"] == 1 and record["uid"] == uids[package], "bootstrap artifact/UID binding")
    require(final_bootstrap["resolved_home"].splitlines()[-1] in
            ("com.android.droidloom.home/.HomeActivity",
             "com.android.droidloom.home/com.android.droidloom.home.HomeActivity"), "resolved HOME")
    require(final_bootstrap["disabled_stock_launcher"] == "package:com.android.launcher3", "stock launcher enabled")
    require(final_bootstrap["selected_ime"] == "com.android.droidloom.ime/.HostInputMethod", "selected IME")

    owned = {}
    expected_paths = set()
    for version, pin in APK_PINS.items():
        package = "local.pocket4.nativeoracle" + version
        install = obj(version + "-install.json")
        require(install["package"] == package and install["APK_SHA256"] == pin, "owned install identity/hash")
        require(prepared["apks"][version]["package"] == package and
                prepared["apks"][version]["sha256"] == pin, "prepared APK pin")
        uid = install["uid"]
        require(type(uid) is int and 10000 <= uid < 100000 and uid not in owned.values(), "owned UID range/uniqueness")
        require(package not in after and uid not in uids.values(), "owned package or UID remains")
        owned[version] = uid
        apk = PurePosixPath(install["path"])
        require(str(apk) == install["path"] and len(apk.parts) == 6 and
                apk.parts[:3] == ("/", "data", "app") and apk.name == "base.apk" and
                apk.parts[3].startswith("~~") and apk.parent.name.startswith(package + "-") and
                ".." not in apk.parts, "owned code path shape")
        expected_paths.update((str(apk.parent), "/data/data/" + package,
                               "/data/user/0/" + package, "/data/user_de/0/" + package))
        uninstall = obj(version + "-uninstall.json")
        require(uninstall["returncode"] == 0 and uninstall["stdout"].strip() == "Success",
                "raw uninstall did not succeed")

    comparison = obj("package-set-comparison.json")
    require(comparison["before_count"] == len(before) and comparison["after_count"] == len(after), "comparison counts")
    for key in ("missing", "unexpected", "third_party_missing", "third_party_unexpected", "owned_still_installed"):
        require(comparison[key] == [], "saved set difference is nonempty")
    expected_uninstall = [
        {"package": "local.pocket4.nativeoracle" + k, "uid": owned[k], "uninstall_success": True}
        for k in ("v8", "v4", "v5", "v6")
    ]
    require(comparison["uninstall"] == expected_uninstall, "uninstall comparison does not bind original installs")
    cleanup = obj("owned-code-data-cleanup.json")
    require(cleanup["owned_uids"] == owned and cleanup["owned_uids_absent_from_package_registry"] is True,
            "cleanup owned UID binding")
    require(cleanup["remaining"] == [], "host-view code/data paths remain")
    require(len(cleanup["checked_paths"]) == 16 and len(set(cleanup["checked_paths"])) == 16 and
            set(cleanup["checked_paths"]) == expected_paths, "host-view path coverage")
    namespace_checks(cleanup["actual_namespace_checks"], expected_paths)

    resources = obj("resources-before-cleanup.json")
    require(isinstance(resources, list) and len(resources) == 5, "owned resource evidence coverage")
    require(len({r["unit"] for r in resources}) == 5, "duplicate owned resource evidence")
    for record in resources:
        require("error" not in record, "owned resource read failed")
        pairs = [line.split() for line in record["memory.events"].splitlines()]
        require(all(len(pair) == 2 for pair in pairs), "malformed memory event")
        events = {key: int(value) for key, value in pairs}
        require(len(events) == len(pairs), "duplicate memory event")
        require(all(events.get(key) == 0 for key in ("oom", "oom_kill", "oom_group_kill")), "owned OOM event")

    # Controls exercise the previously missing completeness boundary on actual records.
    uid_lines = read("package-uids-after.txt").splitlines(keepends=True)
    expect_rejected(lambda: uid_records(b"", after))
    expect_rejected(lambda: uid_records(b"".join(uid_lines[:-1]), after))
    expect_rejected(lambda: uid_records(b"".join(uid_lines + uid_lines[:1]), after))
    bad_namespace = [dict(row) for row in cleanup["actual_namespace_checks"]]
    bad_namespace[0]["stderr"] = "ls: " + bad_namespace[0]["path"] + ": Permission denied\n"
    expect_rejected(lambda: namespace_checks(bad_namespace, expected_paths))
    bad_namespace[0]["stderr"] = "ls: /wrong/path: No such file or directory\n"
    expect_rejected(lambda: namespace_checks(bad_namespace, expected_paths))
    expect_rejected(lambda: namespace_checks(cleanup["actual_namespace_checks"][:-1], expected_paths))

    for label, raw in files.items():
        require(strict_file(paths[label]) == raw, "archived evidence changed during review")
    started = datetime.datetime.fromisoformat(result["started_utc"])
    finished = datetime.datetime.fromisoformat(result["finished_utc"])
    receipt = {
        "schema": "pocket4-native-v5-independent-cleanup-review-v1",
        "reviewed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "arm": args.arm,
        "classification": "PASS_ARCHIVED_CLEANUP_COMPLETENESS",
        "scope": "Independent read-only consistency/completeness review of saved v5 evidence; no new application or namespace execution",
        "production_ready": False,
        "reviewer_sha256": digest(strict_file(Path(__file__))),
        "original_runner_unchanged": True,
        "independently_rechecked_v5_condition": "UID-registry package names equal the complete packages-after set",
        "counts": {"before_packages": len(before), "after_packages": len(after), "uid_records": len(uids),
                   "third_party_packages": len(third_after), "owned_packages_and_uids_absent": len(owned),
                   "exact_host_and_actual_namespace_paths": len(expected_paths), "owned_resource_records_oom_zero": len(resources),
                   "in_memory_incomplete_evidence_negative_controls_rejected": 6},
        "full_before_after_sets_equal": True,
        "third_party_before_after_sets_equal": True,
        "uid_registry_covers_full_after_set": True,
        "bootstrap_exact_artifacts_and_uids_consistent": True,
        "all_namespace_absence_errors_exact_enoent_for_expected_path": True,
        "all_raw_uninstalls_successful": True,
        "saved_source_contracts_and_live_source_hashes_match": True,
        "saved_runtime_envelope_reports_success": True,
        "saved_boot_and_live_control_engine_hashes_match_arm": True,
        "default_signal_engine_scope": "R15/R16 immediately terminated owner is not independently map-sampled; prior live controls in the same arm supply the saved mapping evidence",
        "saved_main_resource_limits_equal": True,
        "archive_stable_during_review": True,
        "runtime_wall_seconds_from_saved_timestamps": (finished - started).total_seconds(),
        "full_package_set_sha256": digest(("\n".join(sorted(after)) + "\n").encode()),
        "inputs": {label: {"sha256": digest(raw), "bytes": len(raw)} for label, raw in sorted(files.items())},
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
