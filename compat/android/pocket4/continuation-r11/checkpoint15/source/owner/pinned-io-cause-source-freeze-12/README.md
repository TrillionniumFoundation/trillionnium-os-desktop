# Producer12 retained pinned-I/O failure provenance

This isolated source freeze starts from the exact two producer11 Rust inputs
recorded by the successful actual compile. Owner11 remains an actual failed
first-ACTIVE attempt. Its original retirement is incomplete; the later exact
outer unit cleanup is separately complete.

The actual relay reason is open relative pinned directory / ENOENT. That label
is from open_at, not the separate openat2 public-projection lookup. No path,
process role or ordering with process death was retained in the original
message. This revision preserves the name, unchanged flags, optional identity
of the held base and original errno on an open failure, then adds static role
context at existing validated call boundaries. It does not ignore ENOENT,
retry a PID/path, change credentials, replace a namespace, or permit a grant.

Three Rust tests use real private files, a rejected symlink and an exact owned
child/pidfd/proc FD, respectively. They are source-only here; Rust is unavailable
locally. They must be compiled and executed in a matching candidate. The child
test does not authenticate a peer or claim lifecycle-origin qualification.

The independently identified retirement send-before-drain issue is excluded
from this immutable diagnostic snapshot. A separately reviewable combined
candidate may add that repair, keeping all nonce, scope, AUDIT, flag and exact
broker-exit checks. No device work, Main change or production qualification is
performed by this snapshot.
