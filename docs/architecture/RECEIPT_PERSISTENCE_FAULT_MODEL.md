# Receipt persistence barriers and host fault model

## Status and authority boundary

Plan: `2026-08-29-d6`. This is a **source candidate** strengthening the existing
D0C-06/D3 managed receipt store. It does not promote integrated-main, an installed
image, Servo, production AgentPort, external effects, physical hardware, signing
or release. The active machine gate state is unchanged.

The implementation remains the one in `receipt_journal.rs`, `chain.rs` and
`managed.rs`; the test harness compiles these exact files, not a rewritten or
simplified copy. There is no additional Cargo feature, production environment
variable, public fault-control API, worker, network listener or installable
fault-injection binary.

## Reopening is a durability transaction

A complete canonical segment name seen after a process restart is not proof
that the preceding writer completed directory synchronization. A process can
exit after `rename` and before the directory sync. Similarly, a complete record
may have reached the host page cache before an error or crash, without its writer
returning a successful commit. Validation of bytes alone is not a durability
barrier and must not allow subsequent acknowledged operations to depend on an
unconfirmed namespace publication.

For an existing managed head with no pending rotation, `open_managed` now:

1. Acquires the existing directory and complete-chain locks, validates the
   marker, inventory, segment links, identities, lifecycle bindings and bounds.
2. Performs only the explicitly permitted active record-tail repair, if any;
   all full-record corruption and predecessor damage remain hard failures.
3. Calls `ManagedDirectory::stabilize_open`: verifies the current inventory
   and pinned active/predecessor state, syncs the active file with `sync_all`,
   then syncs the pinned directory descriptor with `sync_all`.
4. Revalidates the inventory and active/predecessor identities and lengths.
5. Returns the writer only after every checked step succeeds.

An error at either sync or revalidation returns no writer. Drop is not used as
an error-reporting substitute for synchronization. A complete unacknowledged
record is preserved and imported as an observed fact, not classified as absent
because the prior caller received an error. Recovery still does not execute,
retry or replay the operation. An unresolved dispatched potential external
operation retains `NeverAutomatic`.

The pending branch retains the separately checked publication protocol: strict
full-chain validation, empty linked pending header, file sync, same-directory
rename, directory sync and post-publication identity/inventory validation.
Initialization, segment and record v1 encodings, directory layout, capacity
bounds, privacy classes and default activation profiles are unchanged.

## Test-only fault mechanics

`crates/hepta-session-core/src/receipt_journal/persistence_tests.rs` owns a
one-shot thread-local injector. The module and **every call site** are guarded
by `#[cfg(test)]`. Without an armed injector, the test build uses the normal
implementation and real `File` operations. Non-test library and product builds
omit the module and all cutpoint statements entirely.

A selected cutpoint either returns a mapped injected OS error (`EIO`, errno 5,
or `ENOSPC`, errno 28) or pauses an isolated child after writing its exact
checkpoint outside the tested store. For partial-write cases the injector
actually writes a bounded prefix of a header or record before failing/pausing;
it does not synthesize a successful full write. Complete writes and syncs are
still the normal implementation calls.

Error injection models a before/after operation failure at userspace boundaries.
It does not force the kernel, filesystem or device to produce an actual EIO or
ENOSPC. A fault after a successful syscall deliberately models an uncertain
caller outcome; tests must not assume a failed call means no bytes changed.

The independent `harness = false` test target is
`crates/hepta-session-core/tests/journal_persistence_process.rs`. It executes a
mandatory finite matrix of 64 fresh child processes. Each child reaches the
requested checkpoint before the parent sends SIGKILL; the parent verifies
signal 9, reaps the child, then opens and checks the real files. A 10-second
checkpoint deadline and a child guard bound failure cleanup. Labels in the
output contain only scenario and cutpoint identities, not receipt payloads.

The harness compiles the journal source under Cargo's test configuration. It
has its own `main`, so embedded libtest tests are not duplicated into its
reported results. Isolation also prevents unrelated parallel unit tests from
briefly inheriting each other's live locked descriptors during fork/exec. The
main test matrix remains parallel; existing immediate lock-release assertions
are unchanged. This is test isolation, not a relaxation of writer custody.

## Fixed coverage and expected results

| Operation | Cutpoints | Expected invariants |
| --- | ---: | --- |
| Initialization | 28 | Partial marker/header preserved and rejected; complete empty pending may be explicitly published; no reset or implicit recreation |
| Rotation | 17 | Old complete chain preserved; incomplete pending rejected; complete prepared header published only under recovery policy; canonical successor selected after rename |
| Reopen barrier | 4 | Sync error returns no writer; complete unresolved external facts and prior receipt identities preserved |
| Pending completion | 6 | Publication is repeatable after each cut; no lost predecessor, duplicate sequence or partial-chain writer |
| Append | 5 | Failed writer is poisoned; partial record repaired only by explicit policy; complete unacknowledged admission retained |
| Active tail repair | 4 | Only the validated prefix survives; repeated recovery is idempotent; prior IDs cannot be admitted again |

The same 64 scenario/cutpoint combinations run with both injected errno values:
128 injected-error combinations. The process target executes 64 SIGKILL cases.
They are matrix cases, not 192 new Rust test functions. The library contains ten
new test functions covering the six error matrices plus barrier ordering,
pre-mutation rejection, baseline regression and injector isolation. Repeated
runs and default/all-feature builds do not increase unique coverage counts.

A cutpoint must actually be reached. Unrelated validation failure is not a pass:
error tests compare the expected public error mapping, and process tests require
the exact checkpoint and signal. Expected old/blocked/prepared/published states
are declared independently of the resulting directory contents. Tests inspect
all directory entry bytes after refusal, retain prior segment bytes, verify
continuing sequence numbers, reject reused receipt IDs and check no fabricated
outcome or response digest appears during recovery.

## Commands and CI wiring

Use the locked Rust 1.93.0 inputs. Offline operation additionally requires the
previously verified Cargo dependency cache.

```sh
cargo test --locked -p hepta-session-core --lib receipt_journal::persistence_tests:: -- --nocapture
cargo test --locked -p hepta-session-core --test journal_persistence_process
cargo test --locked --workspace --all-targets
cargo test --locked --workspace --all-targets --all-features
python3 tools/verify_receipt_journal.py
python3 -m unittest tests.test_receipt_persistence_cuts tests.test_managed_receipt_store tests.test_receipt_journal_workflow
```

Use `--lib` when applying a libtest name filter to this package. The independent
process target has a custom command-line parser; it does not silently skip
coverage in response to a libtest filter. Its `--list` output is enumeration
only, not an execution result. Normal invocation always executes all 64 cases.

The permanent receipt workflow explicitly runs both focused targets and the
complete workspace suite. Cargo test registration, the exact shared source
path, required cutpoint inventories, per-statement `cfg(test)` guards, checked
barrier ordering and error propagation are source-audited. Mutation tests cover
removed guards, ignored sync errors, missing revalidation, changed source paths,
ignored tests, disabled harness registration and inappropriate hardware/replay
claims. These are source-quality checks, not a formal proof or independent lab
attestation.

## Known limits and change discipline

Process termination leaves the kernel and filesystem mounted. The cases observe
page-cache state and do not simulate power removal, device volatile-cache loss,
sector tearing, filesystem journal replay, faults inside a kernel syscall or
every possible scheduler interleaving. Higher-tier qualification must still
use the actual target filesystem, image, controller/cache policy and fixed BOM,
with independent raw failure evidence. A successful process matrix cannot mark
D8 or D9 complete.

The original private-directory and cooperative-writer assumptions remain. Hash
consistency and advisory locks do not authenticate history against a malicious
same-UID/root writer or coherent offline rollback. This change does not migrate
legacy journals, reset partially initialized stores, prune archived history,
raise capacity bounds or introduce an external monotonic authority.

For a failure, preserve the complete store and bounded error metadata. Do not
remove `next.pending`, edit a marker, trim a full record or recreate an empty
namespace to make a gate pass. Changes to persistence ordering, cutpoints, tests
or helper paths must update this document, `receipt-journal.v1.json`, the audit,
module/component registries, workflow triggers and gate invalidation inputs.
Historical evidence remains bound to its original source identity.

## Reference semantics

Rust's `std::fs::File` documentation distinguishes explicit synchronization
from `Drop`, which ignores close-time errors. The managed protocol relies on
successful file and directory synchronization on its supported local filesystem;
that assumption requires target-system qualification, not just a Rust type check.
Reference: `https://doc.rust-lang.org/std/fs/struct.File.html#method.sync_all`.
