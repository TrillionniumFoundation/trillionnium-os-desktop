# A3 schema3 full-kernel build: failed before QEMU

This phase freezes the actual failed A3 build at producer `4cf864b62859f0fdb39609589ddd9ef90c6dbc9d`, complete tree `d6fc172e0581609e27656a6bef597f377487f0bc`, derived kernel tree `6b3cab110aa6d30d5b89f99c4389c9c3e01022da`. **Full kernel compilation failed and no QEMU was started.** Earlier schema3 tiny-model successes are preserved separately and do not establish a full-kernel pass.

| Actual observation | Result |
| --- | --- |
| Original controller commands | Worktree 0, source verification 0, build/boot action 2; only these three completed |
| Original action / make | `run_kernel` exit 2; actual outer session 36309/exit 2 reported by root |
| Compilation | 225 `Compiling` lines; stopped while compiling `aster-bigtcp` |
| Failure | `ValueError: extern lacks one unchanged successful producer: smoltcp` |
| QEMU / serial / final ELF / BIOS snapshot | Not produced; statuses and hashes remain null |
| Prepared initramfs | 1,107,990 bytes, SHA256 `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`; not booted |
| Profile/source/code custody | Original three postrun booleans true |
| Manifest cleanup | Original `owned_removed`, passed true |

The action ran from 01:22:01.750019 to 01:25:36.183423 UTC on 2026-10-17. Exact source-build arguments, environment, complete console/traceback, action statuses and cleanup receipt are preserved. An earlier release `Finished` line belongs to an earlier stage; the final kernel build failed. No final ELF or BIOS is borrowed from an older run. Fixed upstream remains Asterinas v0.19.0, commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`, nightly `nightly-2026-07-21`.

## Compiler ledger and scheduling evidence

The original `rustc.jsonl` contains 304 recorded calls. Its producer ledger contains 608 events: one started and completed record per recorded call. Thirty-two recorded calls used canonical local metadata. Their exact incoming/effective argv, descriptor hashes, fixed compiler identity and ledger bindings are recoverable and checked offline. **The failing `aster_bigtcp` wrapper invocation is absent from both recorded-call and start-event logs**, because it failed inside the dependency preflight before those records were written. Successful completion of the 304 recorded calls therefore does not mean the full build succeeded.

The full Cargo-rendered failing invocation and traceback appear in `readable/run_kernel.log` and `readable/console.log`. This is the real diagnostic, not the earlier A2/B2 metadata-byte mismatch. The metadata-query directory is present but empty; no six-query result is assumed from older runs.

`observations/A3-smoltcp-observation.json` is closure_repro's separate read-only postfailure receipt. It binds the original console and ledger hashes, records smoltcp started at zero-based event 585 and completed at event 607, the ledger's final event. The receipt reports that both smoltcp `.rmeta` and `.rlib` postfailure stats match the completed producer's recorded device/inode/size/mtime. Packaging copied this existing receipt and did not inspect target files.

Cargo metadata pipelining is the scheduling explanation: a consumer can need the metadata before the dependency's full compiler process completes, while schema3 immediately requires a completed producer. **Exact A3 consumer-before-completion wall-clock timing was not separately recorded**, so that explanation remains an inference here. No unknown writer is identified. Later controlled scheduling experiments and a future jobs fix are separate work, not new A3 results. Stat-bound provenance is not an immutable-content guarantee.

## Actual separate postfailure checks

The original controller stopped after its third command. After root explicitly requested additional read-only checks, a new exclusive `normalized-cloud/controller-A3-postfailure/` was created. All five newly executed commands passed and retain actual command/environment/UTC/log hashes:

1. `python3 -I support/build/verify-source.py`: exit 0, 118 checked files, intentional derived tree, passed.
2. `git status --porcelain=v1`: exit 0, empty output.
3. `git rev-parse HEAD`: exit 0, producer `4cf864b6…`.
4. `git rev-parse HEAD^{tree}`: exit 0, complete tree `d6fc172e…`.
5. `git rev-parse HEAD:kernel/asterinas`: exit 0, derived kernel `6b3cab11…`.

These are separate postfailure checks, not eight successful original controller commands. They did not rebuild or start a guest. The original A3 worktree, target, profile and failure logs were not modified or cleaned.

## Reversible contents and offline verification

All 33 original files are preserved: 16 A3 output files, four original controller files, six new postfailure controller files, six original profile-v3 inputs and the v3 controller script. The deterministic raw archive has 32 nonbinary regular members; the prepared initramfs is stored separately with exact original bytes. Original empty metadata directory, modes, stable read stats and every logical path are recorded. Complete selected producer controls include 86 Git blobs plus 30 Merkle tree objects, lockfiles and MPL license. Every archive/binary chunk is at most 2 MiB.

The controller SHA256 is `19cb2bce49ebe718058946717aafbd2775c57a33b6ce60b87935882276f8ded7`. Original policy retains exact `rustc -vV` bytes and identity hash, code hashes, prelaunch profile snapshot, actual host `343e40cfefc1` and explicit synthetic embedded builder `a01-repro@a01-fixed-profile`. No booted guest identity is claimed because no guest ran.

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-a3-before/verify.py
python3 -I -O support/build/evidence/2026-10-17-repro-kernel-a3-before/verify.py
```

A passing verifier confirms complete retained evidence, source identity, recorded compiler subset, separate postfailure checks and truthful failure semantics. It does not turn A3 into a successful build. It needs no network or Git executable and never runs Cargo, a live artifact check, captured command or VM.

```sh
python3 -I support/build/evidence/2026-10-17-repro-kernel-a3-before/verify.py --restore /absolute/new-directory
```

Optional reconstruction restores verified bytes into fresh files, including the empty metadata directory and selected source controls. Historical inode identities, permissions, host dependencies and target outputs are not recreated or executed. No schema4 fix, future A4/B4 result or cross-host/immutable-environment acceptance is included.
