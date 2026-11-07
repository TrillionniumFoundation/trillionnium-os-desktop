#!/usr/bin/env python3
"""Owned local C transport/projection seams; no Android or kernel mounts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "candidate/android"
OUT = ROOT / "local-controls-01"


def pins():
    return [{"path": p.name, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
            for p in sorted(SOURCE.iterdir()) if p.is_file() for b in [p.read_bytes()]]


def main():
    OUT.mkdir(exist_ok=False)
    report = {"kind": "paired_projection_local_owned_controls_01", "commands": [],
              "input_before": pins(), "success": False, "scope":
              "Actual local C transport/close-error controls and explicit projection syscall seams only; no kernel mount, namespace or Android execution."}
    try:
        compiler = shutil.which("cc")
        if not compiler:
            raise RuntimeError("local cc unavailable")
        report["compiler"] = {"path": str(Path(compiler).resolve()),
                              "sha256": hashlib.sha256(Path(compiler).read_bytes()).hexdigest()}
        flags = [compiler, "-std=c17", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function"]
        for name, leaf, extra, count in [
            ("protocol", "protocol_controls.c", [], 20),
            ("protocol-close-errno", "protocol_controls.c", ["-include", str(SOURCE / "close_errno_seam.h")], 20),
            ("diagnostic", "diagnostic_controls.c", [], 7),
        ]:
            binary = OUT / name
            for phase, argv in [("compile", flags + extra + [str(SOURCE / leaf), "-o", str(binary)]),
                                ("run", [str(binary)])]:
                start = time.monotonic()
                command = {"name": name, "phase": phase, "argv": argv, "timed_out": False}
                report["commands"].append(command)
                try:
                    result = subprocess.run(argv, cwd=SOURCE, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            timeout=20, check=False)
                    command.update(returncode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode())
                except subprocess.TimeoutExpired as exc:
                    command.update(timed_out=True, stdout=(exc.stdout or b"").decode(), stderr=(exc.stderr or b"").decode())
                    raise
                finally:
                    command["elapsed_seconds"] = time.monotonic() - start
                if result.returncode != 0:
                    raise RuntimeError(name + " " + phase + " failed")
                if phase == "run":
                    records = [json.loads(line) for line in command["stdout"].splitlines()]
                    cases = [r for r in records if "case" in r]
                    if len(cases) != count or any(r.get("ok") is not True for r in cases) or records[-1].get("ok") is not True:
                        raise RuntimeError(name + " exact control result mismatch")
                    command["actual_cases_passed"] = len(cases)
        report["input_after"] = pins()
        if report["input_after"] != report["input_before"]:
            raise RuntimeError("inputs changed")
        report["success"] = True
    except Exception as exc:
        report["error"] = repr(exc)
    finally:
        body = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
        with (OUT / "result.json").open("xb") as file:
            file.write(body)
        print(json.dumps({"path": str(OUT / "result.json"), "bytes": len(body),
                          "sha256": hashlib.sha256(body).hexdigest(), "success": report["success"],
                          "error": report.get("error"), "commands": len(report["commands"])}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
