# A01 review fixes and real Linux ELF guest handoff

Fixed full-kernel source remains Asterinas v0.19.0,
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, Rust `nightly-2026-07-21`.
The single kernel root is `kernel/asterinas/`. No A05/A06 core or OSTD file
was changed. Project root README remains zero bytes. This phase merged actual
main `3fe03e725e9afdd76155f03199b8bfff990f00dd` into the A01 branch before fixes.
Before final delivery, main advanced to
`ad5a942376116277b466d8eec9d35f47e9d201c2`; its status updates and value-only
A03 control types were merged as `de4f6082f5c43e2592a4b33daeeaa6827803eb3e`.
The real pinned/offline control-library suite passed 1 unit and 20 integration
tests. Its first attempt could not find rustc and never compiled; that failure
and the corrected explicit-compiler invocation are both retained in `baseline/`.
`report.json` records exact commits, source boundaries and evidence links.

## Actual kernel and OSDK results

At `f473a2ccc8dfeaed1223e8478a19c79c90b323e4`:

- The complete kernel developer build/debug target passed again. GDB hit
  `__ostd_main` at `0xffffffff88426860`, read 32 live instruction bytes matching
  both this build's symbol and boot ELFs, displayed Rust source/stack, detached,
  then the full minimal initramfs boot passed the live checker with raw QEMU
  **33**. The boot ELF remains
  `fcec53875dec2ca19b20e285df94590e9c21036cdabec54799fbda6bddb84026`;
  the original DWARF ELF remains
  `a1c7a44cb844553d00c2942760df0f2389919f1e530bfaa45081c7463d31e21a`.
- Explicit `osdk-native-local-tcp-gdb-capture-v2` completed a single **22/22**
  run, 0 failed/blocked, one explicit VMX soft skip. All eleven actual QEMU
  guests returned raw33; the outer runner actually returned 0.
- Coverage exported **2,094,448 bytes**, matching this guest's announcement.
  Fixed LLVM tools parsed **5,696 functions**, with nonzero counters (maximum
  383,731). GDB captured before original OSTD poweroff, detached, and the
  original guest returned raw33. The historical 2,094,456-byte profiles are
  retained; their size is not imposed on a new announcement.
- Production OSDK host suite: **38 passed, 0 failed, 1 ignored**. That ignored
  real-QEMU transport test was separately executed and passed. Its q35/TCG,
  64-MiB, raw0 HMP probe deliberately has no project kernel and is not kernel
  boot acceptance.

`kernel-debug/` and `osdk/` retain complete commands, selected environment,
source identities, QEMU arguments/PIDs, artifact hashes, serial and GDB logs.
All 63 complete-kernel source inputs and 89 native-run identities were checked
against the exact published source. The runtime native HEAD was local metadata
`8db0b13...`, with the same tree as published `f473a2c...`.

## Concrete review fixes

| Issue | Result and real checks |
| --- | --- |
| Archive follows links / missing source | Adopted A00 exact PR32 source after its 13 checks in each Python mode; independently reproduced and fixed root substitution, added-hardlink and index overwrite. Final **20/20** in each mode; **673 existing files** rearchived and byte-checked. These are host evidence checks, not new guests. |
| Cargo global options / aliases bypass lock policy | Parse global values, canonicalize builtin aliases, pin explicit toolchain selection, force flags before `--`. **13/13** in each mode; four actual fixed-Cargo commands including a locked cfg-if dependency build/run. A subsequent two-line clippy rejection delta has final host tests and exact reverse patch, not a falsely repeated real smoke. |
| Runner lock and interruption | Lock acquired before output allocation; all commands in owned sessions, group TERM/KILL before direct leader reap; ECHILD disarms. **10/10** lifecycle checks in each mode, original timeout check **1/1** in each mode, profile checks **7/7**. Original four failed controls retained. No `/proc` PID inference or subreaper. |
| Monitor first-client provenance | OSDK rejects an outsider arriving first, closes the setup listener, then passes only its own connected TCP endpoint to QEMU. Parent CLOEXEC stays set; child-only inheritance uses FD >=64. Recorder validates the exact reserved fields and connected endpoints, records actual QEMU PID and closes its copy. Final **33/33** recorder checks in each mode plus the real adversarial transport probe. |
| Named scheme loses monitor setting | Common scheme inheritance now preserves the field, including run/test inheritance and overrides; included in the actual host suite. |

The private FD handoff does not claim protection against process injection or
privileged descriptor access. The archive captures stable individual files,
not an atomic snapshot of an entire concurrently changing tree; its destination
parent is trusted. Cargo is a finite integration adapter, not an execution
sandbox. Runner cleanup covers descendants that remain in its original group
and reaps the direct leader; grandchildren exit asynchronously after SIGKILL.

A later review identified the separate coverage-helper session escaping outer
case cleanup. The original timeout left the helper and real GDB alive, verified
through owned pidfds and a busy TCP lease. At
`349a28ff9f78319e497d3fd7b58fe73b6e6e44b5`, helper/GDB remain in the outer
runner group and inner cleanup owns only direct Popen children. Five real host
lifecycle checks passed, plus final recorder 35/35 and capture 4/4 in each Python
mode. These host fixtures contain no kernel. See `host-fixes/capture-lifecycle/`.

A fresh exact coverage guest then passed **1/1**, raw QEMU33, exporting
**2,094,456 bytes**, SHA256
`a6a60289f3e9fed6c3f6ad17f1108e1a44aac61cac313e8ebc3b1611288eb9a1`.
Fixed LLVM parsed 5,696 functions; the actual outer runner exited0. Runtime code
matches `349a28ff...`; documentation input bytes match the subsequently published
`5f59dbb7baa34cf7c69e8730bc4642f061b36fa1`. Invocation dirty state and later
byte binding are retained in `osdk-capture-exact/`. The full 22 above stays bound
to `f473a2c`, preceding this cleanup change; it was not rerun at the later fix.

## Same Linux ELF on the actual Rust kernel

The exact A04 source is PR8 commit
`16d672881909a5a9197d82126032b7d962db7d76`; its current 17-file rootfs tar SHA
is `df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797`.
All ELF bytes/modes, the original accepted A01 kernel `e884f5e5...`, initramfs,
SeaBIOS and QEMU identities were checked before replay. There is no ISO,
Linux host-kernel substitution, host disk or networking in these guests.

The unmodified original 28-case suite timed out at 180 seconds after 8 exact
matches and one completed failure. Its raw QEMU status is null and wrapper
exit is 2. It remains a failure.

The independently named `a01-a04-isolated-case-v1` gave every case a fresh
1-vCPU/512-MiB/q35/TCG guest, at most two concurrently, 30 seconds per guest:
**24 exact Linux-reference matches, 2 completed fd_limit failures, 2 SCM_RIGHTS
timeouts / 28**. Both fd_limit guests powered off raw33 but the ELF exited20;
raw33 alone does not pass a workload. Both SCM cases have timeout/rawnull.
Static/dynamic SQLite WAL, robust mutex owner death, thread/futex, pathname
UNIX credentials, fork/exec and other recorded facts actually matched.
Four additional unported Python/Tokio workloads remain outside this C denominator.
The volatile RAMfs tests do not establish block-media persistence or Hepta W1.

`linux-guest/REPORT.md` contains the original suite, final canonical 28 serial
snapshots, all prior failed diagnostic attempts and exact reproduction. One
old serial pathname was later replaced by an earlier prefix; an intermediate
adapter also had a CRLF parsing mistake. Neither is hidden or relabelled as a
kernel result. The final runner reads the same open descriptor QEMU wrote,
immediately saves raw bytes, and checks compressed and uncompressed hashes.
A later raw pathname difference is explicitly separate from its intact snapshot.
Writer/cause remains unknown. The generated-manifest reappearance and protective
refusal to overwrite also remain recorded.

The full 28-case diagnostic remains bound to
`d85b1e091143a9c4f004c024f433a58188455105`. A later direct-QEMU cancellation
fix at `3db0aa8ac369888db66c2dd05b825f648a2d27ff` passed two real SCM guest
signal checks: CLI143/SIGTERM and CLI130/SIGINT, each returning in about 0.164s,
with owned pidfd exit, direct-child reap and no queued second launch. A separate
three-case repeat gave one match/raw33, one ELF20 failure/raw33 and one timeout;
the driver exited2. See `linux-guest/cancellation/`. Its original dummy attempts
were inconclusive because numeric `/proc` lookup crossed a PID namespace, and
do not establish an original leak. Actual checks used jobs=1 and terminate;
two simultaneously active cancellations and kill fallback were reviewed in
source, not claimed as measured. No later full-28 rerun is implied.

## A00 / A05 / A06 handoff

Build: `support/build/kernel.sh kernel`; boot: `support/build/kernel.sh run_kernel`;
Rust-entry debug: `python3 -I support/build/debug/run.py --output NEW_DIR`.
All complete kernel runs retain x86_64, one vCPU, 512 MiB, q35/TCG and SeaBIOS.

A05 integration interfaces remain `Process` in
`kernel/core/src/process/process/mod.rs`, `sys_ioctl` in
`kernel/core/src/syscall/ioctl.rs`, and `FileLike::ioctl` in
`kernel/core/src/fs/file/file_handle.rs`, relative to the single kernel root.
A06 retains `ClassScheduler`/`LocalRunQueue` and classes/accounting under
`kernel/core/src/sched/sched_class/`; shared OSTD changes require A00 coordination.

Two new same-ELF reproduction targets are ready for A00 to assign to core owners:

- `static.fd_limit` / `dynamic.fd_limit`: soft `RLIMIT_NOFILE=32` is accepted,
  but the child opens 256 files; parent assertion fails. Inspect
  `syscall/open.rs`, `fs/file/file_table.rs`, `syscall/prlimit64.rs` and
  `process/rlimit.rs`.
- `static.scm_rights` / `dynamic.scm_rights`: serial reports unsupported
  `MSG_CMSG_CLOEXEC`; received-FD flag validation fails before the datagram ACK.
  `net/socket/unix/ctrl_msg.rs`, `FileMessage::write_to`, still has the upstream
  CLOEXEC TODO. The same static ELF passed both cases on the original Linux
  host. Detailed observation/inference boundaries are in the Linux report.

A01 did not change these core files. Default UNIX OSDK **20/22**, two TCP-v1
pilots **2/3**, and earlier OSTD/aster-core **362 reported / 3 soft skips / 359
exercised lower bound** remain historical results, not reruns or full upstream
acceptance. SMP, VMX/EPT, HOS2, quota enforcement and production release are
not established by this phase. A00 decides integration into main.

From this directory, `sha256sum -c SHA256SUMS` checks the final immutable archive.
Every compressed log/source bundle also has a member hash index. The published
Git tree is checked against the verified local tree.
