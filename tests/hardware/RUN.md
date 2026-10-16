# A09 hardware test commands, proof boundary and blockers (2026-10-16)

The authorized tool environment is a Linux execution container, NOT the user's physical server. All inventory is read-only. The CUDA probe changes no drivers/firmware/BIOS, performs no VFIO binding, reset, power/thermal tuning or production intervention.

## Safe commands, CPU/inventory only

Read PCI, firmware-version visibility, driver binding, IOMMU/interrupt information, GPU device nodes and kernel/virtualization flags without opening hardware:

    python3 support/hardware/probe.py --target-vendor nvidia --output -

CPU-only contract tests (DO NOT count as GPU device tests):

    python3 -m unittest discover -s tests/hardware -p 'test_*.py' -v
    python3 -m py_compile support/hardware/probe.py tests/hardware/cuda_gemm.py tests/hardware/test_hardware.py

The latest rerun observed 8/8 CPU-only contract tests passed, 0 failures; py_compile passed; no NVIDIA PCI GPU and no CUDA runtime, /dev/kvm or /dev/vfio/vfio in the execution container.

## Accelerator test — ONLY on an authorized, idle, isolated disposable lab GPU

This test intentionally initializes the GPU, allocates its memory, compiles device code, launches a real CUDA kernel and waits for completion. Never use a live H3/training/production card. Requires matching NVIDIA kernel driver/firmware, Linux guest CUDA Driver API library libcuda.so.1, NVRTC library libnvrtc.so, an RTX 4060 and appropriate PCI/IOMMU access. Run under an isolated process/workload supervisor and bounded process timeout; **do not reset or unbind current devices**.

    python3 tests/hardware/cuda_gemm.py --require-name 'RTX 4060' --require-bdf '0000:XX:YY.Z' --timeout-seconds 30 --output -

Replace example BDF with actual read-only PCI observation; BDF may be omitted to diagnose identity visibility, but before acceptance it must be pinned. Fixed 16x16x16 row-major FP32 GEMM; input matrices generated from small integers, exact scalar CPU reference, all 256 outputs compared exactly and with output SHA256 5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847. Uses CUDA Driver API cuInit / cuDeviceGetCount / cuDeviceGet / cuDeviceGetName / cuDeviceGetPCIBusId / cuCtxCreate_v2 / cuMemAlloc_v2 / cuMemcpyHtoD_v2 / cuLaunchKernel / cuCtxSynchronize / cuMemcpyDtoH_v2 / cuMemFree_v2 / cuModuleUnload / cuCtxDestroy_v2 and NVRTC compilation. No CPU fallback, no Ollama.

Exit 0 means GPU compute succeeded **only in the reported execution kernel**, NOT verification of Asterinas; 2 means blocked environment/identity; 1 means actual CUDA/numeric/cleanup/timeout failure. On Linux the CUDA call sequence is wrapped by the bounded `--timeout-seconds` alarm; unsupported platforms or non-main threads fail closed instead of running unbounded. The v2 evidence JSON records per-stage status and process/kernel provenance, and always sets asterinas_execution_verified=false, vmm_passthrough_verified=false, physical_device_assignment_verified=false and failure_recovery_verified=false because a guest-side application cannot attest its host or prove hardware reset safety.

## Actual evidence from execution container

- [Read-only inventory](evidence/2026-10-16-container-probe-1349z.json): this execution snapshot saw an Intel Xeon Platinum 8573C virtual CPU, bridge plus VirtIO PCI functions, and no PCI accelerator. GPU model/ID, firmware, IOMMU, VRAM/memory model, DMA queues and reset details **unknown**, not invented. The earlier `container-probe.json` snapshot is retained separately because the execution container is dynamic.
- [CUDA blocker](evidence/2026-10-16-cuda-gemm-blocked-v2-final.json): process exit **2**, libcuda.so.1 unavailable, no device opened or compute dispatched; per-stage statuses remain `not_run`, with Linux process provenance recorded. The CPU golden SHA is still generated/verified.
- [Kernel join blocker](evidence/2026-10-16-kernel-join-blocked.json): source gate exit **2**; the pinned tree lacks device/group-scoped IOMMU mapping, AMD SVM and ARM EL2 evidence, and live hardware verification.
- [VFIO preflight blocker](evidence/2026-10-16-vfio-preflight-blocked.json): exit **2** for the explicit disposable-lab placeholder BDF because no target PCI function is visible.
- [Architecture decision](../../support/hardware/DECISION.md) and [VMX/SVM/EL2 VMM gates](../../support/vmm/GATES.md): design only, no new kernel guest boot.

## Kernel join and VFIO preflight gates

These commands are read-only prerequisite checks. They do not bind a driver,
open VFIO, reset a device, or authorize assignment:

    python3 support/vmm/kernel_join_gate.py --kernel-root kernel/asterinas \
      --target-arch x86_64 --output -
    python3 support/hardware/vfio_preflight.py --bdf '0000:XX:YY.Z' \
      --expected-member '0000:XX:YY.Z' --expected-driver vfio-pci --output -

The current source gate exits **2** because the pinned Asterinas IOMMU mapping
is global rather than device/group scoped. The current preflight exits **2**
because no target BDF is visible in this container. A coherent synthetic
fixture returns exit **3** (`manual_review_required`); no fixture result proves
a live device assignment, guest boot, DMA quiescence, GPU command execution,
or reset recovery.

The metadata-only Rust join model is checked independently with the three Cargo
commands documented in [VMM gates](../../support/vmm/GATES.md). Its 38 unit
tests and 4 compile-fail doctests validate state transitions and the
four-dimensional ResourceDomain admission mirror only; they do not count as
physical DMA, VMM, passthrough, or GPU-compute evidence. VM CPU is represented
as a reservation envelope, not observed scheduler usage; A06 remains the
canonical quota authority and must propagate arbitrary parent chains.

- [Rust lifecycle evidence](evidence/2026-10-16-device-lifecycle-rust.json): debug/release unit tests and compile-fail doctests passed locally; all physical execution fields remain false.

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
