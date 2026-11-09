# Three existing official app matches: fresh route overlay

The earlier published `official-app-source-reconciliation-r1` capsule at commit
`9d45eba81752d1e10906b5dc6d7e9a3c1a6b42c2` already proved complete official
delivery SHA256 matches for these three APKs. This overlay reuses those complete
results, rereads their canonical metadata, and checks current publisher routes.
It creates no APK or partial-download body files and performs no app installation.

| App | Package | Version / code | Complete matched bytes | Original complete hash UTC |
| --- | --- | --- | ---: | --- |
| Beike | com.lianjia.beike | 3.06.71 / 3067100 | 228933721 | 2026-11-09 07:06:20 |
| Pinduoduo | com.xunmeng.pinduoduo | 8.30.0 / 83000 | 32690199 | 2026-11-09 07:23:08 |
| WeChat | com.tencent.mm | 8.0.80 / 3220 | 286319384 | 2026-11-09 07:48:34 |

All three have one arm64-v8a APK. Their full SHA256, signer certificate SHA256,
original observation records and current delivery metadata are in `overlay.json`.
Package/version/signature metadata remains bound to the historical APKs; the
previous complete official-stream hash establishes byte identity. This task
does not claim to have reparsed or reverified signatures on new downloaded bodies.

## Fresh evidence

The publisher pages all returned HTTP 200 at 10:45–10:46 UTC. At 10:52 UTC,
WeChat still selected the exact `weixin8080android3220_0x28005032_arm64.apk`
endpoint, with the same full length and last-modified value as the earlier hash.
Beike's official selector still redirected to the same `20f1e58d/Android_ke_m.apk`,
with the same length, ETag and last-modified value.

Pinduoduo's HEAD request terminated at its public channel API without useful
length metadata. A single bounded GET at 10:53 UTC followed the normal two-step
publisher redirect to the same dated APK path. It returned `206` and
`Content-Range: bytes 0-0/32690199`, with the same ETag and last-modified value.
Exactly one byte was read and not retained as a file. Transient signed query
values are omitted; their observed URL hashes are recorded. They are not required
to be equal across timed deliveries.

The original full hash and the fresh metadata observations remain separate.
Matching URL/length/ETag/last-modified is corroboration, not another full-body
cryptographic readback. The current publisher route is consistent with the
previously matched APK; cross-region/store rollout currency and the current
installed device state are not established by this overlay.

## Preserved state and cleanup

The historical selected42 manifest was reread unchanged at SHA256
`73b7578fe2376f700edd68184ed6e16182bf4b58d3b5c75554a5c597f5f3a603`.
Its older `official_latest_unknown` fields are historical observations; the
published source-match evidence is a later overlay and is not discarded.
The metadata read PTY has an observed exit-zero, complete terminal record. The later close request reported already-exited and did not independently reconfirm termination. Both bounded metadata jobs
are terminal succeeded with complete durable output. No APK or partial files
were created, so there are no duplicate APK bodies to retire in these three
task-owned subdirectories. Reusing the existing proofs avoided repeating
547943304 bytes of complete APK downloads.

No shared selector, CURRENT record, installed app or user data was changed.
This evidence adds no Android boot, rendering, login, networking, persistence or
business-flow acceptance. Runtime and production readiness remain false.
`FILES.json` binds every file in this compact overlay and excludes itself.
