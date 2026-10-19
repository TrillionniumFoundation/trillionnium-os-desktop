# Original-owner Objective admission history qualification

This runner is separate from R8's fixed-original admission and Session probes.
It reads the tracked `services/hepta-os/OBJECTIVE_HISTORY_CONTRACT.json`, checks
the exact original-owner commit, clean checkout, ancestor, Cargo.lock and reviewed
file hashes, and compiles that identity plus its input hashes into the probe.
It does not change `run_original_agentd.PIN`, the R8 source contract or old checks.

## Scope

The new executable reuses `original_objective_owner.rs` and
`original_objective_fixture.rs`. Those modules create one fresh private Fleet,
use the original Supervisor and original signed AuthBus/Objective compiler, and
keep a disposable signing key in memory. No production issuer, model request,
Operations dispatch, device effect or resumed historical run is installed.
The identities here are Objective requests and run IDs; they are not Operations
`K=(scope_id,operation_id)` or kernel delivery D.

Fifteen runtime checks use thirteen `hepta-history` invocations. Five distinct
Objective requests cover compiled, abstain, deliberate response loss,
post-publication rejection and revoked-issuer rejection. Four use the actual
`hepta-submit` CLI; the third uses a qualification-only original
`AgentdRequest` sender. Four publications remain durable before the storage
faults; the fifth request is rejected without append. No request is a recovery
resubmission.

The third sender checks the original Unix peer UID/PID, writes one complete
bounded frame, then deliberately discards its connection without reading a
response. This is a **harness-controlled response loss**, not an executed
`hepta-submit` CLI lost-reply test. A bounded read-only RunStatus wait lets the
earlier submission finish before measuring whether the history query changed
the journal. The history CLI then locates the original publication without
resubmitting the request.

| Check | Required result |
| --- | --- |
| Live compiled / abstain | Original publication agrees with signature/body/profile, compiler and actual submission receipt; abstain has no current run |
| Retained anchor | A later acknowledged anchor covers an earlier publication without changing it |
| Deliberate response loss | Full write, zero response bytes read, subsequent original history publication; no second ObjectiveStart |
| Error after publication | Two existing admitted runs remain active; the third compiled request returns actual CLI `submit_unknown` / `objective_owner_request_rejected`, yet its exact original history is compiled publication #4 and its current RunStatus is null |
| Wrong anchor / earlier anchor / changed signature | Sent `unknown`, respectively anchor_mismatch / publication_outside_anchor / no_matching_publication |
| Normal restart | New process and current spawn; old RunStatus null; original signed request still yields the same publication under the retained anchor |
| Actual expiry | The previously admitted abstain envelope has a 25-second signed expiry; after the real clock passes it, the replacement owner still locates the same publication under anchor #4; wait is bounded to 30 seconds and the envelope is never resubmitted |
| Valid-prefix rollback | Stop owner, save exact bytes, replace with the first complete publication, restart original owner; the previously retained fourth anchor is missing and remains unknown |
| Last-frame truncation | Stop owner, save exact bytes, replace with the full journal minus its last byte, restart; original recovery keeps exactly the first three complete frames, retained fourth anchor remains unknown |
| Revoked issuer | The currently running original owner still returns the original historical publication; a distinct new signed submission is rejected without a journal append |
| Controlled stop | Original Supervisor confirms inactive; old control endpoint no longer responds |

The runner does not open the active journal to answer history. The harness takes
raw byte snapshots solely for fault evidence and read-only stability checks.
It injects storage faults only after the disposable owner is confirmed stopped.
The **original owner** performs its normal `Unacknowledged` recovery and may
truncate an incomplete tail; the harness does not call recovery or repair APIs.
Before/injected/recovered files and hashes make that distinction reviewable.
The issuer is not restored after revocation.

The post-publication test uses the unchanged original
`ResourceBudget::local_default().max_concurrent_turns = 2`
(`codex-rs/hepta-fleet/src/model.rs`). The original Objective owner publishes
before starting the current run (`hepta-agentd/src/objective_runtime.rs`), whose
coordinator rejects a third active run (`state.rs`, `lane_b_runtime.rs`). This
supports a **capacity-exhaustion inference from fixed source and two observed
active runs**. The desktop CLI intentionally retains only the generic rejection
code; the probe does not claim to have observed the original `CapacityExceeded`
error bytes. No resource budget, authority, production configuration or private
test hook is changed to trigger the error.

Only the abstain envelope's outer AuthBus expiry is shortened before its first
and only submission, using the unchanged fixture's public signing helper. Its
source deadline and compiled Objective remain unchanged. The probe requires an
unexpired envelope before submission and actual original admission; a slow
machine that misses this window fails qualification. After the normal restart,
the probe records wall-clock time strictly greater than the stored expiry and
checks the same history again, with the issuer still trusted at that point.

## Build and execution

Supply the separately pinned Hepta checkout and a new evidence directory outside
both checkouts. `--contract` may point to another checkout's exact tracked
history contract; uncommitted edits to that file are rejected.

```bash
python3 -B tests/integration/hepta/run_objective_history.py \
  --hepta-source /absolute/pinned-hepta \
  --work-dir /absolute/new-history-build \
  --target-dir /absolute/shared-original-target --offline
```

`--prepare-only` writes the external package, copies the reused original fixture
and owner, and adds the new history probe; it does not build or launch anything.
The manifest/lock helpers preserve original dependency identities and the
previously checked unused duplicate patch omission. The original root package
name remains the lock helper's external observer-probe name, but the built
binary is `hepta-objective-history-probe`; no old probe executable is run.

```bash
python3 -B tests/integration/hepta/run_objective_history.py \
  --hepta-source /absolute/pinned-hepta \
  --work-dir /absolute/new-history-runtime --execute --offline \
  --probe-bin /absolute/hepta-objective-history-probe \
  --agentd-bin /absolute/codex-hepta-agentd \
  --observer-bin /absolute/hepta-observe \
  --submitter-bin /absolute/hepta-submit \
  --history-bin /absolute/hepta-history
```

A supplied prebuilt probe requires the caller's matching build provenance; its
embedded original-owner/input binding is checked against this invocation.
All five native ELF hashes are saved and checked after successful execution.
The outer command has a 240-second deadline, owned process-group cleanup, and
copies the private evidence before its temporary Fleet is removed. Original
Supervisor's three-restart budget is retained: one normal restart and two
storage-fault restarts. Source files and the committed contract are checked
again before any result becomes `passed`.

## Validation and remaining gaps

Run the lightweight receipt/source validator tests with:

```bash
python3 -B -m unittest discover -s tests/integration/hepta \
  -p test_objective_history_contracts.py -v
```

These tests use explicitly synthetic receipt records and small temporary Git
contracts. They cannot qualify the Rust probe, original owner, actual socket
or crash recovery. Actual build/runtime receipts must be recorded separately;
this document alone makes no runtime pass claim.

Not executed by this profile: rollback of the caller's retained anchor together
with the journal, production issuer integration, independent
effect reconciliation, kernel G1/G2, Session or Shell rendering. Current owner
history without a retained anchor is only its present journal observation;
missing history never proves original non-admission. Conflict publication, if
returned by the protocol, is not an admission or effect completion.
