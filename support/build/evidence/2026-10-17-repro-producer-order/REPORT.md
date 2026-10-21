# Strict producer ordering: retained A3 failure and schema 4

The real full A3 attempt failed during Rust compilation, before any QEMU
invocation. It is not a guest boot failure or passing kernel test. The old
A3 outputs, target and profile were preserved. This phase contains the small
host scheduling experiment and support-only fix; full A4/B4 builds and boots
are separate validation requirements.

## Actual A3 observation

A3 used published source `4cf864b62859f0fdb39609589ddd9ef90c6dbc9d` and a new
empty target at a distinct real checkout. The command failed with exit 2;
all three profile custody checks remained true. The consumer `aster-bigtcp`
was refused because its `smoltcp` extern had no completed successful producer
available to the wrapper at that point.

The retained producer ledger has 608 events. `smoltcp` started at event 585
and completed successfully at event 607, the last event. Postfailure read-only
inspection found that both its `.rmeta` and `.rlib` still had exactly the
device, inode, size and mtime recorded in the completed receipt. There was
no current stat mismatch or artifact alias. The exact observations, original
receipt and console error lines are in `A3-smoltcp-observation.json`.

This is consistent with Cargo metadata pipelining: a dependent library can
start when its dependency's metadata is ready, before that dependency finishes
code generation. Schema 3 required a completed producer immediately. A3 did
not separately record wall-clock timestamps for its rejected consumer, so
this report does not invent a precise historical timing trace. The controlled
actual-Cargo experiment below reproduces the incompatibility.

## Actual Cargo/rustc experiment

The fixture has a three-node library dependency chain:
`pipeline-leaf` → `pipeline-middle` → native binary. A shim invokes the real
fixed nightly rustc with every original argument and inherited jobserver FDs,
then intentionally delays the successful leaf compiler's exit by one second.
Rustc has already emitted metadata notifications; the strict producer wrapper
does not yet have full successful completion. This is a scheduling probe,
not replacement compiler code generation.

Each case has a new source fixture, absent target, complete source/manifests,
compiler arguments, producer ledger, shim event log and console log.

| Case | Actual Cargo jobs | Cargo build | Native execution |
| --- | ---: | ---: | ---: |
| Parallel control | 2 | 101, expected producer refusal | Not run |
| Serial control | 1 | 0 | 0 |
| `build.pipelining=false` control | 2 | 101, expected producer refusal | Not run |
| Final launcher, caller requested 2 | 1 | 0 | 0 |

The aggregate experiment CLI exits 0 when it observes these expected outcomes.
The two Cargo failures remain failures, not passing builds. The successful
native programs print `PIPELINE_NATIVE_PASS`; they are Linux host fixtures,
never kernel or QEMU evidence. No byte-equality claim is made between these
scheduling fixture cases.

The fixed Cargo still pipelines with the obsolete disable setting. Its public
configuration reference explicitly marks `build.pipelining` as unused and
states that pipelining is always enabled. The timings documentation explains
that dependents may start while their dependencies perform code generation:

- https://doc.rust-lang.org/cargo/reference/config.html#buildpipelining
- https://doc.rust-lang.org/cargo/reference/timings.html

## Minimal opt-in fix

Schema 4 forces `CARGO_BUILD_JOBS=1` only in the opt-in reproduction launcher.
`policy.json` records the caller's value, actual selected value 1 and reason.
The public kernel entry inherits the explicit value through its existing
`${CARGO_BUILD_JOBS:-2}` default; normal build defaults remain unchanged.

The producer gate and compiler wrappers are unchanged. The `profile.py` bytes
are identical to schema 3 except for the schema literal. No unknown producer
is accepted, no receipt is synthesized, and no waiting loop, content fallback,
compiler stream buffering or upstream/core modification is introduced.
`strict-producer-gate-unchanged.json` binds this comparison to the old published
source. The final host probe calls the actual new launcher environment helper
with caller jobs 2 and observes actual Cargo jobs 1, build 0 and native run 0.

The focused suite has 32 tests. Both `python3 -I` and `python3 -I -O` completed
with exit 0, totaling 64 executions. The new subprocess test verifies that the
opt-in launcher overrides a parallel caller, preserves an unrelated variable
and leaves the caller mapping unchanged. All earlier strict producer negative
tests continue to pass.

## Scope and bindings

`code-freeze-v4-final.json` preserves the local preparation state. Its HEAD is
not a claim about the final remote producer. `source-bindings.json` separately
binds the final published commit, Git tree, six source byte hashes and Git
modes when this evidence phase is frozen.

The exact full A3 failed build evidence is packaged independently. This phase
contains only its read-only root-cause receipt and the complete small host
experiment. A4/B4 success, kernel bytes and QEMU logs must come from their
actual fresh builds. No cross-host, arbitrary-environment or immutable-content
claim is made.
