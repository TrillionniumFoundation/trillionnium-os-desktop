#!/usr/bin/env python3
"""Run functional allocation controls, with explicit unsupported-platform skips."""
import json
import os
from pathlib import Path
import signal
import sys
import unittest

ROOT = Path(__file__).resolve().parent
requirements = json.loads((ROOT / "platform-requirements.json").read_text())
ids = requirements["linux_control_ids"]
supported = (sys.platform.startswith("linux") and hasattr(os, "pidfd_open")
             and hasattr(os, "P_PIDFD") and hasattr(signal, "pidfd_send_signal"))
if not supported:
    print(json.dumps({"platform": sys.platform, "supported": False, "passed": 0,
                      "skipped": len(ids), "skipped_ids": ids,
                      "reason": "Linux PIDFD and process lifecycle support is required",
                      "qualification_transferred": False}, sort_keys=True))
    raise SystemExit(0)
sys.dont_write_bytecode = True
suite = unittest.defaultTestLoader.discover(str(ROOT), pattern="test_*allocation.py")
def flatten(value):
    for item in value:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item
actual = sorted(case.id() for case in flatten(suite))
if actual != ids:
    raise RuntimeError("The complete 17-control source set changed")
result = unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({"platform": sys.platform, "supported": True,
                  "run": result.testsRun, "passed": result.testsRun - len(result.failures)
                  - len(result.errors) - len(result.skipped), "skipped": len(result.skipped),
                  "failures": len(result.failures), "errors": len(result.errors),
                  "full_build_qualified": False, "runtime_qualified": False}, sort_keys=True))
raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 17 and not result.skipped else 1)
