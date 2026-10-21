#!/usr/bin/env python3
"""Actually rerun the portable offline verifier from a new owned phase path."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    checksum = (HERE / "SHA256SUMS").read_bytes()
    names = [line.split("  ", 1)[1] for line in checksum.decode().splitlines()]
    rows = []
    outputs = []
    with tempfile.TemporaryDirectory(prefix=".relocation-probe-", dir=HERE) as temporary:
        root = Path(temporary) / "moved-phase"
        root.mkdir()
        for name in [*names, "SHA256SUMS"]:
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write((HERE / name).read_bytes())
        for mode, flags in (("I", ["-I"]), ("IO", ["-I", "-O"])):
            command = [sys.executable, *flags, str(root / "verify.py")]
            started = datetime.datetime.now(datetime.timezone.utc).isoformat()
            result = subprocess.run(command, cwd="/", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180, check=False)
            rows.append({"mode": mode, "argv": command, "cwd": "/", "started_utc": started, "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "raw_exit_code": result.returncode, "verifier_sha256": hashlib.sha256((HERE / "verify.py").read_bytes()).hexdigest(), "input_SHA256SUMS_sha256": hashlib.sha256(checksum).hexdigest(), "log": "relocation-" + mode + ".log", "log_bytes": len(result.stdout), "log_sha256": hashlib.sha256(result.stdout).hexdigest(), "scope": "Actual offline verifier run after copying the checksum-listed complete phase into a new owned temporary path, with cwd outside the phase; no restoration or guest."})
            outputs.append(result.stdout)
            if result.returncode:
                break
    for row, output in zip(rows, outputs):
        (HERE / row["log"]).write_bytes(output)
    (HERE / "relocation-verification.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps({"relocated_modes": [r["mode"] for r in rows], "raw_exits": [r["raw_exit_code"] for r in rows]}, sort_keys=True))
    if len(rows) != 2 or any(r["raw_exit_code"] for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
