# A03 public native namespace lock backend — 2026-10-17 UTC

Branch: `agents/A03-control-core`; [PR #146](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/146).
Exact tested source: `a2ef27a77fecf6ace2f822fb217a65f9454ba69d`.
Latest incorporated main: `1247d30b2a8d82598482512f4d614b622499e541`.
Tested complete tree: `f3fbe9f2be1449deb04d4521ee169449e3a8a027`.
This later acceptance commit changes only this report, its index pointer and
captured evidence. All 51 code/manifest/fixture input hashes match the source
commit. Runtime results are **host model**; bare-target compilation is not a
kernel execution or G1/G2 acceptance.

## Closed source integration gap

A native consumer previously had to replace private `sync.rs` to select its
actual namespace locks. `LockBackend`, `ControlMutex` and `ControlCoreWith<B>`
now expose that choice without copying the state machine. The old namespace
and handle names remain concrete default-backend aliases. Generic tokens,
views, original-owner authority and weak back-references carry the same B;
instance checks and all prior admission/effect/history rules remain in place.
The backend need not implement Clone. Its borrowing GAT guard need not be
Send/Sync, so an actual kernel wrapper can retain CPU-local guardian state.

Four roles identify namespace table, slot state, slot execution and history
loss locks. All namespace constructors/acquisitions use the injected backend.
Roles do not prescribe IRQ masking or preemption policy: execution/loss gates
can be long-held. The backend must provide exclusive access and release/acquire
visibility; actual IRQ, liveness, allocator and owner lock-order validation
remain kernel responsibilities. Host ResourceDomain locks remain default;
generic `commit` still uses B for namespace state around that host simulation.

Six external host tests assert per-role creation/acquisition, no guard during
lock construction, only an execution gate during callbacks, and no internal
guard during capture/resource destruction. They also cover eight simultaneous
same-D workers, loss/query during a paused callback, successful and unused
retry captures, unwind fencing, and retirement/loss destructor reentry.
Terminal publication retry explicitly preserves the original success.

The independent `backend_no_std` crate imports only public APIs and type-checks
native reserve, typed execution, sole-owner resource CAS, query and retirement.
It builds for `x86_64-unknown-none` with an explicitly !Send guard, non-Clone
backend and Send+Sync ownership handles. It uses a synthetic spin wrapper and
does not supply a real kernel adapter, boot image or runtime test.

## Reproduction and results

The matrix ran in a clean detached checkout, with an isolated Cargo target
directory, pinned `nightly-2026-07-21` and rustc
`1.99.0-nightly (87e5904f5 2026-07-20)` on Linux x86_64.
The captured source diff is empty.

```sh
sh tests/control/run-validation.sh /tmp/a03-backend-matrix
python3 tests/control/reproduce-regressions.py /tmp/a03-backend-negatives
python3 tests/control/lock_alloc/run-checks.py /tmp/a03-backend-callback --callback-only
python3 tests/control/lock_alloc/run-checks.py /tmp/a03-backend-table --historical-only
```

The matrix includes Cargo tests, fmt, strict Clippy for both host configurations,
the portable no_std check and rlib build, external no_std fixture build/fmt/
strict target Clippy, all Loom variants and the current allocation probe.

| Validation | Result |
| --- | --- |
| Default std host suite | **220 passed**, 0 failed/ignored |
| Portable-spin host suite | **220 passed**, 0 failed/ignored |
| New public-backend test target | 6/6 in each host configuration |
| Source and external fixture fmt / strict Clippy | Passed |
| Portable and external custom-backend bare-target builds | Passed |
| Regression controls | 19 checks, 19 designated assertion failures, 85 fixed passes |

These are 440 executions of 220 distinct host test functions, not 440 unique
scenarios. Existing 10,000-write histories, full-1024-window hanging prefixes,
partial retirement, wrong publishers, terminal refusal, copyout retry,
parent/revision/usage preservation and boot/CapSpace isolation remain covered.

The new synthetic role control changes only the production slot-state lock
tag to NamespaceTable. It still compiles, then the designated routing test
fails with raw exit 101 (0 passed, 1 failed, 5 filtered). It is explicitly a
mutation control, not a historical defect. Four pinned historical and other
synthetic controls retain their original identities. Neither timeout nor a
compile failure can satisfy the runtime negative oracle.

## Allocation and bounded concurrency

Current allocator validation now instantiates the public TrackingBackend.
Every production Rust module, including sync.rs, is copied byte-for-byte with
no source substitution. The unsafe global allocator hooks stay in a separate
test crate; production unsafe code remains forbidden. All 19 native scenarios
record zero locked alloc/realloc/free, with positive instrumentation controls,
thread-local depth/unwind checks and two targeted allocation failures that
preserve the history/frontier. Historical probes alone substitute sync.rs:

| Probe | Locked alloc | Locked realloc | Locked free | Raw exit |
| --- | ---: | ---: | ---: | ---: |
| e59 table/storage historical control | 20,016 | 0 | 3 | 101, expected |
| d172 callback-capture historical control | 0 | 0 | 2 | 101, expected |
| Exact current source through public backend | 0 | 0 | 0 | 0 |

| Loom fixture group | Schedules |
| --- | ---: |
| Existing 13 default/host transition models | 26,675 |
| Public backend: same-D reservation/effect | 252 |
| Public backend: same-token effect once | 52 |
| Public backend: revoke/commit | 16 |
| Public backend: retire/query | 47 |
| Public backend: publish/observe | 147 |
| Public backend: loss/execution fencing | 64 |
| **19 models total** | **27,253** |

The original models retain the test sync shim. The six public-backend models
select Loom mutexes through the exported trait while all production modules
remain byte-identical, including sync.rs. All named fixtures, fmt and strict
harness Clippy passed; before/after hashes and inventories match. Bounds are
main plus at most three workers, preemption_bound=3, max_branches=10000, with
no permutation/time cutoff. Branch overflow, deadlock or assertion fails.

Uncovered: arbitrary values/schedules beyond these bounds; std/alloc Arc/Weak
ownership atomics/finalization; general OOM and arbitrary backend allocation;
real kernel IRQ/preemption/SMP guardian behavior and lock latency/order;
scheduler migration/hotplug/runtime settlement; actual usercopy faults,
credentials, devices and Hepta fsync/power-loss/reboot cuts. Loom 0.7.2 cannot
verify poisoned mutex unwind recovery; the limited panic paths use real host
threads. No A03 actual kernel runtime test is claimed.

## Consumer contract and remaining owner work

| Owner | Reusable Rust API | Actual integration still required |
| --- | --- | --- |
| A05 ioctl / CapSpace | `ControlCoreWith<B>`, `with_capacity_for_owner`, `NativeTarget`, `NativeGrant`, `reserve_native_or_get`, typed `execute_native_reserved`, `DeliveryViewWith<B>`, query/retire | Kernel backend, trusted boot/CapSpace/process/exec authority, actual handle resolution and copyin/copyout |
| A06 scheduler / sole resource owner | `ControlMutex` / four `LockRole`s, pinned `NativeExecution<ActualOwner>`, `ManagementGrantState`, `NativeResourceState::{apply,apply_owner_configuration,invalidate}` | Existing owner mutation lock, current membership/epoch/lease checks, settled runtime, parent policy and real scheduling enforcement |
| A07 existing Hepta owner | K value/binding types, `HistoryAck`, `OriginalOwnerAuthorityWith<B>`, `retire_through` | Durable K↔D confirmation and authenticated contiguous retirement in the existing ledger |

The detailed contract is [API_CONTRACT.md](../../libs/os-control/API_CONTRACT.md).
No wire/golden changes, second K database or other-agent source edits are made;
root README remains zero bytes. A00 coordinates merging. GitHub source-head
Actions were still queued and reviews absent when the retained snapshot was
read; local project-cloud success is not reported as a remote CI/review pass.
G1/G2 remain unclosed until the respective owners execute their actual paths.

Evidence: [evidence/2026-10-17-backend/](evidence/2026-10-17-backend/), including
per-command logs, input/immutable-object hashes, regression assertions, model
schedule counts, allocator counters and the GitHub snapshot. Capture metadata
retains raw hashes/sizes and normalized-file hashes; normalization removes
trailing whitespace/blank EOF lines only. No source snapshots or binaries are
included in captured evidence.
