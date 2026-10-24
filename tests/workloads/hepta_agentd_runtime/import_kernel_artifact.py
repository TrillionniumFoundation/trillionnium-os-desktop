#!/usr/bin/env python3
"""Import one exact successful A06 ordinary-kernel archive, without booting it.

The SHA-256-pinned archive, original source snapshots, build exits, raw boot and
QueryAbi serial records are prerequisites. This transcribes an existing real
build; it never creates a successful receipt from an ELF or CI status alone.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import stat
import sys
import zipfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_agentd_runtime as gate

require, sha, save = gate.require, gate.sha, gate.save
REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
RUN_ID = 39898657974
ARTIFACT_ID = 12480223660
ARTIFACT_NAME = "a06-exact-kernel-ktest-39898657974"
ARCHIVE_BYTES = 222254688
ARCHIVE_SHA256 = "12f6e6ccd459358e5cc254c7aa60d1f0ca16d9930e66c0f58906c18ab9b5784e"
KERNEL_SHA256 = "5a4f528b344c2d0bdb40c41c446e141d206aafb84d4cb6a6895dcf5c962f1450"
PREFIX = "_temp/a06-queryabi-candidate/"
SOURCE_COUNT = 7821
CHECKER_FILES = (
    "tests/kernel/control/run_queryabi_candidate_guest.py",
    "tests/kernel/control/run_queryabi_guest.py",
    "tests/organ_backend/run_guest_probe.py",
    "support/build/check-boot.py",
)
# No archive-wide extraction. Only these fixed regular members are read, with
# individual decompressed bounds; nothing in the archive becomes executable.
RAW_LIMITS = {
    "result.json": 256 * 1024,
    "serial.log": 8 * 1024**2,
    "source-before.json": 4 * 1024**2,
    "source-after-boot.json": 4 * 1024**2,
    "source-after-guest.json": 4 * 1024**2,
    "product-boot/command.sh": 64 * 1024,
    "product-boot/environment.log": 256 * 1024,
    "product-boot/source-inputs.json": 256 * 1024,
    "product-boot/qemu.json": 256 * 1024,
    "product-boot/serial.log": 8 * 1024**2,
    "product-boot/run_kernel.log": 16 * 1024**2,
    "product-boot/make-exit-code.txt": 64,
    "product-boot/log-exit-code.txt": 64,
    "product-boot/run-exit-code.txt": 64,
    "product-boot/initramfs-manifest.json": 256 * 1024,
}
BINARY_MEMBERS = {
    "kernel.elf": ("product-kernel.elf", 64 * 1024**2, KERNEL_SHA256),
    "initramfs.cpio.gz": ("product-boot/initramfs.cpio.gz", 8 * 1024**2, gate.abi.INITRAMFS_SHA),
    "bios.bin": ("bios.bin", 2 * 1024**2, gate.abi.BIOS_SHA),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 4 * 1024**2,
            "bounded regular metadata file required")
    value = gate.json_value(path.read_bytes())
    require(isinstance(value, dict), "metadata must be an object")
    return value


def validate_metadata(artifacts, run):
    entries = artifacts.get("artifacts")
    require(isinstance(entries, list), "original workflow artifact listing required")
    matches = [item for item in entries if isinstance(item, dict) and item.get("id") == ARTIFACT_ID]
    require(len(matches) == 1, "fixed A06 artifact is missing or repeated")
    artifact = matches[0]
    require(artifact.get("name") == ARTIFACT_NAME and artifact.get("size_in_bytes") == ARCHIVE_BYTES
            and artifact.get("digest") == "sha256:" + ARCHIVE_SHA256,
            "A06 artifact identity, size or digest changed")
    workflow_run = artifact.get("workflow_run", {})
    require(isinstance(workflow_run, dict) and workflow_run.get("id") == RUN_ID
            and workflow_run.get("head_sha") == gate.DESKTOP["head"],
            "artifact is from a different workflow run or source")
    repository = run.get("repository")
    require(run.get("id") == RUN_ID and run.get("head_sha") == gate.DESKTOP["head"]
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and run.get("path") == ".github/workflows/a06-kernel.yml"
            and isinstance(repository, dict) and repository.get("full_name") == REPOSITORY,
            "original final-head A06 run did not complete successfully")
    return artifact


def read_member(archive, name, limit):
    entries = [entry for entry in archive.infolist() if entry.filename == PREFIX + name]
    require(len(entries) == 1, "archive member missing or repeated: " + name)
    entry = entries[0]
    mode = entry.external_attr >> 16
    require(not entry.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG)
            and 0 <= entry.file_size <= limit, "archive member is not a bounded regular file: " + name)
    with archive.open(entry) as stream:
        data = stream.read(limit + 1)
    require(len(data) == entry.file_size and len(data) <= limit, "archive member size changed: " + name)
    return data


def validate_snapshots(raw, result):
    require(isinstance(result, dict), "original candidate receipt must be an object")
    values = [gate.json_value(raw[name]) for name in
              ("source-before.json", "source-after-boot.json", "source-after-guest.json")]
    before = values[0]
    require(isinstance(before, dict) and before == values[1] == values[2],
            "original source snapshots changed across build or execution")
    require(before.get("schema") == "a06.g1-source-snapshot.v1"
            and {key: before.get(key) for key in ("head", "tree")} == gate.DESKTOP,
            "original kernel source identity differs from reviewed source")
    files = before.get("files")
    require(isinstance(files, dict) and len(files) == SOURCE_COUNT
            and result.get("source_file_count") == SOURCE_COUNT,
            "original full source snapshot is incomplete")
    require(isinstance(before.get("root"), str) and Path(before["root"]).is_absolute(),
            "original build source root missing")
    review = load_json(HERE / "source-review.json")
    for item in review["source_files"]:
        if item["repository"] == "desktop":
            record = files.get(item["path"], {})
            require(isinstance(record, dict) and record.get("sha256") == item["sha256"]
                    and record.get("git_blob") == item["git_blob"],
                    "reviewed Desktop file differs from the actual kernel build source")
    return before


def original_checker(desktop, snapshot):
    # Load only original source bytes that match the pinned archive's complete
    # source inventory. A partial read-only checkout is sufficient for replay;
    # userspace preparation independently requires both complete clean repos.
    identities = {}
    for name in CHECKER_FILES:
        path = desktop / name
        record = snapshot["files"][name]
        gate.pinned(path, record["sha256"], 4 * 1024**2)
        data = path.read_bytes()
        blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        require(blob == record["git_blob"] and len(data) == record["size"], "original checker source changed")
        identities[name] = {"git_blob": blob, "sha256": digest(data)}
    path = desktop / CHECKER_FILES[0]
    spec = importlib.util.spec_from_file_location("a06_original_product_checker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, identities


def validate_product(raw, binaries, snapshot, original, raw_directory):
    result = gate.json_value(raw["result.json"])
    require(isinstance(result, dict) and result.get("schema") == "a06.g1-queryabi-product-candidate.v1"
            and result.get("passed") is True and result.get("stage") == "complete"
            and result.get("source_inputs_unchanged") is True
            and result.get("source_head") == snapshot["head"] and result.get("source_tree") == snapshot["tree"],
            "original complete successful product receipt required")
    require(result.get("product_configuration") == "ActionChoice::Run; no --cfg ktest"
            and type(result.get("product_wrapper_exit")) is int and result["product_wrapper_exit"] == 0
            and result.get("product_boot_raw_exit") == 33,
            "original ordinary build and boot did not succeed")
    for name in ("make", "log", "run"):
        require(raw["product-boot/" + name + "-exit-code.txt"].strip() == b"0", "original build stage failed")
    require(raw["product-boot/environment.log"].decode().splitlines().count(snapshot["head"]) == 1,
            "ordinary build environment does not record the actual source head")
    source_gate = gate.json_value(raw["product-boot/source-inputs.json"])
    require(isinstance(source_gate, dict) and source_gate.get("passed") is True and source_gate.get("errors") == []
            and source_gate.get("toolchain") == "nightly-2026-07-21",
            "original pinned kernel source/toolchain gate failed")
    qemu = gate.json_value(raw["product-boot/qemu.json"])
    require(digest(raw["product-boot/qemu.json"]) == result.get("product_qemu_record_sha256"),
            "ordinary product boot record is not bound to the candidate result")
    pairs = original.verify_n0_argv(qemu["argv"])
    original.boot_check.check_boot(raw_directory / "product-boot", live_artifacts=False)
    artifacts = qemu["artifacts"]
    for option, filename in (("-kernel", "kernel.elf"), ("-initrd", "initramfs.cpio.gz"), ("-bios", "bios.bin")):
        require(artifacts[option]["path"] == pairs[option]
                and artifacts[option]["sha256"] == digest(binaries[filename])
                and artifacts[option]["size"] == len(binaries[filename]),
                "retained binary differs from the actual ordinary boot input")
    kernel = binaries["kernel.elf"]
    require(kernel[:6] == b"\x7fELF\x02\x01" and kernel[18:20] == b"\x03\x00",
            "expected the original x86_64 multiboot ELF with converted EM_386 header")
    require(result.get("kernel_elf_sha256") == digest(kernel)
            and result.get("original_initramfs_sha256") == digest(binaries["initramfs.cpio.gz"])
            and result.get("bios_sha256") == digest(binaries["bios.bin"]), "candidate input identities changed")
    command = shlex.split(raw["product-boot/command.sh"].decode())
    root = Path(snapshot["root"])
    boot_directory = Path(pairs["-initrd"]).parent
    prefix = ["make", "-C", str(root / "kernel/asterinas"), "-f", "Makefile", "-f",
              str(root / "support/build/minimal.mk"), "run_kernel"]
    required = {"TARGET_ARCH=x86_64", "SMP=1", "MEM=512M", "ENABLE_KVM=0", "BOOT_PROTOCOL=multiboot",
                "INITRAMFS=on", "AUTO_TEST=none", "A01_INITRAMFS=" + str(boot_directory / "initramfs.cpio.gz"),
                "A01_QEMU_WRAPPER=" + str(root / "support/build/record-qemu.py")}
    require(len(command) == 18 and command[:8] == prefix and command[8].startswith("CARGO_OSDK=")
            and set(command[9:]) == required, "not the original ordinary kernel build command")
    require(result.get("minimal_generated_package_count") == 204
            and result.get("minimal_generated_lock_sha256") == snapshot["files"]["support/build/minimal/Cargo.lock"]["sha256"],
            "ordinary kernel dependency lock differs from original source")
    evaluated = original.evaluate_guest(raw["serial.log"], result.get("qemu_exit"), result.get("timed_out"))
    require(evaluated["passed"] and all(result.get(key) == value for key, value in evaluated.items()),
            "original candidate oracle rejected the raw guest bytes or stored result")
    return command, evaluated


def import_archive(args, out, report):
    artifact = validate_metadata(load_json(args.artifact_metadata), load_json(args.run_metadata))
    gate.pinned(args.archive, ARCHIVE_SHA256, ARCHIVE_BYTES)
    require(args.archive.stat().st_size == ARCHIVE_BYTES, "A06 archive byte count differs")
    require(not out.exists() and not out.is_symlink(), "import destination must be new")
    with zipfile.ZipFile(args.archive) as archive:
        raw = {name: read_member(archive, name, limit) for name, limit in RAW_LIMITS.items()}
        binaries = {}
        for filename, (member, limit, expected) in BINARY_MEMBERS.items():
            data = read_member(archive, member, limit)
            require(digest(data) == expected, "fixed retained binary digest differs: " + filename)
            binaries[filename] = data
    result = gate.json_value(raw["result.json"])
    snapshot = validate_snapshots(raw, result)
    original, checker_identities = original_checker(args.desktop_source, snapshot)
    out.mkdir(mode=0o700)
    report["output_created"] = True
    raw_directory = out / "original"
    for name, data in raw.items():
        path = raw_directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    command, evaluated = validate_product(raw, binaries, snapshot, original, raw_directory)
    for filename, data in binaries.items():
        (out / filename).write_bytes(data)
        (out / filename).chmod(0o444)
    metadata = {}
    for name, path in (("artifact-list.json", args.artifact_metadata), ("workflow-run.json", args.run_metadata)):
        data = path.read_bytes()
        (raw_directory / name).write_bytes(data)
        metadata[name] = {"sha256": digest(data), "bytes": len(data)}
    receipt = {
        "schema": "hepta.native-original-runtime-build.v1", "sources": gate.SOURCES,
        "build_sources": {"desktop": {key: snapshot[key] for key in ("head", "tree")}},
        "kernel_profile": "ordinary-os", "built": True, "source_clean": True,
        "binary_sha256": {"kernel": KERNEL_SHA256}, "commands": [command],
        "origin": {"repository": REPOSITORY, "workflow_run_id": RUN_ID, "artifact_id": ARTIFACT_ID,
                   "artifact_name": artifact["name"], "archive_sha256": ARCHIVE_SHA256,
                   "archive_bytes": ARCHIVE_BYTES, "metadata": metadata},
        "original_evidence": {name: {"path": "original/" + name, "archive_member": PREFIX + name,
                                     "sha256": digest(data), "bytes": len(data)}
                              for name, data in raw.items()},
        "source_snapshots_equal": True, "source_file_count": len(snapshot["files"]),
        "original_checker_sources": checker_identities, "original_candidate_oracle": evaluated,
        "kernel_built_in_this_import": False, "guest_executed_in_this_import": False,
        "runtime_executed": False, "f1_completed": False,
        "attestation": "transcribed exact successful A06 build and raw boot records; not new execution or remote attestation",
    }
    save(out / "kernel-build.json", receipt)
    report.update(imported=True, kernel_sha256=KERNEL_SHA256, kernel_receipt_sha256=sha(out / "kernel-build.json"),
                  source_file_count=SOURCE_COUNT, original_candidate_oracle_passed=evaluated["passed"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--desktop-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    report = {"schema": "hepta.native-original-runtime-kernel-import.v1", "imported": False,
              "kernel_built_in_this_import": False, "guest_executed_in_this_import": False,
              "f1_completed": False, "sources": gate.SOURCES,
              "started_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        import_archive(args, out, report)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if report.get("output_created") is True:
        save(out / "import-result.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["imported"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
