# Real Rust-entry debug with a private SDK: passed

Successful producer `a5af45537dea32039ea172ad0d7e381400c07d95` (complete tree `4cedffeb88c3f5fb450beedc37fad4dce0dda1f4`), fixed Asterinas v0.19.0 / `nightly-2026-07-21`, derived kernel tree `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. This phase records one actual SDK build + Rust kernel rebuild + GDB session + QEMU boot. Six source-bound retry controller commands exited 0. The existing N2 target was reused; 177 actual `Compiling` lines are preserved. **This is not a cold-build claim.**

GDB stopped at Rust `__ostd_main` address `0xffffffff88422740`, read 32 runtime instruction bytes, matched the exact original symbol ELF and the actual loaded boot ELF, and detached with exit 0. QEMU then completed the small initramfs on one CPU with raw/recorder exit 33, no timeout and every boot marker. The complete 72,255-byte serial is retained at `readable/retry/run/boot/serial.log` (SHA256 `30a97b13f9ba1e61039970367df4a4fcb2846963b02f88b88e699518878990ca`). All five owned helper leaders were reaped.

| Preserved exact input | Bytes | SHA256 |
| --- | ---: | --- |
| Original symbol ELF | 111,661,728 | `4e95684449b048413c7b89c003ac82f0e484819c629f74e3da23cba12d069af4` |
| Loaded boot ELF | 5,963,432 | `dfb30f188cc0b6b4fad8dc6f8bb75c4a77768cbb94bf19612b06a50a8116d23f` |
| This run's private SDK | 8,560,432 | `94df3fd621055d9f99d3649c21a32d076448d68d8ea4b51d78c8b639a5d2adf0` |

The full symbol ELF, loaded ELF/initramfs/BIOS and actual private SDK binary are independently retained as compressed chunks of at most 2 MiB. The original target symbol ELF was captured with stable descriptor/path stats only after root confirmed the successful run ended; complete size/hash matched the original GDB artifact binding. Root was then released to run the next kernel tests; packaging thereafter reads only the private snapshot.

`installed-osdk.json` binds the actual `boot/osdk/bin/cargo-osdk` to this installation's SHA receipt and source Cargo inputs. Its bytes embed the real N2 OSDK source root and install metadata identifies that source. This is a post-build observation, **not immutable custody of previously executed SDK bytes**. Original commands, environment, source hashes and source Git commit/tree/path/blob proof for 84 selected controls are retained, including debug runner and OSDK source. Project root README remains empty.

The first controller attempt failed at prepare because it requested a nonexistent private-prefix `nm`; no SDK/kernel build or VM ran in that attempt. Its four completed commands, failed result and full logs remain under `readable/failed/`, with both controller bytes and the exact correction. The retry selects the actual `nm` through the explicit restored PATH and uses a fresh output. This is one failure followed by one real pass.

```sh
python3 -I support/build/evidence/2026-10-17-debug-private-sdk-native/verify.py
python3 -I -O support/build/evidence/2026-10-17-debug-private-sdk-native/verify.py
python3 -I support/build/evidence/2026-10-17-debug-private-sdk-native/verify.py --restore /absolute/new-directory
```

The verifier checks retained inputs, exact GDB PC/runtime-byte/symbol/boot binding, complete serial, private SDK receipt/source, both attempts, source Git membership and full package coverage. Verification and optional reconstruction execute no original controller, SDK, compiler, debugger or VM. Original file identities and target outputs are not recreated.

Initial normal and optimized packaging checks rejected one omitted debug source control (`ostd/src/boot/mod.rs`). `source-control-correction.json` preserves the failures and correction. The exact producer Git blob now matches the original debug source observation, and its Merkle membership is retained. No original run file, target or binary input was modified or reopened.
