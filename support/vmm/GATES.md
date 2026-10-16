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


## A09 Phase-2 executable preflight boundary (2026-10-16)

- `../hardware/vfio_preflight.py`: Linux read-only sysfs group inspection with
  **exact expected-member allowlist**, including display/audio siblings. A
  mismatched or occupied group, no-IOMMU mode, absent PCI device/identity or
  incomplete backlink rejects the route. Even a clean observation returns
  `manual_review_required`, never authorization. This is **not** a Rust-host
  VFIO assignment implementation. It cannot validate ACS, interrupt remapping,
  DMA quiescence, active workload ownership or reliable reset.
- `../../tests/hardware/run_isolated_cuda.py`: bounded, explicit isolated-lab
  CUDA subprocess with pinned guest PCI identity and fixed output SHA. A child
  timeout or CUDA error leaves DMA effect **unknown**, not successfully canceled.
  Its success label remains guest-process reported, not host Asterinas proof.
- Real VM-to-GPU join still requires A01 source import, an actual VMX/EPT-capable
  Intel test machine **or** an independently implemented AMD SVM backend,
  and A05/A06's canonical CapSpace/ResourceDomain. No parallel GPU authority.

### Proposed operation order for A01/A05/A06 (not shipped ABI)

1. `AcquireDevice(DeviceHandle, ResourceDomain, CapSpace context)`: confirm
   group exclusivity, final `exec_epoch`, active grant, parent budget and
   current generation; deny if guest/raw fd bypasses common object checks.
2. `PinMemory(MemoryObject, domain, size, direction)`: charge every ancestor
   before pinning; track CPU aliases and IOVA range; no arbitrary GPA=HPA.
3. `Submit(Queue, Buffer, fence)`: require device/queue generation match,
   buffer prepared for correct DMA direction, CPU writable aliases restricted,
   and kernel-owned descriptor copy; count in-flight before doorbell.
4. `Complete(Completion, fence, generation)`: verify current queue generation,
   hardware signal and DMA sync; only then transition buffers CPU-owned.
5. `Revoke/Cancel`: block **new** submissions; drain/stop guest and DMA safely.
   Outstanding effects remain unknown until separately confirmed; an API
   timeout is not hardware quiescence.
6. `Stop/Reset/Destroy`: require independently demonstrated quiescence,
   interrupt/IOTLB/TLB cleanup and all owners retired before pin recycling.
   On absent evidence, quarantine device+buffers with bounded accounting.
   Physical GPU reset only on disposable isolated lab card after qualification.

These are typed object/transition requirements for kernel owners, not a second
permission signer or a simulated ``passed`` production backend.


## Phase 3: actual A01 dependency and typed state/provenance gate

A01 [PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)
has now merged its pinned Asterinas kernel/QEMU boot baseline into main
at e44c92ac885eb003665ff2e1e5c6fab1f104b2d6. This is a real source/boot
milestone, **not yet a Linux guest VMM boot or GPU handoff**. Do not use its VMX/EPT soft-skipped test as
physical Intel virtualization success. The A09 device transition model in
`device_lifecycle/` is a standalone `no_std` metadata-only prototype, not a
replacement of A05 CapSpace or A06 ResourceDomain.

A00 acceptance checklist, each independently logged from the real kernel:
1. A01: fixed kernel source/ELF hash + serialized host boot; VMX on Intel,
   or independently implemented/tested SVM on AMD; real vCPU/guest memory,
   virtual IRQ/device model, Linux guest boot.
2. A05: exclusive group/device lease bound to canonical CapSpace identity;
   enforce grant/revoke before assignments; reject stale generation/duplicate
   queue completions; track actual hardware IRQ, not guest self-report.
3. A06: charge pinned frames and outstanding queue work to existing
   ResourceDomain hierarchy, including recovery executor reserve; admit only
   within ancestor budgets and existing memory object lifetimes.
4. A01/A05: physical IOMMU and interrupt remapping isolation; host/guest
   device IDs and VM boot nonce; DMA cache sync and CPU writable aliases;
   explicit teardown IOTLB/TLB invalidation and independently observed
   quiescence. If unavailable: quarantine rather than recycle or reset.
5. A00 independent review: match host/guest serial traces and binary digests
   using `acceptance.py`; a consistent unsigned bundle is still **review
   required**, NEVER an automatic GPU claim. Test exact CUDA GEMM and compare
   numerical output on disposable idle RTX 4060.

This PR cannot deliver physical GPU passthrough despite A01 source now being
integrated: no host GPU/VMM adapter or full driver exists, and this tool container lacks `/dev/kvm`, GPU nodes and toolchain.

Confirmed actual merged main source interfaces: `kernel/asterinas/ostd/src/arch/x86/vm/mod.rs`
(Intel VMX/VMCS), `kernel/asterinas/ostd/src/vm/mod.rs` (GuestMode/GuestPhysMemSpace),
`kernel/asterinas/ostd/src/arch/x86/iommu/mod.rs` (crate-private map/unmap and IRQ remap).
**None is an A09-owned public device-passthrough API.** A00/A01 must coordinate
export/integration and actual VMX or AMD SVM execution; A09 does not patch
A05/A06 kernel core sources unilaterally.
