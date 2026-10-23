# Unix datagram physical payload ownership

This slice follows the exact, separately qualified memory-controller source
`2c7a8543ea49e7d87e8915f2b3463f5d2119c020` and its documentation receipt
`368e1570a12f893bb2054f1abf694861bbdfc8e0`. Its own native execution is pending.
The prior 316-test run does not qualify this new source.

## Allocation and publication contract

The original [`MessageQueue::try_send`](../../kernel/asterinas/kernel/core/src/net/socket/unix/datagram/message.rs)
formerly allocated every payload with `Vec<u8>`. It now holds `MessagePayload`,
which owns an original `Segment<UserPageMeta>` and the exact initialized byte
length. The segment uses the original physical allocator, not a new pool or a
byte-count shadow ledger. Admission uses the sending initiator's `current_owner`
and therefore the existing family budget and captured cgroup ancestor chain.
An empty payload owns no physical page. Nonempty messages admit the page-rounded
size, up to the unchanged 65536-byte datagram limit (16 pages).

The original sleeping queue mutex continues to serialize capacity checks,
copying and publication. A family/ancestor denial happens before advancing the
reader or taking auxiliary messages. Physical allocation failure refunds its
reservation. A user-copy fault drops the unpublished segment and refunds its
actual metadata tokens; no partially copied datagram enters the queue. Readers
are bounded to the initialized payload length, so uninitialized page padding
is never returned. There is no new unsafe code or reserve authority.

A queued message retains its original sender's charge even if the sender
migrates, exits, or transfers its socket. MSG_PEEK reads the same pages and does
not add or remove a charge. A consuming receive, including truncation, drops
the queued payload. Closing the actual receiver clears all queued payloads even
if a peer still retains its MessageQueue Arc. The final physical reference,
including any original Segment alias, performs the refund. A failed receiver
user copy retains the queued message and its charge, as before.

The original payload byte limit, zero-length-message behavior, receive flags,
packet boundaries, EAGAIN for byte-capacity backpressure, EMSGSIZE for oversized
payloads, and ECONNREFUSED after receiver closure are preserved. Physical
contiguity is still required for this bounded segment; fragmentation can return
ENOMEM without exhausting all free memory.

## Exact test and development entry

Five tests are added to the original unfiltered core suite under
[`datagram::message::tests`](../../kernel/asterinas/kernel/core/src/net/socket/unix/datagram/message/tests.rs):

| Exact suffix | Original objects and observable result |
| --- | --- |
| `payload_peek_truncation_and_alias_keep_original_physical_charge` | Cross-page payload, actual queue, bounded peek, MSG_TRUNC, retained real Segment alias, exact final-frame refund. |
| `ancestor_quota_denial_does_not_consume_reader_or_publish_datagram` | Unlimited family plus one-page ancestor, failed second datagram, unchanged reader and queue length, receiver-drop refund. |
| `actual_user_copy_fault_refunds_unpublished_pages_and_preserves_receive` | Associated and activated real VMAR, mapped first page followed by unmapped page, actual partial-copy page fault, complete unpublished refund, actual receive-copy fault retaining the packet. |
| `migration_and_receiver_close_refund_captured_domains_with_retained_queue` | Original account binding change under membership lock, two captured domains, real receiver destruction with retained queue Arc, exact refunds and post-close rejection. Process migration itself is qualified separately by the memory-controller suite. |
| `empty_payload_and_original_byte_capacity_preserve_datagram_boundaries` | Empty payload owns zero pages, original full 64-KiB packet consumes 16, original byte/size backpressure, distinct empty-message boundary and unchanged output bytes beyond the packet. |

Tests run on original Core threads with associated real VMARs. Completion is
asserted separately so panic-to-oops cannot pass a parent test; original RCU
witnesses handle mapped source-page destruction. No allocator, physical frame,
quota, user-copy, or queue operation is replaced with a host model.

The strict checker keeps every prior name, requires core **321 / 82 required**
for this branch, and still requires full OSTD **229**, allocator **20**, and
MLSDisk **15** as independent suites. Other branch additions must be merged by
name and source, not counted as executed. Use the original
`support/build/ktest/run.py` with all four crates, unchanged N0 profile and
original deadlines. Host anti-forgery tests and `verify-source.py` remain
separate evidence. Targets and temporary files belong under `/data`.

The first static pass compiled the real `cfg(ktest)` core with the pinned
nightly toolchain; Clippy also completed (106 existing warnings, not a
warning-free claim). All 44 host anti-forgery tests and the 118-path build-input
verifier passed. Changed-file rustfmt and diff checks passed. None of these
results is a QEMU execution or a source-bound native qualification.

## Remaining actual resource gaps

This is payload-page attribution, not whole-socket or heap accounting:

* `Inner.messages: VecDeque<Message>`, Arc/socket/address objects and queue
  metadata still belong to the original kernel heap. Zero-length messages do
  not consume `total_length`, so the current queue has no message-count bound.
  A separate fix must impose explicit backpressure without increasing the
  existing payload byte limit; this slice does not call that issue closed.
* [`AuxiliaryData` and `FileMessage`](../../kernel/asterinas/kernel/core/src/net/socket/unix/ctrl_msg.rs)
  retain `Vec<Arc<dyn FileLike>>`, with meaningful destructors and descriptor
  ownership. They cannot be correctly charged by inventing a physical token
  from their Vec length. Original descriptor limits and control-message count
  checks are not physical heap admission.
* The current SCM_RIGHTS cycle check recognizes `UnixStreamSocket` only. A
  Unix datagram socket may be retained through its own or another receiver's
  queued FileLike Arc. Without a collector or a complete admission policy,
  these cycles can prevent destruction. Self-only checking would not close
  multi-socket cycles. This is a separate high-priority lifecycle repair.
* Page tables, other kernel heap allocations, TCP/IP, unrelated buffers,
  ancillary-object storage and unified fallible recovery remain open.
  `global_recovery_guarantee = false`.
