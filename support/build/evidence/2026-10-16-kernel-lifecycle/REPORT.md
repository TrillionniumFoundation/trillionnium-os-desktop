# A01 kernel lifecycle fixes and fresh source-build evidence

The fixed complete kernel remains Asterinas v0.19.0, upstream commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, nightly-2026-07-21.
The single vendored root is `kernel/asterinas/`. This phase changed no file
under that directory, including OSTD and A05/A06 core source. Its derived tree
remains `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`; the 118 fixed-input checks
pass and the project root README remains zero bytes.

Main was `99924da27531876d7c383d490175d06d8f200856` at phase start. Its later
A00 CI/status and A05 guest-refusal records were merged without conflicts from
`f47540fb8165c8cc078d997f009f6f55ff731f06`, as
`ce4f3515c2c83bb602f6d811f102235ce9777c42`. No other Agent branch was modified.
A00 retains main integration.

## Measured fixes

| Problem | Fix and actual evidence |
| --- | --- |
| Debug CLI default SIGTERM bypassed cleanup | At `9b381118fe8a1889d4523b4de999bbe45f1b0436`, handlers remember cancellation; checkpoints run only after Popen ownership exists. Final cleanup cannot be interrupted by a second asynchronous Python exception. Original live pidfd/TCP/flock leak retained; 10 host tests in each Python mode pass. |
| Standalone kernel.sh exited while make/children retained its lock | At `4b3153079336ddea244c2ffecea1da0e006769b6`, a supervisor retains its waitable worker identity through group TERM/KILL and direct reap. Debug explicitly uses its own inherited worker group, avoiding an escaping nested session. New supervisor 9 and existing worker/manifest 10 pass in each mode; original TERM leak and INT stall remain evidence. |
| Integration runner second signal skipped cleanup entry | At `7cf6f7c329361c9828a98b766d1f0d78cf53b58d`, a cooperative first-signal latch replaces temporary handler switching. Original two real signal seams leaked; patched seams retain first INT/130, complete records and release owned processes/leases/lock. Lifecycle 14, timeout 1 and profile 7 pass in each mode. |
| Version metadata aborted before QEMU with exit 141 | At `22fcd9edeb8d4e1abee7ce2c3109df5d922c8ed5`, make/gcc versions are retained in full, removing the `head` truncation under pipefail. The original actual failure is retained; the subsequent real cancellation reached the Rust entry. |

Both Python modes are `-I` and `-I -O`. Host fixtures are identified as such;
they do not count as kernel boots. WNOWAIT reserves each direct leader until
group signals precede reap; ECHILD disarms signaling. No `/proc` identity
guessing, post-reap numeric group signaling or subreaper was added. Descendants
must stay in the owned group; their exit after KILL is asynchronous, and only
direct children are claimed as reaped. The private worker route selects
lifecycle ownership, not authorization.

## Actual Rust kernel and QEMU runs

The disposable checkout is a detached worktree of this same repository and
fixed source, not a second kernel implementation. It began without a target
directory or generated kernel manifest. Fixed Rust/Cargo/LLVM, GDB15.1 with
Python, QEMU8.2.2, SeaBIOS, vDSO and static BusyBox were checked before launch.
Cargo ran offline. The real logs show locked OSDK installation from source,
full kernel dependency compilation and `aster-core`/Asterinas compilation.

| Run | Actual result and source binding |
| --- | --- |
| Fresh full-kernel debug at `9b381118` | Tool session 88997 exited 0. Native GDB hit `__ostd_main` at `0xffffffff88422840`, verified 32 live instruction bytes against both ELFs, detached, then complete initramfs boot passed with raw QEMU 33. `kernel-debug-clean/` retains commands, artifacts, GDB and serial. |
| Public run_kernel at `7cf6f7c` | Tool session 2857 exited 0, including observed release recompilation and QEMU33. Supervisor reported exit 0 and worker_reaped=true; the live checker also passed. Target cache reuse is explicit. See `kernel-public/`. |
| Final integration runner at `7cf6f7c` | Tool session 74134 exited 0: one complete 22/22 run, zero failed/blocked, one VMX fallback soft skip, eleven actual QEMU guests all raw 33. Coverage exported 2,094,456 bytes; fixed LLVM parsed 5,696 functions, maximum count 383,731. See `osdk/`. |
| Real debug cancellation at `22fcd9ed` | Actual native GDB and QEMU reached the Rust entry and original live 32 marker. A test-only copy of the generated GDB script held there. SIGTERM sent only to the debug CLI produced 143/failed, all owned pidfds exited, the GDB port and workspace lock became available, and direct sessions were reaped. See `real-debug-cancel/`. |

The last row is a successful lifecycle cancellation, **not a boot pass**.
Its recorder was stopped with the owned group, leaving its QEMU record rawnull
and no finalized checker serial. A separately labeled post-cancellation
pathname snapshot is retained. It is not substituted for a complete boot log.
Earlier attempt 1 failed before QEMU with metadata exit 141. Attempt 2 failed
because the test shim generated invalid GDB Python; no cancellation signal was
sent. Both failures remain separate from successful attempt 3.

All full-kernel guests fix x86_64, q35/TCG, CPU max, 1 vCPU, 512MiB, packaged
SeaBIOS and serial. No Linux host kernel or installation ISO is boot acceptance.
No host data disk, production service, BIOS or GPU driver was changed.

| Artifact | SHA256 |
| --- | --- |
| Public boot ELF, 8,290,880 bytes | `490ca0406593c28e64a22333ba432de6122b9a796b0f7f20352b6b2c55e7df56` |
| Stripped debug boot ELF, 5,975,720 bytes | `89c7f0bab00172e4a8d038a3d5c38396d952ff44e4ab159bbe8765edbaa16313` |
| Original DWARF ELF, 111,709,176 bytes | `855e92c82ac3745d40320fd4451e8862e38e2fbfbf7b2c6e98f60d514018d6a8` |
| Initramfs, 1,107,990 bytes | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| This run's coverage.profraw | `3d90660be68c63941c5884390c3d25ccd77c33a461c95b070147989117cf253d` |

Boot ELFs and initramfs are retained compressed. The >100MB original DWARF
file was hashed on site and is rebuilt with the recorded command, not stored
raw in Git. New artifact hashes differ from the earlier build. No cause for
that difference or cross-build bit reproducibility is established; old hashes
and evidence are retained. Runtime local commit metadata, published equal-tree
bindings, selected environment and dirty/untracked state remain explicit.

## Reproduction and handoff

After the documented disposable-host preparation, preserve the environment
variables recorded in each invocation and use a new worktree/output directory:

```sh
support/build/prepare-host.sh --apt
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -I support/build/debug/run.py --output NEW_KERNEL_DEBUG_DIR
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb --output NEW_OSDK_DIR
```

The wrapper uses upstream developer make targets with the small initramfs
overlay. Separate worktrees/target directories isolate generated build state.
The environment nevertheless restored an identical generated manifest about
3 seconds after a locked rename, with a new inode. Writer/cause is unknown. Existing
manifests were preserved under the stable workspace lock; overwrite and inode
ownership protections were not relaxed. Worktrees do not disable that writer.

Relative to `kernel/asterinas/`, A05 interfaces remain
`kernel/core/src/process/process/mod.rs::Process`,
`kernel/core/src/syscall/ioctl.rs::sys_ioctl`, and
`kernel/core/src/fs/file/file_handle.rs::FileLike::ioctl`.
A06 retains `kernel/core/src/sched/sched_class/` and its ClassScheduler,
LocalRunQueue and accounting paths. A01 did not change those implementations.

The previous same-ELF diagnostic is still 24 matches, 2 fd_limit failures and
2 SCM_RIGHTS timeouts/28 at `d85b1e09`; it was not rerun or upgraded here.
RLIMIT_NOFILE enforcement and receive-side MSG_CMSG_CLOEXEC remain owner
reproduction targets in the preceding Linux report. No HOS2 handler, quota
candidate, Hepta W1, block persistence, SMP or VMX/EPT result is claimed here.
Earlier OSTD/aster-core 362 reported passes include 3 soft skips / 359 exercised
lower bound and were not rerun. Original UNIX 20/22 and TCP-v1 failures remain;
a current host-only AF_UNIX bind probe still returns EPERM.

The newly merged A00 workflow's local equivalents passed boot-evidence 15 and
worker 10 in both Python modes. These local exits do not assert remote CI green.
`report.json` links exact source/results. Each compressed bundle has a verified
member index; the final SHA256SUMS is also checked against Git index objects
before publication so later pathname changes cannot silently alter the commit.
