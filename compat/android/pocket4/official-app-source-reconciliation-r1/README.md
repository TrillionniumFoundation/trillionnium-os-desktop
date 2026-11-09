# Official app source reconciliation

This addendum records **three complete publisher-delivery SHA256 matches and four pending source reviews** among seven selected packages. Runtime acceptance remains **0 of 42** and `production_ready` remains `false`. This work installed no apps and retained no APK body files.

The comparison target is the historical 42-app manifest:

- Path: `/home/alex/work/pocket4-android-final/qualification/apps-content-bound-20261108-8b88-r1/update_inputs/final-selected42-production-candidates.json`
- Observed at: `2026-11-08T20:13:16Z`
- Bytes: `134742`
- SHA256: `73b7578fe2376f700edd68184ed6e16182bf4b58d3b5c75554a5c597f5f3a603`

No fresh device-installation readback was performed while assembling this addendum. The other 35 cohort members were not reassessed here. `evidence.json` contains the exact historical package/version/signer identities, source records, publisher-document hashes, log byte ranges, authoritative terminal records where supplied, and explicit interpretation limits.

## Three complete content matches

Each result below contains the complete expected byte count and a computed SHA256 equal to the historical APK. The package, version and signer metadata comes from that historical content-bound record; the streamed public bodies were not retained for a second independent metadata or signature parse.

| App | Package | Historical version | Complete bytes | Completed UTC |
| --- | --- | --- | ---: | --- |
| Beike / 贝壳 | `com.lianjia.beike` | 3.06.71, code 3067100 | 228,933,721 | 2026-11-09 07:06:20.027719 |
| Pinduoduo / 拼多多 | `com.xunmeng.pinduoduo` | 8.30.0, code 83000 | 32,690,199 | 2026-11-09 07:23:08.268136 |
| WeChat / 微信 | `com.tencent.mm` | 8.0.80, code 3220 | 286,319,384 | 2026-11-09 07:48:34.132777 |

Exact SHA256 values:

```text
Beike      c7985ed41b91c782af8acb04b1868419cca8bc1fc52862bf6c89fa86b65c81fb
Pinduoduo  3dbdcf5dcc94086dc0bc7d7f378fe1e328d9f32f30b82853fc8f440759d04ad4
WeChat     9d9b6c516e8e07e437c81485fde21fe13ce4f61b37d19e793fff40c71be39c0e
```

The observed publisher routes are Beike's `m.ke.com/client/` download selector, Pinduoduo's `yangkeduo.com/home/download/` page and publisher API redirect chain, and WeChat's `weixin.qq.com` Android link. Public document hashes and delivery endpoints are retained in the evidence. Signed Pinduoduo query values are omitted; the endpoint and original URL/record hashes preserve their binding.

These matches establish byte identity with the pinned historical APKs at the recorded delivery times. They do not establish all-region/store latest-version status after those observations or current installed-state freshness.

## Four source reviews remain pending

| App | Exact package | Recorded result and remaining evidence |
| --- | --- | --- |
| Douyin | `com.ss.android.ugc.aweme` | The official selector and APK endpoint were resolved. The final range attempt hashed 31,457,280 of 364,363,658 expected bytes before a read timeout. No complete body SHA256 was obtained. |
| SZZC | `com.szzc` | The supplied public page and script observations do not establish a verified publisher-selected APK and complete content comparison. A delivery selector and complete APK identity remain required. |
| Taobao | `com.taobao.taobao` | The official navigation → QR → activity page chain was resolved. Its default APK URL is an HTTP endpoint and its version field is empty. An HTTPS metadata probe of the same host/path failed with a TLS internal alert. APK hash, version and ABI remain unqualified. No HTTP fallback or TLS bypass was attempted. |
| Uber | `com.ubercab` | The historical record contains a ten-APK split set. No new publisher/store delivery observation is present in these inputs. Authoritative evidence for the complete compatible split set is still needed. |

The Taobao chain includes a 3900-byte GBK page decoded with `gb18030`, SHA256 `5cb9a819de19077218a5e04e5b522fe573ce1cdab65f16a4bdd148ecac9fb78e`, and a 3244-byte activity page, SHA256 `8fbe09925f7f4a8963327565472652728bb2bcfaca44b3850e16770b9cfe946e`. The activity page's default endpoint is recorded as `http://download.taobaocdn.com/wireless/taobao4android/latest/701483.apk`. The word `latest` in that path supplies no verified version or package identity. Exact PTY creation timestamps are retained; the source's approximate minute timestamp is omitted.

## Per-artifact results and controller terminals

The result of each artifact is taken from its complete parsed record, expected/actual byte count, and SHA256. A controller's exit code is recorded separately.

- Beike's complete match record is present in stdout bytes `[0, 4618)` of job `1a1bf19eac2-5e21-3d3`. The shared controller later timed out with exit 124 and 7066 stored stdout bytes. The supplied page contains the complete Beike result, not the controller's entire final log.
- The original Pinduoduo partial attempt, job `1a1bf27f822-5e21-426`, reported `UNQUALIFIED` after 27,574,272 bytes. Its controller nevertheless exited 0. The later complete Pinduoduo match is a separate artifact result.
- Job `1a1bf2e653f-5e21-43f` exited 0 while recording the Pinduoduo match, a partial WeChat timeout, and the final incomplete Douyin attempt. Two supplied pages cover its entire 6734-byte final stdout without a gap. Exit 0 does not promote the failed artifact records.
- The later WeChat match is a complete final record in the terminal `m3` PTY tail page `[3841, 9357)`. Its authoritative terminal reports exit 0 and complete capture. This addendum does not claim possession of the omitted first page.
- The three Taobao selector/probe PTYs also exited 0 with complete captures. Their successful termination includes an explicitly unqualified TLS result; it does not qualify an APK.

## Memory and action scope

Pinduoduo's original field `max_buffered_body_bytes = 8388608` is represented as **configured inflight range payload capacity, 8 MiB**, with eight concurrent requests. It is not measured process RSS or proof of a total-memory bound. The WeChat record already uses `configured_inflight_range_payload_bytes` and explicitly leaves total memory unqualified. This addendum makes no peak-RSS claim.

All source comparisons remain separate from Android boot and app runtime acceptance. No login, payment, networking, rendering, persistence or production acceptance follows from a binary source match. The supplied action counts are zero app installs, zero retained APK body files and zero accepted runtime apps in the 42-app cohort.

## Evidence custody

The source records were supplied locally; packaging made no network requests. The primary input is 94928 UTF-8 bytes with SHA256 `b68d6de0649363fb5be7580deb3e139a25aebaa262913c53196e45d53c31fa35`. The Pinduoduo terminal and Taobao selector supplement have separate byte counts and hashes in `input_custody.supplements`.

`evidence.json` uses UTF-8 JSON, sorted object keys, compact separators and one trailing LF. It contains selected metadata and complete result projections. Raw input files, publisher page/script bodies, transient signed query values, progress-only log repetition and APK bodies are excluded from the publication. `FILES.json` binds the two deliverable files.
