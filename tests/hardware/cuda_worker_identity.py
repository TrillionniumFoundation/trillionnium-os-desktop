"""Parent-side validation of supervised CUDA worker identity and provenance.

This validates consistency with the parent-owned Linux process receipt and
explicit lab target, NOT CUDA hardware execution or a physical GPU attestation.
A child-generated JSON receipt must never authorize Asterinas/VM/IOMMU/reset.
"""
import os
from pathlib import Path
import platform
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/hardware"))
from pci_identity import canonical_bdf, matches_target_model

NVRTC_VERSION = re.compile(r"^[1-9][0-9]*\.[0-9]+$")
SUPERVISOR_ID = "linux_waitid_wnowait_killpg"


def validate_supervised_cuda_success(child, record, requested_name, requested_bdf):
    """Raise ValueError for a success receipt inconsistent with its OS parent.

    For the fixed A09 lab, the GPU is exactly RTX 4060, CUDA CC 8.9, with
    one real target PCI BDF; the worker must be the Linux child PID launched
    and reaped by the parent, not any unrelated Linux/GPU process.
    """
    if not isinstance(child, dict) or not isinstance(record, dict):
        raise ValueError("CUDA success identity: malformed child or supervisor receipt")
    expected_bdf = canonical_bdf(requested_bdf)
    if expected_bdf is None:
        raise ValueError("CUDA success identity: explicit valid target PCI BDF required")
    if not matches_target_model(requested_name, "RTX 4060"):
        raise ValueError("CUDA success identity: lab target must be RTX 4060")

    device = child.get("device")
    if not isinstance(device, dict):
        raise ValueError("CUDA success identity: missing CUDA device metadata")
    if not matches_target_model(device.get("device_name"), requested_name):
        raise ValueError("CUDA success identity: wrong CUDA GPU model")
    if canonical_bdf(device.get("device_bdf")) != expected_bdf:
        raise ValueError("CUDA success identity: wrong CUDA PCI BDF")
    if device.get("compute_capability") != "8.9":
        raise ValueError("CUDA success identity: wrong CUDA compute capability")
    index = device.get("device_index")
    driver = device.get("cuda_driver_api_version")
    version = device.get("nvrtc_version")
    if (type(index) is not int or not 0 <= index < 64
            or type(driver) is not int or driver < 1000
            or not isinstance(version, str) or NVRTC_VERSION.fullmatch(version) is None):
        raise ValueError("CUDA success identity: malformed CUDA driver/NVRTC metadata")

    pid = record.get("worker_pid")
    child_exit = record.get("worker_exit_code")
    if (record.get("supervisor") != SUPERVISOR_ID
            or type(pid) is not int or pid <= 0
            or type(child_exit) is not int or child_exit != 0
            or record.get("worker_reaped") is not True
            or record.get("timed_out") is not False
            or record.get("device_reset_verified") is not False
            or any(record.get(key) for key in (
                "worker_group_incomplete", "worker_group_inspection_failed",
                "worker_group_kill_error", "worker_identity_lost",
                "unreaped_worker_may_remain",
            ))):
        raise ValueError("CUDA success identity: OS supervisor did not prove clean worker exit")

    process = child.get("execution_provenance")
    if not isinstance(process, dict):
        raise ValueError("CUDA success identity: missing Linux worker provenance")
    if (type(process.get("process_id")) is not int
            or process["process_id"] != pid
            or process.get("kernel_name") != "Linux"
            or platform.system() != "Linux"
            or process.get("kernel_release") != platform.release()
            or process.get("machine") != "x86_64"
            or platform.machine() != "x86_64"
            or process.get("process_executable") != os.path.realpath(sys.executable)
            or process.get("execution_layer") != "linux_worker_cuda_driver_api"):
        raise ValueError("CUDA success identity: Linux worker identity does not match supervisor")
    if (child.get("asterinas_execution_verified") is not False
            or child.get("vmm_passthrough_verified") is not False
            or child.get("physical_device_assignment_verified") is not False
            or child.get("reset_or_failure_recovery_verified") is not False
            or child.get("failure_recovery_verified") is not False
            or process.get("asterinas_execution_verified") is not False
            or process.get("vmm_passthrough_verified") is not False
            or process.get("physical_device_assignment_verified") is not False):
        raise ValueError("CUDA success identity: child attempted to assert host or reset authority")

    stages = child.get("stages")
    if not isinstance(stages, dict) or stages.get("failure_recovery") != "not_run":
        raise ValueError("CUDA success identity: unverified recovery stage")
    return None
