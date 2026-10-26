# Explicit Linux Makepad/text product

`build_text_product.py` builds one original source combination with
`trill-shell/hepta-native-makepad`, Rust 1.96.0, the original SDK
`337566c8b25d47f7e4fff6a202157b65bf183330` and its complete 54-file resource
bundle. Its reviewable inputs are in `linux-text-profile.json`. The first
device profile is x86_64 Linux with X11; native Asterinas and Android have
their own build and execution gates.

The separate [callback-preedit candidate](PREEDIT_TEXT_PROFILE.md) is selected
only with `--profile preedit-callbacks`. It has its own compiled feature,
61-file notice/resource contract, frozen source-tool inputs and mandatory
actual packaged-window gate. Omitting `--profile` preserves this baseline.

## Build and source identity

Use clean Desktop and original Hepta checkouts. Supply full commits and trees;
the Hepta commit must also be the one actually resolved by the committed UI
lock. The existing source verifier proves the original history owner's ancestry
and the Notes protocol goldens before building. The output's parent must exist,
and the output itself must be new and outside both repositories.

```sh
python3 -B support/ui/build_text_product.py \
  --desktop-commit FULL_DESKTOP_COMMIT --desktop-tree FULL_DESKTOP_TREE \
  --hepta-repo /absolute/original-hepta \
  --hepta-commit FULL_HEPTA_COMMIT --hepta-tree FULL_HEPTA_TREE \
  --output /absolute/new-linux-text-build --jobs 2
```

Release is the default. `--build-profile debug` is an explicit development
variant. `--offline` applies to Cargo and the original resource preparer;
`--liberation-source` may supply the exact existing font source archive, and
`--asset-cache` may read an existing original resource bundle by logical path. All
resource lengths and digests remain checked. This entry does not select the
independent clipboard SDK candidate or an arbitrary dependency override.

The command checks the actual resolved native features and one Hepta revision,
runs UI Rustfmt, the native UI workspace, native text host, observer, support
and host-contract Cargo tests, then builds all five real programs. It verifies
the unchanged source/locks after execution, prepares the original resources,
and calls the existing host archive helper and installer packager. A failed
step retains its logs and a failed receipt; it cannot produce a passing receipt.

`build-receipt.json` binds both source identities, the profile, lock digests,
resolved package features, commands and exit codes, compiler, built binary
hashes, the distinct `packaged_binaries` after GNU `strip --strip-unneeded`,
resources and final package hash. The source profile remains
production-disabled. A build receipt is separate from owned-window,
installed-systemd, authenticated model and physical-device acceptance.

## Actual Cargo source caches and compiler inputs

The verifier follows each resolved Hepta/Makepad package's actual
`manifest_path` to its Git root. Each family must resolve from one worktree.
Hepta must match the separately checked commit and tree; the SDK tree must be
the tree of its pinned commit. Every manifest must be tracked. Before tests and
after the build/resource preparation, the same roots must have matching
HEAD/tree, no tracked changes and no assume-unchanged/skip-worktree flags.
`source_caches` records those roots, trees and manifest paths. Ordinary
untracked Cargo markers are allowed; this is explicitly a tracked-source check,
not a claim that every untracked or generated file has been audited.

Rustup resolves the exact toolchain's Cargo, rustc and rustdoc executables;
their paths/hashes are recorded and checked again after execution. Cargo gets
fixed `RUSTC`/`RUSTDOC` paths and empty wrappers/encoded Rust flags. Ambient
compiler wrappers, Rust flags, Cargo build/target/profile overrides and native
CC/CXX flags are removed; their variable names are recorded without copying
their prior values. The selected jobs/profile settings are then applied.
Existing Cargo caches remain usable. Relevant package/library/CMake search
paths are recorded as native inputs; changing them requires a new build.
These checks describe local build inputs and assume the build host and Git/Cargo
tools operate normally; the receipt is not remote attestation of a hostile host.

## Explicit reuse of one builder target

The default remains a new output directory with a new `output/target`. A failed
builder attempt may have useful dependency objects without a passing test or
package. Reuse that exact target only by supplying both explicit arguments:

```sh
# Append to the complete build invocation above; NEW_OUTPUT must still not exist.
--output /absolute/NEW_OUTPUT \
--target-cache /absolute/PRIOR_OUTPUT/target \
--target-cache-receipt /absolute/PRIOR_OUTPUT/build-receipt.json
```

The target and receipt must be canonical, ordinary paths owned by the current
UID, without permissions allowing other users to write them. The prior receipt
must identify that exact target, have a completed success or failure status,
and retain the original compiler, Cargo, metadata and attempted UI-test logs
with matching hashes. An arbitrary prefilled target or unfinished attempt is
not admitted. Legacy receipts prove current ownership and the recorded path
and bytes; they do not attest a historical creator UID.

The target must not overlap the current output, Desktop, Hepta, verified Cargo
source checkouts, SDK helper or prepared SDK tree. One nonblocking `flock` lease
covers metadata, targeted invalidation, all tests, Clippy, build and packaging;
child commands retain the lease even if the Python parent exits. This is a
dedicated builder cache: stop other Cargo users of the directory before opting
in, because an unrelated Cargo command does not acquire this builder lease.

Reuse requires identical Hepta commit/tree, SDK source profile, compiler
paths/hashes, all five lock hashes, build profile, effective compiler settings
and native input paths. A new Hepta pin or lock set requires a fresh build.
Desktop source may change: the builder first resolves all five manifest graphs
and runs scoped `cargo clean --package` for every in-repository path package,
including local dependencies, to prevent preserved source timestamps from
reusing stale local binaries. Git/registry dependencies and unrelated cache
files are retained. Rust incremental compilation is explicitly disabled.

Every existing source, SDK, compiler and lock check still runs. Every formatting,
test, Clippy, build, resource and packaging command still executes and produces
new logs. No previous passing result is inherited. `target_cache` in the new
receipt records the prior receipt hash and source pair, current UID, directory
identity, invalidated packages, `cold_build: false`, and
`prior_pass_reused: false`. The old receipt and logs stay unchanged; only its
explicitly selected target becomes a mutable cache. A small lease journal in
that directory binds subsequent reuse to the latest completed receipt. An
interrupted lease is refused; it is not silently repaired or relabelled.
Formatting and metadata failures before invalidation leave the previous cache
journal intact. Once invalidation starts, a failure before the UI compilation/
test attempt does not qualify the new target for another reuse; use a fresh
build instead of falling back to an older receipt.

## Install the explicit renderer

The build writes a user-owned mode0600 `linux-text-config.json` with renderer
`makepad`, bundled resources, draft recovery and normal Notes storage. Copy
that file into a new private configuration directory and provide its absolute
path with the package installer's existing `--config` option. Existing
installations retain their chosen configuration during upgrades; review and
change `renderer` explicitly for those installations.

Use [PRODUCT](PRODUCT.md) for installation and interruption recovery and
[NATIVE_MAKEPAD](NATIVE_MAKEPAD.md) for the actual X11/IBus/AT-SPI test. Pass the
new `build-receipt.json` to that harness's `--build-receipt` option.
Use `--packaged-binary` when its `--shell` is the extracted or installed package
ELF; omit that flag for the original Cargo build output. The baseline
SDK's native `PasteText` remains unavailable; keyboard paste and real IME are
qualified by their respective input paths.

The config has no invented Root principal, writer or thread.
Actual Send uses the existing authenticated Root native launch documented in
[TEXT_SESSION](../../services/hepta-session-host/TEXT_SESSION.md). Installed
Root, original writer, human session, original App Server route and provider
must satisfy that owner contract. A package or resource check does not create
those deployment inputs.

## Development

```sh
python3 -B -m unittest discover -s support/ui -p 'test_text_product_profile.py' -v
python3 -B -m unittest discover -s support/ui -p 'test_target_cache.py' -v
```

These focused tests reject a default-egui metadata graph, a disconnected text
feature, mixed revisions, a substituted owner, duplicate original owners and
the separate patched SDK. The actual build command remains the executable
verification of compiler and package behavior.
The cache tests use real files and competing processes. When Cargo is available,
the freshness regression changes local Rust source while restoring its old
timestamp, verifies that scoped invalidation exposes the compile failure, and
checks that the external dependency artifact and unrelated cache bytes survive.

