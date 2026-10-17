# C4: fresh cloud instance, cold Rust kernel build and actual boot

Producer `4e8c7083575cec69efabe8d2250dfdd040c8dee8`; fixed Asterinas v0.19.0 and `nightly-2026-07-21`. Actual source checkout `/tmp/trillionnium-a01-normalized-C4` had no target at prelaunch. Eight controller commands completed successfully, including cold `run_kernel` (upstream `make run_kernel`), source checks and `check-boot.py --live-artifacts`. Actual QEMU raw/recorder exit: 33.

The actual cloud instance was `24f0ea2620fe`, Linux `6.18.55`. The schema4 embedded builder `a01-repro@a01-fixed-profile` is synthetic and separately recorded. This phase accepts C4 alone. Cross-instance equality is accepted only by the independent comparison phase. Frozen producer `run.py` still contains its historical same-host scope text; its bytes remain unchanged.

`readable/serial.log` preserves the complete 72,341-byte serial (SHA256 `d406a57118e90ff4ddd6ab28bd974031951a45e8584e0ff4fd2c247245234b0e`). Exact QEMU argv, executable hash/version, loaded ELF/initramfs/BIOS, source pre/post receipts, empty postrun worktree status, compiler arguments and all ledger events are retained. 369 compiler calls, 738 ledger events, 61 canonical local descriptors. Cargo units all completed zero; query probes have retained status counts `{0: 34, 1: 3}`.

Inputs are standalone compressed exact bytes, at most 2 MiB per chunk. `capture.json` records stable original file stats; no original target paths were opened by packaging. The 86 selected source controls and 30 Git tree objects are copied unchanged from the independently verified A4 closure because the producer commit is identical. New prelaunch, fresh locked fetch, actual host, original controller and C4 controller are included; the only controller change is the accepted case guard. This is an opt-in fixed-path/toolchain/profile result, not arbitrary environment or immutable-host acceptance.

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-c4/verify.py
python3 -I -O support/build/evidence/2026-10-17-repro-kernel-c4/verify.py
python3 -I support/build/evidence/2026-10-17-repro-kernel-c4/verify.py --restore /absolute/new-directory
```

The offline verifier checks complete package coverage, source Git membership, full compiler/custody/guest records and exact retained inputs. Optional restore only creates verified bytes in a fresh directory; neither command executes a build, captured controller or VM. Reproduction uses the preserved controller and producer checkout after restoring the locked private dependencies; the exact literal toolchain and profile paths are prerequisites.

The first cross-phase packaging check exited 1 because the packer accidentally generated a Python cache file in the historical A4 phase. `packaging-correction.json` preserves the failure and exact recovery; only the newly generated extra was removed, and every original A4 file remained unchanged. The captured original packer bytes remain verbatim; `capture-corrected.py` adds bytecode suppression for future packaging. This was a packaging coverage failure, not a kernel or comparison mismatch.
