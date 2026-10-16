# A09 GPU/NPU hardware decision — 2026-10-16

**Status: research + executable host-side tests, NOT an Asterinas GPU driver, VMM or successful GPU compute.** Baseline main commit 4b88b637e520f5a8f10d0e280fb9ee450abee8e4. Upstream Asterinas v0.19.0 commit c4b7ed575b7b32773475b194d2ad41fb6d03765b. Root README remains untouched at 0 bytes. Only A09-owned directories are modified.

## Actual authorized observation vs candidate

The read-only probe ran in the execution-tool Linux container, NOT on a user-provided bare-metal GPU host. Visible environment: Linux 6.18.44, x86_64, virtual CPU model AMD EPYC 9V74 80-Core Processor (3 visible /proc/cpuinfo processor entries, not a claim about physical cores). PCI enumeration exposed host bridge 8086:0d57 and six VirtIO functions: 1af4:1042, 1af4:1041, 1af4:1044, 1af4:105b, 1af4:1053, 1af4:1045. No visible PCI display or compute-accelerator class, NVIDIA or AMD GPU, /dev/dri/renderD128, /dev/kfd, /dev/nvidiactl, /dev/nvidia0, /dev/vfio/vfio or /dev/kvm. No VMX/SVM flags, visible IOMMU group or DMAR/IVRS table. Absence in a restricted container DOES NOT prove physical host absence.

The real GPU's PCI vendor/device/subsystem IDs and BDF, GPU/NPU ID, loaded GSP/other firmware, driver version, IOMMU/interrupt remapping, VRAM/UMA topology, DMA reachability, command submission, queue count, synchronization/fences, reset availability and safety, and CUDA runtime version remain UNKNOWN/UNOBSERVED. They MUST NOT be fabricated from marketing specifications or another machine. See ../../tests/hardware/evidence/2026-10-16-container-probe.json.

**Single chosen lab candidate:** NVIDIA GeForce RTX 4060, a discrete Ada GPU; NVIDIA's [compute-capability table](https://developer.nvidia.com/cuda/gpus) lists 8.9. This identifies a future target model, NOT installed or accessible hardware. Its actual PCI ID must be read from the isolated lab card, not guessed. No NPU was observed, so NPU hardware and its firmware/runtime are separate future research.

The guest driver dependencies to verify on the SAME isolated GPU are the NVIDIA Linux kernel GPU driver and supporting modules, matching userland libcuda.so.1, firmware/GSP actually loaded as applicable, CUDA NVRTC/libnvrtc.so and CUDA Driver API, Linux guest PCI/DMA/MSI support, and the license/redistribution terms. Versions, exact firmware files and hardware reset behavior are deliberately null in the candidate profile, pending real output. Merely finding a software Mesa GL renderer is not evidence of CUDA compute.

## Route trade-off: commit to one path

| Boundary | A. native Rust GPU driver | B. bounded driver service domain | **C. Linux driver VM, exclusive PCI passthrough (priority)** |
| --- | --- | --- | --- |
| Rust host interface | Native PCI/BAR driver, memory manager, scheduler and queue/fence API | RPC + shared-memory MemoryObject and device-bound IOMMU domains | VMM + PCI/IOMMU group ownership, mapped guest MemoryObjects, ResourceDomain lease |
| Drivers/firmware | Need supported vendor protocol and firmware stack, major engineering burden | Must still obtain an actual low-level GPU driver; proprietary Linux kernel components do not simply execute as userspace | Existing NVIDIA driver, firmware and CUDA/NVRTC **inside guest Linux** |
| Memory/DMA | Native VRAM/GTT, mapped pages and IOVA logic | RPC copies or explicitly pinned shared buffers; enforce IOMMU per service | Host charges/pins guest RAM; maps ONLY permitted IOVAs; guest driver controls GPU VRAM; no assumed zero-copy |
| IOMMU/interrupts | Native fault tracking and MSI | Dedicated group/isolation mandatory | Entire isolatable group and interrupt remapping enforced by Rust host; unsafe groups rejected |
| Command queue/sync | Native opaque command parser, fences and reset | Service driver queues, IPC completion and generation | Guest NVIDIA hardware queues, CUDA streams/events and guest fences; host owns whole device, not opaque per-CUDA-work scheduling |
| Fault/reset | Native watchdog, stop DMA, generation and reset recovery | Service death is not necessarily DMA quiescence | VM fencing; stop vCPUs, verify GPU DMA idle, invalidate IOTLB, reset only in qualified isolated lab, quarantine otherwise |
| Cost/overhead | Very high driver/firmware maintenance; potentially low overhead **unmeasured** | Service RPC, copies/mappings/context switching **unmeasured** | VMM, exits, pinned memory/IOMMU bookkeeping; guest compute executes on physical GPU if proven, overhead **unmeasured** |
| Actual outcome | Not implemented | Not implemented | Chosen engineering plan, **not implemented or run** |

**Why C:** For RTX 4060, mature Linux guest GPU drivers and CUDA tools offer the strongest credible local compute path without reimplementing NVIDIA's stack in Rust. This is NOT a native Rust GPU driver and it is NOT a Linux host serving as the claimed new kernel. Do not build parallel long-lived A and B solutions. Linux-host CUDA GEMM later can provide a control baseline, never a new-kernel GPU pass.

## Minimum real compute: executable but currently blocked

Tests under ../../tests/hardware/cuda_gemm.py compile CUDA kernel GEMM16 using NVRTC and the runtime-selected GPU compute capability (candidate expectation CC 8.9). Inputs: fixed 16x16 FP32 integer-valued matrices. Scalar CPU reference computes 256 deterministic exact values and output SHA256 5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847. A real pass REQUIRES actual CUDA device enumeration and PCI BDF, three cuMemAlloc_v2 device buffers, HtoD transfers, cuLaunchKernel, cuCtxSynchronize, DtoH, exact 256-value comparison and successful cuMemFree_v2/module/context cleanup. No software CPU GPU fallback. The tested container returned **exit code 2, blocked: libcuda.so.1 unavailable**; GPU allocation, submission, comparison and recovery were NOT RUN. Six CPU-only unit tests passed. See ../../tests/hardware/RUN.md and immutable JSON evidence, including exact tool environment. CUDA pass alone also does not prove inference, VM passthrough or device-reset recovery.

## A01/A05/A06 kernel join: integrate existing owners, no new signer

These are PROPOSED interfaces for A00 coordination, not shipped Rust ABI and not kernel permissions implemented in this PR.

| Object | Canonical owner | Proposed state and interface requirement |
| --- | --- | --- |
| **DeviceHandle** | A01 PCI/OSTD object + A05 process CapSpace + existing HOS grant check | immutable BDF, complete IOMMU group and IRQ route; exclusive ResourceDomain/VM owner; device_generation, Unassigned/Fenced/Assigned/Quiescing/Quarantined; reject stale handles |
| **MemoryObject** | A01 existing physical frames + A06 single memory-domain accounting | stable pinned frames, alignment, direction, CPU aliases, mapped IOVA and mapping generation, DMA cache policy; unpin only after verified device quiet and IOTLB/TLB invalidation |
| **Buffer** | Slice of MemoryObject charged to ResourceDomain | overflow-checked offset/length, direction, CPU-owned -> prepared -> device-owned -> quiesced -> synchronized-for-CPU -> releasable |
| **Queue** | DeviceHandle generation and owning ResourceDomain; guest NVIDIA owns hardware specifics | queue ID, admission limits, outstanding count, state and associated interrupt; host does not falsely parse opaque CUDA commands |
| **Completion** | Kernel-validated queue event and current generation; never trusted guest assertion alone | sequence, fence, device/queue generation, success/fault/unknown-effect, memory ownership barrier; old-generation completions cannot release new buffers |
| **ResourceDomain** | A06 existing canonical budget/enforcement object | VM CPU, RAM, pinned DMA bytes, device count/lease quotas, parent constraints; cannot claim per-kernel GPU utilization throttling without GPU-side measurement |

**Security and DMA order:** HOS2 grant/identity checked at canonical admission before resource reservation; reserve and pin; check exclusive IOMMU group and DMA direction; map IOVA and quiesce writable CPU aliases or use protected staging; issue device ownership; accept bounded IRQ, perform wait/validation outside spinlock; synchronize DMA/cache, verify current generation and completion, then reclaim. IRQ and language atomics do not replace DMA/MMIO barriers. Cancel/revoke means no *new* admission; stop and drain DMA before physical unmap. If quiescence or reset cannot be proven, quarantine rather than reuse pages or say effect failed. Stop/kill cannot be silently transformed into no-result/no-effect. This does NOT give the model unrestricted MMIO or establish a second GPU capability authority.

Proposed compute provenance after eventual success: **host kernel Asterinas-derived Rust**, **VM Linux guest kernel**, **guest process Python GEMM**, **physical RTX 4060**, **guest NVIDIA driver**, **guest NVRTC/CUDA runtime**. No part of that combination has yet been demonstrated here. A05 must bind VM/device ownership to final process identity and revocation; A06 must enforce parent ResourceDomain budgets and recovery executor reserve; A01 must integrate real frames, PCI/IOMMU and correct VMX/SVM backend. Hepta calls existing HOS2/ResourceDomain surfaces, not direct PCI registers.

## One gated implementation plan

1. A01 provides reproducible fixed-source Asterinas boot and source review for IOMMU/VM, A05/A06 agree on shared device owner and ResourceDomain interfaces.
2. Read-only enumerate an AUTHORIZED, IDLE, ISOLATED RTX 4060 lab card: CPU/motherboard/firmware, PCI/subsystem IDs/BDF/functions, actual NVIDIA driver and loaded firmware, page/dma masks, IOMMU group, remapping/interrupts, memory model, reset capability, CUDA version. **STOP** if device belongs to H3/training/prod.
3. Run CUDA GEMM solely on a separate disposable Linux lab GPU as a baseline. Label kernel Linux, never Asterinas.
4. Implement a minimal but actual VMM with vCPU, VM memory, virtual interrupts, device model, boot and lifecycle, correct Intel VMX vs AMD SVM; AMD SVM is not evidenced in pinned upstream. See ../vmm/GATES.md.
5. Validate group isolation, interrupt remapping, bounded DMA and reset strategy on disposable GPU; then boot a Linux guest **on the Asterinas-derived host** with exclusive GPU passthrough. Repeat identical GEMM; persist host+guest logs and numerical/cleanup facts.
6. Isolated negative tests: wrong PCI identity, unsupported IOMMU group, stale queue generation, canceled/failed kernel, VM death, IOTLB cleanup and qualified reset recovery; measure performance vs Linux host baseline.
7. ONLY AFTER compute and safe reclamation: evaluate CUDA inference/model load, quantization correctness, concurrency, cancellation, fence sharing and allocator/resource quotas; Vulkan/ROCm/NPU are alternatives for later assessment, not parallel codepaths here.

**References:** [fixed Asterinas VMX context](https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/ostd/src/arch/x86/vm/mod.rs); [OSTD example](https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/osdk/tests/examples_in_book/write_a_hypervisor_in_100_lines_templates/lib.rs); [VFIO/IOMMU groups](https://docs.kernel.org/driver-api/vfio.html); [Linux DMA](https://docs.kernel.org/core-api/dma-api-howto.html); [CUDA launch](https://docs.nvidia.com/cuda/cuda-driver-api/cuda_driver_api/group__CUDA__EXEC.html).
