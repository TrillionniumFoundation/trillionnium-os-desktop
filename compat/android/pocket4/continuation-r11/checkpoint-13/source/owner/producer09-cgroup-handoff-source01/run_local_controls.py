#!/usr/bin/env python3
"""Strict local C build and owned filesystem seams only; no namespace runtime."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import traceback

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "candidate/android"
OUT = ROOT / "local-controls-01"


def pins():
    return [{"path": p.name, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
            for p in sorted(SOURCE.iterdir()) if p.is_file() for b in [p.read_bytes()]]


def main():
    OUT.mkdir()
    report = {"schema": 1, "kind": "cgroup_handoff_pair_local_controls01", "success": False,
              "commands": [], "input_before": pins(), "Rust_compiled": False,
              "transport_controls_executed": False, "Android_executed": False,
              "namespace_mount_or_pressure_executed": False,
              "scope": "Strict C compile plus real owned files with explicit filesystem/syscall seams"}
    flags = ["/usr/bin/cc", "-std=c17", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function"]
    commands = [
        ("holding_controls_compile", flags + [str(SOURCE / "cgroup_view_controls.c"), "-o", str(OUT / "holding-controls")]),
        ("holding_controls_run", [str(OUT / "holding-controls")]),
        ("projection_controls_compile", flags + [str(SOURCE / "diagnostic_controls.c"), "-o", str(OUT / "projection-controls")]),
        ("projection_controls_run", [str(OUT / "projection-controls")]),
        ("protocol_controls_compile_only", flags + [str(SOURCE / "protocol_controls.c"), "-o", str(OUT / "protocol-controls")]),
        ("close_errno_controls_compile_only", flags + ["-include", str(SOURCE / "close_errno_seam.h"), str(SOURCE / "protocol_controls.c"), "-o", str(OUT / "protocol-close-errno")]),
        ("host_DSO_compile_only", flags + ["-fPIC", "-shared", "-fvisibility=hidden", "-Wl,--version-script=" + str(SOURCE / "exported.map.txt"), str(SOURCE / "init_relay_barrier.c"), "-o", str(OUT / "libbarrier.host.so")]),
    ]
    try:
        for name, argv in commands:
            row = {"name": name, "argv": argv, "timed_out": False}
            report["commands"].append(row)
            start = time.monotonic_ns()
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=20, check=False, cwd=SOURCE)
            row.update(returncode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode(),
                       elapsed_ns=time.monotonic_ns() - start)
            if result.returncode:
                raise RuntimeError(name + " failed")
            if name.endswith("_run"):
                records = [json.loads(line) for line in row["stdout"].splitlines()]
                cases = [r for r in records if "case" in r]
                expected = 8 if name == "holding_controls_run" else 7
                if len(cases) != expected or any(r.get("ok") is not True for r in cases) or records[-1].get("ok") is not True:
                    raise RuntimeError(name + " actual case count/result differs")
                row["actual_cases_passed"] = expected
        report["input_after"] = pins()
        if report["input_after"] != report["input_before"]:
            raise RuntimeError("source changed")
        report["success"] = True
    except BaseException as error:
        report["first_error"] = repr(error)
        report["traceback"] = traceback.format_exc()
    raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    with (OUT / "result.json").open("xb") as output:
        output.write(raw)
    print(json.dumps({"success": report["success"], "path": str(OUT / "result.json"),
                      "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                      "commands": len(report["commands"]), "first_error": report.get("first_error")}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
