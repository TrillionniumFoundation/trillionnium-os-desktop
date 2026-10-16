#!/usr/bin/env python3
"""Replay pinned A04 C ELF cases in independent fixed A01 kernel guests.

This diagnostic profile never replaces the unmodified A04 suite or claims W1.
It imports the frozen PR8 pack/parser/QEMU APIs without modifying A04 source.
"""
import argparse
import concurrent.futures
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

PROFILE = "a01-a04-isolated-case-v1"
A04_COMMIT = "16d672881909a5a9197d82126032b7d962db7d76"
SOURCE_BLOBS = {
    "support/rootfs/capture.py": "b59fa43a82de2e70cc45e6bcfa05a87e5759ad3e",
    "support/rootfs/README.md": "9df9e78317c4016d6a2614be0f440b416f33cfc0",
    "tests/workloads/linux/guest.py": "05b90cc4a164eadd8754460bfc4668a8cbab70f6",
    "tests/workloads/linux/run.py": "c998f91c4f61789e1ac9a8c57f937e13188aa50c",
    "tests/workloads/linux/probe.c": "b5cf4e553f67885781528d37840c97ea62bda02f",
    "tests/workloads/linux/sqlite_probe.c": "e354a8119779f4defd18923097dbc66b22e4d178",
    "tests/workloads/linux/baselines/linux-debian13-x86_64.json": "3214595d63bc8689919786074548202989164e1c",
    "compat/linux/compare.py": "bcc5eda94f4b1eb9d05fab954b64423d794dd5f0",
    "tests/workloads/linux/chroot_replay.py": "f437342b5e31d3b3a58ae3e764c696d69bab4b22",
    "tests/workloads/linux/replay_qemu.py": "d20c01cfa0aa9902ffbb34ab7b3ab2c18978b664",
    "support/rootfs/manifest-debian13-x86_64.json": "844297a58b831d97d5dd1c0398eb2c854c22bc53",
}


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(path, obj):
    with path.open("x") as stream:
        stream.write(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def verified_source(root):
    records = {}
    for path, expected in SOURCE_BLOBS.items():
        data = (root / path).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != expected:
            raise ValueError("pinned PR8 source differs: " + path)
        records[path] = {"sha256": hashlib.sha256(data).hexdigest(), "git_blob": actual}
    return records


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a04-source-root", type=Path, required=True)
    ap.add_argument("--rootfs", type=Path, required=True)
    ap.add_argument("--a01-kernel-gz", type=Path, required=True)
    ap.add_argument("--a01-initramfs", type=Path, required=True)
    ap.add_argument("--firmware", type=Path, required=True)
    ap.add_argument("--qemu", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--case", action="append", help="select a pinned case; repeat")
    args = ap.parse_args()
    if not 1 <= args.timeout <= 180 or not 1 <= args.jobs <= 2:
        ap.error("timeout must be 1..180 and jobs must be 1..2")
    root = args.a04_source_root.resolve()
    source = verified_source(root)
    q = imported("a04_isolated_qemu", root / "tests/workloads/linux/replay_qemu.py")
    capture = imported("a04_isolated_rootfs", root / "support/rootfs/capture.py")
    guest = q.guest
    reference_path = root / "tests/workloads/linux/baselines/linux-debian13-x86_64.json"
    reference = json.loads(reference_path.read_text())
    manifest_path = root / "support/rootfs/manifest-debian13-x86_64.json"
    capture.verify(args.rootfs, manifest_path)
    kernel_data, qemu_version = q.preflight(
        args.a01_kernel_gz, args.a01_initramfs, args.firmware, args.qemu
    )
    cases = guest.reference_elf_cases(reference)
    if args.case:
        selected = set(args.case)
        if not selected <= {name for name, _, _ in cases}:
            ap.error("unknown case")
        cases = [item for item in cases if item[0] in selected]
    if args.out_dir.exists() or args.out_dir.is_symlink():
        ap.error("output exists; refusing to overwrite evidence")
    os.umask(0o077)
    args.out_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    dump(args.out_dir / "environment.json", {
        "profile": PROFILE, "a04_source_commit": A04_COMMIT, "source": source,
        "entry_script_sha256": guest.sha_file(Path(__file__).resolve()),
        "original_reference_sha256": guest.sha_file(reference_path),
        "qemu_version": qemu_version, "qemu_sha256": guest.sha_file(args.qemu),
        "firmware_sha256": guest.sha_file(args.firmware),
        "kernel_sha256": hashlib.sha256(kernel_data).hexdigest(),
        "original_a01_initramfs_sha256": guest.sha_file(args.a01_initramfs),
        "rootfs_manifest_sha256": guest.sha_file(manifest_path),
        "full_original_suite_passed": False, "full_w1_passed": False,
        "jobs": args.jobs, "per_guest_timeout_seconds": args.timeout,
    })

    def run(item):
        name, _, _ = item
        out = args.out_dir / name
        out.mkdir(mode=0o700)
        subset = copy.deepcopy(reference)
        subset["cases"] = {name: reference["cases"][name]}
        image = out / "initramfs.cpio.gz"
        manifest = guest.pack(args.a01_initramfs, args.rootfs, manifest_path,
                              subset, image, out / "inputs.json")
        kernel = out / "kernel.elf"
        kernel.write_bytes(kernel_data)
        cmd = q.command_for_qemu(args.qemu, args.firmware, kernel, image)
        dump(out / "invocation.json", {
            "argv": cmd, "timeout_seconds": args.timeout,
            "subset_of_original_reference": [name],
            "original_reference_sha256": guest.sha_file(reference_path),
        })
        started = time.time()
        timed_out = False
        with (out / "serial.log").open("x+b") as log:
            try:
                raw_exit = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                          timeout=args.timeout, check=False).returncode
            except subprocess.TimeoutExpired:
                raw_exit = None
                timed_out = True
            log.flush()
            log.seek(0)
            serial_data = log.read()
            serial_stat = os.fstat(log.fileno())
        serial = out / "serial.log"
        snapshot = out / "serial-captured.log.gz"
        with snapshot.open("xb") as stream:
            stream.write(gzip.compress(serial_data, mtime=0))
        # Match Path.read_text's universal newline conversion in A04's original
        # runner while retaining and hashing the complete original serial bytes.
        serial_text = serial_data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        result = guest.parse_serial(serial_text, reference, manifest,
                                    qemu_exit=raw_exit, kernel_sha=guest.sha_file(kernel),
                                    image_sha=guest.sha_file(image))
        dump(out / "guest-result.json", result)
        observed = result["cases"][name]
        record = {
            "case": name, "elapsed_seconds": time.time() - started,
            "raw_qemu_exit_code": raw_exit, "timed_out": timed_out,
            "guest_execution_verified": result["guest_execution_verified"],
            "case_result": observed,
            "exact_match": not timed_out and result["guest_execution_verified"]
            and result["guest_compatibility_passed"] and observed.get("status") == "pass",
            "serial_sha256": hashlib.sha256(serial_data).hexdigest(),
            "serial_snapshot_sha256": guest.sha_file(snapshot),
            "serial_fd_identity": {"device": serial_stat.st_dev,
                                   "inode": serial_stat.st_ino,
                                   "bytes": serial_stat.st_size},
            "initramfs_sha256": guest.sha_file(image), "kernel_sha256": guest.sha_file(kernel),
            "original_suite_qualification": False,
        }
        dump(out / "result.json", record)
        print(json.dumps({key: record[key] for key in
                          ("case", "exact_match", "timed_out", "raw_qemu_exit_code")}), flush=True)
        return record

    results = list(concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs).map(run, cases))
    for record in results:
        snapshot = args.out_dir / record["case"] / "serial-captured.log.gz"
        data = gzip.decompress(snapshot.read_bytes())
        if (hashlib.sha256(data).hexdigest() != record["serial_sha256"]
                or guest.sha_file(snapshot) != record["serial_snapshot_sha256"]):
            raise ValueError("captured serial snapshot changed: " + record["case"])
        serial = args.out_dir / record["case"] / "serial.log"
        record["raw_serial_changed_after_capture"] = guest.sha_file(serial) != record["serial_sha256"]
    summary = {
        "profile": PROFILE, "case_count": len(results),
        "matched": sum(item["exact_match"] for item in results),
        "timed_out": sum(item["timed_out"] for item in results),
        "failed_completed": sum(not item["exact_match"] and not item["timed_out"]
                                for item in results),
        "original_unmodified_suite_passed": False, "full_w1_passed": False,
        "results": results,
    }
    dump(args.out_dir / "summary.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}),
          flush=True)
    return 0 if summary["matched"] == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
