# Native 46 discovery candidate r1

This is an unexecuted independent read-only observation candidate. It does not
change the current guard, the frozen 45-Launcher permission collector, any App,
or any previous receipt. Device dispatch belongs to the root coordinator.

## Why this observation is needed

The previous actual user-0 PackageManager observation, job
`1a1b22e95d0-fc05-7cd4`, reported 205 installed package/version rows and 45 unique
MAIN/LAUNCHER components. That complete snapshot did not contain
`com.example.ndk_tests`.

Permission batch 03, job `1a1b2eccc8a-fc05-8033`, later failed safely with
`EXACT_ACTUAL45_NATIVE_COMPONENT_REFERENCE_CHANGED`. Its two native reads
completed; it ran no Android query. The native comparison reported exactly one
new component, `com.example.ndk_tests/com.example.ndk_tests.NdkTestsActivity`,
with no missing component. That is evidence of a native catalog change. It is
not yet evidence that the framework resolver has 46 components, that an APK was
installed at a particular time, or that a particular builder installed it.

The three historical inputs in `inputs/` are original byte copies with exact
size and SHA-256 pins. They establish the question. They do not supply current
UIDs, current version names, new APK hashes, or action authority.

## Scope and sequence

The candidate composes the actual `current_services_r4` worker and transport.
The original 47-package scope, eight-role runtime guard, paired classpaths,
native daemon/CLI/socket identities, global action lease, per-observation lease,
Meituan saved location state, and original Bili UNKNOWN check remain in place.
No existing per-App Flow or Beike helper is used or modified.

The exact Android sequence is:

1. `cmd package help`.
2. `cmd package list packages -U --show-versioncode --match-libraries --user 0`.
3. `cmd package query-activities --components --user 0 -a android.intent.action.MAIN -c android.intent.category.LAUNCHER`.
4. Repeat exactly the package list.
5. Repeat exactly the resolver query.
6. `cmd package dump-package com.example.ndk_tests`.

The first five commands are byte-for-byte the existing r4 list. Command six is
an existing PackageManager interface documented in the actual PackageManager
help. It is admitted only after both complete PM/resolver samples agree and the
new package identity has been independently bound. Every namespace entry uses
the unchanged frozen R5 entry/helper protocol with the exact seven held FDs,
user-0 attribution, and Android shell UID 2000. No numeric-PID namespace entry,
ADB, grant, install, lifecycle action, App launch, instrumentation, or UI action
is admitted.

Native reads are status, applications, applications, status. The two complete
native component sets must agree with the two actual framework resolver
samples. Full sets, rather than only counts, must be the original exact 45 plus
the observed new component. The complete PM row delta must be exactly one new
package/version/UID row; a changed old UID/version, missing package, duplicate,
or any additional package/component stops this narrow candidate. Those observed
sets are retained in the failure result before the admission check.

## New-package evidence and limits

The new UID and version code come from the actual user-0 PM list and must agree
with a fresh exact `packages.xml` row. The frozen ABX parser and package signing
record parser are reused. Only the new package's selected scalar attributes and
certificate SHA-256 digests are exported. No certificate DER or other package's
metadata record is copied into the projection.

All of that package's actual base/split APKs are streamed through the frozen
`hash_fd` primitive. The existing APK path enumerator limits a package to 32
APKs and 256 directory entries. The new composition additionally enforces a
hard **512 MiB aggregate / 180 seconds** hash bound, checking the actual held
file size before each hash. Each FD is closed in `finally`. The exact resulting
UID, version code, code path, signer digests, APK path/full stat/hash set, and
CE/DE top-level inode ownership are checked with the frozen
`core.app_scope(..., expected, False)` before the package dump and during all
remaining guarded reads. No private application data contents are opened.

`packages.xml` file metadata and SHA-256 are recorded for each bounded read;
the file path is reopened and compared. Selected new-package metadata must
remain equal across the bind and final check. The entire package database is
not written into an artifact.

The private package dump may contain permission sections, so
`permission_queries_executed=true` is deliberately explicit. This candidate
does not interpret or publish those sections: permission grants and AppOps/
role semantics remain UNKNOWN. Only bounded literal public metadata inside one
exact Package header with the exact fresh appId is projected. Missing,
duplicate, other-user, or unrecognized fields remain UNKNOWN. In particular:

- A service-reported `versionName` is labelled as such. It is not a manifest
  parse or a semantic version inferred from versionCode.
- Literal install/update time fields are not converted from unknown units or
  hexadecimal formats. If a field occurs in an unrecognized user structure it
  remains UNKNOWN; the original private dump is retained for a later exact
  interpretation if needed.
- PM installer/origin fields are service observations. They do not authenticate
  an APK distribution source or prove who ran an installation.
- PM certificate digests are signing-record observations. No fresh apksigner,
  cryptographic integrity, vendor signer, or official-source pass is claimed.

The result proposes the original 47 packages plus this new package as a
**48-package scope review set**. It writes no new versioned scope and publishes
no QA/UI/install admission. A separate reviewed scope and actual APK signature
verification are required before the new item can join a full audit or an
effective-permission continuation. Existing 45-package audit coverage remains
historical coverage of those 45 packages, not current complete 46 coverage.

## Source and resource closure

`SOURCE_INHERITANCE.json` proves exact unchanged definitions from actual r4:
19 worker primitives (including the bounded runner and empty-stream handling),
all 11 transport definitions/classes, 11 owned-lifetime functions, and 6 stage
file helpers. The actual diffs are adjacent. The new worker bodies and the
owner's stricter discovery gate are explicit separate source.

The known libffi bootstrap resource is fixed and frozen exactly as in the
actual r4 owned wrapper. Successful qualification requires the inner worker,
every native/Android child's complete clean join, all observation and lease FD
closure, unchanged whole-process FD count, the outer identity census, the
parent's held-pidfd observation of normal child exit, and restoration of the
parent FD identities. No unknown descriptor is closed or ignored. A timeout,
unjoined child, failed final guard, or inconsistent new identity remains a
failure; there is no automatic retry.

Worker deadline is 900 seconds, owned child deadline 1000 seconds, and the exact
controller request deadline 1100 seconds. The existing per-command limits
remain 30 seconds and 256 KiB per output stream. The compressed artifact/outer
output limits remain unchanged. A larger unexpected dump is a bounded failure,
not a reason to silently truncate or retry it.

`stage_discovery_once.py` preserves the original no-follow, O_EXCL, root-private
0700 directories, root 0400 source files, fsync, readback, and stage FD-count
gate. Its seven members include the three fixed public historical inputs.
It invokes only the exact new owned wrapper after source staging. The request
uses a new unique idempotency key and has not been submitted.

## Review and execution

Review the source, all four diffs, `SOURCE_INHERITANCE.json`, exact request,
stage file/payload pins, and local control output before root dispatch. Submit
`process-request.review-only.json` at most once through the existing controller
process interface. A missing/ambiguous start reply is not permission to create
a new key or repeat the observation. Root must reconcile that exact job and
preserve its original complete stdout/stderr and durable terminal.

The five local boundary controls are real local executions under UID 1000,
with FD identities unchanged and no Main/remote call. Synthetic new-package
UID/version rows are explicitly test fixtures, never observed identities.
They test full-set/old-UID preservation, duplicate native rejection, package/
user attribution and missing values, contradictory PM version rejection, and
the closed six-command list. They do not claim target execution, a root-stage
positive control, current resolver46, signature verification, or production.

The first unexecuted draft is preserved under `draft-01/`; the final candidate
only corrects its explicit reporting of unparsed permission rows in the
package dump. No old evidence or deployed source is replaced.
