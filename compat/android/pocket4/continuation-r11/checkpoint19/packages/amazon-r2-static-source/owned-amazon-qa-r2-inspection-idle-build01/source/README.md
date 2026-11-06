# Owned Amazon QA helper R2: one bounded inspection idle gate

This is an independent self-instrumentation package, `org.droidloom.qa.amazon.r2`, with protocol `pocket4-owned-amazon-qa-v2`. Its commercial target remains `com.amazon.mShop.android.shopping`, Android user 0, target UID 10129. The original Amazon R1 source manifest is 08e2a223acae096d6ce4beb5d611395892fe1b2b26d593832510c11af36a4cf3 and its ActionRunner is 77ed79a7ac048f8ef927ac8505843961a2c3bdd0022332ac4fc742d3a676cac3. No Bilibili runtime identity, selector, player path, APK or qualification is imported.

## What changes

A standalone `inspect` calls the public `UiAutomation.waitForIdle(long,long)` once before its first complete-tree capture. Quiet time is 500 ms. The global wait is the smaller of 2000 ms and the remaining original 8000 ms operation budget. Less than 500 ms remaining rejects without calling the API. Timeout, disconnection, clock regression, overrun or a second invocation fails the inspection; no wait, tree capture or input is replayed.

The pure Java gate and its 22 controls come from the independently frozen Bili R8 gate, with package names changed only. Its metadata explicitly describes an accessibility-event quiet interval. It does not claim stable screen contents, a stable future action target or business readiness. The parser binds all 20 metadata fields, operation start/end, budget arithmetic and first capture time.

The failed Amazon05 second observation remains TREE_CHANGED_NULL_CHILD with a partial tree. Event quiet does not convert that failure into a complete tree. The separate host-side first-error attribution repair has its own actual nine-control receipt; it is not an instruction to replay Amazon05 or a new UI admission.

## Guards and scope

The original public clearCache check before each window query, focused application window, display 0, package/UID, complete tree/window hashes, fresh selected node, refresh, single action per nonce and independent state restoration are retained. The 2-second window deadline, 100 ms periodic query, 64-query cap, 8-second operation budget, 12-second watchdog, 512-node bound, depth 32, child bound and 512 KiB result bound are unchanged.

State obtains no UiAutomation connection. Action operations retain their original fresh inspection and entire-tree guards; the idle gate is limited to standalone inspect. There is no shell permission adoption, permission grant, settings change, new Android component, touch input or retry mechanism. The fixed public set-text value remains `usb c cable`; no new search control ID or selector is authorized.

The historical target reference preserves the observed base APK and two split APKs, version 1243240206 and target UID 10129. It is not a new current-state observation or commercial signer verification. The future host flow must revalidate those three APKs and the held namespace/Main/action lock, and bind the newly installed R2 helper's actual UID, APK tuple, signer and noAutomation state. R1 helper UID 10175 is explicitly refused. Standalone adapter execute remains disabled.

## Actual build required

Fresh create-only paths:

- Source: `/home/alex/work/pocket4-owned-amazon-qa-r2-source-01`
- Output: `/home/alex/work/pocket4-owned-amazon-qa-r2-build-01`

The original seven pinned Java/SDK/build tools are retained. No tool update, download or new tool is requested. The API31 compile jar already exposes waitForIdle; the new gate uses no reflection. Existing clearCache public reflection remains unchanged.

The actual build first compiles all pinned Python sources, runs 32 production parser controls in the builder process, and compiles/runs 22 pure Java controls in a separate test class directory. Those classes do not enter the APK. The remaining original 11 commands build, package, align, sign with a new private owned key and inspect the resulting manifest/signature. Thus exactly 13 joined child commands, all 22 Java cases and all 32 parser cases are required by the build receipt and adapter.

The original 230-second builder budget, 300-second job, one CPU, 512 MiB memory, zero swap, TasksMax 128 and first-error/child cleanup remain unchanged. The stage neither installs the helper nor launches Amazon. Private signing keys are excluded from source publication.

## Evidence boundary

This freeze is source and exact-request preparation only. Local Python/Java execution was unavailable and no local syntax, AST or control execution is claimed. V8 performed source hashes, declared patch inversion and exact request/packet checks. The actual build must establish compilation and all 54 controls before any installation is proposed.

No R2 APK, signer, installed UID, Android inspection, input, business result or whole-App acceptance exists at this source cut. A quiet event interval will remain a bounded precondition even after actual controls pass.
