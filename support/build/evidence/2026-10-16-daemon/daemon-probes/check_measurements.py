"""Check actual lifecycle observations; failure is expected on the old code."""
from pathlib import Path
import json
import sys

base = Path(__file__).resolve().parent
passed = 0
failed = 0
for row in json.loads((base / "summary.json").read_text()):
    measured = json.loads((base / "runs" / row["mode"] / "result.json").read_text())
    states = measured["snapshots"][-1]["states"]
    if states["leader"]["pidfd_exited"] and states["descendant"]["pidfd_exited"]:
        passed += 1
        print("PASS both owned processes exited:", row["mode"])
    else:
        failed += 1
        print("FAIL descendant remains after original supervisor returned:", row["mode"])
print(json.dumps({"passed": passed, "failed": failed}))
sys.exit(1 if failed else 0)
