# Pocket4 Android closeout continuation

Current state: **`KERNEL_PAYLOAD_MENU_INSTALLED_OLD_ANDROID_MASKED_NATIVE_AUDIO_REPAIR_FINAL42_RUNTIME_PENDING`**.

Pocket4 is the Linux host running Droidloom Android. The repaired
`7.0.14-p4cred1` kernel, its signed module tree and normal GRUB entries are
now physically installed. The host is still running `7.0.0-38-generic`;
that release remains the default, and no one-shot boot has been selected.
Both old Droidloom autostart entrances are persistently masked and independently
verified. Original Android data remains closed and unchanged.

Native600 and Audio425 source repairs have advanced through normal verification,
but neither has qualified complete production artifacts. The selected Android
cohort and applications remain **0/42 accepted**. **Production ready, runtime
qualified, final candidate deployed and all blockers closed remain false.**

The [current state](continuation/state.json) records exact receipt hashes.
[The prior state](continuation/history/state-before-kernel-stage-20261109.json)
is preserved byte-for-byte. Other historical observations retain their original
scope. Source checks, off-device builds, copied evidence and CI do not establish
device runtime acceptance.

## Qualified kernel and normal startup inputs

The [AppArmor credential repair](../apparmor-binder-retained-credential-r1/README.md)
adds the normal `cred_getsecid` hook to the official Ubuntu source. It reads the
label from the credentials retained by Binder's file descriptor. It does not
substitute the calling task's current credentials, bypass Binder security
context requests, or disable AppArmor.

The normal complete kernel build produced `7.0.14-p4cred1` while preserving the
original configuration features. All **6,901 core modules** were built,
installed and signed through the normal compiled kernel signer. Independent CMS
verification checked every module against the exact compiled public certificate
and checked that every unsigned payload remained unchanged. Actual modified
payload and modified signature controls were rejected. The private signing key
remained in place and its body was not copied or published.

Four real diskless KVM controls compared the original kernel with the repaired
one. Plain Binder IPC passed on both. The original kernel failed all three
security-context cases with `BR_FAILED_REPLY` and `-EINVAL`. The repaired kernel
passed all four transactions, including a descriptor opened under profile A/root
and used after changing to profile B/UID 10001: the receiver obtained the retained
A label. A newly opened descriptor returned B. Both AppArmor profiles enforced
policy and an actual forbidden file open returned `EACCES`. The QEMU processes,
units and cgroups retired; host kernel, policy and original user images remained
unchanged. The capsule includes the exact patch, C/header and guest policy
sources, plus compact [validation records](../apparmor-binder-retained-credential-r1/validation.json).

### Hardware and module compatibility

The current hardware inputs have been checked against the candidate. The **198
loaded module names** map to 196 signed core modules, one component that is
normally built into the new kernel, and one external camera module. The external
`v4l2loopback` **0.15.4** was taken from its official source commit, built against
the exact candidate, signed with the same key, and checked with the same positive
and tampered CMS controls. Its 93 imported symbol versions match.

All **6,902 core and external modules** were checked against the kernel's actual
symbol versions, including extended Rust symbol version sections. An initial
`qt2025` warning came from a tool that read only its ordinary symbol table; its
full ELF sections match the kernel. The original failed report is retained and
the later complete verification has a separate identity.

PCIe port support is linked into the actual kernel. The firmware audit checked
20 compressed streams, including GPU, Ethernet, Bluetooth, Wi-Fi and NPU inputs.
Tracing the actual AX210 device selection showed that it requests firmware API
89; the generic API 100 declaration is not the selected hardware path. The
existing API 89 firmware and PNVM are present and valid. This qualifies deployment
inputs; it does not claim that the new kernel has operated the host's hardware.

### Normal initramfs and real root startup

The complete candidate module tree was transferred and independently read back.
Normal `depmod` generated its indexes. Normal `mkinitramfs`, `lsinitramfs` and
`unmkinitramfs` then completed in a restricted private unit with no warnings.
The unit could not reach real NVMe devices, the Android user images or host
control brokers, and could not load host modules or reboot the host.

The normal image contains **1,079 exact signed modules**. The NVMe modules are
present; ext4, jbd2 and mbcache are verified as built-in through the configuration,
`modules.builtin` and linked symbols. The normal init script, ext4 checker,
fsck front end and logsave program match their host inputs. A private copy of the
normal configuration explicitly selects ext4, matching the fresh host root
mount; the original host configuration was not edited.

The exact kernel and normal image were then booted against a newly created,
disposable **256 MiB NVMe/ext4** disk in an isolated VM. The normal initramfs
ran a forced read-only filesystem check through all five e2fsck passes and
switched to PID 1 on the read-only ext4 root. A separate guest observer checked
the real NVMe device path, root filesystem, normal fsck success stamp and complete
log. The actual QEMU process ran as UID 1000 with no capabilities, a 2 GiB cgroup
limit, two CPUs, no network and no host disk passthrough. It exited; the temporary
overlay disappeared; the base disk and candidate bytes remained unchanged.

This closes the offline startup-input gate. The subsequent host installation
has now completed, as described below; hardware operation under the candidate
and Android startup remain outstanding.

### Actual host installation and guarded startup

The transaction installed 6,918 module-tree files and five boot payloads.
A normal, restricted GRUB preview preserved the complete old menu bytes except
for two new candidate entries. The original fallback remains the default.
Normal `grub-script-check` passed before and after the menu commit.
An independent post-commit observer rechecked the complete candidate inventory,
the original boot files and the exact committed menu.

Two earlier previews remain failed records. The first could not traverse the
original home directory after dropping capabilities; the correction provided
only explicit private mounts. The second omitted a 66-byte locale block; the
unchanged old-menu validator rejected it. The final preview used the normal
locale setting and preserved that block. No generated menu was hand-edited and
the validator was not weakened.

The old system daemon and user presenter units are both masked through normal
systemd commands. Their vendor files, drop-ins and enable links remain intact.
Independent checks confirmed both owned masks, inactive units, unchanged
original data metadata, no data-image descriptors or loop consumers, and
unchanged existing voice and camera services. The masks must remain in place
through the guarded restart so that the old runtime cannot reopen original data.

Owned kernel and mask rollback requests are prepared. Neither has run.
The kernel rollback must first return to the preserved fallback if the
candidate is running. A one-shot GRUB choice does not reset a hung host.
Actual recovery access and the interruption of four running voice services
still require coordination. Existing service definitions and linger settings
have been inspected, but post-reboot recovery has not yet been observed.

## Native600: source qualified, complete r6 failed and retired

The [original provider closure](../native600-original-provider-closure-r1/README.md)
preserves the original 597 commits and adds the actual missing provider projects.
The [RKPD follow-up](../native600-rkpd-apex-r1/README.md) then selects the
complete six-file `apex` cone from the already locked RKPD commit.
It adds no placeholder module and does not enable missing dependencies.
The normal tool build, independent import, source verification and reconciliation
all completed. The RKPD source phase ran eight normal commands and retired
all owned children and locks.

The latest completed full build, **r6**, reached normal Soong **280/280**.
The RKPD failure did not recur. Soong then rejected two unresolved names:
`signature-common-javalib` from the CTS signature consumer and
`trendy_team_desktop_display` from the Cuttlefish vkms package metadata.
Their original sources and metadata are being repaired in a separate generation.

The failed build is fully retired. Normal source-after verification, projection
restoration, complete owned-allocation observation and all lock checks passed.
Peak memory was **7,878,389,760 bytes** under MemoryHigh 22 GiB and MemoryMax
24 GiB; high, max, OOM and swap counters were zero. These resource results do
not change the failed build outcome. Earlier r3, r4 and r5 failures remain
historical records with their own causes and receipts.

The frozen Native600 controls executed **67/67 on Linux** with no skips.
The current RKPD consumer executed **12/12 on Linux**. On the publication Mac,
the former ran 54 controls and explicitly skipped 13 Linux-only controls; the
latter ran all 12. No macOS result is presented as Linux lifecycle acceptance.
The complete engine/ART pair and its compatibility with the selected QPR1
cohort remain unqualified.

## Audio425: source and RKPD qualified, complete APEX pending

The [Audio425 source capsule](../audio425-original-provider-closure-r1/CAPSULE.md)
preserves the previous 321 project commits, adds 104 original projects and
expands 28 existing selections. Normal source reconciliation and verification
completed all **16 commands**, checking **425 projects and 1,518 original
Android.bp files** without external alternates. All owned processes and locks
retired.

This source-only run used a configured 4 GiB limit, recorded a peak of
**4,299,010,048 bytes** and **25,336 memory.max events**, with zero OOM and swap.
Its frozen source acceptance checks did not require a zero max-event count or
a peak below the configured cap. It passed those original source gates.
The full-build contract still requires its own strict peak, OOM, swap and
work-budget checks.

A separately qualified follow-up added the complete six-file RKPD APEX cone
from the same pinned project commit. All **17 normal commands** completed,
with **425 projects and 1,519 original Android.bp files**. Its own peak was
**1,661,616,128 bytes**, with zero max events, OOM and swap. These are separate
source observations; neither is a complete APEX or compiled-bridge result.

The next complete generation uses explicit MemoryHigh 22 GiB, the unchanged
24 GiB maximum, eight CPUs, six requested build jobs, Go parallelism two and
a 5 GiB Go budget. It requires fresh actual admission and full lifetime
measurements. The earlier APEX attempt, r7, failed on
`gemmlowp_headers` and remains failed. Its 102-file, 20,820,363-byte
canonical custody is retained until its replacement and consumers close.

The subsequent complete attempt, **r8**, failed before Soong. Its retained
original-provider guard compared the Connectivity service blueprint with its
original hash after two existing normal patches had already changed that file.
The failed result, exact patch chain and required preimage/postimage correction
are preserved separately. Source-after verification, restoration, all owned
processes and locks completed. Its peak was **497,692,672 bytes**, with zero high,
max, OOM and swap events. No Soong execution or complete APEX is claimed.

The allocation observer ran **17/17 actual Linux controls**. The Mac runner
reports 17 unsupported-platform skips and zero passes. Linux CI requires all
17 controls to execute. The
[canonical Audio importer](../audio-canonical-custody-r1/README.md) binds exact
local copies to complete original build, qualifier and terminal evidence;
its controls do not create or qualify an APEX.

The newly frozen capsules retain the observations at their individual creation
times. Later source completions and build failures are recorded in the common
current state without rewriting those sealed snapshots. Generated SDK,
AIDL/HIDL, namespace and conditional dependencies remain subject to the actual
normal build rules and final artifacts.

## Android cohort and production isolation

The official [GSI releases page](https://developer.android.com/topic/generic-system-image/releases)
was checked on **9 November 2026**. QPR1 remains the latest listed stable channel;
QPR2 and QPR3 are beta. The selected
[QPR1 release](https://developer.android.com/about/versions/17/qpr1/gsi-release-notes)
is **CP3A.260905.010 / 16176746**, with September security metadata. This does not
establish November security coverage or CTS-approved deployment.

The official ART, bionic, APEX, framework and libbinder identities are preserved.
The earlier empty-data Android probe failed on the Binder credential path and
fully retired. The new kernel's isolated success does not retroactively turn
that Android attempt into a successful boot.

The production backend, mapping and seccomp remain unqualified. The existing
65,536-ID subordinate allocation is smaller than the required 100,000 IDs and
is already used by unrelated active namespaces. No ranges, accounts, registry
or host policies have been changed.

The [production identity source](../production-identity-reservation-r1/README.md)
now passes 19 focused tests and ten normal tool commands. It keeps authority
inside a nonserializable lease, checks a distinct account and private group,
rejects aliases and overlapping grants, and holds root-anchored reservation
locks. An actual sealed normal binary refused the missing dedicated account
before creating any registry or map.

Successful enumeration alone does not establish a complete NSS inventory.
Complete provider and live-occupancy admission, a real owned namespace broker,
mount/APEX and data mapping, IPC, seccomp and daemon integration still require
implementation and actual qualification. Source identity checks do not grant
permission to reuse another workload's ranges or write an arbitrary PID's map.

## Applications, current preparations and user data

The selected final set contains 41 retained applications plus a prepared official
Firefox replacement. **0/42** have completed the new cohort's actual runtime
acceptance. The original 45-package inventory is historical, not a second claim
of progress or a replacement denominator.

Calendar, Clock and Gallery candidates have been prepared and checked, but have
not been installed into an accepted runtime. The installed package/split and
QPR1 APEX inventory checks found no package-identity conflicts. Official current
commercial delivery still needs the correct device/channel artifacts. A local
commercial app whose signer differs from the official release requires a
supported data-preserving migration; deleting data or rewriting certificate
records does not qualify it.

The current selector contains **13 preparations** and **721 independently
verified retained files**. Its latest Gallery source closure checked 59 current
source files, five wrong-pin negatives, five normal bootstraps and 61 controls.
It preserves the same EvidenceWitness implementation. These source and host
checks make no Main, Android or application acceptance claims.

Current Camera and Sensor work remains represented in the
[Camera source bundle](continuation/camera_video_current/README.md) and
[Sensor staging proof](sensor-canonical-stage-20261108/verification.json).
Their earlier scope is retained. Fresh installed Binder identity, lifecycle,
actual recording/playback, storage flows and whole-application behavior remain
required. Account, transaction and call/message cases also require authorized
test endpoints before they can execute.

The original Android data and metadata image identities remain unchanged.
Required accounts and current signing material are retained.

## Verified removal and remaining cleanup

Of the original **807** experiment roots, **805 are physically removed** and
**two remain**. The latest three-root removal verified all 721 current inputs,
actual original-owner retirement and the exact 14,111-node deletion inventory.
It removed 14,100 files and 222,466,048 allocated bytes. A separate independent
readback verified absence and unchanged current inputs and original user data.

The remaining roots are a minimal fence whose old execution owner still needs
conclusive closure, and signing material for a QA package that is still
registered. An absent runtime API record alone is not owner-retirement proof,
and an installed consumer prevents deleting its only signing material.

The obsolete duplicate Native source on the former build host was separately
removed after full input migration, source verification and ownership checks:
**1,000,064 entries** and **79,478,636,544 allocated bytes** across two roots. The
observed free-space increase was 79,477,571,584 bytes. This separate retirement
is not added to the original 807-root denominator.

Two later cleanup transactions also completed. Application staging retirement
removed **41 targets / 117 nodes**: 36 obsolete staging files and five failed
roots. Independent full-hash verification preserved the union of **743 current
files**: 721 selected application inputs and 22 current Camera files.

Kernel temporary-payload retirement removed **19 targets / 4,574 nodes**,
accounting for **843,276,288 allocated bytes**. The signed candidate, current
application inputs and original data metadata were independently checked.
These separate transactions are not added to the original 807-root denominator.

Registered QA packages, the two retained original roots, later repair
generations and obsolete Android payloads still require final consumer closure
and physical removal. Required current signing material and user data remain
protected. The intended result is one accepted Android cohort and the required
current applications, with obsolete versions and experiments retired.

## Next execution gates

1. Finish the actual Native source and metadata repairs and obtain normal full
   Native and Audio builds, complete artifact/signature evidence and coherent
   QPR1 ABI results.
2. Complete the reviewed one-shot selection and recovery decision, coordinate
   the disruptive restart, and verify the candidate on real host hardware.
   Preserve the old Android masks and original data throughout.
3. Implement and qualify production identity admission, owned namespace mapping,
   mount/APEX/data boundaries, IPC and seccomp without overlapping other workloads.
4. Verify actual Android startup, audio/video, storage and all 42 selected
   application flows. Complete official current app delivery and supported
   signer/data migration using authorized endpoints.
5. Remove superseded Android, QA apps, staging and experiment outputs after
   verifying their exact owners, current references and physical absence.

The A08 workflow retains the three independent identity, allocation and cleanup
review capsules alongside the seven current frozen source capsules. It runs the
new Linux controls in separate interpreters. This publication records repair and
verification progress; it grants no production or application runtime pass.
