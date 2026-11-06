#!/usr/bin/env python3
"""Derive a retention/dependency plan from exact local receipts, never a device.

Only known source files below are read. No target path is opened, traversed,
deleted, moved or executed. Absolute paths are evidence references, not proof
that those paths still exist or are unused now.
"""
import sys
sys.dont_write_bytecode = True
import ast
import hashlib
import json
from pathlib import Path
from collections import Counter, defaultdict

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
SOURCES = [
    ("baseline", "recovery/independent_repair_r2/actual-execute-01/baseline.private.json", "actual_runtime"),
    ("qualification", "recovery/independent_repair_r2/actual-execute-01/qualification.private.json", "actual_runtime"),
    ("transition", "recovery/independent_repair_r2/actual-execute-01/actual-transition.private.json", "actual_runtime"),
    ("wrapper_activation", "recovery/independent_repair_r2/actual-execute-01/wrapper-activation.private.json", "actual_runtime"),
    ("wrapper_deployment", "recovery/independent_repair_r2/root-readback/actual-wrapper-deployment.original.json", "actual_runtime"),
    ("scope47", "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json", "actual_app_identity"),
    ("latest_native46_failure", "successor_audit_requests/actual/permissions-fixed45-r1/batch-03/artifact.original.json", "actual_partial_observation"),
    ("first_four_installs", "reference/completed-native-upgrades-20261106.json", "actual_installed_and_retained"),
    ("tools", "successor_audit_requests/actual/batches-final-r1/batch-01/artifact.original.json", "actual_tool_binding"),
    ("official_aapt2", "successor_audit_requests/diagnostics/google-maven-aapt2-host-proof-r3/actual/worker.stdout.original.json", "actual_tool_binding"),
    ("framework_build08_plan", "framework_provider_repair/normal06/current470-authorization-r1/sealed-r1/execution-plan.json", "reviewed_reference_not_existence_proof"),
    ("builder470_plan", "framework_provider_repair/normal06/builder470-current-qualification-r1/source-r1/execution-plan.json", "reviewed_actual_qualification_inputs"),
    ("framework_work", "framework_provider_repair/normal06/current470-authorization-r1/sealed-r1/actual-work-preparation.json", "actual_work_preparation"),
    ("framework_builder_result", "framework_provider_repair/normal06/current470-authorization-r1/sealed-r1/actual-builder470-result.json", "actual_builder_result"),
    ("framework_builder_qualification", "framework_provider_repair/normal06/current470-authorization-r1/sealed-r1/actual-current470-qualification-result.json", "actual_builder_qualification"),
    ("framework_build08_failure", "framework_provider_repair/normal06/current470-authorization-r1/actual-build08/fence-terminal.original.json", "actual_failed_build"),
    ("framework_contract", "framework_provider_repair/normal06/current470-authorization-r1/candidate-r1/capability-contract-map.actual.json", "actual_contract_reference"),
    ("qa_source_manifest", "successor_qa/reconstructed/source-generation-r2/recorder/source-manifest.json", "reconstructed_exact_source_manifest"),
    ("qa_current_stage_b", "successor_qa/partial_case_runtime_commit_r1/stage-b-candidate-r1/actual/joint.reconstructed.exact.json", "actual_qa_joint_evidence"),
    ("zbj_verified_candidate", "official_source_scripts/s43_zbj_operator_verification/actual/stdout.original.json", "actual_official_signature_metadata"),
]
INSTALLS = ("pdd-01", "taobao-01", "didi-01", "ctrip-01", "bili-01", "jd-02", "douyin-01")
STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def local_read(relative):
    path = PROJECT / relative
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    need(all(getattr(before, k) == getattr(after, k) for k in STAT), "LOCAL_INPUT_CHANGED")
    need(len(raw) == before.st_size <= 2097152, "BOUNDED_LOCAL_SOURCE")
    return raw


def valid_path(value):
    return (isinstance(value, str) and value.startswith("/") and "\n" not in value and "\x00" not in value and
            ":" not in value and all(part not in ("", ".", "..") for part in value[1:].split("/")) and
            not value.startswith(("/proc/", "/sys/", "/dev/", "/run/")))


def coordinates(path):
    return "android_init_root" if path.startswith(("/system/", "/vendor/", "/product/", "/system_ext/", "/apex/", "/data/")) else "host"


def extract_pin(value):
    if not isinstance(value, dict):
        return {}
    result = {k: value[k] for k in ("bytes", "sha256", "file", "identity", "device", "inode", "uid", "gid", "status") if k in value}
    for name in ("init_view", "zygote_view", "stat", "fstat"):
        if name in value:
            result[name] = value[name]
    return result


def main():
    sources, values, entries = {}, {}, {}
    def add(sid, pointer, path, category="EVIDENCE_OR_DECLARED_DEPENDENCY", pin=None, coordinate=None):
        if not valid_path(path):
            return
        coordinate = coordinate or coordinates(path)
        key = (coordinate, path)
        item = entries.setdefault(key, {"coordinate": coordinate, "path": path, "categories": [], "evidence": [],
            "current_existence_verified_by_this_task": False, "deletion_eligible": False,
            "reclaimable_bytes": None, "recursive_cleanup_authority": False})
        if category not in item["categories"]:
            item["categories"].append(category)
        evidence = {"source_id": sid, "json_pointer": pointer, "evidence_kind": sources[sid]["kind"]}
        if pin:
            evidence["recorded_pin_not_fresh_observation"] = pin
        if evidence not in item["evidence"]:
            item["evidence"].append(evidence)

    def walk(sid, value, pointer="", category="EVIDENCE_OR_DECLARED_DEPENDENCY"):
        if isinstance(value, dict):
            for name in ("path", "resolved_path", "declared_path", "source_root", "root", "work", "aosp_source", "out", "source_path"):
                if valid_path(value.get(name)):
                    add(sid, pointer + "/" + name, value[name], category, extract_pin(value))
            for key, child in value.items():
                if key not in ("path", "resolved_path", "declared_path", "source_root", "root", "work", "aosp_source", "out", "source_path"):
                    walk(sid, child, pointer + "/" + key, category)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(sid, child, pointer + "/" + str(index), category)
        elif valid_path(value):
            add(sid, pointer, value, category)

    for sid, relative, kind in SOURCES:
        raw = local_read(relative)
        sources[sid] = {"file": relative, "bytes": len(raw), "sha256": sha(raw), "kind": kind}
        value = json.loads(raw)
        values[sid] = value
        # The full QA evidence closure is protected; no raw UI is present here.
        walk(sid, value, category="PINNED_QA_EVIDENCE_DEPENDENCY" if sid.startswith("qa_") else "EVIDENCE_OR_DECLARED_DEPENDENCY")

    old_apks, current_private_apks, completed_installs = [], [], []
    def old_copy(sid, pointer, package, item):
        need(valid_path(item["path"]) and type(item["bytes"]) is int and len(item["sha256"]) == 64, "EXACT_RETAINED_OLD_APK")
        add(sid, pointer, item["path"], "RETAINED_PREVIOUS_APK_PENDING_PRODUCTION_REGRESSION", extract_pin(item), "host")
        old_apks.append({"package": package, **item, "evidence_source": sid, "pointer": pointer, "deletion_eligible": False})

    for index, item in enumerate(values["first_four_installs"]["completed_installs"]):
        package = item["package"]
        old_copy("first_four_installs", "/completed_installs/%d/preserved_previous_APK" % index, package, item["preserved_previous_APK"])
        completed_installs.append({"package": package, "evidence_source": "first_four_installs", "pointer": "/completed_installs/%d" % index})

    for name in INSTALLS:
        sid = "install_" + name
        relative = "successor_install/actual/" + name + "/stdout.raw.jsonl"
        raw = local_read(relative)
        sources[sid] = {"file": relative, "bytes": len(raw), "sha256": sha(raw), "kind": "actual_installed_and_retained"}
        parsed = [json.loads(line) for line in raw.splitlines()]
        need(len(parsed) == 2, "EXACT_INSTALL_STAGE_AND_RESULT")
        item = parsed[1]
        need(item["install_verified"] is True and item["outcome_unknown"] is False and item["errors"] == [], "ACTUAL_COMPLETE_INSTALL_RECEIPT")
        values[sid] = item
        package = item["package"]
        walk(sid, parsed)
        if item.get("previous_apk_retained"):
            old_copy(sid, "/1/previous_apk_retained", package, item["previous_apk_retained"])
        else:
            for index, pair in enumerate(item["previous_apks_retained"]):
                old_copy(sid, "/1/previous_apks_retained/%d/retained" % index, package, pair["retained"])
        copy = item["private_candidate_apk"]
        add(sid, "/1/private_candidate_apk", copy["path"], "VERIFIED_CURRENT_APK_REPRODUCTION_INPUT", extract_pin(copy), "host")
        current_private_apks.append({"package": package, **copy, "evidence_source": sid})
        for index, prior in enumerate(item["before"]["apks"]):
            add(sid, "/1/before/apks/%d" % index, prior["path"], "HISTORICAL_PM_MANAGED_APK_PATH_EXISTENCE_UNKNOWN", extract_pin(prior), "android_init_root")
        completed_installs.append({"package": package, "evidence_source": sid, "pointer": "/1"})

    baseline = values["baseline"]
    scope = values["scope47"]
    native = values["latest_native46_failure"]
    need(len(scope["apps"]) == 47 and native["native_catalog_comparison"]["observed_count"] == 46 and
         native["Android_namespace_commands"] == 0 and native["native_catalog_comparison"]["added_components"] ==
         ["com.example.ndk_tests/com.example.ndk_tests.NdkTestsActivity"], "EXACT_LATEST_KNOWN_SCOPE_GAP")
    active_roles = []
    for role, item in baseline["runtime"]["held"]["extra"].items():
        proc = item["held_proc"]
        active_roles.append({"role": role, "held_proc": proc, "namespaces": item["namespaces"], "root": item["root"],
                             "executable_file": item["executable_file"], "binary_pin": baseline["runtime"]["binaries"][role]})
        add("baseline", "/runtime/held/extra/" + role + "/held_proc/exe", proc["exe"], "ACTIVE_RUNTIME_EXECUTABLE_REFERENCE",
            baseline["runtime"]["binaries"][role], "android_init_root" if role in ("android_init", "composer", "surfaceflinger", "system_server", "zygote64") else "host")
    for index, item in enumerate(baseline["runtime"]["classpath"]["files"]):
        add("baseline", "/runtime/classpath/files/%d" % index, item["path"], "ACTIVE_FRAMEWORK_CLASSPATH_REFERENCE", extract_pin(item), "android_init_root")
    add("baseline", "/runtime/engine", "/system/lib64/libberberis_arm64.so", "ACTIVE_TRANSLATION_ENGINE_REFERENCE", baseline["runtime"]["engine"], "android_init_root")
    protected_apps = []
    for package, item in scope["apps"].items():
        for index, apk in enumerate(item["apks"]):
            add("scope47", "/apps/" + package + "/apks/%d" % index, apk["path"], "INSTALLED_APK_IN_PROTECTED_REFERENCE_SCOPE", extract_pin(apk), "android_init_root")
        data = []
        for key, info in item["data_directories"].items():
            path = "/data/" + key + "/0/" + package
            add("scope47", "/apps/" + package + "/data_directories/" + key, path, "APP_CE_DE_DATA_ALWAYS_PROTECTED_NO_CONTENT_TRAVERSAL",
                {**info, "path_derivation": "original user0 scope contract /data/{user,user_de}/0/{package}"}, "android_init_root")
            data.append({"path": path, "recorded_identity": info})
        protected_apps.append({"package": package, "uid": item["uid"], "version_code": item["version_code"],
            "apks": item["apks"], "data_directories": data, "deletion_eligible": False})

    external_jdk = []
    for name, binding in values["tools"]["tool_binding"].items():
        path = binding["pin"]["resolved_path"]
        category = "PINNED_SHARED_HOST_TOOL_NOT_CLEANUP_SCOPE"
        if path.startswith("/home/alex/Documents/"):
            category = "OTHER_PROJECT_EXACT_JDK_DEPENDENCY_NO_PARENT_TRAVERSAL"
            external_jdk.append({"name": name, "path": path, **binding})
        add("tools", "/tool_binding/" + name, path, category, {**binding["pin"], **binding["observed"]}, "host")

    # Literal paths from the exact generated recorder source, without importing
    # or executing that source. Relative constructions are not guessed here.
    relative = "successor_qa/reconstructed/source-generation-r2/recorder/source_contract.py"
    raw = local_read(relative); sid = "qa_source_contract"
    sources[sid] = {"file": relative, "bytes": len(raw), "sha256": sha(raw), "kind": "exact_reconstructed_qa_source_literal_reference"}
    tree = ast.parse(raw)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and valid_path(node.value):
            add(sid, "/python-literal/line-%d" % node.lineno, node.value, "CURRENT_QA_SOURCE_CONTRACT_REFERENCE")

    ordered = sorted(entries.values(), key=lambda x: (x["coordinate"], x["path"]))
    for number, item in enumerate(ordered, 1):
        item["id"] = "path-%04d" % number
        item["categories"].sort()
    old_apks.sort(key=lambda r: (r["package"], r["path"]))
    current_private_apks.sort(key=lambda r: r["package"])
    exact_host_paths = [item["path"] for item in ordered if item["coordinate"] == "host"]
    named_work_roots = sorted({"/".join(path.split("/")[:5]) for path in exact_host_paths if path.startswith("/home/alex/work/")})
    counts = Counter(category for item in ordered for category in item["categories"])
    catalog = {"schema": "pocket4-retention-evidence-path-catalog-v1", "derived_from_local_receipts_only": True,
        "target_host": "pocket4", "source_files": sources, "entries": ordered,
        "runtime_reference": {"runtime_epoch_sha256": baseline["runtime_epoch_sha256"], "framework_epoch_sha256": baseline["framework_epoch"]["sha256"],
            "boot_id": baseline["framework_epoch"]["binding"]["boot_id"], "roles": active_roles,
            "fresh_current_runtime_guard_executed_by_this_catalog": False},
        "installed_protected_reference": {"scope_packages": 47, "APK_count": sum(len(a["apks"]) for a in scope["apps"].values()),
            "apps": protected_apps, "complete_current_installed_or_launcher_set": False,
            "latest_observed_native_components": 46, "new_component_identity_pending": native["native_catalog_comparison"]["added_components"]},
        "retained_previous_APKs": old_apks, "retained_previous_APK_count": len(old_apks),
        "retained_previous_APK_recorded_logical_bytes": sum(item["bytes"] for item in old_apks),
        "retained_previous_APK_current_existence_or_allocated_blocks_rechecked": False,
        "current_private_APK_reproduction_inputs": current_private_apks,
        "completed_install_packages": sorted(x["package"] for x in completed_installs),
        "other_project_exact_JDK_dependencies": external_jdk,
        "known_named_work_roots_for_metadata_scope_review_only": named_work_roots,
        "root_names_do_not_prove_task_ownership_or_unused_status": True,
        "category_entry_counts": dict(sorted(counts.items())),
        "production_ready_apps": 0, "deletion_eligible_entries": 0, "reclaimable_bytes": None,
        "target_reads_performed": 0, "delete_move_stop_or_permission_actions": 0,
        "unresolved": ["Latest native component 46 needs its actual complete identity and fresh framework resolver; historical47 is not a complete current scope.",
            "Running image/rootfs host backing paths and live mount graph need a bounded held-proc mountinfo/config observation; directory names cannot prove them.",
            "No exact current or retired reDroid container/image ID or storage path was found in these local source receipts. Do not scan unrelated container stores by default.",
            "Current process FD/map aliases, cross-root hardlinks, reflinks/snapshots and current allocated blocks are not proved by historical file sizes.",
            "Old-named source, receipts, dependency records, layout directories and tool paths may still be required by current frozen contracts."]}
    raw = canonical(catalog)
    with (HERE / "PATH_CATALOG.json").open("xb") as stream:
        stream.write(raw)
    need((HERE / "PATH_CATALOG.json").read_bytes() == raw, "LOCAL_CATALOG_READBACK")
    summary = {"schema": "pocket4-retention-local-catalog-summary-v1", "catalog_bytes": len(raw), "catalog_sha256": sha(raw),
        "source_count": len(sources), "path_count": len(ordered), "host_paths": len(exact_host_paths),
        "android_root_paths": len(ordered) - len(exact_host_paths), "named_work_roots": len(named_work_roots),
        "retained_previous_APKs": len(old_apks), "retained_previous_APK_recorded_logical_bytes": catalog["retained_previous_APK_recorded_logical_bytes"],
        "other_project_JDK_exact_files": len(external_jdk), "current_protected_scope_packages": 47, "current_scope_exhaustive": False,
        "deletion_eligible_entries": 0, "reclaimable_bytes": None, "target_reads_performed": 0}
    with (HERE / "SUMMARY.json").open("xb") as stream:
        stream.write(canonical(summary))
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
