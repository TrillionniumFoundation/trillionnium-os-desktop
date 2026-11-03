# Exact original-owner image: host evidence only

This archive retains original successful toolchain admission/installation, fixed-nightly formatter output, source-owned host build-script observations, and Python source/parser regressions. It contains no kernel or original-owner guest execution receipt.

The component was admitted only after the complete 123,226,410-byte GitHub transport ZIP and complete 123,224,752-byte official rustc-dev archive both matched their fixed SHA-256 values. The existing interrupted transfers and the original 8/16 MiB image rejection remain historical failures; these records do not relabel them.

The actual private kernel compiler is nightly-2026-07-21, rustc 1.99.0-nightly, commit 87e5904f5eb6398af6b22eac2802c78934260c48. The seven requested components and x86_64-unknown-none target were observed installed. Rustfmt was then installed to that same private toolchain.

Formatting started from clean Desktop 5d95730850a13728824fa89511231215f307e4e3, worked on private copies, and checked all eight changed Rust components. The two resulting formatting changes were applied to local candidate d5c8e093cd6f76e20cedf246b7d7e456a0dbae1c, tree 07cbb5e0187b4355200c2f5e0166228cecf1ecc1. Every formatted component hash was compared with that candidate before commit.

The actual formatted build.rs was compiled with that fixed compiler and run on the original 20,138,584-byte ELF, SHA-256 6ce96a0785b2cbb51bb71fabb2973c1e04d93e213d56694b42b4d717ed55a454. The checks observed ordinary execution without new required inputs, creation of the exact 0444 private compiler input, reuse without inode replacement, and rejection of an owned pre-existing writable file without modifying it. The ELF itself was never executed by this host check.

The format-independent Python bytes passed 47 normal and 14 optimized host checks. After the Rust formatting changes, the actual source gate, diff check, and all 47 normal checks passed again. Parser records are inert test data. Candidate source identities in these records describe the actual before-commit state and component hashes; they must not be rewritten to claim execution of a subsequently published canonical commit.

The actual 204-package locked graph, source-built OSDK, complete kernel, guest memory margin, native effect, writer durability, and complete G2 still require separate normal execution. Legacy 8/16 MiB success, continuous peak, whole process tree memory, global reserve, and production readiness are not established here.
