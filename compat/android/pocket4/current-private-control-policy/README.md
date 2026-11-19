# Private control device and host provider policy qualification

This packet preserves a separately compiled, strict SELinux policy increment for the private control alias and the host provider operations. It is an offline source and policy qualification. Installation, final vendor composition, AppArmor loading and Android runtime acceptance remain separate requirements.

The private control alias uses a bounded detached tmpfs and two fixed names. The control character inode must receive its dedicated type through the policy's named transitions. Access is restricted to the original broker domain; the complete ioctl decision space permits only the driver's GET and SET operations, b701 and b702. The host provider additions include the narrowly required procfs and guest-user-namespace operations. Initial-user-namespace SYS_PTRACE remains denied.

The producer recorded 81 access and existing-transition checks, two new exact named transitions, every ioctl value from 0 through 65535, eight strict neverallow rejection controls, and three policies that compile but fail the actual consumer query when a required rule or transition is removed. The packet retains the original command outputs and complete policy/CIL/query inputs. These observations do not establish that a live host has loaded this policy.

The archive contains 114 regular members: 113 pinned bodies and the complete source freeze. ROOT independently checked every tar member, canonical type/name/mode, complete length and SHA256, every frozen body, original input bodies where identified, and unchanged archive/freeze identities. The new compiled policy is 765107 bytes with SHA256 a3b3bc2cffd79e470df9675c3575ee83525ff0a2c81212fcd36cda709549074f.

The earlier complete-MAC source capsule remains the preserved preceding qualification. Missing historical R9 author assertions and logs are not described as recovered. This packet neither accesses those denied inputs nor grants production readiness.
