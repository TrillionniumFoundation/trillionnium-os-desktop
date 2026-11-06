#!/usr/bin/env python3
"""Prepare a local review plan only. No host, Android, shell, or build entry."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
REFERENCE = HERE / "reference/normal04"
CURRENT = PROJECT / "recovery/independent_repair_r2/actual-execute-01"
SOURCE_REF = "1f500f1f17a0f45710dbc4c6dd1af90cb064efbd"
SOURCE_PREFIX = "compat/android/pocket4/all-launcher-upgrades-20261106/framework_provider_repair/normal04"
RUNTIME_PINS = {
    "baseline.private.json": (44041, "7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8"),
    "qualification.private.json": (1587, "4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6"),
    "initial-app-scope.private.json": (57713, "19d742f98193a09403990ed3ee6944d4624a26690fb953d66cac4361af6f6d77"),
    "current_baseline_guard.py": (3213, "d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3"),
}
ROLES = {"daemon", "launcher", "android_init", "presenter", "surfaceflinger", "zygote64", "system_server", "composer"}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "DUPLICATE_JSON_KEY")
            value[key] = item
        return value
    def invalid(_):
        raise ValueError("NONFINITE_JSON_NUMBER")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def read_pin(path, expected=None):
    raw = path.read_bytes()
    pin = {"local_path": str(path), "bytes": len(raw), "sha256": digest(raw)}
    if expected is not None:
        require((len(raw), digest(raw)) == expected, "PIN_DIFFERS:" + str(path))
    return raw, pin


def literal_assignment(raw, name):
    tree = ast.parse(raw)
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    require(len(matches) == 1, "EXACT_ASSIGNMENT_REQUIRED:" + name)
    return ast.literal_eval(matches[0].value)


def prepare(args):
    documents, pins = {}, {}
    for name, expected in RUNTIME_PINS.items():
        raw, pins[name] = read_pin(CURRENT / name, expected)
        documents[name] = raw if name.endswith(".py") else parse(raw)
    guard = literal_assignment(documents["current_baseline_guard.py"], "PINS")
    baseline = documents["baseline.private.json"]
    qualification = documents["qualification.private.json"]
    initial = documents["initial-app-scope.private.json"]
    require(qualification["baseline"] == guard["baseline"], "GUARD_BASELINE_BINDING")
    require(guard["qualification"]["sha256"] == pins["qualification.private.json"]["sha256"], "GUARD_QUALIFICATION_BINDING")
    require(guard["baseline"]["sha256"] == pins["baseline.private.json"]["sha256"], "GUARD_BASELINE_PIN")
    require(baseline["schema"] == "pocket4-successor-runtime-baseline-v1", "BASELINE_SCHEMA")
    require(qualification["identity_qualified"] is True and qualification["old_native_pidfd_deaths_proved"] is True
            and qualification["initial_app_scope_unchanged"] is True, "ACTUAL_RESTART_IDENTITY_QUALIFICATION")
    require(qualification["production_ready"] is False and qualification["UI_or_install_runtime_admitted"] is False,
            "IDENTITY_QUALIFICATION_IS_NOT_PRODUCTION")
    fds = qualification["observation_fds"]
    require(fds["acquired"] == fds["closed"] and fds["remaining"] == 0 and fds["errors"] == [], "QUALIFICATION_FDS")
    runtime_sha = digest(canonical(baseline["runtime"]))
    require(runtime_sha == baseline["runtime_epoch_sha256"] == qualification["runtime_epoch_sha256"], "RUNTIME_DIGEST")
    runtime_manifest_raw, runtime_manifest_pin = read_pin(PROJECT / "recovery/SOURCE_PINS.json")
    require(digest(runtime_manifest_raw) == guard["manifest_sha"] == qualification["source_manifest_sha256"], "TYPED_GUARD_SOURCE_MANIFEST")
    runtime_manifest = parse(runtime_manifest_raw)
    for name, pin in runtime_manifest["files"].items():
        read_pin(PROJECT / "recovery" / name, (pin["bytes"], pin["sha256"]))
    times = baseline["sample_monotonic_ns"]
    require(len(times) == 3 and times == sorted(set(times)) and 10_000_000_000 <= times[-1] - times[0] <= 90_000_000_000,
            "QUALIFIED_OBSERVATION_SPAN")
    process_binding = baseline["runtime"]["held"]["process_snapshot"]["binding"]
    require(set(process_binding["processes"]) == ROLES and set(baseline["runtime"]["held"]["extra"]) == ROLES,
            "EIGHT_ACTUAL_ROLES_REQUIRED")
    require(initial["runtime_epoch_sha256"] == runtime_sha, "INITIAL_APP_SCOPE_EPOCH")
    source_pins = parse((REFERENCE / "SOURCE_PINS.json").read_bytes())["files"]
    parent_plan = parse((REFERENCE / "execution-plan.json").read_bytes())
    settlement = parse((REFERENCE / "actual/settlement-summary.json").read_bytes())
    terminal = parse((REFERENCE / "actual/job-status.json").read_bytes())
    require(settlement["normal_builder_Popen_reached"] is False and settlement["Soong_invoked"] is False
            and settlement["fence_observers_settled"] is True, "NORMAL04_NOT_SETTLED_BEFORE_BUILDER")
    require(terminal["output_durable"] is True and terminal["terminal_publication_confirmed"] is True
            and terminal["state"] == "failed" and terminal["exit_code"] == 1, "NORMAL04_DURABLE_TERMINAL")
    preserved, missing = {}, []
    for name, pin in source_pins.items():
        path = REFERENCE / name
        if path.exists():
            _, preserved[name] = read_pin(path, (pin["bytes"], pin["sha256"]))
        else:
            missing.append({"name": name, **pin, "state": "PIN_KNOWN_EXACT_BYTES_NOT_RESTORED_HERE"})
    scope = None
    scope_pin = None
    if args.settled_app_scope is not None:
        require(args.settled_app_scope_sha256 and args.settled_app_scope_host_path, "SETTLED_SCOPE_PIN_AND_HOST_PATH_REQUIRED")
        raw, scope_pin = read_pin(args.settled_app_scope)
        require(digest(raw) == args.settled_app_scope_sha256, "SETTLED_SCOPE_PIN")
        scope = parse(raw)
        require(scope["schema"] == "pocket4-versioned-app-scope-v1" and scope["runtime_epoch_sha256"] == runtime_sha,
                "SETTLED_SCOPE_RUNTIME")
        require(set(initial["apps"]) <= set(scope["apps"]), "PREVIOUS_SCOPE_MEMBER_MISSING_NEEDS_EXPLICIT_RECONCILIATION")
        require(scope_pin["sha256"] != pins["initial-app-scope.private.json"]["sha256"], "POST_UPGRADE_SCOPE_REQUIRED")
        scope_pin["path"] = args.settled_app_scope_host_path
    root = parent_plan["root"].replace("native-provider-build-04-", "native-provider-build-05-")
    require(root != parent_plan["root"], "DISTINCT_NORMAL05_ROOT")
    argv = list(parent_plan["argv"])
    argv[argv.index("--out") + 1] = root + "/android-out"
    plan = {
        "schema": "pocket4-normal05-local-review-plan-v1",
        "state": "PLAN_ONLY_AWAITING_SETTLED_APP_SCOPE_AND_EXACT_PACKET_REVIEW" if scope is None else "PLAN_ONLY_INPUT_SCOPE_PINNED_EXACT_PACKET_NOT_PREPARED",
        "created_from_actual_records_only": True,
        "remote_submitted": False, "host_jobs_submitted": 0, "Main_actions": 0, "Android_actions": 0,
        "Main_reads_performed_in_this_preparation": 0, "builder_started": False, "Soong_invoked": False,
        "production_ready": False, "cleanup_eligible": False,
        "source_parent": {"repository": "TrillionniumFoundation/trillionnium-os-desktop", "ref": SOURCE_REF, "prefix": SOURCE_PREFIX},
        "normal04_outcome": {"job_id": settlement["job_id"], "state": settlement["state"],
                             "builder_started": False, "Soong_invoked": False, "fence_observers_settled": True,
                             "evidence": [read_pin(REFERENCE / "actual" / name)[1] for name in
                                          ("normal04-resource-admission.json", "normal04-outer-terminal.json", "job-status.json", "settlement-summary.json")]},
        "candidate_execution": {"host": "pocket4", "operator_uid": 1000, "root": root,
                                "work": parent_plan["work"], "out": root + "/android-out", "argv": argv,
                                "targets": parent_plan["targets"], "dependency_mode": "Strict", "ALLOW_MISSING_DEPENDENCIES": False,
                                "idempotency_key_proposed": "pocket4-native-typed-ingress-framework-strict-native-provider-two-target-build-05-20261106",
                                "single_explicit_attempt_only": True, "automatic_retry": False,
                                "request_bytes": None, "request_sha256": None, "exact_stdin_sha256": None},
        "resources": {"memory_max_bytes": 10 * 1024**3, "memory_swap_max_bytes": 0, "owned_memory_swap_current_required": 0,
                      "fresh_MemAvailable_min_bytes": 15 * 1024**3, "cpu_quota_percent": 200, "jobs": 1,
                      "cpu_affinity_rule": "Require at least four allowed CPUs, place owned build on last two; leave at least two outside this build affinity.",
                      "builder_wait_seconds": 6100, "global_swap_is_owned_budget": False,
                      "admission": "Read fresh /proc/meminfo inside the exact owned build cgroup immediately before admission; preserve raw receipt even on rejection.",
                      "on_rejection": "Stop with actual terminal; no automatic retry, no threshold reduction, no Main resource changes or unrelated process termination."},
        "inherited_build_contract": {key: parent_plan[key] for key in
                                     ("builder_sha256", "builder_result_sha256", "builder_source_manifest_sha256", "qualification_result_sha256",
                                      "work_preparation_sha256", "normal_lock_paths", "locked_neuralnetworks_commit", "locked_car_commit_unchanged")},
        "source_materialization": {"provider_lock_sha256": source_pins["actual-provider-source-lock.json"]["sha256"],
                                   "expected_locked_projects": 225, "expected_root_links": 8,
                                   "mode": "Existing Rust source materialization and sparse reconciliation under original package-build.lock and aosp-source-update.lock.",
                                   "empty_defaults_allowed": False, "synthetic_manifest_allowed": False,
                                   "existing_original_builder_or_shared_AOSP_modified_by_preparation": False,
                                   "actual_provider_reuse_fresh_verification_pending": True,
                                   "official_latest_framework_freshness_proved_by_this_plan": False},
        "runtime_binding": {"source": "Actual independent r2 stop/retire/start qualification, never copied normal04 PID constants.",
                            "guard": {**pins["current_baseline_guard.py"], "path": guard["root"] + "/current_baseline_guard.py"},
                            "guard_source_manifest": {**runtime_manifest_pin, "path": guard["root"] + "/source/SOURCE_PINS.json"},
                            "baseline": guard["baseline"], "qualification": guard["qualification"],
                            "runtime_epoch_sha256": runtime_sha, "framework_epoch_sha256": baseline["framework_epoch"]["sha256"],
                            "roles": sorted(ROLES), "process_binding": process_binding,
                            "limits": baseline["runtime"]["limits"], "fresh_guard_check_performed": False,
                            "existing_guard_api": "current_guard(); check_app_scope(pinned_latest_scope, exact_scope_packages)",
                            "guard_or_recovery_sources_changed": False, "discovery_or_adoption_of_replacements_allowed": False,
                            "inherited_Main_QA_pass": False, "UI_or_install_runtime_admitted_by_plan": False},
        "app_scope_binding": {"state": "UNKNOWN_AWAITING_ALL_CURRENT_INSTALL_JOBS_SETTLED" if scope is None else "SAVED_SCOPE_PINNED_FRESH_CHECK_PENDING",
                              "reference": scope_pin, "packages": None if scope is None else sorted(scope["apps"]),
                              "package_count": None if scope is None else len(scope["apps"]),
                              "initial_scope_historical_reference": pins["initial-app-scope.private.json"],
                              "initial_scope_package_count": len(initial["apps"]),
                              "initial_scope_accepted_as_post_upgrade_scope": False, "fresh_launcher_resolver_claimed": False},
        "minimal_source_change_plan": [
            {"file": "framework_build.py", "change": "Use distinct normal05 owned root/output only; retain builder bytes, source pins, strict targets, original work locks, resource admission, child retirement and completion gates."},
            {"file": "main_snapshot.py", "change": "Use exact existing current typedguard, baseline/qualification pins and final app-scope reference. Derive all eight protected roles from actual baseline; keep paired read-only process/cgroup observations, counters, FD retirement and 15-second observation budget. No new runtime permissions or QA claims."},
            {"file": "capture_lifecycle.py", "change": "Regenerate protected PID exclusion set from the verified baseline process binding including composer; retain kernel-proven owned-child-only signals and existing cleanup implementation."},
            {"file": "root_snapshot_supervisor.py", "change": "Update exact source hashes and eight-role description after source generation; retain fixed modes, 15-second observation/5-second retirement, subreaper and complete output/child/FD qualification."},
            {"file": "fenced_build.py", "change": "Update root and source hashes; compare typedguard baseline/runtime/framework and final app scope bindings pre/post. Preserve original Main limits and zero OOM delta. Mark all runtime/build QA conclusions separately."},
            {"file": "pure_controls.py", "change": "Retain strict source/resource/cleanup negative cases; replace old-role fixtures with baseline-derived eight-role inputs and add stale baseline/scope/guard and missing-composer cases. Report actual new results only after running these pure controls."},
            {"file": "stage.py / SOURCE_PINS.json / transport-boundary.py", "change": "Rebuild the exact fixed packet after all input bytes are present; immutable new root, exact pin verification, AST compile, reviewed controls and source sealing before submission."},
        ],
        "verification_required_before_dispatch": [
            "Root supplies final post-upgrade scope and confirms every concurrent Main install/observation/lifecycle job settled.",
            "Recover every required original source/receipt byte and validate the normal04 pins; do not fabricate missing packet members.",
            "Generate and review actual normal05 diff/exact request; no string substitution of old PID constants as proof.",
            "Run relevant pure negative controls locally; keep actual results separate from Android app/core-flow evidence.",
            "On host run, rerun existing four capture lifecycle controls, exact current typedguard/app scope checks and original resource admission; fresh failure is terminal.",
            "During build, root freezes lifecycle/install changes that would invalidate the reviewed baseline/app scope. No new ADB dependency.",
        ],
        "incomplete_packet_inputs": missing,
        "evidence_interpretation": {"normal04_45_pure_controls_are_historical": True,
                                    "normal05_pure_controls_run": False, "normal05_runtime_lifecycle_controls_run": False,
                                    "normal05_Java_Android_JNI_qualification": "UNKNOWN_NOT_RUN",
                                    "strict_two_target_build_success_is_full_framework_deployment": False,
                                    "strict_two_target_build_success_is_all_app_production": False,
                                    "original_r1_outcome": "UNKNOWN_RETAINED_NOT_REWRITTEN",
                                    "reDroid": "RETIRED_NO_NEW_TARGET"},
        "cleanup": {"eligible": False, "executed": False,
                    "required_before_old_version_cleanup": "All actual launcher apps plus final framework, current identities and applicable real flows pass; UNKNOWN reconciled; final source/config/reproduction manifest and lightweight receipts retained.",
                    "eventual_scope": "Precisely identified obsolete framework/app versions, build outputs and experiments; no permanent old-binary retention requirement after acceptance."},
    }
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settled-app-scope", type=Path)
    parser.add_argument("--settled-app-scope-sha256")
    parser.add_argument("--settled-app-scope-host-path")
    parser.add_argument("--output", type=Path, default=HERE / "execution-plan.json")
    args = parser.parse_args()
    plan = prepare(args)
    raw = (json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"state": plan["state"], "path": str(args.output), "bytes": len(raw), "sha256": digest(raw),
                      "host_jobs_submitted": 0, "Soong_invoked": False, "production_ready": False}))


if __name__ == "__main__":
    main()
