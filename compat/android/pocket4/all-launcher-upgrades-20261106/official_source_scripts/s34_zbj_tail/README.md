# ZBJ s34 finite tail candidate — not executed

This is one explicit continuation of the settled s28 download failure. It creates only a new UID 1000 host directory:

`/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s34`

The source does not enter an Android namespace, acquire a Main lock, open a Main process descriptor, install an APK, operate UI, or change a permission. All candidate and runtime readiness states remain unqualified.

## Exact byte plan

The original 38,387,712-byte prefix plus s28 complete segment indices 0–40 (41 × 2,097,152 bytes) cover bytes 0–124,370,943. s28 index 41 failed with curl exit 18 after 147,456 bytes. That partial is excluded, including from the new tail offset.

The new plan covers inclusive range 124,370,944–166,873,621: 42,502,678 bytes in 41 sequential requests. The first 40 are 1,048,576 bytes each. The final request covers 166,313,984–166,873,621 and is 559,638 bytes. New indices have namespace S34_TAIL_1M_NO_CACHE and cannot be confused with the previous 2 MiB index namespace.

`RANGE_PROOF.json` is a static plan and a reference to the actual settled s28 receipt. It is not a download result.

## Reuse proof required during execution

The source pins the full s28 and s24 package results. Every s28 COMPLETE record is read from its fixed receipt path. Thirty-two reused records must point to the original pinned s24 receipt and match the original body path, stat, bytes, SHA-256, bounds and entity tag. The nine directly downloaded s28 complete records are validated in their own directory.

For every original network receipt, the source re-reads and hashes the original header, curl metrics and stderr. It requires return code 0, joined child, no timeout, one request, zero retries, exact URL, zero redirects, successful TLS verification, one HTTP 206 response, the exact Content-Range and complete actual body size. Content-Length, when supplied, must agree; absence does not replace the required exact actual byte count. All observed ETag lists must agree with the original prefix header. An absent ETag remains explicitly no server validator, not an invented validator.

The original prefix and 41 complete bodies are opened read-only, hashed, copied into a new file and held while assembling. Their identity and paths are checked before and after copying, and hashes are checked again before publication. Original files, failed partials and prior receipts are retained. No existing source file is written or removed.

## New requests and child lifetime

The official URL, Mozilla/5.0 user agent and TLS verification remain in force. Each request uses a standard Range, HTTPS-only protocols, identity content encoding, zero automatic retries, no redirect following, at most 25 seconds connecting and at most 180 seconds overall. Curl starts with `--disable` to avoid implicit per-user curl configuration, then the explicit original protocol settings.

There is one child at a time, two seconds between requests and a total 1,800-second worker budget including local validation and assembly. HTTP 403, HTTP 429, any Retry-After header, a short body, a mismatched response, a changed entity tag or an expired budget stops the sequence; subsequent ranges are recorded as skipped without starting a child. No new URL, proxy, DNS override, range size fallback or retry is selected.

Each started curl is held by its own fresh pidfd. Normal completion requires both join and pidfd exit observation. Timeout may signal that exact owned pidfd once, then join for at most ten seconds. It never signals a process group, arbitrary PID, Main process or old download process. If retirement cannot be proven, the result records outcome_unknown and does not publish a completed candidate. It does not conceal that state by closing or ignoring an unknown resource.

Only a completely assembled, rehashed 166,873,622-byte file is renamed to the new APK path. That result is `STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION`: source channel metadata says 9.5.20/code 370, but the APK must still pass real apksigner/vendor verification, package and manifest checks, ABI suitability and a fresh installed-version comparison. The historical installed reference is code 369; it is not a new device query. No install is authorized by a download receipt alone.

## Local controls and exact packet

Six controls ran locally under actual UID/EUID 1000 with no network or curl execution. They cover the actual s28 failed receipt and full new range coverage; exact response and refusal boundaries; a synthetic HTTP429 fixture produced by a real owned host child followed by no next child; normal child retirement; one owned pidfd timeout signal followed by join; and a same-bytes path replacement. Three real owned host children were joined and their pidfds closed. The whole process FD identity returned from 3 descriptors to the same 3.

The synthetic HTTP fixtures and local child PIDs are test evidence only. No claim is made about current Pocket4 files or a successful s34 transfer.

Current files are pinned by `SOURCE_PINS.json`. `S34_FROM_S28.patch` is the final review diff. The older `SOURCE_DIFF.patch` is an initial draft comparison and is not the frozen review diff. The original s28 source is retained as `base-s28.py`.

`process-request.json` is prepared for the existing durable process tool and has not been submitted by this agent. It uses the exact reviewed source via Python -B -I -c, UID 1000 (no sudo), timeout 2,100 seconds, CPU 100%, 512 MiB and nice 10. Its unique key is `pocket4-zbj-finite-tail-s34-20261106-r1`. Do not replay an unknown start; reconcile its durable job and receipts first.

Recreate the deterministic local packet and pins with:

```sh
python3 -B -I seal_s34_candidate.py
```

That command only reads these local source/evidence files and writes missing local packet artifacts. Existing artifacts must already have the same bytes. Running the candidate download is a separate root-coordinated action.

