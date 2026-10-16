# A01: fixed Asterinas source build and QEMU smoke

The single kernel source root is `kernel/asterinas/`. Its initial import is the
complete Asterinas **v0.19.0**, commit
`c4b7ed575b7b32773475b194d2ad41fb6d03765b`, tree
`96605cf64aeae2d34f29b97e85eff9315fe10a8e`. Upstream documentation, attribution,
and `LICENSE-MPL` are preserved. The project root README stays empty.

## Build and boot

On a disposable native **Ubuntu 24.04 x86_64** development host:

```sh
# --apt installs host build tools and QEMU; it requires root.
support/build/prepare-host.sh --apt
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
```

Without `--apt`, preparation installs the exact Rust toolchain and fetches the
fixed vDSO dependency, assuming host packages already exist. If Rust is already
installed in a nonstandard location, export `CARGO_HOME`, `RUSTUP_HOME`, and its
`bin` directory in `PATH`. `VDSO_LIBRARY_DIR` and `A01_BUSYBOX` may point to
existing verified inputs; the defaults are `support/build/out/linux-vdso` and
`/usr/bin/busybox`.

The wrapper invokes the **upstream `make kernel` and `make run_kernel` targets**,
with `minimal.mk` replacing their initramfs prerequisite. It temporarily copies
the minimal OSDK manifest to `kernel/asterinas/kernel/OSDK.toml`, refuses to
replace an existing file, and removes its copy on exit. No full NixOS ISO,
Nix installation, Docker daemon, GRUB image, writable data disk, network,
display, or KVM is needed for this profile.

The profile fixes x86_64, QEMU q35/TCG, CPU model `max`, **1 vCPU**, **512 MiB**,
explicit packaged SeaBIOS, a serial console, and `isa-debug-exit`. It packages
static BusyBox, a small init script, and the unmodified upstream
`test/initramfs/src/boot_hello.sh` into a deterministic newc/gzip initramfs.

Evidence is written to a new directory under `support/build/out/` by default.
`A01_RUN_DIR` selects a destination that must not already exist;
`A01_QEMU_TIMEOUT` sets the timeout in seconds (default 300).
Each run records environment, exact make command, make exit status, initramfs
manifest, full build output, exact QEMU argv, artifact SHA256 values, raw QEMU
exit status, and complete serial output. The smoke passes only with all guest
markers, no panic, and **raw QEMU exit 33**. QEMU exit 65 is guest failure;
OSDK normalizes successful 33 to make exit 0.
The QEMU recorder binds the complete raw serial bytes by SHA256 and size.
Fresh runs also verify the recorded kernel, initramfs and BIOS bytes against
their live paths. For offline archive checks, use `check-boot.py DIR` without
`--live-artifacts`; historical records without a serial digest require the
checker from their recorded acceptance commit, not a retroactively added hash.
The wrapper rejects incomplete log capture, forces its initramfs prerequisite
on, and shares a persistent workspace lock with the kernel-test runner. Its
temporary manifest is installed without replacing an existing file, and
cleanup removes only the inode installed by that invocation.
The temporary inode is registered before publishing its manifest, including
when a signal arrives immediately after the atomic link operation.

## Kernel-mode regression tests

```sh
# Runs both full crate test sets inside separate QEMU guests.
python3 -I support/build/ktest/run.py

# Or run a single crate.
python3 -I support/build/ktest/run.py --crate ostd
python3 -I support/build/ktest/run.py --crate aster-core
```

These use the same fixed CPU, memory and firmware profile. They build real
upstream test kernels with separate locks derived from the original root
lock, retain complete serial logs, and reject empty or filtered full runs.
See `ktest/README.md` for lock preparation, focused filters, output selection
and reuse of the source-built OSDK.

The recorded next-phase runs report OSTD **221 passed**, aster-core **141
passed**, and zero failures. Three OSTD tests returned success after explicitly
soft-skipping VMX/EPT paths unavailable under TCG; the exercised pass lower
bound is **359**, not 362. These results cover those two kernel crates on
one vCPU; they do not establish the full upstream userspace/device matrix.

## Dependency and source integrity

```sh
python3 support/build/verify-source.py
```

This checks the fixed commit/tree/toolchain contract, upstream Cargo manifests
and locks, license, root Makefile/OSDK manifest, and the empty project README.
`--pristine` checks every upstream file and Git mode against the original tree;
it passes at import commit `7081fb9b34030af47b7a65d4e62a00fcf147de05`.
Later intentional derivative edits are expected to fail that strict comparison.

Derivative changes are confined to OSDK's host build tooling. Its
`osdk/src/commands/build/mod.rs` accepts `OSDK_CARGO_LOCK` and passes `--locked`
to the generated-crate build. The daemon supervisor also cleans its original
process group before reaping the leader; its regression fixtures use a TCP
lease rather than interpreting namespace-local PIDs through `/proc`.
Lock installation uses a temporary file and atomic replacement, including
when the supplied lock is the destination itself or a hard link to it.
The generated OSDK base crate is a separate Cargo workspace; upstream's root
lock alone does not freeze it. `minimal/Cargo.lock` is normalized from that
fixed root lock: 203 packages, with no external version/source/checksum drift.
OSDK installation also uses its own original `osdk/Cargo.lock` with `--locked`.

The native smoke uses QEMU 8.2.2; upstream's full development image uses QEMU
10.2.1 and additional firmware/GRUB tooling. This is a recorded native-host
profile, not equivalence to the full upstream container matrix. Build inputs
and successful output hashes are retained; bit-for-bit cross-host
reproducibility is not claimed.

BusyBox comes from Ubuntu's `busybox-static` package (GPL-2.0); preserve its
package/source attribution when distributing the generated initramfs. The
vDSO comes from `asterinas/linux_vdso` commit
`8af571775a3d3a1df3e84fc9709b9d6b160c771a`, as fixed by upstream. Its README
attributes the x86_64 image to Linux 6.2.10. These userland/build inputs do not
replace or boot a Linux host kernel as the project kernel.

## A00 / A05 / A06 handoff

All paths below are relative to `kernel/asterinas/`:

| Owner / purpose | Actual source interface |
| --- | --- |
| A05 process identity | `kernel/core/src/process/process/mod.rs`: `Process`, `new`, `pid`, `start_time`, `tasks`, `run` |
| A05 trusted launch | `kernel/core/src/process/process/init_proc.rs`: `create_init_process`, `create_init_task`, `spawn_init_process`; final `process.run()` |
| A05 exec transition | `kernel/core/src/process/execve.rs`: `do_execve`, `do_execve_no_return`, VMAR/credentials transition and CLOEXEC handling |
| A05 ioctl entry | `kernel/core/src/syscall/ioctl.rs`: `sys_ioctl(raw_fd, cmd, arg, &Context)` |
| A05 file transport | `kernel/core/src/fs/file/file_handle.rs`: `FileLike::ioctl`; `fs/file/file_table.rs` |
| A06 common scheduler | `kernel/core/src/sched/sched_class/mod.rs`: `ClassScheduler`, `PerCpuClassRqSet`, `LocalRunQueue` |
| A06 scheduler classes | `kernel/core/src/sched/sched_class/{stop,real_time,fair,idle}.rs` |
| A06 runtime accounting | `kernel/core/src/sched/sched_class/time.rs`: runtime/TSC conversion; audit IRQ-disabled lock order |
| Shared OSTD boundary | `ostd/src/task/scheduler/mod.rs`; changes require A00 coordination |

`sys_ioctl` obtains an owned file reference and drops the file-table borrow
before dispatch. `Context` provides the actual process/thread/task and user
copy interfaces. These are integration points; HOS2, CapSpace, exec_epoch,
stable resource identity, and ResourceDomain are **not implemented by A01**.
`Process::start_time` is Jiffies and is not a complete generation identity.
Budget enforcement must cover the common scheduler path and all controlled
classes, rather than modifying only the fair scheduler.

A01 has not changed those core process/ioctl/scheduler files. A05/A06 can begin
against this source root after A00 integrates the branch; A01 retains build
tooling ownership and will not overwrite their core changes.

Real smoke results, failures, and host package limitations are in
`evidence/2026-10-16/`. The BusyBox applet workaround avoids an observed script
`/proc/self/exe` compatibility issue; that core issue remains for A05 to assess.
The next-phase evidence is in `evidence/2026-10-16-next/`. It includes the two
kernel crate runs and the original OSDK host unit result: 13 passed, one
daemon-descendant test failed. GDB availability and 13 selected non-VM
integration tests passed. The host has mismatched PID and `/proc` namespaces;
focused diagnostic passes do not supersede the original failure. Follow-up
daemon fixes and their actual results are recorded separately in
`evidence/2026-10-16-daemon/`. A05/A06 can use the saved kernel crate results
as an upstream baseline.

The host supervisor uses `waitid(WNOWAIT)` to observe a leader without
releasing its PID, kills remaining members of that original group, then reaps
and permanently disarms the entry. `ECHILD` also disarms group signalling.
This assumes OSDK is the sole reaper of its managed children, with SIGCHLD
left waitable rather than auto-reaped. Descendants that actively leave the
group are outside this boundary. The new host unit
fixtures require Bash with `/dev/tcp` and local loopback TCP sockets. Run the
complete derived OSDK unit suite with the fixed toolchain and GDB available:

```sh
cargo +nightly-2026-07-21 test --manifest-path kernel/asterinas/osdk/Cargo.toml \
    --locked --bin cargo-osdk -- --test-threads=1
```

The full upstream matrix, HOS2, SMP control, physical hardware, Android, GPU,
and Hepta end-to-end behavior remain untested. Cross-host reproducibility
remains open.
