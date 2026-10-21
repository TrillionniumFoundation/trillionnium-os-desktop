# SQLite WAL across an abrupt guest restart

This workload advances the persistent-storage part of native Hepta bring-up.
It uses the real SQLite C library, the ordinary Asterinas kernel, a fresh ext2
disk and two separate emulator processes. It does not create an operation
owner, substitute a ledger for Hepta, or claim a native Agentd run.

## What runs

`sqlite_restart_probe.c` selects WAL, explicitly requires `synchronous=FULL`,
disables automatic checkpointing and reduces the SQLite page cache. It commits
32 records, starts another transaction with 16 records, and calls
`sqlite3_db_cacheflush` without committing that second transaction. A fresh
256-bit nonce is stored in the same database and included in the boundary
marker. Directory fsync covers the new database/WAL names; the workload never
manually fsyncs the database file to hide an SQLite VFS failure.

The runner kills its direct QEMU child with SIGKILL only after the complete
boundary marker. It waits for that process to exit, then boots a new guest on
the same disk. The second guest must observe exactly the committed records,
none of the pending records, the original nonce and `integrity_check=ok`.
The normal boot must also finish with QEMU debug-exit status 33.

A second fresh disk runs the same probe with the first COMMIT deliberately
omitted. The unchanged positive verifier must reject it with exit 20. A boot
failure, timeout, arbitrary nonzero status or missing record is not an accepted
negative control. Linux process-crash qualification also checks that a wrong
nonce fails.

## Run

Use a source-built ordinary product ELF and retain its original build receipt.
The caller supplies the expected ELF SHA-256; this is an integrity binding,
not independent proof that the kernel was built from a claimed source tree.
The runner copies that exact input into a new output directory. The base
initramfs is the existing pinned A01 image.

```sh
python3 -I -B tests/workloads/linux/run_sqlite_restart_guest.py \
  --kernel /absolute/path/to/product-kernel.elf \
  --expected-kernel-sha256 <64-lowercase-hex> \
  --initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --output /absolute/path/to/new-sqlite-restart-evidence
```

Host dependencies are a C compiler, static SQLite/glibc development libraries,
`mkfs.ext2`, QEMU x86_64 and SeaBIOS. The runner uses no sudo, loop device, host
mount or host block device. It formats only newly created 64 MiB regular files
under the task output, boots one TCG vCPU with no network, and only terminates
the emulator process it created. It neither restarts nor inspects a live Hepta
owner.

`result.json` records the probe/runner/ELF/BIOS/initramfs identities, tool
version, exact commands, crash result and both verifier outcomes. The raw
serial logs and both disk images remain beside the result. A failed first
case stops the run and preserves its evidence.

## Evidence boundaries and next dependency

SIGKILL of QEMU discards guest CPU and guest page-cache state. It **does not**
discard the host page cache or a physical device's volatile write cache. A
passing result establishes this bounded guest restart scenario, not physical
power-loss durability, ordered FLUSH/FUA under device faults, arbitrary ext2
crash consistency, original Hepta K↔D recovery, or successful retirement.

After this workload passes on the relevant kernel, native Hepta must use its
original SQLite configuration and original recovered writer on the same
filesystem. It must persist the original request and K↔D before dispatch,
persist the correlated terminal result before retirement, and retain unknown
when device history cannot establish an outcome. Device-cache loss and
interrupted block-write tests remain separate requirements. No current-value
comparison can replace the retained operation's result.
