#!/usr/bin/env python3
"""Fail-closed cross-layer GPU evidence consistency gate, NOT an attestation CA.

Host reports must originate from the eventual Asterinas-derived host integration,
NOT Linux sysfs/VFIO or a guest CUDA test. The gate requires raw boot/guest logs
whose SHA256 match manifests, and exact VM/GPU identity correlation. Because
JSON/logs are not authenticated, even a consistent bundle is only eligible for
independent human/hardware review; this code NEVER returns an automatic PASS.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat

KERNEL_PIN = "c4b7ed575b7b32773475b194d2ad41fb6d03765b"
SHA = re.compile(r"^[0-9a-f]{64}$")
BDF = re.compile(r"^[0-9a-fA-F]{4,8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")
NONCE = re.compile(r"^[0-9a-f]{32,64}$")
BACKEND_VENDOR = {"intel-vmx": "GenuineIntel", "amd-svm": "AuthenticAMD", "arm-el2": "ARM"}
MAX_RAW_LOG_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


def valid_bdf(value):
    return isinstance(value, str) and BDF.fullmatch(value) is not None


def bdf_lower(value):
    return value.lower() if valid_bdf(value) else None


def read_untrusted_regular_file(path, max_bytes):
    """Single-fd, nonblocking, no-symlink bounded read on Linux.

    Refuse FIFOs/devices before any read and do not follow symlinks. A file
    changed while being read must be rejected, not used as host attestation.
    """
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise ValueError(f"evidence must be a regular file up to {max_bytes} bytes")
        payload = os.read(fd, max_bytes + 1)
        after = os.fstat(fd)
        if len(payload) > max_bytes or after.st_size != before.st_size or len(payload) != after.st_size:
            raise ValueError("evidence mutated during bounded read or exceeded size cap")
        return payload
    finally:
        os.close(fd)


def bounded_log(path):
    return read_untrusted_regular_file(path, MAX_RAW_LOG_BYTES)


def load_json(path):
    raw = read_untrusted_regular_file(path, MAX_MANIFEST_BYTES)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: must be a JSON object")
    return value

def validate(host, guest, host_log, guest_log):
    failures = []

    def check(condition, code):
        if not condition:
            failures.append(code)

    def hash_log(name, content, digest, marker):
        if not isinstance(content, bytes) or not content:
            failures.append(name + "_raw_log_missing")
            return
        check(isinstance(digest, str) and SHA.fullmatch(digest) is not None and
              hashlib.sha256(content).hexdigest() == digest, name + "_raw_log_digest_mismatch")
        check(isinstance(marker, str) and len(marker) >= 8 and
              marker.encode("utf-8") in content, name + "_boot_marker_not_in_log")

    check(host.get("schema") == "a09.asterinas-host-vmm-evidence.v1", "host_schema_invalid")
    check(guest.get("schema") == "a09.linux-guest-gpu-evidence.v1", "guest_schema_invalid")
    check(host.get("host_kernel") == "asterinas-derived", "not_asterinas_host")
    check(host.get("upstream_pin") == KERNEL_PIN, "wrong_asterinas_source_pin")
    hash_log("host", host_log, host.get("host_boot_log_sha256"), host.get("host_boot_marker"))
    hash_log("guest", guest_log, guest.get("guest_boot_log_sha256"), guest.get("guest_boot_marker"))

    vm = host.get("vm") if isinstance(host.get("vm"), dict) else {}
    guest_vm = guest.get("vm") if isinstance(guest.get("vm"), dict) else {}
    backend = vm.get("backend")
    check(isinstance(backend, str) and backend in BACKEND_VENDOR, "unknown_vmm_backend")
    check(isinstance(backend, str) and BACKEND_VENDOR.get(backend) == vm.get("host_cpu_vendor"), "vm_backend_cpu_mismatch")
    check(vm.get("hardware_virtualization_executed") is True, "vmm_hardware_not_executed")
    check(vm.get("guest_linux_booted") is True, "linux_guest_not_booted")
    check(isinstance(vm.get("vm_id"), str) and len(vm["vm_id"]) >= 8 and
          vm.get("vm_id") == guest_vm.get("vm_id"), "vm_id_mismatch")
    nonce = vm.get("boot_nonce")
    check(isinstance(nonce, str) and NONCE.fullmatch(nonce) is not None and
          nonce == guest_vm.get("boot_nonce"), "boot_nonce_mismatch")

    physical = host.get("device") if isinstance(host.get("device"), dict) else {}
    guest_dev = guest.get("device") if isinstance(guest.get("device"), dict) else {}
    check(physical.get("owner") == "asterinas-host-vmm", "device_not_owned_by_rust_host")
    check(physical.get("iommu_group_complete") is True, "iommu_group_not_proven")
    check(physical.get("iommu_dma_translation_enabled") is True, "iommu_dma_not_enforced")
    check(physical.get("interrupt_remapping_enabled") is True, "interrupts_not_isolated")
    check(physical.get("host_driver_detached_from_prod") is False, "production_driver_mutation_forbidden")
    check(physical.get("device_idle_isolated_lab") is True, "not_isolated_lab")
    check(physical.get("DMA_quiescence_on_teardown_verified") is True, "dma_reclamation_unverified")
    check(physical.get("no_device_reset_during_test") is True, "unexpected_gpu_reset")
    hv, hd, gv, gd = (physical.get("vendor_id"), physical.get("device_id"),
                      guest_dev.get("vendor_id"), guest_dev.get("device_id"))
    valid_pci_id = lambda x: isinstance(x, str) and re.fullmatch(r"0x[0-9a-fA-F]{4}", x) is not None
    check(all(valid_pci_id(x) for x in (hv, hd, gv, gd)) and
          (hv.lower(), hd.lower()) == (gv.lower(), gd.lower()), "physical_guest_pci_id_mismatch")
    check(valid_bdf(physical.get("host_bdf")), "host_pci_bdf_missing")
    check(valid_bdf(guest_dev.get("guest_bdf")), "guest_pci_bdf_missing")
    check(isinstance(guest_dev.get("nvidia_driver_version"), str) and
          bool(guest_dev["nvidia_driver_version"].strip()), "guest_gpu_driver_not_verified")
    check(isinstance(guest_dev.get("firmware_manifest_sha256"), str) and
          SHA.fullmatch(guest_dev["firmware_manifest_sha256"]) is not None,
          "guest_firmware_manifest_not_verified")

    gemm = guest.get("gemm") if isinstance(guest.get("gemm"), dict) else {}
    check(gemm.get("schema") == "a09.cuda-bounded-run.v1", "gemm_runner_schema_invalid")
    check(gemm.get("status") == "guest_cuda_reported_pass_not_asterinas_attestation" and
          gemm.get("child_exit_code") == 0, "gemm_not_successful")
    child = gemm.get("child_evidence") if isinstance(gemm.get("child_evidence"), dict) else {}
    check(child.get("schema") == "a09.cuda-gemm.v1" and
          child.get("status") == "passed_on_reported_cuda_environment" and
          child.get("actual_output_sha256") ==
          "5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847" and
          child.get("expected_output_sha256") ==
          "5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847" and
          child.get("device_access_attempted") is True and
          child.get("device_memory_allocated") is True and
          child.get("results_copied") is True and
          child.get("resources_released") is True and
          child.get("cuda_kernel_launched") is True and
          child.get("synchronization_completed") is True and
          child.get("no_cpu_fallback") is True, "invalid_cuda_gemm_result")
    cuda_dev = child.get("device") if isinstance(child.get("device"), dict) else {}
    check(bdf_lower(cuda_dev.get("device_bdf")) is not None and
          bdf_lower(cuda_dev.get("device_bdf")) == bdf_lower(guest_dev.get("guest_bdf")),
          "guest_cuda_pci_identity_mismatch")
    check(bdf_lower(gemm.get("requested_guest_bdf")) is not None and
          bdf_lower(gemm.get("requested_guest_bdf")) == bdf_lower(guest_dev.get("guest_bdf")),
          "gemm_target_bdf_mismatch")
    # Do not trust self-declared host attestation flags from guest process.
    return sorted(set(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--guest", type=Path, required=True)
    parser.add_argument("--host-log", type=Path, required=True)
    parser.add_argument("--guest-log", type=Path, required=True)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    try:
        host = load_json(args.host)
        guest = load_json(args.guest)
        failed = validate(host, guest, bounded_log(args.host_log), bounded_log(args.guest_log))
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        failed = ["missing_invalid_evidence: " + str(exc)]
    evidence = {
        "schema": "a09.cross-layer-acceptance.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "blocked" if failed else "independent_hardware_review_required",
        "failed_gates": failed,
        "asterinas_gpu_verified": False,
        "independent_attestation": False,
        "notes": "JSON and raw logs are self-reporting and can be forged; no automatic hardware pass",
    }
    raw = json.dumps(evidence, sort_keys=True, indent=2) + "\n"
    if args.output == "-":
        print(raw, end="")
    else:
        Path(args.output).write_text(raw, encoding="utf-8")
    return 2 if failed else 3


if __name__ == "__main__":
    raise SystemExit(main())
