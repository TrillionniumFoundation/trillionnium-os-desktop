#!/usr/bin/env python3
"""One real owned-child timeout; no Main, namespace or remote operation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r2_definitions_only", ROOT / "observe_current_services.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def main():
    before = len(os.listdir("/proc/self/fd"))
    raw, stderr, result = M.held_bounded_child(
        [sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"],
        0.2, 65536, (), {"PATH": "/usr/bin:/bin", "LANG": "C"})
    after = len(os.listdir("/proc/self/fd"))
    assert result["errors"] == [{"type": "RuntimeError", "code": "CHILD_TIMEOUT"}]
    assert result["joined"] is True and result["returncode"] == -9
    assert result["termination_attempted"] is True and result["complete"] is False
    assert before == after and raw == stderr == b""
    try:
        os.waitpid(result["host_pid"], os.WNOHANG)
    except ChildProcessError:
        reaped = True
    else:
        raise AssertionError("Original child was not reaped")
    output = {"schema": "pocket4-readonly-services-r2-real-owned-timeout-control-v1", "ok": True,
              "control_count": 1, "command": result, "original_owned_child_reaped": reaped,
              "process_FDs_before": before, "process_FDs_after": after,
              "Main_operations": 0, "namespace_entries": 0, "Pocket4_operations": 0,
              "source_sha256": hashlib.sha256((ROOT / "observe_current_services.py").read_bytes()).hexdigest()}
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
