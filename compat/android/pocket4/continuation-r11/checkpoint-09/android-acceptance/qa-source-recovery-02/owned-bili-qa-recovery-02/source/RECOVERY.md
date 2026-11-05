# Owned Bilibili QA helper: recovery-02

## Why this is a new source freeze

The workspace transport became unavailable after source-freeze-01 and its request had been written, but before the last packet-binding command could start. Neither request01 nor this request02 has been submitted by the acceptance agent. No helper has been compiled, installed or used on Android.

All seven original production texts were recovered from this thread's full reads and patches. Their UTF-8 byte counts and SHA256 values match the exact pre-disconnection pins. The recovered originals are retained separately in the same independent Git tree.

This recovery source changes only four literal values in three files: the builder output path, the stage source/output paths, and the request key, from 01 to 02. The exact patch is included. Java, manifest, protocol and runtime adapter are byte-identical to freeze01. No behavior or qualification predicate was relaxed.

The original 12-payload SOURCE_PINS hash was 851c87a1b4054d730c3b6c24e904e221f60730935c08bf3251efde140483bc4a. The original archive was 40622 bytes, SHA abc502dbf3633adcd832c751baa84c36f5118df98e6d9cfbb940d6c03f3a86a2. The original request was 155658 bytes, SHA 57bf5d9972bfea67c5abbd0fb32a7336a290a9f992439b3c7a715b202f428ef0. These remain historical references; their full bytes have not been reread after the disconnection.

The original local controls command actually reported 30/30 PASS, with result SHA 0973805469ae3c9f38bc8ac8a8917d27df7ae9b540533a34fe39d38f36788d1c. It covered synthetic wire/selector/restoration/build-receipt controls, four actual owned host child command/close controls, and default PLAN CLIs. The complete result file is unavailable here. It is not reconstructed, included or represented as independently rerun evidence. The last packet-binding command failed at exec-server process creation and did not execute.

## Source and authority

The new package is org.droidloom.qa.bili.r1. Its instrumentation targets itself. It has no requested permissions, Activity, Service, Receiver, Provider or native library. It is testOnly, nondebuggable, and disallows backup. Compile API is the pinned SDK31 public jar; minSdk is 31 and targetSdk is 33.

Only state, inspect and one ACTION_CLICK are supported. State does not connect UiAutomation. Inspect/click use DONT_SUPPRESS_ACCESSIBILITY_SERVICES and the Bilibili-only focused window on display0, UID10117, user0, fixed Main epoch48cb. They cannot enter text, inject coordinates/keys, adopt shell permissions, run shell commands, grant permissions, change settings or request touch exploration. Node count/depth/child/text/time limits and exact inspection hashes remain in Java. A unique private nonce claim prevents a framework redelivery from repeating an action.

Click acknowledges dispatch only; business success and audio remain unverified and outcome_unknown remains true. The helper restores/readbacks only its own ServiceInfo flags/capabilities, reports global restoration null, and the adapter requires a separately completed no-UiAutomation state after the real command/finish. No hardcoded restoration=true is accepted.

The adapter reuses the exact recorder R3 manifest 4ff896b75c4c7751a28eee34ab512583c3a26eb43f5e28598a776d40ee496906: original action lock, Main epoch/config/process/limit fences, held namespace/root entry, private zygote classpaths, once-only step/command evidence and task ownership. Inspect/click require the original owned launch scope and exact task checks. No launch or cleanup replacement is introduced. The old v2 helper and its unresolved APK provenance are not adopted or replaced.

The new APK has independent source/build/signer/installed-byte gates. Runtime requires an externally pinned actual build receipt, exact APK and certificate hashes, explicit new UID, and a fresh original-recorder flow. It hashes the installed single base APK through the held Android root before/after. No runtime is admitted by this recovery.

## Build-only request02

The exact request uses key pocket4-owned-bili-qa-r1-static-build-02-20261104. It stages into /home/alex/work/pocket4-owned-bili-qa-r1-source-02/source and builds into /home/alex/work/pocket4-owned-bili-qa-r1-build-02. Both roots must be absent. Stage and build use UID1000 and no sudo/Main command. The current owned managed unit must have CPU100% and RAM512MiB; stage sets only that unit to swap0/Tasks128 and reads its identity/counters before and after. Any owned oom/oom_kill/oom_group_kill rejects. Outer timeout300s; build command aggregate deadline230s; no automatic retry.

Actual build must verify the seven prior tool/content pins, compile Java8 with JDK21 and SDK31, run D8, package/align, create a new private owned RSA signer, sign v2/v3, and verify signature/permissions/components/SDK/manifest/DEX. The fresh key is created through the pinned Java runtime's keytool module. All eleven commands must join and return0. Source/tool mappings and bytes are rechecked. A failure retains its first error, logs and attempt, including subsequent close/readback errors.

The real SDK31 compile, new keytool-module invocation, actual aapt XML shape and all Android behavior remain unexecuted. The parent must review and submit one exact build-only request. No install, UI, audio, Main deployment or whole-App readiness follows from creating this source tree.

Expected receipts:
- /home/alex/work/pocket4-owned-bili-qa-r1-source-02/stage-result.json
- /home/alex/work/pocket4-owned-bili-qa-r1-build-02/build-result.json
- /home/alex/work/pocket4-owned-bili-qa-r1-build-02/owned-bili-qa.apk

Do not publish or export private-signing/owned.p12 or private-signing/password.txt, APK/DEX/classes, private UI evidence or activation bodies. Public artifact/signature hashes and bounded owned result summaries may be retained. No commercial app data was read in this recovery.

Official API references (not an exact device-framework source audit):
- https://developer.android.com/reference/android/app/Instrumentation#getUiAutomation(int)
- https://developer.android.com/reference/android/app/UiAutomation#FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES
- https://developer.android.com/reference/android/view/accessibility/AccessibilityNodeInfo#performAction(int)
