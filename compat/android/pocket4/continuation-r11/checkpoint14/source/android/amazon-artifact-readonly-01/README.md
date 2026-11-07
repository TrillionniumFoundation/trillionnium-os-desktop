# Amazon installed identity: fixed read-only attempt 01

This candidate reads the current user-0 identity of `com.amazon.mShop.android.shopping`. It does not launch Amazon, run instrumentation or the legacy v2 helper, use Bili's business scope, interact with UI or audio, change permissions/settings, install/uninstall packages, or access commercial App data. It does not report App readiness.

The historical published Amazon receipt records public query `usb c cable`, suggestions, Back, and close, without completed product-search results. It does not contain a complete current UID/version/APK chain. Its source is commit `0894ebe5c269af391ea4ac4940c6e82c34e69eac`, `compat/android/pocket4/evidence/business-amazon-20261104.json`. Version 1243240206 is only the historical matrix reference and is compared, not asserted current.

## Exact operations

One fresh root is `/home/alex/work/pocket4-amazon-artifact-readonly-01`. Its fixed nonce is `42110205266d417c33e33607204a5d8d`. A create-only stage and worker claim prevent reuse. There are exactly four possible Android commands, executed in this order under the same action lock:

1. `cmd package list packages -U --show-versioncode --user 0 com.amazon.mShop.android.shopping`.
2. `cmd package path --user 0 com.amazon.mShop.android.shopping`.
3. The same path query after hashing the held APK files.
4. The same UID/version query.

Each output must be a complete exact row/set for this package. Unrelated or additional package rows fail. The observed UID must equal the fixed activation's mapping; no UID is invented in this source. Version and paths must remain identical across the two observations. `base.apk` and optional splits must be regular single-link uid/gid-1000 files in one exact `/data/app/~~…/com.amazon.mShop.android.shopping-…/` directory. No arbitrary returned path is accepted.

The target root and all six namespaces are held using the already qualified R5 target. Each APK is opened relative to that held root and streamed in 64 KiB chunks, at most 16 files, 256 MiB each, 512 MiB total and 45 seconds. File metadata must remain unchanged while hashing and through package revalidation, and each current pathname must still name the simultaneously held inode. No APK bytes are copied or exported. Signer certificate verification is explicitly not performed by this metadata-only request; exact APK hashes are not called signer evidence.

## Existing fixed mechanisms

The frozen R4 recorder closure is used only to load its pinned shared primitives and call the actual `Flow.command` method. Neither `Flow.__init__`, Bili `MainBinding`, `BoundArun`, the Bili scope verifier, nor any UI launch/cleanup path is instantiated or monkeypatched. The original method retains command intent/output/result, owns its child session, and joins before return. The new narrow caller permits only the four ordered commands, enforces the exact seven-FD held-entry prefix, and always records lease errors plus the independent post guard without replacing the first error.

Main is checked with the exact `48cb65…` activation, canonical framework module, three host processes, fixed service cgroup limits and configuration before admission, around commands, and finally. Init identity is checked before acquiring held descriptors. The actual zygote and init roots must resolve classpath jars to the same backing objects through the original paired-root routine. The original shared helper ELF and qualified receipt are verified; its exact bytes are rehashed on every guard. The original install03 action-lock routine is reused: EX/NB on one held inode, at most five seconds before any Android command, no lock deletion/replacement/unlocking of another owner. Main is rechecked after lock admission.

The request is bounded at one CPU, 512 MiB, nice 10, 240 seconds. Worker admission limits are 140 seconds, plus independent final cleanup/guard. Each command uses the original held timeout/join path. The 16 KiB output checks occur after the original recorder has retained command output; they are not claimed as streaming output limits. Resource-limit counters must be read from the actual job; no synthetic zero-OOM assertion is made.

## Validation and remaining scope

Eight local parser/first-error controls ran successfully. They call the actual new Context but use explicitly synthetic command/lease seams; no namespace, actual Amazon metadata/APK, or device operation was exercised. The stage and complete request are statically parsed and exactly hash-bound. Peer review is not performed for this new entry; root review and a single actual dispatch remain required. This source is only a preparation for current artifact identity, not Amazon launch/business/search/restore acceptance.
