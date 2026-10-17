from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

old = types.ModuleType("original_agentd_guard_before_fix")
old.__file__ = str(Path(__file__).parent / "before_fix_run_original_agentd.py")
exec(compile(Path(old.__file__).read_text(), old.__file__, "exec"), old.__dict__)
observations = []
class ExpectedRed(Exception):
    pass

def assert_anchor_at_signal(pid, signum):
    try:
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        observations.append({"signal": signum, "kernel_result": "ECHILD", "signal_actually_sent": False})
        raise ExpectedRed("old cleanup attempted a group signal after reaping its child") from None
    raise AssertionError("old implementation unexpectedly retained the leader")

with tempfile.TemporaryDirectory(prefix="hepta-guard-red-") as temp:
    root = Path(temp)
    with patch.object(old.os, "killpg", side_effect=assert_anchor_at_signal):
        try:
            old.bounded_command([sys.executable, "-c", "raise SystemExit(1)"], root,
                                {"PATH": "/usr/bin:/bin"}, root / "command.log", 2)
        except ExpectedRed:
            pass
        else:
            raise AssertionError("expected old implementation to violate the identity assertion")
assert len(observations) == 1
print(json.dumps({"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                  "source_commit": "a92d8ed242dc073738b5f7b85cd0af9d329dfce8",
                  "result": "expected_regression_red", "observations": observations,
                  "pid_reuse_attempted": False, "original_agentd_run": False}, indent=2))
