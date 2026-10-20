# Native OSDK integration profile

This runner executes all 22 real tests from the pinned OSDK integration suite.
These tests exercise OSDK tooling and small OSTD example kernels. They do not
establish acceptance of the complete Asterinas kernel, HOS ABI, Linux userspace,
VMX virtualization, or desktop workloads.

```sh
python3 -I support/build/osdk-integration/run.py \
  --output "$PWD/support/build/out/osdk-integration-new"
```

Private host tools can select their firmware and QEMU data without installing
them under `/usr`:

```sh
A01_QEMU_BIOS="/absolute/private tools/share/seabios/bios-256k.bin" \
A01_QEMU_DATA_DIR="/absolute/private tools/share/qemu" \
python3 -I support/build/osdk-integration/run.py \
  --output "$PWD/support/build/out/osdk-integration-private-new"
```

The recorder first applies its existing fixed guest profile, then reuses the
normal kernel recorder's `select_bios` and `select_data_directory` functions.
An explicitly present empty/relative/missing value or wrong file type fails
before QEMU's version probe or execution; no fallback to the default is used.
An explicit data directory cannot be combined with any incoming `-L`, including
duplicate occurrences. With both variables unset, the fixed SeaBIOS default
`/usr/share/seabios/bios-256k.bin` and original data lookup remain unchanged.
Paths containing spaces remain single argv values. Each guest retains its
original OSDK arguments, fixed arguments before host selection, both selection
records, the selected BIOS artifact hash, and the exact shared selector source
hash. The runner's source-input table includes that shared dependency. These
host-path selections do not choose TCP, enable coverage, relax device/control
validation or change the original upstream test assertions.

The default profile is `osdk-native-unix-gdb-capture-v3`. It keeps the original
UNIX debugger and monitor transports and deterministically adds a private UNIX
GDB helper only to coverage collection. It is selected before execution, not
as a retry after a failed profile. The original guest, its coverage announcement,
ISA debug-exit device and test assertions remain unchanged.

| Invocation | Profile | Coverage collection |
| --- | --- | --- |
| Default | `osdk-native-unix-gdb-capture-v3` | UNIX GDB stop before original poweroff; raw QEMU exit 33 |
| `--upstream-coverage-lifecycle` | `osdk-native-unix-v1` | Original unassisted UNIX monitor lifecycle |
| `--local-tcp` | `osdk-native-local-tcp-v1` | Original monitor lifecycle over explicit TCP |
| `--local-tcp --coverage-gdb` | `osdk-native-local-tcp-gdb-capture-v2` | Explicit TCP GDB stop before original poweroff; raw QEMU exit 33 |

The legacy flag is exclusive with both TCP flags. It retains a reproducible
entry for the unassisted upstream lifecycle, including its actual failure when
ISA debug-exit destroys the guest before the subsequent monitor dump:

```sh
python3 -I support/build/osdk-integration/run.py --upstream-coverage-lifecycle \
  --case commands::run::coverage_feature::basic_coverage \
  --output "$PWD/support/build/out/osdk-upstream-coverage-new"
```

The default A01 collection entry is repaired by a host helper; this does not
claim that the unmodified upstream monitor-after-exit lifecycle has been fixed.
Historical v1 failures remain failed records, and results from different
profiles must not be combined into a passing full-matrix result.

The explicit local TCP profile remains available:

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
Results from all profiles must be reported separately. The previous default
20/22 result and the subsequent complete 21/22 UNIX run with missing coverage
remain historical evidence. All profiles use the same persistent workspace lock to serialize shared Cargo caches, while each
run keeps its own normalized dependency locks and scratch roots.

The initial TCP profile deliberately retains ISA debug-exit. A working monitor
connection alone does not establish coverage: ISA debug-exit can destroy guest
memory before the monitor dumps it. Such an exit remains a real failed coverage
case. No alternate shutdown lifecycle or OSTD change is hidden in this profile.
v1 TCP coverage requires OSDK exit 0 and raw QEMU exit 0 after a real monitor dump/quit, a new raw
profile whose size exactly matches this guest's coverage announcement, matching
serial and kernel hashes, and valid nonzero pinned LLVM coverage counts.

The default UNIX capture owns a listener in a new `0700` directory under the
current case's temporary root. The path must be absolute, short enough for
AF_UNIX and safe as one GDB target argument. The recorder binds once, keeps the
listener until QEMU inherits its descriptor, and closes the parent copy after
spawn. It records the private directory and socket pathname identities
separately from the socket descriptor identity. QEMU receives the exact inherited
listener; no bind-close-rebind gap or TCP control endpoint is introduced.

The capture helper and its GDB script verify the same pathname/directory
identities before connection, after connection and after detach. A changed path
fails, and cleanup refuses to unlink a replacement. These checks establish the
owned private-directory lifecycle; they are not an atomic connect-to-inode
primitive against malicious code with the same UID. `SO_PEERCRED` is not treated
as the QEMU PID: a listener created before inheritance retains its creator's
credentials, as exercised by a real Python child fixture in the host tests.

The independently selected TCP GDB capture profile preserves the same original
ISA poweroff lifecycle:

```sh
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb \
  --output "$PWD/support/build/out/osdk-gdb-capture-new"
```

This selects `osdk-native-local-tcp-gdb-capture-v2`. Like UNIX v3, only the coverage
case gains a paused GDB server. The recorder allocates and owns its loopback listener and
passes the descriptor to QEMU. `capture.py` inspects the original ELF64 x86_64
symbol artifact with real `nm`, sets a GDB hardware breakpoint at the exact
`ostd::arch::power::try_poweroff` address, continues, and checks the actual PC.
At this point the unmodified OSTD has completed its coverage announcement. GDB
reads that same live serial stream and uses `monitor memsave` to a fresh absolute
path; the dump must exactly match the announced size. It then removes the
breakpoint and detaches so the original guest can execute ISA debug-exit.

Both capture profiles accept coverage only with actual QEMU exit 33, actual OSDK
and capture/GDB exit 0, a successful finalized capture sidecar, the exact breakpoint PC, fresh
raw bytes, and the pinned LLVM nonzero-count checks. The sidecar binds the
original symbol ELF, wrapped boot ELF, paused serial prefix, final serial log,
raw profile and announcement. Missing, altered, failed or timed-out capture
evidence is rejected. UNIX v3 also binds the endpoint identity receipt to the
actual recorded QEMU PID, the actual `-kernel` argument and read-only loaded
ELF bytes, the per-guest frozen original symbol ELF, and input verification
before and after execution. A guest failure exit is never remapped to 33.
No OSTD source, poweroff handler or production OSDK lifecycle is changed;
legacy UNIX v1 and pure-TCP v1 results remain separate.
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
Every case receives a new exclusive `case-NN/target` as `CARGO_TARGET_DIR`.
Generated `osdk/` base crates and bundles stay private to that case, preventing
same-name examples such as the two `myos` projects from sharing generated
workspace paths. Only `debug`, `release` and `x86_64-unknown-none` are explicit
symlinks to verified directories in the isolated compilation cache. No prior
`osdk/` tree is linked, copied or removed. Existing target/profile entries or
unexpected cache types fail without replacement; partial owned directories
remain available for diagnosis. Cache types and identities are checked before
harness normalization or any Cargo build. `target-profile.json` and the case result bind
the target/cache identities and each shared artifact directory. The persistent
integration lock still serializes these shared compiled artifacts, and coverage
symbols use the current case target. This is cache isolation for the observed
same-name workspace hazard; it neither attributes the historical writer nor
protects against a privileged process replacing paths during execution.
The runner acquires its lock before creating the requested output directory.
All commands have an owned session: timeout, SIGINT and SIGTERM stop that
original group while its direct leader is still unreaped, then reap the leader
before releasing the lock. Descendant exit after SIGKILL is asynchronous;
descendants that leave the group are outside this contract. No numeric group
signal is sent after leader reap, and ECHILD disarms such signalling.

The production OSDK binary is built directly from `kernel/asterinas/osdk` with
its explicitly approved downstream `Cargo.lock` and `--locked`. Its original
upstream lock and the exact host-only derivation remain separately verified. A separate test-only package copies
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

The test package's lock is normalized offline from the approved downstream OSDK
lock (SHA256 `1011e26a7070708d37f2062a84b309d2c228c177a9e5434bfe63917203c17a18`).
For generated kernel/library workspaces, the runner extracts `Cargo.lock` from
Git commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b` into the new run's
`upstream-root.Cargo.lock`. The SHA256 must be
`6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316`;
`root-lock-seed.json` records its Git blob and bytes. The working root lock
contains downstream dependencies and cannot serve as this upstream seed.
A missing Git object fails before Cargo; a fresh checkout can obtain the exact
object with `git fetch https://github.com/asterinas/asterinas.git c4b7ed575b7b32773475b194d2ad41fb6d03765b`.
The Cargo shim checks the seed again on every request, normalizes that original
root lock offline, verifies every external package's name, version,
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
Before probing or starting QEMU, the recorder copies the kernel, BIOS and any
initramfs into a new private `guest-*/artifacts/` directory through the ordinary
recorder's stable-file-descriptor capture helper. These exclusive copies are
read-only and are the actual QEMU input paths. The original requested and
selected arguments remain recorded; `artifact_sources` identifies the source
bytes and stat, while `artifact_snapshots` identifies each saved copy. The
recorder verifies every copy's size, SHA256 and stat before QEMU and after the
guest finishes. Coverage also saves the original ELF64 little-endian EM62
symbol file, passes that private copy to the real GDB capture, and keeps the
strict sidecar binding to those bytes. Later builds can replace generated
source paths without changing an earlier guest's retained inputs.
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
generated example source, Cargo targets, tool binaries and the guest artifact
ELFs. Retain `guest-*/artifacts/` separately when preserving the actual boot and
coverage symbol bytes along with an archive.
The source must be a nonempty directory and the destination must be new and
outside it. Reads use the opened root directory and no-follow file descriptors;
selected symlinks, hardlinks, special files, identity changes and index-name
collisions fail closed. Limits are 128 MiB per selected file and 1 GiB total.
Output directories are opened without following links. Files and both indexes
are created exclusively relative to those pinned directory descriptors; index
digests come from the exact written payloads. Completion verifies directory and
file identities before removing `.archive-incomplete`. A failed new archive
retains that marker and its partial evidence for diagnosis; it never recursively
deletes a destination pathname. An existing destination remains untouched.
The destination parent must be trusted; these checks do not establish an atomic
snapshot of an entire concurrently changing run or a sandbox against same-user
writers. A directory moved during output can retain partial custody at its new
location, and the original destination may have been replaced by another writer.

Pure profile checks (no VM):

```sh
python3 -I -m unittest discover -s support/build/osdk-integration -p 'test*.py' -v
```
