"""Rebuild recorded checker versions from Git and replay archive mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--repository", required=True, type=Path)
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--new-code-commit")
parser.add_argument("--run-tests", action="store_true")
args = parser.parse_args()
here = Path(__file__).resolve().parent
commits = json.loads((here / "code-commits.json").read_text())
new_commit = args.new_code_commit or commits.get("new_code_commit")
if not new_commit:
    raise SystemExit("supply --new-code-commit matching the recorded new source SHA256")
args.output.mkdir(parents=True, exist_ok=False)


def source(commit, relative, destination, expected):
    raw = subprocess.check_output(["git", "show", commit + ":" + relative], cwd=args.repository)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise SystemExit("Git source does not match measured SHA256: " + relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)


old = args.output / "old/check-boot.py"
build = args.output / "new/support/build"
new = build / "check-boot.py"
source(commits["old_code_commit"], "support/build/check-boot.py", old, commits["old_checker_sha256"])
source(new_commit, "support/build/check-boot.py", new, commits["new_checker_sha256"])
fixtures = args.output / "fixtures"
shutil.copytree(here / "fresh-record-fixtures", fixtures)
results = []
for case in ("matching-new-record", "appended-new-record", "known-failed-new-record"):
    checkers = (("old", old), ("new", new)) if case != "known-failed-new-record" else (("new", new),)
    for name, checker in checkers:
        for mode in ((), ("-O",), ("-I",), ("-I", "-O")):
            command = [sys.executable, *mode, str(checker), str(fixtures / case)]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            expected_accept = name == "old" or case == "matching-new-record"
            if (result.returncode == 0) != expected_accept:
                raise SystemExit("unexpected result: " + json.dumps(command) + "\n" + result.stdout)
            results.append({"case": case, "checker": name, "mode": mode,
                            "exit": result.returncode, "output": result.stdout})
(args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
if args.run_tests:
    source(new_commit, "support/build/record-qemu.py", build / "record-qemu.py", commits["new_recorder_sha256"])
    source(new_commit, "support/build/tests/test_boot_evidence.py", build / "tests/test_boot_evidence.py", commits["new_test_sha256"])
    fixture_path = "support/build/evidence/2026-10-16/acceptance/boot/serial.log"
    source(new_commit, fixture_path, build / "evidence/2026-10-16/acceptance/boot/serial.log",
           commits["test_fixture_serial_sha256"])
    for mode in (("-I",), ("-I", "-O")):
        subprocess.run([sys.executable, *mode, str(build / "tests/test_boot_evidence.py")], check=True)
print("PASS: recorded old/new source hashes and 20 archive mutation checks reproduced")
