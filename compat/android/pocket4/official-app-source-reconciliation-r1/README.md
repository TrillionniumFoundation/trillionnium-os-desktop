# Official app source reconciliation

The latest integrated evidence confirms sources for **six of the seven packages reviewed here**: three complete publisher-delivery matches to the historical selected APKs, and three newly prepared official candidates with recorded full-body hashes and fresh `apksigner` results. **Uber's latest complete delivery remains unknown.** The three new candidates still await adoption; they are neither selected nor installed, and runtime acceptance remains **0 of 42**. `production_ready` remains `false`.

This is a seven-package source reconciliation. It does not reassess the other 35 cohort members or establish a global maximum version across stores, regions or staged rollouts. No APK was downloaded, copied, installed or selected while packaging this addendum. The three complete candidate APKs remain in the owner's existing canonical custody.

## Latest result by package

| App | Package | Source result | Remaining adoption or delivery gate |
| --- | --- | --- | --- |
| Beike / 贝壳 | `com.lianjia.beike` | Complete publisher body matches the historical 3.06.71 / 3067100 APK. | No runtime acceptance follows from the match. |
| Pinduoduo / 拼多多 | `com.xunmeng.pinduoduo` | Complete publisher body matches the historical 8.30.0 / 83000 APK. | No runtime acceptance follows from the match. |
| WeChat / 微信 | `com.tencent.mm` | Complete publisher body matches the historical 8.0.80 / 3220 APK. | No runtime acceptance follows from the match. |
| Douyin / 抖音 | `com.ss.android.ugc.aweme` | Complete official candidate 41.0.0 / 410001; fresh v1/v2/v3 verification. It has the historical version and signer but different bytes. The independent 10:33 UTC complete stream produces the same new SHA256. | Adopt the exact canonical body, then perform the required runtime acceptance. |
| Taobao / 淘宝 | `com.taobao.taobao` | Complete official candidate 10.69.0 / 866; fresh v1/v2 verification. It has the historical version and signer but different bytes. The successful current route is a different official endpoint from the earlier TLS failure. | Adopt the exact canonical body, then perform the required runtime acceptance. |
| SZZC / 神州租车 | `com.szzc` | Complete official candidate **9.6.2 / 328**, replacing historical 9.6.1 / 327; fresh v1/v2 verification and the same signing certificate. Independent official QR/selector and bounded metadata observations corroborate the route and version declarations. | Adopt the exact canonical body, then perform the required runtime acceptance. |
| Uber | `com.ubercab` | Official help points to Google Play. No complete latest base APK and required splits were delivered by the observed anonymous official route. | Obtain the complete authoritative compatible delivery. Public listing dates and review version strings do not establish binary currency. |

The three historical matches remain matches to the recorded historical selection, not proof that those packages are still installed or are the newest in every channel. The owner handoff records `selected=false`, `installed=false`, `runtime_accepted=false` and `production_ready=false` for all three new candidates.

## Published owner evidence and canonical candidates

The current candidate evidence is attributed to commit **`0d4ac0c18158ad2aa9e1f48195f3cfe9703d5646`**, directory `compat/android/pocket4/continuation-20261109-be1746a/apps/`. Packaging independently recomputed the UTF-8 byte size, SHA256 and Git blob SHA1 for all nine supplied documents. It also recomputed each complete raw signature stdout/stderr hash and checked the recorded command exits, package declarations, certificate digests and scheme results. It did not rerun those APK inspections.

The existing source documents remain the authoritative complete records:

- [Source increment and official route chains](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/0d4ac0c18158ad2aa9e1f48195f3cfe9703d5646/compat/android/pocket4/continuation-20261109-be1746a/apps/source-increment.json)
- [Owner handoff and remaining gates](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/0d4ac0c18158ad2aa9e1f48195f3cfe9703d5646/compat/android/pocket4/continuation-20261109-be1746a/apps/app-handoff.json)
- [Douyin inspection, including raw signature output](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/0d4ac0c18158ad2aa9e1f48195f3cfe9703d5646/compat/android/pocket4/continuation-20261109-be1746a/apps/douyin-inspection.json)
- [Taobao inspection, including raw signature output](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/0d4ac0c18158ad2aa9e1f48195f3cfe9703d5646/compat/android/pocket4/continuation-20261109-be1746a/apps/taobao-inspection.json)
- [SZZC inspection, including raw signature output](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/0d4ac0c18158ad2aa9e1f48195f3cfe9703d5646/compat/android/pocket4/continuation-20261109-be1746a/apps/szzc-inspection.json)
- [Canonical manifest receipt](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/0d4ac0c18158ad2aa9e1f48195f3cfe9703d5646/compat/android/pocket4/continuation-20261109-be1746a/apps/canonical-final-manifest-receipt.json) and [independent readback receipt](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/0d4ac0c18158ad2aa9e1f48195f3cfe9703d5646/compat/android/pocket4/continuation-20261109-be1746a/apps/independent-readback-receipt.json)

The sole canonical candidate directory named by these receipts is:

```text
/home/alex/work/pocket4-android-final/cohorts/qpr1-cp3a-16176746-20261108-8b88-r1/official-app-inputs-be1746a-r2
```

| Candidate | Complete bytes | SHA256 | Verified schemes |
| --- | ---: | --- | --- |
| `douyin-41.0.0-410001-official.apk` | 364,363,658 | `b1d8834c20e5dbd75e2d48b5b30dea67be88f6903dba78a78d736a80b7feff2f` | v1, v2, v3 |
| `taobao-10.69.0-866-official.apk` | 95,212,303 | `75d76b60cbedf1a5fa1fe53184fca481d5bcef696c8a8134145925644b691808` | v1, v2 |
| `szzc-9.6.2-328-official.apk` | 220,267,107 | `c8611c1828fec03b7363a10cdc4da97c8bca1f0cf5ec91dff0c3b1e66337360f` | v1, v2 |

Their observed signing certificate SHA256 values are:

```text
Douyin  5182ae3b1b85337bb182cf24882449f84447ded18e296a747a9f6a0a2622512e
Taobao  c5e9bc4c5cc7a34482c627cb9a76b88e30b509d0da3ba54a66274200e19c2743
SZZC    d85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44
```

Each equals its respective historical certificate. Douyin declares `arm64-v8a`; Taobao and SZZC declare `arm64-v8a` and `armeabi-v7a`. The raw verifier outputs retain **41, 36 and 67 META-INF warnings**, respectively. False scheme and SourceStamp flags remain recorded; the results are not described as warning-free.

`CANDIDATES.json` is 22,015 bytes / SHA256 `90e9265a63aa83708c87160dcb3b27f5f40c66202fdec0360c7918e9774ce3d1`. `MANIFEST.json` is 10,238 bytes / SHA256 `63ea9fd4fcadd28646cd25fdcb38a6e6c0ae7a054a613a79fb3b63bc9c49e415`. The published independent readback, **2026-11-09 09:51:10–09:51:11 UTC**, reports full validation of all **29 bound members / 680,054,973 bytes**. The candidate files are recorded as uid/gid 0 and mode 0600. This receipt is attributed to its owner; no new Pocket4 readback was performed by this packaging step.

The same owner handoff reports that the global selected manifest and CURRENT were unchanged. It records pending adoption of the three exact bodies. Its separate retirement summary records removal of four complete duplicate APKs totalling 1,044,206,726 logical bytes after custody checks. Those are the owner's recorded actions and do not imply deletion of this review's scratch roots or closure of other cleanup gates.

## Independent complete Douyin stream and old Taobao route

The independent Mac stream from **10:15:55 to 10:33:02 UTC** completed all **364,363,658 bytes** in **1027.561 seconds**. Its SHA256 is the new `b1d883…` value above, which differs from historical candidate `c46bcb9274763d1ee48ff0932be53deb982e1b53dfce2e5afacd8825327b98b4`. The complete artifact result remains `CONTENT_MISMATCH` against that historical comparison; it is not rewritten to a historical match. Its equality with the new owner candidate is an additional, explicit reconciliation.

The supplied three pages reconstruct the full **7,169-byte** archive without gaps, SHA256 `b75382d76504c88bfef1e82a7b75a94d93d29162584d44ece565c6ef8eca1dc4`. All **34 JSON objects** were consumed, including the complete final record. Session `dpty-f6c05a1a3f1e1840e8e32f55c0b09130a1bbf192274b479cd26e290439e5925c` has a positive exit-0, complete-capture terminal. Exact byte ranges, raw-record hashes, page hashes and terminal identity are preserved in the new followup. The stream did not reparse a package manifest or verify a signature.

The earlier Taobao probe at `https://download.taobaocdn.com/wireless/taobao4android/latest/701483.apk` still records curl exit **35**, TLS internal alert, HTTP `000`, zero body bytes, and a reaped curl child. Its controller's exit 0 only records completion of that failed probe. The joint SZZC-script/Taobao archive is **1,285 bytes**, SHA256 `694a19927b1194a919e31d88c1c26ecdfc59580f049fec379f01093e67b148af`. The owner subsequently supplied the separately traced official route `https://download.alicdn.com/wireless/taobao4android/latest/taobao4android_703304.apk` and its complete inspected body. No TLS bypass or HTTP fallback is used to convert the old failure into success.

The ai395 prefix-probe session `dpty-ae429f22045eaa54c2db9792ee86cf6d80271c0e2660ea59a7831d85a19fb11e` remains **`launch_unknown`**, with no start acknowledgment and no returned result bytes. Its exact same-identity reconciliation remains unknown. No exit code, termination or remote side effect is inferred from the empty archive.

## Independent SZZC selector and bounded metadata evidence

The independent chain begins at the official page's footer/download-route QR images. Both QR images decode to `http://m.zuche.com/app/d?ozs=38054`; the observed request used the HTTPS version of that same host/path. Static parsing of the Android branch selects `https://static.zuchecdn.com/download/SZZC.apk`, whose observed HTTPS redirect leads to `https://edfs.zuchecdn.com/android-package/SZZC.apk`. The selector script was parsed, not executed. Exact public resource hashes, all six complete native archive identities and positive terminals are preserved in `szzc.source_documents.selector`.

The bounded APK-range observation declared `com.szzc`, **9.6.2 / 328**, min SDK 23, target SDK 33, and the two ABI directory names. The historical comparison was 9.6.1 / 327. The current object is **220,267,107 bytes**, **312,027 bytes smaller** than the historical 220,579,134-byte APK. A changed length alone was not used to infer a newer version; the version comparison comes from the parsed manifest.

The original strict parser stopped with **`signing_trailing_bytes`**, controller exit **2**, after four bounded ranges. That complete 3,596-byte archive, SHA256 `85478f54ac973bacd772c275628e010b834fd661c86ecd6cd2b89a4d1c20ca64`, remains a partial observation. It does not mean that Android rejected the publisher APK.

A separately authorized exact signing-block diagnostic read **4,121 additional bytes**: a 24-byte footer, the complete 4,096-byte public signing block, and a one-byte uncached validator. Including earlier ranges and the initial one-byte selector probe, APK response bytes total **1,118,866**, below the original 8 MiB aggregate cap. That diagnostic also exited **2** after reproducing the original parser failure; its complete archive is **3,854 bytes**, SHA256 `01159b238c854f57e357c5b5d76879339f2d1706b4e4577db3dc0571d35cd11d`. Both failures remain unchanged.

The actual fixture contains one additional empty length-prefixed element inside v2 `signedData`. The corrected local parser accepts only that exact four-zero-byte v2 representation. Nonempty, repeated, truncated, other-level, v3 and v3.1 trailing data remain rejected. The AOSP generator reference and its precise provenance limitation are preserved: the official file blob was observed, but the unavailable direct commit-pinned retrieval is not represented as an independent commit-to-blob proof.

The correction passes **13 normal and 13 optimized offline controls**, including the original failure and the exact 4,096-byte public fixture. It extracts the declared certificate digest `d85bed…`. **It performs no cryptographic signature verification or full-APK hashing.** Those stronger results come from the separately attributed, already published owner SZZC inspection above. The official QR chain and local parser observations strengthen provenance without creating another competing candidate.

The three compact SZZC documents are retained as exact UTF-8 strings inside `evidence.json`, each with its original byte count and SHA256. The original parser, exact patch and controls source are embedded once as bounded `zlib+base64` payloads. The corrected parser is rebuilt from the original plus a strict, no-fuzz two-hunk application, then checked against its exact final SHA256. The fixture uses the single payload already present in the signing document. No full APK or private signing material is included.

## Replaying the auxiliary signing parser

From this directory, the following reconstructs the auxiliary sources in a temporary directory and runs the existing 13 controls once normally and once with `-O`. Every embedded member and reconstructed current source is hash checked. The child controls deny network and nested process creation, and their complete outputs must match the already recorded receipt hashes. The temporary files are removed and both children reaped. This is an offline format-control replay, not APK acceptance.

```python
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

evidence_path = Path('evidence.json').resolve()
evidence = json.loads(evidence_path.read_bytes())
runner = evidence['followup_observations'][-1]['szzc']['offline_replay']['runner']
source = runner['text'].encode('utf-8')
if len(source) != runner['bytes'] or hashlib.sha256(source).hexdigest() != runner['sha256']:
    raise RuntimeError('embedded runner pin mismatch')
with tempfile.TemporaryDirectory(prefix='p4-app-replay-driver-') as directory:
    script = Path(directory) / 'replay_szzc_signing.py'
    script.write_bytes(source)
    subprocess.run([sys.executable, '-I', '-B', str(script), str(evidence_path)], check=True)
```

Packaging performed this replay from the embedded bytes, including reconstruction of the corrected 25,502-byte parser. Both modes reproduced the supplied 4,222-byte result exactly: normal SHA256 `a27c67f4684622e24fbb0e36c580f76cc289b75e6556856fece6522e8af2017d`, optimized SHA256 `b4c03d138e5d36050b30e030bb0b980220feb0b5ce9fe0aacd20bebd336937eb`.

## Historical evidence remains unchanged

The comparison target is the historical 42-app selected manifest observed at `2026-11-08T20:13:16Z`:

```text
/home/alex/work/pocket4-android-final/qualification/apps-content-bound-20261108-8b88-r1/update_inputs/final-selected42-production-candidates.json
134742 bytes
SHA256 73b7578fe2376f700edd68184ed6e16182bf4b58d3b5c75554a5c597f5f3a603
```

The latest published owner handoff says the global selector was unchanged while the new candidates were prepared. This addendum makes no later installation-census claim. The historical complete matches retain these values:

| App | Complete bytes | SHA256 | Completed UTC |
| --- | ---: | --- | --- |
| Beike | 228,933,721 | `c7985ed41b91c782af8acb04b1868419cca8bc1fc52862bf6c89fa86b65c81fb` | 2026-11-09 07:06:20.027719 |
| Pinduoduo | 32,690,199 | `3dbdcf5dcc94086dc0bc7d7f378fe1e328d9f32f30b82853fc8f440759d04ad4` | 2026-11-09 07:23:08.268136 |
| WeChat | 286,319,384 | `9d9b6c516e8e07e437c81485fde21fe13ce4f61b37d19e793fff40c71be39c0e` | 2026-11-09 07:48:34.132777 |

All original **11 fields** from the 35,149-byte historical evidence, SHA256 `b0227ce473c8c18e64287a738db90d37cdddaa996189d2770bc0896efa2e7d21`, remain equal. The old `followup_observations[0]` is also unchanged. Removing only the appended new followup reconstructs the complete **48,039-byte** previous evidence exactly, SHA256 `1a340bd618a1e798cf445a6536a4fda55ca40b792271ec888e6dbae115d19682`. Its original FILES hash is `c04399ef734fb70e5f88ee330a52396c49a70ca141be24e9d17fad87d4d7a9f9`.

Consequently, the top-level `summary` and `pending_packages` preserve their historical three-match/four-pending meaning. **Use `followup_observations[-1].summary` for the current integrated seven-package result.** The old pending rows are not silently rewritten or presented as the latest state.

Earlier failures and lifecycle limits remain intact:

- Beike's complete match appears in the supplied stdout prefix of job `1a1bf19eac2-5e21-3d3`; its shared controller later exited 124. The omitted tail is not claimed to be present.
- The original Pinduoduo attempt reported `UNQUALIFIED` after 27,574,272 bytes although its controller exited 0. A later complete match is separate evidence.
- Shared job `1a1bf2e653f-5e21-43f` exited 0 with a Pinduoduo match and incomplete WeChat/Douyin artifacts. Exit 0 does not promote those failures. The later WeChat complete record is in the supplied terminal tail; the omitted first page remains omitted.
- The eight-request Douyin attempt ended with controlled exit -15, 58,720,256 bytes in its last complete progress record and no full hash. Its 1,664-byte archive SHA256 is `9c0488c2d535c1d19bab130f54d9534fd18fb75ef65136b3bbe6e4d6e1a133db`.
- The earlier 32-request attempt reported `UNQUALIFIED` at 902.144 seconds after 351,272,960 of 364,363,658 bytes. Its complete final record and all 41 JSON objects remain bound to the 8,295-byte archive SHA256 `cf428cad3b07403163412afd59c97aa1b901e3d634c57f42b67d5ccf5d703342`. The later successful full stream does not change that failed operation.
- SZZC's earlier 1,771-byte SPA response and lack of a selector in that response remain recorded. The subsequent QR/route resolution is a new observation.

## Scope and storage

The independent range programs' 8 MiB or 32 MiB configured inflight payload capacities are not measured RSS or total-memory qualification. No memory or production gate is inferred from those configuration values.

This capsule contains evidence, auxiliary parser source, controls and one 4,096-byte public signing-block fixture. It contains no complete APK, credentials or private key. The source documents were supplied locally; packaging made no network or Pocket4 calls. The new 48,005-byte stream/probe input is SHA256 `09cb7342150dfa02fd39d151abe91bced03c47c576f6faec7a5cf723c22c465a`; the exact published-owner readback is 129,524 bytes / `f1760c42dc7fdadd3624a7c995e553b9f4fddaa55c62096de0f93779cde913b0`.

`evidence.json` uses UTF-8 JSON, sorted keys, compact separators and one trailing LF. Exact nested source-document strings preserve their original bytes. Large raw transport duplication, repeated progress records and whole APKs are excluded. `FILES.json` binds exactly `README.md` and `evidence.json`.
