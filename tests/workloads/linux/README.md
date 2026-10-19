# A04 Linux user ABI workloads — executable reference and guest replay

The new [Ubuntu 24.04 complete 32-case profile](FULL_UBUNTU_PROFILE.md) has a
separate build/reference/guest entry and freezes the full Python/Tokio runtime.
Its actual CI qualification is recorded separately. The Debian 13 pins and
historical results below remain unchanged and are not upgraded by that entry.

Evidence is **real host Linux execution**, not a kernel compatibility claim.
On Debian 13 x86_64 / Linux 6.18.44 / glibc 2.41 / GCC 14.2 /
SQLite 3.46.1, 31/32 cases passed: 0 failed, 1 `not_run` (Rust/Tokio
runtime blocked by managed-host pathname AF_UNIX `EPERM` after its reviewed
locked build). 28/32 cases are the **same four C ELF** files and can run in
A01's minimal initramfs without guest Python. Python SQLite/NSS/TLS (3) and
Rust/Tokio (1) need independent guest runtime provisioning; they are never
silently counted as passing.

The independent Tokio workload now has a reviewed Cargo.lock with SHA-256
`b38d7f2ae2d70dcd07bc58b5ecf050ae1d3ab19eb08acb4559f1a0c5929a1e42`. A locked
release build under Rust 1.99.1 produced temporary ELF SHA-256
`1b998b3f9bb144312dea4e75149dbf4d01819422421803f065c038666b36d8c5`.
Runtime execution reached pathname AF_UNIX bind but the managed host returned
`EPERM`; it remains unqualified and is not credited as a pass.

The dedicated 2026-10-16 cloud preflight verified the A01 kernel/initramfs
hashes but returned `blocked_environment_or_input` with exit 2 because QEMU was
absent; its receipt remains historical evidence at
`tests/workloads/linux/baselines/cloud-preflight-20261016.json`. A later
non-system QEMU/SeaBIOS extraction booted the pinned A01 kernel/initramfs under
TCG and exited 33; see `baselines/qemu-cloud-reprobe-20261017.json`.

All host scratch writes are disposable; the C workloads compile both static
and dynamic ELF and store exact SHA-256 / `PT_INTERP` / `DT_NEEDED` and
observable state invariants. Only deterministic results are compared exactly.
Build the same ELF bytes on the host, do **not** rebuild inside the guest.

```sh
python3 tests/workloads/linux/run.py --rust auto \
  --binary-dir /tmp/a04-elf --output /tmp/a04-host.json
python3 -m unittest discover -s tests/workloads/linux -p 'test_*.py' -v
python3 compat/linux/compare.py \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --candidate /tmp/a04-host.json --proven-only --output /tmp/a04-host-diff.json
```

Staged loader/shared-library validation on the original Linux host (still **not**
a chroot, QEMU or new-kernel test):

```sh
python3 tests/workloads/linux/staged_rootfs.py \
  --rootfs /tmp/a04-rootfs --manifest /tmp/a04-manifest.json \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --output /tmp/a04-staged-result.json
```

On the original Debian 13 host, **28/28 C ELF cases actually passed** against
staged glibc loader and libraries. This result is fixed in
`baselines/staged-rootfs-debian13-x86_64.json`; it does not prove absence of
runtime `dlopen` or non-ELF service dependencies. Full reference comparison
remains incomplete for the 3 Python cases and Tokio.

`--trace --trace-dir /new/private/path` requires actual `strace`, stores its
potentially sensitive syscall logs **persistently**, and refuses overwrites.
Without `strace`, the report records `blocked_strace_unavailable`. Trace hashes
alone do not establish a complete runtime file or service dependency closure.

## Actual ABI and resource-release probes

| Case | Inputs, outcome, error & release invariants |
|---|---|
| `*.smoke` | ELF auxv/page size, MAP_SHARED/mmap/msync/fsync, rename, unlink and munmap; data `AYNC` |
| `*.threads_futex` | 4 pthreads + private futex wake/join; wrong value `EAGAIN=11`, 4 threads reaped |
| `*.ipc_epoll` | AF_UNIX stream socketpair + epoll, SHUT_WR→EOF, fd close→`EBADF=9` |
| `*.file_lock` | forked child sees flock contention and fcntl record lock contention, then releases/acquires and reaps |
| `*.process` | SIGUSR1 delivery, two fork/exec/wait cycles exit 17,23; all children waited |
| `*.errno` | ENOENT=2, O_EXCL EEXIST=17, EBADF=9; temporary files removed |
| `*.scm_rights` | sendmsg/recvmsg SCM_RIGHTS across fork, MSG_CMSG_CLOEXEC, shared file offset and release |
| `*.async_fd` | eventfd + timerfd + epoll EPOLLET; 10ms one-shot expiry; empty fd EAGAIN=11 |
| `*.mmap_cow` | MAP_PRIVATE COW never changes underlying file; MAP_SHARED/msync does; both maps released |
| `*.cloexec` | fork+exec closes `O_CLOEXEC` fd, ordinary fd inherited; child reaped |
| `*.fd_limit` | child-scoped RLIMIT_NOFILE exhaustion returns `EMFILE=24`; parent unchanged |
| `*.uds_peercred` | Pathname AF_UNIX bind/connect/accept4 and `SO_PEERCRED` authentic PID/UID/GID; CLOEXEC, half-close and cleanup |
| `*.robust_owner_death` | Shared robust pthread mutex; child exits while holding lock, parent observes `EOWNERDEAD`, marks consistent and reuses safely |
| `sqlite_*.*` | two process writers 40 WAL commits, crash (exit37), uncommitted rollback, 41 rows on reopen, checkpoint/integrity OK |
| `sqlite_wal` (Python) | separate host Python/SQLite WAL + crash recovery; not included in minimal guest |
| `uds_path` (Python) | path AF_UNIX + epoll accept, client roundtrip and unlinked socket; not in minimal guest |
| `nss_tls` (Python) | glibc localhost name lookup and locally trusted test TLS; no external provider; not in minimal guest |
| `rust_tokio` | reviewed locked release build; runtime blocked by pathname AF_UNIX policy; 4 std threads, 16 tasks, AF_UNIX and async fs |

## A01 QEMU replay (full pinned replay pending exact rootfs)

A01 PR [#5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)
**really booted** the complete Asterinas v0.19.0 kernel on its own branch. Its
archived inputs are `support/build/evidence/2026-10-16/artifacts/{kernel.elf.gz,initramfs.cpio.gz}`.
The A04 `guest.py` **verifies** the pinned A01 initramfs SHA-256
`86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`
then preserves the original A01 init checks while injecting exactly the pinned
Linux ELF bytes and a BusyBox shell runner. This creates a **new** initramfs
which must be actually booted and evidenced; A01's original passing serial is
not reused as an A04 test result.

A non-system QEMU/SeaBIOS extraction has already booted the pinned A01
kernel/initramfs with exit 33. Run the full replay on that disposable setup
once the exact rootfs/ELF archive is available. `/tmp/a04-rootfs` must be
constructed and checked against
the committed rootfs manifest; `/tmp/a04-elf` contains identical pinned ELFs:

```sh
python3 support/rootfs/capture.py --root /tmp/a04-rootfs \
  --manifest /tmp/a04-manifest.json --tar /tmp/a04-rootfs.tar \
  --binary /tmp/a04-elf/probe_dynamic --binary /tmp/a04-elf/probe_static \
  --binary /tmp/a04-elf/sqlite_dynamic --binary /tmp/a04-elf/sqlite_static
python3 support/rootfs/capture.py --root /tmp/a04-rootfs \
  --manifest /tmp/a04-manifest.json --verify
# The resulting manifest and ELF SHA must agree with committed pinned files.
python3 tests/workloads/linux/guest.py pack \
  --a01-initramfs /path/to/A01/artifacts/initramfs.cpio.gz \
  --rootfs /tmp/a04-rootfs --rootfs-manifest /tmp/a04-manifest.json \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --output /tmp/a04-guest.cpio.gz --manifest /tmp/a04-guest-inputs.json

gzip -dc /path/to/A01/artifacts/kernel.elf.gz > /tmp/a04-kernel.elf
# Capture actual stdout/serial and raw exit; do not use A01's earlier serial.
set +e
timeout 180s qemu-system-x86_64 -kernel /tmp/a04-kernel.elf \
  -initrd /tmp/a04-guest.cpio.gz \
  -append 'earlycon console=ttyS0 loglevel=info --' \
  -machine q35 -accel tcg -cpu max -bios /usr/share/seabios/bios-256k.bin \
  -m 512M -smp 1 -nodefaults -no-user-config -no-reboot \
  -nographic -display none -monitor none -serial stdio \
  -device isa-debug-exit,iobase=0xf4,iosize=0x04 \
  > /tmp/a04-serial.log 2>&1
rc=$?
set -e
python3 tests/workloads/linux/guest.py parse \
  --serial /tmp/a04-serial.log --qemu-exit "$rc" \
  --kernel-elf /tmp/a04-kernel.elf --guest-initramfs /tmp/a04-guest.cpio.gz \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --manifest /tmp/a04-guest-inputs.json --output /tmp/a04-guest-result.json
python3 compat/linux/compare.py \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --candidate /tmp/a04-guest-result.json --output /tmp/a04-guest-diff.json
```

The guest script reports exact case begins/ends and JSON observations, including
failures. `guest.py parse` only sets `guest_execution_verified` on an actual
correct-kernel/initramfs-hash/exit-33/marker-complete run. This is evidence
consistency, **not cryptographic remote attestation**.
`guest_compatibility_passed` requires **exact reference facts** for all packaged C cases, not merely an exit code of zero or `ok=true`. The full
`compare.py` remains `incomplete` until the three Python and one Rust/Tokio
cases also run against fixed matching ELF/runtime dependencies.

**Important**: A01's minimal initramfs is a **volatile RAM filesystem**.
SQLite process-crash recovery in `/tmp/a04` is meaningful, but **not** S1
virtio-blk/ext2 flush/reboot persistence. An A05 storage qualification requires
separate writable block media and fsync/fdatasync/rename/dir crash tests.

Do not classify missing provider credentials, absent QEMU binaries/firmware,
missing guest Python or Hepta runtime setup as a syscall ABI failure. Every
candidate-kernel failure must carry the serial, input hashes, exit, case name,
Linux reference and minimal repro; A05/A06 own kernel-side fixes.

## A04 second-stage actual numeric syscall trace (Linux host ONLY)

When `strace` is unavailable, `ptrace_trace.c` records **only syscall numbers,
errno and process/thread exits**, using `PTRACE_GET_SYSCALL_INFO` with
`PTRACE_O_TRACE{CLONE,FORK,VFORK,EXEC}` and `PTRACE_O_EXITKILL`. It deliberately
records **no paths, arguments, buffers, credentials or provider requests**.
The companion script enforces exact rootfs manifest + ELF bytes before tracing
and only publishes an aggregate; raw `.jsonl` lives in a NEW mode-0700 directory,
never in Git. `ptrace` changes scheduling and can be denied by local policy.

On the disposable original Debian 13 host:

```sh
python3 tests/workloads/linux/ptrace_probe.py \
  --rootfs /tmp/a04-rootfs \
  --manifest support/rootfs/manifest-debian13-x86_64.json \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --private-trace-dir /tmp/a04-PRIVATE-trace-new \
  --output /tmp/a04-sanitized-syscalls.json
```

Actual result for the supplied fixed rootfs: **28/28** C cases run against its
staged binaries/loader/libraries under ptrace, **54** distinct Linux x86_64
syscall numbers observed, 0 behavior mismatches/blocked traces. Public
aggregate `baselines/linux-debian13-x86_64-ptrace.json` contains per-case
syscall-event totals/hashes plus cross-case numeric syscall/errno counters. The
observed `wait4` `-ERESTARTSYS` is Linux-internal; it is separately counted as
`internal_restart=512`, **not** reported as an application-visible errno.
Counts and syscall order can vary across schedules. The test compares actual
application results/state invariants, **not identical syscall counts**.
This trace is NOT Hepta ELF, NOT a dynamic path/service/TLS/NSS closure, and NOT
Asterinas execution. `strace -ff` remains required for the full W1 file-path
closure, once the pinned Hepta host and credentials are available.

## One-command QEMU differential (pending actual QEMU environment)

`replay_qemu.py` consumes A01's already-accepted **kernel.elf.gz** and
**initramfs.cpio.gz** from [A01 PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5).
It checks the decompressed kernel SHA, A01 initramfs SHA, packaged SeaBIOS SHA,
QEMU executable/version and A04 rootfs/ELF hashes; packages a new guest
initramfs; boots one CPU with **TCG, no host disk/network or KVM**; retains
serial/raw exit; parses the case observations; and runs strict differential.
It refuses to overwrite its output directory and has no installation commands.

```sh
python3 tests/workloads/linux/replay_qemu.py \
  --a01-kernel-gz /path/to/A01/artifacts/kernel.elf.gz \
  --a01-initramfs /path/to/A01/artifacts/initramfs.cpio.gz \
  --rootfs /tmp/a04-rootfs \
  --rootfs-manifest support/rootfs/manifest-debian13-x86_64.json \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --out-dir /tmp/a04-qemu-evidence-NEW
```

`run-status.json` is written even when preflight is blocked; successful A01
`boot_hello` alone never marks an A04 case as passed. On the original A04
The earlier 2026-10-16 execution-container preflight had QEMU/SeaBIOS absent
and returned `blocked_environment_or_input`; that historical receipt has
`guest_execution_verified=false`. The later 2026-10-17 cloud recheck booted
the pinned A01 kernel/initramfs, while the exact A04 rootfs/ELF archive remains
missing for the full workload. The wrapper's negative/preflight tests are
synthetic host tests, not a new-kernel qualification. The full 28-case
comparison still requires 3 Python cases and 1 Rust/Tokio case to be ported.

## Actual Linux chroot replay of the pinned rootfs (2026-10-16)

`chroot_replay.py` uses the **corrected USTAR** generated by
`support/rootfs/capture.py`, checks each of the 17 member bytes/modes before
extraction, creates a fresh temporary root, then invokes the same 28 C ELF
cases under **real `chroot(2)`** with UID/GID 65534. Dynamic ELF PT_INTERP,
`libc.so.6` and `libsqlite3.so.0` are resolved *inside* the captured rootfs,
not via host `LD_LIBRARY_PATH` or host `/lib`. Only the synthetic `/tmp/a04`
subtree is writable. No mount, package install, service or system disk changes
are made. **chroot alone is NOT a security boundary or network/PID namespace**;
these are trusted A04 synthetic test binaries run on original Linux.

```sh
python3 support/rootfs/capture.py --extract-verified \
  --tar /path/to/corrected-a04-rootfs.tar \
  --manifest support/rootfs/manifest-debian13-x86_64.json \
  --root /tmp/a04-rootfs-check-NEW
python3 tests/workloads/linux/chroot_replay.py \
  --tar /path/to/corrected-a04-rootfs.tar \
  --manifest support/rootfs/manifest-debian13-x86_64.json \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --output /tmp/a04-chroot-result-NEW.json
python3 compat/linux/compare.py \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --candidate /tmp/a04-chroot-result-NEW.json \
  --output /tmp/a04-chroot-diff.json
```

The runner requires an authorized disposable x86_64 Linux host with
CAP_SYS_CHROOT; it refuses overwrite of evidence output, drops process
credentials, and never execs shell scripts from outside the chroot.
An unavailable privilege is a host blocker, **not** a new-kernel ABI failure.

**Actually executed on Debian 13, Linux 6.18.44:** corrected image SHA-256
`8c7522ac9a7aed75b7a27d73c8ba71dfd1baf875912b9bf47fcc6effe2d9c746`,
17/17 file content+mode checks, **28/28 C ELF passed, 0 failures**, exact
Linux-baseline `facts` matched, comparison `incomplete` (28 matches; three
Python cases and Tokio not executed). Full result is pinned at
`baselines/chroot-debian13-x86_64.json`. The negative tests also prove that
incorrect expected facts and tampered ELF bytes cannot become a pass.

This strengthens **userland rootfs closure on the original Linux kernel**,
not Asterinas/QEMU compatibility, Hepta W1, a real mounted read-only guest
rootfs, or SQLite S1 block persistence. Those require separate actual runs.

## Expanded pinned host profile and exact guest qualification

The 2026-10-16 extension adds two real C probes (`uds_peercred`,
`robust_owner_death`) to each static/dynamic ELF, growing the actual
Linux-host case count from 27 to **31** passing cases (1 Tokio not_run).
The same 28 C cases passed using the newly frozen 17-file rootfs in both
explicit-loader and uid65534 chroot modes. Repeated GCC builds produced
identical SHA-256 bytes. Ptrace observed 62 syscall kinds on these 28 cases.
The current rootfs USTAR SHA-256 is:

`df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797`

The A01 kernel/initramfs artifacts are pinned under
`support/build/evidence/2026-10-16/artifacts/`; temporary QEMU/SeaBIOS boot
evidence is recorded in `baselines/qemu-cloud-reprobe-20261017.json`. The
full A04 rootfs/ELF replay remains pending, so no full kernel-ABI success is
claimed. The new guest
qualification gate rejects an `ok=true` program whose actual JSON facts or
errno differ from the pinned Linux reference. An exact C subset match can be
recorded separately from the unported Python/Tokio and Hepta W1 workloads.

## Exact A01 guest-run shell rehearsal on original Linux (2026-10-16)

The earlier per-ELF chroot test did not run A01's actual **generated shell
orchestration**. `host_guest_rehearsal.py` now generates the same
`guest.make_guest_script()` that `guest.py pack` places in A01's initramfs,
extracts the manifest-pinned 17-file rootfs into a fresh disposable directory,
adds only an explicitly recorded host BusyBox and its runtime dependencies,
then runs the script under the **original Linux kernel**, UID/GID 65534.

```sh
python3 tests/workloads/linux/host_guest_rehearsal.py \
  --tar /absolute/path/to/manifest-matching-rootfs.tar \
  --manifest support/rootfs/manifest-debian13-x86_64.json \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --output /new/path/host-shell-evidence.json
```

Observed on disposable Debian 13 x86_64: **28/28 actual C ELF cases pass**,
0 failures, script exit 0, and all 28 JSON observable facts match the pinned
Linux reference. The separate four Python/Tokio entries remain `not_run`.
Evidence: `baselines/host-guest-shell-rehearsal-debian13-x86_64.json` includes
script stdout hash, BusyBox and supplemental library hashes, exact archive
hashes, 17/17 verified input files and `qemu_used=false`. The added BusyBox
and any dependencies are **host-rehearsal instrumentation**, not extra
Hepta/rootfs dependencies or A01's static BusyBox image. `/tmp` is a
**disposable chroot directory**, not tmpfs/S1; no mounts were changed.

Guest serial parsing was also hardened to reject replayed/out-of-order boot
markers, repeated runner status, case markers outside the workload phase,
post-run case output, kernel panic lines, duplicate JSON object keys and
non-finite JSON. Those are **synthetic negative tests**, not guest failures.
Execute them under normal Python and `python3 -O`; any timeout kills the
rehearsal shell's dedicated process group, including child ELF processes.

The **next required evidence** is running the A01 pinned kernel and image in
real QEMU, preserving raw serial, exit code and exact ELF differential. The
actual original-Linux shell rehearsal MUST NEVER qualify an Asterinas kernel.


## Shared bounded chroot evidence gate (original Linux only)

`chroot_replay.py` and `chroot_stress.py` now use the same `bounded_run()`
process-group termination and `exact_observation()` decoder. A testcase
passes only when it completes in time, cleanup is not flagged incomplete,
exit code matches the independent reference, stderr is empty, stdout is
exactly one unambiguous JSON line, and all observable facts match. Duplicate
JSON keys, non-finite numbers and extra output are errors. Forked descendants
remaining in the original process group are killed on completion/timeout;
a detached descendant can escape that group, so inherited pipe survival is
reported as **incomplete cleanup**, not as verified release. Chroot is not a
PID namespace and cannot certify general descendant reaping.

Actual original-Linux replay: **28/28** pinned C ELF cases pass; **5 × 18 = 90/90**
chroot stress executions pass; the current restricted-host suite runs **87
tests with six explicit policy skips** under both normal Python and `-O`. See
`baselines/chroot-executor-hardening-20261016.json` for signed-off
input/result SHA-256s. None of this constitutes an Asterinas QEMU run.


## Frozen 28-case QEMU replay input provenance (not a guest pass)

`replay_qemu.py` now checks **exact SHA-256 bytes** of the independent Linux
reference and the rootfs dependency manifest, not just consistency between
two caller-supplied JSON files. It enforces 28 known C ELF cases plus four
unported Python/Tokio cases before qualifying any kernel result. A mutated
reference that changes `static.smoke` from passed to not-run previously could
shrink the denominator to 27/27 and create a false positive; the hardened
qualification rejects it even if all remaining JSON facts appear successful.
Changing the rootfs manifest similarly fails closed. The pin-guard validation
snapshot recorded 64/64 normal/optimized host tests in
`baselines/qemu-reference-pin-guards-20261016.json`. This input-validation
work is a host regression, **not** a Rust kernel or Hepta W1 execution result.
The 2026-10-16 QEMU preflight snapshot remains exit 2 /
`blocked_environment_or_input` because QEMU was absent at that time; the later
2026-10-17 boot receipt closes that tool prerequisite but not the full replay.

## One-command pinned rootfs.tar QEMU replay (2026-10-16)

`replay_qemu.py` accepts `--rootfs-tar` instead of `--rootfs`, with exactly one input
required. The reviewed USTAR SHA-256 is
`df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797`;
the independently reviewed manifest SHA-256 is
`55aa8369d4f912267139ef7626c752814d7dc833e49accc337529f2545fb94cb`.
Both are checked before the 17 file types/modes/sizes/content digests are
verified and extracted into the NEW private `--out-dir/staged-rootfs`.

```sh
python3 tests/workloads/linux/replay_qemu.py \
  --a01-kernel-gz support/build/evidence/2026-10-16/artifacts/kernel.elf.gz \
  --a01-initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --firmware /usr/share/seabios/bios-256k.bin \
  --rootfs-tar /absolute/path/to/fixed/rootfs.tar \
  --rootfs-manifest support/rootfs/manifest-debian13-x86_64.json \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --out-dir /new/private/a04-qemu-evidence --timeout 180
```

Host-only verification consumed the actual A04 Handoff v2 archive: 17/17 files
matched. Ordinary Python tests were 68/68 and `python3 -O` tests were 68/68.
Four new negative tests reject altered tar bytes, changed manifest, simultaneous
inputs and an existing extraction destination. The historical QEMU preflight
returned exit 2 (`blocked_environment_or_input`) before the later temporary
QEMU/SeaBIOS boot receipt. No full guest ABI pass, Rust/Tokio run, Hepta W1 or
S1 durability is claimed.
Evidence: `baselines/rootfs-tar-staging-debian13-x86_64.json`.

## SQLite private-source recheck (2026-10-16)

The missing system `sqlite3.h` and linker symlink were worked around without
installing packages by compiling the locked `libsqlite3-sys` 0.37.0 amalgamation
from the Cargo registry source. The source hashes, sanitized build command and
full report hash are fixed in
`baselines/sqlite-private-build-20261016.json`. The dynamic and static SQLite
ELFs and the Python WAL case all passed: 40 concurrent commits, crash exit 37,
41 durable-to-reopen rows, rollback of the uncommitted row, checkpoint 0 and
`integrity_check=ok`.

The same run still has four host-policy failures: pathname AF_UNIX blocks both
`uds_peercred` ELFs and `uds_path`, and blocks the Tokio runtime after its locked
release build. Those failures are retained as environment evidence; they are
not counted as a Linux reference pass and do not establish a kernel defect.

## Fixed Hepta cloud probe (2026-10-16)

At the required Hepta source commit
`f8c9419df6ddeb36ff8b522a50219981fb8d9345`, the locked Agentd e2e build
completed in the cloud. The debug test ELF is retained only as build evidence
(`5c34f4ce5aca36ea2619e42aef2673c092641e0c888cda9b1147542e844414`); it is not
the release ELF pinned by `compat/linux/hepta-profile.json`. The e2e test exited
101 because the Wiremock Responses expectation matched zero requests, so no
provider request or terminal tool-effect receipt exists. `strace` was separately
blocked by `PTRACE_TRACEME=EPERM`. The sanitized evidence is
`baselines/hepta-cloud-probe-20261016.json`; these are host composition and
managed-policy blockers, not kernel compatibility results.

## QEMU boot input recheck (2026-10-17)

The cloud runner now has a reproducible temporary QEMU/SeaBIOS extraction. The
fixed A01 kernel/initramfs booted under TCG and exited 33 with complete boot and
reboot markers; see `baselines/qemu-cloud-reprobe-20261017.json` for QEMU,
SeaBIOS, command and serial hashes. This closes the QEMU boot prerequisite only.
The exact Debian13 rootfs and four manifest-pinned ELF bytes remain required
before `replay_qemu.py` can qualify the A04 workload; Ubuntu-built replacements
are rejected by the input hash guards.


## First real guest probe (2026-10-17)

The pinned A01 kernel was booted under temporary QEMU/SeaBIOS with a fresh
probe archive. Of 13 ABI probes, 11 returned the expected zero result. The
remaining two are recorded as real guest gaps: `scm_rights` lacks
`MSG_CMSG_CLOEXEC` support and timed out (exit 143), while `fd_limit` failed
its EMFILE/rlimit assertion (exit 20). See
`baselines/guest-qemu-probe-20261017.json` for exact hashes, serial and case
results. This is guest evidence for A05/A06, not a full pinned Debian13 ELF
compatibility pass.


The focused `fd_limit` rerun confirms the guest-side cause: `setrlimit` and
`getrlimit` reported soft=32/hard=4096, but 256 `open()` calls succeeded with
errno=0 instead of EMFILE. A05 owns this RLIMIT_NOFILE enforcement gap.


The focused SCM_RIGHTS rerun observed `recvmsg(..., MSG_CMSG_CLOEXEC)` with a
received descriptor whose `FD_CLOEXEC` flag remained clear; the kernel serial
reported `unsupported flags: MSG_CMSG_CLOEXEC`. A05 owns this ancillary-data
flag gap.


The focused guest AF_UNIX abstract probe passed bind, connect, accept/read and
child exit, confirming that the host AF_UNIX `EPERM` policy is separate from
the guest socket implementation.
