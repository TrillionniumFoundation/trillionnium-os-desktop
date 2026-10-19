#!/usr/bin/env python3
"""Run A04's identical pinned ELF in an ACTUAL A01 Asterinas QEMU guest.

Owned A04 wrapper only: requires already retrieved A01 accepted artifacts and
hashed staged A04 rootfs, runs disposable TCG with no network/host disks/KVM,
retains actual serial/raw exit and compares ABI observations. Missing inputs,
missing QEMU, hash drift or timeout are blockers, never successful guest tests.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
A01_SEABIOS_SHA256 = "1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735"
# Accepted A01 guest boot evidence: exact host QEMU binary, not just text from `-version`.
A01_QEMU_SHA256 = "8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854"
# These are the exact *reviewed* Debian 13 A04 reference/manifest bytes.
# Unlike elf[] claims, a modified reference can silently shrink the test
# denominator; a modified library manifest can alter runtime dependencies.
# Upgrade these pins only after a new real Linux baseline is independently run.
A04_REFERENCE_SHA256 = "ea38aa903ead1f72683ab10dcefeb756ec8b1e115dfccf49d8a9823c8a968026"
A04_ROOTFS_MANIFEST_SHA256 = "55aa8369d4f912267139ef7626c752814d7dc833e49accc337529f2545fb94cb"
A04_ROOTFS_TAR_SHA256 = "df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797"
A04_ROOTFS_FILE_COUNT = 17
A04_C_ELF_CASE_COUNT = 28
A04_UNPORTED_CASE_COUNT = 4


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guest = imported("a04_qemu_guest", HERE / "guest.py")
differential = imported("a04_qemu_differential", ROOT / "compat/linux/compare.py")
capture = imported("a04_qemu_rootfs_capture", ROOT / "support/rootfs/capture.py")


def load_fixed_reference(reference_path, rootfs_manifest_path):
    """Reject a narrowed Linux reference or changed rootfs before guest replay.

    The user must have supplied the reviewed A04 bytes, not merely two files
    that agree with each other after being changed together.
    """
    if guest.sha_file(reference_path) != A04_REFERENCE_SHA256:
        raise ValueError("pinned A04 Linux reference SHA-256 mismatch")
    if guest.sha_file(rootfs_manifest_path) != A04_ROOTFS_MANIFEST_SHA256:
        raise ValueError("pinned A04 rootfs manifest SHA-256 mismatch")
    reference = json.loads(reference_path.read_text())
    elf_cases = guest.reference_elf_cases(reference)
    if (len(elf_cases) != A04_C_ELF_CASE_COUNT or
            len(reference.get("cases", {})) != A04_C_ELF_CASE_COUNT + A04_UNPORTED_CASE_COUNT or
            set(reference.get("binaries", {})) != set(guest.BINARY_FOR)):
        raise ValueError("A04 ELF denominator or binary identity set drifted")
    return reference


def stage_rootfs(args, out):
    """Accept one reviewed rootfs input; never unpack an unpinned archive.

    A directory remains supported for existing callers, while --rootfs-tar
    is the single-command A00 runner handoff. Archive extraction is confined
    to this NEW private evidence directory and verifies each member's digest,
    type and mode before any of its ELF bytes enter the guest image.
    This checks INPUT identity only; it is not a guest execution claim.
    """
    directory = getattr(args, "rootfs", None)
    archive = getattr(args, "rootfs_tar", None)
    if (directory is None) == (archive is None):
        raise ValueError("exactly one of --rootfs or --rootfs-tar is required")
    if archive is None:
        return directory, {"rootfs_input": "staged_directory"}
    if guest.sha_file(archive) != A04_ROOTFS_TAR_SHA256:
        raise ValueError("fixed A04 rootfs tar SHA-256 mismatch")
    if guest.sha_file(args.rootfs_manifest) != A04_ROOTFS_MANIFEST_SHA256:
        raise ValueError("fixed A04 rootfs manifest SHA-256 mismatch")
    destination = out / "staged-rootfs"
    count = capture.extract_verified_tar(archive, args.rootfs_manifest, destination)
    if count != A04_ROOTFS_FILE_COUNT:
        raise ValueError("fixed A04 rootfs file-count mismatch")
    return destination, {"rootfs_input": "pinned_tar_verified_extraction",
                         "rootfs_tar_sha256": A04_ROOTFS_TAR_SHA256,
                         "rootfs_extracted_files": count}


def load_kernel(gzip_path):
    data = gzip.decompress(gzip_path.read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    if digest != guest.A01_KERNEL_SHA:
        raise ValueError("A01 kernel uncompressed SHA-256 mismatch")
    if data[:4] != b"\x7fELF":
        raise ValueError("pinned kernel lacks ELF magic")
    return data


def check_firmware(firmware):
    if not firmware.is_file() or guest.sha_file(firmware) != A01_SEABIOS_SHA256:
        raise ValueError("SeaBIOS missing or SHA-256 differs from pinned A01 firmware")


def command_for_qemu(qemu, firmware, kernel, initramfs):
    return [str(qemu), "-kernel", str(kernel), "-initrd", str(initramfs),
            "-append", "earlycon console=ttyS0 loglevel=info --",
            "-machine", "q35", "-accel", "tcg", "-cpu", "max",
            "-bios", str(firmware), "-m", "512M", "-smp", "1",
            "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
            "-display", "none", "-monitor", "none", "-serial", "stdio",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]


def preflight(a01_kernel_gz, a01_initramfs, firmware, qemu):
    if not qemu or not Path(qemu).is_file() or not os.access(qemu, os.X_OK):
        raise ValueError("QEMU executable unavailable: no guest run")
    # `-version` is untrusted program output: a wrapper can print the expected
    # string and forge an entire serial trace. Accept ONLY the A01-reviewed
    # QEMU executable bytes, and retain the SHA in the execution evidence.
    if guest.sha_file(Path(qemu).resolve()) != A01_QEMU_SHA256:
        raise ValueError("QEMU executable SHA-256 mismatch with accepted A01 run")
    check_firmware(firmware)
    kernel = load_kernel(a01_kernel_gz)
    if guest.sha_file(a01_initramfs) != guest.A01_IMAGE_SHA:
        raise ValueError("A01 accepted initramfs differs: no guest run")
    version = subprocess.run([str(qemu), "-version"], timeout=10,
                             capture_output=True, text=True, check=False)
    if version.returncode or not version.stdout.startswith("QEMU emulator version "):
        raise ValueError("QEMU version could not be verified")
    return kernel, version.stdout.splitlines()[0]


def qualify_c_elf_reference(reference, manifest, guest_result, diff):
    """Qualify only packaged, pinned C ELF cases; never upgrade incomplete W1.

    A guest exit=33 plus self-reported ok is not enough: require that every
    packaged case matches the *independent* Linux reference and that the
    differential reports no unexpected blocked or altered ELF. The unported
    host Python/Tokio cases must remain explicitly incomplete.
    """
    expected = {name for name, _, _ in guest.reference_elf_cases(reference)}
    listed = manifest.get("cases", [])
    if (len(expected) != A04_C_ELF_CASE_COUNT or
            len(reference.get("cases", {})) != A04_C_ELF_CASE_COUNT + A04_UNPORTED_CASE_COUNT or
            set(reference.get("binaries", {})) != set(guest.BINARY_FOR) or
            set(listed) != expected or len(listed) != len(expected)):
        return {"passed": False, "expected": len(expected), "matched": 0,
                "reason": "inconsistent or incomplete packaged case list"}
    matched = set(diff.get("matched", []))
    actual = guest_result.get("cases", {})
    identical = all(actual.get(name, {}).get("status") == "pass" and
                    actual[name].get("exit_code") == reference["cases"][name]["exit_code"] and
                    actual[name].get("facts") == reference["cases"][name]["facts"]
                    for name in expected)
    allowed_blocked = all(
        item.get("case") in reference["cases"] and item.get("case") not in expected and
        item.get("reason") in ("candidate not run", "Linux reference did not run/pass")
        for item in diff.get("blocked", []))
    passed = bool(diff.get("kernel_boot_verified") and
                  guest_result.get("guest_execution_verified") is True and
                  guest_result.get("guest_compatibility_passed") is True and
                  identical and expected == matched and
                  not diff.get("differences") and allowed_blocked)
    return {"passed": passed, "expected": len(expected),
            "matched": len(expected & matched),
            "reason": None if passed else "guest boot, ELF bytes or exact observable C ELF facts differ"}


def write_json(path, object_):
    if path.exists():
        raise ValueError("refusing to overwrite evidence: " + path.name)
    path.write_text(json.dumps(object_, indent=2, sort_keys=True) + "\n")


def execute(args):
    out = args.out_dir.resolve()
    if out.exists() or out.is_symlink():
        raise ValueError("output directory exists: refusing overwrite")
    os.umask(0o077)
    out.mkdir(mode=0o700, parents=True)
    evidence = {"schema": 1, "suite": "a04-asterinas-qemu-differential",
                "qualification": "blocked", "guest_execution_verified": False,
                "real_hepta_w1_verified": False,
                "a01_original_kernel_sha256": guest.A01_KERNEL_SHA,
                "a01_original_initramfs_sha256": guest.A01_IMAGE_SHA,
                "a01_bios_sha256": A01_SEABIOS_SHA256,
                "guest_storage": "initramfs_volatile_not_S1_block_media"}
    try:
        kernel_bytes, qemu_version = preflight(args.a01_kernel_gz, args.a01_initramfs,
                                               args.firmware, args.qemu)
        evidence["qemu_version"] = qemu_version
        evidence["qemu_executable_sha256"] = guest.sha_file(Path(args.qemu).resolve())
        kernel = out / "a01-kernel.elf"
        kernel.write_bytes(kernel_bytes)
        reference = load_fixed_reference(args.reference, args.rootfs_manifest)
        rootfs_dir, rootfs_provenance = stage_rootfs(args, out)
        evidence.update(rootfs_provenance)
        image = out / "a04-guest.cpio.gz"
        manifest_path = out / "inputs.json"
        manifest = guest.pack(args.a01_initramfs, rootfs_dir, args.rootfs_manifest,
                              reference, image, manifest_path)
        evidence["guest_initramfs_sha256"] = manifest["a04_initramfs_sha256"]
        evidence["packaged_case_count"] = manifest["case_count"]
        cmd = command_for_qemu(args.qemu, args.firmware, kernel, image)
        # Recheck just before launching; an unrelated executable silently
        # installed over this path after preflight must not qualify the guest.
        if guest.sha_file(Path(args.qemu).resolve()) != A01_QEMU_SHA256:
            raise ValueError("QEMU executable changed after preflight")
        # Full args are retained privately as no credentials are used in this profile.
        write_json(out / "invocation.json", {"qemu_args": cmd, "timeout_seconds": args.timeout,
                                              "no_network": True, "no_disks": True, "kvm": False})
        serial = out / "serial.log"
        try:
            with serial.open("wb") as log:
                result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=args.timeout, check=False)
            code = result.returncode
            evidence["qemu_timed_out"] = False
        except subprocess.TimeoutExpired:
            code = None
            evidence["qemu_timed_out"] = True
        evidence["raw_qemu_exit_code"] = code
        evidence["serial_sha256"] = guest.sha_file(serial)
        guest_result = guest.parse_serial(serial.read_text(errors="replace"), reference, manifest,
                                          qemu_exit=code, kernel_sha=guest.sha_file(kernel),
                                          image_sha=guest.sha_file(image))
        write_json(out / "guest-result.json", guest_result)
        diff = differential.compare(reference, guest_result)
        write_json(out / "differential.json", diff)
        c_elf = qualify_c_elf_reference(reference, manifest, guest_result, diff)
        passed = c_elf["passed"] and not evidence["qemu_timed_out"]
        evidence["c_elf_reference_qualification"] = c_elf
        evidence["guest_execution_verified"] = guest_result["guest_execution_verified"]
        evidence["qualification"] = "c_elf_pass" if passed else "guest_failed_or_incomplete"
        evidence["full_w1_and_all_workloads_passed"] = False
        evidence["differential_verdict"] = diff["verdict"]
        evidence["guest_counts"] = guest_result["counts"]
        return evidence
    except (OSError, ValueError, EOFError, gzip.BadGzipFile, subprocess.TimeoutExpired,
            KeyError, json.JSONDecodeError) as exc:
        evidence["qualification"] = "blocked_environment_or_input"
        evidence["blocker_class"] = type(exc).__name__
        # Path details are intentionally not echoed in the public status summary.
        evidence["blocker_reason"] = ("QEMU unavailable" if args.qemu is None else
                                       "pinned input, firmware, or QEMU preflight failed")
        return evidence
    finally:
        write_json(out / "run-status.json", evidence)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a01-kernel-gz", type=Path, required=True)
    ap.add_argument("--a01-initramfs", type=Path, required=True)
    ap.add_argument("--firmware", type=Path,
                    default=Path("/usr/share/seabios/bios-256k.bin"))
    ap.add_argument("--qemu", type=Path, default=shutil.which("qemu-system-x86_64"))
    rootfs_source = ap.add_mutually_exclusive_group(required=True)
    rootfs_source.add_argument("--rootfs", type=Path,
                               help="already-extracted pinned directory")
    rootfs_source.add_argument("--rootfs-tar", type=Path,
                               help="fixed SHA-256 rootfs.tar; extract safely inside NEW --out-dir")
    ap.add_argument("--rootfs-manifest", type=Path, required=True)
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()
    if args.timeout < 1 or args.timeout > 600:
        ap.error("timeout must be between 1 and 600 seconds")
    try:
        report = execute(args)
    except (OSError, ValueError) as exc:
        ap.exit(2, "A04 refused replay: " + str(exc) + "\n")
    print(json.dumps({k: report.get(k) for k in ("qualification", "guest_execution_verified",
                                                  "raw_qemu_exit_code", "differential_verdict")}))
    return 0 if report["qualification"] == "c_elf_pass" else 2


if __name__ == "__main__":
    sys.exit(main())
