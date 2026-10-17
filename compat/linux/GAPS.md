# A04 evidence and precise A05/A06/A07 handoff (2026-10-16)

**No full pinned Debian13 A04 ELF differential has yet executed on the A01 kernel. The capability probe below is separate evidence and is not a full compatibility claim.** Linux host reference now has **31/32 pass**, with
Rust/Tokio `not_run` because managed-host pathname AF_UNIX returns `EPERM`
after its reviewed locked build; its four C ELF have a reproducible 28-case
no-Python guest harness. A01 independently booted
the real pinned Asterinas kernel in QEMU in [PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5),
including retained kernel/initramfs/serial. Those A01 smoke results are not an
A04 guest pass. A04's new initramfs overlay/parser has been tested with
synthetic input, but **not** booted in QEMU here (no QEMU/firmware/toolchain).

The fixed Hepta source has now produced a temporary Agentd ELF through the real
e2e dependency build: SHA-256
`0a8266635f8dd1b49d5213af4f01aab6c66d7450d9b9e940f71490893ce404ae`, loader
`/lib64/ld-linux-x86-64.so.2`, with direct NEEDED entries for libc, libm,
libgcc_s, libssl and libcrypto. The runtime test itself failed before a
provider request: Wiremock matched zero Responses requests and no terminal
receipt was emitted. `strace` was blocked by `PTRACE_TRACEME=EPERM`, so the
full dynamic path, NSS/TLS/SQLite file closure and tool-effect trace remain
unqualified. Missing host assembly or ptrace permission is not an OS bug.

| Owner | Reproduction and pass/failure requirement | Do not conflate with |
|---|---|---|
| A01 loader/boot | `guest.py pack/parse` using SHA-pinned kernel `e884f5e5...`, fixed initramfs, same four ELF. Record actual QEMU serial/raw exit and 28 C cases | Original A01 boot_hello passing != A04 work passing |
| A05 process | `static/dynamic.process`, `.cloexec`, `.fd_limit`, `.errno`: fork/exec/wait, exit 17/23, signals, O_CLOEXEC, RLIMIT_NOFILE/EMFILE=24, ENOENT=2/EEXIST=17/EBADF=9 | Hepta environment identity errors |
| A05 Unix identity | `*.uds_peercred` requires pathname bind/connect/accept4, peer PID/UID/GID from `SO_PEERCRED`, half-close and pathname unlink; fail only on actual guest mismatch | Absent Hepta credentials or unconfigured control socket |
| A05 IPC/files | `*.scm_rights` crosses fork with SCM_RIGHTS/MSG_CMSG_CLOEXEC + shared offset; `*.ipc_epoll`, `.async_fd` need AF_UNIX/socketpair, epoll, eventfd/timerfd and half-close | Guest service absence/unstaged socket pathname |
| A05 locks/memory | `*.file_lock` requires flock/record lock conflict + release; `*.mmap_cow` requires MAP_PRIVATE COW and shared msync | RAM fs success != real Ext2 durability |
| A05 storage | `sqlite_{static,dynamic}.sqlite_wal_elf`: 40 child commits, crash exit 37, 41 durable-to-reopen records, WAL and checkpoint; needs separate S1 ext2/block crash qualification | In-process reopen != power-failure guarantees |
| A06 robust recovery | `*.robust_owner_death`: process-shared `PTHREAD_MUTEX_ROBUST`, child dies holding lock; parent must receive `EOWNERDEAD`, mark consistent, unlock and reuse | 3-second timeout or absent guest runtime is not proven scheduler failure |
| A06 threads | `*.threads_futex`, `*.async_fd`: futex wake/join/EAGAIN=11, timer/eventfd wake and 10ms expiry. Stress/timeout/interrupt variants still pending; Tokio source requires toolchain | Host Linux thread scheduling order |
| A07/Hepta | Pinned Agentd embedded Codex App Server; authenticated ObjectiveStart must drive real Codex tool with independently observed effect and owner evidence. Private `strace -ff` with sanitized aggregate, actual package/ELF closure | Bare daemon readiness, mock provider or absent credentials |

When a guest case fails, attach its Linux JSON reference, guest JSON evidence,
exact ELF + rootfs SHA, QEMU boot serial/raw exit, syscall errno and minimal
repro. Report whether the issue is kernel ABI, initramfs/filesystem, missing
system service, Hepta host configuration, or unavailable credentials.

`compat/linux/compare.py` checks identical ELF bytes and exact observable
results. Scheduler order is deliberately not compared. Synthetic parser tests
and metadata alone must never be promoted to a new-kernel compatibility pass.

### Fixed-commit Hepta composition boundary (source evidence, not an ABI bug)

`codex-rs/hepta-agentd/src/main.rs:112-183` installs the explicitly requested
`AgentdIntelligenceProductRunnerV1` via `with_intelligence_product_runner`,
but has **no call** to `with_intelligence_invocation_provider`. The latter API
exists (`config.rs:515-535`), is optional by default (`config.rs:217`), and
`runtime.rs:80-119` only attaches it if a composition owner supplied one.
This does **not** prove the provider can never be installed from a different
host; it proves the standalone CLI flags inspected are insufficient for a
canonical seven-owner ObjectiveStart demonstration. A07 must identify and
verify the real product host composition and run/effect receipts. This is
userland assembly evidence, not a reason to patch `kernel/asterinas/**`.


## Follow-up: measured Linux syscall dependencies (2026-10-16)

`tests/workloads/linux/baselines/linux-debian13-x86_64-ptrace.json` is an
**actual PTRACE_GET_SYSCALL_INFO observation** for the 28 pinned C ELF cases
with an identical staged loader/rootfs. The session observed 62 unique x86_64
syscall numbers and 28/28 matching application facts. This inventory describes
the *small selected probe workload*, **not** the required syscall completeness
of Hepta, and **not** an A05/A06 kernel defect list.

- A05 loader/VFS/storage: `arch_prctl`, `mmap`, `mprotect`, `munmap`, `openat`,
  `newfstatat`, `pread64`, `pwrite64`, `fcntl`, `flock`, `fsync`, `fdatasync`,
  `rename`, `unlink`, `msync`, `ftruncate` were all actually observed.
- A05 IPC/process: `clone`, `wait4`, `sendmsg`, `recvmsg`, `socketpair`,
  `shutdown`, `epoll_create1`, `epoll_ctl`, `epoll_wait`, `eventfd2`,
  `timerfd_create`, `timerfd_settime`, `pipe2` were actually observed.
- A06 scheduler/synchronization: `futex`, `set_tid_address`, `set_robust_list`,
  `rseq`, `clock_nanosleep`, signal mask/return, `clone3` attempt and thread
  exits. Internal `wait4` restart (`-ERESTARTSYS=512`) is NOT errno=512.

The real reference has both expected failure errno and successes. Comparing
only syscall names or total calls is insufficient: require exact C probe JSON
invariants and check permissible race outcomes (no exact trace order). For each
new-kernel failure, preserve actual QEMU serial and ABI output before deciding
whether to ask A05/A06 for a kernel correction. A01 PR #5 contains accepted
boot bytes but cannot stand in for this A04 guest run. The one-command
`replay_qemu.py` was actually preflighted with missing QEMU and correctly
returned **blocked**, not kernel failure; 32 host unit/integration regression tests
passed. Real QEMU/Asterinas 28-case differential remains pending.

## Newly closed host-only blocker: real extractable rootfs and chroot ELF tests

A04's old deterministic rootfs tar had a **real USTAR bug**: the directory
names contained trailing `/` but their type flags were `REGTYPE`, so extracting
with Python's `tarfile` failed at `etc/` (`NotADirectoryError`). The corrected
`capture.py` explicitly sets `DIRTYPE` and validates every file and directory
against the existing 17-file manifest before fresh extraction. Old tar SHA
`7ee7becc...` must no longer be used as an extractable image; replacement SHA
`8c7522ac9a7aed75b7a27d73c8ba71dfd1baf875912b9bf47fcc6effe2d9c746`.

**Actual Linux host tests:** pinned 28 C ELF cases execute under chroot with
UID/GID 65534; all 28 return baseline-matching JSON with zero failures.
The 17-file tar checks reject traversal/symlink and preserve read-only modes.
This eliminates an A04 packaging problem, but is **not evidence of an A05/A06
kernel bug** and not a substitute for the A01 Asterinas guest replay. The
available A04 execution container still lacks QEMU/SeaBIOS, Rust/Cargo and
full Hepta host assembly; guest and W1 remain not executed.

## 2026-10-16 expanded Linux host evidence (current fixed ELF profile)

- Original Linux: **31/32** workloads passed, one Rust/Tokio not_run after a
  successful reviewed locked build (managed-host pathname AF_UNIX `EPERM`);
  two complete builds gave identical static/dynamic ELF bytes and app facts. New cases: `*.uds_peercred`, `*.robust_owner_death`.
- The fixed 17-file rootfs now contains the new C ELF; current extractable
  USTAR SHA-256: `df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797`.
  Earlier `8c7522ac...` is the *previous* correctly typed USTAR for the older
  ELF profile; its ELF hashes must not be mixed with this reference.
- Original Linux chroot/UID 65534: **28/28** ELF cases pass; staged-loader
  replay **28/28**, ptrace **28/28**; 62 distinct syscall numbers observed.
- Guest parser now compares **whole errno/IPC/SQLite facts**, not only exit=0
  and `ok=true`; the QEMU wrapper requires an exact packaged-ELF differential.
- These results do not establish new-kernel pass, S1 durability, or Hepta W1.
  A01 source and boot evidence have now been integrated into `main`, but the
  A04 extended-ELF guest run is still **not executed** in this container.

## A04 host guest-script rehearsal and parser integrity (2026-10-16 follow-up)

The previously untested *generated guest shell itself* was run against the
fixed rootfs on original Debian 13 Linux, with chroot and UID/GID 65534:
**28/28** ELF cases passed, 0 failures, script exit 0, and complete case
observations matched the independent Linux baseline. The executable shell was
created by `guest.make_guest_script`, so this verifies orchestration syntax
and file locations in addition to direct per-ELF execution. Separate
instrumentation BusyBox/runtime additions have their own hashes. See
`tests/workloads/linux/baselines/host-guest-shell-rehearsal-debian13-x86_64.json`.

Adversarial serial tests now reject duplicated/out-of-order A01 boot markers,
misplaced A04 case/runner markers, kernel panic text, duplicate JSON keys and
non-finite JSON. All these tests are **host/synthetic**, not a QEMU run.
`guest_execution_verified=false` and `qemu_used=false` are explicit in actual
rehearsal evidence. A01/A05/A06 must still run the exact ELF through the
actual Asterinas kernel before any ABI defect or compatibility pass is claimed.


## A04 bounded process cleanup and strict host evidence (2026-10-16)

Original Linux only: `chroot_replay.py` and `chroot_stress.py` now share the
**same bounded process-group and inherited-pipe cleanup**. The previous stress
runner could call `communicate()` without a timeout after killing a timed-out
parent, which could hang if a descendant escaped its process group. A detached
child retaining stdout now produces `incomplete_descendant_cleanup` rather
than a false passing case; it cannot establish full process-tree isolation.
Both runners reject correct-looking JSON accompanied by stderr, extra stdout,
duplicate JSON keys or non-finite numbers. These are test safety regressions,
not evidence of a new-kernel syscall defect.

Actual Debian 13 host validation: **62/62** Python unittests, **62/62** under
`python3 -O`, **28/28** original-Linux chroot C ELF cases plus four not-run
Python/Tokio cases, and **90/90** five-round chroot stress executions (18
cases per round). The fixed 17-file USTAR SHA-256 remains
`df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797`.
See `tests/workloads/linux/baselines/chroot-executor-hardening-20261016.json`
for actual command/manifest/result log hashes and limitations. The A00 runner
request remains [Issue #46](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/46).
**Asterinas A04 ELF guest run, Rust/Tokio and real Hepta W1 remain unexecuted.**


## Fixed-reference denominator guard (2026-10-16)

The one-command A04 QEMU runner now pins both the original Linux reference
SHA-256 and the rootfs manifest SHA-256, plus the expected 28-C/4-unported
case denominator. Previously a self-consistent edited reference could drop a
failing ELF case and still qualify 27/27; negative tests demonstrate the old
acceptance problem and reject that reduced case set. This is **another A04
validation defect closed**, not evidence of an A05/A06 syscall mismatch.
At that validation snapshot, host-only normal/-O tests were **64/64** each. The A01 QEMU+ELF replay
remains unexecuted here (preflight exit 2: missing QEMU).

## Pinned USTAR direct QEMU input (2026-10-16)

New `tests/workloads/linux/replay_qemu.py --rootfs-tar` verifies fixed USTAR
and manifest SHA-256, then safely extracts all 17 files inside a fresh private
QEMU evidence directory. It rejects alternate/mixed/changed inputs. The actual
previously handed-off tar verified 17/17 files under original Debian 13 Linux;
normal/-O regression tests passed 68/68 each. Local QEMU/SeaBIOS is unavailable:
preflight exit 2, `blocked_environment_or_input` (no guest serial).
A00 can run the direct-archive command from Issue #46; A05/A06 ABI compatibility
and real Hepta W1 remain unverified.

## A04 acceptance-chain hardening and cross-Agent guest evidence (2026-10-16)

A04 branch synced to current `main` by merge commit
`b58ab5bacf8cf160f778a5f5e7e098f37de5f1a3`: the merge tree was checked
against main for every **non-A04** path (zero differences). The branch retains
all 49 owned files. Root `README.md` remains 0 bytes.

**Original-Linux reference false positives, reproduced then fixed:** the former
`run.py` classified real child processes as passing even if they printed
`{"ok":false,"ok":true}`, `{"ok":true,"rate":NaN}`, or a correct-looking
JSON object with an error on stderr. Those are not an independent Linux
behavioral reference. `run_case()` now requires **one unambiguous JSON line**, a
strict true success fact, empty stderr and exit=0; it reports invalid output
or timeout as failure without disclosing raw stderr. Six actual child-process
negative/positive regressions are in `test_run_observation.py`. Real Linux
baseline is unchanged: 31 passing cases, one missing Tokio case; all 31
results match the byte-pinned Linux reference.

**A01 QEMU executable identity:** previously the A04 runner accepted any
executable emitting a plausible `QEMU emulator version ...` string, and could
therefore be fooled by a fake emulator/serial producer. It now also pins the
**actual executable bytes** to the A01 accepted QEMU SHA-256
`8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854`
and checks again just before launch. A different distribution build must be
independently reviewed, never silently promoted. This SHA check covers QEMU's
main executable, **not** the full dynamic-library environment or guest
attestation. The synthetic executable-spoof rejection is a host test, not a
QEMU guest run.

### Real guest observations from other owners — keep attribution separate

- **A06 / CFS quota candidate:** A00's actual A01-derived single-vCPU QEMU
  [CPU probe 02](../../results/organ-backend/2026-10-16/cpu-probe-02/result.json)
  (pinned kernel SHA `e884f5e5...`, raw QEMU exit 33) measured **998ms CPU in
  1.000s wall time** after `cpu.max` was configured for 1%; quota execution was
  **not enforced**, despite accepted configuration. This is a concrete
  *cross-Agent* A06 scheduling/backend gap, not an A04-verified syscall mismatch.
  A06 must enforce actual runqueue eligibility/timer throttling and rerun the
  same probe with a bounded tolerated overrun. Simple write/readback is not a pass.
- **A05 / `/proc/self/exe` for shebang interpreters:** A01's original guest
  [failure analysis](../../support/build/evidence/2026-10-16/boot-failure-analysis.md)
  records raw QEMU exit 65 and **1,139** repeats of the init marker, with a
  source-confirmed script-valued procfs executable path. Running external
  BusyBox applets via explicit `/bin/busybox` avoided recursion. The exact
  BusyBox reexec pathname remains an inference; the failed kernel image has a
  different SHA from the subsequently accepted A01 kernel. The A04
  `proc_self_exe.c` probe passes original Linux; an accepted-kernel QEMU guest
  rerun is still needed to establish the current kernel behavior before A05
  patches the process/procfs owner.

A04's full pinned Debian13 ELF guest evidence remains pending; the earlier snapshot lacked QEMU/SeaBIOS and returned `blocked_environment_or_input`. The current capability-probe evidence is recorded separately. At that earlier snapshot, A04 unit tests were
**76/76** normal and **76/76** with `-O`; real original-Linux **31/32** (Tokio not_run), fixed chroot C ELF
**28/28**, and chroot stress **90/90** (five rounds). These remain distinct
from S1 storage crash durability and authenticated Hepta
Agentd→App Server→actual tool execution, both unverified. See
`tests/workloads/linux/baselines/a04-acceptance-hardening-20261016.json` for
commands, input hashes and the exact evidence status.

## Final A04 handoff update (2026-10-16)

The fixed Hepta source now has a reproducible temporary Agentd build receipt:
ELF SHA-256 `0a8266635f8dd1b49d5213af4f01aab6c66d7450d9b9e940f71490893ce404ae`,
loader `/lib64/ld-linux-x86-64.so.2`, and direct NEEDED entries for libc, libm,
libgcc_s, libssl and libcrypto. Cargo inventory and the failed runtime receipt
are in `compat/linux/hepta-profile.json`. The e2e test exited 101 after its
Wiremock Responses expectation matched zero requests; this is an unresolved
host composition/test-harness blocker and produced no tool-effect receipt.

The machine-readable workload catalog binds all 32 reference cases to command
vectors, required interfaces and release facts: 28 ELF, three Python, and one
Rust/Tokio `not_run`; catalog SHA-256 is
`64b268956848d4fd97c6ace51343d607f20495d7bd317491a5bf7ead5e672db0`.
Current restricted-host regression is **87/87**, with six explicit skips for
uid mapping, pathname AF_UNIX and ptrace policy under both normal Python and
`python3 -O`. The authoritative catalog SHA is
`64b268956848d4fd97c6ace51343d607f20495d7bd317491a5bf7ead5e672db0`; the
authorized Debian host evidence remains the recorded 82/82 pre-catalog suite,
31/32 application cases,
28/28 chroot C ELF cases and 90/90 five-round stress runs.

No full pinned Debian13 A04 ELF differential has executed under Asterinas/QEMU; the 2026-10-17 capability probe did execute. `strace` for Agentd is also
blocked by `PTRACE_TRACEME=EPERM`; therefore NSS/TLS/SQLite file closure,
authenticated provider composition and real Agentd → App Server → tool effect
remain unqualified. These are explicit environment or userland blockers, not
kernel ABI findings. The next gate is the exact `replay_qemu.py` run with A01
artifacts and the verified rootfs, followed by A05/A06/A07 owner-specific
triage only for actual guest differences.

## Tokio lock/build follow-up (2026-10-16)

The independent Rust workload now has a committed Cargo.lock with SHA-256
`b38d7f2ae2d70dcd07bc58b5ecf050ae1d3ab19eb08acb4559f1a0c5929a1e42`. A locked
release build succeeded under Rust 1.99.1; temporary ELF SHA-256 is
`1b998b3f9bb144312dea4e75149dbf4d01819422421803f065c038666b36d8c5`. The
runtime attempt reached `UnixListener::bind` and received `EPERM` from the
managed host policy, the same restriction observed by the Python AF_UNIX probe.
Evidence is retained in
`tests/workloads/linux/baselines/tokio-build-blocked-20261016.json`.

This closes the missing lock/build prerequisite but does not turn Tokio into a
passing Linux reference case. A host with AF_UNIX permission must execute the
same binary, verify the four std threads, 16 Tokio tasks, socket round trip,
async file write/read and scratch cleanup before the result can be promoted.
Asterinas guest execution remains a separate gate.

## Current authoritative A04 status (2026-10-16)

The machine-readable catalog currently reports 32 workloads (28 ELF, three
Python and one Rust/Tokio), with 31 reference passes and one explicit
`not_run`. Its authoritative SHA-256 is
`64b268956848d4fd97c6ace51343d607f20495d7bd317491a5bf7ead5e672db0`.
The current restricted-host command runs 87 tests with six explicit policy
skips under both normal Python and `python3 -O`; it does not claim guest
compatibility. The fixed rootfs manifest SHA-256 is
`55aa8369d4f912267139ef7626c752814d7dc833e49accc337529f2545fb94cb`, and
the expanded USTAR SHA-256 is
`df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797`.

No full pinned Debian13 A04 ELF differential has yet run under Asterinas/QEMU; the 2026-10-17 capability probe did run. Tokio has a locked release
build but its runtime is blocked by pathname AF_UNIX `EPERM`; Agentd tracing is
blocked by `PTRACE_TRACEME=EPERM`; and the authenticated Hepta provider/tool
effect path has no terminal receipt. These remain environment or host
composition blockers. A05/A06 kernel defects must only be opened after a real
guest replay produces a reproducible ABI mismatch.

## Dedicated cloud blocker sweep (2026-10-16)

The project cloud environment was rechecked with the committed A01 artifacts.
The kernel gzip SHA-256 is
`4138796d664a9e8dcd3453e31ca7953d69f74ef269169f1339416235c5b59a91`, the
decompressed kernel ELF is
`e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63`, and the
initramfs SHA-256 is
`86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`.
The actual replay preflight verified those pins and exited 2 because
`qemu-system-x86_64` is absent; no guest result was fabricated. The retained
preflight hash is recorded in
`tests/workloads/linux/baselines/cloud-preflight-20261016.json`.

The same sweep confirmed Rust/Cargo 1.99.1, AF_UNIX pathname and abstract bind
`EPERM`, ptrace `EPERM`, `Seccomp=2`, `NoNewPrivs=1`, and `CapEff=0`. SQLite
development headers/linker symlink, the reviewed Debian rootfs archive, and
authenticated Hepta provider composition are unavailable in this cloud image.
These are now evidence-backed environment or owner blockers; none is a new
kernel ABI finding.

## Cloud recheck after workspace recovery (2026-10-17)

The project cloud image was rechecked after restoring the A04 branch. QEMU,
SeaBIOS, Rust/Cargo and qemu-img are absent. AF_UNIX `socket()` creation itself
returns `EPERM`; pathname and abstract binds also return `EPERM`, while
`socketpair()` is allowed. `PTRACE_TRACEME` remains `EPERM` under
`Seccomp=2`, `NoNewPrivs=1`, `CapEff=0`. The replay and trace attempts were
blocked before guest or Hepta execution and are recorded in
`tests/workloads/linux/baselines/cloud-recheck-20261017.json`.

## Cloud blocker closure sweep (2026-10-16)

The cloud-only SQLite dependency gap was rechecked without installing a system
package. The locked `libsqlite3-sys` 0.37.0 amalgamation was compiled from its
Cargo registry source, and both SQLite ELF probes plus the Python WAL probe
passed with 40 concurrent commits, crash exit 37, 41 rows after reopen,
rollback of the uncommitted row, checkpoint 0 and `integrity_check=ok`. The
source hashes and the sanitized report are fixed in
`tests/workloads/linux/baselines/sqlite-private-build-20261016.json`.

The remaining four failures in that same cloud run are classified as managed
host policy: pathname AF_UNIX blocks the two `uds_peercred` ELFs and `uds_path`,
and blocks the Tokio runtime after its locked release build. The cloud has
`Seccomp=2`, `NoNewPrivs=1`, `CapEff=0`; both pathname and abstract AF_UNIX bind
and `PTRACE_TRACEME` return `EPERM`, while `socketpair` is allowed. Namespace or
`bwrap` attempts did not change the result. A host with AF_UNIX and ptrace
permission must rerun these cases before they can become Linux reference passes.

The fixed Hepta source commit also built the Agentd e2e test artifact, but the
Wiremock Responses expectation matched zero requests and no terminal tool-effect
receipt was produced. The current debug ELF hash is retained as build evidence
only; it does not replace the release ELF hash pinned in `hepta-profile.json`.
`strace` is independently blocked by the same ptrace policy. This evidence is
in `tests/workloads/linux/baselines/hepta-cloud-probe-20261016.json` and is a
host composition/provider blocker, not a kernel ABI result.

## Errata and current-denominator update (2026-10-17)

The earlier sections retain their original dated evidence snapshots. The
current A04 denominator and host status supersede the older count strings in
those snapshots: the reviewed Tokio `Cargo.lock` is now present and the
locked release build succeeded, while its runtime remains blocked by managed
host pathname AF_UNIX `EPERM`; the authoritative Linux reference therefore
remains 31/32 (31 pass, Tokio `not_run`). The current rootfs/chroot profile
executes 28 C ELF cases (not 24), and the current restricted-host regression
runs 87 tests with six explicit policy skips under both normal Python and
`python3 -O`. Earlier 64/64, 76/76 and 86/86 counts describe prior snapshots,
not current coverage. No guest compatibility or Hepta tool-effect claim is
changed by this documentation correction.

## QEMU/SeaBIOS cloud recheck (2026-10-17)

The QEMU boot prerequisite is now closed for this cloud image. A temporary,
non-system extraction supplied QEMU 8.2.2 and the fixed SeaBIOS image; their
bytes match the accepted A01 hashes. With TCG and no host disk or network, the
pinned A01 kernel/initramfs booted and exited 33 with the expected SeaBIOS,
kernel, initramfs and reboot markers. The serial hash and command are fixed in
`tests/workloads/linux/baselines/qemu-cloud-reprobe-20261017.json`.

The A04 workload replay is still not qualified: the exact Debian13 rootfs and
the four manifest-pinned ELF bytes are not present in this cloud workspace.
Ubuntu-built replacement ELFs must not be substituted for the pinned inputs.


## First real Asterinas ELF probe (2026-10-17)

With a temporary statically linked probe archive injected into a fresh A01
initramfs, QEMU TCG executed 13 Linux ABI probes on the pinned kernel. Eleven
completed with the expected zero result, including process exit, futex/thread,
epoll, locks, mmap, signals, pathname AF_UNIX peer credentials and robust
mutex owner death. Two failures are now concrete guest kernel gaps: the
`scm_rights` probe reported `unsupported flags: MSG_CMSG_CLOEXEC` and timed out
with exit 143; `fd_limit` exited 20 after its EMFILE/rlimit assertion failed.
The complete input hashes, serial and per-case results are in
`tests/workloads/linux/baselines/guest-qemu-probe-20261017.json`.

These are the first A04 guest observations. They are actionable A05/A06 kernel
interface work, not cloud policy failures. The full four pinned Debian13 ELF
replay remains pending because its exact rootfs and ELF bytes are not present
in this cloud workspace.


The focused `fd_limit` rerun confirms the kernel-side cause: the guest changed
RLIMIT_NOFILE to soft=32/hard=4096 successfully, but 256 `open()` calls all
succeeded with errno=0 instead of returning EMFILE. This is an A05
RLIMIT_NOFILE enforcement gap, not a cloud permission failure.


The focused SCM_RIGHTS rerun further isolates the second gap: `recvmsg` with
`MSG_CMSG_CLOEXEC` returned successfully, but the received descriptor had
`FD_CLOEXEC=0` and the guest serial reported the flag as unsupported. A05 must
apply the requested close-on-exec flag to received SCM_RIGHTS descriptors.


A focused guest probe also passed AF_UNIX abstract bind/connect/accept/read and
child exit. This separates the cloud host's AF_UNIX creation denial from the
guest kernel: pathname and abstract Unix sockets work in the guest; only the
SCM_RIGHTS close-on-exec flag behavior remains an A05 gap.
