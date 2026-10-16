# A09 no_std device lifecycle transition core (not a kernel driver)

This dependency-free Rust crate is a **pure state model**, intended for A01/A05/A06
review and integration after they publish a canonical kernel device and resource
interface. It does not issue a GPU capability; `ResourceDomainId` is *only* the
identifier of A06's existing ResourceDomain. The A05 CapSpace grant, lease,
final exec identity and IOMMU-group ownership must be verified by the real
kernel **before** invoking these transitions. All methods only update Rust
metadata in memory and cannot protect device registers by themselves.

## Operations and refusal behavior

- `DeviceHandle`: group-bound exclusive assignment model; `fence` increments
  generation and rejects late completions. `quarantine` blocks any future
  assignment in this state instance; there is no fabricated reset-to-ready.
- `MemoryObject`: fixed owner/length metadata, **not** pinned physical frames.
  `Buffer` checks offset/length overflow, tracks CPU/prepare/in-flight/CPU-sync,
  rejects release during in-flight or unknown effects. No user-provided HPA.
- `Queue`: bounded outstanding count, per-queue sequence and generation. Failed
  submissions do not consume a sequence or mutate the buffer. `Completion`
  cross-checks memory ID, device generation, queue ID, queue generation and
  sequence before a trusted-driver completion changes buffer ownership.
- Canceling in-flight work **fences queue, increments generation, retains
  outstanding charges and leaves buffer in `UnknownEffect`**. Does not pretend
  CUDA child timeout or VM shutdown stopped DMA. Hardware quiescence and
  invalidation would be a separate verified kernel adapter operation.

## Non-negotiable integration boundaries

1. A01: discover/claim the entire PCI IOMMU group, enforce DMA mappings,
   interrupt remapping, ATS/PASID if ever used, cache/MMIO barriers, physical
   GPU reset safety, platform-correct VMX or SVM, and real memory pinning.
2. A05: the canonical identity/CapSpace/grant lifecycle is the ONLY signer of
   rights. Prohibit untrusted calls into these internal methods. An IRQ or guest
   `Completion` object alone is not trusted hardware proof.
3. A06: charge and release pinned pages/VM CPUs/queue allocations using the
   actual ResourceDomain hierarchy; reject parent overcommit. The pure
   `ResourceDomainId` type does NOT enforce quotas or reserve capacity.
4. A00: coordinate IPC/ABI object layouts before moving this logic into the
   Asterinas kernel. Do not start a second device registry or OS authority.

**The crate must not be wired into real DMA or a production kernel in its
current state**: calls such as `prepare_after_dma_map_and_sync`,
`complete_after_hardware_fence`, and `sync_for_cpu_after_platform_checks` rely
on external privileged platform proofs not represented by Rust types. Their
names make the required prior effect explicit; the model is not an end-to-end
memory-safety or device-isolation proof. It does not track aliasing across
multiple Buffers to one MemoryObject; kernel must enforce overlapping writable
mapping exclusion and address-space teardown separately. These limits are
intentional to keep model state distinct from a real device driver.

## Build/test gate

```sh
cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline
cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline --doc
cargo test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked --offline --release
```

Rust code here uses edition 2021 and `#![no_std]`; tests use the standard test
harness. The available host Rust 1.99.1 toolchain locally passed **28 unit
tests, 3 compile-fail doctests, and the release test suite** with `--locked
--offline`. This host result does not replace the pinned
`nightly-2026-07-21` **kernel** toolchain or A00's required CI job. Python unit
cases in `tests/hardware` remain separate from the Rust result.

**Aliasing guard:** `DeviceHandle`, `Queue` and `Buffer` are intentionally
not `Clone` or `Copy`, so a simple safe Rust value duplication cannot split
their live state accounting. This still does not establish physical
IOMMU-group uniqueness or prevent separately created overlapping buffers;
A01/A05 must enforce one authoritative device registry and A06 memory aliases.

## Cross-physical-device DMA identity binding

The pure model now binds Buffer and Queue metadata to **both PCI BDF and complete
IOMMU-group identity** when the buffer is prepared / queue is created. Matching
ResourceDomainId and device generation alone never authorize cross-device
submission, cancellation, or completion. Changing the device after a completed
CPU-sync is likewise rejected until the original Buffer is safely released.
Three tests cover same-domain/same-generation, wrong-device completion,
and post-sync retargeting. All hardware register and DMA work is still
unimplemented.

These are *metadata checks*, not full rights or global uniqueness. DeviceHandle::new
can create independently forged handles and Queue::new can duplicate numeric
queue IDs; the real A05 kernel registry must enforce unique device ownership
and namespace queue identities, while A06 charges pinned physical frames.
A01 must validate the actual IOMMU group, MMIO/interrupt isolation and DMA
quiescence. This model is not safe to wire directly to hardware as-is.

## Hotplug and stale-BDF protection

`DeviceHandle::new(pci_bdf, iommu_group, instance_id)` now requires a
**nonzero, per-device-attachment lifetime ID** issued by A05's canonical
kernel PCI registry. Buffer/Queue metadata bind to all three fields, not
only the address and IOMMU group. A stale Buffer from a removed device
must not be submitted to a replacement occupying the same BDF and group,
even if both report generation 1 and share a ResourceDomain. The ID is
pure metadata, never a capability or permission signer. The crate does
NOT allocate IDs or guarantee uniqueness; the A05 owner must provide
monotonically non-repeating device attachment identities per boot,
including hotplug/reset/driver rebind. A01 still owns real IOMMU,
DMA quiescence and IRQ isolation. Separate Rust tests cover BDF reuse
and zero-ID refusal. Local Rust tests pass; the model still requires A00 CI and
kernel-owner review before any integration.

## Queue-ID reuse and late-completion ABA

Queue::new now requires a nonzero queue_instance value from A05's canonical
queue registry, independent of its numeric queue ID and device generation.
The instance must not repeat across close/reopen, VM teardown, or queue reset.
BufferPhase::InFlight, Completion and Queue metadata bind to the same
queue_instance; a late completion or cancellation from a former queue lifetime
cannot affect a newer queue that reused its numeric ID and generation.
Tests cover identical queue ID, ResourceDomain, device, and generation
with distinct queue incarnations, plus zero-ID rejection.

This value is NOT a GPU permission or queue-authority token. The standalone
crate cannot mint, authenticate, or globally enforce unique queue instances;
A05 must allocate and enforce them inside its existing kernel registry.
A06 still owns queue/RAM accounting and A01 owns real driver interrupt/fence
evidence. None of these Rust tests establishes physical DMA quiescence.


## HOS2 16-byte ResourceDomain identity (A03/A05/A06 handoff)

The canonical `libs/os-control/src/lib.rs` host model declares
`Id16([u8; 16])` and `id_type!(ResourceDomainId)`, with `from_u128()`
encoding in **big-endian** byte order. A09's former `ResourceDomainId(pub u64)`
was incompatible and could truncate/reinterpret a domain during integration.
The standalone A09 `no_std` metadata mirror now holds the full private
`[u8; 16]`, exposes `new([u8;16])`, `from_u128(u128)`, `bytes()` and
`is_nonzero()`; zero-domain DMA/device/queue admission is rejected. Rust
unit tests cover high 64-bit distinctions, byte encoding and zero IDs.

**No second identity authority:** this is only a value representation mirror
so the canonical A05/A06 adapter can map the **full** stable ResourceDomain ID
without truncation. It is not the actual in-kernel CapSpace/ResourceDomain type,
does not install a permission, and cannot create a budget or exclusive PCI
lease by itself. A00 must review byte encoding with A03/A05/A06 before
connecting to kernel state. Local compilation passes; canonical kernel
integration remains pending CI and A00/A01/A05/A06 review.
