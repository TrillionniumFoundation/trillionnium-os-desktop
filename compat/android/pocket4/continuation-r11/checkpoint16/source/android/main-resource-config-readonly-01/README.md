# Fixed Main resource configuration read

This is a read-only candidate, not a submitted request or new Main baseline.
Diagnostic03's complete original 96,513-byte output (SHA-256
`8545c6b1e77cd2716c3a386bd0008f1fdbb350c6261b93f4d7152b5c5fb36e23`)
contains both exact allowed paths in the actual `DropInPaths` property.
Its two kernel samples and systemd policy agree on `6144`; the immutable
activation expects `12288`. The actor, time, and configuration cause remain
unproven until the relevant actual content is read and interpreted.

Only `50-TasksMax.conf` in `system.control` and the known
`90-digitalis-validation-resources.conf` are read. No path arguments, recursive
search, other drop-ins, unit fragment, logs, activation, Android entry, child
process, service command, file write, policy change, or baseline change occurs.
Each path is walked with `O_NOFOLLOW`; each regular single-link UTF-8 file is
limited to 16 KiB. Both original descriptors remain held while each full named
path is walked again and the bytes, hash, and full metadata are checked.
The five-second collection deadline and 128 KiB output bound fail closed.
Complete original bytes are returned as base64; partial reads never qualify.

The existing fixed-path walker, bounded read, metadata, require and deadline
helpers are reused unchanged from diagnostic03. Default execution is PLAN_ONLY.
This package has no remote result. `collection_complete` only concerns the two
fixed reads; `runtime_authorized` is always false. A matching configuration
value will not itself establish who changed the live policy or authorize Main.
