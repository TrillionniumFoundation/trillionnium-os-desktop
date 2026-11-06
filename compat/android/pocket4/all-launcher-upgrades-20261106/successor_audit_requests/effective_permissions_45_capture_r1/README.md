# Fixed 45 Launcher permission capture candidate

This is an **unexecuted source candidate**. It creates no actual claims or remote
jobs during generation or validation. The successful historical Beike pilot is
the implementation baseline; it is not a result for these new 13 observations.

## Scope and commands

`CAPTURE_PLAN.json` preserves the exact original 13 APK-audit partitions, with
45 unique service targets. Each new batch separately binds the current typed
runtime and the complete 47-package scope before/after the original operations.
The two helper packages stay in the identity context, outside the 45 service
targets. It compares a fresh native catalogue with the actual r4 45-component
reference; it does not claim to rerun Android's MAIN/LAUNCHER resolver.

Each batch performs `cmd package help`, then only the following two already
observed command forms for each fixed package:

- `cmd package dump-package PACKAGE`
- `cmd appops get --user 0 PACKAGE`

There are 103 Android reads in total. `dump-package` has no user selector; the
separate offline parser must identify the exact target Package and User 0
blocks. AppOps is explicitly queried for user 0. There is no role query, new
shell, ADB, grant/revoke, install, UI action or input. Meituan saved location
state and the original Bili UNKNOWN must remain unchanged.

The actual pilot transport, held target/namespace authority, classpaths,
original command runner, scope checks, action lease, native UID1000 caller,
original child pidfd retirement, and known libffi owned-process lifetime are
preserved. The inherited budgets remain: 900-second worker, 30-second command,
262144-byte stream, 1000-second owned child, 1100-second host process.

## Source differences

The four `*-against-actual-pilot.diff` files show batch 01 against the actual
successful Beike source. Other batch source differences are the fixed target
lists, resulting source/request pins, counts, paths and idempotency keys.
The assembler and local gate verify 21 worker, 8 transport and 11 owned-wrapper
definitions byte for byte against that source. No original source is changed.

The new local serial gate and offline parser have full source diffs against
their earlier implementations. The gate uses only pinned JSON/bounded-zlib
primitives from the original serial gate; it never calls its APK-plan admission
or changes its original ledger.

## Two distinct stages of evidence

1. **Raw capture:** preserve complete service stdout/stderr in the root-private
   remote output directory, and expose only paths, exact lengths, SHA256 and
   process/lifetime metadata in the public result. Each batch needs its actual
   complete durable terminal, exact stage+owned outer stdout, original child
   pidfd exit/close, full descriptor identity restoration, complete stream
   capture and original full47 guard checks. A clean capture leaves semantic
   grants/AppOps interpretation UNKNOWN.
2. **Offline interpretation:** retrieve the pinned two logs for a target into
   `p4_private_ui` outside the repository. `interpret_permission_raw.py` accepts
   them only after this batch's real joint gate passes. Literal permission names
   retain whitespace after removing the exact presentation indentation. Missing
   sections/rows, wrong appId, duplicate/unknown formats remain UNKNOWN. Only
   literal PM grant booleans are reported; no service flag is translated into
   presumed user denial. AppOps mode is not a permission grant; the `Uid mode:`
   prefix applies only to that line, and unprefixed scope stays UNKNOWN. Default,
   foreground, role holders and core-operation success are not inferred.

Raw PM/AppOps bodies and usage timestamps never belong in Git. The parser
exports only the necessary permission names/flags and per-operation modes with
their source pins and limits. Its known-format status is not production QA.

## Local coordinator protocol

Root alone decides when to submit, after source review and a free Main window.
This candidate has not run any of these commands against the real ledger:

```text
python3 -B permission_capture_gate.py validate
python3 -B permission_capture_gate.py status
python3 -B permission_capture_gate.py claim-next
```

`validate` checks sources, the original partition and real pilot evidence only.
`status` is read-only and creates no directory. `claim-next` only creates one
new local immutable intent; it does not submit a process. Its exact process
request is the indicated `batch-NN/process-request.review-only.json`.

The dedicated purpose ledger is
`successor_audit_requests/actual/permissions-fixed45-r1/`. A claimed batch must
receive these original evidence files before another can be offered:

- `submitted-job.json` with exactly `job_id`, `idempotency_key`,
  `request_sha256`, `process_request_sha256`, `plan_sha256`;
- `terminal.original.json`, the full authoritative process status;
- `stdout.original.jsonl`, the complete lossless two-line stage+owned output.

The intent and job binding must match the fixed row. Failure, launch unknown,
missing output, truncation, wrong streams, changed scope or incomplete FD/child
retirement stops the sequence. No retry or fresh key is offered. Preserve and
reconcile that original submission; do not replay it. The original APK-audit
FAILED/repair/continuation ledger is independent and is never read as new
permission evidence or modified here.

For a real completed batch, the offline parser CLI is:

```text
python3 -B interpret_permission_raw.py --batch N --package EXACT_PACKAGE \
  --pm-private /absolute/p4_private_ui/PINNED_PM_FILE \
  --appops-private /absolute/p4_private_ui/PINNED_APPOPS_FILE \
  --output /absolute/NEW_PUBLIC_DERIVED_JSON
```

The output is exclusive-create. The source must remain the reviewed frozen
revision. No 45-package permission conclusion exists until actual capture and
separate interpretation provide it.

## Local controls

The nine controls use the original successful pilot's complete public evidence
and its two exact pinned private logs, plus explicitly synthetic negative
fixtures in temporary local directories. They verify source closure, actual
two-stream terminal schema, held child retirement, scope/argv rejection,
unsettled STOP, exact prior Beike literal results, target/User 0 boundaries,
whitespace/missing/duplicate handling and AppOps scope limitations. They do not
claim a future batch or submit a process. Full stdout/stderr and the source
closure validation output are saved with this candidate.
