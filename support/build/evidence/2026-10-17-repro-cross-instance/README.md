# A4 / C4: complete Rust kernel inputs reproduced across two cloud instances

Both real cold builds used producer `4e8c7083575cec69efabe8d2250dfdd040c8dee8` and fixed Asterinas v0.19.0 / `nightly-2026-07-21`. Their actual cloud hostnames were `343e40cfefc1` and `24f0ea2620fe`, with Linux `6.18.44` and `6.18.55`. Both actual kernels booted in QEMU with raw exit 33 and retained full serial logs in their single-case phases.

Complete loaded ELF bytes compare equal (8,286,952 bytes, SHA256 `8c540288c6af2a1a97121031643c1af4c4db395d7e8b4082d6edc4604449849a`). Complete initramfs and BIOS bytes also compare equal. The comparison opened stable descriptors for the verified restored A4 original bytes and actual completed C4 snapshots; their exact stats, sizes and hashes are retained in `live-comparison.json`. No original compiler target was opened. Offline verification independently recomputes full byte equality from both packaged cases.

Each case records 369 compiler calls, 738 ledger events, 332 successful Cargo units and 61 canonical local descriptors; the complete descriptor mappings compare equal. Cargo producer identity counts are recorded and compared separately. Probe results are retained without relabelling their three legitimate exit-1 queries as compiler failures. Exact source controls, compiler arguments, profile custody, original controllers, successful source checks and QEMU evidence are independently verified by each case verifier.

This result holds the literal absolute Cargo/Rustup registry/toolchain roots, native tool prefix and profile virtual prefix fixed, with the explicit schema4 job1/canonical-metadata/epoch/synthetic-builder profile. It establishes the observed two-instance reproduction; it does not establish an immutable environment, arbitrary-path/host reproduction, provider instance attestation or an unprofiled default-build result. The frozen producer's original `result.scope` same-host wording remains verbatim; this independent comparison carries the new result.

```sh
python3 -I support/build/evidence/2026-10-17-repro-cross-instance/verify.py
python3 -I -O support/build/evidence/2026-10-17-repro-cross-instance/verify.py
```

Both sibling phases `2026-10-17-repro-kernel-a4` and `2026-10-17-repro-kernel-c4` are required. Their complete checksum inventories are bound in `comparison.json`; neither historical phase is modified. The verifier performs offline checks only, without a compiler, Cargo, network, captured controller or VM.

The first normal and optimized offline comparison checks exited 1 because integer probe-status keys in memory became strings in JSON. `verification-correction.json` preserves this representation failure and its fix; no kernel input bytes or comparison facts changed. Recomputed data now uses the stored JSON representation, and unexpected phase directories are rejected.
