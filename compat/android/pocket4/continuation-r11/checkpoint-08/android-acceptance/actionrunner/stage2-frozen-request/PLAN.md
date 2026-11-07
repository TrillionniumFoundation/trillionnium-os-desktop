# ActionRunner stage 2: three fixed task roots

This is a separate, not-yet-submitted request. The completed first index is pinned by its exact 71,828-byte stdout SHA-256 `3191468e8cb1b36d464cf42f11a60e96b3a589f1d2174e70879d5ba23f6283b5`.

## Selected roots

| Root under `/home/alex/work` | Observed device / inode | Reason for selection |
| --- | --- | --- |
| `pocket4-app-production-20261103` | 66306 / 42644125 | Original application-control work period; previously located engineering runner receipt in this root. |
| `pocket4-app-production-20261104` | 66306 / 43542269 | Subsequent application-control work period before r10 acceptance. |
| `pocket4-source-publication-20261104-r10` | 66306 / 43681637 | Existing source-publication directory may identify the retained source inventory or archive. This is a search hypothesis, not a source-ownership claim. |

All nine recorded root metadata fields must equal the actual first-stage values before enumeration. Each root is opened relative to a held, no-follow `/home/alex/work` descriptor; metadata must remain unchanged through its index.

## Exact operation

Enumerate only the direct children of these three directories. Do not enter any discovered subdirectory. Report metadata for relevant action-runner, source-inventory, manifest, build-recipe, source-archive or action-APK names, plus unentered task subdirectories that are not excluded. Do not read or hash any file body, parse archives, or run a content grep.

Suppress data/cache/output/object/blob, commercial-flow, evidence, tombstone and journal directories; skip symlinks and special objects. Unmatched ordinary file names are not exported. Even a reported APK or archive receives metadata only.

Bounds are 512 admissible direct entries per root, 128 reported rows total, five seconds, and 128 KiB output. A limit, stale root, error or timeout preserves a failed/partial observation and does not expand the roots, descend, or retry. An overflow-detection entry does not receive further processing. The process runs under the existing operator at 25% CPU, 128 MiB, nice 10, and a 20-second outer limit.

## Next boundary

Use actual returned paths to choose exact small source/manifests for a separately reviewed bounded read, or a specific source subdirectory for a separately reviewed name search. This request does not qualify source ownership, bind the installed ActionRunner APK or signer, or authorize Android commands, instrumentation, UI, audio, launch/close, installation or data changes.

The source defaults to PLAN_ONLY. Local controls use only an owned temporary fixture and do not access these remote roots. The request has not been submitted.
