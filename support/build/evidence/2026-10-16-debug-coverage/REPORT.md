# A01 full-kernel debugging and explicit TCP coverage

This phase keeps the complete vendored Asterinas v0.19.0 kernel at
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, and Rust
`nightly-2026-07-21`. No process, ioctl, scheduler or OSTD source was changed.
The root README remains zero bytes. `report.json` contains the exact code
commits, test counts and evidence references.

## Actual results

- Production OSDK host units: **35/35 passed**. The preceding 34/35 attempt
  remains recorded; its bounded TCP lease cleanup test was corrected before
  the full successful retry.
- Explicit `osdk-native-local-tcp-gdb-capture-v2`: **22/22 cases passed** at
  `fa9b6cd6be310155b10fa36aafcb8896444e0f6e`. Eleven real QEMU guests returned
  raw 33. One case explicitly soft-skipped unavailable VMX; it is not VMX
  acceptance.
- The later fatal-panic coverage guard at
  `1cc76b90dfd162e18a946a01e0bcaa31b8e03b4f` passed 16 focused host checks
  and a new exact coverage guest. The full 22-case run predates this guard.
- Real coverage exported **2,094,456 bytes**; the fixed LLVM tools parsed
  **5,696 functions**, including nonzero execution counters (maximum 383,731).
  Capture used an explicit hardware breakpoint after OSTD's announcement,
  before architecture poweroff. GDB detached and the original guest exited
  raw 33. OSTD and its ISA poweroff lifecycle remain unchanged.
- Full Asterinas kernel debug run 03 hit `__ostd_main` at
  `0xffffffff88426860`, displayed a Rust source line and boot call stack,
  detached, then completed the minimal initramfs boot with raw QEMU 33 and
  the live artifact/serial checker passing. An independent later read-only
  comparison found all 19 allocated sections identical between the symbol
  and executed boot ELFs; run 03 did not read runtime instruction bytes.

Final run 04 also passed: GDB read 32 live instruction bytes at the verified
PC and matched them to both this run's symbol ELF and executed boot ELF. It
then detached and the complete kernel again returned raw 33. The verified
helper source commit is `40f6c7ae47626df9eb66eb3c4a4c9036bc5c8ccc`. Debug helper
host checks passed 7/7 under both `-I` and `-I -O`; listener checks passed 3/3.
The executed stripped ELF SHA256 is
`fcec53875dec2ca19b20e285df94590e9c21036cdabec54799fbda6bddb84026`;
the original DWARF symbol ELF SHA256 is
`a1c7a44cb844553d00c2942760df0f2389919f1e530bfaa45081c7463d31e21a`.
The 111,867,352-byte DWARF artifact is recorded by hash and rebuild commands;
the executed 5,996,200-byte boot ELF is retained compressed.

## Reproduce

On the documented native disposable host, after `support/build/prepare-host.sh
--apt`, export any nonstandard `CARGO_HOME`, `RUSTUP_HOME`, `PATH` and
`VDSO_LIBRARY_DIR` as described in `support/build/README.md`.

```sh
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -I support/build/debug/run.py --output NEW_KERNEL_DEBUG_DIR
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb --output NEW_INTEGRATION_DIR
```

The complete kernel uses upstream developer make targets and the small
1,107,990-byte initramfs, not an installation ISO. Both actual VM profiles use
x86_64, q35/TCG, CPU max, one vCPU, 512 MiB, explicit SeaBIOS and serial logs.
The debug runner owns a loopback listener and passes its actual descriptor
through Bash/make/OSDK into QEMU. The monitor TCP option similarly retains an
OSDK-owned listener with QEMU as client; neither uses a close/rebind port race.
Every saved run includes exact QEMU arguments rather than a generic example.

## Retained failures and limits

The default `osdk-native-unix-v1` result remains **20/22**, with AF_UNIX EPERM
failures retained in the previous native-integration phase. Two initial
TCP-only pilots each passed 2/3 and failed coverage: the monitor connected,
but ISA debug-exit destroyed guest memory before `memsave`. The explicit
GDB capture profile has its own identity and does not rewrite those failures.

The first full-kernel debug attempt compiled release DWARF successfully but
stopped before QEMU because `rust-strip` was missing. The pinned
cargo-binutils 0.4.0 installation then succeeded. The second attempt refused
to replace an existing `kernel/OSDK.toml`. Both complete failures are retained.
The first attempt did not record a symbol ELF SHA; a later SHA is not
backfilled into it.

The temporary manifest reappeared with a new inode after observed cleanup.
An isolated nonce-file control independently reproduced deleted-file
reappearance without Git or kernel work. A workspace synchronization script
is a concrete candidate, but no write syscall/PID was bound to these events.
The cause remains unresolved; the build still refuses an existing manifest
and cleanup still requires its own inode. See `manifest-observation/` for
actual event/stat evidence and the separately identified fake-project tests.
Host ptrace probing returned EPERM; no successful host tracing is claimed.

The earlier kernel-mode baseline remains OSTD 221 and aster-core 141 reported
passes, with three VMX/EPT soft skips and an exercised lower bound of 359.
Those crate suites were not rerun in this phase. These results do not establish
the full upstream userspace/device matrix, SMP, VMX/EPT, cross-host bit
reproducibility, HOS2 or resource-quota enforcement. Reliable Rust frames in
the saved GDB stack precede unknown low-level tail frames; no complete unwind,
source stepping or local-variable acceptance is claimed.

## A00 / A05 / A06 handoff

Kernel root: `kernel/asterinas/`. Build and boot entry points are the commands
above. A01 owns the build/OSDK derivative only; core edits remain with A05/A06.

| Owner | Ready integration point, relative to kernel root |
| --- | --- |
| A05 process | `kernel/core/src/process/process/mod.rs`: `Process`, `pid`, `start_time`, `tasks`, `run` |
| A05 trusted launch | `kernel/core/src/process/process/init_proc.rs`: `create_init_process`, `create_init_task`, `spawn_init_process` |
| A05 exec | `kernel/core/src/process/execve.rs`: `do_execve`, `do_execve_no_return` |
| A05 ioctl | `kernel/core/src/syscall/ioctl.rs`: `sys_ioctl`; `kernel/core/src/fs/file/file_handle.rs`: `FileLike::ioctl` |
| A06 common scheduler | `kernel/core/src/sched/sched_class/mod.rs`: `ClassScheduler`, `PerCpuClassRqSet`, `LocalRunQueue` |
| A06 classes/accounting | `kernel/core/src/sched/sched_class/{stop,real_time,fair,idle,time}.rs` |
| A00 coordinated boundary | `ostd/src/task/scheduler/mod.rs` |

Latest main was independently observed at `3fe03e725e9afdd76155f03199b8bfff990f00dd`
while this phase ran. Its A06 update is a referenced result from another
branch, not an A01 retest; see `baseline/latest-main-observed.json`. The old
1% timeout is historical, while precise 1% enforcement remains unestablished.
A00 controls integration into main; this report does not grant a release.

## Verify the archive

From this evidence directory, run `sha256sum -c SHA256SUMS`. Each run's compressed
log archive also has a member index with original sizes and SHA256 values.
Coverage profraw/profdata and the stripped boot kernel are compressed with
original-byte hashes retained. Commands, selected environment variables,
source identities and failures remain readable; tool binaries and Cargo target
caches are omitted.
