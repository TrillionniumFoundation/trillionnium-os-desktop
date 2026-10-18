# Guest runner cancellation follow-up

The diagnostic runner now handles SIGTERM and SIGINT by cancelling queued work
and stopping/reaping its directly owned QEMU children. The signal handler only
sets an Event. Workers check it before launch and during bounded polling;
Popen publication and every exit path remain inside worker finally cleanup.
Shutdown cancels queued futures and waits for active cleanup. Partial serial
snapshots remain evidence, aborted attempts cannot qualify, and the CLI exits
128 plus the signal. No process-group, proc discovery or subreaper framework
was added.

Actual fixed-source validation used the original accepted Rust kernel and the
same pinned SCM_RIGHTS ELF case. At the observed unsupported-CMSG flag path,
SIGTERM returned CLI143 in 0.164 seconds, SIGINT returned CLI130 in 0.164
seconds. Each run observed an owned QEMU Popen receipt through pidfd: the fd
was not ready before cancellation and was ready after the CLI exited. QEMU
was wait/reaped with its real cleanup exit0; the queued second case never
started. Both summaries are explicitly aborted, with zero matches.

A separate three-case actual guest run preserved normal behavior: dynamic.smoke
matched with raw33, static.fd_limit failed ELF exit20 with raw33, and
static.scm_rights timed out with compatibility rawnull while its child was
terminated and reaped with actual cleanup exit0. Driver exit2 is retained.
All five captured serial snapshots passed compressed and raw-byte hash checks.

The complete earlier 24match/2failure/2timeout result remains frozen at
commit d85b1e091143a9c4f004c024f433a58188455105; it was not rerun or upgraded
for this code change. This follow-up is two real signal checks plus three
repeated focused cases, not additional workload types.

Two original host-only dummy attempts are retained as inconclusive. Their
/proc numeric PID lookup was invalid: the fixture PID pathname did not exist
even before the signal, so false alive fields cannot prove death, absence or
a leak. No original leak reproduction is claimed. Final signal validation
uses owned Popen/pidfd identities and does not inspect numeric proc identities.
The source-level default-signal/queued-work concern motivated this bounded
cleanup fix without inventing an old observed failure.

No A04, kernel-core or OSTD source changed. raw-logs.tar.gz retains partial
and complete serial, manifests, launch records and results. source.tar.gz
retains the exact fixed entry, validation harness and original fixtures;
each archive has a fully verified member hash index. Old root evidence and
its original master manifest remain unchanged.
