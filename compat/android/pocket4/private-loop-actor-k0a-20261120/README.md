# K0a: retained original-thread context for the private-loop implementation

This packet adds real Linux C source for the first lifetime dependency in the
[private-loop design, PR #319](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/319).
It is an internal actor reference, not a private-loop device or an authorization
provider. It has no callers in this patch, no userspace interface, and a default-off
Kconfig option. The original loop driver, ordinary block entry points, namespace
grant and Rust target issuer remain unchanged.

**Status: source patch prepared and its exact-input/patch round trip verified.
Target-kernel compilation and all native/runtime acceptance are pending.**

## Exact source and changes

The source baseline is the existing `6.18.64-p4ctx6181` candidate at:

`ai395:/home/qq/work/p4-kernel-6.18.64-cp3a-20261118-r1/source/linux-6.18.64`

`INPUTS.json` records the complete bytes, SHA256 and read versions of twelve
original source/header files. `EXACT-SOURCE-OBSERVATIONS.json` separately records
bounded excerpts and full-file hashes for `include/linux/sched.h`, `fs/exec.c`
and `kernel/fork.c`; it does not claim those excerpts are complete local files.
The original source tree was only read. No compiler ran on ai395.

| Path | Change |
|---|---|
| `include/linux/p4_private_loop_actor.h` | New opaque internal actor type and four reference/check functions |
| `block/p4_private_loop_actor.c` | New exact task/context reference acquisition, comparison and release |
| `block/Kconfig` | Add `P4_PRIVATE_LOOP_ACTOR`, dependent on `EXPERT`, `USER_NS` and `PID_NS`, default `n` |
| `block/Makefile` | Add only the object controlled by that option |

`MANIFEST.json` pins every preimage/postimage and the complete `K0a.patch`.
The patch is the delivery artifact; the source copies under `candidate/` make
review and integration straightforward. The original twelve headers/sources
need not be duplicated in the repository: retrieve the exact complete inputs
from the pinned source snapshot and reject any byte or SHA mismatch.

## API and ownership

`p4_private_loop_actor_capture(task)` accepts a task reference that the caller
already obtained through a separately reviewed kernel binding. It never accepts
a numeric PID and never promotes a nonleader thread to its thread-group leader.
It takes its own references and returns an error pointer on failure.

The exact target kernel's `is_user_task()` rejects a missing userspace `mm`,
`PF_KTHREAD`, and `PF_USER_WORKER`. Capture also rejects exiting or ptraced
tasks, subjective credential overrides, incompatible `mm`/credential user
namespaces, missing filesystem/namespaces, an exec in progress, invalid paths,
and a filesystem user count that cannot safely be incremented.

| Retained object | Acquisition | Final release | Purpose |
|---|---|---|---|
| Exact `task_struct` | `get_task_struct` | `put_task_struct` | Prevent task pointer reuse while the actor exists |
| Exact thread `struct pid` | `get_task_pid(..., PIDTYPE_PID)` | `put_pid` | Preserve original TID identity, including nonleaders |
| `mm_struct` | `mmgrab` | `mmdrop` | Preserve address-space identity without incrementing `mm_users` |
| Objective credentials | `get_task_cred` | `put_cred` | Keep the compared credential object alive |
| `nsproxy` | `get_nsproxy` | `put_nsproxy` | Preserve the captured namespace-container identity |
| Active PID namespace | `get_pid_ns` | `put_pid_ns` | Preserve the exact captured PID namespace |
| `fs_struct` | Increment `users` under its sequence lock | Decrement under the same lock; free after unlocking | Prevent filesystem-object pointer reuse |
| Captured root and working directory | Two `path_get` calls | Two `path_put` calls | Retain both captured path identities independently of mutable `fs` paths |

The destructor accepts every partial-acquisition state. Allocation occurs before
the task/filesystem locks. Capture follows the existing target kernel order
`task_lock` then the exclusive reader of `fs->seq`; reference destruction and
path/MM teardown happen after both locks are released. `get` requires an already
owned reference; it does not resurrect a dead object. A final `put` may perform
teardown and must not execute under a spinlock.

`p4_private_loop_actor_check_task()` compares the exact task and retained PID,
MM, credential, namespace and filesystem context. It also compares filesystem
sequence, umask, root and working directory while holding the filesystem lock.
Capture performs this second check before returning. Neither function allocates
or opens a block device, issues a loop ioctl, changes a namespace or grants access.

## Boundaries that must survive integration

### The retained filesystem reference affects execution semantics

The extra `fs->users` reference prevents pointer reuse, but it is not a
behaviorally transparent observation. In the actual pinned kernel:

- `fs/exec.c::check_unsafe_exec` compares `fs->users` with the number of threads
  sharing the filesystem. An extra retained reference can select
  `LSM_UNSAFE_SHARE` rather than setting `fs->in_exec`.
- `kernel/fork.c::unshare_fs` may skip a copy when `users == 1`; the extra
  reference can make it copy instead.
- `kernel/fork.c::copy_fs` increments the same count for real `CLONE_FS` users
  and checks `in_exec`. This count is more than a generic object lifetime count.

These are observed source semantics, not a native experiment. This source-only
patch has no actor caller and changes none of those branches. A future issuer
must either prove that its bounded retained lifetime is compatible with these
semantics or introduce a separately reviewed non-task lifetime mechanism. It
must not weaken the original exec/LSM policy to accommodate the reference.

### A successful comparison is not durable authority

`task_lock` protects the relevant task attachment operations; it does not by
itself serialize all credential replacements. A snapshot plus second check
cannot establish that no transient change occurred, and a successful return
does not prevent a change immediately afterward. The filesystem sequence is
also an observation, not an indefinite unforgeable epoch.

Future syscall entry checks must bind the actual `current` task and the
operation's live kernel state. They must not accept a userspace-supplied task,
a same-TGID substitute, cached success, a completed seccomp notification, or a
model result as an access token. The fresh original request, controller,
pending notification, exact original thread, operation, expiry and one-use
rules remain separate requirements.

### Namespace identity is not graph or I/O isolation

Holding a namespace pointer, root and working directory does not freeze the
mount graph or validate an APEX graph. This patch supplies no private device
allocator, block access hook, ioctl gate, mmap gate, page-cache/bio ownership,
device-mapper composition, descriptor-transfer policy or teardown mechanism.
It cannot make an ordinary unconfigured host loop private. The Rust original
target issuer remains unconstructible. No original apexd code, errno result,
security policy or production gate is replaced.

## Verification actually performed

`verify_patch.py` checked all twelve complete input bodies and all four output
pins. In a new temporary source tree it ran the actual `git apply --check` and
`git apply` operations with whitespace errors rejected, compared every candidate
postimage, checked all other retained inputs unchanged, then ran the reverse
check and reverse application. Every original byte was restored; both newly
added files were absent after reversal. The Python preparation script's syntax
was also checked. `STATIC-VERIFICATION.json` records those commands and hashes.

The complete C/header were independently reviewed by the root agent. That review
identified the filesystem sharing semantics and reiterated the credential
serialization boundary, both now explicit above and in the API comments. It did
not supply kernel compilation or runtime credit.

There was no fake-header build, userspace model presented as kernel execution,
device operation, module load, kernel installation, reboot, Android start or VM
start. Pocket4 currently reports `7.0.14-p4cred1`; its two discovered header
trees are `7.0.0-43`. Those are not the target `6.18.64` build inputs.

## First follow-up: compile against the exact target inputs

1. Obtain an isolated complete copy of the fixed `6.18.64-p4ctx6181` source,
   including its existing local patches, matching configuration and the real
   generated-header/toolchain provenance. Verify all packet preimages first.
   A generic 7.0 header package or a stock 6.18 source substituted for the
   existing patched tree is insufficient.
2. Apply only `K0a.patch` in that independent copy. Preserve the original target
   configuration and confirm the existing prerequisites; enable only the new
   option for this source compile. Use a separate Kbuild output directory.
3. With a reserved single CPU, one build job and a bounded memory/time budget,
   run the target's configuration/generated-header preparation and compile
   `block/p4_private_loop_actor.o` with warnings enabled. Record the exact
   configuration, compiler, commands, complete output and object hash. Do not
   use ai395's active vendor-build resources.
4. Fix any actual compile failure in a successor with exact before/after pins.
   This compile alone still provides no live actor or private-loop isolation
   acceptance. Keep the option off in all deployed kernels.

The current blocker for that compile is the missing matching isolated build
tree, not evidence that this C has compiled. No kernel/runtime flag in this
packet may be changed until the corresponding real operation completes.

After compilation, the next implementation dependency is the reviewed graph,
revocation and full block-entry ownership mechanism in PR #319, followed by a
private allocator/configure path, real same-OFD APEX probe/configure handling,
and only then the Rust issuer. Real positive and negative tests must cover exact
nonleader threads, task exit, credential/namespace/filesystem changes, unrelated
actors, descriptor transfer, graph changes, reuse, expiry and cleanup. The
previously denied privileged patched-kernel VM fixture must not be retried via
another key, tool or agent. No installation or live device qualification is
authorized by this source packet.
