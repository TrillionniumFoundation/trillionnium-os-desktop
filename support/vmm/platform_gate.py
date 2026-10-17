"""Read-only first-lab Intel VMX/VT-d feasibility gate for Linux inventory.

This DOES NOT certify Asterinas VM execution, IOMMU enforcement, safe PCI
assignment, or absence of running production GPU workloads. No hardware IO.
"""
from datetime import datetime, timezone
import json


def assess(inventory):
    blockers = []
    if not isinstance(inventory, dict) or inventory.get("schema") != "a09.readonly-hardware-probe.v1":
        blockers.append("invalid_inventory_schema")
        inventory = inventory if isinstance(inventory, dict) else {}
    env = inventory.get("execution_environment") or {}
    cpu = inventory.get("cpu") or {}
    iommu = inventory.get("iommu") or {}
    if not isinstance(env, dict):
        env = {}
    if not isinstance(cpu, dict):
        cpu = {}
    if not isinstance(iommu, dict):
        iommu = {}
    if env.get("kernel") != "Linux":
        blockers.append("linux_reference_host_not_identified")
    if cpu.get("vendor_id") != "GenuineIntel":
        blockers.append("intel_host_not_identified_no_vmx_backend_proof")
    if cpu.get("vmx_flag") is not True:
        blockers.append("intel_vmx_not_exposed")
    if iommu.get("dmar_table_present") is not True:
        blockers.append("intel_dmar_table_not_visible")
    if type(iommu.get("group_count_visible")) is not int or iommu["group_count_visible"] < 1:
        blockers.append("iommu_group_not_visible")
    devices = inventory.get("pci_devices")
    if not isinstance(devices, list):
        devices = []
    gpu = [d for d in devices if isinstance(d, dict)
           and d.get("vendor_id") == "0x10de" and d.get("is_accelerator_class") is True]
    if not gpu:
        blockers.append("nvidia_accelerator_not_visible")
    return {
        "schema": "a09.intel-reference-host-gate.v1",
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "priority_route": "intel-vmx-vtd-exclusive-linux-guest-gpu",
        "status": "blocked" if blockers else "manual_review_required",
        "blockers": sorted(set(blockers)),
        "visible_candidate_bdfs": [str(d.get("bdf")) for d in gpu],
        "passthrough_approved": False,
        "asterinas_gpu_verified": False,
        "still_unverified": [
            "hardware_vmx_execution_on_rust_host",
            "actual_vt_d_dma_and_interrupt_remapping",
            "acs_and_entire_iommu_group_isolation",
            "exclusive_device_owner_and_idle_production_workload",
            "guest_linux_vmm_boot_and_gpu_driver",
            "real_cuda_compute_and_device_quiescence",
        ],
    }


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True,
                        help="unmodified JSON emitted by support/hardware/probe.py")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    try:
        record = json.loads(args.inventory.read_text(encoding="utf-8"))
        result = assess(record)
    except (OSError, ValueError, UnicodeError) as exc:
        result = assess(None)
        result["blockers"].append("inventory_unreadable: " + str(exc))
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        print(payload, end="")
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 2 if result["status"] == "blocked" else 3


if __name__ == "__main__":
    raise SystemExit(main())
