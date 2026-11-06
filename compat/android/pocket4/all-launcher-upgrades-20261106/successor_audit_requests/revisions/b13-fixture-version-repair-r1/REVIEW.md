# Independent b13 fixture version correction

## Actual failure and evidence

The original b13 job `1a1b2ab7980-fc05-7f3a` remains **FAILED**, with its original
ledger at STOP. Its nine tools all exited normally with code 0 and its three APK
signature checks matched PackageManager. The only manifest parse failure was
`AAPT_PACKAGE_VERSION_REQUIRED` for `local.pocket4.fixture`.

The independent fixed reader job `1a1b2ae8cd7-fc05-7f48` then returned the two
complete original streams with their fixed SHA256 and stable file/FD checks:

- badging: 686 bytes, SHA256
  `28b2cf92369048b078c8fbf337bf8ae08173f49768e946baee8421bb0d0860b5`;
- XML tree: 1244 bytes, SHA256
  `2deafdbfa41af5daf85f7980a82491408b1472bcb5aafb0904fa1ea72e9b351f`.

Badging explicitly prints empty `versionCode` and `versionName`. The XML root
has the correct package but no `android:versionCode`, `versionCodeMajor` or
`versionName` attributes. It reports minSDK 26 and targetSDK 35. These facts
are actual raw observations, not a guess from PM version 0.

## Primary platform evidence

[AOSP PackageImpl at commit 13f9d65c456ee75c488b5d5eccdaa277437528ef](https://android.googlesource.com/platform/frameworks/base.git/+/13f9d65c456ee75c488b5d5eccdaa277437528ef/core/java/com/android/internal/pm/parsing/pkg/PackageImpl.java)
(blob `73df5e8e7b1bbf943a03c852bb5fa1ff8b10fa89`) initializes both manifest
version code attributes with integer default 0 in its constructor.
[AOSP PackageInfo](https://android.googlesource.com/platform/frameworks/base.git/+/main/core/java/android/content/pm/PackageInfo.java)
documents an absent version name as null. `ANDROID_DEFAULT_SEMANTICS.json`
records these primary references. They establish Android's missing-attribute
semantics; they do not claim to be the exact source of Pocket4's live ELF.
The live PM code 0 and the complete actual XML independently agree with that
default for this exact APK.

## Narrow code change

The original generic `badging_manifest` function is byte-for-byte unchanged.
Two new functions verify the exact fixture XML and parse only this known
fixture's absent version. The dispatch for every other package calls the
original parser. The special path requires all of the following together:

- the complete pinned fixture scope, package `local.pocket4.fixture`, UID
  10115, PM version code 0, exact CE/DE identities and one APK;
- APK 12713 bytes, SHA256
  `91e352c25e7c6ef54aa53ce652931e40ad1437dfcd0ebad2529bc662558a3dd6`,
  with its exact scoped path and full stat;
- a fresh ordinary successful apksigner command, with no minimum SDK override
  or integrity bypass, and signer matching the actual pinned PM certificate;
- exact raw badging and XML stream bytes, a unique XML manifest root and
  matching package, all three version attributes absent, and the two literal
  empty badging fields.

The result keeps declared `version_code`, `version_code_major` and
`version_name` null and preserves the empty raw strings and original package
line. It separately reports effective `long_version_code: 0` with the XML,
fixed APK, PM and primary-source basis. It does not invent a display version.
Missing XML, an explicit/conflicting version attribute, nonempty/missing
badging version fields, changed package/UID/PM/APK, or signature failure are
rejected. No APK bytes, package signatures or PackageManager behavior change.

## Full corrective run still required

This is new source and a new independent output root, not a replay of the
failed job. `REPAIR_PLAN.json` binds that original failed job, terminal,
artifact, immutable remote result and original request. The worker checks the
original failed publication before and after the new audit. The original
b05 failure/correction lineage remains intact as well.

The proposed run reobserves the exact original b13 group:
`local.pocket4.fixture`, `org.chromium.webview_shell`,
`org.droidloom.qa.editorcontract`. All three APKs and nine tool commands are
required. The 19 legacy and 7 official tool dependency bindings, 20 complete
RUNPATH/absence observations, ordinary signatures, PM signer agreement,
typed runtime guard, current three-package byte/stat/data bindings, action
lease and owned child/FD retirement remain in force. The 47-package document
is the fixed reference; this APK worker actually rechecks these three packages.

Twenty-two existing collector definitions and eleven owned-wrapper definitions
remain byte-for-byte unchanged. The changed collector definitions are only
`validate_request`, `audit` and `main`; the two fixture adapters are additions.
The wrapper changes only CONFIG and its joint worker gate. The existing stage
keeps its O_EXCL, nofollow, root ownership, fsync, complete readback and exec
behavior, with fresh paths, exact three-source pins and schema labels.

The actual old b13 FAILED and old serial STOP are never edited or overridden.
A later local linkage may associate a **new actual** successful correction
with that failure only after complete outer stdout, a durable successful
terminal, all nine commands, signatures, guards and original child pidfd/FD
retirement are verified. No such successful runtime correction is claimed by
this source candidate or its local controls.

## Local controls and limits

Seven offline controls use the fixed actual raw logs and actual earlier
signature receipt only as parser fixtures. They prove the original parser
still rejects this case, the narrow adapter records absent/empty values, and
wrong XML/version/scope/signature contexts reject. They also compare the
other-package numeric path to the unchanged original parser and verify the
exact source/request/stage closure. They run no APK tool, Main command or
remote job, and do not establish a fresh runtime signature.

No new permission/role conclusion, application core-operation success,
resource-table integrity claim, full 45 coverage, production-readiness claim
or cleanup follows from these local controls.
