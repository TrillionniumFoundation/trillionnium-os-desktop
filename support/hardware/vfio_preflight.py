#!/usr/bin/env python3
"""Fail-closed *read-only* VFIO/IOMMU-group inventory for disposable lab planning.

This does not open device nodes, perform VFIO ioctls, detach any PCI driver,
verify ACS/interrupt remapping, or approve device assignment. It cannot prove
that a GPU is idle. Exit codes: 2 blocked; 3 manual review; no 'ready' exit.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

BDF_RE = re.compile(r"^[0-9a-fA-F]{4,8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")
PCI_HEX_RE = re.compile(r"^0x[0-9a-fA-F]{4}$")


def text_file(path):
    try:
        return path.read_text(encoding="ascii", errors="replace").strip()[:4096]
    except (OSError, ValueError):
        return None


def link_name(path):
    if not path.is_symlink():
        return None
    try:
        return path.resolve(strict=True).name
    except OSError:
        return None


def inspect(root, bdf, expected_members, vendor="0x10de", device_id=None):
    """Observe PCI sysfs only; every potentially destructive step is out of scope."""
    if not BDF_RE.fullmatch(bdf):
        raise ValueError(f"invalid PCI BDF: {bdf!r}")
    if not PCI_HEX_RE.fullmatch(vendor):
        raise ValueError("expected vendor must be a four-hex-digit 0x identifier")
    if device_id is not None and not PCI_HEX_RE.fullmatch(device_id):
        raise ValueError("expected device ID must be a four-hex-digit 0x identifier")
    if not expected_members or any(not BDF_RE.fullmatch(member) for member in expected_members):
        raise ValueError("explicit nonempty expected IOMMU group BDF allowlist required")
    if len(set(expected_members)) != len(expected_members) or bdf not in expected_members:
        raise ValueError("duplicate group members or target BDF omitted from allowlist")

    device_path = root / "sys/bus/pci/devices" / bdf
    reasons = []
    recorded = {"bdf": bdf, "vendor_id": None, "device_id": None,
                "subsystem_vendor_id": None, "subsystem_device_id": None,
                "class": None, "driver": None, "iommu_group": None,
                "dma_mask_bits": None, "irq": None, "msi_irq_count": None,
                "reset_file_present": False, "reset_method": None}
    expected = sorted(set(expected_members))
    group_members = []
    if not device_path.is_dir():
        reasons.append("target_pci_device_missing")
    else:
        for key, leaf in (("vendor_id", "vendor"), ("device_id", "device"),
                          ("subsystem_vendor_id", "subsystem_vendor"),
                          ("subsystem_device_id", "subsystem_device"),
                          ("class", "class"), ("dma_mask_bits", "dma_mask_bits"),
                          ("irq", "irq"), ("reset_method", "reset_method")):
            recorded[key] = text_file(device_path / leaf)
        recorded["driver"] = link_name(device_path / "driver")
        recorded["iommu_group"] = link_name(device_path / "iommu_group")
        recorded["reset_file_present"] = (device_path / "reset").exists()
        msi = device_path / "msi_irqs"
        recorded["msi_irq_count"] = len(list(msi.iterdir())) if msi.is_dir() else None
        if recorded["vendor_id"] != vendor:
            reasons.append("pci_vendor_mismatch")
        if device_id is not None and recorded["device_id"] != device_id:
            reasons.append("pci_device_mismatch")
        device_class = recorded["class"]
        if not device_class or not device_class.lower().startswith(("0x03", "0x12")):
            reasons.append("not_display_or_compute_pci_class")
        group = recorded["iommu_group"]
        if group is None or not group.isdecimal():
            reasons.append("iommu_group_absent_or_unresolvable")
        else:
            group_dir = root / "sys/kernel/iommu_groups" / group
            if not group_dir.is_dir():
                reasons.append("iommu_group_directory_missing")
            else:
                members_dir = group_dir / "devices"
                if not members_dir.is_dir():
                    reasons.append("iommu_group_members_unobservable")
                else:
                    group_members = sorted(p.name for p in members_dir.iterdir())
                    if not group_members or bdf not in group_members:
                        reasons.append("iommu_group_members_inconsistent")
                    for member in group_members:
                        peer = root / "sys/bus/pci/devices" / member
                        if not peer.is_dir() or link_name(peer / "iommu_group") != group:
                            reasons.append("iommu_peer_link_inconsistent")
                            break
            if group_members != expected:
                reasons.append("unexpected_or_missing_iommu_group_member")
        # Bound third-party drivers must never be detached in an automated probe.
        if recorded["driver"] not in (None, "vfio-pci"):
            reasons.append("device_bound_to_non_vfio_driver")

    group_drivers = {}
    for member in group_members:
        peer = root / "sys/bus/pci/devices" / member
        group_drivers[member] = link_name(peer / "driver")
        if group_drivers[member] not in (None, "vfio-pci"):
            reasons.append("iommu_peer_bound_to_non_vfio_driver")
    unsafe_mode = text_file(root / "sys/module/vfio/parameters/enable_unsafe_noiommu_mode")
    if unsafe_mode is not None and unsafe_mode.lower() in ("1", "y", "yes"):
        reasons.append("unsafe_noiommu_mode_enabled")

    # Sysfs visibility cannot attest ACS, interrupt remapping, idleness, reset,
    # guest address-space isolation or host device ownership. Never return PASS.
    return {
        "schema": "a09.vfio-preflight.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Linux_sysfs_only_not_asterinas_not_assignment_authorization",
        "requested_bdf": bdf,
        "expected_vendor": vendor,
        "expected_device_id": device_id,
        "expected_group_members": expected,
        "observed": recorded,
        "observed_group_members": group_members,
        "observed_group_drivers": group_drivers,
        "unsafe_noiommu_module_parameter": unsafe_mode,
        "hard_blockers": sorted(set(reasons)),
        "unverified_required_gates": [
            "hardware_IOMMU_and_interrupt_remapping_enforced",
            "complete_isolation_group_and_ACS_effective",
            "no_active_workload_or_production_device_owner",
            "reliable_hardware_DMA_quiescence_and_reset_isolation",
            "Asterinas_derived_host_owns_PCI_group_and_DMA",
            "guest_driver_firmware_and_CUDA_runtime_verified",
        ],
        "status": "blocked" if reasons else "manual_review_required",
        "safe_to_assign": False,
        "side_effects": "none_no_device_node_open_no_ioctls_no_sysfs_writes",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bdf", required=True, help="PCI domain:bus:slot.function")
    parser.add_argument("--expected-member", action="append", required=True,
                        help="repeat for EVERY function of the same IOMMU group, including the target")
    parser.add_argument("--vendor", default="0x10de")
    parser.add_argument("--device-id", default=None, help="must come from observed isolated lab hardware")
    parser.add_argument("--root", type=Path, default=Path("/"), help=argparse.SUPPRESS)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    try:
        result = inspect(args.root, args.bdf, args.expected_member,
                         vendor=args.vendor.lower(),
                         device_id=args.device_id.lower() if args.device_id else None)
    except ValueError as exc:
        parser.error(str(exc))
    payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 2 if result["status"] == "blocked" else 3


if __name__ == "__main__":
    raise SystemExit(main())
