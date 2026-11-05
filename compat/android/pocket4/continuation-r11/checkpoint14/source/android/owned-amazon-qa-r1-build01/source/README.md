# Owned Amazon QA helper r1

This is a new self-instrumentation package, `org.droidloom.qa.amazon.r1`, derived from the retained Bilibili R5 build02 source. It never instruments Amazon's process. Its only commercial target is `com.amazon.mShop.android.shopping`, Android user 0, actual UID 10129, on the retained Main epoch. Existing Bilibili helpers and the old v2 helper are unchanged.

## Scope and unchanged mechanism

The Java and Python wire contracts retain the R5 public `UiAutomation.clearCache()` check before every window query, focused application window on display 0, exact package/UID, complete tree and window hashes, fresh selected node, and one acknowledged action per nonce. Reflection accesses the public no-argument method because compilation uses the pinned SDK 31 public jar; runtime API 34 or newer and an actual `true` result are required. There is no hidden API or fallback.

The 2-second window availability deadline, 100 ms bounded recheck, 64 query cap, 8-second work deadline, 12-second watchdog, 512 nodes, depth 32, 512 KiB result and existing independent restoration checks are unchanged. A `state` request never obtains a UiAutomation connection. UI operations use `FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES`; no shell permission adoption, setting writes, permission grants, touch exploration, network permission, Activity, service or receiver is added.

`set_text` accepts only the fixed public query `usb c cable`. It requires a fresh observed Amazon resource ID, an enabled visible non-password EditText supporting `ACTION_SET_TEXT`, the exact inspected node and full tree, and actual value readback. No Amazon search resource ID or current screen has been guessed. The future host plan must select a unique control from a new actual inspection; this build does not authorize a click or set-text plan.

## Source and installed target binding

`target-artifact-reference.json` binds the actual read-only metadata run: UID 10129, version 1243240206, the base APK and two split APK hashes, held inode metadata, and the Main epoch. The worker JSON was reconstructed from the actual stdout object using its original serialization and matched the original reported byte count and SHA. This is not a held remote result-file readback, an Amazon signer certificate verification, or a future artifact revalidation.

`qa_adapter.py` retains the source-bound Session library and strict successful-finish, build, installed-helper APK, before/after-state and restoration checks. Its standalone `execute` entry always rejects. It cannot activate the Bilibili business Flow. A separately reviewed Amazon host adapter must bind the current three commercial APKs/UID, qualified held namespace transport, action lock, fresh Main fence and exact newly owned task cleanup before any install/state/launch/UI request is submitted. The existing recorder manifest is a shared source pin only; it conveys no Amazon business admission.

## Build only

The source stage and output roots are fresh and create-only:

- `/home/alex/work/pocket4-owned-amazon-qa-r1-source-01`
- `/home/alex/work/pocket4-owned-amazon-qa-r1-build-01`

Compilation uses the same seven pinned SDK/JDK/build-tool artifacts as the successful retained Bilibili R5 build02. The compile jar is API 31, minimum SDK is 31, and target SDK is 33. The actual build still must compile Java, run D8, package, align, generate a new private owned signer, sign, verify the signer, verify alignment, and inspect actual badging/permissions/manifest. The two instrumentation regex gates derive from `re.escape(PACKAGE.encode())`. No inherited APK, signature, or runtime result is accepted.

The stage remains bounded to one CPU, 512 MiB RAM, zero swap, TasksMax 128, 300 seconds and the original child join/error retention. It runs no Android command and does not modify Main. Signing keys remain in the new private build directory and never enter source publication.

## Qualification status

Only local pure contract/manifest checks and source/request binding checks are recorded in this freeze. No new actual Java compilation, installation, instrumentation, Amazon launch, UI action or business acceptance is claimed. The target APK signer is not independently qualified. Whole-App production readiness remains unproved.
