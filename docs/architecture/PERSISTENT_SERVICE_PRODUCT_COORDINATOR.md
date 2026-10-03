# Persistent service product coordinator

This is a Linux Source composition candidate over the existing P1 request bridge,
P2B typed runtime and P2A original-request actor. It permanently consumes one
genuine `ApprovedServiceOwnerBinding`, one fixed `ServiceServoRuntimeEndpoint`
and one actual managed `ReceiptJournal`. The daemon still performs its existing
self-check; installed activation is disabled. No Servo embedder, native outcome,
installed image, hardware or release qualification follows from this Source.

The public product surface has 9 methods on 2 opaque owning/diagnostic structs,
plus 2 closed diagnostic enums. The transport addition is separately inventoried:
2 methods on 1 opaque denial-only owner. All existing A/B/P1 production functions,
unsafe helpers, tests, Cargo inputs and installed profiles retain their complete
original b137 bytes outside finite module/export insertions. The Source checker
requires those complete parents to restore exactly, and retains the older Source
gates through one exact, denial-only parent-view delegation.

## Original admission and wire

`serve_original_control` accepts an actual moved Root path control connection.
The permanently owned Requests binds the genuine original Control/Agent request;
P1 selects its Agent peer, action incarnation and original deadline. The product
does not take a public handler, actor factory, attestor, observer, procfs fixture,
Agent snapshot, replacement stream, receipt seal or renewed clock.

The same accepted stream executes the actual authenticated handshake, bounded
frame receive, canonical codec decode, SHA recomputation and response send. Every
physical handshake/read/send has full P1 Session and original request proofs
before and after. The codec bytes must equal the received canonical frame. The
original P1 deadline remains the maximum; a request wall deadline can only shorten
the action/wire clock. P1's original consume post remains mandatory after the
callback, including when owning per-request objects have already ended.

## Managed durability and unknown work

Startup and every Idle admission inspect the actual complete locked journal,
including sealed predecessors. A managed writer means the existing creator and
managed guard are present; it does not approve an installed directory, image ID,
anti-rollback policy or Root storage namespace. The image string is local receipt
metadata and supplies no authority. The existing full-history `contains_receipt`,
`has_unresolved_receipts`, `execution_reconciliation_facts` and `receipt_fact`
are used directly. Reopening, inspecting only an active segment or acknowledging
uncertainty never grants another invocation here.

The effect order is actual canonical decode and A preflight; whole-history
duplicate check; acknowledged Requested; acknowledged Dispatched; A's exact
original dispatch and actual bridge post; bounded canonical response preparation;
acknowledged terminal append and full fact readback; physical response with P1
pre/post; owning A retirement; original retained report; explicit Reporter and
Control custody release; observed thread completion; complete-chain Idle check.
Each append arms a sticky failure before the real write/sync/readback sequence.
The terminal seal is private, single-use, matched to the same writer and invocation
nonces, request digest, record digest, state and original deadline. A failed extra
terminal readback stays sticky, even if the previous append returned.

Failure before acknowledged dispatch records Interrupted only after an actual
Requested acknowledgement. Failure after dispatch or possible work is
Indeterminate for every effect class. A storage failure, callback unwind, response
post failure, worker failure, actor uncertainty or terminal uncertainty quarantines
this same owned chain. The product cannot reset it, reopen a fresh writer, install
a new Source or convert a receipt into replay/native-success permission. A known
Completed receipt remains preserved if a later physical send or post fails;
partial physical writes are possible and cannot be rolled back. Such failure
does not fabricate a second terminal record or claim the peer received a response.

Existing synchronous file operations can exceed a deadline before their post
sample detects expiry. The Source enforces captured-clock pre/post admission;
it does not establish hard real-time kernel latency or durable power-loss testing.
Capacity failure remains closed; transparent writer rotation or recovery is not
added through a raw writer getter.

## Cancellation, retained report and slot ownership

An independent bounded report worker owns the genuine Reporter, Control custody,
same immutable Session and original report deadline. Real `poll_cancel` alone
establishes remote Cancel. Successful A retirement also cancels the legacy token;
that ordinary token state is never treated as remote Cancel. A separate sticky
latch records real Cancel or independently observed Source failure. Local unwind
or worker denial cancels the token without inventing remote-cancellation evidence.
Cancel before token installation remains sticky when the actual token arrives.

The denial owner captures only a safe `try_clone` of that original connected
socket. Existing AF_UNIX shape, kernel peer, cookie and device/inode helpers prove
the saved FD before and after. A separately captured creator socket pair proves
actual creator credentials and cookies. Consuming shutdown affects only that same
saved socket with `Shutdown::Both`; there is no raw FD, read/send, reconnect,
boolean permit, new dependency, new unsafe block or new deadline. Drop merely
closes the owner copies and never shuts a socket down. After real Cancel already
revokes the action verifier, wake pre/post uses the original independent Session
and Reporter ceiling, rather than attempting to grant action permission again.

Readonly B registration/active/completion scopes retain request verifier Arcs;
those verifiers do not own the P1 active slot. The actual slot owners are the
receiver, A's moved original Binding and Reporter. The receiver ends during P1
receive. A must retire after its actual final bridge post before a terminal report
can revoke action custody. If A retirement refuses, this product discards the
terminal seal and quarantines; only the NoTerminal diagnostic cleanup is possible.
`send_remote_report` alone still retains Reporter's slot Arc. The worker explicitly
drops Reporter, Control custody and wake before private done publication. Idle
also requires observed worker thread completion and full original consume post.
No unbounded join, manual P1 slot reset or renewed report budget is present.

`NoTerminal` records the absence of a private terminal seal. It is never an
Interrupted/Indeterminate report or delivery/recovery authorization. Diagnostic
observations do not supply native, replay, Source or installed authority. A stale
completion retains only its immutable readonly original scope; later registration
cannot replace its nonce/session/request/clock or revive its ended action.

## Verification and remaining qualification

`contracts/approved-service-product.v2.json` and
`tools/verify_approved_service_product.py` freeze actual public/private inventories,
whole function tokens, production bytes, finite parent inverses, effect markers
and unchanged originals. The Python corpus mutates original proof checks, full
history barriers, private seal identity, cancellation state, slot/drop order,
original clock, cookie capture, exports and activation claims. Passing these
checks proves only the finite Source correspondence and rejection corpus.

Authored ordinary Rust units use genuine UnixStream mechanics and real managed
temporary storage. They cover Drop without shutdown, same-socket consumed denial,
cookie drift refusal, cancel/token distinctions, whole-chain predecessor duplicate,
unresolved/terminal-uncertain history and predecessor substitution. They fabricate
no P1 Source, Binding, product seal or native success. Compile-fail examples cover
private fields, unavailable private seal, non-Clone ownership and absence of the
weaker `BrowserRequestHandler`. No Rust execution is claimed by the Source gate.

Independent qualification is still required: strict locked Rust compilation,
ordinary units and doctests; two genuine default-proc Control/Agent invocations
after the first request's 20-second ceiling using the same unique Requests/A/PageOwner;
old readonly completion held across second registration and denied; actual
cancel/EOF/expiry/unwind/storage failure and busy slot corpus; true same Servo/WebView
Native60 and effect guards; default-disabled installed route and Root storage/image
approval; G6 recovery, hardware and release evidence. Source acceptance does not
close these production blockers.
