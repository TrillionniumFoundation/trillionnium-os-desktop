# Pocket4 Android — checkpoint 21

Cut: 2026-11-06 12:54:53 UTC. Parent: df9465b6a899fbbd9f8e40294f14185f70880c4f. This is an ongoing repair checkpoint: **0 of 45 whole apps are qualified for production.**

## Current runtime blocker

The previously qualified framework epoch 734fab42… is no longer valid. Amazon's two-table observation was stopped by the epoch guard before any Android command. A separate read-only diagnostic then found the four fixed old framework identities unavailable (ENOENT), including init, so it did not rediscover or adopt another cell. The earlier service observation still showed the same droidloomd daemon/InvocationID; neither the exit cause nor a daemon restart is established. New UI acceptance, old task cleanup and baseline rebinding remain held pending fresh current-cell qualification.

## Repairs and actual validation

- Native registration rollback now retains incomplete endpoint removals and retries only uncompleted work. Host02 seeded the fixture from the exact original Cargo.lock, then passed the unchanged locked-version/checksum/archive gates. Its real production coordinator and Core compiled; all 27 exact tests, 42 commands and 3 child lifecycle controls passed. Actual provider object ownership and remote completion acknowledgements are still being implemented and are not qualified by this result.
- Owner20's observer waits for the exact init DONE event instead of being created after HELLO. All 31 actor/child-view tests and 8 dependency accounting tests passed with explicit OS/clock/constructor seams. The original retained libffi descriptor and false global-FD-equality fields remain visible; independent terminal exit closes that host process lifetime. Actual init/bionic visibility, producer health and the ENOENT cause remain unresolved.
- IHG R3 built and installed with UID10156. The exact current-install/40-nonce-bound London controller passed 157 pure tests. No London UI action was generated or executed. The older Search/Destination pass remains a narrow historical flow only.
- Amazon's native launch error was traced to the closed child message for historical task874 (different_registration_ownership); the launch outcome remains unknown. No Search click or cleanup ran. The fresh current-table attempt was blocked by the changed epoch.
- Bilibili's independent Android task873 retirement passed with task870 preserved. This does not turn the original launch failure into success or prove remote compositor retirement.
- Marriott's new proc-maps tests were missing from the actual APK JNI source list. The source wiring now includes the one-file test group while preserving VerifyTestList. The first narrow ARM64 build stopped before compilation because a new compiler-permission assumption rejected the existing pinned tool; no object or runtime pass is claimed.
- BestBuy's 59 pure controls passed; its fresh UI readiness check remains unrun.

## Preserved failures and timing correction

Native normal03 actually finished with a Soong missing-provider-defaults failure at 09:00:38.640489 UTC, before checkpoint20's 09:09:22 cut. That terminal fact was retrieved later; checkpoint20's RUNNING label describes its last observation, not the eventual execution state. The old checkpoint bytes are retained. Normal04/05 did not start Soong after resource admission failed; normal05 was 69,525,504 bytes below the required fresh MemAvailable threshold.

## Evidence layout

`status.json` and `acceptance-matrix.json` are the current ledger. `historical-acceptance-matrix.json` preserves the earlier 45-app inventory verbatim. `packages/` holds 1495 files from 183 original source/admission/actual archives, with unchanged body bytes. `root-cut-scope.json` and each package's two metadata files reconstruct omitted repeated dependency trees using exact canonical roots. The v2 reconstruction maps are explicitly derived metadata, not original Git API responses. Private baseline and raw Owner runtime content are excluded.

This checkpoint does not deploy or restart Main, merge the PR, qualify Android Binder/Java/JNI framework artifacts, or complete any whole-app production gate. Work continues from the pending items in status.json.
