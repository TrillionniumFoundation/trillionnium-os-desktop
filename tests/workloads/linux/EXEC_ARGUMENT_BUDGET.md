# Exec argument and environment budget

The ordinary `execve` and `execveat` paths share a limit for copied argument
and environment strings, including every terminating NUL and one native
pointer slot per string. The limit snapshots the calling process's soft
`RLIMIT_STACK`, in bytes:

```
max(128 KiB, min(6 MiB, RLIMIT_STACK / 4))
```

The default 8 MiB stack therefore admits a 2 MiB combined payload. Each string
still has the existing 32-page maximum. A repeated user pointer consumes the
budget on every copy. Empty strings consume both their NUL byte and pointer
slot, so an enormous list of empty arguments cannot bypass the bound. NULL
argv/envp vectors retain their existing empty-vector behavior.

## Admission and compatibility

`process/execve.rs` creates one `program_loader::ArgBudget` for both vectors.
It reserves each pointer slot before invoking the allocating CString reader,
and caps that reader by the smaller of the per-string limit and the remaining
budget. It then charges the bytes actually copied. A user thread changing
the strings or reusing pointers cannot evade a separate pre-scan, because
there is no pre-scan whose unchecked result is later trusted. Vector growth
uses `try_reserve`; pointer address advancement uses checked arithmetic.

`ProgramToLoad::from_executable` validates owned inputs before loading an
image. Before each shebang splice, it charges the actual replacement list:
the interpreter arguments, script path, original argv tail and environment.
The discarded argv[0] is absent from that new accounting. The concatenated
vector is reserved only after admission. `spawn_init_process` checks kernel
boot arguments before ordinary loading or the trusted profile's three role
copies; fixed kernel boot input cannot enter through an unchecked public
loader boundary.

The stack-derived rule and pointer accounting follow Linux's
[`bprm_stack_limits`](https://github.com/torvalds/linux/blob/master/fs/exec.c).
There are deliberate compatibility boundaries: Linux also copies the
executable filename onto its stack, while the current Asterinas stack writer
does not; Linux synthesizes an empty argv[0] for an empty vector, while this
change preserves Asterinas's existing empty-vector behavior. The tests account
for the actual filename copy when running on Linux. They do not describe the
two kernels as byte-for-byte equivalent for all shebang or empty-argv cases.

This change bounds the input storage admitted by one exec operation. It does
not implement a cgroup resident-memory controller or reserve physical memory
for manager/recovery tasks. CString and downstream page allocation retain
their existing allocator behavior; a system-wide memory shortage still needs
separate accounting, allocation-failure and recovery-reserve work.

## Tests and exact evidence

The regression is
`kernel/asterinas/test/initramfs/src/regression/process/execve/execve_args.c`,
also included by the ordinary process regression script. It invokes the real
syscalls against a tiny valid ELF that terminates with a known SIGILL. An
oversized argument call must return E2BIG to the original image, which then
exits through a distinct checked path. The cases cover:

- argv/envp combined and argv alone at the exact limit and one byte above;
- the same aggregate boundary through execveat;
- the 128 KiB floor, one-quarter scaling, and 6 MiB ceiling;
- more than fourteen thousand empty strings, proving pointer storage counts;
- the single-string maximum including NUL;
- shebang replacement at the exact final limit and one byte above;
- retained NULL-vector acceptance.

The Asterinas build requires all 19 checks in their exact groups and order.
The Linux reference contains 17 checks; the Asterinas-specific shebang
boundary is intentionally not claimed by that reference. The guest oracle
rejects missing or duplicate checks, skipped/failing checks, incomplete
markers, wrong order, panic, timeout, or a wrong QEMU exit code.

Build and boot a clean committed candidate through the existing ordinary
gate, using a fresh output directory and target directory:

```sh
python3 -I -B tests/kernel/control/run_queryabi_candidate_guest.py \
  --expected-source-head "$resource_head" \
  --expected-source-tree "$resource_tree" \
  --target-dir "$resource_root/t-exec-budget-product-20261023" \
  --output "$resource_root/e-exec-budget-product-20261023" \
  --timeout 90 --boot-timeout 300

python3 -I -B tests/workloads/linux/run_exec_arg_budget_guest.py \
  --product-evidence "$resource_root/e-exec-budget-product-20261023" \
  --expected-source-head "$resource_head" \
  --expected-source-tree "$resource_tree" \
  --a01-initramfs "$resource_root/e-exec-budget-product-20261023/product-boot/initramfs.cpio.gz" \
  --output "$resource_root/e-exec-budget-guest-20261023" \
  --timeout 120
```

Here `resource_head` and `resource_tree` must be the reviewed clean checkout's
actual Git identities; `resource_root` is a directory outside that checkout.
Use the pinned kernel toolchain, Cargo cache and vDSO path already qualified
by `support/build/kernel.sh`, with both trusted-profile environment flags set
to zero for this ordinary product build. Do not point the new gate at a
trusted G1d kernel or at a stale product receipt from another head.

For a before-fix comparison, the new guest runner accepts a separately
reviewed `--product-source-head` and `--product-source-tree` together with
that old ordinary product receipt. It still pins the regression source to
the current reviewed head, records both identities, and keeps the same
strict positive oracle. A baseline rejection remains `passed: false`; it is
not automatically reclassified as success merely because something failed.

The runner saves the original serial log, compiler command/output, original
product-receipt hash, guest input hashes, QEMU command/identity and before/after
source snapshots. Retain its result alongside the existing product gate.
An evidence-only descendant must identify the actual tested source commit.

Host-only oracle checks:

```sh
python3 -I -B -m unittest discover -s tests/workloads/linux \
  -p test_exec_arg_budget_guest.py -v
```

The Linux reference is useful for checking the boundary calculation, but its
success does not qualify the patched Asterinas kernel. Native status is only
established by the actual guest receipt produced above.
