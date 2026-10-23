# Bounded acyclic UNIX descriptor ownership

## Problem and supported behavior

The original Unix datagram path permits `SCM_RIGHTS` to retain its own receiving socket, or two receiving sockets to retain each other. The privileged stream exception has the same problem. Actual original-kernel diagnostic tests on `adbc15a9d1f8e7490240923b681ae694f815479b` observed both datagram cycles after all external socket owners were dropped; an actual receive broke each cycle. That diagnostic run later failed a separate VMAR test fixture and is not a complete suite qualification. Its failed record and same-ELF diagnosis are retained in [the fixture report](UNIX_DATAGRAM_FIXTURE_DIAGNOSIS.md).

Rejecting every Unix socket descriptor would break the existing Notes bootstrap. Desktop `ui/session/src/notes_bootstrap.rs` and `ui/core/src/notes_private_unix.rs` send an effect stream and a recovery datagram descriptor; Hepta agentd's bootstrap verifies those exact types. The all-Unix-descriptor rejection candidate `fa92354dc95d071426716fc9656ce840c7f0ea5f` is parked and is not the implementation here.

This implementation admits acyclic persistent ownership, including both original Notes descriptor types. A proposed cycle returns `ELOOP` before consuming payload bytes or publishing ancillary data. There is no privileged exemption. This is bounded admission, not Linux's in-flight garbage collector: programs intentionally constructing cyclic Unix socket graphs are unsupported. Control-message aliases may conservatively retain an admission until the final alias is dropped.

## Original owners and publication order

[`ownership.rs`](../../kernel/asterinas/kernel/core/src/net/socket/unix/ownership.rs) stores identity slots and adjacency only. It holds no socket, queue, process, page or generic `FileLike` object. The persistent edges correspond to existing strong owners:

| Existing owner | Actual owned object | Edge lifetime |
| --- | --- | --- |
| Datagram socket's receiver | Local message queue | Receiver's real queue reference |
| Connected datagram socket | Remote queue | `RemoteQueue` reference, including transient clones |
| Stream/seqpacket socket | Original shared endpoint pair | The socket's `Connected` value |
| Listening socket | Original backlog | `Listener` reference |
| Backlog | Pending shared endpoint pair | Until actual pop or close |
| Queued auxiliary data | Transferred Unix socket file | Through queued/received/peek control owners |

The shared endpoint pair is one graph identity because either endpoint retains both original ring buffers and both ancillary queues. Treating each endpoint as an isolated queue would miss cycles. A datagram socket's remote queue is also a real strong reference and cannot be omitted.

An edge is admitted before the corresponding persistent owner is published. `connect`, socket creation, listener creation and accept use their original state/queue locks. Accept prepares the new socket identity and edge before popping; a budget error leaves the pending connection intact. Once popped, the old backlog edge is replaced. A datagram reconnection admits the new remote edge before replacing the old queue; a rejected cycle leaves the old connection unchanged. Its replaced queue and edge drop after the remote lock is released.

The original `AuxiliaryData::from_control` validates descriptor count and credentials. Actual destination queue/pair admission happens later, after capacity preflight and before user-copy. A copy fault, physical-page quota rejection or full byte ring releases unpublished graph leases. A successful partial stream write publishes the lease for the real written prefix. An empty stream write publishes no ancillary data.

`FileMessage` and `AuxiliaryData` retain graph leases alongside their actual files; files drop before leases. `MSG_PEEK` clones the lease and file references; receive moves them. When a received control message becomes a new outgoing caller-rooted message, its old lease is released and its eventual destination admits a new edge. File-table installation creates caller roots, not persistent queue-to-file edges.

## Bounded transaction and allocation contract

The global graph has 1,024 identity slots and 4,096 distinct directed edges. Duplicate references share an edge with an explicit reference count. Slot generations prevent identity reuse; generation exhaustion retires that slot. Node, edge or reference-count exhaustion returns `ENOBUFS`. Consequently ordinary `socket`, `socketpair`, `connect`, `listen`, accept or `sendmsg` can report resource exhaustion. Closing the last actual owner/lease returns its slots. This is a finite global capacity policy, not a Linux compatibility claim or a configurable authority grant.

One IRQ-disabled spinlock serializes reachability and all edges in a single send batch. Reverse reachability visits at most 1,024 nodes and 4,096 edges using fixed scratch arrays; all per-batch loops are bounded by the original 253-descriptor limit. Edge insertion/removal also use bounded tables. Opposite concurrent admissions therefore cannot both observe the prior acyclic graph. Failed batch insertion rolls back its admitted prefix, including duplicate-edge reference increments.

Original object lock → graph lock is the only order. The graph lock never acquires an object lock, allocates, waits, calls a callback or drops an object reference. Lease metadata is allocated beforehand; identity references are dropped after releasing the graph lock. The identity `Arc`s themselves do not refer to leases or real objects, so the admission metadata cannot recreate the socket cycle.

The graph does not add a second physical-memory ledger. Payload frames and stream buffers still use the original frame metadata owner and hierarchical memory admission. Queue metadata, ancillary objects, general kernel heap, page tables and global recovery capacity remain outside that physical-page coverage.

## Indirect file ownership review

The current epoll interest keys and ready entries are weak references; a real epoll-watching-receiver regression verifies final socket/epoll release. Pidfd stores a weak process reference. Proc descriptor entries use weak process/thread ownership, and VMAR snapshots are weak. Inotify watches are weak inode references; socket path inodes do not hold socket files. `fsconfig` descriptor values remain unsupported. Eventfd, timerfd, signalfd, pipes, TTY/PTY and existing device handles do not persist arbitrary `FileLike` references to Unix sockets. Any future file type that adds such an owner must extend this model before it is accepted in `SCM_RIGHTS`; this review is source-specific.

## Tests and qualification boundaries

The unfiltered core gate retains all prior 327 tests and adds 12 named regressions (339 total, 100 required). They exercise actual graph capacity and rollback, last-lease identity lifetime, stale generation rejection, original socket self/cross/future-connect checks, concurrent opposite sends, peek/received aliases, Notes stream+datagram transfers over stream and seqpacket, mixed transports, real user-copy and physical quota failures, full/partial stream writes, ordinary file/pipe/eventfd forwarding and epoll weak-reference behavior. Original OSTD 229, allocator 20 and MLSDisk 15 suites remain required. No old tests are removed or filtered.

[`unix_ownership/probe.c`](../../tests/workloads/linux/unix_ownership/probe.c) adds ten actual userspace cases through original syscalls. It covers Notes descriptor transfer and subsequent endpoint I/O, pending listener cycles versus accepted connection transfer, future datagram connect, both endpoints of all three Unix types, the 128 empty-seqpacket policy, and two forked processes concurrently creating opposite edges followed by real wait/reap. Its runner uses an isolated 512 MiB single-vCPU QEMU guest, a fixed 120-second deadline, exact case inventory, raw exit 33 and boot/probe completion markers. Six host negative-oracle tests reject duplicates, substituted/missing cases, incomplete summaries, timeouts and marker-only success.

The source passes cfg(ktest) Clippy (106 pre-existing warnings), all 81 original build host tests, all six new probe-oracle tests and the original 118-input source gate. The first host attempt found 15 missing tracked historical-evidence files in a sparse checkout; that failed log is retained. The checkout was fully materialized and the unmodified 81-test suite then passed. At this source stage the candidate has compilation/checker evidence only; the new 339-test native run and ten-case userspace run are pending. The Linux `--linux-notes-reference` run executes only the two positive Notes cases and is never accepted as kernel qualification. Likewise the prior `9cb60931` 324-test result does not qualify these changes. No hardware memory-pressure, full Linux GC, power-loss or general AI-organ production readiness is claimed.

After freezing an exact source, run the original full four-crate suite with its source-built OSDK, then build its ordinary kernel and run:

```text
python3 tests/workloads/linux/unix_ownership/run_guest.py --kernel <same-source-ordinary-ELF> --initramfs <same-source-initramfs> --output <new-evidence-directory>
```

Keep source snapshots, compiler/checker failures, raw serial output, QEMU results and retained ELF hashes. A user-space probe failure must not be converted into success by a completion marker or a relaxed timeout.
