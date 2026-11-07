# Owned Bili QA R5: confirmed public cache clearing before window reads

This independent self-instrumentation package is `org.droidloom.qa.bili.r5`, protocol `pocket4-owned-bili-qa-v5`. The pinned SDK 31 compile jar, minSdk 31, targetSdk 33, JDK 21 and build/signing chain remain. UI operations now require runtime API 34 or newer; `state` never connects UiAutomation. There is no Activity, native code, network or dangerous permission. Existing helpers and prior failures stay unchanged.

## Actual failure and candidate scope

R4 attempt `1a1aa49ae1a-fc05-4070` failed after the fixed public query edit was acknowledged. The subsequent inspection completed 21 enumerations from 2 to 1,910 ms within its 2,000 ms budget. Window 1303 stayed unfocused and inactive; the event serial advanced from 0 to 5, then stayed at 5. Host foreground before and after named the same Bili search activity. Independent after-state completed and matched before-state. The failed sequence kept restoration_qualified=false. Owned task 887 was removed, Home 851 retained, and Main/source/artifact checks passed. No submit, course click or capture occurred. Periodic rechecks alone did not close this failure; a cache or playback root cause is not established.

R5 calls public `UiAutomation.clearCache()` on its own UiAutomation object immediately before every window query and requires an actual true return. Missing API, wrong signature, false, Exception or Error stops the inspection. InvocationTargetException is unwrapped to retain its original cause. The method is resolved through `UiAutomation.class.getMethod("clearCache")` and must be declared by UiAutomation, public, nonstatic, zero-argument and primitive-boolean-returning. Reflection preserves the compile-SDK-31 input while using the public API added in 34. There is no setAccessible, hidden API exemption, shell permission adoption or alternate fallback.

The 2 s window budget, 100 ms maximum condition wait, 64-query limit, 8 s operation deadline and 12 s watchdog are unchanged. Clearing time counts against those deadlines. Every completed sample records actual clear confirmation. Failures retain bounded counters, last result and exception class without window text/titles. Python qualification requires all samples and the final successful census to have confirmed clearing. Focus, display 0, application type, package and complete-tree/window/action freshness remain mandatory. The 512-node/32-depth/64-child and result-byte bounds remain. Inputs and actions are never replayed.

## Primary sources and limits

The official API 33-to-34 diff lists public boolean clearCache():
https://developer.android.com/sdk/api_diff/34/changes/android.app.UiAutomation

The observed AOSP method obtains its own connection's cache, returns false if absent, otherwise clears it and returns true:
https://android.googlesource.com/platform/frameworks/base/+/HEAD/core/java/android/app/UiAutomation.java

That observed source is Git blob `6f8e335cff804352090b4ba5ef2e8366a5e52a00`, SHA256 `1a311d87d471042b3c769af71afa9896fd5fbd49a1e13675b509c629a6c35c20`. An observed AOSP AccessibilityInteractionClient implementation returns cached windows when available before querying the service:
https://android.googlesource.com/platform/frameworks/base/+/9667c0817d7dbbc42e3eaacd3332ea5db09dda5e/core/java/android/view/accessibility/AccessibilityInteractionClient.java

These sources establish the API and a possible mechanism. They are not bound to the installed Pocket4 framework. Actual new Android execution is required; no framework change is proposed.

## Validation and next admission

Fifteen host Java controls extract actual R4/R5 methods and execute real reflection. Android cache/windows, clock, condition wait and JSON are explicit seams. A synthetic cache-retention counterexample makes R4 fail after 21 reads and lets R5 qualify after five confirmed clears/reads. Other controls enforce false/exception/signature/API-level/deadline/focus/display/query-error rejection. This is not a replay of real Android caching. Twenty-four actual Python contract controls consume those generated observations and reject missing or inconsistent confirmations. Original Session, action and restoration logic remains unchanged.

The build-only entry creates fresh source/output roots and an owned signer. It does not install or invoke Main/UI. Subsequent admission must bind actual new build/APK/signer/UID/state receipts to a fresh flow through frozen R4 held transport. No older helper or success can satisfy those gates. Playback, audio and whole-App qualification remain open.

R4 base manifest: `e54c6f0a2838f4332287224048c58f2884878b4c7bc7b3fd25be415cd0085c17`.
R4 failed coordinator: `96c7128251ac2ebbf5dd14e0af93534d083bddec8c46cd6ab0087ea4f6c3ea74`.
R4 failed stage: `8dae2d95e6095e8894730bb8be2c80b839745a7ecd1515120b0cd962304e13be`.
