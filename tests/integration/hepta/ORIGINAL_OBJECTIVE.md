# Original signed ObjectiveStart process probe

This probe qualifies one explicit signed objective admission route through the
unchanged Hepta owner at
`f8c9419df6ddeb36ff8b522a50219981fb8d9345`. It starts a disposable Fleet using
the original `FleetRegistry`, `Supervisor<UnixProcessDriver>`, original Agentd
ELF and original evidence/checkpoint APIs. The desktop `hepta-submit` executable
transmits each original typed envelope once over the real Agentd Unix socket.

The success boundary is durable original admission. The compiled objective has
the original `admitted` run phase and `terminal_observed=false`. This is waiting
for the next execution/context step; `WaitingForContext` is not a wire phase at
the pinned revision. No model turn, Operations dispatch, canonical intelligence
invocation, device effect or historical run resumption is qualified here.

## Executed qualification: 2026-10-18 UTC

The [original objective and desktop result](../../../results/integration/2026-10-18-objective-desktop/README.md)
records two actual Linux host runs of this gate. The core-only run and the
Session/Shell run each passed all ten core checks with seven explicit submission
attempts. The second additionally completed the three Session phases below and
kept one native Shell alive for three captured PNGs. The result binds each
original/desktop build and ELF to its actual runtime, with capture and visual
review recorded separately. These local runs do not grant a different source
or a pending GitHub CI run the same qualification.

Both runs used an isolated test issuer explicitly enrolled in the original
owner. `production_issuer`, `model_turn`, `operations_dispatch`,
`canonical_intelligence`, `device_effect` and `historical_run_resumed` remain
false. The stopped-owner journal check validates original durable publication;
it is not an online product recovery service. Production trust, durable unknown
reconciliation, restricted OS effects and Asterinas G1/G2 remain in
[S1–S5](../../../docs/agents/R8_NEXT_SLICE.md).

## Files and responsibilities

| File | Responsibility |
| --- | --- |
| `original_objective_fixture.rs` | Independent disposable test producer; original structured source decoding, compiler, AuthBus signing claims and Ed25519 signing. |
| `original_objective_profile.json` | Explicit fixture admission vocabulary and principal scope. This is not a production issuer enrollment or a natural language parser. |
| `original_objective_owner.rs` | Original Fleet/Supervisor lifecycle, private public-key trust/profile files, original replay frontier initialization, actual CLI invocation and owner reads. |
| `original_objective_probe.rs` | Positive/negative assertions and stopped-owner journal inspection through the original durable decoder. |
| `original_objective_session.rs` | Optional real Session/ctl projection of the published known run, stale history after owner restart and an explicit replacement Session's missing projection. |
| `run_original_objective.py` | External manifest/lock preparation, bounded build/run, explicit native input identities and evidence collection. |
| `test_original_objective_receipts.py` | Twelve focused parser-gate tests rejecting incomplete phases, silent identity replacement, incorrect scope, changed original bindings, renewed stale run timestamps, substituted publication digests and transport-only generation-fence claims. Its synthetic records are not runtime evidence. |

The source envelope is a small structured request to read a marker in the fresh
test workspace. Original `decode_source_envelope_json_v1`,
`canonical_objective_intent_digest_v1`, `admit_and_compile_objective_v1` and
`encode_objective_function_v1` validate it before submission. No arbitrary text
is inserted as `source_envelope_json`. Millisecond timestamps preserve the
original protocol's deadline precision requirement. Empty legal action classes
produce the separate `explicit_abstain` fixture.

Only the independent test producer receives its ephemeral random signing key.
The Agentd process receives its matching public trust file. The desktop CLI
receives the signed ingress bytes; it receives no signing key. All trust,
profile, checkpoint, Fleet, workspace and journal state is scoped to a newly
created private temporary directory. The external replay checkpoint is seeded
from `HeptaEvidenceStore::authbus_replay_frontier_digest`, not a replacement
replay store. No production services, endpoints, enrollments or devices are
discovered.

## Assertions

The core probe makes seven explicit submission attempts and emits ten ordered
checks. The second attempt is a deliberate exact duplicate made by this test
producer, whose retained envelope remains available; the product CLI performs
no retry.

| Check | Required observation |
| --- | --- |
| `compiled_original_admission` | Real receipt matches original compiler semantic and hard-constraint digests; current original run is `admitted`, nonterminal. |
| `exact_replay_same_publication` | Identical signed ingress returns the same publication and chain with `idempotent=true`; journal bytes do not grow. |
| `explicit_abstain_durable_without_run` | Original receipt is `explicit_abstain`; journal grows; `run_status` returns no runtime run. |
| `invalid_signature_owner_rejected` | Full request reaches the owner and the CLI conservatively reports `submit_unknown`; independent journal observation shows no append. |
| `body_generation_fenced_before_send` | Body/endpoint spawn disagreement is `not_sent`, with zero bytes written and unchanged journal. |
| `revoked_issuer_owner_rejected` | Only the disposable issuer is revoked; validly signed new request is rejected, with unchanged journal. |
| `owner_restart_retains_historical_journal` | Original Supervisor replaces Agentd, advances spawn and changes PID; journal is byte-identical; historical runs are absent from the replacement generation. |
| `old_spawn_not_accepted` | The full retained old-generation request reaches the replacement owner and remains `submit_unknown / objective_protocol_mismatch`; the same replacement PID is still ready, its current run projection remains absent and the historical journal is unchanged. Transport failure alone cannot pass this check. |
| `original_journal_matches_receipts` | After controlled owner stop, original journal recovery validates the first publication prefix and final receipt anchors, exact original compiler/protocol identities, authentication, admission profile, body digests and dispositions. The public original journal API returns an exact idempotent receipt on the read-only recovered file; each actual publication/chain digest must match it. |
| `controlled_stop` | Original Supervisor reports inactive and the endpoint no longer answers. |

Every CLI result must match its expected exit code and the full supplied
identity: request ID, agent UUID, endpoint spawn generation, trusted owner UID
and PID, issuer/key epoch/message/sequence/expiry, run/revision/authority and all
five body binding digests. Receipt fields alone do not qualify the attempt.

The original generic `request_rejected` response does not prove that rejection
preceded publication. The desktop transport therefore reports `submit_unknown`
for the bad-signature and revoked-key cases. This isolated probe can add the
independent fact that the original journal did not change; it does not alter
the product's conservative transport semantics.

Original publication uses `current_generation`; requests bind the immutable
`spawn_generation`. These values are distinct after the Supervisor promotes a
running owner. Restart preserves durable history but must not silently make an
old generation's objective a current run. A `None` runtime lookup is not a
general non-admission proof: the explicit abstention check itself demonstrates
a durable publication without a runtime run.

Journal inspection runs only after the original Supervisor confirms owner
inactivity. It gives the original recovery API a read-only `File`, so corrupt
or incomplete evidence cannot be repaired by truncation. The first and final
acknowledgment anchors come from actual transport receipts. The final journal
hash must remain unchanged across inspection.

The original public `append` API checks an identical existing record before
its write path and returns `IdempotentReplay`. The read-only inspection uses
that branch to obtain the stored record's exact digest, sequence and chain;
it neither writes another record nor sends another owner request. A negative
comparison changes one legal hex character of the publication digest while
retaining all other fields and must be rejected.

## Build and run

First obtain a clean original checkout at the exact pinned revision and build
the original Agentd with the existing `run_original_agentd.py` native workflow.
Use its source/toolchain/lock and native binary manifests as the Agentd ELF's
build provenance. This runner verifies ELF identities but does not infer a
binary's source merely from a nearby checkout. The desktop observer and
submitter must likewise come from the reviewed desktop source; the submitter
requires the explicitly enabled `objective-transport` Cargo feature.

Preparation creates a new external package without compiling or launching:

```sh
python3 tests/integration/hepta/run_original_objective.py \
  --hepta-source /absolute/pinned-hepta \
  --work-dir /absolute/new-objective-preparation \
  --target-dir /absolute/shared-original-target \
  --prepare-only
```

The generated package preserves the original explicit workspace resolver,
profile and active patch identities. It seeds the original Cargo lock and
checks every resolved dependency identity against that seed. The sole omitted
patch is the existing runner's reviewed, unused duplicate SSH tungstenite
alias; the retained target must remain unused. Use Rust **1.95.0** for the
original graph. Public dependency fetching may be needed on the first run.

Build and execute with three explicit native input paths and another fresh
work directory:

```sh
python3 tests/integration/hepta/run_original_objective.py \
  --hepta-source /absolute/pinned-hepta \
  --work-dir /absolute/new-objective-run \
  --target-dir /absolute/shared-original-target \
  --agentd-bin /absolute/original-target/dev-small/codex-hepta-agentd \
  --observer-bin /absolute/desktop-target/debug/hepta-observe \
  --submitter-bin /absolute/desktop-target/debug/hepta-submit \
  --execute
```

`--offline` requires an already complete cache. A supplied `--probe-bin`
skips the probe build and requires the caller to retain a separate build/source
binding for that binary. `--prepare-only` and `--execute` cannot be combined.
The runner never starts an Agentd compilation implicitly; this permits shared
target/cache use while a coordinator controls memory and disk consumption.

The launcher sanitizes application configuration, uses a short private
`/tmp/ho-*` root for Unix socket length, and bounds its owned process group with
the existing original runner's anchored-child cleanup. Linux environments
must permit the original process/signal/socket operations; a sandbox denial is
not evidence that Hepta admission failed semantically.

### Optional Session and Rust Shell capture

Add `--session-bin /absolute/trill-session --ctl-bin /absolute/trill-ctl`
to the execution command to qualify the real consumer. The trusted launcher
sets `TRILL_HEPTA_RUN_ID=run.desktop-compiled` together with the four explicit
original Agentd endpoint variables. It starts Session after the original
compiled admission, while the same original owner continues to answer reads.
The seven original run fields must match the direct original-owner observation;
Session sample timestamps/sequence are checked separately. The actual IPC must
remain responsive, host `tasks` must stay empty and one persistent observer
worker must retain the same Session instance.

This optional path adds three ordered phase records:

1. `compiled_run_projected`: the original nonterminal `admitted` run appears in
   `snapshot.hepta.run` with independently fresh sampling.
2. `old_endpoint_run_stale`: the original owner has restarted; the same Session
   retains the complete run observation as history across two failed health
   samples, sets a sticky gap and reports `stale`. Health attempts advance while
   the run sample and its last-attempt timestamp remain unchanged: no run read
   is attempted after the health prerequisite fails.
3. `replacement_run_projection_missing`: the launcher explicitly starts a new
   Session with the new original spawn; the known historical ID has
   `projection_missing` and no current runtime projection. The subsequent
   original journal check independently proves its durable admission still
   exists.

Both Session instances use the same newly owned runtime directory and socket
path. After the first child is stopped and reaped, the second instance uses
the application's normal socket/lock acquisition; the probe deletes no socket
or user file. A continuously running Rust Shell can therefore reconnect to the
same endpoint and observe the explicit Session instance replacement. Separate
`session-1.log` and `session-2.log` files preserve both child logs.

For a separate actual Rust Shell screenshot controller, add
`--session-phase-dir /absolute/new-phase-directory --session-ack-seconds 60`.
The probe creates private `phase-1.json` through `phase-3.json`, each containing
the real Session runtime directory/socket, PID/instance/worker, snapshot,
original owner identity and an `ack` object. The controller captures the Shell
connected to that Session, then writes a regular, single-link, mode-0600
`ack-N.json` whose JSON exactly equals the corresponding `ack` object. This
acknowledgment coordinates capture; it is not owner evidence. The first capture
wait happens after exact replay and the time-sensitive negative checks, so
renderer timing cannot expire those admission inputs. The optional Session
path requires both Session children to be stopped and reaped before a pass.

Omitting Session inputs leaves this route disabled. No UI submission action is
created by the probe or by the read-only Session launcher.

`report.json`, bounded build/runtime logs, exact signed fixture requests, CLI
results, copied journal bytes and stopped-owner decoded identity checks remain
in the work directory. The random private key is not included. Preparation
and build-only results explicitly say the runtime was not executed. A passed
runtime report requires all ordered checks and retains the false scope flags
for model, Operations, canonical intelligence, device effects and historical
resumption.
