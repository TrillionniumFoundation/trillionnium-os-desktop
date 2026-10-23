# Fallible UNIX ancillary input vectors

## Scope and original ownership

`sys_sendmsg` calls `CUserMsgHdr::read_control_messages_from_user`,
then `ControlMessage::read_all_from`, then the socket's original `sendmsg`.
For `SCM_RIGHTS`, `UnixControlMessage::read_from` resolves descriptors through
`FileMessage::read_from` and the current original `FileTable`.
`AuxiliaryData::from_control` merges these original file references before any socket write.
Previously the outer control-vector push, descriptor `Vec::with_capacity`,
and descriptor-vector append could invoke the infallible allocation error handler.

These three sites now reserve capacity through `Vec::try_reserve_exact` before their mutation,
with errors mapped directly to `ENOMEM`.
The per-message 253-descriptor check, merged 253-descriptor check,
32-control-message parsing policy and credential validation remain in place.
Successful descriptor lookup still clones the original file owner;
no shadow file, byte counter, physical allocation account or authority is introduced.
On a later input error, normal Rust destruction releases all unpublished vector references.
The caller's file-table entries remain unchanged and socket payload copying has not started.
The common helper is in
[`message_header.rs`](../../kernel/asterinas/kernel/core/src/net/socket/util/message_header.rs);
Unix descriptor parsing and merging remain in
[`ctrl_msg.rs`](../../kernel/asterinas/kernel/core/src/net/socket/unix/ctrl_msg.rs).

## Allocator error chain

The actual default small-layout path is:

1. OSTD `mm::heap::AllocDispatch::alloc` delegates to the original `GlobalHeapAllocator`.
2. OSDK `HeapAllocator::alloc` chooses its original per-CPU `ObjectCache` size class.
3. An empty local cache tries `SlabCache::alloc`; missing slabs use `alloc_slab`.
4. `Slab::new` propagates `FrameAllocOptions::alloc_frame_with` failure with `?`.
5. `alloc_slab` returns `None`; `SlabCache`/`ObjectCache` return `AllocError`
   after trying their remaining real slots.
6. `AllocDispatch::alloc` returns null for that error.
   `Vec::try_reserve_exact` returns an error rather than invoking `handle_alloc_error`.

The `unwrap` operations on this successful small-slab path refer to already nonempty slots
or conversion of the newly unique frame, not the physical `NoMemory` branch.
For a large layout, `HeapSlot::alloc_large` likewise propagates
`alloc_segment_with` failure as `AllocError`; the dispatch then returns null.
This is a source review of the actual allocator chain, not proof of arbitrary low-memory execution.

## Tests and limits of the evidence

Three named core tests are added, retaining all previous 341 tests (344 total, 105 required):

- A real valid 16-TiB vector reservation exceeds the original allocator's maximum order
  and is rejected immediately without exhausting RAM.
  The prior vector address, capacity, length and frame remain unchanged;
  the original one-page account stays charged across aliases and refunds only at the final frame reference.
- Actual control parsing grows through 32 credential headers, preserves the existing 33rd-message
  rejection, and handles an empty input without allocation.
- Original descriptor merge retains 253 file references in order;
  a 254-reference send is rejected before consuming payload or publishing a queue entry,
  and weak file references prove the unpublished owners were dropped.

The existing ten userspace ownership cases remain unchanged in the strict inventory;
two additional cases exercise all three Unix socket types through real syscalls.
They send 126 plus 127 descriptors in separate control headers, receive the merged 253,
check `CLOEXEC`, perform real eventfd I/O through the first/last received aliases,
close every received descriptor, and check that invalid single/multipart counts and invalid descriptors
publish no message.
The two new cases pass on Linux as reference behavior.
The complete new 12-case guest and unfiltered native kernel suite remain pending until an exact source is frozen.

The large-layout reservation verifies a real allocator rejection and vector/owner rollback.
It does **not** exercise a normal small ancillary layout failing under a controlled memory-pressure condition.
No such failure-injection qualification is claimed, and no global fault flag or panic/exhaustion scenario is installed.
Receive-side vector cloning, ownership-graph `Arc` allocation, generic kernel heap metadata,
ordinary page-table allocation, and guaranteed global recovery remain separate open work.
This slice does not charge ancillary heap objects to `memory.max` or use a recovery reserve implicitly.

Before native qualification, cfg(ktest) Clippy passed with the same 106 existing warnings,
the original 81 build-host tests passed, the six strict probe-oracle tests passed,
and the original 118-input source gate passed.
The initial compile failed because the new test lacked the `HasPaddr` trait import;
that failed compiler log is retained separately from the successful checks.
These checks do not qualify the pending guest execution.
