# A03 callback lifetime and embedded resource metadata — 2026-10-17 UTC

Branch: `agents/A03-control-core`; [PR #133](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/133).
Exact tested source: `537ad2f69a183f7bf70aa0f463eeccc391e12c13`.
Latest incorporated main: `df8e2decbb1f4efb501d03f6141f81c7a128ac1a`.
Synchronization commit `7e9b9bbe0b8967ca0f1a38ffa0a710235224b8dc` has the
**same complete Git tree** as the tested source:
`368edbce70088d702919b89655afd987b16ee305`.
The later evidence commit changes only this report, its pointer and captured
logs. All runtime evidence here is **host model**; no A03 kernel consumer,
mutating HOS2 G1 or durable Hepta G2 is established by these tests.

PR #123 was merged at `25f809623f22b205189a1ad3fa995667189a45b6` while this
follow-up was in progress. Its exact-head code/security reviews completed
without findings. New source belongs to PR #133. Main now contains the actual
A06 CPU cgroup/scheduler alongside A05's read-only QueryAbi; this report does
not rerun or relabel their kernel/QEMU evidence as A03 execution.

## Source changes

A consuming `FnOnce` invocation destroyed captures before the core could
publish its result or release its execution gate. A closure body that only
borrowed a captured Vec/Arc could therefore free storage under the gate.
Implicit capture destruction could also wait for namespace loss or panic
before publication. The core now requires `FnMut`, borrows it for the one
invocation and retains its owned captures until after the gate is released,
including on unwind. Valid results are published before capture cleanup.
The same D still never obtains a second callback invocation.

This tightens the experimental Rust callback bound. Consuming-only closures
must be adapted; there is no wire change. Explicit allocation, destruction or
namespace reentry inside a callback remains the trusted adapter's obligation.
Seven new host tests cover native/host success, body unwind, malformed outcome,
unused terminal retry, wrong native type and capture-destructor panic. Cleanup
workers are joined; bounded waits turn the historical gate-order defect into
specific assertions rather than accepting a hung test process.

`NativeResourceState` is executable Rust for embedding beside the sole actual
CPU accounting state under its original owner lock. Its only mutable metadata
is revision plus a permanent lifecycle/uncertainty fence; trusted resource and
stable-object identities are fixed. It is non-Clone and contains no budget,
runtime counter, clock, parent table, allocator, lock, grant registry or ledger.

`apply(NativeResourceUpdate, effective_ns, consumed_ns, &mut mutation)` checks
identity, expected revision, the fixed HOS2 budget profile and the entire saved
receipt before an infallible borrowed mutation. A private valid receipt converts
to `PublishOutcome` without a fallible post-effect step. Normal return advances
revision once. Panic permanently retains Indeterminate, even if a host mutex's
poison is recovered. There is no reset or optimistic no-effect inference.

`apply_owner_configuration(&mut mutation)` advances the same checked revision
for ordinary owner/Linux writers, without fabricating D or a publisher. It
accepts the owner's own validated non-HOS2 period/unlimited-quota policy.
`invalidate()` permanently closes a detached owner without altering budget,
usage, revision or earlier D outcomes; it cannot downgrade an indeterminate
effect into a known refusal. Private unit fixtures exercise MAX revision and
exhaustion without exposing a revision-reset constructor.

Seven native-owner tests use one mutex containing the sole quota/usage plus
these metadata. They cover two D with the same expected revision, compatibility
writes invalidating old CAS, same-cap updates preserving consumed usage,
pre-effect identity/receipt refusal, panic fencing new D/ordinary writes,
management-snapshot revalidation and invalidation of an old pinned owner.
They create no host ResourceDomain or second budget/accounting instance.

## Exact-source validation

Linux x86_64, pinned `nightly-2026-07-21`, rustc
`1.99.0-nightly (87e5904f5 2026-07-20)`. Final commands used a clean detached
checkout and an isolated Cargo target directory. The source diff is empty.
All 52 code/manifest/fixture input hashes still match the evidence head;
Markdown is excluded. Referenced A06 kernel blobs are separately recorded
as read-only context, not compiled inputs or tests in this acceptance.

```sh
sh tests/control/run-validation.sh /tmp/a03-owner-validation
cargo build --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
python3 tests/control/reproduce-regressions.py /tmp/a03-owner-negatives
python3 tests/control/lock_alloc/run-checks.py /tmp/a03-owner-callback --callback-only
python3 tests/control/lock_alloc/run-checks.py /tmp/a03-owner-historical --historical-only
```

The validation runner includes both Cargo backend suites, fmt, both strict
Clippy checks, bare-target check, bounded Loom and current lock-allocation
validation. The additional no_std library build passed.

| Host test functions | std | portable-spin |
| --- | ---: | ---: |
| Previous acceptance | 198 | 198 |
| New internal resource metadata tests | 2 | 2 |
| callback_lifetime | 7 | 7 |
| native_resource_state | 7 | 7 |
| Total | **214 passed** | **214 passed** |

Zero failed, ignored or filtered; no doctests. These are 428 executions of
214 distinct test functions. Existing 10,000-write, full-1024-window/hanging
prefix, partial-retirement, resource/revoke and recovery tests still pass.

The regression driver completes **17 checks**, requiring **18 designated
assertion failures** and **79 fixed passes** across eleven fixed targets.
In particular, exact historical d172's callback target compiles and runs to
completion with **2 passed / 5 expected failures**, raw exit101. The five
failures detect success-publication/gate cleanup, body unwind, malformed return
and capture panic; unused-callback positive controls still pass. The process
must finish within its outer limit; compiler failure/timeout cannot count as
negative acceptance. Other historical and explicitly synthetic controls retain
their previous definitions. The driver needs its four pinned historical commits.

## Allocation and concurrency

The allocation workspace copies every actual production module unchanged,
substituting only its test std Mutex shim. Hooks remain in a separate unsafe
test crate; production unsafe_code is still forbidden. Fixture/shim equality,
source inventory/bytes, pinned compiler provenance, fmt and strict workspace
Clippy are checked. Failed allocator calls are counted before fault injection.

| Same 19 native namespace scenarios | Locked alloc | Locked realloc | Locked free | Raw exit |
| --- | ---: | ---: | ---: | ---: |
| e59 historical table/control | 20,016 | 0 | 3 | 101, expected |
| d172 capture-only control | 0 | 0 | 2 | 101, expected |
| Tested source | 0 | 0 | 0 | 0 |

The added capture scenario only borrows Vec/Arc captures in the body. The d172
control requires that specific locked cleanup, complete inventory and zero
locked calls in every other scenario/setup. The current check requires all
counts zero. Instrumentation positive controls and two targeted fallible ring/
retirement allocation failures remain required. This is a std lock-depth probe,
not an assertion about arbitrary callback bodies or the kernel allocator.

| Bounded actual-source Loom fixtures | Schedules |
| --- | ---: |
| Prior 12 models: reservation, effect-once, revoke, publication, query, retirement, loss and reconciliation | 26,445 |
| Native metadata CAS / ordinary compatibility write / invalidate under one owner lock | 230 |
| Total: **13 models** | **26,675** |

The new three-worker model requires revision=1+successful configuration writes,
unchanged used quota, no mutation after invalidation, immutable prior terminal
D and refusal of a fresh D against the invalidated original owner. Existing
models include the two-stage reserve/loss and overlapping-retirement windows.
All models, fmt and strict harness Clippy passed; source hashes and inventory
match before/after. Bounds remain main plus three workers, preemption_bound=3,
max_branches=10000, no permutation/time cutoff. This verifies finite fixtures,
not all values or interleavings. Independent module/oracle review found no
remaining blocker within these source changes.

Still outside coverage: std/alloc Arc/Weak ownership atomics/finalization;
allocator internals/general OOM; real IRQ/preemption/SMP lock adapters and weak
memory hardware; CPU migration/hotplug, actual usercopy/device effects, reboot
and Hepta fsync/power-loss cuts. Loom 0.7.2 cannot verify poisoned Mutex unwind
recovery; actual host-thread panic tests cover that limited path. Metadata does
not validate a real boot clock or perform runtime settlement. Portable-spin
remains experimental and does not disable IRQ/preemption. The host ResourceDomain
still has allocating mutation paths.

## A05 / A06 / A07 handoff

A05 retains trusted process/session/capability resolution, exact NativeTarget
pinning, reserve/retry, typed `execute_native_reserved::<ActualOwner, _>`,
QueryDelivery and RetireThrough. Its callback now satisfies FnMut; the core
still invokes it once. Observation conversion must fail closed on None.

A06 can embed `NativeResourceState` alongside its original sole CpuMax under
`CpuControl.max`'s actual lock. It checks management snapshot/lease/ancestors,
parent policy and settled usage first, then borrows the infallible actual budget
mutation into apply and publishes the valid receipt. Linux cpu.max and lifecycle
writers must advance the same metadata. Parent periods require normalization
or explicit refusal, not a raw quota comparison. The actual subtree-control
path can replace the controller Arc: old metadata must be invalidated as part
of replacement or the adapter must prove that its pinned owner is still current.
A retained Arc alone proves memory lifetime, not scheduler membership.

A07 keeps K and K↔D in the existing durable owner and acknowledges only its
confirmed contiguous terminal prefix. No second durable business database is
created. Full signatures and lock obligations are in
[API_CONTRACT](../../libs/os-control/API_CONTRACT.md).

Only A03 paths differ from incorporated main. README remains 0 bytes; HOS2
wire/golden and other agents' source remain unchanged. Actual A05/A06 consumer
integration and A07 persistence remain cross-owner G1/G2 work. The source G0
run 39007400020 was queued when captured; live CI/reviews are separate from
these local passing counts. Logs, exact code hashes, raw-log normalization
metadata and reference owner/tree identities are under
`evidence/2026-10-17-owner/`.
