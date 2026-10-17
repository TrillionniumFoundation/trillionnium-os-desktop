# A09 hardware test commands, proof boundary and blockers (2026-10-16)

The authorized tool environment is a Linux execution container, NOT the user's physical server. All inventory is read-only. The CUDA probe changes no drivers/firmware/BIOS, performs no VFIO binding, reset, power/thermal tuning or production intervention.

## Safe commands, CPU/inventory only

Read PCI, firmware-version visibility, driver binding, IOMMU/interrupt information, GPU device nodes and kernel/virtualization flags without opening hardware:

    python3 support/hardware/probe.py --target-vendor nvidia --output -

CPU-only contract and fail-closed evidence tests (DO NOT count as GPU device tests):

    python3 -m unittest discover -s tests/hardware -p 'test_*.py' -v
    python3 -m py_compile support/hardware/*.py support/vmm/*.py tests/hardware/*.py

The latest rerun observed 87/87 CPU-only, evidence-gate and hardware-fixture
tests passed, 0 failures; py_compile passed; no NVIDIA PCI GPU and no CUDA
runtime, /dev/kvm or /dev/vfio/vfio in the execution container.

## Accelerator test — ONLY on an authorized, idle, isolated disposable lab GPU

This test intentionally initializes the GPU, allocates its memory, compiles device code, launches a real CUDA kernel and waits for completion. Never use a live H3/training/production card. Requires matching NVIDIA kernel driver/firmware, Linux guest CUDA Driver API library libcuda.so.1, NVRTC library libnvrtc.so, an RTX 4060 and appropriate PCI/IOMMU access. Run under an isolated process/workload supervisor and bounded process timeout; **do not reset or unbind current devices**.

    python3 tests/hardware/cuda_gemm.py --require-name 'RTX 4060' --require-bdf '0000:XX:YY.Z' --timeout-seconds 30 --output -

Replace example BDF with actual read-only PCI observation; BDF may be omitted to diagnose identity visibility, but before acceptance it must be pinned. Fixed 16x16x16 row-major FP32 GEMM; input matrices generated from small integers, exact scalar CPU reference, all 256 outputs compared exactly and with output SHA256 5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847. Uses CUDA Driver API cuInit / cuDeviceGetCount / cuDeviceGet / cuDeviceGetName / cuDeviceGetPCIBusId / cuCtxCreate_v2 / cuMemAlloc_v2 / cuMemcpyHtoD_v2 / cuLaunchKernel / cuCtxSynchronize / cuMemcpyDtoH_v2 / cuMemFree_v2 / cuModuleUnload / cuCtxDestroy_v2 and NVRTC compilation. No CPU fallback, no Ollama.

Exit 0 means GPU compute succeeded **only in the reported execution kernel**, NOT verification of Asterinas; 2 means blocked environment/identity; 1 means actual CUDA/numeric/cleanup/timeout failure. The command-line path launches an isolated worker process with `start_new_session`, bounded wait, process-group kill and reap; it never uses an in-process SIGALRM around foreign CUDA/NVRTC calls. A deadline timeout marks every stage `unknown_effect` and never claims cleanup or reset. The v2 evidence JSON records worker PID/exit/reap provenance and always sets asterinas_execution_verified=false, vmm_passthrough_verified=false, physical_device_assignment_verified=false and failure_recovery_verified=false because a guest-side application cannot attest its host or prove hardware reset safety.

## Actual evidence from execution container

- [Read-only inventory](evidence/2026-10-16-container-probe-1349z.json): this execution snapshot saw an Intel Xeon Platinum 8573C virtual CPU, bridge plus VirtIO PCI functions, and no PCI accelerator. GPU model/ID, firmware, IOMMU, VRAM/memory model, DMA queues and reset details **unknown**, not invented. The earlier `container-probe.json` snapshot is retained separately because the execution container is dynamic.
- [CUDA blocker](evidence/2026-10-16-cuda-gemm-supervised-blocked.json): process exit **2**, libcuda.so.1 unavailable, no device opened or compute dispatched; the worker was reaped by the Linux process supervisor and per-stage statuses remain `not_run`. The CPU golden SHA is still generated/verified. The earlier [pre-supervisor record](evidence/2026-10-16-cuda-gemm-blocked-v2-final.json) is retained as historical evidence of the retired in-process alarm path.
- [Kernel join blocker](evidence/2026-10-16-kernel-join-blocked.json): source gate exit **2** for the selected Intel x86_64 route; the pinned tree still lacks device/group-scoped IOMMU mapping and live hardware verification. AMD SVM and ARM EL2 remain explicit non-target observations, not Intel-route approval evidence.
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

The cross-kernel provenance reader is now present at
`support/vmm/acceptance.py`. It validates bounded regular files, hashes,
duplicate-key/non-finite JSON rejection, VM identity/nonce binding, NVIDIA
RTX 4060 identity and exact GEMM metadata. A coherent unsigned bundle exits 3
as `independent_hardware_review_required`; missing or inconsistent evidence
exits 2. It has no success exit and cannot attest a physical GPU by itself.

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

## New host-only safety regressions (not physical hardware evidence)

After the earlier 87-case suite, additional tests were authored for unbound
VFIO group endpoints, unreadable unsafe-IOMMU controls, malicious sysfs
attributes, worker-leader/PGID reuse, surviving child processes, forged
CUDA success, hostile report JSON and duplicate raw boot nonces.

Run from the **exact A09 PR HEAD**:

    python3 -m unittest discover -s tests/hardware -p 'test_*.py' -v
    python3 -O -m unittest discover -s tests/hardware -p 'test_*.py' -v
    python3 -m py_compile support/hardware/*.py support/vmm/*.py tests/hardware/*.py
    cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline --all-targets
    cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline --doc
    cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline --release

**Do not report these exact-head tests as passed while GitHub Actions remain
queued.** In this execution-tool container Python/C are present but no
authorized GPU/VFIO/KVM or local Rust toolchain was exposed.

Only in an authorized, idle, isolated and disposable Linux lab, using a real
read-only enumerated PCI BDF (never a placeholder), run the host control:

    python3 tests/hardware/cuda_gemm.py --require-name 'RTX 4060' \
      --require-bdf '0000:XX:YY.Z' --timeout-seconds 30 \
      --output gemm-lab-host.json

This is a **Linux host baseline only**, not Asterinas GPU verification.
A later Asterinas-derived host -> Linux GPU guest must repeat an identical
GEMM with trusted boot/IOMMU/IRQ/DMA and teardown logs. Current physical
compute, reset recovery and local inference remain BLOCKED/NOT RUN.

## Current isolated-lab first-compute contract (2026-10-17)

A09 host-side regression run #39000264718 passed 133 Python tests and 38
debug / 38 release / 4 doctest Rust tests on its exact pre-sync HEAD; its
validation is CPU/metadata-only. Later profile and documentation commits
require their own completed exact-HEAD checks and must not inherit PASS by
assumption. The testable minimal GPU command is **only for an already
authorized idle disposable lab**, after the operator reads the real BDF,
driver, firmware, IOMMU group and whole-device owner:

    python3 tests/hardware/cuda_gemm.py --require-name 'RTX 4060' \
      --require-bdf '<actual PCI BDF>' --timeout-seconds 30 \
      --output '<new independent Linux-host record path>'

Without a valid explicit BDF or with a lookalike RTX 4060 Ti/Laptop GPU,
the runner refuses CUDA access before loading the driver. It also rejects
wrong compute capability and never silently falls back to CPU GPU emulation.
No one should invoke this command on H3/training/prod or unqualified hardware.
This is **Linux-host** compute, not a Rust-host success.

After A01 actually boots a Linux GPU guest under the Asterinas-derived host,
the guest benchmark and the independent host boot/IOMMU/PCI/quiescence traces
feed the **review-only** acceptance command:

    python3 support/vmm/acceptance.py --host host-vmm.json \
      --host-log host.serial --guest guest-v2.json \
      --guest-log guest.serial --output review-new.json

The guest v2 record must include worker PID/kernel, device BDF, complete
GEMM stages and process-group supervision, matched against the physical
device's vendor/device IDs and boot nonce in both raw serial captures.
Even coherent unsigned records return exit 3 (independent review), never
physical GPU approval. A01/A05/A06 implementation gaps remain in
[issue #96](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/96).
