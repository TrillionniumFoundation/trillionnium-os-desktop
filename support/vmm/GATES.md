# A09 VMM gates — fixed Asterinas v0.19.0

**Not implemented in this project.** Source pin c4b7ed575b7b32773475b194d2ad41fb6d03765b, tree 96605cf64aeae2d34f29b97e85eff9315fe10a8e.

| Platform | Source evidence at pinned SHA | Do NOT claim |
| --- | --- | --- |
| Intel VMX | ostd/src/arch/x86/vm/mod.rs, context.rs, ept.rs, vmx/ and ostd/src/vm/{gpm_space,guest_mode}.rs provide Intel VMX, EPT, guest context/exit primitives | No Linux boot VMM, PCI GPU passthrough, vCPU scheduling, virt IRQ, device model, recovery qualification |
| AMD SVM | No SVM-specific file in pinned x86 vm tree; implementation uses VMX/VMCS | Do not use VMX example as proof of AMD SVM/NPT/VMCB/VMRUN, even though visible virtual CPU is AMD |
| ARM EL2 | No ARM VM implementation found in pinned VM path | No ARM EL2, stage-2/SMMU/GIC guest virtualization pass |
| IOMMU | ostd/src/arch/x86/iommu/{dma_remapping,interrupt_remapping,invalidate,fault,registers} source surfaces exist | Not a complete GPU assignment API, validated IOMMU group/isolation, reset or AMD-Vi evidence |

Execution-tool container: Linux 6.18.44, x86_64, no /dev/kvm, no forwarded vmx/svm flags; NO hypervisor run. Upstream osdk/tests/examples_in_book/write_a_hypervisor_in_100_lines_templates/lib.rs demonstrates a small VMX real-mode guest that prints serial and halts; not a Linux guest VM or a GPU VMM.

## Mandatory engineering gates for selected route C

1. Discover actual architecture at runtime; reject VMX absent on Intel / SVM absent on AMD. If AMD target is chosen, implement/test SVM instead of attempting VMX commands. No aggressive emulation fallback.
2. VM owns real vCPU state, timers, fault injection, VM entry/exits, scheduling and lifecycle, guest physical memory backed by pinned MemoryObjects and ResourceDomain quotas.
3. Provide virtual interrupt controller, timer, minimal bootable virtio block/console, PCI config and MSI/MSI-X/interrupt remapping; do not give guest global host MMIO.
4. A05 CapSpace grant/resource authorization and device generation assign exactly one isolatable IOMMU group to exactly one VM. Validate PCI ACS/group boundaries, all related functions, reset, DMA masks, IOTLB invalidation, IRQ isolation. Reject unisolatable/shared production GPUs.
5. Map guest IOVA only to guest-owned pinned host frames; enforce CPU alias restrictions/cache synchronization and no DMA after unmap. No direct arbitrary physical address from guest.
6. On VM kill, revoke admissions, fence completion generation, stop vCPUs, prove hardware DMA quiescence; quarantine if not provable. Never reset active H3/training device or unbind installed host driver.
7. Record *both* Asterinas-derived host kernel boot identity and Linux guest kernel identity with selected physical PCI GPU BDF/driver/runtime, successful CUDA result, DMA cleanup, VM death and recovery in disposable lab.

Only the above can eventually qualify "local GPU in a Linux guest under a Rust host". QEMU/KVM VM on Linux host or reference VMX snippet is categorically different. Performance and GPU reset behavior remain unmeasured.

## Read-only source and assignment gates

The next implementation step is executable but still fail-closed. Run the source
gate against the exact checked-out Asterinas tree:

    python3 support/vmm/kernel_join_gate.py --kernel-root kernel/asterinas --target-arch x86_64

At the current pinned tree it exits **2** because `dma_remapping::map` and
`unmap` do not accept a device/group identity, use
`PciDeviceLocation::zero()`, and state that all devices share one page table.
The gate fingerprints the files and never treats a source match as live DMA or
VMM evidence; an otherwise complete source fixture returns exit **3** for
manual hardware review.

Before any future assignment review, the read-only VFIO preflight requires an
exact BDF, the complete IOMMU-group allowlist, DMAR/IVRS evidence, all group
functions bound to `vfio-pci`, and reset capability for every member:

    python3 support/hardware/vfio_preflight.py --bdf 0000:XX:YY.Z \
      --expected-member 0000:XX:YY.Z --expected-driver vfio-pci

It never opens `/dev/vfio`, writes a bind file, resets a device, or authorizes
assignment. Missing hardware returns exit **2**; a coherent synthetic fixture
returns `manual_review_required` and exit **3**. There is deliberately no
hardware-assignment success exit, so this remains a prerequisite observation,
not a passthrough or GPU-compute result.

## Metadata-only kernel join model

`support/vmm/device_lifecycle/` is now a dependency-free `no_std` transition
model for the A01/A05/A06 review. It covers `DeviceHandle`, `MemoryObject`,
`Buffer`, `Queue`, `Completion`, a full 16-byte `ResourceDomainId` value mirror,
and a `ResourceDomainBudget` admission mirror for VM CPU reservation
nanoseconds, VM RAM bytes, pinned-DMA bytes and aggregate queue slots. It
rejects zero identities, stale device/queue generations, cross-device
submissions, duplicate completions, queue overflow and unsafe release after
cancellation; unknown-effect cancellation retains the outstanding charge and
fences the queue. Parent/child admission checks and mutations are atomic for
one direct root edge; nested ResourceDomain propagation remains A06's
canonical responsibility.

The model does not pin frames, map IOVA, authenticate CapSpace grants, touch
MMIO, acknowledge IRQs, prove GPU fences, or reset hardware. A05 remains the
only device/queue owner and grant authority; A06 remains the canonical budget
and pinned-DMA owner; A01 remains responsible for real IOMMU, IRQ, VMM and
quiescence. `vm_cpu_ns` is an admission envelope, not observed scheduler
usage. The mirror must not be wired directly to production DMA in this state.

Local verification on the host Rust 1.99.1 toolchain:

    cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline
    cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline --doc
    cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline --release

All three commands passed: 38 unit tests and 4 compile-fail doctests. This is
metadata-state verification only, not a GPU, VMM or passthrough result.
