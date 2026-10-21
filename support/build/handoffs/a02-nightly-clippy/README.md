# A02 fixed-nightly Clippy candidate

Status: **`validated_candidate_pending_owner_adoption`**. This handoff does not
change the A02 working tree, its branch, the ABI library, golden bytes, or main.
The main integration blocker remains open until A00/A02 adopts and verifies the
candidate on its integration revision.

The exact A02 base is `eef96afd4c3fcdc5bcdc2b8ba00260e1fb116b91`, with Git tree
`e9ae0d68393356e252253ccfd3d396929b528237`. On the kernel's fixed
`nightly-2026-07-21`, rustc `1.99.0-nightly` commit
`87e5904f5eb6398af6b22eac2802c78934260c48`, unmodified `cargo clippy --all-targets
-- -D warnings` exits **101** with `clippy::chunks_exact_to_as_chunks`.

`nightly-2026-07-21.patch` changes only the byte-pair iteration in three test
helpers:

- `libs/os-abi/tests/mutation_kill.rs`
- `libs/os-abi/tests/transport_preflight.rs`
- `libs/os-abi/tests/transport_vectors.rs`

Each `.chunks_exact(2)` becomes `.as_chunks::<2>().0.iter()`, formatted by the
fixed nightly's rustfmt. The existing odd-length assertion in `mutation_kill`
and fixed transport-length assertion in `transport_vectors` are retained.
`transport_preflight` had no length assertion in this base; its iteration is the
only change. The latter helper is also converted, although the parallel baseline
Clippy run stopped after reporting the other two test targets. No lint is
suppressed. All 11 other archived source files, including `src/lib.rs` and every
golden input, remain byte-identical.

The final candidate passed these actual offline commands with two Cargo jobs:

```sh
cargo fmt --manifest-path libs/os-abi/Cargo.toml -- --check
cargo test --manifest-path libs/os-abi/Cargo.toml --all-targets --offline
cargo check --manifest-path libs/os-abi/Cargo.toml --target x86_64-unknown-none --no-default-features --offline
cargo clippy --manifest-path libs/os-abi/Cargo.toml --all-targets --offline -- -D warnings
```

All four exits are 0. The tests report **61 passed across seven binaries**, with
0 failed, ignored, or filtered. The no_std target compile is an ABI crate check,
not kernel execution or native HOS2 acceptance. This fixed-nightly result is
independent of any owner report obtained with Rust 1.95.

## Replay without editing an owner worktree

The validator exports only the required paths from the exact Git commit into a
new directory outside the repository. It checks every exported blob against Git,
retains the original source archive and failed Clippy output, checks/applies the
patch there without fuzz, verifies the changed-file allowlist, executes the four
candidate checks, and verifies that validation left candidate source unchanged.
It never switches, commits, pushes, patches, or resets an owner working tree.

```sh
python3 -I support/build/handoffs/a02-nightly-clippy/validate.py \
  --repository /absolute/path/to/trillionnium-os-desktop \
  --work-dir /absolute/path/to/new-outside-repository-directory \
  --cargo-home /absolute/path/to/prepared/cargo \
  --rustup-home /absolute/path/to/prepared/rustup
```

The Git object for the exact base and the installed fixed nightly with Clippy,
rustfmt, and `x86_64-unknown-none` are required. `CARGO_NET_OFFLINE=true` is set;
the validator neither downloads nor installs a replacement compiler. Its output
directory must not already exist. The separately supplied dependency cache may
be reused; the replay's target directory starts absent.

A00/A02 can inspect and adopt the unified patch on the exact base with normal
`git apply --check` and `git apply`, followed by this fixed-nightly validation.
Later owner revisions need a new source binding and validation rather than an
unqualified claim that the exact-base result covers them.

## Retained evidence

`evidence/result.json` binds the final counts and exits. `source-before.json`
records Git blob IDs, sizes, and SHA256 for all 14 exported inputs;
`source-after.json` records final candidate sizes and SHA256. The original
`source-before.tar.gz`, generated Cargo.lock, environment, version outputs, every
validation command/exit/log, and patch/script bindings are retained.

`evidence/exploratory/` preserves the initial direct runs, including the first
mechanical patch's formatting failure (exit 1), its command/environment, and the
baseline Clippy failure. That formatting issue was corrected before the frozen
validator run; exploratory repeat tests are not added to the final 61-test count.
`SHA256SUMS` covers all retained files except itself.
