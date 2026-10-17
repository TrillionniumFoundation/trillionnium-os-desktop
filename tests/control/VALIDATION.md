# A03 control core acceptance — 2026-10-16

Branch: `agents/A03-control-core`. PR: [#50](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/50).
Latest main used: `bc294f75bfb8c03d9963f5a12ea23b9589779d96`.
Tested code commit: `bb42cb691e6de33b8f788c94ea715bf648ff56ed`.
The later evidence commit changes only this report and its logs; source hashes
are in `evidence/2026-10-16/source-sha256.json`.

## Result and boundary

The A03 source-validation, family BOOTTIME and external synchronous handoff
blockers found in this pass are closed at the tested code commit. This is
**host-model runtime evidence plus a no_std library build**. There are **zero
real A03 kernel integration tests** in this acceptance. G1/G2 are not closed.

All changes relative to main are under `libs/os-control/**` and
`tests/control/**`. HOS2 wire/golden files are unchanged. README is 0 bytes.
No second persistent Hepta K database is created; no Ollama is used.

## Changes with reproducible negative evidence

1. **One clock per resource family.** Before the fix, a descendant could
   sample/update at T and an ancestor/sibling could later accept an operation
   timestamped before T. Success now advances a shared family BOOTTIME floor;
   stale reads, CAS and charges fail without partial mutation. Failed CAS,
   exhausted charges and inconsistent-accounting reads do not move the floor.
   Diagnostic `usage` clamps to it; new cousins inherit it. Running the new
   12 resource tests against pre-fix `188ee14281d1e3c312ecaddfe56994e63e10b587`
   produced **4 passed / 8 expected failures**; after the fix, **12/12 passed**.
2. **One-shot external mutation seam.** `execute_reserved` runs the trusted
   adapter under the result-slot lock. Namespace loss fences before callback
   admission or waits for complete publication. Callback panic or malformed
   receipt leaves a pending prefix and blocks re-execution/retirement. Trusted
   externally fenced reconciliation may subsequently `publish` the outcome.
   `commit` uses this same seam for the host ResourceDomain CAS.
3. **Portable state code.** Default std and optional `portable-spin` backends
   use the same core/alloc state machine. The portable backend builds an
   `x86_64-unknown-none` rlib. Its lock backend is not IRQ/preemption safe by
   itself; actual Asterinas locking and allocation paths still need adaptation.
4. **Adversarial long-running history.** A 1024-entry full window retains
   sequence 1 pending while later entries are terminal. Repeated full-window
   writes and retirement fail explicitly without moving the prefix. After a
   trustworthy no-effect refusal resolves the prefix, the same namespace
   continues to 10,000 writes. Retired sequences never execute again.

## Actual commands and counts

Environment: project cloud workspace, Linux x86_64,
`rustc 1.99.0-nightly (87e5904f5 2026-07-20)` through pinned
`nightly-2026-07-21`. The matrix ran from a **clean detached checkout** of
the tested code SHA. `source-diff.patch` is empty.

```sh
sh tests/control/run-validation.sh /tmp/a03-validation
```

The script performs these exact checks; use the pinned toolchain on PATH:

```sh
cargo fmt --manifest-path libs/os-control/Cargo.toml --all -- --check
cargo test --locked --manifest-path libs/os-control/Cargo.toml
cargo clippy --locked --manifest-path libs/os-control/Cargo.toml --all-targets -- -D warnings
cargo test --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin
cargo clippy --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --all-targets -- -D warnings
cargo check --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
```

| Rust test target | std | portable-spin on host |
| --- | ---: | ---: |
| Library unit tests | 6 | 6 |
| control_conformance | 81 | 81 |
| delivery_adversarial | 6 | 6 |
| resource_adversarial | 12 | 12 |
| kernel_handoff (synthetic callback) | 8 | 8 |
| Total | **113 passed** | **113 passed** |

Both runs: 0 failed, 0 ignored, 0 filtered; no doctests. The 226 executions
are the same 113 test functions against two lock backends, not 226 distinct
scenarios. Formatting and both strict Clippy runs passed. Additional actual
checks:

```sh
cargo build --offline --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
sh tests/kernel/control/run-host-smoke.sh
```

The no_std rlib build passed. The existing A05 smoke passed QueryAbi framing,
16 invalid frames, and Linux `/dev/null` ENOTTY versus injected EFAULT checks.
It does not exercise an Asterinas control ioctl. Logs and SHA256 manifests
are in `evidence/2026-10-16/`; captured logs only remove trailing blank lines.

The pre-fix negative oracle is reproducible without altering the checkout:

```sh
mkdir -p /tmp/a03-before
git show 188ee14281d1e3c312ecaddfe56994e63e10b587:libs/os-control/src/lib.rs > /tmp/a03-before/lib.rs
rustc --edition 2021 --crate-name os_control --crate-type rlib /tmp/a03-before/lib.rs -o /tmp/a03-before/libos_control.rlib
rustc --edition 2021 --test tests/control/resource_adversarial.rs --extern os_control=/tmp/a03-before/libos_control.rlib -o /tmp/a03-before/resource-tests
/tmp/a03-before/resource-tests
# Expected: exit 101, 4 passed / 8 failed.
```

## Concurrency evidence and uncovered interleavings

Both backends execute the real Rust state transitions on host threads.
Existing tests cover simultaneous same-D reservations, revoke/commit races,
ancestor epoch fencing, shared parent spending, publication/observation
visibility, copyout-model retries, retirement/query and namespace loss.
New tests add 128 commit/refusal races; 32 rounds with 8 wrong publishers;
128 retry/commit/loss races; 64 retire/query/loss rounds with 128 reads each;
64 descendant/ancestor clock races; and 64 rounds of 8 concurrent one-shot
callbacks. Panic and seven malformed callback receipts remain pending and
cannot create a second callback effect. Public observations never expose
partial terminal metadata or turn lost/retired entries into new effects.

This is adversarial scheduling, **not loom or exhaustive model checking**.
Unexplored arbitrary thread schedules and weak-memory architectures remain.
Actual IRQ/preemption/runqueue lock orders, SMP CPU migration/hotplug,
real copyout faults, asynchronous device effects, process death, reboot and
power-loss/fsync cuts are untested here. An interrupted callback does not
prove zero external effect; it deliberately retains an unresolved prefix.

## Handoffs to A05/A06/A07

| Owner | Rust seam | Required actual integration |
| --- | --- | --- |
| A05 CapSpace/ioctl | `try_with_capacity`, `with_capacity_for_owner`, `DeliveryRequest::from_wire`, `reserve_or_get`, `execute_reserved`, `query_delivery`, `retire_through` | Real process-start/exec epoch, grants/lease checks, generation, boot entropy, history rights, copyin/copyout and executor fencing |
| A06 ResourceDomain/scheduler | `RequestBinding`, `PublishOutcome`, `BudgetReceipt`, `ResourceDomain::{grant,revoke,try_usage,install_budget_for_host_model,charge_interval_for_host_model}` | One real ResourceDomain owner; settle runtime and revoke/CAS under the same real mutation lock; adapt synchronization/allocation and enforce CPU caps |
| A07 existing durable owner | `LogicalOperationId::new(scope_id,operation_id)`, `OperationBinding`, `HistoryAck`, `OriginalOwnerAuthority` | Persist K↔D and semantic digest in the existing owner, authenticate replacement/fencing, fsync confirmation, preserve unknown K and acknowledge only a confirmed contiguous terminal prefix |

The full API and lock invariants are in
[`libs/os-control/API_CONTRACT.md`](../../libs/os-control/API_CONTRACT.md).
No actual consumer imports `os-control` in the current kernel or Hepta owner.
Those cross-owner G1/G2 implementation blockers remain open for their owners;
the std/no_std host results must not be presented as native kernel acceptance.
