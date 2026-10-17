# A09 GPU/NPU hardware decision — 2026-10-16

**Status: research + executable host-side tests, NOT an Asterinas GPU driver, VMM or successful GPU compute.** Original A09 development base `bc294f75bfb8c03d9963f5a12ea23b9589779d96`; branch subsequently merged current main without overwriting files owned by other agents. Upstream Asterinas v0.19.0 commit c4b7ed575b7b32773475b194d2ad41fb6d03765b. Root README remains untouched at 0 bytes. Only A09-owned directories are modified.

## Actual authorized observation vs candidate

The read-only probe ran in the execution-tool Linux container, NOT on a user-provided bare-metal GPU host. Visible environment: Linux 6.18.44, x86_64, virtual CPU model AMD EPYC 9V74 80-Core Processor (3 visible /proc/cpuinfo processor entries, not a claim about physical cores). PCI enumeration exposed host bridge 8086:0d57 and six VirtIO functions: 1af4:1042, 1af4:1041, 1af4:1044, 1af4:105b, 1af4:1053, 1af4:1045. No visible PCI display or compute-accelerator class, NVIDIA or AMD GPU, /dev/dri/renderD128, /dev/kfd, /dev/nvidiactl, /dev/nvidia0, /dev/vfio/vfio or /dev/kvm. No VMX/SVM flags, visible IOMMU group or DMAR/IVRS table. Absence in a restricted container DOES NOT prove physical host absence.

The real GPU's PCI vendor/device/subsystem IDs and BDF, GPU/NPU ID, loaded GSP/other firmware, driver version, IOMMU/interrupt remapping, VRAM/UMA topology, DMA reachability, command submission, queue count, synchronization/fences, reset availability and safety, and CUDA runtime version remain UNKNOWN/UNOBSERVED. They MUST NOT be fabricated from marketing specifications or another machine. See ../../tests/hardware/evidence/2026-10-16-container-probe.json.

A later read-only execution snapshot on the same dynamic tool environment is recorded separately in `2026-10-16-container-probe-1349z.json`: Intel Xeon Platinum 8573C, four visible processor entries, bridge plus VirtIO PCI functions, and the same absence of an accelerator, CUDA, VFIO, KVM and visible IOMMU groups. The differing CPU snapshot is evidence that these observations are time-scoped; it is not a claim about the user's physical host.

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

Tests under ../../tests/hardware/cuda_gemm.py compile CUDA kernel GEMM16 using NVRTC and the runtime-selected GPU compute capability (candidate expectation CC 8.9). Inputs: fixed 16x16 FP32 integer-valued matrices. Scalar CPU reference computes 256 deterministic exact values and output SHA256 5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847. A real pass REQUIRES actual CUDA device enumeration and PCI BDF, three cuMemAlloc_v2 device buffers, HtoD transfers, cuLaunchKernel, cuCtxSynchronize, DtoH, exact 256-value comparison and successful cuMemFree_v2/module/context cleanup. No software CPU GPU fallback. The latest tested container returned **exit code 2, blocked: libcuda.so.1 unavailable**; GPU allocation, submission, comparison and recovery were NOT RUN. The v2 harness runs inside an OS-supervised worker, bounds CUDA/NVRTC result sizes and records process/kernel provenance and per-stage status; 87 hardware/evidence unit tests passed at an earlier A09 head; additional adversarial tests on the newer head await fresh CI and are not pre-counted. See ../../tests/hardware/RUN.md and timestamped JSON evidence, including exact tool environment. CUDA pass alone also does not prove inference, VM passthrough or device-reset recovery.

## A01/A05/A06 kernel join: integrate existing owners, no new signer

These are PROPOSED interfaces for A00 coordination, not shipped Rust ABI and not kernel permissions implemented in this PR.

| Object | Canonical owner | Proposed state and interface requirement |
| --- | --- | --- |
| **DeviceHandle** | A01 PCI/OSTD object + A05 process CapSpace + existing HOS grant check | immutable BDF, complete IOMMU group and IRQ route; exclusive ResourceDomain/VM owner; device_generation, Unassigned/Fenced/Assigned/Quiescing/Quarantined; reject stale handles |
| **MemoryObject** | A01 existing physical frames + A06 single memory-domain accounting | stable pinned frames, alignment, direction, CPU aliases, mapped IOVA and mapping generation, DMA cache policy; unpin only after verified device quiet and IOTLB/TLB invalidation |
| **Buffer** | Slice of MemoryObject charged to ResourceDomain | overflow-checked offset/length, direction, CPU-owned -> prepared -> device-owned -> quiesced -> synchronized-for-CPU -> releasable |
| **Queue** | DeviceHandle generation and owning ResourceDomain; guest NVIDIA owns hardware specifics | queue ID, admission limits, outstanding count, state and associated interrupt; host does not falsely parse opaque CUDA commands |
| **Completion** | Kernel-validated queue event and current generation; never trusted guest assertion alone | sequence, fence, device/queue generation, success/fault/unknown-effect, memory ownership barrier; old-generation completions cannot release new buffers |
| **ResourceDomain** | A06 existing canonical budget/enforcement object | VM CPU admission envelope, RAM, pinned DMA bytes, device count/lease quotas, parent constraints; the A09 `ResourceDomainBudget` mirror checks one root/child edge only and never replaces A06 or claims per-kernel GPU utilization throttling |

**Security and DMA order:** HOS2 grant/identity checked at canonical admission before resource reservation; reserve and pin; check exclusive IOMMU group and DMA direction; map IOVA and quiesce writable CPU aliases or use protected staging; issue device ownership; accept bounded IRQ, perform wait/validation outside spinlock; synchronize DMA/cache, verify current generation and completion, then reclaim. IRQ and language atomics do not replace DMA/MMIO barriers. Cancel/revoke means no *new* admission; stop and drain DMA before physical unmap. If quiescence or reset cannot be proven, quarantine rather than reuse pages or say effect failed. Stop/kill cannot be silently transformed into no-result/no-effect. This does NOT give the model unrestricted MMIO or establish a second GPU capability authority.

The next implementation gate is now executable: `support/vmm/kernel_join_gate.py` fingerprints the pinned Asterinas VM/IOMMU sources and exits **2** on the current global IOMMU mapping (`PciDeviceLocation::zero()` and no device/group-scoped map/unmap). `support/hardware/vfio_preflight.py` separately checks an explicitly named PCI BDF, complete IOMMU group, DMAR/IVRS, driver binding and reset visibility without opening VFIO or changing sysfs. The current container preflight for `0000:01:00.0` exits **2** because that target is not visible. These are prerequisite blockers, not hardware assignment or GPU-compute passes.

The A01/A05/A06 handoff now also has a dependency-free `no_std` metadata model in `support/vmm/device_lifecycle/`. It mirrors the canonical 16-byte `ResourceDomainId` without truncation and enforces device attachment identity, queue incarnation, generation, buffer ownership, completion matching, unknown-effect cancellation, release ordering and checked admission across VM CPU reservation nanoseconds, VM RAM bytes, pinned-DMA bytes and aggregate queue slots. Parent plus child usage mutates atomically for one direct edge; arbitrary ancestor propagation remains A06's job. Local Rust tests pass, but the model performs no pinning, IOMMU mapping, CapSpace authentication, IRQ handling, MMIO, VMM execution or reset; it must not be connected directly to production DMA.

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

## Follow-up: safety hardening, NOT GPU enablement

The A09 branch merged a verified main baseline under a two-parent,
fast-forward-only integration; only A09-owned files were overlaid. Subsequent
commits addressed security failures in read-only inventory, VFIO review,
OS CUDA-worker watchdog and cross-kernel evidence. These are **host-side**
checks, not a physical GPU driver/VMM or successful compute.

- PCI/sysfs attributes use bounded O_NOFOLLOW/O_NONBLOCK reads. CPU and VMX/SVM
  fields become *unknown*, not falsely negative, if procfs is unreadable.
- The VFIO observer requires the target GPU to be bound to `vfio-pci`; an
  unbound compute/audio endpoint or a non-VFIO production driver is blocked.
  An unbound PCI bridge is permitted only as a manual-review observation.
  Present-but-unreadable unsafe IOMMU/interrupt module settings block review.
- CUDA uses a supervised process with its process-group leader held unreaped
  until group inspection and SIGKILL. The CLI rejects leftover descendants,
  lost process identity, incomplete cleanup or a forged success JSON. The
  reported device effect is unknown after worker termination, NOT GPU reset.
- Child reports use bounded regular-file reads with O_NOFOLLOW and disallow
  duplicate/nonfinite JSON, mismatched exit codes, missing fixed GEMM output
  digest, missing kernel/cleanup stages or false resource-release claims.
  A child cannot assert Asterinas host boot, physical assignment or reset.
- Host and Linux guest serial logs each require exactly one full line
  `A09_VM_NONCE=<nonce>`. Extra/conflicting nonce records block review.
  Review output cannot overwrite a previous evidence file.

**CI accuracy:** a prior exact A09 head passed its host Rust/Python model CI.
The new head adds tests and is not considered passed until fresh jobs finish.
No work in these commits touches production hardware, firmware, BIOS, drivers,
storage, training/H3 services or power protections.

**First real-world unblock:** A01 must implement group-scoped PCI/IOMMU,
real VM vCPU/guest memory/interrupt lifecycle and correct VMX/SVM backend.
A05 must make its one CapSpace/grant authority and kernel queue/device registry
own the PCI lease and process identity. A06 must charge real pinned frames and
scheduler usage against the canonical ResourceDomain ancestor chain. Only
then can an authorized idle disposable RTX 4060 lab host run the Linux baseline
and a SEPARATE GPU guest under an actual Asterinas-derived host. Throughput,
DMA reset/recovery, cancellation and GPU inference remain not tested.

## 2026-10-17: first-lab identity, provenance and A01/A05/A06 blocker update

The execution-tool **sandbox**, not an authorized physical GPU host, was
read-only inspected again on Linux 6.18.55 x86_64 with virtual AMD EPYC
9V74 CPU and seven PCI functions (Intel bridge and VirtIO). No accelerator
class, CUDA device node, VFIO, KVM or visible IOMMU group was observed.
The exact time-scoped JSON is
[2026-10-17-sandbox-readonly-pci-034743z.json](../../tests/hardware/evidence/2026-10-17-sandbox-readonly-pci-034743z.json).
Absence in this restricted environment is not evidence of absence on the
user's physical RTX/AI MAX machines. Firmware, driver versions, DMA behavior,
real VRAM/UMA, queue/fences, PCI subgroup and reset **remain unobserved**.

The GPU model must match **exactly RTX 4060** (optional standard NVIDIA/
GeForce prefixes, but not RTX 4060 Ti, Laptop GPU, RTX 4070 or a substring).
Before opening the CUDA Driver API, an explicit real PCI BDF must match a
well-formed address. The canonical comparison handles a 4-hex-digit Linux
segment and an 8-hex-digit CUDA segment without confusing different numeric
domains; PCI slot is limited to 0..31. CUDA's selected device must report
compute capability 8.9. The host-side executable proof remains GEMM16 FP32
with the fixed exact SHA; no hardware inference claim follows from it.

Only the supervised CUDA **v2** process receipt is eligible for later
cross-kernel review: kernel and x86_64 guest identity, worker PID matching
the supervised child process, exited/reaped worker group, exact fixed
numerical/allocator/launch/fence/cleanup stages, independent matching raw
VM-nonce boot logs, and explicit denial of self-attested host, PCI assignment
or reset success. These are *consistency checks on unauthenticated records*,
not a cryptographic hardware proof, and process-group cleanup cannot prove
device DMA quiescence or kill detached-session descendants.

Review integration blocker [#96](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/96)
for the actual A01 group-scoped IOMMU / full VM, A05 canonical CapSpace
device/queue ownership, A06 real hierarchical ResourceDomain pin/scheduler
implementation. Route C remains the only planned GPU implementation.
Even a future Linux-host GEMM is just a labeled baseline. No Asterinas GPU,
Linux GPU guest boot, physical reset, NPU, Vulkan/ROCm runtime or local GPU
inference succeeded here. Root README remains zero bytes.
