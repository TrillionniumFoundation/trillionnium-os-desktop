# A09 → A01/A05/A06 kernel GPU/VMM join: source-grounded blocker

**Status: BLOCKED.** Source reviewed on 2026-10-16 against pinned Asterinas
v0.19.0 `c4b7ed575b7b32773475b194d2ad41fb6d03765b`.
This is a source analysis, NOT an implemented GPU driver or hardware attestation.

## Existing interfaces and actual limitations

| Source file (under kernel/asterinas/ostd/src/) | Source evidence | Owner |
| --- | --- | --- |
| `arch/x86/iommu/dma_remapping/mod.rs` | `pub(crate) unsafe fn map(daddr: Daddr, paddr: Paddr)` and `pub(crate) fn unmap(daddr: Daddr)`. Code explicitly states **the page table of all devices is the same** and uses `PciDeviceLocation::zero()` to map/unmap. NO device/group argument to these functions. | A01/A05 |
| `arch/x86/iommu/interrupt_remapping/mod.rs` | `alloc_irt_entry()` is `pub(in crate::arch)`. It is an interrupt remap primitive, NOT a verified per-VM MSI/IRQ boundary. | A01 |
| `mm/dma/dma_stream.rs` | `DmaStream::alloc/map` and `sync_from_device/to_device` exist. They do not establish a guest-owned IOMMU domain or prove DMA stopped before buffer release. | A01/A06 |
| `vm/guest_mode.rs`, `vm/gpm_space.rs` | `GuestMode::new/execute` and `GuestPhysMemSpace` exist. These are VMX/EPT guest primitives, not a bootable Linux guest VMM with virtual interrupts, PCI and passthrough. | A01 |
| `libs/os-control/src/lib.rs` (repo root) | Canonical host-model `ResourceDomain` and CapSpace identity / CPU budget types exist, not a proven in-kernel pinned DMA quota. | A05/A06 |
| `support/vmm/device_lifecycle/src/lib.rs` | A09's no_std metadata-only DeviceHandle / MemoryObject / Queue / Buffer / Completion model. No actual frames, MMIO, DMA isolation, permission signing or IRQ. | A09 |

**Critical blocker:** Today's global IOMMU mapping is not a group-scoped
device-assignment boundary. Do not connect an untrusted Linux guest GPU to
these global map/unmap surfaces or count them as per-device DMA isolation.

## Executable read-only source gate

```sh
python3 support/vmm/kernel_join_gate.py --repo-root . --output -
# exit 2 BLOCKED, never physical GPU approval
python3 -m unittest discover -s tests/hardware -p 'test_kernel_join_gate.py' -v
```

The gate bounds source reads, fingerprints actual source bytes, detects the
shared IOMMU mapping and absence of device-scoped mapping signatures, and
identifies existing GuestMode/DmaStream/ResourceDomain symbols. It only
provides **lexical evidence**, not a Rust compiler/semantic proof. Even when
source is updated to accept a device domain, the result stays BLOCKED until
real isolated hardware IOMMU/IRQ, VM boot and DMA recovery evidence passes.
Missing source, false completion markers or unsigned evidence never pass.

## One priority route C: Linux NVIDIA guest, Asterinas Rust host

1. **A01**: select actual authorized *disposable* GPU and full IOMMU/ACS group;
   implement exclusive per-device/group IOMMU translation, guest pinned IOVA,
   interrupt remapping, memory/CPU alias barriers and IOTLB invalidation.
   Provide a real VMX-on-Intel guest lifecycle/vCPU/virt IRQ/PCI device model
   booting Linux. AMD SVM needs independently implemented hardware backend.
2. **A05**: canonical CapSpace grant and exclusive device owner tied to final
   VM/process identity. Supply non-reused device-attachment/queue incarnation
   IDs, check generation/rights at every admission, revoke future admission.
   A09 MUST NOT sign a second GPU capability.
3. **A06**: account VM RAM/pinned DMA bytes/queue work and recovery reserve
   in the canonical ResourceDomain parent hierarchy. No unpin or quota refund
   on cancellation before verified DMA quiescence.
4. **A01/A05/A06**: test stale completion, VM kill, lost interrupt, IOMMU fault,
   writable CPU aliases, IOTLB drain, device reset isolation. On unproven
   hardware quiet, quarantine device + associated memory instead of reuse.
5. **A09 isolated lab**: capture *independent* Asterinas-host + Linux-guest
   serial boot nonce logs, PCI IDs, real NVIDIA firmware/driver/NVRTC, kernel
   binaries/hashes, exact FP32 GEMM GPU result, cleanup and recovery facts.
   Linux-host CUDA tests and Mesa software graphics are never Rust-host GPU
   completion evidence.

STOP if GPU belongs to H3/training/prod, no real isolated device, no VMX/VT-d
or qualified SVM/IOMMU backend, no safe reset, missing pinned accounting, or
unknown DMA. No modifications to production drivers, firmware, BIOS, power
limits, system disk or running services. No Ollama.
