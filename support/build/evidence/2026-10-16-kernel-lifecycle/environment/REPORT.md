# Clean-build environment preflight

The frozen preflight found the native host and fixed inputs ready for a clean build attempt at detached **692c9cf6ced7660304e2f94e31f034ab478830d6**. It did not compile the kernel or run a guest. The later live build is recorded separately.

`raw.tar.gz` preserves the exact `next6-build-preflight.json` (**371,576 bytes**, SHA256 `0dec6fbb77ae74ec3a9a3dc1b52e0017c07db80c9c5cc45dd8731ffce44cc5a0`) and the original `next6-cache-cleanup.json` receipt. `members.json` binds their original size/SHA and the compressed archive. The archive was finalized atomically and reopened to verify every member.

The JSON contains the exact selected environment, actual tool commands and exits, complete stdout/stderr, executable paths/hashes, installed Rust components/targets, and fixed BusyBox/SeaBIOS/vDSO/lock inputs. These outputs are stored once. Rust remains `nightly-2026-07-21`; actual GDB 15.1 with embedded Python, QEMU 8.2.2 and LLVM tools were available. Fixed source protection checked **118 inputs**.

The full-kernel lock had **173/173** registry archives verified; the minimal seed had **145/145**. Standalone OSDK had **115/148**, with **33** exact missing name/version entries retained in the embedded cache report. All 309 sparse-index entries matched, and both fixed Git dependencies were present. Whole-lock gaps mainly concern other platforms or inactive branches; this read-only check did not resolve the native feature/target graph. A real clean offline build remains the decisive dependency check.

Two probe limitations remain explicit. Static BusyBox lacks `script`; the packager lists that extra symlink, while the current init/smoke scripts do not invoke it and their required applets are available. Existing `cargo-osdk --version` genuinely exited **2** because that parser lacks the flag; the successful `cargo-osdk osdk --help`, original error output and binary SHA are retained. No source change or missing-version workaround is hidden.

Before/after snapshots remained clean, detached, root README **0 bytes**, no temporary kernel manifest, and target paths unchanged. The original repository's preexisting untracked kernel manifest was only observed and preserved. The worktree shares the original Git object store; it is not a separate kernel implementation. The cleanup receipt describes four earlier ignored Cargo target caches removed by the parent, with adjacent logs/evidence retained; preflight itself removed nothing.

No installation, dependency download, VM, service change, system-disk/BIOS/GPU modification or ISO operation occurred during preflight. Docker, Nix, GRUB and an installer ISO were not required for the selected native direct-multiboot route with a small Python-built initramfs. This archive reads only frozen preflight inputs and does not inspect the ongoing build's writable logs or target. `SHA256SUMS` covers all final files except itself.
