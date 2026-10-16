"""Assert cleanup using measured pidfd state, readiness and absence of rescue."""
from pathlib import Path
import json
import sys

base = Path(__file__).resolve().parent
passed = failed = 0
for row in json.loads((base / "summary-patched.json").read_text()):
    measured = json.loads((base / "runs-patched" / row["mode"] / "result.json").read_text())
    states = measured["snapshots"][-1]["states"]
    ready = any(event["event"] == "descendant_ready" for event in measured["events"])
    no_rescue = all(step.get("already_exited") for step in measured["cleanup"])
    ok = (measured["harness_exit"] == 0 and ready and no_rescue
          and states["leader"]["pidfd_exited"] and states["descendant"]["pidfd_exited"]
          and measured["descendant_heartbeats_after_supervisor_exit"] == 0)
    if ok:
        passed += 1
        print("PASS owned leader/descendant exited without probe rescue:", row["mode"])
    else:
        failed += 1
        print("FAIL incomplete production cleanup:", row["mode"])
print(json.dumps({"passed": passed, "failed": failed}))
sys.exit(1 if failed else 0)
