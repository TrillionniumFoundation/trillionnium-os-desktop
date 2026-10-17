# A03 management authority and failure recovery — 2026-10-17 UTC

Branch: `agents/A03-control-core`; [PR #109](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/109).
Incorporated main: `2e1d592c25335f3cd97f312e4f73545f305d6e61`, including
A00's portable/no_std G0 steps and merged A05 QueryAbi #87.
Exact tested source: `0b238d298a4c0ab03789d34d3c53a891ccae52f4`.
The subsequent evidence commit changes only reports, their pointer and captured
evidence. Results remain **host model** plus bare-target compilation. They do
not establish native mutating G1 or durable Hepta G2.

## Management and resource lifetime are separate

The new `ManagementGrantState` is a non-Clone value embedded once in the
existing resource owner's original mutation lock. It stores one delegation's
identity, publisher, target/object, management epoch, validity interval and
cap ceiling. It has no budget, CPU counter, resource revision, registry,
internal mutex, global clock or persistent ledger. Existing whole-domain
`ResourceDomain::revoke()` keeps its semantics; it is not used as a substitute
for management-only fencing.

`check(saved_snapshot, canonical_binding, trusted_now)` checks current
revocation, instance and all immutable terms, target/publisher/epoch/period,
cap ceiling and `[issued_at_ns, expires_at_ns)`. A05/A06 must call it under the
same original lock as revoke, runtime settlement and resource CAS, using real
current BOOTTIME with rollback prevention. Snapshot creation alone proves no
current rights. `revoke()` closes only this delegation and returns the same
receipt on retry; epoch MAX saturates while revocation stays irreversible.
Applications can keep accounting under their admitted budget and an independent
manager remains usable. No automatic recovery cap, timer or unpause is implied.

`NativeGrant::from_management` binds the original owner and full snapshot;
`NativeExecution::management_snapshot()` borrows it from the stored request.
Same D with another origin, grant ID, ceiling, issued/expiry time, or Some/None
path conflicts even when public RequestBinding fields happen to match.
The old `from_owner` path remains available for an existing native authority
implementation and does not automatically gain lease checks.

Private Arc origin tags distinguish independent states with identical public
configurations. Replacing/destroying an old state cannot authorize its saved
snapshot through a newly constructed state. Tags hold identity only, not another
copy of liveness, resource policy or durable K history. Six independent identity
tests include replacement inside the same owner. A synthetic negative control
removing only two origin comparisons compiles and produces **2 passed / 4
expected assertion failures**; the original tests pass. This is a deliberate
control, not a claim that this draft flaw was previously shipped.

## Exact-source execution

Linux x86_64, pinned `nightly-2026-07-21`, rustc
`1.99.0-nightly (87e5904f5 2026-07-20)`. Commands ran from a clean detached
checkout of the tested source; `source-diff.patch` is empty. The incorporated
A05 files were preserved unchanged; this matrix does not execute their guest.

```sh
sh tests/control/run-validation.sh /tmp/a03-management-validation
cargo build --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
python3 tests/control/reproduce-regressions.py /tmp/a03-management-negatives
```

The runner runs `cargo test --locked --manifest-path libs/os-control/Cargo.toml`
for default std and with `--no-default-features --features portable-spin`, fmt,
both strict Clippy checks (`--all-targets -- -D warnings`), bare-target check
and the pinned Loom harness. The additional bare-target rlib build passed.

| Host Rust targets | std | portable-spin |
| --- | ---: | ---: |
| Previous targets | 168 | 168 |
| management_authority | 15 | 15 |
| management_identity | 6 | 6 |
| native_failure_recovery | 3 | 3 |
| Total | **192 passed** | **192 passed** |

Zero failed, ignored or filtered; no doctests. These are 384 executions of
192 distinct host test functions, separate from the Loom fixtures.
The regression driver requires **11 expected assertion failures**: historical
token 3, historical generic-native context 2, synthetic lock-held cleanup 2,
and synthetic origin-blind authority 4. It then requires **62 fixed passes**
across eight targets. Compiler errors/timeouts cannot count as negative passes.
The driver needs its two named historical commits in local Git history.

Source hashes, commands, exit codes and logs are in
`evidence/2026-10-17-management/`. Code/manifest/fixture SHA256 inputs exclude
Markdown. Saved logs normalize EOF whitespace only; capture metadata preserves
original hashes/sizes when normalization changes bytes. Negative report stdout
hashes refer to raw subprocess output; logs-sha256 covers saved captures.

## Concurrent and exceptional recovery

The separate pinned Loom 0.7.2 harness now copies **all src/**/*.rs modules**
byte-for-byte, replacing only sync.rs with its tracked Mutex adapter. It checks
both source content and inventory before/after, and deletes temporary copies.
Production dependencies/features are unchanged.

| Bounded model | Schedules |
| --- | ---: |
| Same D reservation / one effect | 716 |
| Resource revoke / commit | 22 |
| Retire / query | 19 |
| Publish / observe complete result | 92 |
| Loss / callback fence | 48 |
| Typed native same-token execution | 52 |
| Three-way retire / execute / loss | 2,385 |
| Two D, one resource revision CAS | 160 |
| Post-effect malformed receipt / reconcile / retry | 2,442 |
| Management revoke / native commit in original owner lock | 14 |
| Total | **5,950** |

All **10 models**, harness fmt and strict Clippy passed. Each fixture permits
main plus up to three workers, preemption_bound=3, max_branches=10000, with no
time/permutation cutoff. The runner requires the exact model names and positive
counts. The management model reaches both commit-first and revoke-first orders,
then keeps resource accounting and independent management functional.

Three host regressions add 64 schedules where a native callback mutates once
then panics, poisoning its owner std Mutex. Pending remains Reserved and blocks
retirement/execution until trusted fenced reconciliation or loss. Racing publish,
query, retire and loss never produces another effect. Separate tests inject
owner Drop panic during retirement and loss: the committed frontier/lost state
survives and remaining owners are released. Workers are joined. These pass with
both core backends; they do not establish kernel unwind or crash recovery.

Loom 0.7.2's internal Mutex poison unwrap prevents verification of this unwind
recovery path. The malformed-receipt model verifies a non-unwinding unknown
outcome instead; host tests cover actual poison. Also excluded are std/alloc
Arc/Weak reference-count atomics/finalization, allocator failure, executions
beyond model bounds, actual IRQ/preemption/SMP adapters, usercopy, scheduler
migration/hotplug, async devices, reboot and Hepta fsync/power-loss cuts.
Earlier hanging-prefix/full-1024-window and 10,000-write tests still pass.

## Kernel and durable-owner handoff

A05/A06 can embed this state in their existing authority owner, snapshot it
after trusted resolution, reserve with `from_management`, then validate the
saved snapshot in the typed callback under the original resource lock before
CAS. A05 still owns actual session/capability/handle generation and trusted
clock acquisition. A06 owns actual CPU accounting, lock adapters and recovery
policy. The primitive itself creates neither credentials nor an executor.
A07 continues K=(scope_id,operation_id) and K↔D in its existing durable owner;
only a durably confirmed continuous terminal prefix may be retired.

The full [API contract](../../libs/os-control/API_CONTRACT.md) documents optional
snapshot semantics and lock order. Main now contains genuine read-only A05
QueryAbi and guest evidence; no mutating A03/management-state consumer or durable
A07 consumer is established by this acceptance. A06's private candidate owner
still needs its own adapter. G1/G2 remain open for those integrations.

Prior PR #94 is merged and its GitHub code/security reviews completed without
findings. Independent read-only review found no blocker in this new primitive.
Current PR #109 CI/reviews are separate live results; queued/running is not pass.
All changes relative to incorporated main are A03-owned; README is 0 bytes,
HOS2 wire/golden are unchanged, and no second Hepta ledger or Ollama is used.
