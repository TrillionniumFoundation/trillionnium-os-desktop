# Independent review of current_services_r2

Review type: local source and retained control evidence only. No Main or remote command was submitted by this review.

Reviewed complete 37,779-byte worker SHA-256 `391ab40c114c9b47e201f7de9ed29bd7a86869caf1383b46f0589dc5a8995c2f`, the exact read-only transport and runner differences, full worker finalization, the outer `services` gate, r1-to-r2 minimal diff and the actual single owned-child timeout result. The original r1 remains frozen and unexecuted.

## Resolved blocking defect

The standalone r1 `safe_error` referenced undefined `Rejected` although its `need()` raises `RuntimeError`. The failure branch could lose the original structured error and interrupt cleanup. R2 changes only that recognition to `RuntimeError`, retaining the closed uppercase error-code expression, plus explicit revision roots and dependent pins. The actual timeout control reports `CHILD_TIMEOUT`, return code -9, joined and reaped owned child, incomplete command retained as failure, no output, and process FD count 4 to 4. It is a real local owned child, not a Main experiment. The original frozen core remains unchanged.

## Command and evidence review

The transport admits exactly seven ordered Android argv values:

1. `/system/bin/cmd package help`
2. `/system/bin/cmd appops help`
3. `/system/bin/cmd role help`
4. `/system/bin/cmd package list packages -U --show-versioncode --match-libraries --user 0`
5. `/system/bin/cmd package query-activities --components --user 0 -a android.intent.action.MAIN -c android.intent.category.LAUNCHER`
6. The same package-list argv as 4.
7. The same resolver argv as 5.

The actual package help must admit the required syntax before either query is sent. This is not a statement that the help or commands have already succeeded on the device. Unexpected help, exit status, stderr, row syntax, duplicate identities, truncated/oversized output, guard drift or disagreement between the two PM/resolver samples fails closed, with no retry or next command after a transport error.

Three native reads are `status`, `applications`, `status`, under exact UID 1000/socket/CLI/daemon bindings. Each passes frozen `core.native_running`, which requires complete, joined, return code 0, running response and the actual expected owner. No native lifecycle or launch request is present.

The independent 47-package app scope is pinned directly, without borrowing the compiled two-package Beike Flow. Current process/classpath/app identities are checked before and after each command; original R5 root plus six namespace FDs and environment are fixed. The shared namespace helper's actual qualification remains mandatory. Meituan saved location and original Bili UNKNOWN are checked without alteration. Target closure, observation/lease FD retirement and lock release are required; outer acceptance additionally requires the original explicit library resource identity, exact worker FD identities, normal parent-held child pidfd exit without forced termination, original final stdout and durable success.

No further static blocking defect was found in the reviewed revision. This conclusion is not actual service-query success or QA admission.

## Exact semantic limit

Successful output would enumerate the current user-0 installed APK packages exposed by the exact command, including requested static/shared SDK library entries, and current MAIN/LAUNCHER resolution. It does not include APEX or deliberately force disabled/uninstalled components. New packages or launcher differences are reported explicitly; they are not silently omitted or automatically granted APK-byte or UI authority. `all_installed_APK_bytes_bound` stays false. Effective runtime grants remain UNKNOWN; AppOps/roles remain help-only UNKNOWN. The result cannot certify a currently installed version as latest, a login/core operation as working, or any package as production ready.
