# Pocket4 all Launcher Apps — checkpoint 05

This checkpoint preserves a successful new QA **source preparation**, not a completed App test.

## Verified progress

- Launcher scope remains 45 Apps; 11 native App upgrades are confirmed. Two already-installed Apps exactly match their official current release asset bytes.
- APK evidence is complete for 10 Apps / 14 APKs. Batch 05 remains failed because the old AAPT reader could not parse Calendar badging. No batch 06 has been claimed.
- Fresh Beike source generation job `1a1b17d8002-fc05-7918` succeeded with durable exit 0. Its parent observed the owned child through a held pidfd, a normal zero exit, no forced signal, and restored parent descriptors. The unchanged original worker kept its 5 → 5 process descriptor baseline, closed 1,480 observation descriptors and eight lease descriptors, joined its four native read commands, released the action lock, and confirmed the full 46-package scope unchanged.
- The four published source products were separately read by exact byte count and SHA-256 in job `1a1b18422ad-fc05-794c`. That reader used no Android command and restored its 4 → 4 descriptor count.
- Source staging job `1a1b18ecfc2-fc05-7990` succeeded with durable exit 0 and copied the 13-file helper closure into a new root-owned, UID-1000-readable source directory. UID 1000 cannot modify that source.
- Helper `org.droidloom.qa.successor.p8f89f253350ba2fa.r1` is bound to nonce `b34f158f88bbebf112840fd88df25d03`. Its unprivileged host build was launched as job `1a1b18fedb3-fc05-7998`; its terminal result has **not yet been observed in this checkpoint**.

## Scope of these results

No new helper installation, instrumentation, UI action, login, guest acceptance, App core-operation PASS, long-run PASS, restart PASS, or failure-recovery PASS is claimed here. Production-ready Apps remain **0 / 45**. The old failed source-preparation attempt remains failed. The normal05 framework build remains failed; a complete real-provider closure is being prepared before another build.

The scratch executor reset did not change the target machine. Critical source and raw evidence are retained here; source and input hashes were checked during restoration. Target credentials, private signing material, and account/UI contents are not included.

## Continuing boundaries

Use the existing sidecar and container UI Automator transport, with no new ADB dependency. Keep Bilibili's isolated-cell Accept authorization confined to its original consumed cell; do not replay it on Main. Do not proactively grant Meituan location. Do not bypass App integrity, signer, runtime-ownership, or permission checks. Old Android/framework/App artifacts have not been removed; cleanup remains contingent on verified working replacements and retained reproducible source/configuration.
