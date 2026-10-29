#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Actual shared-open synchronous Binder threads; no Android qualification."""
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("kernel_safety_runner", here.parent / "safety/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.PROBES = ("binder_threads", "binder_thread_lifetime", "binder_thread_work")
runner.SOURCE_FILES = {"binder_threads": [here / "thread_probe.c"],
                       "binder_thread_lifetime": [here / "thread_lifetime_probe.c"],
                       "binder_thread_work": [here / "thread_work_probe.c"]}
runner.PROBE_ARGS = {}
if __name__ == "__main__":
    raise SystemExit(runner.main())
