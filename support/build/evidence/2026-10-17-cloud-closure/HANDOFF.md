# A00 / A05 / A06 handoff

Kernel root: `kernel/asterinas/`. Fixed original upstream SHA:
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`; current derived kernel tree:
`6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. Do not import another copy.
A00 merges PR22; this branch has already merged actual main40ca002 through
5fffe339. The final source bridge identifies the actual consumed Git inputs
of the separately executed validations, rather than claiming whole-tree equality.

| Purpose / owner | Concrete entry or interface |
| --- | --- |
| A01 build | `bash support/build/kernel.sh kernel` → upstream `make kernel` with `minimal.mk` |
| A01 boot | `bash support/build/kernel.sh run_kernel` → upstream `make run_kernel`; x86_64 q35/TCG 1 vCPU/512 MiB, full serial |
| A01 regression | `python3 -I support/build/ktest/run.py`; exact-root SDK reinstall required |
| A01 OSDK matrix | `python3 -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb --output NEW_DIRECTORY` |
| A05 process | `kernel/asterinas/kernel/core/src/process/process/mod.rs`: `Process` |
| A05 thread/context | `kernel/asterinas/kernel/core/src/process/posix_thread/mod.rs`: `PosixThread`; syscall `Context` |
| A05 ioctl dispatch | `kernel/asterinas/kernel/core/src/syscall/ioctl.rs`: `sys_ioctl` → owned file reference → `FileLike::ioctl` |
| A05 file/device boundary | `kernel/asterinas/kernel/core/src/fs/file/file_handle.rs`; file table/inode-handle and device integration |
| A05 launch/exec | `kernel/asterinas/kernel/core/src/process/process/init_proc.rs`; `process/execve.rs` |
| A06 common scheduler | `kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs`: `ClassScheduler`, `impl Scheduler` |
| A06 classes/accounting | `sched/sched_class/{fair,real_time,policy,time}.rs` under the core root |
| Shared OSTD | `kernel/asterinas/ostd/src/task/{mod,processor}.rs`, `task/scheduler/mod.rs`; coordinate with A00 |

A05 already owns process/ioctl/native capability work; A06 owns the scheduler
and resource accounting. A01 retains support/build and initial build-tooling
responsibility, and does not overwrite their core sources. `Process::start_time`
is Jiffies, not a complete generation identity; trusted launch/exec identity,
CapSpace and ResourceDomain must follow the shared ABI contract. Do not weaken
errno, authority, strict windows or persistence requirements to match a partial
implementation. No native enforcement is inferred from a successful host model.

Accepted baselines are the ordinary full-kernel cold-build/boot at d879a9d2,
projected A4/B4 at4e8c708, correct-root OSTD221/core141 atd895dd73
(three soft skips,359 lower bound), and one final OSDK22/22 atd879a9d2
(eleven raw33, one VMX skip). Complete serial, commands and all final actual
inputs are in the indexed phases. Earlier failed attempts remain readable.

A00 should update owned docs/STATUS and the future-import wording in
ARCHITECTURE, and distinguish the recorded main baseline's actual guest
NOT_ENFORCED result from A06's separate Draft guest samples in ROADMAP. A02's fixed-nightly helper fix is
already adopted; the former pending-candidate blocker is historical.

[Remaining work](blockers.json): A05 trusted native control and errno/lifecycle
coverage; A06 final runtime-debit issue63 and complete G1 integration; A07 the
existing unique persistent K↔D owner and real G2; A04 MSG_CMSG_CLOEXEC/NOFILE
and exact ELF inputs; host AF_UNIX/KVM/VMX; cross-host/immutable reproduction;
unidentified workspace writer. These need their stated owners and real test
evidence. PR22 is not a G1/G2 or complete desktop release.
