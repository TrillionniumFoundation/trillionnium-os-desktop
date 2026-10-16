# Native OSDK integration profile

This runner executes all 22 real tests from the pinned OSDK integration suite.
These tests exercise OSDK tooling and small OSTD example kernels. They do not
establish acceptance of the complete Asterinas kernel, HOS ABI, Linux userspace,
VMX virtualization, or desktop workloads.

```sh
python3 -I support/build/osdk-integration/run.py \
  --output "$PWD/support/build/out/osdk-integration-new"
```

The default profile is `osdk-native-unix-v1`. Its original UNIX GDB and monitor
transports remain separate from the explicit local TCP profile:

```sh
python3 -I support/build/osdk-integration/run.py --local-tcp \
  --output "$PWD/support/build/out/osdk-integration-local-tcp-new"
```

`--local-tcp` selects `osdk-native-local-tcp-v1`; it is never selected
automatically after an error. The isolated basic-debug test uses a dynamic
`127.0.0.1` GDB address. The recorder owns that listener through QEMU spawn and
hands its descriptor to QEMU, then creates the current case's readiness marker.
Both basic GDB and VS Code clients wait for that marker before attaching.
An occupied port fails without an alternate endpoint. The explicit monitor
transport uses the production `--qemu-monitor-transport=tcp` interface: OSDK
creates a private connected TCP pair, rejects an unrelated client arriving
first, and closes the listener before spawning QEMU. Only QEMU's connected
endpoint is inherited on a descriptor numbered at least 64; the parent keeps
CLOEXEC set and closes its copy after spawn. The recorder verifies the reserved
chardev, connected loopback endpoints and exact fields, passes that descriptor
to the actual QEMU child, and records its PID. This avoids trusting the first
local process that connects; it is not protection against process injection or
privileged access to another process's descriptors. No wildcard or public
control address is accepted. The exact transport/readiness test patch is
retained alongside the other harness adaptations; debugger and guest assertions
remain unchanged.

Each output records its profile on the environment, cases and guest records.
Results from the two profiles must be reported separately. The previous default
20/22 result and its UNIX failures remain historical evidence. Both profiles use
the same persistent workspace lock to serialize shared Cargo caches, while each
run keeps its own normalized dependency locks and scratch roots.

The initial TCP profile deliberately retains ISA debug-exit. A working monitor
connection alone does not establish coverage: ISA debug-exit can destroy guest
memory before the monitor dumps it. Such an exit remains a real failed coverage
case. No alternate shutdown lifecycle or OSTD change is hidden in this profile.
v1 TCP coverage requires OSDK exit 0 and raw QEMU exit 0 after a real monitor dump/quit, a new raw
profile whose size exactly matches this guest's coverage announcement, matching
serial and kernel hashes, and valid nonzero pinned LLVM coverage counts.

The independently selected GDB capture profile preserves the original ISA
poweroff lifecycle:

```sh
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb \
  --output "$PWD/support/build/out/osdk-gdb-capture-new"
```

This selects `osdk-native-local-tcp-gdb-capture-v2`. Only the coverage case gains
a paused GDB server. The recorder allocates and owns its loopback listener and
passes the descriptor to QEMU. `capture.py` inspects the original ELF64 x86_64
symbol artifact with real `nm`, sets a GDB hardware breakpoint at the exact
`ostd::arch::power::try_poweroff` address, continues, and checks the actual PC.
At this point the unmodified OSTD has completed its coverage announcement. GDB
reads that same live serial stream and uses `monitor memsave` to a fresh absolute
path; the dump must exactly match the announced size. It then removes the
breakpoint and detaches so the original guest can execute ISA debug-exit.

v2 accepts coverage only with actual QEMU exit 33, actual OSDK and capture/GDB
exit 0, a successful finalized capture sidecar, the exact breakpoint PC, fresh
raw bytes, and the pinned LLVM nonzero-count checks. The sidecar binds the
original symbol ELF, wrapped boot ELF, paused serial prefix, final serial log,
raw profile and announcement. Missing, altered, failed or timed-out capture
evidence is rejected. No OSTD source, poweroff handler or production OSDK
lifecycle is changed; the default Unix and pure-TCP v1 results remain separate.
This is explicitly coverage collected under a debugger, not a claim that the
unassisted upstream coverage transport/lifecycle passes.

The output directory must be new. The runner uses an independent Cargo target
directory and a persistent integration runner lock, so it can run alongside a
complete-kernel build. It starts the live GDB and VS Code cases first, then runs
the other 20 cases sequentially. `--case EXACT_NAME` can select individual cases;
the original list is retained in `upstream-test-list.txt`. Each case has a
900-second bound, and each guest has a 300-second bound. Native QEMU, SeaBIOS,
GCC, GDB and the pinned Rust toolchain must be available. `--target-dir` can
reuse a previous runner's independent Cargo cache after validating its origin.
The runner acquires its lock before creating the requested output directory.
All commands have an owned session: timeout, SIGINT and SIGTERM stop that
original group while its direct leader is still unreaped, then reap the leader
before releasing the lock. Descendant exit after SIGKILL is asynchronous;
descendants that leave the group are outside this contract. No numeric group
signal is sent after leader reap, and ECHILD disarms such signalling.

The production OSDK binary is built directly from `kernel/asterinas/osdk` with
its original `Cargo.lock` and `--locked`. A separate test-only package copies
the upstream tests into the run directory. Its three harness substitutions are:

1. Fixed `/tmp` string prefixes point to a newly created short `/tmp/a01oi-*`
   root. The short path preserves Linux UNIX socket path limits. Its device and
   inode are recorded; only that owned root can be removed after the run.
2. The local OSTD helper's manifest anchor points to the original OSDK directory.
3. The kernel100 example's added `align_ext = "0.1.0"` dependency points to
   `kernel/asterinas/ostd/libs/align_ext`, still version 0.1.0. The fixed root lock
   contains that path identity, not the registry copy. This preserves a single
   fixed source implementation without permitting a new external identity.

The exact patch and original/adapted source hashes are retained. Assertions are
unchanged. The helper's original relative toolchain include is supported by an
exact copy of the pinned toolchain file. Existing host `/tmp/myos`,
`/tmp/myworkspace`, and similar paths are untouched.

The test package's lock is normalized offline from the original OSDK lock.
For generated kernel/library workspaces, the Cargo shim normalizes the original
root Asterinas lock offline, verifies every external package's name, version,
source and checksum against that seed, then executes the real Cargo command
with `--locked --offline`. It only writes locks under the run's generated
directories. Every normalization, lock and command is recorded. A dependency
outside the pinned seed is a failure, including a newer cached version.
OSDK's new-project template uses the unqualified `nightly` channel and its build
command removes `RUSTUP_TOOLCHAIN`. The Cargo adapter therefore restores the
fixed channel and absolute `RUSTC`/`RUSTDOC` paths before every real subprocess,
and disables automatic toolchain installation. The runner checks the compiler
commit; command records include actual executable paths, versions and hashes.
The `metadata --no-deps` path only reads manifests before upstream adds local
OSTD. Actual dependency normalization always restarts from the complete seed.
The adapter consumes Cargo's global option values and fixed toolchain selector
before classifying commands, expands built-in short aliases, and inserts the
enforced flags before any program/test `--` separator. This finite profile
rejects custom commands, external `clippy`, configuration overrides, directory
changes and redirected lockfiles; it is not a general-purpose Cargo wrapper or
an execution sandbox. Manifest-only `new/init` and required read-only queries
remain available.

The OSDK adapter changes only `build/run/test` boot options to direct multiboot
and the recording QEMU executable. The QEMU profile fixes q35, TCG, CPU `max`,
one vCPU, 512 MiB and explicit SeaBIOS. It preserves real GDB sockets, wait-for-
client, monitor sockets, coverage's no-shutdown behavior and original log path.
Network and data disks are rejected. Firmware pflash is replaced with SeaBIOS.
Coverage can legitimately exit through monitor quit with raw QEMU status 0;
other examples commonly exit with 33. Raw statuses are retained without being
replaced by a blanket success status. The hypervisor example's upstream VMX-
unavailable fallback is reported as a soft skip, never as a VMX success.

Each case retains the upstream harness output, exact commands, OSDK adapter
requests, Cargo identities/locks, and complete guest serial logs with hashes.
Top-level `result.json` reports passed, failed, blocked and soft skips separately.
An existing generated path blocks its case; cleanup only removes paths that
were absent before that exact case. Failed commands and timeouts remain in the
output for diagnosis.

The current host rejects AF_UNIX socket creation with EPERM. The original UNIX
GDB and coverage monitor transports are retained and their failures remain in
the 22-case denominator. A separate TCP VS Code/GDB case can pass on this host;
it does not establish UNIX socket support or usable coverage. Earlier failed
attempts, including a rejected registry `align_ext` identity, remain archived.
Coverage is accepted only with a nonempty saved raw profile, successful pinned
`llvm-profdata merge/show`, nonzero function count and nonzero execution count.

`archive.py SOURCE DESTINATION` saves logs, command/guest records, hashes, the
adaptation patch and locks, with deterministic gzip for large logs. It omits
generated example source, Cargo targets and tool binaries.
The source must be a nonempty directory and the destination must be new and
outside it. Reads use the opened root directory and no-follow file descriptors;
selected symlinks, hardlinks, special files, identity changes and index-name
collisions fail closed. Limits are 128 MiB per selected file and 1 GiB total.
The destination parent must be trusted; per-file checks do not establish an
atomic snapshot of a concurrently changing entire run directory.

Pure profile checks (no VM):

```sh
python3 -I -m unittest discover -s support/build/osdk-integration -p 'test*.py' -v
```
