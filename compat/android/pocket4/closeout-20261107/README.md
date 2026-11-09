# Pocket4 Android closeout continuation

Current state: **`KERNEL_OFFLINE_BOOT_QUALIFIED_NATIVE_AUDIO_GRAPH_REPAIR_FINAL42_RUNTIME_PENDING`**.

Pocket4 is the Linux host running Droidloom Android. The repaired kernel, all
core module signatures, four real Binder credential controls, hardware deployment
inputs and the normal NVMe/ext4 startup chain have passed their scoped checks.
Native and Audio still have failed complete builds. The new kernel has not been
installed on the host, the selected Android cohort has not completed runtime
acceptance, and the selected applications remain **0/42 accepted**. The original
45-application inventory remains a separate historical denominator.

The [current state](continuation/state.json) contains exact receipt hashes and
preserves the earlier observations. **Production ready, runtime qualified,
final candidate deployed and all blockers closed remain false.** Existing Git
history and [continuation history](continuation/history/) retain earlier source
and failure records. No copied evidence or successful CI run transfers device
runtime qualification.

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

This closes the offline startup-input gate. Host installation, a coordinated
restart, host hardware operation and Android startup remain outstanding.

## Native597: source repair passed, complete artifacts still failed

The [original LLVM/Clang plugin repair](../native597-original-llvm-plugin-cones-r1/README.md)
adds each locked project's complete `soong` cone. It preserves all 597 project
commits, eight root links and every other selection. The eight upstream plugin
files are included with their exact Git and SHA-256 identities.

The normal Rust tool build completed all 23 owned commands. The independent
build-host import completed all 15 commands and actual loader checks. Normal
source verification, reconciliation and verification completed all five commands,
with only the two approved cone additions in the resulting manifest. The 43
actual Linux lifecycle and resource controls passed. These are source/tool
qualifications.

The latest complete attempt, **r3**, reached normal Soong step **280/280** and
accepted the LLVM/Clang module registrations. It then failed because
`com.android.devicelock-systemserverclasspath-fragment` references the missing
`service-devicelock` provider. The attempt also failed its original resource
acceptance: its measured peak was **25,769,807,872 bytes**, 4,096 bytes above the
configured 24 GiB maximum, with zero OOM and swap. The failed result is unchanged.
The original kernel accounting mechanisms can temporarily exceed a memory
maximum, but no particular force-charge path was traced in this attempt.

Source restoration, five normal fallback checks, all process retirement and the
original lock checks completed. The next generation is being prepared from
Native's own actual discovery and source projection, with a 22 GiB early-reclaim
threshold and the unchanged 24 GiB maximum, peak, OOM and swap gates. It will
require a new normal complete build and artifact qualification.

## Audio321: source closure passed, complete APEX still failed

The [CTS/STSs recursive closure](../audio-cts-sts-recursive-closure-r1/README.md)
and [normal source-plan serialization correction](../audio-source-plan-serialization-r1/README.md)
qualified the **321-project** source through seven normal commands. All prior
project commits were preserved. The serialization correction handles the
normal omitted-empty source selection, with 12 portable controls.

The latest complete attempt, **r7**, reached normal Soong step **276/276**. The
previous CTS/STSs provider errors did not recur. It failed when `libtflite_kernels`
referenced the absent `gemmlowp_headers`. Its normal source-after, restoration,
work-budget and resource gates passed. Peak memory was **6,855,122,944 bytes**,
with zero OOM and swap. The build and its owning processes retired.

The complete failed attempt has **102 canonical files / 20,820,363 bytes** of
verified custody. Its original failure remains a failure. The separate
[canonical Audio consumer](../audio-canonical-custody-r1/README.md) checks exact
local copies against the original raw terminal, result time, argv, nonce and
full-artifact evidence. Its 19 portable controls reject changed bytes, forged
ownership, incomplete terminals and transferred host/runtime credit. It does not
create or qualify an APEX.

Audio and Native now use independent actual graph inputs to collect real missing
providers and projection omissions before another normal build. Generated SDK,
AIDL/HIDL, namespace and conditional dependencies must be interpreted using the
original build rules. A source graph audit is not a substitute for the real
Soong build, complete artifacts, signing, ABI and QPR1 runtime compatibility.

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

The existing development runner has not qualified production UID mapping or
seccomp, and the production backend remains incomplete. A fresh read-only audit
found **65,536 allocated subordinate IDs** against a required **100,000**, with
the existing range already used by two unrelated active namespaces. No ranges
were extended, no global account mappings changed and no unrelated containers
were stopped. A nonconflicting allocation and an implemented, tested production
backend are required before release.

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

Later staging and failed generations are being checked against complete current
references before removal. The final goal remains one accepted Android cohort
and the required latest applications, with obsolete binaries, staging trees and
experiments removed after their active consumers and replacement gates close.

## Next execution gates

1. Complete the actual Native and Audio source repairs and obtain normal full
   builds, complete artifact/signature evidence and coherent QPR1 ABI results.
2. Finish the concrete kernel installation and rollback transaction, coordinate
   the disruptive host restart, and verify real host hardware and Android boot.
3. Implement and qualify production identity mapping, namespace ownership and
   seccomp without overlapping unrelated workloads.
4. Complete the selected application's real acceptance flows, official current
   delivery and supported signer/data migrations.
5. Retire superseded Android, QA apps, staging and experiments using fresh
   ownership, reference and physical absence checks.

The A08 workflow checks the frozen source manifests and actual portable
controls. Its source and host results remain distinct from complete Android
builds, deployment and application runtime acceptance.
