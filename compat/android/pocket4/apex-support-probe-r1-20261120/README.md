# Original apexd support-probe request, R1

This is an isolated source successor for one supervisor file. It prepares a
strictly typed observation of the original `LOOP_CONFIGURE` support probe.
It has not been compiled or executed, performs no Android/kernel/VM action,
and closes no native APEX or application qualification gate by itself.

The active native/Calendar/Gallery/R0/vendor CI cohort is separate. Do not add
this patch to its already frozen input inventory or reuse that cohort's report
as evidence for these new bytes.

## Exact baseline

Apply `R1.patch` to the complete, verified producer source only when this file
matches its recorded preimage:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `runtime/droidloom-supervisor/src/production_namespace_apexd_ioctl_request.rs` before R1 | 34,826 | `5edb3ce4e4463c798a7a345b120cba1776831e5af00485403b1b8dfd9d171e5c` |
| Same file after R1 | 47,488 | `2a407538975749c59f92fc858d22f803236cd130f6f9bd8e8a5d1ee86e6bc5a9` |
| `production_namespace_apexd_execution_identity.rs`, required reviewed R0 assembly baseline | 35,481 | `a58fe068c65cb0a763dc4457501e31739034569338d778a755a1c88aef35760d` |
| `production_namespace_default_mounts.rs`, R0 test fixture baseline | 41,934 | `737c6334bbf840fe8ec4dd2ec3313b67cd51454b2ee0e6bde6eff956fb6590e3` |
| Untouched `production_runtime_capex_custody.rs` | 35,626 | `5797c0091639b7ae77af37d58c91a570be4b3e187ace9d18b08a2f0712416502` |

The request preimage is the verified 2359 body retained unchanged in the
complete 2360 source inventory, associated with repository snapshot
`1af163b21f5c7dcaaf94084d7cc1ef19aed05ae1` and producer content tree
`56548053c91840f2dd3de50db45b705069d35fa9`.
These are source provenance references, not a claim that the current CI has
passed or that the new producer has been installed.

The applicable producer `AGENTS.md` is 4,088 bytes, SHA-256
`eac22deaa59d6906afe7eef3dfc9696fbacf20e71a90590608d744b096a8ff46`.
No additional production module or re-export is changed by this increment.

## Implementation

`SupportProbeBody` accepts exactly 304 bytes: the first four bytes encode
`u32::MAX` (the original source `fd=-1`), and the remaining 300 bytes are zero.
No other negative descriptor, flags, block size, reserved field or payload is
accepted. This parser classifies bytes only; it cannot construct task or target
authority.

`OriginalApexdIoctlRequest::original_loop_support_probe` uses the already
received original request and the same observation journal as normal configure.
It moves the journal from `Fresh` to `Entered` before fallible observation.
Any failure keeps the request incomplete; no retry or fallback to normal
configuration is possible. Only a successful full bookend reaches `Complete`.

The new custody contains the exact notification, full request generation,
default mount binding, existing deadline, strict probe body, and the original
ioctl target's retained file description. It duplicates only the nonnegative
target descriptor from notification argument zero, through the original
`PIDFD_GETFD` helper and the actual thread pidfd. The probe's source `-1` is
never passed to descriptor duplication.

The target must be a real block file opened `O_RDWR` without `O_PATH`; its
retained duplicate must have `FD_CLOEXEC`. The latter checks the duplicate's
descriptor flags, not a separately observed flag on the guest descriptor.
Revalidation compares the complete original
notification/generation/default/deadline, repeats actual task and owner checks,
compares full configuration-memory bookends, duplicates the same original
target again, and requires `F_DUPFD_QUERY` to identify the same open file
description. A same-inode reopen is insufficient.

`ObservedApexdLoopSupportProbe` exposes cached bytes and request-bound
revalidation. It exposes no target handle, source descriptor, issuer, native
ioctl, notification reply or success/errno constructor. A retained observation
is not a live lease. A later request with another notification cannot reuse
this journal. No `same_actor_epoch` comparison is used to grant authority.

Normal `original_loop_configure`, `source_number`, source custody, CAPEX
matching/binding, complete request validation and retirement remain unchanged.
The empty `MissingOriginalTargetIssuer` remains uninhabited in its completely
untouched source file. The existing production dispatch still has no usable
private-target provider or reply lane; this patch does not wire around it.

## Verification performed

`STATIC-VERIFICATION.json` records exact input/output/patch hashes and these
actual checks:

- The delta consists of eight insertion regions. Removing only those additions
  restores every byte of the original 34,826-byte file.
- Sixteen protected function bodies, including normal configuration, source
  duplication and complete base revalidation, compare byte-for-byte equal.
- All five original focused tests remain byte-identical.
- Forward `git apply --check`, actual forward application, reverse
  `git apply --check`, and actual reverse application succeeded in a fresh local
  temporary tree. Both resulting file bodies matched their pinned hashes.
- Static inspection of the two new custody paths found only `target_fd` and
  `custody.target_fd` passed to `copy_task_fd`. No source duplication, native
  ioctl, fabricated errno or cross-request actor authorization was added.

The six newly written Rust tests cover exact 304-byte classification (including
all 2,432 single-bit corruptions), normal/negative descriptor separation, eleven
invalid notification headers, changed/short/expired memory, failed/completed
journal replay, and ordinary temporary-file controls for same-inode/different
OFD and nonblock/readonly/`O_PATH` targets. These tests have **not** been executed.
The temporary-file controls are not positive block-device or native probe
evidence.

## Next executable steps

1. Independently review the one-file patch and require the exact recorded
   preimage plus reviewed R0 assembly inputs. Re-run its forward/reverse checks
   in a new source workspace; do not modify any active vendor/source tree.
2. Construct a separate complete-source CI successor. Add the six exact test
   names to the actual compiled catalog and run the changed supervisor tests
   with the original resource limits and at least two logical CPUs reserved.
   Then run the required complete ordinary/release cohort. Do not infer test
   success from this static verification.
3. Recalculate the complete successor test count from the accepted predecessor
   and actual catalog. The frozen native publisher currently binds 1,588
   ordinary cases; a later full release that includes these six tests requires
   its own reviewed catalog/count update. Do not reuse an old report, relax the
   publisher's exact count check or modify the currently running cohort.
4. Keep runtime admission closed while the private target provider is absent.
   Implement and qualify the real owner-bound private loop/control allocation,
   generic block-entry protection, lifetime and revocation interface described
   in the design referenced below. No userspace probe result can substitute for
   those capabilities.
5. Only after that native interface has its own accepted positive and negative
   qualification should a separate change connect this observation to the
   genuine original probe, preserve its real native `EBADF`, and retain the
   same target OFD for a new normal configure request. That integration needs a
   real retained actor/target lease independent of the completed notification.
   It must preserve fresh pending-ID, task/epoch and deadline checks on each
   request, as well as the original AVB/dm/mount gates.

The previous automatically rejected privileged VM fixture must not be retried
as part of these steps. This packet authorizes no new VM, host block node,
kernel load/install, reboot, Android launch or security-policy relaxation.
The native positive/negative qualification environment remains a separate
prerequisite; this source patch does not manufacture it.

Architecture and acceptance dependencies are preserved in
[Draft PR #319](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/319),
exact design revision `1b0b94c516e0c22dc70f82bfa93544ac8ce510ac`.
The multiweek native-subsystem estimate in that design is distinct from this
completed source preparation.
