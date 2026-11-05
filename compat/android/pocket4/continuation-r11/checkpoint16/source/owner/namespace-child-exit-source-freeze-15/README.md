# Namespace-owner Child exit retention — candidate 15

This source-only candidate is derived from the exact 32 inputs of the actual producer14 compile receipt (`a916592cc708dc76411b482a371214410bca4662f6ff72dccd5083d88872b6a6`). Four preimages and four candidate files are included. No original freeze or failed runtime has been changed.

## Actual defect and remaining uncertainty

Owner14's retained response was `ok: true`, `state: stopped`, with `Android cell exited with signal: 1 (SIGHUP)` and `first_failure: null`. The overall Owner14 invocation correctly remained a failed startup: it reached init DONE but never ACTIVE. The exact original retirement and external cleanup are distinct from startup success.

The source explains a cause-loss path: DevelopmentCell observes its exact namespace-owner Child exit, cleanup asks the worker to cancel, the worker can return normally at its cancel-first branch, and the subsequent empty Session reason can erase the exit context. This does not prove the sender of SIGHUP or the guest's original boot failure.

The separate broker error was an `ns/pid_for_children` ENOENT on the held init proc directory. LifecycleSnapshot checked liveness before opening namespace entries, but an error returned before its final live check. The first live observation alone cannot classify the process at the later failed open.

The two fixed data-image directory reads returned debugfs status 0 with empty stdout and explicit `File not found by ext2_lookup` stderr for `/tombstones` and `/system/shutdown-checkpoints`. This is tool output about two fixed paths. It proves neither a clean boot nor a boot cause; no further image enumeration is added.

The exact retained sources and hashes are in `evidence/owner14-cause-loss-review.json`. The original runtime remains FAIL.

## Child exit retention

`child-exit-only.diff` changes three supervisor files:

- DevelopmentCell observes the real Child wait status before asking cleanup to cancel. Stop first polls the Child, so a previously observable exit is saved before this later Stop records intent. If polling itself errors, the original cancellation action is still attempted; the original error remains an error.
- Owner stores whether its Stop method was already requested. The observer also samples the existing RETIRING/RETIRED phase. These flags record prior observed intent and state, not the sender of a signal, a user identity or a guest shutdown reason.
- One optional, bounded audit slot retains raw wait status, code, signal, core flag, observation time and the earlier actual OwnerAttached process record. It does not reopen a dead process. Missing identity marks the recording incomplete. Duplicate observations cannot change the initial status or its prior-intent flags.
- Only a non-success wait status observed before both Stop and worker retirement records a Runtime failure. Successful exit remains an observation; it is not automatically reclassified as an Android fault. A previously recorded failure remains first.
- A successful resource retirement cannot replace an already known termination reason with None. DevelopmentCell copies a known cause even if retirement itself later returns an error. Cleanup errors and incomplete retirement still retain their original gates.

The first recorded failure is an observation order, not an assertion of physical boot causality. The record grants no permission. No event milestone, namespace, capability, socket, memory/PSI budget, enrollment, daemon authorization, network teardown, resource removal or claim-release predicate is relaxed. The optional absent field is omitted from serialization and historical snapshots deserialize with None. The existing normal qualifier does not reject this optional extra field; it still requires actual ACTIVE and the complete original normal-retirement evidence.

## Post-error pidfd observation

`post-error-observation-only.diff` changes only relay `lib.rs`:

- The original complete LifecycleSnapshot capture body is byte-identical under `capture_inner`.
- `capture` still propagates failure. On failure only, it makes one zero-time `poll` of the same held pidfd, captures poll errno immediately, and appends pid/birth plus held pidfd/proc identities.
- The original typed cause remains owned and is displayed first. A secondary observation error cannot replace its errno or turn failure into success. No namespace retry, replacement PID lookup, new FD, thread or fallback is added.
- A ready pidfd is later death evidence. A not-ready result is only that later observation; it does not prove liveness at the earlier failed namespace open or that a missing future PID namespace is legitimate. Both outcomes remain rejected.

All original ProcessPin live checks, NamespacePins checks, CellAuthority comparisons and runtime LMKD authentication/public-view checks remain unchanged.

## Controls and current validation

Eight Rust controls are added, but **none has been compiled or executed here**. The local environment has no rustc or Cargo. The six supervisor controls use exact owned ordinary children and the production Process/audit methods: real SIGHUP and sticky duplicate, exit 17 raw status, intentional Stop with TERM, prior worker failure followed by retirement, successful exit 0, and missing recorded identity. They do not instantiate a full Owner or manufacture a retirement proof.

Two relay controls use held ordinary Child pidfds: a real missing proc entry while the child remains live preserves ENOENT plus the later not-ready observation; an actually reaped child goes through the production snapshot capture and remains rejected with a ready pidfd. They do not reproduce a live process without a future PID namespace.

`source_check.py` was executed locally. Its `static-review.json` verifies all 32 actual input pins, all four changed preimages, exact split/full diffs, cancellation and observation order, the unchanged snapshot body and security/retirement functions, and the eight added test declarations. This is a lexical source-scope check, not a Rust compiler or runtime test.

Expected matching suite counts, subject to real build and execution, are 39 relay tests, 128 supervisor tests and the unchanged 7 ordinary IPC controls, plus the original targeted retirement/worker-context/entry-ABI gates. There is no candidate build PASS, constructor execution or full Owner qualification.

## Next gate

Root reviews these independent diffs, then may prepare a fresh matching build/ordinary-control request bound to these exact inputs. No device request is in this source freeze. Main's observed pids.max 12288 to 6144 change remains unresolved; this candidate provides no new runtime admission and does not reuse an old Main fence. Android boot, LMKD first ACTIVE, RC reload/reinit and installed production integration remain open. This work is after the fixed CP15 cut and must not alter that checkpoint.
