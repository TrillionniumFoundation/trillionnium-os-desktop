# Qualified Linux 6.18 kernel for the CP3A Android runtime

This packet preserves the exact source changes and completed build and fresh virtual-machine evidence for `6.18.64-p4ctx6181`. The selected official CP3A system requires the Linux 6.18 kernel family through its original VINTF inputs.

## Completed qualification

- The official Linux 6.18.64 source archive and upstream signature verification are recorded in the packet.
- All 66 changed source paths and the fixed configuration are retained. The full build compiled the 38 affected translation units and produced the kernel and 6,797 staged, signed modules.
- Two fresh virtual machines passed 160 checks with SELinux active and 100 checks with it inactive. They exercised simultaneous AppArmor and SELinux behavior, scoped legacy proc contexts, Binder credentials, namespace grants, and signature enforcement.
- The five required module types were cryptographically verified and actually loaded with signature enforcement. Unsigned and tampered controls were rejected. Each VM exited and was reaped through its original PIDFD; its unit and cgroup retired.
- The primary integrator independently verified every one of the archive's 108 frozen file bodies and the exact 109-member archive, and checked the complete 260-case VM receipt.

## Exact artifacts

| Artifact | SHA256 |
| --- | --- |
| SOURCE.tar.xz (1,783,524 bytes) | `e7d80dd0e54deb12bef41a71cb5d09b6626405b38bb410162d019cd700dc80da` |
| SOURCE_FREEZE.json (66,444 bytes) | `3ea7961b7fd103c506604658426a25669054f259533dae9e5ec312001a276140` |
| Kernel image (16,855,552 bytes) | `a8ed310e658db436c76ce48bff166bea1314f10cce2ae900c90ae603aa225fc0` |
| Configuration (304,072 bytes) | `bccb147083a909408e25dc63f1dd58cf465ee19bcabc660916a1fa28cc67a3e1` |
| Public module certificate | `68bc58f1f1b84dc5998bbf442d6a94a71d853aef907d81fe51ab55771ad4750c` |
| Complete fresh-VM receipt (44,596 bytes) | `5541563dbaf17f12c1673c87a529a59f1317f76e5d8796e0d4f04368b5e65d53` |

`SOURCE_FREEZE.json` names every member, size and hash. `SOURCE.tar.xz` includes the exact source patch and postimages, build configuration and drivers, public upstream verification, complete compressed full-build receipt, fresh-VM source and actual serial logs, and installation input identities. `FILES.sha256` authenticates the four adjacent input and observation artifacts. `ROOT-VERIFICATION.json` records the independent package check.

## Installation and runtime state

The kernel image and complete module payload remain in the fixed build staging paths recorded in `INSTALLATION_INPUTS.json`; they are not installed by this packet. The image has no PE Authenticode signature. Embedded module trust was tested separately and is not a firmware-trust claim. No private signing key is included.

The VM diagnostic policy tests the kernel ABI and enforcement. It is separate from the final Android policy and actual Pocket4 installation. This packet retains `host_installed=false` and `production_android_runtime_qualified=false`. Android's original init/APEX execution, final vendor image, all 39 required application acceptances, and cleanup of superseded installed generations remain separate completion gates.

The current supervisor source and its own CI are in [the runtime source packet](../runtime-current-source-r1/README.md). Passing the kernel checks does not grant runtime or application acceptance.
