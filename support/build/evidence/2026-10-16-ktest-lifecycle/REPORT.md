# A01: kernel-test ownership and safe manifest cleanup

The complete fixed kernel remains Asterinas v0.19.0, upstream commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, Rust
`nightly-2026-07-21`. The only vendored root is `kernel/asterinas/`.
This phase changes no tracked file under that directory, including A05/A06
core or OSTD. Root README remains zero bytes; upstream documentation and
licenses remain present. Fixed-input verification checks 118 files.

The actual main at phase start was
`ed7c9ef81388f89f1509e62f4d8d54322b23f496`; its A05 host-probe correction
was merged and published as `84040737d2263368d254d4b16dabff7afb797ea4`.
Only A00 integrates main. Work remains on `agents/A01-asterinas-boot`,
[PR #22](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22).

## Fixed failures

| Actual failure | Change and measured verification |
| --- | --- |
| The public ktest CLI received SIGTERM, exited -15 and released its workspace flock while its verifier leader and descendant still held live pidfds and a TCP lease. | Published `efb02440ad6fff3b7a1a5d5019f660743d74ab32` owns every command, including compiler/Git metadata, in one session. Signals latch until ownership is published; TERM/KILL precede direct reap and lock release. `host-ktest/` preserves the original and repaired same-fixture observations. Fifteen host tests pass in each Python mode, including TERM at all eight command stages, repeated-signal seams and cancellation during success publication. |
| The old shell cleanup checked a manifest inode, then an atomic replacement occurred before rm. The foreign inode was deleted and the wrapper exited 0. | Published `a770f31a868d805524065c65a2bcfcbcf10ede2e` pins its owned regular inode with FD8 before publication. Cleanup atomically moves the public entry into a fresh private directory, then inspects that captured entry. Only the captured owned inode is deleted. A foreign file, symlink or directory is restored with RENAME_NOREPLACE or retained with a recovery path and failure status. Thirty-one runner/supervisor host tests pass in each mode. `host-manifest/` retains the original failure and deterministic replacement/conflict tests. |

Python modes are `-I` and `-I -O`. Host fixtures are not kernel boots.
WNOWAIT retains the direct session leader through the last group signal;
ECHILD disarms signaling. Descendants must remain in that original group.
Only direct leaders are claimed reaped; descendant exit is asynchronous and
observed with owned pidfds in the probes. No post-reap group signaling,
numeric PID guessing, subreaper or core implementation change was added.

Per-command `raw_exit_code` retains the actual wait status, while `exit_code`
records normalized status or first cancellation 130/143. An earlier version
of the new receipt used 143 in the raw field; its logs and correction history
remain explicit. Cleanup failure changes an otherwise successful shell exit
to failure and preserves a prior nonzero build status.

## Actual source-build and QEMU results

| Public entry and source | Actual result |
| --- | --- |
| Full `ktest/run.py`, source `efb02440`, tool session 96725 | Outer exit 0. OSTD reports 221 passed, 0 failed, 0 filtered, with 3 explicit VMX/EPT soft skips. aster-core reports 141 passed, 0 failed, 0 filtered. Two actual guests both return raw QEMU33. Exercised pass lower bound is 359, not 362. All ten actual command receipts report raw/effective 0 and their direct leaders reaped. |
| Real ktest cancellation, source `efb02440`, tool session 50773 | Controller exits 0 after verifying CLI143/failed/SIGTERM, native QEMU and CLI pidfds alive before cancellation and exited afterward, stable lock inode reacquired, and six direct command leaders reaped. Actual Cargo leader raw status is 13; effective cancellation is 143. |
| Public `kernel.sh run_kernel`, source `a770f31a`, tool session 58936 | Outer exit 0, complete initramfs boot and raw QEMU33. Live and offline boot checks pass. Supervisor worker reaped. The actual new cleanup helper captures its FD8-owned inode, deletes that inode, removes its custody directory, and returns 0. |

The cancellation uses a test-only PATH adapter that execs native QEMU with
the original ELF/device/serial arguments plus `-S`. The guest is paused before
execution: **no Rust entry, test execution or boot pass is claimed for it**.
Its recorder remains rawnull, with a zero-byte serial file. These incomplete
records are preserved, not replaced by a successful guest's logs. The saved
cancellation ELF matches this phase's actual OSTD test ELF.

All real guests fix x86_64, q35/TCG, CPU max, one vCPU, 512 MiB, packaged
SeaBIOS and serial, without a host data disk or guest network. A host Linux
boot or ISO installer is not acceptance. The complete test run performs an
offline locked source OSDK installation (cached release product) and actual
compilation of both test kernels. The existing target cache is explicitly
reused; it is not an empty-target rebuild. The final public normal boot also
reuses its existing kernel product. The preceding phase's separate clean
full-kernel compilation remains historical evidence, not a new run here.

| Retained actual artifact | SHA256 |
| --- | --- |
| OSTD test ELF, 2,004,424 bytes | `772fe2bf84a55651afb84d0cc1ed43c36e69175bccc451af7c0f6b0aa8fffa35` |
| aster-core test ELF, 6,520,680 bytes | `5b0e758a2bbfb4ba8dad18db9d4a14ab6f23e665eebf1d5c875b1989d418583e` |
| Normal boot ELF, 8,290,880 bytes | `490ca0406593c28e64a22333ba432de6122b9a796b0f7f20352b6b2c55e7df56` |
| Minimal initramfs, 1,107,990 bytes | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| New normal-boot serial, 72,299 bytes | `774861f179d264e69ce774ce85a95011c78c125bd2a4a3defa93959bf73b2302` |

Both actual test ELFs were read and compressed before further target reuse.
Their bytes, serials, generated locks and source inputs are independently
bound to the actual QEMU records. The normal boot ELF equals its previous
cached product; that observation does not prove bit reproducibility. The new
test ELF hashes differ from historical ones; no untested cause is assigned.

## Reproduction and owner handoff

Use the documented disposable host preparation and a separate worktree at
the exact source commit. Preserve the selected CARGO_HOME/RUSTUP_HOME,
offline dependency cache and VDSO_LIBRARY_DIR from the invocation records.

```sh
support/build/prepare-host.sh --apt
python3 -I support/build/ktest/run.py --output NEW_KTEST_DIR
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
```

The build wrapper still uses upstream developer make targets and a small
BusyBox initramfs; no NixOS ISO, Docker/Nix prerequisite or machine firmware
change is required. Existing generated manifests are refused, not overwritten.
The controllers retained beside the evidence show this run's locked
preservation, worktree pinning, exact commands, environment and source SHA.

Relative to `kernel/asterinas/`, unchanged A05 interfaces are
`kernel/core/src/process/process/mod.rs::Process`,
`kernel/core/src/syscall/ioctl.rs::sys_ioctl`, and
`kernel/core/src/fs/file/file_handle.rs::FileLike::ioctl`.
A06 retains `kernel/core/src/sched/sched_class/`, ClassScheduler, LocalRunQueue
and accounting. A01 does not change those implementations or another Agent's
branch. These real regressions are available as their baseline.

## Remaining measured boundaries

After successful owned cleanup, the public manifest pathname again contains
a different inode: owned 1581799, later observed 1581801, with the same minimal
manifest SHA `1ff39174c39411f8b9a7fd328f762268e62d88521b43ebbde384d03d7d9a9f9f`.
The writer/cause remains unknown and the later entry is preserved. Custody
protects the captured entry; it does not guarantee continuous pathname
occupancy or prevent future writers. The first post-boot observer compared
whole stat_result values and reported a nonstable read. That original result
is kept; a separate follow-up records equal before/after content identity
fields, the same later inode and bytes. No missing metadata is reconstructed.

A current host-only AF_UNIX probe fails at socket creation with EPERM before
bind. Its initial inline probe failed outside the bind-only exception guard;
the corrected script records the exact failed stage. The prior OSDK TCP/GDB
22/22 result was not rerun or upgraded by these kernel tests. The preceding
A04 same-ELF result remains 24 matches, two fd_limit failures and two
SCM_RIGHTS timeouts out of 28, not rerun here. Core owners retain those
reproductions. No HOS2 handler, resource quota acceptance, Hepta W1, SMP,
VMX/EPT hardware support, persistence or release result is claimed.

Remote CI state must be read separately from these local/guest exits. This
report does not declare GitHub CI green or main merged. `report.json` and the
per-directory manifests index the completed records; the final publication
gate also verifies their bytes from Git index objects.
