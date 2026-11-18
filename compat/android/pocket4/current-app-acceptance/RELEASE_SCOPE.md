# Pocket4's 39 required application assessments

The user excluded exactly three unavailable official APKs on 2026-11-18:
TextNow (`com.enflick.android.TextNow`), TextFree (`com.pinger.textfree`), and
Uber Rider (`com.ubercab`). The original 42-package selection remains recorded
in `release-scope-20261118.json`; the other 39 packages remain required.
Exclusions are always reported as `exempt_unverified` and contribute zero passes.

The fixed selection comes from the published historical `CANDIDATE42.json`
identified in that definition. It establishes package membership only. Its old
versions, APK identities and runtime results are not adopted. No existing
42-app contract, historical report, business executor, or installation is changed.

## Produce a report for the actual required scope

Prepare a separately reviewed native release manifest containing exactly the
39 required packages, their current complete identities, the accepted Main,
and all six common gates plus every business gate in their bound profiles.
Keep the original 42-app contract and history intact. Do not fabricate APK
identities for the three unavailable packages or reuse old versions as current.
The native checker already accepts an externally pinned application count:

```sh
droidloom-applications \
  --release-check /absolute/path/manifest39.json \
  --release-results /absolute/path/results39.json \
  --expect-release-sha256 "$MANIFEST39_SHA256" \
  --expect-main-sha256 "$MAIN_SHA256" \
  --expect-app-count 39 > /absolute/path/report39.json
```

This command checks declared evidence and bytes; it does not execute Android
tests. An incomplete report is still emitted with exit status 1. Retain that
status and report. A previous 42-app report cannot be relabeled as a 39-app
report; the checker must calculate a report for the new pinned manifest.

Then bind that native output to the explicit user scope:

```sh
python3 -I -B compat/android/pocket4/current-app-acceptance/release_scope.py \
  --manifest /absolute/path/manifest39.json \
  --manifest-sha256 "$MANIFEST39_SHA256" \
  --registry /absolute/path/app-release-gates.json \
  --registry-sha256 "$GATE_REGISTRY_SHA256" \
  --report /absolute/path/report39.json \
  --report-sha256 "$REPORT39_SHA256"
```

The SHA-256 values must come from independently selected, reviewed input
records. File contents and their self-reported hashes are not a substitute
for these explicit pins. Paths must be absolute canonical regular files.
The tool reads only these explicit files and its fixed scope definition; it
never opens referenced APKs, evidence paths, sockets, accounts or user data.

The native report's manifest hash must match the complete supplied manifest.
This binds the Main, boot, framework epoch, cohort and application identities
without adding invented freshness fields to the native report. Business gates
come from the pinned registry, including all checks in each selected profile;
there are no hardcoded obsolete business gate lists. The registry may contain
additional support packages, which do not alter the fixed selected package set.

## Interpretation and checks

The output retains the native report unchanged and adds a required-39 summary
and the three exclusions. Native global issues keep the result incomplete even
if 39 per-app rows contain complete declared evidence. Missing, failed, blocked
and unsupported required gates remain incomplete. Contradictory counts, unknown
schemas, duplicate keys/packages, empty business definitions and another
manifest's report are rejected.

Exit status 0 means complete **declared evidence coverage** for the 39 required
applications; 1 means incomplete coverage; 2 means invalid input. The output
always retains `production_ready`, `runtime_qualified`, `latest_versions_verified`
and `deletion_authorized` as false. It does not authenticate evidence authors,
prove evidence semantics or freshness, or turn a Clock/IHG partial case into
whole-app acceptance. Runtime qualification, current-version verification and
safe final cleanup still require their original evidence and implementation.

Run the host controls with:

```sh
python3 -I -B compat/android/pocket4/current-app-acceptance/test_release_scope.py
```

All fixtures are synthetic JSON. They do not open any APK, contact a device,
install an application, change permissions, or execute a business action.
