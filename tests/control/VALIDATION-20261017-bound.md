# A03 bound native execution and Loom acceptance — 2026-10-17 UTC

Branch: `agents/A03-control-core`; [PR #94](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/94).
Incorporated main: `47288c4465720d125658b392efc655b333c90868` (A02 #95).
Exact tested source: `58ac542b448ee83f7b5b9ddabdfe7136fb44dccc`.
The following evidence commit adds this report, the latest pointer and captured
evidence, plus an API wording clarification: take A06's mutation lock inside
the callback, after the execution gate. No Rust, Cargo or runner changes follow
the tested source. A03 runtime evidence remains **host model**; the bare-target
rlib is compilation evidence, not a real kernel G1/G2 acceptance.

## Fixed native execution context

The previous generic native callback received public RequestBinding fields but
not the original owner instance or reservation-bound ancestor epochs. A trusted
adapter could accidentally re-resolve the same public IDs to another allocation,
or use fresh post-revocation ancestry to authorize an old D. Two same-source
oracles compile against genuine previous head `86663ea...` and produce
**0 passed / 2 expected assertion failures, exit 101**. These are adapter-context
mixups, not unauthenticated wire exploits or evidence of a compromised callback
being made safe.

`execute_native_reserved::<T, _>` now passes a privately constructed borrowed
`NativeExecution`: `owner() -> &T`, `binding()`, `ancestor_epochs()` and `id()`.
They come from the exact stored request and strong owner pin. Generic
`execute_reserved` accepts host requests only and rejects native callbacks
before admission. Wrong concrete types and wrong entry kinds leave Reserved
unchanged, so a correctly typed worker can still execute. Both public paths
share one private fencing/admission transition; pending, immutable terminal,
loss, panic and reconciliation rules remain in force. A06 must recheck actual
current grants/leases/ancestors/CAS/runtime under its original mutation lock.

Eleven new bound-owner tests cover identity/context, dropped external handles,
wrong type/kind/publisher/namespace, stale ancestry, maximum ancestry, terminal
retry and 32×8 same-token plus 64 revoke/commit races. Two normal regression
tests reject the previously allowed generic native path.

## Native owner lifetime

A native owner storing a strong ControlCore back-link creates
`namespace -> slot -> owner -> namespace`. An isolated probe from exact
`86663ea5a934d085a80fcaeaacca535bfb283b77` reproduced retention after all
external handles dropped, then explicitly cleaned the cycle before the
expected assertion failure (exit 101). Source, build commands and hashes are
captured under `strong-backlink/` in this acceptance's evidence.

`ControlCore::downgrade() -> WeakControlCore` and
`WeakControlCore::upgrade() -> Option<ControlCore>` provide the correct
non-owning back-link. Five tests show final namespace/owner release despite
old tokens, Drop reentry during retirement/loss, and intentional strong history
references. Weak upgrade creates no retirement authority or old-D replay right.
Callers must migrate their strong back-links: this API does **not** automatically
collect arbitrary Arc cycles. An external owner Arc or transient admitted pin
still retains its own lifetime.

## Repeatable exact-source checks

Fixed `nightly-2026-07-21`, rustc
`1.99.0-nightly (87e5904f5 2026-07-20)`, Linux x86_64. All commands ran from a
clean detached checkout of the tested source, using a fresh Cargo target.
The incorporated A02 codec was compiled as the existing dev dependency.
`source-diff.patch` is empty.

```sh
sh tests/control/run-validation.sh /tmp/a03-bound-validation
cargo build --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
python3 tests/control/reproduce-regressions.py /tmp/a03-bound-negatives
```

The runner performs default and portable-spin Cargo tests, fmt, both strict
Clippy runs (`--all-targets -- -D warnings`), bare-target check and the separate
Loom harness. The direct test command is `cargo test --locked --manifest-path
libs/os-control/Cargo.toml`; portable-spin adds
`--no-default-features --features portable-spin`.

| Host Rust tests | std | portable-spin |
| --- | ---: | ---: |
| Existing targets, including migrated native_handoff | 150 | 150 |
| native_bound_execution | 11 | 11 |
| native_context_negative | 2 | 2 |
| native_lifetime | 5 | 5 |
| Total | **168 passed** | **168 passed** |

Both backends have zero failed/ignored/filtered and no doctests: 336 executions
of 168 distinct functions. Formatting, both strict lints, bare-target check and
rlib build passed. The negative runner requires seven actual assertion failures
across historical token (3), historical native context (2) and explicitly
synthetic lock-held cleanup (2), then **38 passing** fixed tests across five
targets. Compilation errors or timeouts cannot count as expected failures.
The negative runner needs the two named historical commits in local Git history.

Evidence: `evidence/2026-10-17-bound/`. Source/log SHA256 manifests attest the
exact code/manifest/fixture inputs (Markdown excluded) and captures. EOF
whitespace is normalized in captured logs only;
normalization metadata retains original byte counts/hashes. Negative subprocess
stdout hashes refer to the raw outputs; the capture manifest covers saved files.

## Bounded concurrency model results

The independent harness pins Loom 0.7.2 in **tests/control/loom/Cargo.lock**.
Production dependencies/features are unchanged. It copies actual lib.rs and
native.rs bytes unchanged to a temporary crate and replaces only sync.rs with
the tracked Loom Mutex adapter. Before/after hashes are checked; temporary
sources/artifacts are deleted. It does not reimplement the state machine.

| Model | Explored schedules |
| --- | ---: |
| same-D reservation / single effect | 716 |
| revoke / commit | 22 |
| retire / query | 19 |
| publish / observe complete result | 92 |
| history loss / callback fencing | 48 |
| typed native owner / same-token execution | 52 |
| Total | **949** |

All **6 models passed**, plus harness fmt and strict Clippy. Each fixture uses
main plus at most two workers, preemption_bound=3, max_branches=10000, and no
time/permutation cutoff. An assertion, deadlock, branch-limit error or missing
model count fails the runner. These are bounded transition-model results,
separate from the 168-test backend runs.

Existing real host-thread tests remain: same-D reservation, revoke/commit,
retire/query/loss, publication visibility, paused callbacks, parent spending,
1024-full-window with a hanging prefix, and same-namespace 10,000 writes.
Another test retains 10,000 old tokens without retaining retired slots.

Uncovered: std/alloc Arc/Weak reference-count atomics and finalization are not
instrumented by Loom; their lifetime regressions use host threads instead.
Loom does not cover more workers/preemptions, arbitrary inputs, allocator
failure, actual IRQ/preemption/SMP adapters, scheduler migration/hotplug,
real usercopy, async devices, process death/reboot or durable fsync/power-loss
cuts. No exhaustive weak-memory or actual kernel proof is claimed.

## A05/A06/A07 handoff

A05 resolves a genuine owner and NativeGrant, constructs from the original
wire header, reserves globally, then sends token/publisher to A06's typed
owner adapter. A06's candidate `SubController<CpuController>` is private, so
that adapter must live in A06's module and call the typed entry with its actual
owner type. Do not expose another Process/wrapper/shadow budget as a substitute.
A07 retains K=(scope_id,operation_id) and K↔D in its existing durable owner;
only durably confirmed continuous terminals may be retired with original-owner
authority. No second persistent business ledger is introduced.

[API_CONTRACT.md](../../libs/os-control/API_CONTRACT.md) contains full signatures,
lock and history invariants. A05's genuine read-only QueryAbi guest progress
is retained, but no mutating A03 kernel consumer or durable A07 consumer was
found. Those actual integrations remain G1/G2 work for their owners.
GitHub CI/reviews are reported separately on PR #94; queued/running is not pass.

All PR changes relative to incorporated main are A03-owned. Main's A02 additions
are preserved unchanged by merge. HOS2 wire/golden are untouched, README is
0 bytes, and no Ollama is used.
