# Pocket4 Editor / Probe host support compatibility

This package updates the existing Editor UI03 / QA Probe03 adapter to the current, separately prepared host support. The previous adapter accepted only the old r9/r10 support manifests and rejected the current baseline before collecting package identities.

Only two source files change: `app_common.py` selects the exact host/host-clock manifest paths and hashes; `fixture_entry.py` updates the corresponding rejection message. The other 19 files are unchanged. The new common file is byte-identical to the current business-app r4 source. `migration.patch`, `migration.json`, and `sources.json` provide the exact differences and source identities.

## Local verification

From the repository root, on Linux with Python 3.11 or later:

```sh
python3 -I -B compat/android/pocket4/editor-probe-host-support/tests/test_support_binding.py
```

The twelve tests use only Python's standard library and the source fixtures shipped here. They check current and rejected support cohorts, changed reference/actual-source seals, identity and plan admission, and real local subprocess execution of the inert source-inspection entry. Main-bound loaders, the identity collector, and the mismatched baseline in unit tests are explicit inert fixtures. Tests neither contact a device nor access accounts, NSS groups, user data, or Android.

`validation/local-controls.json` records this package's actual local run. The earlier 17 Pocket4 functional controls have not been rerun. `observation.json` preserves the earlier snapshot before the new Pocket4 result was known. The separate `validation/pocket4-source-inspection.json` records the later actual Pocket4 entry inspection: exit zero, all 21 source files and entrypoints verified, durable complete output, and no Main or Android actions. This inspection does not qualify a runtime or application business flow.

`validation/pocket4-support-bundle-load.json` records a second actual Pocket4 source check. Both exact current host and host-clock manifests loaded successfully; each verified its six pinned source files and imported the three baseline, command and UI entry modules. No BusinessBaseline or ScopeBinding instance was constructed, and no live runtime or account operation was invoked.

The A08 discovery wrapper in `tests/workloads/android/test_pocket4_editor_support.py` loads these same twelve tests and rejects a reduced test count. The source-integrity required inventory includes the wrapper, so deleting it cannot silently drop the controls. On macOS, a canonical TMPDIR is required by the unchanged production path checks; the tests can run with TMPDIR set to an existing directory whose resolved path is identical.

## Device execution boundary

This is reviewable source, not an installation package. Actual execution still requires an independently sealed preparation containing the exact source paths and hashes, the original pinned source/provenance records, the current pinned host support bundle, an accepted final deployment and fresh BusinessBaseline, and new package identities/owned task nonces. The host support checks the separate empty GID 1041 group, its exact host proof and four immutable original group archives, together with the deployed files/cell/drop-in retention set. Historical account-database preimages are not substituted for that current contract.

The original two-task business flows, package UIDs/APKs, input limits, focus and nonce guards, cancellation, and cleanup remain unchanged. Probe retains fourteen input actions and 240/35-second business/cleanup budgets; Editor retains the Unicode, two Enter, emoji deletion and clear flow, at most twenty actions and 360/45-second budgets. Importing or inspecting source does not qualify Main, UI, business, soak, or any of the original 45 whole-app gates.

No production deployment, CURRENT update, service action or shared-runtime claim is made by this package.
