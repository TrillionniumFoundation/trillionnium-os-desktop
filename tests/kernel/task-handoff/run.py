#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Real completed-wait wake migration and original CPUmax regression."""
import importlib.util
from pathlib import Path
import sys
sys.dont_write_bytecode = True
here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("kernel_safety_runner", here.parent / "safety/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.PROBES = ("task_handoff",)
runner.SOURCE_FILES = {"task_handoff": [here / "probe.c"]}
runner.PROBE_ARGS = {}
if __name__ == "__main__":
    raise SystemExit(runner.main())
