# G1-d aggregate user-data frame boundary

The fixed trusted workload receives one immutable account of **16,384 physical
user-data pages (64 MiB at 4 KiB/page)** before its stopped initial image is
loaded. Its descendants retain that same account across fork, threads and exec.
The manager and recovery roles do not consume this workload allowance.

This boundary is separate from the existing 256 MiB per-process virtual-address
limit. It does not implement `memory.max`, a full Linux memory controller,
reclaim, an OOM killer or guaranteed recovery reserves. Kernel slab allocations,
page tables, socket buffers, filesystem metadata, kernel stacks and device MMIO
remain outside this account. A malicious workload can still exhaust resources
outside the implemented boundary. General cgroup migration/reparenting and SMP
stress are not qualified by this test.

## Ownership and failure behavior

| Path | Admission and lifetime |
| --- | --- |
| Private anonymous faults | Reserve one page before the physical allocator; retain the token in frame metadata. |
| Anonymous or file COW | Reserve a new physical page; existing shared references retain their original single charge. |
| Anonymous and backed VMO pages | Charge the actual new-page initiator, including buffered file I/O; an already cached shared page is not charged again. |
| Stopped trusted ELF/boot/stack loading | Use the destination VMAR's explicit owner even when no userspace process is current. |
| Contiguous VMO allocation | Reserve the entire page count before the physical segment allocation. |
| DRM GEM shmem allocation | Reserve the entire page count before allocating the handle vector or user-visible frames. |
| Fork/exec | Preserve the account identity; exec admits its new pages while the old image still exists. A failed load refunds new physical frames as they are released. |
| Physical release | Refund only at the final physical-frame reference. VMO/file cache ownership can outlive a process. Unmapping one shared alias is not a refund. |

Admission is a checked atomic update. Tokens are linear and are stored in
physical-frame metadata; cloning a frame handle does not clone its charge.
Allocator failures, partial device-vector allocation and unused contiguous
reservations refund their tokens. No logging, sleeping or process/cgroup lock
occurs inside reservation/refund operations.

Quota denial retains `ENOMEM` with private kernel provenance while VM locks
unwind. Existing fault behavior is preserved: a fallible kernel copy to a user
buffer can report `EFAULT`; an ordinary unresolved userspace fault uses the
existing signal path. This patch does not call that behavior an OOM kill.
After locks are released, the fault handler emits at most 16 diagnostic records
per account containing the actual fault PID, address, current page count and
limit. The native oracle requires those exact records rather than treating an
arbitrary `EFAULT`, crash or timeout as proof of a memory boundary.

## Native gate

`g1d_user_memory.c` reuses the existing sealed G1-d bootstrap and HOS2 request,
response, history and readback functions. The original full G1-d scenario is
compiled under an unused entry point. This probe performs only these bounded
operations in a disposable N0 guest:

1. The unprivileged workload starts a fork holder of 18 MiB, a fork/exec holder
   of 18 MiB, and a third allocating child. All mappings are below each
   process's 256 MiB address-space limit. The third child reaches the shared
   64 MiB physical-page allowance before its own 64 MiB mapping is filled.
2. With all allocated pages still alive, the same child exercises a new
   anonymous page, shared-anonymous VMO page, COW page and file-mapped page.
   Their fallible copies return `EFAULT` with four matching kernel quota-cause
   records. A separate new file-cache write returns `ENOMEM`.
3. The manager installs a real CPU cap of zero for the controlled family and
   reads the saved terminal result. The separate recovery process allocates
   and touches 16 pages, uses its own recovery grant to restore the CPU cap,
   and the manager reads the resulting revision and resource state.
4. Only after that effect and readback does the workload release/reap one
   18 MiB holder. The allocating child retries the same five operations at
   their original mappings/offsets; all succeed. The parent's original COW
   byte remains unchanged. The remaining children are reaped and the test file
   is truncated before completion.

The recovery allocation is evidence of progress under this bounded user-data
pressure. It is not a proof that recovery has reserved physical pages or can
survive every kernel-memory exhaustion path. Existing manager/recovery files
coordinate the fixed fixture; they do not confer HOS2 authority.

The runner uses the existing product build wrapper, exact clean Git head/tree,
fixed generated lock (204 packages), pinned SeaBIOS and the actual frozen ELF
manifest. It performs one additional QEMU boot with `loglevel=warn`, retaining
the raw serial, commands, build logs, manifests, input hashes and receipts. It
does not run the unrelated altered-initial-image boots. New or malformed
records, missing observations, wrong PID/address/limit bindings, nonterminal
history, wrong revision order, a panic, timeout or non-33 QEMU exit all fail.

From the committed isolated checkout, using the existing pinned toolchain and
source-built cargo-osdk:

```sh
python3 -I tests/kernel/control/test_g1d_user_memory_guest.py -v
python3 -I tests/kernel/control/run_g1d_user_memory_guest.py \
  --expected-source-head <actual-40-hex-head> \
  --expected-source-tree <actual-40-hex-tree> \
  --output <fresh-outside-checkout-evidence-directory> \
  --target-dir <fresh-outside-checkout-target-directory> \
  --timeout 240
```

Set `RUSTUP_HOME`, `CARGO_HOME` and `VDSO_LIBRARY_DIR` to the existing pinned
build environment. `VDSO_LIBRARY_DIR` must contain `vdso_x86_64.so`. The build
runner records and validates actual source/build inputs; a host compilation or
host fixture test is never a native guest pass.

## Bounded counterfactual

After a passing positive boot, create a separate clean counterfactual checkout
and apply `controls/user-memory-128m.patch`. It changes only the fixed account
limit to 128 MiB; it does not remove charging, change the probe, alter the
oracle or modify authority rules. With the original 64 MiB acceptance boundary
absent, the two 18 MiB holders and all 64 MiB of the third child's mapping fit.

Run the same runner with the counterfactual checkout's exact committed
head/tree, fresh output/target paths, and `--expect-no-limit`. Acceptance requires
the two real holders, the real fork/exec identity, a complete 64 MiB third
allocation and exactly one manager `memory_aggregate_limit` failure. No quota
fault, unrelated failure, timeout, panic, recovery claim or completion record
is allowed. The unchanged positive oracle must reject the same raw bytes.

The `G1DM_NO_LIMIT` name means no effective 64 MiB family limit in this bounded
probe, not unlimited system memory. A passing counterfactual receipt sets
`counterfactual_only=true` and keeps both product qualification fields false.
Preserve its source diff, compiler/probe hashes and full native evidence beside
the positive receipt. Never merge the 128 MiB counterfactual into the product.

## Kernel tests

Eight real kernel tests cover: reservation rollback/overflow, final shared
frame release, independent owners, contiguous all-or-nothing admission, VMO
alias ownership, COW data plus per-physical-page refund, and stopped initial
stack admission plus failed-image release without a current Process. The
stack VMO fixes its account from the destination VMAR before the writer commits
pages; an empty ambient kernel-task owner cannot bypass that account. The
existing wrapper supports a complete test-name suffix (not a substring):

```sh
python3 -I support/build/ktest/run.py --crate aster-core --skip-osdk-install \
  --test-name exact_limit_and_unconsumed_reservation_refund --output <fresh-directory>
```

The other suffixes are `shared_frame_charges_once_until_last_reference`,
`independent_owners_do_not_consume_each_others_allowance`,
`contiguous_limit_is_admitted_before_any_page`,
`shared_vmo_aliases_keep_one_physical_charge`, and
`cow_charges_the_copy_and_refunds_each_physical_page`. The stack regressions are
`stopped_initial_stack_charges_its_destination_without_a_current_process` and
`rejected_stopped_initial_stack_refunds_its_pages_when_the_image_is_dropped`.
A single full `--crate aster-core` invocation also covers them without separate
links. Report the actual guest counts and any filtering from its saved receipts.

The archived 281-test run predates these two stack regressions. Their source
addition is not a native pass; rerun the kernel suite and pressure/recovery gate
against the integrated source before extending the qualification record.

## Qualification status

Adding this code and these tests does not assert a native result. The source
commit, tested tree, raw guest result and evidence descendant must be recorded
after execution. These receipts never set `memory_max`, `global_physical_reserve`,
`oom_killer`, `smp_qualification`, `hardware_qualification`, `hepta_durability`
or `production_ready` to true.

The stopped-stack tests keep a strict zero-after-final-release assertion.
`drop(VmarHandle)` first destroys the mapping/VMO, whose XArray detaches nodes
through RCU; those nodes can still hold real charged frames. The tests verify
that the final VMAR weak reference no longer upgrades, queue an original
`RcuDrop` completion witness after the detach callbacks, and pass bounded real
scheduler quiescent states before checking zero. A genuine Core helper thread
with no VMAR/account ensures compatibility with both OSTD FIFO and the Core
class scheduler. The witness never mutates the
account. Production frame lifetime/refund logic is unchanged. The initial
7d8906ef core run exposed the two premature zero assertions (284/286); the
corrected assertions require a fresh native run and do not turn that run into
a pass.
