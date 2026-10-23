# Physical reserve in the original frame allocator

Status: implemented candidate; native allocator tests have not yet run. This
slice has `global_recovery_guarantee=false`. It does not close the full F04
recovery blocker or authorize a production recovery image.

## Owner and authority

The installed `osdk_frame_allocator::FrameAllocator` remains the one global
physical allocator. With `physical-reserve` enabled (selected by G1-d), it can
withdraw one contiguous extent of 1–4096 pages from its original CPU cache / local
buddy / global buddy path. Only after that real withdrawal succeeds does OSTD
return an opaque `PhysicalReserve`. A fixed bitmap inside the original allocator
tracks that extent; no heap allocation, approximate free counter, separate test
allocator, or changed pressure denominator authorizes an allocation.

Ordinary `FrameAllocOptions` calls retain the original route and cannot consume
that extent. An explicit `alloc_frame_from` / `alloc_segment_from` call must borrow
the opaque token. The token has no public constructor from an identity and no
`Clone`; an authorized kernel owner may deliberately share the same token using
`Arc`. Raw allocator hooks accept the token reference, never a caller-supplied
numeric role or reserve ID. This is a privileged Rust mechanism, not a userspace
capability: there is currently no production image/VMAR ingress for it.

Incarnation identities monotonically increase and fail on overflow. The original
allocator rejects old/repeated creation, second active reserves, and allocation
from closed or different incarnations. Failed requests publish no authority.
There is no implicit fallback from reserve exhaustion to ordinary memory.

## Lifetime and refund

The original frame metadata and reference count remain authoritative. All final
refunds enter the original `GlobalFrameAllocator::dealloc(addr, size)` and are
routed by actual physical address, including arbitrary partial contiguous ranges,
shared frames, sliced segments, and metadata repurposing. No caller supplies a
refund class. Closing a token disables new allocations permanently; existing
references remain valid. Only after the final physical frame refund does the
entire extent return to the original ordinary cache/pool. Repeated closure or a
stale token cannot affect a later incarnation.

Segment construction now has two disjoint RAII owners: the original Segment
owns its successfully initialized prefix, and the allocating call owns its raw
uninitialized tail. If a metadata constructor unwinds, each refunds its own
portion through the original allocator. This also repairs that failure path for
ordinary segment allocations. Length multiplication and Layout construction are
checked before physical withdrawal.

Lock order is local IRQ guard → reserve state → CPU cache/local buddy → global
buddy. Ordinary allocation takes no reserve lock. Feature-enabled deallocation
checks the physical partition under its IRQ-disabling spinlock before any pool
access. No path acquires the reserve lock while holding a pool/cache borrow.
There is no allocation, waiting, formatting, or I/O under the reserve lock.

`load_total_free_size()` remains an approximate observation of ordinary free
bytes and excludes the complete withdrawn extent. It is not an admission check.
The token snapshot is a consistent owner-lock observation of its physical start,
capacity, allocated bytes, and closed state. Bitmap allocation is bounded by
4096 pages, honors alignment and physical contiguity, and does not alter ordinary
allocation complexity. Ordinary builds without the feature do not include this
partition or its deallocation lock; the trait hooks default to rejection.

## Tests and evidence boundary

Eight `osdk-frame-allocator` kernel tests use the installed original allocator and
real OSTD frame metadata. They cover admission/replay/stale authority, shared and
repurposed final references, real fragmentation/alignment/failed requests,
metadata-constructor unwind, partial raw and typed refunds, concurrent holders
racing closure, competing reserve creation, and actual exhaustion of the ordinary allocation interfaces.

The exhaustion fixture requires N0, preallocates all its bookkeeping, then holds
real ordinary frames until the original 1/2/3/4/8-page and aligned allocation
paths return failure. It does not lower the allocator's capacity or substitute a
mock pool. It checks that none of those frames lie in the reserved extent; the
explicit token can still obtain its whole real extent; its capacity limit denies
an extra page; and after refund and close the same extent becomes available via
the original ordinary path. It keeps local IRQs disabled only through exhaustion
and restores ordinary memory before assertions/diagnostics. Existing small-cache
batching may leave unusable fragments: the claim is actual allocator failure,
not that an approximate global-free byte counter must equal zero.

The concurrency test uses real kernel tasks and original frame handles. An N0 run
proves scheduling interleavings, not simultaneous execution on different CPUs.
The separate concurrency case can also be selected under SMP; the exhaustion
case deliberately fails its N0 precondition under SMP instead of silently
claiming unsupported stress coverage. Run the existing allocator suite as well,
and run ordinary no-feature compilation plus G1-d compilation. Rustfmt/cargo check
are not kernel execution evidence. The exact frozen source, kernel ELF, test
selection, complete serial log, and successful QEMU exit must be recorded before
this candidate is described as verified.

Candidate host verification used pinned `nightly-2026-07-21` and a separate target:
`cargo check -p osdk-frame-allocator --target x86_64-unknown-none` passed without
reserve features; `RUSTFLAGS="--cfg ktest" cargo clippy -p osdk-frame-allocator
--features physical-reserve --target x86_64-unknown-none -- -D warnings` checks all
eight real test bodies and the feature implementation. Formatting and diff checks
also pass. These are compile/lint results, not a native execution receipt.

The allocator suite must be run from `kernel/asterinas/osdk/deps/frame-allocator`
with the source-matched `cargo osdk test` and the prepared N0 test boot settings;
a core-only ktest whitelist does not execute dependency allocator tests. The
exhaustion test emits its actual ordinary frame count and protected extent after
restoring ordinary memory and completing all assertions.

## Remaining F04 work

No production path currently creates this reserve or assigns its token to a
sealed recovery image. A following change must carry explicitly authorized,
bounded recovery allocation along the original image/VMAR and OSTD VmSpace/page
table ownership. A normal fork/exec must not acquire authority by inheriting a
user-data accounting Arc, root UID, PID, or an unlimited `None` account.

PageTableNode allocation still uses ordinary frames with `expect`, and the global
Rust heap still has infallible allocations that can abort under pressure.
Recovery stack, page tables, IPC/control buffers, D storage, FD slots and kernel
objects require bounded preallocation or fallible admission on their original
owners. Socket/slab/filesystem/DMA pressure and failure rollback must be tested
through those actual paths. An allocator-only reserve cannot guarantee that a
user recovery process runs after arbitrary kernel-memory exhaustion.
