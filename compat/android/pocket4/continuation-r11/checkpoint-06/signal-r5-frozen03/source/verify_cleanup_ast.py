#!/usr/bin/env python3
"""Compare the loader's actual AST to the immutable successful v5 source."""
import ast
import builtins
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

sys.dont_write_bytecode = True
here = Path(__file__).parent
reference = here / "references/preparation-r1"
spec = importlib.util.spec_from_file_location("runtime_ast_control", here / "run.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
original_text = (reference / "v5_original.py").read_text()
assert hashlib.sha256(original_text.encode()).hexdigest() == runtime.ORIGINAL_SHA
original_ast = ast.parse(original_text)
expected = {node.name: node for node in original_ast.body
            if isinstance(node, ast.FunctionDef) and node.name in runtime.RETAINED_FUNCTIONS}
observed = []
def recording_compile(node, filename, mode):
    observed.append(copy.deepcopy(node))
    return builtins.compile(node, filename, mode)
def forbidden(*args, **kwargs):
    raise AssertionError("loader executed a runtime action")
fixture_prep = types.SimpleNamespace(read_json=lambda *args: {"fixture_only": True},
    CPU_INVENTORY_SHA="fixture", load_guard=lambda *args: {"require_unchanged": forbidden},
    main_snapshot=forbidden)
config = {"cpu_inventory": {"path": "/declared-fixture-not-opened"}}
prepared = {key: "/declared-" + key for key in ("stage", "runtime", "user_runtime", "evidence")}
prepared.update(name="declared-only", nonce="0" * 32, arm="signal-mask-r1")
runtime.compile = recording_compile
saved = runtime.subprocess.run
try:
    runtime.subprocess.run = forbidden
    scope = runtime.original_runtime(fixture_prep, config, prepared, reference)
finally:
    runtime.subprocess.run = saved
    del runtime.compile
assert len(observed) == 1
actual = {node.name: node for node in observed[0].body if isinstance(node, ast.FunctionDef)}
assert set(actual) == set(expected) == set(runtime.RETAINED_FUNCTIONS)
for name, original in expected.items():
    assert ast.dump(actual[name], include_attributes=False) == ast.dump(original, include_attributes=False), name
assert scope["cleanup_v5_reference"].__name__ == "cleanup"
assert scope["cleanup_v5_reference"].__globals__ is scope
assert scope["cleanup"].__self__ is scope["owned_cleanup"]
assert scope["cleanup"].__func__.__name__ == "run"
assert scope["owned_cleanup"].s is scope
assert "android" not in actual and "run_probes" not in actual
assert callable(scope["run"]) and callable(scope["cleanup"])
print(json.dumps({"schema": 1, "state": "ORIGINAL_RUNTIME_AST_INVARIANTS_PASS",
    "retained_functions": sorted(actual), "retained_count": len(actual),
    "retained_ast_functions_changed": 0,
    "active_cleanup": "separately qualified cleanup_owned.OwnedCleanup.run",
    "old_cleanup_retained_for_reference_controls_only": True,
    "original_controller_and_private_unit_resource_protocol_unchanged": True,
    "original_v5_source_sha256": runtime.ORIGINAL_SHA,
    "runtime_source_sha256": hashlib.sha256((here / "run.py").read_bytes()).hexdigest(),
    "actions_during_loader": 0, "Android_operations": 0,
    "real_runtime_execution": False, "production_ready": False}, sort_keys=True, indent=2))
