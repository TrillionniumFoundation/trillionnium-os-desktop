# Current IHG acceptance identity and diagnostics

The selected official IHG application is version **5.110.0**, version code
**50023496**. The preceding identity repair replaced the older 5.108.1 /
50023219 metadata and APK expectations so they match that selected candidate.

This revision fixes the application name reported by the IHG artifact guard.
At base commit `8a1108a4cfcdb91f3d1b4b13a7034b66dd6160cd`,
`ihg_artifacts.py` still used 10 Amazon and 8 Ticket12306 error labels.
Those 18 labels now identify IHG. All validation conditions, package and version
bindings, APK size and hash, permissions, resource limits and lifecycle behavior
remain byte identical outside those string literals. No Android operation is
performed by this diagnostic repair.

The complete acceptance source packet still contains 31 files. Relative to the
pinned base commit, only `ihg_artifacts.py` changes and the other 30 source files
are byte identical. Relative to the original pre-identity packet in
`manifest.json`, the combined changes are 22 exact literal replacements in the
same two files: the preceding four identity values and these 18 diagnostic
labels. The other 29 files remain byte identical to that original packet.
`literal_changes` records the complete reversible transformation, and
`sources` binds the current bytes.

## Validation

Run `python3 -I -B test_source.py` from this directory. The existing 15 host
tests retain their metadata, artifact, version and UID checks, verify all
source hashes and reverse the recorded literal changes to the original source.
The existing old-identity rejection also checks that the exception now names
IHG. These tests do not communicate with Android or use a private account.

`MEMBERS.json` binds the files in this capsule except itself. The diagnostic
revision's base commit, preceding source hash and historical host-result hash
are recorded separately in `manifest.json`.

## Historical host evidence

`host-result.json` remains unchanged: 3,278 bytes, SHA-256
`f2e9ab342fe9ee91d70251fd61bbfa254e4f0eafa2c061173704d822a14e7e6e`.
It records the earlier Pocket4 run for the four-literal identity repair:
complete official APK inspection, the aapt2 package/version/launcher check,
API 37 v3 signature verification and the existing preparation validator.
It performed zero Android actions and installed no app.

That earlier result does not qualify this diagnostic revision. Its
`exact_literal_changes=4` and preparation references intentionally retain their
original meaning. `host-prepare-current-ihg.py`, `source-identity.patch`,
`selection-delta.json`, and the manifest's `source_preparation` and
`successor_preparation` references also remain historical inputs for that
identity migration; they do not describe a new diagnostic preparation.

## Adoption

The prior runtime preparation and 13-item selector were retained on Pocket4
for the identity migration, changing selection index 5 only. This diagnostic
revision has not been prepared or adopted on the device. The current
coordinator must create and bind a new preparation before adopting its changed
source, with the original selection comparison and ownership checks intact.

Actual installation, fresh runtime identity observation and complete IHG
business acceptance still require the accepted Android cohort. DeskClock
remains a separate coherent-OS identity migration. Correct diagnostic
attribution does not close a production blocker or grant runtime acceptance;
`production_ready` and `runtime_qualified` remain false.

No APK, account database, credential, user content or signing key is included.
The formal repository destination remains
`compat/android/pocket4/current-app-acceptance/business/` in PR #300.
