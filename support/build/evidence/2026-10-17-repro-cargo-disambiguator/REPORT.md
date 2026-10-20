# Cargo crate-disambiguator diagnosis and profile 3 candidate

The retained full A2 and B2 kernels both booted successfully. Their ELF bytes
were different. This report does not turn those boots into an equality pass,
and native fixture results below are not kernel tests. Full profile-3 cold
kernel builds and boots remain the parent's next validation step.

## Actual full-kernel observation

Source in both builds was published commit
`bdf7a08dcc0980fa85c0ba5abdf365b7d2c42e80`. Source checkouts and empty targets
were genuinely separate `/tmp/trillionnium-a01-normalized-A2` and `...-B2`.
The original outputs and failed equality comparison were left unchanged.

| Observation | A2 | B2 |
| --- | --- | --- |
| Kernel ELF bytes | 8,293,608 | 8,292,192 |
| Kernel SHA256 | `e89063b19e5895aa64695ba27c04d7d53fd5d65e23adeb0aab06983a1a33794d` | `b5fda2500d15c250d022f81bf2d30c0778244faea021a5db34aa68665d68f763` |
| Actual source-root literals in ELF | 0 | 0 |
| Recorded compiler invocations | 369 | 369 |

All 59 local unit keys (manifest/crate/target) had different original Cargo
`-Cmetadata` sets. All 259 nonlocal unit keys had identical metadata sets.
The executable `.text` and `.rodata` sizes/hashes differed, as did symbols;
this was not just a debug section or header difference. The ELF64/EM_386
combination is the upstream `make_elf_for_qemu` patch, not evidence of a
different compiler target. Both actual compiler streams used the required
`x86_64-unknown-none` target and compiler path remap.

OSDK generates a separate workspace for its run-base binary. Dependencies
inside the source tree are therefore external path dependencies from that
workspace. Their Cargo package identities seed crate disambiguators with the
absolute source path. Compiler path remapping cannot replace Cargo's already
computed `-Cmetadata`. The earlier internal-workspace tiny model did not expose
this case. `observed-A2-B2.json` records the read-only comparison.

## Support-only candidate

Profile schema 3 changes only the opt-in `support/build/repro` entry. It keeps
upstream/OSDK/component macros unchanged, keeps different actual source roots,
and keeps Cargo filenames and `--extern` paths unchanged. It replaces local
`-Cmetadata` with a canonical descriptor hash. The descriptor binds package
version and manifest identity, crate type/name, target, compiler version,
working directory, cfg/features, all behavior/codegen arguments and canonical
dependency producer identities.

The separate producer ledger accepts only a completed successful producer
whose retained artifact device/inode/size/mtime still match. Start reservations
detect two different incoming Cargo salts mapping to one descriptor in one
build. These are stat observations, not content-hash or privileged-adversary
immutability claims. Nonlocal crates retain their original salt.

Only the fixed sysroot `proc_macro` implicit extern is allowed. The launcher
queries `rustc +nightly-2026-07-21 -vV` explicitly. A real caller environment
defaulting to `stable` returned the correct fixed compiler commit
`87e5904f5eb6398af6b22eac2802c78934260c48`; its output is retained.

## Actual native experiments

`probe-cargo-salt.py` creates a separate binary workspace with external local
library and host proc-macro dependencies. The binary exercises the library's
Rust `TypeId` and calls an out-of-line function. Each case uses a new target.

The final thin-LTO probe used the frozen candidate helpers directly. All four
Cargo compilations and native executions returned 0. Baseline binaries were
different: `ed71c3093d12eb5d4a96eccc9d0b19f70ac1dc5a8c35aba5e72083268ae339ea`
(428,408 bytes) versus
`5686d01e162f041a8e8cf28c79345918c7a7f7b5ab95f04ff9814d76b1bf7c70`
(428,424 bytes). The two normalized binaries were byte-identical:
`1d5441c88f411e8efb017c792b126a526846431c7142e1e35632024987c190ce`,
428,424 bytes each. Actual differing Cargo extra-filename/extern paths remain
visible in the compiler logs. Successful producer completion records are kept.

An earlier non-LTO candidate probe likewise had four build/run exits 0
and equal normalized binaries (`2730a2b937351860f54270eb0959ab1c684e62237df7d66592d57daf8f7fc3a3`).
The first two formal candidate attempts failed on Cargo's multi-crate-type
probe and implicit sysroot proc_macro respectively. Those failures are kept,
and subsequent source fixes are identified by the helper snapshots. Historical
snapshots are retained as historical versions; the final thin-LTO run executes
the exact final three runtime helper bytes. The launcher-only fixed-nightly
query correction is separately covered by the actual stable-caller probe.

The meaningful local build.rs/OUT_DIR/native-link-search fixture is explicitly
refused (Cargo exit 101, expected-refusal test exit 0). Local build-script
generated input identities require a further mechanism and are outside this
pinned profile. No local build script was actually invoked in A2/B2; no local
native-link-search path occurred. Source `env!` inputs and arbitrary environment
code generation are not globally normalized. No cross-host claim is made.

The final focused suite has 31 tests and returned 0 both normally and with
Python optimization, 62 test executions in all. Coverage includes distinct
features/target/profile/version/source identities, unchanged nonlocal units,
missing/failed/unfinished/changed/ambiguous producers, descriptor collisions,
path-prefix neighbors, implicit sysroot restrictions and fixed-nightly query.

## Forecast, explicitly not execution evidence

`replay-retained-arguments.py` retrospectively models the new descriptor using
the old 369 argument records per run and currently retained artifact stats.
It handles both streams without errors and forecasts identical canonical IDs
for all 59 local unit keys. The synthetic history does not contain historical
compiler completion receipts and must never be consumed as a live producer
ledger. This forecast is not a compile, boot or equality result.

## Reference

The primary rustc option documentation describes `extra-filename` as output
filename suffix data and `metadata` as symbol-name disambiguation input:
https://doc.rust-lang.org/rustc/codegen-options/index.html

The candidate's exact source bindings are in `code-freeze-v3-final.json`.
Its `source_worktree_head` is the pre-publication local preparation state,
not the final remote producer. `source-bindings.json` independently binds
all six tested source files and Git modes to published profile-3 commit
`4cf864b62859f0fdb39609589ddd9ef90c6dbc9d`, tree
`d6fc172e0581609e27656a6bef597f377487f0bc`.
