# Owned Bili QA R6: one current-player controls-reveal transaction

This new self-instrumentation package is `org.droidloom.qa.bili.r6`, protocol `pocket4-owned-bili-qa-v6`. It targets itself, queries only `tv.danmaku.bili` UID 10117, and adds one operation, `reveal_controls`. R5 sources, installed helper, prior failures and actual successful samples remain unchanged. There is no Activity, native code, requested permission or network feature. Build-only does not install or invoke Android.

## Evidence and scope

The retired R5 controls-only reader actually examined two complete 153-node observations. Both had zero visible enabled clickable player descendants and no SeekBar. This explains why the existing ACTION_CLICK contract cannot select a pause/seek/reveal node in those observations. The controls reader's original stdout SHA256 is `1b910b63eeca23c80e283c4d7c4c8ebea3c8a2f9e3af6a5e431c68a01387c45b`. Those retired observations authorize no new action. Raw trees, account text and pixels are excluded from this source package.

R6 uses the original Session's new independent inspection, then the helper rereads its complete current tree and final window. Both hashes must match the inspected tree. The fixed course title/author hashes, exact Details activity, focused display-0 application window, two distinct SurfaceView geometries and their complete direct parents must qualify. The current control container must be empty, with no visible enabled clickable player node or SeekBar. The point is computed inside the current crop, at its center with a strict 16-pixel interior margin; arbitrary coordinates are not accepted.

One DOWN and one UP use pointer 0, finger tool, touchscreen source, device 0 and explicit display 0. The event timestamps use uptimeMillis. The production TouchTransaction records attempts before injection; uncertain or failed DOWN/UP permits one CANCEL with a current timestamp, never a repeated DOWN/UP. Every created event has an independent recycle attempt. Primary and secondary failures remain distinct. A successful ACK is insufficient: the helper then reads a third complete tree and requires the same absolute window, crop, player roles and renderer-structure hash. The tree itself may change when controls appear; the complete pre-input tree freshness gate is unchanged.

The result intentionally leaves `controls_revealed` null and business qualification false. A separately observed new control tree is required before selecting pause or seek. No pause, seek, Back, audio or continuous-playback qualification is added here. Post-input complete trees are private evidence, never source/public summary data.

## Public API and bounded failure behavior

The official MotionEvent reference lists the 16-argument public static obtain factory with explicit displayId as API 34. R6 resolves that exact public signature with getMethod, verifies declaring class/static/return type and requires runtime API >=34. It does not use setAccessible, a hidden display setter or a fallback factory. Compile SDK remains pinned API 31, minSdk 31 and targetSdk 33; reflection permits the public newer runtime API without changing those compiler inputs.
https://developer.android.com/reference/android/view/MotionEvent

The official UiAutomation reference documents injectInputEvent as public API 18, returning injection acknowledgement and requiring caller event recycling. It also documents waiting for window animations/surface work. R6 invokes the existing non-suppressing UiAutomation connection with sync=true; it does not adopt shell permissions, grant permissions or change settings.
https://developer.android.com/reference/android/app/UiAutomation

The 150 ms value is the DOWN/UP admission deadline. It is not a hard bound on a blocking Binder call or proof that Android held the pointer for only 150 ms. Hard process termination, VM Errors or a permanently blocked call cannot be guaranteed to execute Java cleanup. A failed/unknown command cannot be retried, and remains subject to the outer held Main guards, timeout, exact owned-task cleanup and later state evidence. The receipts explicitly deny atomic input target attribution: before/after window agreement cannot prove an atomic receiver binding.

Existing 2 s window readiness, 100 ms query cadence, 64-query limit, 8 s operation budget, 12 s watchdog, 512 nodes, depth 32, 64 children and 512 KiB result remain. Public own-connection cache clearing before each query, original ACTION_CLICK/ACTION_SET_TEXT behavior, accessibility state restoration and independent after-state are retained. R6 Session additionally requires unchanged post-action foreground for reveal_controls.

## Verification and next admission

The exact production TouchTransaction compiled under host JDK 17 and passed 16 controls. Inputs, clock and allocation are explicit seams; this is not Android input execution. Twenty-one Python controls run the actual complete-tree parser, player proof, request/receipt predicates and original Session finally with a command seam. They reject partial/wrong-display/wrong-course/extra-surface/interactive/buffering/moved geometry, caller coordinates, incomplete input ACK and cleanup errors. New helper Android compilation, installation and controls reveal are still unperformed.

The exact build request retains pinned SDK31/JDK21/aapt/D8/zipalign/apksigner, 11 commands, 1 CPU, 512 MiB RAM, swap 0, TasksMax 128 and fresh create-only source/output roots. Both Java production files are mandatory inputs. Actual APK hash, actual signer, source/tool receipts and installed UID must be bound before a later fresh owned flow. No old helper qualifies the new request. The host recorder/namespace transport remains the already pinned R4/R5 lineage; no alternate entry or old-v2 fallback is added.
