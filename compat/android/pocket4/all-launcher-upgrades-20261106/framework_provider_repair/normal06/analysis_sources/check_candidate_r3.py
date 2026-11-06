#!/usr/bin/env python3
"""Independent offline evidence checks; this is not Rust/Soong qualification."""
from pathlib import Path
import base64
import copy
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate-r3"
sha = lambda b: hashlib.sha256(b).hexdigest()
load = lambda p: json.loads(p.read_bytes())
old_bytes = (ROOT.parent / "normal05/source-r2/actual-provider-source-lock.json").read_bytes()
new_bytes = (CANDIDATE / "android/manifest/m2-role-ingress-provider3-source-lock.json").read_bytes()
old = json.loads(old_bytes)
new = json.loads(new_bytes)
evidence = load(ROOT / "candidate-lock-r1/source-lock-delta-evidence.json")
manifest = load(CANDIDATE / "SOURCE_CANDIDATE.json")
results = []

def record(name, function):
    function()
    results.append({"name": name, "outcome": "PASS", "scope": "OFFLINE_SOURCE_ONLY"})

def check(condition, message):
    if not condition:
        raise AssertionError(message)

def identity_files():
    for item in manifest["files"]:
        data = (CANDIDATE / item["path"]).read_bytes()
        check(len(data) == item["bytes"] and sha(data) == item["sha256"], item["path"])
    check(sha(old_bytes) == "72848909e4931d712a3d59f344904ae8642b32c35a01cf520a51afce4c56b50d", "old lock")
    check(sha(new_bytes) == "f5717d49fe0d4656b952bd397beab5d2fa70aa0992dd936ac31f81246c9e4772", "new lock")

record("candidate_file_identity_and_original_lock", identity_files)

# This independent expected value is constructed from the source evidence,
# not from Rust constants or the candidate generator's extension arrays.
expected = copy.deepcopy(old)
by_path = {p["path"]: p for p in expected["projects"]}
new_items = {}
for change in evidence["changes"]:
    if change["change"] == "add_exact_superproject_project":
        new_items[change["project"]] = change["new_project_entry"]
    else:
        by_path[change["project"]]["sparse_paths"].extend(change["sparse_paths_added"])
expected["projects"].extend(new_items[p["path"]] for p in new["projects"][len(old["projects"]):])

def require_exact(value):
    check(value == expected, "lock differs from captured exact source delta")

record("source_delta_reconstructs_exact_successor", lambda: require_exact(new))

gitlinks = {}
for path in (ROOT / "reference/upstream-tree").glob("superproject-*.raw.json"):
    raw = path.read_bytes()
    doc = json.loads(raw.split(b"\n", 1)[1])
    metadata = path.with_suffix(".source.json")
    if not metadata.exists():
        metadata = path.with_name(path.name.replace(".raw.json", ".source.json"))
    meta = load(metadata)
    check("28f0bbddc24d56c8ec5a8df5342ac7a292184039" in meta["url"], "wrong superproject")
    source_path = meta.get("path")
    if source_path is None:
        suffix = meta["url"].split("28f0bbddc24d56c8ec5a8df5342ac7a292184039", 1)[1]
        source_path = suffix.split("?", 1)[0].strip("/")
    for entry in doc["entries"]:
        if entry["type"] == "commit":
            gitlinks[(source_path + "/" + entry["name"]).strip("/")] = entry["id"]

def pinned_added_projects():
    for project in new["projects"][225:]:
        check(gitlinks.get(project["path"]) == project["commit"], project["path"])
    check(new["links"] == old["links"] and len(new["links"]) == 8, "links")
    for before, after in zip(old["projects"], new["projects"][:225]):
        check(before["path"] == after["path"] and before["name"] == after["name"] and before["commit"] == after["commit"], before["path"])
    check(new["policy"] == old["policy"], "policy")

record("original_225_revisions_links_policy_and_17_exact_gitlinks", pinned_added_projects)

def genuine_provider_sources():
    count = 0
    for change in evidence["changes"]:
        for provider in change["provider_evidence"]:
            p = ROOT / provider["source_file"]
            data = p.read_bytes()
            check(len(data) == provider["source_bytes"] and sha(data) == provider["source_sha256"], str(p))
            meta = load(p.with_suffix(p.suffix + ".source.json"))
            check(meta["commit"] == change["commit"], "provider revision")
            check(meta["decoded_sha256"] == sha(data), "provider original receipt")
            wire = p.with_suffix(p.suffix + ".wire-base64.txt")
            if wire.exists():
                raw = wire.read_bytes()
                check(sha(raw) == meta["raw_sha256"] and base64.b64decode(raw, validate=True) == data, "original base64 body")
            count += 1
    check(count > 26, "provider source evidence unexpectedly missing")

record("captured_provider_source_bytes_and_commit_evidence", genuine_provider_sources)

def exact_root_modules():
    source = (CANDIDATE / "tools/droidloom-update/src/android.rs").read_text()
    for canonical, original_path, projection_path, expected_count in [
        ("frameworks/base/packages/SystemUI/Android.bp", "reference/SystemUI.Android.bp", "reference/SystemUI.candidate-r2-projection.bp", 19),
        ("frameworks/base/libs/WindowManager/Shell/Android.bp", "reference/upstream-go/WindowManager-Shell.Android.bp", "reference/WindowManager-Shell.candidate-r2-projection.bp", 9),
    ]:
        start = source.index('        "' + canonical + '" => ')
        end = source.index(']),', start)
        pairs = re.findall(r'\("([a-z_]+)", "([^"]+)"\)', source[start:end])
        check(len(pairs) == expected_count and len(set(pairs)) == expected_count, canonical)
        original = (ROOT / original_path).read_text()
        projected = (ROOT / projection_path).read_text()
        for kind, name in pairs:
            marker = kind + ' {\n    name: "' + name + '",'
            check(original.count(marker) == 1, name)
            begin = original.index(marker)
            finish = original.index('\n}\n', begin) + 3
            check(projected.count(original[begin:finish]) == 1, "provider body changed: " + name)
    check(source == (ROOT / "candidate-r2/tools/droidloom-update/src/android.rs").read_text(), "unexpected second projection change")

record("nineteen_systemui_and_nine_shell_full_upstream_bodies", exact_root_modules)

def device_state_unchanged():
    bp = ROOT / "reference/closure-providers/frameworks/base/services/foldables/devicestateprovider/src/com/android/server/policy/feature/Android.bp"
    text = bp.read_text()
    check('name: "device_state_flags_lib"' in text and 'aconfig_declarations: "device_state_flags"' in text, "genuine provider")
    check('package: "com.android.server.policy.feature.flags"' in text, "wrong flags package")
    lines = (ROOT / "reference/normal05-actual-graph/Android.bp.list").read_text().splitlines()
    check('frameworks/base/services/foldables/devicestateprovider/src/com/android/server/policy/feature/Android.bp' in lines, "provider not observed in graph")
    original = (ROOT / "reference/SystemUI.Android.bp").read_text()
    projected = (ROOT / "reference/SystemUI.candidate-r2-projection.bp").read_text()
    check(original.count('"device_state_flags_lib"') == projected.count('"device_state_flags_lib"') == 2, "consumer references changed")

record("device_state_real_provider_and_original_consumers", device_state_unchanged)

def negative(name, mutate):
    changed = copy.deepcopy(new)
    mutate(changed)
    try:
        require_exact(changed)
    except AssertionError:
        results.append({"name": name, "outcome": "PASS", "scope": "OFFLINE_SOURCE_ONLY", "rejection_observed": True})
    else:
        raise AssertionError("negative input accepted: " + name)

negative("wrong_vendor_project_commit_rejected", lambda x: x["projects"][-1].update(commit="0" * 40))
negative("missing_added_project_rejected", lambda x: x["projects"].pop())
negative("original_project_revision_change_rejected", lambda x: x["projects"][0].update(commit="0" * 40))
negative("original_project_order_change_rejected", lambda x: x["projects"].reverse())
negative("unrestricted_repo_sync_rejected", lambda x: x["policy"].update(allow_unrestricted_repo_sync=True))
negative("link_deletion_rejected", lambda x: x["links"].pop())
negative("missing_required_sparse_path_rejected", lambda x: next(p for p in x["projects"] if p["path"] == "cts")["sparse_paths"].pop())
negative("unobserved_sparse_path_rejected", lambda x: next(p for p in x["projects"] if p["path"] == "cts")["sparse_paths"].append("unobserved"))

def strict_boundaries():
    native = (CANDIDATE / "tools/droidloom-update/src/native_role_ingress.rs").read_text()
    check('pub const TARGETS: &[&str] = &["framework-minus-apex", "libandroid_runtime"];' in native, "target scope")
    check('"runtime_authorization_enabled": true' not in native, "runtime authorization")
    check('"transitive_build_closure_qualified": true' not in native, "closure claim")
    check('const SOURCE_LOCK_SHA: &str = "' + sha(new_bytes) + '";' in native, "compiled exact source pin")
    check('const PREVIOUS_NATIVE_PROVIDER_LOCK_SHA: &str = "' + sha(old_bytes) + '";' in native, "compiled predecessor pin")
    check('validate_native_provider_extension(&previous_provider_value, &previous_native_value)?;' in native, "old gate dropped")
    check('validate_systemui_provider_extension(&previous_native_value, &serde_json::from_slice(&expanded)?)?;' in native, "new gate not chained")

record("strict_target_and_previous_source_gate_chain_preserved", strict_boundaries)
receipt = {
    "schema": "pocket4-normal06-candidate-r3-offline-controls-v1",
    "candidate_manifest_sha256": sha((CANDIDATE / "SOURCE_CANDIDATE.json").read_bytes()),
    "checks": results,
    "passed": len(results),
    "scope": "Local source/evidence consistency and fail-closed input checks only",
    "rust_compiler_executed": False,
    "rust_unit_tests_executed": False,
    "soong_executed": False,
    "host_or_android_actions": False,
    "full_dependency_closure_qualified": False,
    "production_ready": False,
}
body = (json.dumps(receipt, indent=2) + "\n").encode()
path = ROOT / "candidate-r3-offline-controls.json"
path.write_bytes(body)
print(json.dumps({"path": str(path), "passed": len(results), "bytes": len(body), "sha256": sha(body)}))
