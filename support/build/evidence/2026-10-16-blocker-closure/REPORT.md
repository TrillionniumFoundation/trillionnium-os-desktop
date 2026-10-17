# A01 cloud blocker closure

This phase used the user-confirmed current project cloud workspace, host
`29609d47ba8e`. It completed two A01 fixes, a complete TCP/GDB OSDK regression,
and a real full-kernel Rust-entry debug boot. **All project blockers are not
closed.** The remaining hardware, owner integration and reproducibility work
is recorded explicitly below.

The upstream remains Asterinas v0.19.0 commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, toolchain
`nightly-2026-07-21`. The only kernel root is `kernel/asterinas/`. This phase
did not change any tracked file under that root, A02 source, A05/A06 core,
the root README, or another agent branch.

## Changes and actual results

| Change or execution | Exact result and scope |
| --- | --- |
| Early encoded-flags rejection, published `071dd8edcd2a3cf9b33dbbeab713428317b9b76c`, tree `5268494bc732e2f39b319248ec4a4dc1705d8d75` | Debug and integration reject presence, including an empty value, before output, lock or tools. Final host suites: 16 integration + 12 debug methods, each in ordinary/optimized isolated Python, **56 executions passed**. Eight red assertions and sixteen direct-CLI old/fixed probes are retained separately. |
| Retained QEMU input snapshots, published `31170ffb2ab6d18a85051d426e5d85a83f1b2abf`, tree `3bef60f628add169a08af75a81dac8c26bcca1da` | Capture stable regular-file input FDs into new exclusive private copies; QEMU actually loads those paths. Source metadata and original args remain recorded. Verify snapshots before/after execution and fail on inconsistency. The original checker is unchanged. Final host suites: 23 boot + 3 listener methods, each in both modes, **52 executions passed**. Intermediate44 and red2 are retained separately. |
| Full `osdk-native-local-tcp-gdb-capture-v2` matrix at `071dd8ed...` | **22/22**, zero failed/blocked, eleven actual QEMU raw33 guests. One example explicitly soft-skips VMX. Fixed LLVM parsed 5,696 nonzero function-entry counters; no coverage percentage or default-UNIX acceptance is claimed. Tool session57340 and controller both exit0. |
| Full Asterinas Rust-entry debug at `31170ffb...` | **PASS**, tool session39476/controller/driver/GDB all0, real QEMU raw33. PC `0xffffffff88422f10` and32 live instruction bytes match `__ostd_main` in both original symbol and executed boot ELF; detach followed by complete single-vCPU initramfs markers. All five owned leaders reaped0. A fresh independent live-artifact check also exits0. |
| A02 exact-base candidate, `eef96afd4c3fcdc5bcdc2b8ba00260e1fb116b91` | Unmodified strict kernel-nightly Clippy101. Isolated three-test-helper patch: fmt0, **61 host tests passed**, no_std target-check0, strict all-target Clippy0. Library/goldens unchanged. **Pending A00/A02 adoption**, not an owner-branch/main fix. |
| Input/environment verification | Fixed-source checker **118 inputs passed**, installed package list and nine actual tool hashes retained. An observed native environment is not an immutable image or second host. |

The successful full-kernel retry reused the actual DWARF build produced by
the preceding failed debug attempt: **zero new `Compiling` lines**, not an
empty-target rebuild. Both revisions have unchanged complete kernel source.
The previous phase's actual empty-target source build, normal boot and
OSTD/core221/141 reported passes remain bound to their earlier source; they
were not rerun or added to this phase's denominator. Three VMX/EPT soft skips
still leave the earlier exercised lower bound359.

## Actual artifacts and retained failures

| Actual successful debug artifact | Bytes | SHA256 |
| --- | ---: | --- |
| QEMU-loaded boot snapshot | 5,975,720 | `fbe81c0e2deae705d61d77ccaaf604e2bf1ca30e4541de71d263af6ecc62ec1b` |
| Original DWARF symbol ELF | 111,689,912 | `06c320f0799d4f8afcb610046dceae64b3cc9885aa64537bc24ce0219c67eaf3` |
| Small initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| SeaBIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| Complete raw serial | 72,303 | `3363db54a8da156395dbd9995a0dff6bb517c3f259373204f886a485e5363460` |

The first debug attempt failed before QEMU because the controller omitted the
prepared GDB directory from PATH. The second really compiled, hit the entry,
and returned QEMU raw33, but **overall failed**: its recorded kernel pathname
was replaced by historical normal ELF `d90ebc32...` before the strict live
checker. That attempt's complete boot bytes were unavailable when archived;
its actual symbol ELF, failure logs, observed replacement stat/hash and foreign
manifest bytes are retained. Its failed verdict remains unchanged. The new
successful attempt retains the actual three loaded snapshots. Its later
source-path observation also matched; we do not claim a second real writer
replacement occurred during the successful retry.

The first OSDK attempt omitted prepared GDB discovery and was cancelled via
tool Ctrl+C130. Its original controller/QEMU result fields remain null; no
graceful-cleanup claim is made. The second independent output directory holds
the completed22/22 result. An unsuccessful separate pidfd cancellation probe
is not evidence of a delivered signal. The abandoned attempt's original fixed
root is not silently described as cleaned.

## Replay

Use a fresh detached worktree at the published code revision; existing foreign
generated manifests are preserved rather than overwritten. On an ordinary
prepared host, the public entries remain:

```sh
support/build/prepare-host.sh --apt
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -I support/build/debug/run.py --output NEW_DEBUG_DIR
python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb --output NEW_OSDK_DIR
```

`kernel.sh` invokes the upstream developer targets `make kernel` and
`make run_kernel`; the small initramfs replaces the distribution prerequisite.
The fixed guest profile is x86_64/q35/TCG, CPU max, one vCPU,512MiB, explicit
SeaBIOS, no writable disk/network/display, serial logging and isa-debug-exit.
No NixOS ISO was downloaded or booted for acceptance.

The actual cloud retry used these existing prepared paths (not new dependency
installation or an immutable environment claim):

```sh
export CARGO_HOME=/workspace/scratch/ae1a8cf05419/toolchains/cargo
export RUSTUP_HOME=/workspace/scratch/ae1a8cf05419/toolchains/rustup
export RUSTUP_TOOLCHAIN=nightly-2026-07-21
export CARGO_NET_OFFLINE=true CARGO_BUILD_JOBS=2
export VDSO_LIBRARY_DIR=/workspace/scratch/ae1a8cf05419/linux-vdso
export PATH=/workspace/scratch/ae1a8cf05419/a01-host-tools-next-e5ae/root/usr/bin:$CARGO_HOME/bin:$PATH
export LD_LIBRARY_PATH=/workspace/scratch/ae1a8cf05419/a01-host-tools-next-e5ae/root/usr/lib/x86_64-linux-gnu
unset CARGO_ENCODED_RUSTFLAGS
```

Complete actual argv, environment selections, build commands, QEMU commands,
firmware hashes, GDB transcript and unmodified raw serial are in the per-run
archives and member indexes. TCP matrix cache reuse is explicit; its fresh
replay without `--target-dir` starts its own target. The former untracked
manifest in the disposable debug worktree was atomically preserved under its
workspace lock before retry; custody bytes and the no-overwrite move receipt
are retained. The original project's foreign manifest was not modified.

## Remaining owners and closure criteria

The baseline [twelve-item ledger](blockers/README.md) is a read-only snapshot
at `350d98d...`; this phase adds concrete candidate evidence, without changing
its historical snapshot into a claim of adoption.

| Item | Current state / required owner action |
| --- | --- |
| A02 nightly Clippy | [Validated exact-base patch and replay](../../handoffs/a02-nightly-clippy/README.md) ready. A00/A02 must adopt and validate their integration revision. |
| Two original UNIX OSDK cases | Current host `socket(AF_UNIX)` returns EPERM; socketpair success is a different API. TCP22 is the explicit alternative profile, not default-profile closure. Execution-platform owner must supply a permitted host/profile. |
| Three VMX/EPT ktests | No `/dev/kvm`, vmx/svm absent, CapEff0. Requires a supported isolated virtualization environment and explicitly appropriate profile; current TCG success does not exercise these paths. |
| Cross-visible-path / cross-host reproducibility | Absolute component keys and whoami builder identity need coordinated changes; a second identified host and immutable environment are missing. No uncoordinated core/macros change was made. |
| Unknown file writer | Actual artifact replacement and foreign manifest reappearance retained. Snapshot acceptance protects the selected run inputs; writer attribution remains unknown. |
| CI | Exact code-head `31170ffb...` readback reports two checks/two workflow runs queued. Queued checks are not green; A00/runner administrator owns runner availability. |
| A04 compatibility | Historical same-original-ELF28 remains24 matches,2 fdlimit failures,2 SCM_RIGHTS timeouts. No new compatibility fix or rerun is claimed. |
| G1/G2 and G3 | A05 CapSpace/ioctl, A06 final runtime charge/quota, A07 original durable Hepta owner, and later GPU/Android/UI/bare-metal acceptance remain their owners' work. Infrastructure does not establish those runtime features. |

## A00 / A05 / A06 handoff

All following paths are under the one `kernel/asterinas/` root:

| Owner | Concrete interface |
| --- | --- |
| A05 process identity | `kernel/core/src/process/process/mod.rs`: `Process`, `pid`, `start_time`, `tasks`, `run` |
| A05 launch/exec | `kernel/core/src/process/process/init_proc.rs`; `kernel/core/src/process/execve.rs` |
| A05 ioctl dispatch | `kernel/core/src/syscall/ioctl.rs`: `sys_ioctl`; `kernel/core/src/fs/file/file_handle.rs`: `FileLike::ioctl` |
| A06 scheduling | `kernel/core/src/sched/sched_class/mod.rs`; `{stop,real_time,fair,idle}.rs`; `time.rs` |
| Shared framework | `ostd/src/task/scheduler/mod.rs`; A00 coordination required |

A01 changes remain in build support and its lock. A05/A06 can use the published
build/debug entry points and preserved regression evidence, then implement
their owned runtime code without another kernel import. The accepted normal
ELF used by the historical A04 comparison remains identified separately; this
phase's debug ELF does not replace that baseline.

Subdirectories preserve exact source bindings, raw member indexes and
checksums. The root `SHA256SUMS` covers this final phase; publication readback
is recorded after the final evidence commit rather than self-referencing its
unknown future SHA.

The full symbol gzip is stored losslessly as13 ordered chunks in
`debug-failures/artifacts/symbol-storage.json`, with a no-overwrite reassembler;
its decompressed ELF is shared by the failed producer and successful retry.
Run `python3 -I verify-phase.py` from this directory to check current manifests,
every indexed raw archive member and the complete111MB symbol ELF in memory.
This verifies stored evidence; it does not execute a new kernel regression.
