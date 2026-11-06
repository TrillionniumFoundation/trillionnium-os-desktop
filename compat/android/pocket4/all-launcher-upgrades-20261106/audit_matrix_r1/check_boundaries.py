#!/usr/bin/env python3
"""Small controls against the actual read-only matrix inputs; no synthetic PASS."""
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
spec = importlib.util.spec_from_file_location("evidence_matrix", HERE / "build_matrix.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fd_census():
    result = {}
    # Listing closes its own directory FD before any fstat. Never close unknown FDs.
    names = os.listdir("/proc/self/fd")
    for name in names:
        try:
            value = os.fstat(int(name))
            result[name] = (value.st_dev, value.st_ino, value.st_mode, os.readlink("/proc/self/fd/" + name))
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno != 9:
                raise
    return result


def rejects(call, expected):
    try:
        call()
    except RuntimeError as error:
        assert str(error) == expected, (str(error), expected)
    else:
        raise AssertionError("negative control accepted")


def main():
    before = fd_census()
    cases = []
    index = json.loads((PROJECT / m.INDEX).read_bytes())
    actual_packages = [row["package"] for row in index["launcher_apps"]]
    rejects(lambda: m.same_launcher_set(actual_packages + ["new.actual.launcher"], actual_packages),
            "FRESH_RESOLVER_ADDED_OR_MISSING_PACKAGE_REQUIRES_EXPLICIT_SCOPE_REVISION")
    rejects(lambda: m.same_launcher_set(actual_packages[:-1], actual_packages),
            "FRESH_RESOLVER_ADDED_OR_MISSING_PACKAGE_REQUIRES_EXPLICIT_SCOPE_REVISION")
    cases.append({"name": "resolver_added_and_missing_package_cannot_disappear", "passed": True})
    failed = json.loads((PROJECT / "successor_audit_requests/actual/batches-final-r1/batch-13/artifact.original.json").read_bytes())
    fixture = next(a for a in failed["apps"] if a["package"] == "local.pocket4.fixture")
    assert fixture["PM_version_code"] == 0 and fixture["base_manifest"] is None
    manifest = m.current_manifest(fixture)
    assert manifest["version_name"] is None and manifest["version_code"] is None and manifest["historical_name_substituted"] is False
    cases.append({"name": "actual_fixture_code_zero_does_not_invent_manifest_version", "passed": True})
    unknown = m.unknown_permissions()
    assert unknown["runtime_grants"] is None and unknown["requested_permissions"] is None
    assert unknown["state"] == "UNKNOWN_NOT_QUERIED" and unknown["missing_does_not_mean_denied"] is True
    beike = next(a for a in json.loads((PROJECT / "successor_audit_requests/actual/batches-final-r1/batch-03/artifact.original.json").read_bytes())["apps"] if a["package"] == "com.lianjia.beike")
    declarations = m.permission_projection(beike)
    raw = [e for a in beike["apks"] for e in a["declared_permissions"]["entries"]]
    projected = [e for a in declarations["per_APK"] for e in a["entries"]]
    assert raw == projected and declarations["grant_inference_permitted"] is False
    cases.append({"name": "actual_permission_declarations_preserved_not_interpreted_as_grants", "passed": True})
    raw = (PROJECT / "successor_install/actual/jd-02/stdout.raw.jsonl").read_bytes()
    jd = json.loads(raw.splitlines()[-1])
    assert len(jd["before"]["apks"]) == len(m.retained_set(jd["before"]["apks"], jd)) == 2
    missing = copy.deepcopy(jd)
    missing["previous_apks_retained"].pop()
    rejects(lambda: m.retained_set(jd["before"]["apks"], missing), "ALL_PREVIOUS_BASE_AND_SPLITS_REQUIRED")
    cases.append({"name": "actual_JD_base_plus_split_requires_both_retained_items", "passed": True})
    base = PROJECT / "successor_audit_requests/actual/batches-final-r1/batch-13"
    term, output = json.loads((base / "terminal.original.json").read_bytes()), (base / "stdout.original.jsonl").read_bytes()
    rejects(lambda: m.terminal(term, output), "AUTHORITATIVE_TERMINAL_STATE")
    m.terminal(term, output, "failed", 1)
    truncated = dict(term)
    truncated["output_complete"] = False
    rejects(lambda: m.terminal(truncated, output, "failed", 1), "DURABLE_COMPLETE_TERMINAL")
    cases.append({"name": "actual_failed_or_incomplete_terminal_cannot_be_success", "passed": True})
    inputs = m.Inputs()
    result = m.build(inputs)
    inputs.recheck()
    s = result["summary"]
    assert (s["current_Launcher_packages"], s["original_eight"], s["APK_audit_attempted_apps"],
            s["APK_joint_audit_passed_apps"], s["APK_joint_audit_passed_APKs"], s["completed_upgrades"]) == (45, 8, 45, 42, 82, 11)
    assert s["production_ready_apps"] == s["cleanup_eligible_apps"] == s["old_products_deleted_bytes"] == 0
    partial = [a for a in result["apps"] if a["APK_audit"]["batch"]["batch"] == 13]
    assert len(partial) == 3 and all(a["APK_audit"]["joint_qualified"] is False for a in partial)
    assert all(a["production_ready"] is False and a["cleanup_eligible"] is False for a in result["apps"])
    cases.append({"name": "all_actual_sources_revalidated_42_joint_pass_3_failed_batch_observations", "passed": True})
    after = fd_census()
    assert before == after
    print(json.dumps({"schema": "pocket4-matrix-local-controls-v1", "local_uid": os.getuid(), "local_euid": os.geteuid(),
        "cases": cases, "passed": len(cases), "skipped": 0, "process_fd_identities_unchanged": True,
        "runtime_jobs_submitted": 0, "gate_claims": 0, "private_UI_read": False,
        "builder_sha256": hashlib.sha256((HERE / "build_matrix.py").read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
