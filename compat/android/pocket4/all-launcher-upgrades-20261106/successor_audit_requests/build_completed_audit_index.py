#!/usr/bin/env python3
"""Build a local evidence index from already-settled APK audits; no runtime calls."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN_SHA = "d288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139"
GATE_SHA = "59568b064ea70628ae78a04755f3866d771a82b2907ded11122b2cdb1751c59d"
SCOPE_SHA = "489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4"
OFFICIAL_SHA = "56cffabe44e18702385863c5118c4768bbb2c229d9b3e77892a7fded50c64c34"

def pin(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert 1 <= args.through <= 13
    gate_path = HERE / "revisions/gate-r2-terminal-protocol/audit_serial_gate.py"
    assert pin(gate_path)["sha256"] == GATE_SHA
    spec = importlib.util.spec_from_file_location("exact_local_audit_gate", gate_path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    plan_path = HERE / "final-upgrades-r1/REQUEST_MANIFEST.json"
    plan, requests = gate.load_plan(plan_path, PLAN_SHA)
    state = HERE / "actual/batches-final-r1"
    decision = gate.inspect(plan, requests, PLAN_SHA, state)
    assert decision["state"] in ("NEXT_READY", "ALL_13_APK_AUDITS_SETTLED")
    assert len(decision["completed"]) == args.through
    scope_path = HERE.parent / "successor_install/actual/douyin-01/app-scope-after.private.json"
    assert pin(scope_path)["sha256"] == SCOPE_SHA
    scope = json.loads(scope_path.read_bytes())
    official_path = HERE / "actual/fcitx-microg-official-asset-comparison-r1.json"
    assert pin(official_path)["sha256"] == OFFICIAL_SHA
    official = {row["package"]: row for row in json.loads(official_path.read_bytes())["results"]}
    completed = {}
    evidence = [pin(plan_path), pin(gate_path), pin(scope_path), pin(official_path), pin(Path(__file__).resolve())]
    permission_rows = []
    for number in range(1, args.through + 1):
        folder = state / ("batch-%02d" % number)
        stdout = (folder / "stdout.original.json").read_bytes()
        value, raw = gate.decode_artifact(stdout)
        assert (folder / "artifact.original.json").read_bytes() == raw
        terminal = json.loads((folder / "terminal.original.json").read_bytes())
        artifact_pin = pin(folder / "artifact.original.json")
        for name in ("intent.json", "submitted-job.json", "process-request.json", "terminal.original.json",
                     "stdout.original.json", "artifact.original.json", "gate-status.stdout.original.json"):
            evidence.append(pin(folder / name))
        for app in value["apps"]:
            package = app["package"]
            assert package not in completed
            requested, defined = set(), set()
            apk_rows = []
            for apk in app["apks"]:
                declared = apk["declared_permissions"]
                assert declared["all_names_decoded"] is True and declared["declared_manifest_only"] is True
                for entry in declared["entries"]:
                    if entry["tag"].startswith("uses-permission"):
                        requested.add(entry["name"])
                    elif entry["tag"] == "permission":
                        defined.add(entry["name"])
                    permission_rows.append({"package": package, "apk_path": apk["path"],
                                            "declaration": entry,
                                            "effective_grant": "UNKNOWN_NOT_QUERIED"})
                apk_rows.append({key: apk[key] for key in ("path", "bytes", "sha256", "manifest", "signature")})
            row = {"package": package, "audit_status": "ACTUAL_APK_AUDIT_VERIFIED", "batch": number,
                   "job_id": terminal["job_id"], "uid": app["uid"], "base_manifest": app["base_manifest"],
                   "complete_apk_set": apk_rows, "data_directory_identities": app["data_directories"],
                   "requested_permission_names_exact": sorted(requested),
                   "defined_permission_names_exact": sorted(defined),
                   "actual_audit_artifact": artifact_pin,
                   "all_current_signers_equal_PM_records": app["all_current_signers_equal_PM_records"],
                   "effective_permission_grants": "UNKNOWN_NOT_QUERIED",
                   "business_QA_verified_by_this_index": False, "production_ready": False}
            if package in official:
                row["published_official_asset_comparison"] = official[package]
            completed[package] = row
    roster = [p for batch in plan["batches"] for p in batch["packages"]]
    assert len(roster) == len(set(roster)) == 45
    rows = []
    for package in roster:
        expected = scope["apps"][package]
        reference = {"uid": expected["uid"], "version_code": expected["version_code"],
                     "apk_set": [{k: apk[k] for k in ("path", "bytes", "sha256")} for apk in expected["apks"]],
                     "meaning": "Fixed final-scope reference; not a new APK audit of a pending package."}
        row = completed.get(package, {"package": package, "audit_status": "PENDING",
                                     "actual_manifest_version_name": None,
                                     "effective_permission_grants": "UNKNOWN_NOT_QUERIED",
                                     "business_QA_verified_by_this_index": False, "production_ready": False})
        rows.append({**row, "final_scope_reference": reference})
    pending = [p for p in roster if p not in completed]
    base = {"schema": "pocket4-settled-apk-audit-index-v1",
            "through_batch": args.through, "settled_batches": args.through,
            "launcher_packages_expected": 45, "launcher_packages_audited": len(completed),
            "launcher_packages_pending": len(pending), "pending_packages": pending,
            "runtime_epoch_sha256": plan["runtime_epoch_sha256"],
            "scope_boundary": "Each audit checks its request.packages against the fixed reference. The typed guard checks runtime; no individual batch proves all 46 packages.",
            "excluded_nonlauncher_package": "local.pocket4.actions.v2",
            "effective_permission_grants": "UNKNOWN_NOT_QUERIED",
            "production_ready_packages": 0, "cleanup_count": 0,
            "new_runtime_or_network_commands": 0,
            "packages": rows}
    declarations = {"schema": "pocket4-actual-manifest-permission-index-v1",
                    "source": "Exact decoded aapt AndroidManifest.xml declarations in settled audit artifacts.",
                    "effective_grants_are_not_inferred_from_declarations": True,
                    "entries": permission_rows}
    lines = ["# APK audit coverage through batch %02d" % args.through, "",
             "%d of 45 Launcher packages have complete actual APK audits; %d remain pending." %
             (len(completed), len(pending)),
             "Effective grants remain UNKNOWN_NOT_QUERIED. Production ready: 0. Cleanup: 0.", "",
             "## Settled package evidence", "",
             "| Package | UID | Actual version / code | min / target SDK | ABI | Exact APK SHA256 | Requested / defined permission names |",
             "| --- | ---: | --- | --- | --- | --- | --- |"]
    for package in roster:
        if package not in completed:
            continue
        row = completed[package]; manifest = row["base_manifest"]
        abis = sorted({abi for apk in row["complete_apk_set"] for abi in apk["manifest"]["native_abis"]})
        hashes = ", ".join(apk["sha256"] for apk in row["complete_apk_set"])
        lines.append("| %s | %s | %s / %s | %s / %s | %s | %s | %s / %s |" %
                     (package, row["uid"], manifest["version_name"], manifest["long_version_code"],
                      manifest["min_sdk"], manifest["target_sdk"], ", ".join(abis), hashes,
                      len(row["requested_permission_names_exact"]), len(row["defined_permission_names_exact"])))
    lines += ["", "## Remaining evidence gaps", "",
              "These package names are expected by the fixed 45-package plan. Their reference APK hashes are retained in index.json; those references are not marked as new audit results.", ""]
    lines += ["- " + package for package in pending]
    lines += ["", "Network operation, effective grants, login or visitor flow, long running behaviour, restart recovery, and production readiness are not established by this APK-only index.",
              "The declared-permissions index preserves every observed name and raw attribute; it does not strip names or infer a permission decision.", ""]
    assert not args.output.exists() and args.output.is_absolute()
    args.output.mkdir(mode=0o700, parents=True)
    published = []
    for name, raw in (("index.json", canonical(base) + b"\n"),
                      ("declared-permissions.json", canonical(declarations) + b"\n"),
                      ("COVERAGE.md", "\n".join(lines).encode())):
        with (args.output / name).open("xb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        published.append(pin(args.output / name))
    manifest = {"schema": "pocket4-apk-audit-index-evidence-pins-v1", "files": published,
                "source_and_actual_evidence": evidence, "next_batch_claimed": False,
                "remote_execution_performed": False}
    with (args.output / "SOURCE_AND_EVIDENCE_PINS.json").open("xb") as handle:
        handle.write(canonical(manifest) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    fd = os.open(args.output, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps({"audited": len(completed), "pending": len(pending),
                      "permission_declarations": len(permission_rows), "files": published,
                      "pins": pin(args.output / "SOURCE_AND_EVIDENCE_PINS.json")}, sort_keys=True))

if __name__ == "__main__":
    main()

