# A03 native-owner seam and retirement acceptance — 2026-10-17 UTC

Branch: `agents/A03-control-core`; [PR #94](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/94).
Latest incorporated main: `b75f8e4ca6f55495a10d1652107c26010cdede7d`.
Exact tested source commit: `43ba5e51644d36a467ad0845eee6058da1436652`.
The subsequent evidence commit adds only this report, the latest-report pointer
and captured logs/manifests. Runtime results are **Linux host-model evidence**;
the alloc-only rlib build is compilation evidence. Neither closes G1/G2.

## Implemented blockers

1. **Stale tokens retained retired storage.** The bounded window now owns each
   full canonical request and owner pin. Tokens cache immutable metadata and
   hold a weak namespace reference, with no strong or weak result-slot handle.
   Exact namespace instance/generation, non-reusing sequence and binding are
   rechecked before execution. Retirement/loss releases namespace-held result
   slots and owner pins even when 10,000 old tokens remain in caller memory.
   Concurrent transient pins and external owner Arcs retain their own lifetime.
   A private unit
   directly checks slot/namespace destruction; five public regressions cover
   one-slot 10,000-write operation, resource release, pending retention and
   last-namespace destruction. Caller token collections still require their
   own quota; this is no claim of bounded arbitrary caller allocations.
2. **External execution required a shadow host resource.** `NativeTarget`,
   `NativeGrant` and `NativeDeliveryRequest` now bind an existing owner Arc,
   stable IDs, publisher, epoch/ancestor snapshot and complete HOS2 request.
   `reserve_native` / `reserve_native_or_get` use the same global sequence,
   bounded window and result history as host requests. Equal IDs on different
   owner allocations conflict; host/native kinds also conflict under one D.
   Native success tests use only the synthetic original owner's mutable state,
   never a parallel host ResourceDomain. Host `commit` rejects native tokens;
   `execute_reserved` invokes the trusted real-owner callback once.
3. **Owner destruction under internal locks.** Retirement publishes the new
   frontier before releasing the namespace lock and destroying removed pins.
   Loss publishes loss and releases both table/loss gates before destruction.
   Two bounded destructor-reentry tests fail on the earlier lock-held cleanup
   and pass after this change; all helper threads are joined before assertions.

The native constructors validate values but do not authenticate them. A05 must
resolve actual capabilities, retain the real grant context and recheck it in
A06's owner mutation lock. No new budget state, scheduler or durable K ledger
is introduced. HOS2 wire/golden are unchanged; README remains zero bytes.
All PR changes relative to incorporated main are in A03-owned paths.

## Repeatable validation

Fixed toolchain: `nightly-2026-07-21`, rustc
`1.99.0-nightly (87e5904f5 2026-07-20)`. All commands below ran from a clean
detached checkout of the tested commit; `source-diff.patch` is empty.

```sh
sh tests/control/run-validation.sh /tmp/a03-native-validation
cargo build --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
python3 tests/control/reproduce-regressions.py /tmp/a03-negative-validation
```

The runner includes fmt, `cargo test --locked --manifest-path
libs/os-control/Cargo.toml`, both backends' strict `clippy --all-targets --
-D warnings`, and a bare-target check. The second test configuration adds
`--no-default-features --features portable-spin`.

| Rust target | std | portable-spin on host |
| --- | ---: | ---: |
| Library unit tests | 7 | 7 |
| control_conformance | 81 | 81 |
| delivery_adversarial | 6 | 6 |
| kernel_handoff | 8 | 8 |
| resource_adversarial | 12 | 12 |
| resource_lifecycle | 10 | 10 |
| nonblocking_history | 6 | 6 |
| token_retirement | 5 | 5 |
| native_handoff | 15 | 15 |
| Total | **150 passed** | **150 passed** |

Both backends: zero failed/ignored/filtered; no doctests. These are 300
executions of 150 distinct Rust test functions. Formatting, both strict
Clippy runs, no_std check and rlib build passed. Evidence is in
`evidence/2026-10-17-native/`, with exact source/log SHA256 manifests.
Text captures normalize trailing whitespace at EOF/blank lines only;
`capture-normalization.json` preserves pre-normalization byte counts and hashes
for new captures. The negative runner report hashes refer to raw subprocess
stdout; `logs-sha256.json` covers the captured files.

The negative runner compiles historical main `40ca002fac0726b366726d3353916637b29adeae` against the five
new public token tests: **2 passed / 3 expected failures, exit 101**. It also
constructs an explicitly labelled synthetic rollback of only the two cleanup
paths: **0 passed / 2 expected failures, exit 101**. It requires fixed source
to pass the same public targets (**5 + 15**), recording every command, exit
code and source hash. Script success requires both failures and fixes to be
observed; compilation errors are never accepted as a negative result.
The original private-token failure and pre-fix native snapshot logs are also
retained as historical captures, separate from the reproducible runner.

## Concurrency and limits

Both lock backends run real Rust transitions on host threads. New native tests
add 32 rounds of eight simultaneous same-D reservations and eight concurrent
execution attempts, with one callback/effect per D, plus retirement/query and
loss-gate destructor reentry. Previous
same-D, revoke/commit, parent budget, publisher, query/retire/loss,
publication visibility and paused-callback regressions remain in the matrix.
The permanent pending-prefix/full-1024-window test still rejects additional
writes and blocked retirement while allowing history queries, then continues
in the same namespace to 10,000 deliveries. A separate one-slot test retains
10,000 old tokens and proves they never execute another effect.

This is scheduling stress and controlled interleaving verification, not loom
or exhaustive state-space/weak-memory proof. Real IRQ/preemption, allocator
failure, kernel stack, SMP migration/hotplug, real usercopy faults, async
devices, process death/reboot and Hepta fsync/power-loss cuts remain untested.
A callback that panics or returns malformed metadata remains unresolved;
it is not converted into a fictitious refusal or silently executed again.

## Concrete handoffs and actual integration status

| Owner | Provided Rust interface | Actual consumer requirement |
| --- | --- | --- |
| A05 | `NativeTarget::from_owner`, `NativeGrant::from_owner`, `NativeDeliveryRequest::from_wire`, `reserve_native_or_get`, `execute_reserved`, `query_delivery`, `retire_through` | Bind actual boot/CapSpace/session/capability; decode with A02, authenticate publisher and history rights, preserve original handle bytes and implement usercopy/fencing |
| A06 | `RequestBinding`, `PublishOutcome`/`BudgetReceipt`, actual owner Arc pin | Settle real runtime, check current grants/ancestor epochs/lease and CAS/parent policy under the same lock as revoke; adapt IRQ/preemption/allocation to the kernel |
| A07 | `LogicalOperationId(scope_id, operation_id)`, `OperationBinding`, `OwnerReceipt`/`HistoryAck`, `OriginalOwnerAuthority` | Associate K with D in the existing durable owner, fsync confirmed terminal prefixes, then retire; no second database |

The full signatures and lock/order invariants are in
[API_CONTRACT.md](../../libs/os-control/API_CONTRACT.md).
A05 #87 has genuine **read-only QueryAbi guest evidence**, using A02's shared
codec; it does not yet consume this mutation core. A06 #18 has an existing
CPU controller but no `os_control` import or stable-ID/revision/grant bridge.
No A07 durable consumer was found. The native seam removes A03's shadow-owner
prerequisite; those actual integrations still belong to their owners.

The earlier PR #86 G0 [run 38986007642](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38986007642)
actually succeeded, including both A03 host test/lint steps; this supersedes
the old report's queued/blocked CI snapshot. It covers the earlier std suite,
not this native seam, portable-spin or bare-target build. Current-head CI
status is reported separately in PR #94; local evidence is not a CI pass.
