#!/usr/bin/env python3
"""Actual read-only qualification gates; never call fresh preparation."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
sys.dont_write_bytecode = True
HERE = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument("--manifest", required=True)
parser.add_argument("--manifest-sha256", required=True)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location("r4_prepare_gate_control", HERE / "prepare_runtime.py")
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
inputs = HERE / "references/android-input-a03.json"
base = types.SimpleNamespace(
    source_manifest=args.manifest, source_manifest_sha256=args.manifest_sha256,
    preparation_source="/home/alex/work/pocket4-owned-signal-host-r11-source-01/isolated-signal-canary-r1",
    host_wrapper_source_manifest="/home/alex/work/pocket4-owned-signal-host-r11-source-01/isolated-signal-canary-runtime-r1/source-manifest.json",
    inputs=str(inputs), inputs_sha256="48830abbdf42313576ecdfba9891ab4b93e6599bd938d6978713dfc9c0114492",
    host_suite_receipt="/home/alex/work/pocket4-signal-host-candidate-r11-01-9d630262/result.json",
    host_suite_sha256="b8c9b01588d1c2a13c80ba1afc5765fcf6656147d26e630a7c2cf74f4f482283",
    host_launch_inputs="/home/alex/work/pocket4-owned-signal-host-r11-source-01/isolated-signal-canary-runtime-r1/host-launch-inputs.json",
    host_launch_inputs_sha256="c313ea1f0d03474b05ee2ee8ae3bb74d0131d57469fb9dbf454d03745e3002fb",
    namespace_helper="/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held-namespace-entry",
    namespace_helper_sha256="21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689",
    namespace_helper_source="/home/alex/work/pocket4-owned-held-ns-runner-r4-01/held_namespace_entry.rs",
    namespace_helper_source_sha256="adf5b08f7854bec061ab8d2a208f3414339701c816218881e6550afde2e6c31c",
    namespace_helper_qualification="/home/alex/work/pocket4-owned-held-ns-runner-r4-export-01/qualification.json",
    namespace_helper_qualification_sha256="3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3")
rows = []
prep, config, contract = P.qualify(base)
assert contract["services_started"] is False and contract["old_data_read"] is False
rows.append({"name": "actual-external-r1-verifier-and-host-suite-and-helper-qualification-pass",
             "passed": True, "scope": "read actual immutable receipts and source/tool pins only"})
for name, key, value in [
    ("wrong-helper-qualification-pin", "namespace_helper_qualification_sha256", "0" * 64),
    ("wrong-helper-binary-pin", "namespace_helper_sha256", "0" * 64),
    ("copied-runtime-manifest-cannot-substitute-host-wrapper", "host_wrapper_source_manifest", args.manifest),
]:
    changed = copy.copy(base); setattr(changed, key, value)
    try:
        P.qualify(changed)
    except (RuntimeError, KeyError, ValueError) as error:
        rows.append({"name": name, "passed": True, "expected_rejection": repr(error)})
    else:
        raise AssertionError(name)
print(json.dumps({"schema": 1, "state": "PREPARATION_EXTERNAL_GATES_PASS",
    "controls": rows, "passed": len(rows), "contract": contract,
    "input_scope": "Retired a03 configuration used only for static build/engine/source qualification; validate_inputs/prepare were not called.",
    "new_paths_created_by_qualification": 0, "Android_operations": 0,
    "namespace_entries": 0, "old_data_read": False, "services_started": False,
    "production_ready": False}, sort_keys=True, indent=2))
