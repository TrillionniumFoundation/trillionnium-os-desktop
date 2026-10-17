# A08 Android / Rust-kernel interface inventory

Reviewed 2026-10-16. Pinned Asterinas v0.19.0 source commit:
c4b7ed575b7b32773475b194d2ad41fb6d03765b.
Source permalink prefix:
https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/

Target userspace: Android android-15.0.0_r36,
aosp_cf_x86_64_phone-trunk_staging-userdebug, x86_64, 4KiB,
reference guest_swiftshader. The Cuttlefish reference runs a LINUX
guest kernel; no Linux/Cuttlefish result may be recorded as Asterinas pass.

## Fixed Asterinas entry-point findings

| Android requirement | Source-level finding at pin | Status and required runtime work |
| --- | --- | --- |
| Binder driver and binder/hwbinder/vndbinder devices | Core device/misc tree has no Binder driver. Code search shows no Binder protocol implementation | **BLOCKED: driver not evidenced**. A05 owns ioctl+credentials; A08 owns service-side validation |
| futex | kernel/core/src/syscall/futex.rs has sys_futex WAIT/WAKE, bitset, requeue, wake-op | **ENTRY POINT** only. Verify robust mutexes, pthread, PI and ART futex flags |
| mmap/mprotect | syscall/mmap.rs, mprotect.rs, munmap.rs and mremap.rs present | **ENTRY POINT** only. Shared/executable/JIT mappings, W^X, page alignment unverified |
| clone/fork/exec | syscall/clone.rs, fork.rs, execve.rs, wait4.rs, set_tid_address.rs, set_robust_list.rs present | **ENTRY POINT** only. Zygote fork/mount/namespace flags unverified |
| signals | syscall/rt_sigaction.rs, rt_sigprocmask.rs, rt_sigreturn.rs, sigaltstack.rs, tgkill.rs present | **ENTRY POINT** only. ART signal chaining and crash handling unverified |
| shared memory | syscall/memfd_create.rs and fs/ramfs/memfd; warns MFD_HUGETLB unsupported | **PARTIAL**. Seal behavior, shared fd longevity and hardware buffer ownership unverified |
| SCM_RIGHTS / fd passing | syscall/sendmsg.rs and recvmsg.rs exist | **ENTRY POINT** only. Real fd ownership/dup/cross-UID/error semantics unverified |
| UID & process identity | getuid.rs, setresuid.rs, Linux credentials/caps | **ENTRY POINT** only. Per-app UID and Binder calling UID must come from trusted kernel |
| SELinux / equivalent MAC | security/lsm/mod.rs exposes LSM abstraction; security/lsm/modules has capability.rs, yama.rs | **BLOCKED**. Neither general LSM hook nor label-only shim proves Android MAC policy enforcement |
| seccomp | syscall list has no seccomp.rs; syscall/prctl.rs supports PR_SET_NO_NEW_PRIVS but NOT PR_SET_SECCOMP or PR_GET_SECCOMP, unknown prctl returns EINVAL | **BLOCKED**. Need actual filter installation and multi-thread synchronization |
| procfs, mounts, property service | Generic filesystems/process implementation exists, but Android-specific init/procfs contract not traced | **UNKNOWN** until pinned AOSP init syscall and mount logs |
| LMKD, PSI/cgroups, oom_score_adj | Android lmkd expects real pressure signals and process killing | **UNKNOWN/BLOCKED** until A06 measures actual pressure/accounting |
| App Freezer | requires Binder freeze interactions, thread stop/resume, cgroup/task controls | **UNKNOWN/BLOCKED** until actual freeze/thaw tests |
| page reclamation | allocator/reclaimer entry points not reviewed for Android | **UNKNOWN**; cannot return invented PSI or hide OOM |
| graphics/HWC | no AOSP graphics stack has been booted against the kernel | **UNKNOWN**; A09 owns buffers/fences, A10 owns desktop compositor |

Source presence is **not** a claim that the syscall is compatible or kernel-tested.
Host C probe passes on Linux only. Main repo has no project kernel imported at
this checkpoint, so A08 must submit smallest failing syscall test to each owner.

## Binder acceptance contract

Use pinned AOSP libbinder and servicemanager source to derive actual ioctl ABI,
not guessed return values. Verify BINDER_VERSION, BINDER_WRITE_READ,
BINDER_SET_MAX_THREADS, context-manager setup and any advertised later command;
userspace mmap ring, synchronous and oneway transactions, nested/reentrant
calls, death notifications, weak/strong ref lifetimes, fd passing, bad size
rejection, SIGKILL/close teardown, thread-pool saturation, and context-manager
recovery. Identity (PID/UID/security context) is assigned by the kernel and
checked against DAC/MAC, never taken from user payload. Distinguish binder,
hwbinder and vndbinder service namespaces; never alias them without evidence.

## Android userspace boot gates (all NOT TESTED)

Bionic ELF loader/TLS/libc, then init with fstab, properties, ueventd and MAC;
Binder & servicemanager; Zygote fork/app_process64; system_server and its AIDL
service clients; ART/JIT, installd and PackageManager; display/input; unchanged
APK install, launch, background/foreground, persistence and restart. Bionic
libraries are earlier load prerequisites even though ART is initialized by
Zygote and executed within later system_server/app process. Capture genuine
init, serial and logcat logs. Stop at first observed failure; never skip a
dependency with a fake success stub.

## VINTF, HAL, input and rendering

Run support/android/audit.py image on actual PRODUCT_OUT to hash system.img
and vendor.img, enumerate vendor VINTF manifests, system framework
compatibility matrices and each AIDL/HIDL HAL format, version, interface and
instance. Exact HAL inventory **PENDING BUILD**, not inferred from an Android
release name. Check declared device/framework requirement matching at runtime.
Investigate SurfaceFlinger, software HWC, gralloc buffer format/strides/lengths,
shared buffer security, acquire/release fences and queue generation. A working
SwiftShader software renderer is **not GPU acceleration**. Validate separate
Chinese IME, keyboard, touch, back/home, focus, notifications and task switch
scenarios before connecting one complete Android display to the Rust desktop.

## Safety, storage, ISA and CDD

Android app UID and binder identity, user-specific filesystem DAC, enforced
SELinux or equivalently strong MAC, and seccomp filtering need explicit negative
tests. Record allowed and denied paths with audit logs. Direct Boot, DE/CE
encryption, user unlock, Keystore, backup/recovery and fd/fsync durability are
separate gates; no mock secret or fixed key is hardware attestation. No Play
Integrity/DRM spoofing. 4KiB is only this x86_64 profile; ARM64/16KiB is
separate. Native Bridge is an interface, **not a CPU translator**. DEX-only,
x86_64 native, ARM64 native and 32-bit native APKs must each have independent
results and exact APK/source SHA. Do not broaden Android AppFunctions consent
requirements into blanket manual approval for OS resource operations. Apply
CDD provisions to actually claimed Android device capabilities.

## Coordination contracts

- A00 owns cross-agent architecture/ABI and mainline integration.
- A01 owns pinned Asterinas full-kernel import and QEMU boot.
- A04 owns generic ELF, pthread, memfd, SCM_RIGHTS Linux ABI reproductions.
- A05 owns Binder device/ioctl, UID and MAC/seccomp kernel enforcement.
- A06 owns memory-pressure/LMKD, app freezer and resource domains.
- A09 owns shared buffers, fences, render devices and GPU/hardware.
- A10 owns native desktop window/focus/input and Android-surface integration.
- A08 owns userspace AOSP selection, evidence scripts, Binder/ART/HAL consumers,
  original APK workloads, lifecycle test, and concrete errno/log reproductions.

No other Agent's kernel files or root README were changed.
