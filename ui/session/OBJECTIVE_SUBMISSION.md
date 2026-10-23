# Original Objective submission composition

## Status and scope

This is a new, explicitly enabled trusted-host library seam. The standalone
Session IPC, Shell composer and CLI have no Objective-send command. Enabling
`objective-submission` does not configure an issuer, durable owner or production
chat submission. A real implementation of the existing request owner's durable
retention API is still required before production use.

The source baseline is Desktop commit
`39c1d84ebf854958f5829c0118b0c8b92a6b4926`, tree
`87bc4e4d72697a7583fb0afafe4db4b41582941c`. The existing protocol contracts remain
`services/hepta-os/OBJECTIVE_TRANSPORT.md` and
`services/hepta-os/OBJECTIVE_HISTORY_CONTRACT.json`. This change does not replace
their pinned Hepta protocol owner, alter signed request fields, or change any
dependency version or lockfile.

## Ownership and call order

An independently trusted embedding host supplies an original issuer envelope,
the original `ObjectiveTransport` configured with the exact endpoint/AgentId,
generation, peer UID/PID and request ID, and an implementation of
`OriginalObjectiveRequestOwner`. These values must not originate from renderer
authority decisions. `ProvidedObjective::parse_json` checks structure only;
authentication and admission remain with original Hepta.

`ObjectiveSubmission::prepare` preserves the exact supplied JSON, obtains the
original transport's pure identity preview, checks generation agreement, and
calls the existing owner to retain that identity and byte string. Only a
successful durable retention acknowledgement yields a local send permission.
No connection is opened by preparation. An owner failure, including an
ambiguous storage result, yields no sender; the original owner must retain and
recover any ambiguous record it may have committed.

`submit_once` takes that permission and marks the local state unknown **before**
calling the unchanged original one-shot transport. It keeps the original
`SubmissionAttempt`, then asks the same owner to retain the observation. No
return status, including `NotSent` or `RefusedBeforePublication`, creates another
send permission. A panic, crash or lost reply cannot be repaired by constructing
a fresh facade and resending. Global duplicate and competing-sender fencing is
the original owner's responsibility; this adapter only enforces its own linear
permission.

The original transport has its existing bounded I/O deadline and validates the
configured peer UID/PID. The embedding host must use a bounded blocking worker;
owner callbacks must independently bound storage I/O. The adapter creates no
background task, unbounded queue or new deadline guarantee over owner storage.

## Recovery and receipt handoff

`recover_unknown` verifies envelope metadata against the supplied original
submission identity and asks the existing owner to match **all exact original
bytes and metadata** against its pending record. It never creates a transport or
send permission, even if the process might have crashed before socket write.
Its conservative starting state is unknown.

If a receipt handoff fails, the original attempt remains privately attached and
the view shows that it is not durably recorded. An explicit
`retain_observed_submission` call can repeat only the same immutable owner
receipt write. It cannot issue another Objective request. Owner receipt writes
must therefore be append-only and idempotent for the same observation. There is
no automatic store or transport retry.

`reconcile_once` performs an explicit original `ObjectiveHistoryClient` read with
the unchanged original JSON. A replacement owner's current generation and PID
may differ, but the AgentId must remain the same. Any history anchor comes from
the original owner; this adapter never guesses a publication sequence from an
admission response. History results are retained through the same owner. A
failed history handoff cannot be overwritten by another query; the host must
first retain that exact existing result.

The view keeps the original submission result, latest history observation and
first observed historical publication separately. An unknown history result,
including `NoMatchingPublication`, never erases earlier admission/publication
observations and never means "not admitted". The fields are observations, not
an independently computed authoritative verdict. Original admission/history
proves neither model completion nor a desktop/mobile effect. The adapter does
not read `RunStatus` absence as evidence of non-admission.

## Cancellation

`cancel_before_send` consumes and drops only this never-used local transport
permission, then records that local fact with the original owner. If recording
fails, the permission remains consumed and `retain_local_cancellation` can
repeat only the identical owner handoff. It does not send a run-cancel command,
erase pending intent or claim an Objective was cancelled elsewhere.

Once sending starts, local cancellation returns
`OriginalOwnerCancellationRequired`. The existing Session `Cancel` command
kills an owned host child; it must not be reused as an Objective cancellation.
Production run cancellation must use the original Hepta `run_cancel` endpoint
with its run ID and expected revision. Its cancellation acceptance is not a
proof that an external effect did not happen. In particular, a dispatched run
may remain in cancellation/indeterminate reconciliation. This patch does not
implement or simulate that separate owner endpoint.

The original cancellation entry points were checked at Hepta
`507b46749dea0cece820c4997208f20464362d75`:
[`AgentdClient::run_cancel`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/507b46749dea0cece820c4997208f20464362d75/codex-rs/hepta-agentd/src/client.rs#L404-L423),
[`state_control` readiness gate](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/507b46749dea0cece820c4997208f20464362d75/codex-rs/hepta-agentd/src/state_control.rs#L503-L519)
and [the original cancellation state machine](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/507b46749dea0cece820c4997208f20464362d75/codex-rs/hepta-agentd/src/lane_b_runtime.rs#L334-L389).
This source reference does not change the Desktop transport/history pins.

## Required production integration

The existing Desktop transport explicitly requires sender-side pending
retention. Original Agentd evidence enqueue happens after reception and does
not provide that sender-side guarantee. The original owner needs a concrete
typed retention implementation in its existing transactional store: exact
signed bytes, exact submission identity, opaque retained handle, durable
duplicate fence, immutable receipt/history observations and recovery. No local
UI file, database, signer or second ledger is supplied here.

The original ProductionDurableWriter/LocalLeaseOutbox transaction is a candidate
implementation location to be reviewed and extended by its owner. Its existing
FinalUse dispatch claim concerns external effects; it must not be reused as an
Objective admission claim without an explicit owner design. The new FinalUse
issuer provider does not sign AuthBus Objective or SourceEnvelope requests.

Production enablement still requires that real durable owner implementation,
the original AuthBus issuer and lawful SourceEnvelope/profile, bounded trusted
host composition, original run status/cancellation projection, and end-to-end
original-owner qualification. The default UI remains without a Send command
until these are connected. Makepad/Robrix sharing and accessibility qualification
are separate work; this seam changes no renderer.

## Verification

The implementation contains eight dependency-free tests of the actual linear
permission policy. They exercise retention before exposure, refused retention,
unknown fencing, local cancellation, failed receipt retention, recovery without
a sender and unwinding after start. They can run directly with `rustc --test`;
they do not execute Tokio, the original socket transport or a durable owner.

Ten feature-gated Session tests use actual disposable Unix sockets and the
original `ObjectiveTransport`/`ObjectiveHistoryClient`. Their owner is an
explicit in-memory test fixture, and their original protocol sample has an
expired all-zero signature. They test ordering, exact byte identity, duplicate
fencing by the injected owner, lost replies, cancellation, receipt failures,
recovery, agent matching and history preservation. They do not qualify
authentication, real original-owner persistence or physical effects. An
additional original transport regression checks that pre-send identity lookup
opens no connection and exactly matches the later attempt.

Run the production feature explicitly; default-feature tests alone do not
compile this seam:

```sh
cargo test --manifest-path ui/Cargo.toml -p trill-session --all-targets \
  --features objective-submission --locked --offline
cargo clippy --manifest-path ui/Cargo.toml -p trill-session --all-targets \
  --features objective-submission --locked --offline -- -D warnings
cargo test --manifest-path services/hepta-os/Cargo.toml \
  --features objective-transport --locked --offline --test objective_transport
```

The A10 workflow runs the feature-specific Session tests and Clippy after the
existing dependency/build gate, on its pinned Rust 1.88.0 toolchain, and archives
their actual logs. Local evidence records which commands actually executed and
which stopped during dependency resolution; authored tests are never counted
as passing tests without execution.
