# Owned IHG QA helper R1: build-only candidate

The new self-instrumented package is org.droidloom.qa.ihg.r1. It binds only
com.ihg.apps.android UID 10137 on user/display 0 and the pinned Main epoch.
The current read-only receipt observed version 50023219, one exact 44,999,052-byte
APK, and com.ihg.apps.android/.activity.MainActivity. Those observations are
historical inputs at runtime: the target and launcher must be revalidated before
any future launch. Commercial signer qualification is false.

This source derives from the actually built and installed 12306 R1 helper.
Only target/self package, UID, protocol, escaped scope/resource regex, labels,
source/output paths and known-prior-UID exclusions change. Its exact original
UiAutomation readiness/cache policy, complete tree/window identity, fresh node
validation and state restoration remain. The manifest has no permissions,
activities, services, receivers or providers; instrumentation targets only self.
Java and Python entries admit state, inspect and source-bound ACTION_CLICK only.
Inherited text code stays unreachable. This build carries no click plan or UI
authority, no login/booking/payment/permission/settings/audio operations.

No IHG helper installation, UID, APK hash or signer is assumed. A new real
11-command build must verify its signed bytes, self manifest, seven pinned tools
and output receipts before a separate install/state admission. Known Bili R6
and Ticket R1 helper UIDs, and previous commercial target UIDs, are rejected as
new helper identities. The standalone adapter remains denied; a dedicated IHG
held Main artifact/task adapter and exact-owned-task cleanup must be bound.

The existing SDK31 / min31 / target33 build, 1 CPU, 512 MiB, swap0, 128 tasks,
create-only roots, joined-child/first-error handling and final input hashes are
unchanged. Local predicate controls do not qualify Java compilation or Android
behavior. No commercial UI tree, pixels, APK or private signing material is
included. Whole-app production readiness remains unqualified.
