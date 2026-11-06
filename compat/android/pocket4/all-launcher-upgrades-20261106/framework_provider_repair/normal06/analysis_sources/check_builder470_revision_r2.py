#!/usr/bin/env python3
"""Only the two requested result fixes, binding checks, and cleanup negatives."""
from pathlib import Path
import ast
import copy
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "builder470-hostprep-r1"
NEW = ROOT / "builder470-hostprep-r2"
sha = lambda b: hashlib.sha256(b).hexdigest()
load = lambda p: json.loads(p.read_bytes())
old_source = (OLD / "compile_builder470.py").read_text()
new_source = (NEW / "compile_builder470.py").read_text()
old_root = "/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-01-20261106"
new_root = "/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106"
old_gate = "require(cleanup.get('complete') is True,'owned child cleanup incomplete')"
new_gate = "require(cleanup.get('complete') is True and cleanup.get('children')==[] and cleanup.get('errors')==[],'owned child cleanup incomplete or residual child cleanup occurred')"
old_result = "'tests_passed':len(focused),'test_names':TESTS"
new_result = "'tests_passed':len(focused),'independent_result_gates':focused,'test_names':TESTS"
assert new_source.count(new_root) == new_source.count(new_gate) == new_source.count(new_result) == 1
assert new_source.replace(new_root, old_root).replace(new_gate, old_gate).replace(new_result, old_result) == old_source

for folder in [OLD, NEW]:
    plan = load(folder / "execution-plan.json")
    for item in plan["files"]:
        data = (folder / item["path"]).read_bytes()
        assert len(data) == item["bytes"] and sha(data) == item["sha256"], item["path"]
old_tree, new_tree = ast.parse(old_source), ast.parse(new_source)
old_functions = {n.name: ast.get_source_segment(old_source, n) for n in old_tree.body if isinstance(n, ast.FunctionDef)}
new_functions = {n.name: ast.get_source_segment(new_source, n) for n in new_tree.body if isinstance(n, ast.FunctionDef)}
assert old_functions == new_functions and len(old_functions) == 26

# Run the exact first three statements and the exact failure handler from the
# new main's finalization try. cleanup_children is replaced only inside this
# local control by a synthetic return value; no child API or subprocess runs.
outer = next(n for n in new_tree.body if isinstance(n, ast.Try) and n.finalbody)
finalization = next(n for n in outer.finalbody if isinstance(n, ast.Try))
assert len(finalization.body) >= 3
assert isinstance(finalization.body[0], ast.Assign)
assert ast.unparse(finalization.body[0]) == "cleanup = cleanup_children()"
assert ast.unparse(finalization.body[1]) == "result['cleanup'] = cleanup"
assert isinstance(finalization.body[2], ast.Expr) and ast.unparse(finalization.body[2]).startswith("require(cleanup.get('complete')")
control = ast.Module(body=[ast.Try(body=copy.deepcopy(finalization.body[:3]), handlers=copy.deepcopy(finalization.handlers), orelse=[], finalbody=[])], type_ignores=[])
ast.fix_missing_locations(control)
code = compile(control, "<exact-r2-cleanup-finalization-control>", "exec")
def require(condition, message):
    if not condition:
        raise RuntimeError(message)
cases = [
    ("clean_empty_owned_children", {"complete": True, "children": [], "errors": []}, "RUST_BUILD_AND_19_INDEPENDENT_FOCUSED_TESTS_PASS"),
    ("reaped_residual_child_still_rejects_pass", {"complete": True, "children": [{"synthetic_fixture": True, "reaped": True}], "errors": []}, "FAILED"),
    ("cleanup_error_still_rejects_pass", {"complete": True, "children": [], "errors": [{"synthetic_fixture": True, "operation": "close_pidfd"}]}, "FAILED"),
    ("incomplete_cleanup_rejects_pass", {"complete": False, "children": [], "errors": []}, "FAILED"),
]
observed = []
for name, fixture, expected in cases:
    scope = {"require": require, "cleanup_children": lambda value=fixture: value, "result": {"state": "RUST_BUILD_AND_19_INDEPENDENT_FOCUSED_TESTS_PASS"}, "failure": None}
    exec(code, scope)
    assert scope["result"]["state"] == expected
    if expected == "FAILED":
        assert scope["failure"] and scope["result"].get("finalization_error")
    observed.append({"name": name, "synthetic_cleanup_fixture": fixture, "observed_state": scope["result"]["state"], "expected_state": expected, "check_passed": True})

updates = [n for n in ast.walk(new_tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "result" and n.func.attr == "update" and n.args and isinstance(n.args[0], ast.Dict)]
update = next(n.args[0] for n in updates if any(isinstance(k, ast.Constant) and k.value == "independent_result_gates" for k in n.args[0].keys))
value = next(v for k, v in zip(update.keys, update.values) if isinstance(k, ast.Constant) and k.value == "independent_result_gates")
assert isinstance(value, ast.Name) and value.id == "focused"
tests = next(ast.literal_eval(n.value) for n in new_tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TESTS" for t in n.targets))
assert len(tests) == len(set(tests)) == 19

old_packet = load(OLD / "stage-stdin.json")
new_packet = load(NEW / "stage-stdin.json")
assert set(old_packet["files"]) == set(new_packet["files"])
changed_inner = sorted(k for k in old_packet["files"] if old_packet["files"][k] != new_packet["files"][k])
assert changed_inner == ["compile_builder470.py"]
assert new_packet["files"]["compile_builder470.py"] == new_source
assert old_packet["files"]["candidate-source-manifest.json"] == new_packet["files"]["candidate-source-manifest.json"]
new_stage = (NEW / "stage_builder470.py").read_text()
old_stage = (OLD / "stage_builder470.py").read_text()
normalized_stage = new_stage.replace(new_root, old_root).replace(str(len(new_source.encode())), str(len(old_source.encode()))).replace(sha(new_source.encode()), sha(old_source.encode()))
assert normalized_stage == old_stage
for basename in ["exact-stage-request.json", "exact-compile-request.json"]:
    a, b = load(OLD / basename), load(NEW / basename)
    allowed = {"args", "idempotency_key", "stdin"}
    assert {k:v for k,v in a.items() if k not in allowed} == {k:v for k,v in b.items() if k not in allowed}
    assert a["idempotency_key"] != b["idempotency_key"]
    if "stage" in basename:
        assert b["stdin"].encode() == (NEW / "stage-stdin.json").read_bytes()
        assert b["args"][3] == (NEW / "stage_transport.py").read_text()
    else:
        assert b["args"][3] == (NEW / "compile_transport.py").read_text()

diffs = {}
for name in ["compile_builder470.py", "stage_builder470.py"]:
    old = (OLD / name).read_text()
    new = (NEW / name).read_text()
    body = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="builder470-hostprep-r1/"+name, tofile="builder470-hostprep-r2/"+name)).encode()
    outname = "r1-to-r2-" + name + ".diff"
    (NEW / outname).write_bytes(body)
    diffs[outname] = {"bytes": len(body), "sha256": sha(body)}
receipt = {
    "schema": "pocket4-builder470-r2-narrow-revision-controls-v1",
    "r1_unchanged": True,
    "r1_never_submitted_per_root": True,
    "only_compiler_changes": ["new owned root", "persist actual focused list as independent_result_gates", "require complete and empty cleanup children/errors for success"],
    "unchanged_helper_bodies": 26,
    "independent_result_gates_binds_actual_focused_list": True,
    "selected_tests": 19,
    "cleanup_controls": observed,
    "packet_changed_inner_files": changed_inner,
    "candidate_source_inventory_unchanged": True,
    "resources_and_other_request_parameters_unchanged": True,
    "execution_plan_sha256": sha((NEW / "execution-plan.json").read_bytes()),
    "diffs": diffs,
    "remote_actions": 0,
    "actual_owned_child_cleanup_performed": False,
    "Rust_or_Soong_executed": False,
    "production_ready": False,
}
data = (json.dumps(receipt, indent=2) + "\n").encode()
(NEW / "revision-controls.json").write_bytes(data)
print(json.dumps({"bytes": len(data), "sha256": sha(data), "diffs": diffs, "cleanup_controls": len(observed), "all_passed": True}))
