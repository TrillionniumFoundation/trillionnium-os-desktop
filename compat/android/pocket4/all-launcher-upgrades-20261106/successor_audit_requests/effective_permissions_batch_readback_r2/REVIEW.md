# One fixed successful permission batch, private compressed readback

This source-only revision preserves the original per-file reader and the uncompressed batch candidate. It materializes one host-only request for microG's actual successful correction, not the failed original prefix. No process has been submitted by this preparer and no capture ledger has been claimed or changed.

## Fixed microG input

The independent joint linkage verifies original b01 success, original b02 FAILED/STOP, and correction job `1a1b2d790f2-fc05-7ffb` before preparing this readback. The two exact root-owned files are from that successful correction output directory:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `android-02.stdout` | 1,478,016 | `738586aac7aef5aafee12cc238bb0f70be69ba218d8b512b25fe168559dfab8d` |
| `android-03.stdout` | 1,478 | `2c636551a798d17ebcb17ca12440f7772d486b86af9f017683fba7ed0735118c` |

Total raw body size is 1,479,494 bytes. Only the first file has the corrected 2 MiB capture ceiling; AppOps retains 256 KiB. The reader has no CLI path parameter. It cannot read arbitrary root files, earlier prefixes or future service results.

`need`, `sha`, `canonical`, `read_file` and `read_host_pin` remain byte-identical to the actual successful Beike private reader. Each file is opened through retained nofollow directory descriptors; it must be a single-link root-owned regular file with the exact size and full SHA-256. The held file, newly opened final path and original full nine-field stat must agree after reading. All directory and file descriptors close in the original finally paths. The original whole-process count check remains explicit; this is not described as a whole-process descriptor-identity census.

## Compression and complete publication

The inner result retains each complete original body as hex with its exact pin, plus the complete reader outcome. Only after all per-file checks and the final FD count pass is that entire canonical result compressed with standard-library zlib level 9 and wrapped in the existing four-field `zlib-base64` envelope shape. The complete inner result has a fixed bound of 2 × actual body bytes + 32,768 bytes. The emitted compressed stdout is capped at 1 MiB. If that bound fails, no partial success envelope is emitted and the readback fails; the capture itself is not reclassified or retried.

The original host request's UID, nofollow reader, timeout 60 seconds, CPU 25%, memory 256 MiB and nice 10 are unchanged. No candidate executable, APK, Main process, action lock, namespace, UI or service is invoked by this reader.

The new local decoder requires the actual launched job to match the fixed source/request and key, then the authoritative durable success with exact complete stdout/empty stderr lengths and no truncation or log errors. It performs bounded decompression, rejects truncated or trailing compressed data, verifies the complete inner SHA, and rechecks every decoded service body's exact length and SHA. It refuses to overwrite existing decoded artifacts. It does not infer grants or roles.

## Private storage

For batch 02, complete process-read responses, complete compressed stdout and decoded bodies belong only under:

```text
/workspace/scratch/265e5bca485a/p4_private_ui/fixed45-permissions-compressed-readback-r2/batch-02/
```

Save the reconstructed exact stdout as `stdout.original.jsonl`. Save public start and terminal metadata under `batch-02/actual-public/start.original.txt` and `terminal.original.json`. Do not save the private stdout or process-read payloads in Git. The decoder can then run locally with the reviewed plan hash:

```text
python3 -B decode_private_readback.py --batch 2 --plan-sha256 <reviewed READBACK_PLAN SHA-256>
```

Only `READBACK_RECEIPT.derived.json` is public; it contains actual job/pins/counts and no service body. Semantic permission interpretation remains a separate later step. The existing Fcitx readback and actual derived permission record are reused; no second Fcitx request is generated.

## Later batches

`prepare_compressed_readback.py --batch N` supports only a batch that the full-joint capture gate already lists as completed. It creates a new source-only directory exclusively and emits one request for that batch's two-to-eight logs. Future source requests are not precreated and nothing is automatically submitted. Normal batches retain 256 KiB per file and at most 2 MiB total. The original failed b02 cannot qualify; only the specifically linked successful correction is accepted for that number. Later original failures or unknown captures cannot produce a reader.

Three local controls pass with zero skips and FD 4 → 4: actual microG pins and the five unchanged functions; a large synthetic codec fixture with corruption/truncation/trailing-data rejection; and rejection of an unobserved batch, the old failed job, arbitrary file paths and expanded AppOps budgets. The synthetic body is not permission evidence. No actual private body or device state was read by these controls.
