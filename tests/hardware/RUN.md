# A09 hardware test commands, proof boundary and blockers (2026-10-16)

The authorized tool environment is a Linux execution container, NOT the user's physical server. All inventory is read-only. The CUDA probe changes no drivers/firmware/BIOS, performs no VFIO binding, reset, power/thermal tuning or production intervention.

## Safe commands, CPU/inventory only

Read PCI, firmware-version visibility, driver binding, IOMMU/interrupt information, GPU device nodes and kernel/virtualization flags without opening hardware:

    python3 support/hardware/probe.py --target-vendor nvidia --output -

CPU-only contract tests (DO NOT count as GPU device tests):

    python3 -m unittest discover -s tests/hardware -p 'test_*.py' -v
    python3 -m py_compile support/hardware/probe.py tests/hardware/cuda_gemm.py tests/hardware/test_hardware.py

Actual observed: 6/6 unit tests passed, 0 failures; py_compile passed; no NVIDIA PCI GPU and no CUDA runtime, /dev/kvm or /dev/vfio/vfio in container.

## Accelerator test — ONLY on an authorized, idle, isolated disposable lab GPU

This test intentionally initializes the GPU, allocates its memory, compiles device code, launches a real CUDA kernel and waits for completion. Never use a live H3/training/production card. Requires matching NVIDIA kernel driver/firmware, Linux guest CUDA Driver API library libcuda.so.1, NVRTC library libnvrtc.so, an RTX 4060 and appropriate PCI/IOMMU access. Run under an isolated process/workload supervisor and bounded process timeout; **do not reset or unbind current devices**.

    python3 tests/hardware/cuda_gemm.py --require-name 'RTX 4060' --require-bdf '0000:XX:YY.Z' --output -

Replace example BDF with actual read-only PCI observation; BDF may be omitted to diagnose identity visibility, but before acceptance it must be pinned. Fixed 16x16x16 row-major FP32 GEMM; input matrices generated from small integers, exact scalar CPU reference, all 256 outputs compared exactly and with output SHA256 5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847. Uses CUDA Driver API cuInit / cuDeviceGetCount / cuDeviceGet / cuDeviceGetName / cuDeviceGetPCIBusId / cuCtxCreate_v2 / cuMemAlloc_v2 / cuMemcpyHtoD_v2 / cuLaunchKernel / cuCtxSynchronize / cuMemcpyDtoH_v2 / cuMemFree_v2 / cuModuleUnload / cuCtxDestroy_v2 and NVRTC compilation. No CPU fallback, no Ollama.

Exit 0 means GPU compute succeeded **only in the reported execution kernel**, NOT verification of Asterinas; 2 means blocked environment/identity; 1 means actual CUDA/numeric/cleanup failure. The evidence JSON always sets asterinas_execution_verified=false, vmm_passthrough_verified=false, physical_device_assignment_verified=false and reset_or_failure_recovery_verified=false because a guest-side application cannot attest its host or prove hardware reset safety.

## Actual evidence from execution container

- [Read-only inventory](evidence/2026-10-16-container-probe.json): visible AMD EPYC 9V74 virtual CPU, seven VirtIO/bridge PCI functions and no PCI accelerator. GPU model/ID, firmware, IOMMU, VRAM/memory model, DMA queues and reset details **unknown**, not invented.
- [CUDA blocker](evidence/2026-10-16-cuda-gemm-blocked.json): process exit **2**, libcuda.so.1 unavailable, no device opened or compute dispatched. The CPU golden SHA is still generated/verified.
- [Architecture decision](../../support/hardware/DECISION.md) and [VMX/SVM/EL2 VMM gates](../../support/vmm/GATES.md): design only, no new kernel guest boot.

## Seven-stage GPU test scorecard

| Step | Status |
| --- | --- |
| 1. Enumerate real GPU, PCI ID and driver | BLOCKED: no accessible GPU |
| 2. Allocate device memory | NOT RUN |
| 3. Submit real GPU command | NOT RUN |
| 4. Copy back GPU result | NOT RUN |
| 5. Compare GPU vs CPU result | CPU reference verified only; GPU not run |
| 6. Free GPU/context resources | NOT RUN; code cleanup covered by design, not device |
| 7. Recover after fault and reset | NOT RUN; destructive work not authorized on productive GPU |

Hardware compute, real Linux guest on Asterinas, host/guest driver ownership, DMA isolation, inference, concurrent requests and recovery remain **BLOCKED/NOT TESTED**. A Linux host CUDA success in the future would be a separate baseline and never a passed new Rust-kernel test.
