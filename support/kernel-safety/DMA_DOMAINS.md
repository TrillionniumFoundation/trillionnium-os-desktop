# Restricted per-requester DMA domain stage

This stage supplies an opt-in OSTD mechanism and explicit hardware regressions. An independently translated device is not a qualified desktop/mobile hardware stack. Existing `DmaCoherent` and `DmaStream` drivers still use the shared legacy table. No userspace/HOS2 capability authorizes the new interface yet, and DMA buffers are outside `hepta.page.*`.

## Ownership and scope

`DeviceDmaDomain::bind(DmaRequester)` creates a separate page table and unique nonzero VT-d domain identifier. The accepted profile is segment 0, root bus, function 0, device 1..31, with one DRHD and no other DMAR structures. The unit must either cover all segment-zero requesters or explicitly name that root endpoint with one path element. It requires snoop control, active queued invalidation/translation, and DMA draining. CVM execution is refused. Missing or unsupported hardware returns an error; the API does not fall back to direct DMA or the shared legacy table.

This restricted addressing profile does not establish PCI alias/ACS groups, peer-to-peer routing isolation, ATS/PASID, multiple remapping units, firmware reserved mappings, hotplug/reset policy or real-machine qualification. TT=00 contexts admit untranslated requests. New-domain leaf entries request CPU cache snooping and binding requires ECAP.SC. Page-walk coherency (ECAP.C) is not assumed: publication writes back every live second-level table, context and root plus queued descriptors using architectural CLFLUSH and fences. It currently flushes an entire affected tree, so update cost grows with mapped pages; this is a correctness stage, not a throughput qualification.

A domain allocates new zeroed untyped `Segment<()>` buffers. Only those physical pages are published into its table. Live physical frame uniqueness prevents the selected IOVA (the frame's physical address) from replacing another live buffer mapping. Buffers retain an `Arc` to the domain, so dropping the administrative handle cannot destroy a live buffer's domain. `revoke` removes a mapping while returning the still-owned bytes for CPU access. No API grants an arbitrary typed physical frame to DMA.

## Publication and revocation

The root table's IRQ-safe lock serializes requester assignment, domain IDs and page-table changes. Domain IDs are reserved before allocation/publication, so an allocation panic cannot leave a live domain ID available for reuse. A context's Present bit is cleared and hardware context/IOTLB caches drained before replacing it. The high half (address width and domain ID) is written before publishing the low half with Present set. A final invalidation removes cached absent entries before the new mapping is exposed to its caller.

Map/unmap now use synchronous context-cache plus IOTLB invalidation. Queued requests include both drain flags followed by an invalidation wait. Register invalidation also waits for IVT to clear and requires a nonzero actual invalidation granularity. Removed page-table fragments and untyped data pages remain alive until completion. Releasing a domain leaves its requester blocked; it never restores broad legacy access. A released domain ID is reused only after context invalidation/draining.

If a page-table operation panics after publication, the data segment is deliberately retained rather than returned to the allocator while DMA could still reach it. This protects memory lifetime at the expense of leaked capacity. Hardware invalidation failure currently stalls the operation rather than authorizing reuse. **There is no bounded recovery guarantee.** Timeouts need a quarantine/reset design that retains all reachable pages and identifiers until hardware revocation is proven; returning an error and immediately freeing the bytes would be unsound.

IOMMU register MMIO has a permanently owned uncached mapping. It is not accessed through the physical-RAM direct map: the actual 512 MiB fixture exposed an unmapped 0xfed90000 access during initialization. Variable register offsets are checked within the reserved 4 KiB aperture; larger register layouts are not qualified.

The invalidation queue now wraps its tail before publishing it to hardware. Fault handling acknowledges the fault and overflow bits using write-one-to-clear semantics. Fault records are read with the high-half validity bit first, followed by the stable low half, then acknowledged with a 64-bit high-half write. Repeated negative tests must observe actual requester-bound hardware faults, not just unchanged memory.

## Validation design

The `dma-domain-ktest` feature enables one explicit OSTD hardware test. The runner attaches two QEMU EDU functions at 00:05.0 and 00:06.0, with a 39-bit Intel IOMMU, queued invalidation caching mode and snoop control, no device IOTLB and no interrupt remapping. There are no disks, network or host devices. Each device must read and write its own buffer, fail reads and writes against the other domain, fail writes to a revoked IOVA, and remain unable to use that IOVA after domain teardown/rebind. Sentinel bytes and actual fault source IDs are checked. Repeated allocate/drop operations cross the hardware queue wrap boundary. A second boot of the same ELF with no IOMMU must explicitly reject domain creation; a third boot with snoop control absent must reject the unsupported platform.

The EDU internal DMA buffer is not exposed as a general MMIO byte array: test values are loaded and inspected through DMA to each domain's own scratch buffer. This tests actual translations rather than a CPU page-table model.

Run the complete OSTD suite after changes, including the existing three VMX/EPT soft skips recorded separately. Run the actual hardware fixture with both 2 and 4 CPUs, then ordinary kernel/core and earlier safety/page-memory regressions as appropriate to the changed integration. A passing QEMU run establishes behavior for that emulator and source, not physical PCIe routing or device reset qualification.

## Development and remaining closure

The implementation lives in OSTD `arch/x86/iommu/{dma_remapping,cache,registers,invalidate,fault}`; safe drivers consume the public `mm::dma::DeviceDmaDomain` and buffer types. The only unsafe raw tree walk reads owned three-level IommuPtConfig nodes while the root-table lock prevents mutation, then flushes child nodes before parents. Removed fragments remain retained until the hardware drain completes. The traversal never follows leaf data addresses or accepts arbitrary physical addresses from a safe caller.

Run the fixture through `tests/kernel/dma-domain/run.py` (see its README), plus the complete OSTD suite after changing these ownership/cache rules. A next product stage must discover real requester aliases/ACS groups, bind domain administration to the original Hepta grant and device lease, move each real driver off legacy DMA, budget pinned DMA and translation pages, reserve independent recovery capacity, and implement tested reset/quarantine before any bounded timeout may release memory. This stage implements none of those claims by naming an API.

## Primary hardware contracts

- [Intel VT-d architecture specification, revision 5.0](https://cdrdv2-public.intel.com/831418/vt-directed-io-spec.pdf): sections 6.5.2, 6.5.3 and 6.5.4 describe context/IOTLB invalidation, publication/reuse and untranslated-request draining; register descriptions specify the W1C fault bits.
- [QEMU EDU specification](https://www.qemu.org/docs/master/specs/edu.html): device command protocol and the internal DMA buffer.
- [QEMU Intel IOMMU implementation](https://github.com/qemu/qemu/blob/v9.2.0/hw/i386/intel_iommu.c): emulator behavior is additional test context, not a replacement for Intel's hardware contract.
