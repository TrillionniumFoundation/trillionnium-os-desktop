# Owned Bili QA R8: one inspect-only event quiet gate

This new self instrumentation package is `org.droidloom.qa.bili.r8`.
It never instruments, resigns, replaces, or grants permissions to the commercial Bili application.
The protocol is `pocket4-owned-bili-qa-v8`; an R7 wire or installed R7 UID cannot qualify R8.

## Exact change

Only the standalone `inspect` operation performs one `UiAutomation.waitForIdle` call,
after the original non-suppressing connection and immediately before its first original snapshot.
The quiet interval is 500 ms, the global cap is 2000 ms, and the effective global budget is
`min(2000, max(0, operation_started + 8000 - now))`.
Less than 500 ms remaining fails without an API call. Returned waits that exceed the effective
or original operation deadline fail. An already quiet stream may return immediately.

The original 8000 ms operation deadline, 12000 ms watchdog, 2000 ms window deadline,
512-node / depth-32 / 64-child bounds and result byte limits remain unchanged.
There is no new capture retry, input retry, sleep, selector, coordinate, or tree-field exemption.
The exact R7 tree capture, refresh, final full-tree/window action gates, fixed public set_text,
controls reveal and player_button transaction bodies remain unchanged after package renaming.

The gate records one bounded metadata object: requested and effective budgets, actual times,
call count, return/qualification state, error code and original exception class.
A timeout retains its original cause, and a secondary clock error cannot replace it.
A successful event-quiet observation does not prove content readiness or future tree stability.
A later TREE_CHANGED_NULL_CHILD remains that original failure; the event-quiet result cannot
make a partial tree qualify. The other operations have an empty idle observation.

Official API semantics:
https://developer.android.com/reference/android/app/UiAutomation#waitForIdle(long,long)
The API has been available since level 18 and observes accessibility event-stream quiet.
Its event quiet condition is not an atomic Android tree snapshot or action transaction.

## Actual basis and limits

The previous fresh R7 sampled-readiness run failed at its first inspect, before any action:
TREE_CHANGED_NULL_CHILD, 125 emitted nodes, depth 17, child maximum 6, 971 ms incomplete capture.
The newly added 8-read sampling gate never received a complete sample in that run.
This motivates a bounded pre-capture quiet observation; it does not prove the cause or that R8
will avoid future concurrent tree changes. The old failed result is not reclassified or replayed.

## Build-only request and controls

Default entry points print plans. The exact request only stages create-only owned source and
builds a separate test-only APK with a new owned signer; it does not install or touch Android.
The original pinned seven build tools, 230-second build budget, 300-second managed request,
512 MiB memory, one CPU, zero swap and 128-task owned cgroup limits remain unchanged.

The real build first compiles every Python source and executes 32 pure controls against the
actual new protocol parser in its process. It then compiles the exact production idle class
and 22 Java controls into a separate test-class directory and runs them with the pinned JDK.
Only afterward does it compile the APK, with the idle class and without the test classes.
The complete build has 13 joined child commands. Its receipt must bind both control reports
and the Java stdout hash before qa_adapter.qualified_build accepts it.

At source-freeze time, Python/Java compilation and these controls have not run.
This executor is unavailable; an actual Root-dispatched build is still required.
The new APK, signer and installed UID remain unknown. Build success is not Android runtime,
business-flow, restoration, install, or whole-app production qualification.
Whole-app production readiness remains unqualified.
