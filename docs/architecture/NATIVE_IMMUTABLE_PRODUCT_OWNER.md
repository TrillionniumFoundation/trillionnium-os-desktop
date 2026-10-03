# Closed immutable Servo product-owner consumer

This source candidate implements the concrete consumer of the existing typed
Servo bridge. `ClosedImmutableNativeOwner` owns the actual pinned `Servo`, one
native `WebView`, and the Accessibility tree delivered by that view's delegate.
It consumes `ServoRuntimeCommand::into_parts` and completes each real request at
most once. It uses no file mailbox, deterministic PageRuntime, JavaScript,
selector fallback or copied actor element-name constant.

The source is a reusable adapter module. The new upstream connected target
invokes that same module through actual AF_UNIX framing, the concrete product
coordinator, default live procfs/pidfd admission, and a managed receipt journal.
The target is an explicit same-UID transient-unit qualification executable. It
is not `hepta-browserd`'s installed main, a headed desktop, a root-approved
principal broker or the retained-terminal control handoff. Exact-pin compilation
and execution of this new target remain required; workspace tests and source
validation do not establish those facts. Default production activation remains
closed. This package inherits base85a's known failing S08 semantic-action lane
without claiming its failure has been repaired. This read-only target needs none
of those S07/S08 action patches and cannot authorize an Act.

## Fixed profile and actual call direction

`closed_immutable_servo_runtime_pair` returns a non-cloneable endpoint carrying a
private closed selection and the existing creator-thread bridge owner. That
selection moves through `ServoBrowserActor::from_attested`. Both live preflight
entrypoints retain their original peer/control checks and reject Navigate, Act,
Extract and Wait before the coordinator writes requested/dispatched history.
An earlier stale, revoked, cancelled or session-policy error takes precedence;
all are refusals without engine dispatch. The direct handle path repeats the
closed guard, so callers cannot bypass it by skipping coordinator preflight.
There is no caller-provided capability boolean or arbitrary runtime injection.

The only admitted profile identifier is `immutable-read-only-v1`; persistence
must be ephemeral. Create allocates the actual WebView with one fixed data URL
containing markup and text, no script, subframe or external resource. It does not
navigate an existing view. Navigation callbacks deny every subsequent request.
The adapter supports Health, Create, Snapshot and Observe. Health identifies the
live engine consumer but does not assert a rendered or headed window. The codec's
existing `ui_mode=headed` request spelling is retained; this software-context
qualification target does not prove headed GUI fulfillment or product startup.
A later headed entry must supply the actual native rendering/window owner and
qualify that integration separately.

The native owner remains on the creator's PID and thread. Every public authority
entry checks both before touching Servo or RefCell state. An inherited child
cannot drive it; child Drop forgets inherited engine/channel state rather than
running a parent's Servo shutdown or channel destructor. Servo's own threaded
runtime is not a supported post-fork execution/shutdown API, and this does not
assert arbitrary forked native runtime correctness. The forgotten child copy's
native resources and descriptors remain until that child exits; this module
does not establish immediate descriptor cleanup for a long-lived child.

## View, document and tree lifetime

Create must reach actual `LoadStatus::Complete` and receive a bounded real
RootWebArea before success. The actor session is associated with that native
WebView ID and WebView tree ID. Later commands must carry the same session,
current actor token, immutable URL and document generation. The first observed
RootWebArea establishes the actual document tree ID; another document ID,
unexpected view, later loading transition, close or crash invalidates the owner.
No old callback or command creates a new generation or replays a request.

Snapshot and Observe traverse the current merged AccessKit tree, which includes
incremental actual delegate updates. They expose actual local node ID/tree ID,
role, name, value/text, href and raw CSS bounds. Missing values are null. Decimal
bounds are strings because the existing codec deliberately admits integer JSON
numbers only. Bounds have no action-coordinate, screen-scaling or click
authority. Observe returns the complete bounded semantic record; its fields
specification does not enable an extractor or synthesize ElementReferences.
Actor revision metadata remains distinct from the native tree revision and IDs.
None is a proof of human focus, a production app origin or a successful action.

## Deadline, cancellation and failures

The original accepted connection/request Instant stays at its existing ceiling
of 20 seconds. At first native command receipt the adapter reserves one absolute
five-second deadline and takes the minimum with the original completion
Instant. Identity checks, native work, callbacks, tree readback and final
completion spend that same interval; polling or a callback cannot renew it.
Completion here means queuing the single native result to its original bridge.
`Queued` is not an Agent response or a durable journal acknowledgment. The
bridge's later final live attestation and forwarding retain the original
20-second ceiling; this package does not claim a five-second complete wire
response. A queue operation observed late retires the bridge before its next
pump can forward that buffered value.
`next_wake_deadline` includes this original minimum. The event-loop caller must
process wakes and drive the owner before it expires. Native filesystem/Servo
calls themselves are not preempted: checks bracket them and refuse late success.

Live request custody is checked before native creation and after semantic
capture, and the existing bridge checks again before returning a buffered result
to the actor. Cancellation, peer loss, expiry, overflow, unexpected lifecycle or
engine failure cannot fabricate a successful result. One pending completion is
allowed. At most 64 updates, 256 tree nodes, 4096 bytes per node text field and 65536
canonical result bytes are admitted. Partial trees remain pending; an absent
actual document is never a successful snapshot. Ambiguous owners retire without
same-owner reconstruction or synthetic cleanup input.

## Close cannot claim pipeline retirement

The fixed PIN's `WebViewInner::drop` sends CloseWebView and removes the paint
handle. Its eventual WebViewClosed callback upgrades a weak WebView handle; no
public API provides definitive pipeline retirement after that handle is dropped.
This adapter therefore releases its local binding/tree/native handle and latches
retirement, then consumes the completion with a BrowserCrashed error. It never
returns a successful `closed` result or a success with a hidden false disclaimer.
The existing actor and receipt observer record an indeterminate terminal fact;
the coordinator remains ReplayReconciliationRequired. The test must verify this
actual managed history. There is no replay, success reclassification or same
Servo owner reuse. Releasing a local handle is not a proved rollback or shutdown.

## Source assembly and actual qualification

`tools/prepare_native_product_owner.py` accepts only a pristine pinned Servo
checkout with bounded nofollow reads of the original manifests/common helper.
It adds the reviewed local Hepta dependencies solely to the separate integration
target and copies this same reusable adapter. It changes no original Servo test
or action patch. The generated dependency lock must retain original package and
dependency identities except the existing Hepta exact libc 0.2.186 constraint
against the PIN's libc 0.2.189 resolution. Both lock digests are recorded; this is
an explicit new graph needing new actual qualification. It is not the unchanged
old Servo build. Unknown package/edge drift fails preparation verification.

The experiment carries the exact PIN's three-line `rustfmt.toml`, including
`match_block_trailing_comma = true`, with SHA-256
`9bac67039cd8f892bb9c1ff0780e6e1f2f8dbd8b6787552e4c827f9363452eda`.
Preparation checks both the original upstream configuration and the local copy
before writing any target source. Rust 1.93.0 checks the repository source with
that configuration; the actual upstream Rust 1.97.1 formatter runs normally and
the original byte-for-byte source comparison remains required. Run
`37073558008` on `772837c` failed this comparison before compilation: the source
omitted optional match-arm commas required by the upstream configuration. That
failure remains a failure; the successor's actual compilation and four cases
need a new run.

The new workflow compiles the target on Rust 1.97.1 using Servo's own
`checked-release` profile, which keeps debug assertions and overflow checks while
optimizing actual live executable hashing. It changes no production deadline or
workspace build profile. Each of the four actual case names runs in a fresh
systemd transient process with 60-second outer termination. The launcher supplies
UID/GID/unit/executable hash before start, the target uses default live `/proc`,
and missing policy/support or missing cases fail. It preserves original 20/5
request budgets and does not share old native or S08 runtime evidence. The
original normal/enforce/burst/held stimuli and the old tests remain untouched.

The ordinary workspace regression `apps/hepta-browserd/tests/immutable_profile_admission.rs` uses real AF_UNIX/pidfd/managed files with explicitly synthetic procfs service/executable facts and a callback fixture. It proves encoded profile refusal precedes durable admission and engine command, and is not Servo evidence.

The actual PIN positive case checks real semantic Heading/name data and stable native view
and document identities across Create/Observe/Snapshot, plus complete managed
receipts. Negative cases check all four unsupported operations and stale session
without durable admission; unconfirmed Close with actual uncertain history;
wrong live policy, original cancellation and expiry without native effects.
The target does not claim content-crash/headed/installed power-loss coverage.

## Remaining production integration

`hepta-agent-portd` still returns ProductHandlerUnavailable on its default
production branch, and `hepta-browserd` CLI remains a scaffold. The old accepted
oneshot queue is not a RetainedProductConnection queue and this package does not
erase that distinction. Root-owned configured policy/principal admission,
cross-UID live identity observation, original control handoff and terminal report
ownership, native human-session event ingress, actual headed window startup,
service lifetime supervision and installed qualification remain open.

The next entry can instantiate this exact adapter on the existing native event
thread, move only its endpoint to the coordinator worker, and move opaque
RetainedProductConnection plus ProductControlMonitor through a separately
reviewed bounded custody-preserving ingress. It must obtain externally approved
root policy and an actual original handoff deadline, never synthesize principal
approval or renew 20 seconds at receiver construction. No part of that future
wiring is asserted by this source package.
