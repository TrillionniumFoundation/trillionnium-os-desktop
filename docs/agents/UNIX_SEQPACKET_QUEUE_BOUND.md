# Unix seqpacket message-slot admission

This change bounds the original `Connected::Inner::all_aux` queue at 128 messages per direction for `SOCK_SEQPACKET`. Every packet, including a zero-length packet without SCM_RIGHTS, consumes one slot. The existing 64 KiB byte ring and its existing oversized-packet rule are unchanged. This is a documented local resource policy, not a claim of identical Linux queue sizing.

## Ownership and observable behavior

[`Connected::try_write`](../../kernel/asterinas/kernel/core/src/net/socket/unix/stream/connected.rs) checks the slot count and uses fallible `VecDeque::try_reserve(1)` before changing `has_aux`, copying user bytes or moving control data. A full queue returns `EAGAIN`; metadata allocation failure returns `ENOMEM`. The existing socket blocking loop waits on the original pollee. A full seqpacket queue suppresses `POLLOUT` until a message is consumed. Empty queued seqpackets report `POLLIN` even though the byte ring contains no bytes.

Consuming an empty packet wakes writers after freeing its actual auxiliary slot. `MSG_PEEK` does not release a slot. Peer close retains the original shutdown notification and `EPIPE` result. Stream sockets still use their original byte-based admission; empty stream writes publish no auxiliary record.

The two original ring-buffer segments retain the physical owner introduced by IPC frame accounting. Queue nodes and ancillary objects remain ordinary kernel heap allocations; the new count bound is not byte accounting and does not qualify global heap, page-table or recovery memory guarantees. SCM_RIGHTS reference cycles require the separate original-owner admission work; this patch does not claim to resolve them or disable Notes socket transfer.

## Development and exact validation boundary

Three named kernel tests in [`connected/queue_tests.rs`](../../kernel/asterinas/kernel/core/src/net/socket/unix/stream/connected/queue_tests.rs) use the actual endpoint pair, original buffers, eventfd control ownership, original socket polling and real sleeping task send path. They check 128 empty packets, peek versus consume, unchanged payload/control state on rejection, final frame release, and writer wakeup on consume or close. The fixture reads credentials from a real unstarted original process; it grants no permissions or fake socket state.

The full unfiltered core gate increases from 324 to 327 tests, with all earlier 85 required names plus these three. The ordinary OSTD 229, allocator 20 and MLSDisk 15 suites and their original capacities/deadlines remain required. Host checker tests and cfg(ktest) compilation are separate checks, not execution evidence. At this commit the three new seqpacket tests have not run in a guest.

## Prior data-page/queue run (source-bound)

The preceding source `9cb609318c16fb4ad8d5352dfc57465df92688e0` / tree `5cca874fa37d75279e539bdb868ae936925b5869` passed the original four suites in `/data/asterinas-audit-build.8tdrjboi/unix-datagram-native-9cb-01`: core 324/324 (85 required, no skipped/filtered tests), allocator 20/20, MLSDisk 15/15 and OSTD 229/229 (the original three TCG VMX soft skips). All four raw QEMU exits were 33; outer exit was 0 after 337.113 seconds. Before/after source manifests were equal. The retained core ELF SHA-256 is `43e5a12d31db3296727de464c5123a6afbb176ea8ace288136733d753101e672`; its serial SHA-256 is `6d8f85e872cd8301ab1b6fcbb61059eb5c012ac696c5757358478745eed9bc2d`.

That result covers the five datagram frame-owner and three datagram queue-bound regressions. It does not cover this later seqpacket patch. The earlier `adbc15a9` failed run and same-ELF fixture diagnosis remain preserved; see [fixture diagnosis](UNIX_DATAGRAM_FIXTURE_DIAGNOSIS.md).
