# Private loop targets for unchanged original apexd

## 1. Decision and evidence boundary

Implement a bounded, owner-bound **private loop/control realm** using the real loop configuration and I/O machinery. The missing work is a native device and resource-lifetime capability, not an errno translation or an application setting. There is no safe small patch that only adds a constructor to the existing Rust empty issuer enum.

This is an implementation design, not a kernel patch or a deployed feature. The accompanying executable is only a pure protocol model. `INPUTS.json` pins every reviewed source file by host, exact path, size and SHA256, plus the original ABI/blocker records. The repository base is `1af163b21f5c7dcaaf94084d7cc1ef19aed05ae1`; the reviewed source cohort is the fixed 2359-file producer. The 2360 successor manifest does not modify the five APEX Rust files listed in that input set. This does not authorize changing the 2359 source used by the active r21 vendor build.

The current host kernel and the 6.18.64 candidate are distinct. This design targets the pinned 6.18.64 candidate sources; it does not claim that candidate is installed. Its candidate source-pin list has 57 modified files and no loop/block/ublk patch implementing the proposed interface.

## 2. What the original binary actually needs

The preserved CP3A original apexd binary is SHA256 `ec9d36db2cd8eb6c9bb9e5005b3c4d81206e901d13c112acb1a9f57f6dfb30a4`. The reviewed ABI record is pinned in `INPUTS.json`.

1. Keep the original source open-file description (OFD): initially O_RDONLY, O_CLOEXEC and O_DIRECT, with its original fallback behavior. A newly opened path or a different source FD is not equivalent custody.
2. Preserve the original loop control and block-open protocol: `LOOP_CTL_ADD` (0x4c80), `LOOP_CTL_GET_FREE` (0x4c82), then the selected real block target opened O_RDWR | O_CLOEXEC. Exact index allocation and worker-thread relations still need confirmation from the original implementation before finalizing the control ABI.
3. Execute the actual 304-byte zeroed `loop_config`, with `fd=-1`, against that unconfigured block OFD using `LOOP_CONFIGURE` (0x4c0a). Native return -1 / errno EBADF (9) selects the modern interface. An error from `pidfd_getfd(-1)`, a fabricated seccomp reply, ENOTTY or EACCES is not that observation.
4. Configure the **same original block OFD** using the fully verified source, payload offset/size, block size 4096 and original AUTOCLEAR flag 4. The original request flags and the driver's resulting read-only status are separate facts. Do not silently substitute the existing backend's flags 1|4 for the original request.
5. Execute real BLKRASET (0x1262); original read-ahead uses the property KiB value times two sectors (default 256 sectors). Only an actual EACCES result permits the original sysfs fallback to `read_ahead_kb` (default text `128`). This fallback needs its own real access and identity checks.
6. Continue through real dm-verity, the original block path and real mounts. The loop feature alone is insufficient. The observed normal activation path selects restart-on-corruption, while another path takes a different boolean. The independent EIO/sticky-state requirement must be reconciled using the original path; do not rewrite its mode to manufacture a pass.

Neither original init/apexd bytes nor existing security enforcement may be changed to satisfy these steps.

## 3. Why the existing interfaces do not provide this

| Exact pinned source | Observed behavior | Consequence |
| --- | --- | --- |
| `drivers/block/loop.c` | One global loop IDR; global ADD/GET_FREE. `loop_configure()` calls `fget(config->fd)` and returns EBADF before inspecting `Lo_unbound`. | The correct probe is available in the real core, but ordinary loop allocation has no required private owner contract. |
| `production_private_loop_owner.rs` | Uses ordinary loop control, obtains a global index, creates a private node with the same device number and opens it O_RDWR. It retains target/source custody during its own configuration sequence. | A private pathname is still an alias to a global kernel device. The current retention code cannot be represented as the missing preconfiguration issuer. |
| `production_runtime_capex_custody.rs` | `MissingOriginalTargetIssuer` is an empty enum, and the required association cannot be constructed. | This correctly fails closed. Keep it unconstructible until genuine native evidence exists. |
| `production_namespace_apexd_ioctl_request.rs` | Requires a real S_IFBLK O_RDWR target; the normal configure request requires a nonnegative source FD, retains source custody and uses F_DUPFD_QUERY. | The `fd=-1` support probe needs a separate typed request path. It is not a malformed normal configure request. |
| `production_namespace_apexd_execution_identity.rs` | `ActualApexdGeneration` contains `wire::Notification` along with actor/epoch fields. `ActualApexdTask` can be a nonleader worker, using PIDFD_THREAD. | Probe and normal configure need different fresh notifications while retaining a stable verified actor/epoch and OFD association. A leader-only lease is insufficient. |
| `production_apex_seccomp.rs` | Notifies loop/dm/block ioctl classes plus selected namespace/mount calls. There is no open/openat notification and no target-delivery ADDFD protocol. | Do not assume the current filter can inject a block FD at the original open. Prefer real private device nodes; an ADDFD alternative is a separate audited protocol change. |
| `kernel/p4_guest_mntns.c` | Holds exact kernel references, but capture requires a single-threaded leader, consumes a one-shot grant and expires after 5 seconds. | Its held-reference pattern is useful. Its ABI and lifetime are not a reusable multithreaded APEX device lease. Do not relax that grant. |

ublk provides a different block userspace-server interface; its inspected block operations do not implement the original loop ioctl ABI. Device cgroups govern access to device types/numbers; they do not create private loop instances or confer same-OFD custody. Neither is a substitute without additional native work.

## 4. Minimum native architecture

### 4.1 Objects and authority

Introduce a separate controller-owned private realm, private control object and real loop-backed gendisk instances. Allocation must not come from ordinary user-visible global GET_FREE semantics. Device numbers may still identify kernel objects, but possession of a device number or mknod permission must never be sufficient authority to operate a private target.

The controller is the existing broker, bound by held task/credential/namespace references. The original actor is the independently verified original apexd task/epoch, including nonleader worker identity where required. There must be no public constructor from a numeric PID, copied JSON, caller-supplied success bit or path. Use real retained kernel objects and kernel-generated generations; define how actor exit, exec/credential changes and namespace/mount-graph changes invalidate the lease.

Expose the real private control/block nodes in the original controlled mount construction, before sealing the default graph. The original binary should use its normal open/ioctl paths. A global device alias, anonymous regular FD with a block-like name, or a preconfigured backend target cannot satisfy this contract. A true S_IFBLK file can be created by the block core, but any such creation must preserve block open, holder, LSM and release semantics.

An alternate seccomp open/ADDFD delivery path is not currently implemented. If adopted, it needs complete openat/openat2 path resolution, dirfd and symlink rules, notification invalidation, file receive/LSM validation and same-task delivery. It must not be treated as an incidental helper for this design.

### 4.2 Semantic ABI draft

These names specify required semantics; they are **not allocated ioctl numbers or a committed UAPI**. Final numeric ABI allocation requires kernel review.

| Operation | Required real inputs | Required effect / bound result |
| --- | --- | --- |
| Create realm | Existing controller capability, original actor pidfd/task identity, verified namespace/root/mount epoch handles, fixed resource limit | A controller lease bound to held objects. No general host device authority is delegated. |
| Private control ADD / GET_FREE | Original native control OFD, original arguments and current actor | Same original loop-control semantics within that realm; target belongs solely to this epoch. Exact allocation/index behavior must first be verified. |
| Observe/open target | Original native real block OFD | Retain its true OFD and target generation before the support probe; independent aliases cannot adopt it. |
| Native support probe | Original pending request, exact zero body with source fd=-1, same original target OFD | Invoke the real core and preserve its EBADF result without consuming the later source-binding grant. |
| Arm exact backing | Retained original read-only source OFD, complete source comparison, immutable sealed backing, exact checked geometry, same target | One-shot association authorizing only this source/geometry on this target. Builtin image custody is a separate required path. |
| Native configure | Fresh original request, same target OFD and armed source/geometry | Real loop configuration. Lost/ambiguous completion retains all custody; it is not interpreted as an unbound device. |
| Revoke / query retirement | Held realm/target references | Stop new work, drain actual graph and I/O references, clear/unbind and return real state. Retirement completes only after actual references and aliases are released. |

Use version/size fields, reserved-zero checks and fixed widths. Do not accept arbitrary paths, arbitrary ioctl numbers, arbitrary capability masks or caller-chosen identity/epoch values. Check 32-bit compat explicitly. A query can report native state but does not become a transferable replacement for held authority.

### 4.3 Mandatory kernel coverage

A patch limited to `lo_ioctl()` or the driver's `open()` is incomplete. The pinned 6.18.64 call sites below must be accounted for in the patch review and native tests.

| Source / native entry | Required review |
| --- | --- |
| `drivers/block/loop.c`: `loop_add`, `loop_control_get_free`, control ioctls, `loop_configure`, loop data path | Separate private instances from ordinary global allocation; preserve real probe order; bind source/geometry exactly once; serialize configure/revoke with native loop state. |
| `block/bdev.c`: `bdev_open`, `bdev_file_open_by_dev`, `bdev_file_open_by_path` | Cover path and in-kernel opens, holders, reference ownership, aliases and teardown. `bdev_file_open_by_dev` uses a real block inode and standard block fops. |
| `block/fops.c`: `blkdev_open`, `read_iter`, `write_iter`, mmap, splice, fallocate, fsync, uring paths | Gate real file operations, including buffered/cache and direct paths. An initial narrow feature may deny unsupported raw mmap/splice/uring only after proving the unchanged original workload does not need them. |
| `block/ioctl.c`: native and compat common ioctls before the driver callback | Cover generic destructive/mutating ioctls, not only loop ioctls. BLKRASET occurs here before driver dispatch. Preserve its real permission/result behavior. |
| `block/blk-sysfs.c`: `queue_ra_store` and relevant attributes | Gate actual private-device sysfs writes; ioctl checks do not cover this path. Preserve inode/queue identity through the original fallback. |
| `include/linux/blkdev.h`, `block/blk.h` | Define a lifetime-owned internal authorization association and entry gates. There is no existing comprehensive per-OFD private-loop authorization hook. |

Do **not** put the new capability in `file->private_data`: the pinned block code uses this for exclusive-holder semantics. The correct association needs its own reviewed ownership/refcount structure. Keep a separate disabled-by-default feature boundary until the complete path exists; a generic hook alone must not expose a new private device.

Asynchronous I/O and dm/filesystem graph users must be authorized by retained lease/graph references. Checking `current` in a workqueue is wrong: legitimate completion executes outside the original task. Conversely, authorizing the original task once at open is not sufficient for revocation, fd transfer, a second alias, mmap or an existing page-cache path.

### 4.4 Retirement is part of the interface

On owner death, expiry, exec/identity change or an invalid request, stop new configuration and graph admission. Preserve source, target and controller references across in-flight configuration, I/O and unknown results. Wait for real completion or query actual state; never infer unbound from a syscall failure. Stop/reap the owning Android graph and release real mounts/graph users before claiming retirement. Buffered data and already-mapped filesystem pages require graph retirement; a raw block mmap prohibition does not by itself solve that problem.

Only after real graph/I/O drain and native unbind may the original/sealed source custody be released. Unlinking a node or closing one FD does not prove that every alias, holder and reference is gone. A terminal empty query must be tied to the same kernel generation and observed after closure. Failure or ambiguity retains evidence and resources for supervised reconciliation rather than reporting cleanup complete.

## 5. Rust integration and first source task

### R0 — concrete first implementation task (no kernel dependency)

Work in a new isolated checkout of the exact source references; do not edit the r21 vendor producer. Start with `runtime/droidloom-supervisor/src/production_namespace_apexd_execution_identity.rs` and its existing tests.

Extract a private `ActualApexdActorEpoch` value from the existing `ActualApexdGeneration` fields **other than notification**: `original`, `identity`, `tgid`, `proc`, `pidfd`, `executable`, and `default`. Retain those exact fields and all their current validation, held handles, deadlines, credentials, cgroup, namespaces, root and successor-graph checks in the owning task. Make `ActualApexdGeneration` contain this stable value **and** the unchanged `wire::Notification`; full request equality must retain both. Do not add a public constructor or serialize live authority.

Add an internal structural same-actor/epoch comparison that grants no live authority. Do not expose it as a cross-request acceptance token. The completed probe notification will no longer be pending when the same worker issues normal configure; therefore requiring both old and new requests to remain pending would not implement that sequence. Keep every existing pending/deadline check unchanged. A genuinely retained live actor/target lease independent of the completed request belongs to R1 plus the new native interface, not to this value decomposition. If the original program uses different worker threads, explicitly establish that relation from original execution and extend the contract through a separate review. Do not silently broaden an exact thread identity to a whole TGID.

Add focused tests that distinguish: same actor / different fresh notification; different actor/epoch with coincident notification; changed pidfd/proc/executable/default graph; stale or replayed notification. Retain the existing native request validation unchanged. Keep `MissingOriginalTargetIssuer` empty. Acceptance for R0 is a reviewed source diff plus focused source tests and unchanged fail-closed issuer behavior; it is **not** native kernel or Android success.

### R1 — typed requests and custody, after R0

Introduce distinct private types for the exact support probe and normal configure. Preserve each request's fresh pending notification and deadline; use the real PIDFD_THREAD identity and target OFD capture. Probe parsing must accept only the exact native fd=-1 zero body and must not try to obtain a source FD. Normal configuration keeps the original read-only/O_DIRECT source custody, complete comparison and checked geometry. F_DUPFD_QUERY and the new kernel target generation are complementary checks, not alternatives.

Prepare this code behind the still-unconstructible native issuer. Do not call the normal positive constructor from model facts, tests, booleans or hashes. A successful native probe followed by actual same-OFD configuration is the only eventual positive path. Revalidate actor, epoch, pending notification and all held custody immediately before dispatch and before returning a result.

### K0–K3 — reviewed native patch series

1. **K0, internal lifetime/gate foundation:** introduce the dedicated private-loop lease type and authorization association, with no exposed allocator. Add the complete entry-hook coverage from section 4.3; normal devices must retain existing semantics. Include internal state/refcount tests and static call-path review. Do not overwrite block holder fields or pretend existing namespace grants suffice.
2. **K1, private allocation/control:** create the separate realm and real block/control objects. Confirm original control-index behavior and supported operation set before publishing UAPI. Hold original actor and controller references; cover aliases and by-device opens. This depends on K0 and still stays disabled outside isolated qualification.
3. **K2, native loop/configuration and graph custody:** connect the real `loop_configure` probe/configure path, one-shot exact source arm, native read-ahead/sysfs paths, and explicit dm/graph lease propagation. Kernel/file/graph ownership must be unambiguous on every failure edge.
4. **K3, teardown and race completion:** implement exit/revoke, pending native result reconciliation, asynchronous I/O drain, native clear and terminal generation-bound retirement. Exercise memory and race diagnostics in an authorized environment before enabling the feature.

### R2 and Q — bind and qualify

Only after K0–K3 exist and pass isolated native tests may the Rust implementation replace the empty issuer with a constructor requiring the real kernel lease, the original target OFD and both actual native results. Preserve builtin image and sealed CAPEX source distinctions. Then run unchanged CP3A original apexd in its original default graph, followed by the independent AVB/dm/mount/runtime gates. App and cleanup readiness must remain false until their own real acceptance completes.

## 6. Required acceptance and falsification

| Gate | Actual positive evidence required | Required negative evidence |
| --- | --- | --- |
| Source R0/R1 | Fresh requests preserve one actor/epoch and exact OFD custody without reusing notification identity | Identity/epoch/notification changes, replay and malformed probe cannot construct authority; issuer remains unavailable without native interface |
| Real private object | Real S_IFBLK, O_RDWR original target, isolated allocation/control semantics and native owner-bound generation | Ordinary host loop/control FDs, unauthorized aliases/mknod, another realm, reused device number, unauthorized received/reopened FD and wrong task rejected |
| Probe | Unchanged original request causes actual loop-core -1/EBADF for exact fd=-1 body | ENOTTY, EACCES, fabricated replies and errors from source-FD duplication do not qualify; probe does not consume configure grant |
| Configure | Original same OFD, complete preserved source custody, exact original geometry and native success; native status/readback agrees | Source or geometry substitution, overflow, stale notification, revoked owner, changed mount graph and second configure fail closed |
| Generic operations | Every necessary operation on the authorized target/graph works with actual permissions | Generic/compat ioctl, mmap, splice, io_uring, by-dev/path opens, aliases and sysfs cannot bypass the realm; no host-global device mutation |
| I/O and teardown | Real graph reads and completion drain; actual unbind and reference retirement before source release | Owner exit/configure race, FD passing, queue completion, source closure, pending/unknown result and cache/mapping cases cannot free custody early or return success |
| Original APEX path | Original init/apexd bytes, required private graph, real read-ahead, dm-verity, AVB and mount outcomes | No policy weakening, host-global loop export, fake errno, dummy backing, original byte edits or substituted corruption mode |
| Full deployment | Independent Android boot/service, original data/metadata continuity and current app business-case receipts | Model/source tests, CI artifacts, basic kernel probes or successful image preparation cannot increment runtime-qualified apps |

The supplied model checks protocol invariants under assumed native facts. Its finite search is limited to the declared 19 events, a maximum of two graph and two I/O references, fixed notification values, and a fixed identity/source/geometry set. It has no memory-order, scheduling, LSM, block cache, device, real errno or kernel race semantics. The targeted model tests add specific invalid-input variations; none replace the native matrix above.

## 7. Existing full Android VM alternative: read-only conclusion

A bounded complete scan of the current producer `runtime` examined 208 selected Rust/TOML files (4,577,835 bytes, 238 entries) for qemu/crosvm/KVM_CREATE_VM, `/dev/kvm`, cuttlefish and microvm. It found zero matches. The architecture document describes shared-kernel namespaces. The pinned threat model explicitly says hardened VM mode is separately designed. The docs search also found Cuttlefish source-build projection references; these are build inputs, not evidence that a full Android VM runtime exists.

The inspected kernel qualification VM is a diskless 2-vCPU/768-MiB mechanism fixture, with no guest disks/network, basic Binder/grant/context probes and shutdown. Its guest init does not boot original Android/apexd. This cannot be reported as an available production Android backend. The docs search hit its result cap; this statement is deliberately limited to the pinned runtime coverage, explicit documents and inspected fixture, not an exhaustive claim that no VM-related file exists anywhere.

A conventional VM could give Android its own loop/dm devices and avoid the shared-kernel private-loop interface. Existing evidence does not establish a ready backend, usable guest boot kernel/initramfs, compatible official image boot configuration, graphics/input/audio/network integration, or safe existing data/metadata attachment and continuity. Those are required deliverables, not properties conferred by choosing QEMU. The official GSI/system image alone is not proof of a bootable integrated VM deployment.

Before a VM route is considered shorter, obtain an exact existing full Android guest boot artifact and backend source, verify its intended device model and original CP3A compatibility, demonstrate that ordinary permitted host permissions already suffice, and provide an explicit data/metadata continuity design. Then an independently authorized actual boot is required. This packet performs none of those actions. A known-good existing backend might shorten the loop isolation problem, but no such backend has been identified in the inspected current source. Creating that backend is also a multiweek integration project; giving it a more precise schedule without those artifacts would be speculation.

The previously rejected privileged patched-kernel VM fixture remains prohibited. Do not rerun it, rename it, change execution tools or claim the conventional VM discussion as permission to bypass that rejection. This comparison is architectural feasibility only.

## 8. Work estimate and handoff boundaries

Estimate: **2–4 engineering weeks for two experienced kernel/runtime engineers** to implement and validate the native interface, assuming an authorized isolated environment and no new original-binary ABI surprises. Basis: roughly 1–2 days for R0/R1 and original control contract; 5–8 days for private allocation, block entry coverage and lifetime/graph integration; 2–3 days for runtime binding; and 3–5 days for genuine negative, lifecycle and race qualification, with some parallelism and review overhead. These are planning ranges, not measured completion times or a promise that the complete platform will be production ready in that period.

This turn completed read-only source analysis and the pure model. It did not implement K0–K3, change production code, load a kernel, boot Android/VM or qualify an app. The active r21 vendor/source build has separate ownership, budget and locks. Preserve its fixed source cohort, all data/metadata, original binaries, security requirements and failure records.

The next worker can execute R0 in an isolated checkout using `INPUTS.json`, keeping the current issuer unavailable. Native execution remains dependent on a reviewed complete patch and an independently permitted qualification environment. Do not issue an automatic retry for an action already rejected by approval review. Do not translate the supplied model's result into a CURRENT runtime success, production-ready claim or cleanup authorization.
