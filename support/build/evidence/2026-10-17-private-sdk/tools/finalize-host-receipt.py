#!/usr/bin/env python3
"""Freeze the final SDK support patch's observed host-only validation."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
REPO = BASE.parent / "trillionnium-os-desktop"
EXPECTED = {
    "support/build/kernel.sh": "4ee3118990158bb93be6ffe191cac8de5399f507973af6adc3a05e3614407f83",
    "support/build/minimal.mk": "9fe262b0287831263217a72380ab24b8e79a3baf2bff4f5a3186c01558ad6635",
    "support/build/README.md": "0896cf8c0ca002419d1d79b69076e8fbe99d4a2fa8dc57b8ef9354ccb0caed06",
    "support/build/tests/test_kernel_runner.py": "2311311e33ab57c37117bf431ce938370fb0610b0324c472d4772e3b7c2a4531",
}
actual = {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in EXPECTED}
assert actual == EXPECTED, actual
old = BASE / "private-sdk-validation-ready.json"
assert hashlib.sha256(old.read_bytes()).hexdigest() == "cb0ccf3a74ad7b684e226659df4b1c81585433853b9520f43e1fd8dd7f7adb14"
results = []
for log, count, isolated in (("private-sdk-kernel-runner-v2-ordinary.log", 40, False),
                             ("private-sdk-kernel-runner-v2-isolated.log", 40, True),
                             ("private-sdk-kernel-supervisor-v2-isolated.log", 9, True),
                             ("private-sdk-repro-profile-v2-isolated.log", 32, True)):
    content = (BASE / log).read_text()
    assert f"Ran {count} tests" in content and content.rstrip().endswith("OK"), log
    directory = "support/build/repro" if "repro" in log else "support/build/tests"
    test = "test_profile.py" if "repro" in log else ("test_kernel_supervisor.py" if "supervisor" in log else "test_kernel_runner.py")
    command = ["python3"] + (["-I"] if isolated else []) + ["-m", "unittest", "discover", "-s", directory, "-p", test, "-v"]
    results.append({"log": log, "sha256": hashlib.sha256((BASE / log).read_bytes()).hexdigest(),
                    "command": command, "cwd": str(REPO), "tests": count, "observed_tool_returncode": 0,
                    "passed": True})
checks = []
for command in (["bash", "-n", "support/build/kernel.sh"], ["git", "diff", "--check"]):
    checked = subprocess.run(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert checked.returncode == 0, checked.stderr
    checks.append({"command": command, "returncode": checked.returncode,
                   "stdout": checked.stdout.decode(), "stderr": checked.stderr.decode()})
receipt = {
    "schema": "a01-private-sdk-host-validation/2",
    "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "base_commit": "09aea79c71dc9f48ba519757078dd8a20f5c8fb3",
    "scope": "final support-layer code plus host fixtures; no SDK/kernel/QEMU install or VM result",
    "status": "ready_after_independent_v2_approval",
    "source_sha256": actual,
    "results": results,
    "syntax_and_diff_checks": checks,
    "supersedes": {"receipt": old.name, "sha256": hashlib.sha256(old.read_bytes()).hexdigest(),
                   "status": "superseded_not_final_acceptance",
                   "reason": "Independent real Cargo found absolute Cargo home paths containing '..' could prefer global SDK; final entry rejects parent components in explicit/default Cargo home before output."},
    "independent_review": "sdk-root-independent-review/final-v2",
    "real_cargo_lookup_report": "cargo-lookup-results/report.json",
    "real_cargo_relative_home_report": "cargo-relative-lookup-results/report.json",
    "pre_fix_actual_make_report": "results/report.json",
    "limitations": ["Host-only tests do not constitute a full Rust kernel build or QEMU boot.",
                    "Historical initial wrong-root SDK binary was not retained; old static path diagnosis remains its stated evidence.",
                    "Private prefixes isolate ordinary installations, not an immutable sandbox against an unrelated same-user writer."],
}
destination = BASE / "private-sdk-validation-ready-v2.json"
with destination.open("x") as output:
    output.write(json.dumps(receipt, indent=2) + "\n")
print(json.dumps({"ready": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}))
