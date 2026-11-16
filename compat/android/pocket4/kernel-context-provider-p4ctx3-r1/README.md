# Pocket4 p4ctx3 explicit context providers

This source capsule contains the original p4ctx1 context-provider framework and the final typed SCM extension, together with the exact finite guest controls used to qualify `7.0.14-p4ctx3`. The completed candidate passed 47 combined AppArmor-first / enforcing SELinux controls and 12 controls with the SELinux provider absent. The same 47-control source and finite policy exposed six failures on p4ctx1 and two on p4ctx2. These earlier failures remain comparison evidence.

The capsule records isolated kernel qualification. It does not attest a deployed host kernel, a booted production Android instance, the original CP3A client integration, or application production readiness. `scope.json` keeps these claims separate. No kernel, module, policy binary, APK, initramfs, or raw log is included.

## Changes and preserved behavior

The original framework is reproduced byte for byte as `kernel/p4ctx1-context-provider.patch` (SHA-256 `1810edbc8ea65e9cccd4ba6dfead6403ec3e4ac327e7bed952bb0fd76cfb140f`). It adds an explicit SELinux representation choice for procfs, Binder, and socket context consumers. The original 32-byte provider ioctl, initial-user-namespace authorization, expected namespace inode, FIXED/USED state machine, immutable socket choice, and procfs/Binder remount constraints remain intact. The original ABI accepts an explicit SELinux selector; it does not add an explicit AppArmor SET value. Default instances retain the historical provider behavior. Explicit AppArmor proc attributes retain their named provider.

`kernel/p4ctx3-typed-scm.patch` is the final nine-file extension (SHA-256 `58b33c63587b7adf4846a354fdcf6d80a124d3fcac6144a85649ab0ee566c827`). UNIX ancillary context capture stores both the security identifier and the complete 64-bit supplier LSM ID. It captures the recipient's immutable provider before publication, including a stream endpoint that receives before `accept()`. Conversion uses the captured supplier and validates the returned context's provider and length. Invalid or mismatched identities are rejected without trying another provider. The supplying hook owns release of a rejected allocation.

IPv4 `IP_PASSSEC` selects through the retained socket wrapper. The wrapper is read under `sk_callback_lock`; the LSM hook runs after that lock is released. A socket or descriptor crossing network namespaces retains its provider. The original permission hooks and their order are preserved.

The p4ctx2 runtime exposed a stream-specific defect: the receive path populated the security identity only through the existing credentials branch. `SO_PASSSEC` without `SO_PASSCRED` therefore received no selected context and could merge differently labeled SKBs. The final change snapshots the selected ancillary mode at receive entry, captures the first SKB's typed identity independently, and compares later SKBs before the existing credentials copy can overwrite it. A selected receive that starts with `SO_PASSSEC` off cannot opt into labeling already-copied bytes halfway through. The credential, pidfd, and file-descriptor branches retain their original order and behavior.

## Source identity and replay

`kernel/provenance.json` binds the original p4guest1 foundation, the p4ctx1 framework, and the completed p4ctx3 build. The recorded upstream identity is `Ubuntu-7.0.0-43.43`, commit `f53b359683af7918c5436499948763cb726d5082`. The base is the already-qualified p4guest1 source, which includes prior credential/grant changes; the context framework patch alone is not a patch from pristine upstream.

The original framework changes 18 existing files and adds four files. Its exact before/after pins are in `kernel/p4ctx1-framework-pins.json`. The final SCM extension changes nine files. The capsule includes only those nine p4ctx1 preimages, with exact before/after hashes, so its final patch can be replayed without a full kernel checkout. These preimages are deliberately a source subset, not a buildable kernel tree. Full Kbuild used a separately verified complete tree containing 99,342 nodes. The complete original source and candidate source remained unchanged through that build. The only configuration change from p4ctx1 to p4ctx3 was `CONFIG_LOCALVERSION`.

Run the offline integrity, syntax, exact patch, and evidence consistency checks with Python 3 and the normal `patch` program:

```sh
python3 verify.py
```

For normal static probe compilation and the outside-guest rejection checks, with GCC, static libc development files, and `readelf` installed:

```sh
python3 verify.py --compile-probe
```

For an additional normal guest-policy compilation, with `secilc` and `apparmor_parser` installed:

```sh
python3 verify.py --compile-probe --compile-policies
```

The latter command uses the supplied AppArmor feature declaration, an empty parser configuration, `--skip-kernel-load`, and `--skip-cache`. The SELinux compilation retains neverallow enforcement. Compiler outputs are temporary and removed on exit. These checks do not launch QEMU, load host policy, install modules, or change the recorded runtime claims. Their output explicitly reports zero fresh VM runs. New compiler checks may use different tool versions from the recorded qualification; the original tool hashes and original binary hashes remain in the evidence.

`inventory.json` covers every capsule file except itself. `qualification/controls/` preserves the actual source of the normal builders, VM controllers, and retirement checks. These controllers contain fixed original paths, generation-specific pins, resource contracts, and exclusive-creation guards. They are reviewable records of the performed runs; reusing them for a fresh VM generation requires retaining those admission and lifecycle conditions while assigning a fresh owned output generation. The offline verifier does not execute them.

## Actual runtime discrimination

| Kernel / arm | Cases | Passed | Failed | Meaning |
| --- | ---: | ---: | ---: | --- |
| p4ctx1, combined | 47 | 41 | 6 | Original-framework comparison: selected UNIX ancillary and IP context missing; stream controls expose missing typed context |
| p4ctx2, combined | 47 | 45 | 2 | Typed capture works, but stream ancillary without credentials still fails |
| p4ctx3, combined | 47 | 47 | 0 | Final candidate qualified for the finite context controls |
| p4ctx3, SELinux absent | 12 | 12 | 0 | Unavailable provider fails closed, without state mutation or fallback |

The comparison controllers succeeded because they observed the exact expected earlier defects. Their successful controller exit does not qualify those earlier kernels. `qualification/runtime-summary.json` marks this explicitly, and `qualification/case-comparison.json` retains each candidate result and the earlier failure details.

The combined controls cover:

- Provider ioctl authorization, stale namespace inode, unknown ID, explicit zero, nonzero flags, initial netns rejection, fixed selection, use after a closed or failed socket creation, and inheritance during namespace derivation.
- Exact default AppArmor and selected SELinux proc representations, named AppArmor attributes, and omitted/same/different remount options while an attribute descriptor remains open.
- Real Binder transactions with default and selected providers, absent/requested context, saved opener A with active sender B, fresh opener B, reverse impersonation denial, transferred descriptors, and held-device remount behavior. Saved opener, active identity, UID, capability state, transaction result, and child retirement are recorded.
- Independent AppArmor denial, independent SELinux denial, and combined denial under zero capabilities, with a readable setup-domain baseline for both sentinel files.
- UNIX stream and datagram messages queued before receive, stream messages queued before accept, A-to-B sender transitions, accepted socket inheritance, `SO_PEERSEC`, a small-buffer `ERANGE` control, and socket transfer by `SCM_RIGHTS` followed by receive from the opposite netns.
- Real UDP payload over a guest-private loopback with a finite CIPSO/NetLabel DOI and domain. Both source and receive carry the expected 12-byte CIPSO option; the selected receiver gets exactly `u:object_r:p4_packet_peer_t:s0`. Default-provider behavior, transferred receiving-fd inode, zero-capability sender/receiver, original loopback state restoration, and deletion of only the owned labeling objects are checked.
- Stream label boundaries with `MSG_WAITALL` and `MSG_PEEK`: peek/consume/next return 2/2/2 bytes with A/A/B labels. Separate cases cover no credentials, credentials plus pidfd, and credentials plus pidfd plus `SCM_RIGHTS`; descriptor identity, payload, pidfd target, and close-on-exec behavior are checked.
- Duplicate initial procfs/Binder mount options, whose final value applies before publication, and bounded guest kernel-log capture with no observed kernel fault marker.

The 12-case inactive arm omits SELinux from the active LSM list and loads zero SELinux policy bytes. SET and selected mounts return `EOPNOTSUPP`; the namespace remains at the original default state. Unknown and malformed requests retain their distinct rejection behavior.

## Diagnostic policy and isolation

The finite guest policy is diagnostic source, not production Android policy. Its two later changes are recorded in `probe/diagnostic-policy-r4c-delta.json` and `probe/diagnostic-stream-r5-delta.json`. The IP correction supplies the original SELinux association prerequisites for the A sender and setup receiver while preserving the B-sender neverallow. The stream control permits only the setup domain to relabel the controlled test socket from A to B so that identical PID/UID/GID across two SKBs cannot hide a security-label boundary. The reverse Binder impersonation neverallow remains enforced. Initial failed diagnostics and their source explanation are referenced by the delta records; no missing AVC is invented.

Every VM was diskless, had `-nic none`, used KVM with two vCPUs and 768 MiB guest RAM, and ran on host CPUs 20–21 under a 1.5 GiB / 200% / zero-swap unit with `KillMode=control-group`. Only the VM's private loopback was used. The original root-owned lock inode 41719533 was acquired without replacing it. The QEMU process identity, start ticks, pidfd exit, service invocation, cgroup removal, memory events, immutable inputs, and unchanged host identity were checked. The final independent verifier reacquired and released that same lock, rehashed every run input, verified all four old process identities dead, and found no remaining owned descendants or QEMU processes.

The full Kbuild completed the kernel and all 6,901 modules for `7.0.14-p4ctx3`. It used CPUs 0–5, six build jobs, a 600% quota, 22 GiB memory high, 24 GiB maximum, and no swap. The full result and separate independent retirement report require zero OOM events. Artifact hashes remain attestations only; the artifacts are not distributed here.

## Evidence map and remaining scope

`qualification/build-summary.json` binds the complete Kbuild and the 12-command normal probe/policy build. `qualification/runtime-summary.json` binds all four VM arms to their original H jobs, terminal state, exact result bytes/hash, boot identity, and retirement. `qualification/retirement-summary.json` contains the independent full-build and four-VM retirement findings. The original terminal states are succeeded/exit 0 with complete and durable output. SHA-256 identities support reconciliation against the retained original records; an offline replay is not a new observation of those machines.

The original CP3A consumer integration, actual production Android boot, production policy, application-level behavior, host deployment, and a grant regression on this exact p4ctx3 image remain outside this capsule's demonstrated scope. The earlier p4guest1 grant results are not relabeled as p4ctx3 runs. No production flag is inferred from successful source replay, compilation, or these isolated guests.

Kernel source and UAPI licensing headers are retained. The original kernel licensing notice, GPL-2.0 text, and Linux syscall-note exception are under `kernel/licenses/`.
