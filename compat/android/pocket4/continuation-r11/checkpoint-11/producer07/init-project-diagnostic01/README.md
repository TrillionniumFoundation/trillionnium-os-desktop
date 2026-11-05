# Init PROJECT failure diagnostic revision

The original owned NORMAL invocation failed after authenticated init HELLO,
broker READY, and PROJECT send. It did not reach PROJECTED, COMMIT, DONE, or
enrollment. Its original result remains failed. Exact unit/process cleanup and
the Main fence passed. The original C stderr has no stage or errno; the cause
within PROJECT is not yet established.

This revision only adds failure diagnostics. It preserves ABI 1, the 128-byte
messages, nonce and credential checks, one-shot release, the three directory
ownership/mode predicates, O_EXCL target creation, socket capability identity,
bind flags, post-mount identity, deadlines, and exit 127 on failure. It grants
no new authority. The projection and enclosing transport cleanup now preserve
the error reported before closing descriptors. Predicate-only failures receive
an explicit EPERM or EPROTO instead of a stale errno.

One bounded stderr line records a fixed source-controlled stage and errno.
Where the existing validation already read stat data, it also records dev/ino,
uid/gid, and mode. No path, content, extra scan, thread, retry, or successful
handshake logging is added. The original authentication and failure decisions
are unchanged. The inherited LD_PRELOAD compatibility library remains in use;
this revision does not bypass its functions or silently replace mount with a
different syscall.

Local strict production-DSO and fixture compilation passed. Seven controls use
owned temporary directories and an explicit mount seam to verify directory
mode refusals, target O_EXCL, errno preservation despite close overwrites,
post-mount type refusal, and line bounds. Removing errno restoration makes the
control fail. These are not real mount/Android/namespace controls.

The original and revised 20-case transport fixtures both failed at their first
case locally because creation of an AF_UNIX SOCK_SEQPACKET listener returned
EPERM. Socketpair HELLO had completed. This is preserved as a local execution
limit, not a transport PASS or an Android source failure. The device build must
run the revised original 20 transport cases, their close-errno variant, and the
seven diagnostic controls before a new exact Android DSO is eligible.

The next actual attempt must use a fresh package/state/unit/attempt nonce and
fresh Owner generation, the newly built DSO's exact hash, and the original
finite-domain/Main-fence/exact-cleanup gates. No old nonce or cell is retried.
This diagnostic revision by itself does not qualify the Owner lifecycle,
LMKD pressure, RC reload, installed supervisor, or any commercial application.
