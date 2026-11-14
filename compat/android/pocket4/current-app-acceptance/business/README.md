# Current official IHG acceptance identity

The selected official IHG application is version **5.110.0**, version code
**50023496**. The existing final app acceptance source still expected 5.108.1 /
50023219. Its metadata and APK guards therefore rejected the selected updated
application before the real business flow could run.

This capsule contains the complete 31-file app acceptance source packet. Only
four literal values in `app_profiles.py` and `ihg_artifacts.py` changed: the IHG
version in both modules, and its current complete APK size and SHA-256. The
remaining 29 files are byte identical. UID, launcher, signer verification,
resource limits, lifecycle checks, Main bindings and business requirements are
preserved. The original preparation remains available unchanged.

## Validation

Run `python3 -I -B test_source.py` from this directory. These 15 host tests
reproduce the prior version/hash rejection, exercise the corrected parsers and
negative cases, verify all source hashes and check exact transformation scope.
They do not communicate with Android or use a private account.

`host-result.json` records the separate pocket4 validation. That run read the
complete official APK, verified its actual aapt2 package/version/launcher and
API 37 v3 signature, and loaded the complete successor with the existing real
preparation validator. It performed zero Android actions and installed no app.

## Adoption

The runtime preparation and new 13-item selector are retained on pocket4; only
selection index 5 changes and all other 12 references remain identical. The
coordinator must compare the original selection SHA before adopting the new
selector in its current checkpoint. `selection-delta.json` identifies both.

Actual application installation, fresh runtime identity observation and the
complete IHG business acceptance still have to run on the accepted Android
cohort. DeskClock remains a separate coherent-OS identity migration. This
source repair gives no application or production readiness credit.

No APK, account database, credential, user content or signing key is included.
The formal repository destination is
`compat/android/pocket4/current-app-acceptance/business/` in PR #300.
