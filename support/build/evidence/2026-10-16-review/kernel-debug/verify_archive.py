#!/usr/bin/env python3
"""Verify this real debug-run archive, without a new guest or raw DWARF ELF."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1048576), b""):
        result.update(block)
    return result.hexdigest()


def file_digest(path):
    with path.open("rb") as stream:
        return digest(stream)


def main():
    root = Path(__file__).resolve().parent
    repository = root.parents[4]
    index = json.loads((root / "members.json").read_text())
    require(file_digest(root / index["archive"]) == index["archive_sha256"], "tar SHA differs")
    expected = {value["member"]: value for value in index["members"]}
    with tarfile.open(root / index["archive"], "r:gz") as archive:
        require(len(archive.getmembers()) == len(expected), "raw member count differs")
        seen = set()
        for member in archive:
            require(member.isfile() and member.name in expected and member.name not in seen,
                    "unexpected raw member")
            seen.add(member.name)
            with archive.extractfile(member) as stream:
                require(digest(stream) == expected[member.name]["sha256"] and
                        member.size == expected[member.name]["bytes"], "raw member differs")
    for value in json.loads((root / "readable-index.json").read_text()):
        require(file_digest(root / value["path"]) == value["sha256"] ==
                expected[value["member"]]["sha256"], "readable copy differs")
    run = root / "readable/run"
    environment = json.loads((run / "environment.json").read_text())
    source = json.loads((root / "source-binding.json").read_text())
    commit = source["code_commit"]
    require(environment["git_head"] == commit, "run source HEAD differs")
    for relative, value in source["source_files"].items():
        raw = subprocess.check_output(["git", "-C", str(repository), "show", commit + ":" + relative])
        require(hashlib.sha256(raw).hexdigest() == value["recorded_sha256"] ==
                environment["source_sha256"][relative], "recorded source differs from Git object")
    require(len(source["source_files"]) == 63, "source input list differs")
    result = json.loads((run / "result.json").read_text())
    qemu = json.loads((run / "boot/qemu.json").read_text())
    require(result["passed"] is True and qemu["raw_exit_code"] == 33 and
            qemu["timed_out"] is False, "original debug run did not pass")
    require(file_digest(run / "boot/serial.log") == qemu["serial_sha256"] ==
            result["boot"]["serial_sha256"], "raw serial differs")
    for relative in ["exit-code.txt", "gdb-exit-code.txt", "driver-exit-code.txt",
                     "boot/make-exit-code.txt", "boot/log-exit-code.txt", "boot/run-exit-code.txt"]:
        require((run / relative).read_text().strip() == "0", "nonzero recorded status: " + relative)
    log = (run / "gdb.log").read_text()
    pc = result["gdb"]["pc"]
    binding = result["entry_artifact_binding"]
    instruction_bytes = binding["expected_bytes"]
    require(re.findall(r"^A01_GDB_RUST_ENTRY_HIT pc=(0x[0-9a-f]+) entry=(0x[0-9a-f]+)$", log,
                       re.MULTILINE) == [(pc, pc)], "verified Rust PC differs")
    require(re.findall(r"^A01_GDB_RUST_ENTRY_BYTES pc=(0x[0-9a-f]+) size=(\d+) bytes=([0-9a-f]+)$",
                       log, re.MULTILINE) == [(pc, "32", instruction_bytes)] and
            result["gdb"]["runtime_entry_bytes"] == instruction_bytes and
            len(bytes.fromhex(instruction_bytes)) == 32, "runtime entry bytes differ")
    require(log.count("A01_GDB_DETACHED") == 1 and "Source language is rust." in log,
            "Rust source or detach evidence missing")
    refs = json.loads((root / "artifact-references.json").read_text())
    kernel = repository / refs["kernel"]["repository_path"]
    require(file_digest(kernel) == refs["kernel"]["gzip_sha256"], "referenced kernel gzip differs")
    with gzip.open(kernel, "rb") as stream:
        require(digest(stream) == qemu["artifacts"]["-kernel"]["sha256"], "executed kernel differs")
    with gzip.open(kernel, "rb") as stream:
        stream.seek(binding["boot_artifact"]["entry_file_offset"])
        require(stream.read(32).hex() == instruction_bytes, "retained kernel entry differs")
    initrd = repository / refs["initramfs"]["repository_path"]
    require(file_digest(initrd) == qemu["artifacts"]["-initrd"]["sha256"], "executed initramfs differs")
    for role in ("symbol_artifact", "boot_artifact"):
        require(binding[role]["entry_bytes"] == instruction_bytes, "bound artifact entry differs")
    with tempfile.TemporaryDirectory(prefix="a01-next5-debug-check-") as temporary:
        checker = Path(temporary) / "check-boot.py"
        checker.write_bytes(subprocess.check_output(["git", "-C", str(repository), "show",
                                                    commit + ":support/build/check-boot.py"]))
        checked = subprocess.run([sys.executable, "-I", str(checker), str(run / "boot")],
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        require(checked.returncode == 0, checked.stdout)
    print(json.dumps({"passed": True, "scope": "offline retained evidence/source check; no new guest",
                      "raw_members_verified": len(expected), "source_files_verified": 63,
                      "source_commit": commit, "kernel_and_initramfs_references_verified": True,
                      "runtime_entry_bytes_verified": True, "boot_checker_exit": checked.returncode,
                      "boot_checker_stdout": checked.stdout, "raw_dwarf_required": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
        raise SystemExit("next5 debug evidence rejected: " + str(error)) from error
