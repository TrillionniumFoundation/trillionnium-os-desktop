# Break at the full Rust kernel entry

From the project root, after the normal native host/toolchain setup:

```sh
python3 -I support/build/debug/run.py --output support/build/out/NEW-debug-run
```

The output directory must be new. Set `CARGO_HOME`, `RUSTUP_HOME` and
`VDSO_LIBRARY_DIR` as for the ordinary build. GDB and native `nm` must be in
PATH, or select them with `--gdb /absolute/path/to/gdb` and `--nm /path/to/nm`.
An extracted GDB may also need its existing dependency `LD_LIBRARY_PATH`.
The fixed Rust remains `nightly-2026-07-21`.

The helper creates its own listening socket at `127.0.0.1:0`, reserves it with
an inherited descriptor numbered at least 64, and invokes
`bash support/build/kernel.sh gdb_server`. The persistent
`support/build/out-kernel.lock` governs this shared kernel workspace and the
full source build. The helper fixes and records `CARGO_TARGET_DIR` as
`kernel/asterinas/target` so the symbol path belongs to this build.
The QEMU recorder hands that actual
socket to QEMU, so there is no close/rebind port race and no external service.
No throwaway TCP readiness probe consumes the real GDB connection.

The debug target uses upstream OSDK's release debug information and a separate
stripped boot ELF. GDB loads the original Rust symbol ELF at
`kernel/asterinas/target/x86_64-unknown-none/release/asterinas-osdk-bin`.
It installs `hbreak *__ostd_main`, continues from the initial stop, requires
the actual PC to equal the Rust entry address, prints a unique verified hit,
and records a backtrace, source/line information and RIP. The helper checks
the hit against `nm`'s defined `T __ostd_main` address. A firmware register
read or a successful connection alone cannot pass.

Before connecting GDB, the helper reads 32 entry instruction bytes through each
ELF's executable `PT_LOAD` mapping and requires the original symbol ELF and
executed boot ELF to agree. The boot file's size and SHA256 must also match
QEMU's record. At the hardware breakpoint, GDB reads those same 32 bytes from
the live inferior and emits a separate verified-byte marker. The helper requires
both the matching PC and matching runtime bytes, and records both artifact
hashes in `entry-artifact-binding.json`. This binds the entry instructions;
it does not claim a comparison of every loaded guest byte.

GDB disables breakpoints and detaches; then the complete kernel must finish
the minimal userspace boot, power off with raw QEMU status 33, and pass the
ordinary live boot checker. Debugger success alone does not pass this entry.
The readiness/build, GDB and post-detach boot deadlines default to 900, 90
and 120 seconds; adjust them with the corresponding `--*-timeout` options.

Evidence includes the original boot output, complete driver/GDB/tool logs,
commands and explicit environment updates, complete OSDK production source
hashes and both original Cargo locks, installed OSDK SHA after the build,
streamed symbol ELF SHA256/ELF64/machine62, observed live QEMU metadata and
final status. GDB source/line output is retained as observed; an entry-PC hit
alone does not establish source-level debugging. Failures retain
their intermediate record. Cleanup only signals each helper-owned session
while its direct leader is still unreaped, then reaps it; no already-reaped
numeric process group is signalled.

Host-only checks create their own socket and temporary process group. They
do not build a kernel or launch QEMU:

```sh
python3 -I support/build/debug/test_debug.py
python3 -I -O support/build/debug/test_debug.py
```

This directory provides an executable development entry point. Consult a
saved real run's `result.json` and `gdb.log` for actual breakpoint evidence;
adding the entry point or passing host-only checks makes no guest claim.
