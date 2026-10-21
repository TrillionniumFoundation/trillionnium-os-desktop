# Organ control broker seam

This crate is the first implementation seam for issue #111. It is deliberately
**default deny** and does not claim A05 or A07 completion.

trill-ui-broker exposes a versioned, pointer-free UI protocol. The renderer or
mobile client sees only bounded strings, digests, generations, boot-local
delivery identifiers, explicit generation fences (authority/body/resource/bridge/owner), and unknown states. It never receives raw HOS2
pointers, CapSpace handles, signer material, Agentd UDS paths, PIDs as
authority, or platform device handles.

The protocol keeps the durable Hepta key
K = (scope_id, operation_id, payload_digest) in DurableIntent separate from
the boot-local HOS2 delivery binding
D = (boot_id, delivery_id, capspace_epoch, sequence). A delivery binding is
not a durable operation identity and a process restart does not silently turn
a new D into a retry of K.

SameUidAuthenticator uses Linux kernel SO_PEERCRED data through
peer_credentials_from_unix. This authenticates the kernel-reported UID/PID
at the transport boundary only. Same-UID application identity, A05 CapSpace
grants, A07 Final-use, signer verification, and device authority still require
the future owner integration. The broker therefore grants only Observe,
OfflineDraft, and Reconcile; SubmitEffect and CancelEffect are always denied.

Each SessionHandle is bound to the Broker instance that authenticated it.
Its numeric session_id is a local counter, not a transferable credential.
Another Broker, including one created after a restart, rejects the old handle
even when its local counter has the same value. A foreign handle cannot close
a local session. Clones keep the original session identity; closing that
session invalidates every clone. This process-local binding does not replace
transport authentication or grant any effect authority.

Session admission has conservative fixed defaults for this in-process seam:
128 live sessions per Broker and 16 per kernel `(uid, pid)` peer. Changing a
client ID, nonce, or group does not create another peer quota. The global bound
also covers clients that create additional processes. These are resource
limits, not authenticated application identities or effect grants. A different
UID must still pass the configured authenticator before receiving any session.
Structural validation and authentication run before admission; capacity
rejections do not allocate a session ID or revoke an existing session.

Sessions expire after 15 minutes without a request from a valid local handle,
using the host monotonic clock. Expiration is checked before activity refresh;
an expired handle or any retained clone must authenticate a new session.
The broker keeps only a weak lifetime token, so dropping the last handle makes
its record reclaimable. Admission and request handling sweep dropped and idle
records before use; `reap_sessions()` also supports an embedding host's timer.
Reclamation after Drop is lazy, and an idle Broker retains at most 128 records.
Explicit close releases capacity immediately and invalidates every clone.
Closing or expiring a session does not change an operation's unknown effect
state or delete the separate bounded reconciliation cache.

The broker operation and replay maps are bounded process caches used to
remember an indeterminate observation and make notification replay idempotent.
They are not a second K ledger. The maps are intentionally lost on restart.
Until the original Hepta owner supplies a verified receipt, reconciliation
returns unknown and never infers success from a process exit, timeout, or UI
message.

Notifications are bounded. A dropped prefix sets reconcile_required, so a
mobile client that disconnects must pull/reconcile before presenting a terminal
effect. Offline drafts return local_only; they contain a digest and can be
stored by the local draft facility, but cannot submit an effect.

The crate adversarial tests cover protocol version/unknown-field rejection,
foreign-UID rejection, denied effect capabilities, K/D separation, generation
fences, unknown reconciliation, bounded notification loss, replay conflict,
foreign/restarted Broker handles, shared clone invalidation, global and
cross-peer admission limits, failed-admission ID preservation, last-clone
reclamation, and deterministic idle-timeout boundaries and refresh.

## Linux Session transport

The existing `trill-session` process owns one Broker and now consumes it on
`$XDG_RUNTIME_DIR/trillionnium-ui/organ.sock`. The existing host lifecycle socket
remains `session.sock`. Both listeners use the original Session instance lock,
the same checked, same-UID 0700 runtime/socket directories, and 0600 sockets.
Neither listener is an Agentd socket or an HOS2 device endpoint.

Each Organ connection carries one compact newline-delimited JSON
`ExchangeRequest` containing `hello: ClientHello` and `request: Request`.
After writing the line, the client must shut down its write half. The server
reads through EOF before admitting a session. It refuses missing terminators,
additional lines, trailing non-whitespace data, unknown or duplicate fields, and
frames over 64 KiB. Typed decoding starts directly from the original frame
bytes; it does not normalize through a JSON map that could erase duplicates.

The server reads the connected socket's real SO_PEERCRED before reading the
hello. Client-supplied IDs, roles, UID/PID values, and numeric session counters
cannot substitute for those credentials. An accepted exchange calls the same
Broker's `open_session`, `handle`, and `close_session`; close happens before a
reply write. A reply's session counter is diagnostic and cannot be presented
on another connection as a credential. Every new connection authenticates
again. Pull/reconcile still carries the existing explicit notification cursor
and K/D/fence objects; disconnect does not create a new operation or retry.

Session handles one active connection at a time and polls each listener once
per loop. Both host and Organ request/response I/O use a single 500 ms deadline,
including partial reads and writes. Incoming progress never resets that
deadline. The Organ client helper also bounds its connect, write, and reply
read within one two-second deadline; it uses the already locked socket2
0.6.5 implementation for nonblocking connect, including a full Unix-listener
backlog. An I/O error is an uncertain response outcome and causes no automatic
retry, rollback, or invented non-submission receipt.

Startup uses that bounded connect helper to probe an existing socket while
holding the original instance lock. Only an actual ConnectionRefused result
permits the original stale-socket removal. A full backlog, timeout, unconnected
descriptor, or other error refuses startup and preserves the existing socket.

The transport grants only the original broker's observe, local-draft, and
reconcile capabilities. Submit and Cancel remain denied. Reconciliation
without the original owner's authenticated receipt remains unknown. This
host IPC integration supplies no application identity, A05 CapSpace grant,
Final-use verifier, durable K/D owner, or physical-device qualification and
does not close issue #111's production integration conditions.
