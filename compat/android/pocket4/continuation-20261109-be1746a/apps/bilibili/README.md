# Bilibili: complete official body, fresh signature verification and canonical custody

The official Android 64-bit download linked by `https://app.bilibili.com/index.html`
was fetched from `https://dl.hdslb.com/mobile/latest/android64/iBiliPlayer-bili.apk`.
The actual 2026-11-09 10:49–10:50 UTC generation received all 242,067,951 bytes
under one unchanged ETag and Last-Modified value. Its SHA256 is
`33b302b285bdbb5ee1e3030c5d65a88b8229ff3d7bbf78df105600e968109bfc`.
This exactly matches the historical content-bound selected APK.

New `aapt` and `apksigner verify --verbose --print-certs` executions both exited
zero. The delivered package is `tv.danmaku.bili`, version 9.18.0, code 9180300,
with arm64-v8a native libraries. APK signature schemes v2 and v3 verified. The
signer certificate SHA256 is
`93ba270f5521139ecafe4bb638ac5b1198bc548f62d9fd8f8580a079faf5910e`.
The complete new body and signer equal the historical selected identity; this
does not re-read the current installed Android package or qualify its execution.

`inspection.json` preserves the complete result, executed command identities and
every range digest. `custody.json` records the root-owned 0600 canonical APK at
`/home/alex/work/pocket4-android-final/cohorts/qpr1-cp3a-16176746-20261108-8b88-r1/official-app-inputs-be1746a-r3/bilibili-9.18.0-9180300-official.apk`.
The 29 download fragments and the 242,067,951-byte staging APK were retired.

A separate full readback verified all 11 manifest members, totaling 242,129,471
bytes, with stable identities and the same file hashes. Its canonical receipt is
`/home/alex/work/pocket4-android-final/qualification/parallel-continuation-20261109-be1746a-r1/bilibili-independent-readback.json`,
SHA256 `fdfcb6ce9653f3a4435c8c56a191ffff4e6345688256dcbb4a4de039c03e429f`.
`independent-readback.json` contains that result and its terminal observation.

The final selector stayed at SHA256
`73b7578fe2376f700edd68184ed6e16182bf4b58d3b5c75554a5c597f5f3a603`.
There were zero installations, selector changes or accepted runtime workflows.
The source claim is the APK returned by this publisher route at the recorded
observation, with no claim about every store, regional rollout or future update.
