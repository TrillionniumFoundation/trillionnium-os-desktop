# Pocket4 Native helper retirement and current successor observation

The obsolete private Tradefed helper build payloads were actually retired on ai395 at 2026-11-09 11:11:50 UTC. The exact H job `1a1c001baf4-5e21-860` completed successfully with durable complete output. `retirement-result.json` is the original remote receipt, not a planned cleanup.

## Exact retired scope

Only these four directories below `/home/qq/work/pocket4-native-source597-ai395-20261108-8b88-r1/native-tradefed-helper-be1746a-r1` were removed:

- `target`
- `cargo-home`
- `rustup`
- `tmp-r2` (empty-directory removal)

The receipt records 6,283 regular-file paths, 6,265 unique regular-file inodes and 1,614 directories removed. Unique inode logical bytes were 1,316,931,505; summing file paths counted 1,432,322,288 bytes. Physical disk blocks reclaimed were not measured and can differ due to hardlinks, reflinks and filesystem behavior.

Every root had its exact device/inode, uid/gid and mode rechecked. The complete candidate inventory rejected symlinks, mounts, unexpected member types and external hardlinks. A root process guard found no current consumer, the previously ambiguous PID was absent, and the complete 3,293,953-byte current r10 build input had no helper reference. Directory-fd operations with NOFOLLOW retired only the bound payloads. Six subprocesses exited normally and were reaped.

## Preserved custody

The source checkout, logs, qualification files and receipts remain. The source HEAD is `ff910cc50d842b5308b860340295bda44c28cf5a`, tracked state is clean, and the source lock remains `02fd330466357ecf744d85f27d23b03fabde46f31fae3ef69a5f6634e66e8837`. The before/after protected manifest is identical: 135,591 bytes, SHA256 `1d5c459a12d7e9e24c3f3527411b6cf4507c24a12d9cade7e85508962a4e3788`. Full manifests and the 180,067-byte gzip payload preinventory are retained under the helper's `retirement-be1746a-r1` evidence directory; their exact hashes are in the receipt. No owner recipe, working AOSP, global cache or CURRENT was changed.

`retire_exact_payloads.py` records the exact completed controller. It is evidence and must not be run by CI or replayed as a build or cleanup request. The four payloads are already absent. H retries must reconcile the original durable job identity, never launch a replacement cleanup generation.

## Latest actual Native generation

At 11:11:49 UTC, r10's inner unit was active/running and its outer H job `1a1bffe0c63-5e21-848` was also independently observed running. The inner InvocationID is `f272100976c84eef97a9c06b6ad4fc32`. The old READY file still says PREPARED_NOT_LAUNCHED; the live service and inner-started evidence supersede that historical preparation state. No r10 terminal existed at this sample.

The preceding r9 really ran and failed with `new recipe and tools belong to another actual import generation`; its owned unit was retired and the source projection was absent after recovery. The owner subsequently prepared the corrected r10 request. `native-current-observation.json` binds the exact observation, source input, earlier failure references and clean recipe-bcc snapshot. This capsule starts no build and grants no full-build, runtime or production qualification.
