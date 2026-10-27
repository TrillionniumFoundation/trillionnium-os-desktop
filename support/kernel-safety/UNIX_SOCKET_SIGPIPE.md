# Unix STREAM SIGPIPE and per-call suppression

Unix STREAM sends queue SIGPIPE to the calling POSIX thread only after a final
EPIPE result with no successful progress and without MSG_NOSIGNAL. The signal
is queued after the blocking/retry operation and after its inner socket guards
have been released. Successful, partial, EAGAIN and non-EPIPE results do not
queue this signal. Kernel and test callers without a current Thread or without
a PosixThread keep the original error result and have no user signal target.

MSG_NOSIGNAL suppresses only this send's SIGPIPE and preserves EPIPE. It does
not change the process-wide signal disposition or another call's behavior.
Both the Unix socket and sendmmsg entry point remove only this known flag from
their existing unsupported-flag diagnostic masks. Other unsupported flags and
the original raw-flag parsing are unchanged. This does not implement TCP/vsock
SIGPIPE or any additional send flag.

Unix SEQPACKET shares a Rust socket implementation with STREAM but does not
inherit STREAM's signal rule. Linux's Unix SEQPACKET path delegates to datagram
sending; applying a blanket all-socket EPIPE signal rule would be incorrect.
References: [send(2)](https://man7.org/linux/man-pages/man2/send.2.html) and the
[Linux stable Unix socket source](https://github.com/gregkh/linux/blob/v6.2.10/net/unix/af_unix.c).

A socket writev vector is one logical send operation. The syscall passes the
existing validated VmReaderArray to sendmsg once. Splitting the vector into
file.write calls could otherwise queue SIGPIPE on a later EPIPE after earlier
bytes were accepted, while writev returns a positive count. Empty vectors and
initial user-iovec validation keep their prior behavior. Later copy faults
retain successful progress. Non-socket vector loops and offset pwritev's
ESPIPE boundary are unchanged. Each sendmmsg message remains a separate send;
this is not a rule suppressing all signals whenever a batch returns a positive
message count.

Unix STREAM payload copying commits the prefix actually copied before a later
user-memory fault. The private transaction copies each physical ring segment
and uses the fault's copied-byte count; it does not infer delivery from reader
consumption. A fault before any copied byte remains an error with no published
data. The wrapping second segment retains progress from the first. Both the
plain stream and stream-with-ancillary paths use this transaction; SEQPACKET,
the shared producer helper, TCP and UDP keep their prior copy paths.

The production queue uses the same current-thread UserSignal construction as
the local FIFO implementation. It does not look up another process or inspect
procfs. One Core ktest exercises its no-POSIX-target path without an unwrap.
Three additional Core tests use real rings to check a linear fault prefix,
wrapping faults, a zero-copy error and the packet path without a partial commit.
The real guest probe in tests/kernel/unix-signal has 42 closed cases with owned
default-disposition children, handlers, per-call suppression, SEQPACKET,
nonblocking partial writes, partial writev, empty vectors, later bad user data
and offset writes. Its C and runner bytes are frozen before the production
repair. Preserve the actual QA-only before failure and independently verify
the same test after the fix. Older network tests which ignore SIGPIPE remain
unchanged and do not establish default-disposition coverage.

Console warnings are synchronous and can add IRQ-disabled work, but removing
these warnings alone does not prove a Native Hepta timeout cause or authorize
effects. Original Native 500ms bounds, source profiles, kernel controls and
guest parameters remain independent gates. A changed Unix socket owner must
not be admitted by rewriting an older fixed source profile.
