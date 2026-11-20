# K0a: retained original-thread context for the private-loop implementation

This packet adds real Linux C source for the first lifetime dependency in the
[private-loop design, PR #319](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/319).
It is an internal actor reference, not a private-loop device or an authorization
provider. It has no callers in this patch, no userspace interface, and a default-off
Kconfig option. The original loop driver, ordinary block entry points, namespace
grant and Rust target issuer remain unchanged.

**Status: the unchanged K0a C source passed an actual single-object compile
against the matching 6.18.64 candidate, followed by its original objtool checks.
Full-kernel building, Kbuild option selection, installation, live actor issuance
and all native/Android runtime acceptance remain pending.**

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

## Initial source verification

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

The original `MANIFEST.json` and `STATIC-VERIFICATION.json` remain unchanged
historical records of that initial source-only delivery. The actual later
object compilation is recorded separately below; it does not retroactively
turn the original static checks into compiler or runtime tests.

## Actual matching-kernel object compilation

The compile ran in the new, private workspace
`pocket4:/home/alex/work/p4-private-loop-k0a-compile-20261120-3b9d-r1`.
No compiler ran on ai395. The process used CPU 23, one job, a 2 GiB address-space
limit, a 180-second CPU limit and a 220-second compiler-runner deadline.
The enclosing owned job had a 300-second wall limit. The source preparation
had its own bounded limits and checked available disk space before extraction.

`prepare_matching_tree.py` verified the exact official Linux 6.18.64 archive
and its detached signature, extracted it into an absent independent tree,
applied the **final qualified 66-file candidate patch**, and verified every
candidate source pin. The earlier 57-file patch was not used. It then applied
the unchanged K0a patch, verified its twelve original inputs and four
postimages, and confirmed the existing 66 candidate files remained exact.
It copied the original final configuration and all 43 actual generated C
headers. The unrelated generated Rust configuration was not a C build input.
No header was synthesized, no configuration option was relaxed, and Pocket4's
running 7.0 kernel or installed 7.0 headers did not substitute for this tree.

| Actual input | Complete bytes | SHA256 |
|---|---:|---|
| Official `linux-6.18.64.tar.xz` | 155,382,076 | `020d45510c539972e6f14c5c71566878d3b7ef56fb082b3e09134f2ebaade562` |
| Final qualified candidate patch | 84,316 | `b9e77cdc6683b1a7eeb193fda35d8ac6945a24cb3e1a9f9f8cd804a0de20fdd2` |
| Final matching `.config` | 304,072 | `bccb147083a909408e25dc63f1dd58cf465ee19bcabc660916a1fa28cc67a3e1` |
| GCC executable | 1,305,304 | `b5f1b773a7c733738352000c92a077dc5852a1a2fc6d836b1e411be1e9ec5f88` |
| Original candidate objtool | 979,400 | `2453a7416b1f9aa1799ee6c900ef5dba6641182f99f5a8b50b604c106959e3ba` |

The archive signature verified with signer
`647F28654894E3BD457199BE38DBBDC86092693E`. An initial download exceeded its
30-second supervisor budget and left a retained 5 MiB prefix. The separate R2
download used a new filename, checked the prefix, required an actual HTTP 206
range response, and verified the entire official archive hash. Both terminal
job states are retained in `HOST-JOBS.json`; the unsuccessful attempt is not
represented as a pass or omitted from the evidence.

`compile_kernel_object.py` used the actual target's retained GCC command for
`kernel/p4_guest_mntns.o`, changing only source/output prefixes, the translation
unit name, and the kernel-to-block include/output paths. Architecture,
hardening, warning, instrumentation, debug and sanitizer flags were preserved.
`COMPILE-COMMAND-SOURCE.json` records that source command and the two exact
configuration differences between its older TU output and the final full
configuration: the final configuration additionally enables
`CONFIG_LOCK_DOWN_IN_SECURE_BOOT` and `CONFIG_SECURITY_PERF_EVENTS_RESTRICT`.
The compile consumed the unchanged **final** configuration/generated headers.

The compiler dependency scan and actual compilation identified the same 510
source/header dependencies. Their complete SHA256 values and nine-field file
identities were recorded and checked unchanged after compilation. The real
GCC process and the candidate's verified original objtool both exited zero,
with empty stderr. The resulting object is an x86-64 ELF relocatable file;
its four expected actor API symbols were read back. Every actual child was
reaped with its original pidfd held until reaping.

| Actual output | Complete bytes | SHA256 |
|---|---:|---|
| GCC object before objtool | 190,984 | `400eabf71a5968a9423c7c293e90109056fe67eaa89b4856646402384cf84fb1` |
| Final object after objtool | 193,456 | `5a2be5176041e92657ba75fecfeae2cf3623c73b83d175c19344851a59f47b41` |
| Complete compile receipt | 251,396 | `6b47c885ba790987a3adb0b18a327068529e9ac612964fd05eb0c5393e0c532d` |
| Complete matching-tree receipt | 23,008 | `232793bb6e70cfdd0aba664c1a0be17f2a623d465cc2507a884582f65f18b243` |

`OBJECT-COMPILE.json` is the original complete host receipt, including all 510
dependency pins, exact command vectors, process results and object/tool pins.
`ACTUAL-LOGS.json` retains all stdout/stderr bodies for those commands and the
source/signature preparation. `OBJECT-COMPILE-SUMMARY.json` indexes the exact
evidence, resource limits and remaining boundaries. The original ELF remains
in the private host workspace; no executable or kernel image is installed by
this packet.

This was direct explicit translation-unit compilation with actual generated
headers. It did **not** run Kbuild configuration selection, select the new
default-off option, link a kernel, load a module, install a kernel, reboot,
operate a block device, issue an actor, or start Android or a VM. A complete
Kbuild/link validation remains a separate integration gate. The live
filesystem-sharing, credential-change and actor-lifetime behaviors above
have not been exercised by this compile.

## Next implementation dependency

The next implementation dependency is the reviewed graph,
revocation and full block-entry ownership mechanism in PR #319, followed by a
private allocator/configure path, real same-OFD APEX probe/configure handling,
and only then the Rust issuer. Real positive and negative tests must cover exact
nonleader threads, task exit, credential/namespace/filesystem changes, unrelated
actors, descriptor transfer, graph changes, reuse, expiry and cleanup. The
previously denied privileged patched-kernel VM fixture must not be retried via
another key, tool or agent. No installation or live device qualification is
authorized by this source packet.
