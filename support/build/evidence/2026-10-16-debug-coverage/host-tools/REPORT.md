# Missing strip dependency and fixed installation

The first complete debug build produced an optimized Rust kernel with DWARF, then failed before QEMU because upstream OSDK requires `rust-strip`. The unchanged original installation command and full log show `cargo +nightly-2026-07-21 install --locked --version 0.4.0 cargo-binutils` completed with exit 0 in 51.24 seconds. The Rust nightly was not changed.

The fixed cargo-binutils package metadata, packaged Cargo.lock, VCS metadata, license notices and the locally fetched crates.io registry entry are retained. Its downloaded crate SHA matches the registry checksum. The full crate, compiler/tool executables, install target and dependency build artifacts are not copied. Their original paths and hashes are metadata, not retained binaries. The extracted crate did not have a .cargo-checksum.json file; none was invented.

`original-rust-strip-version.log` preserves the parent's original version output. `version-recheck-commands.json` and matching logs record new read-only checks, explicitly separate from the original installation. Both the wrapper and fixed toolchain LLVM report LLVM 22.1.8-rust-1.99.0-nightly. The first new wrapper version check inherited an incomplete PATH and failed to find the LLVM tool; its full output and the limits of the later status account are preserved in `incomplete-path-recheck.posthoc.json`. Prepending the existing task cargo/bin fixed discovery without installing or changing anything. All three subsequent explicit-PATH version checks exited 0.

`tool-hashes.json` records the used strip tools and companion LLVM coverage tools. This directory does not claim that a tool version alone proves a GDB breakpoint or coverage test.
