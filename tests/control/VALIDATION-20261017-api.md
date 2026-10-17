# A03 reservation enum imports — 2026-10-17 UTC

Branch: `agents/A03-control-core`; [PR #146](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/146).
Exact tested source: `a42d078004ea3b29b65bbaecb89932985330e330`.
Latest incorporated main: `1247d30b2a8d82598482512f4d614b622499e541`.
Tested complete tree: `ff0ee9f3431eecfac8f048e354326972de3f173c`.
The acceptance commit adds only this report, its index pointer and evidence;
all 53 tested code/manifest/fixture hashes remain unchanged.

## Reproduced defect and fix

The initial public-backend commit a2ef27a changed the original
`ReserveAttempt` enum into a concrete type alias. Rust permits qualified
variant expressions through an alias, but rejects variant imports such as
`use os_control::ReserveAttempt::{Existing, Reserved}`. The same typed consumer
compiled on main1247d30 and failed on a2ef27a with E0432, identifying
`ReserveAttempt` as a type alias rather than a module.

`ReserveAttempt` now re-exports the actual `ReserveAttemptWith` enum. The enum
has a default backend type parameter. Both names permit variant imports and
retain the same type identity for default and custom backends. Three Cargo
tests compile those imports and match actual native reservation/retry returns;
typed observations remain values, never new execution authority.

This is a scoped compatibility repair, not a full source-compatibility claim.
Without an expected type, standalone `Existing(observation)` or
`ReserveAttempt::Existing(observation)` cannot infer B after the enum becomes
generic. Supply `let attempt: ReserveAttempt = ...` or a backend type argument.
The inference boundary is explicit in the source and consumer contract. No
request/result state transition, lock role, D identity, wire byte or resource
accounting rule changes in this follow-up.

## Exact-source verification

Pinned `nightly-2026-07-21`, rustc
`1.99.0-nightly (87e5904f5 2026-07-20)`, Linux x86_64. The complete matrix ran
from a clean detached source checkout with an isolated Cargo target directory;
the captured source diff is empty.

```sh
sh tests/control/run-validation.sh /tmp/a03-api-matrix
python3 tests/control/reproduce-regressions.py /tmp/a03-api-negatives
# The first command also executes this separately reproducible compile control:
python3 tests/control/api_compat/run-checks.py /tmp/a03-api-compat
```

| Check | Exact-source result |
| --- | --- |
| std host Cargo tests | **223 passed**, 0 failed/ignored |
| portable-spin host Cargo tests | **223 passed**, 0 failed/ignored |
| New API target | 3/3 in each host configuration |
| Source fmt, both strict Clippy configurations | Passed |
| Portable no_std check and bare-target rlib build | Passed |
| External no_std backend fmt/build/strict target Clippy | Passed |
| Source-compatibility compiler control | Two positive compiles and one exact expected E0432 |
| Runtime regression driver | 20 checks; 19 designated assertion failures; 88 fixed passes |
| Native allocation probe | All 19 scenarios: zero locked alloc/realloc/free |
| Loom | 19 models, **27,253 schedules** |

The 446 host executions run 223 distinct test functions. Existing 10,000-write,
hanging/full-window, wrong publisher, revision/cap/target conflict, immutable
refusal, retirement, usage retention and copyout retry scenarios still pass.
The model counts and bounds match the previous acceptance: at most three
workers plus main, preemption_bound=3, max_branches=10000, no time/permutation
cutoff. All named models and strict harness checks pass, with source hashes
and inventories unchanged. Six public-backend models and the current allocator
probe use all production modules byte-for-byte, without replacing sync.rs.

The new compile-control runner pins the original main and genuine broken
commit, copies their complete dynamic Rust module inventories, and compiles
one identical consumer against all three versions. Every library must first
compile successfully. The broken consumer must exit1 with the unique E0432,
exact alias-not-module primary span at consumer.rs:2 and the corresponding
single-error abort summary. Arbitrary compiler errors, timeouts, source changes
or a different consumer cannot pass. This compiler negative is separate from
the 19 runtime assertion failures; it does not inflate the runtime count.
The tiny consumer oracle is retained in its JSON; no production source
snapshot or binary is retained.

The current allocation probe also passes its positive instrumentation,
thread-local depth/unwind and two targeted fallible-allocation controls.
Historical e59/d172 allocator counterexamples were not rerun for this enum-only
change; their unchanged fixture hashes and prior results remain in the
[backend acceptance](VALIDATION-20261017-backend.md).

## Evidence and integration boundary

Evidence lives in [evidence/2026-10-17-api-compat/](evidence/2026-10-17-api-compat/):
compiler JSON diagnostics, per-command logs, model counts, allocation events,
53 input hashes, immutable README/wire/golden object hashes and GitHub status.
Capture normalization removes trailing whitespace/blank EOF lines; metadata
records raw and stored hashes/sizes. The retained GitHub snapshot reports
Actions queued and code/security review running. Neither is called a pass.

Runtime evidence remains **host model**. No real A03 kernel execution, IRQ/SMP
lock-adapter acceptance, scheduler enforcement or durable Hepta K confirmation
is established. Uncovered interleavings remain arbitrary schedules beyond the
model bounds, Arc/Weak ownership atomics/finalization, general OOM, real owner
lock/IRQ/preemption order, CPU migration/hotplug, actual copyout and fsync/reboot
cuts. Loom does not verify poisoned-mutex unwind; limited host panic tests do.

A05 continues to use `ControlCoreWith<B>`, typed tokens/views,
`reserve_native_or_get`, `execute_native_reserved` and authenticated history
query/retirement. A06 retains the sole actual resource owner and uses
`NativeResourceState` under its original mutation lock. Both enum names now
support matching these typed results. A07 persists K↔D and confirms a terminal
prefix in the existing Hepta ledger. The detailed
[API contract](../../libs/os-control/API_CONTRACT.md) records the inference
boundary and owner obligations. G1/G2 remain actual integration work.

All changes stay within A03 ownership. README is zero bytes; wire/golden
objects are unchanged; no second persistent K database is introduced.
