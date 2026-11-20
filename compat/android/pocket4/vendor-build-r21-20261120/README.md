# Pocket4 R21 vendor supervisor continuation

R20 stopped before starting a build because its retired-unit check expected
`MainPID` on a systemd scope. Scopes do not expose the service-only field.
The previously prepared R21 worker distinguishes `.scope` from `.service`
while retaining exact state, exit-status, stderr and control-group checks.
This packet completes the missing R21 outer supervisor and launch bundle.

## Changes and validation

`outer.py` is the exact R20 supervisor with only generation labels, paths and
the pinned bundle digest updated. Reversing those substitutions reproduces
the original R20 SHA-256 exactly. Admission thresholds, serial locks, build
and recovery budgets, original PID ownership and reaping behavior are unchanged.

`prepare.py` records that transformation. It requires the original R20 outer
and bundle as inputs and refuses to overwrite generated files. The source
worker and operational contract are existing immutable inputs; their full
hashes are in `PREPARATION.json` and `BUNDLE.json`. They are not rewritten by
this packet. Original paths are on the configured `ai395` build host under
`/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1/control/`.

`verify_retired_wire.py` extracts only the two pure parser functions from the
exact pinned R21 worker. Its 15 positive and negative cases passed, followed
by successful observations of the actual retired service and scope. It does
not import the worker or start a build. The complete result and durable
terminal identity are in `PARSER-VERIFICATION.json`.

## Actual execution

The single real launch used idempotency key
`p4android-20261120-3b9d-r21-original-supervisor-once`, with terminal
`dpty-1618aa2e0ba5842dbb2e4afdbe2af92bfeea50728dbfee0476bb3cd3f07ef41c`.
`EXECUTION-OBSERVATION.json` is a point-in-time observation, not a final result.
Always read the original terminal and the R21 `actual/outer-terminal.json`
before deciding whether a launch is still active or has completed. A quiet
terminal is not authorization to launch again.

The vendor build uses the fixed 2,359-file source cohort
`4d78aae1aba2ec9952c37153069cca85c5a87953`. The separate latest 2,360-file
runtime producer is `56548053c91840f2dd3de50db45b705069d35fa9`.
Validation or binaries from either cohort do not qualify the other.

The observed run passed `verify-cmake652-before` and entered
`normal-reconcile-lint652`. The full vendor result, Android boot, APEX device
custody, application runtime acceptance and production deployment were still
unproven at that observation. This packet makes no production-ready claim.

## Operational boundaries

The supervisor retains the original memory, disk-growth, CPU, runtime,
source-recovery and cleanup constraints. Do not run a competing build,
relaunch under a new key, mutate frozen inputs, or treat a failed/recovered
attempt as a successful vendor build. Original failures remain part of the
evidence. Application-source selection may advance independently only when
it does not mutate this frozen vendor contract.

## Final R21 result

The original R21 supervisor has now exited with code 1. Its build phase passed
both ordinary source verification commands and the lint reconciliation, then
failed during the real vendor Soong graph construction. The missing APEX module
names were `test_com.android.ipsec` and `test_com.android.permission`.

The same supervisor retained the original serial lock through recovery. The
normal source recovery and final lint652 verification both returned 0, every
owned unit retired, every created child was reaped, and the complete source
content bookend matched. The original native input and producer files remained
unchanged. This closes retirement and recovery for R21; it does not qualify a
vendor artifact. The final outer receipt is 538,436 bytes with SHA256
`1272d9ba69e958d8e4bdd3c1b2efbf7663f42a51e29cc760fb146ee5ad06e5bd`.

`FINAL-OBSERVATION.json` retains the terminal identities, exact final record
hashes, command results and next source scope. `RECOVERY-OBSERVATION-FINAL.json`
is the unchanged final recovery record. The earlier execution observation is
retained as historical evidence. The four omitted upstream provider files
(2,186 bytes) are being handled by a separate strictly monotonic successor
profile; no frozen R21 input was edited and no new build is claimed here.
