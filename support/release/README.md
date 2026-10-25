# Current Desktop / Hepta pair

This module binds one Desktop checkout to one complete original Hepta checkout,
builds the real host binaries and runs their owning-package tests. It does not
create an authority or enable effects.

## Development

Use Python 3.9+, Git, Rust 1.88.0 for Desktop UI, Rust 1.95.0 for Hepta,
`just` and `cargo-nextest`. Linux GUI development also needs the packages in
[the UI runbook](../ui/RUN.md). Keep Cargo targets and generated receipts outside
both source repositories. All build and test commands use committed lockfiles.

Run the tool regressions from the Desktop repository:

```sh
python3 -B -m unittest discover -s support/release -p 'test_*.py' -v
```

The active manifest is
[`profiles/current-organ-source.json`](profiles/current-organ-source.json).
Check out its exact Hepta commit, with enough original history to prove the
history-owner ancestor. Commit all intended changes first. Verify the source
pair without running host programs:

```sh
python3 -I -B support/release/check_organ_pair.py \
  --os-repo "$PWD" --hepta-repo /absolute/path/to/hepta-private-ci \
  --os-head FULL_REVIEWED_DESKTOP_SHA --os-tree FULL_REVIEWED_DESKTOP_TREE \
  --manifest support/release/profiles/current-organ-source.json \
  --output-dir /absolute/path/to/new-pair-receipt
```

Add `--execute-host` to build the actual UI binaries and original Agentd, then
run UI, adapter, Agentd, memory and cognitive-store tests. Add `--offline` only
after the exact committed dependencies are cached. A missing dependency is a
failure; the runner never replaces a lockfile or reduces the Hepta workspace.
The output directory must be new and outside both repositories. Each command
has a separate full log and SHA256 in `pair-receipt.json`.
`--desktop-target-dir` and `--hepta-target-dir` may reuse existing external
Cargo caches; source verification and locked dependency resolution still run.
Use `--build-host` for a binary-only rebuild (for example after final formatting);
it records `host-builds` and does not claim to have run tests. It cannot be
combined with `--execute-host`. `--hepta-profile dev` can reuse an existing
debug test cache; the default `dev-small` keeps CI binary sizes smaller.

## Technical contract

`organ_release_profile.py` owns source identity verification. It requires clean
checkouts, full commit/tree identities, original history ancestry, regular
tracked files and byte-identical protocol goldens. The manifest records one
Hepta pin and selected source blobs; the final external receipt binds the
Desktop commit/tree without a circular self-hash.

`check_organ_pair.py` consumes that manifest. Commands are defined in code,
never supplied by a manifest. The default result is `source-only`. With host
execution, every command must succeed and the original source check must pass
again afterward before `host-build-tests` is recorded. A binary-only run uses
the narrower `host-builds` qualification. A compiler, test, timeout,
or generated source/lock drift failure records `qualification: none`.

The runner does not claim graphical pixels, a production Notes transaction,
kernel boot, or physical device qualification. Those lanes have their own
original-owner and device receipts, bound to the same source pair. In
particular, a fixture issuer is never relabelled as a production issuer.

When the protocol or build inputs change, update the reviewed source map,
generate and review a new manifest with the original source-profile tool,
commit it, and verify again against the final Desktop identity. Keep historical
profiles and receipts intact. See [the detailed source contract](../../docs/agents/ORGAN_RELEASE_PROFILE.md).

## Expanded source profile

Schema 2 uses the code-owned map [`organ_source_map_v2.json`](organ_source_map_v2.json).
It adds the X11 effect/observation wire golden, signed Objective inbox and submission
store, Binder byte transport, seccomp dispatch, page-table accounting, requester DMA
domains, trusted boot roles and boot identity. On the original Hepta side it binds
the Desktop consumer, native HOS2 owner, original Root service/issuer/clock/frontier,
checkpoint coordinator, SQLite pool guard and commit gate.

The source-profile builder selects this map with `--source-map`; the pair runner
selects one of the two fixed map filenames from the manifest's integer schema
version. Missing roles, byte drift, an unsupported version or a version downgrade
cannot remove those checks. Schema 1 and its map remain available for historical
manifests. A schema-2 tool does not make a historical schema-1 pin describe new code:
generate a new manifest only after both intended source commits are frozen.

Both schema versions keep production effects disabled and all seven deployment
inputs unconfigured in a source receipt. An independently tested Root fixture or
a successful compilation does not promote those fields. Actual deployment,
original-owner GUI tests, persistent guest storage, trusted-role execution and
cross-kernel Unknown recovery require separate evidence for the same final pair.
