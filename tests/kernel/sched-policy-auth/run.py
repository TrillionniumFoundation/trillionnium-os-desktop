#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Real scheduling-policy target ownership checks in an ordinary owned guest."""
import importlib.util
from pathlib import Path
import sys
sys.dont_write_bytecode = True
here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('kernel_safety_runner', here.parent / 'safety/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.PROBES = ('sched_policy_auth',)
runner.SOURCE_FILES = {'sched_policy_auth': [here / 'probe.c']}
runner.PROBE_ARGS = {}
if __name__ == '__main__':
    raise SystemExit(runner.main())
