#!/usr/bin/env python3
"""Source compile + exact owned projection seams; retain transport limitation."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "candidate/android"
OUT = ROOT / "local-controls-02"


def pins():
    return [{"path": p.name, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
            for p in sorted(SOURCE.iterdir()) if p.is_file() for b in [p.read_bytes()]]


def main():
    OUT.mkdir(exist_ok=False)
    report = {"kind": "paired_projection_local_compile_seams_02", "commands": [],
              "input_before": pins(), "success": False, "transport_controls_passed": False,
              "prior_result_sha256": hashlib.sha256((ROOT / "local-controls-01/result.json").read_bytes()).hexdigest(),
              "scope": "Local C strict compile and owned directory/projection syscall seams. No Rust, kernel mount, namespace, Android or successful transport qualification."}
    try:
        try:
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
        except OSError as exc:
            report["local_seqpacket_listener_creation"] = {"success": False, "errno": exc.errno, "error": str(exc)}
        else:
            listener.close()
            report["local_seqpacket_listener_creation"] = {"success": True}
        compiler = "/usr/bin/cc"
        flags = [compiler, "-std=c17", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function"]
        commands = [
            ("close_errno_strict_compile", flags + ["-include", str(SOURCE / "close_errno_seam.h"), str(SOURCE / "protocol_controls.c"), "-o", str(OUT / "protocol-close-errno")]),
            ("diagnostic_strict_compile", flags + [str(SOURCE / "diagnostic_controls.c"), "-o", str(OUT / "diagnostic")]),
            ("actual_projection_seams", [str(OUT / "diagnostic")]),
            ("barrier_shared_strict_compile", flags + ["-fPIC", "-shared", "-fvisibility=hidden", str(SOURCE / "init_relay_barrier.c"), "-o", str(OUT / "libbarrier.host.so")]),
        ]
        for name, argv in commands:
            started = time.monotonic()
            command = {"name": name, "argv": argv, "timed_out": False}
            report["commands"].append(command)
            result = subprocess.run(argv, cwd=SOURCE, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
            command.update(returncode=result.returncode, stdout=result.stdout.decode(), stderr=result.stderr.decode(),
                           elapsed_seconds=time.monotonic() - started)
            if result.returncode:
                raise RuntimeError(name + " failed")
            if name == "actual_projection_seams":
                records = [json.loads(line) for line in result.stdout.decode().splitlines()]
                cases = [r for r in records if "case" in r]
                if len(cases) != 7 or any(r.get("ok") is not True for r in cases) or records[-1].get("ok") is not True:
                    raise RuntimeError("projection seam results differ")
                report["owned_projection_seam_cases_passed"] = len(cases)
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
