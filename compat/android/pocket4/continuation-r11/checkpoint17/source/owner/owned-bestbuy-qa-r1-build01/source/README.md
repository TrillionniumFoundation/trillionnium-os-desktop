# Owned BestBuy QA helper R1: build-only candidate

The new self-instrumented package is org.droidloom.qa.bestbuy.r1. It binds only
com.bestbuy.android UID 10130 on user/display 0 and the pinned Main epoch.
The current read-only receipt observed version 2012312321, three exact APKs
totalling 245,511,693 bytes, and com.bestbuy.android/.activity.SplashActivity.
All base and split paths, hashes and held-file metadata are bound in the source
reference. These observations become historical inputs at runtime: the complete
artifact chain, target identity and launcher require fresh checks before launch.
Commercial signer qualification remains false.

This source derives from the actually built IHG R1 helper. Only target/self
package, UID, protocol, escaped scope/resource regex, labels, source/output paths
and known-prior-UID exclusions change. The exact original UiAutomation readiness
and cache policy, complete tree/window identity, fresh node validation and state
restoration remain. The manifest has no permissions, activities, services,
receivers or providers; instrumentation targets only self. Java and Python admit
state, inspect and source-bound ACTION_CLICK only. Inherited text code remains
unreachable. This build includes no click plan or UI authority.

No BestBuy helper installation, UID, APK hash or signer is assumed. A new real
11-command build must verify its signed bytes, self manifest, seven pinned tools
and output receipts before separate install/state admission. Prior IHG commercial
UID 10137 and actual IHG helper UID 10196 are additionally excluded from candidate
helper identity. Prior build, install and launch qualification never transfers to
BestBuy. The standalone adapter stays denied; a dedicated BestBuy held Main
artifact/task adapter and exact-owned-task cleanup must be separately bound.

The existing SDK31 / min31 / target33 build, 1 CPU, 512 MiB, swap0, 128 tasks,
create-only roots, joined-child/first-error handling and final input hashes are
unchanged. Local predicate controls do not qualify Java compilation or Android
behavior. No commercial UI tree, pixels, APK or private signing material is
included. Whole-app production readiness remains unqualified.
