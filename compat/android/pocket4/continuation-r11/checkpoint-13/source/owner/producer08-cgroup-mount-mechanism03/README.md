# Owned repeated cgroup mount mechanism 03

This is a fresh once-only probe after actual mechanism02 failed. The old full
result remains FAIL: the child recorded first/fresh mounts successful and both
same-target remounts EBUSY, then the parent incorrectly rejected ordinary EOF
after the sole frame and attempted forced cleanup. The old receipt is preserved.

The new parent accepts exactly one complete nonce/child-bound frame, then EOF,
and separately requires exact child exit/reap. It drains the socket even when
the child exits first, so any queued additional nonempty frame still rejects.
EOF before the frame, malformed/extra frames, wrong nonce/PID, nonzero exit,
missing EOF, missing exit, deadline expiry, and any forced cleanup fail.
The 15-second production deadline and 3-second cleanup deadline remain fixed.

Fifteen real local socketpair/direct-child controls passed using the production
collection function, including EOF before pidfd readiness, data pending after
exit, extra data after exit, and both timeout paths. Strict probe and fixture
compilation passed. The former predicate also reproduced the EOF rejection on
a real socket. No local namespace, mount, Android, or pressure operation ran.

Root/nonce are fresh. The three mount arms, held finite own-job cgroup authority,
UID/GID/mode identity comparison, original user namespace, private propagation,
all mount/FD cleanup, Main fences and CPU1/512MiB/120s resource gates are unchanged.
The controller additionally requires the explicit peer_eof result. Local tests
do not qualify the new Pocket4 invocation or attribute the old Owner08 journal.
