# Calculator organ v1 — development and storage contract

The current source adds durable application state and joint original-owner recovery to the original Calculator candidate. The machine-selected source pair and historical evidence remain recorded in [SOURCES](../../docs/SOURCES.md). A protocol or component test alone does not qualify the installed product; historical fd8/a39 receipts do not qualify a later source pair.

Calculator owns its visible state and one pending causal receipt. The original Hepta writer, Objective sender, outbox and FinalUse retain authority, history and retry policy. Public Session IPC cannot submit Calculator effects or retire receipts.

## Identity and exact effect

`CalculatorTargetIdentity` contains `session_instance` (32 lowercase hex), positive `task_id`, and `incarnation` (32 lowercase hex). Destination is `trill.calculator:{session}:{task}:{incarnation}`. SHA-256 scope input is UTF-8 `trill.calculator.scope.v1\0{session}\0{task}\0{incarnation}`. Predecessor input is `trill.calculator.predecessor.v1\0{session}\0{task}\0{incarnation}\0{revision}`. New incarnations never acquire old effects or receipts.

Topic: `trill.calculator.evaluate.v1`. The exact JSON request has fields `{schema_version:1,action:"evaluate",operation_id,destination_id,target,expected_revision,left,operator,right}`. Operands are canonical signed i64 decimal strings: parsing and formatting reproduce identical bytes, excluding plus signs, leading zeros, whitespace and negative zero. Operators are `add`, `subtract`, `multiply`, `divide`. Arithmetic is checked; division must be integral. This is a finite arithmetic profile, not an expression evaluator.

All wire objects reject unknown fields. Request/response bounds are each 4096 bytes. Operation IDs contain 1–128 ASCII letters/digits or `._-:`. The original owner retains and hashes the exact JSON bytes; transport never reconstructs them. It binds scope, predecessor, policy generation and semantic digest through the original operation intent.

The private effect endpoint is an inherited unnamed Unix stream, using four-byte big-endian length framing. An independent inherited unnamed Unix datagram endpoint accepts observation/retirement only. Exchange budgets are absolute. Ambiguous effect transport is permanently invalidated; observation does not authorize reconnect or replay.

## State and causal result

`CalculatorValueState` is `{left,operator,right,result}`; string fields have at most 64 UTF-8 bytes, and operator is null or the four-operator enum. Initial strings are empty and operator is null. GUI edits and external effects share one revision; local edits preserve any pending causal receipt.

`state_sha256` hashes `trill.calculator.state.v1\0`, followed by left, operator name (empty for null), right, result. Each field contributes an eight-byte big-endian UTF-8 byte length followed by those bytes. This removes JSON ordering ambiguity.

Envelope: `{schema_version:1,target,operation_id,payload_sha256,result}`. Result is one of:

- `{status:"applied",previous_revision,revision,state,state_sha256}`, with revision exactly predecessor + 1 and app-computed arithmetic.
- `{status:"not_applied",reason,current_revision}`. Reasons: `revision_conflict`, `operation_conflict`, `revision_exhausted`, `target_mismatch`, `ui_deadline_elapsed`, `receipt_pending`, `invalid_operand`, `overflow`, `division_by_zero`, `non_integral_division`.
- `{status:"unknown",current_revision}`; current arithmetic values never prove a missing historical effect.

Capacity is one pending Applied response and one last retirement identity. Identical pending repeats return that receipt without applying again, including after a deadline. Within these two retained entries, reused IDs with different bytes are refused. An exact last-retired operation is Unknown at the app, while the original writer retains its terminal. Older history and global operation identity are protected by the original writer ledger, not an unbounded app cache. New effects wait for exact original-writer retirement. The in-memory model receipt alone proves neither compositor pixels nor persistence. In the durable profile, CalculatorStore synchronizes the complete state and causal receipt before returning Applied; the original Hepta writer must still verify and retain its own terminal.

## Readback and retirement

Only these requests are accepted on the datagram lane:

1. `{schema_version:1,action:"read_calculator",target,observation_id}`. The observation ID is nonzero 32-lowercase-hex. Response: `{schema_version:1,action:"calculator_state",target,observation_id,revision,state,state_sha256,receipt_pending}`. This is current state, separate from historical execution.
2. `{schema_version:1,action:"observe",target,operation_id,payload_sha256}`. Exact pending-receipt match returns its original Applied response; otherwise Unknown.
3. `{schema_version:1,action:"acknowledge",target,operation_id,payload_sha256,receipt_sha256}`. The digest covers the exact app-serialized Applied response bytes. Only the original writer, after verifying its matching durable terminal, sends this. Response: `{schema_version:1,action:"acknowledged",target,operation_id,payload_sha256,receipt_sha256,status}`, where status is `retired`, `already_retired`, or `not_retired`.

The app retains one last exact retirement for idempotent acknowledgement, without a second operation ledger. No evaluate payload is accepted on this lane. The optional temporary profile loses its volatile receipt on App exit. The durable profile preserves the exact target checkpoint and permits an independent recovery-only helper to read or acknowledge it. It never inherits Notes persistence, creates a replacement operation or treats missing evidence as success. [Calculator durability](../../support/ui/CALCULATOR_DURABILITY.md) specifies the 16 KiB format, physical synchronization, worker and helper contracts.

## Versioned multi-target startup

New Session mode: `--desktop-root-bootstrap-stdin`. Real Notes task 1 and Calculator task 2 are prepared before metadata-only reservation:

`{schema_version:1,action:"desktop_targets_reserved",profile:"notes_calculator_v1",notes,calculator,nonce}`.

The identities share the actual Session and have independent incarnations. Nonzero nonce is 32 lowercase hex. Root checks credentials and retained Session pidfd, registers both exact destinations, then returns the identical fields with `action:"activate_desktop_bootstrap"` when the original owner is ready. Session transfers existing Notes two-FD offer/ACK, then new Calculator two-FD offer/ACK on the same private bootstrap pair:

`{schema_version:1,action:"offer_calculator_target",target,destination_id}` → `{schema_version:1,action:"calculator_target_ack",target,destination_id,status:"attached"|"rejected"}`.

The original Core creates a new versioned multi-target thread with `hepta_calculator_state`, `hepta_calculator_evaluate`, `hepta_calculator_status`. Its original turn/call proofs, Objective, protected writer/outbox and FinalUse remain the execution path. Existing Notes thread catalogs are not silently altered.

The new original admission profile is `organ.desktop.thread-tool.v1`, paired with the `notes_calculator_v1` six-tool catalog (the three Notes tools and these three Calculator tools). Its persistent turn fence is shared across both destinations: at most one effect is admitted per original Core turn. A later turn may select another target. Changing tool, target or call ID within the same turn cannot evade a retained or unknown effect. Multiple effects in one turn are outside this v1 profile.

## Acceptance

Contracts test bounded parsing, exact identity/digests, arithmetic, revision conflicts, pending-receipt retention and read-only recovery. Real acceptance additionally requires the original Core callback → Objective → same writer/FinalUse → actual app mutation → independent readback → matching original terminal. A launch, local arithmetic test or mocked owner test is insufficient.

## Development and execution scope

This draft uses the existing UI workspace and its locked Rust 1.96.0 dependencies.
Run from the repository root, with a separate Cargo target directory when another
product build is active:

```sh
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-ui-core --locked
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-session --locked
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-app-window --locked
RUSTUP_TOOLCHAIN=1.96.0 cargo test --manifest-path ui/Cargo.toml -p trill-ui-core --locked \
  emit_cross_repository_wire_fixture_from_app_serialization -- --nocapture
python3 -I -B support/docs/check_modules.py --report /tmp/trill-calculator-module-docs.json
```

Add `--offline` only when the exact locked dependency graph is already cached.
The golden fixture is actual shared Rust serialization/model output, explicitly
`MODEL_SERIALIZATION_ONLY`. Physical bootstrap tests use real anonymous sockets
and descriptors. The lifecycle test starts a real owned Session and App process,
imports the actual inherited pidfd and advances empty-input egui frames using
their returned repaint delay; normal Session exit and termination must request
Close without an input or effect. This establishes host process/egui component
behavior, not native compositor window exit or visible pixels.

The candidate Session flag requires the private original Root handshake, exact
Notes/Calculator storage and helper configuration and the joint owner profile; it is not a standalone
command for granting authority. The complete Root launcher, paired Hepta source,
six-tool original Core thread, real writer/FinalUse effect, independent app
readback and original terminal must be separately compiled and executed before
this candidate becomes a product selection. Record exact commits/trees, locks,
binary hashes, test failures/skips and raw receipts. Preserve frozen fd8/a39
and prior receipts independently; never carry their passing counts to this draft.
