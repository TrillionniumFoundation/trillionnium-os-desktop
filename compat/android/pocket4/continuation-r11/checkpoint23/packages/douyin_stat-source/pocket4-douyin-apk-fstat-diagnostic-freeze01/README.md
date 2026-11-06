# Douyin single APK fstat diagnostic 01

Status: SOURCE_ONLY / UNRUN. Root is the sole dispatcher.

## Original observation

The complete failed metadata report is bound at 7852 bytes / bad61d846ce2c2b0e84964f94e34df898fab835db5e67597694583880c26d2bf. It observed UID 10122 and version 410001, then failed at the first held APK shape gate. Both prior PM reads returned 0, and the original Main guards, held binding, action lock and two data FDs closed. The report did not record the failed APK stat tuple, so the exact failed conjunct at that time remains UNKNOWN.

## New fixed observation

Only the one base.apk path from that complete original report is admitted. The reader holds the original current init identity, pidfd, six namespace descriptors and root. It opens each fixed APK ancestor and the leaf with O_PATH / O_NOFOLLOW, and exports complete fstat identity plus the seven original predicate booleans. Two observations and a final held/named recheck must agree.

A false old predicate does not make this diagnostic fail. It is the fact being measured. It never qualifies the old metadata operation, signer, APK content, installation, launch or business flow. Even if every current predicate is true, the historical failure remains unchanged.

The original R6 SourceContract/current8 guard and helper qualification are used without modifying shared source. The existing action lock is opened read-only, acquired once without waiting, and released in finally. No directory is enumerated. There is no APK content read, Android command, subprocess, namespace entry, file creation/write, or App nonce consumption.

Own descriptors are journaled before validation and closed once. A close error is preserved and never retried by descriptor number. R6's internal close failures propagate; the result explicitly does not claim whole-process ambient FD equality.

## Request and verification

exact-request.json is the exact request. Its stdin is the raw read_apk_metadata.py source, with full byte/SHA binding in transport.py; it does not stage files on Pocket4. Resource envelope: 256 MiB, CPU 100%, nice 15, 65 seconds. Observation admission ends at 30 seconds, final checks at 45 seconds, and self-alarm at 55 seconds.

Run the pure V8 function in reproduce.js with a mapping from archive-relative filenames to their complete UTF-8 strings. It rebuilds source, transport, request and proof byte for byte. The original-to-diagnostic.diff retains the complete original-to-new source comparison; source-semantics.json identifies the narrow operation change. Original metadata sources, request, stage, complete failure evidence and the reviewed R6 reference sources are preserved under references/.

No Python compilation, controls or device execution has been performed for this reader. Root must review and dispatch exactly once. Do not run the archived old metadata request.
