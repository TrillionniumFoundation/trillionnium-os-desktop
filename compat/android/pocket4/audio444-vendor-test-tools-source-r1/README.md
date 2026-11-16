# Audio444 original vendor test tool source capsule

This capsule records the completed source repair for the isolated Droidloom Audio recipe. It adds the original providers behind nine missing Soong modules and their transitive source dependencies. The source profile grew from 431 to 444 projects on the same pinned Android superproject.

## Scope and Native602 compatibility

The patch applies only to the device recipe base `1fcd1aa60d3144c1f7dfb166346d17ff24a35402` (tree `a1936bfaa2f982a89b687538f9c33b23234faeab`) and records recipe commit `5f8097c23b8ff8dad107f3df2db5a219ff0b6b27` (tree `5d6fa7d51133efb5e91a5b1734de6aa597f1949e`). Those are the isolated recipe's local Git identities, not commits at the root of the public aggregate repository.

Publish this directory as a compatibility capsule. The public repository's existing Native602 sources and capacity remain unchanged. The `MAX_PROJECTS = 448` change inside the patch belongs to the old Audio-only recipe; **do not copy that bound over a global tool that supports Native602**. Integrating the Audio feature into another source generation requires a separate merge that preserves its larger project capacity and corresponding tests.

All 43 changed files have complete SHA256 and Git blob SHA1 values in `manifest.json`. Four modified preimages are included as plain text. The other 39 files are additions in `source444.patch`. No executable, APK, APEX, build output, cache or raw test journal is included.

## What changed

The missing original module names were `absl-py`, `ca_certs_locater`, `dexdeps`, `mobly_sponge_converter_lib`, `py-google-api-python-client`, `py-httplib2`, `py-oauth2client`, `resultdb_uploader_python_library` and `scapy`.

The lock adds 13 original projects for their Python and Mobly dependencies. Existing `dalvik` and `tools/asuite` projects gain the `tools/dexdeps` and `atest` sparse cones respectively. Every old project commit and the original superproject identity remain pinned. The superproject is `platform/superproject` at `28f0bbddc24d56c8ec5a8df5342ac7a292184039`, reference `refs/heads/android-17.0.0_r1`.

The normal Rust builder requires 37 original Android.bp provider files with exact bytes and hashes before entering Soong. Tests reject an old 431-project lock, partial or repinned providers, wrong sparse cones, missing files, changed bytes and symlink substitutions. Original Android.bp license headers remain in the fixtures. Neither missing-dependency enforcement nor SELinux neverallow checks are disabled.

`provider-origins.json` records each original project, commit, Git blob, size and SHA256. Its qualification flags are the historical source-time provenance flags; completed source materialization is described separately in `qualification-summary.json`.

## Replay the changed source blobs

Requirements: Git and `shasum` (or an equivalent SHA256 verifier). Set `capsule` to this directory's absolute path. These commands make a disposable partial tree, verify all four original files, apply the original patch and verify every one of the 43 postimages:

```sh
capsule=/absolute/path/to/audio444-vendor-test-tools-source-r1
replay_dir=$(mktemp -d)
cp -R "$capsule/preimages/." "$replay_dir/"
(
    cd "$replay_dir"
    shasum -a 256 -c "$capsule/preimages.sha256"
    git -c core.hooksPath=/dev/null init --quiet --template=
    git -c core.hooksPath=/dev/null apply --check "$capsule/source444.patch"
    git -c core.hooksPath=/dev/null apply "$capsule/source444.patch"
    shasum -a 256 -c "$capsule/postimages.sha256"
)
```

`replay-result.json` records the actual successful offline replay of these 43 changed blobs. This replay does not reconstruct all unchanged files of the complete repository, build Android, or rerun the historical Rust tests. For a full recipe checkout already at the exact base, `git apply --check` and `git apply` can instead be run there after checking its clean state and all preimage hashes. The manifest records both original commit objects and their root tree identities without claiming that this partial replay rebuilt the complete root tree.

## Completed validation and its limits

There are **103 distinct passing Rust tests: 29 in droidloom-source and 74 in droidloom-update**. Test names and exact log paths, sizes and hashes are recorded, with no raw log contents. The update filters contain overlapping tests; the repeated vendor-cli filter is also excluded from the distinct count.

The initial source-test wrapper `1a1c31667bc-e62c-302` remains **failed with exit 101**: its source test command had passed 29 tests, then an incorrect `--lib` invocation was used for the binary-only update crate. Corrected update job `1a1c31803ae-e62c-309` succeeded with exit 0. Release job `1a1c31a1697-e62c-313` also succeeded with exit 0 and verified the normal 444-project lock and plan. All cited terminal outputs were complete and durable.

Actual source reconciliation job `1a1c3315df6-e62c-383` succeeded with exit 0. All **17 source commands** succeeded and their children were retired. The materialized source manifest is 271667 bytes with SHA256 `c035fe2cea55763bdebe8970a14d105b4d3140e196a90863f30d50c286b1aaab`. Source allocation grew by **142802944 bytes**. The source operation used two CPUs, 4 GiB maximum memory and no swap; memory max and OOM events remained zero. The same three original lock inodes were retained and the source projection was absent after owned-unit retirement.

The separate 14 controller lifecycle checks are recorded as controller validation, not added to the 103 Rust tests or the 17 source commands. Full paths and SHA256 pointers to the actual inner and outer results appear in `qualification-summary.json`.

This capsule qualifies source integrity, normal source tests and source materialization. It does not qualify the vendor CIL, the selected nine-CIL strict combination, the complete Audio APEX, device runtime or production readiness. The source release remains CP2A/user; no QPR1/CP3A identity is asserted. No CURRENT update or final cleanup is performed by this capsule.
