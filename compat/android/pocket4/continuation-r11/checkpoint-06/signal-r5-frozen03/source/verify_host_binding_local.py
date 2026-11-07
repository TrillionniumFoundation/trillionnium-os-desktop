#!/usr/bin/env python3
"""Real frozen source-path control for the r2 HERE/manifest admission defect.

This executes only source verification, not any native test, service, Android
command or actual host-suite receipt replay.  The expected-rejection arm is the
actual frozen r2 file; the positive arm uses the real pinned original r1 tree.
"""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import sys

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-r1", type=Path, required=True)
    parser.add_argument("--frozen-r2", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("r3_runtime_binding_control", Path(__file__).with_name("run.py"))
    runtime = importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
    r1 = args.frozen_r1.resolve(strict=True); r2 = args.frozen_r2.resolve(strict=True)
    assert runtime.sha(r1 / "source-manifest.json") == runtime.HOST_WRAPPER_MANIFEST_SHA
    assert runtime.sha(r2 / "source-manifest.json") == "edbc982ada938b847c270c8aabeb6749922c00c92d9dc02202f18e6eee135937"
    program = json.loads((r2 / "source-manifest.json").read_bytes())
    bad_module = runtime.load_module(r2 / "host_suite.py", "actual_frozen_r2_host_module")
    rejected = None
    try:
        bad_module.verify_source(bad_module.HERE / "source-manifest.json", runtime.HOST_WRAPPER_MANIFEST_SHA)
    except RuntimeError as error:
        rejected = str(error)
    assert rejected == "input pin differs: " + str(r2 / "source-manifest.json")
    correct_module = runtime.qualified_host_wrapper(program, str(r1 / "source-manifest.json"))
    assert correct_module.HERE == r1 and correct_module.HERE != r2
    original = correct_module.verify_source(correct_module.HERE / "source-manifest.json", runtime.HOST_WRAPPER_MANIFEST_SHA)
    assert original["artifact"] == "isolated-signal-canary-runtime-r1"
    controls = [{"name": "actual-frozen-r2-copied-module-reproduces-manifest-context-rejection",
                 "passed": True, "expected_rejection": True, "error": rejected},
                {"name": "r3-loads-complete-pinned-r1-context-and-original-verifier-passes", "passed": True,
                 "module_here": str(correct_module.HERE), "source_manifest_sha256": runtime.HOST_WRAPPER_MANIFEST_SHA}]
    for name in ("host_suite.py", "host-test-contract.json", "r16-host-layout.json"):
        changed = copy.deepcopy(program); changed["files"][name]["sha256"] = "0" * 64
        rejected = None
        try:
            runtime.qualified_host_wrapper(changed, str(r1 / "source-manifest.json"))
        except RuntimeError as error:
            rejected = str(error)
        assert rejected == "host qualification code or contract changed"
        controls.append({"name": "reject-declared-changed-" + name, "passed": True,
                         "expected_rejection": True, "fixture": "explicit in-memory mutated expected file hash"})
    print(json.dumps({"schema": 1, "state": "REAL_SOURCE_CONTEXT_CONTROLS_PASS", "controls": controls,
                      "count": len(controls), "native_suite_executed": False, "Android_started": False,
                      "device_operations": 0, "scope": "source verifier module context only"}, indent=2))


if __name__ == "__main__":
    main()
