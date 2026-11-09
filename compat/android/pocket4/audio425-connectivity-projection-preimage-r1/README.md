# Audio425 Connectivity projection preimage repair

The normal Audio build already applied two existing Connectivity compatibility patches.
A later original-provider guard compared the resulting service Blueprint with the
upstream preimage and rejected this legitimate, fully bound projection.

This source change preserves the original-provider guard. In Audio scope it obtains
the exact original bytes from the normal Projection journal and separately verifies
the complete expected postimage and the two exact applied patches. Other build
scopes retain their previous behavior. It does not accept an arbitrary current
hash, remove a consumer, define a replacement module or relax strict dependencies.

## Exact source boundary

The original service Blueprint is 16,884 bytes with SHA256
`f118cc0ac04460b290d84248c511539ec245999be73901fd6d59df1b3eae888f`.
Applying the existing normal patches in order produces 17,018 bytes with SHA256
`e5b482317718cea8ce2a8dbe5c339daaf7837e92b1fa58c735dd4f3f48c58c44`.
All 23 original provider names remain present. Both bodies and both unchanged
normal patches are included for review. The production patch embeds six additional
upstream C++/Blueprint fixtures with exact Git blob and complete SHA256 provenance.

Apply `audio425-connectivity-projection-preimage.patch` after the two patches
already present in `audio425-original-provider-closure-r1`. The precise predecessor
is recipe `47e1f50438cb3ec0debee674965d310e25ab7569`; its normal
`tools/droidloom-update/src/android.rs` is 390,137 bytes with SHA256
`68dcc77042fba930fc9c98309059e5ce6895cb51eac1dc59a445aa0ef10e3a7c`.
The resulting file is 401,364 bytes with SHA256
`4e223bbf459443138dab5b957e8661075e7cccf884b0a3e7fd867a217de45c40`.
The 425-project lock and all 1,519 original Blueprint selections remain unchanged.

## Actual normal qualification

The original normal tool run completed 24 commands, 23 source tests and 41 selected
Audio tests with no failures or ignored tests. Its four new Rust regression tests
cover the complete original patch sequence, normal and interrupted journal
restoration, rejected missing/changed inputs, rejected zero/partial patch sequences,
and preservation of the non-Audio branch. Both normal CLI binaries were rebuilt.

The normal source continuation then completed 17 commands, verified all 425
projects and 1,519 original Blueprints, and retired every owned child. The public
qualification file retains the exact content hashes and counts of those original
receipts. This packaging operation performs no new build and adds no simulated
full-build success.

Run the normal regression filters in the complete reconstructed recipe:

```sh
cargo test --locked --offline -j1 -p droidloom-source
cargo test --locked --offline -j1 -p droidloom-update android::tests::audio_
cargo build --locked --offline -j1 -p droidloom-source -p droidloom-update
```

These Rust tests need the complete recipe and original fixture tree. No additional
portable Python controls or platform skips are claimed by this capsule.

## Ordered public source chain

The publication baseline `e123939aae9ffeec4e6a2bb928b28cadd44e7f1e` already
contains the original 321-to-425 closure and same-commit RKPD APEX repair.
For the later source sequence apply:

1. This Connectivity preimage repair, preserving the 425-project lock.
2. `audio430-pasit-original-provider-closure-r1`, which appends five original projects.
3. `audio430-original-released-api-inputs-r1`, which adds four original released API files.

`source-origins.json` binds the ordered patch hashes and each resulting lock hash.
The later two capsules are unchanged; they are not cumulative replacements for
this missing intermediate patch.

The inputs belong to the original Android 17 release generation. Full Audio APEX
completion, compiled-input evidence, cryptographic and content qualification,
compatibility with the newer QPR1 cohort, deployment and audio runtime acceptance
remain separate pending requirements. No host process, namespace, lock or runtime
authority is carried by these public source files.
