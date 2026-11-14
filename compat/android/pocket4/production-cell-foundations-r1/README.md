# Production cell foundations

The production supervisor needs a trusted runtime selection, custody of original runtime inputs, an explicit syscall filter, and a readiness check against the running Android property's real storage. This capsule preserves the exact six source files compiled in the independent 415-file source snapshot. It is an intermediate source checkpoint; it does not enable the production daemon or qualify Android.

## Changes

- `production_selection.rs` accepts the fixed root-owned selection and exact selected cell bytes. Client-supplied paths and identifiers do not replace the owner admission.
- `production_runtime_assets.rs` binds the original QPR1 system, init ELF and APEX lineage to a root-owned manifest. It retains source descriptors, the reservation, loop device and detached read-only runtime tree until real retirement. This tested generation still transfers the retained init file descriptor; the later detached init file-mount successor is separate and has not inherited these test results.
- `production_readiness.rs` reads the original Bionic property-area ABI with bounds and stable serial checks. Only the real `sys.boot_completed=1` in the owned current root can satisfy this check. There is no shell/getprop fallback and no property creation.
- `production_runtime_seccomp.rs` rejects selected host-management syscalls and additional authority namespaces. This foundation still allows mount operations and NEWNS. It is not the final mount or Android MAC policy.
- `lib.rs` and `production_mounts.rs` connect these modules without broadening the mount helper visibility.

The source parent is the immutable C11 Binder generation recorded in `SOURCE-ORIGINS.json`. The two changed preimages and four new files are captured by `foundation.patch`. `verify_source_replay.py` applies this patch to the exact preimages and verifies all six resulting files. It neither compiles nor executes Android.

## Actual qualification and limits

The ordinary Pocket4 qualification executed 117 tests with no failures or ignored tests, built both normal binaries, and completed all 13 commands including eight expected ordinary-UID entry rejections. It used one CPU, a 4 GiB memory cap, no swap, and peaked at 2,619,682,816 bytes. The owning unit and cgroup retired. Original data was not opened and no private control or Android execution ran in this qualification.

Separately, the preceding C11 root-sealed private Binder control passed real protocol-8 request/reply and TXN_SECURITY_CTX cases in three fresh private contexts, plus rejection cases and independent retirement. This is a host-kernel construction/IPC result; the observed host label was unconfined and it does not qualify Android SELinux or guest services.

Both strict r12 full builds failed and retired. Audio reported missing original SDK 33 module-library and zygote Rust inputs. Native reported missing telecom and update_engine aconfig providers. Their failure and source restoration remain recorded as failures; subsequent original-source closures do not turn them into successful builds.

Remaining runtime gates include the ProductionCell/daemon path, a delegated cgroup, same-QPR1 init APEX/linkerconfig mount ownership, real property/LSM behavior, non-bypassable writable-proc and mount permissions, runtime assets, actual Android boot, and all 42 application acceptances. The current host uses AppArmor; the old development SELinux shim contains unconditional no-ops and has not been admitted as a production policy. No readiness flag is upgraded by this capsule or its CI replay.

The detailed qualification records remain with the actual owner on the build hosts. `QUALIFICATION.json` records their immutable file references and observed scope without importing executable build outputs or local test journals.
