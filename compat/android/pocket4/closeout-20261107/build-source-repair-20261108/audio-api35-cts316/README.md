# Audio316: exact original API35 and CTS provider repair

This package reconstructs the public source files of the builder that actually passed the Audio316 controls. It preserves the real source lineage `6eb50f3e` (308 projects) → `2884a01f` (actual 309 projects) → `3b4199c0` (316 projects). The new patches retain the original providers and Blueprint modules, their tests, and their declared dependencies.

The recorded qualification is **9 passing tests, two normal dev-profile CLI builds, and a successful normal lock verification**. There were **zero release builds**. Full Audio source reconciliation, the Audio APEX build, payload qualification, installation, runtime behavior, and application acceptance remain separate gates. The first Audio316 source attempt was refused at the first occupied Native lock before any normal source command ran.

## Reconstruct the source

Keep this directory beside the existing `source-prerequisites` and `integrated-builder` directories under `build-source-repair-20261108`. The earlier three source patches are dependencies of this current reconstruction; they are not bundled a second time.

From that directory, run:

```sh
python3 audio-api35-cts316/reconstruct_source.py \
  --package-root . \
  --output /tmp/audio316-source
```

The output path must not already exist. The helper checks every patch and inventory checksum, applies the five patches with native Git, and verifies all source bytes and executable modes after the 308, actual309, and 316 stages. It performs no Cargo compilation, AOSP materialization, network fetch, Android operation, or deployment. A failed reconstruction leaves its new output available for inspection.

The exact order is:

1. `source-prerequisites/base-source.patch`
2. `source-prerequisites/audio-prerequisite.patch`
3. `integrated-builder/audio-final.patch`
4. `audio-api35-cts316/audio-actual309.patch`
5. `audio-api35-cts316/audio-api35-cts-original-providers.patch`

`source-chain.json` is the machine-readable chain. The final public source tree is `2c21ee1bbcbde46c8d07a26c6083e372d550c1c1`, containing 431 files. `compiled-source-files.json` records every relative path, size, SHA256, and Git mode.

## Why the actual309 delta is required

The earlier published prepared309 branch was `7775926d`. Its 409 public files and tree `74ac3f46` were compared against the actual compiled parent `2884a01f`. The branches differ in the source lock, the source library, and the updater, and the actual branch adds the complete original ICU4J and JUnitParams Blueprint fixtures. The actual tests also cover these original consumers and providers.

Both branches use the same original JUnitParams project and commit. Their lock bytes still differ because the actual branch places the project in sorted order and records its own purpose text. These byte differences matter to the exact-lock gates. The historical prepared309 controls cannot qualify the actual branch.

This package therefore starts from the exact published308 parent and applies the real actual309 delta. It does not consume the prepared309 patch or inherit its qualification. `base-comparison.json` records the complete comparison and the verified published inventories.

| Source stage | Local source commit | Public files | Public Git tree |
|---|---|---:|---|
| Published308 parent | `6eb50f3e0a2184cb822d0704c6f53f261ebd2de4` | 409 | `660de60cfd4b57fd3b823dff7757e0a4f098df49` |
| Actual compiled309 parent | `2884a01f853caa94f7b66c7e945b0e2818f8ca74` | 411 | `3865514b9e2377430c1e3276e229fc0193df331b` |
| Actual compiled316 | `3b4199c0af6e430a852131a71f87aa65aef8f813` | 431 | `2c21ee1bbcbde46c8d07a26c6083e372d550c1c1` |

The complete local compiled inventory had 436 tracked files. The public tree excludes the same five non-build metadata or image files as the established public base: `AGENTS.md`, `m831-provenance.json`, `assets/screenshots/whatsapp.png`, `.github/FUNDING.yml`, and `.github/workflows/ship.yml`. No additional transient sidecars were present in these four compared trees. No public source file was rewritten or normalized to remove private values.

## Original provider closure

The actual316 patch changes three existing files and adds 20 original provider fixtures. It keeps the existing 309 project commits and purposes and adds only the reviewed sparse paths. The source lock contains 316 projects and has SHA256:

```text
c104640627a1beb35b25423656e751a4b56ac17287505c0ee2efeeb7d0419560
```

The repair includes the three original SDK35 public leaves, the CTS shim/install providers and their required original sibling modules, debugfs inputs, CTS Tradefed/runner inputs, and the actual ATS/dEQP/EasyMock dependency closure. The seven new projects are the original `tools/deviceinfra/prebuilts`, `external/deqp`, four `external/deqp-deps` projects, and `external/easymock`, all pinned to the same recorded superproject.

The full original dEQP cones are retained, with the whole `android/cts/runner` directory and `android/cts/angle`. The existing SDK9 and active Clang inputs remain at their existing pins. No provider stubs were added, no original tests were removed, and missing dependencies remain disallowed.

The closure distinguishes real Soong module dependencies from phony packaging names. The CTS package mutator creates dependencies on its Tradefed modules, tools, and host shared libraries; those edges require their real providers. Phony names alone are not expanded into an unrelated complete CTS source tree. This is source-level closure evidence; it is not a claim that a full Soong build has succeeded.

## Actual controls and normal tools

`public-proof.json` is a compact projection of the actual controls and their completed retirement. It records the original evidence hashes, exact command arguments with private prefixes removed, individual test names, stream hashes, resource results, and the two compiled tool identities.

The actual compiler reported:

```text
rustc 1.93.0 (254b59607 2026-01-19)
```

The actual commands were:

```sh
cargo test --offline --locked -j1 -p droidloom-source --lib audio_ -- --test-threads=1
cargo test --offline --locked -j1 -p droidloom-update --bin droidloom-update audio_api35_cts_ -- --test-threads=1
cargo test --offline --locked -j1 -p droidloom-update --bin droidloom-update audio_junit_provider_ -- --test-threads=1
cargo test --offline --locked -j1 -p droidloom-update --bin droidloom-update audio_build_source_lock_is_scoped_and_exact -- --test-threads=1
cargo build --offline --locked -j1 --message-format=json -p droidloom-source -p droidloom-update --bins
target/debug/droidloom-source verify-lock --lock android/manifest/audio-bridge-source-lock.json
```

The test groups passed 4, 2, 2, and 1 cases respectively. The normal build emitted both CLI executables with `opt_level=0`, `debuginfo=2`, and debug assertions enabled. Its artifacts were newly built, with `fresh=false`. The controls ran with a 1.5GiB memory limit, one CPU quota, and swap disabled; peak memory was 789,499,904 bytes, with zero memory-max or OOM event increments. All recorded command children retired and the owned build cgroup was absent at completion.

Cargo registry dependencies are not included. The `--offline` commands require the locked dependencies to be available in the build environment. The package preserves source reproducibility; it does not claim that a build at a different absolute path produces identical debug binary bytes. No compiled binaries are distributed here.

## Replay and qualification scope

The preparation job first checked all 436 actual compiled source files against the frozen manifest. It independently reconstructed the public subsets of both previously published branches and matched their complete inventories and Git trees. It then applied the two new deltas in an isolated Git repository, checked all 411 actual309 and 431 compiled316 source bytes and modes, and removed that temporary replay.

`source-replay-proof.json` reports precisely that two-delta replay. The three earlier published patches were not re-executed in this preparation job; their starting public308 tree and inventory were matched exactly. The reconstruction helper above is provided for a complete five-patch replay from an empty directory. No tests or compilation were rerun during publication preparation.

## Licenses and provenance

All repository licenses and notices remain in the reconstructed source, including `LICENSE`, `LICENSES/Apache-2.0.txt`, the other existing license texts, and dependency notices. `original-blueprint-provenance.json` lists the exact original project, commit, Blueprint path, upstream URL, fixture bytes, and SHA256 for the 22 fixtures introduced by the actual309 and 316 deltas.

Twenty-one of these are complete original Blueprints with their original headers. The Perfetto fixture is a verbatim two-module excerpt; its record identifies the exact full original Blueprint hash and excerpt boundaries. It is explicitly marked as an excerpt whose original file header is outside the included range. No original Blueprint or included excerpt text was edited.

The public package contains no private host paths, process identities, runtime launch records, credentials, AOSP checkout, Cargo registry cache, or compiled binaries. Its source and compact proof files are the durable reconstruction inputs needed after private experiment directories are retired.
