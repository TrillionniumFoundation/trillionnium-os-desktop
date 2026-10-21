# A00 / A05 / A06 handoff

Kernel root: `kernel/asterinas/`, with one complete fixed Asterinas implementation.
A01 branch: `agents/A01-asterinas-boot`, PR22 to main. A00 coordinates final
integration and owns shared status/architecture/workflow updates. Tested producer identities and publication receipts are in
`source-bridge.json` and `raw/publication/`; final PR/CI readback is separate.

Use the configured project-cloud environment with its fixed Cargo/Rustup/native
prefixes. Existing `cloud-replay-env.sh` supplies that exact layout; keep its
literal shared dependency paths for schema4 reproduction. No full NixOS ISO,
Docker or Nix daemon is needed for the small initramfs route.

| Purpose / owner | Concrete path or command |
| --- | --- |
| Full kernel build | `bash support/build/kernel.sh kernel` → upstream `make kernel` |
| Ordinary boot | `bash support/build/kernel.sh run_kernel` → upstream `make run_kernel` |
| Complete Rust entry debug | `python3 -I support/build/debug/run.py --output support/build/out/NEW-debug-run` |
| Core/OSTD regression | `python3 -I support/build/ktest/run.py`; each invocation installs and directly executes its private source-bound SDK |
| TCP/GDB OSDK matrix | `python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb --output NEW_DIRECTORY` |
| A04 exact inputs | `python3 -I support/build/handoffs/a04-exact-rootfs/verify.py --output NEW_DIRECTORY` |
| A05 process object | `kernel/asterinas/kernel/core/src/process/process/mod.rs`: `Process` |
| A05 thread object | `kernel/asterinas/kernel/core/src/process/posix_thread/mod.rs`: `PosixThread` |
| A05 initial launch / exec | `kernel/asterinas/kernel/core/src/process/process/init_proc.rs`; `kernel/asterinas/kernel/core/src/process/execve.rs` |
| A05 ioctl dispatch | `kernel/asterinas/kernel/core/src/syscall/ioctl.rs`: `sys_ioctl` → owned file reference → `FileLike::ioctl` |
| A05 file/device transport | `kernel/asterinas/kernel/core/src/fs/file/file_handle.rs`; `inode_handle.rs`; `util/ioctl/mod.rs` under the core root |
| A06 common scheduler | `kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs`: `ClassScheduler`, `impl Scheduler` |
| A06 classes / time | `sched/sched_class/{fair,real_time,policy,time}.rs` under the core root |
| A06 cgroup accounting integration | `kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs`; final debit/lifetime correction remains owner issue63 |
| Shared OSTD | `kernel/asterinas/ostd/src/task/{mod,processor}.rs`, `task/scheduler/mod.rs`; coordinate common changes with A00 |

Ordinary kernel/run/GDB actions now install into each fresh run directory's
`osdk/` prefix and share dependency caches, rather than sharing an installed
SDK binary. CARGO_HOME must be absolute without parent components; when it is
unset HOME must meet the same default-location requirements. Debug's
installed-osdk.json uses that boot's private SDK and install receipt. The
ktest entry now rejects `--skip-osdk-install` with exit2 before output/lock;
it accepts neither a global binary nor a previous output's SDK. Run the default
command without that legacy flag. Do not convert historical wrong-root results to source-
bound acceptance; the originally implicated SDK binary was not retained.

The standard boot profile remains x86_64 q35/TCG, CPU max, one vCPU, 512 MiB,
fixed SeaBIOS and devices, serial log and raw33. Kernel/run/GDB use new output
directories; retain command/env/serial/ELF/BIOS/initrd hashes for every owner
candidate. Private prefixes and stable-file checks are not an immutable sandbox
against a same-user external writer.

A05 owns process/ioctl/CapSpace/launch identity. A06 owns scheduler and resource
accounting; public OSTD changes need A00 coordination. A01 retains build/support
and upstream-lock responsibility and does not overwrite their core sources.
Use the existing A02 ABI and A03 state core as references without creating a
second native authority or Hepta persistent operation ledger.

Accepted historical full OSTD/core counts remain 362 reported, three soft
VMX/EPT skips, 359 exercised lower bound; historical final TCP/GDB matrix is
22/22 with 11 actual raw33 guests and one VMX skip. They are tied to their own
earlier producer commits. Main47288's 13 host ABI checks and this round's
161+32 host checks do not turn them into new latest-source guest regressions.
New N2 source0a7037 cold ordinary build plus warm raw33 boot is accepted in
`2026-10-17-private-sdk-native`: complete ELF SHA256
`5c2cee2a8806baf873149ce07f752cc3b1c633efd4199e0c8c0ba20ef5f325f7`.
Both action-private SDK payloads are retained and byte-identical; the original
global SDK has unchanged stat/hash observations, not a retained before/after
payload pair. D1 sourcea5af455 passed actual TCP/GDB entry-byte binding, detach and raw33;
K sourceff0d09a passed OSTD221/core141, three soft skips and359 exercised
lower bound across two raw33 guests. Debug and ktest reused targets and
actually recompiled; they are not cold or zero-compilation replays.

| New accepted phase | Producer / result |
| --- | --- |
| `2026-10-17-repro-kernel-c4` and `2026-10-17-repro-cross-instance` | 4e8c708; absent-target build/raw33, complete ELF/initrd/BIOS match historical A4 on different observed cloud instance |
| `2026-10-17-private-sdk-native` | 0a7037f; ordinary279 compilation lines, warm boot0 compilation/raw33, private SDK roots and complete bytes checked |
| `2026-10-17-debug-private-sdk-native` | a5af455;177 compilation lines,32 runtime entry bytes match symbol+boot, detach/raw33 |
| `2026-10-17-ktest-private-sdk-native` | ff0d09a;54+83 compilation lines,362 reported/3 soft/359 exercised lower bound, two raw33 |

Only these five new guests count this round. Host161 ordinary support checks,
host32 debug checks, ktest11 per mode and main ABI13 checks have separate
scope. Exact A04 payload recovery does not close guest compatibility gaps.

A05 can begin trusted CapSpace/session, process-start/exec_epoch and launch
identity work at the paths above; QueryAbi-only historical acceptance does not
supply effect authority. A06 can begin the final pending runtime debit/lifetime
correction tracked by issue63, then run the unchanged guest CPU probe against
its own modified kernel. A00 must coordinate G1/G2 and unique persistent K↔D
acceptance; none is implied by A01's build/regression passes.
