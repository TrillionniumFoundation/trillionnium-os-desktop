# C14 private writable-proc EACCES: bounded read-only review

## Finding and credit boundary

The r3 private control still failed. Its authenticated failure is stage 4, source line 472, errno 13, at the first O_RDWR open of /proc/1/oom_score_adj. No write or SELinux-xattr observation was reached. The original stdout remains 0 passed / 1 failed.

The same owned proc mount was already changed from ro to rw, while the fixed global proc submounts remained ro. The narrow source-supported explanation is a pre-exec credentials / memory-user-namespace mismatch: changing mapped credentials makes the inherited mm non-user-dumpable; cloning PID1 preserves that mm's user namespace; proc assigns a 0644 OOM inode to root of that earlier namespace. Mapped guest root has neither owner-write access nor a DAC override for an inode whose UID/GID are not mapped into its current user namespace.

This explains the observed open failure without changing any global DAC, MAC, mount policy or user data. It is a source-supported causal explanation, not a claimed direct observation of the dead child's dumpability, fsuid or inode ownership. Those fields were absent from the original failed control.

No private control, mount, Android boot, compilation, policy change, owner-source edit or CURRENT edit was performed for this review. OOM writable-proc, xattr, Android runtime and production-ready credit remain unqualified.

## Exact observed generation

| Input | Identity |
| --- | --- |
| C14 writable-proc child | 18,335 bytes; SHA256 ad24ed2a2c984b8bd44cb5be4aa7c768ccd0f3cf4b6d56f6b10a4fd82bbd1933 |
| C14 namespace lifecycle child | 27,915 bytes; SHA256 af77e882eba8e32d13657e29b363b07c4de68fce5e4e3efedb055c5ab700eda2 |
| r3 stderr | 5,702 bytes; SHA256 fa33bdac8fe6a8a430cb3b01b6e2c2c3c0a88c9c7ffbc1e5b337e0dba8673573 |
| r3 stdout | 314 bytes; SHA256 2e4070a465f2aa2a55e7ca6f3ad2465710ddfeae3867299c0bbf703d1e0cf90f |
| Host observed release | 7.0.14-p4cred1 |
| Host read-only sysctl observation | fs.suid_dumpable=2; overflowuid=65534; overflowgid=65534 |

The last read-only owner check found r14 as the latest matching frozen source directory and the active writable-proc child still at ad24ed2a.... This is a point-in-time observation, not an indefinite ownership claim. Source identity, current host values and directory inventory are preserved in evidence/host-owner-current-original.stdout and evidence/c14-lifecycle-original.stdout.

The failing child source is retained byte-for-byte as evidence/c14-writable-proc-child.rs. It is the C13 local exact preimage whose identity also matches C14's remote record. Original failure text was extracted byte-for-byte from the parent's raw collection r6-review/proc-response-r14-failure-original.json (74,770 bytes; SHA256 b2627b0b856cebb0fd06866a27651254405048adf5149292ce014dc64d841284).

## Kernel source chain

These are excerpts from the actual ai395 build tree:

/home/qq/work/pocket4-kernel-binder-cred-20261108-8b88-r1/build-r1/source-parent/linux-source-7.0.0

| Step | Actual source behavior |
| --- | --- |
| C14 child lines 513–526 | unshare(CLONE_NEWUSER), wait for mapping, setresgid/setresuid(0), then re-arm parent death and set NO_NEW_PRIVS |
| C14 child lines 751–770 | the later isolated PID1 clone does not create another user namespace or perform exec |
| kernel/cred.c lines 381–400 | changed effective/fs IDs or privilege subset cause set_dumpable(mm, suid_dumpable) before publishing new credentials |
| kernel/fork.c lines 1525–1538 | dup_mm copies the old mm and calls mm_init with the old mm->user_ns |
| kernel/fork.c lines 1142 and 1164–1173 | mm_init retains its supplied namespace; a newly allocated mm instead takes current_user_ns |
| fs/proc/base.c lines 1861–1917 | task_dump_owner uses mm->user_ns root when get_dumpable(mm) != SUID_DUMP_USER |
| fs/proc/base.c line 3361 | oom_score_adj is a regular 0644 entry with ordinary inode permission behavior |
| fs/namei.c lines 433–490 and 516–558 | owner/group/other DAC applies; failed DAC needs a valid scoped capability override |
| kernel/capability.c lines 455–480 | DAC override requires both inode UID and GID to be mapped into the caller's user namespace |

The failed call is open, so __set_oom_adj's later write-time CAP_SYS_RESOURCE condition is not the observed cause. Hidepid denial is also a distinct source path: proc_pid_permission returns ENOENT/EPERM there, while this open reported EACCES.

The existing source permits the mapped guest root / inherited-mm mismatch. A PR_GET_DUMPABLE value and held inode metadata from the failed generation were not recorded; therefore the actual owner-ID and MAC contribution cannot be retrospectively certified. The static DAC chain is sufficient to explain the reported failure under the current non-user-dumpable setting; it does not justify claiming an independently observed LSM allow/deny decision.

### Binding to the running release, with limits

The retained original provenance chain is:

1. kernel-input-preparation-original.json: the original preparation failed only at missing certificate input, and remains labelled PREPARATION_FAILED. It records Ubuntu-7.0.0-43.43, peeled commit f53b359683af7918c5436499948763cb726d5082, exact source .deb SHA256 208b9997b555c9494535edd0dee6f0ee67a7ccddc180fb40c30218f06bd2dc59, and source tar member SHA256 e2d3ecb74dabd037458e173f53a9b2eaced0039f65594c7ed38e60d3e6bab7ab.
2. kernel-input-continuation-r2.json explicitly pins that failed preparation, completes the missing inputs and preserves its failure history.
3. kernel-configuration-r3-result.json pins the input continuation.
4. kernel-full-r7-result.json pins configuration r3, records successful normal commands with make -C exactly the audited source directory, release 7.0.14-p4cred1, and pins kernel-artifact-manifest.json.
5. That manifest binds the resulting bzImage and copied vmlinuz: 17,134,080 bytes, SHA256 83d50d51be0f6a2d574f6b04ab80205613383c60da7b96788c9c3122efb7b5ad.

The current source Makefile and generated kernel.release also report 7.0.14 / 7.0.14-p4cred1. The current host uname agrees. This review used the actual recorded build tree, not a floating or nearby upstream branch. It did not recompute the full source archive or read a running-kernel build ID; it relies on the preserved build/install provenance for that last binary attribution. The unpacked source tree has no .git marker. The initial rev-parse attempt failed and its raw stderr plus failed H receipt remain preserved; it is not presented as a successful Git HEAD verification.

## Narrow patch advice for the owner

The safe immediate change is diagnostic-only and must leave the failed OOM obligation failed:

- At the original single open attempt, retain the original errno before any extra syscall. Do not retry an uncertain request or turn the failure into success.
- Add a bounded, authenticated test-only observation of PR_GET_DUMPABLE and fixed own-PID1 credentials. Read the exact OOM inode with O_PATH/fstat or equivalent no-follow metadata, and compare through the parent's already held proc-directory/PIDFD authority and exact UID/GID mappings. Report guest-view overflow and host-view IDs distinctly; a 65534 presentation is not evidence that the inode truly belongs to a mapped guest account.
- Preserve nonce, SCM credentials, owned PIDFD, mount inventory, shared work deadline and independent cleanup requirements. Record the precise new executable/source identity. The original r3 receipt must remain failed.

No unconditional PR_SET_DUMPABLE(1), chmod/chown, added ancestor capability, alternate user-data permission, LSM exception, or self/comm success should satisfy the OOM gate. The kernel's special self-thread comm permission was inspected only to understand the difference; it is not an adopted substitute.

A functional solution must be evaluated in the intended lifecycle. The present pre-exec raw child intentionally inherits the supervisor's mm provenance. A future verified, fixed-image exec can allocate a new mm in the current mapped user namespace, but its actual exec result, final credentials/capabilities, dumpability, exact inode ownership, LSM context, PIDFD/namespace identity and descriptor closure must be observed. A namespace FD alone identifies the current credential namespace, not mm->user_ns. Do not relabel pre-exec preparation as post-exec or Android qualification.

After an authorized final exec, retain the original OOM test obligation: one fixed own-PID1 O_RDWR open, bounded original read, same-FD write-back of the original value and exact readback, within the work deadline. The actual Android OOM adjustment range is a separate obligation. fs/proc/base.c lines 1130–1133 rejects a value below oom_score_adj_min without capable(CAP_SYS_RESOURCE), and kernel/capability.c lines 414–416 targets init_user_ns. Guest-root capabilities alone do not establish this right. No such adjustment or policy change was attempted here.

## Evidence and tests

The seven remote jobs are read-only inspections. Six succeeded with exit 0, complete and durable output. The initial symbol scan ended exit 1 when rev-parse was attempted in the unpacked source tree; its already printed source hashes and its error are retained separately. These jobs are not tests of writable-proc or Android.

No normal tests were rerun because this delivery changes no executable implementation. All runtime and production gates remain false in INDEX.json. FILES.json freezes the deliverable bytes and preserves the original integer-valued JSON receipts without lossy reserialization.
