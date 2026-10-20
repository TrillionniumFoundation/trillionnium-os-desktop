#!/usr/bin/env python3
"""Verify retained debug logs and boot inputs without a VM or the raw DWARF ELF."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(stream):
    result = hashlib.sha256()
    for data in iter(lambda: stream.read(1048576), b""):
        result.update(data)
    return result.hexdigest()


def file_digest(path):
    with path.open("rb") as stream:
        return digest(stream)


def main():
    root = Path(__file__).resolve().parent
    repository = root.parents[4]
    artifacts = root / "artifacts"
    manifest = json.loads((artifacts / "manifest.json").read_text())
    runs = json.loads((root / "runs.json").read_text())
    checked = []
    for run in runs:
        directory = root / run["archive_directory"]
        index = json.loads((directory / "members.json").read_text())
        archive = directory / index["archive"]
        require(file_digest(archive) == index["sha256"], "raw archive SHA mismatch")
        expected = {member["member"]: member for member in index["members"]}
        with tarfile.open(archive, "r:gz") as retained:
            actual = retained.getmembers()
            require(len(actual) == len(expected), "raw archive member count differs")
            for member in actual:
                require(member.isfile() and member.name in expected, "unexpected raw member")
                value = expected.pop(member.name)
                with retained.extractfile(member) as stream:
                    require(digest(stream) == value["sha256"] and member.size == value["bytes"],
                            "raw member bytes differ: " + member.name)
        require(not expected, "raw archive is incomplete")
        for readable in json.loads((directory / "readable-index.json").read_text()):
            require(file_digest(directory / readable["path"]) == readable["sha256"],
                    "readable file differs from original raw member")
        result = json.loads((directory / "readable/run/result.json").read_text())
        require(result["passed"] is run["passed"], "run summary differs")
        if run["passed"]:
            boot = directory / "readable/run/boot"
            qemu = json.loads((boot / "qemu.json").read_text())
            require(qemu["raw_exit_code"] == 33 and qemu["timed_out"] is False,
                    "successful debug run lacks raw QEMU33")
            require(qemu["artifacts"]["-kernel"]["sha256"] ==
                    manifest["executed_stripped_kernel"]["uncompressed_sha256"] and
                    qemu["artifacts"]["-initrd"]["sha256"] == manifest["executed_initramfs"]["sha256"],
                    "executed input does not match retained artifact")
            require(file_digest(boot / "serial.log") == qemu["serial_sha256"],
                    "raw serial differs")
            log = (directory / "readable/run/gdb.log").read_text()
            hits = re.findall(r"^A01_GDB_RUST_ENTRY_HIT pc=(0x[0-9a-f]+) entry=(0x[0-9a-f]+)$",
                              log, re.MULTILINE)
            require(hits == [(result["gdb"]["pc"], result["gdb"]["entry_address"])],
                    "GDB hit differs from recorded Rust entry")
            require(hits[0][0] == hits[0][1] and "Source language is rust." in log and
                    log.count("A01_GDB_DETACHED") == 1, "GDB source/entry/detach evidence missing")
            require(result["gdb"]["gdb_status"] == 0 and result["boot"]["driver_status"] == 0,
                    "GDB or driver failed")
            if "entry_artifact_binding" in result:
                binding = result["entry_artifact_binding"]
                expected_bytes = binding["expected_bytes"]
                runtime = re.findall(r"^A01_GDB_RUST_ENTRY_BYTES pc=(0x[0-9a-f]+) size=(\d+) bytes=([0-9a-f]+)$",
                                     log, re.MULTILINE)
                require(binding["entry_size"] == 32 and len(bytes.fromhex(expected_bytes)) == 32,
                        "entry-byte evidence has wrong size")
                require(runtime == [(result["gdb"]["pc"], "32", expected_bytes)] and
                        result["gdb"]["runtime_entry_bytes"] == expected_bytes,
                        "runtime entry bytes do not match the original artifacts")
                for role in ("symbol_artifact", "boot_artifact"):
                    require(binding[role]["entry_bytes"] == expected_bytes,
                            "symbol and boot entry bytes differ")
                require(binding["boot_artifact"]["sha256"] == qemu["artifacts"]["-kernel"]["sha256"],
                        "bound boot ELF differs from executed input")
                with gzip.open(artifacts / manifest["executed_stripped_kernel"]["retained"], "rb") as image:
                    image.seek(binding["boot_artifact"]["entry_file_offset"])
                    require(image.read(32).hex() == expected_bytes, "retained boot entry bytes differ")
        checked.append({"run": run["run"], "passed_in_original_run": run["passed"],
                        "raw_members_verified": len(index["members"])})
    kernel = manifest["executed_stripped_kernel"]
    require(file_digest(artifacts / kernel["retained"]) == kernel["gzip_sha256"], "ELF gzip differs")
    with gzip.open(artifacts / kernel["retained"], "rb") as stream:
        require(digest(stream) == kernel["uncompressed_sha256"], "executed kernel differs")
    initrd = manifest["executed_initramfs"]
    require(file_digest(artifacts / initrd["retained"]) == initrd["sha256"], "initramfs differs")
    require(manifest["raw_symbol_elf"]["retained"] is False, "raw DWARF retention claim changed")
    code = json.loads((root / "code-commits.json").read_text())
    commit = code["published_debug_code_commit"]
    git_show = lambda relative: subprocess.check_output(
        ["git", "-C", str(repository), "show", commit + ":" + relative])
    for relative, value in code["all63_run04_recorded_inputs_match_published_commit"].items():
        require(hashlib.sha256(git_show(relative)).hexdigest() == value["recorded_run04_sha256"],
                "recorded source differs from published Git object")
    replay = json.loads((root / "source-recovery/replay.json").read_text())
    with tempfile.TemporaryDirectory(prefix="a01-debug-source-recheck-") as temporary:
        temporary = Path(temporary)
        for relative in replay["recovered_sha256"]:
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(git_show(relative))
        subprocess.run(["git", "apply", str(root / "source-recovery/recover-run01-03.patch")],
                       cwd=temporary, check=True)
        for relative, expected in replay["recovered_sha256"].items():
            require(file_digest(temporary / relative) == expected, "older measured source recovery differs")
    print(json.dumps({"passed": True, "scope": "offline log/input archive verification; no new guest",
                      "runs": checked, "published_code_commit": commit,
                      "recorded_source_files_verified": 63, "earlier_source_recovery_verified": True,
                      "raw_dwarf_elf_required": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
        raise SystemExit("debug archive rejected: " + str(error)) from error
