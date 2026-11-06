#!/usr/bin/env python3
"""Local-only deterministic assembly; no imports or invocation of device work."""
import sys
sys.dont_write_bytecode = True
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
OUT = HERE / "observer-candidate-r2"
PARENT = PROJECT / "successor_audit_requests/current_services_r4"
STAGE = "/home/alex/work/pocket4-retention-metadata-source-20261106-r2"
OUTPUT = "/home/alex/work/pocket4-retention-metadata-observation-20261106-r2"
EPOCH = "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9"
GUARD = {"path": "/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py", "bytes": 3213,
         "sha256": "d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3"}
PROTECTED_SCOPE = {"path": "/home/alex/work/pocket4-current-explicit-48-app-observation-20261106-r1/app-scope.private.json",
                   "bytes": 59957, "sha256": "b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4"}
SOURCES = {
    "observe_current_services.py": (39573, "4fda5cdf8fda65155c4187a1e8e5381aba59011329c824b98ad2e0c0b8aa8f0e"),
    "owned_readonly_lifetime.py": (18837, "ad2db51aa4445e6e5b5dc07439182556d51ec629cd8487ac9d3b1e5cf947a55c"),
}


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def pin(path, raw):
    return {"path": path, "bytes": len(raw), "sha256": sha(raw)}


def put(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    target = OUT / name
    with target.open("xb") as file:
        file.write(raw)
    need(target.read_bytes() == raw, "EXACT_NEW_LOCAL_READBACK")
    return {"name": name, "bytes": len(raw), "sha256": sha(raw)}


def segments(source):
    return {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def assignment(source, name, value):
    rows = [n for n in ast.parse(source).body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name]
    need(len(rows) == 1, "EXACT_ASSIGNMENT")
    return source.replace(ast.get_source_segment(source, rows[0]), name + " = " + repr(value), 1)


def main():
    OUT.mkdir(mode=0o700)
    inherited = {}
    for name, expected in SOURCES.items():
        raw = (PARENT / name).read_bytes()
        need((len(raw), sha(raw)) == expected, "EXACT_ACTUAL_R4_SOURCE")
        inherited[name] = raw.decode()
    typed_path, tree_path = HERE / "TYPED_REFERENCES.json", HERE / "TREE_SCOPES.review-only.json"
    typed, trees = json.loads(typed_path.read_bytes()), json.loads(tree_path.read_bytes())
    refs = [{"id": r["catalog_id"], "coordinate": r["coordinate"], "path": r["path"]}
            for r in typed["entries"] if r["coordinate"] != "cgroup_membership_reference_not_filesystem_path"]
    need(len(refs) == 793 and len(trees["roots"]) == 16, "EXACT_TYPED_INITIAL_SCOPE")
    ndk_path = PROJECT / "successor_audit_requests/native46_discovery_r1/actual/artifact.original.json"
    ndk_raw = ndk_path.read_bytes()
    need((len(ndk_raw), sha(ndk_raw)) == (112546, "69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400"), "EXACT_ACTUAL_NDK_OBSERVATION")
    ndk = json.loads(ndk_raw)
    need(ndk["ok"] is True and ndk["errors"] == [] and ndk["current_scope_47_unchanged"] is True and
         ndk["new_scope_published"] is False and ndk["new_signature_verification_performed"] is False, "ACTUAL_DISCOVERY_LIMITS")
    app = ndk["new_package_identity"]
    need(app["package"] == "com.example.ndk_tests" and app["uid"] == 10162 and app["version_code"] == 0 and
         len(app["apks"]) == 1 and app["apks"][0]["bytes"] == 1397258, "EXACT_NDK_IDENTITY")
    paths = [app["code_path"], app["apks"][0]["path"], "/data/user/0/" + app["package"], "/data/user_de/0/" + app["package"]]
    for i, path in enumerate(paths, 1):
        need(path not in {r["path"] for r in refs}, "NO_DUPLICATE_ADDED_REFERENCE")
        refs.append({"id": "ndk-ref-%02d" % i, "coordinate": "held_android_init_root", "path": path})
    apps = json.loads((PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json").read_bytes())["apps"]
    scope_actual_path = PROJECT / "successor_audit_requests/explicit48_scope_r1/actual/worker.stdout.original.json"
    scope_actual_raw = scope_actual_path.read_bytes()
    need((len(scope_actual_raw), sha(scope_actual_raw)) == (10290, "aaa24285be227f4ad52fe63e5a2a06af63f7bab571fb5cf4d99e6d0ab02f12d1"), "EXACT_ACTUAL_48_WORKER")
    scope_actual = json.loads(scope_actual_raw)
    need(scope_actual["ok"] is True and scope_actual["errors"] == [] and
         scope_actual["original_47_unchanged"] is True and scope_actual["new_package_matches_actual_discovery"] is True and
         scope_actual["new_signature_verification_performed"] is False and scope_actual["UI_or_install_admitted"] is False and
         scope_actual["observation"]["app_scope"] == PROTECTED_SCOPE, "ACTUAL_48_IDENTITY_ONLY_SCOPE_REQUIRED")
    packages = scope_actual["packages"]
    need(len(packages) == len(set(packages)) == 48 and packages == sorted((*apps, "com.example.ndk_tests")),
         "EXACT_ACTUAL_48_PROTECTED_SET")
    validation_path = PROJECT / "successor_audit_requests/explicit48_scope_r1/actual/root-validation.actual.json"
    validation_raw = validation_path.read_bytes()
    need((len(validation_raw), sha(validation_raw)) == (1330, "e66b00681144b4ba1049cab4e429c44f33ab5e1e1aa3e8c190776acb71b5f73b"), "ROOT_ACTUAL_48_JOINT_VALIDATION")
    validation = json.loads(validation_raw)
    need(validation["scope"] == PROTECTED_SCOPE and validation["job_id"] == "1a1b31300b9-fc05-8095" and
         validation["status"] == "PASS_IDENTITY_SCOPE_ONLY", "ACTUAL_48_JOINT_SCOPE_PIN")
    origin_pins = {str(p.relative_to(PROJECT)): {"bytes": len(p.read_bytes()), "sha256": sha(p.read_bytes())}
                   for p in (typed_path, tree_path, ndk_path, scope_actual_path, validation_path)}
    scope = {"schema": "pocket4-retention-metadata-scope-v1", "references": refs, "trees": trees["roots"],
        "protected_scope_reference": PROTECTED_SCOPE, "protected_packages": packages, "origin_pins": origin_pins,
        "complete_current_scope_claimed": False,
        "additional_reference_evidence": {"source": str(ndk_path.relative_to(PROJECT)), "bytes": len(ndk_raw), "sha256": sha(ndk_raw),
            "package": app["package"], "uid": app["uid"], "version_code": app["version_code"],
            "scope_published_by_observer": False, "signature_verified_by_observer": False,
            "purpose": "Protect four actual new-package paths as metadata references without extending UI or install authority."}}
    scope_raw = canonical(scope)
    need(len(scope_raw) <= 262144, "SCOPE_SINGLE_PIN_READER_BOUND")
    scope_pin = pin(STAGE + "/scope.review-only.json", scope_raw)
    put("scope.review-only.json", scope_raw)
    original = inherited["observe_current_services.py"]
    common_names = ("need", "sha", "canonical", "parse", "read_root_pin", "load_source")
    definitions = segments(original)
    common = "\n\n".join(definitions[name] for name in common_names) + "\n\n"
    header = '#!/usr/bin/env python3\n"""Bounded metadata-only retention observation; never a cleanup or UI action."""\n'
    header += "import argparse,base64,errno,fcntl,hashlib,json,os,re,stat,sys,time,types,zlib\nfrom pathlib import Path\nsys.dont_write_bytecode=True\n"
    constants = {"EPOCH": EPOCH, "STAGE": STAGE, "OUTPUT": OUTPUT, "GUARD": GUARD, "SCOPE_PIN": scope_pin,
                 "PROTECTED_SCOPE": PROTECTED_SCOPE, "PROTECTED_PACKAGES": packages, "REFERENCE_COUNT": len(refs),
                 "STAT": ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")}
    header += "\n".join(name + " = " + repr(value) for name, value in constants.items()) + "\n\n"
    worker_raw = (header + common + (HERE / "observer_body.py.inc").read_text()).encode()
    compile(worker_raw, "observe_retention.py", "exec")
    put("observe_retention.py", worker_raw)
    worker_pin = pin(STAGE + "/observe_retention.py", worker_raw)
    request = {"schema": "pocket4-bounded-retention-observation-request-v1", "guard": GUARD, "scope": scope_pin,
               "worker": worker_pin, "output_root": OUTPUT}
    request_raw = canonical(request)
    put("request.review-only.json", request_raw)
    config = {"schema": "pocket4-owned-readonly-observation-config-v1", "kind": "retention", "stage_root": STAGE,
              "worker": worker_pin, "request": pin(STAGE + "/request.review-only.json", request_raw),
              "prior_source": {"bytes": SOURCES["owned_readonly_lifetime.py"][0], "sha256": SOURCES["owned_readonly_lifetime.py"][1],
                               "preserved": True, "actual_prior_execution_job": "1a1b22e95d0-fc05-7cd4", "scope_authority_not_inherited": True}}
    wrapper = assignment(inherited["owned_readonly_lifetime.py"], "CONFIG", config)
    wrapper = wrapper.replace('CONFIG["kind"] in ("explicit47", "calendar", "services")', 'CONFIG["kind"] == "retention"', 1)
    wrapper = wrapper.replace('CONFIG["kind"] in ("calendar", "services")', 'CONFIG["kind"] == "retention"', 1)
    old_gate = segments(wrapper)["worker_gate"]
    new_gate = '''def worker_gate(value, returned):
    need(returned == 0 and value.get("schema") == "pocket4-bounded-retention-observation-v1" and
         value.get("ok") is True and value.get("errors") == [] and value.get("automatic_retry") is False and
         value.get("production_ready") is False and value.get("process_FDs_before") == value.get("process_FDs_after"),
         "RETENTION_WORKER_DID_NOT_PASS")
    guard = value.get("guard_before", {})
    need(guard.get("schema") == "pocket4-successor-main-guard-v1" and
         guard.get("runtime_epoch_sha256") == "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9" and
         value.get("guard_after") == guard and retired(value.get("owned_descriptors_final")) and
         retired(value.get("lease_FDs_final")) and value.get("action_lock_released") is True,
         "RETENTION_RUNTIME_OR_FD_GATE_FAILED")
    need(value.get("status") == "BOUNDED_DEPENDENCY_METADATA_OBSERVED_WITH_EXPLICIT_GAPS" and
         value.get("bounded_observation_finished") is True and value.get("scope_references_unchanged") is True and
         value.get("protected_scope_before") == value.get("protected_scope_after") and
         value.get("current_scope_reference", {}).get("sha256") == "b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4" and
         value.get("exact_reference_summary", {}).get("count") == 797 and len(value.get("tree_observations", [])) == 16 and
         value.get("reclaimable_bytes") is None and value.get("cleanup_eligible") == 0 and
         value.get("inventory_exhaustive_or_cleanup_qualified") is False and value.get("complete_installed_package_set_claimed") is False and
         value.get("old_failed_or_unknown_receipts_reclassified") is False,
         "RETENTION_METADATA_MUST_NOT_PROMOTE_CLEANUP")
    actions = ("deletions", "moves", "existing_permission_changes", "existing_process_signals", "UI_actions", "App_launches",
               "installs", "permission_changes", "native_command_count", "Android_namespace_commands", "ADB_commands",
               "business_data_content_reads", "worker_direct_commands")
    need(all(type(value.get(key)) is int and value[key] == 0 for key in actions), "RETENTION_READ_ONLY_BOUNDARY")'''
    wrapper = wrapper.replace(old_gate, new_gate, 1)
    wrapper = wrapper.replace("seconds=1000)", "seconds=220)", 1)
    wrapper_raw = wrapper.encode()
    compile(wrapper_raw, "owned_readonly_lifetime.py", "exec")
    put("owned_readonly_lifetime.py", wrapper_raw)
    changed = {name for name in segments(wrapper) if segments(wrapper)[name] != segments(inherited["owned_readonly_lifetime.py"])[name]}
    need(changed == {"enter", "decode_worker", "worker_gate", "main"}, "ONLY_REVIEWED_OWNED_WRAPPER_CHANGES")
    need(all(segments(worker_raw.decode())[name] == definitions[name] for name in common_names), "SIX_ORIGINAL_SOURCE_FUNCTIONS_UNCHANGED")
    stage_original = (PARENT / "stage_and_run_services.py").read_text()
    files = [
        {"name": name, "bytes": len((OUT/name).read_bytes()), "sha256": sha((OUT/name).read_bytes())}
        for name in ("owned_readonly_lifetime.py", "observe_retention.py", "request.review-only.json", "scope.review-only.json")]
    stage = assignment(stage_original, "ROOT", STAGE)
    stage = assignment(stage, "FILES", files)
    stage = stage.replace("New exact source/input stage, then five fixed read-only PackageManager queries.", "New exact metadata-only source/input stage; no native or Android commands.")
    stage = stage.replace("pocket4-current-readonly-services-source-stage-v4", "pocket4-retention-metadata-source-stage-v1")
    stage = stage.replace("pocket4-current-readonly-services-source-stage-result-v4", "pocket4-retention-metadata-source-stage-result-v1")
    payload = {"schema": "pocket4-retention-metadata-source-stage-v1", "files": [{"name": row["name"], "text": (OUT/row["name"]).read_text()} for row in files]}
    payload_raw = canonical(payload)
    need(len(payload_raw) < 1048576, "PROCESS_STDIN_TOOL_BOUND")
    stage = stage.replace("raw=sys.stdin.buffer.read(262145);need(0<len(raw)<=262144,'BOUNDED_EXACT_INPUT')",
                          "raw=sys.stdin.buffer.read(%d);need(len(raw)==%d,'BOUNDED_EXACT_INPUT')" % (len(payload_raw)+1, len(payload_raw)))
    compile(stage, "stage_and_run.py", "exec")
    put("stage_and_run.py", stage)
    put("stage.stdin.original.json", payload_raw)
    packet = {"host": "pocket4", "executable": "/usr/bin/sudo", "args": ["-n", "/usr/bin/python3", "-I", "-B", "-c", stage],
              "cwd": "/", "stdin": payload_raw.decode(), "timeout_seconds": 240, "cpu_quota_percent": 25,
              "memory_max_bytes": 536870912, "nice": 10, "idempotency_key": "sidecar-evidence-20261106-retention-metadata-observe-r2"}
    put("process-request.review-only.json", canonical(packet))
    for name, before, after in (("owned-against-actual-r4.diff", inherited["owned_readonly_lifetime.py"], wrapper),
                               ("stager-against-actual-r4.diff", stage_original, stage)):
        put(name, "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="actual-current-services-r4", tofile="independent-retention-observer-r1")))
    review = {"schema": "pocket4-retention-observer-source-review-v1", "remote_submitted": False,
        "new_scope_authority_or_cleanup_authority": False,
        "original_sources": {name: {"bytes": value[0], "sha256": value[1]} for name, value in SOURCES.items()},
        "source_functions_copied_exactly": list(common_names), "owned_functions_changed": sorted(changed),
        "owned_other_functions_unchanged": sorted(set(segments(wrapper)) - changed),
        "direct_commands": [], "source_stage_pins": files, "source_stage_input_bytes": len(payload_raw),
        "scope": {"literal_catalog_references": 795, "filesystem_references_from_original_catalog": 793,
                  "host_references": 488, "Android_references_including_new_NDK": 309, "cgroup_not_traversed": 2,
                  "added_actual_NDK_references": 4, "total_filesystem_references": len(refs), "tree_roots": 16,
                  "protected_subset_guard": PROTECTED_SCOPE, "does_not_publish_48scope": True},
        "observation_semantics": "An owned normal observation can report bounded incomplete trees or exact missing paths. It never claims exhaustive inventory, closed external references, or reclaimable bytes. Runtime/lease/descriptor errors still fail the entire joint result.",
        "private_output_policy": "Only pins, metadata counters and known reference IDs are public; raw maps, mount options, paths, FD metadata and tree entries stay in the new root-private output.",
        "files": {p.name: {"bytes": len(p.read_bytes()), "sha256": sha(p.read_bytes())} for p in sorted(OUT.iterdir()) if p.is_file()}}
    put("SOURCE_REVIEW.json", canonical(review))
    print(json.dumps({"ok": True, "source": worker_pin, "wrapper": pin(STAGE+"/owned_readonly_lifetime.py", wrapper_raw),
                      "packet": pin("process-request.review-only.json", (OUT/"process-request.review-only.json").read_bytes()),
                      "stdin_bytes": len(payload_raw), "scope_bytes": len(scope_raw), "reference_count": len(refs)}))


if __name__ == "__main__":
    main()
