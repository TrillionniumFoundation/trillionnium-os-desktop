# E retained-task accounting and persistent SysTree ownership

## Qualified source and exact scope

The local native qualification belongs to source
[`2f806c2852cd21a9769c7b01a76ba5f97027c111`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/2f806c2852cd21a9769c7b01a76ba5f97027c111),
tree `6897d0d26277f832d75100e64b92e9432977f240`. It extends the pids
candidate `ad4f91a888e04339385ec2eeeefa4bc9312eed74` with nine SysTree
ownership source changes. Subsequent documentation/evidence commits do not
change the identity of these executions. Publishing this evidence is separate
from the final branch's required CI and merge decision.

This slice verifies a workload leaf with `pids.max=16`, accounting for forks,
threads, retained leaders, and unreaped zombies through the original hierarchy.
It also fixes lookup-derived ownership of SysTree inodes, which previously let
the low-privilege workload open a root-created pids control for writing. The
original manager and recovery remain outside the finite workload leaf.

The technical design, locking/release points, native cases, and reproduction
commands are in [G1D_PIDS_ISOLATION.md](../../../tests/kernel/control/G1D_PIDS_ISOLATION.md).
The complete E milestone, aggregate memory control, native Hepta production
identity and durable K↔D loop, SMP trusted control, and hardware remain open.

## Actual results

| Execution | Original outcome | What the independent review confirmed |
| --- | --- | --- |
| Full aster-core at `2f806c28…` | **275 declared / 275 passed**, 0 failed, filtered, or soft-skipped; QEMU 33 | The original checker reproduces the complete result from the raw serial. The new `object_ownership_survives_inode_and_view_reconstruction` appears exactly once and ends in `ok`. |
| Permission SMP at the same source | **3 passed**, 278 declared / 275 filtered; two CPUs, QEMU 33 | The original SMP parser sees all three exact tests and real CPU 0/CPU 1 lock observations. This subset is not 278 executed tests or SMP trusted-control qualification. |
| Positive G1-d exact image | Passed, QEMU 33, 7.183 seconds, no timeout | All retained-task, permission, CPU/history, manager-exec, recovery, and legal-user-pause predicates reproduce from the original oracle. Actual UID/GID 60001 and zero capabilities are retained. |
| Positive G1-d byte-mismatch and truncated images | Each passed its rejection oracle, QEMU 65, no timeout | Rejection occurred before image/role commit or activation, for the exact original reason. |
| Thread-admission mutant | Original positive oracle **failed**, runner 1; exact guest QEMU 33, no timeout | A real thread succeeded where EAGAIN was required. The accounting child failed at the intended limit assertion, then PID 1 observed the expected pipe closure. |
| Premature-zombie-refund mutant | Original positive oracle **failed**, runner 1; exact guest QEMU 33, no timeout | `WNOWAIT` observed current and ancestor counts of zero, then PID 1 failed at the exact retained-charge assertion before consuming wait. |
| Both mutants' altered-image boots | Four exact rejection results passed, each QEMU 65 | The same probe and original manifest-rejection rules remain active in both mutant kernels. |

The independent review replays **12 original G1-d boots**: the three positive
boots, six semantic-mutant boots, and the three retained pre-fix boots. It uses
the byte-identical original oracle and compares every returned field with the
saved result. It does not launch another kernel or turn a negative's
`passed: false` into a successful positive result.

### Actual semantic-negative witnesses

| Mutant | Head / tree | Exact serial evidence |
| --- | --- | --- |
| Thread admission without limit, with real charge/RAII rollback retained | `cec72fe3653b3451043c71cd8f1299a1342d5034` / `31d0f5a634e56039bc9d6b533eb466dd2bd95afa` | `G1D_PIDS_THREAD_LIMIT_UNSAFE rc=0 expected=11 pid=4 parent=1`; `pids_thread_must_return_eagain`, PID 4; then `pids_pipe_read`, PID 1. |
| Refund one leader at exit before reap | `f5070bc982b29f3280ae38727337a2db4e5d1ee0` / `217d15036b637aee584277c6f7c3a22a94e7cc25` | `G1D_PIDS_ZOMBIE_RETAINED current=0 ancestor=0 wnowait=1`; `pids_zombie_charge_retained`, PID 1. |

Both mutants retain the persistent-owner fix. The actual thread patch changes
only the controller and `CLONE_THREAD` admission; the zombie patch inserts one
refund line into the formatted positive `systree_node.rs`. Independent fresh
patch application reproduced every recorded pre/postimage exactly. Neither
negative reaches the completed accounting/workload markers. Their kernels
terminate through the original probe's failure path, without a panic or timeout.
The restoration receipt returns the production checkout to the clean positive
`2f806c28…` source. These local mutant commits are test inputs, not production
changes to merge.

## Preserved failures

The pre-fix `ad4f91a888e04339385ec2eeeefa4bc9312eed74` / tree
`3c41bde0b28195872d3bbb2d7b0c4ee62aab09ae` exact guest failed despite normal
QEMU exit 33. Its raw serial contains
`G1D_PIDS_BOUNDARY name=raise_limit rc=3 errno=0`, then
`pids_workload_write_denied` for PID 2/role 2. The actual low-privilege workload
successfully opened the root-created attribute; it immediately closed the
returned descriptor. Later IPC/liveness failures are consequences of that
original rejected run. The unchanged probe passes after the backing-object
owner fix. The old failure is not rewritten or attributed to the fixed source.

The first `2f806c28…` G1-d preparation attempt also remains in the package. It
compiled the static probe but rejected an already-used target directory with
`ValueError: G1-d target must be fresh`, before a product build or guest boot.
The subsequent `e-systree-g1d-v2` execution used a fresh target and output and
completed all three boots with the unchanged 120-second limit.

## Source and input identities

| Input | SHA-256 |
| --- | --- |
| Positive ordinary G1-d kernel ELF | `646eb89ddc0dea8beda466f1deba84224fcd3972647fc059947b65ac5489d9e1` |
| Static original G1-d probe, 1,087,856 bytes | `02910d4f6fb0bab00cd95876b4068607f0de567037ed16fea2ada5c98e2c7004` |
| Original `run_g1d_guest.py` | `86025b620fe8a39b0dd745add7a795d1279d50302035ae0a838b3c886040993c` |
| Original `g1d_init.c` | `11369d7cb1f09e0be0aafff40bed1a495843de0ec927615c66908588452c6b62` |
| Original included `g1d_pids.c` | `69f6bc1a6935f1cb03667033956c2b0f3c330c6cdb9920d06e46fe99667d1b57` |
| Generated kernel dependency lock | `e54bc99b3df5e21a1fdcd88d89b32ac478e73c7b4bf69ae0b1084f59d56fc506` |
| QEMU | `8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854` |
| BIOS | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| Formatted positive `cgroupfs/systree_node.rs` | `8d024510aaac5665d6fc097e13775abf888b185c23ac164223735454579aedec` |
| Formatted positive `sysfs/test.rs` | `b8569805e5b0b8c76a8fd44dff65892053980fa3dce43e536b42d76e527c8657` |

Probe, QEMU, BIOS, and generated-lock identities match across the fixed source,
two mutants, and pre-fix source. Each three-boot group uses one kernel; only its
initial probe image is changed for the byte-mismatch/truncated controls. Every
G1-d guest uses the original one-CPU q35/TCG profile with 512 MiB and the original
private bootstrap. The 300-second management lease, 30-second recovery grace,
and 120-second guest deadline were not increased.

The nine formatted owner source files were checked against their exact
`ad4f91a8…` Git blobs and the saved `formatted.patch`; fresh application
reproduces the recorded postimages. The full source snapshots remain in the
larger original archive described below. Their before-build/after-build/after-
guest hashes match within each source group; the original runner also records
`source_inputs_unchanged: true`.

## Included evidence and independent review

- [primary-evidence.tar.gz](primary-evidence.tar.gz): **318,026 bytes**, SHA-256
  `66a617e34b22ff9f0d90a16c79e3af721056b81ffee9ec3e5b0631c846239f00`.
  It contains the **78 files listed in the primary manifest**, plus that
  manifest and the full-archive manifest. Included original material covers
  core/SMP logs and receipts, all 12 G1-d serial streams and per-boot receipts,
  probe descriptors, source preparation/formatting records, both actual
  mutation patches and results, clean restoration, and the final formatted
  source/probe/oracle files needed for review.
- [primary-manifest.json](primary-manifest.json): per-member original byte count
  and SHA-256; the local review verified every listed file against both the
  extracted bytes and archive member.
- [full-archive-manifest.json](full-archive-manifest.json): identities of all
  **132 original full-archive members**, including full source snapshots and
  build logs. The 7,487,851-byte original archive is retained on the execution
  host at the path recorded by the primary manifest, with SHA-256
  `66ada5e7dc34aa5a27143346fdf11b9511bb9bab2e17427cc751b63d5a50baf0`.
  This larger archive was not downloaded for this independent local review;
  it is not represented as another file included in this directory.
- [independent-review.json](independent-review.json): actual original-checker
  replays, exact source/patch comparisons, preserved failure witnesses, and
  explicit scope limits. The SMP serial and recorded two-CPU command/exit were
  checked; this local review did not reopen the original host's kernel, BIOS,
  or QEMU executables. Their original runner receipts remain preserved.
- [source-git-preimages.json](source-git-preimages.json): GitHub tree/blob
  identities independently retrieved for all nine owner source preimages.

Selected raw serial identities:

| Execution | SHA-256 |
| --- | --- |
| Full core | `d824fc8c256d7248aaddb770e05d05bea79a2df6708bd00ddf2b2acaedf1c694` |
| Permission SMP | `0be9410ddb15ea483264eff988139891c814df0ab23b968332c2184a6e34ef80` |
| Fixed exact G1-d | `2fa197b6678aeec5132950026e80e371376ca9be3864559a0c9c82ee58e4aeca` |
| Thread mutant exact | `03192f2d7d32326cd3d561ba1b4a93b4bf19351d4496be027f244b8a8f71b050` |
| Zombie mutant exact | `a67ea269dcea8f7d8bccc120e448371a8ed6addccd950e6228a89416be515979` |
| Original pre-fix exact failure | `6767d04c0fad177ab69e4391f60e601f047d6d3bd5e365503e0ce5a268e71950` |

## Remaining boundary

The pids cap bounds charged retained tasks, including unreaped leaders. It does
not bound aggregate process-tree memory, kernel memory, retained tracing
metadata, or numeric PID allocator lifetime. `memory.max` is still a stub;
256 MiB `RLIMIT_AS` remains a per-process limit. Removing a zombie-only cgroup
remains conservatively `EBUSY` until reap.

The ownership regression covers reconstructed metadata and the actual
root-created G1-d workload controls. It does not establish native delegation
across multiple non-root creators/readers, a general SysTree `chown` policy, or
mode persistence across inode reconstruction. Existing root manager/recovery
identities, privilege policy, and the limited recovery contract remain in force.
The same-source native Hepta owner/store lifecycle, production grant provider,
final-exec role admission, durable K↔D/replay/retirement, autonomous recovery,
SMP trusted control, and actual GPU/ARM/mobile hardware retain their own gates.
