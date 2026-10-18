# Actual Rust-kernel cancellation at the live entry

The successful attempt03 used published source `22fcd9edeb8d4e1abee7ce2c3109df5d922c8ed5`,
tree `f50be48bfeffeef5d50cce72a50f09c21f65f417`, identical to runtime local
`aa4ec5abf2acc60153c39f6c87c8aa29e6abaff5`. All recorded source inputs were
matched against immutable Git objects (`source-binding.json`). Existing build
cache was reused; this is not a fresh full compilation or reproducibility claim.

This is **real-kernel cancellation acceptance, not a complete boot pass**.
QEMU8.2.2 q35/TCG, CPU max, 1 vCPU/512MiB booted the source-built Asterinas
kernel. Actual native GDB15.1 hit `__ostd_main` at `0xffffffff88422840` and
executed the original helper's PC and 32 live instruction-byte check. The bytes
matched both this run's symbol ELF and executed boot ELF. The explicit test shim
copies the generated `-x` script, inserts a ready JSON plus sleep60 **after** its
original live-byte marker, and execs real GDB; `--version` directly execs real GDB.
It changes no production source or ELF. Both scripts and the adaptation receipt
are retained. The held test script is not presented as unmodified debug acceptance.

The controller held CLI, QEMU and native-GDB pidfds, verified all alive, verified
the TCP listener and workspace lock occupied, then sent SIGTERM **only to the
debug CLI**. The CLI returned **143**, recorded `passed=false` and SIGTERM;
QEMU and GDB pidfds exited, the GDB port accepted a fresh bind without address
reuse, the same workspace lock inode was reacquired, and every debug-owned direct
session was reaped. Controller cleanup needed no further process signal.
No `/proc` lookup, subreaper or signal to a reaped numeric group was used.

Cancelling the worker also stopped its recorder before normal finalization.
Consequently `qemu.json` retains **raw_exit_code=null**, no final serial SHA, and
there is no `boot/serial.log`. These are preserved facts, not raw33 or a boot
failure. `post-cancel-kernel-qemu.log.gz` is explicitly a post-cancellation
unfinalized pathname snapshot (not a finalized serial binding); complete captured
driver stdout and GDB logs are retained. GDB termination may detach and briefly
resume the guest before driver cleanup; this remains a cancellation test.

Two earlier failed attempts are preserved separately, neither counted as a
cancellation or kernel pass:

- attempt01, source7cf/tree515: driver141 during truncated GNU Make version
  metadata, before QEMU. The subsequent source22fcd fixes the SIGPIPE-prone
  metadata pipelines by retaining full make/gcc version output. No head shim or
  weakened pipefail was used.
- attempt02, source7cf/tree515: real Rust PC breakpoint hit, then the controller's
  inserted GDB Python failed with SyntaxError caused by nested newline escaping.
  It did not execute the live32 check or send cancellation. The corrected shim
  uses chr(10) and syntax-compiles the inserted Python before executing real GDB.

All three complete controllers, commands, selected environment, generated and
adapted scripts, observations, failures and completed debug output are in
`raw-attempts.tar.gz`; each regular member is verified in `raw-members.json`.
The executed ELF, small initramfs and readable final receipts are standalone.
The 111-MB DWARF ELF is represented by its observed SHA/size and source build
recipe, not committed. Manifest preservation happened only under stable flock,
matching the minimal profile hash and renaming to exclusive paths; its writer
and cause remain unknown.

Run `sha256sum -c SHA256SUMS` here to verify every delivered regular file.
