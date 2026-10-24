# Original Hepta → Session host composition

This Linux host library connects Desktop's existing `ObjectiveSubmission` state
machine to Hepta's original `ProductionObjectiveSender` capability. It is a
trusted embedding component. Its typed host accepts bounded user intentions
through an injected original authority. It provides no issuer or database owner.
An unconfigured standalone Session remains unavailable.

All original Hepta dependencies and Hepta-carried patches in this crate are
fixed at `52456c309f64ee80e7e377f774445c5dfe0523c9`, tree
`9d0949a72d064cc2222859780c6ccd9a22c8e575`, matching the native UI source.
The [fixed cross-repository map](../../docs/SOURCES.md#hepta-native-organ) and
[latest scoped executions](../../results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)
keep component tests separate from the final combined workspace, installed
production authority and device qualification. The local `hepta-os-observer`
dependency retains its own protocol contracts; it has no Hepta Git dependency.

The optional native App Server text path has a separate
[development and technical handoff](TEXT_SESSION.md): actual source entry
points, feature/build commands, authenticated inputs, stream outputs and
same-identity recovery. It uses the original Root/Agentd text worker and does
not route model chat through the finite literal Notes compiler below.

## Sources and ownership

| Responsibility | Existing owner |
| --- | --- |
| Original signed Objective envelope and task identity | Original Hepta issuer and Objective ingress |
| Agent, generation, expected peer UID/PID and private endpoint | Trusted original host composition |
| Original writer, lease, authority and live verifier | `AgentdConfig::original_objective_sender` and the installed `AgentdProductionWriterHost` |
| Exact request, permanent send fence and append-only observations | `codex-hepta-memory::ProductionObjectiveSender`, in the original CognitiveStore |
| Independent durable, current recovery cut | Embedding's `ObjectiveSenderCheckpoint` implementation |
| One local sending opportunity and receipt-only retry | `ui/session::objective_submission::ObjectiveSubmission` |
| One bounded submission or history socket call | `services/hepta-os::objective` |
| View projection and concrete capability adaptation | This crate's `lib.rs`, `owner.rs`, `receipt.rs` and `recovery.rs` |

There is no second SQLite database, file ledger or scheduler,
authority store, model call or device executor in this crate. A checkpoint
implementation is a required generic capability; the library supplies no
production default. A test verifier or echo checkpoint cannot qualify a
production deployment.

## Embedding contract

The original Agentd host first assembles its original production inputs and
writer. Its `AgentdConfig::original_objective_sender` method borrows that exact
installed writer through the restricted capability. Do not open a second writer
to construct this adapter. New requests use the original composition profile's
binding between Agentd spawn generation and writer lease generation; historical
requests retain their original generation after recovery.

Construct and call `HeptaSessionSubmission` on the embedding's existing bounded
blocking worker, outside any entered Tokio context. Supply the independently
running original Hepta multi-thread runtime handle. The adapter uses that handle
for original asynchronous persistence and creates no host runtime or worker.
The existing transport retains its own bounded one-shot socket runtime. The
original runtime must remain alive until all adapter operations finish.

`ObjectiveSenderOrigin` is immutable. The same value constructs both the original
owner's retained request and the transport endpoint, preventing an initial
retention/transport rebind. Retention uses a caller-selected nonzero cooperative
asynchronous deadline configured to at most ten seconds. The original sender
separately configures its checkpoint deadline to at most five seconds. Tokio's
timeout cannot preempt a blocking synchronous callback or a future's blocking
poll, so these settings are not absolute wall-clock limits. The embedding must
keep verifier, clock and validation callbacks bounded and nonblocking, and must
ensure checkpoint cancellation cannot leave a background publication running.
A deadline after a possible commit is `PersistenceUnknown`; it never grants
another send.

Callers must obtain endpoints, expected peer identity, authority and the exact
signed envelope from the original trusted host. Structural parsing here does not
verify the signature or issue permission. Raw request bytes and endpoint paths
are private to the adapter; the public view contains metadata only.

## Request and recovery lifecycle

1. `prepare` parses the unchanged original envelope, verifies the complete
   identity against the original owner model, durably retains the exact bytes and
   permanently occupies their original send opportunity before returning.
2. `submit_once` first consumes Session's local permission. The original writer
   then consumes its local ticket and rechecks current authority before any
   transport I/O. A refusal at either boundary does not rearm the request.
3. The original transport makes one attempt. The adapter hands its immutable
   observation to the original owner. A store or checkpoint failure may leave the
   observation only in memory, or committed without a known independent ACK.
4. `retain_observed_submission` and `retain_observed_history` repeat only the
   immutable observation handoff. They never resubmit the Objective or rerun a
   history query.
5. `cancel_before_send` consumes only this unused local opportunity. It does not
   cancel an admitted or running Hepta Objective. Cancellation after start needs
   the original RunCancel owner. The optional typed host below invokes that owner.
6. After restart, enumerate retained requests with the original sender's bounded
   `retained_page` API. Pass an unchanged returned request to `recover_unknown`.
   It creates no submission transport and no sending or local cancellation
   permission. Recovered metadata comes from the original `snapshot_acknowledged`
   operation: reading the snapshot and obtaining the independent current-cut ACK
   share the original write transaction. A local committed row whose independent
   ACK failed cannot become confirmed merely by constructing a new facade.
   While that ACK remains unavailable, recovery returns `PersistenceUnknown`.
7. `reconcile_once` performs an explicit original history query against an
   independently supplied current trusted endpoint for the same agent. It leaves
   the original request and historical generation unchanged.

The original retained enumeration is a bounded live keyset, not a frozen global
snapshot. Follow its opaque owner-bound cursor; if concurrent inserts can occur
before the cursor, restart enumeration from `Beginning`. The host owns this
scheduling policy. This crate creates no polling task.

## What a view establishes

Admission, historical publication, durable observation retention and local send
phase are separate facts. Admission or a publication is not run completion, an
effect receipt, device state or evidence of a Notes document's durability.

An admission response contains no publication sequence and cannot become a
history anchor. The adapter only derives an anchor from a matching historical
publication already retained by the original owner. Publication matching includes
the original canonical signed-body SHA-256, the full original message identity,
bounded publication sequence and the original typed outcome.

The first observed publication remains visible when a later query is unknown.
On recovery, the original first retained observation, including its response
generation, takes precedence over a new in-memory query. A contradictory later
publication or a wrong signed-body digest is rejected before append and is
projected as an unknown protocol mismatch, rather than displayed as a newly
established publication. The prior original publication remains intact.

History validation and append share the original owner's `BEGIN IMMEDIATE`
transaction through `retain_observation_checked`. The callback only projects
bounded retained metadata and compares the original publication; it performs no
I/O, waiting or store re-entry. Two recovered facades using this adapter therefore
cannot both retain contradictory first publications after separate stale reads.
An exact observation retry is checked again and re-acknowledged without another
event. The original generic observation API still treats payloads as opaque;
other trusted publication writers must use the same checked invariant if they
participate in this host's observation format.

Recovered observations are fallback metadata. A first publication acknowledged
by the original owner during this facade's lifetime is also preserved there;
this metadata grants no permission and is not a second persistence owner.
Recovery intentionally
leaves the local Session phase unknown and without sending permission, even if a
retained admission or local cancellation is known. A false `*_recorded` field
means recovery of that observation is unresolved; a visible reply alone does not
turn the field true.

## Retained observation format

`receipt.rs` writes a private version-one record only from the existing
transport's immutable attempt types. It stores the exact original request hash,
full submission or query identity, bytes written, frame bound, requested history
anchor and typed original observation. It does not claim to preserve raw network
reply bytes or to authenticate unsigned metadata independently.

`recovery.rs` rejects unknown fields, unknown versions, altered identities,
invalid frame/response-generation relationships, unknown issue codes, duplicate
submission observations and contradictory publications. The original owner's
schema, event-chain, lease and full recovery-cut checks remain mandatory before
these records can be projected. This format must not be silently rewritten during
a future migration.

## Development and qualification

The standalone host and integrated Desktop UI workspaces use Rust 1.96,
matching the pinned original Hepta runtime graph. Both Cargo roots explicitly
retain the original Hepta dependency patches because dependency workspaces
cannot propagate their root patches to a consuming product.
Their serde and serde_json constraints are aligned through normal Cargo lock
resolution; no original Hepta package, workspace membership or dependency is
substituted to make the host compile.

The host's `dev-small` profile follows the original Hepta profile: no optimization,
no debug information and stripped symbols. Validation uses one build job where
resource pressure requires it. This profile is not native-kernel, real-device or
production-input qualification.

Required tests use the real original writer/store and disposable Unix sockets.
They must cover retention before connect, lost replies, receipt-only retry,
revocation before send, checkpoint failure after commit, duplicate fencing,
retained enumeration and recovery without a new send, canonical body matching,
contradictory publication rejection, local cancellation and invalid runtime
context. Test-only issuers/checkpoints are explicit fixtures.

Execution records must bind the Desktop source, exact original Hepta commit,
Cargo.lock, compiler, profile, command, complete exit status and raw logs. A
source-only candidate, queued CI job or test stopped by a resource guard is not a
passed qualification. Tests against a local candidate path must be identified as
such until the final pinned Git dependency graph is executed.

## Remaining production gates

This slice does not itself supply the seven independent production inputs, the
original authority service's operation handler, a protected checkpoint service,
a Shell command, model execution, Notes readback/revocation,
crash/power-loss qualification or real-device evidence. Those gates require their
own original-owner execution records. Enabling renderer Send before those
contracts are assembled and validated would overstate this library's scope.


## Typed Session integration

`TypedObjectiveHost<A>` takes the original multithread runtime and an
`ObjectiveHostAuthority` implementation from the deployment. The authority
supplies the existing writer's sender capability, current original peer and
signed original ingress. Its `run_id` must deterministically bind the persistent
trust namespace and client intent ID. Status or duplicate Submit first scans the
original sender's bounded retained pages. A retained run only recovers and reads
history; it never receives another issue/send opportunity, including after host
restart. The first request's text remains authoritative for a reused ID.

`ObjectiveWorker::spawn` runs that host on one blocking worker with eight action
slots and at most 128 disposable observation entries. Availability and Status
use a separate bounded, coalesced passive queue. Passive polling cannot consume
Submit/Cancel slots; actions run before pending passive refreshes. Actions keep
FIFO order so a Cancel cannot accidentally overtake its own queued Submit.
A private authenticated
socket server calls `request` to return immediately, allowing Session's bounded
IPC budget to remain responsive. The cache is not a ledger; original-owner
retention is the sole recovery source. A full queue reports Capacity and never
falls back to a direct operation. See `ui/session/OBJECTIVE_BRIDGE.md` for framing.
Dropping the host discards work that has not started. An already-running original
call retains its original uncertainty rules; queue disposal is not a durable
cancellation receipt. Worker-thread regressions in `src/worker_tests.rs` exercise
poll floods, action ordering/capacity and shutdown without substituting an owner.

Availability queries the actual Agentd capabilities and requires
`objective.start` major 1. Submit, history, RunStatus and RunCancel bind the
expected original UID/PID and owner/generation. Cancel reads a fresh original
run revision; the renderer never supplies it. Run and cancellation observations
are not device-effect receipts, and absence of a run does not mean non-admission.
`observed_unix_ms` describes view freshness only. UI must expire cached readiness.

Availability also reads bounded original `retained_page` records for navigation
after Shell process death. The deployment's pure `retained_client_intent_id`
mapping reads its original canonical source `requestId`, returns None for other
producers, and performs no signing, preparation or delivery. The host validates
each ID, original owner/spawn and the exact `run_id(id)` round trip. Only IDs and
traversal completeness cross the UI boundary; raw signed requests stay private.
At most 128 IDs and 64 original pages are considered under one asynchronous
deadline. A partial traversal cannot advertise Ready. This is a live keyset
traversal, not a frozen global history snapshot. New recovery scans begin again
at Beginning. Tests verify that a fresh host recovers the IDs without creating
an original observation, permission or additional wire submission.
The required nonblocking `check_submission_available` separately checks the
original writer's permanent checkpoint fence and deployment feed freshness.
Fencing disables Ready and new issuing while preserving retained navigation
and original status reads. A readable sender never substitutes for this check.

The deployment must provide a genuine issuer, protected clock, live verifier,
independent durable current-cut checkpoint and existing writer. Tests in
`typed_host.rs` use the real original sender and SQLite owner with explicitly
synthetic socket replies. They verify replay fencing, recovery and cancellation
revision selection; they do not qualify production authority or real Agentd.

## Literal Notes compiler

The named “Write note via Hepta” action treats the submitted UTF-8 text as the
exact content of one Notes document. `compile_notes_intent` calls the original
`notes_operation_intent` validator, then binds that operation's semantic digest
into the original structured Objective source. This binds payload, trusted
subject and policy generation, current Notes incarnation and expected revision.
No text is interpreted as model instructions, shell commands or network access.
The original Notes bounds still apply: 4096 text bytes and 8192 payload bytes.

The trusted deployment supplies `NotesIntentContext`, including the actual
current target/revision, operation identity, principal scope, protected time and
deadline. `notes_admission_profile_json` registers the same finite literal
normalization for a persistent principal scope and genuine issuer identity.
The registration must be installed in the original Objective owner. The
compiler grants no signing, admission or effect authority. The deployment must
retain the returned exact payload and `OperationIntentV1` through the original
`prepare_operation` before original final-use dispatch.

`tests/notes_intent.rs` executes the original strict decoders and original
`admit_and_compile_objective_v1` against this profile. It checks that changing
content or predecessor changes the original operation identity and that literal
Chinese text survives without reinterpretation. The test authentication context
is explicitly synthetic; it does not replace the production issuer or qualify
a real document write. Notes application storage and crash recovery are owned
by the [original Notes store and recovery helper](../../support/ui/NOTES_DURABILITY.md);
neither this compiler nor admission proves a persisted document or a durable
original-writer terminal receipt.
