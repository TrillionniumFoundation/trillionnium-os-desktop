# A03 follow-up acceptance — 2026-10-17 UTC

Branch: `agents/A03-control-core`; follow-up [PR #86](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/86).
Latest incorporated main: `acd9ee30d51c405b32a36ff02ce25a9272b65834`.
A00 merged the prior 113-test [PR #50](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/50) while this follow-up was in progress.
Exact tested code: `b671c42ac8006abcf6290abbe64197e4c488f7b6`.
The subsequent merge/evidence commit preserves main's added A02 pinned-host
workflow and adds this report, the historical pointer and captured evidence.
The merge changes no Rust source, manifests, lockfiles or test entry points
relative to the tested code commit. Code/test hashes are recorded alongside
the logs in `evidence/2026-10-17/`.

## Three additional blockers fixed

1. **Dead child cap constraint.** `ResourceDomainInner::drop` removes its
   immediate parent's active child-cap entry only when the last strong
   reference disappears. Clones, grants, descendants, retained results and
   reservation tokens still keep the constraint alive. Stable identity
   tombstones, parent CPU consumption and family clock are preserved. The
   original eight lifecycle regressions produced **0 passed / 8 failed**
   before the fix, then **8/8 passed**. Fix commit:
   `7c07dc5992a29fa7e2f7df73822617aacd59e7a4`.
2. **Slow callback blocks unrelated history and admission.** Each slot now
   separates the long execution gate from the short state mutex. Queries,
   retirement and invariant audits can observe Executing as Reserved while
   the callback is paused. Namespace loss first closes admission, releases
   the table lock, waits/fences execution gates and only then completes loss.
   Two simultaneous loss callers wait for all admitted callbacks without
   preventing observation. Before the fix, the initial five regressions were
   **1 passed / 4 failed**; all six final regressions now pass. Terminal
   snapshots remain immutable and never regress to Reserved.
3. **Unbounded recursive resource destruction.** An isolated pre-fix probe
   created 1024 parent-linked domains on a 64KiB host thread stack and aborted
   during final-reference destruction (SIGABRT / shell exit 134). The 64,
   128 and 256-level controls completed. `MAX_RESOURCE_DEPTH=64`, including
   the root, now rejects deeper creation with `ResourceError::Exhausted`
   before consuming identities or modifying child metadata. Two additional
   tests verify the boundary, unused rejected IDs and maximum permitted
   destruction on that host stack. This is not native kernel stack proof.

## Exact-source validation

The previous scratch/toolchain contents were not retained in the current
cloud container. Normal Bash execution was restored and the fixed toolchain
was reinstalled locally: `nightly-2026-07-21`, rustc
`1.99.0-nightly (87e5904f5 2026-07-20)`. No external SSH endpoint was found or
used. Validation ran from a clean detached checkout of the code commit;
`source-diff.patch` is empty. This is Linux x86_64 host execution.

```sh
sh tests/control/run-validation.sh /tmp/a03-validation
cargo build --locked --offline --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
```

The script runs Cargo tests, strict `clippy --all-targets -- -D warnings` for
both backends, rustfmt checking and the no_std target check. Results:

| Test target | std | portable-spin on host |
| --- | ---: | ---: |
| Library unit tests | 6 | 6 |
| control_conformance | 81 | 81 |
| delivery_adversarial | 6 | 6 |
| kernel_handoff | 8 | 8 |
| resource_adversarial | 12 | 12 |
| resource_lifecycle | 10 | 10 |
| nonblocking_history | 6 | 6 |
| Total | **129 passed** | **129 passed** |

Both backends: 0 failed, 0 ignored, 0 filtered; no doctests. These are
258 executions of the same 129 test functions, not 258 distinct scenarios.
Formatting, both strict Clippy runs and the x86_64-unknown-none rlib build
passed. Existing 1024-full-window/hanging-prefix and same-namespace 10,000
delivery tests remain part of the passing matrix.

Negative logs retain the original failures; the depth probe source and its
exact pre-fix build/run commands are included. Captured text logs only remove
trailing blank lines. `logs-sha256.json` and `source-sha256.json` cover the
evidence and exact tested source respectively.

## CI remains a separate integration dependency

The prior exact-head G0 run
[38932599590](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38932599590)
actually completed with **failure**, not queued. Its A02 ABI Rust tests
passed, but the ABI strict Clippy step failed on
`clippy::chunks_exact_to_as_chunks` in three A02-owned fixture readers.
Both A03 steps were **skipped**, so this CI run does not validate A03.
[A02 PR #76](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/76),
head `606244b6109b1060b4916baa76e3fdd14dcc5240`, contains the owner correction
and was still open/unmerged at inspection. Main now includes A00's A02-only
pinned acceptance workflow from #83; it does not change the old G0 failure or
run A03. Before follow-up PR #86 was opened, no associated PR run for the new
tested code head was returned. Do not label an unobserved check a CI pass.
A03 did not modify A02 or A00 workflow files, weaken linting, or re-run the
known unchanged failing job.

## Concurrency and real-kernel boundary

New channel-gated tests establish observations while callbacks are paused,
then always release and join workers before assertions. Coverage includes
pending query, unrelated reservation/sequence progress, immediate pending
retirement, invariant audit, closing admission, terminal observation under
publication contention, two loss callers and two independently paused
callbacks. Resource tests add 64 last-reference drop versus parent-CAS races.
The earlier same-D, revoke/commit, publisher, query/retire/loss and publication
visibility regressions still pass with both mutex backends.

No exhaustive loom/state-space proof or arbitrary weak-memory scheduling
coverage is claimed. There are **zero real kernel acceptance tests** in this
follow-up. IRQ/preemption locks, kernel allocator and stack discipline, SMP
migration, real copyout faults, asynchronous devices, process death/reboot,
and durable fsync/power-loss cuts remain A05/A06/A07 integration work.

The updated [API contract](../../libs/os-control/API_CONTRACT.md) gives A05
`reserve_or_get` / `execute_reserved` / QueryDelivery / RetireThrough, A06
the single ResourceDomain and result-receipt seam, and A07 the original-owner
authority and value-only K↔D binding. The actual kernel and Hepta owner still
do not consume this crate. G1/G2 remain open; model acceptance cannot close
those cross-owner blockers. The portable spin backend is not an IRQ adapter.

All changes remain in `libs/os-control/**` and `tests/control/**`. README is
0 bytes; HOS2 wire/golden, other agent sources and the original persistent
Hepta owner are unchanged. No second business database or Ollama was used.
