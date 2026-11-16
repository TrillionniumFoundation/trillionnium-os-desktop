"""Build one R7 shared source closure from a genuinely qualified v3 Main.

This program never stops a service, enters Android, sends UI, creates a nonce,
or reauthorizes an old flow. Its runtime guard reads must be scheduled after the
new baseline qualifier has finished. All JSON integers stay in Python.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

OLD_ROOT = Path("/home/alex/work/pocket4-current-host-r6-source-01")
OLD_MANIFEST_SHA = "002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff"
OLD_EPOCH = "7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c"
BASELINE_ROOT = Path("/home/alex/work/pocket4-main-current-baseline-03-20261107")
DESTINATION = Path("/home/alex/work/pocket4-current-host-r7-source-01")
DEPLOYMENT_MANIFEST_SHA = "b9d5c284356744e3f6a9d90389a72cb41dd946598c0858b7fa49f87ccab9cbbc"
SOURCE_COMMIT = "17ca3fa46e8b249df89ad4f12e338a524c54e640"
APP = Path("/usr/local/bin/android-app")
BACKEND = Path("/usr/local/libexec/android-digitalis-observe-helper")
APP_BYTES = 37467
APP_SHA = "e775301b11960df8109f39ef1adfc662bebd8fc536414580c71c7aa0da263efe"
BACKEND_BYTES = 36404
BACKEND_SHA = "d1fc02bdbbd72c8e9ee440dbf81274662d60228a4e7ecc661484241d889d7bd4"
BASELINE_SCHEMA = "pocket4-main-current-baseline-v3"
QUALIFICATION_SCHEMA = "pocket4-main-current-baseline-qualification-v3"
PRODUCTION_FILES = {"recorder.py", "source_contract.py", "main_binding.py",
                    "existing_ui_entry.py", "bound_android_transport.py",
                    "current_baseline_guard.py", "current_coordinator.py"}

def need(value, code):
    if not value:
        raise RuntimeError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def bad(_):
        raise RuntimeError("NONFINITE_JSON_NUMBER")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)

def valid_sha(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None

def read_regular(path, maximum=4 * 1024 * 1024, expected=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and 0 <= before.st_size <= maximum, "PINNED_SOURCE_SHAPE")
        chunks = []
        count = 0
        deadline = time.monotonic() + 10
        while True:
            need(time.monotonic() < deadline, "PINNED_SOURCE_READ_DEADLINE")
            data = os.read(fd, min(65536, maximum + 1 - count))
            if not data:
                break
            count += len(data)
            need(count <= maximum, "PINNED_SOURCE_BOUND")
            chunks.append(data)
        after = os.fstat(fd)
        named = os.stat(path, follow_symlinks=False)
        keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
        need(all(getattr(before, k) == getattr(after, k) == getattr(named, k) for k in keys),
             "PINNED_SOURCE_CHANGED")
        raw = b"".join(chunks)
        need(len(raw) == before.st_size and (expected is None or sha(raw) == expected),
             "PINNED_SOURCE_BYTES_CHANGED")
        return raw
    finally:
        os.close(fd)

def source_snapshot(root):
    manifest_raw = read_regular(root / "source-manifest.json", 131072, OLD_MANIFEST_SHA)
    manifest = parse(manifest_raw)
    need(manifest["artifact"] == "pocket4-bilibili-current-recorder-held-r6"
         and manifest["revision"] == 6, "EXACT_OLD_R6_SOURCE_REQUIRED")
    files = {}
    for name, pin in manifest["files"].items():
        path = Path(name)
        need(not path.is_absolute() and ".." not in path.parts, "SOURCE_RELATIVE_PATH_REQUIRED")
        raw = read_regular(root / path, 131072, pin["sha256"])
        need(len(raw) == pin["bytes"], "OLD_SOURCE_LENGTH_CHANGED")
        files[name] = raw
    need(PRODUCTION_FILES <= set(files) and len(files) == 14, "EXACT_SHARED_SOURCE_CLOSURE")
    return manifest_raw, files

def assignment(source, name, expression):
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, ast.Assign)
               and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
               and n.targets[0].id == name]
    need(len(matches) == 1, "UNIQUE_CONSTANT_REQUIRED:" + name)
    node = matches[0]
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [name + " = " + expression + "\n"]
    result = "".join(lines)
    compile(result, "<rebound-source>", "exec")
    return result

def literal_assignment(source, name):
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.Assign)
             and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
             and n.targets[0].id == name]
    need(len(nodes) == 1, "UNIQUE_LITERAL_REQUIRED")
    return ast.literal_eval(nodes[0].value)

def reference(path, raw):
    return {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}

def validate_binding(binding):
    need(binding.get("schema") == "pocket4-shared-r7-rebind-binding-v1",
         "EXPLICIT_R7_BINDING_REQUIRED")
    need(valid_sha(binding.get("epoch")) and binding["epoch"] != OLD_EPOCH,
         "OLD_MAIN_EPOCH_MUST_REMAIN_RETIRED")
    for key, basename in (("baseline", "baseline.private.json"),
                          ("qualification", "qualification.json"),
                          ("guard", "current_baseline_guard.py")):
        row = binding.get(key)
        need(type(row) is dict and set(row) == {"path", "bytes", "sha256"}
             and row["path"] == str(BASELINE_ROOT / basename)
             and type(row["bytes"]) is int and 0 < row["bytes"] <= 4 * 1024 * 1024
             and valid_sha(row["sha256"]), "EXACT_NEW_BASELINE_REFERENCE_REQUIRED")
    cohort = binding.get("deployed_cohort", {})
    need(cohort.get("schema") == "pocket4-shared-deployed-cohort-binding-v1"
         and cohort.get("manifest_sha256") == DEPLOYMENT_MANIFEST_SHA
         and cohort.get("source_commit") == SOURCE_COMMIT
         and cohort.get("target_count") == 11 and cohort.get("final_pair") == "candidate"
         and type(cohort.get("references")) is dict
         and set(cohort["references"]) == {"manifest", "result", "terminal"},
         "EXACT_APPLIED_COHORT_REQUIRED")
    for row in cohort["references"].values():
        need(type(row) is dict and set(row) == {"path", "bytes", "sha256"}
             and type(row["path"]) is str and row["path"].startswith("/")
             and type(row["bytes"]) is int and row["bytes"] > 0
             and valid_sha(row["sha256"]), "EXACT_COHORT_REFERENCE_REQUIRED")
    need(cohort["references"]["manifest"]["sha256"] == DEPLOYMENT_MANIFEST_SHA,
         "DEPLOYED_MANIFEST_PIN_CHANGED")

def render(old_manifest_raw, old_files, binding, app, backend, guard):
    """Pure source rendering only; this is not Main admission."""
    validate_binding(binding)
    need(sha(old_manifest_raw) == OLD_MANIFEST_SHA, "EXACT_OLD_MANIFEST_REQUIRED")
    old_manifest = parse(old_manifest_raw)
    need(set(old_files) == set(old_manifest["files"]), "OLD_SOURCE_CLOSURE_CHANGED")
    for name, pin in old_manifest["files"].items():
        need(len(old_files[name]) == pin["bytes"] and sha(old_files[name]) == pin["sha256"],
             "OLD_SOURCE_PIN_CHANGED:" + name)
    need(len(app) == APP_BYTES and sha(app) == APP_SHA, "EXACT_DEPLOYED_APP_REQUIRED")
    need(len(backend) == BACKEND_BYTES and sha(backend) == BACKEND_SHA, "EXACT_DEPLOYED_BACKEND_REQUIRED")
    need(len(guard) == binding["guard"]["bytes"] and sha(guard) == binding["guard"]["sha256"],
         "EXACT_V3_GUARD_BYTES_REQUIRED")
    files = dict(old_files)
    files["references/android_app.py"] = app
    files["references/android_backend.py"] = backend
    files["current_baseline_guard.py"] = guard

    text = files["recorder.py"].decode()
    for name, value in (("APP_SHA", APP_SHA), ("BACKEND_SHA", BACKEND_SHA)):
        text = assignment(text, name, repr(value))
    files["recorder.py"] = text.encode()

    text = files["bound_android_transport.py"].decode()
    for name, value in (("ANDROID_APP_SHA256", APP_SHA),
                        ("FRAMEWORK_EPOCH_SHA256", binding["epoch"])):
        text = assignment(text, name, repr(value))
    needle = "stat.S_ISREG(before.st_mode) and before.st_size == 37574"
    need(text.count(needle) == 1, "EXACT_TRANSPORT_SOURCE_LENGTH_GATE_REQUIRED")
    text = text.replace(needle, "stat.S_ISREG(before.st_mode) and before.st_size == 37467")
    files["bound_android_transport.py"] = text.encode()

    text = files["current_coordinator.py"].decode()
    updates = {"BASELINE": "Path(" + repr(binding["baseline"]["path"]) + ")",
               "QUALIFICATION": "Path(" + repr(binding["qualification"]["path"]) + ")",
               "BASELINE_SHA": repr(binding["baseline"]["sha256"]),
               "QUALIFICATION_SHA": repr(binding["qualification"]["sha256"]),
               "EPOCH": repr(binding["epoch"]), "GUARD_SOURCE_SHA": repr(binding["guard"]["sha256"])}
    for name, expression in updates.items():
        text = assignment(text, name, expression)
    files["current_coordinator.py"] = text.encode()

    text = files["source_contract.py"].decode()
    updates = {"ARTIFACT": "pocket4-bilibili-current-recorder-held-r7",
               "MAIN_EPOCH": binding["epoch"], "BASELINE_SCHEMA": BASELINE_SCHEMA,
               "BASELINE_SHA": binding["baseline"]["sha256"],
               "BASELINE_QUALIFICATION_SHA": binding["qualification"]["sha256"],
               "CURRENT_GUARD_SHA": binding["guard"]["sha256"]}
    for name, value in updates.items():
        text = assignment(text, name, repr(value))
    pins = literal_assignment(text, "REFERENCE_PINS")
    pins["references/android_app.py"] = (APP_BYTES, APP_SHA)
    pins["references/android_backend.py"] = (BACKEND_BYTES, BACKEND_SHA)
    text = assignment(text, "REFERENCE_PINS", repr(pins))
    marker = "PRODUCTION_FILES ="
    need(text.count(marker) == 1, "SOURCE_CONTRACT_INSERTION_POINT")
    text = text.replace(marker, "DEPLOYED_COHORT_BINDING = " + repr(binding["deployed_cohort"]) + "\n" + marker)
    marker = '        binding = manifest.get("current_baseline", {})'
    need(text.count(marker) == 1, "SOURCE_MANIFEST_BINDING_POINT")
    text = text.replace(marker,
        '        require(manifest.get("deployed_cohort") == DEPLOYED_COHORT_BINDING,\n'
        '                "EXACT_SHARED_DEPLOYED_COHORT_BINDING_REQUIRED")\n' + marker)
    text += ('\n    require(activation.get("deployed_cohort_observed") is True and\n'
             '            activation.get("deployed_cohort", {}).get("references") == DEPLOYED_COHORT_BINDING["references"] and\n'
             '            activation["deployed_cohort"].get("manifest_sha256") == DEPLOYED_COHORT_BINDING["manifest_sha256"] and\n'
             '            activation["deployed_cohort"].get("final_pair") == "candidate" and\n'
             '            activation["deployed_cohort"].get("target_count") == 11,\n'
             '            "ACTUAL_CURRENT_SHARED_COHORT_REQUIRED")\n')
    files["source_contract.py"] = text.encode()
    for name, raw in files.items():
        if name.endswith(".py"):
            compile(raw, name, "exec")
    # These frozen references remain history; never rewrite their old pins.
    changed = {n for n in files if files[n] != old_files[n]}
    need(changed == {"recorder.py", "bound_android_transport.py", "current_coordinator.py",
                     "source_contract.py", "current_baseline_guard.py",
                     "references/android_app.py", "references/android_backend.py"},
         "EXACT_DECLARED_SHARED_SOURCE_DELTA")
    manifest = copy.deepcopy(old_manifest)
    manifest.pop("actual_baseline_result", None)
    manifest.update(artifact="pocket4-bilibili-current-recorder-held-r7", revision=7,
                    parent_R6_manifest_sha256=OLD_MANIFEST_SHA,
                    source_fork_is_not_deployment=True, old_flows_reauthorized=False,
                    old_helpers_and_tasks_reauthorized=False, whole_app_production_ready=False)
    manifest["current_baseline"] = {
        **manifest["current_baseline"], "schema": BASELINE_SCHEMA, "epoch_sha256": binding["epoch"],
        "baseline_sha256": binding["baseline"]["sha256"],
        "qualification_sha256": binding["qualification"]["sha256"],
        "guard_sha256": binding["guard"]["sha256"]}
    manifest["current_baseline_private"] = binding["baseline"]
    manifest["current_qualification"] = binding["qualification"]
    manifest["deployed_cohort"] = binding["deployed_cohort"]
    manifest["files"] = {n: {"bytes": len(raw), "sha256": sha(raw)} for n, raw in sorted(files.items())}
    manifest_raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    return files, manifest_raw

def load_module(raw, path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module

def verify_guard_literals(module, binding):
    need(module.SOURCE_SCHEMA == "pocket4-current-baseline-source-v3"
         and str(module.BASELINE_PATH) == binding["baseline"]["path"]
         and str(module.QUALIFICATION_PATH) == binding["qualification"]["path"]
         and module.BASELINE_SHA == binding["baseline"]["sha256"]
         and module.QUALIFICATION_SHA == binding["qualification"]["sha256"]
         and module.BASELINE_BYTES == binding["baseline"]["bytes"]
         and module.QUALIFICATION_BYTES == binding["qualification"]["bytes"]
         and module.MAIN_EPOCH == binding["epoch"], "EXACT_NATIVE_V3_GUARD_REQUIRED")

def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

def run(args):
    need(os.geteuid() == 0, "ROOT_SOURCE_AND_CURRENT_GUARD_READ_REQUIRED")
    for value in (args.baseline_sha256, args.qualification_sha256, args.guard_sha256):
        need(valid_sha(value), "EXTERNAL_NEW_BASELINE_PIN_REQUIRED")
    paths = {"baseline": BASELINE_ROOT / "baseline.private.json",
             "qualification": BASELINE_ROOT / "qualification.json",
             "guard": BASELINE_ROOT / "current_baseline_guard.py"}
    raw = {key: read_regular(path, expected=getattr(args, key + "_sha256")) for key, path in paths.items()}
    baseline, qualification = parse(raw["baseline"]), parse(raw["qualification"])
    need(baseline.get("schema") == BASELINE_SCHEMA and qualification.get("schema") == QUALIFICATION_SCHEMA
         and qualification.get("identity_qualified") is True
         and baseline.get("deployed_cohort_observed") is True
         and baseline.get("deployment_performed") is False
         and baseline.get("whole_app_production_ready") is False
         and qualification.get("old_epoch_reauthorized") is False
         and qualification.get("UI_or_install_runtime_admitted") is False,
         "ACTUAL_QUALIFIED_V3_BASELINE_REQUIRED")
    actual = baseline["deployed_cohort"]
    binding = {"schema": "pocket4-shared-r7-rebind-binding-v1",
               "epoch": baseline["framework_epoch"]["sha256"],
               **{key: reference(paths[key], value) for key, value in raw.items()},
               "deployed_cohort": {"schema": "pocket4-shared-deployed-cohort-binding-v1",
                   **{key: actual[key] for key in ("references", "job_id", "manifest_sha256",
                       "source_commit", "target_count", "final_pair")}}}
    validate_binding(binding)
    guard = load_module(raw["guard"], paths["guard"], "r7_shared_actual_guard")
    verify_guard_literals(guard, binding)
    before = guard.current_guard(baseline, action_attempted=False)
    need(before.get("schema") == "pocket4-current-main-guard-v3"
         and before.get("deployed_cohort_matches") is True
         and before.get("full_eight_namespace_sets_match") is True,
         "FRESH_FULL_MAIN8_DEPLOYED_COHORT_GUARD_REQUIRED")
    old_raw, old_files = source_snapshot(OLD_ROOT)
    app = read_regular(APP, 131072, APP_SHA)
    backend = read_regular(BACKEND, 131072, BACKEND_SHA)
    files, manifest_raw = render(old_raw, old_files, binding, app, backend, raw["guard"])
    need(not DESTINATION.exists(), "NEW_R7_DESTINATION_MUST_NOT_EXIST")
    DESTINATION.mkdir(mode=0o700)
    (DESTINATION / "references").mkdir(mode=0o700)
    for name, value in sorted(files.items()):
        write_new(DESTINATION / name, value)
    write_new(DESTINATION / "source-manifest.json", manifest_raw)
    contract_module = load_module(files["source_contract.py"], DESTINATION / "source_contract.py",
                                  "r7_actual_source_contract")
    contract = contract_module.SourceContract(DESTINATION / "source-manifest.json", sha(manifest_raw))
    contract.verify()
    helper = contract_module.verify_shared_helper()
    transport = contract.load("bound_android_transport.py", "r7_actual_bound_transport")
    need(transport.source_bytes(APP) == app, "ACTUAL_TRANSPORT_SOURCE_GATE_FAILED")
    after = guard.current_guard(baseline, action_attempted=False)
    need(after == before, "MAIN_GUARD_CHANGED_DURING_SHARED_REBIND")
    need(read_regular(OLD_ROOT / "source-manifest.json", 131072, OLD_MANIFEST_SHA) == old_raw,
         "OLD_R6_SOURCE_CHANGED")
    for name, value in old_files.items():
        need(read_regular(OLD_ROOT / name, 131072, sha(value)) == value, "OLD_REFERENCE_CHANGED")
    result = {"schema": "pocket4-shared-r7-rebind-result-v1", "state": "PASS",
              "destination": str(DESTINATION), "source_manifest_sha256": sha(manifest_raw),
              "source_manifest_bytes": len(manifest_raw), "binding": binding,
              "guard_before": before, "guard_after": after,
              "source_contract": {"bytes": len(files["source_contract.py"]),
                                  "sha256": sha(files["source_contract.py"])},
              "exact_source_closure_verified": True, "current_transport_source_gate_verified": True,
              "qualified_held_helper_revalidated": helper,
              "old_R6_unchanged": True, "old_flows_reauthorized": False,
              "UI_or_install_runtime_admitted": False, "nonce_generated": False,
              "Android_commands": 0, "lifecycle_operations": 0}
    result_raw = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
    write_new(DESTINATION / "rebind-result.json", result_raw)
    print(json.dumps({"state": "PASS", "root": str(DESTINATION),
                     "manifest_sha256": sha(manifest_raw),
                     "source_contract_sha256": sha(files["source_contract.py"]),
                     "source_contract_bytes": len(files["source_contract.py"]),
                     "result_sha256": sha(result_raw), "epoch": binding["epoch"],
                     "Android_commands": 0, "UI_or_install_runtime_admitted": False}))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--qualification-sha256", required=True)
    parser.add_argument("--guard-sha256", required=True)
    args = parser.parse_args()
    run(args)

if __name__ == "__main__":
    main()

