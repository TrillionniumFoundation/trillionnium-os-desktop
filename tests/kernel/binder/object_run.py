#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run actual Binder object/handle IPC in an isolated guest; not Android conformance."""
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("kernel_safety_runner", here.parent / "safety/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.PROBES = ("binder", "binder_objects", "binder_fds", "binder_cleanup")
runner.SOURCE_FILES = {"binder": [here / "binder_probe.c"], "binder_objects": [here / "object_probe.c"], "binder_fds": [here / "fd_probe.c"], "binder_cleanup": [here / "cleanup_probe.c"]}
runner.PROBE_ARGS = {}
if __name__ == "__main__":
    raise SystemExit(runner.main())
