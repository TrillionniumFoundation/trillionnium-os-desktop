# Owned Bili QA R4: bounded window condition rechecks

This independent self-instrumentation package is `org.droidloom.qa.bili.r4`,
protocol `pocket4-owned-bili-qa-v4`. It retains the SDK 31 compile jar, minSdk 31,
targetSdk 33, the original pinned JDK 21 and signing/build chain. It has no
Activity, native code, network or dangerous permission. `state` still never
connects UiAutomation. Existing R1/R2/R3 packages and evidence are unchanged.

## Actual defect and the limited change

R3 buffer/viewport attempt `1a1aa1bd88f-fc05-3d43` failed before query entry,
course click or screenshot. Its second search-page inspection recorded two
unfocused window enumerations at elapsed 1 ms; event serial advanced from 0 to
4. The old method then waited the entire remaining budget and rejected at
2,000 ms without another enumeration. The absent condition recheck is proven;
a stale-cache diagnosis or Bili playback failure is not. Main, source, APK and
owned task cleanup were preserved in that failed attempt.

R4 retains the 2,000 ms readiness deadline, 8 s operation deadline, 12 s watchdog,
64-query bound and strict display-0/focused/application/package selection.
Window events still wake the condition wait immediately. Without another event,
the wait is limited to 100 ms before a new read. There is no click, input or
instrumentation retry and no extra deadline. Enumeration errors remain failures.
No clearCache, reflection, hidden API, service-flag change or new privilege is
introduced. Existing service-info restoration and independent post-state checks
remain required.

Each completed enumeration adds only sample number, elapsed milliseconds and
event serial to a bounded timing list. The original first/last window census
remains. The Python contract validates every timing entry, its first/last census
identity, count and successful deadline. No text or titles enter this diagnostic.
Original 512-node/32-depth/64-child and complete-tree/window/action checks,
fixed public query, gzip wire limits and failure preservation remain unchanged.

## Controls and qualification boundary

The local Java control extracts actual old/new `awaitFocusedWindow` bodies.
Android enumeration, clock, condition wait and JSON storage are explicit seams.
Eleven controls reproduce the old two-query failure and verify bounded rechecks,
permanent unfocused/wrong-display failures, ambiguity, query exception, query
limit, late IPC and recycling. This is an owned temporal fixture, not a replay
of real Android accessibility delivery or a cache test. Seven Python controls
execute the actual metadata validator. Android SDK compilation, signed APK,
installation, current UID and a new business flow require actual new receipts.

The build-only entry creates fresh source/output roots and a new owned signer;
it neither installs an APK nor invokes Main or UI. Later admission must bind the
exact artifact to frozen R4 held transport and a fresh Main/action-lock flow.
There is no older-helper fallback or inherited build/UID success. Playback,
audio and whole-App production readiness remain unqualified.

Base source manifest SHA256:
`91af9446dc2e749ecf3ef75967bfa2154eae8a94a73d9b4149e0574789a5d422`.
Original R3 Java SHA256:
`374c4b3ba1d83a97a376613b2ab2e015006019a61dd36970b27c64693d5bcef5`.
Original failed coordinator/stage SHA256:
`5febc5c0979c8b2b8b65c3d232ef7a5a58ef5a4523b75265b8e41bceb1a72f94`
and `3f722a44958d90dd384fd7150f6bca0eb322f134fbe689c58ba6044c4a2fcce3`.
