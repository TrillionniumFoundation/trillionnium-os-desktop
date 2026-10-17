# A03 bounded native window and observation boundary — 2026-10-17 UTC

Branch: `agents/A03-control-core`; [PR #123](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/123).
Latest incorporated main: `e59f8b2fce1287f1ea706dc94880824a9b586ae3`, including
merged A03 #109 and A05 read-only native QueryAbi #87.
Exact tested source: `eb59dfe824778e95d3cab952f235882cfeca06aa`;
tree `d618ff8f411a0bbd351f703e47db5f8156a096ca`.
The follow-up evidence commit changes only this report, its pointer and captured
evidence. All runtime results below are **host model**. Bare-target compilation
does not establish mutating kernel G1 or durable Hepta G2.

## Closed A03 issues

The namespace previously allocated slots, tree nodes and reclamation storage
while internal locks were held. It now preallocates a bounded contiguous
`VecDeque` at bootstrap. New-slot allocation happens after an admission
preflight and outside the table lock; insertion repeats the full admission
check. A racing candidate is destroyed after unlocking. The sequence identity
comes from the monotonic frontier, never from recycled ring indices.

Retirement checks its full terminal prefix before preparing an exactly bounded
reclamation buffer outside the table lock, then checks again before removing
entries. Concurrent retirement can only shrink the required prefix. Duplicate,
invalid and pending acknowledgements allocate nothing. Failed scratch reserve
returns `ResourceExhausted` with no partial advance. History loss closes
admission, walks the now-stable sequence interval and fences each slot without
a snapshot allocation. Final owner destruction remains outside table/loss locks.

The public `DeliveryObservation::hos2_saved_status_code()` previously accepted
Terminal+OutOfOrder/Retired even though canonical publication forbids them.
It now returns `None` for both impossible saved outcomes. Actual retired history
continues to encode normally; numeric HOS2 codes and wire/golden are unchanged.
Against exact historical main, the independent status target has 1 positive
pass and 2 expected assertion failures; current source has 3/3 passes.

## Exact-source validation

Linux x86_64, pinned `nightly-2026-07-21`, rustc
`1.99.0-nightly (87e5904f5 2026-07-20)`. Commands ran in a clean detached
checkout of the tested source using an isolated Cargo target directory.
`source-diff.patch` is empty; all 49 captured code/manifest/fixture input hashes
also match the evidence commit. No Markdown is used as a substitute for tests.

```sh
sh tests/control/run-validation.sh /tmp/a03-window-validation
cargo build --locked --manifest-path libs/os-control/Cargo.toml --no-default-features --features portable-spin --lib --target x86_64-unknown-none
python3 tests/control/reproduce-regressions.py /tmp/a03-window-negatives
python3 tests/control/lock_alloc/run-checks.py /tmp/a03-window-historical --historical-only
```

The validation runner executes std and portable-spin Cargo tests, fmt, both
strict Clippy checks, bare-target check, the pinned Loom harness and the
current lock-allocation harness. The separate bare-target library build passed.

| Rust host tests | std | portable-spin |
| --- | ---: | ---: |
| Existing targets | 192 | 192 |
| New internal ring-capacity test | 1 | 1 |
| status_boundary | 3 | 3 |
| bounded_window | 2 | 2 |
| Total | **198 passed** | **198 passed** |

Zero failed, ignored or filtered; no doctests. These are 396 executions of
198 distinct functions, separate from the following harnesses.
The new native black-box tests execute 30,000 writes per backend: capacities
3 and 17 each stay nonempty while repeatedly retiring only part of the prefix,
and another capacity-17 namespace starts with a hanging head plus 16 terminal
entries. It rejects new admission, permits history/retry, refuses retirement
without advancing the frontier, explicitly resolves the head without effect,
then continues partial retirement through 10,000 writes. Old D never executes
again. A private test additionally checks that ring capacity does not grow.
The prior full-1024-window and long-running tests also pass.

The regression driver requires **13 expected assertion failures**: historical
token 3, native context 2, status boundary 2, synthetic lock-held cleanup 2,
and synthetic origin-blind authority 4. It then requires **65 fixed passes**
across nine targets. Compile errors/timeouts cannot be negative acceptance.
The cleanup control preserves the now-unused scratch buffer's inferred Rust
type so its failure remains the intended runtime assertion. The two synthetic
controls are explicitly mutations, not claims of historical shipped defects.
The driver requires its three pinned historical commits in local Git history.

## Allocator and concurrency evidence

The test-only allocator workspace copies every production Rust module
byte-for-byte, replacing only sync.rs with a std Mutex depth shim. Unsafe
allocator hooks live in a separate test crate; production unsafe_code remains
forbidden. The runner checks source inventory/bytes, fixture/shim equality,
pinned compiler provenance, fmt and strict workspace Clippy. A failed build,
arbitrary panic or incomplete event inventory cannot count as a negative pass.

| Same 18 native namespace scenarios | Locked alloc calls | Locked realloc calls | Locked dealloc calls | Raw fixture exit |
| --- | ---: | ---: | ---: | ---: |
| Exact historical main e59f8b2 | 20,014 | 0 | 1 | 101, expected |
| Exact tested source eb59dfe | 0 | 0 | 0 | 0 |

Scenarios include nonempty saved ancestry, same-D retries, publication, full
windows, pending-prefix retirement, loss and 10,000 writes. Controls detect
alloc/realloc/dealloc, a failed allocation attempt under a lock, nested/thread
local depth and poison/unwind cleanup. Two targeted current-source allocation
failures exercise initial ring reservation and retirement scratch reservation:
`ResourceExhausted`, unchanged frontier and usable history are required.

| Bounded Loom model | Schedules |
| --- | ---: |
| Same D reservation / one effect | 916 |
| Resource revoke / commit | 22 |
| Retire / query | 32 |
| Publish / observe complete result | 92 |
| Loss / callback fence | 64 |
| Typed native same-token execution | 52 |
| Three-way retire / execute / loss | 3,188 |
| Two D, one resource revision CAS | 160 |
| Post-effect malformed receipt / reconcile / retry | 2,442 |
| Management revoke / native commit in original owner lock | 14 |
| Reservation preflight / loss / query | 14,302 |
| Overlapping retire(1) / retire(2) / query | 5,161 |
| Total: 12 models | **26,445** |

All models, fmt and strict harness Clippy passed. Bounds remain main plus
three workers, preemption_bound=3, max_branches=10000, no permutation/time
cutoff. Actual source is copied with only the Mutex shim changed. Source and
inventory hashes are checked before/after. Existing host-thread tests also
exercise reservation, publication, revoke, retirement/loss and poison recovery.
Independent source review found no new ring indexing, frontier, lock-order or
last-owner-drop blocker; independent oracle review checked the allocator hooks
and exact historical control. Reviews remain bounded engineering evidence.

Not covered: Arc/Weak reference-count atomics/finalization ordering; arbitrary
values or schedules beyond model bounds; actual IRQ/preemption/SMP and kernel
allocator behavior; CPU migration/hotplug, usercopy, asynchronous devices,
reboot and Hepta fsync/power-loss cuts. Loom 0.7.2 cannot verify its own poisoned
Mutex unwind path; existing real host-thread poison tests provide that limited
evidence. The allocator harness uses a std lock shim, not portable-spin or an
actual kernel allocator. Only two fallible allocation sites are faulted;
Arc creation and external owner allocation do not gain general OOM recovery.
The host ResourceDomain still has allocating mutation paths. Portable-spin
remains an experimental build backend requiring a real IRQ/lock adapter.

## Consumer contracts and remaining integration

A05 uses `try_with_capacity` / `with_capacity_for_owner`, the trusted
`NativeTarget` / `NativeGrant` constructors, `reserve_native_or_get`, typed
`execute_native_reserved::<ActualOwner, _>`, `query_delivery` and
`retire_through`. It must reject `hos2_saved_status_code() == None` before
serialization. Real session identity, current capability resolution and
usercopy remain A05 responsibilities.

A06 keeps its actual owner and original mutation lock, rechecks management
snapshot/ancestors/lease, settles runtime and performs resource CAS inside the
typed callback. `ManagementGrantState::check/revoke` remains available for
embedding in that owner. No shadow ResourceDomain is required. The callback
must obey the documented no-allocation/no-namespace-reentry rule; the ring
change does not supply kernel IRQ or scheduler locks.

A07 preserves K and K↔D in the existing durable owner, then retires only its
confirmed continuous terminal prefix using `HistoryAck` and the original-owner
authority. No new persistent ledger is introduced. The detailed Rust contract
is in [API_CONTRACT](../../libs/os-control/API_CONTRACT.md).

Only A03-owned paths change; README is 0 bytes, no wire/golden change and no
Ollama use. Main's real read-only QueryAbi remains distinct from these native
mutation host fixtures. No actual A03 mutating kernel or durable Hepta consumer
is established here. G1/G2 remain with those integrations. GitHub CI/reviews
are live external results; the source G0 run 39004727578 was queued when
captured and is not included in the local passing counts.

Logs, exact input hashes, negative checks and normalization metadata are in
`evidence/2026-10-17-window/`. Saved text strips EOF whitespace only; raw log
hashes/sizes are retained when changed. The negative/harness execution JSON
hashes refer to raw subprocess bytes; logs-sha256 covers the captured files.
