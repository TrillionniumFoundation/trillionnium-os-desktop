# Supply the original Car APEX providers to the strict vendor graph

The actual R25 normal Soong build rejected `external/lua/Android.bp:36:19` because
`liblua` names `com.android.car.framework` in `apex_available`, but the selected
652-project sparse source omitted that real APEX provider. The selected Lua source
and its dependency declaration are correct and remain unchanged.

This source-only successor adds an explicit `production-full-car` profile. It
retains every original 652 project identity, Gitlink, ordering, policy and root
link; appends the required original Car and automotive telemetry cones; and adds
`platform/frameworks/opt/car/services` at the exact Gitlink in the same selected
AOSP superproject. The resulting lock contains 653 projects. There are no stub
modules, fake APEX providers, missing-dependency overrides or Soong edits.

## Exact sources and behavior

The original superproject is `28f0bbddc24d56c8ec5a8df5342ac7a292184039`.
`packages/services/Car` stays at `9f04df65daa8b9a65ee05fd4039fe95446874d76`;
the added services project is pinned to
`2bb3349c1a84b9b15c5ef05ef9c2e3dc6dde427a`. The real provider is
`packages/services/Car/apex_car_framework/Android.bp`.

The new compiled validator derives the exact permitted extension from the
unchanged, fully hashed previous lock. It rejects partial cones, different
Gitlinks, different ordering, policy changes and unrelated scope expansion.
Normal source materialization, reconciliation and verification retain their
existing exact Git and filesystem checks.

The updater's future normal build uses this new profile and names its result
`droidloom-production-full653-vendor-normal-result.json`. Related normal-result
consumers and fixtures change together. Historical `production_full`,
`production_cmake`, `production_lint` and `production_apex_tests` source profiles
remain intact. The actual `android::recover` implementation and the complete
projection/restoration code are byte-identical to the frozen baseline. The old
652 recovery operation must finish using its original inputs.

## Review and reproducibility

`MANIFEST.json` pins all 12 postimages and every changed original input.
`changes.patch` applies to those exact original bodies. `base/` retains the small
set of original producer files needed to reproduce and check this isolated
packet; it is not a complete Rust workspace. `candidate/` contains the complete
new bodies for the next full producer assembly.

From this directory, `python3 prepare_successor.py` deterministically reproduces
the candidate and patch. `python3 verify_source_candidate.py` checks the exact
original-to-candidate transformation, forward/reverse patch application,
preservation of the original recovery code and the source-level Car dependency
references. The sibling `p4_vendor_car_source_audit/` preserves the actual fixed
Git declarations and read-only observations used by these checks.

The finite source checks passed: 12 newly included Car Blueprint files resolve
60 internal Car dependency references to real selected original providers. The
74 inherited or external references remain explicitly enumerated for normal
Soong validation. This does not assert a complete variant-graph build pass.

Eight Rust test sources cover exact monotonic extension, rejection of missing or
foreign provider scope, unchanged old manifests, the explicit CLI profile and
refusal to use an unreconciled 652 manifest as 653. Their fully qualified names
are recorded in the handoff. Rust compilation and these Rust tests have not run
for this packet. Native assembly must recheck all before pins and run its full
existing compile/test gates before any new vendor attempt.

## Runtime boundary

This packet does not change the operator's AOSP tree, run a vendor build, change
CURRENT, adopt a runtime release, start Android or access user data images.
Source review, compilation, normal Soong build, runtime qualification and final
production readiness are distinct gates. Only the source-level checks described
above have completed.
