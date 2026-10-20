# A01: current main source build, real boot and kernel regressions

**The full derived Asterinas kernel was freshly built and booted from producer
`b39e154ae5a1e9853f57e23f9bee84712ee8ef7e`.** This run installed the fixed Rust
toolchain and native dependencies, built an initially absent kernel target,
booted the actual ELF with a small initramfs, and ran both complete kernel-mode
test suites. The first boot command was refused before QEMU because an unexpected
manifest had appeared; the preserved-file retry succeeded. This report keeps
both outcomes and their original source identities.

Branch: `agents/A01-asterinas-boot`. [PR #22](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22)
targets `main`. The later evidence commit publishes these records; it is not
claimed as a separately built kernel producer.

## 1. Source identity and ownership

| Input | Verified value |
| --- | --- |
| Actual main used to create the local A01 branch | `01225ab0a20a9f25dd8313a7fad7652dd9154e30` |
| Ordinary merge / native producer | `b39e154ae5a1e9853f57e23f9bee84712ee8ef7e` |
| Preserved prior A01 second parent | `7b28d9cfe9556835c4bf1ac5d1c1ec078c449b77` |
| Producer project tree | `80ceaa07562dd359572afdc6bfad473aa20d7271` |
| Derived kernel tree | `065a20ff147bf1541acbdfd996338ab0267fbfc6` |
| Fixed complete upstream | Asterinas v0.19.0, `c4b7ed575b7b32773475b194d2ad41fb6d03765b` |
| Fixed upstream tree | `96605cf64aeae2d34f29b97e85eff9315fe10a8e` |
| Single kernel source root | `kernel/asterinas/` |
| Toolchain / target | `nightly-2026-07-21` / `x86_64-unknown-none` |
| Original kernel Cargo.lock SHA256 | `6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316` |
| Rust toolchain file SHA256 | `b2508d8c9cd57258fad2fc77737e07172846161f6a7dd726cbd8e974de69c6f7` |

The official upstream commit object was fetched and checked against its tree.
The original import subtree is exactly that upstream tree. All 2,938 original
upstream files remain; 2,907 are unchanged, 31 have existing derivation changes,
and five derived additions bring the current kernel directory to 2,943 files.
Upstream licenses, attribution and documentation are retained. The project root
README remains **zero bytes**. The approved existing host OSDK manifest and lock
remain distinct from the unchanged upstream kernel lock; no kernel/toolchain
upgrade or alternate implementation was introduced.

The complete kernel/core, OSTD and external ABI owner ranges are identical to
main012. In particular, main's six changed owner files since the preceding native
producer are preserved, including the zombie final-charge lease fix and new
regressions. A01 has not edited A05/A06 implementation files.

There are 3,012 selected build/source input records. All execution captures and
the independent before/after audit match the producer's bytes, file modes and
Git blobs. [source-summary.json](source-summary.json) distinguishes the two
audit serialization formats and preserves every complete-worktree status.
[source-records.tar.xz](source-records.tar.xz) contains acquisition commands,
official fetch receipts, source publication identity, both audit scripts and
every original before/after manifest. The independent audit passed 15 checks
before and after native execution. Some observations contain the untracked
temporary manifest; selected tracked inputs remained unchanged throughout.

## 2. Dependencies actually installed in this run

The prior private runtime had been pruned. This run restored a new isolated
prefix at `/workspace/scratch/d7da9e7650f0/a01-current-runtime`, with actual
installation receipts from 2026-10-18 **08:34:02–08:36:06 UTC**. Historical
bootstrap scripts were recovered from the published repository, then executed
again; old execution logs were not relabeled as new installation evidence.

| Dependency | Actual result |
| --- | --- |
| Rust | nightly-2026-07-21; rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48` |
| Cargo | 1.99.0-nightly; commit `3efb1f477e99b42974b982d939fd100303cdf7db` |
| Rust additions | rust-src, rustc-dev, LLVM tools, rustfmt, clippy and x86_64-unknown-none target |
| cargo-binutils | 0.4.0 installed with `--locked`; rust-strip uses LLVM 22.1.8 |
| Native packages | 57 private extractions from Ubuntu snapshot `20260828T000000Z`; 57/57 package SHA256 checks and 4/4 InRelease signature checks pass |
| QEMU | 8.2.2, package `1:8.2.2+ds-0ubuntu1.18` |
| Firmware | SeaBIOS 1.16.3-2; explicit packaged file used by QEMU |
| Native compiler/linker | clang/lld 18.1.3 |
| Initramfs userspace | static BusyBox `1:1.36.1-6ubuntu3.1` plus the maintained init and upstream boot_hello script |
| vDSO | fixed commit `8af571775a3d3a1df3e84fc9709b9d6b160c771a`, tree `8e0a300d78c2a020ccc79f1253bc27a8301416e6` |
| Dependency checks | 17/17 pass |

See [runtime-summary.json](runtime-summary.json) and
[runtime-current.tar.gz](runtime-current.tar.gz) for original installation
commands, logs, snapshot/signature material, Rust manifest, package inventories,
tool/library hashes and licenses. The initial restricted-network failure is
retained separately from the successful installation. Native packages were
downloaded and extracted privately; no host package installation was performed.
Docker, Nix and KVM are unavailable in this environment. The actual route uses
native tools and QEMU TCG, without a NixOS ISO. Some recorded host tools and
libraries are still used, so this is not a complete immutable host lock.

## 3. Build and startup entry points

From the repository root in the prepared environment, the maintained commands
are:

```sh
source /workspace/scratch/d7da9e7650f0/a01-current-runtime/env.sh
export CARGO_BUILD_JOBS=2
export A01_SMP=1
export A01_QEMU_TIMEOUT=300
export A01_KTEST_TIMEOUT=300
unset CARGO_ENCODED_RUSTFLAGS

support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -B -I support/build/ktest/run.py --output /absolute/new/ktest-output
```

The actual run selected separate, initially absent output directories using
`A01_RUN_DIR`. [kernel/command.sh](kernel/command.sh) and
[boot/command.sh](boot/command.sh) are the exact executed make commands. The
wrapper installs the locked, source-bound OSDK in each run's private prefix and
invokes upstream **`make kernel` / `make run_kernel`**, with `minimal.mk`
substituting the small initramfs prerequisite. It retains upstream source and
the existing temporary-manifest ownership guard.

For another disposable Ubuntu 24.04 x86_64 developer host, the standard setup
entry is `support/build/prepare-host.sh --apt`; without `--apt` it prepares the
fixed Rust/vDSO/binutils inputs assuming native packages already exist. The
exact private-prefix installation used here is archived in the runtime scripts
and receipts; it is separate from that host-install setup option. Any new run
must use a new output path and preserve an already existing public manifest
before resolving it. The wrapper refuses to replace that file.

## 4. Actual build and QEMU evidence

| Stage | Actual result |
| --- | --- |
| Fresh `make kernel` | 08:49:31.749120–08:52:49.014296 UTC; exit 0; 197.265 seconds; 284 compilation lines; target was absent before launch |
| First `make run_kernel` wrapper attempt | 08:53:39 UTC; exit 1 before make/QEMU because the public manifest already existed; no guest launched |
| Retry `make run_kernel` | 08:58:30.833090–08:58:34.030317 UTC; make/driver 0; actual QEMU raw 33; no timeout; guest duration 0.969 seconds |
| Kernel artifact | Complete ELF, 8,283,136 bytes; frozen after first build and byte-identical to the actual loaded private copy |
| Complete boot serial | 72,194 bytes; all five required markers exactly once |

The retry uses the target just built by the 197-second build. This is one fresh
target build followed by its boot, not two cold builds, and it does not claim an
empty Cargo registry/download cache. The original build warnings remain in the
logs; no kernel Clippy qualification is asserted.

```text
kernel ELF SHA256:
6518b6472efbc599498b71550ef9761f6f20e74814db0c9a81bff101ab036e55

initramfs SHA256 (1,107,990 bytes):
86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3

SeaBIOS SHA256 (262,144 bytes):
1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735

full boot serial SHA256:
0efe9f6156db9aa42574e35ab919c1a3e0aeea30b6a74ff0397e50c362a4ae1e
```

The exact executable, working directory, full kernel command line and complete
device arguments are preserved in [boot/qemu.json](boot/qemu.json), including
the actual `argv` and shell command. The profile is x86_64, q35, TCG, CPU `max`,
**1 vCPU, 512 MiB**, explicit SeaBIOS and QEMU ROM directory, no default devices,
no network or data disk, serial output and `isa-debug-exit`. It boots this
project's Rust kernel and its initramfs. No host Linux boot or installer is used
as acceptance evidence.

[boot/serial.log](boot/serial.log) retains the complete raw bytes, including:

```text
OSTD initialized. Preparing components.
TRILLIONNIUM_A01_INIT_BEGIN
TRILLIONNIUM_A01_CPU_COUNT=1
Successfully booted.
TRILLIONNIUM_A01_BOOT_OK
```

[guest-artifacts.tar.xz](guest-artifacts.tar.xz) holds the complete loaded ELF,
initramfs, firmware, and both complete test ELFs. Its internal manifest and
[artifact-bindings.json](artifact-bindings.json) map archive members to their
original recorded paths and hashes. The boot recorder used read-only private
snapshots and verified them before/after the guest. The test runner used its
recorded target paths; their archived bytes were stable-FD checked after the
tests and matched the original QEMU hashes. The report does not retroactively
claim that the ktest recorder used private snapshots.

## 5. Regression results and scope

| Suite on b39e154a | Reported pass | Soft skip | Exercised-pass lower bound | Failed / filtered |
| --- | ---: | ---: | ---: | ---: |
| OSTD, full unfiltered crate | 221 | 3 | 218 | 0 / 0 |
| aster-core, full unfiltered crate | 160 | 0 | 160 | 0 / 0 |
| Combined real kernel suites | **381** | **3** | **378** | **0 / 0** |

The two actual test guests each returned raw QEMU **33**. The OSTD soft skips
explicitly report unavailable VMX/VMX-EPT invalidation capability. The core log
includes all six new real Process/Task final-charge object regressions and the
odd/even period endpoint regression from main. These objects are not scheduled
through a userspace exit syscall, so this does not prove complete scheduler
exit/reap/migration timing or general SMP.

[ktest/result.json](ktest/result.json),
[OSTD serial](ktest/ostd/guests/guest-001/serial.log),
[core serial](ktest/aster-core/guests/guest-001/serial.log) and each neighboring
`qemu.json` retain actual results. The original fixed test-base locks were used
without regeneration or unlocking; generated lock copies and every Cargo/OSDK
command are in [native-records.tar.xz](native-records.tar.xz).

The current existing host acceptance gate passed **81/81** once per suite:
source inputs 10, boot evidence 29, kernel runner 42. Its 131 selected tracked
inputs and producer identity remain unchanged. The full before/after status
contains the temporary manifest during parallel native compilation; those raw
observations are retained and are not called a continuously clean worktree.
See [host-gate-summary.json](host-gate-summary.json) and
[host-gate.tar.gz](host-gate.tar.gz). These host fixture tests are separate from
the three real QEMU guests. Previous ABI, debug, coverage and OSDK integration
matrices retain their historical producer scope and were not rerun here.

## 6. Preserved failure and unresolved manifest writer

The kernel wrapper's successful cleanup reported removing its owned inode
1716473. A subsequent clean source observation was recorded at 08:52:49.443853
UTC. A different public entry, inode **1720253**, was later observed; its ctime
was 08:52:55.137552 UTC. The first boot wrapper correctly refused it before
creating a QEMU guest. [The original error](failures/prelaunch-failure/run_kernel-driver.log),
[observation](failures/prelaunch-failure/observation.json), raw bytes and
[quarantine receipt](failures/prelaunch-failure/quarantine.json) remain intact.

Under the shared native workspace lock, the observed regular file was opened
without following symlinks, checked by stable FD and hash, and reversibly renamed
into a unique custody directory. It was not unlinked or overwritten; guards
were unchanged. The new retry directory then completed the real boot.

After the test suites, another entry, inode **1718453**, was observed with ctime
08:58:41.186090 UTC. Both entries contain the same 1,019-byte minimal manifest
and retain its earlier mtime. The ktest runner does not publish this public
manifest as part of its design. No syscall trace identifies a responsible
writer; inode, timestamps and matching bytes cannot establish authorship.
[The second observation](failures/post-ktest-manifest/observation.json), raw bytes,
its reversible quarantine and the subsequent clean source capture are retained.
The independent after-audit at 09:04:15 UTC confirmed that the public entry was
absent and all selected tracked sources still matched b39e154a.

This environmental issue can block a future invocation's preflight and remains
unresolved. It did not invalidate the recorded ELF/serial hashes or the three
successful guest runs. No claim of continuously clean public paths or repaired
writer behavior is made. Both exact execution/quarantine scripts are archived.

## 7. A00 / A05 / A06 handoff and remaining qualification

[HANDOFF.md](HANDOFF.md) gives exact Process, exec/init, ioctl, control-device,
common scheduler, CPU controller and cgroup lease/deletion interfaces with their
existing ownership. A01 supplies the complete source and tested build/boot
entries. A05/A06 can begin from main's preserved process and scheduler objects.

Only `QueryAbi` is currently implemented on `/dev/hepta-control`;
`ReadUsage`, `InstallBudget`, `QueryDelivery` and `RetireThrough` remain
`EOPNOTSUPP`. Native authority grants/revocation, durable K↔D recovery,
full scheduler lifecycle/SMP acceptance and G1/G2 remain owner work. R8 already
contains Linux-host trusted ObjectiveStart admission and Rust Shell projection;
that is distinct from native HOS2 effect enforcement. No full device/userspace,
bare-metal, VMX/EPT or cross-host reproducibility qualification is asserted.

## Archive integrity and offline review

```sh
cd support/build/evidence/2026-10-18-main012-current
sha256sum -c SHA256SUMS
mkdir /absolute/new/a01-review
tar -xJf native-records.tar.xz -C /absolute/new/a01-review
tar -xJf source-records.tar.xz -C /absolute/new/a01-review
tar -xJf guest-artifacts.tar.xz -C /absolute/new/a01-review
```

The three xz archives have internal member hashes and all were decoded and
checked against the original bytes. Runtime and host archives retain their
independently verified manifests. Raw logs and source receipts are not rewritten
to replace their original paths or source SHA. The plain serial/QEMU/result
files here are byte-identical review copies. [archive-index.json](archive-index.json)
records archive hashes and scope; [report.json](report.json) is the machine-readable
acceptance summary. Evidence publication changes only A01-owned report/history
files and this new evidence directory; the native producer remains b39e154a.
[publication-source-bridge.json](publication-source-bridge.json) verifies that
3,010 of the same 3,012 selected inputs are unchanged; the two differences are
this build README and upstream-lock reporting/history fields. All 118 fixed-pin
checks produce the identical receipt recorded during the native build.
The final checksum receipt is `review/checksum-verification.json`. It binds the
checksum manifest and raw verification output; the manifest excludes itself
and that receipt to avoid a circular hash. Git records both files.
