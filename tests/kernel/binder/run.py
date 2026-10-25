#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Real limited Binder v8 byte IPC in an ordinary guest; not Android conformance."""
import importlib.util
from pathlib import Path
import sys
sys.dont_write_bytecode = True
here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("kernel_safety_runner", here.parent / "safety/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.PROBES = ("binder",)
runner.SOURCE_FILES = {"binder": [here / "binder_probe.c"]}
runner.PROBE_ARGS = {}
if "--budget-only" in sys.argv[1:]:
    sys.argv.remove("--budget-only")
    runner.PROBE_ARGS = {"binder": " --budget-only"}
if __name__ == "__main__":
    raise SystemExit(runner.main())
