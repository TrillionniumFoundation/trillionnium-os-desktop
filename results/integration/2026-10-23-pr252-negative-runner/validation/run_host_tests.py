#!/usr/bin/env python3
"""Run only the original Python host-oracle suite and retain complete logs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def fingerprint(data):
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
    }


def sources():
    return {
        path.relative_to(ROOT / "change").as_posix(): fingerprint(path.read_bytes())
        for path in sorted((ROOT / "change").rglob("*"))
        if path.is_file()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before-fix", "after-fix"))
    args = parser.parse_args()
    receipts = []
    for optimized in (False, True):
        name = args.phase + ("-optimized" if optimized else "-normal")
        paths = {kind: ROOT / "validation" / (name + "." + kind)
                 for kind in ("stdout", "stderr", "json")}
        if any(path.exists() for path in paths.values()):
            raise FileExistsError(name + " evidence already exists")
        command = [sys.executable, "-I", "-B"]
        if optimized:
            command.append("-O")
        command.extend(["-m", "unittest", "discover", "-s", "tests/kernel/control",
                        "-p", "test_g1d_guest.py", "-v"])
        before = sources()
        started = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()
        with paths["stdout"].open("xb") as stdout, paths["stderr"].open("xb") as stderr:
            result = subprocess.run(command, cwd=ROOT / "change", stdin=subprocess.DEVNULL,
                                    stdout=stdout, stderr=stderr, check=False, timeout=60)
        after = sources()
        receipt = {
            "scope": "Original Python host-oracle tests only; no Cargo, compiler, QEMU, guest or GitHub execution.",
            "phase": args.phase,
            "optimized": optimized,
            "command": command,
            "cwd": str(ROOT / "change"),
            "started_at": started,
            "duration_seconds": time.monotonic() - clock,
            "exit_code": result.returncode,
            "expected_exit_code": 1 if args.phase == "before-fix" else 0,
            "python_version": sys.version,
            "runner": fingerprint(Path(__file__).read_bytes()),
            "stdout": fingerprint(paths["stdout"].read_bytes()),
            "stderr": fingerprint(paths["stderr"].read_bytes()),
            "source_before": before,
            "source_after": after,
            "source_unchanged": before == after,
            "real_guest_qualified": False,
        }
        paths["json"].write_text(json.dumps(receipt, indent=2) + "\n")
        receipts.append({"name": name, "exit_code": result.returncode,
                         "source_unchanged": before == after,
                         "receipt": str(paths["json"])})
        if result.returncode != receipt["expected_exit_code"] or before != after:
            print(json.dumps(receipts, indent=2))
            return 1
    print(json.dumps(receipts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
