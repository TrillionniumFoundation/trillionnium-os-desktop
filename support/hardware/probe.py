#!/usr/bin/env python3
"""Read-only, unprivileged PCI/GPU capability inventory. Never opens a device node."""
import argparse
import json
import os
from pathlib import Path
import platform
import stat
from datetime import datetime, timezone


MAX_SYSFS_ATTRIBUTE_BYTES = 4096
MAX_CPUINFO_BYTES = 2 * 1024 * 1024


def read(path, max_bytes=MAX_SYSFS_ATTRIBUTE_BYTES):
    """Bounded read of regular sysfs/procfs leaves, not a GPU operation.

    Refuse symlinks, FIFOs and oversized files before interpreting identity.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
                return None
            raw = os.read(fd, max_bytes + 1)
            return (raw.decode("utf-8", errors="replace").strip()
                    if len(raw) <= max_bytes else None)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None


def count_entries(path):
    try:
        if not path.is_dir():
            return None
        return sum(1 for _ in path.iterdir())
    except (OSError, ValueError):
        return None


def basename_link(path):
    try:
        return path.resolve(strict=True).name if path.is_symlink() else None
    except OSError:
        return None


def pci_devices(root):
    directory = root / "sys/bus/pci/devices"
    if not directory.is_dir():
        return []
    devices = []
    for dev in sorted(directory.iterdir()):
        if not dev.is_dir():
            continue
        kind = read(dev / "class")
        msi = dev / "msi_irqs"
        devices.append({
            "bdf": dev.name,
            "vendor_id": read(dev / "vendor"),
            "device_id": read(dev / "device"),
            "subsystem_vendor_id": read(dev / "subsystem_vendor"),
            "subsystem_device_id": read(dev / "subsystem_device"),
            "class": kind,
            "driver": basename_link(dev / "driver"),
            "iommu_group": basename_link(dev / "iommu_group"),
            "dma_mask_bits": read(dev / "dma_mask_bits"),
            "numa_node": read(dev / "numa_node"),
            "legacy_irq": read(dev / "irq"),
            "msi_irq_count": count_entries(msi),
            "reset_file_present": (dev / "reset").exists(),
            "is_accelerator_class": kind is not None and kind.lower().startswith(("0x03", "0x12")),
        })
    return devices


def snapshot(root=Path("/"), target_vendor="nvidia"):
    cpuinfo_value = read(root / "proc/cpuinfo", max_bytes=MAX_CPUINFO_BYTES)
    cpuinfo = cpuinfo_value or ""
    model = next((s.split(":", 1)[1].strip() for s in cpuinfo.splitlines()
                  if s.startswith(("model name", "Hardware")) and ":" in s), None)
    flags_line = next((s.split(":", 1)[1].split() for s in cpuinfo.splitlines()
                       if s.startswith(("flags", "Features")) and ":" in s), [])
    pci = pci_devices(root)
    vendor_id = {"nvidia": "0x10de", "amd": "0x1002"}[target_vendor]
    matches = [p for p in pci if p["vendor_id"] == vendor_id and p["is_accelerator_class"]]
    nodes = ["dev/dri/renderD128", "dev/kfd", "dev/nvidiactl", "dev/nvidia0", "dev/vfio/vfio", "dev/kvm"]
    node_status = {"/" + name: (root / name).exists() for name in nodes}
    proc_driver = read(root / "proc/driver/nvidia/version")
    modules = {name: read(root / ("sys/module/" + name + "/version"))
               for name in ("nvidia", "amdgpu", "kvm", "kvm_amd", "kvm_intel")}
    groups = root / "sys/kernel/iommu_groups"
    return {
        "schema": "a09.readonly-hardware-probe.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "execution_environment": {
            "kernel": platform.uname().system if root == Path("/") else "fixture",
            "kernel_release": platform.release() if root == Path("/") else None,
            "machine": platform.machine() if root == Path("/") else None,
            "container_marker": (root / ".dockerenv").exists(),
        },
        "cpu": {"model": model,
                "visible_processor_entries": (
                    sum(s.startswith("processor\t") for s in cpuinfo.splitlines())
                    if cpuinfo_value is not None else None),
                "cpuinfo_complete": cpuinfo_value is not None,
                "vmx_flag": ("vmx" in flags_line) if cpuinfo_value is not None else None,
                "svm_flag": ("svm" in flags_line) if cpuinfo_value is not None else None},
        "pci_devices": pci,
        "candidate": {"target_vendor": target_vendor, "matching_visible_devices": [p["bdf"] for p in matches],
                      "identified_pci_id": [{"vendor": p["vendor_id"], "device": p["device_id"]} for p in matches]},
        "device_nodes_present": node_status,
        "iommu": {"group_count_visible": count_entries(groups),
                  "dmar_table_present": (root / "sys/firmware/acpi/tables/DMAR").exists(),
                  "ivrs_table_present": (root / "sys/firmware/acpi/tables/IVRS").exists(),
                  "usable_for_passthrough": None},
        "driver_module_versions": modules,
        "nvidia_kernel_driver_version_text": proc_driver,
        "firmware_version": None,
        "gpu_memory_model": None,
        "gpu_command_queues_sync_reset": None,
        "user_compute_runtime_version": None,
        "access": "read_only_no_device_open_no_driver_change",
        "gpu_compute_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-vendor", choices=("nvidia", "amd"), default="nvidia")
    parser.add_argument("--output", default="-", help="'-' prints JSON; other paths save an inventory file")
    args = parser.parse_args()
    result = snapshot(target_vendor=args.target_vendor)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0  # successful inventory, NOT successful GPU compute


if __name__ == "__main__":
    raise SystemExit(main())
