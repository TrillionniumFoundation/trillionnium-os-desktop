#!/usr/bin/env python3
"""Fail-closed, read-only VFIO/IOMMU-group preflight.

The probe reads PCI sysfs, IOMMU-group membership and read-only module
parameters. It never opens a device node, performs a VFIO ioctl, writes a
bind/unbind file, invokes reset, or approves assignment. A coherent sysfs
snapshot therefore ends in ``manual_review_required`` rather than PASS.

Exit codes are 2 for blocked input/observation and 3 for a coherent snapshot
that still needs an authorized hardware review. No exit code means that a GPU
is idle, that ACS/interrupt remapping is effective, or that reset is safe.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterable


SCHEMA = "a09.vfio-preflight.v1"
BDF_RE = re.compile(r"^[0-9a-fA-F]{4,8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")
PCI_HEX_RE = re.compile(r"^0x[0-9a-fA-F]{4}$")
DEFAULT_VENDOR = "0x10de"
DEFAULT_DRIVER = "vfio-pci"
MAX_SYSFS_TEXT_BYTES = 4096


def text_file(path: Path) -> str | None:
    """Read one sysfs page, without following the final symlink or blocking FIFO.

    Path.read_text() reads the whole file before slicing and can hang on
    special nodes. A sysfs attribute presents a regular pseudo-file.
    """
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SYSFS_TEXT_BYTES:
                return None
            raw = os.read(fd, MAX_SYSFS_TEXT_BYTES + 1)
            return (raw.decode("ascii", errors="replace").strip()
                    if len(raw) <= MAX_SYSFS_TEXT_BYTES else None)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None


def path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


def link_name(path: Path) -> str | None:
    try:
        if not path.is_symlink():
            return None
        return path.resolve(strict=True).name
    except (OSError, ValueError):
        return None


def list_names(path: Path) -> tuple[list[str], str | None]:
    try:
        return sorted(entry.name for entry in path.iterdir()), None
    except (OSError, ValueError) as exc:
        return [], f"{type(exc).__name__}: {exc}"


def _base_result(root: Path, bdf: str | None,
                 expected_members: Iterable[str] | None,
                 vendor: str, device_id: str | None) -> dict[str, Any]:
    expected = sorted({str(member).lower() for member in (expected_members or ())})
    return {
        "schema": SCHEMA,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Linux_sysfs_only_not_asterinas_not_assignment_authorization",
        "status": "blocked",
        "requested_bdf": bdf.lower() if isinstance(bdf, str) else bdf,
        "expected_vendor": vendor.lower(),
        "expected_device_id": device_id.lower() if device_id else None,
        "expected_group_members": expected,
        "observed": {
            "bdf": bdf.lower() if isinstance(bdf, str) else bdf,
            "vendor_id": None,
            "device_id": None,
            "subsystem_vendor_id": None,
            "subsystem_device_id": None,
            "class": None,
            "driver": None,
            "iommu_group": None,
            "dma_mask_bits": None,
            "irq": None,
            "msi_irq_count": None,
            "reset_file_present": False,
            "reset_method": None,
        },
        "observed_group_members": [],
        "iommu_group_members": [],
        "observed_group_drivers": {},
        "iommu": {
            "group_visible": False,
            "group_complete": False,
            "dmar_table_present": path_exists(root / "sys/firmware/acpi/tables/DMAR"),
            "ivrs_table_present": path_exists(root / "sys/firmware/acpi/tables/IVRS"),
            "interrupt_remapping": None,
            "evidence": False,
        },
        "driver_binding": {
            "expected": DEFAULT_DRIVER,
            "target": None,
            "target_bound_to_expected": False,
            "all_group_bound_to_expected": False,
        },
        "reset": {
            "target_file_present": False,
            "group_files_present": {},
            "all_group_files_present": False,
            "qualified": False,
            "invoked": False,
        },
        "unsafe_noiommu_module_parameter": text_file(
            root / "sys/module/vfio/parameters/enable_unsafe_noiommu_mode"
        ),
        "unsafe_interrupts_module_parameter": text_file(
            root / "sys/module/vfio_iommu_type1/parameters/allow_unsafe_interrupts"
        ),
        "hard_blockers": [],
        "blockers": [],
        "unverified_required_gates": [
            "hardware_IOMMU_and_interrupt_remapping_enforced",
            "complete_isolation_group_and_ACS_effective",
            "no_active_workload_or_production_device_owner",
            "reliable_hardware_DMA_quiescence_and_reset_isolation",
            "Asterinas_derived_host_owns_PCI_group_and_DMA",
            "guest_driver_firmware_and_CUDA_runtime_verified",
        ],
        "device_opened": False,
        "assignment_verified": False,
        "safe_to_assign": False,
        "writes_performed": False,
        "reset_performed": False,
        "side_effects": "none_no_device_node_open_no_ioctls_no_sysfs_writes",
    }


def _block(result: dict[str, Any], *reasons: str) -> dict[str, Any]:
    result["hard_blockers"] = sorted(set(result["hard_blockers"] + list(reasons)))
    result["blockers"] = list(result["hard_blockers"])
    result["status"] = "blocked"
    return result


def preflight(root: Path = Path("/"), bdf: str | None = None,
              expected_members: Iterable[str] | None = None,
              vendor: str = DEFAULT_VENDOR,
              device_id: str | None = None,
              expected_driver: str = DEFAULT_DRIVER) -> dict[str, Any]:
    """Inspect one exact BDF and an explicit complete group allowlist."""
    result = _base_result(root, bdf, expected_members, vendor, device_id)
    result["driver_binding"]["expected"] = expected_driver
    if expected_driver != DEFAULT_DRIVER:
        return _block(result, "non_vfio_expected_driver_forbidden")
    if not bdf:
        return _block(result, "target_bdf_required")
    if not BDF_RE.fullmatch(bdf):
        return _block(result, "invalid_target_bdf")
    if not PCI_HEX_RE.fullmatch(vendor):
        return _block(result, "invalid_expected_vendor")
    if device_id is not None and not PCI_HEX_RE.fullmatch(device_id):
        return _block(result, "invalid_expected_device_id")
    if not expected_members:
        return _block(result, "explicit_nonempty_expected_iommu_group_allowlist_required")
    bdf = bdf.lower()
    members = [str(member).lower() for member in expected_members]
    if any(not BDF_RE.fullmatch(member) for member in members):
        return _block(result, "invalid_expected_iommu_group_member")
    if len(set(members)) != len(members) or bdf not in members:
        return _block(result, "duplicate_group_members_or_target_omitted_from_allowlist")
    vendor = vendor.lower()
    device_id = device_id.lower() if device_id else None
    result["requested_bdf"] = bdf
    result["expected_vendor"] = vendor
    result["expected_device_id"] = device_id
    result["expected_group_members"] = sorted(members)
    result["observed"]["bdf"] = bdf

    device = root / "sys/bus/pci/devices" / bdf
    if not device.is_dir():
        return _block(result, "target_pci_device_missing")
    fields = (
        ("vendor_id", "vendor"), ("device_id", "device"),
        ("subsystem_vendor_id", "subsystem_vendor"),
        ("subsystem_device_id", "subsystem_device"),
        ("class", "class"), ("dma_mask_bits", "dma_mask_bits"),
        ("irq", "irq"), ("reset_method", "reset_method"),
    )
    for key, leaf in fields:
        result["observed"][key] = text_file(device / leaf)
    result["observed"]["driver"] = link_name(device / "driver")
    result["observed"]["iommu_group"] = link_name(device / "iommu_group")
    result["observed"]["reset_file_present"] = path_exists(device / "reset")
    msi = device / "msi_irqs"
    if msi.is_dir():
        names, error = list_names(msi)
        if error:
            _block(result, "msi_irq_enumeration_unobservable")
        else:
            result["observed"]["msi_irq_count"] = len(names)
    if result["observed"]["driver"] is None and (device / "driver").is_symlink():
        _block(result, "device_driver_link_unresolvable")
    if result["observed"]["vendor_id"] != vendor:
        _block(result, "pci_vendor_mismatch")
    if device_id is not None and result["observed"]["device_id"] != device_id:
        _block(result, "pci_device_mismatch")
    if not (result["observed"]["class"] or "").lower().startswith(("0x03", "0x12")):
        _block(result, "not_display_or_compute_pci_class")
    if result["observed"]["driver"] not in (None, expected_driver):
        _block(result, "device_bound_to_non_vfio_driver")
    if result["observed"]["driver"] is None:
        _block(result, "target_gpu_not_bound_to_vfio")

    group_id = result["observed"]["iommu_group"]
    groups_root = root / "sys/kernel/iommu_groups"
    if group_id is None or not group_id.isdecimal():
        return _block(result, "iommu_group_absent_or_unresolvable")
    group_dir = groups_root / group_id
    if not group_dir.is_dir():
        return _block(result, "iommu_group_directory_missing")
    members_dir = group_dir / "devices"
    if not members_dir.is_dir():
        return _block(result, "iommu_group_members_unobservable")
    group_members, error = list_names(members_dir)
    if error:
        return _block(result, "iommu_group_members_unobservable")
    result["observed_group_members"] = group_members
    result["iommu_group_members"] = group_members
    result["iommu"]["group_visible"] = True
    result["iommu"]["evidence"] = True
    if not group_members or bdf not in group_members:
        _block(result, "iommu_group_members_inconsistent")
    if group_members != sorted(members):
        _block(result, "unexpected_or_missing_iommu_group_member")
    group_complete = bool(group_members and group_members == sorted(members))
    for member in group_members:
        if not BDF_RE.fullmatch(member):
            _block(result, "invalid_observed_iommu_group_member")
            continue
        peer = root / "sys/bus/pci/devices" / member
        if not peer.is_dir() or link_name(peer / "iommu_group") != group_id:
            _block(result, "iommu_peer_link_inconsistent")
            group_complete = False
        peer_driver_link = peer / "driver"
        peer_driver = link_name(peer_driver_link)
        result["observed_group_drivers"][member] = peer_driver
        result["reset"]["group_files_present"][member] = path_exists(peer / "reset")
        if peer_driver_link.is_symlink() and peer_driver is None:
            _block(result, "iommu_peer_driver_link_unresolvable")
        if peer_driver not in (None, expected_driver):
            _block(result, "iommu_peer_bound_to_non_vfio_driver")
        # An unbound PCI bridge can be part of a viable VFIO group; unlike
        # compute or audio endpoints, vfio-pci cannot claim the bridge.
        peer_class = (text_file(peer / "class") or "").lower()
        if peer_driver is None and not peer_class.startswith("0x06"):
            _block(result, "iommu_peer_unbound_non_bridge")
    result["iommu"]["group_complete"] = group_complete and not any(
        reason in result["hard_blockers"] for reason in (
            "iommu_group_members_inconsistent", "unexpected_or_missing_iommu_group_member",
            "iommu_peer_link_inconsistent", "invalid_observed_iommu_group_member",
        )
    )
    target_driver = result["observed"]["driver"]
    result["driver_binding"]["target"] = target_driver
    result["driver_binding"]["target_bound_to_expected"] = target_driver == expected_driver
    result["driver_binding"]["all_group_bound_to_expected"] = bool(group_members) and all(
        driver == expected_driver for driver in result["observed_group_drivers"].values()
    )
    result["reset"]["all_group_files_present"] = bool(group_members) and all(
        result["reset"]["group_files_present"].values()
    )
    unsafe_mode = result["unsafe_noiommu_module_parameter"]
    unsafe_mode_path = root / "sys/module/vfio/parameters/enable_unsafe_noiommu_mode"
    if (unsafe_mode_path.exists() or unsafe_mode_path.is_symlink()) and unsafe_mode is None:
        # Present-but-unreadable or hostile attributes cannot attest a safe
        # VFIO setting. Missing remains unobserved, never approval.
        _block(result, "unsafe_noiommu_mode_unobservable")
    normalized_unsafe_mode = (unsafe_mode or "").lower().replace("\\n", "").strip()
    if normalized_unsafe_mode in ("1", "y", "yes"):
        _block(result, "unsafe_noiommu_mode_enabled")
    unsafe_interrupts = result["unsafe_interrupts_module_parameter"]
    unsafe_interrupts_path = root / "sys/module/vfio_iommu_type1/parameters/allow_unsafe_interrupts"
    if (unsafe_interrupts_path.exists() or unsafe_interrupts_path.is_symlink()) and unsafe_interrupts is None:
        _block(result, "unsafe_interrupt_remapping_setting_unobservable")
    normalized_unsafe_interrupts = (unsafe_interrupts or "").lower().replace("\\n", "").strip()
    if normalized_unsafe_interrupts in ("1", "y", "yes"):
        _block(result, "unsafe_interrupt_remapping_override_enabled")
    if result["hard_blockers"]:
        result["blockers"] = sorted(set(result["hard_blockers"]))
        result["status"] = "blocked"
    else:
        result["status"] = "manual_review_required"
    return result


def inspect(root: Path, bdf: str, expected_members: Iterable[str],
            vendor: str = DEFAULT_VENDOR, device_id: str | None = None) -> dict[str, Any]:
    """Compatibility alias for callers using the earlier inspect API."""
    if not isinstance(bdf, str) or not BDF_RE.fullmatch(bdf):
        raise ValueError(f"invalid PCI BDF: {bdf!r}")
    if not expected_members:
        raise ValueError("explicit nonempty expected IOMMU group BDF allowlist required")
    normalized = [str(member).lower() for member in expected_members]
    if any(not BDF_RE.fullmatch(member) for member in normalized):
        raise ValueError("invalid expected IOMMU group BDF")
    if len(set(normalized)) != len(normalized) or bdf.lower() not in normalized:
        raise ValueError("duplicate group members or target BDF omitted from allowlist")
    return preflight(root, bdf, expected_members, vendor=vendor, device_id=device_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bdf", default=None, help="exact PCI domain:bus:slot.function")
    parser.add_argument("--expected-member", action="append", default=None,
                        help="repeat for every function in the same IOMMU group")
    parser.add_argument("--vendor", default=DEFAULT_VENDOR)
    parser.add_argument("--device-id", default=None)
    parser.add_argument("--expected-driver", default=DEFAULT_DRIVER, help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path, default=Path("/"), help=argparse.SUPPRESS)
    parser.add_argument("--output", default="-", help="'-' prints JSON; other paths save JSON")
    args = parser.parse_args(argv)
    result = preflight(args.root, args.bdf, args.expected_member,
                       vendor=args.vendor, device_id=args.device_id,
                       expected_driver=args.expected_driver)
    payload = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        try:
            Path(args.output).write_text(payload, encoding="utf-8")
        except OSError:
            return 1
    return 2 if result["status"] == "blocked" else 3


if __name__ == "__main__":
    raise SystemExit(main())
