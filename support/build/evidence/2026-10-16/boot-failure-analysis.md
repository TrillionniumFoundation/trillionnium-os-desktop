# A01 boot-02 init recursion investigation

This records a failed real Asterinas kernel boot and a userspace workaround. It does not mark a successful smoke test. The subsequent locked build and boot are recorded separately.

## Observed result

The complete serial log is retained as `failure/boot-02/serial.log.gz`; invocation, input hashes, timing, and raw status are in the adjacent `qemu.json`. The original init script and initramfs are also retained there. The subsequent corrected, locked boot passed; see `REPORT.md` and `acceptance/boot/serial.log`.

- QEMU 8.2.2, explicit TCG, q35, one vCPU, 512 MiB.
- Kernel boot artifact SHA256: `cb797b3a06485419465e4bebb81104bc56fb589e28099e390a5d4f61668fd8e2`.
- Initramfs SHA256: `dab288c9b7ce9850aeb815c9b5646d5428f50a335906c1512fd52b41282edaba`.
- Raw QEMU exit status: **65**, the guest failure debug-exit status. No timeout occurred; duration was 22.749 seconds.
- The log contains `OSTD initialized. Preparing components.`, successful initramfs unpacking, and `[kernel] running /init as the init process`.
- `TRILLIONNIUM_A01_INIT_BEGIN` appears **1,139** times. Neither `Successfully booted.` nor `TRILLIONNIUM_A01_BOOT_OK` appears.
- The initial child processes reach `SYS_MOUNT`. After the proc mount, a later child starts executing the init script again; repeated clone/exec activity follows. Eventually PID 1 exits and the kernel panics with `The init process terminates with code 35584`.

Thus a Rust kernel image reached userspace, but the requested boot smoke failed. These facts do not establish HOS2 functionality, upstream regression success, or a production-ready kernel.

## Verified source behavior

The fixed upstream source is Asterinas `c4b7ed575b7b32773475b194d2ad41fb6d03765b`. The relevant source paths below are relative to `kernel/asterinas/`.

| Path and symbol | Verified behavior |
| --- | --- |
| `kernel/core/src/process/process/init_proc.rs`, `create_init_process` | Constructs `ProcessVm::new(executable_path.clone())` from the selected init path, which is `/init` for this boot. |
| `kernel/core/src/process/process/init_proc.rs`, `create_init_task` | Passes that path to `ProgramToLoad::from_executable` and loads its resulting ELF into the existing VMAR. |
| `kernel/core/src/process/program_loader/mod.rs`, `ProgramToLoad::from_executable` | Follows the script's shebang to its interpreter. The final ELF path is available as `elf_path()`. This does not replace the original `ProcessVm` executable-path field. |
| `kernel/core/src/process/process_vm/mod.rs`, `ProcessVm::new` and `executable_path` | Stores and returns the originally supplied executable path. |
| `kernel/core/src/fs/fs_impls/procfs/pid/task/exe.rs`, `ExeSymOps::read_link` | Returns `vmar.process_vm().executable_path()`. For this script-started process, that resolves to the script rather than the loaded interpreter ELF. |
| `kernel/core/src/process/execve.rs`, `do_execve` | Similarly captures the original executable path before shebang interpretation and constructs the new `ProcessVm` with it. |

The host BusyBox is `v1.36.1 (Ubuntu 1:1.36.1-6ubuntu3.1)`, installed as a static x86_64 ELF. On this exact binary, `busybox sh -c 'type mount; type grep'` reports `mount is mount` and `grep is grep`, showing built-in applet resolution rather than ordinary PATH lookup. The binary contains `/proc/self/exe`. `echo` and `test` are shell builtins; an absolute `/bin/busybox` resolves as that explicit executable.

## Root-cause inference and its limits

The observed transition after mounting proc, the verified script-valued executable path, and BusyBox applet resolution strongly support this explanation: ash's applet dispatch reexecutes its own executable through `/proc/self/exe`, which this kernel resolves to `/init`. Executing that script launches ash again and repeats init instead of running the intended applet.

The guest log records syscall numbers but not exec path arguments at its configured log level. A host `strace` probe could not run because `PTRACE_TRACEME` was unavailable. Therefore the exact BusyBox reexec pathname is an inference from the combined evidence, not a directly captured exec-argument trace. The incorrect script-valued proc executable path is independently established by source inspection.

## Minimal workaround applied

Only `support/build/minimal/init` was changed for the workaround. Every external utility now uses `/bin/busybox <applet>` explicitly, including mount, grep, mkdir, chmod, ln, cat, uname, and poweroff. The upstream smoke script runs through `/bin/busybox sh /test/boot_hello.sh`. Shell `echo` and `test` remain builtins.

This avoids reliance on ash locating an external applet by reexecuting the original interpreter process. It leaves upstream process, procfs, and scheduler source unchanged. `sh -n support/build/minimal/init` passes. The workaround requires a new real QEMU run before it can be called boot-verified.

Separately, the generated OSDK run-crate lock was normalized from the fixed upstream root lock, with no external version/source/checksum drift; see `kernel-lock.json`. The first unconstrained generated-lock build remains diagnostic and is not the final locked acceptance build.

## Identity evidence

Fixed upstream `kernel/core/src/net/uts_ns.rs` intentionally reports `Linux` and release `5.13.0` for compatibility. `/proc/version` derives those fields in `kernel/core/src/fs/fs_impls/procfs/version.rs`. Consequently uname or proc version text alone cannot distinguish this Asterinas guest from Linux. The actual kernel input hash, complete OSTD/Asterinas boot log, guest checks, and raw QEMU exit status must be assessed together.
