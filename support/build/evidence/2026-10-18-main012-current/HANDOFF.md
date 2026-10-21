# A01 current-source handoff to A00 / A05 / A06

This handoff binds the inspected interfaces and this run's recorded native
results to producer `b39e154ae5a1e9853f57e23f9bee84712ee8ef7e`, project tree
`80ceaa07562dd359572afdc6bfad473aa20d7271`, kernel tree
`065a20ff147bf1541acbdfd996338ab0267fbfc6`. Its first parent is current-main
baseline `01225ab0a20a9f25dd8313a7fad7652dd9154e30`; the ordinary merge preserves
the existing A01 branch history as its second parent. No owner core file changed
relative to that main baseline. The independent audit below only reads existing
source and execution receipts; it does not rerun Cargo or QEMU.

## Current run and independently checked source closure

The actual run directory is `support/build/out/2026-10-18-main012/`. Each stage
retains its own command, environment, source identity, result and original log.
The independent-audit/source-before.json and source-after-native.json manifests
contain 3,012 identical records,
all matching producer HEAD. Their shared source-list SHA256 is
`68c724b562bb1bcc6a6fde03787caea95ce36400fbb9c12714f36244a930fe99`.
The after audit completed at 2026-10-18 09:04:15 UTC, with all 15 read-only checks
passing, the main kernel/OSTD/ABI ownership comparison empty, root README zero
bytes, and a clean full Git status at both after-audit observations.

| Actual stage on this producer | Result and evidence boundary |
| --- | --- |
| `support/build/kernel.sh kernel` | Exit 0; 08:49:31.749120–08:52:49.014296 UTC, 197.265 seconds. The kernel target directory was absent before the build. This is a new source build; it does not claim a cold Cargo download cache or cross-host bit reproducibility. |
| First `support/build/kernel.sh run_kernel` | Exit 1 at 08:53:39 UTC before QEMU: a newly present untracked `kernel/asterinas/kernel/OSDK.toml` was refused. This attempt did not launch a guest and is not a boot PASS. |
| `run_kernel_retry01` | After preserving and reversibly quarantining the observed manifest under the native workspace lock, the unchanged build entry returned 0; QEMU raw exit 33, no timeout, 0.969 seconds. All five expected boot markers occur once. |
| OSTD kernel-mode suite | 221 reported passed, 0 failed/filtered; 3 explicit VMX/EPT capability soft skips, so the exercised-pass lower bound is 218. QEMU raw exit 33. |
| aster-core kernel-mode suite | 160 passed, 0 failed/filtered/soft-skipped, QEMU raw exit 33. The serial log contains successful execution of all six new final-charge object tests and the odd/even-period test. |
| Combined kernel-mode suites | 381 reported passed, 3 soft skips, exercised-pass lower bound 378. These are this producer's actual suites, not inherited counts from the earlier 153-case core run. |

The first produced and actually loaded kernel ELF are byte-identical,
8,283,136 bytes, SHA256
`6518b6472efbc599498b71550ef9761f6f20e74814db0c9a81bff101ab036e55`.
The full boot serial log is 72,194 bytes, SHA256
`0efe9f6156db9aa42574e35ab919c1a3e0aeea30b6a74ff0397e50c362a4ae1e`.
The boot input is the small 1,107,990-byte initramfs, SHA256
`86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`.
This was the derived Rust kernel with its initramfs, not a host Linux boot or an
ISO installer. The exact fixed-device command remains in the retry's `qemu.json`.

### Current manifest-writer issue remains unassigned

This run reproduced the unexpected manifest appearance twice. The prelaunch
entry had inode 1720253; the post-ktest entry had inode 1718453. Both observed
files are 1,019 bytes with SHA256
`1ff39174c39411f8b9a7fd328f762268e62d88521b43ebbde384d03d7d9a9f9f`, matching the
minimal profile. Their stat fields, raw bytes and the original nonempty Git
status receipts are preserved. The known kernel/boot cleanup receipts are not
rewritten as failures or used to assign authorship to these distinct entries.

Both entries were preserved and renamed under the shared native build lock,
without unlinking, overwriting or modifying the guard. The second quarantine
completed at 09:03:55 UTC and the later independent source audit confirmed the
public entry absent and the tracked source unchanged. This is a clean final
observation, not a claim that the entire run's worktree was continuously clean.
The responsible writer and root cause remain unidentified; timestamps, matching
bytes and inode observations alone do not establish who created either file.

## Source and build ownership

- Sole complete kernel source root: `kernel/asterinas/`.
- Fixed upstream: Asterinas v0.19.0 commit
  `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, tree
  `96605cf64aeae2d34f29b97e85eff9315fe10a8e`,
  Rust `nightly-2026-07-21`, target `x86_64-unknown-none`.
- A01 owns `support/build/**`, `support/upstream-lock.json`, and the initial
  upstream import/build configuration. A01 preserves current main's core and
  OSTD source. A00 coordinates any shared OSTD or fixed-version change.
- A05 owns process/ioctl/native-control integration. A06 owns scheduler work;
  changes to shared Process/resource interfaces follow the existing A05/A06/A00
  coordination instead of creating a second resource truth.
- Build: from the repository root with the prepared native environment,
  `support/build/kernel.sh kernel`; boot: `support/build/kernel.sh run_kernel`.
  These use upstream `make kernel` and `make run_kernel` through the maintained
  small-initramfs overlay. The initial profile is q35/TCG, one vCPU, 512 MiB,
  multiboot/SeaBIOS, serial output and `isa-debug-exit`.
- Kernel tests: this run executed
  `python3 -B -I support/build/ktest/run.py --output <new-output-directory>`
  without a crate filter, covering both current OSTD and `aster-core` suites.

## A05 interfaces

All following paths are relative to `kernel/asterinas/`.

| Purpose | Path / symbols | Current boundary |
| --- | --- | --- |
| Authoritative process identity | `kernel/core/src/process/process/mod.rs`: `Process`, `hepta_capspace_session`, `hepta_exec_epoch`, `advance_hepta_exec_epoch` | The boot-local nonce and image epoch are jointly serialized; checked counters reject wraparound. |
| Successful image replacement | `kernel/core/src/process/execve.rs`: `do_execve` | The successful replacement advances the process epoch; an exhausted fence fails the process. It does not automatically grant fresh management authority. |
| Trusted init insertion point | `kernel/core/src/process/process/init_proc.rs`: `spawn_init_process`, `create_init_process`, `create_init_task`, final `process.run()` | Existing constructors/ELF loading are available for the coordinated stopped-task, resource-binding and trusted post-exec activation work. That transaction is not implemented merely by identifying these paths. |
| System-call transport | `kernel/core/src/syscall/ioctl.rs`: `sys_ioctl` | Owns the file reference before dropping the file-table borrow and dispatching the file ioctl. |
| Native control file | `kernel/core/src/device/misc/hepta_control.rs`: `HeptaControlDevice::open`, `HeptaControlFile::check_session`, `PerOpenFileOps::ioctl` | `/dev/hepta-control`, experimental `0xC0204802`; actual Process Arc identity and exec epoch are checked. `dup` shares a session; inherited/transferred fds do not transfer the process identity. |
| Single HOS2 codec | `kernel/core/src/lib.rs`: `hos2_os_abi` path module | Imports repository `libs/os-abi/src/lib.rs` directly; there is no copied second codec. The os-control crate is not yet a native kernel dependency. |

Only `QueryAbi` is implemented and advertised. `ReadUsage`, `InstallBudget`,
`QueryDelivery`, and `RetireThrough` return `EOPNOTSUPP`. A successful ordinary
boot or a host ABI suite does not prove an actual control-device effect,
CapSpace grants, revocation, or durable retirement.

## A06 interfaces

| Purpose | Path / symbols |
| --- | --- |
| Common scheduler | `kernel/core/src/sched/sched_class/mod.rs`: `ClassScheduler`, `PerCpuClassRqSet`, `LocalRunQueue::{try_pick_next, update_current, dequeue_current}`, `pick_next_entity`, `replenish_throttled` |
| Scheduling classes | `kernel/core/src/sched/sched_class/{stop,real_time,fair,idle,time}.rs` |
| Shared bandwidth state | `kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs`: `CpuController`, `CpuMax`, `task_cpu_eligible`, `charge_task_cpu`, `charge_bandwidth_hierarchy` |
| Final-charge lifetime | `kernel/core/src/process/posix_thread/mod.rs`: `cpu_cgroup`, `set_cpu_cgroup`, `CpuCgroupLease`; `process/process/mod.rs`: `set_cpu_cgroup_for_tasks` |
| Membership and deletion | `kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs`: `CgroupMembership::{move_process_to_node, move_process_to_root}`, `retain_cpu_charge_lease`, `release_cpu_charge_lease`; neighboring `inode.rs` retains the filesystem deletion boundary |
| Current owner regressions | `kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/final_charge_regressions.rs`; `kernel/core/src/process/test_util.rs`; parity case in `controller/cpu.rs` |

Current main fixes the unreaped-zombie final-debit gap. A still-present Process
cgroup binding wins while live or not yet detached. A detached zombie, even if
its parent retains its Arc, and an already-reaped process use the retained
thread lease for the final scheduler interval. This charges bandwidth/debt;
the `cpu.stat` usage projection has a distinct tick-accounting path.

Compared with the earlier native producer `40c901c6e189058bdd6f42bb43bf46b3bbcf8ffa`,
main `01225ab0a20a9f25dd8313a7fad7652dd9154e30` has six owner-file changes: the
CPU controller, its new final-charge regression module, `process/mod.rs`,
`process/posix_thread/mod.rs`, `process/process/mod.rs`, and new `process/test_util.rs`.
There are six new real-but-unscheduled Process/Task final-charge tests and one
new odd/even completed-period test. They do not run the userspace exit syscall
or prove arbitrary scheduler timing, migration, IRQ lock order, or SMP.

## Current scope requiring further owner work

Keep current main's zombie/parity fixes; do not describe them as absent. Continue
with full syscall/scheduler exit/reap/rmdir/migration scenarios, measured strict
window and recovery behavior, and the coordinated HOS2 resource-effect layer.
G1/G2, complete SMP/bare-metal/user-space/device matrices and Asterinas UI/input
remain distinct qualifications. R8 already has a Linux-host trusted
ObjectiveStart admission and visible Rust Shell projection; it is still not
the durable K↔D and native HOS2 effect path.
