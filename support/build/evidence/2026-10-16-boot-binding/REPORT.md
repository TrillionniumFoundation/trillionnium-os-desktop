# A01: bound boot evidence and preserved symbol ELF

The complete pinned Asterinas kernel was built and booted again after the OSDK
host-tool fixes. Upstream `make kernel` and `make run_kernel` succeeded, the
small initramfs ran the original `boot_hello.sh`, and QEMU returned **33**.
The new checker accepted the complete serial bytes and rehashed the live
kernel, initramfs and BIOS inputs. This is a full Asterinas kernel boot.

## Changes and source

| Published code | Result |
| --- | --- |
| `2c658089bb90aa5b254ddf336ef3dc1333e755c9` | Bind serial bytes by SHA256/size; validate live inputs on fresh runs; register temporary-manifest ownership before publication |
| `4ae1a80e6b87fd55913bd01e6aadd28a20e6c322` | Independently publish the boot ELF; preserve the original Cargo symbol ELF; generate an actual VSC symbol path with quoting; bound debugger waits and propagate test failures |
| `d95ad1b3a55ba9a5da3dbf542ecfbd305f8c8aaa` | Merge actual main `7ba970724ddb7528c3f0908a048cbc647586c6f7`, including A02 ABI and A00 scoped CI changes |

The unique source root remains `kernel/asterinas/`, fixed upstream commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, original tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`, Rust
`nightly-2026-07-21`. The derivative kernel tree at the OSDK fix is
`6a9463ebaaa2060e1fe3968bd940b60d9b1bf8a0`.
All 118 fixed source/build inputs passed verification. No upstream Cargo
manifest/lock, toolchain, A05 process/ioctl or A06 scheduler source changed.
The upstream licenses and documentation remain intact; root README is empty.

## Actual tests

| Check | Observed result |
| --- | --- |
| Complete derived OSDK host unit suite | **28/28** passed, 0 ignored/filtered; includes 11 daemon tests and 5 new ELF/VSC tests |
| Original symbol ELF mutation reproducer | Both tests fail before the fix; both pass after it, including replacement of an existing hard link |
| VSC symbol-path/render unit tests | 3 passed; actual VSCode LLDB client was not run |
| Original integration harness compilation | Passed; compilation alone is not a VM result |
| Boot evidence unit suite | 15 passed under isolated and isolated/optimized Python; fixtures also check all four Python modes |
| Kernel runner regression suite | 10 passed; includes SIGTERM immediately after real `ln` publication |
| Git-reconstructed checker archive comparison | 20/20 expected outcomes; old checker wrongly accepts a changed serial tail, new checker rejects it |
| New recorder, retained full kernel replay | Raw33 accepted with live-input checks; known bad initramfs raw65 rejected |
| Fresh complete kernel developer targets | `make kernel` = 0; `make run_kernel` = 0; QEMU = 33; wrapper/checker = 0 |
| Latest-main merge smoke | A02 Rust 9 passed, Python ABI/mutation 12 passed, 12 independent golden vectors verified; earlier A03 merge smoke 18 passed |

The native OSDK example integration expansion is a separate ongoing phase.
It is not included in these pass counts. Previous OSTD 221 reported passes
(3 explicit VMX/EPT soft skips) plus aster-core 141 passes remain previous
phase results, with exercised lower bound 359. They were not rerun in this
phase and are not relabeled as new results.

## Full-kernel invocation and bytes

```sh
export CARGO_HOME=/workspace/scratch/ae1a8cf05419/toolchains/cargo
export RUSTUP_HOME=/workspace/scratch/ae1a8cf05419/toolchains/rustup
export PATH="$CARGO_HOME/bin:$PATH"
export VDSO_LIBRARY_DIR=/workspace/scratch/ae1a8cf05419/linux-vdso
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
```

The wrapper uses upstream developer targets and a temporary minimal OSDK
profile. It installs OSDK from the fixed source with its original lock, then
builds the complete kernel with the separately normalized generated-workspace
lock. The actual environment, exact make argv and full output are in
`regression/next3-kernel/` and `regression/next3-boot-debug/`.
The boot's exact QEMU command is in the latter directory's `qemu.json`:
q35, TCG, CPU `max`, **1 vCPU**, **512 MiB**, explicit SeaBIOS, serial,
`isa-debug-exit`, no data disks or network. No NixOS ISO was required.

| Artifact | SHA256 |
| --- | --- |
| Boot ELF, 8,297,624 bytes | `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63` |
| Initramfs, 1,107,990 bytes | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| SeaBIOS | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| Complete fresh serial, 72,331 bytes | `ed3b017987fc1d6f06cb7be1c8de54786c2124d45aa342fdb1e26e6ddf7ac682` |

Kernel/initramfs bytes match previously retained artifacts; the machine-readable
reference in `regression/artifact-reference.json` avoids another implementation
or duplicate binary import. The raw symbol ELF remains EM_X86_64 (62), the boot
wrapper ELF is EM_386 (3), and their inodes differ after the real build.
The actual source hashes used before GitHub commit metadata alignment are
retained in `vsc-elf/vsc-review-report.json`; `regression/source.json` binds
them to the published code. Cross-host bit reproducibility is not claimed.

## Failure evidence and limits

The old checker accepted appended nonfatal bytes after recording no serial
digest. New records bind the complete bytes. Older archives are not retroactively
backfilled; use their pinned acceptance checker. `boot-binding/` retains the
new raw33/raw65 runs, the actual tail mutation, all mode results and a script
that reconstructs both checker versions from Git. Offline checks deliberately
do not depend on historical absolute host paths; fresh runs additionally use
`--live-artifacts`.

The temporary-manifest SIGTERM injection reproduces a concrete publication
window in the old runner and passes after the fix. Separately, one real
`next3-kernel` run left matching manifest bytes with a different inode. The next
boot correctly refused to replace that file. Its bytes/stat and failed command
are retained. The subsequent traced boot removed its own matching inode on
exit. The earlier replacement's cause is **unexplained**; neither the signal
fixture nor Git metadata operations are asserted as its cause.

The first complete host-suite attempt lacked GDB in PATH and failed with
process exit12. Its raw log was accidentally overwritten by the later successful
rerun; this is an evidence gap, not a preserved full failure record. The report
retains that limitation. GDB 15.1 was then provided from the previously verified
task-local dependency root, without changing the fixed Rust toolchain or system
configuration. The separate original ELF-pollution failures are fully retained.

This phase does not establish KVM, nested VMX/EPT, SMP control, the default
upstream GRUB/container matrix, all device/userspace regressions, actual VSCode
LLDB operation, or HOS2 kernel enforcement. A05/A06 retain their source
ownership. Their concrete Process/exec/sys_ioctl and ClassScheduler interfaces
and the build/boot entries remain in `support/build/README.md`. CPU quota
enforcement remains an A05/A06 task; host ABI/model tests do not satisfy it.

The default source verifier still protects all original Cargo manifests. A
future coordinated A05/A06 dependency edit needs an explicit A01 lock refresh;
this phase does not silently relax that contract. Existing native package
configuration restrictions and the BusyBox script workaround remain documented
in the previous evidence. No active system disk, BIOS, GPU driver or production
service was modified.
