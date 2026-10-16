# A01 daemon cleanup fix and committed kernel replay

The OSDK host daemon lifecycle defect is reproduced and fixed. The pushed code
commit **fb81fec167913827bcddfda15676dc6b26f35965** passes the complete derived
OSDK unit suite **23/23**, the selected non-VM integration subset **13/13**, two
real kernel crate runs and another complete Asterinas initramfs boot.

The earlier original 13/14 unit result remains a recorded failure; it is not
rewritten. This phase both replaces its namespace-dependent observation and
fixes a separately demonstrated production leak.

## Real before/after evidence

The isolated host harness copies the production daemon modules into temporary
workspaces. A private nonce event identifies controlled children; pidfds,
namespace-local kill probes and ongoing heartbeats observe actual lifetime.
The driver returning zero alone is not the acceptance condition.

| Scenario | Old production code | Patched production code |
| --- | --- | --- |
| TERM exits leader; descendant ignores TERM | Descendant alive and heartbeating for 6.206 seconds after supervisor exit | Leader and descendant exited; no later heartbeat |
| Leader exits successfully during startup | Descendant alive and heartbeating for 6.256 seconds after supervisor exit | Leader and descendant exited; no later heartbeat |
| Leader and descendant both ignore TERM | Original 5-second escalation works, useful control | Both exited after escalation |
| Drop without explicit stop | Not repeated on old code | Both exited; no later heartbeat |
| Leader exits with failure during startup | Not repeated on old code | Expected startup error, both exited; no later heartbeat |

The old measurement assertions fail for two cases and pass for the control.
The patched measurement assertions pass all five cases. Old leaks were cleaned
using only pidfds obtained for those controlled descendants. Patched cases
needed no rescue SIGKILL from the probe. Full source provenance, commands,
events, heartbeats, assertions and logs are in `daemon-probes/`.

That harness is a host lifecycle test, not a kernel boot. It does not establish
general atomic PID authentication against unrelated hostile processes. Its
snapshot notes identify the actual compiled file hashes, including the
nonsemantic documentation difference from the final commit. Production sources
are reconstructed from Git plus the recorded comment transform; duplicate
kernel implementations are not imported into this evidence directory.

## Fix and scope

`RunningDaemon::poll_exit` now uses
`waitid(EXITED | NOHANG | NOWAIT)`. Its waitable leader reserves the numeric PID
until the original group has received its final KILL. Normal exit, abnormal
exit, TERM cleanup, timeout and Drop all clean the group before `Child::wait`.
TERM still has its 5-second grace while the leader is alive. An exited leader
does not prevent escalation against a TERM-ignoring descendant.

The entry permanently disarms before reap. EINTR is retried; ECHILD disarms
without sending further numeric group signals. Repeated stop/Drop therefore
cannot target a recycled group after ownership has been released.

This assumes OSDK is the sole reaper and SIGCHLD is waitable rather than
auto-reaped. Concurrent external reaping can invalidate a numeric group anchor;
once loss is observed, safety takes precedence over cleaning an unidentified
group. Descendants that actively change group/session, or forcible termination
of the supervisor before cleanup, are outside this process-group boundary.
It is not a process containment mechanism.

Only OSDK host-tool sources changed. Relative to the imported kernel, the full
derivative set is `osdk/src/commands/build/mod.rs`, `osdk/src/daemon/mod.rs`,
`osdk/src/daemon/supervisor.rs`, and its new `supervisor/tests.rs`. Cargo
manifests/locks, fixed toolchain, OSTD and all A05/A06 process/ioctl/scheduler
sources are unchanged. The fixed-source verifier passed 118 inputs.

## Tests at the pushed source

| Check | Actual result |
| --- | --- |
| Complete derived OSDK host unit suite | 23 passed, 0 failed, 0 ignored, 0 filtered |
| Daemon test module, included in those 23 | 11 passed; TCP lease/EOF replaces `/proc/<pid>` assumptions |
| Selected non-VM OSDK integration | 13 passed; 9 other integration cases unselected |
| Real OSTD kernel crate guest | 221 reported passed, 0 failed, 0 filtered, 3 explicit VMX/EPT soft skips |
| Real aster-core kernel crate guest | 141 passed, 0 failed, 0 filtered, 0 soft skips |
| Complete Asterinas boot | OSTD, initramfs, original boot_hello.sh, completion and shutdown; raw QEMU=33, make=0 |
| Rust formatting, cargo check, fixed inputs | Passed |

The exercised kernel pass lower bound remains **359**, not 362. No full
upstream userspace/device matrix, VMX/EPT/KVM or SMP control result is implied.
The source-built patched OSDK was installed again with `--locked`; its binary
SHA256 is `518d499926ea1c1a415651232a46a4c31141fa75e1a774e12a2c58f401626a5e`.
The committed kernel-test environment records a clean worktree at fb81fec.
The selected integration cases ran before GitHub commit metadata alignment,
against the identical source tree `08477b30c657a445f3eaef25d2d948d34605ffc0`.

GDB 15.1 availability passed using the previously verified scratch dependency
root. No additional system packages, privileges, proc mount, hardware or services were changed.
The first intermediate cargo check failed due to a missing macro import; its
log and the corrected successful check remain in `regression/`. A transient
exec-server transport disconnection recovered before testing; it was not an
approval rejection or a passed test.

## Reproduce and inspect

```sh
support/build/prepare-host.sh --apt
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
python3 -I support/build/ktest/run.py

# With GDB and Bash available on the native host:
cargo +nightly-2026-07-21 test --manifest-path kernel/asterinas/osdk/Cargo.toml \
    --locked --bin cargo-osdk -- --test-threads=1
```

The wrappers use upstream make/cargo-osdk routes, small initramfs and fixed
x86_64/q35/TCG/CPU max/1-vCPU/512-MiB/SeaBIOS/serial/debug-exit. No full NixOS
ISO, network, writable data disk, GRUB, Docker or Nix is required for this guest.
The daemon unit fixtures use local loopback TCP and Bash `/dev/tcp`.
`daemon-probes/` contains the independent before/after reproducer and its
recorded temporary harness manifests/locks.

`commands.json` and the acceptance directories retain exact commands, exit
codes, selected environment, build/install logs, complete raw serial and QEMU
argv. Nonserial command logs are gzip-compressed with timestamp zero.
All three guests exited raw 33 without timeout. Their artifact hashes match
the previously retained ELF/initramfs bytes; `retained-artifacts.json` points to
those files and avoids copying identical artifacts again. The full kernel ELF
SHA256 remains `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63`.
Run `sha256sum -c evidence.sha256` from this directory to verify saved files.

Source pins remain Asterinas v0.19.0 commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, nightly-2026-07-21. This code's
kernel subtree is `85cf10d7c0daa074c747871dfb91d1d25b75ef97`. Main at this round's start was
`47afb8229bd3a3ff05077c7b01aac6fa8ef6f956`. A00 subsequently merged the source
through PR #5 at `c757c709652f9a9701765ff8a9e7c3026fc1019e`. This evidence and
lock update follow separately in [PR #15](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/15)
from the same A01 branch; its base at creation was
`e44c92ac885eb003665ff2e1e5c6fab1f104b2d6`.
Root README remains 0 bytes. The existing A05/A06 interface map and ownership
handoff remain in [`../../README.md`](../../README.md).

Open limits: full upstream integration/userspace/device matrix, controlled SMP,
VMX/EPT/KVM, physical hardware and cross-host bit reproducibility remain
unverified. The prior BusyBox script `/proc/self/exe` workaround and native
libibverbs1 package-configuration restriction remain. HOS2, CapSpace,
exec_epoch, ResourceDomain, Hepta, Android and GPU functionality are outside
this A01 host-tool fix. The formerly observed daemon lifetime defect is no
longer a failing result within the tested process-group/sole-reaper scope.

A residual untracked minimal OSDK profile was preserved outside tracked source
under the shared workspace lock after testing; no bytes were discarded. It
matched the committed minimal profile exactly. Its original stat/hash and
retention location are in `regression/preserved-profile.json`; the cause of
the observed ownership/inode change was not established. This is recorded
without attributing it to another actor or treating cleanup as a new test.
