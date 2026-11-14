# Official application input refresh — 2026-11-09 16:52–16:55 UTC

Two changed publisher download routes were resolved to complete, independently inspected APK files. These are replacement input candidates for two of the existing 13 public candidates. They do not increase the selected application count or grant runtime acceptance.

| Application | Current package version | Complete APK bytes | Full SHA-256 | Result against earlier candidate |
| --- | --- | ---: | --- | --- |
| Beike / `com.lianjia.beike` | `3.06.71` / `3067100` | 228991122 | `6984af4bbeda2818ad0a35183dd59af798eceebb9e441ef869b32dcc5095f728` | Same version, same signer and ARM64 ABI; different bytes from the earlier `c7985ed4…` file. |
| Air China / `com.rytong.airchina` | `7.53.3` / `75303` | 207069802 | `f16f429b21c3402b362f5d3058476dfd97c29986f688e95e0d5294368d104fab` | Newer than the earlier `7.53.2` / `75302` candidate; same signer and ABI set. |

The Air China publisher page still contained the old `7.53.2` text. The version in the signed, downloaded APK is `7.53.3`. Page text alone cannot close this currency gate.

## Complete verification evidence

`full-artifact-verification.json` is the exact remote `RESULT.json`: 25453 bytes, SHA-256 `1f0cbf58d1d2568b797e2f9e2c8c34a8abbd4ad5b785324a0292ac21502de37a`. Its two records bind the prior catalog digests, publisher URLs, complete new file digests, command arguments, command exits and output digests. The successful download/verification job was `1a1c139c682-e62c-39`; its authoritative terminal receipt reports exit 0, complete logs and durable output. The source and result files are copied here without reformatting.

Both APKs were obtained over HTTPS, with certificate verification enabled, using the existing publisher route. Each download completed with HTTP 200. A new invocation of `/usr/bin/aapt dump badging`, `/usr/bin/aapt dump xmltree … AndroidManifest.xml` and `/usr/bin/apksigner verify --verbose --print-certs` returned exit 0. The APK identity remained unchanged throughout verification. The ZIP directory contained one manifest and the expected native ABI set, with no duplicate entry names. A separate full ZIP CRC pass was not performed; this is explicitly recorded.

Beike has one signer, SHA-256 `0b66624117621bb9bc3e7d12a1fe5436794cf8999b0253d9ff9bec71e0932178`, and `arm64-v8a`. The verifier accepted v1 and v2 signatures and emitted 86 existing-style META-INF coverage warnings; the full stdout is retained, including the warnings. Air China has one signer, SHA-256 `b48f75514e956be6bd7d56f1701136c8d76f19459bd724ac52390a572bc0ecbf`, and `arm64-v8a` plus `armeabi-v7a`. Its v2/v3 signatures verified without warnings. Air China's target SDK is 36. Neither manifest declares `debuggable`, `testOnly` or `isSplitRequired`.

`source-input.json` is the exact input projection actually executed. Two unused, historical `mtime_ns` values in that projection crossed a JavaScript numeric boundary and were rounded. `source-projection-notes.json` records the original and executed values explicitly. The prior catalog SHA, prior APK SHA, package, version, ABI and signer fields are unchanged. No admission decision uses those historical timestamp fields. New APK identity checks ran entirely with Python integers on Pocket4, without this JSON conversion. The original prior catalogs remain the authority for their historical stat records.

The files under `oneoff-executed/` preserve the exact one-off orchestration used in this observation. They are execution evidence for existing curl/aapt/apksigner commands, not a new maintained tool or a CI/runtime acceptance harness. Their destination directories are exclusive, and rerunning them against an existing directory is not an update operation.

## Pinduoduo and Douyin route follow-up

The exact bounded GET and script observations are in `route-get-result.json` and `publisher-script-result.json`. The GET discovery job `1a1c13a8e89-e62c-3b` and script retrieval job `1a1c13c2271-e62c-3d` both finished with exit 0 and complete, durable logs.

Pinduoduo's current official download page references a 7391-byte download script, SHA-256 `26c696a3319817434ccb6fef7852b4847cc86606715c62986831edb6cc8584c7`. Its 64-bit button constructs `https://home-api.pinduoduo.com/homesite/download-app-v2?rs=0&arch=arm64`. An actual bounded GET follows the official `baidu_seo/arm64` route to the same `1479984c21f48ccaa8756af217ba8371.apk` object as the earlier complete candidate, with `Content-Range` total 32690199. The earlier HEAD response's `guanwang` channel is retained as a method-dependent observation; it is not substituted for the page's GET route.

Douyin's current page references the same 42611-byte Android download script as the earlier source chain, SHA-256 `d8c48c8aa7f4a23b0134f683ff138088d5e6e2f8c225d3272aea738ee9435fdd`. Its 64-bit button still links to `https://ugapk.com/mGFG`. An actual bounded GET succeeds with HTTP 206 and reaches the same `lf9-apk.ugapk.cn` version `410001` object, total 364363658 bytes. The HEAD 404 is not a failed GET delivery gate.

These two route checks fetched only the first 65536 APK bytes. They do not constitute a second complete APK hash/signature verification. The earlier independently verified full candidates remain distinct evidence. No new runtime or complete-file credit is assigned to the range responses.

## Adoption and custody

The two newly downloaded APKs are retained, read-only, under `/home/alex/work/pocket4-official-drift-20261109-2840-r1/<package>/official-current.apk`. The candidate flags remain `installed:false`, `canonical_custody:false`, `selected:false`, `runtime_qualified:false` and `production_ready:false`. They are ready for the active owner to copy under its canonical custody and adopt with the exact digests above. Neither this observation nor this capsule changes shared CURRENT, the selected catalog, a preparation, an Android package, data.img or metadata.img.

Adoption still requires owner coordination, replacement of the old input references, a matching fresh generation/Main, installation and the actual application business gates. Existing source/application acceptance remains **0 of 42**. The old Beike and Air China artifacts cannot be retired while the active owner still references them. The new files cannot be removed from the isolated directory before their exact canonical replacement custody is confirmed.

`FILES.json` records every capsule member except itself. Its manifest and the exact evidence bytes are frozen for publication. This is an input/source refresh receipt; no Android operation was performed.
