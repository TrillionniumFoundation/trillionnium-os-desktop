#!/usr/bin/env python3
"""Read-only, fail-closed A09/A01 kernel GPU passthrough source audit.

This is a *static* prerequisite check, never IOMMU, VMM or GPU attestation.
It does not touch a device node, sysfs, BIOS, driver or running service.
"""
import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
import re

SOURCE_PATHS = {
    "iommu_dma": "kernel/asterinas/ostd/src/arch/x86/iommu/dma_remapping/mod.rs",
    "iommu_irq": "kernel/asterinas/ostd/src/arch/x86/iommu/interrupt_remapping/mod.rs",
    "guest_mode": "kernel/asterinas/ostd/src/vm/guest_mode.rs",
    "dma_stream": "kernel/asterinas/ostd/src/mm/dma/dma_stream.rs",
    "resource_domain": "libs/os-control/src/lib.rs",
}
MAX_SOURCE_BYTES = 512 * 1024


def audit(root):
    root = Path(root)
    source = {}
    sha256 = {}
    blocked = []
    for name, relpath in SOURCE_PATHS.items():
        path = root / relpath
        try:
            # The Git checkout is trusted as a code source, not as a hardware
            # observation. Bounds prevent unexpectedly huge source reads.
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            fd = os.open(path, flags)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_BYTES:
                    raise ValueError("missing, non-regular or oversized source")
                raw = os.read(fd, MAX_SOURCE_BYTES + 1)
                after = os.fstat(fd)
                identity = lambda v: (v.st_dev, v.st_ino, v.st_size,
                                      v.st_mtime_ns, v.st_ctime_ns)
                if len(raw) > MAX_SOURCE_BYTES or len(raw) != after.st_size or identity(before) != identity(after):
                    raise ValueError("source changed during bounded read")
            finally:
                os.close(fd)
            source[name] = raw.decode("utf-8")
            sha256[name] = hashlib.sha256(raw).hexdigest()
        except (OSError, UnicodeError, ValueError):
            source[name] = ""
            sha256[name] = None
            blocked.append("required_source_missing_or_unreadable:" + name)

    iommu = source["iommu_dma"]
    shared = ("page table of all devices is the same" in iommu.lower()
              or "PciDeviceLocation::zero()" in iommu)
    # Comment or string text is not an actual callable Rust interface.
    # This remains a conservative source heuristic and cannot approve DMA.
    code_only = re.sub(r"/\*[\s\S]*?\*/", " ", iommu)
    code_only = re.sub(r"//[^\n]*", " ", code_only)
    code_only = re.sub(r'"(?:\\.|[^"\\])*"', " ", code_only)
    scoped_map = bool(re.search(
        r"(?:pub\([^)]*\)\s+)?(?:unsafe\s+)?fn\s+map\s*\([^)]*\bdevice\s*:",
        code_only, re.S))
    scoped_unmap = bool(re.search(
        r"(?:pub\([^)]*\)\s+)?fn\s+unmap\s*\([^)]*\bdevice\s*:",
        code_only, re.S))
    if shared:
        blocked.append("iommu_shared_device_page_table_detected")
    if iommu and not (scoped_map and scoped_unmap):
        blocked.append("iommu_device_scoped_map_unmap_not_found")

    vmx = "pub struct GuestMode" in source["guest_mode"]
    dma_stream = "pub struct DmaStream" in source["dma_stream"]
    resource_domain = "pub struct ResourceDomain" in source["resource_domain"]
    if not vmx:
        blocked.append("ostd_guest_mode_primitive_missing")
    if not dma_stream:
        blocked.append("ostd_dma_stream_primitive_missing")
    if not resource_domain:
        blocked.append("canonical_resource_domain_source_missing")
    # These are not detectable as hardware facts via Rust source inspection.
    # Even a future per-device domain implementation needs independent tests.
    blocked.append("per_iommu_group_dma_irq_isolation_not_hardware_verified")
    blocked.append("linux_guest_gpu_passthrough_not_hardware_verified")
    blocked.append("quiescence_and_dma_pin_accounting_not_hardware_verified")

    return {
        "schema": "a09.asterinas-gpu-kernel-join-source-gate.v1",
        "status": "blocked",
        "passthrough_approved": False,
        "asterinas_gpu_verified": False,
        "scope": "static_source_inspection_only",
        "required_paths": SOURCE_PATHS,
        "source_sha256": sha256,
        "observations": {
            "shared_iommu_page_table_source_pattern": shared,
            "device_scoped_map_signature_visible": scoped_map,
            "device_scoped_unmap_signature_visible": scoped_unmap,
            "ostd_guest_mode_primitive_visible": vmx,
            "ostd_dma_stream_primitive_visible": dma_stream,
            "host_resource_domain_type_visible": resource_domain,
        },
        "hard_blockers": sorted(set(blocked)),
        "next_owner_actions": {
            "A01": "Device/group IOMMU domains + IRQ remapping, TLB/IOTLB and DMA quiescence + real VMM guest boot",
            "A05": "Canonical CapSpace/device/queue exclusive ownership and revocation",
            "A06": "Pinned DMA RAM/queue/VM memory charged to canonical ResourceDomain",
            "A00": "Independently review A01/A05/A06 interfaces and isolated physical GPU evidence",
        },
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--output", default="-")
    args = p.parse_args()
    payload = json.dumps(audit(args.repo_root), sort_keys=True, indent=2) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 2  # No source-only or host-only route can certify real passthrough.


if __name__ == "__main__":
    raise SystemExit(main())
