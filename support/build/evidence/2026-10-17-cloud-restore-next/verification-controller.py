#!/usr/bin/env python3
"""Capture actual portable verifier exits/logs; no restoration or VM launch."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    rows = []
    # Capture both before adding these resulting receipts to the outer checksum
    # set. Final read-only invocations check the completed phase afterward.
    for mode, flags in (("I", ["-I"]), ("IO", ["-I", "-O"])):
        argv = [sys.executable, *flags, str(HERE / "verify.py")]
        start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result = subprocess.run(argv, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180, check=False)
        rows.append({"mode": mode, "argv": argv, "cwd": str(HERE), "started_utc": start, "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "raw_exit_code": result.returncode, "verifier_sha256": sha((HERE / "verify.py").read_bytes()), "log": "verification-" + mode + ".log", "log_bytes": len(result.stdout), "log_sha256": sha(result.stdout), "scope": "Portable offline verification of completed restoration evidence; no new dependencies, compiler or guest. Captured before these receipts are added to outer checksums."})
        if result.returncode:
            (HERE / ("verification-" + mode + ".log")).write_bytes(result.stdout)
            (HERE / "verification-failed.json").write_text(json.dumps(rows, indent=2) + "\n")
            raise SystemExit(result.returncode)
        rows[-1]["_output"] = result.stdout
    for row in rows:
        (HERE / row["log"]).write_bytes(row.pop("_output"))
    (HERE / "verification.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps({"portable_modes": [r["mode"] for r in rows], "raw_exits": [r["raw_exit_code"] for r in rows], "verifier_sha256": sha((HERE / "verify.py").read_bytes())}, sort_keys=True))


if __name__ == "__main__":
    main()
