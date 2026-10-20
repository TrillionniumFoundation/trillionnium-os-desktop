#!/usr/bin/env python3
"""Recheck retained ktest bytes and recreate the exact checker from Git; no VM."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    repo = (args.repository or here.parents[4]).resolve()
    provenance = json.loads((here / "provenance.json").read_text())
    refs = json.loads((here / "artifact-references.json").read_text())
    environment = json.loads((here / "environment.json").read_text())
    commit = provenance["published_equivalent"]["commit"]
    git = lambda *argv: subprocess.check_output(["git", "-C", str(repo), *argv])
    require(git("rev-parse", commit + "^{tree}").decode().strip() ==
            provenance["published_equivalent"]["tree"], "source tree mismatch")
    for relative, expected in environment["build_inputs_sha256"].items():
        require(digest(git("show", commit + ":" + relative)) == expected,
                "recorded source input differs: " + relative)
    for reference in provenance["prior_installation_evidence"]:
        require(digest((repo / reference["repository_path"]).read_bytes()) ==
                reference["sha256"], "prior installation evidence changed")
    results = []
    with tempfile.TemporaryDirectory(prefix="a01-ktest-archive-") as temporary:
        checker = Path(temporary) / "check.py"
        checker.write_bytes(git("show", commit + ":support/build/ktest/check.py"))
        for crate in ("ostd", "aster-core"):
            directory = here / crate
            record = json.loads((directory / "guests/guest-001/qemu.json").read_text())
            serial = (directory / "guests/guest-001/serial.log").read_bytes()
            require(digest(serial) == record["serial_sha256"], "raw serial SHA mismatch")
            require((directory / "osdk-exit-code.txt").read_text().strip() == "0",
                    "nonzero OSDK exit")
            lock = (directory / "generated.Cargo.lock").read_bytes()
            require(digest(lock) == environment["build_inputs_sha256"][
                f"support/build/ktest/locks/{crate}.Cargo.lock"], "generated lock mismatch")
            reference = refs["kernels"][crate]
            compressed = (repo / reference["repository_path"]).read_bytes()
            plain = gzip.decompress(compressed)
            require(digest(compressed) == reference["gzip_sha256"], "ELF gzip mismatch")
            artifact = record["artifacts"]["-kernel"]
            require(digest(plain) == artifact["sha256"] and len(plain) == artifact["size"],
                    "retained ELF differs from executed input")
            expected = json.loads((directory / "result.json").read_text())
            for mode in ([], ["-O"], ["-I"], ["-I", "-O"]):
                command = [sys.executable, *mode, str(checker),
                           str(directory / "guests"), "--crate", crate]
                process = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT)
                require(process.returncode == 0, process.stdout)
                require(json.loads(process.stdout) == expected, "checker summary differs")
                results.append({"crate": crate, "mode": mode, "exit": process.returncode,
                                "result": json.loads(process.stdout)})
    print(json.dumps({"passed": True, "source_commit": commit,
                      "checker_calls": results, "vm_started": False,
                      "original_absolute_paths_required": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit("ktest archive rejected: " + str(error)) from error
